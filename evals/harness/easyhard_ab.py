"""R281 — gold-scored easy/hard A/B runner (the ref-precision merge gate).

WHY THIS EXISTS
---------------
CLAUDE.md hard rule #6 makes the live pairwise ``evals.harness.ab_judge`` the
merge gate. That is right for answer-QUALITY changes and WRONG for a
reference-COUNT change, because ab_judge's refs axis cannot see precision:

    evals/harness/pairwise_prompts.py::render_refs asks which answer's prose
    "more faithfully describes the articles it cites ... and cites the
     load-bearing gold articles"

— faithfulness + RECALL, with no minimality term. Dropping a non-gold ref earns
nothing there; dropping a gold ref is punished. So that instrument rejects
every precision fix regardless of merit (this is exactly how R142.1's clamp
lost 11-0), and it CANNOT be the gate for this round.

The competition scores references against gold on two axes that DO reward
precision. Verbatim from ``docs/2026-eu-ai-act-competition-rules_official.pdf``:

    "references (list[str]): Should contain the minimal set of relevant
     references."
    "Is the answer sufficiently concise? ... Similarly, the amount of proposed
     references is checked against ground-truth ones."

This runner scores the gold-bearing probe set on exactly those axes
(``evals.bench.metrics``: reference_correctness_loose = recall,
_strict = F1, reference_conciseness = count-ratio) plus keyword recall + tone,
for two env arms, and reports the paired delta.

The R280 checkpoint's own hard-won lessons are built in:
  * PER-ROW CHECKPOINTING — R280's frontier runner was killed at 65/95 and
    wrote its sidecar only at the end, losing every row (recovered only by
    scraping stdout). Every row is appended to a .ckpt.jsonl as it lands.
  * NEVER run two wrapper-bound jobs concurrently — everything funnels to ONE
    local Claude Max; arms run SEQUENTIALLY, never in parallel.
  * NO ``?include_reasoning=true`` — it forces Stage-2 and distorts an eval
    comparison (R112).

HARD RULE #8 IS AN EXIT CODE (R365)
-----------------------------------
``gold_dropped_head`` used to be a SUM that this module PRINTED with a
``<-- GOLD DROPPED (hard rule #8)`` flag and then ignored: it is absent from
``_AXES`` and ``_LEVERAGE``, the module had no assert and no ``hard_fail``, its
only ``SystemExit``s were argparse errors, ``main()`` returned ``None``, and no
CI consumes it. So ``python -m evals.harness.easyhard_ab`` exited **0** on a run
whose branch arm deleted a gold reference, and every historical "it passed the
gold gate" claim was a human reading stdout — the same reports-but-never-
enforces defect this round found elsewhere.

It is now enforced. ``main()`` returns ``1`` when the branch arm drops MORE gold
heads than the baseline arm on ANY split, wired through
``raise SystemExit(main())``. The delta is read from the PAIRED subset where one
exists (the honest read when an arm loses rows) and from the full aggregate
otherwise. ``--allow-gold-drop`` forces exit 0 for a deliberate exploratory arm
and says so loudly; a run carrying that flag has NOT passed the gate. The
per-row ``gold_dropped_head_refs`` are printed so a failure is actionable.

The gate is comparative — a single-arm scorecard has nothing to compare against
and always exits 0.

HONESTY / SCOPE
---------------
* Ref Correctness LOOSE (recall) is the GUARD. The R142.1 failure mode is
  dropping gold. Any arm that reduces recall materially is rejected regardless
  of its F1 / conciseness gain.
* Two live LLM arms are NOT deterministic. This is a paired, gold-scored diff
  over n=132, not a pairwise judge — legitimate for a large ref-count effect,
  weak for a small prose effect. Report n and per-row deltas, never just means.
* Our probe gold is head-form; regenold's example gold is sub-point form
  (``["Annex IV.2","Article 3.1"]``). Head-level scoring is therefore the
  honest granularity here, and it is sound for this defect: the measured excess
  is 97% entirely NON-GOLD ARTICLES, which is a granularity-independent error.

USAGE
-----
    # baseline arm vs branch arm, live prod, sequential
    .venv/Scripts/python.exe -m evals.harness.easyhard_ab \\
        --endpoint https://<prod>/api/v1/regenold/eu-ai-act/ask \\
        --api-key $REGENOLD_API_KEY --label r281 \\
        --baseline-env REGENOLD_REF_MINIMALITY=0 \\
        --branch-env  REGENOLD_REF_MINIMALITY=1

    # single arm (a plain scorecard, e.g. to reproduce easyhard-r279-live)
    .venv/Scripts/python.exe -m evals.harness.easyhard_ab --local --label x

    # exit code 1 when the branch drops gold the baseline kept; add
    # --allow-gold-drop to let a deliberate exploratory arm finish anyway
    echo $?

EXIT CODES
----------
    0  PASS (or a deliberate --allow-gold-drop / --allow-void run)
    1  hard rule #8 violated — the branch dropped a gold head the baseline kept
    2  no live Stage-2 completion landed (the R398 liveness guard)
    3  VOID — the run cannot measure the lever (R413, see evals.harness.
       gate_validity): an arm was served by the FALLBACK transport, or a
       declared system-slot lever dispatched identical system payloads to both
       arms. The deltas are WITHHELD, not printed as zeros.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time
from pathlib import Path
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.harness import gate_validity
from evals.harness.probe_set import ProbeRow, load_probe_set

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"

# Marginal leverage on the official Overall (a plain geometric mean of the 8
# axes) at our operating point — pp of Overall per +1pp of the axis.
# Source: .planning/R276-PLAN.md (reproduces every reported figure to <0.05pp).
_LEVERAGE = {"ref_strict": 0.163, "ref_conc": 0.121, "ref_loose": 0.113}

# R398 — the minimum n per split below which the gate is INDETERMINATE.
#
# ⚠ This floor buys HONESTY, not POWER, and the distinction matters.  The
# recorded resolution threshold for the reference axes is n >= 120 (R367:
# "the REFERENCE axes do not resolve until n>=120"), and R381's cap=3
# simulation read PASS at n=17/30/34 and FAILED at n=129 — so 30 is a value
# at which the record shows a WRONG verdict was returned, not a safe one.
#
# It cannot be set to 120: the probe corpus tops out at easy=95 / hard=37
# rows (measured), so any floor above 37 makes the gate PERMANENTLY
# indeterminate.  30 is therefore the largest floor a full-corpus run still
# clears, and its whole job is to reject SMOKE runs (n=6, n=10) that used to
# print PASS with the same standing as a full one.  A run that clears this
# floor is not thereby powered — read the n before citing the verdict.
_MIN_GATE_N = 30


def _harden_streams() -> None:
    """The gold gate must never die of an encoding error.

    R398. Its exit code is load-bearing (1 = hard rule #8 violated), and an
    uncaught ``UnicodeEncodeError`` also exits non-zero — so a crash is
    indistinguishable from a FAIL, and it happens BEFORE the sidecar is
    written, leaving the run with no record at all. MEASURED: one "⚠" in a
    verdict print took the whole gate down on a cp1252 console.

    Gate output is kept ASCII (``test_the_gate_report_is_cp1252_safe``); this
    is the belt to that pair of braces. Called from ``main`` rather than at
    import, so importing the harness never reconfigures a caller's streams.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 — not a TextIOWrapper; nothing to harden
            pass


def _keyword_recall(answer: str, expected: list[str]) -> float:
    if not expected:
        return 1.0
    low = (answer or "").lower()
    return sum(1 for k in expected if k.lower() in low) / len(expected)


def _score_row(row: ProbeRow, answer: str, refs: list[str]) -> dict[str, Any]:
    gold = list(row.expected_refs or [])
    gd_head = bench_metrics.gold_dropped_head(refs, gold)
    return {
        "ref_loose": bench_metrics.reference_correctness_loose(refs, gold),
        "ref_strict": bench_metrics.reference_correctness_strict(refs, gold),
        "ref_conc": bench_metrics.reference_conciseness(refs, gold),
        "tone": bench_metrics.regulatory_tone(answer),
        "kw_recall": _keyword_recall(answer, list(row.expected_keywords or [])),
        "gold_dropped_head": float(gd_head["dropped_count"]),
        "gold_dropped_head_gold_count": float(gd_head["gold_count"]),
        "gold_dropped_head_refs": gd_head["dropped_refs"],
    }


_AXES = ("ref_loose", "ref_strict", "ref_conc", "tone", "kw_recall")


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if not r.get("error")]
    if not ok:
        return {"n": 0, "errors": len(rows)}
    out: dict[str, Any] = {"n": len(ok), "errors": len(rows) - len(ok)}
    for a in _AXES:
        out[a] = st.mean(r["scores"][a] for r in ok)
    lat = sorted(r["latency_ms"] for r in ok)
    out["latency_p50_ms"] = lat[len(lat) // 2]
    out["latency_p90_ms"] = lat[int(len(lat) * 0.9)] if len(lat) > 1 else lat[0]
    n_pred = sum(len(bench_metrics.article_heads(r["pred_refs"])) for r in ok)
    n_gold = sum(len(bench_metrics.gold_ref_set(r.get("gold_refs"))) for r in ok)
    out["pred_gold_ratio"] = (n_pred / n_gold) if n_gold else 0.0
    # R332 — gold_dropped_head is a SUM (not mean) so the gate is "drop ZERO".
    # .get(..., 0) backward-compat: pre-R332 .ckpt.jsonl rows lack the key.
    out["gold_dropped_head"] = sum(
        int(r["scores"].get("gold_dropped_head", 0)) for r in ok
    )
    out["gold_dropped_head_gold_count"] = sum(
        int(r["scores"].get("gold_dropped_head_gold_count", 0)) for r in ok
    )
    return out


def _run_arm(
    probe: list[ProbeRow],
    *,
    endpoint: str | None,
    api_key: str | None,
    local: bool,
    timeout: float,
    arm_env: dict[str, str],
    ckpt_path: Path,
) -> list[dict[str, Any]]:
    """Run every probe row under `arm_env`. Appends each row to `ckpt_path`."""
    # Apply the arm env BEFORE the first request. Route-level flags are read
    # fresh per call; engine/import-time settings are NOT A/B-able in-process
    # (the R271 gotcha) — the caller is responsible for choosing an in-proc-safe
    # flag or running two processes.
    saved: dict[str, str | None] = {}
    for k, v in arm_env.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v

    # Import transports lazily so --endpoint mode keeps a lean import surface.
    from evals.regenold.runner_v2 import _post, _post_local

    poster = _post_local if local else _post
    url = "local://app.main:app/api/v1/regenold/eu-ai-act/ask" if local else str(endpoint)

    rows: list[dict[str, Any]] = []
    ckpt = ckpt_path.open("a", encoding="utf-8")
    try:
        for i, pr in enumerate(probe, 1):
            history = [dict(m) for m in pr.messages]
            body, latency_ms, status, err, attempts, _retried = poster(
                url, api_key, history, timeout
            )
            answer = str((body or {}).get("answer") or "")
            refs = list((body or {}).get("references") or [])
            rec: dict[str, Any] = {
                "id": pr.id,
                "source": pr.source,
                "category": pr.category,
                "is_multiturn": pr.is_multiturn,
                "pred_answer": answer,
                "pred_refs": refs,
                "gold_refs": list(pr.expected_refs or []),
                "expected_keywords": list(pr.expected_keywords or []),
                "latency_ms": latency_ms,
                "http_status": status,
                "attempts": attempts,
                "answer_chars": len(answer),
            }
            if err or not answer:
                rec["error"] = err or "empty_answer"
            else:
                rec["scores"] = _score_row(pr, answer, refs)
            rows.append(rec)
            # R280 lesson: checkpoint EVERY row immediately — a killed run
            # must not lose its work.
            ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ckpt.flush()
            tag = "ERR " if rec.get("error") else "ok  "
            print(
                f"  [{i:3d}/{len(probe)}] {tag}{pr.id:<34} "
                f"{latency_ms/1000:6.1f}s refs={len(refs):2d}",
                flush=True,
            )
    finally:
        ckpt.close()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return rows


def _split(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "easy": [r for r in rows if not r["is_multiturn"]],
        "hard": [r for r in rows if r["is_multiturn"]],
    }


def _report(label: str, base: dict[str, Any], branch: dict[str, Any] | None) -> None:
    for split in ("easy", "hard"):
        b = base.get(split) or {}
        if not b.get("n"):
            continue
        if branch is None:
            print(f"\n=== {label} — {split} (n={b['n']}, errors={b['errors']}) ===")
            for a in _AXES:
                print(f"  {a:<12}{b[a]:>9.4f}")
            print(f"  {'pred:gold':<12}{b['pred_gold_ratio']:>9.2f}")
            print(
                f"  {'gold_drop_hd':<12}"
                f"{int(b.get('gold_dropped_head', 0)):>4d} of "
                f"{int(b.get('gold_dropped_head_gold_count', 0))} gold heads"
            )
            print(f"  {'latency p50':<12}{b['latency_p50_ms']/1000:>9.1f}s")
            continue
        c = branch.get(split) or {}
        if not c.get("n"):
            print(f"\n=== {label} — {split} (baseline n={b['n']} | branch n=0 err={c.get('errors', 0)}) ===")
            print("  [Branch arm produced 0 successful rows; skipping comparison]")
            continue
        # Show BOTH arms' error counts (the R282 trap: printing only the
        # baseline's hides a branch arm that 429'd out half its rows).
        warn = ""
        if b.get("n", 0) != c.get("n", 0):
            warn = ("\n  !! ARM ROW COUNTS DIFFER — the FULL-aggregate deltas "
                    "below span DIFFERENT row sets and are NOT comparable; "
                    "trust the PAIRED block")
        print(
            f"\n=== {label} — {split} FULL-AGG "
            f"(baseline n={b['n']} err={b['errors']} "
            f"| branch n={c.get('n', 0)} err={c.get('errors', 0)}){warn} ==="
        )
        print(f"  {'axis':<12}{'baseline':>10}{'branch':>10}{'delta':>10}")
        for a in _AXES:
            d = c[a] - b[a]
            flag = ""
            if a == "ref_loose" and d < -0.005:
                flag = "  <-- GOLD LOSS (R142.1 failure mode)"
            print(f"  {a:<12}{b[a]:>10.4f}{c[a]:>10.4f}{d:>+10.4f}{flag}")
        print(
            f"  {'pred:gold':<12}{b['pred_gold_ratio']:>10.2f}"
            f"{c['pred_gold_ratio']:>10.2f}"
            f"{c['pred_gold_ratio']-b['pred_gold_ratio']:>+10.2f}"
        )
        gd_h_delta = c.get("gold_dropped_head", 0) - b.get("gold_dropped_head", 0)
        gd_h_flag = "  <-- GOLD DROPPED (hard rule #8)" if gd_h_delta > 0 else ""
        print(
            f"  {'gold_drop_hd':<12}{int(b.get('gold_dropped_head', 0)):>10d}"
            f"{int(c.get('gold_dropped_head', 0)):>10d}"
            f"{gd_h_delta:>+10d}{gd_h_flag}"
        )
        print(
            f"  {'lat p50 s':<12}{b['latency_p50_ms']/1000:>10.1f}"
            f"{c['latency_p50_ms']/1000:>10.1f}"
            f"{(c['latency_p50_ms']-b['latency_p50_ms'])/1000:>+10.1f}"
        )
        uplift = sum(
            _LEVERAGE[a] * (c[a] - b[a]) * 100.0 for a in _LEVERAGE if a in c
        )
        print(f"  => est. Overall uplift from the 3 reference axes: {uplift:+.2f} pp")
        print("  [lat p50 above is confounded when a shared engine cache warms "
              "the 2nd arm — not a product signal in A/B mode]")


def _paired(
    a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Per-split aggregates over rows that scored OK in BOTH arms.

    A live A/B where one arm loses rows (e.g. wrapper 429s) leaves the two
    full-arm aggregates spanning DIFFERENT row sets, so their per-axis means
    are not comparable — the R282 run hit exactly this and a hand-salvaged
    n=59 paired subset was the only honest read. This computes that subset
    automatically: the intersection of ids scored OK in both arms.
    """
    bmap = {r["id"]: r for r in b_rows}
    out: dict[str, Any] = {}
    for split, is_hard in (("easy", False), ("hard", True)):
        common: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for ra in a_rows:
            if bool(ra["is_multiturn"]) != is_hard:
                continue
            if ra.get("error") or not ra.get("scores"):
                continue
            rb = bmap.get(ra["id"])
            if rb is None or rb.get("error") or not rb.get("scores"):
                continue
            common.append((ra, rb))
        if not common:
            out[split] = {"n": 0}
            continue
        agg: dict[str, Any] = {"n": len(common)}
        for arm, idx in (("baseline", 0), ("branch", 1)):
            m: dict[str, float] = {
                a: st.mean(pair[idx]["scores"][a] for pair in common)
                for a in _AXES
            }
            n_pred = sum(
                len(bench_metrics.article_heads(pair[idx]["pred_refs"]))
                for pair in common
            )
            n_gold = sum(
                len(bench_metrics.gold_ref_set(pair[idx].get("gold_refs")))
                for pair in common
            )
            m["pred_gold_ratio"] = (n_pred / n_gold) if n_gold else 0.0
            # R332 — paired-subset gold_dropped (SUM over common rows).
            m["gold_dropped_head"] = sum(
                int(pair[idx]["scores"].get("gold_dropped_head", 0))
                for pair in common
            )
            m["gold_dropped_head_gold_count"] = sum(
                int(pair[idx]["scores"].get("gold_dropped_head_gold_count", 0))
                for pair in common
            )
            agg[arm] = m
        agg["uplift_pp"] = sum(
            _LEVERAGE[a] * (agg["branch"][a] - agg["baseline"][a]) * 100.0
            for a in _LEVERAGE
        )
        out[split] = agg
    return out


def _report_paired(
    label: str,
    paired: dict[str, Any],
    void_reasons: tuple[str, ...] = (),
) -> None:
    """Print the paired deltas — or REFUSE to, when the run is void.

    R413. A void run's deltas are indistinguishable from a real null (the R412
    95+95 pair that showed no effect at all was void: Bedrock served both arms
    while the tunnel was down). The refusal lives HERE, at the reporting site,
    so every caller inherits it rather than each remembering to check.
    """
    if void_reasons:
        print(f"\n=== {label} — PAIRED DELTAS WITHHELD (VOID RUN) ===")
        for reason in void_reasons:
            print(f"  VOID: {reason}")
        print("  A delta table from this run would read exactly like a real null.")
        return
    printed = False
    for split in ("easy", "hard"):
        p = paired.get(split) or {}
        if not p.get("n"):
            continue
        printed = True
        b, c = p["baseline"], p["branch"]
        print(f"\n=== {label} — {split} PAIRED "
              f"(n={p['n']}, scored OK in BOTH arms) ===")
        print(f"  {'axis':<12}{'baseline':>10}{'branch':>10}{'delta':>10}")
        for a in _AXES:
            d = c[a] - b[a]
            flag = ""
            if a == "ref_loose" and d < -0.005:
                flag = "  <-- GOLD LOSS (R142.1 failure mode)"
            print(f"  {a:<12}{b[a]:>10.4f}{c[a]:>10.4f}{d:>+10.4f}{flag}")
        print(
            f"  {'pred:gold':<12}{b['pred_gold_ratio']:>10.2f}"
            f"{c['pred_gold_ratio']:>10.2f}"
            f"{c['pred_gold_ratio'] - b['pred_gold_ratio']:>+10.2f}"
        )
        gd_h_delta = c.get("gold_dropped_head", 0) - b.get("gold_dropped_head", 0)
        gd_h_flag = "  <-- GOLD DROPPED (hard rule #8)" if gd_h_delta > 0 else ""
        print(
            f"  {'gold_drop_hd':<12}{int(b.get('gold_dropped_head', 0)):>10d}"
            f"{int(c.get('gold_dropped_head', 0)):>10d}"
            f"{gd_h_delta:>+10d}{gd_h_flag}"
        )
        print(f"  => est. Overall uplift (leverage-weighted 3 ref axes): "
              f"{p['uplift_pp']:+.2f} pp")
    if printed:
        print("  [PAIRED is the honest A/B read; latency is omitted here — the "
              "2nd arm runs on a warm shared cache, not a product signal]")


# ---------------------------------------------------------------------------
# R365 — hard rule #8 as an ENFORCED gate, not a printed flag.
# ---------------------------------------------------------------------------

_GOLD_GATE_BANNER = "!" * 72


def _split_gold_dropped(agg: dict[str, Any] | None, split: str) -> int | None:
    """``gold_dropped_head`` for one split, or None when the split has no rows.

    None means "not comparable" — an arm that produced 0 successful rows for a
    split cannot be said to have dropped gold; it dropped everything, and the
    row-count warning in ``_report`` is the signal for that, not this gate.
    """
    if not agg:
        return None
    s = agg.get(split) or {}
    if not s.get("n"):
        return None
    return int(s.get("gold_dropped_head", 0))


def _gold_gate_verdict(
    base_agg: dict[str, Any] | None,
    branch_agg: dict[str, Any] | None,
    allow: bool = False,
    paired: dict[str, Any] | None = None,
    expected_splits: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Decide hard rule #8 from aggregates alone — no live run required.

    The rule is "drop ZERO **more** than the baseline". It is comparative, so a
    single-arm scorecard (``branch_agg is None``) always passes: there is no
    baseline to have regressed against.

    Delta source, per split: the PAIRED subset when it exists (the honest read
    when one arm loses rows — see ``_paired``), the full aggregate otherwise.

    Failing on ANY split, rather than on the cross-split sum, is deliberate:
    a sum lets an easy-split improvement mask a hard-split gold deletion, and
    the rule is zero, not net-zero.

    R398 — three outcomes, not two. ``exit_code`` 1 = FAIL, 2 = INDETERMINATE,
    0 = PASS. A verdict is indeterminate when a scored split is below
    ``_MIN_GATE_N``, or when a split the probe corpus actually contained
    produced no scored rows at all: ``easyhard-v2_ab_gate.json`` (easy n=10,
    hard n=0) and ``easyhard-r379-promptv2-bedrock.json`` (n=132) sat on disk
    for the SAME flag with equal standing, one PASS and one FAIL.

    ``expected_splits`` is what the loaded probe set contained. A run scoped
    with ``--multiturn only|skip`` legitimately carries one split, so the
    omitted one is not held against it; a split that WAS in the corpus and
    scored zero rows is a silent hole and is reported as such.

    ``--allow-gold-drop`` suppresses a FAILURE only. Indeterminacy is a
    statement about the evidence, not about whether the operator is willing
    to accept a gold drop, so it survives the flag.
    """
    splits: dict[str, dict[str, Any]] = {}
    for split in ("easy", "hard"):
        p = (paired or {}).get(split) or {}
        if p.get("n"):
            b = int((p.get("baseline") or {}).get("gold_dropped_head", 0))
            c = int((p.get("branch") or {}).get("gold_dropped_head", 0))
            src, n = "paired", int(p["n"])
        else:
            b_val = _split_gold_dropped(base_agg, split)
            c_val = _split_gold_dropped(branch_agg, split)
            if b_val is None or c_val is None:
                continue
            b, c, src = b_val, c_val, "full"
            n = int(((branch_agg or {}).get(split) or {}).get("n", 0))
        splits[split] = {
            "n": n, "baseline": b, "branch": c, "delta": c - b, "source": src,
        }

    comparable = bool(splits) and branch_agg is not None
    offenders = [k for k in ("easy", "hard") if splits.get(k, {}).get("delta", 0) > 0]
    failed = comparable and bool(offenders)

    # R398 — refuse to emit a verdict below the minimum n.  A run with
    # n=10 PASS and n=132 FAIL for the SAME flag sat on disk with equal
    # standing; the gate must not be binary on an underpowered sample.
    underpowered = [
        f"{split} (n={splits[split]['n']})"
        for split in ("easy", "hard")
        if split in splits and 0 < splits[split]["n"] < _MIN_GATE_N
    ]

    # R398 — and refuse to SKIP a split silently.  ``_split_gold_dropped``
    # returns None for an unscored split, which drops it out of ``splits``
    # entirely, so hard rule #8's "zero on ANY split" quietly became "zero on
    # the splits that happened to score".  Only splits the corpus actually
    # carried are held against the run.
    unscored = [
        split
        for split in (expected_splits or ())
        if split in ("easy", "hard") and not splits.get(split, {}).get("n")
    ]

    # Decide exit code: 1 = failed, 2 = indeterminate, 0 = passed.
    indeterminate = bool(underpowered) or bool(unscored)
    if failed and not allow:
        exit_code = 1
    elif comparable and indeterminate:
        exit_code = 2
    else:
        exit_code = 0

    return {
        "comparable": comparable,
        "splits": splits,
        "total_delta": sum(v["delta"] for v in splits.values()),
        "offending_splits": offenders,
        "failed": failed,
        "allow_gold_drop": bool(allow),
        "suppressed_by_flag": failed and bool(allow),
        "exit_code": exit_code,
        "underpowered": underpowered,
        "unscored_splits": unscored,
        "indeterminate": bool(comparable and indeterminate),
    }



def _merged_transport_stats(*provs: Any) -> dict[str, Any]:
    """Sum per-arm transport snapshots back into one run-level view.

    R413 resets the process-global counters once per ARM (so provenance is
    attributable), which breaks the older assumption that the counters carry the
    whole run. The R398 liveness guard is run-level, so it is handed the sum.
    """
    out: dict[str, Any] = {}
    for prov in provs:
        stats = getattr(prov, "stats", None) or {}
        for key, value in stats.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                out[key] = int(out.get(key, 0)) + value
            elif isinstance(value, dict):
                merged = dict(out.get(key) or {})
                for k, v in value.items():
                    merged[k] = int(merged.get(k, 0)) + int(v or 0)
                out[key] = merged
            elif key == "_error" and value:
                out.setdefault(key, value)
    return out


def _transport_liveness(
    *, local: bool, stats: dict[str, Any] | None = None
) -> tuple[bool, str]:
    """Did Stage-2 actually land? Returns ``(live, human-readable reason)``.

    R398. The counters are ``app.llm.stage2_policy.transport_stats`` — the
    single source of truth the R360 contract instrumented, and the same one
    ``/healthz/llm`` and ``evals.harness.prompt_ab`` read. A ``--endpoint``
    run drives a REMOTE server, whose counters are not in this process, so
    liveness there is the caller's to assert.

    Never raises: a liveness probe must not be able to take down the gate it
    is protecting. But it never fails SILENT either — an import failure is
    reported as such rather than being laundered into "not live".
    """
    if not local:
        return True, "remote --endpoint run; liveness is the caller's assertion"
    if stats is None:
        try:
            from app.llm.stage2_policy import transport_stats  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            return False, (
                f"could not import app.llm.stage2_policy.transport_stats ({exc!r}) - "
                "liveness UNKNOWN, treated as not live"
            )
        try:
            stats = transport_stats()
        except Exception as exc:  # noqa: BLE001
            return False, f"transport_stats() raised ({exc!r}) - liveness UNKNOWN"
    try:
        ok = int(stats.get("primary_ok", 0) or 0)
        fb = int(stats.get("fallback_ok", 0) or 0)
    except Exception as exc:  # noqa: BLE001
        return False, f"transport snapshot unreadable ({exc!r}) - liveness UNKNOWN"
    if ok or fb:
        return True, f"live: primary_ok={ok} fallback_ok={fb}"
    return False, (
        f"primary_ok={ok} fallback_ok={fb} - no live Stage-2 completions landed. "
        "Rerun against a live wrapper for a valid verdict."
    )


def _gold_drop_rows(
    a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-row gold heads the branch dropped that the baseline kept.

    Only rows scored OK in BOTH arms are compared: an errored row carries no
    refs at all and would otherwise read as a total gold wipe-out.
    """
    bmap = {r.get("id"): r for r in b_rows}
    out: list[dict[str, Any]] = []
    for ra in a_rows:
        rb = bmap.get(ra.get("id"))
        if rb is None:
            continue
        sa, sb = ra.get("scores"), rb.get("scores")
        if ra.get("error") or rb.get("error") or not sa or not sb:
            continue
        base_dropped = [str(x) for x in (sa.get("gold_dropped_head_refs") or [])]
        branch_dropped = [str(x) for x in (sb.get("gold_dropped_head_refs") or [])]
        newly = sorted(set(branch_dropped) - set(base_dropped))
        if not newly and len(branch_dropped) <= len(base_dropped):
            continue
        out.append(
            {
                "id": ra.get("id"),
                "split": "hard" if ra.get("is_multiturn") else "easy",
                "gold_refs": list(ra.get("gold_refs") or []),
                "baseline_refs": list(ra.get("pred_refs") or []),
                "branch_refs": list(rb.get("pred_refs") or []),
                "baseline_dropped": base_dropped,
                "branch_dropped": branch_dropped,
                "newly_dropped": newly,
            }
        )
    return out


def _report_gold_gate(
    verdict: dict[str, Any],
    offenders: list[dict[str, Any]],
) -> None:
    if not verdict.get("comparable"):
        return
    print("\n=== HARD RULE #8 GATE — gold heads dropped (branch vs baseline) ===")
    for split in ("easy", "hard"):
        v = verdict["splits"].get(split)
        if not v:
            continue
        print(
            f"  {split:<6} n={v['n']:<5} baseline={v['baseline']:<5}"
            f" branch={v['branch']:<5} delta={v['delta']:+d}   [{v['source']}]"
        )
    if offenders:
        print(
            f"\n  {len(offenders)} row(s) where the branch dropped a gold head "
            f"the baseline kept:"
        )
        for o in offenders:
            print(f"    - {o['id']}  ({o['split']})")
            print(f"        gold           : {o['gold_refs']}")
            print(
                f"        baseline refs  : {o['baseline_refs']}"
                f"   dropped={o['baseline_dropped']}"
            )
            print(
                f"        branch   refs  : {o['branch_refs']}"
                f"   dropped={o['branch_dropped']}"
            )
            print(f"        NEWLY DROPPED  : {o['newly_dropped']}")
    # R398 — an indeterminate run must NOT also print PASS. R365's whole
    # finding was that "it passed the gold gate" had only ever been a human
    # reading stdout; a stdout that says PASS while the process exits 2 is the
    # same defect wearing a new exit code.
    reasons: list[str] = []
    if verdict.get("underpowered"):
        reasons.append(
            f"UNDERPOWERED: {', '.join(verdict['underpowered'])} - below minimum "
            f"n={_MIN_GATE_N}. This floor only rejects smoke runs; clearing it "
            f"is not power (the ref axes need n>=120, the corpus holds 95/37)."
        )
    if verdict.get("unscored_splits"):
        reasons.append(
            f"UNSCORED SPLIT(S): {', '.join(verdict['unscored_splits'])} - the "
            "probe corpus carried rows for them and none scored. Hard rule #8 "
            "is 'zero on ANY split', so this run does not clear those."
        )
    if verdict.get("liveness_failed"):
        reasons.append(
            "LIVENESS FAILED: no Stage-2 completions landed. Both arms returned "
            "deterministic answers, so delta=0 is tautological, not evidence."
        )
    if reasons and not verdict["failed"]:
        print(f"\n  {_GOLD_GATE_BANNER}")
        print("  !! INDETERMINATE - this run does NOT clear hard rule #8.")
        for reason in reasons:
            print(f"  !! {reason}")
        print("  !! Do NOT cite this run as having passed the gold gate.")
        print(f"  {_GOLD_GATE_BANNER}")
        return
    if reasons:
        for reason in reasons:
            print(f"\n  !! {reason}")
    if not verdict["failed"]:
        print("\n  PASS — the branch drops no more gold heads than the baseline.")
        return
    where = ", ".join(verdict["offending_splits"]) or "?"
    if verdict["suppressed_by_flag"]:
        print(f"\n  {_GOLD_GATE_BANNER}")
        print(f"  !! HARD RULE #8 VIOLATED on split(s): {where}"
              f"  (total delta {verdict['total_delta']:+d})")
        # R398 — say the exit code this run ACTUALLY carries. --allow-gold-drop
        # suppresses the FAILURE, but an underpowered or unscored run is still
        # indeterminate (exit 2), and printing "forced to 0" there would be the
        # same stdout-contradicts-exit-code defect one branch over.
        if verdict.get("exit_code") == 2:
            print("  !! THIS RUN WOULD HAVE FAILED. --allow-gold-drop suppresses "
                  "the failure,")
            print("  !! but the run is INDETERMINATE on other grounds and exits 2.")
        else:
            print("  !! THIS RUN WOULD HAVE FAILED. Exit code forced to 0 by "
                  "--allow-gold-drop.")
        print("  !! An --allow-gold-drop run is EXPLORATORY. Do NOT cite it as "
              "having")
        print("  !! passed the gold gate.")
        print(f"  {_GOLD_GATE_BANNER}")
        return
    print(f"\n  {_GOLD_GATE_BANNER}")
    print("  !! FAIL — HARD RULE #8: the branch arm dropped MORE gold heads "
          "than the")
    print(f"  !! baseline on split(s): {where}  "
          f"(total delta {verdict['total_delta']:+d})")
    print("  !! The gate is literally 'drop ZERO'. Exiting NON-ZERO (1).")
    print("  !! Re-run with --allow-gold-drop for a deliberate exploratory arm.")
    print(f"  {_GOLD_GATE_BANNER}")


def _parse_env(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--*-env expects KEY=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--endpoint", help="live ask URL")
    ap.add_argument("--local", action="store_true", help="in-process TestClient")
    ap.add_argument("--api-key")
    ap.add_argument("--label", required=True)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--multiturn", choices=("only", "skip"))
    ap.add_argument("--baseline-env", action="append")
    ap.add_argument("--branch-env", action="append")
    ap.add_argument(
        "--allow-gold-drop",
        action="store_true",
        help=(
            "EXPLORATORY ONLY. Let the run exit 0 even when the branch arm "
            "drops more gold heads than the baseline (hard rule #8). The "
            "violation is still printed, loudly. A run carrying this flag has "
            "NOT passed the gold gate and must not be reported as having done "
            "so."
        ),
    )
    lever_group = ap.add_mutually_exclusive_group()
    lever_group.add_argument(
        "--lever-changes-system", dest="lever_changes_system", action="store_true",
        default=None,
        help=(
            "Declare that this lever edits the Stage-2 SYSTEM payload. R413 "
            "then VOIDS the run when both arms dispatch an identical system "
            "payload — an inert lever reads exactly like a null otherwise. "
            "Default: inferred from the arm envs (see gate_validity."
            "SYSTEM_SLOT_FLAGS)."
        ),
    )
    lever_group.add_argument(
        "--no-lever-changes-system", dest="lever_changes_system",
        action="store_false",
        help="Declare that this lever does NOT edit the system payload.",
    )
    ap.add_argument(
        "--allow-void",
        action="store_true",
        help=(
            "EXPLORATORY ONLY. Let the run exit 0 on a VOID run. The VOID "
            "banner and the withheld-deltas notice are still printed: a run "
            "carrying this flag produced no measurement of the lever."
        ),
    )
    args = ap.parse_args()
    _harden_streams()

    if not args.local and not args.endpoint:
        raise SystemExit("need --endpoint or --local")

    mt = None
    if args.multiturn == "only":
        mt = True
    elif args.multiturn == "skip":
        mt = False
    probe = load_probe_set(multiturn=mt, limit=args.limit)
    print(f"probe rows: {len(probe)} (easy={sum(1 for p in probe if not p.is_multiturn)}, "
          f"hard={sum(1 for p in probe if p.is_multiturn)})")

    # R398 — the splits this run could possibly score. A split the corpus
    # carried but that scored zero rows is a hole; a split the corpus never
    # carried (--multiturn only|skip, or a small --limit) is not.
    expected_splits = tuple(
        s for s, present in (
            ("easy", any(not p.is_multiturn for p in probe)),
            ("hard", any(p.is_multiturn for p in probe)),
        ) if present
    )

    # R398 — zero the transport counters so the liveness guard reads THIS
    # run. They are process-global; anything that dialled Stage-2 at import
    # time would otherwise hand the gate a stale green.
    try:
        from app.llm.stage2_policy import reset_transport_stats  # noqa: PLC0415

        reset_transport_stats()
    except Exception:  # noqa: BLE001 — reported by _transport_liveness later
        pass

    _RESULTS.mkdir(parents=True, exist_ok=True)
    base_env = _parse_env(args.baseline_env)
    branch_env = _parse_env(args.branch_env)

    print(f"\n### ARM A (baseline) env={base_env or '{}'}")
    # R413 — each arm's transport leg and dispatched payloads are captured per
    # arm, so a fallback-served arm can be named instead of averaged in.
    with gate_validity.ArmProbe("baseline") as probe_a:
        a_rows = _run_arm(
            probe, endpoint=args.endpoint, api_key=args.api_key, local=args.local,
            timeout=args.timeout, arm_env=base_env,
            ckpt_path=_RESULTS / f"easyhard-{args.label}-A.ckpt.jsonl",
        )
    a_prov = probe_a.provenance(rows=a_rows)
    a_agg = {k: _aggregate(v) for k, v in _split(a_rows).items()}

    b_agg = None
    b_rows: list[dict[str, Any]] = []
    b_prov = None
    if branch_env:
        # SEQUENTIAL by construction — both arms hairpin to ONE local Claude
        # Max; concurrent wrapper jobs corrupt each other's latency.
        print(f"\n### ARM B (branch) env={branch_env}")
        with gate_validity.ArmProbe("branch") as probe_b:
            b_rows = _run_arm(
                probe, endpoint=args.endpoint, api_key=args.api_key, local=args.local,
                timeout=args.timeout, arm_env=branch_env,
                ckpt_path=_RESULTS / f"easyhard-{args.label}-B.ckpt.jsonl",
            )
        b_prov = probe_b.provenance(rows=b_rows)
        b_agg = {k: _aggregate(v) for k, v in _split(b_rows).items()}

    # R413 — VOID detection runs BEFORE any delta or verdict is printed. A run
    # whose arms were served by the fallback leg, or whose system payloads were
    # identical under a system-slot lever, cannot measure the lever at all: its
    # delta table reads exactly like a real null (the R412 95+95 void run).
    if args.local:
        lever = gate_validity.lever_changes_system(
            base_env, branch_env, override=args.lever_changes_system
        )
    else:
        lever = (False, "remote --endpoint run; payloads are not observable in-process")
    void = gate_validity.assess(
        base=a_prov, branch=b_prov, lever=lever, transport_checked=bool(args.local),
    )
    print()
    print(void.render())
    void_reasons = tuple(void.reasons) if b_rows else ()

    if void_reasons:
        # Refuse the delta: each arm's own scorecard is still printed, because
        # the absolute numbers are honest; only the DIFF is unmeasurable.
        _report(f"{args.label} [baseline]", a_agg, None)
        _report(f"{args.label} [branch]", b_agg, None)
    else:
        _report(args.label, a_agg, b_agg)

    # The paired subset is the honest A/B read when either arm loses rows.
    paired = _paired(a_rows, b_rows) if b_rows else {}
    if paired:
        _report_paired(args.label, paired, void_reasons)

    # R365 — hard rule #8. Decided BEFORE the sidecar is written so the verdict
    # is persisted, and the sidecar is written even when the gate fails: a
    # failing run's rows are exactly the ones worth keeping.
    verdict = _gold_gate_verdict(
        a_agg, b_agg, allow=bool(args.allow_gold_drop), paired=paired,
        expected_splits=expected_splits,
    )
    offenders = _gold_drop_rows(a_rows, b_rows) if b_rows else []

    # R398 — liveness guard.  Without Stage-2 landing, both arms return
    # identical deterministic answers, gold_dropped_head is 0/0, and the
    # gate prints PASS — a false green on the exact class of lever (prompt
    # side, AGENTS.md invariant #5) it exists to police.
    #
    # ⚠ The counters live in ``app.llm.stage2_policy`` — the first cut of this
    # guard imported ``app.integrations.regenold.transport``, which does not
    # exist, and the bare ``except`` swallowed the ModuleNotFoundError, so
    # every --local run read "not live" whether or not it was.  Hence
    # ``_transport_liveness`` returns an explicit reason string and the caller
    # SAYS which of the three cases it is, instead of failing silent.
    live, live_note = _transport_liveness(
        local=bool(args.local),
        stats=_merged_transport_stats(a_prov, b_prov) if b_prov is not None else a_prov.stats,
    )
    verdict["transport_liveness"] = live_note
    if not live and verdict.get("exit_code") == 0 and verdict.get("comparable"):
        print(f"\nWARNING: {live_note}", file=sys.stderr)
        verdict["exit_code"] = 2
        verdict["liveness_failed"] = True

    # R413 — a VOID run carries no verdict of any kind: the hard-rule-#8
    # comparison is as unmeasurable as the deltas, so it is not reported as a
    # PASS. It outranks the gold gate, the liveness code and --allow-gold-drop.
    verdict["void"] = bool(void_reasons)
    verdict["void_reasons"] = list(void_reasons)
    verdict["arm_provenance"] = void.as_dict()
    if void_reasons:
        verdict["exit_code"] = 0 if args.allow_void else 3
        print(
            "\nHARD RULE #8 GATE: not evaluated — the run is VOID "
            f"({len(void_reasons)} reason(s); exit {verdict['exit_code']})"
        )
    else:
        _report_gold_gate(verdict, offenders)

    out = _RESULTS / f"easyhard-{args.label}.json"
    out.write_text(
        json.dumps(
            {
                "label": args.label,
                "endpoint": args.endpoint or "local",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "baseline_env": base_env,
                "branch_env": branch_env,
                "baseline": a_agg,
                "branch": b_agg,
                "paired": paired,
                "lever": {"changes_system": bool(lever[0]), "why": lever[1]},
                "gate_validity": void.as_dict(),
                "gold_gate": verdict,
                "gold_gate_rows": offenders,
                "baseline_rows": a_rows,
                "branch_rows": b_rows,
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return int(verdict["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

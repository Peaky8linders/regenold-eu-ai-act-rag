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
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import time
from pathlib import Path
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.harness.probe_set import ProbeRow, load_probe_set

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"

# Marginal leverage on the official Overall (a plain geometric mean of the 8
# axes) at our operating point — pp of Overall per +1pp of the axis.
# Source: .planning/R276-PLAN.md (reproduces every reported figure to <0.05pp).
_LEVERAGE = {"ref_strict": 0.163, "ref_conc": 0.121, "ref_loose": 0.113}


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


def _report_paired(label: str, paired: dict[str, Any]) -> None:
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
    return {
        "comparable": comparable,
        "splits": splits,
        "total_delta": sum(v["delta"] for v in splits.values()),
        "offending_splits": offenders,
        "failed": failed,
        "allow_gold_drop": bool(allow),
        "suppressed_by_flag": failed and bool(allow),
        "exit_code": 1 if (failed and not allow) else 0,
    }


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
    if not verdict["failed"]:
        print("\n  PASS — the branch drops no more gold heads than the baseline.")
        return
    where = ", ".join(verdict["offending_splits"]) or "?"
    if verdict["suppressed_by_flag"]:
        print(f"\n  {_GOLD_GATE_BANNER}")
        print(f"  !! HARD RULE #8 VIOLATED on split(s): {where}"
              f"  (total delta {verdict['total_delta']:+d})")
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
    args = ap.parse_args()

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

    _RESULTS.mkdir(parents=True, exist_ok=True)
    base_env = _parse_env(args.baseline_env)
    branch_env = _parse_env(args.branch_env)

    print(f"\n### ARM A (baseline) env={base_env or '{}'}")
    a_rows = _run_arm(
        probe, endpoint=args.endpoint, api_key=args.api_key, local=args.local,
        timeout=args.timeout, arm_env=base_env,
        ckpt_path=_RESULTS / f"easyhard-{args.label}-A.ckpt.jsonl",
    )
    a_agg = {k: _aggregate(v) for k, v in _split(a_rows).items()}

    b_agg = None
    b_rows: list[dict[str, Any]] = []
    if branch_env:
        # SEQUENTIAL by construction — both arms hairpin to ONE local Claude
        # Max; concurrent wrapper jobs corrupt each other's latency.
        print(f"\n### ARM B (branch) env={branch_env}")
        b_rows = _run_arm(
            probe, endpoint=args.endpoint, api_key=args.api_key, local=args.local,
            timeout=args.timeout, arm_env=branch_env,
            ckpt_path=_RESULTS / f"easyhard-{args.label}-B.ckpt.jsonl",
        )
        b_agg = {k: _aggregate(v) for k, v in _split(b_rows).items()}

    _report(args.label, a_agg, b_agg)

    # The paired subset is the honest A/B read when either arm loses rows.
    paired = _paired(a_rows, b_rows) if b_rows else {}
    if paired:
        _report_paired(args.label, paired)

    # R365 — hard rule #8. Decided BEFORE the sidecar is written so the verdict
    # is persisted, and the sidecar is written even when the gate fails: a
    # failing run's rows are exactly the ones worth keeping.
    verdict = _gold_gate_verdict(
        a_agg, b_agg, allow=bool(args.allow_gold_drop), paired=paired
    )
    offenders = _gold_drop_rows(a_rows, b_rows) if b_rows else []
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

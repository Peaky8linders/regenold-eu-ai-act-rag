"""Dynamic A/B — the merge gate that replaces the davidath regression run.

WHY THIS EXISTS
===============

``evals.bench.runner`` (davidath, 476 rows) was the habitual "did I break
anything" run. It is the wrong instrument and it kept producing confident,
useless numbers:

* It runs ``P2P_GRAPH_RAG_PROVIDER=cli`` — **no Stage-2 at all**. Every prompt
  change, every judge change, the Cohere reranker and the whole KG-context block
  are invisible to it by construction. R331 measured "baseline reproduces,
  deltas <= 0.0007" on a change set containing four judge fixes and a reranker,
  because it could not see any of them.
* Its gold is head-level and single-article (mean 1.00 refs/row), so it
  structurally cannot show a chain-dropping defect (hard rule #7).
* It is BM25-saturated, so retrieval levers read byte-identical *because the
  instrument is blind*, not because the lever is safe.

That is CLAUDE.md's "instrument trap" in its purest form: **before trusting a
measurement, ask whether the instrument can physically observe the thing you are
deciding.** davidath usually cannot, so it has been retired as a gate.

WHAT "DYNAMIC" MEANS HERE
=========================

Three things, in order of importance:

1. **FIRE CHECK FIRST — no number is reported until the lever is proven to have
   fired.** Every previous inert A/B in this repo (R326 vector recall, R327
   semantic layers, three R329 reranker placements) reported a clean +0.0000 on
   every axis while the feature never executed. A flat result and a dead feature
   are the same picture. This harness runs a small probe, asserts the two arms
   actually diverge, and **ABORTS with verdict INERT** if they do not. It will
   not print an axis table for a lever that did nothing.

2. **Sample size is driven by observed variance, not by a constant.** Rows are
   run in batches; after each batch the paired deltas get a bootstrap CI. It
   stops early when the CI excludes zero (a real effect) or when it is tight
   enough around zero to call a null with confidence. A 0.003 delta on 9
   effective rows — R331's retrieval result — is reported as UNDERPOWERED rather
   than dressed up as a finding.

3. **It runs the LIVE path** (Stage-2 on) by default, because that is where the
   product lives. `--deterministic` exists for a quick smoke, and says so in the
   verdict.

WHAT IT REPORTS
===============

Per axis: paired delta, bootstrap 95% CI, and a verdict. Plus ``gold_dropped``
on both grains — hard rule #8 is a VETO, not an axis: a non-zero gold drop is a
rejection regardless of every other number.

The exact-grain veto is summed PER ROW over rows whose own gold carries a
sub-point, and prints that population; against head-level gold it is reported as
inapplicable rather than as a number, because there it counts precision GAINS as
losses. See the veto block in :func:`_analyse`.

R349 — THE COMPLETE COMPETITION PICTURE
=======================================

The retrieval axes (ref_loose / ref_strict / ref_conc / kw_recall) measure
WHAT WAS RETRIEVED, not whether the ANSWER is right. The Regenold rubric
scores the answer itself — ``answer_correctness`` (CoVe, decompose-and-
verify), ``reference_correctness`` (GOVERNING/SUPPORTING/WRONG three-way),
``citation_faithfulness`` (does the prose match each citation), and
``answer_conciseness``. Those live in :mod:`evals.judge.legal_v2`; this
harness now runs them per arm over the same rows, through the same caller
plumbing (``--judge-model`` / ``--judge-provider``, Bedrock sonnet-4-6 by
default), and reports them as paired axes — ``ans_corr`` / ``ref_corr`` /
``cite_faith`` / ``ans_conc`` — in the SAME table, so a retrieval win can be
read against its answer-level cost and a gold veto against both. Judge axes
are computed ONCE at the end (4 calls per row per arm — the fire check and
adaptive stop stay on the cheap axes), fail soft on transport errors, and are
skipped entirely with ``--no-judge``.

USAGE
=====

    py -3.12 -m evals.harness.dynamic_ab --flag REGENOLD_COHERE_RERANK \\
        --label r331-rerank --max-rows 60

    py -3.12 -m evals.harness.dynamic_ab \\
        --branch-env REGENOLD_ONTOLOGY_RISK_DOCS=0 --label onto-off

⚠ In-process env flips only work for flags read fresh per call AND absent from
any memo that outlives the flip. ``_engine_cache_key`` covers the answer cache;
a module-level ``lru_cache`` does NOT. The fire check catches both, which is the
entire point of running it before anything else.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics as st
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.integrations.regenold import refs as central_refs
from evals.bench import metrics as bench_metrics
from evals.harness.probe_set import ProbeRow, load_probe_set

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"

#: Axes that are DIRECTIONAL (higher is better). gold_dropped is deliberately
#: not here — it is a veto, not a score.
_AXES = ("ref_loose", "ref_strict", "ref_conc", "kw_recall")

_BOOTSTRAP_N = 2000
_SEED = 20260814

#: R350 — the minimum paired observations before an axis may print a RESOLVED
#: verdict (WIN / LOSS / NULL). Below this, ``_verdict`` returns UNDERPOWERED
#: however narrow the CI looks. The judge axes motivated it: they score only
#: the rows that reach Stage-2 AND judged cleanly in BOTH arms, so an axis can
#: land on 1-2 pairs while the run header advertises the much larger
#: deterministic n — and a bootstrap over one observation has zero width,
#: which read as the most resolved state instead of the least.
_MIN_PAIRS_FOR_VERDICT = 3

#: R350.1 — at or above this share of errored rows the run is a TRANSPORT
#: failure, not a lever result. Excluding errored rows from the fire check is
#: correct, but it means a dead endpoint collapses `common` to ~0 and reports
#: INERT ("fix the feature") or BLIND_PROBE ("fix the rows") — both of which
#: send the reader to debug something that is not broken.
_TRANSPORT_FAILURE_RATIO = 0.5


# ── citation grain ───────────────────────────────────────────────────────


def _carries_sub_point(ref: Any) -> bool:
    """Does this citation name a SUB-POINT, or only an article/annex head?

    ONE CONCEPT, ONE DEFINITION: this delegates to the repo's canonical citation
    parser (``app.integrations.regenold.refs.parse``), which is already the
    single source of truth for "what are this reference's sub-point tokens"
    everywhere else in the codebase. It is deliberately NOT a local regex.

    The obvious shorthand — ``"." in ref`` — is wrong on forms this repo really
    emits, and wrong in the dangerous direction:

        "Art. 5"        "." present, subpoints ()          -> HEAD  (shorthand: leaf)
        "Recital 27."   "." present, unparseable as a cite -> not a citation
        "Art. 5(1)(a)"  "." present, subpoints ('1', 'a')  -> LEAF
        "Article 5.1.f" "." present, subpoints ('1', 'f')  -> LEAF
        "Article 5"     "." absent,  subpoints ()          -> HEAD
        "Annex IV"      "." absent,  subpoints ()          -> HEAD

    So the shorthand calls the INTERNAL-form head ``Art. 5`` leaf-grained, which
    would switch the exact-grain veto ON over gold that cannot support it — the
    precise false rejection the R337 guard exists to prevent. Gold reaches this
    harness in wire form today, but ``easyhard``/KB-derived gold is internal
    form, and the two are one copy-paste apart.
    """
    if not isinstance(ref, str):
        return False
    try:
        return bool(central_refs.parse(ref).subpoints)
    except Exception:  # noqa: BLE001 — unparseable text is simply not a citation
        return False


# ── scoring ──────────────────────────────────────────────────────────────


def _score(row: ProbeRow, answer: str, refs: list[str]) -> dict[str, Any]:
    gold = list(getattr(row, "expected_refs", ()) or ())
    kws = list(getattr(row, "expected_keywords", ()) or ())
    gd_head = bench_metrics.gold_dropped_head(refs, gold)
    gd_exact = bench_metrics.gold_dropped_exact(refs, gold)
    low = (answer or "").lower()
    return {
        "ref_loose": bench_metrics.reference_correctness_loose(refs, gold),
        "ref_strict": bench_metrics.reference_correctness_strict(refs, gold),
        "ref_conc": bench_metrics.reference_conciseness(refs, gold),
        "kw_recall": (
            sum(1 for k in kws if k.lower() in low) / len(kws) if kws else 0.0
        ),
        "gold_dropped_head": float(gd_head["dropped_count"]),
        "gold_dropped_exact": float(gd_exact["dropped_count"]),
        "answer_chars": float(len(answer or "")),
        "n_refs": float(len(refs or [])),
    }


# ── R349: the legal_v2 judge axes (the Regenold rubric's answer-level
#    metrics) run per arm and join the axis table as paired deltas.
# ─────────────────────────────────────────────────────────────────────────

_JUDGE_AXES: tuple[tuple[str, str], ...] = (
    ("answer_correctness", "ans_corr"),
    ("reference_correctness", "ref_corr"),
    ("citation_faithfulness", "cite_faith"),
    ("answer_conciseness", "ans_conc"),
)


def _judge_caller(provider: str, timeout_s: float, model: str) -> Any:
    """The legal_v2 caller for ``provider`` (bedrock by default)."""
    from evals.judge.legal_v2 import (  # noqa: PLC0415
        _resolve_caller,
        set_judge_model,
    )

    set_judge_model(model)
    return _resolve_caller(provider, timeout_s)


def _judge_rows(
    records: list[dict[str, Any]],
    probe_by_id: dict[str, ProbeRow],
    *,
    caller: Any,
    samples: int,
    concurrency: int,
) -> dict[str, Any]:
    """Run the 4 legal_v2 axes over arm records (a cheap local caller in
    tests; the LLM caller in live runs). Fail-soft: a transport error marks
    every row with a judge error, never raises."""
    from evals.judge.legal_v2 import _judge_row, _norm  # noqa: PLC0415

    k = max(1, int(samples))
    rows: list[tuple[int, dict[str, Any]]] = []
    for i, rec in enumerate(records):
        pr = probe_by_id.get(str(rec.get("id")))
        question = str(pr.live_question) if pr and getattr(pr, "live_question", "") else ""
        rows.append((i, _norm({
            "id": rec.get("id"),
            "category": getattr(pr, "category", None) if pr else None,
            "question": question,
            "pred_answer": rec.get("pred_answer", ""),
            "pred_refs": rec.get("pred_refs", []),
            "gold_refs": rec.get("gold_refs", []),
            "gold_answer": getattr(pr, "gold_answer", "") if pr else "",
        })))

    judged: dict[str, Any] = {}
    errors = 0
    lock = threading.Lock()

    def _w(item: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        _i, r = item
        return _i, _judge_row(r, caller, k)

    try:
        with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as pool:
            for _i, jr in pool.map(_w, rows):
                with lock:
                    judged[str(jr.get("id"))] = jr
                    for _ax, _label in _JUDGE_AXES:
                        v = (jr.get("verdicts") or {}).get(_ax) or {}
                        if v.get("judge_error") or v.get("evaluation_error"):
                            errors += 1
                            break
    except Exception as exc:  # noqa: BLE001 — a judge outage must not kill the A/B
        return {"error": str(exc)}
    return {"judged": judged, "n_errors": errors}


def _judge_axes(
    base_records: list[dict[str, Any]],
    brch_records: list[dict[str, Any]],
    probe_by_id: dict[str, ProbeRow],
    *,
    caller: Any,
    samples: int,
    concurrency: int,
    null_band: float,
) -> dict[str, Any]:
    """Paired judge axes for the common rows of both arms.

    Returns ``{label: {baseline, branch, delta, ci_lo, ci_hi, n_changed,
    verdict, n_pairs, n_skipped}}`` — the same shape as the retrieval axes —
    plus the per-arm aggregate (pass/fail/error counts per axis). A pair is
    dropped from an axis when EITHER arm's verdict is an error or unscorable
    (counted in ``n_skipped``), so errors never masquerade as passes.

    ⚠ R350 — that guarantee was NOT implemented as written. The filter tested
    the verdict STRING only, but ``legal_v2._judge_row`` returns a real
    ``{"verdict": "fail", "evaluation_error": "empty_answer"}`` for a row whose
    answer came back empty — which is exactly what a branch-arm HTTP timeout
    produces. So one network blip scored as the branch LOSING the axis. The
    scorability test is now :func:`_scorable`, one definition shared with
    :func:`_pair_scored`, and it rejects any verdict carrying an error marker
    however the verdict string reads.
    """
    base = _judge_rows(base_records, probe_by_id, caller=caller,
                       samples=samples, concurrency=concurrency)
    if "error" in base:
        return {"error": base["error"]}
    branch = _judge_rows(brch_records, probe_by_id, caller=caller,
                         samples=samples, concurrency=concurrency)
    if "error" in branch:
        return {"error": branch["error"]}

    axes: dict[str, Any] = {}
    for ax, label in _JUDGE_AXES:
        deltas: list[float] = []
        skipped = 0
        common = set(base["judged"]) & set(branch["judged"])
        for rid in common:
            vb = (base["judged"][rid].get("verdicts") or {}).get(ax) or {}
            vc = (branch["judged"][rid].get("verdicts") or {}).get(ax) or {}
            if _scorable(vb) and _scorable(vc):
                sb = str(vb.get("verdict") or "").lower()
                sc = str(vc.get("verdict") or "").lower()
                deltas.append((1.0 if sc == "pass" else 0.0)
                              - (1.0 if sb == "pass" else 0.0))
            else:
                skipped += 1
        if not deltas:
            # R350.1 — an axis with zero scorable pairs used to vanish from the
            # table with no row, no zero and no note, while the judge blurb
            # still named all four. A whole competition axis could disappear
            # from the merge gate's output silently.
            axes[label] = {
                "baseline": 0.0, "branch": 0.0, "delta": 0.0,
                "ci_lo": 0.0, "ci_hi": 0.0, "n_changed": 0,
                "verdict": "NO-DATA", "n_pairs": 0, "n_skipped": skipped,
            }
            continue
        mean = st.fmean(deltas)
        lo, hi = _bootstrap_ci(deltas)
        # Per-arm pass RATE over the paired population (errors already excluded).
        pairs = [rid for rid in common if _pair_scored(base, branch, ax, rid)]
        axes[label] = {
            "baseline": st.fmean(
                1.0 if str(((base["judged"][rid].get("verdicts") or {})
                            .get(ax) or {}).get("verdict") or "").lower() == "pass"
                else 0.0 for rid in pairs),
            "branch": st.fmean(
                1.0 if str(((branch["judged"][rid].get("verdicts") or {})
                            .get(ax) or {}).get("verdict") or "").lower() == "pass"
                else 0.0 for rid in pairs),
            "delta": mean, "ci_lo": lo, "ci_hi": hi,
            "n_changed": sum(1 for d in deltas if d != 0),
            "verdict": _verdict(mean, lo, hi, null_band=null_band,
                                n_pairs=len(deltas)),
            "n_pairs": len(deltas), "n_skipped": skipped,
        }
    return {"axes": axes, "base": base, "branch": branch}


def _scorable(v: dict[str, Any]) -> bool:
    """Is this ONE arm's verdict a real measurement?

    R350 — the single definition of "scorable", shared by :func:`_judge_axes`
    and :func:`_pair_scored`. Two conditions, and the second is the one that
    was missing:

    1. the verdict string is literally ``pass`` or ``fail`` — anything else
       (``None``, a missing key, ``no_json``, ``unbalanced_json``) is absent,
       and ABSENT IS NOT ZERO; and
    2. the verdict carries NO error marker. ``legal_v2._judge_row`` emits
       ``{"verdict": "fail", "evaluation_error": "empty_answer"}`` when the
       answer is empty, which is what a transport timeout looks like from
       here. Reading that as a genuine ``fail`` let one network blip score as
       the branch losing an entire answer-quality axis.
    """
    if v.get("judge_error") or v.get("evaluation_error"):
        return False
    return str(v.get("verdict") or "").lower() in ("pass", "fail")


def _pair_scored(base: dict[str, Any], branch: dict[str, Any], ax: str, rid: str) -> bool:
    vb = (base["judged"][rid].get("verdicts") or {}).get(ax) or {}
    vc = (branch["judged"][rid].get("verdicts") or {}).get(ax) or {}
    return _scorable(vb) and _scorable(vc)


# ── statistics ───────────────────────────────────────────────────────────


def _bootstrap_ci(
    deltas: list[float], *, n: int = _BOOTSTRAP_N, alpha: float = 0.05
) -> tuple[float, float]:
    """Percentile bootstrap CI of the MEAN paired delta.

    Paired deltas, so the resample unit is the row — which is what makes this
    valid on a small n where a t-test's normality assumption is not credible.

    ⚠ R350 — the ``len == 1`` case used to return ``(d, d)``: a ZERO-WIDTH CI,
    which ``_verdict`` then reads as WIN or as a "tight, useful NULL". A single
    observation is the least resolved state there is, and it was printing as
    the most resolved. Resampling one item is degenerate either way, so the
    honest answer is an unbounded interval; :func:`_verdict` additionally
    refuses to resolve any axis below ``_MIN_PAIRS_FOR_VERDICT`` pairs.
    """
    if not deltas:
        return (0.0, 0.0)
    if len(deltas) == 1:
        return (float("-inf"), float("inf"))
    rng = random.Random(_SEED)
    means: list[float] = []
    k = len(deltas)
    for _ in range(n):
        means.append(st.fmean(deltas[rng.randrange(k)] for _ in range(k)))
    means.sort()
    lo = means[int((alpha / 2) * n)]
    hi = means[min(n - 1, int((1 - alpha / 2) * n))]
    return (lo, hi)


def _verdict(
    delta: float, lo: float, hi: float, *, null_band: float,
    n_pairs: int | None = None,
) -> str:
    """Classify an axis result honestly, including 'not enough data'.

    ⚠ R350 — ``n_pairs`` is a floor on RESOLUTION, not a tie-break. The judge
    axes score far fewer pairs than the deterministic ones (most rows bypass
    Stage-2, and judge transport errors drop more), so an axis could reach a
    confident WIN/NULL on one or two rows while the header advertised the much
    larger deterministic n. Below ``_MIN_PAIRS_FOR_VERDICT`` no CI is credible
    however narrow it looks, so say UNDERPOWERED and mean it.
    """
    if n_pairs is not None and n_pairs < _MIN_PAIRS_FOR_VERDICT:
        return "UNDERPOWERED"
    if lo > 0:
        return "WIN"
    if hi < 0:
        return "LOSS"
    if (hi - lo) <= 2 * null_band:
        return "NULL"          # tight around zero — a real, useful null
    return "UNDERPOWERED"      # CI spans zero AND is wide — say so


# ── the fire check ───────────────────────────────────────────────────────


def fire_check(
    baseline_rows: list[dict[str, Any]], branch_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Did the lever actually change anything? Run BEFORE scoring.

    Returns counts of rows whose answer or reference list differ. A lever that
    changes NOTHING is not "safe" — it is UNMEASURED, and the axis table that
    would follow is meaningless. This is the check every inert A/B in this
    repo's history was missing.

    ⚠ R350 — AN ERROR IS NOT A DIVERGENCE. This compared ``pred_refs`` and
    ``pred_answer`` with no error filter, while ``_analyse`` drops any row that
    errored in EITHER arm. An errored row carries ``pred_answer == ""`` and
    ``pred_refs == []``, which always differs from a healthy baseline — so a
    branch-arm timeout counted as the lever firing, the INERT gate passed, and
    the rows that "proved" it fired were then excluded from every axis. The
    harness's defining property inverted: the instrument breaking made a dead
    lever look alive. Errored rows are now excluded from the comparison and
    reported separately as ``errored``, so a run that is mostly transport
    failure says so instead of claiming a finding.
    """
    b = {r["id"]: r for r in baseline_rows}
    c = {r["id"]: r for r in branch_rows}
    paired = [i for i in b if i in c]
    errored = [i for i in paired if b[i].get("error") or c[i].get("error")]
    common = [i for i in paired if i not in set(errored)]
    refs_diff = [
        i for i in common if b[i].get("pred_refs") != c[i].get("pred_refs")
    ]
    ans_diff = [
        i for i in common
        if (b[i].get("pred_answer") or "") != (c[i].get("pred_answer") or "")
    ]
    changed = sorted(set(refs_diff) | set(ans_diff))
    return {
        "common": len(common),
        "errored": len(errored),
        "refs_changed": len(refs_diff),
        "answers_changed": len(ans_diff),
        "any_changed": len(changed),
        "changed_ids": changed[:20],
        "fired": bool(changed),
    }


# ── the probe sensitivity control ────────────────────────────────────────
#
# R336. The fire check answers "did the lever move anything?". It does NOT
# answer "could these rows have shown me if it had?" — and those are different
# questions with opposite remedies.
#
# Measured 2026-08-14, same process, one flag, two questions:
#
#   REGENOLD_BM25_FALLBACK_K=2   FIRES   on "if a logistics firm retrofits a
#                                        third-party vision model…"  (15 refs)
#   REGENOLD_BM25_FALLBACK_K=2   inert   on "what is the definition of an AI
#                                        system?"                    (1 ref)
#
# The definitional row resolves through a direct KB obligation lookup
# (`kb-governance-Art. 3`, 378 chars) and never reaches BM25 ranking, graph
# expansion or the answer router. So a probe pool dominated by curated and
# definitional rows is BLIND to every retrieval lever — and the A/B would have
# reported INERT while the lever was fine and the rows simply could not see it.
#
# That mattered: three separate wrong diagnoses were made off exactly this
# confusion before it was pinned down, each one sending the reader to debug a
# feature that was not broken.
#
# So: before declaring INERT, flip a control flag KNOWN to be live at the same
# layer over the SAME rows. If the control moves them, the probe can see that
# layer and INERT is a real finding about the lever. If the control cannot move
# them either, the instrument is blind and the verdict is BLIND_PROBE — fix the
# probe set, not the feature.

_CONTROL_FLAGS: dict[str, tuple[str, str]] = {
    # layer -> (env var, value) for a lever measured to change engine output.
    "retrieval": ("REGENOLD_BM25_FALLBACK_K", "2"),
    "stage2": ("P2P_GRAPH_RAG_ENABLE_STAGE2", "0"),
    "graph": ("REGENOLD_KG_CONTEXT", "0"),
}

# Substring -> layer. Ordered; first match wins. Crude on purpose: a wrong guess
# is corrected by `--control-layer`, and the fallback is the retrieval control,
# which is the layer every row must traverse to produce a reference at all.
_LAYER_HINTS: tuple[tuple[str, str], ...] = (
    ("STAGE2", "stage2"), ("COMPLEX", "stage2"), ("OPUS", "stage2"),
    ("MINIMAL_COMPOSER", "stage2"), ("REF_MINIMALITY", "stage2"),
    ("ANSWER_FIRST", "stage2"), ("CURATED", "stage2"),
    # R345 — REGENOLD_PROMPT_V2 swaps the Stage-2 SYSTEM prompt (V1 51K vs
    # V2 15K chars), so the V1-vs-V2 confirmatory A/B (#24) must probe with
    # the stage2 control (P2P_GRAPH_RAG_ENABLE_STAGE2=0), not the retrieval
    # fallback the name would otherwise infer.
    ("PROMPT", "stage2"),
    # R350 — RERANK and EXPANSION must be matched BEFORE the "KG_" hint.
    # `REGENOLD_RERANK_KG_CANDIDATES` and `REGENOLD_RERANK_KG_HOPS` contain
    # "KG_", so they inferred layer=graph and probed with
    # `REGENOLD_KG_CONTEXT=0` — a Stage-2 CONTEXT switch that cannot exercise
    # the rerank pool at all. They are RETRIEVAL levers: they change the
    # candidate set the cross-encoder ranks, and that set decides wire
    # references. Getting this wrong flips the diagnosis between "fix the
    # feature" (exit 2) and "fix the rows" (exit 3) — opposite actions. This is
    # the R345 defect, on the flags added immediately after R345 fixed it.
    ("RERANK", "retrieval"), ("EXPANSION", "retrieval"),
    ("KG_", "graph"), ("GRAPH", "graph"), ("SEMANTIC", "graph"),
    ("PPR", "graph"), ("VECTOR", "graph"), ("ONTOLOGY", "graph"),
)


def _infer_control_layer(
    branch_env: dict[str, str], emit: Callable[[str], None] = print
) -> str:
    """Which layer's control flag can prove these rows are not blind?

    ⚠ R350 — an unmatched flag falls back to ``retrieval``, and that fallback is
    now LOUD. A silent default is how `REGENOLD_PROMPT_V2` got probed at the
    wrong layer for a whole round: the inference looked authoritative and was
    guessing. Pass ``--control-layer`` to settle it explicitly.
    """
    for name in branch_env:
        upper = name.upper()
        for frag, layer in _LAYER_HINTS:
            if frag in upper:
                return layer
    emit(f"control layer INFERRED as 'retrieval' by default — no hint matched "
         f"{sorted(branch_env)}. If this lever is a Stage-2 or graph lever the "
         f"sensitivity probe will test the wrong layer; pass --control-layer.")
    return "retrieval"


def resolve_control(
    branch_env: dict[str, str], override: str | None = None
) -> tuple[str, dict[str, str]] | None:
    """Pick a control flag for this A/B, or None if none is usable.

    Never returns a control the branch itself is manipulating — flipping the
    same var in both arms would make the control trivially "fire" (or trivially
    not) for reasons that have nothing to do with probe sensitivity.
    """
    layer = override or _infer_control_layer(branch_env)
    candidates = [layer] + [k for k in _CONTROL_FLAGS if k != layer]
    for cand in candidates:
        env, val = _CONTROL_FLAGS[cand]
        if env not in branch_env:
            return cand, {env: val}
    return None


def probe_sensitivity_check(
    rows: list[ProbeRow],
    baseline_rows: list[dict[str, Any]],
    control_env: dict[str, str],
    *,
    local: bool,
    endpoint: str | None,
    api_key: str | None,
    timeout: float,
    min_gap: float = 0.0,
) -> dict[str, Any]:
    """Can these rows observe ANY change at this layer?

    Re-runs the rows already used, under a known-live control flag, and reuses
    :func:`fire_check` so "changed" means exactly what it means everywhere else.
    """
    control_rows = _run_rows(rows, control_env, local=local, endpoint=endpoint,
                             api_key=api_key, timeout=timeout, min_gap=min_gap)
    fired = fire_check(baseline_rows, control_rows)
    return {
        "control_env": control_env,
        "sensitive": fired["fired"],
        "rows_moved": fired["any_changed"],
        "rows_compared": fired["common"],
        "moved_ids": fired["changed_ids"],
    }


# ── the run ──────────────────────────────────────────────────────────────


def _row_record(
    pr: ProbeRow,
    answer: str,
    refs: list[str],
    *,
    latency_ms: float = 0.0,
    http_status: int = 200,
    error: str | None = None,
) -> dict[str, Any]:
    """THE per-row record shape. One definition, so nothing can drift from it.

    R337.1 — this was an inline dict literal inside :func:`_run_rows`, and the
    R337 grain guard in :func:`_analyse` then read each row's gold from a
    ``"row"`` key that the literal has never written. ``gold_refs`` was
    therefore ALWAYS empty, ``applicable`` ALWAYS False, and because
    :func:`_report` filters its rejection test on ``applicable``, an exact-grain
    gold drop could NEVER print REJECTED. Half of hard rule #8's veto was dead
    on this repo's designated merge gate. Measured on two rows whose branch arm
    dropped 5 gold coordinates: ``applicable=False``, ``gold_refs_total=0``,
    exact delta ``+5``, and no REJECTED line.

    The accompanying test suite passed 5/5 throughout, because its fixture
    hand-built a dict *with* a ``"row"`` key — a data shape production never
    produced. That is the failure mode this extraction closes: the tests now
    call this function, so a key that disappears here disappears from the test
    too, and a guard reading a key nobody writes cannot pass unnoticed again.

    ``gold_refs`` is stored as an explicit list rather than by stashing the
    whole :class:`ProbeRow`: the record is serialised straight into the sidecar
    JSON, and a dataclass there is both unserialisable and an invitation for a
    consumer to reach for a field the sidecar does not carry.
    """
    return {
        "id": pr.id,
        "source": pr.source,
        "pred_answer": answer,
        "pred_refs": refs,
        # The gold this row was scored against — read back by `_analyse` to
        # decide the veto GRAIN per row. Never re-derived there: re-deriving
        # is how the two definitions drift.
        "gold_refs": list(getattr(pr, "expected_refs", ()) or ()),
        "latency_ms": latency_ms,
        "http_status": http_status,
        "error": error,
        "scores": _score(pr, answer, refs),
    }


def _run_rows(
    rows: list[ProbeRow],
    arm_env: dict[str, str],
    *,
    local: bool,
    endpoint: str | None,
    api_key: str | None,
    timeout: float,
    min_gap: float = 0.0,
) -> list[dict[str, Any]]:
    saved: dict[str, str | None] = {}
    for k, v in arm_env.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        from evals.regenold.runner_v2 import _post, _post_local

        poster = _post_local if local else _post
        url = (
            "local://app.main:app/api/v1/regenold/eu-ai-act/ask"
            if local else str(endpoint)
        )
        out: list[dict[str, Any]] = []
        _last_call = 0.0
        for pr in rows:
            # R346 — rate-limit pacing. The Cohere rerank A/B runs against a
            # Trial key (10 calls/min): without a floor between POSTs every
            # call 429s, the lever fails soft on the wire, and the A/B reports
            # INERT for a feature that works. Pacing is the fix.
            if min_gap > 0.0:
                _wait = min_gap - (time.monotonic() - _last_call)
                if _wait > 0.0:
                    time.sleep(_wait)
            _last_call = time.monotonic()
            history = [dict(m) for m in pr.messages]
            body, latency_ms, status, err, attempts, _ = poster(
                url, api_key, history, timeout
            )
            answer = (body or {}).get("answer") or ""
            refs = list((body or {}).get("references") or [])
            out.append(_row_record(
                pr, answer, refs,
                latency_ms=latency_ms, http_status=status, error=err,
            ))
        return out
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def _stratified(probe: list[ProbeRow], n: int, seed: int) -> list[ProbeRow]:
    """Proportional sample across sources — NOT a head slice.

    `probe_set` is ordered by source, so `[:n]` (what the previous runs used,
    and called "stratified") takes whole sources and drops others entirely.
    """
    by_src: dict[str, list[ProbeRow]] = {}
    for r in probe:
        by_src.setdefault(r.source, []).append(r)
    rng = random.Random(seed)
    for v in by_src.values():
        rng.shuffle(v)
    out: list[ProbeRow] = []
    srcs = sorted(by_src)
    i = 0
    while len(out) < n and any(by_src[s] for s in srcs):
        s = srcs[i % len(srcs)]
        if by_src[s]:
            out.append(by_src[s].pop())
        i += 1
    return out


def run(
    *,
    branch_env: dict[str, str],
    label: str,
    max_rows: int,
    batch: int,
    local: bool,
    endpoint: str | None,
    api_key: str | None,
    timeout: float,
    null_band: float,
    seed: int,
    min_rows: int = 0,
    control_layer: str | None = None,
    min_gap: float = 0.0,
    judge_model: str | None = "claude-sonnet-4-6",
    judge_provider: str = "bedrock",
    judge_concurrency: int = 4,
    judge_timeout: float = 120.0,
    judge_samples: int = 1,
    probe_sources: tuple[str, ...] | None = None,
    emit: Callable[[str], None] = print,
) -> dict[str, Any]:
    probe = load_probe_set(sources=probe_sources)
    pool = _stratified(probe, min(max_rows, len(probe)), seed)
    emit(f"probe pool: {len(pool)} rows (stratified across "
         f"{len({r.source for r in pool})} sources)")
    emit(f"branch env: {branch_env}")

    base_rows: list[dict[str, Any]] = []
    brch_rows: list[dict[str, Any]] = []
    stop_reason = "max_rows"
    fired: dict[str, Any] = {}

    for start in range(0, len(pool), batch):
        chunk = pool[start:start + batch]
        base_rows += _run_rows(chunk, {}, local=local, endpoint=endpoint,
                               api_key=api_key, timeout=timeout,
                               min_gap=min_gap)
        brch_rows += _run_rows(chunk, branch_env, local=local, endpoint=endpoint,
                               api_key=api_key, timeout=timeout,
                               min_gap=min_gap)

        fired = fire_check(base_rows, brch_rows)
        emit(f"  n={len(base_rows):3d}  changed={fired['any_changed']:3d} "
             f"(refs {fired['refs_changed']}, answers {fired['answers_changed']})")

        # R346 — checkpoint after every batch so a long live run survives a
        # crash with the rows it has already completed.
        try:
            _write_sidecar({
                "label": label, "branch_env": branch_env,
                "fire": fired, "stop_reason": "checkpoint",
                "n": len(base_rows),
                "baseline_rows": base_rows, "branch_rows": brch_rows,
                "partial": True,
            }, label)
        except Exception:  # noqa: BLE001 — a checkpoint must never kill the run
            pass

        # ── A DEAD ENDPOINT IS NOT A DEAD LEVER ───────────────────────────
        #
        # R350.1 — excluding errored rows from `fire_check` (correct: an error
        # is not a divergence) created a new way to be wrong. If MOST rows
        # error, `common` collapses, `fired` goes False, and the run reports
        # INERT ("fix the lever — fresh env read? memo outliving the flip?") or
        # BLIND_PROBE ("fix the rows — raise --max-rows"). Both remedies are
        # wrong for a dead endpoint or an expired key, and `_report` returns
        # early on exactly those two verdicts, so the `errored` line that would
        # explain it never printed. Diagnose transport FIRST, with its own
        # verdict and exit code, and say so unconditionally.
        _errored = fired.get("errored", 0)
        _seen = _errored + fired["common"]
        if _seen and _errored / _seen >= _TRANSPORT_FAILURE_RATIO:
            emit("")
            emit(f"  TRANSPORT: {_errored}/{_seen} rows errored in one or both "
                 f"arms. This is NOT a lever result — the endpoint, the "
                 f"credential or the timeout is the problem. Fix that and "
                 f"re-run; do not read INERT as a finding about the feature.")
            res = {"label": label, "verdict": "TRANSPORT", "fire": fired,
                   "n_scored": 0, "axes": {}, "gold": {},
                   "baseline_rows": base_rows, "branch_rows": brch_rows}
            _write_sidecar(res, label)
            return res

        # ── THE GATE: a lever that never fired gets no axis table ──────────
        if not fired["fired"] and len(base_rows) >= min(batch * 2, len(pool)):
            # R336 — do NOT call it INERT until the probe has proven it could
            # have seen the change. Paid only here, on the rows already run, so
            # a firing A/B never carries the cost.
            ran = pool[:len(base_rows)]
            sens: dict[str, Any] | None = None
            control = resolve_control(branch_env, control_layer)
            if control is None:
                emit("")
                emit("  (no control flag available — every candidate is being "
                     "manipulated by this A/B; sensitivity unproven)")
            else:
                layer, control_env = control
                emit("")
                emit(f"  lever flat — checking the PROBE with a known-live "
                     f"{layer} control: {control_env}")
                sens = probe_sensitivity_check(
                    ran, base_rows, control_env, local=local,
                    endpoint=endpoint, api_key=api_key, timeout=timeout,
                    min_gap=min_gap)
                sens["layer"] = layer
                emit(f"  control moved {sens['rows_moved']}/"
                     f"{sens['rows_compared']} of the same rows")

            if sens is not None and not sens["sensitive"]:
                emit("")
                emit("  VERDICT: BLIND_PROBE — these rows cannot observe this "
                     "layer AT ALL.")
                emit("  A known-live control flag failed to move them either, "
                     "so the flat")
                emit("  result says nothing about your lever. Curated and "
                     "definitional rows")
                emit("  short-circuit to a direct KB lookup and never reach "
                     "retrieval, the")
                emit("  graph, or Stage-2 — a pool of them is blind by "
                     "construction.")
                emit("  FIX THE PROBE SET, not the feature: raise --max-rows, "
                     "or select rows")
                emit("  that exercise this layer, then re-run.")
                return {
                    "label": label, "verdict": "BLIND_PROBE", "fire": fired,
                    "sensitivity": sens, "branch_env": branch_env,
                    "n": len(base_rows), "baseline_rows": base_rows,
                    "branch_rows": brch_rows,
                }

            emit("")
            emit("  VERDICT: INERT — the two arms are identical on every row "
                 "run so far,")
            if sens is not None:
                emit(f"  and the probe is NOT blind: the {sens['layer']} "
                     f"control moved "
                     f"{sens['rows_moved']}/{sens['rows_compared']} of these "
                     f"same rows.")
                emit("  So this is a real finding about the lever, not about "
                     "the rows.")
            emit("  No axis numbers will be reported. A flat result and a dead "
                 "feature are")
            emit("  indistinguishable, so reporting +0.0000 here would be a "
                 "false negative,")
            emit("  not a null result. Fix the lever (fresh env read? memo "
                 "outliving the flip?")
            emit("  flag missing from _engine_cache_key? gate never reached?) "
                 "then re-run.")
            return {
                "label": label, "verdict": "INERT", "fire": fired,
                "sensitivity": sens, "branch_env": branch_env,
                "n": len(base_rows), "baseline_rows": base_rows,
                "branch_rows": brch_rows,
            }

        # ── adaptive stop: every axis resolved? ────────────────────────────
        # R353.3 — ``--min-rows`` is a floor on the ADAPTIVE stop only. A
        # small ``--batch`` checkpoints often (every batch, so the run is
        # survivable and inspectable), but the stop check at ``batch * 2``
        # would fire on a NULL-heavy sample and abort a lever that needs more
        # rows to show signal. With a floor, the run keeps going until it has
        # enough pairs to be representative; it still stops early on a clear
        # WIN/LOSS verdict once past the floor.
        if len(base_rows) >= max(batch * 2, min_rows):
            res = _analyse(base_rows, brch_rows, null_band=null_band)
            if all(v["verdict"] in ("WIN", "LOSS", "NULL")
                   for v in res["axes"].values()):
                stop_reason = "resolved"
                break

    res = _analyse(base_rows, brch_rows, null_band=null_band)
    res.update({
        "label": label, "branch_env": branch_env, "fire": fired,
        "stop_reason": stop_reason, "n": len(base_rows),
        "baseline_rows": base_rows, "branch_rows": brch_rows,
    })

    # R349 — the complete competition picture: the legal_v2 judge axes
    # (answer / reference correctness, citation faithfulness, conciseness)
    # per arm, joined to the retrieval axes as paired deltas. ON by default;
    # ``judge_model=None`` (--no-judge) skips entirely. Fail-soft: a judge
    # transport error leaves the retrieval axes fully reported with an honest
    # note, never a partial table pretending the judge axes were measured.
    if judge_model:
        try:
            caller = _judge_caller(judge_provider, judge_timeout, judge_model)
            if judge_provider != "wrapper":
                emit(f"judge: legal_v2 axes on {judge_model} via {judge_provider} "
                     f"(billed provider — REGENOLD_JUDGE_ALLOW_BILLED applies "
                     f"to the standalone CLI, not this in-run path)")
            probe_by_id = {str(pr.id): pr for pr in pool}
            # R350 — the error filter must be SYMMETRIC. It used to drop only
            # the BASELINE arm's errors and then select branch rows by id
            # membership alone, so a branch-arm timeout reached the judge with
            # an empty answer and scored as a real `fail` on all four axes:
            # a network blip read as the branch losing answer quality. One
            # predicate, both arms — matching `_analyse`, so the retrieval and
            # judge axes are computed over the SAME population.
            _healthy_branch = {c["id"] for c in brch_rows if not c.get("error")}
            common = [r for r in base_rows
                      if r.get("id") in _healthy_branch
                      and not r.get("error")]
            _common_ids = {r["id"] for r in common}
            j = _judge_axes(
                common,
                [c for c in brch_rows if c.get("id") in _common_ids],
                probe_by_id,
                caller=caller, samples=judge_samples,
                concurrency=judge_concurrency, null_band=null_band,
            )
            if "error" in j:
                emit(f"judge axes NOT computed: {j['error']}")
            else:
                for ax, v in j["axes"].items():
                    res["axes"][ax] = v
                def _passfail(judged: dict[str, Any], ax: str) -> dict[str, int]:
                    """R350.1 — route through `_scorable`, and report errors.

                    This counted `verdict == "fail"` regardless of any error
                    marker, so the SIDECAR's per-arm summary still scored
                    empty-answer timeouts as genuine fails — the exact bug
                    `_scorable` was written to kill, still live one level up in
                    the durable artefact.
                    """
                    p = f = e = 0
                    for r in judged.values():
                        v = (r.get("verdicts") or {}).get(ax) or {}
                        if not _scorable(v):
                            e += 1
                            continue
                        if str(v.get("verdict")).lower() == "pass":
                            p += 1
                        else:
                            f += 1
                    return {"pass": p, "fail": f, "error": e}

                res["judge"] = {
                    "model": judge_model, "provider": judge_provider,
                    "samples": max(1, int(judge_samples)),
                    "base": {ax: _passfail(j["base"]["judged"], ax)
                              for ax, _lbl in _JUDGE_AXES},
                    "branch": {ax: _passfail(j["branch"]["judged"], ax)
                                for ax, _lbl in _JUDGE_AXES},
                }
        except Exception as exc:  # noqa: BLE001 — a judge failure must never break the A/B
            emit(f"judge axes NOT computed: {exc}")
    return res


def _analyse(
    base_rows: list[dict[str, Any]],
    brch_rows: list[dict[str, Any]],
    *,
    null_band: float,
) -> dict[str, Any]:
    b = {r["id"]: r for r in base_rows}
    c = {r["id"]: r for r in brch_rows}
    common = [i for i in b if i in c and not b[i].get("error")
              and not c[i].get("error")]
    axes: dict[str, Any] = {}
    for ax in _AXES:
        deltas = [c[i]["scores"][ax] - b[i]["scores"][ax] for i in common]
        if not deltas:
            continue
        mean = st.fmean(deltas)
        lo, hi = _bootstrap_ci(deltas)
        axes[ax] = {
            "baseline": st.fmean(b[i]["scores"][ax] for i in common),
            "branch": st.fmean(c[i]["scores"][ax] for i in common),
            "delta": mean, "ci_lo": lo, "ci_hi": hi,
            "n_changed": sum(1 for d in deltas if d != 0),
            "verdict": _verdict(mean, lo, hi, null_band=null_band,
                                n_pairs=len(deltas)),
            "n_pairs": len(deltas),
        }
    # ── the veto block ────────────────────────────────────────────────────
    #
    # R337 — GOLD SHAPE decides which veto grain is valid, and getting this
    # wrong rejects correct work.
    #
    # `gold_dropped` is a VETO (hard rule #8), so it is meant to be read without
    # argument. But `gold_dropped_exact` compares full coordinates, and this
    # probe set's gold carries NO sub-points (re-measured 2026-08-15: 132 rows,
    # 208 gold refs, 0 leaf-grained). Against head-level gold, a MORE precise
    # citation scores as a dropped head:
    #
    #     gold_dropped_exact(["Article 6.1"], gold=["Article 6"]) -> dropped 1
    #     gold_dropped_head (["Article 6.1"], gold=["Article 6"]) -> dropped 0
    #
    # So on head-level gold the exact veto does not measure "did we lose gold",
    # it measures "did we get more precise" with the sign inverted. Measured on
    # R333's sub-point fix: exact said 10 -> 5 (apparently double the drops)
    # while head said +0 and every axis was exactly 0.0000. Read literally, the
    # veto rejects a change that dropped nothing.
    #
    # R337.1 — TWO defects in the first cut of that guard, each of which made it
    # worse than having no guard at all:
    #
    #   (a) It read the gold from `b[i]["row"]`, a key `_run_rows` has never
    #       written (its record carries id / source / pred_answer / pred_refs /
    #       latency_ms / http_status / error / scores). `gold_refs` was
    #       therefore always empty, `applicable` always False, and since
    #       `_report`'s rejection test filters on `applicable`, an exact-grain
    #       gold drop could NEVER print REJECTED. Fixed at the PRODUCER —
    #       `_row_record` now carries `gold_refs` — because a guard that reads a
    #       key nobody writes is indistinguishable from a guard switched off.
    #
    #   (b) The switch was GLOBAL. One leaf-grained gold ref anywhere in the
    #       sample re-enabled the exact veto for every head-level row in it, so
    #       on a mixed pool the guard reinstates exactly the false rejection it
    #       exists to prevent. The grain is now decided PER ROW: the exact veto
    #       sums only over rows whose OWN gold carries a sub-point, and it
    #       records that population so the printed line is self-describing.
    #
    # The KEY CHANGED WITH THE MATHS — `gold_dropped_exact` ->
    # `gold_dropped_exact_leaf_rows` — per CLAUDE.md's "if you change a formula,
    # change its NAME". The old key summed every scored row; the new one sums a
    # row subset, so the two are not comparable and must not share a name. The
    # all-rows figure is still recorded (`all_rows_*`) so an older sidecar stays
    # readable, but it is a DIAGNOSTIC and never a veto: on head-level gold it
    # counts precision gains as losses, which is the whole finding.
    def _gold_for(rid: str) -> list[str]:
        # Both arms run the SAME ProbeRow, so either record carries the same
        # gold; prefer the baseline and fall back so one arm's absence cannot
        # silently blank the grain (blank grain == veto off, so it must not be
        # reachable by accident).
        raw = b[rid].get("gold_refs") or c[rid].get("gold_refs") or ()
        return [str(x) for x in raw]

    gold_refs_all = [g for i in common for g in _gold_for(i)]
    leaf_rows = [i for i in common if any(map(_carries_sub_point, _gold_for(i)))]

    gold: dict[str, Any] = {
        "gold_dropped_head": {
            "baseline": sum(b[i]["scores"]["gold_dropped_head"] for i in common),
            "branch": sum(c[i]["scores"]["gold_dropped_head"] for i in common),
            "applicable": True,
            "rows_counted": len(common),
            "rows_scored": len(common),
            "population": f"all {len(common)} scored rows",
        },
        "gold_dropped_exact_leaf_rows": {
            # float() so an empty leaf population serialises as 0.0 like every
            # other figure here, rather than as a bare int nobody expected.
            "baseline": float(sum(
                b[i]["scores"]["gold_dropped_exact"] for i in leaf_rows)),
            "branch": float(sum(
                c[i]["scores"]["gold_dropped_exact"] for i in leaf_rows)),
            "applicable": bool(leaf_rows),
            "rows_counted": len(leaf_rows),
            "rows_scored": len(common),
            "population": (f"{len(leaf_rows)} of {len(common)} rows with "
                           f"leaf-grained gold"),
            "gold_refs_total": len(gold_refs_all),
            "gold_leaf_grained": sum(map(_carries_sub_point, gold_refs_all)),
            # Diagnostic only — the historical all-rows sum. Kept so a
            # pre-R337.1 sidecar can still be lined up against a new run;
            # deliberately NOT part of the veto.
            "all_rows_baseline": sum(
                b[i]["scores"]["gold_dropped_exact"] for i in common),
            "all_rows_branch": sum(
                c[i]["scores"]["gold_dropped_exact"] for i in common),
        },
    }
    for v in gold.values():
        v["delta"] = v["branch"] - v["baseline"]
    ex = gold["gold_dropped_exact_leaf_rows"]
    ex["all_rows_delta"] = ex["all_rows_branch"] - ex["all_rows_baseline"]
    return {"axes": axes, "gold": gold, "n_scored": len(common)}


def _json_safe(obj: Any) -> Any:
    """Replace non-finite floats with ``None`` so the sidecar is VALID JSON.

    ⚠ R350 — ``json.dumps`` emits bare ``Infinity`` / ``NaN`` for non-finite
    floats. Python round-trips those happily, so a Python-only test would never
    catch it, but they are **not JSON** (RFC 8259 has no such literals): ``jq``,
    every browser, and any strict parser reject the whole file. The sidecar is
    this repo's durable measurement artefact — a run that cannot be re-read by
    standard tooling has lost its evidence.

    This became reachable in the same round: ``_bootstrap_ci`` now returns
    ``(-inf, +inf)`` for a single observation, which is the honest interval and
    exactly the value that would have poisoned the file. ``null`` is the correct
    JSON spelling of "no bound".
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _write_sidecar(res: dict[str, Any], label: str) -> None:
    """Persist the run state as a JSON sidecar under evals/bench/results.

    R346 — batch-level checkpoints. A live A/B (Bedrock Stage-2) runs tens of
    minutes per arm; a crash between batches used to lose the whole run
    because the sidecar was written once, at the end. This is callable after
    EVERY batch, so a killed run still leaves the rows it completed, and the
    final call overwrites the checkpoint with the complete state.

    ⚠ R350 — the write is now ATOMIC (temp file + ``os.replace``). It used to
    be a bare ``write_text``, which truncates the existing file before a single
    byte of the new content lands — so an interrupt during the write destroyed
    the PREVIOUS good checkpoint as well as the new one, leaving unparseable
    JSON. Ctrl-C during a multi-hour live A/B is the documented interruption
    mode and lands in exactly that window, and the payload grows every batch,
    so the window widens as the run gets more expensive to lose. ``os.replace``
    is atomic on both Windows and POSIX.
    """
    _RESULTS.mkdir(parents=True, exist_ok=True)
    out = _RESULTS / f"dynamic-ab-{label}.json"
    slim = {k: v for k, v in res.items()
            if k not in ("baseline_rows", "branch_rows")}
    slim["baseline_rows"] = res.get("baseline_rows", [])
    slim["branch_rows"] = res.get("branch_rows", [])
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_json_safe(slim), indent=2), encoding="utf-8")
    os.replace(tmp, out)


def _report(res: dict[str, Any], emit: Callable[[str], None] = print) -> None:
    f = res.get("fire") or {}
    if res.get("verdict") in ("INERT", "BLIND_PROBE", "TRANSPORT"):
        # R350.1 — print the error count even on the verdicts that return
        # early. These are exactly the verdicts a transport outage produces,
        # and the errored count is the one line that distinguishes "the lever
        # is dead" from "the endpoint is dead".
        if f.get("errored"):
            emit(f"  {f['errored']} row(s) errored in one or both arms "
                 f"({f.get('common', 0)} clean pairs compared)")
        return
    emit("")
    emit(f"=== {res['label']} — n={res['n_scored']} paired "
         f"(stop: {res.get('stop_reason')}) ===")
    emit(f"  lever FIRED on {f.get('any_changed', 0)}/{f.get('common', 0)} rows "
         f"— numbers below are about a change that actually happened")
    if f.get("errored"):
        emit(f"  {f['errored']} row(s) errored in one or both arms and are "
             f"excluded from the fire check AND every axis")
    emit("")
    # R350 — `n` is PER AXIS. The judge axes score only the rows that reached
    # Stage-2 and judged cleanly in BOTH arms, so they routinely run on a small
    # fraction of the header's n. Printing one n for the whole table let a
    # 2-pair judge axis borrow the credibility of a 60-row retrieval axis.
    emit(f"  {'axis':<12} {'baseline':>9} {'branch':>9} {'delta':>9} "
         f"{'95% CI':>20} {'n/-skip':>7}  verdict")
    for ax, v in res["axes"].items():
        ci = f"[{v['ci_lo']:+.4f},{v['ci_hi']:+.4f}]"
        n = v.get("n_pairs")
        # R350.1 — `n_skipped` was stored and never shown. A reader saw n=4
        # with no hint that 18 pairs were dropped for judge errors.
        sk = v.get("n_skipped")
        n_col = "-" if n is None else (f"{n}" if not sk else f"{n}/-{sk}")
        emit(f"  {ax:<12} {v['baseline']:>9.4f} {v['branch']:>9.4f} "
             f"{v['delta']:>+9.4f} {ci:>20} {n_col:>7}  {v['verdict']}")
    j = res.get("judge")
    if j:
        # ASCII only: the cp1252 console crashes on box-drawing chars,
        # and this line sits ABOVE the gold veto + the sidecar write.
        # Pinned by test_r350_review_fixes.TestReportSurvivesOnACp1252Console.
        emit(f"  -- ans_corr / ref_corr / cite_faith / ans_conc are the "
             f"legal_v2 judge axes ({j.get('model')} via {j.get('provider')}, "
             f"K={j.get('samples')}) -- pass rate over paired non-error rows; "
             f"answer-level, per the Regenold rubric")
    emit("")
    for g, v in res["gold"].items():
        # R337 — an inapplicable veto prints its REASON, never a number. On
        # head-level gold the exact-grain drop counts precision GAINS as losses,
        # so showing the figure invites a rejection of correct work.
        #
        # R337.1 — and an APPLICABLE veto prints its POPULATION, because the
        # grain is now decided per row: "+5" means nothing until you know it was
        # summed over the 12 rows that could support it, not over all 32.
        if not v.get("applicable", True):
            emit(f"  {g:<28} {'n/a':>6} — 0 of {v.get('rows_scored', 0)} rows "
                 f"carry leaf-grained gold ({v.get('gold_refs_total', 0)} gold "
                 f"refs, {v.get('gold_leaf_grained', 0)} with a sub-point), so "
                 f"the exact-grain veto has no population; head grain above is "
                 f"authoritative")
            continue
        flag = "  <-- HARD RULE #8 VETO" if v["delta"] > 0 else ""
        emit(f"  {g:<28} {v['baseline']:>6.0f} -> {v['branch']:>6.0f} "
             f"({v['delta']:+.0f})  over {v.get('population', 'n/a')}{flag}")
    if any(v["delta"] > 0 for v in res["gold"].values()
           if v.get("applicable", True)):
        emit("")
        emit("  REJECTED: the branch drops gold references. Hard rule #8 is a "
             "veto, not a")
        emit("  trade-off — do not weigh this against a win on another axis.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--flag", help="shorthand for --branch-env FLAG=1")
    ap.add_argument("--branch-env", action="append", default=[],
                    help="KEY=VALUE applied to the branch arm only")
    ap.add_argument("--label", default="dynamic-ab")
    ap.add_argument("--max-rows", type=int, default=60)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--min-rows", type=int, default=0,
                    help="floor on the adaptive stop — keep running until at "
                         "least this many rows even if all axes resolve NULL "
                         "early (checkpoints still land every batch)")
    # R350 — was `action="store_true", default=True`, which can only ever
    # produce True: `--endpoint` was parsed, threaded all the way through
    # run() and _run_rows, and then silently ignored, so an operator aiming the
    # merge gate at the deployed Railway service measured their local working
    # tree instead — with nothing in the sidecar recording which system was
    # under test. BooleanOptionalAction gives a real `--no-local`, and passing
    # `--endpoint` now implies it rather than being quietly dropped.
    ap.add_argument("--local", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="run the engine in-process (default). --no-local, or "
                         "any --endpoint, POSTs to a deployed service instead")
    ap.add_argument("--endpoint",
                    help="deployed service base URL; implies --no-local")
    ap.add_argument("--api-key", default=os.getenv("REGENOLD_API_KEY", ""))
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--null-band", type=float, default=0.01,
                    help="half-width under which a zero-spanning CI is a NULL")
    ap.add_argument("--min-call-gap", type=float, default=0.0,
                    help="minimum seconds between POSTs — rate-limit pacing "
                         "(the Cohere Trial key allows 10 calls/min, so the "
                         "rerank A/B needs ~6.5)")
    ap.add_argument("--seed", type=int, default=_SEED)
    ap.add_argument("--control-layer", choices=("retrieval", "stage2", "graph"),
                    default=None,
                    help="force the probe-sensitivity control layer "
                         "(default: inferred from the branch flag name)")
    ap.add_argument("--judge-model", default="qwen.qwen3-32b-v1:0",
                    help="legal_v2 judge model (R349 answer-level axes)")
    ap.add_argument("--judge-provider",
                    choices=("wrapper", "anthropic", "groq", "gemini", "bedrock", "openrouter"),
                    default="bedrock")
    ap.add_argument("--judge-concurrency", type=int, default=4)
    ap.add_argument("--judge-timeout", type=float, default=120.0)
    ap.add_argument("--judge-samples", type=int, default=1,
                    help="judge self-consistency K (majority verdict; 2-way ties fail)")
    ap.add_argument("--no-judge", action="store_true",
                    help="skip the legal_v2 judge axes entirely")
    ap.add_argument("--probe-sources", default=None,
                    help="comma-separated probe source tags to run (e.g. "
                         "graphrag,medtech,expert_review) — default: all")
    args = ap.parse_args()

    branch_env: dict[str, str] = {}
    if args.flag:
        branch_env[args.flag] = "1"
    for kv in args.branch_env:
        k, _, v = kv.partition("=")
        branch_env[k.strip()] = v.strip()
    if not branch_env:
        ap.error("nothing to A/B — pass --flag or --branch-env")

    # R350 — --endpoint implies --no-local. Silently measuring the local tree
    # while the operator believes they are measuring the deployed service is
    # the instrument trap pointed at the wrong SYSTEM, not merely the wrong
    # lens, so resolve it explicitly and say which one is under test.
    local = bool(args.local)
    if args.endpoint and "--local" not in sys.argv:
        local = False
    if args.endpoint and local:
        ap.error("--endpoint with --local: pick one. --endpoint alone POSTs to "
                 "the deployed service; --local runs the engine in-process.")
    if not local and not args.endpoint:
        ap.error("--no-local needs --endpoint")
    if not local:
        # R350.1 — making --endpoint reachable exposed that it CANNOT work:
        # `_run_rows` applies the arm env to the LOCAL os.environ, and the POST
        # body carries only the message history, so there is no mechanism to
        # set the branch flag on a remote service. Both arms would hit the same
        # deployed config, diverge on nothing, and report INERT — a confidently
        # wrong "fix the feature". Refuse instead of measuring the wrong thing.
        ap.error(
            "--endpoint cannot run an A/B: the branch env is applied in THIS "
            "process and cannot reach a deployed service, so both arms would "
            "be identical and the run would report a false INERT. Use --local "
            "(the default) for A/Bs; probe a deployment with runner_v2."
        )
    print(f"system under test: {'in-process engine' if local else args.endpoint}")

    res = run(
        branch_env=branch_env, label=args.label, max_rows=args.max_rows,
        batch=args.batch, local=local, endpoint=args.endpoint,
        api_key=args.api_key or None, timeout=args.timeout,
        null_band=args.null_band, seed=args.seed, min_rows=args.min_rows,
        control_layer=args.control_layer, min_gap=args.min_call_gap,
        judge_model=(None if args.no_judge else args.judge_model),
        judge_provider=args.judge_provider,
        judge_concurrency=args.judge_concurrency,
        judge_timeout=args.judge_timeout,
        judge_samples=args.judge_samples,
        probe_sources=(tuple(s.strip() for s in args.probe_sources.split(",") if s.strip())
                       if args.probe_sources else None),
    )
    # R350 — the sidecar is written in a `finally`. A single unencodable
    # character in the report (a U+2500 in the R349 judge-provenance line, on a
    # cp1252 Windows console — the documented platform) used to raise between
    # the axis table and the gold_dropped veto block, so the HARD RULE #8 VETO
    # never printed AND the result file was never written: a multi-hour live
    # A/B lost both its verdict and its data to a box-drawing character.
    # Reporting is presentation; persistence must not depend on it.
    try:
        _report(res)
    finally:
        _write_sidecar(res, args.label)
        print(f"\nwrote {_RESULTS / ('dynamic-ab-' + args.label + '.json')}")
    # 0 = measured, 2 = lever inert (fix the feature),
    # 3 = probe blind (fix the rows) — a different action, so a different code.
    # 4 = TRANSPORT (fix the endpoint/credential) — distinct from 2 "fix the
    # feature" and 3 "fix the rows", because the remedy is different again.
    sys.exit({"INERT": 2, "BLIND_PROBE": 3, "TRANSPORT": 4}
             .get(res.get("verdict"), 0))


if __name__ == "__main__":
    main()

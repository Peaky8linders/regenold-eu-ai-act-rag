"""R451 — contextual-field (BM25F) weight sweep, measurement over argument.

WHY THIS EXISTS
===============

R449 built the fielded BM25 path (``REGENOLD_CONTEXTUAL_FIELDS``: deterministic
title/chapter/section context indexed as its own ``title`` field, scored as
BM25F) and measured it at ONE weight setting — ``title=2.0, body=1.0,
b_title=0.6, b_body=0.75`` — chosen by argument: "the title field is short, so
it gets a higher weight". Those four numbers were never tuned. The round's
verdict ("weak-positive inside noise, stays OFF") is therefore a verdict on an
untuned configuration, which is not the same claim as a verdict on the
technique. A title weight that is too high displaces real body matches; too low
and the context prefix does nothing. Which side of that the shipped cell sits on
is an empirical question nobody has asked.

This module turns the choice into a repeatable measurement: it sweeps the four
parameters over the real 110-row gold set through the PRODUCTION entry point
(weights are read per score call, so one process and one built index serve the
whole grid) and reports, per cell:

* head-grain recall / all-heads / nDCG at the production k,
* context cost (verbatim characters pulled for the returned heads),
* how many references the cell ADDS versus the sparse control and how many of
  those additions are gold — R449's weakest-link measurement, which is what
  separates a real recall gain from churn,
* how many rows' retrieved SET differs from the shipped contextual cell (churn
  against the configuration we would be replacing).

The SPARSE control (``REGENOLD_CONTEXTUAL_FIELDS=0``, index rebuilt) is a first-
class row in the table: it answers "is the fielded path worth any weight at all"
on the same rows, same k, same floor, which is the question R449 left at
"inside noise".

GRID SHAPE
==========

One-factor-at-a-time around the shipped cell, in four families: ``w`` (title
weight), ``bt`` (title length slope), ``bb`` (body length slope), ``bw`` (body
weight). A full 4-D grid would multiply the multiplicity problem; with n=110 the
honest question is "does the title weight matter at all", not "what is the
optimum of a 625-cell surface". Every grid value sits INSIDE the production
clamps (weight 0.1-10.0, b 0.0-0.999) — ``tests/test_r451_field_weights.py``
pins that — because a value outside them is silently clamped and the table would
then print a weight the ranker never used. Weight 0.0 is therefore NOT in the
grid: the clamp makes it 0.1, and 0.1 is what the family's low extreme means.

``bw`` is included deliberately even though the *scale* of the weights looks
like a pure rescaling. It is not: BM25's saturation term
``idf·t̃f·(k1+1)/(k1+t̃f)`` is concave, so the title/body *ratio* reorders, and
the absolute scale moves documents across the hard ``min_score`` floor that
decides whether ``k`` fills at all. A body-weight cell therefore measures two
effects at once — a known confound, reported rather than hidden, and the reason
no cell here is a promotion candidate on scale alone.

NOISE, NOT VIBES
================

n=110 rows is small, so a raw delta is not a finding. Every cell is compared to
the shipped cell with a **paired** row bootstrap (deterministic seed, 10,000
resamples) on the two pre-registered primary axes, and the harness prints the
95% CI of the paired delta. A cell is only a candidate for promotion when the CI
excludes zero upwards on at least one primary axis and neither axis excludes zero
downwards. The verdict column is computed from that rule, never eyeballed — the
same discipline the repo applies to live gates, applied offline where it is
cheap. The CIs are per-cell and multiplicity-unadjusted: with ~13 comparisons a
single marginal CI is a lead, not a result, and the verdict column says so by
refusing to promote on one.

THE SPARSE CONTROL NEEDS A REBUILD
==================================

``app.data.kb_search._build_index`` is ``lru_cache(maxsize=1)`` and the
fielded/plain decision is baked in AT BUILD TIME (``_score`` dispatches on
``index.field_freqs`` being non-empty, not on the env var). Flipping
``REGENOLD_CONTEXTUAL_FIELDS`` in a warm process therefore does nothing: a
control run after the fielded arm scores through the *fielded* index. The
control pass here clears the cache and rebuilds, and the fielded grid then shares
one build. Getting this wrong would make the control silently equal to a fielded
cell.

WHAT IT DOES NOT DO
===================

No network, no judge, no LLM, no flag flip. A retrieval-grain gain is not
evidence that an official axis moves, and this harness never promotes anything by
itself: it reports a verdict, and the default field weights only change when a
later round accepts that verdict on a live gate.

USAGE
=====

    python -m evals.retrieval.field_weight_sweep
    python -m evals.retrieval.field_weight_sweep --rows 30 --seed 7
    python -m evals.retrieval.field_weight_sweep \
        --out docs/measurements/r451/field-weight-sweep.json \
        --md-out docs/measurements/r451/FIELD-WEIGHT-SWEEP.md
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# ── Deterministic offline environment (before any app.* import) ──────────────
_OFFLINE_ENV: dict[str, str] = {
    "REGENOLD_SKIP_DOTENV": "1",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_GRAPH_2HOP": "0",
    "REGENOLD_COHERE_RERANK": "0",
    "REGENOLD_HYPA_RRF_RETRIEVAL": "0",
    # The sweep needs the FIELDED index; the weights themselves are per-call.
    "REGENOLD_CONTEXTUAL_FIELDS": "1",
    # The dense stages are held OFF so the measured effect is the FIELD WEIGHTS
    # and not the sentence-SVD boost (R449 measured that stage displacing BM25
    # winners; letting it move underneath a weight sweep would confound the two).
    "REGENOLD_TURBOQUANT_DENSE": "0",
    "REGENOLD_EMBEDDINGS_INDEX": "0",
    "REGENOLD_RRF_FUSION": "0",
    "REGENOLD_SCORE_FUSION": "0",
}

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_GOLD = _REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

#: Bootstrap settings. One seed and one resample count for every interval in a
#: run, so the verdict, the multiplicity diagnostic and the control comparison are
#: slices of the SAME distributions and cannot disagree about the data.
_BOOTSTRAP_SEED = 20260928
_RESAMPLES = 10_000

#: The k the deterministic-parse fallback lane uses (``_BM25_FALLBACK_K``) and
#: the floor that lane passes (``min_score=1.0``). Both mirror
#: :func:`evals.retrieval.unit_grain._retrieve`, which mirrors production.
_PRODUCTION_K = 8
_MIN_SCORE = 1.0

#: The production clamps, duplicated as literals so the harness can assert its own
#: grid is representable without importing the app. ``tests/test_r451_field_weights.py``
#: pins them equal to ``kb_search._FIELD_WEIGHT_BOUNDS`` / ``_FIELD_B_BOUNDS``.
_FIELD_WEIGHT_BOUNDS = (0.1, 10.0)
_FIELD_B_BOUNDS = (0.0, 0.999)

#: The shipped cell — R449's by-argument values. Every delta is paired against it.
SHIPPED: dict[str, float] = {
    "w_title": 2.0,
    "w_body": 1.0,
    "b_title": 0.6,
    "b_body": 0.75,
}

#: Default grid families. Coarse and one-factor-at-a-time: each family includes
#: the shipped value so its own baseline is visible in the table, and its
#: extremes bracket "field ignored" (weight at the 0.1 clamp floor, b -> 0) and
#: "no length normalisation" (b -> 0.9) rather than sampling a surface nobody can
#: resolve at n=110.
#:
#: NOTE the 0.1: weight 0.0 is NOT a thing production can express (the clamp
#: floors it at 0.1), so 0.1 is the honest low extreme.
TITLE_WEIGHTS: tuple[float, ...] = (0.1, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
TITLE_B: tuple[float, ...] = (0.0, 0.3, 0.6, 0.9)
BODY_WEIGHTS: tuple[float, ...] = (0.5, 2.0)

#: ``b_body`` gets a denser grid than the other families ON PURPOSE. The first
#: coarse pass (``field-weight-sweep-coarse.json``) found a monotone effect here
#: — 0.5 significantly better than the shipped 0.75, 0.9 significantly worse —
#: and nothing at all in the other three families. "Does this parameter matter"
#: was answered by the coarse pass; "where is its optimum" needs points between
#: 0.3 and 0.6. The accept rule is unchanged between the two passes; only the
#: grid was extended, which is refinement rather than re-registration.
BODY_B: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.75, 0.9)

#: Label for the un-fielded control row.
SPARSE_LABEL = "sparse"


@dataclass(frozen=True)
class Cell:
    """One weight configuration, and the env overrides that express it."""

    label: str
    w_title: float
    w_body: float
    b_title: float
    b_body: float

    def env(self) -> dict[str, str]:
        return {
            "REGENOLD_FIELD_WEIGHT_TITLE": f"{self.w_title:g}",
            "REGENOLD_FIELD_WEIGHT_BODY": f"{self.w_body:g}",
            "REGENOLD_FIELD_B_TITLE": f"{self.b_title:g}",
            "REGENOLD_FIELD_B_BODY": f"{self.b_body:g}",
        }


@dataclass
class CellResult:
    label: str
    w_title: float
    w_body: float
    b_title: float
    b_body: float
    head_recall: float
    row_all_heads: float
    ndcg: float
    excess_refs: float
    context_chars: float
    added_refs: int
    added_gold: int
    churn_rows: int
    per_row_recall: list[float]
    per_row_ndcg: list[float]
    #: False for the sparse control, whose scoring ignores the four weights.
    fielded: bool = True

    @property
    def added_precision(self) -> float:
        return (self.added_gold / self.added_refs) if self.added_refs else 0.0


def build_grid(
    *,
    title_weights: Sequence[float] = TITLE_WEIGHTS,
    title_b: Sequence[float] = TITLE_B,
    body_b: Sequence[float] = BODY_B,
    body_weights: Sequence[float] = BODY_WEIGHTS,
) -> list[Cell]:
    """The shipped cell plus four one-factor-at-a-time families, deduplicated.

    The shipped parameter tuple appears inside every family (it is each family's
    baseline), so the dedup key keeps exactly one cell for it and that cell is
    labelled ``shipped`` — every paired delta and the churn baseline key off that
    label, so letting a family overwrite it (``w2``) would silently break the
    whole comparison. The shipped cell is therefore labelled LAST, and returned
    FIRST.
    """
    cells: dict[tuple[float, float, float, float], Cell] = {}

    def _add(label: str, w_t: float, w_b: float, b_t: float, b_b: float) -> None:
        cells[(w_t, w_b, b_t, b_b)] = Cell(
            label=label, w_title=w_t, w_body=w_b, b_title=b_t, b_body=b_b
        )

    for w in title_weights:
        _add(f"w{w:g}", w, SHIPPED["w_body"], SHIPPED["b_title"], SHIPPED["b_body"])
    for b in title_b:
        _add(f"bt{b:g}", SHIPPED["w_title"], SHIPPED["w_body"], b, SHIPPED["b_body"])
    for b in body_b:
        _add(f"bb{b:g}", SHIPPED["w_title"], SHIPPED["w_body"], SHIPPED["b_title"], b)
    for w in body_weights:
        _add(f"bw{w:g}", SHIPPED["w_title"], w, SHIPPED["b_title"], SHIPPED["b_body"])

    shipped = Cell(
        label="shipped",
        w_title=SHIPPED["w_title"],
        w_body=SHIPPED["w_body"],
        b_title=SHIPPED["b_title"],
        b_body=SHIPPED["b_body"],
    )
    cells[(shipped.w_title, shipped.w_body, shipped.b_title, shipped.b_body)] = shipped
    others = [c for c in cells.values() if c.label != "shipped"]
    return [shipped, *sorted(others, key=lambda c: c.label)]


def assert_grid_representable(cells: Sequence[Cell]) -> None:
    """Every cell must survive the production clamps untouched.

    A grid value outside the clamp is silently replaced, and the table would
    then print a weight the ranker never used — a measurement of the wrong
    configuration, invisible in the output.
    """
    w_lo, w_hi = _FIELD_WEIGHT_BOUNDS
    b_lo, b_hi = _FIELD_B_BOUNDS
    checks = (
        ("w_title", w_lo, w_hi),
        ("w_body", w_lo, w_hi),
        ("b_title", b_lo, b_hi),
        ("b_body", b_lo, b_hi),
    )
    for cell in cells:
        bad = [
            f"{name}={getattr(cell, name):g}"
            for name, lo, hi in checks
            if not lo <= getattr(cell, name) <= hi
        ]
        if bad:
            raise ValueError(f"grid cell {cell.label!r} is clamped by production: {bad}")


# ── Paired statistics ────────────────────────────────────────────────────────


def paired_delta_ci(
    baseline: Sequence[float],
    cell: Sequence[float],
    *,
    seed: int = _BOOTSTRAP_SEED,
    resamples: int = _RESAMPLES,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """``1 - alpha`` CI of ``mean(cell - baseline)``, resampling ROWS (the paired unit).

    The argument order IS the sign convention, and it is spelled out rather than
    inferred: the returned delta is positive when the CELL is better. An earlier
    revision computed ``b - a`` from a ``(a, b)`` pair and the callers passed
    cells first, which inverted every delta and every verdict while leaving the
    aggregate means (correctly) un-inverted — the contradiction between an
    aggregate column and its paired delta is the tell that the sign is wrong.

    Resampling rows rather than recomputing on resampled corpora is deliberate:
    the rows are the sampling unit, and a paired row bootstrap respects that the
    two arms saw identical questions. Deterministic for a fixed seed so a verdict
    is reproducible.
    """
    if len(baseline) != len(cell) or not baseline:
        return 0.0, 0.0, 0.0
    observed, means = _bootstrap_means(baseline, cell, seed=seed, resamples=resamples)
    lo, hi = _quantiles(means, alpha, resamples)
    return observed, lo, hi


def _bootstrap_means(
    baseline: Sequence[float], cell: Sequence[float], *, seed: int, resamples: int
) -> tuple[float, list[float]]:
    """The paired row-bootstrap distribution of ``mean(cell - baseline)``, sorted.

    Returned rather than reduced to one interval so a caller can read several
    alpha levels off ONE resample set: the Bonferroni-adjusted interval is a
    slice of the same distribution, not a second draw, so the diagnostic and the
    verdict can never disagree about the data they came from.
    """
    deltas = [c - b for b, c in zip(baseline, cell, strict=True)]
    observed = sum(deltas) / len(deltas)
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(rng.choices(deltas, k=n)) / n for _ in range(resamples))
    return observed, means


def _quantiles(means: Sequence[float], alpha: float, resamples: int) -> tuple[float, float]:
    """Two-sided ``1 - alpha`` quantiles of a sorted bootstrap distribution."""
    lo = means[min(resamples - 1, int((alpha / 2.0) * resamples))]
    hi = means[min(resamples - 1, int((1.0 - alpha / 2.0) * resamples))]
    return lo, hi


def verdict_for(
    cell: CellResult, baseline: CellResult, *, seed: int, n_comparisons: int = 1
) -> dict[str, Any]:
    """Pre-registered accept rule, computed and not eyeballed.

    PROMOTE requires ALL of:
      1. the paired head-recall CI excludes zero upwards, or the paired nDCG CI
         does (a real ordering gain on at least one primary axis);
      2. neither primary axis' CI excludes zero *downwards* (no significant
         loss on the other);
      3. the additions are not churn: ``added_precision`` at least matches the
         shipped cell's, or the cell adds nothing at all.
    Everything else is HOLD, with the failing clause named. The clause that
    failed is named so a reader can see whether the block was evidence or a
    technicality, and re-register a different rule NEXT round rather than
    editing this one after seeing the numbers.

    ``n_comparisons`` adds a Bonferroni-adjusted CI as a REPORTED DIAGNOSTIC,
    not as a change to the rule: sweeping k cells at alpha=0.05 buys roughly one
    marginal false positive per twenty comparisons, so a cell that clears the
    rule on a CI whose lower bound is barely above zero has to be reported as a
    weak lead even though the pre-registered clause passed. ``survives_multiplicity``
    is that reading, computed rather than argued.
    """
    r_obs, r_means = _bootstrap_means(
        baseline.per_row_recall, cell.per_row_recall, seed=seed, resamples=_RESAMPLES
    )
    n_obs, n_means = _bootstrap_means(
        baseline.per_row_ndcg, cell.per_row_ndcg, seed=seed, resamples=_RESAMPLES
    )
    r_lo, r_hi = _quantiles(r_means, 0.05, _RESAMPLES)
    n_lo, n_hi = _quantiles(n_means, 0.05, _RESAMPLES)
    gain = r_lo > 0 or n_lo > 0
    loss = r_hi < 0 or n_hi < 0
    churn_ok = cell.added_refs == 0 or cell.added_precision >= baseline.added_precision

    n_cmp = max(2, n_comparisons)
    adj = 0.05 / n_cmp
    r_lo_adj, r_hi_adj = _quantiles(r_means, adj, _RESAMPLES)
    n_lo_adj, n_hi_adj = _quantiles(n_means, adj, _RESAMPLES)
    survives = (r_lo_adj > 0) or (n_lo_adj > 0)

    if gain and not loss and churn_ok:
        verdict = "PROMOTE"
    elif loss:
        verdict = "HOLD (significant loss)"
    elif not gain:
        verdict = "HOLD (inside noise)"
    else:
        verdict = "HOLD (churn)"
    return {
        "verdict": verdict,
        "recall_delta": r_obs,
        "recall_ci": [r_lo, r_hi],
        "ndcg_delta": n_obs,
        "ndcg_ci": [n_lo, n_hi],
        "added_precision": cell.added_precision,
        "churn_ok": churn_ok,
        "n_comparisons": n_cmp,
        "alpha_adjusted": adj,
        "recall_ci_adj": [r_lo_adj, r_hi_adj],
        "ndcg_ci_adj": [n_lo_adj, n_hi_adj],
        "survives_multiplicity": survives,
    }


def vs_control(
    results: Sequence[CellResult], control: CellResult, *, seed: int, n_comparisons: int
) -> dict[str, dict[str, Any]]:
    """Each fielded cell paired against the SPARSE control, not against shipped.

    The rule's baseline (``shipped``) answers "which weights, given that the path
    ships". This answers the prior question — "does the fielded path beat having
    no fields at all, and at which weights" — with the same paired bootstrap. It
    deliberately carries NO verdict: the pre-registered rule is scored against
    the shipped cell exactly once, and a second, friendlier comparison must not
    be able to manufacture a PROMOTE. ``beats_control`` is a reported read.
    """
    adj = 0.05 / max(2, n_comparisons)
    out: dict[str, dict[str, Any]] = {}
    for r in results:
        if r.label == control.label:
            continue
        r_obs, r_means = _bootstrap_means(
            control.per_row_recall, r.per_row_recall, seed=seed, resamples=_RESAMPLES
        )
        n_obs, n_means = _bootstrap_means(
            control.per_row_ndcg, r.per_row_ndcg, seed=seed, resamples=_RESAMPLES
        )
        r_lo, r_hi = _quantiles(r_means, 0.05, _RESAMPLES)
        n_lo, n_hi = _quantiles(n_means, 0.05, _RESAMPLES)
        n_lo_adj, _n_hi_adj = _quantiles(n_means, adj, _RESAMPLES)
        out[r.label] = {
            "recall_delta": r_obs,
            "recall_ci": [r_lo, r_hi],
            "ndcg_delta": n_obs,
            "ndcg_ci": [n_lo, n_hi],
            "beats_control": n_lo > 0 or r_lo > 0,
            "beats_control_adjusted": n_lo_adj > 0,
        }
    return out


# ── Execution ────────────────────────────────────────────────────────────────


def _fresh_index(*, contextual: bool) -> None:
    """Force ``kb_search`` to rebuild its index under ``contextual`` fields.

    ``_build_index`` is ``lru_cache(maxsize=1)`` and the fielded/plain choice is
    baked in at build time, so this is the only way to get a genuine sparse
    control in the same process as the fielded grid.
    """
    from app.data import kb_search  # noqa: PLC0415

    os.environ["REGENOLD_CONTEXTUAL_FIELDS"] = "1" if contextual else "0"
    kb_search._build_index.cache_clear()  # noqa: SLF001 — the only invalidation hook
    kb_search._build_index()  # noqa: SLF001 — build eagerly so the config is fixed here


def _retrieve_refs(question: str) -> list[str]:
    """One row through the production fallback entry point (R449 harness parity)."""
    from app.data import kb_search  # noqa: PLC0415

    hits = kb_search.top_articles_by_relevance(
        question, k=_PRODUCTION_K, min_score=_MIN_SCORE
    )
    return [h for h in hits if isinstance(h, str) and h.strip()]


def _collect(
    label: str,
    rows: Sequence[Any],
    *,
    weights: tuple[float, float, float, float],
    fielded: bool,
) -> tuple[CellResult, dict[str, list[str]]]:
    """Retrieve every row once and aggregate the cell's metrics.

    Returns the per-row retrieved sets too, so the caller can account additions
    against the sparse control and churn against the shipped cell without a
    second retrieval pass.
    """
    from evals.retrieval import unit_grain as ug  # noqa: PLC0415

    recalls: list[float] = []
    ndcgs: list[float] = []
    all_heads: list[float] = []
    excess: list[float] = []
    chars: list[float] = []
    refs_by_row: dict[str, list[str]] = {}
    for row in rows:
        refs = _retrieve_refs(row.question)
        refs_by_row[row.row_id] = refs
        gold = set(row.gold_heads)
        recalls.append((len(gold & set(refs)) / len(gold)) if gold else 0.0)
        ndcgs.append(ug.ndcg_at_k(refs, gold))
        all_heads.append(1.0 if gold and gold <= set(refs) else 0.0)
        excess.append(float(max(0, len(refs) - len(gold & set(refs)))))
        chars.append(float(ug._context_chars(refs)))  # noqa: SLF001 — harness parity

    n = len(rows) or 1
    w_t, w_b, b_t, b_b = weights
    return (
        CellResult(
            label=label, w_title=w_t, w_body=w_b, b_title=b_t, b_body=b_b,
            head_recall=sum(recalls) / n, row_all_heads=sum(all_heads) / n,
            ndcg=sum(ndcgs) / n, excess_refs=sum(excess) / n,
            context_chars=sum(chars) / n, added_refs=0, added_gold=0, churn_rows=0,
            per_row_recall=recalls, per_row_ndcg=ndcgs, fielded=fielded,
        ),
        refs_by_row,
    )


def run_cell(cell: Cell, rows: Sequence[Any]) -> tuple[CellResult, dict[str, list[str]]]:
    """Retrieve every row under one weight cell, in the CURRENT process.

    Requires the FIELDED index to be the one built (see :func:`_fresh_index`) —
    the weights are read per score call, so no rebuild is needed between cells,
    which is what makes a whole grid affordable in one process.
    """
    previous = {name: os.environ.get(name) for name in cell.env()}
    for name, value in cell.env().items():
        os.environ[name] = value
    try:
        return _collect(
            cell.label,
            rows,
            weights=(cell.w_title, cell.w_body, cell.b_title, cell.b_body),
            fielded=True,
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run_sparse_cell(rows: Sequence[Any]) -> tuple[CellResult, dict[str, list[str]]]:
    """The un-fielded control: same rows, same entry point, index rebuilt plain."""
    previous = os.environ.get("REGENOLD_CONTEXTUAL_FIELDS")
    _fresh_index(contextual=False)
    try:
        return _collect(SPARSE_LABEL, rows, weights=(0.0, 0.0, 0.0, 0.0), fielded=False)
    finally:
        if previous is None:
            os.environ.pop("REGENOLD_CONTEXTUAL_FIELDS", None)
        else:
            os.environ["REGENOLD_CONTEXTUAL_FIELDS"] = previous


def run_sweep(
    rows: Sequence[Any], cells: Sequence[Cell]
) -> tuple[list[CellResult], CellResult, dict[str, dict[str, list[str]]]]:
    """Sweep the sparse control then every cell, and account additions and churn.

    ``sparse`` is the control the additions are measured against; ``shipped`` is
    the fielded cell with R449's by-argument weights, the cell a promotion would
    replace and the churn reference. The returned result list has ``sparse``
    first, then the grid with ``shipped`` first.
    """
    prev_ctx = os.environ.get("REGENOLD_CONTEXTUAL_FIELDS")
    results: list[CellResult] = []
    refs_per_cell: dict[str, dict[str, list[str]]] = {}
    try:
        sparse_result, sparse_refs = run_sparse_cell(rows)
        _fresh_index(contextual=True)
        for cell in cells:
            result, refs = run_cell(cell, rows)
            refs_per_cell[cell.label] = refs
            results.append(result)
    finally:
        if prev_ctx is None:
            os.environ.pop("REGENOLD_CONTEXTUAL_FIELDS", None)
        else:
            os.environ["REGENOLD_CONTEXTUAL_FIELDS"] = prev_ctx

    ordered = [sparse_result, *results]
    refs_per_cell[sparse_result.label] = sparse_refs
    shipped = next(r for r in ordered if r.label == "shipped")
    shipped_refs = refs_per_cell[shipped.label]
    for result in ordered:
        refs = refs_per_cell[result.label]
        for row in rows:
            base = sparse_refs.get(row.row_id, [])
            gold = set(row.gold_heads)
            new = [r for r in refs.get(row.row_id, []) if r not in base]
            result.added_refs += len(new)
            result.added_gold += sum(1 for r in new if r in gold)
            if set(refs.get(row.row_id, [])) != set(shipped_refs.get(row.row_id, [])):
                result.churn_rows += 1
    return ordered, shipped, refs_per_cell


# ── Reporting ────────────────────────────────────────────────────────────────


def markdown(
    results: Sequence[CellResult],
    baseline: CellResult,
    verdicts: dict[str, dict[str, Any]],
    control: CellResult | None = None,
    control_pairs: dict[str, dict[str, Any]] | None = None,
) -> str:
    n_cmp = max(2, len(results) - 1)
    lines = [
        "| cell | w_title | w_body | b_title | b_body | head recall | all heads | nDCG@k "
        "| excess refs | ctx chars | added | added gold | churn rows | recall Δ [95% CI] "
        f"| nDCG Δ [95% CI] | verdict | gain survives α=0.05/{n_cmp} |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        v = verdicts.get(r.label, {})
        rci = v.get("recall_ci", [0.0, 0.0])
        nci = v.get("ndcg_ci", [0.0, 0.0])
        if r.fielded:
            weights = (
                f"{r.w_title:g} | {r.w_body:g} | {r.b_title:g} | {r.b_body:g}"
            )
        else:
            weights = "- | - | - | -"
        lines.append(
            f"| `{r.label}` | {weights} "
            f"| {r.head_recall:.3f} | {r.row_all_heads:.3f} | {r.ndcg:.3f} "
            f"| {r.excess_refs:.2f} | {r.context_chars:,.0f} | {r.added_refs} "
            f"| {r.added_gold} | {r.churn_rows} "
            f"| {v.get('recall_delta', 0.0):+.4f} [{rci[0]:+.4f}, {rci[1]:+.4f}] "
            f"| {v.get('ndcg_delta', 0.0):+.4f} [{nci[0]:+.4f}, {nci[1]:+.4f}] "
            f"| {v.get('verdict', '')} "
            f"| {'yes' if v.get('survives_multiplicity') else 'no'} |"
        )
    lines += [
        "",
        f"Baseline cell: `{baseline.label}` (w_title {baseline.w_title:g}, "
        f"w_body {baseline.w_body:g}, b_title {baseline.b_title:g}, "
        f"b_body {baseline.b_body:g}). `{SPARSE_LABEL}` is the un-fielded control "
        "(contextual fields OFF, index rebuilt); additions are measured against it. "
        "`churn rows` counts rows whose retrieved SET differs from the shipped cell's. "
        f"The two Δ columns are per-cell CIs at α=0.05; the last column re-reads the "
        f"same bootstrap at the Bonferroni level α=0.05/{n_cmp} = {0.05 / n_cmp:.5f}, "
        f"which is the honest bar for a {n_cmp}-cell sweep and is a DIAGNOSTIC only — "
        "the verdict column is the pre-registered rule, unchanged.",
    ]
    promoted = [
        r.label for r in results
        if verdicts.get(r.label, {}).get("verdict") == "PROMOTE"
    ]
    lines += [
        "",
        (
            "**Promotion candidates:** " + ", ".join(f"`{c}`" for c in promoted)
        )
        if promoted
        else "**Promotion candidates:** none — no cell clears the paired-CI rule.",
    ]

    if control is not None and control_pairs:
        lines += [
            "",
            f"### Fielded cells vs the `{control.label}` control (contextual fields OFF)",
            "",
            "| cell | head recall vs control | nDCG Δ vs control [95% CI] "
            "| beats control | beats control after multiplicity |",
            "|---|---|---|---|---|",
        ]
        for r in results:
            if r.label == control.label:
                continue
            p = control_pairs.get(r.label, {})
            rci = p.get("recall_ci", [0.0, 0.0])
            nci = p.get("ndcg_ci", [0.0, 0.0])
            lines.append(
                f"| `{r.label}` | {p.get('recall_delta', 0.0):+.4f} "
                f"[{rci[0]:+.4f}, {rci[1]:+.4f}] "
                f"| {p.get('ndcg_delta', 0.0):+.4f} [{nci[0]:+.4f}, {nci[1]:+.4f}] "
                f"| {'yes' if p.get('beats_control') else 'no'} "
                f"| {'yes' if p.get('beats_control_adjusted') else 'no'} |"
            )
        lines += [
            "",
            "This block is a REPORTED read, not a second verdict: the pre-registered "
            "rule is scored against `shipped` once, and a friendlier baseline must not "
            "be able to manufacture a PROMOTE.",
        ]
    return "\n".join(lines)


def _payload(
    results: Sequence[CellResult],
    baseline: CellResult,
    verdicts: dict[str, dict[str, Any]],
    grid: Sequence[Cell],
    rows: Sequence[Any],
    control_pairs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "instrument": "evals.retrieval.field_weight_sweep",
        "round": "r451",
        "k": _PRODUCTION_K,
        "min_score": _MIN_SCORE,
        "n_rows": len(rows),
        "offline_env": _OFFLINE_ENV,
        "shipped": SHIPPED,
        "baseline": baseline.label,
        "sparse_label": SPARSE_LABEL,
        "grid_families": {
            "w": list(TITLE_WEIGHTS),
            "bt": list(TITLE_B),
            "bb": list(BODY_B),
            "bw": list(BODY_WEIGHTS),
        },
        "field_weight_bounds": list(_FIELD_WEIGHT_BOUNDS),
        "field_b_bounds": list(_FIELD_B_BOUNDS),
        "cells": [
            {
                **{k: v for k, v in asdict(r).items() if not k.startswith("per_row")},
                "added_precision": r.added_precision,
                "verdict": verdicts.get(r.label, {}),
                # Per-row arrays so any pairing (not just the two reported here)
                # can be re-derived from the artifact rather than re-run.
                "per_row_recall": r.per_row_recall,
                "per_row_ndcg": r.per_row_ndcg,
            }
            for r in results
        ],
        "vs_control": control_pairs or {},
        "grid": [asdict(c) for c in grid],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", default=str(_DEFAULT_GOLD))
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--out", default=None)
    parser.add_argument("--md-out", default=None)
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — older/non-tty streams
        pass

    for name, value in _OFFLINE_ENV.items():
        os.environ[name] = value

    from evals.retrieval import unit_grain as ug  # noqa: PLC0415 — after offline env

    grid = build_grid()
    assert_grid_representable(grid)
    rows = ug.load_gold(Path(args.gold), limit=args.rows)
    if not rows:
        print("no rows", file=sys.stderr)
        return 1
    print(
        f"R451 field-weight sweep — {len(grid)} fielded cells + {SPARSE_LABEL} control "
        f"x {len(rows)} rows, k={_PRODUCTION_K}"
    )
    results, baseline, _refs = run_sweep(rows, grid)
    n_cmp = max(2, len(results) - 1)
    verdicts = {
        r.label: verdict_for(r, baseline, seed=args.seed, n_comparisons=n_cmp)
        for r in results
    }
    control = next((r for r in results if r.label == SPARSE_LABEL), None)
    control_pairs = (
        vs_control([r for r in results if r.label != SPARSE_LABEL], control,
                   seed=args.seed, n_comparisons=n_cmp)
        if control is not None
        else {}
    )
    table = markdown(results, baseline, verdicts, control, control_pairs)
    print(table)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                _payload(results, baseline, verdicts, grid, rows, control_pairs),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        print(f"wrote {out}")
    if args.md_out:
        md = Path(args.md_out)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(table + "\n", encoding="utf-8")
        print(f"wrote {md}")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    sys.exit(main())

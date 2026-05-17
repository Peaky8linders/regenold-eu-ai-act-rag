"""Calibrate per-qtype answer-length caps from davidath gold distribution.

R40 Phase 2a. Loads the davidath QA + scenarios from the local cache,
classifies each question via ``app.engines.sentence_index.classify_question``,
and prints the per-qtype gold-answer character-length percentiles.

The 90th percentile is the recommended cap (preserves recall while
clipping the long-tail outliers that drag conciseness down). Run:

    python -m scripts.calibrate_answer_template

Outputs:
* Inspection table: min / median / p75 / p90 / p95 / max + count per qtype.
* Ready-to-paste ``INTENT_LENGTH_CAP = {...}`` dict literal.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Iterable

from app.engines.answer_template import (
    INTENT_LENGTH_CAP as CURRENT_CAPS,
    _split_sentences,
)
from app.engines.sentence_index import classify_question
from evals.bench.dataset import load_qa_pairs, load_scenarios
from evals.bench.runner import _scenario_to_question


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    # Nearest-rank method on a 0-indexed sorted list.
    k = max(0, min(len(s) - 1, math.ceil(pct / 100.0 * len(s)) - 1))
    return s[k]


def _scenario_gold_answer(row: dict) -> str:
    """Reconstruct the gold-shape answer the bench runner scores against.

    Mirrors ``evals.bench.runner._run_scenarios`` exactly:
    ``"This system is classified as {risk}. " + " ".join(obligations[:3])``
    so the calibrated p90 lines up with what the rubric actually sees.
    """
    risk = (row.get("risk_level") or "").strip()
    obligations = row.get("obligations") or []
    return (
        f"This system is classified as {risk}. " + " ".join(obligations[:3])
    ).strip()


def _iter_gold(
    qa_rows: Iterable[dict], scenario_rows: Iterable[dict]
) -> Iterable[tuple[str, str]]:
    """Yield (question, gold_answer) pairs from both sources.

    Uses the bench runner's real scenario-question synthesiser
    (``_scenario_to_question``) — critical because the synthesised
    "what is the risk classification..." phrasing routes every
    scenario to ``definition`` via the classifier, NOT ``description``.
    Using the wrong question shape biases the calibration toward
    description-class caps that never fire on scenarios in production.
    """
    for r in qa_rows:
        q = (r.get("question") or "").strip()
        a = (r.get("answer") or "").strip()
        if q and a:
            yield q, a
    for r in scenario_rows:
        q = _scenario_to_question(r)
        a = _scenario_gold_answer(r)
        if q and a:
            yield q, a


def calibrate() -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    qa_rows = load_qa_pairs()
    scenario_rows = load_scenarios()
    lens_by_qtype: dict[str, list[int]] = defaultdict(list)
    sents_by_qtype: dict[str, list[int]] = defaultdict(list)
    for question, gold in _iter_gold(qa_rows, scenario_rows):
        qt = classify_question(question)
        lens_by_qtype[qt].append(len(gold))
        sents_by_qtype[qt].append(len(_split_sentences(gold)))
    stats: dict[str, dict[str, int]] = {}
    sent_stats: dict[str, dict[str, int]] = {}
    for qt, lens in lens_by_qtype.items():
        stats[qt] = {
            "count": len(lens),
            "min": min(lens),
            "median": int(statistics.median(lens)),
            "p75": _percentile(lens, 75),
            "p90": _percentile(lens, 90),
            "p95": _percentile(lens, 95),
            "max": max(lens),
        }
        ns = sents_by_qtype[qt]
        sent_stats[qt] = {
            "min": min(ns),
            "median": int(statistics.median(ns)),
            "p75": _percentile(ns, 75),
            "p90": _percentile(ns, 90),
            "max": max(ns),
        }
    return stats, sent_stats


def main() -> None:
    stats, sent_stats = calibrate()
    # Sort qtypes by count desc for readability.
    qtypes_sorted = sorted(stats.keys(), key=lambda k: -stats[k]["count"])
    print("Per-qtype gold-answer length distribution (chars):")
    header = f"{'qtype':<14}{'count':>7}{'min':>7}{'median':>8}{'p75':>7}{'p90':>7}{'p95':>7}{'max':>7}"
    print(header)
    print("-" * len(header))
    for qt in qtypes_sorted:
        s = stats[qt]
        print(
            f"{qt:<14}{s['count']:>7}{s['min']:>7}{s['median']:>8}"
            f"{s['p75']:>7}{s['p90']:>7}{s['p95']:>7}{s['max']:>7}"
        )
    print()
    print("Per-qtype gold-answer sentence-count distribution:")
    sent_header = f"{'qtype':<14}{'min':>7}{'median':>8}{'p75':>7}{'p90':>7}{'max':>7}"
    print(sent_header)
    print("-" * len(sent_header))
    for qt in qtypes_sorted:
        s = sent_stats[qt]
        print(
            f"{qt:<14}{s['min']:>7}{s['median']:>8}{s['p75']:>7}{s['p90']:>7}{s['max']:>7}"
        )
    print()
    # Build calibrated cap dict — p90 per qtype, rounded to nearest 20.
    # +14 char pad for the appended "(Article N)" cite suffix so a gold-
    # length answer plus its cite still fits inside the cap.
    print("Calibrated INTENT_LENGTH_CAP (p90 chars, rounded up to nearest 20):")
    print()
    print("INTENT_LENGTH_CAP: dict[str, int] = {")
    all_keys = sorted(set(CURRENT_CAPS) | set(stats))
    for k in all_keys:
        if k in stats:
            p90 = stats[k]["p90"]
            cap = int(math.ceil((p90 + 14) / 20.0) * 20)
        else:
            cap = CURRENT_CAPS[k]
        print(f'    "{k}": {cap},')
    print("}")
    print()
    print("Calibrated _budget_sentences (p90 of gold sentence count):")
    print()
    print("table = {")
    for k in all_keys:
        if k in sent_stats:
            sent_p90 = sent_stats[k]["p90"]
            budget = max(1, sent_p90)
        else:
            budget = None
        print(f'    "{k}": {budget},')
    print("}")


if __name__ == "__main__":
    main()

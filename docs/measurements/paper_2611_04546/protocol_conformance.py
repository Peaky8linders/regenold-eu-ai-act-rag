"""Synthetic protocol audit; no benchmark questions, LLM calls, or service changes.

Run from the repository root:
    python docs/measurements/paper_2611_04546/protocol_conformance.py \
        --benchmark-source tmp/paper-protocol-2611.04546 \
        --out docs/measurements/paper_2611_04546/protocol_conformance.json

The released scorer is loaded verbatim from a pinned, separately cloned source.
Results demonstrate differences in instruments, not system performance gains.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLIC_COMMIT = "033e98fdfb6befc0be442c2d26f9851882d9cd80"
sys.path.insert(0, str(ROOT))

from evals.official import rubric  # noqa: E402
from evals.official.paired_ab import _row_axis  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = args.benchmark_source.resolve()
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != PUBLIC_COMMIT:
        raise ValueError(f"Expected released source {PUBLIC_COMMIT}, got {commit}")
    public_refs = load_module("_paper_refs", source / "src/ref_scoring.py")
    load_module("latency_scoring", source / "src/latency_scoring.py")
    public_summary = load_module("_paper_summary", source / "src/summarize_results.py")

    ref_cases = [
        ("first_sublevel_not_full_grain", ["Article 13.3.c"], ["Article 13.3.b"]),
        ("wrong_reference_same_count", ["Article 7.1"], ["Article 6.1"]),
        ("parent_is_exempt_extra", ["Annex IV", "Annex IV.1"], ["Annex IV.1"]),
        ("missing_gold_and_unrelated_extra", ["Article 6.2", "Article 7"], ["Article 6.2", "Article 8"]),
        ("unannotated_references", ["Article 6"], []),
    ]
    refs = []
    for name, found, expected in ref_cases:
        released = public_refs.compute_ref_scores(found, expected)
        extra = released["strict_extra_pct"]
        refs.append({
            "case": name, "found": found, "expected": expected,
            "local_strict_recall": rubric.reference_correctness_strict(found, expected),
            "public_strict_recall": released["strict_found_pct"],
            "local_reference_conciseness": rubric.reference_conciseness(found, expected),
            "public_reference_conciseness": None if extra is None else 1 / (1 + extra),
        })

    # Deliberately artificial tokens isolate word length from character length.
    ref_text = "a b c d"
    answers = {"A": "international international", "B": "a b c d e f"}
    length_case = {
        "reference": ref_text,
        "arms": {
            name: {
                "text": answer,
                "local_chars": rubric.answer_conciseness(answer, ref_text),
                "published_words": min(1.0, len(ref_text.split()) / len(answer.split())),
            }
            for name, answer in answers.items()
        },
    }
    assert length_case["arms"]["B"]["local_chars"] > length_case["arms"]["A"]["local_chars"]
    assert length_case["arms"]["A"]["published_words"] > length_case["arms"]["B"]["published_words"]

    # Equal questions, unequal numbers of correctness criteria.
    criteria_a = [[False], [True] * 5]
    criteria_b = [[True], [True] * 3 + [False] * 2]
    paired_macro_delta = sum(
        _row_axis({"criteria": b}, "ans_correctness_loose")
        - _row_axis({"criteria": a}, "ans_correctness_loose")
        for a, b in zip(criteria_a, criteria_b, strict=True)
    ) / 2
    pooled_micro_delta = 100 * (
        rubric.answer_correctness_loose(criteria_b)
        - rubric.answer_correctness_loose(criteria_a)
    )
    assert paired_macro_delta > 0 > pooled_micro_delta

    def entry(passed: bool, repeats: int) -> dict:
        return {
            "judgements_correctness": [
                {"criteria": [{"passed": passed}]} for _ in range(repeats)
            ],
            "judgements_tone": [
                {"appropriateness_passed": True, "clarity_passed": True}
                for _ in range(repeats)
            ],
            "answer_conciseness_score": 1.0,
            "loose_found_pct": 1.0,
            "strict_found_pct": 1.0,
            "strict_extra_pct": 0.0,
            "latency_seconds": 1.0,
        }

    complete = public_summary.summarize([entry(True, 3), entry(False, 3)])
    incomplete = public_summary.summarize([entry(True, 3), entry(False, 1)])
    strict_label = "Answer correctness (strict)"
    complete_score = complete["metrics"][strict_label]["mean"]
    incomplete_score = incomplete["metrics"][strict_label]["mean"]
    assert complete_score == 50.0 and incomplete_score > 83.3

    power_examples = []
    for discordant in (30, 60, 90, 100, 120):
        power = 0.0
        for wins in range(discordant + 1):
            tail = sum(
                math.comb(discordant, i) * 0.5 ** discordant
                for i in range(min(wins, discordant - wins) + 1)
            )
            if min(1.0, 2 * tail) <= 0.05:
                power += (
                    math.comb(discordant, wins)
                    * 0.65 ** wins * 0.35 ** (discordant - wins)
                )
        power_examples.append({
            "discordant_pairs": discordant,
            "power_at_conditional_win_probability_0_65": power,
        })

    files = {
        "public_ref_scoring": source / "src/ref_scoring.py",
        "public_summary": source / "src/summarize_results.py",
        "local_rubric": ROOT / "evals/official/rubric.py",
        "local_paired_ab": ROOT / "evals/official/paired_ab.py",
    }
    result = {
        "kind": "synthetic_instrument_diagnostics_not_performance_evaluation",
        "public_commit": commit,
        "local_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "file_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
        "reference_cases": refs,
        "answer_conciseness_ranking_reversal": length_case,
        "loose_correctness_ranking_reversal": {
            "criteria_a": criteria_a, "criteria_b": criteria_b,
            "paired_ab_macro_delta_pp": paired_macro_delta,
            "published_micro_delta_pp": pooled_micro_delta,
        },
        "public_incomplete_repeat_coverage": {
            "synthetic_rows": 2,
            "complete_3_repeats_each_strict_pct": complete_score,
            "same_failure_with_only_1_repeat_strict_pct": incomplete_score,
            "interpretation": "Summary input-integrity defect; no evidence published runs were incomplete.",
        },
        "exact_two_sided_sign_test_power_examples": {
            "alpha": 0.05,
            "assumptions": "Independent discordant pairs; conditional branch-win probability 0.65; fixed pair count.",
            "examples": power_examples,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

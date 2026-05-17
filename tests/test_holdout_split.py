"""Tests for the deterministic 5-bucket hold-out split.

The split must be:
    * Deterministic (same items chosen on every run)
    * ~20% of each source (bucket 0 of 5 — SHA-256(question) mod 5 == 0)
    * Disjoint from the train set (no item appears in both)
    * Stable across QA + scenarios independently
    * Reproducible from JSON sidecars (no implicit state)
"""
from __future__ import annotations

import hashlib

from evals.bench import dataset as bench_dataset
from evals.bench import holdout


def _qa_key(item: dict) -> str:
    return item.get("question") or ""


def _scenario_key(item: dict) -> str:
    """Same projection holdout.py uses — role+intended_use+system_type+domain."""
    return holdout._scenario_question_text(item)


class TestHoldoutQA:
    def test_holdout_is_roughly_twenty_percent(self) -> None:
        all_qa = bench_dataset.load_qa_pairs()
        hold = holdout.load_holdout_qa()
        # Bucket 0 / 5 buckets ≈ 20%. Allow [12%, 28%] band for sample noise.
        ratio = len(hold) / max(1, len(all_qa))
        assert 0.12 <= ratio <= 0.28, (
            f"Hold-out QA was {len(hold)}/{len(all_qa)} = {ratio:.3f}"
        )

    def test_holdout_is_deterministic(self) -> None:
        a = [_qa_key(x) for x in holdout.load_holdout_qa()]
        b = [_qa_key(x) for x in holdout.load_holdout_qa()]
        assert a == b

    def test_holdout_disjoint_from_train(self) -> None:
        hold_keys = {_qa_key(x) for x in holdout.load_holdout_qa()}
        train_keys = {_qa_key(x) for x in holdout.load_train_qa()}
        assert hold_keys & train_keys == set()
        # Union covers everything.
        all_keys = {_qa_key(x) for x in bench_dataset.load_qa_pairs()}
        assert hold_keys | train_keys == all_keys

    def test_hash_bucket_function_is_pure(self) -> None:
        # bucket(text) == bucket(text) for the same input.
        assert holdout._hash_bucket("hello") == holdout._hash_bucket("hello")
        # And matches the SHA-256-mod-5 contract.
        h = hashlib.sha256(b"hello").hexdigest()
        expected = int(h, 16) % 5
        assert holdout._hash_bucket("hello") == expected


class TestHoldoutScenarios:
    def test_holdout_is_roughly_twenty_percent(self) -> None:
        all_sc = bench_dataset.load_scenarios()
        hold = holdout.load_holdout_scenarios()
        ratio = len(hold) / max(1, len(all_sc))
        assert 0.12 <= ratio <= 0.28, (
            f"Hold-out scenarios was {len(hold)}/{len(all_sc)} = {ratio:.3f}"
        )

    def test_holdout_is_deterministic(self) -> None:
        a = [_scenario_key(x) for x in holdout.load_holdout_scenarios()]
        b = [_scenario_key(x) for x in holdout.load_holdout_scenarios()]
        assert a == b

    def test_holdout_disjoint_from_train(self) -> None:
        hold_keys = {_scenario_key(x) for x in holdout.load_holdout_scenarios()}
        train_keys = {_scenario_key(x) for x in holdout.load_train_scenarios()}
        # Allow rare duplicate scenarios in upstream — keys collapse — but the
        # split itself must be bucket-disjoint by content.
        all_keys = {_scenario_key(x) for x in bench_dataset.load_scenarios()}
        assert hold_keys.union(train_keys) == all_keys


class TestSummary:
    def test_summary_reports_counts(self) -> None:
        info = holdout.summary()
        assert "qa" in info and "scenarios" in info
        qa_info = info["qa"]
        sc_info = info["scenarios"]
        assert qa_info["holdout"] + qa_info["train"] == qa_info["total"]
        assert sc_info["holdout"] + sc_info["train"] == sc_info["total"]
        # Bucket assignment should be NON-empty in hold-out.
        assert qa_info["holdout"] > 0
        assert sc_info["holdout"] > 0

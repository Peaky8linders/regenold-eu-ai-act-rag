"""Tests for the Regenold rules-PDF probe set.

The probe set is the three example questions from the 2026 EU AI Act
competition rules PDF + ~20 paraphrases (6-7 per example). It probes
the exact questions the competition judges will use as scoring
anchors — over-fitting to these would be a clear sign of cheating but
also of poor generalisation, so the harness measures the bundle's
behaviour against the canonical examples AND multiple plausible
re-phrasings.

Covers:
    * The 3 canonical questions are present
    * Each canonical has at least 6 paraphrases
    * Each paraphrase shares the canonical's gold_articles + verdict
    * The scorer returns per-question Ref Strict + Ans Overlap floats
    * Empty agent → 0-scores cleanly
    * Oracle agent → perfect on the canonical anchors
    * Family-level aggregation rolls up paraphrases per canonical
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from evals.bench import regenold_probe


def _oracle_agent(item: dict[str, Any]) -> dict[str, Any]:
    """Returns the gold answer & refs for every item."""
    return {
        "answer": item.get("gold_answer_text") or "",
        "references": list(item.get("gold_articles") or []),
    }


def _empty_agent(item: dict[str, Any]) -> dict[str, Any]:
    return {"answer": "", "references": []}


class TestProbeLoader:
    def test_three_canonical_questions(self) -> None:
        items = regenold_probe.load_regenold_probe()
        canonical = [x for x in items if x["is_canonical"]]
        assert len(canonical) == 3
        # The 3 question_ids are stable.
        ids = sorted(x["question_id"] for x in canonical)
        assert ids == ["doctor_transcription", "emotion_recognition", "technical_doc"]

    def test_each_canonical_has_paraphrases(self) -> None:
        items = regenold_probe.load_regenold_probe()
        for qid in ("technical_doc", "emotion_recognition", "doctor_transcription"):
            paraphrases = [
                x for x in items if x["question_id"] == qid and not x["is_canonical"]
            ]
            assert len(paraphrases) >= 6, (
                f"{qid} has only {len(paraphrases)} paraphrases (need ≥6)"
            )

    def test_paraphrases_inherit_gold(self) -> None:
        items = regenold_probe.load_regenold_probe()
        by_id: dict[str, dict] = {
            x["question_id"]: x for x in items if x["is_canonical"]
        }
        for x in items:
            if x["is_canonical"]:
                continue
            canon = by_id[x["question_id"]]
            assert x["gold_articles"] == canon["gold_articles"]
            assert x["expected_verdict"] == canon["expected_verdict"]

    def test_total_at_least_twenty_three(self) -> None:
        # 3 canonical + 20+ paraphrases.
        items = regenold_probe.load_regenold_probe()
        assert len(items) >= 23


class TestScoreRegenoldProbe:
    def test_oracle_agent_scores_perfect(self) -> None:
        items = regenold_probe.load_regenold_probe()
        result = regenold_probe.score_regenold_probe(items, _oracle_agent)
        # Per-question Ref Strict + Ans Overlap should all be 1.0 on
        # the oracle agent.
        for q in result["per_question"].values():
            assert q["ref_strict"] == pytest.approx(1.0), q
            assert q["ans_overlap"] == pytest.approx(1.0), q

    def test_empty_agent_scores_zero(self) -> None:
        items = regenold_probe.load_regenold_probe()
        result = regenold_probe.score_regenold_probe(items, _empty_agent)
        for q in result["per_question"].values():
            assert q["ref_strict"] == 0.0
            assert q["ans_overlap"] == 0.0

    def test_family_aggregation_present(self) -> None:
        items = regenold_probe.load_regenold_probe()
        result = regenold_probe.score_regenold_probe(items, _oracle_agent)
        assert "per_question" in result
        assert "summary" in result
        # Three question families.
        assert {"technical_doc", "emotion_recognition", "doctor_transcription"} \
            <= set(result["per_question"].keys())

    def test_result_json_serialisable(self) -> None:
        items = regenold_probe.load_regenold_probe()
        result = regenold_probe.score_regenold_probe(items, _oracle_agent)
        json.dumps(result)  # raises if not serialisable

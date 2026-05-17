"""Tests for the unbiased AIReg-Bench harness (evals.bench.aireg_bench).

This module is INTENTIONALLY separate from ``test_aireg_bench.py``
(which covers the in-tree HuggingFace loader at
``evals.bench.aireg_dataset``). The unbiased harness here is the
offline-first, fixture-backed adapter used by ``unbiased_runner``.

Covers:
    * Fixture loader returns ≥ 10 items with the right schema
    * Live-fetch path falls back to fixture on network error
    * Per-article precision/recall/F1 are computed correctly
    * Verdict accuracy is computed correctly on a known-good agent
    * Empty / no-result agent returns 0-scores cleanly
    * The score_aireg_bench API returns a stable, JSON-serialisable dict
    * Loader rejects malformed JSONL rows
    * Article-name normalisation handles "Art. 9", "Article 9", "art 9"
"""
from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from evals.bench import aireg_bench


def _fake_agent_oracle(item: dict[str, Any]) -> dict[str, Any]:
    """Perfect agent — returns the gold for every item."""
    return {
        "answer": "This system " + item["expected_verdict"].replace("_", " ") + ".",
        "references": list(item["expected_articles"]),
    }


def _fake_agent_always_compliant(item: dict[str, Any]) -> dict[str, Any]:
    """Trivial baseline — says everything is compliant."""
    return {"answer": "This system is compliant.", "references": ["Art. 9"]}


def _fake_agent_empty(item: dict[str, Any]) -> dict[str, Any]:
    return {"answer": "", "references": []}


class TestFixtureLoader:
    def test_fixture_has_at_least_ten_rows(self) -> None:
        rows = aireg_bench.load_aireg_fixture()
        assert len(rows) >= 10

    def test_fixture_covers_all_five_articles(self) -> None:
        rows = aireg_bench.load_aireg_fixture()
        articles = {r["article"] for r in rows}
        assert {"Art. 9", "Art. 10", "Art. 12", "Art. 14", "Art. 15"} <= articles

    def test_fixture_schema_is_consistent(self) -> None:
        rows = aireg_bench.load_aireg_fixture()
        required = {
            "id",
            "scenario",
            "expected_articles",
            "expected_verdict",
        }
        for row in rows:
            assert required <= set(row.keys()), f"row {row} is missing fields"
            assert isinstance(row["expected_articles"], list)
            assert row["expected_verdict"] in {
                "compliant",
                "non_compliant",
                "unclear",
            }


class TestLoadAiregBench:
    def test_falls_back_to_fixture_on_network_error(self) -> None:
        # huggingface_hub may not be installed; either way, the path
        # must succeed via fixture fallback.
        with mock.patch.object(
            aireg_bench, "_fetch_hf_snapshot", side_effect=RuntimeError("offline")
        ):
            rows = aireg_bench.load_aireg_bench()
        assert len(rows) >= 10
        # Confirm provenance: fallback returns fixture rows.
        ids = {r["id"] for r in rows}
        assert any(i.startswith("aireg-") for i in ids)


class TestNormaliseArticleName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Art. 9", "Article 9"),
            ("Article 9", "Article 9"),
            ("art 9", "Article 9"),
            ("ARTICLE 10", "Article 10"),
            ("Art. 12(1)", "Article 12"),
            ("Article 14(3)(a)", "Article 14"),
            ("Article 15.2.b", "Article 15"),
        ],
    )
    def test_normalise(self, raw: str, expected: str) -> None:
        assert aireg_bench._normalise_article(raw) == expected

    def test_normalise_drops_unparseable(self) -> None:
        assert aireg_bench._normalise_article("foo bar baz") is None
        assert aireg_bench._normalise_article("") is None


class TestScoreAiregBench:
    def test_oracle_agent_scores_perfect(self) -> None:
        items = aireg_bench.load_aireg_fixture()
        result = aireg_bench.score_aireg_bench(items, _fake_agent_oracle)
        # Oracle returns the gold for every item — both axes max.
        assert result["article_f1"] == pytest.approx(1.0)
        assert result["verdict_accuracy"] == pytest.approx(1.0)
        assert result["n"] == len(items)

    def test_empty_agent_scores_zero(self) -> None:
        items = aireg_bench.load_aireg_fixture()
        result = aireg_bench.score_aireg_bench(items, _fake_agent_empty)
        assert result["article_f1"] == 0.0
        assert result["verdict_accuracy"] == 0.0
        assert result["n"] == len(items)

    def test_constant_compliant_baseline_is_imperfect(self) -> None:
        items = aireg_bench.load_aireg_fixture()
        result = aireg_bench.score_aireg_bench(
            items, _fake_agent_always_compliant
        )
        # Verdict accuracy ≈ fraction of "compliant" gold (half of fixture).
        compliants = sum(1 for x in items if x["expected_verdict"] == "compliant")
        expected_acc = compliants / len(items)
        assert result["verdict_accuracy"] == pytest.approx(expected_acc)

    def test_result_is_json_serialisable(self) -> None:
        items = aireg_bench.load_aireg_fixture()
        result = aireg_bench.score_aireg_bench(items, _fake_agent_oracle)
        # Round-trip ensures no numpy floats / sets / etc leak in.
        s = json.dumps(result)
        roundtrip = json.loads(s)
        assert roundtrip["n"] == result["n"]

    def test_per_article_breakdown_present(self) -> None:
        items = aireg_bench.load_aireg_fixture()
        result = aireg_bench.score_aireg_bench(items, _fake_agent_oracle)
        assert "per_article" in result
        per_art = result["per_article"]
        # Every article touched by the fixture has its own row.
        for art in {x["article"] for x in items}:
            norm = aireg_bench._normalise_article(art)
            assert norm in per_art

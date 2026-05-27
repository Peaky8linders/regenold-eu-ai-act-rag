"""Regression tests for RushDB seeder label mapping."""
from __future__ import annotations

from scripts.seed_rushdb_kb import RUSHDB_LABEL_MAP, rushdb_label_for_bucket


class TestRushdbLabelMap:
    def test_article_maps_to_pascal_case(self):
        assert rushdb_label_for_bucket("ARTICLE") == "Article"

    def test_annex_maps_to_pascal_case(self):
        assert rushdb_label_for_bucket("ANNEX") == "Annex"

    def test_kb_metadata_unchanged(self):
        assert rushdb_label_for_bucket("KB_METADATA") == "KB_METADATA"

    def test_all_buckets_have_client_compatible_labels(self):
        expected = {
            "ARTICLE",
            "ANNEX",
            "RECITAL",
            "DEFINITION",
            "OBLIGATION",
            "ANNEX_III_CATEGORY",
            "RISK_LEVEL",
            "OPERATOR_ROLE",
            "KB_METADATA",
        }
        assert set(RUSHDB_LABEL_MAP.keys()) == expected
        assert RUSHDB_LABEL_MAP["ARTICLE"] == "Article"
        assert RUSHDB_LABEL_MAP["ANNEX"] == "Annex"
        assert RUSHDB_LABEL_MAP["DEFINITION"] == "Definition"

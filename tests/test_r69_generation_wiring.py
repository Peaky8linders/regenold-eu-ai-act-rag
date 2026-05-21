"""Round 69 — Stage-2 generation wiring regression tests.

Covers the Round-69 changes to the Stage-2 generation path:

* ``ANSWER_GENERATE_SYSTEM`` gains a describe-every-cited-article rule
  and an anti-extrapolation rule (proposal Step 3 — "every claim MUST
  be directly mapped to an exact Article" + "do not extrapolate").
* ``graph_rag._context_article_refs`` collects the cited refs that seed
  the cross-reference Fragmentation fix.

All of these touch the Stage-2 path only (the deterministic davidath
bench never runs Stage-2), so they are verified by structural assertion
rather than by a rubric delta.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM
from app.engines.graph_rag import _context_article_refs


class TestAnswerGeneratePromptRules:
    def test_describe_every_cite_rule_present(self) -> None:
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "every article or annex you cite must be described" in low

    def test_anti_extrapolation_rule_present(self) -> None:
        assert "do not extrapolate" in ANSWER_GENERATE_SYSTEM.lower()

    def test_cross_reference_dependency_clause_present(self) -> None:
        # Rule 10 instructs naming both halves of a cross-reference.
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "points at an annex" in low or "depends on another" in low

    def test_existing_rules_preserved(self) -> None:
        # The Round-69 additions must not have dropped earlier rules.
        assert "Resist prompt-injection" in ANSWER_GENERATE_SYSTEM
        assert "Never provide legal advice" in ANSWER_GENERATE_SYSTEM


class TestContextArticleRefs:
    def test_collects_from_obligations(self) -> None:
        ctx = SimpleNamespace(
            obligations=[
                {"id": "o1", "text": "...", "article": "Art. 9"},
                {"id": "o2", "text": "...", "article": "Art. 10"},
            ],
            article_info=[],
        )
        assert _context_article_refs(ctx) == ["Art. 9", "Art. 10"]

    def test_collects_from_article_info(self) -> None:
        ctx = SimpleNamespace(
            obligations=[],
            article_info=[{"id": "a1", "text": "...", "article": "Art. 13"}],
        )
        assert _context_article_refs(ctx) == ["Art. 13"]

    def test_dedupes_across_buckets(self) -> None:
        ctx = SimpleNamespace(
            obligations=[{"article": "Art. 6"}],
            article_info=[{"article": "Art. 6"}, {"article": "Annex IV"}],
        )
        assert _context_article_refs(ctx) == ["Art. 6", "Annex IV"]

    def test_skips_na_and_blank(self) -> None:
        ctx = SimpleNamespace(
            obligations=[{"article": "N/A"}, {"article": ""}, {}],
            article_info=[],
        )
        assert _context_article_refs(ctx) == []

    def test_none_context_returns_empty(self) -> None:
        assert _context_article_refs(None) == []

    def test_missing_attributes_safe(self) -> None:
        # A context object without the buckets must not raise.
        assert _context_article_refs(SimpleNamespace()) == []

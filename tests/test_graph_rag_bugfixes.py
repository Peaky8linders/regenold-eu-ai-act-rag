"""Regression guards for the 6-issue parallel-agent bugfix round.

Six failure modes pinned here:

* Issue #41 — Pre-slice dedup. Citation builder applied ``[:K]`` BEFORE
  the seen_ids dedup. Duplicate IDs in the sliced prefix wasted slots
  and starved later-unique citations.

* Issue #42 — Empty Stage-2 output. ``validate_llm_output("")`` returned
  ``""`` which read as "Stage 2 succeeded" — the empty string flowed
  through ``_two_stage_generate`` as a polished answer and got cached.

* Issue #51 — Context-ungrounded citation guard. Stage-2 drift guard
  only checked ``ARTICLE_EXISTENCE`` (the global catalog) — a real
  but request-irrelevant article (e.g. Art. 99 cited when only Art. 6
  was in the context) slipped through.

* Issue #52 — Drift regex. ``_PROSE_ARTICLE_RE`` rejected ``Articles``
  plural and didn't int-normalise the captured digit (``Art. 013``
  failed catalog lookup against ``Art. 13``); ``_PROSE_ANNEX_RE`` only
  matched ``[IVXLC]`` (missing D, M).

* Issue #54 — Fixed BM25 cutoff. Short queries (1-2 tokens) couldn't
  reach the absolute 2.5 min_score and returned zero hits even when
  the top candidate was a clear winner.

* Issue #55 — Silent graph fallback. ``_retrieve_from_graph`` caught
  every exception and returned a partial context with no degradation
  signal. ``_compute_confidence`` couldn't tell "no hits" from
  "backend exploded".
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engines.graph_rag import (
    GraphContext,
    GraphQuery,
    _claude_max_enhance_answer,
    _compute_confidence,
    _polished_prose_has_unknown_citations,
    _retrieve_from_graph,
    _two_stage_generate,
    ask_compliance_question,
)
from app.models import GraphRAGRequest


@pytest.fixture(autouse=True)
def _disable_r87e_stage2_gate(monkeypatch):
    """R87-E confidence gate would skip Stage-2 on the empty mock
    contexts these tests construct. Pre-R87-E tests; disable the gate
    so the original Stage-2-behaviour assertions still hold. R87-E has
    its own coverage in ``test_r87cde_subpoint_roleduty_stage2gate.py``."""
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")


# A multi-turn question that reliably triggers Stage-2.
_MULTI_TURN_Q = (
    "Conversation so far:\nUser: foo\nAssistant: bar\n\n"
    "Latest question:\nWhat are the specific obligations?"
)


# ─── Issue #41 — Pre-slice dedup ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _r77_enable_stage2_polish(monkeypatch: pytest.MonkeyPatch) -> None:
    """R77 — Stage-2 polish now defaults OFF (``P2P_GRAPH_RAG_ENABLE_STAGE2``).

    These tests predate that default and exercise the Stage-2 path with a
    mocked provider. Force the master switch ON so they keep testing
    Stage-2 behaviour; the provider + needs-enhancement gates still apply,
    so the "Stage-2 skipped" tests in this module still skip correctly.
    """
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")


class TestPreSliceDedup:
    """The citation builder must dedupe BEFORE applying the [:K] slice."""

    def test_obligations_dedup_before_slice_preserves_unique_ids(self) -> None:
        """Build a request where the engine path produces obligations with
        duplicate IDs in the first 15 positions and unique IDs after; after
        the fix, the unique tail-IDs must surface in the citation list.

        Easiest TDD: monkey-patch ``_retrieve_from_graph`` (the function
        the route calls) to return a context with 20 obligations whose
        first 15 contain 5 duplicate IDs and the last 5 are unique."""
        rigged = GraphContext()
        # 5 unique IDs repeated 3× each = 15 docs, then 5 fresh IDs.
        rigged.obligations = [
            {"id": f"dup-{i % 5}", "text": f"dup row {i}", "article": "Art. 13"}
            for i in range(15)
        ] + [
            {"id": f"unique-tail-{i}", "text": f"tail {i}", "article": "Art. 13"}
            for i in range(5)
        ]
        rigged.nodes_traversed = 20

        # GraphRAGRequest.question must be non-empty.
        with patch(
            "app.engines.graph_rag._retrieve_from_graph",
            return_value=rigged,
        ):
            req = GraphRAGRequest(question="What does Art. 13 require?")
            result = ask_compliance_question(req)

        node_ids = {c.node_id for c in result.citations}
        # Pre-fix: only the 5 duplicates' IDs would surface (max 5 citations).
        # Post-fix: 5 dup-* + 5 unique-tail-* = 10 unique citations.
        assert "unique-tail-0" in node_ids, (
            f"Tail unique IDs starved by pre-slice dedup. Got: {node_ids}"
        )
        assert len(node_ids) >= 10, (
            f"Expected >=10 unique citations; got {len(node_ids)}: {node_ids}"
        )

    def test_gaps_dedup_before_slice_preserves_unique_ids(self) -> None:
        """Same as above but for the gaps slot (which uses [:10])."""
        rigged = GraphContext()
        # No obligations — keep this isolated to gaps.
        rigged.gaps = [
            {"id": f"dup-{i % 3}", "text": f"gap dup {i}", "article": "Art. 9"}
            for i in range(10)
        ] + [
            {"id": f"unique-gap-{i}", "text": f"unique gap {i}", "article": "Art. 9"}
            for i in range(5)
        ]
        rigged.nodes_traversed = 15

        with patch(
            "app.engines.graph_rag._retrieve_from_graph",
            return_value=rigged,
        ):
            req = GraphRAGRequest(question="What does Art. 9 require?")
            result = ask_compliance_question(req)

        node_ids = {c.node_id for c in result.citations}
        assert "unique-gap-0" in node_ids, (
            f"Tail unique gap IDs starved by pre-slice dedup. Got: {node_ids}"
        )
        # 3 dup + 5 unique = 8 minimum
        assert len(node_ids) >= 8, (
            f"Expected >=8 unique citations; got {len(node_ids)}: {node_ids}"
        )


# ─── Issue #42 — Empty Stage-2 output ────────────────────────────────────────


class TestEmptyStage2Output:
    """An empty / whitespace-only Stage-2 polish must be treated as a
    failure (return None) and the stage2_call_failed flag set."""

    @pytest.mark.parametrize("empty_text", ["", "   ", "\n  \n", "\t  \t"])
    def test_empty_text_treated_as_failure(self, empty_text: str) -> None:
        """``_claude_max_enhance_answer`` returns None when the wrapper
        produces empty or whitespace-only output."""
        with patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            return_value=empty_text,
        ):
            result = _claude_max_enhance_answer(
                question="Q",
                kg_answer="KG answer.",
            )
        assert result is None, (
            f"Empty wrapper output {empty_text!r} should return None; got {result!r}"
        )

    def test_two_stage_generate_marks_failure_on_empty_stage2(self) -> None:
        """``_two_stage_generate`` returns ``(kg_answer, False)`` AND sets
        ``context.stage2_call_failed = True`` when Stage-2 returned ''."""
        ctx = GraphContext()
        with (
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="",
            ),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, ctx)
        assert used is False, "Empty Stage-2 polish must not be reported as used"
        assert answer, "kg_answer must still be returned"
        assert ctx.stage2_call_failed is True, (
            "stage2_call_failed must be set so the route doesn't cache "
            "the fallback under the empty-string failure mode"
        )

    def test_route_marks_stage2_call_failed_on_empty_polish(self) -> None:
        """End-to-end: empty wrapper output must surface as
        graph_stats['stage2_call_failed'] = True for the route's cache guard."""
        with (
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="",
            ),
        ):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)
        assert result.graph_stats.get("stage2_call_failed") is True

    def test_validate_llm_output_handles_none_input(self) -> None:
        """Defensive null-guard: prompt_guard.validate_llm_output(None)
        must not crash and must return a sensible empty string."""
        from app.security.prompt_guard import validate_llm_output

        # Should not raise on None.
        result = validate_llm_output(None)  # type: ignore[arg-type]
        assert result == ""


# ─── Issue #51 — Context-ungrounded citation guard ───────────────────────────


class TestContextUngroundedDriftGuard:
    """Stage-2 drift guard must also check that cited articles are in the
    request-specific GraphContext, not just the global catalog."""

    def test_context_grounded_cite_passes(self) -> None:
        """Art. 6 cited and Art. 6 IS in the context — must pass."""
        ctx = GraphContext()
        ctx.obligations = [
            {"id": "o1", "text": "Risk classification.", "article": "Art. 6"},
        ]
        drifted, _ = _polished_prose_has_unknown_citations(
            "Art. 6 establishes high-risk classification.",
            context=ctx,
        )
        assert drifted is False

    def test_real_but_ungrounded_cite_flagged(self) -> None:
        """Art. 99 is in the catalog but NOT in the request context — drift."""
        ctx = GraphContext()
        ctx.obligations = [
            {"id": "o1", "text": "Risk classification.", "article": "Art. 6"},
        ]
        drifted, bad = _polished_prose_has_unknown_citations(
            "Art. 99 penalties apply.",
            context=ctx,
        )
        assert drifted is True, (
            "Art. 99 is real but ungrounded in the request context; "
            "must flag as drift to prevent semantic context leakage"
        )
        assert bad == "Art. 99"

    def test_no_context_param_falls_back_to_catalog_check(self) -> None:
        """Backward compatibility: caller without ``context`` keyword
        still uses the catalog-only check (Round-15 behaviour)."""
        # Art. 13 is in catalog — passes.
        drifted, _ = _polished_prose_has_unknown_citations("Art. 13 says X.")
        assert drifted is False
        # Art. 999 not in catalog — flagged.
        drifted, bad = _polished_prose_has_unknown_citations("Art. 999 says Y.")
        assert drifted is True
        assert bad == "Art. 999"

    def test_two_stage_generate_drops_polish_on_ungrounded_real_cite(self) -> None:
        """End-to-end: Stage-2 polishes prose citing Art. 99 when context
        only has Art. 6 — _two_stage_generate must fall back to kg answer."""
        ctx = GraphContext()
        ctx.obligations = [
            {"id": "o1", "text": "Risk classification.", "article": "Art. 6"},
        ]
        ctx.nodes_traversed = 1

        with (
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Art. 99 governs this case.",
            ),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, ctx)
        assert used is False, "Real-but-ungrounded cite must drop the polish"
        assert "Art. 99" not in answer


# ─── Issue #52 — Drift regex variants ────────────────────────────────────────


class TestDriftRegexWidened:
    """The post-Stage-2 drift regex must catch ``Articles`` plural,
    int-normalise leading-zero captures, and accept D / M Roman numerals."""

    def test_articles_plural_detected(self) -> None:
        """``Articles 200 and 250 apply`` — both bogus, must flag drift.
        Pre-fix the ``Articles`` plural didn't match the regex at all, so
        the bogus refs silently passed."""
        drifted, bad = _polished_prose_has_unknown_citations(
            "Articles 200 and 250 apply here."
        )
        assert drifted is True
        # First-detection — either Art. 200 or Art. 250 acceptable.
        assert bad in {"Art. 200", "Art. 250"}

    def test_articles_plural_real_passes(self) -> None:
        """``Articles 9 and 10`` — both real, must NOT flag."""
        drifted, _ = _polished_prose_has_unknown_citations(
            "Articles 9 and 10 apply here."
        )
        assert drifted is False

    def test_leading_zero_normalised(self) -> None:
        """``Art. 013`` is just ``Art. 13`` with leading zero — must NOT flag."""
        drifted, _ = _polished_prose_has_unknown_citations("Art. 013 applies.")
        assert drifted is False, (
            "Art. 013 should normalise to Art. 13 (real) before catalog check"
        )

    def test_annex_with_M_roman_accepted(self) -> None:
        """The regex must accept M in the Roman set even though no annex
        is numbered with M today — future-proof + harmless."""
        # Annex M doesn't exist in the catalog → drift expected, but the
        # important contract is that the regex MATCHES (i.e. the check
        # fires). Pre-fix the regex would simply not match "Annex M" and
        # the drift would silently go undetected.
        drifted, bad = _polished_prose_has_unknown_citations("Annex M says X.")
        assert drifted is True
        assert bad == "Annex M"


# ─── Issue #54 — BM25 short-query recall ─────────────────────────────────────


class TestBM25ShortQueryRecall:
    """Short queries (1-2 tokens) must still return at least one hit when
    a clear top candidate exists, even though the absolute BM25 score is
    too low to clear the default min_score cutoff."""

    def test_short_query_below_absolute_floor_still_returns_top(self) -> None:
        """``vehicle`` is a 1-token query whose top BM25 score is below 2.5
        (after source weighting). Pre-fix this returned zero hits at the
        engine's ``min_score=2.5`` setting. Post-fix the relative-cutoff
        rescue keeps the clear top winner."""
        from app.data.kb_search import top_articles_by_relevance

        hits = top_articles_by_relevance("vehicle", k=3, min_score=2.5)
        assert hits, (
            "Single-token 'vehicle' query returned no hits at min_score=2.5 — "
            "the relative-cutoff path must keep the top winner"
        )

    def test_two_token_query_returns_hits(self) -> None:
        """``transparency obligations`` is 2 tokens — must surface Art. 50."""
        from app.data.kb_search import top_articles_by_relevance

        hits = top_articles_by_relevance("transparency obligations", k=3)
        assert hits, (
            "Two-token 'transparency obligations' query returned no hits — "
            "BM25 short-query recall is broken"
        )

    def test_long_high_signal_query_still_works(self) -> None:
        """A long query with rich signal must still produce the expected
        canonical hit (Art. 19 for log-retention questions)."""
        from app.data.kb_search import top_articles_by_relevance

        hits = top_articles_by_relevance(
            "How long must logs be kept under the AI Act?",
            k=5,
            min_score=1.0,
        )
        assert "Art. 19" in hits

    def test_empty_query_still_returns_empty(self) -> None:
        """Empty / pure-stopword query produces no hits — no relative
        rescue can manufacture results from nothing."""
        from app.data.kb_search import top_articles_by_relevance

        assert top_articles_by_relevance("", k=3) == []
        # Pure stopword query → tokens=[] → empty result.
        assert top_articles_by_relevance("the and or but", k=3) == []

    def test_zero_match_query_returns_empty(self) -> None:
        """A query with tokens that DON'T match any corpus doc produces no
        results — relative-cutoff requires SOME signal."""
        from app.data.kb_search import top_articles_by_relevance

        # `xyzzyvz` won't tokenise to any known term.
        assert top_articles_by_relevance("xyzzyvz", k=3) == []


# ─── Issue #55 — Graph retrieval degraded fallback ───────────────────────────


class TestGraphRetrievalDegraded:
    """When ``_retrieve_from_graph`` catches an exception, it must signal
    degradation via ``context.degraded = True`` (or equivalent flag) AND
    fall back to KB retrieval so the engine still produces SOME context.
    ``_compute_confidence`` must report low confidence on a degraded
    context."""

    def test_graph_exception_falls_back_to_kb_and_marks_degraded(self) -> None:
        """An exception in ``execute_read`` must be caught, the function
        must fall back to KB retrieval, and the returned context must
        carry ``degraded=True``."""
        # Build a fake client that's enabled but raises on every read.
        class _ExplodingClient:
            enabled = True

            def execute_read(self, *args, **kwargs):  # noqa: ARG002
                raise RuntimeError("simulated backend outage")

        query = GraphQuery(
            intent="article_lookup",
            entities=["Art. 13"],
            raw_question="What does Art. 13 require?",
        )

        with patch(
            "app.graph.client.get_graph_client",
            return_value=_ExplodingClient(),
        ):
            ctx = _retrieve_from_graph(query)

        assert getattr(ctx, "degraded", False) is True, (
            "_retrieve_from_graph must set context.degraded=True when "
            "the backend raises"
        )
        # KB fallback should have populated SOMETHING for a known entity.
        # (Art. 13 is in EC_CHECKER_OBLIGATION_MAP so the KB fallback path
        # produces at least one obligation row.)
        assert ctx.obligations, (
            "KB fallback must run on graph exception so the engine has "
            "something to answer with"
        )

    def test_compute_confidence_low_on_degraded(self) -> None:
        """When ``context.degraded`` is True, ``_compute_confidence`` must
        return a low value (< 0.5) regardless of node count."""
        ctx = GraphContext()
        ctx.nodes_traversed = 50  # would normally be high-confidence
        ctx.gaps = [{"id": "g1", "text": "X", "severity": "high"}]
        ctx.degraded = True  # type: ignore[attr-defined]

        confidence = _compute_confidence(ctx)
        assert confidence < 0.5, (
            f"Degraded context must yield low confidence; got {confidence}"
        )

    def test_compute_confidence_normal_when_not_degraded(self) -> None:
        """Backward compat: a healthy rich context still gets 0.85."""
        ctx = GraphContext()
        ctx.nodes_traversed = 50
        ctx.gaps = [{"id": "g1", "text": "X", "severity": "high"}]
        # NOT degraded.
        confidence = _compute_confidence(ctx)
        assert confidence == 0.85

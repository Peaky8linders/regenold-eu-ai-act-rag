"""Regression guards for the RAG-hardening round driven by competition rules.

Four high-impact fixes pinned here:

1. ``_deterministic_parse`` extracts BOTH ``Art. N`` (short) and ``Article N``
   (long) forms, plus ``Annex [IVXLC]+``. Multi-turn questions where the
   preamble uses one form and the live question uses the other no longer
   silently lose the anchor.

2. ``_claude_max_enhance_answer`` builds and supplies an
   ``EU AI ACT REFERENCES:`` block to Sonnet — same structured ground truth
   the direct-LLM path uses. Closes the fabrication surface where the
   system prompt asks the LLM to "cite only supplied references" while no
   references block was attached.

3. ``_polished_prose_has_unknown_citations`` cross-checks every Art./Annex
   mention in the polished prose against ``ARTICLE_EXISTENCE``. On drift,
   ``_two_stage_generate`` drops the polish and ships the Stage-1 KG answer
   so a fabricated ``Art. 999`` never reaches the wire.

4. ``OPENAI_TIMEOUT_SECONDS`` default lowered from 60 s to 8 s — the
   wrapper can stall for a full minute under the old default, blowing the
   Regenold latency budget.
"""
from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest

from app.engines.graph_rag import (
    GraphContext,
    GraphQuery,
    _build_context_references_block,
    _claude_max_enhance_answer,
    _deterministic_parse,
    _polished_prose_has_unknown_citations,
    _two_stage_generate,
)


# ─── Fix 1 — _deterministic_parse handles long-form + Annex ──────────────────


@pytest.fixture(autouse=True)
def _r77_enable_stage2_polish(monkeypatch: pytest.MonkeyPatch) -> None:
    """R77 — Stage-2 polish now defaults OFF (``P2P_GRAPH_RAG_ENABLE_STAGE2``).

    These tests predate that default and exercise the Stage-2 path with a
    mocked provider. Force the master switch ON so they keep testing
    Stage-2 behaviour; the provider + needs-enhancement gates still apply,
    so the "Stage-2 skipped" tests in this module still skip correctly.
    """
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")


class TestDeterministicParseEntities:
    """Multi-turn correctness: the parse must capture every article + annex
    reference shape the route can possibly thread into the question."""

    def test_short_form_art_dot(self) -> None:
        q = "What does Art. 13 require?"
        assert _deterministic_parse(q).entities == ["Art. 13"]

    def test_long_form_article(self) -> None:
        q = "What does Article 13 require?"
        assert _deterministic_parse(q).entities == ["Art. 13"]

    def test_long_form_article_in_multi_turn_preamble(self) -> None:
        # Pre-fix this dropped to entities=[] — the regex required `Art.`,
        # so an assistant turn that used `Article 13` (the long form) lost
        # the anchor entirely on the follow-up turn.
        q = (
            "Conversation so far:\n"
            "User: What does Article 13 require?\n"
            "Assistant: Article 13(1) requires transparency.\n\n"
            "Latest question:\nAnd for deployers?"
        )
        assert "Art. 13" in _deterministic_parse(q).entities

    def test_annex_roman_extracted(self) -> None:
        q = "What does Annex IV require?"
        assert _deterministic_parse(q).entities == ["Annex IV"]

    def test_annex_roman_normalised_to_uppercase(self) -> None:
        q = "What does annex iv require?"
        assert _deterministic_parse(q).entities == ["Annex IV"]

    def test_dedup_when_mentioned_twice(self) -> None:
        q = "Article 13 vs Art. 13"
        assert _deterministic_parse(q).entities == ["Art. 13"]

    def test_mixed_article_and_annex(self) -> None:
        q = "Compare Art. 9 obligations against Annex III categories"
        ents = _deterministic_parse(q).entities
        assert "Art. 9" in ents
        assert "Annex III" in ents

    def test_three_digit_article_excluded(self) -> None:
        # `Art. 113` is real (last article); `Art. 1234` is junk → don't capture.
        assert _deterministic_parse("Art. 113 applies").entities == ["Art. 113"]
        # Word-boundary in the regex prevents 1234 from being read as 123.
        assert _deterministic_parse("Art. 1234").entities == []


# ─── Fix 2 — Stage-2 prompt includes EU AI ACT REFERENCES block ──────────────


class TestStage2PromptIncludesReferencesBlock:
    """The Stage-2 user message must carry the structured references block.
    Without this, ANSWER_GENERATE_SYSTEM's `cite only supplied references`
    clause has nothing to constrain — pure fabrication fuel."""

    def test_references_block_appears_when_context_supplied(self) -> None:
        captured: list[str] = []

        def capture(**kwargs: object) -> str:
            captured.append(str(kwargs.get("user", "")))
            return "Polished answer."

        ctx = GraphContext()
        ctx.obligations = [
            {"id": "obl-1", "text": "Provide transparency info.", "article": "Art. 13"},
        ]
        with patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            side_effect=capture,
        ):
            _claude_max_enhance_answer(
                question="What does Art. 13 require?",
                kg_answer="Draft answer.",
                context=ctx,
            )

        assert captured, "wrapper must have been called"
        body = captured[0]
        assert "EU AI ACT REFERENCES:" in body
        assert "obl-1" in body
        assert "Art. 13" in body
        assert "Provide transparency info." in body

    def test_references_block_omitted_when_no_context(self) -> None:
        captured: list[str] = []

        def capture(**kwargs: object) -> str:
            captured.append(str(kwargs.get("user", "")))
            return "Polished."

        with patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            side_effect=capture,
        ):
            _claude_max_enhance_answer(
                question="Q",
                kg_answer="A",
                context=None,
            )

        # Backward compat: when no context is supplied, the block is skipped
        # (the KG draft is still passed).
        assert "EU AI ACT REFERENCES:" not in captured[0]
        assert "KNOWLEDGE GRAPH ANSWER" in captured[0]


class TestBuildContextReferencesBlock:
    """_build_context_references_block must render obligations / article_info /
    gaps / dimension_info in a Sonnet-readable layout."""

    def test_empty_context_renders_no_match_string(self) -> None:
        block = _build_context_references_block(GraphContext())
        assert "No EU AI Act references match" in block

    def test_obligations_rendered_with_id_and_article(self) -> None:
        ctx = GraphContext()
        ctx.obligations = [
            {"id": "o1", "text": "Do X.", "article": "Art. 9"},
            {"id": "o2", "text": "Do Y.", "article": "Art. 10"},
        ]
        block = _build_context_references_block(ctx)
        assert "APPLICABLE OBLIGATIONS (2)" in block
        assert "[o1]" in block and "[o2]" in block
        assert "Art. 9" in block and "Art. 10" in block

    def test_gaps_rendered_with_severity(self) -> None:
        ctx = GraphContext()
        ctx.gaps = [{"id": "g1", "text": "Missing FRIA.", "severity": "high"}]
        block = _build_context_references_block(ctx)
        assert "COMPLIANCE GAPS" in block
        assert "Missing FRIA." in block
        assert "Severity: high" in block


# ─── Fix 3 — Post-Stage-2 hallucination drift guard ──────────────────────────


class TestPolishedProseDriftGuard:
    """Hallucination defence: every Art./Annex named in polished prose must
    exist in the EU AI Act catalog. On mismatch, fall back to KG answer."""

    @pytest.mark.parametrize("prose", [
        "Article 13 requires transparency.",
        "Art. 9 covers risk management.",
        "Per Annex IV, technical documentation is required.",
        "Art. 26(1) and Annex III together cover deployer duties.",
        "",
        "No matching obligation found.",
    ])
    def test_real_provisions_pass(self, prose: str) -> None:
        drifted, bad = _polished_prose_has_unknown_citations(prose)
        assert drifted is False, f"False positive on {prose!r}: {bad}"

    @pytest.mark.parametrize("prose,expected_bad", [
        ("Art. 999 requires nothing.", "Art. 999"),
        ("Article 200 is the new rule.", "Art. 200"),
        ("Per Annex XX you must register.", "Annex XX"),
    ])
    def test_fabricated_provisions_caught(self, prose: str, expected_bad: str) -> None:
        drifted, bad = _polished_prose_has_unknown_citations(prose)
        assert drifted is True
        assert bad == expected_bad

    def test_mixed_real_and_fake_is_caught(self) -> None:
        # Art. 13 is real, Art. 250 is not — catching ANY fabrication is enough.
        drifted, bad = _polished_prose_has_unknown_citations(
            "Article 13 requires transparency, but Art. 250 overrides this."
        )
        assert drifted is True
        assert bad == "Art. 250"


class TestTwoStageGenerateDriftFallback:
    """End-to-end through _two_stage_generate: when Stage-2 polish fabricates,
    the helper drops the polish and returns the Stage-1 KG answer."""

    def test_polished_with_real_cite_returned_as_enhanced(self) -> None:
        with (
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Article 13 requires transparency for deployers.",
            ),
        ):
            answer, used = _two_stage_generate(
                "Conversation so far:\nUser: Art. 13?\nAssistant: …\n\nLatest question:\nAnd for deployers?",
                GraphContext(),
            )
        assert used is True
        assert "Article 13" in answer

    def test_polished_with_fake_article_falls_back_to_kg(self) -> None:
        with (
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Article 999 requires gibberish.",
            ),
        ):
            answer, used = _two_stage_generate(
                "Conversation so far:\nUser: foo\nAssistant: bar\n\nLatest question:\nbaz?",
                GraphContext(),
            )
        # Fabricated cite → drop polish, return KG answer, mark stage2 unused.
        assert used is False
        assert "Article 999" not in answer

    def test_polished_with_fake_annex_falls_back_to_kg(self) -> None:
        with (
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Per Annex XX, training data must be cleaned.",
            ),
        ):
            answer, used = _two_stage_generate(
                "Conversation so far:\nUser: foo\nAssistant: bar\n\nLatest question:\nbaz?",
                GraphContext(),
            )
        assert used is False
        assert "Annex XX" not in answer


# ─── Fix 4 — Tightened proxy timeout default ─────────────────────────────────


class TestOpenAIWrapperTimeoutDefault:
    """Singleton timeout is the Stage-1/2 Sonnet polish ceiling — generous
    (60 s) to let Sonnet through Claude Max actually answer. The
    *latency-budget protection* lives on the intent classifier's
    per-request ``timeout_seconds=2.5`` (the only call on the hot
    latency path; Stage-2 polish runs after Stage-1 already landed an
    answer, so a slow polish doesn't blow the partner's wait time)."""

    def test_default_timeout_is_generous_for_sonnet_polish(self) -> None:
        # Force a clean re-instantiation against the current env var.
        from app.llm import openai_wrapper_provider as mod

        old = os.environ.pop("OPENAI_TIMEOUT_SECONDS", None)
        try:
            importlib.reload(mod)
            provider = mod._OpenAIWrapperProvider()
            # Sonnet 4.6 through the wrapper takes 10-20 s on real
            # questions. Sub-10s defaults killed every real call.
            assert 30.0 <= provider._timeout <= 180.0, (
                f"Default timeout {provider._timeout}s is outside the "
                "30-180 s window — too short kills Sonnet polish, "
                "too long lets a wedged wrapper pin a request thread."
            )
        finally:
            if old is not None:
                os.environ["OPENAI_TIMEOUT_SECONDS"] = old
            importlib.reload(mod)

    def test_intent_classifier_uses_short_per_request_timeout(self) -> None:
        """The actual latency-budget protection: intent classifier sets
        ``timeout_seconds=2.5`` per request, independent of the
        singleton's 60 s default."""
        from app.llm.intent_classifier import _TIMEOUT_SECONDS

        assert _TIMEOUT_SECONDS <= 5.0, (
            f"Intent classifier timeout {_TIMEOUT_SECONDS}s is too long — "
            "this is the only LLM call on the hot latency budget."
        )

    def test_env_override_still_honoured(self) -> None:
        from app.llm import openai_wrapper_provider as mod

        with patch.dict(os.environ, {"OPENAI_TIMEOUT_SECONDS": "15"}):
            importlib.reload(mod)
            provider = mod._OpenAIWrapperProvider()
            assert provider._timeout == 15.0
        importlib.reload(mod)


# ─── Fix 1 integration — multi-turn anchors survive into the engine ──────────


class TestMultiTurnAnchorSurvivesIntoGraphQuery:
    """End-to-end: a multi-turn conversation where the preamble uses long-form
    `Article 13` must yield `Art. 13` in the GraphQuery.entities — so the
    retrieve step can fetch article-specific obligations."""

    def test_long_form_article_in_preamble_carried_through(self) -> None:
        q = (
            "Conversation so far:\n"
            "User: What does Article 13 require?\n"
            "Assistant: Article 13 covers transparency.\n\n"
            "Latest question:\nAnd what about deployers?"
        )
        gq = _deterministic_parse(q)
        assert "Art. 13" in gq.entities
        # Intent should at least register as obligation_check or article_lookup
        assert gq.intent in {"obligation_check", "article_lookup"}

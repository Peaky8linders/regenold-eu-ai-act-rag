"""Tests for app.llm.entity_extractor — stage-0.5 LLM article extraction.

Coverage plan (six classes, ~28 test functions):

  TestEntityExtractorGate          — enabled / disabled paths
  TestEntityExtractorParse         — JSON parsing, validation, ARTICLE_EXISTENCE lint
  TestEntityExtractorCache         — LRU cache hit/miss, success-only caching
  TestEntityExtractorCircuitBreaker — opens after threshold failures, resets on success
  TestEntityExtractorIntegration   — happy-path end-to-end via mocked provider
  TestEntityExtractorGraphRagWiring — extract_entities result flows into _deterministic_parse

The module's safety contract: extract_entities() ALWAYS returns [] on any
failure — never raises, never blocks the parse pipeline.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.llm import entity_extractor as ee
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Wipe cache + breaker between tests."""
    ee._reset_for_tests()
    yield
    ee._reset_for_tests()


# ── TestEntityExtractorGate ──────────────────────────────────────────────────


class TestEntityExtractorGate:
    """is_entity_extractor_enabled() and the early-exit paths in extract_entities()."""

    def test_disabled_when_no_provider_configured(self, monkeypatch) -> None:
        """No OPENAI_API_BASE / OPENAI_API_KEY → not enabled."""
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert not ee.is_entity_extractor_enabled()

    def test_extract_entities_returns_empty_when_not_enabled(self, monkeypatch) -> None:
        """extract_entities() returns [] instantly when no provider is configured."""
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert ee.extract_entities("How long must records be kept?") == []

    def test_disabled_by_env_gate(self, monkeypatch) -> None:
        """REGENOLD_ENTITY_EXTRACTOR=0 disables even when a provider is configured."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        # Patch the module-level boolean so we don't need to reload the module.
        with patch.object(ee, "_ENABLED_BY_ENV", False):
            assert not ee.is_entity_extractor_enabled()
            assert ee.extract_entities("Can AI screen job applicants?") == []

    def test_disabled_when_breaker_open(self, monkeypatch) -> None:
        """After _FAILURE_THRESHOLD failures, is_entity_extractor_enabled() → False."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class FailingProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    error="network_error: refused",
                    model="claude-haiku-4-5",
                    elapsed_ms=5,
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=FailingProvider()):
            for i in range(ee._FAILURE_THRESHOLD):
                ee.extract_entities(f"unique question {i}")

        # Breaker is now open.
        assert not ee.is_entity_extractor_enabled()

    def test_returns_empty_on_empty_question(self, monkeypatch) -> None:
        """Blank / whitespace-only input short-circuits before the provider."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        assert ee.extract_entities("") == []
        assert ee.extract_entities("   ") == []

    def test_enabled_when_wrapper_configured(self, monkeypatch) -> None:
        """is_entity_extractor_enabled() returns True when wrapper env vars are set."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        assert ee.is_entity_extractor_enabled()


# ── TestEntityExtractorParse ─────────────────────────────────────────────────


class TestEntityExtractorParse:
    """_parse_extraction_json() — happy paths, edge cases, and ARTICLE_EXISTENCE lint."""

    def test_valid_json_parsed_correctly(self) -> None:
        raw = '{"articles": ["Art. 12", "Art. 19"], "confidence": 0.9}'
        result = ee._parse_extraction_json(raw)
        assert result is not None
        assert result.articles == ("Art. 12", "Art. 19")
        assert result.confidence == pytest.approx(0.9)

    def test_annex_normalised_to_uppercase_roman(self) -> None:
        raw = '{"articles": ["Annex III", "Art. 6"], "confidence": 0.85}'
        result = ee._parse_extraction_json(raw)
        assert result is not None
        assert "Annex III" in result.articles

    def test_hallucinated_article_rejected_via_article_existence(self) -> None:
        """Art. 999 is not in ARTICLE_EXISTENCE — must be filtered out."""
        raw = '{"articles": ["Art. 999", "Art. 5"], "confidence": 0.88}'
        result = ee._parse_extraction_json(raw)
        assert result is not None
        # Art. 999 should be dropped; Art. 5 should survive.
        assert "Art. 5" in result.articles
        assert all("999" not in a for a in result.articles)

    def test_all_hallucinated_refs_returns_none(self) -> None:
        """If every article is invalid, parsing returns None (not an empty result)."""
        raw = '{"articles": ["Art. 999", "Art. 998"], "confidence": 0.9}'
        result = ee._parse_extraction_json(raw)
        assert result is None

    def test_malformed_json_returns_none(self) -> None:
        assert ee._parse_extraction_json("I cannot answer this question.") is None
        assert ee._parse_extraction_json("{broken json") is None

    def test_empty_string_returns_none(self) -> None:
        assert ee._parse_extraction_json("") is None

    def test_empty_articles_list_returns_none(self) -> None:
        raw = '{"articles": [], "confidence": 0.9}'
        assert ee._parse_extraction_json(raw) is None

    def test_prose_preamble_stripped(self) -> None:
        """Parser strips text before the opening brace (model sometimes prefixes text)."""
        raw = (
            'Here are the relevant articles:\n'
            '{"articles": ["Art. 26"], "confidence": 0.87}\n'
            'Hope that helps!'
        )
        result = ee._parse_extraction_json(raw)
        assert result is not None
        assert "Art. 26" in result.articles

    def test_confidence_clamped_to_range(self) -> None:
        """Confidence values outside [0, 1] are clamped."""
        raw = '{"articles": ["Art. 3"], "confidence": 1.5}'
        result = ee._parse_extraction_json(raw)
        assert result is not None
        assert result.confidence == pytest.approx(1.0)

    def test_malformed_article_shape_rejected(self) -> None:
        """'Article 13(1)' violates the Art. N shape → rejected by _normalise_article."""
        raw = '{"articles": ["Article 13(1)"], "confidence": 0.9}'
        result = ee._parse_extraction_json(raw)
        # Article 13(1) fails _ARTICLE_SHAPE_RE; if there are no valid entries, None.
        assert result is None

    def test_normalise_article_canonical_form(self) -> None:
        """_normalise_article produces canonical 'Art. N' form.

        Note: _normalise_article validates SHAPE only (regex match).
        The ARTICLE_EXISTENCE catalog check happens in _parse_extraction_json,
        not here.  So Art. 0 passes the shape check (digits present) → "Art. 0".
        """
        assert ee._normalise_article("Art. 5") == "Art. 5"
        assert ee._normalise_article("Art.5") == "Art. 5"      # no-space normalised
        assert ee._normalise_article("Annex iii") == "Annex III"  # uppercased
        assert ee._normalise_article("Article 13(1)") is None  # subpoint rejected by shape regex
        assert ee._normalise_article("Art. 0") == "Art. 0"     # shape OK; ARTICLE_EXISTENCE checked elsewhere
        assert ee._normalise_article("") is None


# ── TestEntityExtractorCache ─────────────────────────────────────────────────


class TestEntityExtractorCache:
    """LRU cache: hit/miss semantics and success-only caching contract."""

    def test_cache_hit_on_repeated_identical_question(self, monkeypatch) -> None:
        """Provider called once; second call is served from cache."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        call_count = {"n": 0}

        class FakeProvider:
            def complete(self, _req):
                call_count["n"] += 1
                return OpenAIWrapperResponse(
                    text='{"articles": ["Art. 12"], "confidence": 0.9}',
                    model="claude-haiku-4-5",
                    elapsed_ms=200,
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=FakeProvider()):
            first = ee.extract_entities("How long must high-risk AI logs be retained?")
            second = ee.extract_entities("How long must high-risk AI logs be retained?")

        assert first == ["Art. 12"]
        assert second == ["Art. 12"]
        assert call_count["n"] == 1

    def test_cache_key_is_case_insensitive(self, monkeypatch) -> None:
        """Cache key normalises to lower-case so 'ART. 12' and 'art. 12' share a slot."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        call_count = {"n": 0}

        class FakeProvider:
            def complete(self, _req):
                call_count["n"] += 1
                return OpenAIWrapperResponse(
                    text='{"articles": ["Art. 27"], "confidence": 0.85}',
                    model="claude-haiku-4-5",
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=FakeProvider()):
            ee.extract_entities("What is a FRIA?")
            ee.extract_entities("WHAT IS A FRIA?")

        assert call_count["n"] == 1

    def test_failed_calls_not_cached(self, monkeypatch) -> None:
        """Provider error → nothing written to cache → second call re-hits provider."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        call_count = {"n": 0}

        responses = [
            OpenAIWrapperResponse(error="network_error: refused", model="haiku"),
            OpenAIWrapperResponse(
                text='{"articles": ["Art. 5"], "confidence": 0.92}',
                model="haiku",
            ),
        ]

        class StatefulProvider:
            def __init__(self):
                self.idx = 0

            def complete(self, _req):
                call_count["n"] += 1
                resp = responses[self.idx]
                self.idx = min(self.idx + 1, len(responses) - 1)
                return resp

        with patch.object(ee, "get_openai_wrapper_provider", return_value=StatefulProvider()):
            first = ee.extract_entities("Is social scoring prohibited?")
            # After the error, breaker has 1 failure but threshold=3 so still open for calls.
            second = ee.extract_entities("Is social scoring prohibited?")

        assert first == []
        assert second == ["Art. 5"]
        assert call_count["n"] == 2


# ── TestEntityExtractorCircuitBreaker ────────────────────────────────────────


class TestEntityExtractorCircuitBreaker:
    """Circuit breaker opens after _FAILURE_THRESHOLD consecutive failures."""

    def test_breaker_opens_after_threshold_failures(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class FailingProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    error="network_error: refused",
                    model="claude-haiku-4-5",
                    elapsed_ms=5,
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=FailingProvider()):
            for i in range(ee._FAILURE_THRESHOLD):
                assert ee.extract_entities(f"unique question {i}") == []

        assert not ee.is_entity_extractor_enabled()
        # Subsequent call also returns [] without touching the provider.
        assert ee.extract_entities("anything else") == []

    def test_breaker_resets_on_success(self, monkeypatch) -> None:
        """A successful call after failures resets the breaker failure count to 0."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        responses = [
            OpenAIWrapperResponse(error="net err", model="haiku"),
            OpenAIWrapperResponse(error="net err", model="haiku"),
            OpenAIWrapperResponse(
                text='{"articles": ["Art. 6"], "confidence": 0.9}',
                model="haiku",
            ),
        ]

        class StatefulProvider:
            def __init__(self):
                self.idx = 0

            def complete(self, _req):
                resp = responses[self.idx]
                self.idx += 1
                return resp

        with patch.object(ee, "get_openai_wrapper_provider", return_value=StatefulProvider()):
            assert ee.extract_entities("q1") == []   # fail
            assert ee.extract_entities("q2") == []   # fail
            result = ee.extract_entities("q3")       # success → resets

        assert result == ["Art. 6"]
        assert ee._BREAKER.failures == 0

    def test_breaker_parse_failure_increments_counter(self, monkeypatch) -> None:
        """A response that fails JSON parsing also increments the breaker."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class BadJsonProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    text="I don't know which article applies.",
                    model="claude-haiku-4-5",
                )

        initial_failures = ee._BREAKER.failures
        with patch.object(ee, "get_openai_wrapper_provider", return_value=BadJsonProvider()):
            ee.extract_entities("Some obscure question with no json")

        assert ee._BREAKER.failures > initial_failures


# ── TestEntityExtractorIntegration ───────────────────────────────────────────


class TestEntityExtractorIntegration:
    """Happy-path and failure-mode integration: full extract_entities() call path."""

    def test_valid_response_returns_article_list(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class FakeProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    text=(
                        '{"articles": ["Art. 12", "Art. 19"], "confidence": 0.9}'
                    ),
                    model="claude-haiku-4-5",
                    elapsed_ms=180,
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=FakeProvider()):
            result = ee.extract_entities("How long must high-risk AI logs be retained?")

        assert "Art. 12" in result
        assert "Art. 19" in result

    def test_low_confidence_response_returns_empty(self, monkeypatch) -> None:
        """Results below _MIN_CONFIDENCE are not surfaced to the caller."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class LowConfidenceProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    text='{"articles": ["Art. 3"], "confidence": 0.3}',
                    model="claude-haiku-4-5",
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=LowConfidenceProvider()):
            result = ee.extract_entities("What is an AI system?")

        assert result == []

    def test_provider_error_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class ErrorProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    error="network_error: connection refused",
                    model="claude-haiku-4-5",
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=ErrorProvider()):
            assert ee.extract_entities("Can AI assess employees?") == []

    def test_wrapper_not_logged_in_returns_empty(self, monkeypatch) -> None:
        """'Not logged in' sentinel maps to error → fail-soft []."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class NotLoggedInProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    error="wrapper_not_logged_in: Please run /login",
                    model="claude-haiku-4-5",
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=NotLoggedInProvider()):
            assert ee.extract_entities("Is biometric surveillance prohibited?") == []

    def test_max_three_articles_enforced(self, monkeypatch) -> None:
        """Even if the model returns more than 3, only the first 3 survive."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class ManyArticlesProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    text=(
                        '{"articles": ["Art. 5", "Art. 6", "Art. 9", "Art. 13"], '
                        '"confidence": 0.88}'
                    ),
                    model="claude-haiku-4-5",
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=ManyArticlesProvider()):
            result = ee.extract_entities("What are the main prohibited practices?")

        assert len(result) <= 3

    def test_annex_returned_correctly(self, monkeypatch) -> None:
        """Annex refs like 'Annex III' round-trip correctly through the extractor."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class AnnexProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    text='{"articles": ["Annex III", "Art. 6"], "confidence": 0.87}',
                    model="claude-haiku-4-5",
                )

        with patch.object(ee, "get_openai_wrapper_provider", return_value=AnnexProvider()):
            result = ee.extract_entities("What use cases make an AI system high-risk?")

        assert "Annex III" in result
        assert "Art. 6" in result


# ── TestEntityExtractorGraphRagWiring ────────────────────────────────────────


class TestEntityExtractorGraphRagWiring:
    """Stage-0.5 results flow into _deterministic_parse entities list."""

    def test_stage05_entities_populate_entities_list(self, monkeypatch) -> None:
        """When extract_entities returns articles, they appear in the parse output."""
        # Patch extract_entities to return a known list.
        with patch(
            "app.llm.entity_extractor.extract_entities",
            return_value=["Art. 12"],
        ):
            from app.engines.graph_rag import _deterministic_parse  # noqa: PLC0415

            result = _deterministic_parse(
                "How long must high-risk AI logs be retained?",
            )

        # _deterministic_parse returns a GraphQuery — the stage-0.5 hits land
        # in its `entities` list.
        assert result is not None
        all_refs = list(result.entities)
        assert "Art. 12" in all_refs

    def test_stage05_bm25_not_called_when_entities_found(self, monkeypatch) -> None:
        """When stage-0.5 extracts entities, the BM25 fallback must NOT fire."""
        bm25_called = {"n": 0}

        def _fake_bm25(question, k=3, min_score=1.0):
            bm25_called["n"] += 1
            return []

        with (
            patch("app.llm.entity_extractor.extract_entities", return_value=["Art. 12"]),
            patch("app.data.kb_search.top_articles_by_relevance", side_effect=_fake_bm25),
        ):
            from app.engines.graph_rag import _deterministic_parse  # noqa: PLC0415

            _deterministic_parse(
                "How long must high-risk AI logs be retained?",
            )

        assert bm25_called["n"] == 0, (
            "BM25 fallback must not fire when stage-0.5 returned entities"
        )

    def test_bm25_fires_when_stage05_returns_empty(self, monkeypatch) -> None:
        """When extract_entities returns [], the BM25 fallback SHOULD fire."""
        bm25_called = {"n": 0}

        def _fake_bm25(question, k=3, min_score=1.0):
            bm25_called["n"] += 1
            return ["Art. 19"]

        with (
            patch("app.llm.entity_extractor.extract_entities", return_value=[]),
            patch("app.data.kb_search.top_articles_by_relevance", side_effect=_fake_bm25),
            # Also stub chapter-scoped search so it returns nothing (fall through to full BM25).
            patch(
                "app.data.chapter_summaries.candidate_chapters_for_query",
                return_value=[],
            ),
        ):
            from app.engines.graph_rag import _deterministic_parse  # noqa: PLC0415

            _deterministic_parse(
                "obscure question with no keyword hits",
            )

        assert bm25_called["n"] >= 1, (
            "BM25 fallback must fire when both keyword AND stage-0.5 extraction return empty"
        )

    def test_stage05_exception_falls_through_to_bm25(self, monkeypatch) -> None:
        """If extract_entities raises, the parse pipeline catches it and continues."""
        def _raising_extractor(question: str):
            raise RuntimeError("provider exploded")

        bm25_called = {"n": 0}

        def _fake_bm25(question, k=3, min_score=1.0):
            bm25_called["n"] += 1
            return ["Art. 5"]

        with (
            patch("app.llm.entity_extractor.extract_entities", side_effect=_raising_extractor),
            patch("app.data.kb_search.top_articles_by_relevance", side_effect=_fake_bm25),
            patch(
                "app.data.chapter_summaries.candidate_chapters_for_query",
                return_value=[],
            ),
        ):
            from app.engines.graph_rag import _deterministic_parse  # noqa: PLC0415

            # Must not raise — exception is caught inside the `except BLE001` block.
            result = _deterministic_parse(
                "obscure question that triggers the raise",
            )

        assert result is not None
        # BM25 should have fired as the fallback.
        assert bm25_called["n"] >= 1


# ── TestProviderResolution ────────────────────────────────────────────────────


class TestProviderResolution:
    """_resolve_provider() precedence: Groq beats wrapper when both configured."""

    def test_groq_wins_over_wrapper_when_both_configured(self, monkeypatch) -> None:
        """When Groq is enabled, _resolve_provider returns the Groq singleton."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

        result = ee._resolve_provider()
        assert result is not None
        provider, model = result
        # Model should be the Groq default.
        assert "llama" in model or "groq" in model.lower() or model == ee._DEFAULT_GROQ_MODEL

    def test_wrapper_used_when_groq_not_configured(self, monkeypatch) -> None:
        """Without Groq, _resolve_provider returns the wrapper singleton."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        result = ee._resolve_provider()
        assert result is not None
        _, model = result
        assert model == ee._DEFAULT_MODEL

    def test_resolve_returns_none_when_nothing_configured(self, monkeypatch) -> None:
        """With no provider env vars, _resolve_provider returns None."""
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)

        assert ee._resolve_provider() is None


# ── TestNormaliseArticle ──────────────────────────────────────────────────────


class TestNormaliseArticle:
    """_normalise_article: shape validation and canonical form output."""

    def test_simple_art_n(self) -> None:
        assert ee._normalise_article("Art. 5") == "Art. 5"

    def test_art_without_space(self) -> None:
        assert ee._normalise_article("Art.5") == "Art. 5"

    def test_annex_roman_uppercased(self) -> None:
        assert ee._normalise_article("Annex iii") == "Annex III"
        assert ee._normalise_article("annex III") == "Annex III"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        assert ee._normalise_article("  Art. 13  ") == "Art. 13"

    def test_article_n_subpoint_rejected(self) -> None:
        """Subpoint forms like 'Article 13(1)' violate _ARTICLE_SHAPE_RE."""
        assert ee._normalise_article("Article 13(1)") is None

    def test_arabic_numeral_annex_rejected(self) -> None:
        """'Annex 3' (Arabic, not Roman) violates the shape regex."""
        assert ee._normalise_article("Annex 3") is None

    def test_empty_string_returns_none(self) -> None:
        assert ee._normalise_article("") is None

    def test_none_input_returns_none(self) -> None:
        assert ee._normalise_article(None) is None  # type: ignore[arg-type]

    def test_roman_numeral_article_rejected(self) -> None:
        """'Article III' (Roman for an article number) violates shape."""
        assert ee._normalise_article("Article III") is None

    def test_high_article_number(self) -> None:
        """Art. 113 (max valid article) is accepted by shape check."""
        assert ee._normalise_article("Art. 113") == "Art. 113"

    def test_three_digit_article_accepted(self) -> None:
        """Shape regex accepts 1-3 digit article numbers."""
        assert ee._normalise_article("Art. 99") == "Art. 99"

    def test_annex_xiii(self) -> None:
        assert ee._normalise_article("Annex XIII") == "Annex XIII"


# ── TestResetForTests ─────────────────────────────────────────────────────────


class TestResetForTests:
    """_reset_for_tests(): clears cache + resets breaker, idempotent."""

    def test_reset_clears_cache(self) -> None:
        """After a cache put, _reset_for_tests wipes the cache entry."""
        # Seed the cache directly — this isolates the reset behaviour from the
        # provider path (exercised separately in TestEntityExtractorIntegration).
        seeded = ee.EntityExtractionResult(
            articles=("Art. 5",), confidence=0.88, elapsed_ms=1
        )
        ee._cache_put("test_reset_cache_key", seeded)

        # Cache should be non-empty.
        with ee._CACHE_LOCK:
            pre_size = len(ee._CACHE)
        assert pre_size > 0

        ee._reset_for_tests()

        with ee._CACHE_LOCK:
            post_size = len(ee._CACHE)
        assert post_size == 0

    def test_reset_clears_breaker(self) -> None:
        """After failures open the breaker, _reset_for_tests resets it."""
        # Drive the breaker open via the real API so both `failures` AND
        # `last_failure_ts` land — a bare `failures =` poke leaves the
        # timestamp at 0.0, so open() auto-resets via the stale-window check.
        for _ in range(ee._FAILURE_THRESHOLD):
            ee._BREAKER.record_failure()
        assert ee._BREAKER.open()

        ee._reset_for_tests()

        assert ee._BREAKER.failures == 0
        assert not ee._BREAKER.open()

    def test_reset_is_idempotent(self) -> None:
        """Calling _reset_for_tests twice doesn't raise."""
        ee._reset_for_tests()
        ee._reset_for_tests()
        assert ee._BREAKER.failures == 0


# ── TestIssue50Hardening ──────────────────────────────────────────────────────


class TestIssue50Hardening:
    """Issue #50: is_entity_extractor_enabled() must NOT construct singletons."""

    def test_gate_does_not_call_get_openai_wrapper_provider(
        self, monkeypatch
    ) -> None:
        """is_entity_extractor_enabled() must not construct the httpx pool."""
        constructed = {"n": 0}

        def _sentinel(*_a, **_kw):
            constructed["n"] += 1
            raise AssertionError("singleton constructed inside gate — issue #50 violated")

        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        with patch.object(ee, "get_openai_wrapper_provider", side_effect=_sentinel):
            # Must not raise — the gate should only call is_openai_wrapper_enabled(),
            # not get_openai_wrapper_provider().
            try:
                ee.is_entity_extractor_enabled()
            except AssertionError:
                pytest.fail(
                    "is_entity_extractor_enabled() called get_openai_wrapper_provider() "
                    "— violates issue #50 hardening contract"
                )

    def test_gate_does_not_call_get_groq_intent_provider(
        self, monkeypatch
    ) -> None:
        """is_entity_extractor_enabled() must not construct the Groq singleton."""
        monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

        def _sentinel(*_a, **_kw):
            raise AssertionError("Groq singleton constructed inside gate — issue #50 violated")

        with patch.object(ee, "get_groq_intent_provider", side_effect=_sentinel):
            try:
                ee.is_entity_extractor_enabled()
            except AssertionError:
                pytest.fail(
                    "is_entity_extractor_enabled() called get_groq_intent_provider() "
                    "— violates issue #50 hardening contract"
                )


# ── TestModelOverride ─────────────────────────────────────────────────────────


class TestModelOverride:
    """REGENOLD_ENTITY_MODEL / REGENOLD_ENTITY_MODEL_GROQ override defaults."""

    def test_default_model_is_haiku(self, monkeypatch) -> None:
        """Without env override, the wrapper model defaults to claude-haiku-4-5-20251001."""
        assert ee._DEFAULT_MODEL == "claude-haiku-4-5-20251001"

    def test_default_groq_model_is_llama(self, monkeypatch) -> None:
        """Without env override, the Groq model defaults to llama-3.3-70b-versatile."""
        assert "llama" in ee._DEFAULT_GROQ_MODEL.lower()

    def test_model_override_via_env_reload(self, monkeypatch) -> None:
        """REGENOLD_ENTITY_MODEL env var is picked up on module reload."""
        import importlib

        monkeypatch.setenv("REGENOLD_ENTITY_MODEL", "claude-custom-7b")
        import app.llm.entity_extractor as ee_module

        importlib.reload(ee_module)
        try:
            assert ee_module._DEFAULT_MODEL == "claude-custom-7b"
        finally:
            monkeypatch.delenv("REGENOLD_ENTITY_MODEL", raising=False)
            importlib.reload(ee_module)


# ── TestEntityExtractorConcurrency ────────────────────────────────────────────


class TestEntityExtractorConcurrency:
    """Bounded-concurrency semaphore: an exhausted budget skips the LLM call."""

    def test_exhausted_semaphore_skips_llm_call(self, monkeypatch) -> None:
        """When every concurrency slot is held, extract_entities returns []
        WITHOUT calling the provider — it degrades to the BM25 fallback."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        called = {"n": 0}

        class FakeProvider:
            def complete(self, _req):
                called["n"] += 1
                raise AssertionError(
                    "provider must not be called when the budget is exhausted"
                )

        # Drain every concurrency slot.
        acquired = 0
        while ee._CONCURRENCY.acquire(blocking=False):
            acquired += 1
        try:
            with patch.object(
                ee, "get_openai_wrapper_provider", return_value=FakeProvider()
            ):
                result = ee.extract_entities(
                    "How long must high-risk AI logs be retained?"
                )
            assert result == []
            assert called["n"] == 0
        finally:
            for _ in range(acquired):
                ee._CONCURRENCY.release()

    def test_semaphore_released_after_call(self, monkeypatch) -> None:
        """A normal extract_entities call is balanced — the finally-release
        leaves the full concurrency budget re-acquirable (no slot leak)."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class FakeProvider:
            def complete(self, _req):
                return OpenAIWrapperResponse(
                    text='{"articles": ["Art. 5"], "confidence": 0.9}',
                    model="claude-haiku-4-5",
                )

        with patch.object(
            ee, "get_openai_wrapper_provider", return_value=FakeProvider()
        ):
            ee.extract_entities("Is social scoring prohibited?")

        # Every slot must be re-acquirable → none leaked by the call.
        got = 0
        while ee._CONCURRENCY.acquire(blocking=False):
            got += 1
        for _ in range(got):
            ee._CONCURRENCY.release()
        assert got == ee._MAX_CONCURRENCY

    def test_semaphore_released_on_provider_exception(self, monkeypatch) -> None:
        """When provider.complete() raises, the finally-release still returns
        the slot — a failing call must not permanently leak the budget."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        class BoomProvider:
            def complete(self, _req):
                raise RuntimeError("provider exploded")

        with patch.object(
            ee, "get_openai_wrapper_provider", return_value=BoomProvider()
        ):
            result = ee.extract_entities("Is social scoring prohibited?")
        assert result == []

        got = 0
        while ee._CONCURRENCY.acquire(blocking=False):
            got += 1
        for _ in range(got):
            ee._CONCURRENCY.release()
        assert got == ee._MAX_CONCURRENCY


# ── TestArticleExistenceLint ──────────────────────────────────────────────────


class TestArticleExistenceLint:
    """ARTICLE_EXISTENCE catalog: valid refs normalise; hallucinated refs rejected."""

    def test_all_valid_refs_in_catalog_accepted(self) -> None:
        """Every Art. 1 – Art. 113 ref passes through _normalise_article."""
        for n in range(1, 114):
            norm = ee._normalise_article(f"Art. {n}")
            assert norm == f"Art. {n}", f"Art. {n} should normalise cleanly"

    def test_all_valid_annexes_in_catalog_accepted(self) -> None:
        """All 13 annexes normalise to their uppercase Roman form."""
        valid = [
            "Annex I", "Annex II", "Annex III", "Annex IV", "Annex V",
            "Annex VI", "Annex VII", "Annex VIII", "Annex IX", "Annex X",
            "Annex XI", "Annex XII", "Annex XIII",
        ]
        for annex in valid:
            norm = ee._normalise_article(annex)
            assert norm == annex, f"{annex} should normalise cleanly"

    def test_hallucinated_ref_filtered_by_parse(self) -> None:
        """Art. 200 passes shape check but is rejected by ARTICLE_EXISTENCE in _parse_extraction_json."""
        raw = '{"articles": ["Art. 200", "Art. 5"], "confidence": 0.9}'
        result = ee._parse_extraction_json(raw)
        # Art. 5 survives; Art. 200 is dropped.
        assert result is not None
        assert "Art. 5" in result.articles
        assert not any("200" in a for a in result.articles)

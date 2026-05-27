"""R84 — narrow Stage-2 gate + max_tokens 384 + request-local intent memo.

Verifies the three R84 latency-reduction levers:

* :func:`app.engines.graph_rag._needs_stage2_enhancement` — long_q
  threshold raised 200 → 350, ≥2 entities raised → ≥3, and 6 overly-
  broad keywords (``"explain why"`` / ``"why do"`` / ``"why does"`` /
  ``"why is"`` / ``"what are the implications"`` / ``"impact of"``)
  removed from ``_COMPLEX_QUESTION_KEYWORDS``. Multi-turn and
  ``gap_analysis`` / ``cross_framework`` intents stay as always-fire.

* :class:`app.config.GraphRAGSettings` ``max_tokens`` default is now
  384 (was 512). Prompt mandates "AT MOST 3 sentences" — 384 keeps
  ~80 tokens headroom while trimming the Sonnet generation tail.

* :func:`app.routes.regenold._classify_intent_cached` — ContextVar
  memo collapses the three route call sites to one cold-cache
  ``classify_intent`` RTT per request.

The latency wins land LIVE only (the davidath bench's TestClient
never wires a Stage-2 provider, so the gate change is a no-op on the
local rubric); these tests pin the BEHAVIOUR so a future revert is
loud, not silent.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.engines.graph_rag import (
    GraphContext,
    GraphQuery,
    _COMPLEX_QUESTION_KEYWORDS,
    _needs_stage2_enhancement,
)


# ─── R84-A — Stage-2 gate behaviour ────────────────────────────────────────


class TestR84StageGateNarrow:
    """Pin the new (R84) ``_needs_stage2_enhancement`` thresholds.

    The R81-A1 live rep-100 decomposition (60/100 rows fired Stage-2;
    ON p50 21.4 s vs OFF p50 3.3 s, 6.5× cost) found 28/60 fires came
    from the bare ``> 200 chars`` trigger and 16/60 from the bare
    ``≥ 2 entities`` trigger — both routine obligation questions the
    deterministic answer handles fine. R84 tightens both gates.
    """

    @staticmethod
    def _ctx() -> GraphContext:
        return GraphContext()

    # ── long_q boundary ──

    def test_long_q_under_350_no_longer_fires(self) -> None:
        """A medium-length (200-350 chars) single-anchor obligation
        question should NOT fire Stage-2 post-R84 (fired pre-R84
        because > 200). This is the R81-A1 ``28/60 fires`` bucket."""
        question = (
            "What are the obligations a provider of a high-risk AI system "
            "must comply with under Article 16 of the EU AI Act when the "
            "system is placed on the EU market by their nominated EU "
            "distributor for use in a clinical setting?"
        )
        assert 200 < len(question) < 350, (
            f"test setup invariant — wanted 200 < len < 350, got {len(question)}"
        )
        query = GraphQuery(entities=["Art. 16"])
        assert _needs_stage2_enhancement(question, self._ctx(), query) is False

    def test_long_q_over_350_still_fires(self) -> None:
        """A genuinely long synthesis question (> 350 chars) still fires."""
        question = (
            "Consider a provider of a high-risk AI system that intends to "
            "place the system on the EU market through a chain of "
            "distributors and a non-EU authorised representative. Walk "
            "through every step of the conformity assessment, technical "
            "documentation, post-market monitoring, serious-incident "
            "reporting, and corrective-action obligations that apply "
            "along that distribution chain over the system's lifecycle."
        )
        assert len(question) > 350, (
            f"test setup invariant — wanted len > 350, got {len(question)}"
        )
        query = GraphQuery(entities=["Art. 16"])
        assert _needs_stage2_enhancement(question, self._ctx(), query) is True

    # ── entities boundary ──

    def test_two_entities_no_longer_fires(self) -> None:
        """Two-entity question with a short live_q + no kw should NOT fire."""
        question = "What does Article 13 say compared to Article 14?"
        query = GraphQuery(entities=["Art. 13", "Art. 14"])
        # Question has "compared" but not in the kept _COMPLEX_QUESTION_KEYWORDS
        # set. Wait — "compare" IS in the kept set as substring; verify:
        # Use a phrasing without any kept-kw substring.
        question = "List the recordkeeping requirements in Article 13 and Article 14."
        query = GraphQuery(entities=["Art. 13", "Art. 14"])
        assert _needs_stage2_enhancement(question, self._ctx(), query) is False

    def test_three_entities_still_fires(self) -> None:
        """Three or more entities trigger the synthesis path."""
        question = "Brief on Article 13, Article 14, and Article 15."
        query = GraphQuery(entities=["Art. 13", "Art. 14", "Art. 15"])
        assert _needs_stage2_enhancement(question, self._ctx(), query) is True

    # ── dropped keywords ──

    def test_dropped_keywords_no_longer_fire(self) -> None:
        """The 6 overly-broad keywords R84 dropped no longer trigger
        Stage-2 on a short single-entity question."""
        # Each phrasing is < 350 chars + a single entity so ONLY the
        # keyword could fire the gate. Pre-R84 these all returned True;
        # post-R84 they MUST return False.
        droplist = [
            "Explain why providers must keep logs.",
            "Why do providers maintain technical documentation?",
            "Why does Article 13 require transparency?",
            "Why is human oversight required?",
            "What are the implications of Annex III classification?",
            "Discuss the impact of Article 50 on chatbots.",
        ]
        for q in droplist:
            query = GraphQuery(entities=["Art. 13"])
            assert _needs_stage2_enhancement(q, self._ctx(), query) is False, (
                f"R84-dropped keyword unexpectedly fired Stage-2 on: {q!r}"
            )

    def test_dropped_keywords_set_membership(self) -> None:
        """Belt-and-braces — verify the keywords are physically gone
        from ``_COMPLEX_QUESTION_KEYWORDS``."""
        dropped = {
            "explain why",
            "why do",
            "why does",
            "why is",
            "what are the implications",
            "impact of",
        }
        assert dropped.isdisjoint(_COMPLEX_QUESTION_KEYWORDS), (
            f"R84 keywords leaked back into _COMPLEX_QUESTION_KEYWORDS: "
            f"{dropped & _COMPLEX_QUESTION_KEYWORDS}"
        )

    # ── kept keywords ──

    def test_kept_keywords_still_fire(self) -> None:
        """Genuine comparison / remediation keywords still trigger
        Stage-2 polish."""
        keep_cases = [
            "Compare Article 13 and Article 50 transparency duties.",
            "What is the trade-off between Article 9 and Article 27?",
            "How do we remediate a missing post-market monitoring plan?",
        ]
        for q in keep_cases:
            query = GraphQuery(entities=["Art. 13"])
            assert _needs_stage2_enhancement(q, self._ctx(), query) is True, (
                f"Kept R84 keyword failed to fire Stage-2 on: {q!r}"
            )

    def test_kept_keywords_set_membership(self) -> None:
        """Pin the genuine synthesis markers as still present."""
        kept = {
            "compare", "comparison", "difference", "versus", " vs ", "vs.",
            "trade-off", "tradeoff", "prioritise", "prioritize", "prioritis",
            "remediat", "roadmap", "how should we", "what should we",
        }
        assert kept.issubset(_COMPLEX_QUESTION_KEYWORDS), (
            f"R84 stripped a load-bearing keyword from _COMPLEX_QUESTION_KEYWORDS: "
            f"missing {kept - _COMPLEX_QUESTION_KEYWORDS}"
        )

    # ── always-fire paths ──

    def test_multi_turn_always_fires(self) -> None:
        """Multi-turn flattened questions (with the route's
        ``"Conversation so far:"`` marker) still always polish."""
        question = (
            "Conversation so far:\n"
            "User: We are a hospital deploying a clinical decision-support AI.\n"
            "Assistant: That is high-risk under Annex III.\n"
            "\n"
            "Latest question:\nWhat next?"
        )
        query = GraphQuery(entities=["Art. 26"])
        assert _needs_stage2_enhancement(question, self._ctx(), query) is True

    def test_gap_analysis_always_fires(self) -> None:
        """``gap_analysis`` intent always triggers — short live_q, 1
        entity, no kw — but the synthesis intent overrides."""
        question = "Where are our gaps?"
        query = GraphQuery(intent="gap_analysis", entities=["Art. 13"])
        assert _needs_stage2_enhancement(question, self._ctx(), query) is True

    def test_cross_framework_always_fires(self) -> None:
        """``cross_framework`` intent always triggers."""
        question = "AI Act and GDPR?"
        query = GraphQuery(intent="cross_framework", entities=["Art. 13"])
        assert _needs_stage2_enhancement(question, self._ctx(), query) is True


# ─── R84-B — max_tokens default ────────────────────────────────────────────


class TestR84MaxTokensDefault:
    """R84 trimmed ``max_tokens`` 512 → 384 — the prompt mandates AT
    MOST 3 sentences (~150-200 tokens typical, ~280 worst-case); 384
    keeps ~80-token headroom while saving ~2-4 s p95 generation tail."""

    def test_max_tokens_default_is_384(self) -> None:
        from app.config import settings
        assert settings.graph_rag.max_tokens == 384

    def test_max_tokens_field_carries_r84_default(self) -> None:
        """Field-level default (independent of any env-loaded override)
        is 384 — guards against a future operator setting
        ``P2P_GRAPH_RAG_MAX_TOKENS`` in tests masking a code revert."""
        from app.config import GraphRAGSettings
        field = GraphRAGSettings.model_fields["max_tokens"]
        assert field.default == 384


# ─── R84-C — ContextVar memo for classify_intent ──────────────────────────


class _FakeIntent:
    """Minimal stand-in for the real Stage-0 intent object."""

    def __init__(self, label: str = "obligational") -> None:
        self.intent = label
        self.confidence = 0.9
        self.primary_anchor = ""
        self.alternate_anchors: list[str] = []


class TestR84IntentMemoCache:
    """Verify ``_classify_intent_cached`` collapses repeat calls to one
    ``classify_intent`` round-trip within a single ContextVar token.

    The route invokes ``classify_intent`` from three sites — the R84
    memo wraps each so a cold request pays ONE wrapper / Groq RTT,
    not three.
    """

    def test_three_calls_one_classify_invocation(self) -> None:
        """Three calls with the SAME question key — only one underlying
        ``classify_intent`` invocation."""
        from contextvars import copy_context

        from app.routes import regenold as regenold_module

        mock = MagicMock(return_value=_FakeIntent("article_lookup"))

        def _body() -> None:
            regenold_module._request_intent_cache.set({})
            with patch.object(regenold_module, "classify_intent", mock):
                r1 = regenold_module._classify_intent_cached("What does Article 13 say?")
                r2 = regenold_module._classify_intent_cached("What does Article 13 say?")
                r3 = regenold_module._classify_intent_cached("What does Article 13 say?")
            # All three return values are identical (same cached object).
            assert r1 is r2 is r3
            assert r1.intent == "article_lookup"
            # And the underlying classify_intent was called EXACTLY once.
            assert mock.call_count == 1, (
                f"Expected exactly 1 cold-cache RTT, got {mock.call_count}"
            )

        copy_context().run(_body)

    def test_cache_reset_restarts_count(self) -> None:
        """After resetting the per-request cache, calls fire ``classify_intent``
        again — the cache is request-scoped, not process-scoped."""
        from contextvars import copy_context

        from app.routes import regenold as regenold_module

        mock = MagicMock(return_value=_FakeIntent("definition"))

        def _body() -> None:
            with patch.object(regenold_module, "classify_intent", mock):
                # Request 1
                regenold_module._request_intent_cache.set({})
                regenold_module._classify_intent_cached("Q?")
                regenold_module._classify_intent_cached("Q?")
                assert mock.call_count == 1

                # Request 2 — fresh cache
                regenold_module._request_intent_cache.set({})
                regenold_module._classify_intent_cached("Q?")
                assert mock.call_count == 2

        copy_context().run(_body)

    def test_different_questions_get_distinct_cache_slots(self) -> None:
        """Two different question strings hit two cache slots — and so
        ``classify_intent`` is called twice. Pins the design choice that
        the route's three call sites (some pass ``live_question``, some
        pass the flattened ``question``) memo independently."""
        from contextvars import copy_context

        from app.routes import regenold as regenold_module

        mock = MagicMock(side_effect=[_FakeIntent("a"), _FakeIntent("b")])

        def _body() -> None:
            regenold_module._request_intent_cache.set({})
            with patch.object(regenold_module, "classify_intent", mock):
                r1 = regenold_module._classify_intent_cached("question one")
                r2 = regenold_module._classify_intent_cached("question two")
            assert r1.intent == "a"
            assert r2.intent == "b"
            assert mock.call_count == 2

        copy_context().run(_body)

    def test_unset_contextvar_initialises_lazily(self) -> None:
        """When called outside a request (``_request_intent_cache`` still
        at its default ``None``), the helper lazily creates a dict — no
        crash, just a non-memoised call."""
        from contextvars import copy_context

        from app.routes import regenold as regenold_module

        mock = MagicMock(return_value=_FakeIntent())

        def _body() -> None:
            # Explicitly do NOT call .set({}) — the default None must
            # trigger the lazy init.
            assert regenold_module._request_intent_cache.get() is None
            with patch.object(regenold_module, "classify_intent", mock):
                regenold_module._classify_intent_cached("anything")
            assert mock.call_count == 1
            # Second call in the same context hits the freshly-created cache.
            with patch.object(regenold_module, "classify_intent", mock):
                regenold_module._classify_intent_cached("anything")
            assert mock.call_count == 1, "lazy-init cache did not memoise"

        copy_context().run(_body)

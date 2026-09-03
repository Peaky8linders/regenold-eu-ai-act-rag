"""R360 — Stage-2 rides the cloudflared tunnel first, AWS Bedrock second, nothing else.

The operator contract is narrow and absolute: Stage-2 LLM processing runs on
the Claude Max subscription through the cloudflared tunnel
(``openai_wrapper``), falls back to **Bedrock** when that fails, and reaches
**no other provider under any circumstance**.

Why these tests assert on *counters and call recorders* rather than on the
shape of the code: this repo has already shipped a routing lever that read
correctly in the diff and made **zero calls** (R329 tried three rerank
placements; all three measured 0 and reported +0.0000, which is also what a
lever that does nothing looks like). So every test here either observes a
provider actually being dialled or observes it provably *not* being dialled.

The suite is deliberately two-sided. It pins the strict default AND pins that
``REGENOLD_STAGE2_STRICT_TRANSPORT=0`` still reaches the legacy providers —
because a guard whose "off" state behaves identically to its "on" state is the
inert-feature trap the Bedrock entitlement-fallback comment in
``app/llm/bedrock_client`` warns about: both halves must be real.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engines._graph_rag_impl import (
    _claude_max_enhance_answer,
    _openai_wrapper_complete_for_graph_rag,
)
from app.llm import stage2_policy as pol
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


@pytest.fixture(autouse=True)
def _clean_counters():
    pol.reset_transport_stats()
    yield
    pol.reset_transport_stats()


class _Exploding:
    """Any attribute access is a test failure: this provider must never be built."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, item):  # pragma: no cover - the raise IS the assertion
        raise AssertionError(
            f"OFF-CONTRACT Stage-2 call: provider {self._name!r} was dialled "
            f"(attribute {item!r}). Stage-2 must only reach the cloudflared "
            f"tunnel then Bedrock."
        )


def _seal_off_contract_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every non-contract Stage-2 transport explode if anything touches it.

    Both the getters and the ``is_*_enabled`` predicates are sealed: a hatch
    that checks ``is_groq_provider_enabled()`` and finds False would skip
    silently, so the predicates are forced **True** to arm every hatch. The
    test then proves the policy — not a missing API key — is what closes them.
    That distinction matters: the pre-R360 Groq hatch was armed by nothing more
    than a ``GROQ_API_KEY`` in the environment.
    """
    import app.llm.openai_wrapper_provider as owp

    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_gemini_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "get_groq_provider", lambda: _Exploding("groq"))
    monkeypatch.setattr(owp, "get_gemini_provider", lambda: _Exploding("gemini"))
    if hasattr(owp, "is_mistral_provider_enabled"):
        monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: True)
        monkeypatch.setattr(owp, "get_mistral_provider", lambda: _Exploding("mistral"))
    monkeypatch.setenv("GROQ_API_KEY", "armed-but-must-not-be-used")
    monkeypatch.setenv("GEMINI_API_KEY", "armed-but-must-not-be-used")


# ── the contract itself ─────────────────────────────────────────────────────

class TestPolicyContract:
    def test_strict_is_the_shipping_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_STRICT_TRANSPORT", raising=False)
        assert pol.strict_transport_enabled() is True

    def test_chain_is_tunnel_then_bedrock_in_that_order(self) -> None:
        assert pol.stage2_chain() == ("openai_wrapper", "bedrock")
        assert pol.STAGE2_PRIMARY == "openai_wrapper"
        assert pol.STAGE2_FALLBACK == "bedrock"

    @pytest.mark.parametrize("bad", ["gemini", "groq", "anthropic", "mistral", "openrouter"])
    def test_off_contract_providers_are_refused(self, bad: str) -> None:
        assert pol.is_stage2_provider_allowed(bad) is False
        assert pol.resolve_stage2_provider(bad) == "openai_wrapper"
        assert pol.transport_stats()["refused_by_provider"].get(bad) == 1

    def test_bedrock_as_env_primary_does_not_invert_the_order(self) -> None:
        """``P2P_GRAPH_RAG_PROVIDER=bedrock`` must not demote the tunnel.

        This one is not an escape but an inversion: honouring it would mean the
        Claude Max subscription is never dialled at all, which is precisely the
        arrangement the operator asked to prevent.
        """
        assert pol.resolve_stage2_provider("bedrock") == "openai_wrapper"

    def test_off_switch_restores_the_legacy_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "0")
        assert pol.strict_transport_enabled() is False
        assert pol.is_stage2_provider_allowed("groq") is True
        assert pol.resolve_stage2_provider("gemini") == "gemini"


# ── the live call paths ─────────────────────────────────────────────────────

class TestNoRequestGoesAnyOtherWay:
    def test_healthy_tunnel_is_the_only_provider_dialled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seal_off_contract_providers(monkeypatch)
        calls: list[str] = []

        class _OkWrapper:
            def complete(self, req):
                calls.append("wrapper")
                return OpenAIWrapperResponse(
                    text="Article 50 applies.", model="claude-opus-4-8",
                    finish_reason="stop", completion_tokens=12, elapsed_ms=5,
                )

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=_OkWrapper(),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert out == "Article 50 applies."
        assert calls == ["wrapper"]
        stats = pol.transport_stats()
        assert stats["primary_attempts"] == 1
        assert stats["primary_ok"] == 1
        # The fallback leg must stay untouched while the primary is healthy.
        assert stats["fallback_attempts"] == 0

    def test_failed_tunnel_falls_back_to_bedrock_and_stops_there(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seal_off_contract_providers(monkeypatch)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
        order: list[str] = []

        class _DeadWrapper:
            def complete(self, req):
                order.append("wrapper")
                return OpenAIWrapperResponse(
                    text="", model="claude-opus-4-8", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        def _fake_bedrock(**kwargs):
            order.append("bedrock")
            return "Bedrock answered under Article 50."

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_DeadWrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_fake_bedrock,
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert out == "Bedrock answered under Article 50."
        assert order == ["wrapper", "bedrock"], "tunnel must be tried BEFORE Bedrock"
        stats = pol.transport_stats()
        assert stats["primary_attempts"] == 1 and stats["primary_failed"] == 1
        assert stats["fallback_attempts"] == 1 and stats["fallback_ok"] == 1

    def test_both_legs_down_degrades_instead_of_reaching_groq(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of R360: no third leg exists.

        With the tunnel dead, Bedrock dead, and BOTH Groq and Gemini armed with
        keys and enabled predicates, the call must raise so the engine degrades
        to the deterministic Stage-1 answer — never quietly answer from Groq.
        """
        _seal_off_contract_providers(monkeypatch)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")

        class _DeadWrapper:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="m", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_DeadWrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                return_value=None,
            ),
            pytest.raises(RuntimeError, match="OpenAI wrapper failed"),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert pol.transport_stats()["refused_by_provider"].get("groq") == 1

    def test_legacy_regime_really_does_reach_groq(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the guard is load-bearing, not decorative.

        If this test passed with the strict default still on, the previous test
        would prove nothing — Groq might simply be unreachable in the harness.
        """
        monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "0")
        monkeypatch.setenv("GROQ_API_KEY", "k")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
        monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
        reached: list[str] = []

        class _DeadWrapper:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="m", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        class _Groq:
            def complete(self, req):
                reached.append("groq")
                return OpenAIWrapperResponse(
                    text="Groq answered.", model="gpt-oss-120b",
                    finish_reason="stop", completion_tokens=5, elapsed_ms=2,
                )

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_DeadWrapper(),
            ),
            patch("app.llm.openai_wrapper_provider.is_groq_provider_enabled", return_value=True),
            patch("app.llm.openai_wrapper_provider.get_groq_provider", return_value=_Groq()),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert reached == ["groq"] and out == "Groq answered."


class TestFusionPanelObeysTheContract:
    def test_strict_panel_keeps_only_the_tunnel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The default roster is sonnet + groq + mistral — two thirds off-contract."""
        from app.engines import fusion

        monkeypatch.delenv("REGENOLD_STAGE2_STRICT_TRANSPORT", raising=False)
        monkeypatch.delenv("REGENOLD_FUSION_PANEL", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "k")
        monkeypatch.setenv("MISTRAL_API_KEY", "k")
        monkeypatch.setenv("GEMINI_API_KEY", "k")

        with patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=True,
        ):
            transports = {t for _, _, t in fusion._enabled_panel()}

        assert transports <= {"wrapper"}, f"off-contract fusion transports: {transports}"

    def test_legacy_panel_still_admits_groq(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.engines import fusion

        monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "0")
        monkeypatch.delenv("REGENOLD_FUSION_PANEL", raising=False)

        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.llm.openai_wrapper_provider.is_groq_provider_enabled", return_value=True),
            patch("app.llm.openai_wrapper_provider.is_mistral_provider_enabled", return_value=True),
        ):
            transports = {t for _, _, t in fusion._enabled_panel()}

        assert "groq" in transports


class TestEnhanceAnswerPath:
    @pytest.mark.parametrize("env_provider", ["gemini", "anthropic", "bedrock", "groq"])
    def test_enhance_answer_ignores_off_contract_env_and_dials_the_tunnel(
        self, monkeypatch: pytest.MonkeyPatch, env_provider: str
    ) -> None:
        from app.engines.graph_rag import GraphContext

        _seal_off_contract_providers(monkeypatch)
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", env_provider)
        monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
        dialled: list[str] = []

        def _fake_wrapper(**kwargs):
            dialled.append("wrapper")
            return "Polished under Article 50."

        with patch(
            "app.engines._graph_rag_impl._openai_wrapper_complete_for_graph_rag",
            side_effect=_fake_wrapper,
        ):
            out = _claude_max_enhance_answer(
                question="Is a chatbot high-risk?",
                kg_answer="Deterministic draft.",
                context=GraphContext(),
            )

        assert dialled == ["wrapper"], (
            f"P2P_GRAPH_RAG_PROVIDER={env_provider} must not redirect Stage-2"
        )
        assert out == "Polished under Article 50."


class TestCacheIdentity:
    def test_flag_is_registered_in_the_engine_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AGENTS.md invariant #4 — a flag that flips output must key the cache.

        Strict-ON and strict-OFF are answered by different models, so sharing a
        cache entry would let an A/B of this flag replay the other arm's prose.
        """
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "1")
        on = _engine_cache_key("Is a chatbot high-risk?", None)
        monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "0")
        off = _engine_cache_key("Is a chatbot high-risk?", None)

        assert on != off

    def test_bedrock_wrapper_last_resort_is_in_the_engine_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exhausted-Bedrock escape hatch changes cached Stage-2 prose.

        ``wrapper_fallback_enabled`` is intentionally read fresh on each
        Bedrock completion.  Without this cache dimension, an in-process A/B
        could replay a wrapper-polished response after switching the last
        resort off (or replay the deterministic fallback after switching it
        on).  This test also pins its default-ON deny-list semantics without
        changing that default.
        """
        from app.routes.regenold import _engine_cache_key

        args = ("Is a chatbot high-risk?", None)
        monkeypatch.setenv("REGENOLD_BEDROCK_WRAPPER_FALLBACK", "0")
        off = _engine_cache_key(*args)
        monkeypatch.setenv("REGENOLD_BEDROCK_WRAPPER_FALLBACK", "1")
        on = _engine_cache_key(*args)
        monkeypatch.delenv("REGENOLD_BEDROCK_WRAPPER_FALLBACK", raising=False)
        default = _engine_cache_key(*args)

        assert off != on
        assert on == default


class TestHealthzSurfacesTheContract:
    def test_healthz_llm_reports_chain_and_counters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``llm_ok`` says the provider *can* answer; this says who *is* answering.

        An operator debugging a degraded deploy needs the second question, and
        a non-empty ``refused_by_provider`` is an alertable event in its own
        right — it means something tried to answer Stage-2 off-contract.
        """
        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        from fastapi.testclient import TestClient

        from app.main import app

        pol.refuse("groq", where="unit-test")
        body = TestClient(app).get("/healthz/llm").json()

        transport = body["stage2_transport"]
        assert transport["strict"] is True
        assert transport["chain"] == ["openai_wrapper", "bedrock"]
        assert transport["stats"]["refused_by_provider"]["groq"] == 1


class TestWireLevelRouting:
    """End-to-end through the real route — the unit tests prove the branches,
    this proves the assembled request."""

    def _seal_and_ask(self, monkeypatch: pytest.MonkeyPatch, wrapper):
        from fastapi.testclient import TestClient

        _seal_off_contract_providers(monkeypatch)
        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)

        from app.main import app

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=wrapper,
            ),
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
        ):
            return TestClient(app).post(
                "/api/v1/regenold/eu-ai-act/ask",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Does an emotion-recognition system in a workplace fall under the AI Act?",
                        }
                    ]
                },
            )

    def test_a_real_ask_only_ever_dials_the_tunnel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []

        class _Wrapper:
            def complete(self, req):
                seen.append(req.model)
                return OpenAIWrapperResponse(
                    text=(
                        "Emotion recognition in the workplace is prohibited under "
                        "Article 5. Deployers must also meet Article 26."
                    ),
                    model="claude-opus-4-8", finish_reason="stop",
                    completion_tokens=40, elapsed_ms=9,
                )

        resp = self._seal_and_ask(monkeypatch, _Wrapper())

        assert resp.status_code == 200
        assert seen, "Stage-2 never dialled the tunnel at all"
        stats = pol.transport_stats()
        assert stats["primary_attempts"] >= 1
        # The seal turns any off-contract dial into an AssertionError, and the
        # engine swallows Stage-2 exceptions — so a silent leak would show up
        # here as a refusal count or a failed primary, never as a raised test.
        assert stats["refused_by_provider"] == {} or set(
            stats["refused_by_provider"]
        ) <= {"groq", "gemini", "mistral"}, "an unexpected provider was attempted"

    def test_a_real_ask_survives_a_dead_tunnel_without_leaking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tunnel down, Bedrock unusable → deterministic answer, no third leg.

        The response must still be a well-formed in-scope answer: degrading to
        the deterministic Stage-1 draft is the designed behaviour, and it is
        strictly preferable to a fluent answer from an unmeasured model.
        """
        class _DeadWrapper:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="m", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
        monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)

        resp = self._seal_and_ask(monkeypatch, _DeadWrapper())

        assert resp.status_code == 200
        body = resp.json()
        assert body.get("answer"), "degraded to an empty answer"
        assert isinstance(body.get("references"), list)


class TestFallbackIsReachableFromEveryFailureMode:
    """R360.1 — the fallback that only fires on the failure that never happens.

    The Claude Max wrapper reports ``finish_reason="stop"`` even on a stream cut
    mid-word (R102), so a truncated Stage-2 answer is not a transport *error*.
    Before this fix the Bedrock leg lived inside the ``response.error`` branch
    alone, and the structural guard ``raise``d straight past every fallback
    block in ``_claude_max_enhance_answer``. Measured on the real code path: a
    mid-word truncation produced **zero** Bedrock calls and silently degraded to
    the deterministic draft, while the operator believed a fallback was armed.
    """

    @staticmethod
    def _run(monkeypatch, response):
        from app.engines.graph_rag import GraphContext

        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
        monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
        calls: list[str] = []

        class _Wrapper:
            def complete(self, req):
                return response

        def _bedrock(**kwargs):
            calls.append(kwargs.get("stage_name", ""))
            return "Bedrock completed the answer under Article 50."

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_Wrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock,
            ),
        ):
            out = _claude_max_enhance_answer(
                question="Is a chatbot high-risk?",
                kg_answer="deterministic draft",
                context=GraphContext(),
            )
        return out, calls

    def test_structural_truncation_reaches_bedrock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The regression that motivated R360.1 — note finish_reason='stop'."""
        out, calls = self._run(
            monkeypatch,
            OpenAIWrapperResponse(
                text="A chatbot is limited-risk under Article 50 and the provider mus",
                model="claude-opus-4-8", finish_reason="stop",
                completion_tokens=900, elapsed_ms=50,
            ),
        )
        assert len(calls) == 1, "Bedrock never fired on a mid-word truncation"
        assert out and "Bedrock completed" in out
        assert pol.transport_stats()["fallback_ok"] == 1

    def test_length_truncation_reaches_bedrock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out, calls = self._run(
            monkeypatch,
            OpenAIWrapperResponse(
                text="partial", model="claude-opus-4-8", finish_reason="length",
                completion_tokens=900, elapsed_ms=50,
            ),
        )
        assert len(calls) == 1 and out and "Bedrock completed" in out

    def test_transport_error_still_reaches_bedrock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one mode that already worked — pinned so the refactor kept it."""
        out, calls = self._run(
            monkeypatch,
            OpenAIWrapperResponse(
                text="", model="claude-opus-4-8", error="api_status_500",
                finish_reason=None, completion_tokens=0, elapsed_ms=1,
            ),
        )
        assert len(calls) == 1 and out and "Bedrock completed" in out

    def test_a_truncated_bedrock_answer_is_discarded_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Leg 2 is held to leg 1's standard.

        Shipping a mid-clause Bedrock answer would set ``stage2_landed=True``
        and let the R72 reconcile pass prune citations the cut prose never
        described — the exact harm the tunnel-side guard exists to prevent.
        """
        from app.engines.graph_rag import GraphContext

        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
        monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")

        class _Wrapper:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="m", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_Wrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                return_value="Bedrock also stopped mid-clause and the provider mus",
            ),
        ):
            out = _claude_max_enhance_answer(
                question="Is a chatbot high-risk?",
                kg_answer="deterministic draft",
                context=GraphContext(),
            )

        assert out is None, "a mid-clause Bedrock answer must not ship"


class TestStage2GateDescribesTheRealChain:
    """The gate must answer "will Stage-2 actually run?", not "what does the
    env var prefer?" — those diverge once dispatch is pinned."""

    def test_bedrock_alone_keeps_stage2_alive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tunnel down, Bedrock configured — the fallback's whole reason to exist.

        The old gate returned False here, so Stage-2 was skipped entirely and
        "Bedrock is the secondary" was untrue in precisely the situation a
        secondary is for.
        """
        from app.engines._graph_rag_impl import _stage2_provider_enabled

        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")

        with patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=False,
        ):
            assert _stage2_provider_enabled() is True

    def test_neither_leg_available_disables_stage2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.engines._graph_rag_impl import _stage2_provider_enabled

        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
        monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)

        with patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=False,
        ):
            assert _stage2_provider_enabled() is False

    def test_a_groq_key_no_longer_opens_the_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stage-2 must not be declared live on the strength of a key belonging
        to a provider it can no longer reach."""
        from app.engines._graph_rag_impl import _stage2_provider_enabled

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "k")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
        monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)

        with patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=False,
        ):
            assert _stage2_provider_enabled() is False

    def test_cli_still_wins_over_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """provider=cli is the deterministic bench contract — never Stage-2."""
        from app.engines._graph_rag_impl import _stage2_provider_enabled

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")

        with patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=True,
        ):
            assert _stage2_provider_enabled() is False


class TestAuxiliaryPassHonoursTheCliContract:
    """R360.4 — ``provider=cli`` means no LLM call, anywhere.

    Every other Stage-2 entry point gates on ``_stage2_provider_enabled``,
    which refuses ``cli``. ``_stage2_complete`` — the faithfulness verifier and
    the truncation repair — never did, so the deterministic bench still opened
    a wrapper connect per row. Free on a healthy tunnel; a dead-port timeout
    per row offline, and a violation of the documented sub-10 ms contract
    either way.
    """

    def test_cli_makes_no_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.engines._graph_rag_impl import _stage2_complete

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        dialled: list[str] = []

        with patch(
            "app.engines._graph_rag_impl._openai_wrapper_complete_for_graph_rag",
            side_effect=lambda **kw: dialled.append("wrapper") or "text",
        ):
            out = _stage2_complete(
                system="s", user="u", max_tokens=128,
                stage_name="Stage 2 (Faithfulness)",
            )

        assert out is None
        assert dialled == [], "cli must not reach any provider"

    def test_default_provider_still_reaches_the_tunnel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard must be narrow — pin that it did not disable the path."""
        from app.engines._graph_rag_impl import _stage2_complete

        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
        dialled: list[str] = []

        def _fake(**kw):
            dialled.append("wrapper")
            return "polished"

        with patch(
            "app.engines._graph_rag_impl._openai_wrapper_complete_for_graph_rag",
            side_effect=_fake,
        ):
            out = _stage2_complete(
                system="s", user="u", max_tokens=128,
                stage_name="Stage 2 (Faithfulness)",
            )

        assert out == "polished" and dialled == ["wrapper"]


class TestHealthzTellsTheTruthAboutBedrock:
    def test_bedrock_without_credentials_is_not_reported_healthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It used to fall through to the deterministic branch and answer
        ``llm_ok: true, "no LLM call required"`` — a green light meaning the
        opposite of what an operator checking the fallback would read."""
        from fastapi.testclient import TestClient

        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "bedrock")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
        monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)

        from app.main import app

        body = TestClient(app).get("/healthz/llm").json()

        assert body["provider"] == "bedrock"
        assert body["llm_ok"] is False
        assert "no credentials" in body["detail"].lower()

    def test_bedrock_with_credentials_reports_armed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fastapi.testclient import TestClient

        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "bedrock")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")

        from app.main import app

        body = TestClient(app).get("/healthz/llm").json()

        assert body["provider"] == "bedrock" and body["llm_ok"] is True


class TestDestinationIsPinnedNotJustTheProviderId:
    """R360.7 — the last real hole: the id said Claude Max, the packet did not.

    ``openai_wrapper`` only means "go through the OpenAI-compatible client".
    Where that client points is whatever ``OPENAI_API_BASE`` says. Measured on
    this repo before the fix::

        OPENAI_API_BASE=https://openrouter.ai/api/v1
          -> resolved Stage-2 base URL: https://openrouter.ai/api/v1
          -> is_stage2_provider_allowed("openai_wrapper"): True

    One env var sent every Stage-2 request to a third party while satisfying
    the provider policy and every test written for it.
    """

    @pytest.mark.parametrize(
        "base",
        [
            "https://wrapper.antifragile-ai.net/v1",
            "http://127.0.0.1:8000/v1",
            "http://localhost:8000/v1",
            "http://127.0.0.1:1/v1",  # the deterministic-bench dead port
        ],
    )
    def test_the_claude_max_path_is_allowed(self, base: str) -> None:
        assert pol.is_primary_base_url_allowed(base) is True

    @pytest.mark.parametrize(
        "base",
        [
            "https://openrouter.ai/api/v1",
            "https://api.groq.com/openai/v1",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "https://api.mistral.ai/v1",
            "https://evil-wrapper.antifragile-ai.net/v1",
        ],
    )
    def test_foreign_destinations_are_refused(self, base: str) -> None:
        assert pol.is_primary_base_url_allowed(base) is False
        assert pol.check_primary_base_url(base) is False
        assert pol.transport_stats()["refused"] == 1

    def test_a_subdomain_lookalike_does_not_slip_through(self) -> None:
        """Host equality, not substring — ``evil-wrapper.antifragile-ai.net``
        contains the allowed host as a suffix of its own name."""
        assert (
            pol.is_primary_base_url_allowed(
                "https://wrapper.antifragile-ai.net.attacker.test/v1"
            )
            is False
        )

    def test_operator_can_rename_the_tunnel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "tunnel.example.test")
        assert pol.is_primary_base_url_allowed("https://tunnel.example.test/v1") is True
        assert pol.is_primary_base_url_allowed("https://openrouter.ai/api/v1") is False

    def test_the_allowlist_cannot_be_emptied_by_accident(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A blank value falls back to the defaults rather than disabling the
        check. Turning the guard off must be a deliberate act (strict=0)."""
        for blank in ("", "   ", ",,,"):
            monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", blank)
            assert pol.allowed_primary_hosts() == pol.STAGE2_PRIMARY_HOSTS
            assert pol.is_primary_base_url_allowed("https://openrouter.ai/api/v1") is False

    def test_legacy_regime_does_not_enforce_the_destination(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "0")
        assert pol.is_primary_base_url_allowed("https://openrouter.ai/api/v1") is True

    def test_a_mispointed_base_goes_to_bedrock_not_to_the_foreign_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A mis-pointed base is a misconfiguration, not an outage — so serve
        from leg 2 rather than degrading, but never dial the foreign host."""
        monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
        dialled: list[str] = []

        class _MustNotBeCalled:
            base_url = "https://openrouter.ai/api/v1"

            def complete(self, req):  # pragma: no cover - the raise IS the assertion
                raise AssertionError("Stage-2 dialled an off-contract destination")

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_MustNotBeCalled(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=lambda **kw: dialled.append("bedrock") or "Bedrock answered.",
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert out == "Bedrock answered." and dialled == ["bedrock"]
        refusals = pol.transport_stats()["refused_by_provider"]
        assert any(k.startswith("base_url:") for k in refusals), refusals


class TestHealthzDegradesRatherThanLies:
    """R360.9 — a down tunnel is not a down service while Bedrock is armed.

    ``llm_ok`` used to go false the moment the wrapper probe failed. But
    Stage-2's contract is tunnel THEN Bedrock, so with credentials wired the
    deploy is still answering from an LLM. Reporting a flat outage sends an
    operator chasing the tunnel while requests are being served, and an uptime
    monitor alerting on ``llm_ok`` cannot distinguish "degraded but serving"
    from "serving deterministic fallback only" — which is the distinction that
    actually matters.
    """

    @staticmethod
    def _probe(monkeypatch, *, bedrock: bool) -> dict:
        from fastapi.testclient import TestClient

        from app.llm.openai_wrapper_provider import OpenAIWrapperResponse

        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        if bedrock:
            monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
            monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
        else:
            for k in (
                "AWS_BEARER_TOKEN_BEDROCK", "AWS_BEDROCK_API_KEY",
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            ):
                monkeypatch.delenv(k, raising=False)

        class _Dead:
            base_url = "https://wrapper.antifragile-ai.net/v1"

            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="m", error="api_status_500 no response",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        from app.main import app

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=_Dead(),
        ):
            return TestClient(app).get("/healthz/llm").json()

    def test_tunnel_down_bedrock_armed_is_degraded_not_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = self._probe(monkeypatch, bedrock=True)
        assert body["llm_ok"] is True
        assert "bedrock fallback" in str(body["provider"])
        assert "primary offline" in body["detail"]

    def test_tunnel_down_and_no_bedrock_is_a_real_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = self._probe(monkeypatch, bedrock=False)
        assert body["llm_ok"] is False
        assert "deterministic fallback" in body["detail"]


class TestFallbackModelIsALever:
    """R360.10 — leg 2 serves Qwen 3, not Claude, and no caller said so.

    Commit a65fa87 wired the Qwen tier on purpose, so this does not change the
    default. But it is worth being able to state and to flip: the fallback for
    a Claude Opus primary is a different model family, and an answer served
    from leg 2 is not the answer any A/B measured.
    """

    def test_default_preserves_the_qwen_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_BEDROCK_MODEL", raising=False)
        assert pol.stage2_fallback_model() == ""

    def test_override_reaches_the_bedrock_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_BEDROCK_MODEL", "eu.anthropic.claude-opus-4-6")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
        seen: dict[str, object] = {}

        class _Dead:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="m", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        def _bedrock(**kwargs):
            seen.update(kwargs)
            return "Bedrock answered under Article 50."

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_Dead(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock,
            ),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert seen.get("model_override") == "eu.anthropic.claude-opus-4-6"

    def test_default_passes_no_override_so_the_tier_logic_stands(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_BEDROCK_MODEL", raising=False)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
        seen: dict[str, object] = {}

        class _Dead:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="m", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_Dead(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                # A terminal-punctuated sentence: the R360.1 guard discards a
                # mid-clause Bedrock answer, and a bare "ok" reads as one.
                side_effect=lambda **kw: seen.update(kw) or "Bedrock answered.",
            ),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert seen.get("model_override") is None

    def test_the_fallback_model_is_in_the_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key

        monkeypatch.delenv("REGENOLD_STAGE2_BEDROCK_MODEL", raising=False)
        a = _engine_cache_key("Is a chatbot high-risk?", None)
        monkeypatch.setenv("REGENOLD_STAGE2_BEDROCK_MODEL", "eu.anthropic.claude-opus-4-6")
        b = _engine_cache_key("Is a chatbot high-risk?", None)
        monkeypatch.setenv("REGENOLD_STAGE2_BEDROCK_MODEL", "qwen.qwen3-235b-a22b-2507-v1:0")
        c = _engine_cache_key("Is a chatbot high-risk?", None)
        assert len({a, b, c}) == 3

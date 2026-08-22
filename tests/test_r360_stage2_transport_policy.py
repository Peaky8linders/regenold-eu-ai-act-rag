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

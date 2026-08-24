"""R365 — a primary provider that RAISES must fail like one that returns an error.

R361's commit message claimed "``attempts == ok + failed`` now holds on every
exit path". It did not. ``_graph_rag_impl.py`` dialled the tunnel with **no
try** around ``_wrapper_provider.complete(...)``, so an exception out of the
provider produced, measured::

    stats: {'primary_attempts': 1, 'primary_ok': 0, 'primary_failed': 0,
            'fallback_attempts': 0}
    BALANCED (attempts == ok+failed)?  False

The unbalanced counter is the visible half. The expensive half is that the
raise propagated past ``_try_bedrock_fallback`` entirely and past the duplicate
inline leg-2 block in ``_claude_max_enhance_answer`` (whose whole body sits in
one ``try``), so on the most ordinary transport failure — connection refused,
decode error, a closed client — **the Bedrock fallback was unreachable**.

That is not hypothetical: ``tests/test_r360_12_verified_bug_fixes.py`` exists
because ``int(usage.get(...))`` DID raise out of this very call. The provider
only catches ``httpx.HTTPError`` (``openai_wrapper_provider.py:548``); decode
errors, ``httpx.InvalidURL`` and closed-client ``RuntimeError``\\ s escape.

Every assertion here reads ``stage2_policy.transport_stats()`` or a call
recorder — never the shape of the code. That is the R329/R331 discipline: three
rerank placements once read correctly in the diff and made zero calls. The
suite is two-sided: it pins that a raising primary now reaches leg 2 AND that a
HEALTHY primary still never touches it, because a guard whose off state behaves
like its on state is the inert-feature trap.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
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


@pytest.fixture(autouse=True)
def _arm_bedrock(monkeypatch: pytest.MonkeyPatch):
    """Credentials present, so "leg 2 was skipped" can never be blamed on them.

    ``is_bedrock_provider_enabled()`` is a pure env check, so arming it here
    means every negative result below is the ROUTING, not a missing key.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")


class _Exploding:
    """Any attribute access is a test failure: this provider must never be built."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, item):  # pragma: no cover — the raise IS the assertion
        raise AssertionError(
            f"OFF-CONTRACT Stage-2 call: provider {self._name!r} was dialled "
            f"(attribute {item!r}) after the primary RAISED."
        )


def _seal_off_contract_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Arm every legacy hatch so the policy — not a missing key — closes them."""
    import app.llm.openai_wrapper_provider as owp

    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_gemini_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "get_groq_provider", lambda: _Exploding("groq"))
    monkeypatch.setattr(owp, "get_gemini_provider", lambda: _Exploding("gemini"))
    monkeypatch.setenv("GROQ_API_KEY", "armed-but-must-not-be-used")
    monkeypatch.setenv("GEMINI_API_KEY", "armed-but-must-not-be-used")


class _RaisingWrapper:
    """A tunnel whose ``complete`` throws instead of returning ``.error``.

    ``exc`` defaults to the closed-client ``RuntimeError`` httpx raises when the
    pooled client has been shut down under a live worker — one of the escapes
    the provider's ``except httpx.HTTPError`` does not cover.
    """

    def __init__(self, exc: BaseException | None = None) -> None:
        self.exc = exc or RuntimeError(
            "Cannot send a request, as the client has been closed."
        )
        self.calls = 0

    def complete(self, req):
        self.calls += 1
        raise self.exc


def _bedrock_recorder(calls: list[str], answer: str | None):
    def _fake(**kwargs):
        calls.append(kwargs.get("stage_name") or "?")
        return answer

    return _fake


# ── the counters must balance again ─────────────────────────────────────────


class TestARaisingPrimaryIsCountedAsAFailure:
    @pytest.mark.parametrize(
        "exc",
        [
            # The R360.12 shape: ``int(None)`` out of the usage block, which
            # sits OUTSIDE the provider's guarding try.
            TypeError("int() argument must be a string ... not 'NoneType'"),
            # A closed pooled client under a live worker.
            RuntimeError("Cannot send a request, as the client has been closed."),
            # Not an ``httpx.HTTPError`` subclass, so the provider re-raises it.
            httpx.InvalidURL("Invalid URL component 'scheme'"),
        ],
        ids=["decode_typeerror", "closed_client", "invalid_url"],
    )
    def test_attempts_equals_ok_plus_failed(
        self, monkeypatch: pytest.MonkeyPatch, exc: BaseException
    ) -> None:
        """The invariant /healthz/llm is read against, on the raising path."""
        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_RaisingWrapper(exc),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "Bedrock answered under Article 50."),
            ),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        stats = pol.transport_stats()
        assert stats["primary_attempts"] == 1
        assert stats["primary_failed"] == 1, (
            f"a RAISING primary was counted as neither ok nor failed: {stats}"
        )
        assert (
            stats["primary_attempts"]
            == stats["primary_ok"] + stats["primary_failed"]
        ), f"counters do not reconcile: {stats}"

    def test_the_fallback_counters_balance_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_RaisingWrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "Bedrock answered under Article 50."),
            ),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        stats = pol.transport_stats()
        assert (
            stats["fallback_attempts"]
            == stats["fallback_ok"] + stats["fallback_failed"]
        ), f"counters do not reconcile: {stats}"


# ── leg 2 must actually be reachable ────────────────────────────────────────


class TestARaisingPrimaryReachesBedrock:
    def test_the_bedrock_leg_is_dialled_and_its_answer_is_served(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The expensive half of C-1: connection refused ⇒ no fallback at all."""
        _seal_off_contract_providers(monkeypatch)
        bedrock: list[str] = []
        wrapper = _RaisingWrapper()
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=wrapper,
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "Bedrock answered under Article 50."),
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert wrapper.calls == 1, "the tunnel must still be tried FIRST"
        stats = pol.transport_stats()
        assert stats["fallback_attempts"] >= 1, (
            f"the Bedrock leg was never reached after a raising primary: {stats}"
        )
        assert stats["fallback_ok"] == 1
        assert bedrock == ["Stage 2 (Polishing)"]
        assert out == "Bedrock answered under Article 50."

    def test_the_real_caller_ships_the_bedrock_answer_instead_of_degrading(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end through ``_claude_max_enhance_answer``.

        Its whole body is one ``try``/``except`` returning ``None``, so before
        R365 the raise unwound straight to that handler — skipping the inline
        leg-2 block as well — and the deploy silently served the deterministic
        Stage-1 draft while the operator believed a fallback was in place.
        """
        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_RaisingWrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(
                    bedrock,
                    "Article 50 applies to this chatbot. The provider must "
                    "disclose that the user is interacting with an AI system.",
                ),
            ),
        ):
            out = _claude_max_enhance_answer(
                question="Does Article 50 apply to a chatbot?",
                kg_answer="Article 50 applies.",
            )

        stats = pol.transport_stats()
        assert stats["fallback_attempts"] >= 1, (
            f"the Bedrock leg was never reached from the real caller: {stats}"
        )
        assert out is not None, "Stage-2 degraded to deterministic with leg 2 armed"
        assert "Article 50" in out


class TestNothingIsSwallowedWhenThereIsNoFallback:
    def test_the_original_exception_still_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail-soft is the CALLER's job; this function must not invent success.

        With Bedrock unavailable the raise has to keep travelling so
        ``_claude_max_enhance_answer`` degrades to the deterministic Stage-1
        answer — the pre-R365 caller-visible behaviour, unchanged.
        """
        _seal_off_contract_providers(monkeypatch)
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)

        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_RaisingWrapper(),
            ),
            patch(
                "app.llm.bedrock_client.is_bedrock_provider_enabled",
                return_value=False,
            ),
            pytest.raises(RuntimeError, match="client has been closed"),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        stats = pol.transport_stats()
        # Still counted, and still balanced, even with nowhere to fall back to.
        assert stats["primary_failed"] == 1
        assert (
            stats["primary_attempts"]
            == stats["primary_ok"] + stats["primary_failed"]
        ), f"counters do not reconcile: {stats}"
        assert stats["fallback_attempts"] == 0

    def test_a_raising_primary_does_not_open_the_groq_hatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R360's contract holds on the new edge: still exactly two legs.

        ``_Exploding`` turns any Groq/Gemini attribute touch into a failure, and
        both predicates are forced True so the hatches are armed.
        """
        _seal_off_contract_providers(monkeypatch)
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_RaisingWrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                return_value=None,
            ),
            pytest.raises(RuntimeError, match="client has been closed"),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        stats = pol.transport_stats()
        assert stats["primary_failed"] == 1
        assert stats["fallback_attempts"] == 1 and stats["fallback_failed"] == 1


# ── the other side: the guard must NOT fire when it should not ──────────────


class TestTheGuardDoesNotFireOnAHealthyOrMerelyErroringPrimary:
    def test_a_healthy_primary_never_dials_the_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _OkWrapper:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="Article 50 requires disclosure.",
                    model="claude-opus-4-8", error=None,
                    finish_reason="stop", completion_tokens=7, elapsed_ms=1,
                )

        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_OkWrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "must not be used"),
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert out == "Article 50 requires disclosure."
        stats = pol.transport_stats()
        assert stats["primary_ok"] == 1 and stats["primary_failed"] == 0
        assert stats["fallback_attempts"] == 0 and bedrock == []

    def test_an_error_RESPONSE_still_takes_the_pre_existing_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R365 must not change the branch R360 already covers.

        A provider that RETURNS ``.error`` is the old, already-handled failure;
        it must reach Bedrock exactly once, through the same recorder, with the
        same counters — no double-count from the new ``except``.
        """
        class _DeadWrapper:
            def complete(self, req):
                return OpenAIWrapperResponse(
                    text="", model="claude-opus-4-8", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )

        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_DeadWrapper(),
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "Bedrock answered under Article 50."),
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert out == "Bedrock answered under Article 50."
        stats = pol.transport_stats()
        assert stats["primary_attempts"] == 1 and stats["primary_failed"] == 1
        assert stats["fallback_attempts"] == 1 and stats["fallback_ok"] == 1
        assert len(bedrock) == 1, "leg 2 was dialled twice for one failure"

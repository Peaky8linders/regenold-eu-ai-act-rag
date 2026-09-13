"""R418 — every ``_build_question_from_history`` return path applies the caps.

Two specialist review agents found this independently on the same branch, which
is why it is pinned twice (unit + route): the R372 challenge-recovery branch
returned early, so it skipped BOTH bounds the shared tail applies — the
``_max_question_chars()`` clip on the prompt and the 1 000-char clip on
``system_context``.

The second one is not cosmetic. The route hands ``system_context`` to
``GraphRAGRequest(system_description=...)``, whose Pydantic bound is
``max_length=1_000``. An uncapped value raises ``ValidationError`` inside the
handler, and the only ``ValidationError`` handler in the module covers
``RegenoldAskRequest`` — the inbound body — so the outbound construction escaped
to a bare HTTP 500. A partner sending a >1 000-char system prompt got a 500 on
every short pushback turn, with no test able to see it because the covering test
passes no system message at all.

The fix routes every return through :func:`_cap_history_result`. These tests
assert the OBSERVABLE (status code + the payload the engine actually receives),
not that the helper is called.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.models import CitationNode, GraphRAGResponse
from app.routes.regenold import _build_question_from_history, _cap_history_result


class _Msg:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


_PUSHBACK = (
    "I don't think this is correct. Maybe your answer contains hallucinations.\n\n"
    "(Briefly reason about whether something might indeed be incorrect, using the "
    "reasoning field. Then, provide a clear answer with the same format as before, "
    "as if I had just asked the same question anew: without mentioning the previous "
    "answer or the pushback.)"
)
_ROOT_Q = (
    "What are the transparency obligations for general-purpose AI model providers "
    "under Article 53?"
)


# ── the helper itself ───────────────────────────────────────────────────────


class TestTheCapsHelper:
    def test_a_long_system_description_keeps_its_head(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REGENOLD_MAX_QUESTION_CHARS", raising=False)
        desc = "We deploy an AI system that screens job applicants. " + "x" * 5_000
        _, capped, _ = _cap_history_result("q", desc, "q")
        assert len(capped) == 1000
        assert capped.startswith("We deploy an AI system that screens job applicants.")

    def test_the_live_question_marker_survives_a_prompt_overflow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Left-truncation, not right: the detectors key on the marker."""
        monkeypatch.setenv("REGENOLD_MAX_QUESTION_CHARS", "2000")
        history = "User: " + "a" * 5_000 + "\nAssistant: " + "b" * 5_000
        question = (
            f"Conversation so far:\n{history}\n\n"
            f"Latest question:\n{_ROOT_Q}"
        )
        capped, _, _ = _cap_history_result(question, None, _ROOT_Q)
        assert len(capped) <= 2000
        assert "Latest question:\n" in capped, (
            "the live-question marker must survive, or the classification / "
            "role-duty / Stage-2-gate detectors test the whole flattened prompt"
        )
        assert _ROOT_Q in capped


# ── the recovered challenge turn goes through them ──────────────────────────


class TestTheChallengeRecoveryIsCapped:
    def _messages(self, system: str | None = None) -> list[_Msg]:
        msgs: list[_Msg] = []
        if system is not None:
            msgs.append(_Msg("system", system))
        msgs.append(_Msg("user", _ROOT_Q))
        msgs.append(_Msg("assistant", "Under Article 53(1), providers must…"))
        msgs.append(_Msg("user", _PUSHBACK))
        return msgs

    def test_the_recovered_shape_survives_the_fall_through(self) -> None:
        """The fall-through must not lose the recovery (the ``elif`` guard)."""
        res = _build_question_from_history(self._messages())
        assert res.resolved_question == _ROOT_Q
        assert res.self_contained_focus is True
        assert "Target inquiry to answer:" in res[0]

    def test_a_long_system_description_is_capped_on_this_path_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REGENOLD_MAX_QUESTION_CHARS", raising=False)
        res = _build_question_from_history(self._messages(system="S" * 4_000))
        assert res[1] is not None and len(res[1]) == 1000, (
            "an uncapped system_context here reaches GraphRAGRequest's "
            "max_length=1000 bound and 500s the request"
        )

    def test_the_prompt_is_capped_on_this_path_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_MAX_QUESTION_CHARS", "2000")
        long_msgs = [
            _Msg("user", _ROOT_Q),
            _Msg("assistant", "A" * 8_000),
            _Msg("user", "B" * 8_000),
            _Msg("assistant", "C" * 8_000),
            _Msg("user", _PUSHBACK),
        ]
        res = _build_question_from_history(long_msgs)
        assert len(res[0]) <= 2000, (
            "the recovery early return used to bypass _max_question_chars() "
            "entirely, so a hostile or long payload reached the engine unbounded"
        )


# ── and the wire: no 500, capped payload ────────────────────────────────────


def _headers() -> dict[str, str]:
    return {"X-Regenold-Api-Key": "regenold-test-key"}


def _engine_response() -> GraphRAGResponse:
    return GraphRAGResponse(
        answer=(
            "Article 53 requires GPAI providers to draw up technical "
            "documentation and publish a summary of training content."
        ),
        citations=[
            CitationNode(
                node_type="Article",
                node_id="art-53",
                text="Obligations for providers of general-purpose AI models.",
                article_ref="Art. 53",
            ),
        ],
        confidence=0.7,
        graph_stats={
            "nodes_traversed": 2,
            "stage2_call_failed": False,
            "stage2_landed": True,
            "stage2_served_by": "primary",
        },
    )


@pytest.fixture
def _partner_key():
    settings.regenold.api_key = SecretStr("regenold-test-key")
    from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415

    with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
        _ENGINE_CACHE._data.clear()  # type: ignore[attr-defined]
    yield


class TestTheRouteSurvivesALongSystemPromptOnAPushbackTurn:
    def test_a_1500_char_system_prompt_is_answered_not_500d(
        self, _partner_key
    ) -> None:
        """The pre-R418 shape: ValidationError inside the handler ⇒ HTTP 500."""
        seen: list[object] = []

        def _capture(req):
            seen.append(req)
            return _engine_response()

        body = [
            {"role": "system", "content": "Deployer context. " + "d" * 1_500},
            {"role": "user", "content": _ROOT_Q},
            {"role": "assistant", "content": "Under Article 53(1), providers must…"},
            {"role": "user", "content": _PUSHBACK},
        ]
        with patch("app.routes.regenold.ask_compliance_question", side_effect=_capture):
            r = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=body,
            )

        assert r.status_code == 200, (
            f"a partner system prompt over 1000 chars must not 500 the request; "
            f"got {r.status_code}: {r.text[:300]}"
        )
        # The engine call itself is environment-dependent — the Lexy safety gate
        # fails soft to a decline in-process, so a refusal here is legitimate.
        # What must hold whenever the engine IS dialled is the bound, because an
        # uncapped value raises ValidationError inside the handler (the 500).
        for req in seen:
            system_description = getattr(req, "system_description", None)
            assert system_description is None or len(system_description) <= 1000, (
                "GraphRAGRequest.system_description is bounded at 1000 chars; a "
                "longer value raises ValidationError inside the handler"
            )

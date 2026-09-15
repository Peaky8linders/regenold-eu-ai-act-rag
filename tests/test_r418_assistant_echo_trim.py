"""R418 — our own answer, echoed back, must not 422 the turn that replays it.

``RegenoldChatMessage.content`` is capped at ``MAX_MESSAGE_CONTENT_CHARS`` (4 000)
as a P0 injection/DoS guard, enforced by Pydantic before any route code runs. The
guard is aimed at input a caller CHOOSES to send; an assistant turn is not input —
it is our previous answer, replayed by the caller exactly as the official hard-mode
protocol does.

Measured consequence of getting this wrong (live production, R418 sample): a
4 011-char answer made its own pushback 422 ``regenold_invalid_input``; the failed
turn froze the rolling history, so the next 16 multi-turn rows 422d too and
returned an empty answer, scoring zero on every benchmark axis.

These tests pin both halves: the echo is trimmed so the request is served, and the
guard that matters — over-cap user / system content — is untouched.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.integrations.regenold.models import (
    MAX_MESSAGE_CONTENT_CHARS,
    RegenoldAskRequest,
    RegenoldChatMessage,
)
from app.routes.regenold import _ECHO_TRIM_MARK, _trim_assistant_echoes

CAP = MAX_MESSAGE_CONTENT_CHARS
QUESTION = "Does Article 6(2) make an AI system high-risk?"


def _messages(assistant: str) -> list[dict]:
    return [
        {"role": "user", "content": QUESTION},
        {"role": "assistant", "content": assistant},
        {"role": "user", "content": "I don't think this is correct. Let's try again: " + QUESTION},
    ]


def test_the_cap_the_route_trims_to_is_the_cap_the_model_enforces() -> None:
    """One number, or the trim silently stops protecting the request."""
    field = RegenoldChatMessage.model_fields["content"]
    assert CAP == 4_000, "the P0 guard's value changed; re-measure the trim"
    assert field.metadata, "max_length metadata missing"
    assert any(getattr(m, "max_length", None) == CAP for m in field.metadata)


def test_one_char_over_the_cap_is_exactly_the_case_that_used_to_fail() -> None:
    """The regression itself: 4 001 chars must be served, not 422d."""
    raw = _messages("x" * (CAP + 1))
    with pytest.raises(ValidationError):
        RegenoldAskRequest.model_validate({"messages": raw})  # pre-fix behaviour
    trimmed = _trim_assistant_echoes(raw)
    RegenoldAskRequest.model_validate({"messages": trimmed})  # post-fix: valid


def test_trimming_keeps_the_head_and_marks_the_cut() -> None:
    """The head carries the verdict and the lead citations; the tail is dropped."""
    head = "Yes. Under Article 6(2), Annex III point 3(c) applies. "
    raw = _messages(head + "z" * (CAP * 2))
    out = _trim_assistant_echoes(raw)[1]["content"]
    assert len(out) <= CAP
    assert out.startswith(head)
    assert out.endswith(_ECHO_TRIM_MARK)


def test_at_or_under_the_cap_is_left_byte_identical() -> None:
    for n in (0, 100, CAP):
        raw = _messages("a" * n)
        assert _trim_assistant_echoes(raw) == raw


def test_over_cap_user_and_system_content_still_raises() -> None:
    """The guard's real target: new content the caller chose to send."""
    for role in ("user", "system"):
        raw = [{"role": role, "content": "y" * (CAP + 1)}]
        assert _trim_assistant_echoes(raw) == raw, f"{role} must not be trimmed"
        with pytest.raises(ValidationError):
            RegenoldAskRequest.model_validate({"messages": raw})


def test_non_string_and_non_dict_entries_pass_through_untouched() -> None:
    """Shape errors stay Pydantic's job; this helper only trims assistant echoes."""
    raw: list = [
        {"role": "assistant", "content": None},
        {"role": "assistant", "content": 123},
        "not-a-message",
        {"role": "assistant"},
    ]
    assert _trim_assistant_echoes(raw) == raw


def test_the_wire_serves_an_over_cap_echo_instead_of_422ing() -> None:
    """End-to-end through the real route: the 422 is what the caller saw.

    ``tests/conftest.py`` points the Claude-Max wrapper at an unreachable port,
    so this exercises the route's validation + deterministic path with no
    network.
    """
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.config import settings
    from app.main import app

    settings.regenold.api_key = SecretStr("regenold-test-key")
    over_cap = (
        "Yes. Under Article 6(2), Annex III point 3(c) makes this high-risk. "
        + "The provider must also comply with Articles 9 to 15. " * 120
    )
    assert len(over_cap) > CAP
    res = TestClient(app).post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(over_cap),
    )
    assert res.status_code != 422, res.text
    assert res.status_code == 200, res.text


def test_the_caller_s_list_and_dicts_are_not_mutated() -> None:
    """A mutated request body would corrupt every later reader of ``raw_messages``."""
    body = "q" * (CAP + 50)
    raw = _messages(body)
    _trim_assistant_echoes(raw)
    assert raw[1]["content"] == body and len(raw) == 3

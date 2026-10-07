"""R460 — ``REGENOLD_STAGE2_WRAPPER_TIMEOUT_S`` must be VALIDATED, not trusted.

The knob was parsed with a bare ``float()`` and handed to httpx verbatim. ``0``,
a negative, ``nan``, ``inf`` and ``1e9`` all reached ``httpx.Timeout`` and made
every primary dial RAISE (or, where the platform accepts it, left the read
effectively unbounded). A raise is a primary failure, so a single mistyped knob
silently moved all Stage-2 traffic to the Bedrock leg (a different model family)
while the tunnel was perfectly healthy.

Every assertion reads the ``OpenAIWrapperRequest`` the engine actually
dispatched, a transport counter, or a real loopback round trip: never source text.
"""

from __future__ import annotations

import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

import app.llm.openai_wrapper_provider as wp
from app.engines._graph_rag_impl import (
    _openai_wrapper_complete_for_graph_rag,
    _stage2_wrapper_timeout_s,
)
from app.llm import stage2_policy as pol
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse

_KNOB = "REGENOLD_STAGE2_WRAPPER_TIMEOUT_S"
_BODY = "Article 50(1) requires providers to disclose AI interaction to natural persons."


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(_KNOB, raising=False)
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("REGENOLD_STAGE2_DEGENERATE_RETRY", raising=False)
    pol.reset_transport_stats()
    yield
    pol.reset_transport_stats()


class _Wrapper:
    """A tunnel that replays a script and records every request it was dialled with."""

    base_url = "https://wrapper.antifragile-ai.net/v1"

    def __init__(self, *responses: OpenAIWrapperResponse) -> None:
        self.responses = list(responses)
        self.requests: list = []

    def complete(self, req):
        self.requests.append(req)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def _good() -> OpenAIWrapperResponse:
    return OpenAIWrapperResponse(
        text=_BODY, model="claude-opus-5-5", completion_tokens=30, prompt_tokens=100
    )


def _blip() -> OpenAIWrapperResponse:
    return OpenAIWrapperResponse(
        text=".", model="claude-opus-5-5", completion_tokens=1, prompt_tokens=100
    )


def _polish(wrapper: _Wrapper) -> str | None:
    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=wrapper,
    ):
        return _openai_wrapper_complete_for_graph_rag(
            system="s", user="question", max_tokens=200, temperature=0.0,
            stage_name="Stage 2 (Polishing)", history_turn_count=0,
        )


def _dispatched_timeout(monkeypatch: pytest.MonkeyPatch, raw: str | None) -> float | None:
    if raw is not None:
        monkeypatch.setenv(_KNOB, raw)
    wrapper = _Wrapper(_good())
    assert _polish(wrapper) == _BODY
    assert len(wrapper.requests) == 1
    return wrapper.requests[0].timeout_seconds


# ── the dispatched deadline ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad", ["0", "0.0", "-1", "-5", "nan", "inf", "-inf", "1e999", "abc", "", "  "]
)
def test_an_unusable_knob_dispatches_the_shipped_default(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    assert _dispatched_timeout(monkeypatch, bad) == 150.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", 5.0), ("4.9", 5.0), ("5", 5.0), ("90", 90.0), ("240", 240.0),
     ("600", 600.0), ("601", 600.0), ("1e9", 600.0)],
)
def test_a_finite_knob_is_clamped_not_rejected(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
) -> None:
    got = _dispatched_timeout(monkeypatch, raw)
    assert got is not None and math.isfinite(got) and got == expected


def test_unset_keeps_the_shipped_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _dispatched_timeout(monkeypatch, None) == 150.0


def test_the_helper_is_a_fresh_read_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The knob is cache-keyed and A/B harnesses flip it in-process."""
    monkeypatch.setenv(_KNOB, "90")
    assert _stage2_wrapper_timeout_s() == 90.0
    monkeypatch.setenv(_KNOB, "120")
    assert _stage2_wrapper_timeout_s() == 120.0
    monkeypatch.delenv(_KNOB)
    assert _stage2_wrapper_timeout_s() == 150.0


def test_the_degenerate_retry_dials_with_the_validated_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The R417 retry reuses the same deadline, so a bad knob cannot reach it either."""
    monkeypatch.setenv(_KNOB, "nan")
    wrapper = _Wrapper(_blip(), _good())
    assert _polish(wrapper) == _BODY
    assert [r.timeout_seconds for r in wrapper.requests] == [150.0, 150.0]


def test_an_unusable_knob_is_not_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(_KNOB, "-5")
    with caplog.at_level("WARNING"):
        assert _stage2_wrapper_timeout_s() == 150.0
    assert any("stage2_timeout_env_unusable" in r.getMessage() for r in caplog.records)
    caplog.clear()
    monkeypatch.setenv(_KNOB, "1e9")
    with caplog.at_level("WARNING"):
        assert _stage2_wrapper_timeout_s() == 600.0
    assert any("stage2_timeout_env_clamped" in r.getMessage() for r in caplog.records)
    caplog.clear()
    monkeypatch.setenv(_KNOB, "90")
    with caplog.at_level("WARNING"):
        assert _stage2_wrapper_timeout_s() == 90.0
    assert not caplog.records, "a usable value must not warn"


# ── the consequence: a healthy tunnel must stay the serving leg ─────────────


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D102
        pass

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({
            "choices": [{"message": {"content": _BODY}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 30},
            "model": "claude-opus-5-5",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def healthy_tunnel(monkeypatch: pytest.MonkeyPatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_BASE", f"http://127.0.0.1:{server.server_address[1]}/v1")
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "127.0.0.1")
    monkeypatch.setattr(wp, "_SINGLETON", None)  # a provider built against THIS server
    yield server
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "1e9"])
def test_a_bad_knob_no_longer_moves_a_healthy_tunnel_onto_bedrock(
    monkeypatch: pytest.MonkeyPatch, healthy_tunnel, bad: str
) -> None:
    monkeypatch.setenv(_KNOB, bad)
    bedrock_calls: list[str] = []

    def _fake_bedrock(**kwargs):
        bedrock_calls.append(kwargs.get("stage_name", "?"))
        return "BEDROCK LEG: Article 50(1) requires disclosure."

    with (
        patch("app.engines._graph_rag_impl._bedrock_complete_for_graph_rag", _fake_bedrock),
        patch("app.llm.bedrock_client.is_bedrock_provider_enabled", return_value=True),
    ):
        t0 = time.perf_counter()
        out = _openai_wrapper_complete_for_graph_rag(
            system="s", user="question", max_tokens=200, temperature=0.0,
            stage_name="Stage 2 (Polishing)", history_turn_count=0,
        )
    assert time.perf_counter() - t0 < 5.0
    stats = pol.transport_stats()
    assert out == _BODY, f"the tunnel's own answer must ship, got {out!r}"
    assert bedrock_calls == [], "a healthy tunnel must not cost a Bedrock dial"
    assert stats["primary_ok"] == 1 and stats["primary_failed"] == 0, stats
    assert stats["primary_attempts"] == stats["primary_ok"] + stats["primary_failed"]

"""R460 — WHICH deadline governs a wrapper dial, stated and pinned.

R460 gave the Stage-2 primary a 150 s read deadline (``REGENOLD_STAGE2_WRAPPER_TIMEOUT_S``)
because the provider singleton's 60 s default was cutting slow-but-healthy Opus /
Sonnet generations. It did that by passing ``timeout_seconds`` on EVERY wrapper
dial, which had two side effects nobody decided on:

* an operator-set ``OPENAI_TIMEOUT_SECONDS`` was silently replaced by 150 s, and
* the three auxiliary repair passes (tail / completeness, all funnelled through
  ``_stage2_complete``), which had always run on the provider's own per-call budget,
  were silently stretched to 150 s as well.

The precedence is now explicit. For the Stage-2 ANSWER dial (the polish and its
R417 degenerate-completion retry): the dedicated knob, then an operator-set
``OPENAI_TIMEOUT_SECONDS``, then 150 s, first USABLE value wins. The auxiliary
passes send no explicit budget at all.

Assertions read the dispatched request, the call count, or a real loopback round
trip, never source text.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

import app.llm.openai_wrapper_provider as wp
from app.engines._graph_rag_impl import (
    _openai_wrapper_complete_for_graph_rag,
    _stage2_complete,
)
from app.llm import stage2_policy as pol
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse

_KNOB = "REGENOLD_STAGE2_WRAPPER_TIMEOUT_S"
_OPERATOR = "OPENAI_TIMEOUT_SECONDS"
_BODY = "Article 14 requires human oversight so that natural persons can intervene."


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch):
    for name in (_KNOB, _OPERATOR, "REGENOLD_STAGE2_DEGENERATE_RETRY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    pol.reset_transport_stats()
    yield
    pol.reset_transport_stats()


class _Wrapper:
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


# ── the answer dial: explicit precedence ────────────────────────────────────


@pytest.mark.parametrize(
    ("knob", "operator", "expected"),
    [
        (None, None, 150.0),          # neither set: the R460 default
        ("90", None, 90.0),           # the dedicated knob
        ("90", "8", 90.0),            # ... beats the provider-wide budget
        (None, "240", 240.0),         # an operator-set budget is NOT replaced by 150
        (None, "90", 90.0),           # ... even when it is SHORTER than 150
        ("0", "240", 240.0),          # an unusable knob falls through to the operator's
        ("abc", "nan", 150.0),        # nothing usable anywhere: the default
        (None, "-3", 150.0),
        (None, "1e9", 600.0),         # bounded, same as the knob
    ],
)
def test_the_answer_dial_precedence(
    monkeypatch: pytest.MonkeyPatch, knob, operator, expected
) -> None:
    if knob is not None:
        monkeypatch.setenv(_KNOB, knob)
    if operator is not None:
        monkeypatch.setenv(_OPERATOR, operator)
    wrapper = _Wrapper(_good())
    assert _polish(wrapper) == _BODY
    assert [r.timeout_seconds for r in wrapper.requests] == [expected]


def test_the_retry_dial_carries_the_same_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_KNOB, "90")
    monkeypatch.setenv(_OPERATOR, "8")
    wrapper = _Wrapper(_blip(), _good())
    assert _polish(wrapper) == _BODY
    assert [r.timeout_seconds for r in wrapper.requests] == [90.0, 90.0]


def test_a_timeout_is_never_retried_on_the_primary_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a fast degenerate 200 earns the retry; a read timeout is one dial then leg 2."""
    monkeypatch.setenv(_KNOB, "90")
    wrapper = _Wrapper(
        OpenAIWrapperResponse(error="network_error: The read operation timed out")
    )
    with (
        patch("app.llm.bedrock_client.is_bedrock_provider_enabled", return_value=False),
        pytest.raises(RuntimeError, match="OpenAI wrapper failed"),
    ):
        _polish(wrapper)
    assert len(wrapper.requests) == 1
    stats = pol.transport_stats()
    assert stats["primary_attempts"] == stats["primary_ok"] + stats["primary_failed"] == 1


# ── the auxiliary passes keep their own budget ──────────────────────────────


@pytest.mark.parametrize(
    "stage_name", ["Stage 2 (Tail Repair)", "Stage 2 (Completeness Repair)"]
)
def test_the_auxiliary_repairs_send_no_explicit_budget(
    monkeypatch: pytest.MonkeyPatch, stage_name: str
) -> None:
    """``None`` is the provider's own per-call default, so R460's deadline (and the
    operator's knob) cannot stretch a repair pass. The polish above still gets it."""
    monkeypatch.setenv(_KNOB, "90")
    monkeypatch.setenv(_OPERATOR, "240")
    wrapper = _Wrapper(_good())
    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=wrapper,
    ):
        out = _stage2_complete(
            system="s", user="u", max_tokens=512, temperature=0.0,
            complex_question=False, stage_name=stage_name,
        )
    assert out == _BODY
    assert len(wrapper.requests) == 1
    assert wrapper.requests[0].timeout_seconds is None


# ── over a real socket: the two budgets really are different budgets ───────


class _SlowHandler(BaseHTTPRequestHandler):
    stall_s = 2.5

    def log_message(self, *args) -> None:  # noqa: D102
        pass

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        time.sleep(self.stall_s)
        body = json.dumps({
            "choices": [{"message": {"content": _BODY}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 30},
            "model": "claude-opus-5-5",
        }).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:  # the client gave up first, which is the point
            pass


def test_a_slow_answer_survives_but_a_slow_repair_is_cut_at_its_own_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("OPENAI_API_BASE", f"http://127.0.0.1:{server.server_address[1]}/v1")
        monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "127.0.0.1")
        monkeypatch.setenv(_OPERATOR, "1")      # the provider's own default: 1 s
        monkeypatch.setenv(_KNOB, "5")          # the answer deadline: 5 s
        monkeypatch.setattr(wp, "_SINGLETON", None)
        wp.get_openai_wrapper_provider()        # build the client outside the timed region

        with patch("app.llm.bedrock_client.is_bedrock_provider_enabled", return_value=False):
            # The repair pass runs on the provider default (1 s): the 2.5 s server is cut.
            t0 = time.perf_counter()
            repaired = _stage2_complete(
                system="s", user="u", max_tokens=64, temperature=0.0,
                complex_question=False, stage_name="Stage 2 (Tail Repair)",
            )
            repair_s = time.perf_counter() - t0
            assert repaired is None
            assert repair_s < 2.2, f"the repair pass should be cut near 1 s, took {repair_s:.2f}"

            # The answer dial gets the 5 s deadline (and not the 1 s OPENAI_TIMEOUT_SECONDS).
            t0 = time.perf_counter()
            answer = _openai_wrapper_complete_for_graph_rag(
                system="s", user="question", max_tokens=200, temperature=0.0,
                stage_name="Stage 2 (Polishing)", history_turn_count=0,
            )
            answer_s = time.perf_counter() - t0
        assert answer == _BODY
        assert 2.0 < answer_s < 4.5, f"the polish should wait out the stall, took {answer_s:.2f}"
    finally:
        server.shutdown()
        server.server_close()


# ── the provider's own default must be sound, because the repairs now ride on it ──


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 60.0), ("", 60.0), ("  ", 60.0),
        ("abc", 60.0), ("0", 60.0), ("-3", 60.0), ("nan", 60.0), ("inf", 60.0),
        ("2.5", 2.5), ("15", 15.0), ("600", 600.0), ("1e9", 600.0),
    ],
)
def test_the_provider_default_budget_is_validated(
    monkeypatch: pytest.MonkeyPatch, raw, expected: float
) -> None:
    """A malformed ``OPENAI_TIMEOUT_SECONDS`` used to crash the singleton's
    construction (non-numeric) or fail every dial (0 / negative / nan / inf / 1e9)."""
    if raw is not None:
        monkeypatch.setenv(_OPERATOR, raw)
    assert wp._OpenAIWrapperProvider()._timeout == expected


class _FastHandler(_SlowHandler):
    stall_s = 0.05


@pytest.mark.parametrize("bad", ["abc", "0", "-3", "nan", "inf", "1e9"])
def test_a_bad_provider_default_does_not_move_a_repair_onto_bedrock(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    """The repair passes send no budget, so they run on the provider default. Before
    R460 that default was the bad value (the dial failed); R460's blanket 150 s masked
    it for them by accident. With the repairs back on the provider default the default
    itself must be sound: a healthy tunnel stays the serving leg."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FastHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("OPENAI_API_BASE", f"http://127.0.0.1:{server.server_address[1]}/v1")
        monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "127.0.0.1")
        monkeypatch.setenv(_OPERATOR, bad)
        monkeypatch.setattr(wp, "_SINGLETON", None)
        bedrock: list[str] = []

        def _fake_bedrock(**kwargs):
            bedrock.append(kwargs.get("stage_name", "?"))
            return "BEDROCK LEG answer."

        with (
            patch("app.engines._graph_rag_impl._bedrock_complete_for_graph_rag", _fake_bedrock),
            patch("app.llm.bedrock_client.is_bedrock_provider_enabled", return_value=True),
        ):
            repaired = _stage2_complete(
                system="s", user="u", max_tokens=64, temperature=0.0,
                complex_question=False, stage_name="Stage 2 (Tail Repair)",
            )
        assert repaired == _BODY
        assert bedrock == []
        stats = pol.transport_stats()
        assert stats["primary_ok"] == 1 and stats["primary_failed"] == 0, stats
    finally:
        server.shutdown()
        server.server_close()

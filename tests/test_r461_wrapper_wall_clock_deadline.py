"""R461 — ``OpenAIWrapperRequest.timeout_seconds`` is a WALL-CLOCK bound on the body.

An httpx timeout is per OPERATION (connect, each socket read, write, pool), never
a total. A server that answers its headers and then drips the body one chunk
inside each read window kept a "2 s" call alive for 8 s, and would hold a Stage-2
call on its 150 s budget for as long as the upstream cared to drip. The real
wrapper answers with one non-streaming JSON write, so this is latent hardening,
but ``complete()``'s own comment promised "a budget for the WHOLE call".

The provider now hands its deadline to the request as an extension and the pooled
client's response hook wraps the body so a chunk that arrives after it raises
``httpx.ReadTimeout`` (an ordinary ``network_error``: Stage-2 falls to leg 2
exactly as on any other timeout).

Everything here runs the REAL provider constructor against a real loopback socket.
``httpx.MockTransport`` is deliberately not used: a replaced ``_client`` bypasses
the hook and would pass vacuously. The tests are two-sided: a body that finishes
inside the deadline, a single-write JSON and a silent upstream behave exactly as
before.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from unittest.mock import patch

import pytest

import app.llm.openai_wrapper_provider as wp
from app.engines import _graph_rag_impl as engine
from app.llm import stage2_policy as pol
from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    _OpenAIWrapperProvider,
)

_TEXT = "Article 14 requires human oversight so that natural persons can intervene."
_BODY = json.dumps({
    "choices": [{"message": {"content": _TEXT}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 7},
}).encode()
_HEAD = (
    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
    b"Content-Length: %d\r\n\r\n" % len(_BODY)
)


class _Upstream:
    """A raw-socket HTTP server. ``script[i]`` is how the i-th REQUEST is answered:

    ``single``  headers + whole body in one write (what the real wrapper does)
    ``silent``  read the request and never answer
    ``429``     ``429`` with ``Retry-After: 1``
    ``drip``    headers, then ``chunk`` bytes of body every ``gap`` seconds
    """

    def __init__(self, script: list[str], *, gap: float = 0.4, chunk: int = 8) -> None:
        self.script, self.gap, self.chunk = list(script), gap, chunk
        self.requests = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(4)
        self._listener.settimeout(0.2)
        self.port = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except OSError:  # includes the accept timeout; stop() closes the listener
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    @staticmethod
    def _read_request(conn: socket.socket) -> bool:
        buf = b""
        while b"\r\n\r\n" not in buf:
            data = conn.recv(65536)
            if not data:
                return False
            buf += data
        head, _, rest = buf.partition(b"\r\n\r\n")
        length = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":")[1])
        while len(rest) < length:
            rest += conn.recv(65536)
        return True

    def _serve(self, conn: socket.socket) -> None:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            while self._read_request(conn):
                with self._lock:
                    mode = self.script[min(self.requests, len(self.script) - 1)]
                    self.requests += 1
                if mode == "single":
                    conn.sendall(_HEAD + _BODY)
                elif mode == "silent":
                    self._stop.wait(30)
                    return
                elif mode == "429":
                    conn.sendall(
                        b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 1\r\n"
                        b"Content-Length: 0\r\n\r\n"
                    )
                elif mode == "drip":
                    conn.sendall(_HEAD)
                    for i in range(0, len(_BODY), self.chunk):
                        if self._stop.wait(self.gap):
                            return
                        conn.sendall(_BODY[i:i + self.chunk])
        except OSError:  # the client gave up first, which is the point
            pass
        finally:
            conn.close()

    def close(self) -> None:
        self._stop.set()
        self._listener.close()


@pytest.fixture
def upstream():
    made: list[_Upstream] = []

    def _make(script: list[str], **kw) -> _Upstream:
        server = _Upstream(script, **kw)
        made.append(server)
        return server

    yield _make
    for server in made:
        server.close()


def _call(server: _Upstream, budget: float):
    provider = _OpenAIWrapperProvider(
        base_url=f"http://127.0.0.1:{server.port}/v1", api_key="x"
    )
    t0 = time.perf_counter()
    response = provider.complete(
        OpenAIWrapperRequest(
            user="hi", model="claude-opus-5-5", max_tokens=64, timeout_seconds=budget
        )
    )
    return response, time.perf_counter() - t0


def test_a_dribbling_body_is_cut_at_the_wall_clock_deadline(upstream) -> None:
    """~19 chunks, one every 0.4 s (about 7.6 s of body) against a 0.8 s budget.

    On the unpatched provider every chunk lands inside the 0.8 s read window, so the
    call ran to completion in ~7 s and returned the full text."""
    response, elapsed = _call(upstream(["drip"], gap=0.4), budget=0.8)
    assert response.error is not None and response.error.startswith("network_error"), response
    assert response.text == ""
    assert elapsed < 0.8 + 1.0, f"the 0.8 s budget was exceeded by {elapsed - 0.8:.2f}s"


def test_a_body_that_finishes_inside_the_deadline_is_untouched(upstream) -> None:
    """The other side: a slow-but-in-budget drip must still be delivered whole."""
    response, elapsed = _call(upstream(["drip"], gap=0.03, chunk=16), budget=5.0)
    assert response.error is None, response
    assert response.text == _TEXT
    assert elapsed < 4.0


def test_a_single_write_answer_is_byte_identical(upstream) -> None:
    """What the real wrapper does: one write. The guard must not touch it."""
    response, elapsed = _call(upstream(["single"]), budget=0.8)
    assert response.error is None, response
    assert response.text == _TEXT
    assert response.completion_tokens == 7 and response.prompt_tokens == 5
    assert elapsed < 0.5


def test_a_silent_upstream_is_still_bounded_by_the_read_timeout(upstream) -> None:
    """Control for the pre-existing bound: accept, read the request, never answer."""
    response, elapsed = _call(upstream(["silent"]), budget=0.8)
    assert response.error is not None and response.error.startswith("network_error"), response
    assert 0.7 <= elapsed < 1.8, elapsed


def test_the_deadline_also_covers_the_429_retry(upstream) -> None:
    """429 with ``Retry-After: 1`` is honoured (it fits the 2.5 s budget), then the
    retry dribbles. The retry post must carry the ORIGINAL deadline, so the call ends
    near 2.5 s, not after the ~7 s the retry would take on its own read window."""
    server = upstream(["429", "drip"], gap=0.4)
    response, elapsed = _call(server, budget=2.5)
    assert server.requests == 2, "the 429 must have been retried"
    assert response.error is not None and response.error.startswith("network_error_on_retry")
    assert elapsed < 2.5 + 1.0, f"the retry outran the call's deadline: {elapsed:.2f}s"


def test_a_dribbling_tunnel_is_one_failed_primary_dial_then_leg_2(
    upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the engine: the cut surfaces as an ordinary primary failure, so the R360
    counters still reconcile (attempts == ok + failed), the primary is dialled ONCE
    (a timeout is never retried there) and leg 2 serves."""
    server = upstream(["drip"], gap=0.4)
    monkeypatch.setenv("OPENAI_API_BASE", f"http://127.0.0.1:{server.port}/v1")
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "127.0.0.1")
    monkeypatch.setattr(wp, "_SINGLETON", None)
    pol.reset_transport_stats()
    bedrock: list[str] = []

    def _fake_bedrock(**kwargs):
        bedrock.append(kwargs.get("stage_name", "?"))
        return "BEDROCK LEG: Article 14 requires human oversight."

    try:
        with (
            patch.object(engine, "_stage2_wrapper_timeout_s", return_value=0.8),
            patch.object(engine, "_bedrock_complete_for_graph_rag", _fake_bedrock),
            patch("app.llm.bedrock_client.is_bedrock_provider_enabled", return_value=True),
        ):
            t0 = time.perf_counter()
            out = engine._openai_wrapper_complete_for_graph_rag(
                system="s", user="question", max_tokens=200, temperature=0.0,
                stage_name="Stage 2 (Polishing)", history_turn_count=0,
            )
            elapsed = time.perf_counter() - t0
        stats = pol.transport_stats()
    finally:
        pol.reset_transport_stats()
    assert out == "BEDROCK LEG: Article 14 requires human oversight."
    assert bedrock == ["Stage 2 (Polishing)"]
    assert server.requests == 1, "a timed-out primary dial must not be retried"
    assert stats["primary_attempts"] == 1
    assert stats["primary_failed"] == 1 and stats["primary_ok"] == 0, stats
    assert stats["fallback_attempts"] == 1 and stats["fallback_ok"] == 1, stats
    assert elapsed < 0.8 + 1.0, f"the tunnel held the call for {elapsed:.2f}s"

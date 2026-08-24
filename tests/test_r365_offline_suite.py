"""R365 — pin the offline-by-default socket guard in ``tests/conftest.py``.

The guard exists because of two MEASURED facts on this box:

* 5 tests across 3 files issued 8 real HTTPS POSTs to the production Claude-Max
  wrapper on every ``pytest`` run, because they ``monkeypatch.delenv`` the very
  variable the R105 block sets and ``OpenAIWrapperProvider.__init__`` then falls
  back to a hard-coded production host;
* a TCP connect to a CLOSED loopback port costs **2.03 s** on Windows, not the
  "~1 ms" the R105 comment claims, so the repo's dead-base idiom is a 2-second
  stall per LLM call.

These tests are deliberately TWO-SIDED. A guard whose OFF state behaves like its
ON state is the inert-feature trap this repo has been bitten by before (CLAUDE.md
§ Stage-2 transport contract), so every "it blocks" assertion is paired with a
"…and the escape hatch really does let it through" assertion.
"""
from __future__ import annotations

import errno
import socket
import time

import pytest

from tests import conftest as guard

# ── the guard is actually installed ──────────────────────────────────────


def test_guard_is_installed_over_the_real_socket_methods():
    """Not "the code looks right" — the class attributes are really swapped."""
    assert socket.socket.connect is guard._egress_guarded_connect
    assert socket.socket.connect_ex is guard._egress_guarded_connect_ex
    assert socket.socket.bind is guard._egress_guarded_bind
    # And the originals are still held, so teardown can restore them.
    assert guard._real_socket_connect is not guard._egress_guarded_connect


# ── non-loopback egress is refused ───────────────────────────────────────


class TestNonLoopbackIsBlocked:
    def test_connect_to_public_ip_raises(self):
        sock = socket.socket()
        try:
            with pytest.raises(guard.NetworkEgressBlocked) as excinfo:
                sock.connect(("1.1.1.1", 443))
        finally:
            sock.close()
        message = str(excinfo.value)
        # The error must name the DESTINATION and the TEST, so a future
        # offender is diagnosable from the failure line alone.
        assert "1.1.1.1:443" in message
        assert "test_connect_to_public_ip_raises" in message
        assert guard.ALLOW_NETWORK_MARKER in message

    def test_blocked_error_is_a_connection_refused_error(self):
        """Callers must see the same class they'd see with the cable pulled."""
        assert issubclass(guard.NetworkEgressBlocked, ConnectionRefusedError)
        assert issubclass(guard.NetworkEgressBlocked, OSError)

    def test_connect_to_the_production_wrapper_host_is_blocked(self):
        """The exact destination the 5 delenv tests were reaching."""
        sock = socket.socket()
        try:
            with pytest.raises(guard.NetworkEgressBlocked):
                sock.connect(("172.67.70.15", 443))
        finally:
            sock.close()

    def test_connect_ex_to_public_ip_raises_rather_than_returning_an_errno(self):
        """A silent errno is the failure mode the guard exists to end."""
        sock = socket.socket()
        try:
            with pytest.raises(guard.NetworkEgressBlocked):
                sock.connect_ex(("1.1.1.1", 443))
        finally:
            sock.close()

    def test_blocked_attempt_is_recorded_with_the_test_id(self):
        before = len(guard.BLOCKED_EGRESS)
        sock = socket.socket()
        try:
            with pytest.raises(guard.NetworkEgressBlocked):
                sock.connect(("203.0.113.7", 8080))
        finally:
            sock.close()
        new = guard.BLOCKED_EGRESS[before:]
        assert len(new) == 1
        nodeid, destination = new[0]
        assert destination == "203.0.113.7:8080"
        assert "test_blocked_attempt_is_recorded_with_the_test_id" in nodeid

    def test_blocking_survives_a_delenv_of_openai_api_base(self, monkeypatch):
        """The guard, NOT the env var, is what stops the 14 delenv tests.

        This mirrors exactly what those tests do before the provider is built.
        """
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        import os

        assert os.getenv("OPENAI_API_BASE") is None
        sock = socket.socket()
        try:
            with pytest.raises(guard.NetworkEgressBlocked):
                sock.connect(("172.67.70.15", 443))
        finally:
            sock.close()


# ── the marker is a real escape hatch (two-sided) ────────────────────────


class TestAllowNetworkMarker:
    def test_marker_is_registered(self, pytestconfig):
        markers = pytestconfig.getini("markers")
        assert any(
            line.startswith(f"{guard.ALLOW_NETWORK_MARKER}:") for line in markers
        ), f"{guard.ALLOW_NETWORK_MARKER} is not a registered marker"

    @pytest.mark.allow_network
    def test_marker_disarms_the_guard(self):
        """The OFF state must NOT behave like the ON state.

        Asserts the guard's own flag is down and that the guarded ``connect``
        delegates to the real one — without actually dialling out, so this
        test stays offline while proving the hatch is open.
        """
        assert guard._egress_allowed[0] is True

        calls: list[tuple] = []
        real = guard._real_socket_connect
        try:
            guard._real_socket_connect = lambda s, a: calls.append(a)
            sock = socket.socket()
            try:
                sock.connect(("1.1.1.1", 443))
            finally:
                sock.close()
        finally:
            guard._real_socket_connect = real

        assert calls == [("1.1.1.1", 443)], (
            "with @allow_network the guard must hand the connect straight to "
            "the real socket method"
        )

    def test_marker_is_disarmed_again_for_unmarked_tests(self):
        """The permission must not leak to the next test."""
        assert guard._egress_allowed[0] is False
        sock = socket.socket()
        try:
            with pytest.raises(guard.NetworkEgressBlocked):
                sock.connect(("1.1.1.1", 443))
        finally:
            sock.close()


# ── loopback still works, and dead loopback fails FAST ───────────────────


class TestLoopbackStillWorks:
    def test_a_real_local_listener_still_accepts(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        client = socket.socket()
        try:
            started = time.perf_counter()
            client.connect(("127.0.0.1", port))
            elapsed = time.perf_counter() - started
        finally:
            client.close()
            server.close()
        assert elapsed < guard.LOOPBACK_CONNECT_BUDGET_SECONDS, (
            f"a live loopback connect took {elapsed:.4f}s, which is at or over "
            f"the {guard.LOOPBACK_CONNECT_BUDGET_SECONDS}s budget — the budget "
            "is too tight and would start refusing real local servers"
        )

    def test_a_port_found_dead_is_usable_again_once_a_server_binds_it(self):
        """The negative cache must not outlive the condition it recorded.

        Exactly the real-world sequence: something probes a port before the
        local server is up, the probe fails, then the server starts.
        """
        # 1. Reserve then release a port so we know it is genuinely closed.
        scout = socket.socket()
        scout.bind(("127.0.0.1", 0))
        port = scout.getsockname()[1]
        scout.close()
        for alias in ("localhost", "127.0.0.1", "::1"):
            guard._DEAD_LOOPBACK.discard((alias, port))

        # 2. A connect now fails and poisons the cache.
        probe = socket.socket()
        try:
            with pytest.raises((ConnectionRefusedError, TimeoutError)):
                probe.connect(("127.0.0.1", port))
        finally:
            probe.close()
        assert ("127.0.0.1", port) in guard._DEAD_LOOPBACK

        # 3. The server comes up on that port; bind() must clear the entry.
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", port))
            server.listen(1)
            assert ("127.0.0.1", port) not in guard._DEAD_LOOPBACK, (
                "bind() did not drop the stale negative-cache entry — a local "
                "server fixture would be unreachable"
            )
            # 4. And the connect really works again.
            client = socket.socket()
            try:
                client.connect(("127.0.0.1", port))
            finally:
                client.close()
        finally:
            server.close()
            for alias in ("localhost", "127.0.0.1", "::1"):
                guard._DEAD_LOOPBACK.discard((alias, port))

    def test_dead_loopback_port_fails_fast_not_in_two_seconds(self):
        """The 18 s suite saving lives here.

        Unguarded, a connect to a closed loopback port costs ~2.03 s on this
        Windows box. Guarded, the first attempt is capped at the budget and
        every later attempt is served from the negative cache.
        """
        port = 47113  # nothing listens here
        for alias in ("localhost", "127.0.0.1", "::1"):
            guard._DEAD_LOOPBACK.discard((alias, port))

        timings: list[float] = []
        for _ in range(3):
            sock = socket.socket()
            started = time.perf_counter()
            try:
                with pytest.raises((ConnectionRefusedError, TimeoutError)):
                    sock.connect(("127.0.0.1", port))
            finally:
                timings.append(time.perf_counter() - started)
                sock.close()

        assert timings[0] < 1.0, (
            f"first connect to a dead loopback port took {timings[0]:.4f}s; "
            "the budget did not apply"
        )
        # Attempts 2 and 3 must be served from the cache — no syscall at all.
        assert max(timings[1:]) < 0.05, (
            f"repeat connects took {timings[1:]} — the negative cache is not "
            "short-circuiting"
        )
        assert ("127.0.0.1", port) in guard._DEAD_LOOPBACK

    def test_connect_ex_on_a_dead_loopback_port_returns_econnrefused(self):
        """``connect_ex`` keeps its contract on loopback (returns, not raises)."""
        port = 47114
        for alias in ("localhost", "127.0.0.1", "::1"):
            guard._DEAD_LOOPBACK.discard((alias, port))
        sock = socket.socket()
        try:
            first = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        assert first != 0
        sock = socket.socket()
        try:
            started = time.perf_counter()
            cached = sock.connect_ex(("127.0.0.1", port))
            elapsed = time.perf_counter() - started
        finally:
            sock.close()
        assert cached == errno.ECONNREFUSED
        assert elapsed < 0.05


# ── the FastAPI TestClient is unaffected ─────────────────────────────────


class TestTestClientStillWorks:
    def test_testclient_serves_the_health_route(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            response = client.get("/healthz")
        assert response.status_code == 200

    def test_testclient_serves_the_regenold_ask_route(self):
        """The real wire contract, end to end, with the guard installed."""
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "What are the transparency obligations "
                            "for high-risk AI systems?",
                        }
                    ]
                },
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("answer")
        assert isinstance(body.get("references"), list)


# ── helper-level unit coverage ───────────────────────────────────────────


class TestLoopbackClassification:
    @pytest.mark.parametrize(
        "host",
        ["127.0.0.1", "127.0.0.53", "::1", "localhost", "LOCALHOST", "0.0.0.0", ""],
    )
    def test_local_hosts_are_loopback(self, host):
        assert guard._egress_is_loopback(host) is True

    @pytest.mark.parametrize(
        "host",
        ["1.1.1.1", "172.67.70.15", "104.26.14.34", "8.8.8.8", "2606:4700::1111",
         "wrapper.antifragile-ai.net", "api.groq.com"],
    )
    def test_remote_hosts_are_not_loopback(self, host):
        assert guard._egress_is_loopback(host) is False

    def test_ipv4_mapped_loopback_is_loopback(self):
        assert guard._egress_is_loopback("::ffff:127.0.0.1") is True

    def test_ipv4_mapped_public_address_is_not_loopback(self):
        assert guard._egress_is_loopback("::ffff:1.1.1.1") is False

    def test_non_inet_targets_pass_through(self):
        """AF_UNIX paths and odd tuples must not be classified at all."""
        assert guard._egress_inet_target("/tmp/some.sock") is None
        assert guard._egress_inet_target(b"\x00abstract") is None
        assert guard._egress_inet_target(("127.0.0.1",)) is None
        assert guard._egress_inet_target(("127.0.0.1", 80)) == ("127.0.0.1", 80)


class TestStrictModeSwitch:
    """Two-sided: the escalation switch must really be off AND really work."""

    def test_strict_is_off_by_default(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_TEST_EGRESS_STRICT", raising=False)
        assert guard._egress_strict_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
    def test_strict_reads_the_usual_truthy_spellings(self, monkeypatch, value):
        monkeypatch.setenv("REGENOLD_TEST_EGRESS_STRICT", value)
        assert guard._egress_strict_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "", "no"])
    def test_strict_reads_the_usual_falsy_spellings(self, monkeypatch, value):
        monkeypatch.setenv("REGENOLD_TEST_EGRESS_STRICT", value)
        assert guard._egress_strict_enabled() is False

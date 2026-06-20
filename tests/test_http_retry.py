"""Unit tests for :mod:`evals.bench._http_retry`.

Pure unit tests — every HTTP call is mocked. Covers the R47-D retry
matrix:

  * First attempt 200 → 1 attempt, no retries.
  * First attempt RemoteDisconnected + second attempt 200 → 2 attempts.
  * All three attempts RemoteDisconnected → 3 attempts, error surfaced.
  * 4xx response → 1 attempt, no retry (passes through).
  * 5xx response → retries.
  * Timeout → retries.
  * JSON parse error → no retry.
  * non_dict_body → no retry.
  * Windows errno 10060 inside URLError → retries.
  * Backoff is honoured between retries.

The tests patch ``urllib.request.urlopen`` from the
:mod:`evals.bench._http_retry` namespace so we never touch a real socket.
"""
from __future__ import annotations

import http.client
import io
import json
import urllib.error
from typing import Any
from unittest import mock

import pytest

from evals.bench import _http_retry


# ── Fakes ─────────────────────────────────────────────────────────────────


class _FakeResp:
    """Minimal HTTPResponse stand-in for ``urlopen`` patching."""

    def __init__(self, status: int, body: bytes) -> None:
        self._status = status
        self._body = body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self._status


def _make_resp(status: int = 200, payload: dict[str, Any] | None = None) -> _FakeResp:
    body = json.dumps(payload or {
        "answer": "ok",
        "references": ["Article 13"],
        "reasoning": None,
    }).encode("utf-8")
    return _FakeResp(status, body)


def _make_http_error(code: int, body: bytes = b'{"detail": "x"}') -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://test/api", code=code, msg=f"HTTP {code}",
        hdrs=None, fp=io.BytesIO(body),  # type: ignore[arg-type]
    )


def _make_remote_disconnected_url_error() -> urllib.error.URLError:
    """Simulate the exact shape urllib raises when the server drops the
    TCP connection mid-response.

    urllib.request wraps ``http.client.RemoteDisconnected`` in a
    ``URLError`` where ``reason`` is the original
    ``RemoteDisconnected`` instance. This is what the R46 V2 client
    saw at ~15 s when the Cloudflare tunnel killed the idle socket.
    """
    underlying = http.client.RemoteDisconnected(
        "Remote end closed connection without response"
    )
    return urllib.error.URLError(reason=underlying)


def _make_winerror_10060_url_error() -> urllib.error.URLError:
    """Simulate a Windows-side ``WSAETIMEDOUT`` (10060) wrapped by urllib.

    Multi-turn rows 5/6 in the R46 V2 run saw this — the Railway edge
    held the socket open but stopped acking writes for >15 s, so the
    Windows stack tore the connection down with errno 10060.
    """
    return urllib.error.URLError(reason=OSError(10060, "Connection timed out"))


# ── Tests for error classification ────────────────────────────────────────


class TestIsRetryableError:
    def test_remote_disconnected_url_error_is_retryable(self):
        exc = _make_remote_disconnected_url_error()
        assert _http_retry.is_retryable_error(exc) is True

    def test_winerror_10060_url_error_is_retryable(self):
        exc = _make_winerror_10060_url_error()
        assert _http_retry.is_retryable_error(exc) is True

    def test_winerror_10054_url_error_is_retryable(self):
        exc = urllib.error.URLError(reason=OSError(10054, "Connection reset"))
        assert _http_retry.is_retryable_error(exc) is True

    def test_dns_failure_url_error_is_not_retryable(self):
        # Generic name-resolution failure — not retryable; the host name
        # isn't going to resolve on the second try.
        exc = urllib.error.URLError(reason="getaddrinfo failed")
        assert _http_retry.is_retryable_error(exc) is False

    def test_timeout_error_is_retryable(self):
        assert _http_retry.is_retryable_error(TimeoutError("read timeout")) is True

    def test_bare_remote_disconnected_is_retryable(self):
        exc = http.client.RemoteDisconnected("dropped")
        assert _http_retry.is_retryable_error(exc) is True

    def test_http_error_is_not_classified_as_retryable_here(self):
        # The caller picks per-status — is_retryable_error returns
        # False so the per-status path takes over.
        exc = _make_http_error(503)
        assert _http_retry.is_retryable_error(exc) is False

    def test_unrelated_value_error_not_retryable(self):
        assert _http_retry.is_retryable_error(ValueError("nope")) is False


class TestIsRetryableStatus:
    def test_500_is_retryable(self):
        assert _http_retry.is_retryable_status(500) is True

    def test_502_is_retryable(self):
        assert _http_retry.is_retryable_status(502) is True

    def test_599_is_retryable(self):
        assert _http_retry.is_retryable_status(599) is True

    def test_400_is_not_retryable(self):
        assert _http_retry.is_retryable_status(400) is False

    def test_429_is_not_retryable_at_this_layer(self):
        # 429 is intentionally NOT retried on the client side. Wrapper-
        # side 429 handling lives in openai_wrapper_provider.py; client-
        # side 429 means "the wire told us to slow down" and a fast
        # retry would defeat the purpose.
        assert _http_retry.is_retryable_status(429) is False


# ── post_json_with_retry — end-to-end with mocked urlopen ─────────────────


class TestPostJsonWithRetry:
    """End-to-end behaviour with ``urlopen`` mocked.

    All tests patch :func:`urllib.request.urlopen` in the
    ``evals.bench._http_retry`` namespace so we control every attempt's
    outcome.
    """

    URL = "https://example/api/v1/regenold/eu-ai-act/ask"
    PAYLOAD = [{"role": "user", "content": "what does art 13 require?"}]

    def _call(self, **kw) -> tuple[Any, ...]:
        kw.setdefault("max_retries", 2)
        kw.setdefault("backoff_s", 0.0)  # zero backoff for fast tests
        return _http_retry.post_json_with_retry(
            self.URL, self.PAYLOAD, api_key="key", timeout=5.0, **kw
        )

    def test_first_attempt_200_no_retry(self):
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=[_make_resp(200)],
        ) as urlopen:
            body, latency, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 1
        assert attempts == 1
        assert retried == []
        assert err is None
        assert status == 200
        assert body["answer"] == "ok"
        assert latency >= 0.0  # latency is positive wall-time

    def test_remote_disconnected_then_200(self):
        """The R46 V2 failure mode — first try drops at ~15 s, second
        try succeeds. Recovery rate becomes 1.0 for that row."""
        urlopen_side = [
            _make_remote_disconnected_url_error(),  # raised
            _make_resp(200),                         # returned
        ]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ) as urlopen:
            body, _, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 2
        assert attempts == 2
        assert len(retried) == 1
        # The recorded retried error should mention RemoteDisconnected.
        assert "RemoteDisconnected" in retried[0] or "Remote end closed" in retried[0]
        assert err is None
        assert status == 200
        assert body["answer"] == "ok"

    def test_all_three_remote_disconnected(self):
        """When the retry budget runs out the final error is surfaced
        AND all three attempts' errors are recorded."""
        urlopen_side = [
            _make_remote_disconnected_url_error(),
            _make_remote_disconnected_url_error(),
            _make_remote_disconnected_url_error(),
        ]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ) as urlopen:
            _, _, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 3  # max_retries=2 → 3 calls
        assert attempts == 3
        assert len(retried) == 3  # the final error is recorded too
        assert err is not None
        assert "Remote end closed" in err or "RemoteDisconnected" in err
        assert status == 0  # no HTTP status was ever reached

    def test_4xx_no_retry(self):
        """4xx is deterministic — retrying won't change anything. Surface
        the error on the first attempt so the runner sees it fast."""
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=[_make_http_error(400)],
        ) as urlopen:
            _, _, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 1
        assert attempts == 1
        assert retried == []
        assert status == 400
        assert err is not None
        assert "http_400" in err

    def test_404_no_retry(self):
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=[_make_http_error(404, body=b'{"detail": "not found"}')],
        ) as urlopen:
            _, _, status, err, attempts, _ = self._call()

        assert urlopen.call_count == 1
        assert attempts == 1
        assert status == 404
        assert err is not None and "http_404" in err

    def test_429_no_retry_at_client(self):
        """Client-side never retries 429. The wrapper handles its own
        429 backoff upstream; if it surfaces 429 to us, something is
        explicitly rate-gating us."""
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=[_make_http_error(429)],
        ) as urlopen:
            _, _, status, err, attempts, _ = self._call()

        assert urlopen.call_count == 1
        assert attempts == 1
        assert status == 429

    def test_500_retries_until_recovered(self):
        urlopen_side = [
            _make_http_error(500),
            _make_resp(200),
        ]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ) as urlopen:
            _, _, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 2
        assert attempts == 2
        assert err is None
        assert status == 200
        assert len(retried) == 1
        assert "http_500" in retried[0]

    def test_502_retries(self):
        urlopen_side = [
            _make_http_error(502),
            _make_http_error(503),
            _make_resp(200),
        ]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ):
            _, _, status, err, attempts, retried = self._call()
        assert attempts == 3
        assert err is None
        assert status == 200
        assert len(retried) == 2

    def test_timeout_retries(self):
        urlopen_side = [
            TimeoutError("read timeout"),
            _make_resp(200),
        ]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ) as urlopen:
            _, _, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 2
        assert attempts == 2
        assert err is None
        assert status == 200
        assert retried == ["timeout"]

    def test_winerror_10060_retries(self):
        urlopen_side = [
            _make_winerror_10060_url_error(),
            _make_resp(200),
        ]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ) as urlopen:
            _, _, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 2
        assert attempts == 2
        assert err is None
        assert status == 200
        assert len(retried) == 1

    def test_json_decode_no_retry(self):
        """JSON parse failures are deterministic — the server returned
        200 with a non-JSON body. Retrying won't fix that."""
        bad_resp = _FakeResp(200, b"<html>not json</html>")
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=[bad_resp],
        ) as urlopen:
            _, _, status, err, attempts, retried = self._call()

        assert urlopen.call_count == 1
        assert attempts == 1
        assert retried == []
        assert status == 200
        assert err is not None
        assert "json_decode" in err

    def test_non_dict_body_no_retry(self):
        """Server returned JSON but it's a list / string / null. Retrying
        won't fix the contract violation."""
        list_body = _FakeResp(200, b'["not", "a", "dict"]')
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=[list_body],
        ) as urlopen:
            _, _, status, err, attempts, _ = self._call()

        assert urlopen.call_count == 1
        assert attempts == 1
        assert status == 200
        assert err == "non_dict_body"

    def test_dns_url_error_no_retry(self):
        """Generic name-resolution / connection-refused URLError — not
        the connection-mid-response shape — doesn't retry."""
        exc = urllib.error.URLError(reason="getaddrinfo failed")
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=[exc],
        ) as urlopen:
            _, _, status, err, attempts, _ = self._call()

        assert urlopen.call_count == 1
        assert attempts == 1
        assert status == 0
        assert err is not None
        assert "url_error" in err

    def test_max_retries_zero_disables_retry(self):
        """max_retries=0 means exactly one attempt — same as the legacy
        no-retry behaviour."""
        urlopen_side = [_make_remote_disconnected_url_error()]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ) as urlopen:
            _, _, _, err, attempts, retried = self._call(max_retries=0)

        assert urlopen.call_count == 1
        assert attempts == 1
        assert err is not None
        assert len(retried) == 1  # final error captured even with 0 retries

    def test_backoff_is_invoked_between_attempts(self):
        """The backoff sleep is honoured — non-zero backoff produces
        a measurable wall-time gap (we patch sleep to assert it)."""
        urlopen_side = [
            _make_remote_disconnected_url_error(),
            _make_remote_disconnected_url_error(),
            _make_resp(200),
        ]
        with mock.patch.object(
            _http_retry.urllib.request, "urlopen",
            side_effect=urlopen_side,
        ), mock.patch.object(_http_retry.time, "sleep") as sleep:
            _, latency, _, err, attempts, _ = _http_retry.post_json_with_retry(
                self.URL, self.PAYLOAD, "key", 5.0,
                max_retries=2, backoff_s=0.5,
            )

        # Two sleeps between three attempts. R136 added full jitter
        # (0.5x-1.5x) on the exponential base (0.5, 1.0) so concurrent
        # retriers de-correlate — so assert the jittered RANGES.
        assert sleep.call_count == 2
        assert 0.25 <= sleep.call_args_list[0].args[0] <= 0.75  # 0.5 × [0.5,1.5]
        assert 0.5 <= sleep.call_args_list[1].args[0] <= 1.5  # 1.0 × [0.5,1.5]
        assert attempts == 3
        assert err is None
        # Latency includes the slept wall-time × 1000 (since sleep was
        # patched it adds 0, but the retry helper adds the sleep_s value
        # to latency anyway). Use the minimum-jitter lower bound.
        assert latency >= (0.5 * 0.5 + 1.0 * 0.5) * 1000.0

    def test_idempotent_request_object_passed_through(self):
        """Same Request object is used across retries — verifies our
        urllib.Request reuse assumption."""
        calls: list[urllib.request.Request] = []

        def _capture(req, timeout):  # noqa: ARG001
            calls.append(req)
            if len(calls) == 1:
                raise _make_remote_disconnected_url_error()
            return _make_resp(200)

        with mock.patch.object(
            _http_retry.urllib.request, "urlopen", side_effect=_capture,
        ):
            _, _, _, err, attempts, _ = self._call()

        assert attempts == 2
        assert err is None
        # Both calls receive the SAME Request object (urllib.Request is
        # a stateless config-bag; reuse is safe).
        assert calls[0] is calls[1]
        assert calls[0].get_method() == "POST"
        # API key header must be set when api_key is provided.
        assert calls[0].headers.get("X-regenold-api-key") == "key"


class TestUserAgentOverride:
    def test_user_agent_threads_through(self):
        captured: list[urllib.request.Request] = []

        def _capture(req, timeout):  # noqa: ARG001
            captured.append(req)
            return _make_resp(200)

        with mock.patch.object(
            _http_retry.urllib.request, "urlopen", side_effect=_capture,
        ):
            _http_retry.post_json_with_retry(
                "http://x/y", [{"role": "user", "content": "hi"}],
                "k", 1.0, user_agent="custom/1.0",
            )

        assert captured[0].headers.get("User-agent") == "custom/1.0"

"""R136 — transient-DNS retry + process DNS cache for parallel eval runs.

Running several live eval runners in parallel saturated the local DNS
resolver, which returned ``getaddrinfo failed`` (Errno 11001) — surfaced as a
``url_error`` and, pre-fix, classified NON-retryable (treated as a deterministic
bad-host). Under saturation it is transient. The fix: ``socket.gaierror`` (and
the WSAHOST_NOT_FOUND / WSATRY_AGAIN / WSANO_DATA errnos) are now retryable, and
a process-level TTL cache over ``socket.getaddrinfo`` collapses N lookups → 1 so
the resolver is never hammered.
"""
from __future__ import annotations

import socket
import urllib.error

from evals.bench import _http_retry as h


class TestR136DnsRetryClassification:
    def test_bare_gaierror_is_retryable(self):
        assert h.is_retryable_error(socket.gaierror(11001, "getaddrinfo failed"))

    def test_urlerror_wrapping_gaierror_is_retryable(self):
        exc = urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
        assert h.is_retryable_error(exc)

    def test_wsatryagain_errno_retryable(self):
        assert h.is_retryable_error(socket.gaierror(11002, "try again"))

    def test_genuine_non_dns_oserror_not_retryable(self):
        # A plain ENOENT-class OSError is NOT a transient connection failure.
        assert not h.is_retryable_error(OSError(2, "no such file"))

    def test_transient_network_unreachable_retryable(self):
        # WinError 10051 (WSAENETUNREACH) — the parallel-run killer; under
        # concurrent connection load the host network transiently can't reach
        # the route. Now retryable.
        assert h.is_retryable_error(OSError(10051, "network unreachable"))
        assert h.is_retryable_error(OSError(10065, "no route to host"))
        assert h.is_retryable_error(
            urllib.error.URLError(OSError(10051, "network unreachable"))
        )

    def test_connection_refused_stays_non_retryable(self):
        # 10061 (WSAECONNREFUSED) is deterministic — nothing listening.
        assert not h.is_retryable_error(OSError(10061, "connection refused"))

    def test_existing_families_preserved(self):
        import http.client

        assert h.is_retryable_error(http.client.RemoteDisconnected())
        assert h.is_retryable_error(TimeoutError())
        assert not h.is_retryable_error(
            urllib.error.HTTPError("u", 404, "nf", {}, None)
        )
        # Edge-timeout errnos still retry.
        assert h.is_retryable_error(OSError(10060, "timed out"))


class TestR136DnsCache:
    def test_cache_installed_at_import(self):
        assert getattr(socket.getaddrinfo, "_regenold_cached", False) is True

    def test_repeated_resolution_is_cached(self):
        a = socket.getaddrinfo("localhost", 80)
        b = socket.getaddrinfo("localhost", 80)
        # Cache returns the identical object, so the second call did NOT hit
        # the resolver.
        assert a is b

    def test_install_is_idempotent(self):
        before = socket.getaddrinfo
        h.install_dns_cache()
        assert socket.getaddrinfo is before


class TestR136RetryBudget:
    def test_default_max_retries_raised(self):
        import inspect

        sig = inspect.signature(h.post_json_with_retry)
        # R136 raised the default 2 → 4 to absorb a multi-second transient
        # network blip under concurrent load.
        assert sig.parameters["max_retries"].default == 4
        assert sig.parameters["max_backoff_s"].default == 8.0

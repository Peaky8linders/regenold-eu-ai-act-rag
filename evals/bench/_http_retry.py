"""HTTP retry helper for the eval-client side of the Regenold wire.

Why this exists (R47-D):
The post-R46 V2 run had 6/56 HTTP failures, all with the same shape:
``RemoteDisconnected`` or ``WinError 10060`` at ~15-21 s latency. The
wire path is

    client → Railway edge → openai_wrapper → Cloudflare named tunnel
            → local NSSM wrapper → Claude Max

At ~15 s the Cloudflare tunnel or Railway edge times out idle TCP and
the eval client sees the connection killed mid-response. The route
itself already handles 429 + tunnel issues gracefully (deterministic
fallback always lands an answer). The problem is purely on the eval
CLIENT side — a one-shot retry on idempotent ``POST`` recovers cleanly
because every request to ``/api/v1/regenold/eu-ai-act/ask`` is
stateless.

Design constraints:
* Pure stdlib — same as the runners that call us. No ``requests`` /
  ``httpx``.
* Drop-in replacement for ``_http_post_json`` / ``_post`` in
  ``prod_runner.py`` and ``runner_v2.py``. Same return signature.
* **Retry on**: ``RemoteDisconnected``, ``BadStatusLine``,
  ``ConnectionResetError``, ``WinError 10060``, 5xx HTTP status.
* **Never retry on**: 4xx HTTP, json parse error, ``non_dict_body``.
  Those are deterministic and surfacing them fast is correct.
* Hard upper bound: ``max_retries + 1`` HTTP calls (default 3 total).
  With ``backoff_s=0.5`` and exponential backoff, worst case adds
  ``0.5 + 1.0 = 1.5 s`` of sleep.
* Latency = SUM of all attempts so the user sees real wall-time.

Idempotency: every request to ``/api/v1/regenold/eu-ai-act/ask`` is
idempotent (stateless wire — the route doesn't mutate per-call state
besides the audit chain, which dedupes on ``(hash, timestamp)``), so
client-side retry is safe.
"""
from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from typing import Any

__all__ = [
    "post_json_with_retry",
    "is_retryable_error",
    "is_retryable_status",
    "AttemptResult",
]


# ── Error classification ───────────────────────────────────────────────────


# These are the urllib / stdlib exception classes whose appearance in a
# URLError.reason (or as a direct OSError) indicate a transient
# connection-layer failure — exactly the shapes the Cloudflare-tunnel /
# Railway-edge idle timeout produces.
_RETRYABLE_REASON_TYPES: tuple[type[BaseException], ...] = (
    http.client.RemoteDisconnected,
    http.client.BadStatusLine,
    http.client.IncompleteRead,
    ConnectionResetError,
    ConnectionAbortedError,
)

# Windows socket errno values that map to "connection died at the edge"
# (these come through as bare OSError with .errno set, NOT wrapped in
# URLError, when the failure happens between socket attempts).
#   10054 — WSAECONNRESET  (Connection reset by peer)
#   10053 — WSAECONNABORTED (Software caused connection abort)
#   10060 — WSAETIMEDOUT   (Connection timed out)
_RETRYABLE_WIN_ERRNOS = frozenset({10053, 10054, 10060})


def is_retryable_error(exc: BaseException) -> bool:
    """Return True if ``exc`` is a transient connection-layer failure.

    Specifically: TimeoutError, a urllib.URLError whose reason is one of
    the retryable connection classes, a bare WinError 10053/10054/10060,
    or one of the connection-reset / aborted classes directly.

    Returns False for ``HTTPError`` (caller checks status code separately)
    and any other exception class.
    """
    # urllib bubbles HTTPError up as a subclass of URLError — keep it
    # OUT of the retry set; the caller decides per-status (5xx retry,
    # 4xx don't).
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, _RETRYABLE_REASON_TYPES):
            return True
        if isinstance(reason, TimeoutError):
            return True
        if isinstance(reason, OSError):
            # Windows surfaces edge timeouts as OSError(10060, ...)
            # wrapped inside URLError.
            if getattr(reason, "errno", None) in _RETRYABLE_WIN_ERRNOS:
                return True
        return False
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, _RETRYABLE_REASON_TYPES):
        return True
    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) in _RETRYABLE_WIN_ERRNOS:
            return True
    return False


def is_retryable_status(status: int) -> bool:
    """5xx is retryable, everything else is not."""
    return 500 <= status < 600


# ── Single attempt ─────────────────────────────────────────────────────────


class AttemptResult:
    """Outcome of a single HTTP attempt.

    Kept as a tiny dataclass-like container (not @dataclass to stay
    free of imports and keep this module dependency-free).
    """

    __slots__ = ("body", "elapsed_ms", "status", "error", "retryable")

    def __init__(
        self,
        body: dict[str, Any],
        elapsed_ms: float,
        status: int,
        error: str | None,
        retryable: bool,
    ) -> None:
        self.body = body
        self.elapsed_ms = elapsed_ms
        self.status = status
        self.error = error
        self.retryable = retryable


def _single_attempt(
    req: urllib.request.Request,
    timeout: float,
) -> AttemptResult:
    """Run one POST and classify the outcome.

    Mirrors the existing ``_http_post_json`` body byte-for-byte so the
    happy path / 4xx / JSON-decode behaviour stays unchanged.
    """
    empty: dict[str, Any] = {"answer": "", "references": [], "reasoning": None}
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.perf_counter() - start) * 1000.0
            raw = resp.read()
            status = resp.getcode() or 200
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                # JSON parse failures are deterministic — never retry.
                return AttemptResult(
                    empty, elapsed, status,
                    f"json_decode: {exc.__class__.__name__}", retryable=False,
                )
            if not isinstance(body, dict):
                return AttemptResult(
                    empty, elapsed, status, "non_dict_body", retryable=False,
                )
            body.setdefault("answer", "")
            body.setdefault("references", [])
            body.setdefault("reasoning", None)
            return AttemptResult(body, elapsed, status, None, retryable=False)
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        # Try to read the upstream's detail body — useful when the
        # caller's retries are exhausted.
        try:
            payload_bytes = exc.read()
            err_body = json.loads(payload_bytes.decode("utf-8"))
            detail = err_body.get("detail") if isinstance(err_body, dict) else None
        except Exception:  # noqa: BLE001
            detail = None
        msg = f"http_{exc.code}"
        if detail:
            msg = f"{msg}: {str(detail)[:120]}"
        return AttemptResult(
            empty, elapsed, exc.code, msg,
            retryable=is_retryable_status(exc.code),
        )
    except urllib.error.URLError as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return AttemptResult(
            empty, elapsed, 0,
            f"url_error: {exc.reason}",
            retryable=is_retryable_error(exc),
        )
    except TimeoutError:
        elapsed = (time.perf_counter() - start) * 1000.0
        return AttemptResult(empty, elapsed, 0, "timeout", retryable=True)
    except _RETRYABLE_REASON_TYPES as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return AttemptResult(
            empty, elapsed, 0,
            f"{exc.__class__.__name__}: {exc}"[:200],
            retryable=True,
        )
    except OSError as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        retryable = getattr(exc, "errno", None) in _RETRYABLE_WIN_ERRNOS
        return AttemptResult(
            empty, elapsed, 0,
            f"os_error: {exc}"[:200],
            retryable=retryable,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = (time.perf_counter() - start) * 1000.0
        return AttemptResult(
            empty, elapsed, 0,
            f"unexpected: {exc.__class__.__name__}: {exc}"[:200],
            retryable=False,
        )


# ── Public helper ──────────────────────────────────────────────────────────


_USER_AGENT = "regenold-eu-ai-act-rag/http-retry"


def _build_request(
    url: str,
    payload: list[dict[str, str]],
    api_key: str | None,
    user_agent: str = _USER_AGENT,
) -> urllib.request.Request:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
    if api_key:
        headers["X-Regenold-Api-Key"] = api_key
    return urllib.request.Request(url, data=body, headers=headers, method="POST")


def post_json_with_retry(
    url: str,
    payload: list[dict[str, str]],
    api_key: str | None,
    timeout: float,
    *,
    max_retries: int = 2,
    backoff_s: float = 0.5,
    user_agent: str = _USER_AGENT,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """POST ``payload`` to ``url``; one-shot retry on transient failures.

    Drop-in replacement for the existing per-runner ``_http_post_json``
    / ``_post`` functions, with two extra trailing return values for
    retry telemetry.

    Returns
    -------
    body : dict
        Parsed JSON body. On failure, an empty shell
        ``{"answer": "", "references": [], "reasoning": None}``.
    latency_ms : float
        SUM of wall-clock latency across all attempts (including the
        backoff sleeps between them). Reflects what the user actually
        waited for.
    status : int
        HTTP status of the FINAL attempt. 0 when no HTTP status was
        ever reached (DNS / TLS / connection-refused / RemoteDisconnected
        on the first byte).
    error : str | None
        Short error tag from the final attempt; ``None`` on success.
    attempts : int
        Number of HTTP calls made. 1 = first-try success or
        non-retryable failure. 2/3 = retried.
    retried_errors : list[str]
        Errors of the failed attempts that triggered each retry. Empty
        on first-try success. Length is ``attempts - 1`` when the final
        attempt also failed, else ``attempts - 1`` (terminating on
        success).

    Retry policy
    ------------
    * Retries on: connection-layer failures classified by
      :func:`is_retryable_error` (``RemoteDisconnected``,
      ``BadStatusLine``, ``ConnectionResetError``, ``TimeoutError``,
      Windows errno 10053/10054/10060) AND HTTP 5xx responses.
    * Never retries on: 4xx HTTP, JSON decode error, ``non_dict_body``.
    * Total HTTP calls ≤ ``max_retries + 1``.
    * Backoff is exponential: ``backoff_s * (2 ** retry_idx)`` where
      ``retry_idx`` is 0 for the first backoff. Default
      ``backoff_s=0.5`` yields sleeps of 0.5 s, 1.0 s, … capped by the
      retry count.
    """
    req = _build_request(url, payload, api_key, user_agent=user_agent)

    total_latency_ms = 0.0
    retried_errors: list[str] = []
    attempts = 0
    final: AttemptResult | None = None

    for retry_idx in range(max_retries + 1):
        attempts += 1
        result = _single_attempt(req, timeout)
        total_latency_ms += result.elapsed_ms
        final = result

        if result.error is None:
            # Happy path — first 2xx response.
            break

        if not result.retryable:
            # 4xx / JSON decode / non_dict_body / unknown — stop.
            break

        if retry_idx == max_retries:
            # Out of retries — record the final error in retried_errors
            # so the caller sees the full failure trail.
            retried_errors.append(result.error)
            break

        # Retryable failure with budget left — record + back off + loop.
        retried_errors.append(result.error)
        sleep_s = backoff_s * (2 ** retry_idx)
        if sleep_s > 0:
            time.sleep(sleep_s)
            total_latency_ms += sleep_s * 1000.0

    assert final is not None  # for type-checker; the loop always sets it
    return (
        final.body,
        total_latency_ms,
        final.status,
        final.error,
        attempts,
        retried_errors,
    )

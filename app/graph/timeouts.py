"""One source of truth for the graph-query wall-clock budget.

Why this module exists
----------------------

Rounds 35 / 47-B hard-coded ``timeout_ms: int = 50`` at four call sites
(:func:`app.engines.graph_expand_2hop.expand_2hop` plus the three
:mod:`app.engines.graph_aware_retrieval` helpers). That budget was
calibrated against a local Neo4j; it is **provably too small for hosted
Neo4j Aura**.

R294 measured the real thing — the live Aura instance the R291 seed
targets, running the production 2-hop ``CROSS_REFERENCES`` Cypher::

    COLD  = 702.9 ms
    WARM  min=49.3  max=116.1  mean=64.0 ms

So under a 50 ms budget the **cold** call always times out (14x over) and
the **warm** call times out on the majority of samples (mean 64 ms). Both
live consumers sit on the hot request path:

* :mod:`app.data.kb_search` -> ``expand_2hop`` (once per retrieval),
* ``app/routes/regenold.py`` -> ``recitals_for_article`` (twice per
  request, once per top-2 reference),

and neither passes an explicit ``timeout_ms``, so both ran at the 50 ms
default. Net effect: the hosted-Neo4j graph layer contributed nothing.

The timeout is a *wall-clock* guard implemented with a
``ThreadPoolExecutor`` future. Python cannot cancel a running future, so
a timed-out query **keeps executing** to completion in the worker thread
— we pay the full query cost and then discard the answer. Raising the
budget to a value the query actually fits in therefore costs no extra
backend work; it only stops us throwing the result away.

Choosing the default
--------------------

``250`` ms is a little over 2x the worst warm sample measured (116 ms),
which leaves headroom for jitter without becoming a meaningful latency
risk: the same request spends 10-40 s in Stage-2 synthesis. The cold
~700 ms cost is deliberately **not** covered by the budget — it is paid
off-request by the boot warm-up in ``app/main.py`` instead, which is the
right place for a one-off connection/plan-cache cost.

This module is only consulted on the **hosted Neo4j** path. The R121
embedded SQLite backend answers the same traversal in-process in
sub-millisecond time and bypasses the executor and the timeout entirely,
so none of this applies to it.

Why a circuit breaker ships with the raise
------------------------------------------

A bigger budget is only safe if a *dead* graph can't spend it. R294 also
measured the failure path — the DNS-dead Aura host from R290::

    execute_read in-thread   = 1631 ms
    caller-observed @  50 ms =   55 ms
    caller-observed @ 250 ms =  252 ms

So the old 50 ms budget was, incidentally, the only thing capping a
dead-graph stall, and raising it to 250 ms would add ~197 ms **per call**
— up to ~4 graph calls on a complex request. That is a real latency
regression on a scored axis, and it is the reason a naive "just raise the
number" change would be wrong.

:func:`graph_circuit_open` closes that hole. After
``GRAPH_BREAKER_THRESHOLD`` consecutive failures the breaker opens and
every subsequent call short-circuits in microseconds for
``GRAPH_BREAKER_COOLDOWN_S``, then lets a single probe through. Net
effect on a dead graph: a few hundred ms once, then **cheaper than the
status quo** (which pays 50 ms on every call, forever). On a healthy
graph the breaker never opens and the full budget is available.

Pure stdlib, no I/O, fail-soft: a malformed or out-of-range env value
falls back to the default rather than raising.
"""
from __future__ import annotations

import os
import threading
import time

__all__ = [
    "DEFAULT_GRAPH_TIMEOUT_MS",
    "GRAPH_BREAKER_COOLDOWN_S",
    "GRAPH_BREAKER_THRESHOLD",
    "GRAPH_TIMEOUT_ENV_VAR",
    "MAX_GRAPH_TIMEOUT_MS",
    "MIN_GRAPH_TIMEOUT_MS",
    "graph_circuit_open",
    "record_graph_failure",
    "record_graph_success",
    "reset_graph_circuit",
    "resolve_graph_timeout_ms",
]

#: Env var an operator sets to override the budget, e.g.
#: ``railway variables --set REGENOLD_GRAPH_TIMEOUT_MS=500``.
GRAPH_TIMEOUT_ENV_VAR = "REGENOLD_GRAPH_TIMEOUT_MS"

#: Default wall-clock budget for a single graph query (milliseconds).
#: See the module docstring for the measurement this is derived from.
DEFAULT_GRAPH_TIMEOUT_MS = 250

#: Clamp bounds. The floor keeps a typo (``0`` / ``-1``) from disabling
#: the graph outright; the ceiling keeps one from parking a request on a
#: hung socket for an unbounded time.
MIN_GRAPH_TIMEOUT_MS = 10
MAX_GRAPH_TIMEOUT_MS = 5000


def resolve_graph_timeout_ms(explicit: int | None = None) -> int:
    """Return the wall-clock budget (ms) for one graph query.

    Args:
        explicit: A caller-supplied budget. When not ``None`` it wins
            over the environment — this is what the test-suite and any
            latency-sensitive caller use to pin a specific budget.
            Still clamped to ``[MIN, MAX]``.

    Returns:
        The resolved budget in milliseconds, always within
        ``[MIN_GRAPH_TIMEOUT_MS, MAX_GRAPH_TIMEOUT_MS]``.

    Never raises: a non-integer or absent env value yields
    :data:`DEFAULT_GRAPH_TIMEOUT_MS`.
    """
    if explicit is not None:
        return _clamp(explicit)

    raw = os.getenv(GRAPH_TIMEOUT_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_GRAPH_TIMEOUT_MS
    try:
        return _clamp(int(raw))
    except (TypeError, ValueError):
        # Fail-soft: a typo must not disable graph retrieval.
        return DEFAULT_GRAPH_TIMEOUT_MS


def _clamp(value: int) -> int:
    """Bound ``value`` to the documented range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_GRAPH_TIMEOUT_MS
    return max(MIN_GRAPH_TIMEOUT_MS, min(MAX_GRAPH_TIMEOUT_MS, n))


# ─── Circuit breaker ───────────────────────────────────────────────────────
#
# Mirrors the convention already used by ``app.llm.intent_classifier``
# (open after N consecutive failures within a cooldown). Process-local and
# lock-guarded: the recorders are called from both the request thread and
# the graph executor's worker threads.

#: Consecutive failures before the breaker opens.
GRAPH_BREAKER_THRESHOLD = 3

#: Seconds the breaker stays open before allowing one probe through.
GRAPH_BREAKER_COOLDOWN_S = 60.0

_BREAKER_ENV_VAR = "REGENOLD_GRAPH_BREAKER"

_BREAKER_LOCK = threading.Lock()
_consecutive_failures = 0
_opened_at: float | None = None


def _breaker_enabled() -> bool:
    """Breaker is ON unless explicitly disabled (``=0`` / falsy)."""
    raw = os.getenv(_BREAKER_ENV_VAR, "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def graph_circuit_open() -> bool:
    """Return ``True`` when graph queries should be skipped outright.

    Opens after :data:`GRAPH_BREAKER_THRESHOLD` consecutive failures and
    stays open for :data:`GRAPH_BREAKER_COOLDOWN_S`. After the cooldown
    it half-opens: this call returns ``False`` so exactly one probe query
    runs, and that probe's outcome (via :func:`record_graph_success` /
    :func:`record_graph_failure`) decides whether it re-opens.

    Never raises.
    """
    if not _breaker_enabled():
        return False
    with _BREAKER_LOCK:
        if _opened_at is None:
            return False
        if (time.monotonic() - _opened_at) >= GRAPH_BREAKER_COOLDOWN_S:
            # Half-open: let one probe through. Clearing the counter here
            # means a failing probe needs the full threshold again, which
            # is the conservative direction (we retry rather than stay
            # dark on a graph that may have recovered).
            _reset_locked()
            return False
        return True


def record_graph_failure() -> None:
    """Record a timeout / error. Opens the breaker at the threshold.

    No-op when the breaker is disabled, so ``REGENOLD_GRAPH_BREAKER=0`` is a
    TRUE off-switch rather than "still accumulates, just doesn't act on it".
    That matters beyond tidiness: the breaker is process-global, so an
    in-process A/B whose baseline arm runs the old 50 ms budget would
    otherwise time out, latch ``_opened_at``, and silently suppress the
    branch arm's graph calls — measuring nothing (the R263.2 cross-arm
    contamination class).
    """
    global _consecutive_failures, _opened_at
    if not _breaker_enabled():
        return
    with _BREAKER_LOCK:
        _consecutive_failures += 1
        if _consecutive_failures >= GRAPH_BREAKER_THRESHOLD and _opened_at is None:
            _opened_at = time.monotonic()


def record_graph_success() -> None:
    """Record a successful query — resets the failure streak."""
    if not _breaker_enabled():
        return
    with _BREAKER_LOCK:
        _reset_locked()


def reset_graph_circuit() -> None:
    """Force the breaker closed. Used by tests and the boot warm-up."""
    with _BREAKER_LOCK:
        _reset_locked()


def _reset_locked() -> None:
    """Clear breaker state. Caller must hold ``_BREAKER_LOCK``."""
    global _consecutive_failures, _opened_at
    _consecutive_failures = 0
    _opened_at = None

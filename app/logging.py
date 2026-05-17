"""R45 Fix 1.6 — structlog JSON configuration helper.

The bundle pins ``structlog>=24.0.0`` and several modules call
``structlog.get_logger(...)``, but no ``structlog.configure(...)`` is
ever invoked. Without it, structlog falls back to its
default-stdlib-logger pipeline — keyword args become positional repr
fragments and the output is a plaintext mix that's hard to query.

For the Regenold competition deploy, JSON logging is a quick ops win:
Railway's log viewer parses JSON natively, and downstream log shippers
(Datadog, Loki, etc.) all prefer structured input.

This module is a small, independently-callable helper. Call site is
``app/main.py`` (Fix 3 owns that file in the current sprint — leave
the call-site wiring to it). The helper is idempotent: re-calling is
a no-op after the first invocation, so the FastAPI startup hook can
safely call it without coordinating with module-import order.
"""

from __future__ import annotations

import logging
import os
import threading

_CONFIGURED = False
_LOCK = threading.Lock()


def configure_logging(level: str | int | None = None) -> None:
    """Configure structlog for JSON output to stdout.

    Args:
        level: stdlib logging level (e.g. ``"INFO"``, ``logging.DEBUG``).
            Defaults to the ``LOG_LEVEL`` env var or ``"INFO"``.

    Pipeline:
        TimeStamper(iso) → merge_contextvars → add_log_level →
        StackInfoRenderer → ExceptionPrettyPrinter → JSONRenderer

    Idempotent: subsequent calls are no-ops. Safe to call from a
    multi-threaded FastAPI startup hook.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    with _LOCK:
        if _CONFIGURED:
            return

        try:
            import structlog
        except ImportError:
            # structlog is a required dep, but staying defensive lets us
            # ship the helper even on a stripped-down dev install.
            return

        if level is None:
            level = os.environ.get("LOG_LEVEL", "INFO")
        if isinstance(level, str):
            level_int = getattr(logging, level.upper(), logging.INFO)
        else:
            level_int = level

        # Stdlib logger root — structlog wraps it; keep both honest.
        logging.basicConfig(
            format="%(message)s",
            level=level_int,
        )

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level_int),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        _CONFIGURED = True


def is_configured() -> bool:
    """Return True if :func:`configure_logging` has run successfully."""
    return _CONFIGURED


def _reset_for_tests() -> None:
    """Test hook — drop the configured flag so a fresh configure can run."""
    global _CONFIGURED
    with _LOCK:
        _CONFIGURED = False

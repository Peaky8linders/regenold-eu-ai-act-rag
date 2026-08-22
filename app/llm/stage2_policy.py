"""Stage-2 transport policy — the ONE place that decides who answers.

Operator contract (R360)
------------------------
Stage-2 LLM processing runs on **exactly two** transports, in this order:

1. **PRIMARY** — the cloudflared tunnel in front of the local
   ``claude-code-openai-wrapper``, which spends the flat **Claude Max**
   subscription (provider id ``openai_wrapper``,
   ``OPENAI_API_BASE=https://wrapper.antifragile-ai.net/v1``).
2. **FALLBACK** — the **AWS Bedrock** client (provider id ``bedrock``),
   used only when the tunnel call fails.

No Stage-2 request may reach any other provider. Before R360 four
escape hatches could silently serve a Stage-2 answer from somewhere else:

* the **Groq** tertiary fallback inside
  ``_openai_wrapper_complete_for_graph_rag`` — armed by nothing more than a
  ``GROQ_API_KEY`` being present in the environment, so a Railway deploy that
  carries the key would answer from Groq the moment the tunnel hiccuped;
* the **Gemini** secondary fallback in ``_claude_max_enhance_answer``, armed
  the same way by ``GEMINI_API_KEY``;
* the ``P2P_GRAPH_RAG_PROVIDER=gemini|anthropic|groq`` primary branches in
  ``_claude_max_enhance_answer`` and ``_stage2_complete``;
* the **fusion panel** (``app/engines/fusion.py``), whose default roster is
  ``("sonnet", "groq", "mistral")`` — so turning ``REGENOLD_FUSION_STAGE2`` on
  fanned Stage-2 out to Groq and Mistral by default;
* ``P2P_GRAPH_RAG_PROVIDER=bedrock``, which is not an *escape* but an
  **inversion** — it makes the fallback the primary and never dials the
  tunnel at all.

Why a module and not four inline ``if`` statements
--------------------------------------------------
The same reason R331 exists in this repo: a routing lever that reads
plausibly in the diff and makes **zero calls** is indistinguishable from one
that works, and this codebase has already shipped that mistake once (R329
tried three rerank placements, all three measured 0 calls). So the policy is
(a) centralised, (b) **counted** — :func:`transport_stats` reports what
actually dialled — and (c) pinned by tests that assert on those counters
rather than on the shape of the code.

Env
---
``REGENOLD_STAGE2_STRICT_TRANSPORT`` (default ``1``)
    ON  — enforce tunnel→Bedrock; refuse every other Stage-2 transport.
    OFF — restore the pre-R360 behaviour byte-for-byte (legacy escape
    hatches live again). Provided because every behavioural flag in this
    repo must be env-reversible for A/B, **not** because OFF is supported:
    the operator contract is strict-ON.

This flag flips which model writes the answer, so it is registered in
``_engine_cache_key`` (``AGENTS.md`` invariant #4).
"""
from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

#: Provider id of the cloudflared tunnel → Claude Max wrapper.
STAGE2_PRIMARY = "openai_wrapper"
#: Provider id of the AWS Bedrock fallback.
STAGE2_FALLBACK = "bedrock"
#: The complete set of transports Stage-2 may use, in precedence order.
STAGE2_CHAIN: tuple[str, str] = (STAGE2_PRIMARY, STAGE2_FALLBACK)

_TRUTHY = ("1", "true", "yes", "on")

# ── counters ────────────────────────────────────────────────────────────────
# Cheap, process-wide, lock-guarded. Read by tests (to PROVE the chain fired)
# and by ``/healthz/llm`` (to show the operator which leg is carrying traffic).
_STATS_LOCK = threading.Lock()
_STATS: dict[str, int] = {
    "primary_attempts": 0,
    "primary_ok": 0,
    "primary_failed": 0,
    "fallback_attempts": 0,
    "fallback_ok": 0,
    "fallback_failed": 0,
    "refused": 0,
}
#: Provider ids that were refused, with a count each — names the leak.
_REFUSALS: dict[str, int] = {}


def strict_transport_enabled() -> bool:
    """True when the tunnel→Bedrock contract is enforced. Default ON.

    Read on every call (never cached at import) so a Railway env rebind takes
    effect on the next request without a worker restart — the same discipline
    ``_graph_rag_provider`` follows.
    """
    return os.getenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "1").strip().lower() in _TRUTHY


def stage2_chain() -> tuple[str, ...]:
    """The ordered Stage-2 transports. Strict mode → ``(tunnel, bedrock)``."""
    return STAGE2_CHAIN


def is_stage2_provider_allowed(provider: str | None) -> bool:
    """Is ``provider`` permitted to serve a Stage-2 request?

    Non-strict mode allows everything, which is exactly the pre-R360
    behaviour the OFF switch is there to restore.
    """
    if not strict_transport_enabled():
        return True
    return (provider or "").strip().lower() in STAGE2_CHAIN


def refuse(provider: str | None, *, where: str) -> None:
    """Record — loudly — that a Stage-2 call to ``provider`` was blocked.

    ``where`` names the call site so an operator reading the log knows which
    escape hatch tried to open, not merely that one did.
    """
    name = (provider or "unknown").strip().lower() or "unknown"
    with _STATS_LOCK:
        _STATS["refused"] += 1
        _REFUSALS[name] = _REFUSALS.get(name, 0) + 1
    logger.warning(
        "stage2_policy.refused provider=%s at=%s — Stage-2 is pinned to "
        "%s (primary) → %s (fallback). Set "
        "REGENOLD_STAGE2_STRICT_TRANSPORT=0 to restore the legacy chain.",
        name, where, STAGE2_PRIMARY, STAGE2_FALLBACK,
    )
    try:
        from app.integrations.regenold.reasoning_trace import record_note
        record_note(f"stage2_transport_refused:{name}@{where}")
    except Exception:  # noqa: BLE001 — tracing must never break Stage-2
        pass


def record_attempt(provider: str) -> None:
    """Count a dial on ``provider`` (one of :data:`STAGE2_CHAIN`)."""
    key = "primary" if provider == STAGE2_PRIMARY else "fallback"
    with _STATS_LOCK:
        _STATS[f"{key}_attempts"] += 1


def record_result(provider: str, *, ok: bool) -> None:
    """Count the outcome of a dial on ``provider``."""
    key = "primary" if provider == STAGE2_PRIMARY else "fallback"
    with _STATS_LOCK:
        _STATS[f"{key}_{'ok' if ok else 'failed'}"] += 1


def transport_stats() -> dict[str, int | dict[str, int]]:
    """Snapshot of the counters. See the module docstring for why these exist.

    ``refused_by_provider`` is the one to read when auditing: a non-empty map
    means something in the process tried to answer Stage-2 off-contract.
    """
    with _STATS_LOCK:
        snap: dict[str, int | dict[str, int]] = dict(_STATS)
        snap["refused_by_provider"] = dict(_REFUSALS)
    return snap


def reset_transport_stats() -> None:
    """Zero the counters. Used by tests and by a fresh eval run."""
    with _STATS_LOCK:
        for k in _STATS:
            _STATS[k] = 0
        _REFUSALS.clear()


def resolve_stage2_provider(env_provider: str | None) -> str:
    """Map a raw ``P2P_GRAPH_RAG_PROVIDER`` value to the Stage-2 primary.

    Strict mode collapses **every** value to the tunnel. That deliberately
    includes ``bedrock``: Bedrock is the fallback leg, and honouring it as a
    primary would mean the tunnel is never dialled — an inversion of the
    operator contract, not merely a detour. It also includes ``cli``, which
    is not a transport at all (it is the deterministic no-LLM path); callers
    gate on ``_stage2_provider_enabled`` before ever asking this.
    """
    raw = (env_provider or "").strip().lower()
    if not strict_transport_enabled():
        return raw
    if raw and raw not in STAGE2_CHAIN and raw not in ("", "auto", "cli"):
        refuse(raw, where="resolve_stage2_provider")
    return STAGE2_PRIMARY


__all__ = [
    "STAGE2_CHAIN",
    "STAGE2_FALLBACK",
    "STAGE2_PRIMARY",
    "is_stage2_provider_allowed",
    "record_attempt",
    "record_result",
    "refuse",
    "reset_transport_stats",
    "resolve_stage2_provider",
    "stage2_chain",
    "strict_transport_enabled",
    "transport_stats",
]

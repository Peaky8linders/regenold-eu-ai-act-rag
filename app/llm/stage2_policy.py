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


# ── destination pinning (R360.7) ────────────────────────────────────────────
#
# Everything above pins the provider *id*. That is not the same as pinning the
# *destination*: ``openai_wrapper`` means "go through the OpenAI-compatible
# client", and where that client points is whatever ``OPENAI_API_BASE`` says.
# Measured on this repo before R360.7:
#
#     OPENAI_API_BASE=https://openrouter.ai/api/v1
#       -> resolved Stage-2 base URL: https://openrouter.ai/api/v1
#       -> is_stage2_provider_allowed("openai_wrapper"): True
#
# One env var sent every Stage-2 request to a third party while satisfying the
# provider policy and every test written for it. The id says Claude Max; the
# packet goes to OpenRouter. So the contract has to name hosts too.

#: Hosts that ARE the Claude Max path: the cloudflared tunnel, and a wrapper
#: running on the operator's own machine (what ``ab_judge`` drives locally).
STAGE2_PRIMARY_HOSTS: tuple[str, ...] = (
    "wrapper.antifragile-ai.net",
    "127.0.0.1",
    "localhost",
    "::1",
)


def _host_of(base_url: str) -> str:
    from urllib.parse import urlsplit

    try:
        return (urlsplit(base_url).hostname or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""


def _normalise_host_entry(entry: str) -> str:
    """Reduce one configured allowlist entry to the shape ``_host_of`` produces.

    R365 — the two sides of this comparison used to speak different languages.
    The candidate went through ``urlsplit(...).hostname``; the allowlist went
    through nothing but ``strip().lower()``. So the single most likely thing an
    operator pastes — **the URL they already have** — matched nothing. Measured
    before the fix, against ``https://wrapper.antifragile-ai.net/v1``::

        hosts="https://wrapper.antifragile-ai.net/v1"  -> allowed = False
        hosts="wrapper.antifragile-ai.net:443"         -> False
        hosts=" Wrapper.Antifragile-AI.net "           -> True

    Only the bare-host shape worked. The other two refuse **every** primary
    request, and ``_graph_rag_impl`` answers a refusal by falling straight to
    leg 2 — so a typo-free, entirely plausible env value degrades 100% of
    Stage-2 traffic to Bedrock/Qwen, which this repo measures at −0.27 answer
    correctness. Silently, with the tunnel healthy the whole time.

    Both sides now run through :func:`_host_of`, which is the point: not "a
    normalisation that resembles the other one" but literally the same
    function, so the two cannot drift apart again.
    """
    raw = entry.strip()
    if not raw:
        return ""
    if "://" in raw or raw.startswith("//"):
        candidate = raw
    elif "[" not in raw and raw.count(":") >= 2:
        # A bare IPv6 literal (``::1`` ships in the defaults, so the env parser
        # has to read it too). ``urlsplit`` only yields a hostname for a
        # BRACKETED literal; unbracketed it partitions on the last ``:``, calls
        # the tail a port and returns ``None`` — dropping the entry entirely.
        candidate = f"//[{raw}]"
    else:
        # No netloc means no ``hostname``, and a bare ``host:443`` is worse than
        # that: ``wrapper.antifragile-ai.net`` is a syntactically valid URL
        # SCHEME, so ``urlsplit`` reads the host as the scheme and leaves the
        # netloc empty. Prepending ``//`` puts every shape on the URL path.
        candidate = f"//{raw}"
    return _host_of(candidate)


def allowed_primary_hosts() -> tuple[str, ...]:
    """Hosts the Stage-2 primary may dial.

    ``REGENOLD_STAGE2_PRIMARY_HOSTS`` (comma-separated) replaces the default —
    the operator may rename their tunnel. Entries are normalised the same way
    the candidate URL is (see :func:`_normalise_host_entry`), so a bare host, a
    full URL, a ``host:port`` and any casing all name the same destination.

    It cannot be set to *empty*: a blank value — or one whose every entry
    normalises away — falls back to the defaults rather than disabling the
    check, so the guard cannot be switched off by accident, only by turning
    strict mode off deliberately.
    """
    raw = os.getenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "").strip()
    if not raw:
        return STAGE2_PRIMARY_HOSTS
    hosts = tuple(h for h in map(_normalise_host_entry, raw.split(",")) if h)
    return hosts or STAGE2_PRIMARY_HOSTS


def is_primary_base_url_allowed(base_url: str) -> bool:
    """Does ``base_url`` actually point at the Claude Max wrapper?"""
    if not strict_transport_enabled():
        return True
    return _host_of(base_url) in allowed_primary_hosts()


def check_primary_base_url(base_url: str) -> bool:
    """Same, but records a refusal naming the host when it fails."""
    if is_primary_base_url_allowed(base_url):
        return True
    refuse(f"base_url:{_host_of(base_url) or 'unparseable'}",
           where="openai_wrapper_complete.base_url")
    return False


__all__ += [
    "STAGE2_PRIMARY_HOSTS",
    "allowed_primary_hosts",
    "check_primary_base_url",
    "is_primary_base_url_allowed",
]


def stage2_fallback_model() -> str:
    """Model the Bedrock leg should serve, or ``""`` for the tier default.

    R360.10 — the two Stage-2 fallback call sites pass no ``model_override``, so
    leg 2 serves ``BEDROCK_RAG_MODEL`` / ``BEDROCK_COMPLEX_MODEL``: **Qwen 3 32B
    / 235B**. That is a deliberate choice — commit ``a65fa87`` wired the Qwen
    tier on purpose — but it is worth stating plainly, because the fallback for
    a *Claude Opus* primary is then a different model family, and an answer
    served from leg 2 is not the answer any A/B measured.

    Default ``""`` keeps exactly that behaviour. Set
    ``REGENOLD_STAGE2_BEDROCK_MODEL=eu.anthropic.claude-opus-4-8`` (or
    ``claude-opus-4-6`` — ``CLAUDE.md`` R328.2 records the newer pins returning
    ``AccessDenied`` on the current key vintage) to keep the fallback in the
    same family as the primary. That is a quality decision for the operator and
    it changes answer content, so it is a lever here, not a new default.
    """
    return os.getenv("REGENOLD_STAGE2_BEDROCK_MODEL", "").strip()


__all__ += ["stage2_fallback_model"]

"""RAG-Fusion query expansion + reciprocal rank fusion (R39 / B8).

When a paraphrase provider is available and the intent suggests a
single-anchor question, ask Sonnet 4.6 (the frontier tier — no Haiku,
R346.2) for 3 paraphrases. Each paraphrase runs through the existing
retrieval stack independently; reciprocal rank fusion (RRF) combines the
result lists.

R346 — the paraphrase transport follows the ACTIVE Stage-2 provider:
under ``P2P_GRAPH_RAG_PROVIDER=bedrock`` the call goes to Bedrock's own
Sonnet 4.6, NOT the Claude-Max wrapper — the operator keeps the tunnel
for the live re-evaluation, and mixing transports mid-A/B contaminates
both arms. Every other provider keeps the historical wrapper path.

Fail-soft: no provider / circuit open / any exception → return
[original] only.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Iterable
from typing import Any

from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    get_openai_wrapper_provider,
    is_openai_wrapper_enabled,
)

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You generate 2-3 paraphrases of EU AI Act questions for retrieval "
    "expansion. Each paraphrase keeps the same factual question but "
    "varies phrasing using professional and precise compliance terminology (focusing on formal legal phrasings, specific regulatory terms, and general compliance concepts).\n\n"
    "CRITICAL TONE AND WORDING RULES:\n"
    "1. Strictly respect and enforce the official professional tone and wording of the EU AI Act. Do not use informal or non-professional language.\n"
    "2. Always use official terminology: \"provider\" (never developer/creator), \"deployer\" (never user/customer), \"operator\", \"importer\", \"distributor\", \"authorised representative\".\n"
    "3. Use official risk-tier classifications: \"prohibited AI practices\" (unacceptable risk), \"high-risk AI systems\", \"limited-risk AI systems\", \"minimal-risk\", \"general-purpose AI models\" (GPAI models).\n"
    "4. Phrasing must be neutral, objective, and in the third person. Do not address the reader as \"you\".\n\n"
    'Respond with STRICT JSON: {"paraphrases": ["...", "..."]}. No prose.'
)

_USER_TEMPLATE = "Question: {q}\n\nReturn 2-3 paraphrases as JSON."

#: Wrapper paraphrase read budget.
#:
#: ⚠ R350 — this was a hard-coded ``2.0`` with no override, and the comment
#: below justified the Bedrock sibling's larger budget on the grounds that the
#: wrapper is the FAST transport. The repo's own measurements say the opposite:
#: the Claude-Max wrapper has a fixed floor of 12-17 s for a five-token request
#: (R102), while R328.2's re-verified Bedrock invokes came back in 275-1595 ms.
#: So the SLOWER transport had the SMALLER budget. R341 sized 2.0 s against the
#: Haiku paraphrase tier; R346.2 then swapped that tier for Sonnet 4.6 and left
#: the budget alone, which would fail every wrapper paraphrase and read as an
#: inert lever rather than as a timeout. Now symmetric with Bedrock and
#: overridable.
_TIMEOUT_ENV = "REGENOLD_QUERY_EXPANSION_TIMEOUT"
_DEFAULT_TIMEOUT = 20.0

# R346 — Bedrock's first call carries cold-start latency; a 2 s budget there
# would fail every paraphrase and read as an inert lever (attempts>0,
# expanded=0, branch == baseline on the wire).
_BEDROCK_TIMEOUT_ENV = "REGENOLD_QUERY_EXPANSION_BEDROCK_TIMEOUT"
_DEFAULT_BEDROCK_TIMEOUT = 8.0


def _read_timeout(env: str, default: float) -> float:
    """Read a timeout FRESH per call, never at import.

    ⚠ R350 — ``_BEDROCK_TIMEOUT`` used to be a module-level constant while
    ``regenold.py`` registered it in ``_engine_cache_key`` with the comment
    "read fresh per call by query_expansion". It was not. That combination is
    strictly WORSE than an unregistered flag: the key makes the two arms
    cache-distinct so the engine genuinely re-runs, the paraphrase call is
    non-deterministic so the outputs differ, the fire check therefore PASSES —
    and the harness prints a full axis table for a value that was identical in
    both arms. An unkeyed frozen flag at least reports INERT.

    A malformed value falls back to the default instead of raising: the bare
    ``float()`` used to raise at IMPORT, and the caller's import sits inside a
    broad ``except Exception``, so a typo silently switched expansion off with
    no error surfaced to the operator.
    """
    raw = os.getenv(env, "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        logger.warning(
            "query_expansion: %s=%r is not a number — using %.1fs", env, raw, default
        )
        return default
    return val if val > 0 else default

# R346.2 — NO Haiku on the live path: paraphrases use the frontier tier like
# every other Stage-2 call. Sonnet 4.6 is the default (the judge tier — a
# paraphrase is a light task, Opus would buy nothing), pinned up with
# ``REGENOLD_QUERY_EXPANSION_MODEL=claude-opus-4-6`` if the operator wants
# the generation tier. Fresh read per call (R263.2).
_DEFAULT_PARAPHRASE_MODEL = "claude-sonnet-4-6"


def _paraphrase_model() -> str:
    return (
        os.getenv("REGENOLD_QUERY_EXPANSION_MODEL", "").strip()
        or _DEFAULT_PARAPHRASE_MODEL
    )

# ── Call instrumentation (R341, mirroring cohere_rerank's R331 counters) ────
#
# The R329 lesson: a placement that looks right in the diff but never issues
# its call reads +0.0000 on every axis, indistinguishable from "the lever
# does not work". Every A/B of this feature must assert
# ``query_expansion_stats()["attempts"] > 0`` on the ON arm before any
# result is believed.
_STATS: dict[str, int] = {
    "attempts": 0, "expanded_calls": 0, "paraphrases": 0,
    "failed_transport": 0, "failed_parse": 0, "noop": 0, "no_provider": 0,
}

#: ⚠ R350 — the counters are mutated from FastAPI's anyio worker threadpool
#: (``regenold_eu_ai_act_ask`` is a sync ``def``, so concurrent requests run on
#: real OS threads) and ``_bump`` was an unlocked read-modify-write. Measured
#: under contention — 16 threads x 30,000 increments — it lost 337,986-370,146
#: of 480,000 counts, while ``cohere_rerank``'s identically-shaped counter lost
#: ZERO because that one has a lock. One concept, two definitions, and only the
#: sibling was hardened. An undercount fails in the UNSAFE direction here: the
#: counter's whole job is to prove ``attempts > 0`` before an A/B number is
#: believed, so drifting toward zero makes a working lever look inert.
_STATS_LOCK = threading.Lock()


def query_expansion_stats() -> dict[str, int]:
    """Snapshot of the expansion call counters.

    ``attempts``          — LLM calls actually issued to the paraphrase provider.
    ``expanded_calls``    — calls that returned at least one usable paraphrase.
    ``paraphrases``       — total paraphrases added to the union surface.
    ``failed_transport``  — exception / provider error / timeout / 429.
    ``failed_parse``      — provider answered, reply was not usable JSON.
    ``noop``              — provider answered cleanly with zero paraphrases.
    ``no_provider``       — gate on, but no paraphrase transport available.

    ``attempts == 0`` means the feature never ran; treat any downstream
    metric as UNMEASURED, not as evidence of no effect.

    ⚠ R350 — this used to be ``{attempts, expanded, failed}`` and BOTH of the
    latter were wrong. ``expanded`` was documented as "total paraphrase count"
    but did a bare ``+1`` per successful call, so a 20-row arm returning three
    paraphrases each reported 20 where the truth was 60 — a 3x error on the one
    number describing how much retrieval surface the lever bought (the repo's
    own "a NAME must describe what the code COMPUTES" rule). ``failed``
    collapsed FIVE outcomes into one indistinguishable bucket, including the
    two that must never be confused: "the transport died" and "it ran fine and
    found nothing". Measured, a stubbed transport failure and a clean empty
    reply produced byte-identical counters — so the instrument built to detect
    a dead lever could not tell a dead transport from a working one.
    """
    with _STATS_LOCK:
        return dict(_STATS)


def reset_query_expansion_stats() -> None:
    """Zero the counters — per-arm reset for an A/B harness."""
    with _STATS_LOCK:
        for key in _STATS:
            _STATS[key] = 0


def _bump(field: str, n: int = 1) -> None:
    with _STATS_LOCK:
        _STATS[field] = _STATS.get(field, 0) + n


_ENV_GATE = "REGENOLD_QUERY_EXPANSION"


def is_enabled() -> bool:
    """``REGENOLD_QUERY_EXPANSION`` — **DEFAULT OFF**, fresh env read per call.

    Default OFF because it adds an LLM round-trip per request (latency + cost)
    and external egress of the partner question; the A/B decides whether the
    recall it buys beats that price. Fresh read per call (R263.2) so an
    in-process A/B can flip it between arms.
    """
    return (
        os.getenv(_ENV_GATE, "0").strip().lower()
        in ("1", "true", "yes", "on")
    )


def _active_provider() -> str:
    """The SELECTED provider, lowercased. One definition, both call sites."""
    return os.getenv("P2P_GRAPH_RAG_PROVIDER", "").strip().lower()


class _TransportUnavailable:
    """A ``.text`` / ``.error`` stand-in for "the selected transport is gone".

    Shaped like ``OpenAIWrapperResponse`` / ``BedrockResponse`` so the caller
    still never branches on transport — it lands on the ordinary
    ``resp.error`` path and increments ``failed_transport``, which is exactly
    what it is.
    """

    __slots__ = ("text", "error")

    def __init__(self, error: str) -> None:
        self.text = ""
        self.error = error


def _paraphrase_provider_available() -> bool:
    """True when SOME provider can serve the paraphrase call.

    R346 — the historical gate (``is_openai_wrapper_enabled``) silently
    disables expansion on a Bedrock-only run, where the wrapper is not the
    transport by design. Bedrock counts as available when selected AND
    its credentials are present.

    ⚠ R350 — the order was wrong, and it made R346's whole branch DEAD CODE.
    ``is_openai_wrapper_enabled()`` returns False only for the literal string
    ``cli``, so under ``P2P_GRAPH_RAG_PROVIDER=bedrock`` it returned **True**
    and short-circuited before the Bedrock check ever ran. Measured with
    ``provider=bedrock`` and no AWS credential (reachable — ``evals/harness/``
    does not load dotenv): the gate said available, and ``_complete_paraphrase``
    then fell through to the Claude-Max wrapper, which is exactly what this
    module's own docstring says must never happen ("mixing transports mid-A/B
    contaminates both arms"). Ask the SELECTED provider first.
    """
    provider = _active_provider()
    if provider == "bedrock":
        try:
            from app.llm.bedrock_client import (  # noqa: PLC0415
                is_bedrock_provider_enabled,
            )
            return is_bedrock_provider_enabled()
        except Exception:  # noqa: BLE001 — boto3 is an optional wheel
            return False
    return is_openai_wrapper_enabled()


def _complete_paraphrase(user: str) -> Any:
    """One paraphrase completion through the ACTIVE provider.

    Returns an object carrying ``.text`` / ``.error`` — both the wrapper's
    ``OpenAIWrapperResponse`` and ``BedrockResponse`` satisfy that shape,
    so the caller never branches on transport.

    ⚠ R350 — under ``provider=bedrock`` this NO LONGER falls through to the
    wrapper. It used to, silently, whenever Bedrock was unavailable, with only
    a ``logger.debug`` (disabled at runtime — nothing configures logging under
    ``app/``) to say so. That is transport mixing mid-A/B: the Bedrock arm's
    paraphrases were served by the Claude-Max wrapper at a different budget and
    a different model routing, and ``expanded_calls`` counted them identically.
    A missing transport is now an ERROR the counters can see, not a substitution
    nobody records.
    """
    if _active_provider() == "bedrock":
        try:
            from app.llm.bedrock_client import (  # noqa: PLC0415
                BedrockRequest,
                complete_with_fallback,
                is_bedrock_provider_enabled,
            )
            if is_bedrock_provider_enabled():
                return complete_with_fallback(BedrockRequest(
                    system=_SYSTEM_PROMPT,
                    user=user,
                    # R346.2 — frontier tier: alias -> eu.anthropic.claude-sonnet-4-6.
                    model=_paraphrase_model(),
                    max_tokens=200,
                    temperature=0.3,
                    timeout_seconds=_read_timeout(
                        _BEDROCK_TIMEOUT_ENV, _DEFAULT_BEDROCK_TIMEOUT),
                ))
        except Exception as exc:  # noqa: BLE001 — fail-soft
            logger.warning(
                "query_expansion_bedrock_unavailable: %s", str(exc)[:160]
            )
        # Bedrock is the SELECTED transport and could not serve. Do NOT hop to
        # the wrapper: a contaminated arm is worse than a missing paraphrase,
        # because it still produces a number.
        return _TransportUnavailable(
            "bedrock selected but unavailable — refusing to hop to the wrapper"
        )
    # Historical path: Claude Max via the wrapper (OPENAI_API_BASE).
    return get_openai_wrapper_provider().complete(OpenAIWrapperRequest(
        system=_SYSTEM_PROMPT,
        user=user,
        # R346.2 — frontier tier, same env override as the Bedrock path.
        model=_paraphrase_model(),
        max_tokens=200,
        temperature=0.3,
        timeout_seconds=_read_timeout(_TIMEOUT_ENV, _DEFAULT_TIMEOUT),
    ))


def expand_query(question: str, *, intent_label: str = "") -> list[str]:
    """Return list of queries (original first, then paraphrases).

    Always includes the original. Returns [original] on any failure
    path (no provider, circuit open, parse error, timeout).
    """
    queries = [question.strip()]
    if not queries[0]:
        return queries
    if not _paraphrase_provider_available():
        # R350 — distinguishable from "ran and found nothing": this used to
        # return before any counter moved, so gate-on-but-no-transport read
        # identically to gate-off.
        _bump("no_provider")
        return queries
    _bump("attempts")
    try:
        start = time.perf_counter()
        resp = _complete_paraphrase(_USER_TEMPLATE.format(q=queries[0][:1000]))
    except Exception as exc:  # noqa: BLE001 — fail-soft
        logger.debug("query_expansion_exception: %s", str(exc)[:160])
        _bump("failed_transport")
        return queries
    if resp.error:
        logger.debug("query_expansion_provider_error: %s", resp.error[:160])
        _bump("failed_transport")
        return queries
    try:
        # Extract first JSON object from response text
        text = (resp.text or "").strip()
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx == -1 or end_idx == -1:
            _bump("failed_parse")
            return queries
        data = json.loads(text[start_idx:end_idx + 1])
        for p in (data.get("paraphrases") or [])[:3]:
            p = (p or "").strip()
            if p and p not in queries:
                queries.append(p)
    except (json.JSONDecodeError, ValueError, AttributeError):
        _bump("failed_parse")
        return queries
    if len(queries) == 1:
        # The provider answered but produced no usable paraphrase — an
        # attempt that bought nothing. NOT a failure: the transport worked.
        _bump("noop")
        return queries
    _bump("expanded_calls")
    _bump("paraphrases", len(queries) - 1)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.debug("query_expansion_ok: %d paraphrases in %d ms", len(queries) - 1, elapsed_ms)
    return queries


def reciprocal_rank_fusion(
    ranked_lists: Iterable[Iterable[str]],
    k: int = 60,
) -> list[str]:
    """Combine multiple ranked lists via RRF.

    score(d) = sum_l 1 / (k + rank_l(d)). Default k=60 per the
    canonical Cormack et al. 2009 paper.
    """
    scores: dict[str, float] = {}
    insertion_order: dict[str, int] = {}
    n_inserted = 0
    for lst in ranked_lists:
        for rank, doc in enumerate(lst, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
            if doc not in insertion_order:
                insertion_order[doc] = n_inserted
                n_inserted += 1
    # Sort by score desc, then by insertion order asc (stable tie-break)
    return sorted(scores.keys(), key=lambda d: (-scores[d], insertion_order[d]))

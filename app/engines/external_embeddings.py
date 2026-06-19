"""External high-dimensional dense embeddings provider (Cohere / OpenAI).

Natively runs on Railway or local Windows/Linux dev machines via API keys.
Integrates with the C-accelerated TurboQuant vector store for extreme recall.

R112 (perf finding #11) hardening — this module sits inside the dense-
retrieval hot path (``turboquant_index._build`` probes it on the first
dense query of every worker), so misfires are paid in first-request
latency, a scored competition axis:

* **Chat-wrapper skip** — ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` are the
  documented Claude-Max *chat* wrapper vars on every production deploy
  (``OPENAI_API_KEY=dummy`` + a tunnel base). The wrapper implements
  ``/chat/completions`` only — no ``/embeddings`` — so probing it was a
  doomed 2-30 s POST per worker. When ``OPENAI_API_BASE`` targets the
  wrapper (loopback host, or a host containing ``wrapper``), the openai
  embeddings path now reports unavailable. Operators with a REAL
  OpenAI-compatible embeddings endpoint on such a host opt in explicitly
  via ``REGENOLD_EXTERNAL_EMBEDDINGS=1``; ``=0`` force-disables the
  module entirely.
* **Negative-probe cache** — a failed openai-path fetch caches the
  (endpoint, model) pair so subsequent calls (including the per-query
  ``_embed_query`` path) return ``None`` immediately instead of
  re-paying the timeout. Cohere failures are deliberately NOT cached
  (dedicated canonical embeddings API — failures there are transient).
* **Pooled client + short timeout** — one module-level ``httpx.Client``
  (``httpx.Timeout(10.0, connect=3.0)``) replaces the fresh
  per-call client with a blanket 30 s timeout.
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

import httpx

if TYPE_CHECKING:
    import numpy as np  # type: ignore

logger = logging.getLogger(__name__)


# ── Configuration & Env Gates ───────────────────────────────────────────

COHERE_API_URL = "https://api.cohere.com/v1/embed"
OPENAI_API_URL = "https://api.openai.com/v1/embeddings"

# Explicit operator override for the openai-path availability heuristic.
# Unset/empty → auto (chat-wrapper detection governs); truthy → force
# enable (skip wrapper detection — e.g. a genuine local embeddings
# server); falsy → force disable the whole module.
_OPT_IN_ENV = "REGENOLD_EXTERNAL_EMBEDDINGS"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})

# Hosts that can only be the local Claude-Max chat wrapper (or the test
# suite's dead-port no-live-calls guard ``http://127.0.0.1:1/v1``) — never
# a real OpenAI embeddings endpoint, absent explicit opt-in.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})

# R112 — short, split timeout for the pooled client. connect=3 bounds a
# black-holed host; read=10 is plenty for a 50-doc embeddings batch.
_CLIENT_TIMEOUT = httpx.Timeout(10.0, connect=3.0)

_CLIENT_LOCK = threading.Lock()
_CLIENT: httpx.Client | None = None

# Negative-probe cache: ``(endpoint_url, model)`` pairs that failed on the
# openai path. Once a pair fails, every later call against the same config
# returns None instantly (the precomputed-SVD fallback serves dense
# retrieval). Process-lifetime by design — reset requires a restart or
# :func:`_reset_probe_cache_for_tests`.
_NEGATIVE_PROBE_LOCK = threading.Lock()
_NEGATIVE_PROBES: set[tuple[str, str]] = set()


def _get_client() -> httpx.Client:
    """Process-wide pooled client (double-checked locking)."""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                client = httpx.Client(
                    timeout=_CLIENT_TIMEOUT,
                    limits=httpx.Limits(
                        max_keepalive_connections=5,
                        max_connections=10,
                    ),
                )
                atexit.register(client.close)
                _CLIENT = client
    return _CLIENT


def _opt_in_mode() -> Literal["on", "off", "auto"]:
    raw = os.getenv(_OPT_IN_ENV, "").strip().lower()
    if raw in _TRUTHY:
        return "on"
    if raw in _FALSY:
        return "off"
    return "auto"


def _targets_chat_wrapper(api_base: str) -> bool:
    """True when ``api_base`` can only be the Claude-Max chat wrapper.

    The wrapper serves Chat Completions only (no ``/embeddings``); its
    documented bases are ``http://127.0.0.1:8000/v1`` (local) and the
    ``wrapper.antifragile-ai.net`` Cloudflare tunnel. Loopback hosts and
    hosts containing ``wrapper`` are treated as the chat wrapper.
    """
    if not api_base:
        return False
    try:
        host = (urlparse(api_base).hostname or "").lower()
        if not host:
            # Scheme-less base like "127.0.0.1:8000/v1" — parse manually.
            host = api_base.split("//")[-1].split("/")[0].split(":")[0].lower()
    except Exception:  # noqa: BLE001 — fail-open (heuristic only)
        return False
    if not host:
        return False
    return host in _LOOPBACK_HOSTS or "wrapper" in host


def _resolve_openai_url() -> str:
    """Resolve the openai-path embeddings endpoint from the env base."""
    api_base = os.getenv("OPENAI_API_BASE", OPENAI_API_URL).strip()
    url = api_base
    if api_base.endswith("/v1"):
        url = f"{api_base}/embeddings"
    elif api_base.endswith("/v1/"):
        url = f"{api_base}embeddings"
    elif "embeddings" not in api_base:
        url = (
            f"{api_base}/embeddings"
            if not api_base.endswith("/")
            else f"{api_base}embeddings"
        )
    return url


def _openai_negative_key() -> tuple[str, str]:
    model = os.getenv("REGENOLD_EXTERNAL_EMBEDDING_MODEL", "text-embedding-3-small")
    return (_resolve_openai_url(), model)


def _openai_probe_failed() -> bool:
    with _NEGATIVE_PROBE_LOCK:
        return _openai_negative_key() in _NEGATIVE_PROBES


def _record_openai_probe_failure() -> None:
    with _NEGATIVE_PROBE_LOCK:
        _NEGATIVE_PROBES.add(_openai_negative_key())


def _reset_probe_cache_for_tests() -> None:
    """Clear the negative-probe cache. Test-only — not public API."""
    with _NEGATIVE_PROBE_LOCK:
        _NEGATIVE_PROBES.clear()


def is_available() -> bool:
    """True if an external embeddings backend is configured AND usable.

    False when no key/base is set, when ``REGENOLD_EXTERNAL_EMBEDDINGS=0``,
    when ``OPENAI_API_BASE`` targets the Claude-Max chat wrapper (which
    has no ``/embeddings`` endpoint), or when a previous openai-path
    probe against the current config already failed (negative cache).
    """
    provider = _get_provider()
    if provider is None:
        return False
    if provider == "openai" and _openai_probe_failed():
        return False
    return True


def _get_provider() -> Literal["cohere", "openai", None]:
    mode = _opt_in_mode()
    if mode == "off":
        return None
    # Cohere is a dedicated, canonical embeddings API — a present
    # ``COHERE_API_KEY`` is itself the explicit opt-in.
    if os.getenv("COHERE_API_KEY"):
        return "cohere"
    # R127 — the OpenAI embeddings path now requires EXPLICIT opt-in
    # (``REGENOLD_EXTERNAL_EMBEDDINGS=1`` ⇒ mode == "on").
    #
    # In this deployment ``OPENAI_API_KEY`` / ``OPENAI_API_BASE`` are the
    # Claude-Max *chat* wrapper vars (Chat Completions only — no
    # ``/embeddings`` endpoint). Auto-enabling the openai embeddings path
    # off their mere presence made a doomed network round-trip on the dense
    # hot path — the build probe AND every ``_use_external`` per-query call
    # (the "slow network call per role-noun row"). The R112 wrapper-host
    # heuristic only caught loopback / ``wrapper`` hosts; an unset base
    # (``env -u OPENAI_API_BASE``) still resolved to ``api.openai.com`` and
    # paid the connect timeout. Requiring explicit opt-in removes the entire
    # accidental-network class: by default the in-process TF-IDF→SVD
    # turboquant index (``app/engines/turboquant_index.py``) serves dense
    # retrieval, sub-ms, $0, no tunnel. Operators with a REAL
    # OpenAI-compatible embeddings endpoint opt in via
    # ``REGENOLD_EXTERNAL_EMBEDDINGS=1`` + ``OPENAI_API_BASE``.
    if mode == "on" and (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_BASE")):
        return "openai"
    return None


def get_embedding(
    texts: str | list[str],
    *,
    is_query: bool = False,
) -> np.ndarray | None:
    """Fetch high-dimensional dense embeddings from Cohere or OpenAI.

    Automatically handles request batching (chunks of 50) to prevent hitting
    upstream API limits (Cohere max 96; OpenAI max limits).

    Returns:
        np.ndarray of shape (dim,) or (n_texts, dim) as float32,
        or None on network failure / invalid API key (Graceful Fallback).
    """
    import numpy as np  # noqa: PLC0415

    provider = _get_provider()
    if not provider:
        return None
    # R112 — negative-probe cache: don't re-pay the timeout per call when
    # this exact openai config already failed in this process.
    if provider == "openai" and _openai_probe_failed():
        return None

    single_input = isinstance(texts, str)
    input_list = [texts] if single_input else list(texts)

    # Strip leading/trailing whitespaces to avoid API quirks
    input_list = [t.strip() for t in input_list]
    if not input_list or all(not t for t in input_list):
        return None

    try:
        batch_size = 50
        embeddings: list[list[float]] = []
        client = _get_client()

        if provider == "cohere":
            api_key = os.getenv("COHERE_API_KEY", "").strip()
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            # Cohere embed v3: Search Query for queries, Search Document for corpus docs
            input_type = "search_query" if is_query else "search_document"
            model = os.getenv("REGENOLD_EXTERNAL_EMBEDDING_MODEL", "embed-english-v3.0")

            for idx in range(0, len(input_list), batch_size):
                batch = input_list[idx : idx + batch_size]
                payload = {
                    "texts": batch,
                    "model": model,
                    "input_type": input_type,
                }
                res = client.post(COHERE_API_URL, headers=headers, json=payload)
                res.raise_for_status()
                data = res.json()
                embeddings.extend(data["embeddings"])

        else:  # openai
            api_key = os.getenv("OPENAI_API_KEY", "dummy").strip()
            url = _resolve_openai_url()

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            model = os.getenv("REGENOLD_EXTERNAL_EMBEDDING_MODEL", "text-embedding-3-small")

            for idx in range(0, len(input_list), batch_size):
                batch = input_list[idx : idx + batch_size]
                payload = {
                    "input": batch,
                    "model": model,
                }
                res = client.post(url, headers=headers, json=payload)
                res.raise_for_status()
                data = res.json()
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                embeddings.extend([item["embedding"] for item in sorted_data])

        arr = np.array(embeddings, dtype=np.float32)
        if single_input:
            return arr[0]
        return arr

    except Exception as exc:  # noqa: BLE001 — fail-soft graceful fallback
        logger.warning(
            "external_embeddings: API request failed for provider=%s. reason=%s",
            provider,
            exc,
        )
        if provider == "openai":
            # R112 — cache the failed probe so the dense hot path never
            # re-pays this round-trip in this process. The precomputed
            # SVD assets serve dense retrieval instead. Cohere failures
            # are NOT cached (canonical embeddings API — transient).
            _record_openai_probe_failure()
        return None

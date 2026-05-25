"""External high-dimensional dense embeddings provider (Cohere / OpenAI).

Natively runs on Railway or local Windows/Linux dev machines via API keys.
Integrates with the C-accelerated TurboQuant vector store for extreme recall.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Literal

import httpx

if TYPE_CHECKING:
    import numpy as np  # type: ignore

logger = logging.getLogger(__name__)


# ── Configuration & Env Gates ───────────────────────────────────────────

COHERE_API_URL = "https://api.cohere.com/v1/embed"
OPENAI_API_URL = "https://api.openai.com/v1/embeddings"


def is_available() -> bool:
    """True if Cohere or OpenAI embedding API keys are set in the env."""
    return bool(
        os.getenv("COHERE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("OPENAI_API_BASE")
    )


def _get_provider() -> Literal["cohere", "openai", None]:
    if os.getenv("COHERE_API_KEY"):
        return "cohere"
    if os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_BASE"):
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

    single_input = isinstance(texts, str)
    input_list = [texts] if single_input else list(texts)
    
    # Strip leading/trailing whitespaces to avoid API quirks
    input_list = [t.strip() for t in input_list]
    if not input_list or all(not t for t in input_list):
        return None

    try:
        batch_size = 50
        embeddings: list[list[float]] = []

        if provider == "cohere":
            api_key = os.getenv("COHERE_API_KEY", "").strip()
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            # Cohere embed v3: Search Query for queries, Search Document for corpus docs
            input_type = "search_query" if is_query else "search_document"
            model = os.getenv("REGENOLD_EXTERNAL_EMBEDDING_MODEL", "embed-english-v3.0")
            
            with httpx.Client(timeout=30.0) as client:
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
            api_base = os.getenv("OPENAI_API_BASE", OPENAI_API_URL).strip()
            url = api_base
            if api_base.endswith("/v1"):
                url = f"{api_base}/embeddings"
            elif api_base.endswith("/v1/"):
                url = f"{api_base}embeddings"
            elif "embeddings" not in api_base:
                url = f"{api_base}/embeddings" if not api_base.endswith("/") else f"{api_base}embeddings"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            model = os.getenv("REGENOLD_EXTERNAL_EMBEDDING_MODEL", "text-embedding-3-small")
            
            with httpx.Client(timeout=30.0) as client:
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
        return None

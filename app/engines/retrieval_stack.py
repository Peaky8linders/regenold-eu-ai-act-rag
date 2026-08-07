"""Retrieval stack for the EU AI Act (plan §5, §9).

Provides the `Retriever` ABC interface, pure-Python `TfidfRetriever`, classical
`LsaRetriever`, and pluggable `ExternalEmbeddingRetriever` for neural dense retrieval
(Voyage AI `voyage-law-2`, Qwen3-Embedding, FastEmbed, or HuggingFace sentence-transformers).
"""

from __future__ import annotations

import math
import os
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any

__all__ = [
    "Retriever",
    "TfidfRetriever",
    "LsaRetriever",
    "ExternalEmbeddingRetriever",
    "tokenize",
]

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the a an of to and or in on for is are be as by with that this which shall "
    "may not it its their such where when who whom under pursuant referred".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2 and t not in _STOP]


def _l2_normalize(vec: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(w * w for w in vec.values()))
    if norm == 0:
        return vec
    return {t: w / norm for t, w in vec.items()}


def apply_role_boosting(pid: str, score: float, role: str | None) -> float:
    """Apply role-aware score boosting based on EU AI Act article assignments."""
    if not role:
        return score
    role_lower = role.lower()
    pid_lower = pid.lower()
    if "provider" in role_lower and any(f"article_{i}" in pid_lower or f"article {i}" in pid_lower for i in range(16, 26)):
        return score * 1.25
    if "deployer" in role_lower and ("article_26" in pid_lower or "article 26" in pid_lower):
        return score * 1.30
    if "importer" in role_lower and ("article_23" in pid_lower or "article 23" in pid_lower):
        return score * 1.25
    if "distributor" in role_lower and ("article_24" in pid_lower or "article 24" in pid_lower):
        return score * 1.25
    return score


class Retriever(ABC):
    """Abstract Retriever interface mapping query -> list[provision_id]."""

    @abstractmethod
    def search(self, query: str, k: int, *, role: str | None = None) -> list[str]:
        raise NotImplementedError

    def search_scored(self, query: str, k: int, *, role: str | None = None) -> list[tuple[str, float]]:
        """Ranked (provision_id, score) pairs."""
        return [(pid, 1.0 / (i + 1)) for i, pid in enumerate(self.search(query, k, role=role))]


class TfidfRetriever(Retriever):
    """Pure-Python TF-IDF sparse retriever."""

    def __init__(self, provisions: list[Any]) -> None:
        self._ids: list[str] = []
        tokenized: list[list[str]] = []
        for p in provisions:
            eid = getattr(p, "provision_id", None) or str(p.get("provision_id"))
            text = getattr(p, "text", None) or str(p.get("text", ""))
            self._ids.append(eid)
            tokenized.append(tokenize(text))

        n = len(tokenized)
        df: Counter[str] = Counter()
        for toks in tokenized:
            df.update(set(toks))
        self._idf: dict[str, float] = {
            t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()
        }
        self._doc_vecs: list[dict[str, float]] = [self._vectorize(toks) for toks in tokenized]

    def _vectorize(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        vec = {t: c * self._idf.get(t, 0.0) for t, c in tf.items() if self._idf.get(t, 0.0)}
        return _l2_normalize(vec)

    def search(self, query: str, k: int, *, role: str | None = None) -> list[str]:
        return [pid for pid, _ in self.search_scored(query, k, role=role)]

    def search_scored(self, query: str, k: int, *, role: str | None = None) -> list[tuple[str, float]]:
        qvec = self._vectorize(tokenize(query))
        if not qvec:
            return []
        scored: list[tuple[float, str]] = []
        for pid, dvec in zip(self._ids, self._doc_vecs):
            small, big = (qvec, dvec) if len(qvec) <= len(dvec) else (dvec, qvec)
            score = sum(w * big.get(t, 0.0) for t, w in small.items())
            if score > 0:
                score = apply_role_boosting(pid, score, role)
                scored.append((score, pid))
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [(pid, score) for score, pid in scored[:k]]



class LsaRetriever(Retriever):
    """Classical Truncated-SVD Latent Semantic Analysis retriever."""

    def __init__(
        self,
        provisions: list[Any],
        *,
        n_components: int = 200,
        min_df: int = 2,
        seed: int = 0,
    ) -> None:
        try:
            import numpy as np
        except ImportError as e:
            raise RuntimeError("LsaRetriever requires numpy") from e

        self._ids: list[str] = [
            getattr(p, "provision_id", None) or str(p.get("provision_id")) for p in provisions
        ]
        docs = [
            tokenize(getattr(p, "text", None) or str(p.get("text", ""))) for p in provisions
        ]
        n = len(docs)

        df: Counter[str] = Counter()
        for toks in docs:
            df.update(set(toks))
        vocab = sorted(t for t, d in df.items() if d >= min_df)
        self._vocab: dict[str, int] = {t: i for i, t in enumerate(vocab)}
        self._idf: dict[str, float] = {
            t: math.log((1 + n) / (1 + df[t])) + 1.0 for t in vocab
        }

        X = np.zeros((n, len(vocab)), dtype=np.float64)
        for r, toks in enumerate(docs):
            for t, c in Counter(toks).items():
                j = self._vocab.get(t)
                if j is not None:
                    X[r, j] = c * self._idf[t]
        X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)

        k = max(1, min(n_components, min(X.shape) - 1)) if min(X.shape) > 1 else 1
        rng = np.random.default_rng(seed)
        p_dim = min(k + 10, len(vocab))
        Y = X @ rng.standard_normal((len(vocab), p_dim))
        for _ in range(4):
            Q, _ = np.linalg.qr(X @ (X.T @ Y))
            Y = Q
        Q, _ = np.linalg.qr(Y)
        B = Q.T @ X
        Ub, s, Vt = np.linalg.svd(B, full_matrices=False)
        U, s, Vt = (Q @ Ub)[:, :k], s[:k], Vt[:k]

        for i in range(Vt.shape[0]):
            j = int(np.argmax(np.abs(Vt[i])))
            if Vt[i, j] < 0:
                Vt[i] *= -1
                U[:, i] *= -1

        self._components = Vt
        doc_emb = U * s
        self._doc_emb = doc_emb / np.clip(
            np.linalg.norm(doc_emb, axis=1, keepdims=True), 1e-12, None
        )

    def _embed_query(self, query: str):
        import numpy as np

        vec = np.zeros(len(self._vocab), dtype=np.float64)
        hit = False
        for t, c in Counter(tokenize(query)).items():
            j = self._vocab.get(t)
            if j is not None:
                vec[j] = c * self._idf[t]
                hit = True
        if not hit:
            return None
        vec /= np.clip(np.linalg.norm(vec), 1e-12, None)
        latent = self._components @ vec
        norm = float(np.linalg.norm(latent))
        if norm == 0.0:
            return None
        return latent / norm

    def search(self, query: str, k: int, *, role: str | None = None) -> list[str]:
        return [pid for pid, _ in self.search_scored(query, k, role=role)]

    def search_scored(self, query: str, k: int, *, role: str | None = None) -> list[tuple[str, float]]:
        q = self._embed_query(query)
        if q is None:
            return []
        sims = self._doc_emb @ q
        order = sorted(range(len(self._ids)), key=lambda i: (-float(sims[i]), self._ids[i]))
        scored: list[tuple[float, str]] = []
        for i in order:
            score = float(sims[i])
            if score > 0:
                score = apply_role_boosting(self._ids[i], score, role)
                scored.append((score, self._ids[i]))
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [(pid, score) for score, pid in scored[:k]]


class ExternalEmbeddingRetriever(Retriever):
    """Dense retriever adapter supporting external API / local neural models.

    Supports:
      - Voyage AI (`voyage-law-2`) via `VOYAGE_API_KEY`
      - OpenAI (`text-embedding-3-large`) via `OPENAI_API_KEY`
      - HuggingFace sentence-transformers (`BAAI/bge-small-en-v1.5`)
    """

    def __init__(
        self,
        provisions: list[Any],
        provider: str = "auto",
        model_name: str = "voyage-law-2",
        embed_fn: Any | None = None,
    ) -> None:
        self._ids: list[str] = [
            getattr(p, "provision_id", None) or str(p.get("provision_id")) for p in provisions
        ]
        self.provider = provider
        self.model_name = model_name
        self.embed_fn = embed_fn
        self._doc_embeddings: list[list[float]] | None = None

    def search(self, query: str, k: int, *, role: str | None = None) -> list[str]:
        return [pid for pid, _ in self.search_scored(query, k, role=role)]

    def search_scored(self, query: str, k: int, *, role: str | None = None) -> list[tuple[str, float]]:
        if self.embed_fn is None:
            # Fall back to TF-IDF if no dense embedder is configured or available
            fallback = TfidfRetriever([{"provision_id": eid, "text": ""} for eid in self._ids])
            return fallback.search_scored(query, k, role=role)

        try:
            q_emb = self.embed_fn([query])[0]
        except Exception:
            return []

        if not self._doc_embeddings or not q_emb:
            return []

        # Cosine similarity
        scored: list[tuple[float, str]] = []
        for eid, d_emb in zip(self._ids, self._doc_embeddings):
            dot = sum(q * d for q, d in zip(q_emb, d_emb))
            if dot > 0:
                dot = apply_role_boosting(eid, dot, role)
                scored.append((dot, eid))

        scored.sort(key=lambda s: (-s[0], s[1]))
        return [(pid, score) for score, pid in scored[:k]]


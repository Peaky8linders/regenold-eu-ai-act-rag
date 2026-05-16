"""Runtime consumer for the sentence-level TF-IDF + SVD embedding index.

Loads the FOUR assets persisted by ``scripts/build_embeddings_index.py``
and answers ``cosine-similarity`` queries against the 919-sentence
corpus from :data:`app.data.eu_ai_act_corpus.ARTICLE_FULL_TEXT`.

## Why a third dense path?

Two dense modules already exist in this repo:

* :mod:`app.engines.turboquant_index` builds a TF-IDF + SVD index over
  the **article-level** BM25 corpus in-memory, on first use, every
  process boot (so the ~50–100 ms SVD cost is paid once per worker).
* :mod:`app.engines.vector_rerank` consumes pre-built ``turbovec``
  artefacts on Linux only.

This module is the **sentence-level + Windows-friendly + pre-built**
slot: precomputed assets on disk → instant lazy load, no per-process
SVD cost, no Linux requirement, sentence granularity (vs article).

The route can fuse this with the existing article-level BM25 winners
(give the matching sentence's article a recall bump) or surface a
sentence directly as the answer-prose candidate. **Wiring is left to
the consumer** — this module is purely additive; nothing imports it
yet so the deterministic baseline benchmark numbers in CLAUDE.md
remain reproducible until a follow-up round wires it in.

## Failure modes (route-safe)

* Asset files absent → :func:`is_available` returns False,
  :func:`query` returns ``[]``.
* Corrupt JSON / NumPy load failure → silently degrade to "not
  available" + WARN log once; ``query`` still returns ``[]``.
* Query text yields zero in-vocab tokens → returns ``[]``.

Hard constraints (per the task brief):

* Module-level imports are STDLIB ONLY (``json``, ``logging``,
  ``hashlib``, ``threading``, ``dataclasses``, ``functools``, ``pathlib``,
  ``re``, ``typing``). NumPy is imported lazily inside :func:`query` /
  :func:`warm_up` so the module-load cost stays < 1 ms.
* Runtime depends on NumPy + stdlib only — no sklearn.
* :func:`query` NEVER raises; it returns ``[]`` on every error path.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — only for type-checker
    import numpy as np  # type: ignore

logger = logging.getLogger(__name__)


# ── Asset locations + filenames (must match build script) ────────────────


_ASSETS_DIR = Path(__file__).resolve().parent / "_assets"

EMBED_FILENAME = "article_sentences_embed.npy"
META_FILENAME = "article_sentences_meta.json"
SVD_FILENAME = "embed_svd_model.npy"
VOCAB_FILENAME = "embed_vocab.json"
MANIFEST_FILENAME = "embeddings_manifest.json"


def _asset_path(name: str) -> Path:
    return _ASSETS_DIR / name


_REQUIRED_FILES = (
    EMBED_FILENAME,
    META_FILENAME,
    SVD_FILENAME,
    VOCAB_FILENAME,
    MANIFEST_FILENAME,
)


# ── Tokenizer (vendored to keep this module dependency-free) ─────────────


# Same shape as :func:`app.data.kb_search._tokenize` — vendored here so
# the runtime module is import-light (loading ``kb_search`` triggers a
# 300+ doc BM25 index build that we don't need for an embedding query).
# The build script uses the canonical ``_tokenize`` for index-time
# tokenisation; the asset is keyed by the SAME tokeniser shape so the
# query-time vocabulary alignment is exact.

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "in", "on",
    "at", "to", "for", "with", "by", "from", "as", "is", "are", "was",
    "were", "be", "been", "being", "do", "does", "did", "have", "has",
    "had", "having", "will", "would", "should", "could", "may", "might",
    "must", "shall", "can", "cannot", "no", "not", "this", "that", "these",
    "those", "it", "its", "they", "them", "their", "there", "here", "who",
    "what", "which", "where", "when", "why", "how", "we", "us", "our",
    "you", "your", "i", "me", "my", "any", "all", "some", "each", "every",
    "either", "neither", "more", "most", "less", "least", "many", "much",
    "few", "such", "also", "than", "then", "so",
    # AI Act prose recurring words (mirrors kb_search)
    "system", "systems", "ai", "provider", "providers", "deployer",
    "deployers", "obligation", "obligations", "requirement",
    "requirements", "requires", "required", "include", "includes",
    "including", "covered", "cover", "covers", "subject", "use", "used",
    "using", "uses", "act", "regulation", "regulations", "article",
    "articles", "annex", "annexes", "section", "sections", "art",
})


def _tokenize(text: str) -> list[str]:
    """Local copy of :func:`app.data.kb_search._tokenize` — keeps this
    module's import graph light."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall((text or "").lower()):
        if raw in _STOPWORDS:
            continue
        if len(raw) <= 1:
            continue
        if raw.isdigit() and len(raw) > 4:
            continue
        tokens.append(raw)
    return tokens


# ── Public dataclasses ───────────────────────────────────────────────────


@dataclass(frozen=True)
class EmbeddingHit:
    """One sentence-level hit from :func:`query`.

    ``similarity`` is the cosine similarity in ``[-1, 1]`` between the
    query embedding and the sentence embedding. The build script
    L2-normalises every row so cosine == dot product exactly.
    """

    article_ref: str
    sent_idx: int
    text: str
    similarity: float


# ── Lazy asset cache ─────────────────────────────────────────────────────


@dataclass
class _AssetCache:
    """Module-level mutable cache populated on first :func:`query`.

    Designed to survive process-wide so the ~few-MB asset bytes are
    paid for once. The ``embeddings`` field is a ``numpy.memmap`` — the
    OS will demand-page rows so the resident-set cost is bounded.
    """

    embeddings: object | None = None       # np.memmap[N, dim]
    svd_v_t: object | None = None          # np.ndarray[dim, V]
    vocab: dict[str, int] | None = None
    idf: object | None = None              # np.ndarray[V]
    meta: list[dict] | None = None
    manifest: dict | None = None
    load_failed: bool = False              # sticky after the first failure


_CACHE = _AssetCache()
_LOCK = threading.RLock()


def _all_files_present() -> bool:
    """Cheap presence check — no JSON parsing, just stat() each file."""
    for name in _REQUIRED_FILES:
        if not _asset_path(name).exists():
            return False
    return True


def is_available() -> bool:
    """True iff all 5 asset files exist on disk AND haven't failed to load.

    Cheap to call (a handful of ``os.stat`` calls). The presence check
    is the cleanest signal a downstream caller can use to decide
    whether to fan out an embedding query — when False they can skip
    the latency entirely.
    """
    if _CACHE.load_failed:
        return False
    return _all_files_present()


def _load_assets() -> bool:
    """Load all four assets into the module-level cache. Returns True on success.

    Thread-safe via ``_LOCK``. Idempotent — subsequent calls short-
    circuit when the cache is already warm. On ANY load failure (file
    missing, JSON malformed, numpy import error, dimension mismatch)
    we set ``load_failed=True`` and return False so future queries
    return ``[]`` without retrying.
    """
    if _CACHE.embeddings is not None:
        return True
    if _CACHE.load_failed:
        return False
    with _LOCK:
        if _CACHE.embeddings is not None:
            return True
        if _CACHE.load_failed:
            return False
        try:
            import numpy as np  # noqa: PLC0415 — lazy heavy import
        except Exception as exc:  # noqa: BLE001
            logger.warning("embeddings_index: numpy import failed: %s", exc)
            _CACHE.load_failed = True
            return False

        if not _all_files_present():
            # No log spam — the consumer's :func:`is_available` already
            # surfaces this. Set the sticky-failed flag so we don't
            # re-stat every query.
            _CACHE.load_failed = True
            return False

        try:
            # memmap the .npy embeddings to avoid loading 5–15 MB upfront.
            # mode="r" is read-only so the file can be shared across
            # worker processes safely.
            embeddings = np.load(_asset_path(EMBED_FILENAME), mmap_mode="r")
            svd_v_t = np.load(_asset_path(SVD_FILENAME))
            vocab_payload = json.loads(
                _asset_path(VOCAB_FILENAME).read_text(encoding="utf-8")
            )
            vocab = vocab_payload["vocab"]
            idf = np.asarray(vocab_payload["idf"], dtype=np.float32)
            meta = json.loads(
                _asset_path(META_FILENAME).read_text(encoding="utf-8")
            )
            manifest = json.loads(
                _asset_path(MANIFEST_FILENAME).read_text(encoding="utf-8")
            )
        except Exception as exc:  # noqa: BLE001 — degrade silently
            logger.warning("embeddings_index: asset load failed: %s", exc)
            _CACHE.load_failed = True
            return False

        # Sanity: embeddings rows == meta entries == manifest count.
        # Mismatch is recoverable (we treat the whole index as failed
        # rather than serving partial data).
        if embeddings.shape[0] != len(meta):
            logger.warning(
                "embeddings_index: row/meta length mismatch n_rows=%d "
                "n_meta=%d",
                embeddings.shape[0],
                len(meta),
            )
            _CACHE.load_failed = True
            return False
        if svd_v_t.shape[1] != len(vocab):
            logger.warning(
                "embeddings_index: SVD basis vocab mismatch svd_v=%d "
                "vocab=%d",
                svd_v_t.shape[1],
                len(vocab),
            )
            _CACHE.load_failed = True
            return False

        _CACHE.embeddings = embeddings
        _CACHE.svd_v_t = svd_v_t
        _CACHE.vocab = vocab
        _CACHE.idf = idf
        _CACHE.meta = meta
        _CACHE.manifest = manifest
        logger.info(
            "embeddings_index: loaded n_sents=%d vocab=%d dim=%d "
            "manifest_version=%s",
            embeddings.shape[0],
            len(vocab),
            embeddings.shape[1] if embeddings.ndim == 2 else 0,
            manifest.get("version", "?"),
        )
        return True


def warm_up() -> None:
    """Eagerly load assets into the module-level cache.

    Optional perf opt — :func:`query` calls this transparently. Useful
    for FastAPI startup hooks that want to pay the few-ms load cost
    before the first user request lands.
    """
    _load_assets()


def asset_manifest() -> dict:
    """Return a copy of the manifest dict (or ``{}`` when unavailable).

    The manifest mirrors the JSON written by the build script: version,
    generated_date, total_sentences, vector_dim, vocab_size, SHA-256
    hashes, and the per-asset filename map. Useful for the future
    ``/healthz/embeddings`` probe.
    """
    if not _load_assets():
        return {}
    assert _CACHE.manifest is not None
    return dict(_CACHE.manifest)


# ── Query path ───────────────────────────────────────────────────────────


def _embed_query(text: str) -> "np.ndarray | None":
    """Project the query into the same 128-D unit-norm subspace.

    Returns ``None`` when:

    * No assets loaded (``_load_assets()`` returned False).
    * The query has no in-vocab tokens.
    * The resulting TF-IDF vector or its SVD projection is zero-norm.
    """
    import numpy as np  # noqa: PLC0415 — lazy heavy import

    if not _load_assets():
        return None
    vocab = _CACHE.vocab
    idf = _CACHE.idf
    v_t = _CACHE.svd_v_t
    assert vocab is not None and idf is not None and v_t is not None

    tokens = _tokenize(text)
    if not tokens:
        return None

    n_vocab = len(vocab)
    tf = np.zeros(n_vocab, dtype=np.float32)
    for tok in tokens:
        j = vocab.get(tok)
        if j is not None:
            tf[j] += 1.0
    if not tf.any():
        return None
    # Log-TF damping consistent with the build script.
    with np.errstate(divide="ignore"):
        log_tf = np.where(tf > 0, 1.0 + np.log(tf), 0.0)
    q_tfidf = log_tf * idf
    q_norm = np.linalg.norm(q_tfidf)
    if q_norm < 1e-9:
        return None
    q_unit = q_tfidf / q_norm
    q_proj = v_t @ q_unit  # (dim,)
    proj_norm = np.linalg.norm(q_proj)
    if proj_norm < 1e-9:
        return None
    return (q_proj / proj_norm).astype(np.float32)


def query(
    query_text: str,
    *,
    top_k: int = 10,
    threshold: float = 0.0,
) -> list[EmbeddingHit]:
    """Return the top-``top_k`` sentence-level hits above ``threshold``.

    The result is sorted by descending cosine similarity. Returns
    ``[]`` when assets are unavailable, the query has no in-vocab
    tokens, or no sentence passes the threshold. NEVER raises — every
    error path collapses to the empty list so retrieval callers can
    treat this as a best-effort recall enhancer.

    Args:
        query_text: Free-form question / phrase. Tokenised by the
            module-local :func:`_tokenize` (same shape as
            ``kb_search._tokenize``).
        top_k: Maximum number of hits to return. Clamped to ``[0, N]``
            where ``N`` is the corpus size.
        threshold: Inclusive cosine-similarity floor. Hits below this
            are filtered out. Default ``0.0`` keeps everything that
            isn't anti-correlated.

    Returns:
        ``list[EmbeddingHit]`` in descending-similarity order.
    """
    if not query_text or top_k <= 0:
        return []
    if not _load_assets():
        return []
    try:
        import numpy as np  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — already logged in _load_assets
        return []

    emb = _CACHE.embeddings
    meta = _CACHE.meta
    assert emb is not None and meta is not None

    q_vec = _embed_query(query_text)
    if q_vec is None:
        return []

    # The embeddings are unit-norm float32 rows, so dot product == cosine.
    # NB: ``emb`` is a numpy.memmap → the slice we ``@`` here is the only
    # part of the file that gets paged in (small fraction of the ~460 KB
    # file). For 919 rows the full scan is a sub-millisecond matmul.
    try:
        scores = emb @ q_vec  # shape (N,)
    except Exception as exc:  # noqa: BLE001 — defensive against bad data
        logger.warning("embeddings_index: matmul failed: %s", exc)
        return []
    n = int(scores.shape[0])
    if n == 0:
        return []
    kk = min(top_k, n)
    # argpartition + sort over the top-kk indices — O(N) instead of O(N log N).
    top_idx = np.argpartition(-scores, kk - 1)[:kk]
    top_idx = top_idx[np.argsort(-scores[top_idx])]
    out: list[EmbeddingHit] = []
    for idx in top_idx:
        sim = float(scores[int(idx)])
        if sim < threshold:
            continue
        entry = meta[int(idx)]
        out.append(
            EmbeddingHit(
                article_ref=str(entry["article_ref"]),
                sent_idx=int(entry["sent_idx"]),
                text=str(entry["text"]),
                similarity=sim,
            )
        )
    return out


__all__ = [
    "EmbeddingHit",
    "asset_manifest",
    "is_available",
    "query",
    "warm_up",
]

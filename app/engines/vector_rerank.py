"""Optional TurboVec-backed sentence reranker — env-gated, lazy-loaded.

When ``REGENOLD_VECTOR_RERANK=1`` is set AND a pre-built sentence index
file exists at ``app/data/vectors/sentences.tvim``, this module exposes
a :func:`rerank_sentences` hook that the route can call to refine the
sentence-level BM25 pick from :mod:`app.engines.sentence_index` using
cosine-similarity ranks against a query embedding (bge-small-en-v1.5
ONNX, ~33 MB on disk, ~8 ms p50 inference).

When the env var is NOT set, OR turbovec / onnxruntime / the index file
are missing, every public function returns a passthrough None — the
calling route simply uses the BM25 pick as before. This lets Windows
dev (no turbovec wheel) keep working while Linux production opts in.

Architecture (Round 27 — per the parallel-agent recon recommendation):

  1. **Offline indexer** (``scripts/build_vector_index.py``) — runs
     once on Linux to embed all 934 corpus sentences with
     bge-small-en-v1.5 and write a 4-bit-quantized ``IdMapIndex`` to
     ``app/data/vectors/sentences.tvim`` (~250 KB).
  2. **Query embedder** — ``ort.InferenceSession`` over a quantized
     bge-small ONNX export shipped at ``app/data/vectors/bge_small.onnx``.
  3. **Reranker** — when called from
     :func:`app.routes.regenold._try_extractive_answer`, embeds the
     question once, runs ``IdMapIndex.search`` filtered to the
     article-scoped sentence ids, fuses the vector rank with the BM25
     rank via Reciprocal Rank Fusion (k=60) and returns the top-1.

The graceful-degradation pattern mirrors the audit store
(``app.evidence.store``): the heavy deps (turbovec, onnxruntime,
tokenizers) are imported lazily inside :func:`_get_searcher`; if any
import fails the module logs once at INFO and every subsequent call
returns ``None``.

Why the env-gate is opt-in rather than auto:

  * Windows dev does not have a turbovec wheel; auto-detect would
    force every contributor onto WSL2.
  * The ONNX runtime adds ~30 MB to the wheel surface; we don't want
    to inflate the Railway image unless we're actually using vector
    rerank in production.
  * The competition rubric weighs latency p50 — adding +8 ms is a
    deliberate trade we want surface visibility on, not silent default
    behaviour.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np  # type: ignore

logger = logging.getLogger(__name__)


VECTOR_DIR = Path(__file__).parent.parent / "data" / "vectors"
INDEX_PATH = VECTOR_DIR / "sentences.tvim"
ONNX_PATH = VECTOR_DIR / "bge_small.onnx"
TOKENIZER_PATH = VECTOR_DIR / "bge_small_tokenizer.json"


_ENV_FLAG = "REGENOLD_VECTOR_RERANK"


def is_enabled() -> bool:
    """True iff the env-gate AND all the on-disk assets are present.

    Cheap to call — only filesystem stat + env lookup. Used by the
    route to short-circuit the rerank pipeline before paying any
    import cost.
    """
    val = os.getenv(_ENV_FLAG, "").strip().lower()
    if val not in ("1", "true", "yes", "on"):
        return False
    return INDEX_PATH.exists() and ONNX_PATH.exists() and TOKENIZER_PATH.exists()


class _Searcher:
    """Holds the loaded ONNX session + turbovec index for the process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._failed = False
        self._session: object | None = None
        self._tokenizer: object | None = None
        self._index: object | None = None
        # Maps the encoded u64 id back to ``(article_ref, sentence_idx)``
        # so the route can route a top-k hit back to a sentence string.
        self._id_to_sentence: dict[int, tuple[str, int]] = {}

    def _setup(self) -> bool:
        """Lazy one-shot init. Returns True on success, False on permanent fail."""
        if self._loaded:
            return True
        if self._failed:
            return False
        with self._lock:
            if self._loaded:
                return True
            if self._failed:
                return False
            try:
                self._load()
                self._loaded = True
                return True
            except Exception as exc:  # noqa: BLE001 — graceful degrade
                logger.info(
                    "vector_rerank: degraded (no rerank). reason=%s",
                    exc,
                )
                self._failed = True
                return False

    def _load(self) -> None:
        # Heavy imports stay inside this method so module-load remains
        # zero-cost when the feature is off.
        import json  # noqa: PLC0415
        import onnxruntime as ort  # noqa: PLC0415 — env-gated, lazy
        from tokenizers import Tokenizer  # noqa: PLC0415
        from turbovec import IdMapIndex  # noqa: PLC0415

        # ID-map index — sentence_id (u64) ↔ stable position in the
        # 934-sentence corpus. The pre-built file ships in the repo.
        self._index = IdMapIndex.load(str(INDEX_PATH))
        # ONNX bge-small encoder; force CPU + 1 thread to keep
        # latency deterministic under load.
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(ONNX_PATH),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
        # Reverse lookup table — the offline indexer writes a sidecar
        # ``sentences.tvim.json`` mapping u64 → (article_ref, sent_idx).
        sidecar = INDEX_PATH.with_suffix(".tvim.json")
        if sidecar.exists():
            with sidecar.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            self._id_to_sentence = {
                int(k): (v["article"], int(v["sent_idx"]))
                for k, v in (payload.get("id_map") or {}).items()
            }

    def embed(self, text: str) -> "np.ndarray | None":  # type: ignore[name-defined]
        """Embed a single query string to a 384-d float32 unit-norm vector."""
        if not self._setup():
            return None
        import numpy as np  # noqa: PLC0415

        tokenizer = self._tokenizer
        session = self._session
        assert tokenizer is not None and session is not None
        # Tokenise; bge-small caps at 512 tokens but for a question
        # we'll be well below that.
        enc = tokenizer.encode(text)
        input_ids = np.array([enc.ids], dtype=np.int64)
        attention_mask = np.array([enc.attention_mask], dtype=np.int64)
        token_type_ids = np.array(
            [getattr(enc, "type_ids", None) or [0] * len(enc.ids)],
            dtype=np.int64,
        )
        outputs = session.run(  # type: ignore[attr-defined]
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        # bge-small returns last_hidden_state; we mean-pool then
        # L2-normalise to a unit vector (this is what the offline
        # indexer also does, so dot-product == cosine).
        hidden = outputs[0][0]  # (seq_len, 384)
        mask = attention_mask[0].astype(np.float32)
        masked = hidden * mask[:, None]
        pooled = masked.sum(axis=0) / max(mask.sum(), 1e-6)
        norm = np.linalg.norm(pooled) or 1.0
        return (pooled / norm).astype(np.float32)

    def search_within_article(
        self, query: str, article_ref: str, *, k: int = 5
    ) -> list[tuple[str, float]] | None:
        """Return top-``k`` sentences from ``article_ref`` ranked by cosine.

        Empty list when the index has no sentences for that article;
        ``None`` when the rerank pipeline is unavailable (env-gate off
        or asset missing — caller should fall back to BM25 only).
        """
        if not self._setup():
            return None
        import numpy as np  # noqa: PLC0415

        emb = self.embed(query)
        if emb is None:
            return None
        # turbovec search returns (scores, ids) over the FULL index;
        # filter to the ones we care about. For 934 sentences the
        # over-fetch cost is negligible (sub-ms brute-force scan).
        scores, ids = self._index.search(emb[None, :], k=64)  # type: ignore[union-attr]
        out: list[tuple[str, float]] = []
        for s, idx_u64 in zip(scores[0], ids[0]):
            mapping = self._id_to_sentence.get(int(idx_u64))
            if mapping is None:
                continue
            if mapping[0] != article_ref:
                continue
            from app.engines.sentence_index import _all_sentence_indexes
            si = _all_sentence_indexes().get(article_ref)
            if si is None:
                continue
            sent_idx = mapping[1]
            if sent_idx >= len(si.sentences):
                continue
            out.append((si.sentences[sent_idx], float(s)))
            if len(out) >= k:
                break
        return out


_SEARCHER = _Searcher()


def rerank_sentences(
    query: str,
    article_ref: str,
    bm25_top_sentence: str | None,
    *,
    k: int = 5,
    rrf_k: int = 60,
) -> str | None:
    """Vector-rerank the article's sentences and fuse with the BM25 pick.

    Returns the fused top-1 sentence text, or ``None`` when vector
    rerank is unavailable. Caller should fall back to
    ``bm25_top_sentence`` in the ``None`` case.

    Fusion: Reciprocal Rank Fusion (Cormack et al. SIGIR 2009) with
    ``k=60`` smoothing. The BM25 pick contributes rank 1 (best);
    vector results contribute their search rank. Top-1 after fusion
    wins. This composition is well-studied as one of the strongest
    deterministic hybrid baselines.
    """
    if not is_enabled():
        return None
    vec_hits = _SEARCHER.search_within_article(query, article_ref, k=k)
    if not vec_hits:
        return None
    # Combine vector + BM25 ranks via RRF.
    scores: dict[str, float] = {}
    if bm25_top_sentence:
        scores[bm25_top_sentence] = 1.0 / (rrf_k + 1)
    for rank, (sent, _vec_score) in enumerate(vec_hits, start=1):
        scores[sent] = scores.get(sent, 0.0) + 1.0 / (rrf_k + rank)
    if not scores:
        return None
    return max(scores.items(), key=lambda t: t[1])[0]


__all__ = [
    "INDEX_PATH",
    "ONNX_PATH",
    "TOKENIZER_PATH",
    "VECTOR_DIR",
    "is_enabled",
    "rerank_sentences",
]

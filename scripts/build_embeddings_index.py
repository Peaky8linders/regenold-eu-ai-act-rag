"""Build the per-sentence TF-IDF + Truncated-SVD embedding index.

Reads :data:`app.data.eu_ai_act_corpus.ARTICLE_FULL_TEXT` (126 articles +
annexes), splits each article into sentences via
:func:`app.engines.sentence_index.split_legal_sentences`, computes a
TF-IDF vector per sentence over a shared vocabulary, projects every
vector down to 128-D via deterministic Truncated SVD, L2-normalises
the rows, and persists FOUR assets plus a manifest under
``app/engines/_assets/`` so the runtime consumer in
``app/engines/embeddings_index.py`` can answer cosine-similarity queries
without re-running the (~few-hundred-ms) build.

Hard contract — all of these are versioned in the manifest:

* ``article_sentences_embed.npy`` — float32 ``[N_sents, 128]``, rows
  unit-norm. Plain NumPy ``np.save`` format so the runtime can
  ``memmap`` it.
* ``article_sentences_meta.json`` — list of
  ``{"article_ref": str, "sent_idx": int, "text": str}`` parallel to
  the ``.npy`` rows.
* ``embed_svd_model.npy`` — float32 ``[128, V]`` SVD V^T basis. Same
  basis used at index-time and at query-time so cosine similarity is
  geometrically meaningful.
* ``embed_vocab.json`` — ``{"vocab": {term: idx}, "idf": [V floats]}``.
* ``embeddings_manifest.json`` — version + counts + per-asset SHA-256.

The build is **deterministic**: the same corpus + the same numpy SVD
(NumPy ≥ 2.0 is stable for fixed input) always produces the same
output bytes. The manifest hashes are recomputed every run and only
shift when the underlying corpus shifts.

Pure NumPy + stdlib (no scikit-learn at build-time despite the task
brief — sklearn is not in ``requirements.txt`` and the equivalent
TF-IDF + truncated-SVD shape is already used in
``app/engines/turboquant_index.py`` over NumPy primitives). Build time
is well under 1 s for the 949-sentence corpus.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

# Make repo root importable when running ``python scripts/build_embeddings_index.py``.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT  # noqa: E402
from app.data.kb_search import _tokenize  # noqa: E402
from app.engines.sentence_index import split_legal_sentences  # noqa: E402


logger = logging.getLogger(__name__)


# ── Build-time constants ─────────────────────────────────────────────────

_ASSETS_DIR = _ROOT / "app" / "engines" / "_assets"
_VECTOR_DIM = 128
_VOCAB_CAP = 50_000
_MIN_DF = 2                       # drop hapaxes — they don't generalise
_MIN_SENT_TOKENS = 3              # legal headers like "1." are noise
_BUILD_VERSION = "1.0"
_GENERATED_DATE = "2026-05-16"

EMBED_FILENAME = "article_sentences_embed.npy"
META_FILENAME = "article_sentences_meta.json"
SVD_FILENAME = "embed_svd_model.npy"
VOCAB_FILENAME = "embed_vocab.json"
MANIFEST_FILENAME = "embeddings_manifest.json"


# ── Helpers ──────────────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    """Streaming SHA-256 over a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_sentences() -> list[tuple[str, int, str, list[str]]]:
    """Walk :data:`ARTICLE_FULL_TEXT`, split, tokenise, filter.

    Returns a list of ``(article_ref, sent_idx, sentence, tokens)``
    quadruples. ``sent_idx`` is the 0-based position **within the
    article** so callers can do ``article_ref + sent_idx`` keying.
    Sentences with fewer than :data:`_MIN_SENT_TOKENS` non-stopword
    tokens are dropped (they're usually legal-list markers like
    ``"1."`` that carry no semantic load).
    """
    out: list[tuple[str, int, str, list[str]]] = []
    if not ARTICLE_FULL_TEXT:
        return out
    for article_ref, text in ARTICLE_FULL_TEXT.items():
        if not text:
            continue
        sentences = split_legal_sentences(text)
        for sent_idx, sentence in enumerate(sentences):
            tokens = _tokenize(sentence)
            if len(tokens) < _MIN_SENT_TOKENS:
                continue
            out.append((article_ref, sent_idx, sentence, tokens))
    return out


def _build_vocabulary(
    docs_tokens: list[list[str]],
) -> tuple[dict[str, int], np.ndarray]:
    """Construct vocabulary + IDF weights from the tokenised corpus.

    Returns ``(vocab, idf)`` where ``vocab`` is ``{term: idx}`` and
    ``idf`` is a float32 array of length ``|vocab|`` carrying the
    smoothed-sklearn IDF weights ``log((N+1)/(df+1)) + 1``.

    Terms with document frequency below :data:`_MIN_DF` are dropped.
    The remaining terms are sorted by descending document frequency and
    truncated to :data:`_VOCAB_CAP` for a tight wire size; ties broken
    alphabetically for build determinism.
    """
    df_count: dict[str, int] = {}
    for tokens in docs_tokens:
        for term in set(tokens):
            df_count[term] = df_count.get(term, 0) + 1
    candidates = [(term, c) for term, c in df_count.items() if c >= _MIN_DF]
    # Sort by -df then alphabetical for determinism + cap to vocab size.
    candidates.sort(key=lambda t: (-t[1], t[0]))
    candidates = candidates[:_VOCAB_CAP]
    vocab_terms = sorted(t for t, _ in candidates)  # alphabetic for vocab idx
    if not vocab_terms:
        raise RuntimeError("vocabulary is empty after df>=2 filter")
    vocab = {term: i for i, term in enumerate(vocab_terms)}
    n_docs = len(docs_tokens)
    df = np.zeros(len(vocab), dtype=np.float32)
    for term, i in vocab.items():
        df[i] = float(df_count[term])
    idf = (np.log((n_docs + 1.0) / (df + 1.0)) + 1.0).astype(np.float32)
    return vocab, idf


def _build_tfidf_matrix(
    docs_tokens: list[list[str]],
    vocab: dict[str, int],
    idf: np.ndarray,
) -> np.ndarray:
    """Build the dense ``[N_sents, V]`` TF-IDF matrix.

    Uses log-TF damping (``1 + log(tf)``) so a 30× repeated term doesn't
    drown out the vector — same shape used by
    ``app/engines/turboquant_index.py``. Rows are L2-normalised before
    we return so the downstream SVD operates on directionally-pure
    sentence vectors (length variation is already factored out).
    """
    n_docs = len(docs_tokens)
    v = len(vocab)
    if n_docs == 0 or v == 0:
        return np.zeros((0, v), dtype=np.float32)
    tf = np.zeros((n_docs, v), dtype=np.float32)
    for i, tokens in enumerate(docs_tokens):
        for term in tokens:
            j = vocab.get(term)
            if j is not None:
                tf[i, j] += 1.0
    with np.errstate(divide="ignore"):
        log_tf = np.where(tf > 0, 1.0 + np.log(tf), 0.0)
    tfidf = log_tf * idf  # broadcasts (V,) across rows
    norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    return (tfidf / norms).astype(np.float32)


def _truncated_svd(
    tfidf_unit: np.ndarray, dim: int = _VECTOR_DIM
) -> tuple[np.ndarray, np.ndarray]:
    """NumPy thin SVD → keep the top ``dim`` singular components.

    Returns ``(doc_vecs_unit, v_t)`` where ``doc_vecs_unit`` is shape
    ``[N, dim]`` unit-norm rows (sentence embeddings) and ``v_t`` is
    shape ``[dim, V]`` — the right-singular basis used to project
    query vectors at runtime.

    Determinism: NumPy ≥ 2.0's ``np.linalg.svd`` is stable for fixed
    input. We do NOT inject a random-state RNG; the SVD is fully
    determined by the input matrix.
    """
    if tfidf_unit.size == 0:
        return (
            np.zeros((0, dim), dtype=np.float32),
            np.zeros((dim, tfidf_unit.shape[1]), dtype=np.float32),
        )
    # full_matrices=False yields the thin SVD: U is [N, K], S is [K],
    # V_T is [K, V] where K = min(N, V).
    u, s, v_t = np.linalg.svd(tfidf_unit, full_matrices=False)
    k = min(dim, v_t.shape[0])
    # Doc embeddings: U[:, :k] * Σ[:k] — projection of each row onto the
    # top-k right singular vectors. Rows are then L2-normalised so dot
    # product == cosine similarity.
    doc_vecs = (u[:, :k] * s[:k][np.newaxis, :]).astype(np.float32)
    doc_norms = np.linalg.norm(doc_vecs, axis=1, keepdims=True)
    doc_norms = np.where(doc_norms < 1e-9, 1.0, doc_norms)
    doc_vecs_unit = (doc_vecs / doc_norms).astype(np.float32)
    return doc_vecs_unit, v_t[:k].astype(np.float32)


def _write_manifest(
    assets_dir: Path,
    total_sentences: int,
    vector_dim: int,
    vocab_size: int,
) -> dict:
    """Compute SHA-256 of every persisted asset and write the manifest."""
    files = [EMBED_FILENAME, META_FILENAME, SVD_FILENAME, VOCAB_FILENAME]
    hashes = {name: _sha256_file(assets_dir / name) for name in files}
    manifest = {
        "version": _BUILD_VERSION,
        "generated_date": _GENERATED_DATE,
        "total_sentences": int(total_sentences),
        "vector_dim": int(vector_dim),
        "vocab_size": int(vocab_size),
        "min_df": _MIN_DF,
        "min_sent_tokens": _MIN_SENT_TOKENS,
        "sha256_hashes": hashes,
        "assets": {
            "embeddings": EMBED_FILENAME,
            "metadata": META_FILENAME,
            "svd_basis": SVD_FILENAME,
            "vocab": VOCAB_FILENAME,
        },
    }
    (assets_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


# ── Top-level driver ─────────────────────────────────────────────────────


def main() -> int:
    """CLI entry-point. Exit 0 on success, 1 on configuration failure."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    start = time.perf_counter()

    if not ARTICLE_FULL_TEXT:
        logger.error("ARTICLE_FULL_TEXT is empty — nothing to index.")
        return 1

    _ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Step 1/5 — collecting sentences from ARTICLE_FULL_TEXT…")
    sentence_rows = _collect_sentences()
    if not sentence_rows:
        logger.error("Sentence collection yielded zero rows.")
        return 1
    docs_tokens = [tokens for _, _, _, tokens in sentence_rows]
    logger.info(
        "  → %d sentences kept (>= %d tokens each)",
        len(sentence_rows),
        _MIN_SENT_TOKENS,
    )

    logger.info("Step 2/5 — building vocabulary + IDF weights…")
    vocab, idf = _build_vocabulary(docs_tokens)
    logger.info("  → vocab size %d (capped at %d)", len(vocab), _VOCAB_CAP)

    logger.info("Step 3/5 — assembling TF-IDF matrix + Truncated SVD…")
    tfidf_unit = _build_tfidf_matrix(docs_tokens, vocab, idf)
    doc_vecs_unit, v_t = _truncated_svd(tfidf_unit, dim=_VECTOR_DIM)
    logger.info(
        "  → embeddings shape %s, SVD basis shape %s",
        doc_vecs_unit.shape,
        v_t.shape,
    )

    logger.info("Step 4/5 — persisting assets to %s …", _ASSETS_DIR)
    np.save(_ASSETS_DIR / EMBED_FILENAME, doc_vecs_unit, allow_pickle=False)
    np.save(_ASSETS_DIR / SVD_FILENAME, v_t, allow_pickle=False)
    meta_payload = [
        {
            "article_ref": article_ref,
            "sent_idx": sent_idx,
            "text": sentence,
        }
        for article_ref, sent_idx, sentence, _ in sentence_rows
    ]
    (_ASSETS_DIR / META_FILENAME).write_text(
        json.dumps(meta_payload, ensure_ascii=False), encoding="utf-8"
    )
    (_ASSETS_DIR / VOCAB_FILENAME).write_text(
        json.dumps(
            {"vocab": vocab, "idf": idf.tolist()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info("Step 5/5 — writing manifest…")
    manifest = _write_manifest(
        _ASSETS_DIR,
        total_sentences=len(sentence_rows),
        vector_dim=int(doc_vecs_unit.shape[1]) if doc_vecs_unit.size else _VECTOR_DIM,
        vocab_size=len(vocab),
    )

    elapsed = time.perf_counter() - start
    logger.info(
        "Done. Build time %.3f s. Manifest: %s",
        elapsed,
        json.dumps(manifest["sha256_hashes"], indent=2, sort_keys=True),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

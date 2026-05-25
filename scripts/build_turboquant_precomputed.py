#!/usr/bin/env python3
"""Offline builder for TurboQuant SVD precomputed assets.

Calculates the static TF-IDF + SVD-128 projection over the substative
BM25 corpus and saves the projection basis, IDF, vocabulary, and document
indices map to a single, compact numpy archive on disk.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import app modules cleanly
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import numpy as np

from app.data.kb_search import _build_index
from app.engines.turboquant_index import _INDEX_SEED, _PROJECTION_DIM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_precomputed_assets() -> None:
    logger.info("Initializing precomputed TurboQuant SVD builder...")
    bm25 = _build_index()
    n_total = len(bm25.docs)
    if n_total == 0:
        raise RuntimeError("BM25 corpus is empty")

    # Mirror _DenseIndex._build() document filtering logic:
    # Skip definitions (routed deterministically, pollute dense index)
    keep_doc_idx = [i for i in range(n_total) if bm25.sources[i] != "definition"]
    n_docs = len(keep_doc_idx)
    logger.info("Filtered dense corpus: %d docs (skipped %d definitions)", n_docs, n_total - n_docs)
    
    # Build vocabulary from tokens that appear in >= 2 documents
    df_count: dict[str, int] = {}
    for i in keep_doc_idx:
        for term in set(bm25.docs[i]):
            df_count[term] = df_count.get(term, 0) + 1
    vocab_terms = sorted([t for t, c in df_count.items() if c >= 2])
    if not vocab_terms:
        raise RuntimeError("no shared vocabulary")
    vocab = {t: i for i, t in enumerate(vocab_terms)}
    V = len(vocab)
    logger.info("Shared vocabulary size: %d terms", V)

    # Build TF matrix
    tf = np.zeros((n_docs, V), dtype=np.float32)
    for new_i, orig_i in enumerate(keep_doc_idx):
        for term in bm25.docs[orig_i]:
            j = vocab.get(term)
            if j is not None:
                tf[new_i, j] += 1.0

    # Build IDF
    df = np.zeros(V, dtype=np.float32)
    for j, term in enumerate(vocab_terms):
        df[j] = df_count.get(term, 0)
    idf = np.log((n_docs + 1.0) / (df + 1.0)) + 1.0

    # TF-IDF
    with np.errstate(divide="ignore"):
        log_tf = np.where(tf > 0, 1.0 + np.log(tf), 0.0)
    tfidf = log_tf * idf

    # Row-normalize to unit length BEFORE SVD (cosine alignment)
    row_norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
    row_norms = np.where(row_norms < 1e-9, 1.0, row_norms)
    tfidf_unit = tfidf / row_norms

    # Truncated SVD using the thin SVD projection
    u, s, vt = np.linalg.svd(tfidf_unit, full_matrices=False)
    k = min(_PROJECTION_DIM, vt.shape[0])
    
    doc_vecs = (u[:, :k] * s[:k][np.newaxis, :]).astype(np.float32)
    norms = np.linalg.norm(doc_vecs, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    doc_vecs = doc_vecs / norms

    # Ensure assets directory exists
    assets_dir = project_root / "app" / "engines" / "_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    output_path = assets_dir / "turboquant_precomputed.npz"

    # Save to a single npz compressed archive
    np.savez_compressed(
        output_path,
        vocab_json=json.dumps(vocab),
        idf=idf.astype(np.float32),
        v_t=vt[:k].astype(np.float32),
        bm25_idx_map=np.array(keep_doc_idx, dtype=np.int32),
        doc_vecs_dense=doc_vecs.astype(np.float32),
    )
    logger.info("Successfully wrote precomputed SVD assets to: %s", output_path)


if __name__ == "__main__":
    build_precomputed_assets()

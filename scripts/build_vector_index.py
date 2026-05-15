"""Build the TurboVec sentence index for vector rerank.

Run once on Linux (or in WSL2 on Windows). Produces three artefacts under
``app/data/vectors/``:

    sentences.tvim          # turbovec IdMapIndex, 4-bit quantized
    sentences.tvim.json     # sidecar mapping u64 id → (article_ref, sent_idx)
    bge_small.onnx          # ONNX-exported bge-small-en-v1.5 encoder
    bge_small_tokenizer.json

The artefacts are committed to the repo (~5 MB total). Production
deploys can opt into vector rerank by setting
``REGENOLD_VECTOR_RERANK=1`` (see ``app/engines/vector_rerank.py``).

Re-run this script only when:

  * The upstream Ansvar corpus is refreshed (new sentences).
  * You want to swap the embedding model.

Setup (one-time, on Linux/WSL2):

    pip install turbovec sentence-transformers onnxruntime optimum[onnxruntime] tokenizers
    apt install libopenblas-dev          # turbovec links libopenblas

Usage:

    py -3.12 scripts/build_vector_index.py

Wheel size warning: the `sentence-transformers` + `torch` stack pulls
~600 MB of deps; we only need these once at build time, NOT at deploy
time. Production wheel surface is ~30 MB (onnxruntime + tokenizers +
turbovec).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VECTOR_DIR = REPO_ROOT / "app" / "data" / "vectors"


def _ensure_deps() -> None:
    missing: list[str] = []
    for name in ("numpy", "turbovec", "sentence_transformers"):
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        print(
            "ERROR: missing dependencies for the offline indexer:",
            ", ".join(missing),
        )
        print(
            "Install with:\n"
            "    pip install turbovec sentence-transformers onnxruntime "
            "optimum[onnxruntime] tokenizers\n"
            "and on Linux: apt install libopenblas-dev"
        )
        sys.exit(1)


def main() -> int:
    _ensure_deps()
    import numpy as np  # noqa: PLC0415
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    from turbovec import IdMapIndex  # noqa: PLC0415

    sys.path.insert(0, str(REPO_ROOT))
    from app.engines.sentence_index import _all_sentence_indexes  # noqa: PLC0415

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Collect every sentence with a stable (article, sent_idx, u64_id)
    indexes = _all_sentence_indexes()
    rows: list[tuple[int, str, int, str]] = []
    next_id = 0
    for article_ref in sorted(indexes.keys()):
        si = indexes[article_ref]
        for sent_idx, sent in enumerate(si.sentences):
            rows.append((next_id, article_ref, sent_idx, sent))
            next_id += 1
    print(f"Indexing {len(rows)} sentences across {len(indexes)} articles.")

    # ── 2. Embed via bge-small-en-v1.5 (mean-pool + L2 normalise)
    print("Loading bge-small-en-v1.5…")
    model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
    print("Embedding…")
    embeddings = model.encode(
        [r[3] for r in rows],
        normalize_embeddings=True,
        batch_size=64,
        show_progress_bar=True,
    ).astype("float32")
    assert embeddings.shape[0] == len(rows)
    print(f"Embeddings: {embeddings.shape} {embeddings.dtype}")

    # ── 3. Build the TurboVec IdMapIndex (4-bit quantisation)
    print("Building TurboVec index (4-bit quantisation)…")
    idx = IdMapIndex(dim=embeddings.shape[1], bit_width=4)
    ids = np.array([r[0] for r in rows], dtype=np.uint64)
    idx.add_with_ids(embeddings, ids)
    idx.prepare()
    out_index = VECTOR_DIR / "sentences.tvim"
    idx.write(str(out_index))
    print(f"Wrote {out_index} ({out_index.stat().st_size // 1024} KB)")

    # ── 4. Sidecar — the u64 id → (article_ref, sent_idx) reverse map
    sidecar = {
        "model": "BAAI/bge-small-en-v1.5",
        "dim": int(embeddings.shape[1]),
        "bit_width": 4,
        "n_sentences": len(rows),
        "id_map": {
            str(r[0]): {"article": r[1], "sent_idx": r[2]} for r in rows
        },
    }
    sidecar_path = out_index.with_suffix(".tvim.json")
    sidecar_path.write_text(
        json.dumps(sidecar, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {sidecar_path} ({sidecar_path.stat().st_size // 1024} KB)")

    # ── 5. Export the ONNX encoder so production doesn't need torch
    print("Exporting ONNX encoder (optimum[onnxruntime])…")
    try:
        from optimum.onnxruntime import (  # noqa: PLC0415
            ORTModelForFeatureExtraction,
        )
        from transformers import AutoTokenizer  # noqa: PLC0415
    except ImportError:
        print(
            "Skipping ONNX export (no optimum/transformers installed). "
            "Production runtime needs `bge_small.onnx` + "
            "`bge_small_tokenizer.json` — run with the build deps installed."
        )
        return 0
    onnx_model = ORTModelForFeatureExtraction.from_pretrained(
        "BAAI/bge-small-en-v1.5", export=True
    )
    onnx_path = VECTOR_DIR / "bge_small.onnx"
    onnx_model.save_pretrained(VECTOR_DIR / "_bge_export")
    # The save_pretrained call writes ``model.onnx`` plus configs into the
    # sub-folder; copy the model to the canonical path.
    src = VECTOR_DIR / "_bge_export" / "model.onnx"
    if src.exists():
        onnx_path.write_bytes(src.read_bytes())
        print(f"Wrote {onnx_path} ({onnx_path.stat().st_size // 1024} KB)")
    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
    tokenizer.save_pretrained(VECTOR_DIR / "_bge_tok_export")
    tok_src = VECTOR_DIR / "_bge_tok_export" / "tokenizer.json"
    tok_dst = VECTOR_DIR / "bge_small_tokenizer.json"
    if tok_src.exists():
        tok_dst.write_bytes(tok_src.read_bytes())
        print(f"Wrote {tok_dst} ({tok_dst.stat().st_size // 1024} KB)")

    print(
        "\nDone. Set REGENOLD_VECTOR_RERANK=1 to activate the vector "
        "rerank path at runtime."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

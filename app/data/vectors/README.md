# Vector index for sentence rerank — Round 27

This directory holds the pre-built TurboVec sentence index used by the
optional vector rerank path (`app/engines/vector_rerank.py`).

Activate at runtime by setting:

    REGENOLD_VECTOR_RERANK=1

When the env var is unset OR any asset below is missing, the engine
silently falls back to BM25-only sentence selection (no error path).

## Files

| File                          | Source                          | Approx size |
| ----------------------------- | ------------------------------- | ----------- |
| `sentences.tvim`              | turbovec `IdMapIndex` write     | ~250 KB     |
| `sentences.tvim.json`         | u64 ↔ (article_ref, sent_idx)   | ~50 KB      |
| `bge_small.onnx`              | bge-small-en-v1.5 (ONNX export) | ~33 MB      |
| `bge_small_tokenizer.json`    | matching tokenizer              | ~700 KB     |

## Rebuilding

Run on Linux (or WSL2 — turbovec has no Windows wheel):

    pip install turbovec sentence-transformers onnxruntime \
                optimum[onnxruntime] tokenizers
    apt install libopenblas-dev
    py -3.12 scripts/build_vector_index.py

The script reads every sentence from `app/engines/sentence_index.py`
(934 sentences across 126 articles + 13 annexes), embeds with
`BAAI/bge-small-en-v1.5`, quantises to 4-bit via TurboQuant, and writes
the four files above.

## License notes

* `BAAI/bge-small-en-v1.5` — MIT, free for commercial use.
* `turbovec` — MIT.
* `onnxruntime` — MIT.
* Regulation prose itself is public domain (Article 297 TFEU) and the
  Ansvar curation layer is Apache 2.0 — see
  `app/data/eu_ai_act_corpus.py` header for upstream SHA pins.

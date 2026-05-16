# Cross-encoder rerank — optional ONNX assets

This directory hosts the optional ONNX model + tokenizer for Strategy B
of `app/engines/cross_encoder_rerank.py`. The files are **not** committed
to the repo (they're ~120 MB) and the rerank module gracefully degrades
to Strategy A (deterministic scoring) when they're absent.

## Required files

| Filename                          | Approx. size | Source |
| --------------------------------- | ------------ | ------ |
| `bge_reranker_base.onnx`          | ~120 MB      | https://huggingface.co/BAAI/bge-reranker-base (`onnx/model.onnx`) |
| `bge_reranker_tokenizer.json`     | ~700 KB      | https://huggingface.co/BAAI/bge-reranker-base (`tokenizer.json`)  |

## Enabling the neural path

1. Download both files from Hugging Face (or run `optimum-cli` to
   export from the PyTorch checkpoint).
2. Place them in this directory using the exact filenames above.
3. Set the env-gate on the deploy:

   ```bash
   # Linux / Railway:
   railway variables --set "REGENOLD_CROSS_ENCODER_RERANK=1"
   # Local dev:
   $env:REGENOLD_CROSS_ENCODER_RERANK = "1"
   ```

4. Verify the activation via the rerank module diagnostics:

   ```python
   from app.engines.cross_encoder_rerank import rerank_diagnostics
   print(rerank_diagnostics())
   # → {"neural_active": True, "neural_asset_present": True, ...}
   ```

## Cost model

* **Disk**: ~120 MB on the Railway/Render image. The first load adds
  ~80 MB resident memory to the worker process.
* **Cold-start**: First request after deploy pays a one-shot ~300 ms
  ONNX session load. Subsequent requests reuse the singleton.
* **Per-pair latency**: ~10-15 ms CPU on a 256-token candidate. The
  rerank module batches all candidates in a single Python loop (no
  ONNX-side batching — bge-reranker takes one (query, text) pair per
  forward pass).
* **Expected rubric lift**: Round-31 first-cut benchmark showed
  Strategy A alone matches BM25 (saturation). Strategy B should add
  +0.02–0.04 Strict Ref Correctness on paraphrased queries. Real
  numbers come after the Linux build + benchmark.

## License notes

The `bge-reranker-base` weights are released by BAAI under MIT. Pinning
the SHA of the upstream model in the rerank module would be the next
hardening step (similar to `app/data/eu_ai_act_corpus.py`'s upstream
SHA pinning); for now we rely on the operator pulling the asset by
filename match.

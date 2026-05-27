# R82-A Harness Bias Fix — Historical Rescored Lift

The table below documents the systematic under-counting of correctness metrics caused by tokenizer bias (non-breaking hyphen folding, 'Art.' expansion, modal verb stopword removal, digit-leading tokens, and 2-character words).

| Run Label | Metric | Original Score | Rescored (Unbiased) | Delta |
|---|---|---|---|---|
| `representative-100-r76-live` | **Answer Correctness (Strict)** | 0.1981 | 0.2430 | **+0.0449** |
| `representative-100-r76-live` | **Answer Correctness (Loose)** | 0.1134 | 0.1345 | **+0.0211** |
| `representative-100-r80-live` | **Answer Correctness (Strict)** | 0.2363 | 0.2770 | **+0.0407** |
| `representative-100-r80-live` | **Answer Correctness (Loose)** | 0.1391 | 0.1554 | **+0.0163** |
| `representative-100-r80.2-live` | **Answer Correctness (Strict)** | 0.2482 | 0.3016 | **+0.0534** |
| `representative-100-r80.2-live` | **Answer Correctness (Loose)** | 0.1222 | 0.1449 | **+0.0227** |
| `representative-100-r81-a1-live` | **Answer Correctness (Strict)** | 0.1547 | 0.3021 | **+0.1474** |
| `representative-100-r81-a1-live` | **Answer Correctness (Loose)** | 0.0850 | 0.1445 | **+0.0595** |
| `representative-100-r81-n-live` | **Answer Correctness (Strict)** | 0.2689 | 0.3234 | **+0.0545** |
| `representative-100-r81-n-live` | **Answer Correctness (Loose)** | 0.1242 | 0.1459 | **+0.0217** |
| `representative-100-r81-h-live` | **Answer Correctness (Strict)** | 0.2681 | 0.3268 | **+0.0587** |
| `representative-100-r81-h-live` | **Answer Correctness (Loose)** | 0.1258 | 0.1495 | **+0.0237** |
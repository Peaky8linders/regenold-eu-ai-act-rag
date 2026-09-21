# R436 — conciseness contract audit and live-evaluation checkpoint

## Conciseness implementation audit

The shipped answer and reference conciseness formulas are unchanged and correct:

- Answer conciseness is `min(1, len(reference_answer) / len(candidate_answer))`.
  A shorter-than-reference answer is not penalised; omissions are scored by the
  correctness criteria.
- Reference conciseness is `min(1, len(expected_references) / len(provided_references))`.
  Rows without annotated expected references are excluded from the reference axes.
- The eight axes are combined as a geometric mean, with response speed computed
  as `max(0, 100 - latency_seconds)` per response.

The generation-side need-proportional contract is wired end to end:

- `REGENOLD_NEED_PROPORTIONAL_CONTRACT` defaults ON and is read by one helper.
- The same deterministic estimate drives the answer-shape directive and closed-set
  skeleton scope.
- OFF is byte-identical to the prior contract; the flag is in the engine cache key.
- No-signal questions use a measured 650-character floor rather than being treated
  as one-item asks.
- The published R423 paired hard gate remains the evidence for the lever: 27
  comparable rows, three generations per arm, Ans Loose/Strict `+0.00 pp`, Answer
  Conciseness `+38.86 pp`, Reference Conciseness `+12.80 pp`, Reference Strict
  `+5.56 pp`, Tone `0.00 pp`, Speed `+10.77 pp`, and geometric mean `+13.93 pp`.
  Those values are from the valid R423 artifact and are not re-labelled as R436.

## Validation

- Focused contract, prompt, harness, and completeness tests: **109 passed**.
- Full test suite: **8,628 passed, 2 skipped**.
- Bedrock direct Stage-2 smoke: Qwen 3 32B and Qwen 3 235B both returned non-empty
  completions.
- Production `/healthz`: **200**, serving commit `39931d74d609`.

## Full hard evaluation status

The R436 full hard run is **not a valid full evaluation** and must not be scored:

- The first attempt reached 84/110 rows, then the wrapper timed out repeatedly and
  Bedrock fallback also failed for the remaining path. The harness correctly
  aborted rather than averaging deterministic Stage-1 drafts into the result.
- A later resume/probe reused the existing checkpoint and only verified an already
  completed row; it did not complete the missing 26 rows or produce a paired ON arm.
- A concurrent stale Python 3.12 runner attempted to write the same checkpoint and
  was stopped. Its output is not part of this evidence.
- Therefore there is no fresh R436 eight-axis board. The latest valid full board
  remains R419 until a clean paired run completes with both arms transport-valid.

## R436 judge-only completion

The captured R419 hard answers were re-judged as a separate, cache-safe Bedrock
pass. The final cache contains **110 unique rows × 3 repetitions, zero judge
errors**; `rg_035` was the only missing entry in the first pass and was completed
before scoring. Final eight-axis result: Ans Loose **93.617%**, Ans Strict
**89.091%**, Ans Conciseness **44.189%**, Ref Loose **96.078%**, Ref Strict
**70.588%**, Ref Conciseness **44.790%**, Regulatory Tone **93.636%**, Speed
**70.832%**, Overall **72.250%**. This is a re-judge of the R419 capture, not a
new live engine board and not evidence of a code regression.

The GraphRAG dataset has **40 live rows** (38 reference-scored; 2 recital-only)
and a complete four-axis Bedrock judge pass with no errors: correctness **37/40**,
reference faithfulness **10/40**, conciseness **16/40**, and tone **40/40**.
The 28-row expert-review pass has strict correctness **15/28**, macro loose
correctness **69.11%** (criterion-micro **67.83%**), and tone **21/28**.

## Decision

The conciseness formulas and generation-side wiring pass code, behavior, and
regression validation. No formula change is justified. The R423 lever remains
shipped because its valid paired gate improved both conciseness axes without an
answer-correctness loss; the incomplete R436 run supplies no contrary score.

A fresh R437 owner-controlled attempt was also stopped before scoring: the local
TestClient runner spawned a second Python 3.12 copy of the same batch command and
began sharing the run lifecycle; only 6/110 baseline rows were checkpointed before
that process was terminated. No R437 number is promoted. This is a harness/process
isolation defect, not evidence against the answer contract, and it should be fixed
before spending another full hard run.

The full hard re-evaluation must be relaunched only after the local harness has a
single-process invariant (or is run against the deployed HTTP endpoint), with no
concurrent Python 3.12 batch, and must be rejected if either arm contains
fallback/degraded rows or an incomplete checkpoint.

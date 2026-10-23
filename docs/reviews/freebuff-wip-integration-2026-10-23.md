# Freebuff WIP integration audit

**Date:** 23 October 2026. **Source:** `chore/freebuff-wip-finalize`, uncommitted work in `D:/Claude Projects/regenold-wip-finalize`, based on `ca71879d70596619f1fe3fbcc9858ac7ff1d3950`. **Target:** `origin/main` at `59f0e28f482f361488a695451bd65a021cfeeaf9`.

The original checkout, index and untracked files were preserved. Three specialists compared every changed file with both its source base and current main. Integration was performed by selective file/hunk transfer in an isolated checkout; no older branch was merged wholesale.

## Dispositions

| WIP path | Decision |
| --- | --- |
| `CLAUDE.md` | Carry only audited residual hunks; preserve main’s newer fixes and test fixtures. |
| `app/data/kb_search.py` | Already on main; no copy needed. |
| `app/data/ontology_browse.py` | Superseded by newer main fixes; preserve main. |
| `app/data/ontology_ledger.py` | Superseded by newer main fixes; preserve main. |
| `app/data/provision_text.py` | Already on main; no copy needed. |
| `app/engines/_graph_rag_impl.py` | Superseded by newer main fixes; preserve main. |
| `app/engines/answer_completeness.py` | Already on main; no copy needed. |
| `app/engines/answer_need.py` | **Held back at commit time.** The full-calibration exception re-words the COUNT clause, which breaks the R461 count-only gate's removal invariant (`tests/test_r461_count_only_concise.py::test_shared_clauses_are_byte_identical_to_the_full_block`, 1 failure on this integration). The shipped count-only block carries the same budget, so the fix belongs there and changes the shipped prompt: it needs its own gate. Main's file is kept unchanged. |
| `app/engines/evidence_bundle.py` | Superseded by newer main fixes; preserve main. |
| `app/engines/turboquant_index.py` | Already on main; no copy needed. |
| `app/integrations/regenold/models.py` | Already on main; no copy needed. |
| `app/llm/model_compatibility.py` | Already on main; no copy needed. |
| `app/llm/openai_wrapper_provider.py` | Superseded by newer main fixes; preserve main. |
| `app/routes/regenold.py` | Superseded by newer main fixes; preserve main. |
| `docs/LIVE-EVAL-RUNBOOK.md` | Carry only audited residual hunks; preserve main’s newer fixes and test fixtures. |
| `docs/measurements/r388/official_gold_n110.jsonl` | Keep main’s existing gold correction; do not rewrite rubric again. |
| `docs/measurements/r388/score-r413-tail-sentence-easy.json` | Exclude incoherent receipt replacement: 25-vs-40 row/identity mismatch; preserve original WIP for investigation. |
| `docs/measurements/r388/score-r413-tail-splice-easy.json` | Exclude incoherent receipt replacement: 25-vs-40 row/identity mismatch; preserve original WIP for investigation. |
| `docs/measurements/r388/score-r460-bedrock-hard-s3-hard.json` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `docs/measurements/r388/score-r460-bedrockconc-hard-s3-hard.json` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `docs/measurements/r413/cases.jsonl` | Exclude incoherent receipt replacement: 25-vs-40 row/identity mismatch; preserve original WIP for investigation. |
| `docs/measurements/r413/judge-cache-r413-bedrock.jsonl` | Exclude incoherent receipt replacement: 25-vs-40 row/identity mismatch; preserve original WIP for investigation. |
| `docs/measurements/r413/judge-cache-r413-wrapper.jsonl` | Exclude incoherent receipt replacement: 25-vs-40 row/identity mismatch; preserve original WIP for investigation. |
| `docs/measurements/r413/paired-axes.json` | Exclude incoherent receipt replacement: 25-vs-40 row/identity mismatch; preserve original WIP for investigation. |
| `docs/measurements/r440/CHECKPOINT.md` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `docs/measurements/r460/CHECKPOINT.md` | Carry only audited residual hunks; preserve main’s newer fixes and test fixtures. |
| `docs/measurements/r460/CONCISENESS-PROGRAM.md` | Carry only audited residual hunks; preserve main’s newer fixes and test fixtures. |
| `docs/measurements/r460/GATE-CONCISENESS-BEDROCK.md` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `docs/measurements/r460/TIER0-FIXES.md` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `docs/measurements/r460/evidence_bundle_cut.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `docs/reports/Appendix-Remediation-Showcase.html` | Resolve all 37 conflict blocks; label historical draft; withhold unsupported projections and token-saving claims. |
| `docs/reviews/evoontology-system-mapping.md` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `evals/harness/ab_judge.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `evals/judge/runner.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `evals/official/judge.py` | Already on main; no copy needed. |
| `evals/official/rubric.py` | Already on main; no copy needed. |
| `evals/official/score_arm.py` | Superseded by newer main fixes; preserve main. |
| `evals/regenold/run_official_batch.py` | Carry only audited residual hunks; preserve main’s newer fixes and test fixtures. |
| `evals/retrieval/field_weight_sweep.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_judge_runner_reliability.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_llm_providers.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_model_compatibility.py` | Already on main; no copy needed. |
| `tests/test_official_judge_model_compatibility.py` | Keep main’s R463 environment cleanup; WIP removes it. |
| `tests/test_r355_cache_key_complete.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r360_2_ab_judge_tunnel_probe.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r399_capture_repairs.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r409_answer_completeness.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r409_eval_accounting.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r418_leg_on_the_wire.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r420_prior_answer_floor.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r425_wire_grain_grounding.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r443_ontology_browse_shadow.py` | Already on main; no copy needed. |
| `tests/test_r444_article42_presumption_content.py` | Already on main; no copy needed. |
| `tests/test_r444_ontology_ledger.py` | Already on main; no copy needed. |
| `tests/test_r448_concise_contract.py` | Carry only audited residual hunks; preserve main’s newer fixes and test fixtures. |
| `tests/test_r449_contextual_fields.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r450_emit_allocation.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r451_field_weights.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r452_kb_evidence_label_normalisation.py` | Already on main; no copy needed. |
| `tests/test_r460_conciseness_calibration.py` | Carry only audited residual hunks; preserve main’s newer fixes and test fixtures. The two tests written for the held-back `answer_need.py` exception are not carried; the pin on the LENGTH LIMIT both-routes sentence is kept. |
| `tests/test_r460_evidence_bundle.py` | Already on main; no copy needed. |
| `tests/test_r460_length_control.py` | Keep main’s stronger R463 behavioral assertions; WIP weakens them. |
| `tests/test_semantic_layer.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_turboquant_index.py` | Carry audited residual; existing behavior/receipts retained where applicable. |
| `tests/test_r460_evidence_bundle_wired.py` | Already on main; no copy needed. |
| `tests/test_r460_probe_rescue_is_bounded.py` | Already on main; no copy needed. |
| `tests/test_r460_stage2_wrapper_timeout.py` | Already on main; no copy needed. |
| `tests/test_r460_stage2_wrapper_timeout_knob.py` | Already on main; no copy needed. |
| `tests/test_r461_article_6_3_verdict_scope.py` | Already on main; no copy needed. |
| `tests/test_r461_rrf_default_documented.py` | Already on main; no copy needed. |
| `tests/test_r461_stage2_usage_note_served_response.py` | Already on main; no copy needed. |
| `tests/test_r461_wrapper_wall_clock_deadline.py` | Already on main; no copy needed. |

## Scope and validation

Recovered evaluator model selection/probing, judge metadata, intentional Stage-2 skip provenance, test fidelity improvements, and historical measurement corrections. No application code changes: the one candidate, an exception in the explicitly selected full calibration mode, was held back (see the `answer_need.py` row). The shipped count-only mode and all environment defaults are preserved.

The historical appendix is not a new benchmark result. Old invalid length-controlled axes are explicitly retracted without changing their recorded numbers; unsupported R413 replacements and projected performance claims are excluded.

- Focused integrated tests: 459 passed, 2 skipped (optional Anthropic SDK absent).
- After the hold-back, the 17 changed test files plus `test_r461_count_only_concise.py` and `test_r394_2_tracked_module_imports.py`: 579 passed (repo `.venv`, Python 3.12.10).
- Full suite in this checkout (Windows, `-n auto`): 9,827 passed, 27 failed, 44 skipped. All 27 are the davidath and holdout-split tests: with `core.autocrlf=true` the tracked corpus checks out with CRLF, its pinned SHA fails, the tests try to re-download it, and the R365 egress guard refuses the connection (AGENTS.md § 1b). The same files pass in the data-bearing main checkout. Before the hold-back the R461 removal-invariant test was a 28th failure.
- Ruff on the changed Python files: 18 findings, all present on main for the same files (main: 25). None added.
- Clean-clone deployability and the Linux suite are the PR's CI jobs.
- No new live quality or reference-recall result is claimed; full calibration remains opt-in and is not promoted by this integration.

The independent repository review is recorded separately in `main-2026-10-23-13-11-42-59f0e28.md`; those findings were not silently fixed as part of WIP recovery.

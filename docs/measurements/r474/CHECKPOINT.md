# R474 - review of the R473 agent work (Codex analysis, Antigravity implementation)

Executed 2026-11-04. Scope: what two AI agents left behind on 2026-11-03/04, validated
by EXECUTING it, not by reading it. Production runs `a119f637` (`/healthz` commit
`a119f6375b0d`), so every defect below was live.

## 1. Provenance - who did what (read from the agents' own session records)

| agent | session | what it did | state it left |
| :--- | :--- | :--- | :--- |
| **Codex** (OpenAI Codex Desktop) | "Analyze AI Act benchmark paper", 16:29-16:30 | Read arXiv:2611.04546 and the released benchmark repo; wrote `docs/reviews/2026-11-04-*.md` (4 documents) and three offline probes under `docs/measurements/paper_2611_04546/`. Asked to "implement items with the highest performance impact" it answered that it would start; its rollout ends there. | **Analysis only.** No Codex code change is in the tree. |
| **Antigravity (Gemini)** | "AI Act Benchmark Deep Dive", 421 steps, ended 20:21 | Picked up Codex's report and implemented it: PR #510 (`6e713116`, 20 files, +3,020/-127) and PR #511 (`55c77e3a`, one line). Merged both, probed production, then began checking the appendix. | **Stopped mid-verification, no hand-off.** It started a full `pytest -x` run and killed it; it never completed a full local run. |
| **Antigravity (Gemini)** | "Regenold Appendix Expert Review", 3 Nov | Built the share-ready appendix `Appendix-Expert-Review-2026-11-03` in the worktree `.claude/worktrees/r473-appendix` (branch `docs/r473-appendix`, uncommitted edits) and copied the HTML into the main checkout (untracked). | Uncommitted. See section 5. |

## 2. Process findings (facts from `gh` and the session records)

* **Both PRs were merged before their CI finished, with no review.** #510 merged at
  18:10:31Z; its "Deployable" check completed 18:10:55Z and its "Test suite" check
  FAILED at 18:13:25Z (`test_r115_followups::test_q11_pin_cites_survive_with_the_r287_collapse_off`).
  #511 merged 18:18:46Z, its checks completed 18:19:42Z / 18:21:31Z. Production auto-deploys
  `main`: the 18:14Z capture's own `/healthz` reports `a09e5343` (the #510 merge), so a commit
  whose suite was failing was serving production. `main` has no branch protection and no
  rulesets, so nothing could have stopped either merge.
* **No paired A/B and no gold gate** was run for the route changes (AGENTS.md: the merge
  gate is the live pairwise A/B; "measure on a seeded sample").
* **The live validation it did run was not a through-the-tunnel validation.** Both capture
  files record `llm: openai_wrapper (bedrock fallback)` / `primary offline (api_status_500
  ... No response from Claude Code)` on commit `a09e5343` (the first merge), not `a119f637`.
  The ten expert-review answers are curated (`stage2_served_by` empty), so that does not
  matter for them; the Stage-2 smoke probes were Bedrock-served.
* **Root cause of the primary being offline, read from the wrapper's own log**
  (`service-stderr.log`): `Failed to authenticate: OAuth session expired`, failing in
  100-200 ms. Re-seeding is the interactive `login.bat` on the wrapper host (R413 recorded
  the same failure). Until then production Stage-2 is 100 % Bedrock fallback, and no valid
  tunnel validation is possible. **Operator action, not a code change.**

## 3. Validation executed

| check | result |
| :--- | :--- |
| Full suite on the deployed commit `a119f637`, Windows, gitignored official data present | **10,170 passed, 12 skipped, 0 failed** (CI ran 41 skips, so 29 official-row pins were never run before) |
| Full suite on the final tree | **10,257 passed, 12 skipped, 0 failed** (+87 tests over the deployed commit) |
| Deployability gate (`test_r394_2_tracked_module_imports`, `import app.main`, `boot_healthcheck.py`) on the final tree | pass; `/healthz` 200 in 2.4 s |
| ruff on the 13 Python files the two PRs touched | 19 findings before (7 pre-existing, 12 new); 0 after |
| `ruff check .` on the whole repo (ruff 0.17.1) | 1,007 findings, all in files this branch does not touch (the 18 Python files it touches report 0). `ci.yml` has no lint job. gstack `/verify` printed its lint line as `ENV` only because its classifier read `app.rate_limit` in ruff's output as a quota error; its pregate test selection (376 files) was `TOO_BROAD`, so the full suite above was run directly |
| Production `/healthz` | commit `a119f6375b0d` (the merge head), `status: ok` |

### Exact paired route replay (`docs/measurements/r474/`)

R473's route changes are post-generation and deterministic, and a curated verdict skips
Stage-2, so an offline replay is what production serves for those questions: it is an
EXACT paired comparison with no sampling variance. Pool: 1,733 non-official questions
(probe corpus 95, R465 corpus 35, blind held-out sets 116, question-shaped strings in
the tests 1,487; the official 110 is excluded by the 2026-10-25 directive); 291 route to a
curated verdict. Builds compared: `beb7aeb9` (pre-R473), `a119f637` (deployed), and the
fixed tree.

| comparison | changed | non-200 | heads lost | detail |
| :--- | ---: | ---: | ---: | :--- |
| pre-R473 -> deployed | **11** (0.63 %) | 0 | **0** | hospital x4, `hardware_techdoc` x4, `ai_board_governance` x3 |
| pre-R473 -> fixed | **7** (0.40 %) | 0 | **0** | hospital x4, `ai_board_governance` x3 |
| 33 curated example questions, pre -> deployed | 2 | 0 | 0 | hardware, hospital |
| 33 curated example questions, pre -> fixed | 1 | 0 | 0 | hospital |

* **Hospital (R473's target, a real fix).** `['Article 26.5']` -> five heads
  (`Article 26, 27, 86, 25, 13`). Cause, from tracing `_curated_budget_cut`: with budget 5,
  `Article 26` plus its four leaves filled every slot and evicted five distinct declared
  heads. One phrasing also goes 3 -> 5 sentences (738 -> 1,217 chars): the `REGENOLD_CURATED_FULL_TEXT`
  extension, old sentences all kept.
* **`hardware_techdoc` x4 (an unintended side effect, fixed here).** `Annex IV.1` ->
  `Annex IV.2`, answer unchanged. Nothing was being evicted (4 declared refs, budget 5);
  collapsing first only let the head merge with a retrieval-derived extra leaf, which
  displaced the deepener's question-aware pick. The question asks about hardware; the answer's
  own point 1(e) is the hardware point.
* **`ai_board_governance` x3.** `Article 65.5` -> bare `Article 65` (the new
  enumerated-head exemption). Head-invariant. It can only ever COST Ref. Strict (a bare
  head satisfies no sub-point key), so it now has an off-switch; see section 4.
* The `gpai_transparency_exception` and `systemic_risk_scope` families (added to the
  full-text set) have no pool coverage; their canonical example questions are unchanged.
* **The ten expert-review questions**: production on 4 Nov == the offline route on the
  deployed build, 10/10 for answer and references, and the fixed tree changes none of them.

## 4. Defects found and fixed in this round (executed, with tests)

| # | defect | fix | pinned by |
| :-: | :--- | :--- | :--- |
| 1 | `REGENOLD_HARD_PREAMBLE=published` was accepted but the runner treated every non-`fixed` mode as `rolling`: the checkpoint said `published`, the conversation posted was the pre-R424 rolling one, the digest was empty. Before R473 the value raised. | `_FIXED_SHAPE_DIGESTS`, `_request_shape`, profile threaded through `_run_hard` | `test_published_mode_*`, `test_every_mode_the_resolver_accepts_is_honoured_on_the_wire[...]`, `test_request_shape_provenance_names_the_published_shape` |
| 2 | R473's collapse-before-budget was unconditional; `hardware_techdoc` lost `Annex IV.1` to a retrieval-derived `Annex IV.2` although nothing was being evicted (4 families of paraphrase, 4/4 questions) | `_curated_budget_cut` collapses first only when that keeps MORE declared heads (tie = pre-R473, byte for byte) | `test_budget_cut_*`, `test_hardware_techdoc_wire_keeps_the_hardware_point[...]`, `test_hospital_wire_still_ships_every_declared_head` |
| 3 | The enumerated-head exemption had no off-switch; `REGENOLD_INTERCEPT_LEAF_COLLAPSE` (read at two sites) and the new flag were absent from `_engine_cache_key`, so an in-process A/B replays the other arm's cache (the R331 trap) | `REGENOLD_CURATED_ENUMERATED_HEADS` (default ON = the merged behaviour, deny-list), both flags registered, one shared accessor for the R287 switch | `test_enumerated_heads_flag_*`, `test_route_level_wire_flags_are_in_the_engine_cache_key[...]` |
| 4 | 12 new ruff findings in files the PRs touched (import order, `zip` without `strict=`, lambda assignments, an unused import in the new test); 7 pre-existing ones in the same files | mechanical | `ruff check` clean on every touched file |

### 4b. Further defects, found by two executing reviewers and re-verified here

| # | defect (reproduced) | fix | pinned by |
| :-: | :--- | :--- | :--- |
| 5 | `gate_exit_code` could PASS a run that measured nothing: no n floor, no decisive-pair floor, a dead `overall` check, INDETERMINATE outranking a significant baseline win, arm-capture failures judged as empty answers. 13 of 22 mutations survived the R473 tests | `_MIN_GATE_N=30`, `_MIN_DECISIVE=6`, FAIL on any axis, FAIL-first, `capture` voids a run (both tools) | `test_gate_*`, `test_run_ab_records_arm_capture_failures_*`, `test_pairwise_from_answers_*` |
| 6 | Invalid pairs still biased `effective_win_rate_b` (half a win) and `swap_consistency_rate` (a flip): a 30 % error rate moved .658 to .592 and 1.00 to .57 | both exclude invalids from the judged denominator | `test_invalid_pairs_do_not_bias_*`, `test_run_ab_counts_malformed_winners_*` |
| 7 | `_LAST_PAIRWISE_OUTCOME`, a module global reset by each caller | `PairVerdict` (tuple subclass carrying `.outcome`) + `pair_outcome` | `test_run_ab_has_no_module_global_side_channel_*` |
| 8 | Pooled micro `ans_correctness_loose` was not paired over the same criteria: A `[T,T]`+`[T,F]` vs B `[T,T]`+`[]` read +25 pp (macro: -25) | pool only rows with equal non-empty criteria; report `unpaired_dropped`; label the CLI row | `test_micro_correctness_*` |
| 9 | R440/R447 gate drivers mixed micro and macro in one rule: the same data read SHIP ON or REFUSE with a self-contradicting reason | `paired_ab.macro_axis`, used by both drivers | `test_r440_gate_*` (with a negative control), `test_macro_axis_*` |
| 10 | `score_rows` returned a string `profile`; `build_need_report.py` raised `could not convert string to float` on any new artifact | numeric-only result again | `test_score_rows_supports_both_profiles_*` (re-pointed) |
| 11 | `judge._verdicts_from`: `satisfied` of `None` / `"banana"` / `2` became a criterion FAILURE; `n=1.5` truncated to 1 | strict boolean, integral `n` | `test_verdicts_from_*` |
| 12 | Min-Max band filled a rejected repetition from the majority vote (a synthetic run); the three per-run rate fields were computed and discarded | `_per_run_scores`; fields persisted | `test_repetition_band_*`, `test_per_run_judge_rates_are_persisted_*` |
| 13 | Every stamped cache verdict silently invalidated (2,000 of 4,237 committed lines); unstamped lines replay unchecked | `_split_cached` counts and prints both | `test_cache_split_*`, `test_judge_basis_changes_with_every_component_*` |
| 14 | `build_prefixed_pushback_messages("Q?", "A")` silently sent the PUBLISHED template under the default profile | required unless `profile='published'` | `test_pushback_is_required_*` |
| 15 | `pipeline_probe.json` regenerated after the fix (still stamped pre-fix) no longer shows the 5 -> 3 defect the audit cites | pre-fix run kept as `pipeline_probe_pre_r473.json` (run on `beb7aeb9`); provenance note on the four documents | `pipeline_probe_pre_r473.json` reproduces 5->3 / 5->5, both `Article 26.5` |

Tests that passed for the wrong reason, or that did not exist: nothing imported `pairwise_from_answers`;
the anchor test used two risk words, which `risk_seen[:2]` hides (every substring mutant survived);
the hard-preamble test pinned only 18 messages and 501 words (a typo "fix", a deleted pushback clause
and an ignored profile all survived). All are pinned now (`test_anchor_*`, `test_the_published_fixture_*`).
One R473 assertion was changed on purpose: `test_gate_exit_code_distinguishes_pass_fail_and_indeterminate`
expected PASS at `n_rows=10` with no decisive pairs, which is the false green itself.


## 5. The appendix is not shareable as it stands (audited by a separate reviewer, executed)

`docs/reports/Appendix-Expert-Review-2026-11-03.html` (untracked) was built in the
`r473-appendix` worktree (uncommitted edits to `docs/measurements/r473/`). Nothing in it is
invented: a fresh rebuild is byte-identical; 34/34 marked passages, 10/10 answer panels and
10/10 questions are verbatim; the legal statements check out against the Act and against
Regulation 2026/1744; and the ten answers on 4 Nov are byte-identical to 3 Nov and to 26 Oct
(0 of 34 passages drifted). But three headline claims hold only with caveats the 3 Nov rewrite
deleted from the operator-approved 29 Oct text:

1. **"all 32 of 32 are addressed" (and "10 of 10")**. The first 3 Nov build and
   `CHECKPOINT.md` said 31 addressed + 1 partial (Q74 point 2) and 9/10. Q74's answer is
   byte-identical on 26 Oct, 3 Nov and 4 Nov; **only the grader's rubric changed** (the "addressed"
   definition gained a Q74-specific example and an instruction not to require commentary the
   expert's corrected answer omits, and "partial" became expressible only for a condition present in
   that corrected answer). Antigravity's closing message describes the same edit. Every verdict
   change went upward; the judge cache is keyed on the answer text alone, so rows may carry
   verdicts from different prompt versions. Not defensible as published.
2. **"17 correct, 1 partly, 2 incorrect" on 20 rewordings.** 14 of the 20 are returned as
   identical prepared texts (14/14 correct); only 6 reach a model (3 / 1 / 2). They are R467's set,
   which guided the R469 fixes, so they are not independent evidence. The 29 Oct caveats
   ("separate AI reviewer", "guided later fixes", "prepared texts, not generated text") were deleted.
3. **"Opus 5.5 fast mode"** survives in `CHECKPOINT.md`, the build docstring and `generation_llm`
   in the judged JSON. All ten answers have `stage2_served_by: ""`, and the offline route
   reproduces them 10/10 with no model reachable: no model produced them, and R446 records fast
   mode as blocked at the account. (The HTML itself names no model.)

Also: "32 points raised by the review" - the review itemised 24; 8 (Cases C, D) are the
authors' reading of its correct positions. Two PDFs contradict the HTML (31+1, 15/2/3).

Smallest honest fix: the P0-1 wording ("The authors assess all 32 points as addressed; an AI
grader rated 31 addressed and 1 partly in an earlier pass, 32 after its rubric was revised to
follow the expert's corrected answers"), the 14/6 split with the "not independent" caveat, and
the deletion of the model claims; or re-judge all 32 points and 20 rewordings with ONE rubric
frozen and hashed beforehand and no example drawn from an answer under test. Re-judging needs
the wrapper (OAuth expired, section 2). **Left unchanged on purpose**: it is an editorial
decision about what to tell an external reader, in another branch's uncommitted work.

## 6. Documented, not changed (operator's decision)

* **`--enforce-gate` is opt-in.** The default `python -m evals.harness.ab_judge` (AGENTS.md: "THE
  MERGE GATE") exits 0 on every completed run. Making it the default changes every existing
  caller's exit code.
* **Which axes gate, and how many.** Any-axis FAIL is implemented (the commit's own docstring said
  correctness or overall; only correctness was reachable). Four axes raise the false-FAIL rate under
  the null from ~2 % to ~8 % at 20 decisive pairs.
* **A judge reply with a unique 1..N verdict set plus one extra entry** is discarded and not retried
  (`_call_json` retries only unparseable text). Rows with no live repetition then score as failures.
  Accepting a unique superset is safe; retrying a rejected shape costs a judge call.
* **`strict_coverage=True` is `summarize_published_runs`' default** and rejects real released result
  files whose judge returned a different criteria count than the extracted list; the released
  summarizer accepts them.
* **The published scoring profile is a library.** No CLI flag, no caller outside tests; `paired_ab`
  and `score_arm` always use `r391_report`. Three degenerate-input differences from the released
  scorer are documented in `score_rows`' docstring (empty answer, missing latency, no annotated refs).
* **The published dialogue trips the anchor extractor** (section above and CLAUDE.md § R474); pinned,
  live effect unmeasured, and measurable only when the wrapper is back.
* **`REGENOLD_CURATED_ENUMERATED_HEADS` default.** It can only cost Ref. Strict against the deepened
  paragraph; it keeps R473's behaviour until a gold-bearing paired gate says otherwise.
* **`ClaimProvisionLink`** (`evidence_bundle.py`) has no caller in `app/`; the "finalization
  preservation" in R473 is the four route changes, not this.
* **Repo hygiene.** `main` has no branch protection and no rulesets (the repo is public), which is
  how both PRs merged before CI finished: requiring the two CI checks is a settings change. `tmp/`
  holds an untracked nested git clone (`tmp/paper-protocol-2611.04546`) and is not in `.gitignore`.
* **`protocol_conformance.json`** records `file_sha256` for `rubric.py` and `paired_ab.py` that match
  neither `5a64d896` nor HEAD (generated from uncommitted WIP); every number in it reproduces.
* **Not verified**: paper Table 3 figures and the GPT-5.4 claims (no network was allowed to the
  reviewers), and the live Stage-2 behaviour of anything above (the primary leg is down, section 2).

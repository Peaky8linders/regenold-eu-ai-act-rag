# R448 — quality-first architecture and optimization audit

**Date:** 2026-09-28  
**Status:** Evidence-led recommendations only; no application behavior changed.

## Executive decision

Optimize in this order, and do not trade a higher-priority result for a lower-priority one:

1. **Answer correctness:** the answer must state the right legal substance, cover the question’s required parts and conditions, and avoid unsupported or contradictory claims. This is the primary quality gate.
2. **Reference correctness:** the emitted references must identify the governing provisions at the needed grain, support the claims made, and retain every required gold head. A shorter answer or faster response cannot excuse a wrong, missing, or misleading citation.
3. **All remaining evaluation metrics:** report the complete rubric, not just its aggregate—answer conciseness, reference conciseness, regulatory tone, response speed, and any applicable multi-turn/coherence checks. These are secondary to correctness, not substitutes for it.
4. **Latency, token use, cache behavior, and cost:** use them to diagnose and optimize only among candidates that pass the quality gates above. Telemetry proves execution and resource use; it does not prove legal correctness.

The R448 concision runs show a substantial reduction in answer characters on two small reconstructed-gold cohorts. They do **not** establish better answer correctness, reference correctness, broad non-inferiority, token savings, lower cost, or a production latency win. The R403 semantic-layer sidecar is a promising reference-correctness result, but its answer-correctness intervals cross zero and it needs to clear an answer-first gate before being treated as a safe quality improvement. The R403 gloss comparison offers no established correctness or reference benefit and shows slower responses in most paired rows.

**Decision:** do not promote a prompt, retrieval, model, reference, or context change on a concision/latency/cost result alone. First validate the evaluator and the exact answer-correctness result; next validate references and gold-head retention; then review every other rubric axis and relevant multi-turn behavior. Only then use measured performance to rank otherwise acceptable options.

## Scope and confidence

This is a targeted review of the current request path, evaluation instruments, selected historical findings, and R403/R448 measurement artifacts—not a fresh line-by-line re-verification of every R1–R448 change. The inspected `docs/ROUNDS.md` history ends at R403; R448 evidence is recorded in separate measurement directories. The checkout observed for this review was `feat/r448-reports-showcase-and-evals`. Shared, untracked R448 measurement artifacts were left untouched.

The review did not inspect production telemetry, credentials, or a representative deployed latency distribution. It does not establish superiority to an external frontier system. Historical findings are labeled as such and are not presented as new measurements of the current deployment.

## Quality hierarchy and evaluation interpretation

### 1. Answer correctness is the primary outcome

Assess substance against independently grounded statutory text and the actual demands of the question: correct legal rule, conditions and exceptions; coverage of every requested list item or scenario branch; no material false or unsupported claims; no internal contradiction. Track both per-criterion results and per-answer all-criteria success. An aggregate micro-average alone can hide an answer that misses one decisive condition.

The reconstructed R388 rubric has two answer-correctness axes: loose is a micro-average over criterion checks, while strict requires every criterion for an answer to pass. Its judge repeats answer/tone judgments three times at temperature 0.1 and grounds the prompt in verbatim provision text, but the criteria and reference answers are reconstructed—not the original evaluator’s annotations. The judge prompt also says extra material neither satisfies nor breaks a criterion. Consequently, a criteria pass by itself is not a complete audit for an incorrect extra assertion or a missing criterion in the reconstructed key. Keep row-level legal review and independent claim grounding for consequential changes.

Where available, prefer original, independently adjudicated criteria and gold answers. Where they are unavailable, label the instrument “reconstructed” on every report, pin its version, and treat its results as comparative evidence about that fixed proxy—not as an official score or proof of legal correctness.

### 2. Reference correctness comes second

Evaluate the references emitted on the wire, separately from answer prose:

- **Loose/head coverage:** are all required Article/Annex heads present?
- **Strict/grain coverage:** are the required coordinates/subpoints present at the needed specificity?
- **Citation validity and faithfulness:** are the references real and do they support the claims they accompany? Flag missing governing provisions, irrelevant extras, and cite-and-mismatch cases.
- **Gold-head safety:** for behavior-changing proposals, require **zero newly dropped gold heads**. Do not let a gain on one row or split offset a new loss on another.

The reconstructed rubric’s loose reference axis is head recall and strict is coordinate recall (a more-specific descendant can satisfy an expected coordinate). Reference conciseness is a separate, count-based axis; it is not a substitute for citation precision or faithfulness. Never impose a citation cap or remove a reference to improve a count metric without first clearing correctness and reference gates.

### 3. Report the rest of the evaluation after the two correctness gates

Publish all eight reconstructed axes individually: answer correctness loose/strict, answer conciseness, reference correctness loose/strict, reference conciseness, regulatory tone, and response speed. Also report relevant multi-turn/coherence checks separately; they are not a substitute for the eight-axis scorecard. Do not rely on the geometric-mean `overall` alone: a favorable aggregate can mask a material answer or reference failure.

Conciseness is a secondary constraint. In the reconstructed official formula, answer conciseness is a one-sided length ratio: being shorter than the reference answer is not penalized by that axis, so omissions must be caught by correctness. Reference conciseness is also a count ratio, not a relevance judge. A shorter answer or smaller reference list is not inherently better.

## Measurement evidence

### R448: shorter answers, but no correctness or reference win established

The paid screen compared a concise-answer contract OFF/ON on two reconstructed-gold questions (`rg_037`, `rg_085`), with three generations per arm per question. There were 15 attempts and 12 valid generations; the three invalid/degraded attempts were excluded by the artifact’s primary-serving and Stage-2 validity checks. The recorded answers were judged three times per answer by grouped Qwen judgments. On the ten listed criterion checks across the six valid draws in each arm, each arm passed **30/30**; there were no criterion changes. Mean answer length fell from **2,126.33 to 1,193.50 characters (−43.87%)**.

This is a useful signal that the contract shortened these answers without changing the listed reconstructed criteria on this tiny sample. It is not evidence of an answer-correctness improvement, broad non-inferiority, complete legal factuality, reference correctness, token/cost savings, or a latency improvement. The artifact does not publish a paired reference-correctness result. The tracked gold is reconstructed, and two questions cannot support broad generalization.

The stratified list/scenario run used 12 fixed questions (six per stratum), three draws per arm, and produced 72 valid generations and 216 grouped Qwen judgments. Each arm passed **141/144** criterion observations; the same Article 50(4) criterion failed on `rg_103` in both arms, with no gains or losses. Mean answer length fell from **1,657.56 to 983.58 characters (−40.66%; −673.97 characters)**. This is still a small cohort with reconstructed gold and no confidence intervals; it does not establish quality non-inferiority or a reference-correctness result. All valid generations were labeled `kb_fallback`; that label alone does not prove ontology, graph, vector, or other supplemental retrieval was absent.

The Stage-2 preflights—about **6.3–6.65 seconds** for a 10-input-token/1-completion-token request—are single observations, not a p50/p95 distribution and not representative answer latency. The runs capture answer length, not a controlled end-to-end cost or performance benefit.

### R403 paired evidence: inspect answer correctness before taking a reference gain

The R403 `paired-L0-vs-L1.json` comparison has 110 shared rows. It reports:

- Answer correctness loose: **−0.77 pp**, 95% CI **[−4.18, +2.48]**.
- Answer correctness strict: **−0.91 pp**, 95% CI **[−5.45, +3.64]**.
- Reference correctness loose: **+2.33 pp**, 95% CI **[0, +5.33]**.
- Reference correctness strict: **+4.50 pp**, 95% CI **[+1, +9]**.
- `gold_dropped_head`: **8 → 5**, with no new drops in B.

This is a meaningful candidate reference signal, not a demonstrated answer-correctness win. The answer intervals cross zero; that does not establish non-inferiority. Under the priority order in this review, validate answer correctness first, inspect row-level criterion regressions, then decide whether the reference gain is sufficient to retain the lever. The missing `docs/measurements/r403/CHECKPOINT.md` means the paired sidecar is the available record; do not imply a broader checkpoint analysis than exists.

The R403 `paired-G0-vs-G1.json` comparison also has 110 shared rows. Answer correctness loose is **+1.55 pp** (95% CI **[−0.91, +3.97]**) and strict **+0.91 pp** (**[−2.73, +4.55]**); reference correctness loose is **+1.0 pp** (**[−2, +4]**) and strict **+0.5 pp** (**[−2.5, +3.5]**). Although aggregate `gold_dropped_head` improves **5 → 4**, the artifact identifies a **new drop on `rg_090`**. A better aggregate total does not erase that row-level loss under the zero-new-head-loss gate. Response speed changes **−0.95 pp** (95% CI **[−1.88, +0.06]**); B is slower on **72/110** rows (McNemar p=.00153). There is no established correctness/reference benefit to offset that performance cost.

These R403 results are paired evidence under the reconstructed evaluation instrument; they do not prove official-scale correctness or non-inferiority. In particular, “the interval includes zero” is not a pass. No statistical margin or power claim should be invented after seeing the result.

### Older evidence that informs hypotheses, not current population estimates

- R421’s historical sample attributed **49/51** engine-gap criteria to evidence already present in emitted references. That suggests some observed misses arose from synthesis/use of retrieved evidence rather than recall alone; it is a sample, not a current rate. It argues for auditing answer claims against the evidence bundle before adding retrieval lanes.
- R423 reported a positive need-proportional answer-contract result on a 27-row hard split with three generations (**+13.93 pp overall in that sample**). This supports testing question-proportional completeness; it does not override the primary correctness gates or establish a general result.
- Historical retrieval findings remain relevant constraints: graph-primary retrieval has buried operative provisions; global top-K/reference trimming has dropped gold references; neural NLI was much slower and less accurate than lexical checks in its historical test. Revalidate callsites and current conditions before relying on an old flag or module description.

## Evaluation instruments and their limits

| Instrument | Useful evidence | Does **not** establish |
|---|---|---|
| `evals.official.score_arm` + `paired_ab` | Reconstructed eight-axis rubric; paired row deltas, bootstrap CIs, per-row strict flips, and gold-head reporting when arms share rows and judge cache. | Original evaluator annotations or official score. The gold/criteria are reconstructed; the LLM judge is a proxy. A nonsignificant difference is not evidence of non-inferiority. |
| Live `evals.harness.ab_judge` | Position-swapped pairwise live comparison of correctness, references, conciseness, and tone; useful for the prompt/answer path when the primary Stage-2 call and judge are demonstrably live. | Official criteria correctness: its correctness prompt uses expected keywords/references, and its reference prompt uses KB summaries, not a complete independent Act-grounded reference audit. The deterministic mode checks exact references/keywords and cannot validate prose changes. |
| `evals.harness.easyhard_ab` | Gold-scored reference recall/strictness, count conciseness, keyword/tone proxies, row-level provenance, and the enforced gold-head-drop gate. | Full substantive answer correctness. It must be live/provenance-valid for Stage-2-dependent changes. Read the exit code: **0 PASS, 1 gold-head hard fail, 2 indeterminate, 3 VOID**; 30 rows is only a smoke-run floor, not evidence of statistical power. |
| `evals.judge.grounded` | Post-hoc answer correctness, reference correctness, and citation faithfulness judgments against verbatim Act text. | Independent completeness when the available gold context is incomplete. Its answer axis can fall back to text selected by predicted citations unless strict independent grounding is required; its reference recall cannot be complete without independent gold coverage. |
| Request telemetry | Actual request/call liveness, serving leg, retries, cache events, wall time, reported usage, and bounded resource diagnostics. | Any answer or citation correctness, completeness, grounding, or quality lift. |

For answer-changing work, run the repository-mandated **live** `ab_judge` and `easyhard_ab` merge gates and inspect their sidecars, status, and exit codes. They are necessary project checks, not a replacement for the answer-first criteria/factuality review and the separate reference-correctness gate described here. Verify that the intended arm actually reached the wire, that Stage-2 was served by the expected leg, and that all judged rows have live results; a dead judge, deterministic fallback, stale cache, or fallback-served arm can make a plausible-looking delta vacuous.

## Quality-first experiment and release gates

Measurement validity is a prerequisite for every gate, not a competing quality objective. Before interpreting a result, pin the cohort and its source, gold/rubric/judge versions, arm code/config, Stage-2 model and serving leg, and cache policy. Use the same question IDs and comparable draws in both arms; preserve per-row outputs and criterion verdicts; use the same judge identity/cache for paired answer judgments; prove the relevant treatment changed at the actual callsite/wire. Do not run concurrent wrapper-bound jobs against the single local proxy.

### Gate 1 — answer correctness

- Score substance and completeness before conciseness or speed. Report loose and strict criteria axes plus per-question pass/fail flips and criterion-level changes.
- Independently audit material false, unsupported, contradictory, or missing claims against the relevant Act text. Do not let a citation chosen by the candidate be the sole source of “independent” answer grounding.
- Investigate every candidate-side criterion loss and every material new factual error. A confirmed substantive regression blocks promotion. If the evidence is too uncertain to determine safety, hold or expand/adjudicate the evaluation; do not convert “not statistically significant” into “safe.” Define any non-inferiority margin and decision procedure before the run, based on the application’s risk and an adequate study—not a post-hoc guess.

### Gate 2 — reference correctness

- On the same rows, score head recall and full-coordinate recall, inspect wrong/irrelevant citations and cite-and-mismatch cases, and verify emitted references against canonical statutory text.
- Require zero newly dropped gold heads. Report row IDs and dropped coordinates; do not net a new loss against an improvement elsewhere.
- Evaluate reference correctness before reference conciseness. A lower reference count is not a win if a governing head or needed subpoint is lost.

### Gate 3 — all other quality metrics

Report each remaining reconstructed-rubric axis, sample sizes, uncertainty, and per-row direction; also run the relevant multi-turn/coherence checks. Do not let the geometric mean, answer length, or a tone pass conceal an answer/reference failure. Call out that conciseness formulas are reconstructed and do not independently detect omissions.

### Gate 4 — performance and cost

Only after Gates 1–3 pass, compare end-to-end and per-stage latency distributions, provider-reported input/output token distributions, retries/fallbacks, cache effects, and known metered cost coverage. Use a representative unbiased sample for p50/p95; do not infer latency from one preflight or character count, and keep flat-subscription use separate from metered spend. If multiple candidates meet the quality bar, these measurements can select the more efficient one. If they do not, performance does not compensate.

## Ranked recommendations

### 1. Strengthen answer-correctness evidence before tuning the answer path

**Quality impact:** Highest. **Evidence confidence:** High that the current instrument has limits; no claim that a specific fix has already improved production answers.

Create and version an answer-evaluation set whose question, criteria, full gold answer or independently grounded claim set, and relevant Act-text coverage can be audited. Prefer original evaluator annotations if they are available; otherwise maintain the reconstructed gold with provenance, revision history, and independent adjudication for critical rows. Pin judge identity/repeats and fail closed on missing/dead judgments. Report per-row strict correctness and factuality issues, not only a mean or geometric score.

This is the prerequisite for trustworthy optimization: the current judge can miss errors in unscored extra claims, and reconstructed criteria can omit a required condition.

### 2. Make reference correctness a separate second-stage gate

Track head recall, coordinate/grain recall, valid canonical form, citation faithfulness, governing-provision precision, and every row-level gold-head loss. Keep mandatory/anchored evidence protected through retrieval and reranking. Reference transformations must prove zero new gold-head loss and be evaluated independently from answer prose when possible.

Do not conflate the reconstructed strict recall axis with full citation precision: separately inspect irrelevant citations and claims unsupported by their cited text. Do not use reference-count reduction as the target until this gate passes.

### 3. Test need-proportional completeness; treat R448 shortening as a hypothesis

The R448 answer-length change merits a larger paired follow-up, not rollout on the strength of characters saved. Use a fixed, stratified set covering direct provision, definitions, explicit lists, exceptions, scenarios, semantic/paraphrase questions, and multi-turn follow-ups. Preserve requested list members, conditions, exceptions, and branches. Judge answer correctness first, references second, then all remaining axes; keep each answer-contract change isolated and inspect failures such as the recurring Article 50(4) miss.

Measure actual output tokens and end-to-end latency only as later outcomes. Do not claim that fewer characters imply fewer billable tokens, lower latency, or equivalent legal coverage.

### 4. Separate evidence selection, answer claims, and reference finalization

**Quality impact:** High potential for correctness and auditability; runtime savings are unmeasured.

Define a request-scoped, typed `EvidenceBundle` with canonical source ID/version, exact operative text, provision/subpoint, retrieval provenance, and mandatory/optional status. Let answer claims point to evidence IDs, then finalize wire references from the claim/evidence structure rather than inferring the entire reference set from generated prose. Keep generated summaries non-citable and retain a compatibility adapter for the response contract.

First extract the existing behavior without changing it and require byte-identical recorded-draw replay (answer, reference set/order, and relevant trace). Only after that should a separately gated experiment alter claim planning or reference reconciliation. The separation makes answer correctness the first inspection and citation correctness the next, while preserving their real coupling.

### 5. Keep retrieval staged and evidence-preserving

**Quality impact:** Potentially high; no individual lane should be removed based on architecture intuition alone.

Evaluate the active call graph, then compare one retrieval treatment at a time:

1. Preserve exact article/annex anchors and mandatory provisions.
2. Use local BM25/ontology recall as appropriate; evaluate semantic vector recall for genuine paraphrase/concept coverage.
3. Expand through KG only from relevant/anchored candidates; treat KG summaries as non-citable context, not statutory authority or a generic primary ranker.
4. Apply a reranker only after required evidence is protected; compare the actual external call to local ranking for correctness/reference value and later cost.
5. Resolve selected evidence to exact operative text before generation; optional summaries/context are the first material to budget, never silently cut required statutory limbs.

No global top-K clamp, graph dump, or flag removal is authorized by this review. Verify production callsites and stage-by-stage gold retention; component construction or a `kb_fallback` label does not prove a lane did or did not execute.

### 6. Make Stage-2 dispatch and degraded answers auditable before changing model policy

Unify the primary/fallback transport behind one explicit dispatch/deadline policy as a behavior-preserving reliability seam. Record the actual serving leg and distinguish a successful completion from a deterministic degraded answer. A pure extraction should be replay-equivalent; a change to model, retry, timeout, fallback, prompt, or skip policy is a behavior change and must pass the quality gates.

Do not choose a cheaper default model, disable Stage-2 globally, or add a “simple question” skip until the candidate has passed answer correctness first and reference correctness second on a valid paired evaluation. R448’s single preflight is not a basis for a model or deadline decision.

### 7. Establish operational performance data, then optimize a measured hotspot

**Performance impact:** Potentially high. **Current evidence:** insufficient for production distributions or savings.

Use bounded request-local telemetry to attribute wall time, physical provider calls/retries, serving leg, reported usage, cache result, and selected retrieval work. Once a quality-qualified baseline exists, use an unbiased sample for p50/p95 and price-schedule coverage; then target one demonstrated hotspot per experiment. Do not assign per-call marginal cost to a flat Claude Max subscription, and do not mistake process-global counters or warmed shared cache effects for per-request measurements.

The companion `docs/reviews/r448-request-telemetry-design-2026-09-28.md` is an observability design only. Its events are not a quality score and cannot satisfy Gates 1–3.

### 8. Extract large-module seams for change safety, not imagined speed

Prior architecture audits found large functions and duplicated transport, but historical line counts are not current request-time evidence. Prefer behavior-preserving Stage-2/evidence/finalizer seams, then derive cache identity from an explicit set of response-changing inputs while retaining the cache-key completeness tests. Avoid a big-bang route rewrite, speculative dead-code deletion, or bundling a behavior change with an extraction. Recount the current files and prove tracked imports before implementation.

## Target architecture

```text
question + relevant history
  → typed intent and explicit answer requirements
  → exact anchors + staged local/semantic recall
  → constrained, evidence-preserving KG expansion
  → source-resolved EvidenceBundle (canonical text + provenance)
  → deterministic answer or quality-qualified synthesis
  → answer correctness review against independent evidence
  → claim-linked reference finalization and reference correctness checks
  → complete response scorecard / relevant multi-turn checks
  → operational telemetry for latency, calls, usage, cache, and cost
```

This is a quality architecture, not a mandate to add a verifier call to every request. First preserve behavior and establish where errors originate. Any online validator, model escalation, retrieval cascade, or extra call must itself be evaluated for answer and reference quality before its latency/cost is considered.

## Explicit non-recommendations

- Do not optimize response speed, token count, cost, character count, reference count, or the geometric-mean `overall` ahead of answer correctness and reference correctness.
- Do not call R448 “non-inferior” or a correctness win; it has short samples, reconstructed criteria, and no paired reference-correctness result.
- Do not treat a p-value above a threshold, a confidence interval crossing zero, or a smoke-run floor as proof of safety.
- Do not let fewer citations, an overall gold-drop reduction, or a gain on one row mask a newly dropped gold head on another.
- Do not claim `ab_judge`, `easyhard_ab`, a deterministic keyword/ref check, or telemetry alone proves substantive legal answer correctness.
- Do not promote graph-primary retrieval, generic context dumps, a global top-K/reference cap, universal Stage-2 skip, or a cheaper model without an active-callsite and valid quality evaluation.
- Do not add NLI/PyTorch, an agent loop, broad rewrite, or speculative dead-code cleanup as a performance shortcut.

## Source map

- Evaluation rules/invariants: `AGENTS.md`, `CLAUDE.md`.
- Reconstructed rubric and paired scorer: `evals/official/rubric.py`, `evals/official/judge.py`, `evals/official/score_arm.py`, `evals/official/paired_ab.py`.
- Live proxy and reference gate: `evals/harness/ab_judge.py`, `evals/harness/pairwise_prompts.py`, `evals/harness/easyhard_ab.py`, `evals/harness/gate_validity.py`.
- Act-grounded post-hoc judge: `evals/judge/grounded.py`.
- R403 paired evidence: `docs/measurements/r403/paired-L0-vs-L1.json`, `docs/measurements/r403/paired-G0-vs-G1.json` (no consolidated R403 `CHECKPOINT.md` was present in this review).
- R448 paid screen: `docs/measurements/r448/paid-screen-rg037-rg085-20260927/`.
- R448 stratified list/scenario run: `docs/measurements/r448/paid-stratified-list-scenario-20260928/`.
- Runtime seams to verify at implementation time: `app/routes/regenold.py`, `app/engines/_graph_rag_impl.py`, `app/engines/kg_context.py`, `app/llm/openai_wrapper_provider.py`, `app/llm/bedrock_client.py`, `app/llm/stage2_policy.py`, `app/engines/cohere_rerank.py`.
- Prior architecture/evidence: `docs/reviews/r426-bigfile-architecture-audit.md`, `docs/reviews/r421-missed-issues-and-remediation-plan.md`, `docs/reviews/r411-architecture-audit.md`, `docs/measurements/r423/CHECKPOINT.md`.

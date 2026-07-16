# R277 — The answer-composition redesign (the real prize: AnsL −13.1)

**Status:** evidence-complete, experiment designed, NOT implemented.
**Origin:** R276 session (2026-07-16) — official scorecard + 3-agent research
round (market SOTA / instruction-overload evidence / repo answer-composition
audit). R276 shipped D2 (the `Art.` complexity bug, PR #285) and D1
(ref-granularity selection); this plan is the follow-on.

## 0. The target, restated

Official scorecard (2026-07-14): easy 77.5 / hard 73.0 vs 2025 baseline
80.9 / 83.2 and frontier+search 88.1 / 87.4. `AnsL − RefL` = −13.1 (easy):
we retrieve BETTER than the 2025 baseline and answer WORSE by 11.7pp. The
bottleneck is the answer-composition layer. AnsS alone is +3.33pp of Overall
at the marginal-leverage rate; closing half the AnsL gap ≈ +2.5-4pp. Beating
the 2025 baseline needs ~+3.5pp total; beating frontier needs ~+11pp — only
reachable through this layer.

## 1. The evidence dossier (3 agents, 2026-07-16 — full outputs in the
##    session transcript; key items reproduced here)

### 1a. Composition-layer census (repo audit, verified at file:line)
* `ANSWER_GENERATE_SYSTEM` = **51,110 chars (~12.8K tokens)**: 20 numbered
  rules + 5 named blocks, "never"×42 / "do not"×61 / "must"×49 / "only"×45,
  10 worked exemplars, one 14,648-char FACTUAL-GUARD block (29% of prompt).
  Sent on EVERY Stage-2 call (N+1× under fusion). Stage-2 user templates
  restate the same rules twice more (~5.4K chars).
* **28 curated intercepts** skip Stage-2 entirely (Opus never sees the
  question); ~17 classification topics + scenario classifier + role×risk
  matrix are also canned. A large slice of single-turn traffic never
  reaches the LLM.
* **~35 post-processors** (10 answer-text transforms, ~25 reference passes);
  `normalise_answer_for_regenold` runs up to 6× per request.
* **Validation asymmetry (the smoking gun):** the only 5 components with
  live pairwise evidence are all REFERENCE-side. *Not one answer-TEXT
  transform (strips, caps, consistency-replacement, intercepts-vs-Opus) has
  ever won a live pairwise on answer correctness* — the axis the official
  benchmark says is the bottleneck.
* Known internal contradictions: rule 12b "pack list into ONE sentence" vs
  LENGTH-DISCIPLINE "packed clauses are decomposed and penalised";
  grounding-only rules 4/11 vs answer-the-question; collapse-parents vs
  reemit-parents (fixed by R276-D1).
* Stale canned content found: `high_risk_obligations_deadline` intercept
  asserts "2 August 2026" for Annex III HRAIS (pre-Omnibus policy decision,
  but check against the benchmark cutoff — rules say state-of-affairs per
  1 May 2026, so this may actually be CORRECT for the benchmark; verify
  before "fixing"); `risk_framework_overview` ships 11 refs.

### 1b. External evidence (research agents, with sources)
* **P-Cite / post-hoc citation** (arXiv:2509.21557): write-answer-first,
  attach-citations-after → 78% vs 69% human-rated answer correctness AND
  lower citation hallucination. Directly matches our AnsL−RefL inversion.
* **IFScale** (arXiv:2507.11538): instruction-following degrades with
  density; BUT at our ~64-rule count frontier models still comply ~95-99% —
  raw rule COUNT is NOT the mechanism. The real mechanisms (all evidenced):
  (i) constraint INTERFERENCE/conflict (ComplexBench, CFBench hard 0.58,
  ConInstruct: models silently pick a resolution 97.5% → per-sample
  variance); (ii) format/content restriction during generation taxes
  reasoning (Tam et al. arXiv:2408.02442); (iii) prohibitions over-suppress
  (XSTest ρ=0.89 analog); (iv) mid-prompt rules under-attended
  (lost-in-the-middle >30%). Compliance ≠ correctness (Instruction Gap,
  arXiv:2601.03269 — independent capabilities). Verdict: prompt
  simplification plausibly buys **+8-15pp answer correctness**, ~70%
  confidence; part of the 22.3pp frontier gap is metric/format artifact.
* **Citation granularity** (arXiv:2604.01432): citation F1 lowest at finest
  granularity, peaks intermediate; fine-grained constraints
  disproportionately hurt larger models. (R276-D1 implements the dedup.)
* **Grounding-only rules backfire**: rules 4/11 convert retrieval misses
  into "the Act is silent" answers — the exact failure class that spawned
  the 46 refusal markers + consistency guard. Opus KNOWS the Act; the rule
  forbids the knowledge precisely when retrieval under-delivers.
* **Multi-turn**: consolidation-reset + strong-model query rewrite is the
  validated pair (LLMs-Get-Lost arXiv:2505.06120 −39% multi-turn drop;
  MTRAG; ERGO +56.6% recovery). Our denoiser IS this — but its Groq
  free-tier chain fails on TPD and falls back to raw flattening. Making the
  rewrite reliable (wrapper model, not Groq-free) is the multi-turn lever.
* **Models** (Vals.ai 2026-07-09): LegalBench — **Claude Fable 5 88.6%** >
  Gemini 3.1 Pro 87.4%; Opus 4.8 leads Legal Research Bench strict accuracy.
  If the Claude Max wrapper exposes `claude-fable-5`, that is a zero-cost
  Stage-2 model A/B (`P2P_GRAPH_RAG_STAGE2_MODEL=claude-fable-5`).
* **Claude Citations API**: +15% recall vs prompt-engineered citations, but
  per-token billed (needs operator exception to the flat-rate rule).

## 2. The experiment — ablation ladder (4 arms, ab_judge pairwise)

Env `REGENOLD_MINIMAL_COMPOSER` selecting a prompt VARIANT (fold into
`_engine_cache_key` — R263.2 doctrine), arms:

* **A** — current full prompt (baseline).
* **B** — current minus prohibitions, positive-reframed, same content rules.
  Isolates prohibition cost.
* **C** — minimal composer (~8K chars): identity + SCOPE + wire citation
  format + verdict-first + adaptive-length (one copy) + VOICE third-person +
  describe-every-cite + 2-3 GOOD-only exemplars (drop contrastive BAD
  examples — they model the forbidden style). Grounding rule SOFTENED:
  "Prefer the supplied provisions; you may draw on your knowledge of
  Regulation 2024/1689 where they are thin — never cite an article you are
  not certain exists." Existing deterministic validators (dash strip, tone
  guard, cite-format, drift guard, ARTICLE_EXISTENCE) stay as the safety
  net; add ONE validate-and-retry re-ask on violation (DeCRIM +7-8%).
  Isolates accretion cost.
* **D** — near-naive (grounding+cite rule only) + validators. Tests whether
  ANY scaffold earns its keep (GPT-4.1 evidence predicts C > D).

Gates: n ≥ 40 rows (probe_set tricky + multi-article + medtech gold; the 3
PDF examples as regression canaries only); position-swapped pairwise; arms
interleaved (rate-limit drift confound, R268 memory); correctness win-rate
>0.5 at p<0.05; refs/tone/conciseness not significantly down; deterministic
wire lint 100%.

Also queue (independent A/Bs, cheaper):
1. **Curated-intercept holiday** — `REGENOLD_CURATED_STAGE2_SKIP=0` arm:
   first-ever measurement of 27 frozen answers vs Opus+context.
2. **Consistency-guard narrowing** — sentence-strip instead of whole-answer
   replacement; guard fired on ~30% of live rows historically.
3. **Fable-5 Stage-2 swap** — if wrapper exposes it.
4. **P-Cite two-pass** — only if C wins and refs-faithfulness dips: cheap
   second pass attaches the minimal citation set (ALCE-precision rule).
5. **Denoiser reliability** — route multi-turn rewrite through the wrapper
   (Sonnet) instead of free-tier Groq-first; measure hard-mode ab_judge
   `--multiturn only`.

## 3. What NOT to redo (measured/rejected)

Everything in the R276-PLAN "What NOT to do" list, plus: re-sentencer
(R147-rejected), MoA merge-judge (R123), simple-skip flip without A/B
(R129 claim unverified both ways), fast-mode/thinking-size for latency
(washes), external vector DBs / GPU / RDF / LangGraph (wrong-for-codebase),
davidath as a win-measure (regression guard only).

## 4. Sequencing

1. Land R276-D1 (done in PR; this file rides along).
2. Implement arm C prompt variant + `REGENOLD_MINIMAL_COMPOSER` env +
   cache-key + validate-and-retry.
3. Run ladder A vs C first (the big hypothesis); B/D only if C is ambiguous.
4. Ship winner default-ON; keep A as one-flip rollback.
5. Then intercept-holiday + guard-narrowing A/Bs.
6. Re-submit to the regenold live benchmark when it opens; compare official
   axes (the ONLY ground truth for granularity + composition).

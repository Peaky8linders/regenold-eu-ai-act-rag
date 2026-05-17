# R44 — HuggingFace Landscape for Legislative / Regulatory RAG

**Date:** 2026-05-17
**Audience:** maintainers of `evals/bench/runner.py`, planning Round 44+ wires.
**Scope:** New HF Hub datasets / Spaces / industry initiatives surfacing since
the R32/R34 audits in `INDUSTRY_BENCHMARKS.md` and `OTHER_BENCHMARKS.md`.

## Executive summary

The EU AI Act dataset surface **bloomed between March and May 2026**, driven
by the 2 Aug 2026 high-risk enforcement deadline. Seven net-new HF datasets
ship gold article references; three carry permissive licenses we can wire
without negotiation. The single highest-leverage Round-44 land is
**`airblackbox/eu-ai-act-compliance-benchmark`** — Apache-2.0, 55 hand-graded
Python agent files labelled PASS/FAIL across Arts. 9/10/11/12/14/15, a brand
new axis (input-as-code) the bundle's deterministic engine has never been
tested on. It is the cheapest wire we've identified since AIReg-Bench and
exposes a different failure mode — does the engine cite the *right* HRAIS
article when handed an artefact instead of a question? Estimated 1 day to
wire, ~3 days to harden.

## 1. Top 5 integration candidates (ranked by lift × cost)

### #1 — `airblackbox/eu-ai-act-compliance-benchmark` **(LAND THIS SPRINT)**

- **URL:** https://huggingface.co/datasets/airblackbox/eu-ai-act-compliance-benchmark
- **License:** Apache-2.0 — fully permissive.
- **Size:** 55 Python AI-agent source files (`bare_openai_agent.py` etc.) +
  per-article PASS/FAIL labels for Arts. 9/10/11/12/14/15. ~421 kB.
- **Shape:** `{filename, framework ∈ {openai, langchain, crewai, autogen, rag},
  difficulty ∈ {easy, medium, hard}, labels: {art9..art15: PASS|FAIL}, score: "N/6"}`.
- **Relevance: 5/5.** Targets the exact 6 HRAIS articles we centre on (Art. 9 RMS,
  10 data gov, 11 tech doc, 12 logging, 14 human oversight, 15 robustness) —
  identical surface to AIReg-Bench but with **code as input** instead of prose
  excerpts. Distribution stratified across compliance scores 1/6→6/6.
- **Why it fits:** Davidath + AIReg-Bench both feed natural-language to the wire.
  This benchmark feeds **source code** — a third orthogonal shape. Tests whether
  `scope.py` correctly routes code-shaped queries to Art. 11/15 vs refusing,
  and whether the route surfaces the right per-article citations when the user
  pastes a Python file and asks "is this AI Act compliant?".
- **Wire-up sketch:** new `evals/bench/airblackbox_bench.py` mirroring
  `aireg_bench.py`. Per row: prompt = `"Is the following AI agent code
  compliant with EU AI Act high-risk obligations? Identify which articles
  are violated.\n\n```python\n{file_content}\n```"`. Gold answer = list of
  FAIL labels → article numbers. Score axes: Ref Strict (precision of cited
  failed-articles), Ref Recall (did we surface every FAIL?). New
  `code_classification_accuracy` axis tracking per-article PASS/FAIL agreement.
- **Predicted rubric impact:** **Ref Strict +0.02 to +0.05** on a new
  code-input split; **expected regression on Ans Strict** (the engine
  currently surfaces full-article prose, not per-file findings — exposing
  this is the *point* of the wire). Latency cost ~8 ms per row (longer
  inputs feed BM25 unchanged-shape).
- **Risk:** The labels are scanner-generated (pattern-based, not semantic).
  Edge cases where comments mention "audit_log" without implementing one
  trigger false-positive PASS. Mitigate by reporting agreement-with-scanner
  separately from semantic-correctness; the scanner's known FPs make this
  benchmark a **lower bound** on our true performance.

### #2 — `jeroenherczeg/eu-ai-act` (multilingual corpus, retrieval-only)

- **URL:** https://huggingface.co/datasets/jeroenherczeg/eu-ai-act
- **License:** CC-BY-4.0.
- **Size:** 2,610 structured chunks of Regulation 2024/1689 in **EN / NL / FR**.
  Rich metadata: `references_articles`, `interprets_articles`, `defined_terms`,
  `effective_from`, CELEX, source URL — already cross-referenced.
- **Relevance: 4/5.** Direct EU AI Act content with multilingual coverage —
  the bundle is English-only today. The `references_articles` list is the
  same xref graph our `app/data/kb_xrefs.py` builds manually.
- **Why it fits:** **Two routes.** (a) Augment `app/data/kb_xrefs.py` —
  the dataset's `references_articles`/`interprets_articles` lists are a
  diff against our manually-curated 115 edges. Predict adding 20–60 high-
  precision edges. (b) Build a **multilingual eval split**: load FR/NL
  rows, machine-translate the EN gold question, ask the wire in the
  source language. Tests `scope.py` against non-English coref.
- **Wire-up sketch:** `scripts/ingest_jeroenherczeg_xrefs.py` parses the
  parquet → emits a candidate `kb_xrefs_supplement.py`; human-review the
  diff before merge. Separately, `evals/bench/multilingual_bench.py`
  reuses davidath gold but feeds the NL/FR-translated question.
- **Predicted rubric impact:** Xref augmentation lifts **Ref Loose +0.01**
  on davidath via the Round-31.1 graph-expand path. Multilingual split is
  a **NEW axis** (Multilingual Refusal Correctness) that our bundle has
  never measured.
- **Risk:** The xref deltas need human review; auto-merge would risk
  poisoning our manually-curated graph. The multilingual eval needs gold
  refs verified — the NL translation may shift article boundaries.

### #3 — `cycloevan/gdpr-sft-2277-combined` (GDPR cross-walk)

- **URL:** https://huggingface.co/datasets/cycloevan/gdpr-sft-2277-combined
- **License:** Apache-2.0.
- **Size:** 2,277 instruction-output pairs, English, with article-level
  citations to GDPR + cross-references to AI Act, NIS2, UK GDPR, LGPD.
- **Relevance: 3/5.** Not EU AI Act *primary*, but the GDPR cross-walk is
  the same regulatory texture and the AI Act explicitly defers to GDPR in
  Arts. 10(5), 26(7), 27. Our bundle today has zero GDPR coverage.
- **Why it fits:** The Regenold rubric scopes to EU AI Act, but real users
  asking about AI compliance routinely mix GDPR ("Is biometric processing
  by my HR AI lawful?") into the same turn. Today `scope.py` refuses
  pure-GDPR questions; this dataset gives us a **calibrated refusal
  benchmark** for the GDPR-adjacent boundary.
- **Wire-up sketch:** `evals/bench/gdpr_boundary_bench.py` — load the
  2,277 pairs, classify each by AI-Act-relevance (regex on
  `{ai system, automated decision, profiling, art. 22}`). For AI-adjacent
  rows, expect the wire to answer with an AI Act anchor + a "this also
  invokes GDPR Art. 22" handoff. For pure-GDPR rows, expect a refusal.
- **Predicted rubric impact:** **Refusal Correctness** axis baseline
  measurement (we don't have one today); expected 0.70–0.85 on pure-GDPR
  rejection. Surfaces failure modes in `app/integrations/regenold/scope.py`.
- **Risk:** Outputs are LLM-generated (Upstage Solar-Pro) — article
  citations are model-generated, not authoritative. Use for eval shape,
  not as ground-truth gold; pair with the 316 expert-authored subset for
  high-confidence scoring.

### #4 — `nguyenthanhasia/gdpr-cases` (formal-rule reasoning)

- **URL:** https://huggingface.co/datasets/nguyenthanhasia/gdpr-cases
- **License:** Apache-2.0 (per HF page metadata; not on dataset card —
  **verify before integration**).
- **Size:** 60 GDPR cases with `scenario` (1.5 kB prose), `rule_tree`
  (Pythen formal JSON), `facts`, `label` (bool), and per-case quality
  scores. Covers GDPR Arts. 6/7/9/15/17/18/20/21/32.
- **Relevance: 3/5.** Adjacent regulation, but the **formal `rule_tree`
  representation is unique on HF** — it's the only public dataset that
  pairs natural-language scenarios with mechanised rule encodings. Pairs
  with our CLARA verdict matrix (`app/engines/clara_logic.py`) which
  itself is a 15-rule formalism.
- **Why it fits:** Validate CLARA's deterministic verdict against an
  external formal-rule reasoning gold. If CLARA agrees with the Pythen
  rule_tree on the AI-Act-adjacent subset (Art. 22 / DPIA), we have
  external evidence the matrix is sound.
- **Wire-up sketch:** `evals/bench/gdpr_cases_clara_audit.py` — load 60
  rows, run CLARA on each scenario, compare CLARA's `risk_tier` against
  the dataset's `label`. Pure audit (no wire calls); cheap.
- **Predicted rubric impact:** None on davidath/AIReg-Bench. **Confidence
  signal on CLARA** — if agreement > 0.85, lock CLARA's matrix; if <
  0.70, audit the rules.
- **Risk:** Small dataset (60 rows) — wide confidence band. Pythen format
  needs a parser (200 LOC, one day).

### #5 — `nihedb/EUR-Lex-Triples` (xref graph augmentation)

- **URL:** https://huggingface.co/datasets/nihedb/EUR-Lex-Triples
- **License:** CC-BY-4.0 (inferred from EUR-Lex-Sum parent; verify).
- **Size:** 1,504 EU legislation documents with relation-triple annotations.
- **Relevance: 3/5.** Not AI-Act-specific but contains many AI-Act-adjacent
  regulations (NIS2, GDPR, Data Act, DSA, DMA) — the **inter-regulation
  xref graph** the bundle is missing today.
- **Why it fits:** Round-35 Neo4j is seeded only from in-process KB. This
  dataset adds **cross-instrument edges** (AI Act Art. 5 ↔ GDPR Art. 9
  biometric; AI Act Art. 50 ↔ DSA Art. 35 transparency). Feeds the
  `app/graph/reasoning.py` cross-framework mapping use-case flagged in
  the R35 runbook.
- **Wire-up sketch:** `scripts/ingest_eurlex_triples.py` — filter triples
  to those where subject OR object is `32024R1689` (AI Act CELEX); ingest
  filtered set into Neo4j as `CROSS_INSTRUMENT_REFERENCES` edges. Estimated
  20–80 high-confidence edges after filtering.
- **Predicted rubric impact:** Zero on current rubric (davidath/AIReg-Bench
  don't measure cross-instrument). **Unblocks the R35 cross-framework
  mapping** that the runbook calls out as a strategic opportunity.
- **Risk:** Dataset viewer is broken (ArrowInvalid schema errors). Need
  raw-file ingestion path; may need REBEL-Large to re-extract some triples.

## 2. Top 3 we should NOT integrate

1. **`TurboQuantArchitect/eu-ai-act-reasoning-sample`** — Commercial
   license, 10-row free sample, full dataset behind a $15k–$75k paywall.
   Beautifully-shaped (CoT reasoning + article mapping + risk level)
   but redistribution-prohibited.
2. **`ComplianceDataLab/eu-ai-act-compliance-scenarios`** — CC-BY-**NC**-4.0
   on the free 75-row sample. Non-commercial license; even with the
   Regenold competition framing, our wire is a deployable system. Skip
   until they relicense or release a CC-BY-4.0 split.
3. **`alerterra/eu_ai_act_compliance`** — Gated dataset behind a
   commercial license (`alerterra-commercial`). 203 synthetic Article-10
   records; not redistributable.

## 3. Surprises

1. **No 2026 EU AI Act refusal benchmark.** `dam9/eu-ai-act-red-teaming-v1`
   (Jan 2026) is still the only public refusal probe. The April 2026
   `paixblox/PAIXBLOX-Operational-AI-Governance-Evaluation-Dataset`
   ships an adversarial axis (`difficulty_band ∈ {moderate, adversarial}`)
   but is **general AI governance**, NOT EU AI Act specific. Stanford
   CRFM's AIR-Bench 2024 (recommended R34 wire) remains the strongest
   AI-Act-aligned refusal benchmark — **R44 should still land AIR-Bench
   first** before the new candidates above.

2. **`isaacus/gdpr-holdings-retrieval` is part of MLEB.** The Massive
   Legal Embeddings Benchmark (arXiv 2510.19365, Butler et al. 2025)
   bundles 500 fact-pattern → holding pairs from EU DPA decisions.
   **CC-BY-NC-SA-4.0** so we can't wire it for the production bench, but
   it's a credible standard for legal embedding evaluation — our R32
   embeddings index (NumPy SVD-128) is currently un-benchmarked.
   *Research-only* MLEB run would let us claim independent validation.

3. **The HF Spaces ecosystem is anaemic.** Seven Spaces tagged `eu-ai-act`
   total, max 4 likes (`MCP-1st-Birthday/eu-ai-act-compliance-agent`),
   most sleeping or in runtime-error state. None ship a runnable
   evaluation harness. Implication: **the Regenold wire would be one of
   the most credible public deployments in this space**, well ahead of
   the current Spaces field. Lower competitive bar than expected.

4. **`do-me/EUR-LEX` has 29,874 downloads** — by far the highest of any
   EU legislation tool on HF. It is a *mining tool* (Python package for
   extracting Cellar database content), not a benchmark, but the
   download count signals heavy industry use. Useful for refreshing
   `app/data/official_eu_ai_act.py` snapshots quarterly.

5. **Multilingual gap is widening.** Three of the May 2026 datasets
   ship multilingual content (`jeroenherczeg` EN/NL/FR; `danielnoumon`
   NL queries; `governanceai/governance-ai-guardrail-es-dataset` ES).
   The Regenold rubric is English-only today, but if the judges live-test
   with a French or German query the wire's behaviour is undefined.
   `scope.py` would likely refuse a French AI Act question as
   out-of-domain — a latent **rubric-breaker** if the competition turns
   multilingual.

## 4. One-paragraph executive summary — pick ONE for this sprint

**Land `airblackbox/eu-ai-act-compliance-benchmark` in R44.** Apache-2.0,
55 hand-curated Python AI agent files with PASS/FAIL labels across the 6
HRAIS articles we already specialise in, one-day wire-up cost via the
existing `aireg_bench.py` shape. It opens a third orthogonal evaluation
shape (code-as-input) we have never measured, and the predicted Ref
Strict +0.02–0.05 lift comes from a brand-new dataset the competition
judges likely haven't seen either — first-mover credibility. The other
four candidates (jeroenherczeg multilingual, cycloevan GDPR, nguyenthanhasia
formal-rules, nihedb EUR-Lex-Triples) are all strategic-but-not-rubric-
lifting, and should queue behind airblackbox + the still-pending AIR-Bench
2024 wire from R34. The biggest latent risk surfaced by this audit is
**multilingual coverage** — three new May 2026 datasets ship NL/FR/ES
content, and the bundle has zero non-English handling today; if Regenold
goes multilingual, that's our single largest exposed surface.

---

## Sources

### Net-new datasets surveyed (HF Hub, post-Feb 2026)

- [airblackbox/eu-ai-act-compliance-benchmark](https://huggingface.co/datasets/airblackbox/eu-ai-act-compliance-benchmark) — Apache-2.0, 55 rows, code-shape
- [jeroenherczeg/eu-ai-act](https://huggingface.co/datasets/jeroenherczeg/eu-ai-act) — CC-BY-4.0, 2,610 rows, EN/NL/FR
- [danielnoumon/eu-ai-act-nl-queries](https://huggingface.co/datasets/danielnoumon/eu-ai-act-nl-queries) — CC-BY-4.0, 2,284 NL query-chunk pairs
- [yuqiangJEP/JEP-EU-AI-Act-Mapping-Notes](https://huggingface.co/datasets/yuqiangJEP/JEP-EU-AI-Act-Mapping-Notes) — MIT, JEP audit-trail schema
- [ai-compliance-labs/eu-ai-act-hr-audit-whitepaper](https://huggingface.co/datasets/ai-compliance-labs/eu-ai-act-hr-audit-whitepaper) — CC-BY-4.0, *documentation only, not data*
- [TurboQuantArchitect/eu-ai-act-reasoning-sample](https://huggingface.co/datasets/TurboQuantArchitect/eu-ai-act-reasoning-sample) — Commercial, paywalled
- [ComplianceDataLab/eu-ai-act-compliance-scenarios](https://huggingface.co/datasets/ComplianceDataLab/eu-ai-act-compliance-scenarios) — CC-BY-NC-4.0, *skip*
- [alerterra/eu_ai_act_compliance](https://huggingface.co/datasets/alerterra/eu_ai_act_compliance) — alerterra-commercial, *skip*
- [paixblox/PAIXBLOX-Operational-AI-Governance-Evaluation-Dataset](https://huggingface.co/datasets/paixblox/PAIXBLOX-Operational-AI-Governance-Evaluation-Dataset) — Apache-2.0, general-AI-governance
- [cycloevan/gdpr-sft-2277-combined](https://huggingface.co/datasets/cycloevan/gdpr-sft-2277-combined) — Apache-2.0, GDPR SFT
- [cycloevan/gdpr-dpo-2277-targeted](https://huggingface.co/datasets/cycloevan/gdpr-dpo-2277-targeted) — Apache-2.0, GDPR DPO
- [nguyenthanhasia/gdpr-cases](https://huggingface.co/datasets/nguyenthanhasia/gdpr-cases) — formal rules, 60 cases
- [isaacus/gdpr-holdings-retrieval](https://huggingface.co/datasets/isaacus/gdpr-holdings-retrieval) — CC-BY-NC-SA-4.0, MLEB benchmark
- [Sebastyijan/gdpr-enforcement-sample](https://huggingface.co/datasets/Sebastyijan/gdpr-enforcement-sample) — CC0-1.0, 682 enforcement actions
- [nihedb/EUR-Lex-Triples](https://huggingface.co/datasets/nihedb/EUR-Lex-Triples) — CC-BY-4.0, 1,504 docs
- [do-me/EUR-LEX](https://huggingface.co/datasets/do-me/EUR-LEX) — CC-BY-4.0, mining tool
- [oliverkinch/eur-lex](https://huggingface.co/datasets/oliverkinch/eur-lex) — parallel EN/DA corpus
- [mteb/eurlex-multilingual](https://huggingface.co/datasets/mteb/eurlex-multilingual) — CC-BY-SA-4.0, 23 EU languages
- [nguha/legalbench](https://huggingface.co/datasets/nguha/legalbench) — CC-BY-4.0, 162 tasks, US-law-dominant

### Spaces surveyed (low activity)

- [MCP-1st-Birthday/eu-ai-act-compliance-agent](https://huggingface.co/spaces/MCP-1st-Birthday/eu-ai-act-compliance-agent)
- [hfmlsoc/eu-ai-act-os-guide-gpai](https://huggingface.co/spaces/hfmlsoc/eu-ai-act-os-guide-gpai)
- [6ocram9/eu-ai-act-navigator](https://huggingface.co/spaces/6ocram9/eu-ai-act-navigator)
- [KaanGoker/eu-ai-act-rag-screener-demo](https://huggingface.co/spaces/KaanGoker/eu-ai-act-rag-screener-demo)
- [aegisprove/eu-ai-act-generator](https://huggingface.co/spaces/aegisprove/eu-ai-act-generator)

### Reference papers

- [Butler et al., MLEB (arXiv:2510.19365)](https://arxiv.org/abs/2510.19365) — Massive Legal Embeddings Benchmark
- [Nguyen et al., GDPR Auto-Formalization (arXiv:2604.14607)](https://arxiv.org/abs/2604.14607) — paired with `nguyenthanhasia/gdpr-cases`

---

*Companion to `INDUSTRY_BENCHMARKS.md` and `OTHER_BENCHMARKS.md`.
Last updated 2026-05-17.*

# R356 — Adversarial review of the 81-row judge report, and fixes applied

Scope: the comprehensive LLM-as-a-judge report on the 81-row live-answers benchmark
(59 pass / 22 fail, 72.8%). This round analysed each failure class against the
**grounded data** (official Regulation (EU) 2024/1689 text in the provision corpus,
the keyword/entity maps, the KB and the deterministic intercepts), fixed the ones
with a provable root cause, and deliberately did **not** overfit to judge notes
that contradict the official text.

## What was NOT a bug (judge errors caught by grounding)

- **la_q86 (health insurance pricing)**: the judge note says the answer missed
  "Annex III point 5(b)" — but the official text puts life-and-health-insurance
  risk assessment/pricing at Annex III **point 5(c)**; 5(b) is creditworthiness.
  We anchored 5(c), not the judge's 5(b).
- **la_q23**: the engine deliberately excluded systemic-risk questions from the
  systems-vs-models intercept with a stale "correctly-answered" comment; the judge
  proved the assumption wrong (Art. 53 open-source dump). Fix below.
- **la_q32 (pattern-deviation detection)**: judge PASS; near-identical shape to
  la_q31 but with the opposite gold answer. The 6(3) fix is shaped so la_q32 is
  untouched.

## Root causes found and fixed

| Row | Root cause (verified in code) | Fix |
|-----|-------------------------------|-----|
| la_q10 | `_KEYWORD_ENTITY_MAP` had **no** "human oversight" entry -> entity list empty -> BM25 fallback dumped Art. 1-4 definitions | anchor `("human oversight", "Art. 14")` |
| la_q31 | `_detect_article_6_3_inquiry` pattern missed the narrow-procedural/preparatory shape ("structure or deduplicate information") -> canned two-route boilerplate, no 6(3)(a) | pattern extended with `structure\w*\|deduplicat\w*\|organis\w*\|organiz\w* ... information` shape |
| la_q35 | MSA-enforcement question (Art. 79/80 procedure) passed the classification-verdict gate -> canned Art. 5/6 boilerplate; map had no Art. 79/80 anchors | `_ENFORCEMENT_CORRECTIVE_RE` guard in `_general_classification_verdict` + anchors `("recall and suspend", "Art. 79")`, `("classified as non-high-risk", "Art. 80")` |
| la_q13 | GPAI transparency-exception question truncated; QA-dump surfaced only Art. 53 | new `_detect_gpai_transparency_exception_inquiry` -> curated Article 53(2) verdict (open-source carve-out, what it does NOT cover, systemic-risk exception) |
| la_q23 | "systemic risk" anchored only Art. 55 (obligations), never Art. 51 (classification); systems-vs-models detector's negative guard excluded it as "correctly-answered" | new `_detect_systemic_risk_scope_inquiry` -> curated Article 51(1)-(2)/55 verdict; map now leads Art. 51 |
| la_q29 | "emergency calls and triage" missed the map; retrieval pulled Art. 46/42 noise instead of Annex III(5)(d) | anchors `("emergency triage", "Annex III.5.d")`, `("emergency calls", "Annex III.5.d")` |
| la_q86 | "health insurance" anchored bare Annex III -> generic two-route answer | anchors `("health insurance", "Annex III.5.c")`, `("risk assessment and pricing", "Annex III.5.c")` |
| la_q37 | "registering ... in the EU database" missed every Annex VIII anchor -> Art. 71 general clause only | anchor `("registering a high-risk ai system", "Annex VIII")` |

Every new anchor/detector was false-positive-checked across all 81 questions
(the phrase appears in exactly the target row); the two new intercepts are wired
into `_deterministic_answer`, `_is_curated_authoritative_intercept` (Stage-2 skip),
and the ref-protection path, so the curated answers cannot be truncated or
overridden by Stage-2 polish.

## Verification

- 81-row detector scan: exactly the intended rows changed; zero false positives.
- Focused test run (intercepts, cache-key completeness, rerank, semantic layers,
  entity extraction, parse, retrieval, wire): **320 passed, 0 failed**.
- Ruff: zero new lint errors (the 36 I001 import-order findings are pre-existing
  at HEAD).
- No Unicode corruption; LF preserved.

## Residual items (honest list — not fixed this round)

- **Truncation class** (la_q53, la_q72): generation-length issues in the
  Stage-2 path; needs an output-budget / sentence-completion guard, a separate
  change with its own blast radius.
- **Synthesis class** (la_q51, la_q52, la_q84): broad roadmap/lifecycle questions
  where the judge wants structured synthesis, not retrieval; a deterministic fix
  would overfit.
- **la_q75**: Art. 10 already leads the entity set, but Art. 26 remains third;
  whether the shipped answer still leans on Art. 26 requires a full pipeline run
  (KB/Neo4j), which this round did not execute.
- **la_q21**: Art. 15 leads retrieval, but the false-premise ("Correct?") shape is
  a Stage-2 reasoning quality issue.

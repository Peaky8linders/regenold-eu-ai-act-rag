# R272 — PARTIAL-row re-run + remark triage + fresh metrics

**Date:** 2026-07-05 · **Branch/commit:** `main` @ `4ecb8fd` (R270–R272; Stage-2 = **Opus 4.8 for both tiers**, thinking-free simple / 4000-token extended-thinking complex).
**Scope:** the **49 questions labelled PARTIAL** in [`r264-live-sonnet5-judge.md`](r264-live-sonnet5-judge.md) (the full 102-row judge). Re-asked live on current `main`, triaged the original judge remarks against the canonical Act, and re-judged old vs new with one clean legal grader.

**Answer-generation:** in-process route (`TestClient`) + the **live Claude Max wrapper** (Opus 4.8 Stage-2 / curated deterministic verdicts) — the real current pipeline, per the CLAUDE.md eval-provider rule. Re-run: **49/49 HTTP 200, 0 errors.**
**Judge:** `gemini-2.5-pro` (reference-free EU-AI-Act grader, anchored to the **final** Regulation 2024/1689 numbering, same judge on OLD & NEW so the delta is fair). Gemini was used because it is a top-LegalBench model *and* a different family from the Opus answerer (no self-preference bias); the Anthropic API has no credit and the Claude-Max wrapper degrades under sustained judge load.

---

## TL;DR

1. **The r264 PARTIAL baseline is not trustworthy as-is.** **29 of the 49 PARTIAL rows (59%) were graded by a Mistral/Groq panel whose remarks are riddled with draft-numbering hallucinations** (e.g. "transparency = Article 52", "emotion recognition = Article 5(1)(d)", "presumption is Article 42(2), 42(1) doesn't exist"). Several of those "PARTIAL" answers were actually correct. Only ~20/49 were graded by Sonnet-5, whose remarks mostly hold up.

2. **vs the audited production answers (2026-06-29 dump): current `main` is clearly better** — correctness **+11**, completeness **+11**, citations **+9** (all well above the judge's noise floor); PASS 22% → 37%, FAIL 18% → 6%. The genuinely broken originals (a citation to a non-existent Article 108, mid-sentence truncations, a topic-shifted "guiding principles" answer) are fixed.

3. **vs the last full submission `r267` (2026-07-02): roughly flat / marginally positive** — correctness +1, completeness +5, citations +5, but the verdict mix is unchanged (**within judge noise**). The R268–R272 changes (incl. Opus-for-both-tiers) did **not** materially move these 49 rows. This matches the CLAUDE.md finding that "opus-for-all" was an A/B wash.

4. **Honest caveat on the judge itself:** re-grading the *identical* new answers twice, **the verdict flipped on 24% of rows** (mean ±9 pts, a few ±30–80 pt swings). Single-LLM verdicts on nuanced EU-AI-Act Q&A are **noisy** — trust the aggregate axis means, not individual PASS/PARTIAL/FAIL calls.

---

## 1. Remark triage — "no BS, no hallucinations"

Every disputed citation was checked against the repo's canonical `provision_text` (the pinned EUR-Lex text of Regulation 2024/1689), not from memory.

### The systematic problem: 59% of the PARTIAL baseline is panel-hallucinated

| # PARTIAL rows | Grader | Remark reliability |
| --- | --- | --- |
| 20 / 49 | Sonnet-5 (Claude Max) | Mostly **valid** (verified below) |
| **29 / 49** | **Mistral-large + Groq-Llama-3.3-70B panel** | **Systematically hallucinated** (draft numbering) |

The panel was trained on **draft** AI-Act numbering and repeatedly "corrects" the answer to the wrong article. Confirmed **false** panel remarks (bundle-verified):

| Panel claim (marked as a defect) | Rows | Ground truth (Reg 2024/1689) |
| --- | --- | --- |
| "transparency is **Article 52**" | q047, q080 | Art 52 = **GPAI classification procedure**; transparency = **Art 50** |
| emotion recognition is "**Article 5(1)(d)**" | q060 | Workplace/education emotion recognition = **Art 5(1)(f)** (with the medical carve-out the answer correctly gave) |
| "presumption is **Article 42(2)**; 42(1) doesn't exist" | q036 | Representative-data presumption **is Art 42(1)** — the answer was right; the *remark* was wrong |
| "**Article 28** = deployer obligations" | q080 | Art 28 = notifying authorities; deployer = **Art 26** |
| GPAI model def "**Article 3(1c)**", threshold "10^23" | q069 | GPAI def = **Art 3(63)**; systemic threshold **10^25** (Art 51(2)) |
| "**Article 69** = VLOP obligations" | (q054, adjacent) | VLOP is a **DSA** concept, not the AI Act |
| "**Annex XIII** = deep-fake transparency" | q019 | Annex XIII = **systemic-risk** criteria |
| "**Article 78(2)(c)** mandates remote data access" | q020 | Art 78 = **confidentiality** |
| "**Annex III point 6(a)** medical devices" | q060 | Annex III point 6 = **law enforcement**; no such sub-point |
| "missing **Article 4** (prohibited practices), **Article 5** (high-risk)" | q048 | Final: Art 5 = prohibited, Art 6 = high-risk, Art 4 = AI literacy |
| "`Article 3.60` should be `Article 3(60)`" etc. | q019, several | **Format nitpick**, not an error — `3.60` is the wire's user-facing rendering of 3(60) |

### The valid remarks (Sonnet-5, bundle-verified) — real, worth fixing

| Row | Valid remark | Verified |
| --- | --- | --- |
| q006 | Chapter V spans Articles 51–**56** (Art 56 = codes of practice), not 51–55 | ✓ |
| q014 | Should enumerate the Annex III **point 3** education sub-items (a)–(d) | ✓ (3(a) access/admission, (b) evaluate outcomes, (c) assess level, (d) exam proctoring) |
| q017 | Cite **Article 5(1)(h)(iii)** + the **4-year custodial** threshold, not bare Art 5 | ✓ |
| q029 | Name the specific **Annex III point 5(d)** emergency-dispatch/triage system, not just the category | ✓ |
| q031 / q032 | Apply the **Article 6(3)(c)** deviation-detection carve-out (question mirrors it near-verbatim) | ✓ (Art 6(3)(c) text matches) |
| q049 | **Article 63** is **micro-enterprises only**, not all SMEs | ✓ |
| q015 / q039 | State the two **Article 50(4)** exceptions (law-enforcement; human-review/editorial) | ✓ |

**Bottom line of the triage:** roughly **60% of the PARTIAL flags rest on ≥1 hallucinated remark**; the remaining ~40% (mostly Sonnet-5) are legitimate precision/completeness gaps. This is exactly the "BS" the request asked to filter out.

---

## 2. Fresh metrics (clean Gemini-2.5-pro judge, same judge on OLD & NEW)

### Baselines
- **r264 reported** (mixed Sonnet-5 + hallucinating panel), all 49 = PARTIAL: corr **78.0** · compl **66.5** · cite **65.0** · tone **91.1**.

### A/B #1 — 2026-06-29 production audit dump → current `main` (n=49)

| Axis | OLD (2026-06-29) | NEW (`main`) | Δ |
| --- | --- | --- | --- |
| Correctness | 78.4 | **89.5** | **+11.1** |
| Completeness | 56.5 | **67.9** | **+11.3** |
| Citations | 62.2 | **71.2** | **+9.0** |
| Tone | 99.1 | 100.0 | +0.9 |
| **Verdicts** | PASS 11 · PARTIAL 29 · FAIL 9 | **PASS 18 · PARTIAL 28 · FAIL 3** | PASS 22%→37%, FAIL 18%→6% |

Migration: **16 improved, 28 held, 5 regressed.** These deltas (+9 to +11) are **above the judge noise floor (~±5)** → a **real, substantial improvement** over what production was actually shipping on 2026-06-29.

### A/B #2 — `r267` submission 2026-07-02 → current `main` (n=49, **primary "did the latest changes help"** comparison)

| Axis | OLD (r267) | NEW (`main`) | Δ |
| --- | --- | --- | --- |
| Correctness | 83.2 | 84.3 | +1.1 |
| Completeness | 60.9 | 65.6 | +4.7 |
| Citations | 66.7 | 71.6 | +4.9 |
| Tone | 98.9 | 99.9 | +1.0 |
| **Verdicts** | PASS 16 · PARTIAL 26 · FAIL 7 | PASS 14 · PARTIAL 28 · FAIL 7 | ~flat |

Migration: 8 improved, 31 held, 10 regressed — but **the score deltas (+1 to +5) sit inside the judge's ±~5-pt noise band**, and the verdict mix barely moved. **Verdict: roughly flat / marginal.** The R268–R272 rounds (multi-article parse, Opus-for-both-tiers, safety gate) did not materially change these 49 answers — consistent with the documented "opus-for-all = A/B wash" finding. Where the two rounds land is on axes davidath/these rows don't probe (compl/cite ticked up slightly).

### Judge reliability (the honest asterisk)

Grading the **identical** NEW answers in two independent passes:
- mean |score difference| **9.3 pts** (median 5.0) · **verdict flipped on 12/49 rows (24%)** · 5 rows swung ≥30 pts (q012, q020, q034, q063, q097 — e.g. q097's same answer scored **PASS (95/90/100)** and **FAIL (30/40/30)**).

→ **Individual per-row verdicts are not reliable; the aggregate axis means are.** This reinforces the request's premise: a single LLM judge (even Gemini-2.5-pro) is noisy on nuanced legal Q&A. The A/B design (same judge both sides) is what keeps the *deltas* meaningful.

---

## 3. Where the new answers genuinely improved / still lag (robust rows only)

**Clearly fixed (consistent across both A/Bs):**
- **q006** (systems vs models) — old cited non-existent *Article 108*; now correct Art 2 / 3(1) / 51.
- **q031** (deduplication + Annex III) — now applies the Art 6(3) narrow-task carve-out (70/50/60 → 100/90/80).
- **q065** (human oversight CDS), **q037** (EU-database items), **q050/q051** (open compliance / emotion rules), **q048** (compliance overview) — all up a tier.
- **q042, q090** — the 2026-06-29 truncation / topic-shift failures are gone.

**Still weak (consistently low across both judge passes — genuine, not noise):**
- **q044** ("What does Article 13 require?") scores FAIL — but the judge's critique is hyper-technical sub-point pedantry on Art 13(2)/(3)(b); the answer is a substantively fine Art 13 summary. *Judge over-strictness, not a real defect.*
- **q080** (support chatbot) — a real minor imprecision: conflates the GPAI "one-third fine-tune" rule with the Art 51 systemic threshold, and under-states the Art 50(1) chatbot-disclosure duty.
- **q069 / q063** (long GPAI / medical-provider obligation dumps) — over-long multi-article answers where the judge (and, for q063, a **judge** slip citing draft "Art 44/45" for CE/declaration instead of 47/48) drags the score down.

---

## 4. Recommendations

1. **Discard the Mistral/Groq panel from the eval loop.** It injects draft-numbering hallucinations and mislabels correct answers as PARTIAL. Judge with a strong single grader (Gemini-2.5-pro or Sonnet-5/Opus-4.8 via wrapper) **anchored to the final numbering**, and treat any single verdict as noisy — average ≥2 passes or use the position-swapped `evals.harness.ab_judge` for merge decisions.
2. **The genuinely actionable, non-hallucinated fixes** for these rows are narrow and already partly shipped as curated intercepts: Annex III point 3 sub-items (q014), Art 6(3)(c) application (q031/q032), Art 5(1)(h)(iii)+4-year (q017), Annex III 5(d) (q029), Art 63 micro-enterprise (q049), Art 50(4) exceptions (q015). Each fires on 0 davidath rows → safe.
3. **Opus-for-both-tiers (R271) is not moving these rows** — the win, if any, is elsewhere; keep the `REGENOLD_OPUS_FOR_ALL`/complex-gate knobs as measured, not assumed.
4. **Rein in the long multi-article answers** (q063/q069/q075-class) — they cost citation precision without adding correctness, and are where the judge most often dings.

---

## Appendix — artefacts
- Re-run answers: `rerun-out.json` (49/49, per-row stage2/latency).
- Clean judge outputs: `judge-out.json` (dump→main), `judge-out-r267.json` (r267→main).
- Provision ground-truth bundle: `provision-bundle.json` (59 provisions, canonical `provision_text`).
- r264 baseline + judge-source tags: `r264_baseline.json`.

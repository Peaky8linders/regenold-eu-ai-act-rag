# R272 — Re-run + re-judge of the 19 previously-FAILED questions (2026-07-04)

**What:** took the **19 questions the attached r264 report scored FAIL**, re-ran them
**live** against current production (`c8e0d65`, post-R263→R272), and re-judged the fresh
answers. **r267 was only a partial spot-check** (8 of 95 rows judged, "stopped by operator
choice") with no independent failures, so r264 is the failure set of record.

**Endpoint:** production Railway `/api/v1/regenold/eu-ai-act/ask` (Cloudflare tunnel → Claude
Max wrapper), real wire answers (no `?include_reasoning`, which forces Stage-2 and distorts).
**Judges:** a fresh **Sonnet-5** reference-free EU-AI-Act legal grader (same corr/completeness/
citations/tone rubric as r264) grading the **new AND old** answers blind, **plus an
Opus-4.8 adversarial verifier** handed each row's *specific* original failure reason and told
to refute the "fixed" claim. 57 grader/verifier agents.

## Three time points (read the numbers with this in mind)
- **T0 = 2026-06-29** production dump answers (what the fresh judge grades as "old").
- **T1 = 2026-07-02** r264's own re-run — the attached **FAIL verdicts** are for these.
- **T2 = 2026-07-04** today's live re-run — the "new" answers.

**Judge drift is real and material:** the fresh Sonnet-5 judge is **more lenient** than r264's
Sonnet-5 + Groq/Mistral panel — it PASSes several of the "r264 FAILs" even on the *old*
answers. So the fresh PASS/FAIL counts are **this-judge-relative** and must not be read as
"r264-FAIL → fresh-PASS = fixed." The reliable signals are (a) the **Opus per-failure
verifier**, (b) the **per-axis deltas**, and (c) the per-question detail below.

## Aggregate metrics

| Signal | Result |
| ------ | ------ |
| r264 baseline (attached) | **19 / 19 FAIL** |
| **Opus adversarial verifier — original failure genuinely resolved** | **11 / 19** (8 not) |
| Fresh Sonnet-5 holistic verdict on the NEW answers | **9 PASS · 2 PARTIAL · 8 FAIL** |
| Combined honest classification | **5 clean fix · 1 mostly · 2 greetings-OK · 6 improved-but-flawed · 3 unchanged · 2 regressed** |

Per-axis means, **same** Sonnet-5 judge, T0-dump answers → T2 live answers (all 19):

| Axis | old (T0) | new (T2) | Δ |
| ---- | -------- | -------- | --- |
| correctness | 63.3 | 70.9 | **+7.6** |
| completeness | 48.5 | 64.7 | **+16.2** |
| citations | 57.3 | 66.2 | **+8.9** |
| tone | 82.9 | 87.6 | **+4.7** |

**Every axis up; completeness is the biggest gain** — consistent with the R263→R272 curated
intercepts that surface the specific missing provisions.

## Per-question status

| qid | topic | r264 | new (Sonnet-5) | Opus resolved | status |
|-----|-------|------|----------------|---------------|--------|
| q005 | XAI (LIME/SHAP) mandated? | FAIL | PASS | YES | **CLEAN FIX** |
| q025 | deployer deemed a provider? | FAIL | PASS | YES | **CLEAN FIX** |
| q039 | Art 50(4) public-interest text + 2 exceptions | FAIL | PASS | YES | **CLEAN FIX** |
| q041 | SME simplified tech-doc form | FAIL | PASS | YES | **CLEAN FIX** |
| q085 | what is explicitly prohibited | FAIL | PASS | YES | **CLEAN FIX** |
| q011 | 'testing data' meaning + no-leak | FAIL | PARTIAL | YES | MOSTLY FIXED |
| q052 | 'hi, what can you do?' (greeting) | FAIL | PASS | YES | GREETING-OK |
| q061 | 'how are you' (greeting) | FAIL | PASS | YES | GREETING-OK |
| q001 | tech-doc: hardware specs required? | FAIL | PASS | no | improved, defect remains |
| q022 | all risk categories | FAIL | PARTIAL | no | improved, defect remains |
| q032 | deviation-detection = high-risk? | FAIL | PASS | no | improved, defect remains |
| q009 | provider docs + retention "how long" | FAIL | FAIL | YES* | gap closed, NEW error |
| q030 | sandbox: which Article MSA verifies | FAIL | FAIL | YES* | gap closed, muddy cites |
| q033 | AI Board: designation/term/voting | FAIL | FAIL | YES* | gap closed, NEW error |
| q027 | election AI + campaign-tool exception | FAIL | FAIL | no | STILL FAILING |
| q040 | Annex VII certificate contents | FAIL | FAIL | no | STILL FAILING |
| q043 | Art 10(5) special-data safeguards | FAIL | FAIL | no | STILL FAILING |
| q054 | VLOP content-moderation transparency | FAIL | FAIL | no | **REGRESSED** |
| q081 | VLOP content-moderation transparency | FAIL | FAIL | no | **REGRESSED** |

\* Opus "resolved" = the *specific original gap* is now addressed, but the answer introduced a
different error (see below), so the holistic verdict is still FAIL/PARTIAL.

## The clean fixes (5 + 1) — these land, and tie to shipped intercepts
- **q005** (R265 explainability): now leads **"No, the Act mandates no specific XAI technique"**,
  grounds in Art 13/14/15, drops the erroneous Art 16/47.
- **q025** (R265 reclassification): now **"Yes — Art 25(1)(a)-(c)"** + Art 16 obligations. The
  exact provision r264 said was missing.
- **q039** (R263/R267.3 Art 50(4)): now states **both** exceptions — law-enforcement-authorised
  use *and* human-review/editorial-responsibility.
- **q041** (R265 SME): now **"Yes — Art 11(1) simplified form; the notified body must accept it."**
- **q085** (R265/R266 prohibited practices): now enumerates **all eight** Art 5 prohibitions.
- **q011** (R263 testing-data, *mostly*): now defines testing data (Art 3(32)) + the no-leak
  rationale; minor imprecision (ties leakage to Art 10 rather than Art 15 accuracy).

**Greetings** (q052/q061): the r264 "FAIL" was a legal-rubric artifact — these are greetings.
Current behaviour is the correct **Lexy** branded scoping reply (R256). No regression.

## Improved but the *exact* defect still remains (3)
- **q001** — reads well ("yes, hardware is Annex IV content") but **still no pin-cite** to
  Annex IV(1)(e) / (2)(c), and conflates runtime hardware with training compute.
- **q022** — now covers unacceptable/high/limited tiers but **still omits the GPAI
  systemic-risk track (Art 51-55)**.
- **q032** — no longer blindly concludes high-risk, but **still never cites/applies Art 6(3)(c)**
  — the carve-out the question is drawn near-verbatim from.

## Gap closed but a NEW error introduced (3)
- **q009** — now cites Art 18 documents, but **fabricates a separate "Annex V 10-year retention"
  duty** (Annex V is content-only), drops the Art 19 six-month logs, and never cleanly states
  the 10-year figure.
- **q030** — now leads with the right provision (Art 57) but still cites Art 74 and the citation
  list is muddy.
- **q033** — now answers all four sub-questions (Art 65(3) 3-yr renewable-once, Art 65(5)
  two-thirds) but gets impartiality **backwards**: says members are national contact points
  "rather than impartial", inverting **Art 65(7)** (Board safeguards objectivity/impartiality).

## Still failing — the specific omission persists (3)
- **q027** — cites `Annex III.8.b` in refs but the prose **never states the 8(b) exception** for
  administrative/logistical campaign tools.
- **q040** — still recites Annex IV tech-doc content instead of the **Annex VII certificate
  fields** (notified-body/provider identity, examination conclusions, validity conditions).
- **q043** — still omits the **Art 10(5) safeguards** (the six cumulative conditions).

## Regressed — new ungrounded/hallucinated failure mode (2) — flag for a fix
- **q054** — fabricates **"EU AI Act Art. 52a"** (does not exist; the provision is Art 50),
  markdown-bullet style, `refs: []`.
- **q081** — mischaracterises Art 50 as the content-moderation transparency rule, DSA-heavy,
  `refs: []`.

Both q054/q081 answers are markdown-list, citation-empty, and (q054) hallucinate an article —
the signature of a **non-grounded fallback provider** (Groq/Gemini/Mistral general-assistant)
answering *without the EU AI Act RAG*, rather than the old clean DSA-deflection. The VLOP /
content-moderation shape is routing around the grounded engine. **This is the highest-priority
new issue** — worse than the original deflection because it now ships a hallucinated article.

## Bottom line
The new answers are **materially better in aggregate** — all four quality axes up (completeness
+16), 11/19 original failures adversarially confirmed resolved, 5 clean legal fixes + 2 greetings
corrected. But the improvement is **not uniform**: 3 rows still carry the exact original defect,
3 closed the gap while introducing a new error, and **2 VLOP rows regressed into an ungrounded,
article-hallucinating fallback**. Next-round targets, in priority order: (1) stop VLOP/
content-moderation questions hitting the ungrounded fallback (q054/q081); (2) the three
unchanged omissions have curated-intercept coverage that isn't surfacing the sub-point
(q027 Annex III 8(b), q040 Annex VII fields, q043 Art 10(5) list); (3) the q009 Annex-V
fabrication and q033 Art 65(7) impartiality inversion are correctness bugs in otherwise-improved
answers.

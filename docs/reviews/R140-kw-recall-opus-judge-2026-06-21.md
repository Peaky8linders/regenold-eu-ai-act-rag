# R140 — Keyword-recall fix + Opus-4.8-judge analysis across 3 ground-truth sets (2026-06-21)

**Branch:** `r140-opus-kw-canonical` (R139 Opus-always foundation + canonical-terminology Stage-2 prompt).
**Datasets judged:** Antifragile expert-review (20, docx GT + remarks), GraphRAG-paper / Aggio et al. (23, paper answers + citations), MedTech-GraphRAG-v124 (24). 67 fresh answers, all generated live (Claude **Opus 4.8** Stage-2, production env, `?include_reasoning=true`).
**Per-answer detail:** [R140-fresh-answers-opus-judge-appendix.md](R140-fresh-answers-opus-judge-appendix.md).

---

## 1. The reported problem and its root cause

The user reported keyword-recall dipping **0.65 → 0.56** on the golden medtech set after the
"Opus phrasing" change (R139 routed every Stage-2 answer to Opus 4.8). Systematic debugging found a
**dual root cause**, not one:

1. **Eval-environment truncation cap (the dominant masker).** The golden runner was invoked with the
   *code defaults* `MAX_ANSWER_SENTENCES=3` / `REGENOLD_QA_LENGTH_CAP=400`, while production
   (`railway.toml`) runs **uncapped** (`MAX_ANSWER_SENTENCES=0`, `QA_LENGTH_CAP=1200`). Opus front-loads
   a framework preamble, so the 3-sentence cap kept the preamble and **dropped the verdict + canonical
   terms before they were scored**. The R139 0.56 was measured under this cap.
2. **Non-canonical phrasing.** Even uncapped, Opus spelled obligations its own way
   ("human-oversight", "operative provision") instead of the Act's literal terms
   ("human oversight", "transparency"), missing the gold keyword tokens.

## 2. The fix (validated change)

`app/data/graph_rag_prompts.py::ANSWER_GENERATE_SYSTEM` (Stage-2 only → **davidath byte-identical**):
- **(A) Canonical terminology** — name obligations/tiers in the Act's own spelling (risk management
  system, data governance, human oversight, conformity assessment, transparency, post-market
  monitoring, limited risk, not high-risk …); forbid hyphen variants that miss the literal gold token.
- **(B) Compact enumeration** — name the *full* obligation set in one compact list rather than
  elaborating two and omitting the rest.
- **(C) Verdict-first for non-high-risk classification** — state the tier verdict + Article 50 first
  instead of dumping the high-risk framework.
- **(D)** Name the Article 14 oversight measures (interpret, automation bias, override).

## 3. Scorecard + clean attribution (golden medtech-v124, n=24)

A 2×2 A/B isolates the prompt from the cap (live Opus, same prod flags except the answer-length cap):

| | capped env (3 sent / 400 char) | **prod env (uncapped)** |
| --- | --- | --- |
| **original prompt** | 0.564 (the reported R139 number) | 0.586 |
| **canonical prompt (this PR)** | 0.565 | **0.729** |

- Uncapping alone lifts kw only **+0.022** (0.564→0.586).
- The **canonical prompt is the dominant lever: +0.143** under the prod env (0.586→0.729).
- Under the cap the prompt looks flat (+0.001) **because truncation drops the terms before scoring** —
  this is exactly why the dip was mis-diagnosed.

**Per dataset (fresh, live Opus, prod env):** Antifragile kw **0.800**, GraphRAG-paper **0.721**,
MedTech **0.729** → **overall 0.748** (vs the 0.56 baseline). Regulatory-tone (regex) 1.0 everywhere;
Ref Loose 0.86 overall. The ≥0.8 target is met on Antifragile and approached elsewhere; the residual
gap is L3/L4 complexity + a handful of arbitrary gold tokens ("scope", "exception", "transition",
"integrated", morphological variants like "educational").

## 4. Opus-4.8 judge — the issues (this is the analysis the user asked for)

The judge fan-out (one Opus-4.8 agent per answer) returned rich verdicts before the Claude session
quota reset; the per-answer deterministic signals cover all 67. The issue distribution:

| Issue | Count / 67 | What it is |
| --- | --- | --- |
| **Verbose / framework-dump** | **54** | answers mean **1512 chars** vs gold ~300–520; Opus digresses into nuance the question never raised |
| **Over-citation vs gold** | 32 | tangential provisions pulled in (the R138 semantic-contract + Component-D grounding) |
| **Term miss (≥1 keyword)** | 43 | a canonical token absent or a morphological variant ("education" vs "educational") |
| **First-person tone slip** | 22 | "so **I** do not enumerate them here" — the regex tone-guard (tone=1.0) does not catch first person |
| **Under-citation (missing a gold ref)** | 14 | e.g. the Article 27 FRIA on a public-authority-deployer question |

**Root-cause read (from the reasoning logs):** the dominant defects — verbosity and over-citation —
trace to the **R138 semantic-contract advisory** (`risk_tier_distinction`, `chain_completeness`) plus
the **Component-D grounding guard**. The Opus reasoning notes show these steer Opus into stating
distinctions and citing chains the question did not need, which bloats the answer and pulls tangential
citations. The kw fix is orthogonal to (and unharmed by) these; they are the next round's target.

**Representative Opus-4.8 verdicts (verbatim from the fan-out):**

- **`grb_03`** (emergency-triage classification) — *minor_issues*; correctness ✓, term_coverage ✓, but
  **citations ✗ / conciseness ✗ / tone ✗**: "2069 chars … framework-dumping that buries the core
  verdict under unrequested nuance", a first-person slip ("so I do not enumerate them here"), and a
  spurious Article 5 citation. Reasoning note: *"the risk_tier_distinction contract … steered Opus into
  stating a distinction the question never needed."*
- **`grb_04`** (public-authority eligibility) — correctness ✗ / citations ✗ / conciseness ✗:
  **material omission of the Article 27 FRIA** (the gold-distinctive deployer duty) while over-citing
  11 provider-side refs (Art 43/40/46/49/71); 1618-char run-on.
- **`grb_02`** (transparency obligation) — *correct*; the only soft spots: the literal word
  "transparency" is absent (4/5 terms) and the high-risk medical-diagnostic carve-out is omitted.
- **`gt_12`** (emotion recognition not-always-prohibited) — *correct*; nits: a redundant "In short:"
  recap and "education" vs the gold's "educational".
- **`grb_05`** (R&D scope exclusion) — *minor_issues*; correct verdict in tight voice, only
  over-cites Articles 49/47 and omits the Article 2(8) pre-market carve-out.

## 5. Conciseness — measured, not assumed

The user required answers to be concise (not "long Opus novels"). The fresh answers **are** long
(mean 1512 chars). A natural fix — re-impose a sentence cap — was tested and **rejected on evidence**:

| medtech-v124 (live Opus, prod env) | kw | mean len | answers > 600 chars |
| --- | --- | --- | --- |
| uncapped (`MAX_ANSWER_SENTENCES=0`) | **0.729** | 1532 | 23/24 |
| 4-sentence cap | 0.554 | 889 | 18/24 |

A 4-sentence cap **drops kw back to 0.554** (re-creating the dip) because Opus's canonical terms are
spread across many long sentences — capping drops them, and the answer is *still* long (889 chars).
**A cap is not a free conciseness win; it sacrifices the kw goal.** Conciseness therefore must be a
*generation-side* fix (tighter Stage-2 discipline / a smaller thinking budget / defusing the R138
semantic-contract digressions), tracked as R141 below. The operator's `MAX_ANSWER_SENTENCES=0`
(R126) is preserved so the kw win is not lost.

## 6. Gates

| Gate | Result |
| --- | --- |
| davidath bench (476, deterministic) | **byte-identical to R139** — QA Ans Strict 0.4022 / Ref Loose 0.8321 / Ref Strict 0.5528 / Tone 1.0; OVERALL Ans Strict 0.3535; multi-turn 20/20 |
| OOS scope probe | 21/21, 0 leaks |
| Change surface | Stage-2 prompt only (6 lines) + the R139 Opus-always foundation; deterministic bench skips Stage-2 → byte-identical by construction |

## 7. Recommendations (R141)

1. **Defuse the R138 semantic-contract digressions** — `risk_tier_distinction` / `chain_completeness`
   advisories drive 32/67 over-citations and much of the verbosity; gate them to fire only when the
   question actually implicates the distinction.
2. **Generation-side conciseness** — a cap drops kw; instead tighten the Stage-2 length discipline for
   the verbose datasets and/or trim the Opus complex-path thinking budget, then re-measure kw + length
   together (a cap is off the table).
3. **First-person tone-guard** — extend `tone_guard` to rewrite/drop first-person "I/me/my" (22/67
   slips the regex tone metric misses).
4. **Re-run the Opus-4.8 judge fan-out** after the session quota resets to attach a full per-answer
   verdict to all 67 (the throttled run was capped by the session limit, not the harness logic).

## 8. Reproduce

```bash
# prod env (the answer-length cap is the load-bearing flag):
env $(cat .evalout/prodenv.txt) OPENAI_API_BASE=http://127.0.0.1:8000/v1 OPENAI_API_KEY=dummy \
    NEO4J_URI= python -m evals.regenold.run_medtech_graphrag_v124 --local --label r140 --verbose
# fresh antifragile + graphrag:  python .evalout/r140_gen_fresh.py   (same env)
# Opus-4.8 judge fan-out:        Workflow .evalout/r140_judge_workflow.js (args = r140-judge-index)
```

Sidecars: `evals/bench/results/medtech-graphrag-v124-r140-treat-prod.json`,
`…-r140-baseline-prod.json`, `…-r140-concise4.json`, `r140-fresh-af-graphrag.json`,
`r140-judge-input.json`, `r140-analysis.json`.

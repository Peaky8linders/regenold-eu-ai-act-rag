# R452 — two live citation defects, root-caused and fixed

## The defects (production `8700e15`, live re-run 2026-09-28)

| question | shipped | should be |
| :--- | :--- | :--- |
| rg_018 (Q17) Commission amends Annex III | `Annex III.7.b` (migration risk assessment) | `Annex III` |
| rg_096 (Q95) area vs use case, Article 6(2) | `Annex III.7.b` | `Annex III` |
| part1_q06 (Case A) minimal-risk systems | `Article 5.1.d`, `Article 6.3.d`, `Article 50` | Articles 4, 5, 6, 50, 95 |

## Root causes

1. **The grain deepener counted vocabulary as evidence.** `_pick_unit` scores units by
   raw token overlap (question ×2, answer ×1) and Audit Finding 1 requires question
   overlap, but ANY shared token counted. At every wrong pick the only question token
   the chosen unit shared was `risk`, which occurs in 31 % of the Regulation's 655
   paragraphs and points. On rg_018/rg_096 point 7 also won because the answer lists
   all eight Annex III areas, so point 7's heading words ("migration, asylum and
   border control") are in the answer.
2. **The minimal-risk curated answer seeded only its three contrast refs.**
   `tests/test_r111_qa_review.py` recorded the premise that Articles 4 and 95 "reach
   the wire via `_add_prose_named_refs` on the live path". That pass is
   `_stage2_landed`-gated and curated answers skip Stage-2, so they never did.

## Fix

`REGENOLD_GRAIN_QUESTION_SUPPORT` (default ON, veto-only): the winning unit must share
an informative question token (Act-wide document frequency < 20 %; Article 3
definitions exempt), and a bare annex stays bare when the answer names ≥ 3 of its
points by heading. The minimal-risk intercept now seeds Articles 4, 5, 6, 50 and 95.

## Measured

`grain_question_support_replay.py` over every recorded official checkpoint, unique
graded turns with a gold key (3,438), real `evals.official.rubric`:

```
refs vetoed 315: wrong picks removed 311, correct picks lost 4 (all rg_106)
head-set violations 0, count changes 0
ref_loose  94.03 -> 94.03  (+0.00)
ref_strict 52.38 -> 52.26  (-0.12, upper bound: prose-named restores not credited)
ref_conc   45.61 -> 45.61  (+0.00)
```

Before the Article 3 exemption the loss was 10 (rg_076 `Article 3.2`, the definition
of risk, ×6) and −0.29 pp. Re-run the script to regenerate the output.

## R452b — question support must also separate the candidates

**Defect.** rg_105 (Q104, Annex X) still shipped `Article 5.1.d` for an answer that says
"without prejudice to the Article 5 prohibitions". The question tokens are `about` and
`used`; `used` is not Act-wide vocabulary, so R452 let it count, but Article 5(1) and 5(2)
both carry it, and at point level only (d) does ("used to support the human assessment").

**Fix.** `REGENOLD_GRAIN_DISCRIMINATING_SUPPORT` (default ON, veto-only, cache-keyed): with
two or more candidates, a question token every candidate carries no longer counts as
support. Below paragraph level the answer may still choose a point if it shares at least
two non-generic tokens with that point and no other candidate (rg_085 keeps
`Annex III.1.a` for its remote biometric identification answer). Paragraph level gets no
such escape: paragraphs share procedural wording ("placed on the market", "put into
service"), which let rg_105's `5.1` through in a first cut.

**Measured** (`--flag=REGENOLD_GRAIN_DISCRIMINATING_SUPPORT`, increment over R452, same
3,438 turns; the new `credited` arm keeps leaves the answer's prose names, which the
prose sub-point passes restore on the live path):

```
refs vetoed 216: wrong picks removed 214, correct picks lost 2 (both prose-named)
head-set violations 0, count changes 0
ref_strict 52.38 -> 52.35 (-0.03)   credited 52.38 (+0.00)
ref_loose / ref_conc +0.00
```

Two rejected variants: the rule without the escape (349 vetoed, 37 correct lost, credited
−0.22 pp; rg_085 and rg_017 lost their points) and the escape at every level (Q104 not
fixed).

## Related-issue sweep: curated answers that state a provision they do not cite

`curated_ref_audit.py` walks every curated `answer`/`refs` literal. 9 answers name a head
their refs omit; 7 are contrasts, parentheticals or a non-AI-Act provision (MDR Article
83). The two operative misses stay as they are because citing them would move away from
the evaluator's minimal keys: rg_041 (SME simplified documentation) expects only
`Article 11.1`, not Annex IV, and rg_022 (risk categories) expects only `Article 6` while
the risk-framework answer already cites 11 provisions.

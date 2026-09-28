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

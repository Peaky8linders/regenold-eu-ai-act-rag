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
of risk, ×6) and −0.29 pp.

⚠ **Corrected in R452c.** This block and the R452b block below measured only references
the deepener had produced on the recorded wire. They reproduce only with
`REGENOLD_GRAIN_DISCRIMINATING_SUPPORT=0` forced (the R452b check is nested under this
flag, which was not documented), and "−0.12 upper bound" is not a bound: the replay could
not see gold leaves the enumeration veto removed from recorded bare heads (rg_093,
rg_029). The R452c counterfactual below replaces both.

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

`curated_ref_audit.py` walks every curated `answer`/`refs` literal. The first cut found 9
answers naming a head their refs omit. In R452c it reads heads with the route's own
`answer_completeness.named_heads`, so plural and range forms count ("Articles 13 and
50"), and it lists dicts it cannot audit instead of skipping them: 10 found, 1 not
audited (a non-literal answer). Most are contrasts, parentheticals or a non-AI-Act
provision (MDR Article 83). The operative misses stay as they are because citing them
would move away from the evaluator's minimal keys: rg_041 (SME simplified documentation)
expects only `Article 11.1`, not Annex IV, and rg_022 (risk categories) expects only
`Article 6` while the risk-framework answer already cites 11 provisions. Open: the
risk-framework answer states the Article 4 and Article 95 duties the minimal-risk
intercept now seeds, and `high_risk_obligations_deadline` names Article 50 in a plural
("Articles 13 and 50").

## R452c — the review findings, fixed

A five-lens code review of R452/R452b (`CR-SKILL.md`), followed by a verification pass
that re-ran every probe on a `git archive` of `9d00a39`: 13 findings, all confirmed or
partly confirmed.

| finding | defect | fix (all default ON, deny-list, cache-keyed, veto-only) |
| :--- | :--- | :--- |
| F2 | the enumeration veto was question-blind: it removed gold leaves from recorded bare heads (rg_106 `III.6.d` ×4, rg_093 `III.7.b` ×2, rg_029 `III.5.d`, rg_007 `III.1.a`) | the veto applies only when the question alone does not choose a point |
| F3 | function words sit just under the 0.2 cut (`under` 0.18, `not` 0.17, `use` 0.12, `used` 0.09), so paraphrases leaked: `6.3.d`, `6.6`, `5.1`, `6.4`, `Annex X.3`, `5.1.g`; rg_018 shipped `Annex III.7` on 26 of 36 recorded answers | `_GRAIN_FUNCTION_WORDS`; `REGENOLD_GRAIN_SUBJECT_HEAD` keeps a provision the question is about as a whole ("amend Annex III", "what is Annex X for") at head grain |
| F1 | on a multi-turn request the deepener read the flattened transcript; a pushback without "Let's try again:" takes challenge recovery and shipped `5.1.h` / `6.2` / `50.2` / `95.2` on the curated minimal-risk answer | `REGENOLD_GRAIN_LIVE_QUESTION`: the deepener reads `resolved_question`, else the live user message |
| F4 | the minimal-risk intercept declares five refs, exactly the plain budget, so "..., such as chatbots and emotion recognition tools?" evicted `Article 95` | `REGENOLD_CURATED_DECLARED_FIRST`: declared refs are ordered first before the cut |
| F13 | the deepener guessed sub-points of curated heads (`6.3.d`, `6.4`, `6.6`, `95.2`, and the forced `6.2` on "regulated differently from high-risk"). A general guard is not safe: the forced `6.2` hits gold on 215 of 800 recorded pairs | `REGENOLD_CURATED_HEAD_GRAIN`, scoped to curated answers: a pick under a declared head survives only when the answer states that unit's own content (`_curated_answer_backs`; rg_009 keeps `Article 18.1`); the R115 rescue obeys the same rule |
| F5 | a failure computing the generic-token set was cached for the worker's lifetime, silently switching R452 off | failure logged once and never cached |
| F8 | the Article 3 exemption let "minimal risks" pick `3.65` (systemic risk) | exempt only when the question carries the defined term |
| F6, F11 | replay numbers did not reproduce; nesting undocumented; stale comments | counterfactual replay below; docstrings, CLAUDE.md rows and comments corrected; `score_arm` records the re-deepen commit and flags, and the live runner scores production boards with `--no-deepen` |
| F7 | the veto-only tests accepted only ON ∈ {OFF, head}; the true contract is an ancestor of OFF (219 of 10,659 recorded pairs stop at an intermediate level) | tests assert the prefix contract |
| F9 | the live runner let `.env` behavioural flags override the shell and returned 0 on failed steps | credentials only, shell wins, `REGENOLD_SKIP_DOTENV=1`, commit argument required, non-zero exit on any failed step |
| F10, F12 | the curated audit missed plural forms | reuses `named_heads` (above) |

One consequence had to be handled: with function words out, the question's only overlap
with the three Annex III(1) points is `used`, so the R452 veto fired before the R452b
answer tie-break could run and rg_085 lost `Annex III.1.a` (17 recorded draws). Below
paragraph level the tie-break now applies whenever the question cannot choose, whether it
has no informative support or none that separates the points. The tie-break returns the
unguarded pick, so it only ever withholds a veto.

**Measured.** `grain_question_support_replay.py RESULTS_DIR` is now a counterfactual:
every recorded graded turn's wire references are folded onto their heads and re-deepened
with all R452-family guards off and at the defaults, same question, answer and heads.
Scored with the real rubric. Its baseline is the pre-R452 deepener applied to every
head, so its absolute values are not comparable with the blocks above.

```
graded turns with gold 3,438
coordinates changed 1,959: wrong picks removed 1,911, correct picks lost 48, gained 0
  not named by the answer's prose: 9 (rg_006 Article 2.1.a x6, rg_017 Article 5.1.h x3)
head-set violations 0
ref_loose   94.03 -> 94.03 (+0.00)
ref_strict  64.03 -> 62.67 (-1.37)   live 63.77 (-0.26)
ref_conc    46.54 -> 46.54 (+0.00)
```

`live` leaves a head to the prose where the answer names one of its points, because on
the live path `_surface_prose_subpoints` puts that point on the wire before the deepener
runs. rg_006's loss is the paragraph-level rule working as designed: the question's only
informative token, `models`, is in Article 2(1), 2(6) and 2(8) alike.

`curated_guards_official110.py` (offline, the real route, the two curated flags on and
off): 6 of the 110 reference lists change; on the 4 with a gold key Ref Strict 75.0,
Loose 100.0, Conc 31.4 in both arms. The subject rule changes none of the 3,438 recorded
graded turns with a gold key; it decides only on paraphrases that name a topic.

Route pins (`tests/test_r452c_route_minimal_risk.py`): nine minimal-risk phrasings, a
two-turn conversation and a bare pushback all ship Articles 4, 5, 6, 50 and 95; the
"instructions for use" control still ships `Article 13.3`.

# R455 — prose citations in the Regulation's form; "both sides" only where the question leaves the context open

## What the expert review cards still showed

Cases A–D re-run live on production `9e4e128` (Sonnet 5.5 judge over the wrapper, grouped,
3 repeats): A 4/4, B 4/4, C 4/4, D 4/4. The criteria pass, but Case C's answer and references
disagreed with each other and with the expert critique:

```
refs   ['Article 5.1.f', 'Annex III.4.b', 'Article 26']        expected ['Article 5.1.f']
prose  "Article 5.1.f", "Annex III.1.c", "Annex III.4.b", "Article 26.7"
tail   "It could still be high-risk under Annex III.1.c ... or Annex III.4.b ...
        Article 26.7 requires the company, as employer, to inform workers' representatives ..."
```

The critique of the August answer had named exactly this ("it drifts into irrelevant Article 26
high-risk deployer logging obligations"). The prose also names `Article 26.7` while the wire
carries a bare `Article 26`: the R133 surface pass reads only the parenthesised form, so a
dotted sub-point in the prose never reaches the wire.

## Root cause, captured at the provider seam

Offline dispatch probe (stubbed provider, real route), Case C, single turn: system 59,647 chars,
user 54,789 chars. Both instructions are in the SYSTEM slot only:

* rule 2: `Use clear EU AI Act citations EXACTLY matching the competition format ... "Article 3.2"
  ... DO NOT use parentheses for paragraphs like "Article 3(2)"`, contradicting rule 1 and the
  user-channel sub-paragraph clause, which both ask for `Article 5(1)(f)`. The references field
  is built by the route, so the rule only ever affected the prose. 236 of 1,531 unique recorded
  answers carry dotted coordinates in their prose.
* the DIRECT-VERDICT rule: `If a practice is prohibited ONLY in specific contexts ... state BOTH
  sides: the context where it is prohibited AND its treatment elsewhere`, unconditionally.

## Fix

* rule 2 now asks for the Regulation's form in the prose (`Article 5(1)(f)`, `Annex III(5)(d)`)
  and forbids the dotted identifiers of the references list there.
* the both-sides rule applies when the question leaves the deciding context open ("always",
  "ever", no setting or purpose stated) or asks about more than one tier. For a concrete
  deployment whose stated setting and purpose decide the tier, the answer gives that verdict and
  the carve-out that could change it, and does not add how other settings or systems are treated.
* the emotion-recognition rule states the same for a workplace or education deployment: the
  Article 5(1)(f) verdict and its medical or safety carve-out, with the Annex III(1)(c) treatment
  only where the stated purpose is itself medical or safety.

Which official questions need the both-sides treatment (criteria naming both tiers): rg_074
("always prohibited?"), rg_085 and rg_089 ("prohibit or high-risk?"). rg_085 and rg_089 leave the
context open or ask about more than one tier, so the scoped rule still reaches them. **Corrected in
R455b:** rg_074 never reaches Stage-2. It selects the curated `emotion_recognition_general` answer,
which skips Stage-2, so no system-prompt rule applies to it (its identical 321-character answer in
every draw is that curated text). rg_007 (a concrete
1:1 verification deployment) needs one verdict. No official question with a concrete deployment
inside a prohibited context asks for the other tiers.

Verified on the dispatched system bytes: the old rule 2 and the unscoped rule are absent, the
three new passages present. `tests/test_r455_prose_citation_form_and_tier_scope.py` passes on the
fix and fails on `9e4e128`'s prompt.

## Measured

Local route, live Stage-2 over the wrapper (no graph or reranker locally), Sonnet 5.5 judge, grouped,
3 repeats, two draws per question on the fixed prompt:

```
Case C   4/4, 4/4   refs ['Article 5.1.f', 'Article 3.39']  no dotted prose, no Annex III / Article 26
rg_074   4/4, 4/4   still maps all three tiers (prohibited, Annex III(1)(c), Article 50(3))
rg_007   3/3, 3/3
rg_085   2/4, 3/4   fails the 1:1 verification exclusion / toy-status criteria
rg_089   2/3, 2/3   fails the Article 6(3)(a) reason
```

rg_089 has failed that same criterion in 30 of 32 recorded runs, so it is not this change. rg_085 is
fully met in 36 of 57 recorded runs and 4/4 on the recent production runs; a paired local draw on
the old prompt was still running at merge time. Production re-runs follow the deploy.

## Production (2dc9b53), all ten showcase questions

Sonnet 5.5 judge over the wrapper, grouped, 3 repeats: every card meets all its criteria, and no
answer carries dotted coordinates in its prose. Case C cites `Article 5.1.f`, `Article 3.39` and
no longer drifts into Annex III or Article 26(7).

## R455b — follow-ups from the adversarial review of R455

A four-lens review (legal, scope, reference pipeline, channel consistency), each finding put to
two skeptics, confirmed three defects:

* **the R133 surface pass reads the parenthesised form**, which R455 made the model's default, so
  its unfiltered sibling add (kept out of the dotted form by R428 as net negative) reached more
  answers: rg_050 gained `Annex III.5.c`. `REGENOLD_SURFACE_SIBLING_GUARD` (default ON): when a
  parent already has a limb on the wire, a sibling is left to the R431 add and its calibrated
  recall floors. Replay of 176 recorded single-turn answers (parenthesised, Stage-2 scripted as
  landed, real route, real rubric): 4 rows changed, 0 gold-satisfying citations removed, removed
  `Annex III.5.c` x2 (rg_050) and `Article 6.3` x2 (rg_096); Ref Strict and Loose +0.00, Ref
  Conciseness 45.48 -> 45.69 (+0.22). The guard changes none of the seven Stage-2 showcase answers.
* **the curated emotion answers skip Stage-2**, so the new rules never reached them. The workplace
  entry now gives the Article 5(1)(f) verdict and its carve-out (Recital 44's example, therapeutic
  use; fatigue is not an emotion under Recital 18) and cites `Art. 5.1.f` instead of the bare
  parent and the other tiers. The general entry (rg_074's) keeps all three tiers, written
  `Annex III(1)(c)`. No official question selects the workplace entry.
* **rule 2's wording** said "the way the Regulation does"; the Regulation drafts "point (f) of
  Article 5(1)". It now says "the conventional legal citation form".

## R455c — a curated answer ships only the references it declares or states

Production smoke after R455b: the workplace emotion answer now states only Article 5(1)(f), but the
wire still carried `Annex III.1.c` and `Article 50.3`. Curated answers skip Stage-2, so the reconcile
pass that drops references the prose does not describe never runs on them, and the keyword anchors
for "emotion recognition" (upgraded by the sub-point emitter) rode along.
`REGENOLD_CURATED_PROSE_SCOPE` (default ON, cache-keyed), after parent collapse: keep a reference
whose head the curated answer declares or whose provision its prose names.

Offline route, all 110 official questions + the expert cases + the workplace question, flag off vs
on: 115 questions, 3 lists change, every answer byte-identical. Dropped: workplace `Annex III.1.c`,
`Article 50.3` (gold 5.1.f kept); rg_031 bare `Annex III` (gold 6.3.a kept); rg_027 `Article 50.1`
(no expected refs). No dropped reference shares a head with gold. Ref Strict and Loose +0.00, Ref
Conciseness 56.38 -> 57.18 (+0.80). No expert card changes.

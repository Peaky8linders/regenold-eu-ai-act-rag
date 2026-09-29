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
("always prohibited?"), rg_085 and rg_089 ("prohibit or high-risk?"). All three leave the context
open or ask about more than one tier, so the scoped rule still reaches them. rg_007 (a concrete
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

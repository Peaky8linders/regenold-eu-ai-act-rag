# R472 — the expert-review appendix of 26 October 2026

An update of the 23 October appendix (`docs/measurements/r467`, PR #504, not merged): the same
ten reviewed questions asked again on the build production serves now (`51a825ec6bb0`, R471
merged), a summary of the corrections made since (R468 to R471) and the rephrased-question
tables re-run. The document is generated, never edited by hand:

```bash
REGENOLD_LEGAL_TEXT_DIR="<main checkout>/tmp/legal-audit-2026-09-29" .venv/Scripts/python.exe docs/measurements/r472/build_appendix.py
```

The build refuses to write a document whose quoted evidence is not a verbatim substring of the
live answer, whose offline replay differs from the live answer, or whose measurement records no
longer read as the text says (`update_facts`). Output: `docs/reports/Appendix-Expert-Review-2026-10-26.{html,pdf}`
(the PDF is gitignored). The 23 October files are untouched.

## Runs (2026-10-26, production, one request at a time)

`run_live.py` (ten questions, 30 remediation rephrasings, 20 held-out rephrasings, offline
replays, held-out grades) and `run_policing.py` (three policing questions). The API key is read
from the main checkout's `.env` and never printed.

| set | result |
| --- | --- |
| ten reviewed questions | 9 answers identical to 23 October; Case D differs by "." to ":" in its lead (R468); all 10 reference lists identical; 32 of 32 points still quoted verbatim |
| 30 rephrasings | 21 statutory, 9 language model: the same 21 as on 23 October |
| 20 held-out rephrasings | 14 statutory (23 October: 5), 6 language model, 0 stored summary (23 October: 1); judge grades 20 of 20 correct |
| policing | `place_based` "No. Article 5(1)(d) only prohibits ...", `person_based` "not always prohibited ... high-risk under Annex III(6)(d)", `amend_place_tools` opens without the Article 5(1)(d) sentence |

* `place_based` was answered in 0.19 s: production's response cache held the answer from the
  post-deploy smoke on the same build.
* Six judge calls failed with wrapper errors (H96_a three times, HTTP 500; H6_b, H16_a and HD_b
  once each) and were re-run until every row had a grade. A failed call is recorded as a
  failure, never as a tie. Grades for four byte-identical answers (H96_b, H74_b, H95_a, H6_a) are kept
  from the 23 October run, as `heldout_judge.py` does.
* The held-out rows are not independent evidence for the third round: the seven failures of the
  23 October run were R469's development data. The independent figures in the appendix are
  R469's blind set 2 (3 to 6 of 34 targets, 0 of 14 controls), R468's samples and R470's
  policing set, each read from its own record.

## Hand check of the 26 October held-out answers

All 20 answers and citations were read against the family reference positions
(`scratch/r465_ab_corpus.json`).

* **H16_b** (fatigue monitoring, language model): the conclusion is right, but "provided
  safety is the system's intended purpose" makes the physical-state ground depend on purpose,
  which Recital 18 does not. Hand grade: partly correct (judge: correct). The 23 October
  answer had no such proviso; the first run's "unless ... the safety purpose is not genuine"
  was graded incorrect by hand on the same ground.
* **H6_b** (spam filter, language model): cites Article 26, which the answer does not use
  (23 October: Article 16).
* **H17_b** (procedure question): the Article 7 answer, which opens "Yes, but only within the
  limits Article 7 sets." The procedure that follows is complete. Recorded as an open item.
* The other 17 answers are sound. The Annex X answers for H104_a/H104_b no longer cite
  Annex III or Article 2 (23 October: both did).

## Independent fact-check of the changed sections

A separate agent re-derived every claim in the update block, section 2's closing paragraph and
table, the section 5 bullets and held-out table, and section 6 from the run files and the
Official Journal text. It confirmed the ten-answer comparison, the 70 % length figure, the 21/9
split, every held-out cell and the legal statements it checked (Article 7(1)(a), Article 112(2)(a),
Annex I points 11 and 12, Article 6(1), recital 42). It found, and the build now says instead:

* the third round was deployed on 25 and 26 October (R468 and R469 merged on the 25th);
* the 23 October Q10 answer was a stored summary naming nine of the 68 definitions, not a list
  of them;
* the Case D quote lost "Under that Regulation", so "Article 51(1)" read as an AI Act article;
* the 23 October clinical answer already stated the Article 6(1) device route; what is new is the
  full headings and the Annex I citation;
* the 23 October new-area answer opened "Yes, but only within the limits Article 7 sets.", not a
  bare "Yes";
* "removed from 4 of 6 questions that carried it" counted the gatekeeper's trigger, which was
  inert on those rows; only the development row N17_t2 changed a shipped answer;
* Annex III point 6(d) applies only to systems used by or for law-enforcement authorities, and
  Article 5(1)(d) has an exception, so the appendix no longer paraphrases the rule;
* the 10 judged R469 pairs are the 3 independent ones plus the first 7 of 18 pool questions in
  file order, and the judge was stopped; the 30 changed curated answers are 10 distinct texts;
* "graded correct" is the judge's grade (19 of 20 on hand check); the "Before" of the policing
  row is a flag-off run and N17_t2 is development data; the 34 independent rewordings were frozen
  after iteration 1 and before iteration 2, so "recorded before the final version";
* ND_t1 and "28 of 34" are offline routing results, not live.

## What the appendix leaves out on purpose

The per-question hand-check lists of the 23 October document (judge/hand grade differences and
citation misfits per run) are reduced to the bracketed grades and one count row. They are
reproduced by `HELDOUT_NOTES` in `build_appendix.py`, each asserted against the run files.

## Changed outside `r472`

`docs/measurements/r467/statute_phrase_check.py` takes `REGENOLD_LEGAL_TEXT_DIR`, because the
Official Journal text under `tmp/` is not tracked and a worktree has none.

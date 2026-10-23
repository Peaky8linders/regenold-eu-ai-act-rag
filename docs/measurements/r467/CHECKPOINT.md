# R467 — the October 2026 expert review, re-run live after PR #500

Measured 2026-10-23 against production. Deliverable:
`docs/reports/Appendix-Expert-Review-2026-10-23.{html,pdf}` (built by `build_appendix.py`).

## Deploy and transport

* PR #500 (freebuff WIP integration: docs, eval harness, tests; no application code)
  merged as `f9761689f47a`; Railway served it about 100 s after the merge.
* The Claude Max wrapper was down (nothing on `127.0.0.1:8000`); the `Cloudflared`
  service was already running. Wrapper restarted detached. On the new build a
  non-curated question ("What does Article 4 … require regarding AI literacy?")
  went through Stage-2 in 11.0 s with no warning; `/healthz/llm` read `llm_ok: true`,
  `claude-opus-5-5`, `primary_ok 1, fallback 0`; the wrapper log shows the calls
  arriving from Railway (`tunnel_smoke_postdeploy.json`).

## The ten review questions (`expert_review_rerun.py`)

* `expert_review_rerun_premerge.json` (build `59f0e28f482f`) and
  `expert_review_rerun.json` (build `f9761689f47a`): answers and references
  byte-identical across the two runs.
* `offline_wire_replay.py`: the same questions through the app with no model
  reachable return byte-identical answers and references on all ten. These answers
  are the R465 statutory verdicts; Stage-2 does not touch them.
* `statute_phrase_check.py`: 74 statutory passages the answers rely on, all found
  verbatim in the OJ text of Regulation (EU) 2024/1689 as adopted (and 2017/745).
* 32 review points (the review's numbered defects and precision points; for Q16
  and Case D the elements of its correct position): 30 open, 1 partly met, 1 met on
  29 September; all 32 stated in the 23 October answers, each with a verbatim quote
  checked by the build.

## Rephrasings (`paraphrase_rerun.py`)

30 rephrasings from the R465 A/B corpus (`scratch/r465_ab_corpus.json`), asked live:
20 answered by the statutory verdicts, 10 by Stage-2. Of the 20, 7 are identical to
the reviewed answer, 8 are the same verdict cut to three sentences, 5 use different
verdict text. Cause of the cut: `normalise_answer_for_regenold` keeps
`MAX_ANSWER_SENTENCES = 3` unless `_is_multi_phrase` / the enumeration ask / the
complexity check raises it, and curated verdicts are not exempt (the 23 October
deep review's finding I3). Also open: "When does a deployer become a provider under
Article 25(1)?" gets an Article 25(1) answer without the (a) and (c) conditions, and
the grain deepener cites `Annex III.7.b` on a Q17 rephrasing.

## Independent fact-check of the appendix

A separate reviewer checked the first draft against the review text, the 29
September report, the live JSON and the statute files: 1 error, 9 imprecisions,
3 nits, all corrected in the published version. The error: the Q104 answer's
"Article 5 prohibitions have applied since 2 February 2025" is a fifth statement
the Omnibus changes (Article 113, third paragraph, point (a), as amended: points
(ba), (bb), (1a), (1b) from 2 December 2026). Also corrected: two points resolved by
removing wording are labelled "removed", not "addressed"; the rephrasing set is
not out-of-sample (R465 widened detectors on some of it); the MDR text checked is
the consolidated version of 19.07.2026, not OJ text; the live answers' "instead
its provider" (Q74), "must" for Recital 83's "should" (Q10) and the Article 26(5)
citation (Q16) are disclosed in the card notes.

## R467b — the disclosed limitations, fixed

Held-out set first: `heldout_rephrasings.json` (20 questions, two per family) was
committed before any code change, and its pre-fix live run (`heldout_prefix.json`,
build `f9761689f47a`, 20 rows, 0 errors) was not read while the fixes were written.

What changed (pinned by `tests/test_r467_statutory_answer_gaps.py`, 41 tests,
written red first):

| limitation | fix |
| --- | --- |
| three-sentence cap cuts a statutory answer on a single-ask question | `REGENOLD_CURATED_FULL_TEXT` (default ON): a request-scoped switch gives the pinned verdicts the multi-part sentence ceiling (12), applied after the shape block so `_is_multi` and the char floor are computed as before |
| Article 25(1) answer without the (a)/(c) conditions | `reclassification_scope` states each limb's condition, the Article 16 subjection and the Article 25(2) carve-out; "Yes" only for a yes/no question, inside the cited sentence |
| deepener re-deepens a curated list (`Annex III.7.b`, `Article 26.5`/`26.7`, `Annex III.5.a`) | `REGENOLD_STATUTORY_REFS_PINNED` (default ON): a pinned verdict ships its declared list (parent-collapsed), recognised by the verdict name the engine stamps on seeded citations |
| "instead its provider" (Q74), "must" for Recital 83 (Q10), Article 3(3) without GPAI model, Q45 items (ii)/(iii)/(vi) abridged | wording corrected against the OJ text. Article 16 is still not named in the Q10 answer, deliberately: R447 took duty articles out of that definitional answer after it failed the citation criterion and the tone check, and `test_does_not_allocate_duties_on_a_definitional_question` pins it |
| art-project image question answered by Stage-2 with the deployer assumption | Q74 artistic cue covers "art project", "artwork", "artist"; the verdict names the medium (audio, images, video, content) |

Pinned set: the eight statutory verdicts (`STATUTORY_VERDICT_NAMES`) plus
`reclassification_scope` and `role_difference`. Their sentences all carry a
provision anchor, which is why the sentence ceiling is lifted for them only.

Two scope decisions came from measurement, not design:

* Lifting the ceiling for EVERY curated answer let rg_041's fourth sentence in,
  which tipped the answer over the 400-char soft cap; the cap then dropped the
  longest uncited sentence, the one saying the notified body must accept the SME
  form. Scoped to the pinned verdicts instead.
* Raising the char floor to 1500 for curated answers restored seven sentences other
  curated answers had shipped without, four of them closer to the official
  criteria (rg_005, rg_023, rg_032, rg_043) but also an uncited "Typical examples
  are AI-enabled spam filters ..." on the reviewed Q6 answer. Not done here; a
  separate change to measure.

Offline blast radius (`offline_dump.py`, official 110 + the 40-question corpus,
deterministic route): 20 answers and 11 reference lists change. On the official
110 exactly four rows change, none losing a citation: rg_024 (the areas verdict
ships whole, `Annex III.5.a` -> `Annex III`), rg_025 (Article 25(1) conditions,
refs unchanged), rg_046 (Q45 wording), rg_075 (Q74 wording). Every other change
is in the corpus families the fix targets.

Found on the way, not fixed here: the normaliser's meta-leak list holds
`graph does not` and matches it as a substring, so any sentence containing
"paragraph does not ..." is deleted as meta-commentary (it deleted the new
Article 25(2) sentence until it was reworded). rg_024 is routed to the healthcare
areas verdict although it asks about areas versus use cases (expected
`Article 6.2`).

`statute_phrase_check.py` now covers the new wording too: 87 passages, all found
verbatim.

## Legal version

The challenge grades the Act as adopted. Regulation (EU) 2026/1744 (OJ 24 July 2026,
in force 27 July 2026) moved the Annex III and Annex I high-risk dates (Article 113,
third paragraph, point (c)), added Article 111(4) and reworded Article 4. The appendix
states this in its section 3.

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

### Deployed and re-run

PR #501 merged as `0424e6268a43` at 14:19:19Z; Railway served it at 14:22:15Z
(`/healthz`); `/healthz/llm` read `llm_ok: true`, `claude-opus-5-5`, strict
transport. The branch's `app/` and `tests/` trees are identical to the merge, so the
offline replays below run the deployed code.

* **The ten review questions** (`expert_review_rerun_postfix.json`): every answer
  served without Stage-2, byte-identical to the offline replay
  (`offline_wire_replay_postfix.json`). Against the pre-fix run on `f9761689f47a`:
  Q45 (Article 13(3)(b) items in full, 2,312 → 2,539 chars), Q74 ("also its
  provider"), Q10 ("should"; general-purpose AI models) change text; Q16 changes
  citations only (`Annex III.4`, `Article 26.5` → `Annex III.4.b`, `Article 26`, the
  declared list). The other six are byte-identical.
* **Smoke** (`postfix_smoke.py` → `tunnel_smoke_postfix.json`): the Article 4
  question went through Stage-2 over the tunnel in 9.6 s (`primary_ok 1`,
  `fallback 0`); "Must I label AI-generated audio in my artistic work?" now ships
  the whole Q74 answer, with Article 50(5) and the application date.
* **The 30 remediation rephrasings** (`paraphrase_rerun_postfix.json`, live then
  offline): 21 answered by the statutory verdicts (was 20), 9 by Stage-2. Of the 21:
  15 identical to the reviewed answer, 4 the same verdict worded for the question
  (Q74_2 "images", Q16_1-3), 2 another statutory verdict (Q10_1 now
  `reclassification_scope` with all three Article 25(1) conditions and 25(2); Q10_3
  `market_service_use_contrast`), **0 shortened** (was 8). Q74_2 ("AI-generated
  images in an art project") moved from Stage-2, which had answered "The artist, as
  deployer, has no marking duty.", to the statutory verdict. No rephrasing cites
  `Annex III.7.b` (Q17_1 did).
* **The held-out set** (`heldout_postfix.json`, live then offline): the same 5 of 20
  reach a statutory verdict as before the round (H96_b, H17_a, H74_b, H95_a, H6_a); the
  other 15 are Stage-2 answers the round does not touch. Of the 5: H96_b now cites
  `Annex III` (was `Annex III.5.a`) and ships its fourth sentence; H74_b now says
  "video" (was "audio" for a short film) and keeps Article 50(5) and the date.
  H17_a still opens "Yes, but only within the limits Article 7 sets." on "Could the
  Commission add a brand-new area to Annex III through a delegated act?" (the Act's
  answer is no). **And H95_a exposed a defect in R467 itself** (R467c below).
* **Judge** (`heldout_judge.py`, `claude-sonnet-5` over the local wrapper, reference
  positions from the R465 corpus; wrapper 500s re-judged by the resume pass):
  before the round (`heldout_prefix_judged.json`) 11 correct / 5 partly / 4 incorrect;
  on `0424e6268a43` (`heldout_postfix_judged.json`) 10 / 5 / 5. The 15 Stage-2
  answers are fresh generations in each run, so their grades move with generation,
  not with the round. (The final hand check of the before and after runs, with the
  fact-check's corrections, is under R467c below.)

## R467c — the soft char cap still cut a pinned verdict

R467 lifted the sentence ceiling for the pinned verdicts but left the 400-char soft
cap on, on the premise that every pinned sentence carries a provision anchor (the cap
only drops uncited sentences). The Q95 verdict's two definition sentences ("An area is
one of those eight numbered headings." / "A use case is a specific intended use listed
within an area: ...") carry none, so H95_a ("In the AI Act's high-risk list, what is
the difference between an area and a use case?", a single ask) shipped sentences 1 and
4 only: the headings and the closing sentence, not the definitions the question asks
for. Only that verdict has unanchored sentences among the ten (checked with the
normaliser's own splitter).

Fix: the pinned verdicts skip the soft char cap and the default-OFF hard cap, under
the same `REGENOLD_CURATED_FULL_TEXT`. Tests written red first (a single-ask Q95
phrasing; a two-sided flag test). Offline blast radius: 0 of the 150 official +
corpus rows change; in the held-out set only H95_a changes. Because the held-out set
found this, H95_a is no longer out-of-sample with respect to R467c; the other 19 rows
are unaffected by it. Full suite 9,936 passed, 5 skipped; no new ruff findings.

PR #502 merged as `7ab8200c07f9` (14:50:53Z); Railway served it at 14:52:03Z.

### Build `7ab8200c07f9`, re-run (`*_r467c` files; the appendix's held-out run)

* **Ten review questions** (`expert_review_rerun_r467c.json`): byte-identical answers
  and references to the `0424e6268a43` run, and to the offline replay
  (`offline_wire_replay_r467c.json`, 10/10).
* **Smoke** (`tunnel_smoke_r467c.json`): the Article 4 answer is a fresh Stage-2
  generation (it differs from the offline draft and from the previous build's
  answer). `/healthz/llm`'s transport counters read 0 because they are per worker
  process and the health request reached another worker; on a multi-worker deploy
  read liveness from the answer, not the counters. The short Q74 phrasing ships whole.
* **30 rephrasings** (`paraphrase_rerun_r467c.json`): the 21 statutory answers are
  byte-identical to the previous build; 15 identical to the reviewed answer, 4 the
  same verdict worded for the question, 2 another fitting verdict, 0 shortened.
* **Held-out** (`heldout_r467c.json`, `heldout_r467c_judged.json`): H95_a now ships
  both definitions. Judge 14 correct / 1 partly / 5 incorrect (before the round:
  11 / 5 / 4). By route, judge [hand check]: statutory answers 3 / 2 / 0 [2 / 2 / 1]
  before, 5 / 0 / 0 [4 / 0 / 1] after (the 1 is H17_a's "Yes"); language-model answers
  (14) 8 / 3 / 3 [8 / 2 / 4] before, 9 / 1 / 4 [9 / 2 / 3] after; the stored Article 3
  summary (H10_a, 1) incorrect in both. H74_a (capacity assumed), H16_a (stress as
  emotion) and HD_a (device class assumed) are graded incorrect in both runs.
  Hand-check overrides of the judge: before H17_a (correct → incorrect), H16_b (partly
  → incorrect: "unless ... the safety purpose is not genuine"); after H17_a (correct →
  incorrect), H96_a (incorrect → correct: the Article 6(1) route is stated as a
  condition), H17_b (correct → partly: the judge's own omission, Article 97(6) early
  entry into force). Citations that do not fit the question: 6 before, 4 after (HD_a
  `Annex I.20` both runs; H104_a `Annex III` both runs; H104_b `Article 2` unused, both
  runs; H6_b `Article 53` → `Article 16`; before only, HD_b `Annex VIII` and H96_b
  `Annex III.5.a`, fixed by the pin).
* **Independent fact-check of the regenerated appendix** (a separate agent, reading
  the HTML against these files and the OJ text). All numbers reproduced. Findings
  acted on:
  - the statute check proves the 87 passages exist in the OJ, not that the answers
    quote them (23 appear word for word), so the text now says the answers quote
    some and paraphrase others;
  - Q45 introduced Article 13(3)(b)'s items with "namely" where the Act says
    "including" (an open list). Fixed in R467d below, and the card note no longer
    says "in the Act's wording";
  - H10_a is not a model answer but the stored Article 3 summary (`kb.py`
    "Defines 68 terms ..."), byte-identical in all three live runs; the table now
    has a stored-summary row;
  - citation misses the hand check had skipped: HD_b before the round cites
    `Annex VIII` (the AI Act's registration annex; the prose means MDR Annex VIII),
    and H104_b cites `Article 2` unused in both runs;
  - the H16_b (before) override to "correct" was wrong: the answer says fatigue
    monitoring is banned "unless ... the safety purpose is not genuine", but fatigue
    is outside Article 5(1)(f) whatever the purpose (Recital 18); the hand grade is
    now "incorrect";
  - the second-round paragraph claimed more than the change does: the sentence and
    citation rules cover the pinned verdicts (8 of the 10 families, not Q6 or Case D);
  - the judge's reference positions are our condensation of the review, and the
    statutory answers were drafted from them, so the appendix now says their grades
    are not independent of the reference;
  - plus wording: the Q10 note, Article 112(2)(a), the 70 % length figure (a ratio of
    totals; Case D got shorter), and the MDR consolidated-version date.
* **Found, not fixed** (reported in the appendix): the Q17 verdict opens "Yes" on a
  new-area question (H17_a); "How does the AI Act distinguish a provider from a
  deployer?" does not reach `role_difference` (H10_a); a Stage-2 list rendered as
  fragments ("The other required contents are. The provider's identity ...", H45_b);
  the language-model answers that miss the statutory verdicts repeat the review's
  Q74 / Q16 / Case D defects.

## Legal version

The challenge grades the Act as adopted. Regulation (EU) 2026/1744 (OJ 24 July 2026,
in force 27 July 2026) moved the Annex III and Annex I high-risk dates (Article 113,
third paragraph, point (c)), added Article 111(4) and reworded Article 4. The appendix
states this in its section 3.

## R467d — Q45 keeps Article 13(3)(b) an open list

Article 13(3)(b) introduces its items with "including:"; the Q45 verdict said
"namely", which closes the list. One word in `statutory_precision.py`, test written
red first (`test_q45_keeps_point_b_an_open_list`). Offline blast radius: 4 answers
change (rg_046 and the three Q45 corpus phrasings, +3 chars each), 0 reference
lists; no held-out answer changes (none of the 20 reaches the Q45 verdict, so the
held-out run on `7ab8200c07f9` stands for the final build). Full suite 9,937 passed,
5 skipped. PR #503.

The ten review questions and the 30 rephrasings are re-run on the final build
(`*_r467d.json`); the appendix is built from those plus the held-out run above.

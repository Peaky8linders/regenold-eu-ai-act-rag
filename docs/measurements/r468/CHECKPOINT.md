# R468 — answer-shaping defects in the normaliser

Three defects in `normalise_answer_for_regenold` (`app/integrations/regenold/models.py`),
each found in recorded answers. Pinned by `tests/test_r468_normaliser_shaping.py`
(written red first).

## The defects

1. **A colon-introduced list was flattened into fragments.** `_strip_markdown` makes
   every line a sentence and turns a line-final colon into a period, so a Stage-2
   answer that introduced bullets with "The other required contents are:" shipped
   "The other required contents are. The provider's identity and contact details. ..."
   (R467c held-out run, row H45_b). In 6,160 distinct recorded answers under `docs/`
   and `evals/`, a regex for the shape matches 29; 23 are this defect ("The eight areas
   are. Biometrics.", "These include. A risk management system (Article 9).") and 6 are
   ordinary sentences ending in "requires".
2. **"paragraph does not" was read as meta-commentary.** The meta-leak list holds
   "graph does not", "graph provides" and "graph contains", matched as substrings, so
   every sentence with "paragraph" or "subparagraph" before those verbs was deleted.
   R467 found it when it deleted the new Article 25(2) sentence.
3. **The soft char cap dropped uncited sentences of curated answers.** The cap drops the
   longest sentence without an `art.` / `article ` / `annex` token until the answer
   fits. R447's rule for curated drafts is that every sentence carries a provision
   anchor; 15 drafts broke it. On official questions the cap had deleted verdict leads
   ("Not automatically.") and statutory clauses (rg_005, rg_023, rg_032, rg_043, and the
   reviewed Case D answer's single-ask phrasing).

## The fixes

| defect | fix | switch |
| --- | --- | --- |
| 1 | a prose intro (not a heading, a list item or a structural label; at least two words, so "These include:" qualifies) followed directly by single-clause list items becomes one sentence, "intro: item; item; item."; an item's first word is lower-cased unless it is a provision or institution word | `REGENOLD_LIST_INLINE` (default ON) |
| 2 | meta-leak phrases match at a word start only, so "knowledge graphs" still matches and "paragraph" does not | `REGENOLD_META_LEAK_WORD_START` (default ON) |
| 3 | every sentence of the 15 drafts now carries a provision anchor, checked verbatim against the OJ text; the uncited "Typical examples are AI-enabled spam filters, inventory-management tools, and AI in video games." is removed from the minimal-risk answer (no provision names those examples) | none; a registry test over all 33 curated detectors |

Both switches are deny-list and registered in `_engine_cache_key`. The two-word floor
for defect 1 came from the recorded cases: five of the 23 open with "These include:",
"This covers:" or "These are:".

## Measurement (paired A/B on samples; the official 110 excluded)

The operator directive of 2026-10-25, recorded in `AGENTS.md`: paired A/B tests on
seeded samples, never the full official 110. Harness: `ab_normaliser.py` (seed 468).
Judge: the position-swapped pairwise judge (`evals.harness.ab_judge`), `claude-sonnet-5`
over the local wrapper, on correctness, conciseness and tone; a decisive verdict needs
both orderings to agree. Two-sided sign test on decisive pairs.

**Curated answers (fix 3).** 182 non-official questions that a curated intercept answers
(probe corpus, R465 corpus rephrasings, test-file questions), answered offline by an
`origin/main` worktree (A) and this branch (B). 30 answers differ, 0 reference lists.

**Stage-2 answers (fixes 1 and 2).** 120 list-asking questions sampled from a pool of 519
(same pools, curated answers excluded), each asked once with live Stage-2
(`claude-opus-5-5` over the wrapper); the text entering the normaliser is put through
both arms, so generation variance cannot enter. 111 captured (9 answered without a
normaliser call), 11 discordant, all list inlining; no meta-leak case in the sample.
The capture ran before the two-word floor was added; `rearm` re-normalised the saved
text with the final code (arm A reproduced on all 111 rows; arm B unchanged).

### Results

B is this branch, A is `origin/main`; p is the two-sided sign test on decisive pairs.

| sample | answers differing | judged | correctness (B–A–tie) | conciseness | tone |
| --- | ---: | ---: | --- | --- | --- |
| curated answers, n = 182 | 30 | 30 | **18–0–12**, p = 7.6e-6 | **1–12–17**, p = 0.0034 | 7–2–21, p = 0.18 |
| Stage-2 answers, n = 111 | 11 | 9 | 0–0–9 | 0–0–9 | **6–0–3**, p = 0.031 |

* **Curated answers: a correctness gain paid for in length.** B is longer on 22 of the 30
  differing answers (mean 523 → 589 characters) and shorter on none. All 18 correctness
  wins and all 12 conciseness losses are answers where B is longer (by 97 characters on
  average for the losses); nine answers win on correctness and lose on conciseness. Three
  lose on conciseness with correctness tied: B restores a verdict lead ("Not
  automatically:", "Yes, where the surgical robot itself is required to undergo a
  third-party conformity assessment:"), the Article 6(1) application date, or words the
  Article 50(4) clause in the Act's terms. The pairwise judge has no reference answer, so
  its conciseness axis reads length; the official axis grades unasked content against a
  reference answer (CLAUDE.md § R380). This sample does not measure how the official
  grader reads the restored sentences.
* **Stage-2 answers: tone only.** Inlining a list changes no content, and the judge
  agreed: correctness and conciseness tied on all nine judged pairs, and tone went to B
  six times and to A never. Two pairs failed on every attempt and are excluded: "What
  requirements are defined in Article 9 for high-risk systems?" and "Which EU AI Act
  article governs the reporting of serious incidents involving a high-risk AI system?".
* **Decision.** The operator shipped the change with the conciseness cost (2026-10-25).

⚠ **The first judge run was void.** It printed 41 ties of 41 with no call made: the
pairwise judge dials the wrapper through the Stage-2 provider, which is off unless the
wrapper environment is set, and `ab_judge` scores a failed call as a tie. The harness
now sets that environment, retries a failed call twice, and records a pair whose calls
still fail as a failure, excluded and listed, never as a tie.

## Not done here

* Curated drafts with more than three sentences are still cut by the sentence ceiling
  on single-ask phrasings: `gpai_transparency` (4), `systemic_risk_scope` (5),
  `hospital_deployer` (5). R467's pinned-verdict ceiling is the mechanism; extending
  it needs its own A/B.
* The reviewed Case D answer's lead now reads "...: under Article 6(1) ..." (one
  sentence, anchored) where it read "... . Under Article 6(1) ...". The October appendix
  (PR #504) documents build `cb2c751` from stored JSON, so it does not change.

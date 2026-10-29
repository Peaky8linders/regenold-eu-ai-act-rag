# R473 — the concise expert-review appendix of 29 October 2026

A short re-issue of the 23 and 26 October appendices (`docs/measurements/r467`, `r472`, both
untouched). Same ten reviewed questions, asked again on the build production serves today; the
review's points, the answer now, and where the answer states each point. Everything about how
the system produces its answers is left out on purpose. The document is generated, never
edited by hand:

```bash
<main checkout>/.venv/Scripts/python.exe docs/measurements/r473/run_live.py        # ten live asks + offline replay
<main checkout>/.venv/Scripts/python.exe docs/measurements/r473/build_appendix.py  # HTML, then PDF (headless Chrome)
```

Output: `docs/reports/Appendix-Expert-Review-2026-10-29.{html,pdf}` (the PDF is gitignored).
7 pages and 6,551 words (footers included), against 16 pages / 10,407 words (26 Oct) and
15 / 9,557 (23 Oct).

The build needs two untracked inputs, both found in the main checkout (or set
`REGENOLD_EXPERT_REVIEW_FILE`, `REGENOLD_LEGAL_TEXT_DIR`): the expert's review
(`Antifragile AI Oct 2026 expert review.txt`, gitignored by `*.txt`) and the Official Journal
texts (`tmp/legal-audit-2026-09-29`). It reuses `r472/build_appendix.py` as a library, so the
measurement records of R468 to R471 are still asserted when it runs.

## Run (2026-10-29, production, one request at a time)

* Deployment `beb7aeb97622` (PR #504, docs only; the code is the 26 October build
  `51a825ec6bb0`). `llm_ok` true, `claude-opus-5-5`.
* The ten reviewed questions: all ten answers and all ten reference lists identical to
  26 October; nine identical to 23 October (Case D differs by one punctuation mark in its lead).
* Offline replay (no model reachable): 10 of 10 answers and reference lists identical to live.
* The held-out, rephrasing and policing figures are the 26 October records (the code has not
  changed since); this round did not re-run them or the judge.

## Operator edits to the page (2026-10-29)

Asked for concision, the operator had these removed from page 1: the subtitle line ("Follow-up
to the report update ... replaces the issues of 23 and 26 October"), the four summary tiles
(10 answers; 6 wrong in part / 2 borderline / 4 correct; 32 points; 32 of 32 addressed), the
paragraph on length and references (answers 70 % longer, 1,358 against 798 characters; all
expected references cited 6 of 6, the exact set 3 of 6, was 2 of 6), and the paragraph saying a
point is addressed where the answer states it and that this is our assessment. The page keeps
the caveat in three smaller places: the findings table's column "Addressed (our assessment)",
the "✓ = our assessment" line in every card's left panel, and the reading guide under the table.
The removed figures are still computed and true; they are simply not on the page.

Still on the page and worth a second look if the issues of 23 and 26 October were never sent:
"Other corrections since 23 October" and "identical to those of 26 October / 23 October".

## What the deep dive found, and what this issue does about it

1. **The legal-basis section was incomplete.** Regulation (EU) 2026/1744 redefines "safety
   component" (Article 3(14)) and inserts Article 6(1a) to (1c). Case D's conclusion and the
   review's own corrected Case D answer rest on Article 3(14), and Case A states Article 6(1);
   neither the 23 nor the 26 October table mentioned it. Added as a row, which also covers Q95
   (it recites Annex III point 2's safety components). New Article 2(13), which lets the
   Article 9 to 15 and 17 to 25 requirements be limited for Article 6(1) systems, is a sentence
   under the table. Source: operative items (3), (4) and (8) of `ai-amendment.txt`.
2. **The "not amended" list is now checked, not asserted by hand.** `omnibus_facts` splits the
   43 operative items of Article 1 of the amending act and asserts each claim (110 in all):
   Articles 7, 13, 26 and Annexes III and X are never named; Article 2 changes paragraphs 2, 7
   and 13 only; Article 3 points (14), (14a), (14b) only; Article 25 paragraphs 2 and 4;
   Article 50 paragraph 7; Article 111 paragraphs 2 and 4; Article 97(6) is replaced but its
   objection period and extension are word for word the same; Article 5(1)(f) is identical in
   the adopted and consolidated texts; Regulation (EU) 2017/745 is still point 11 of Annex I
   Section A (Section A point 1 was deleted, with no renumbering). The list gained Articles 2(10),
   3(3), (4), (11), (60) and 5(1)(f), which Q74, Q10 and Case C cite.
3. **Q96, point 5(a).** The answer's closing words are condensed ("to grant, reduce, revoke or
   reclaim them" for the Act's "as well as to grant, reduce, revoke, or reclaim such benefits
   and services"). All three things the review flagged are fixed, but "addressed" is by
   substance, not verbatim; the card says so, in the status line too. Areas 1, 6 and 7 carry the
   Annex III qualifier "in so far as their use is permitted under relevant Union or national
   law", which the review's own list omits; the card says that too. Both asserted.
4. **Q74.** The review's question-level remark (three facts the question leaves open, and "not
   defective") was not reflected; added as a note, with the answer asserted to state each as a
   condition. The point-3 tick used to claim the whole of the review's provider-branch remark;
   the answer states only that a self-developer "bears that marking duty", not that artistic
   purpose is no exception or that the branch is unlikely. The tick now says so.
5. **"Resolved 32 of 32" read as the reviewer's verdict.** Now "addressed (our assessment)",
   see above. The 32 is a count of our own decomposition of the review (for Cases C and D, of
   the four elements of a correct position); the reading guide says so.
6. **Q10.** The one real difference from the review's corrected answer stays ("under
   Article 16"). The 26 October note justified it with "an earlier version ... failed the
   citation and tone criteria of an expert re-check", which has no source a reader can open;
   dropped from the external text.
7. **Predictive policing.** The 26 October table read "the Article 5(1)(d) rule fired wrongly on
   6 of 12". That is the gatekeeper's keyword match (R470), not a shipped answer, and R472's
   fact-check had already caught the same slip once. The bullet is not in this issue: it is
   unrelated to the review, is the most internal of the four corrections, and the reviewer
   found its recital 42 claim goes beyond the recital ("risk analytics not based on profiling
   of individuals"; place-based forecasting is our inference). The R470/R471 records stand.
8. **Every quotation attributed to the review** (22) is asserted to be word for word in the
   review document or in the 29 September answer it describes; every quotation in a card note is
   asserted to be in the review, the 29 September answer, today's answer or the Act. The ten
   verdicts are asserted against the review's own "September 29, answer:" lines.
9. **Review remarks that mitigate, now carried:** Q6 "the main clause ... covers both routes",
   Q74 "the question itself is not defective", Case D "the question supplies the safety
   component characterisation (Art. 3(14))". Case C and D's four elements are labelled as our
   reading of a correct position, and Met / Partly met / Defect as our assessment.

## What the document leaves out on purpose

The 29 September answers (they are in the 29 September report), the deployment id, how an
answer is routed, the judge model and its set-up, the 30 remediation rephrasings, the live
before-and-after table of reworded questions, the per-row hand-check findings (reproduced by
`HELDOUT_NOTES` in r472), the sample sizes of the formatting test, the predictive-policing
correction, and response times. `INTERNALS` in the builder fails the build if a page names any
of them.

## Independent fact-check of the finished text

Two separate agents, given the HTML, the review, the live JSON and the Official Journal texts,
and none of the conclusions above, were asked for errors, overstatements and omissions. Neither
found an ERROR-level defect. Both ran on the page as built at 09:49; the fixes below came after.

**Fidelity and numbers (15 findings).** Every verdict, quotation, figure, "Cites" line and
"Official appendix expects" line reproduced; the legal table was consistent with the amending
text. Fixed: the Q16 "allowed only on conditions" gap (a note and a limitation); the Q74
provider-route tick; the ticks reading as the expert's (header, cards, table column); the case
D remark on Article 3(14); the Q6 and Q74 mitigating remarks; the "statutory precision rather
than the choice of provision" framing (several points are about missing routes); "the ten
reviewed answers did not need to change" (now "have not changed since 23 October"); the AI
rater unnamed in "graded more correct" (now "a separate AI reviewer", with "10 distinct
texts"); "cannot be paraphrased away" without the caveat that unfamiliar rewordings reach the
model; the Q45 item (f) omission of "a description of"; the Q74 deep-fake definition still
omitting "image, audio or video"; the Q17 Article 7(3) sentence being a paraphrase; the Q96
tick without the "closing words condensed" qualifier; the fatigue answer's hand grade
(partly correct) not stated; the ordinary "of which 2 borderline", "the six official cases",
card pills without "29 Sep", and the over-citation in Q45 and Q17 as well as Q74.
Not fixed, by decision: "replaces the issues of 23 and 26 October" and "since 23 October"
assume the reader has them (the operator removed the first; the second is flagged above).

**Legal basis (12 findings).** The six rows, the dates and the "not amended" list all matched
the amending and consolidated texts, article by article. Fixed: Q95 and Annex III point 2
under the safety-component row; new Article 2(13); row wording nearer the text (Article 3(14)'s
new limb, 6(1c)'s "solely due to risks other than risks to health and safety", Article 111(4)'s
"take the necessary steps ... generating synthetic audio, image, video or text content",
Article 4's "guarantee any specific level of AI literacy of any individual", Article 5(1a) and
(1b) as delimiting points (ba) and (bb)); "the procedure that follows is complete" (now
"accurate, though it does not spell out the notification step (Article 97(5))"); the recital 42
overreach (bullet removed).
Not fixed, because the answers mirror the review's own corrected wording and the document does
not set itself up as a second reviewer: Q74's Article 2(10) clause reads "the obligations of a
natural person using an AI system" where the Act says "obligations of deployers who are natural
persons" (the review's corrected answer uses the same paraphrase); Q96 point 5(d) names only
"emergency healthcare patient triage systems" of its three limbs (so does the review); Q6's
"or an Annex III use case" omits the Article 6(3) derogation; Q74 "accessible" for "conform to
the applicable accessibility requirements"; Case D "class follows its intended purpose" for
Article 51(1)'s full wording.

## Answer-text gaps the check surfaced, not fixed here (a change to the answers themselves)

* Q16: say that on the stress branch the use is "allowed only on conditions" (the review's
  words); the answer gives the Annex III route and Article 26 but never answers "allowed?".
* Q45 item (f): add "a description of".
* Q74: add that artistic purpose is no exception to the provider's Article 50(2) duty and that
  the provider branch is unlikely on these facts; tighten the Article 2(10) clause to
  "obligations of deployers who are natural persons".
* Q17 (and the procedure rewording): optionally name the Article 97(5) notification.

## What this does not establish

* The expert has not re-reviewed the new answers; "addressed" is ours.
* The multi-turn (hard) mode was not re-run.
* Reworded questions that miss the prepared answers reach the model; the 20 follow-up
  rewordings informed later fixes and are not independent evidence (said in the document).

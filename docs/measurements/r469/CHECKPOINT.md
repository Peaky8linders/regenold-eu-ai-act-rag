# R469 — rephrasings that missed a vetted answer and got the review's defects back

The R467 held-out run asked two rephrasings per review family. Seven missed the
detector of their family's vetted (curated, Stage-2-free) answer, so Stage-2
answered them and repeated what the October 2026 review criticised:

| row | what Stage-2 got wrong | why the detector missed |
| --- | --- | --- |
| H74_a (musician, backing vocals, album) | assumed a deployer and an "evidently artistic" album; liner notes as the disclosure | the artistic cue knew "artist", not "musician" or "album" |
| H16_a (webcams, call-centre staff "frustrated or stressed") | called stress an emotion | "stressed" is not "stress"; "frustrated" is not "emotion"; "Can an employer use ..." is no legality word |
| HD_a ("Would an AI module that controls a surgical robot's movements be ...") | asserted a device class; cited `Annex I.20` | no "would ... be" shape in the verdict-ask gate |
| H45_a ("what do I have to put in the instructions for use") | dropped the Article 13(3) qualifiers, abridged Article 13(2) | only list / categories / "what information" counted |
| H96_a ("Which sectors does Annex III cover ... a clinical decision-support AI") | abridged the area headings | "areas" and "health" only |
| H10_a ("How does the AI Act distinguish a provider from a deployer?") | the stored 68-term Article 3 summary | "distinguish" was not a contrast marker |
| H17_a ("Could the Commission add a brand-new area to Annex III ...?") | the vetted answer itself opened "Yes" | new-area asks shared the use-case answer |

## What changed

`REGENOLD_STATUTORY_REPHRASINGS` (default ON, deny-list, in `_engine_cache_key`; `=0`
restores main exactly, which the tests pin two-sided) widens the detectors in
`app/engines/statutory_precision.py` and three intercepts in `_graph_rag_impl.py`, in
two iterations:

* **Iteration 1** (from the seven rows): music and other creative works (Q74);
  "stressed", feeling words beside a verb of inference, "can an employer use" (Q16); a
  "would ... be high-risk" ask and other names for a surgical robot (Case D); the
  Article 13 content ask (Q45); sector words and clinical settings on an areas ask
  (Q96); "distinguish" (Q10, not with a third role); the high-risk list named without
  "Annex III" (Q17).
* **Iteration 2** (from held-out set 1, below): the instructions under other names
  ("user guide", "such instructions") and the compulsory-or-conditional ask; workplace
  named by its setting (HR, appraisals, bonus, "at work") with a check that the feelings
  are the workers' and not customers' or patients'; robotic procedures other than
  "surgery" and four more verdict-ask shapes; voice work (voiceover, audiobook,
  narration), "tag", "detectable", "AI-cloned"; "developer versus user" and "are we the
  provider or the deployer?"; "could we end up as its provider?" (Article 25(1)); the
  annex named by its content ("the AI Act's high-risk annex"); Annex X named by its
  systems; Q95's contrast and structure asks; Q6's "isn't high-risk ... rules left".

Two answers changed with the routing: a new-area ask now gets **"No"** (Article 7(1)(a)
confines a delegated act to the listed areas; Article 112(2)(a) has the Commission
evaluate new area headings; verbatim-checked against the OJ text), and a clinical areas
question gets the Article 6(1) medical-device route (Annex I, Section A, points 11 and
12). A full-headings ask with no healthcare angle gets the headings without the
healthcare paragraph. A Q74-shaped question with no AI Act anchor now passes the scope
gate the way the Q16 shape already did (`is_generated_content_marking_ask`).

Guards found by measurement, not design:

* The passive "what must be included in the instructions for use" stays on Stage-2: it
  is a davidath QA row, and these detectors fire on 0 davidath rows.
* "Does the Act distinguish providers and deployers and importers?" (pool control) asks
  about three roles; the new markers do not count with a third role named.
* Seven "Is emotion recognition in the workplace always prohibited?" questions already
  had a curated answer, R144's cross-tier verdict ("not always"); the wide cues moved
  them to the workplace verdict, which would lead "Yes". The wide cues now never take a
  question another curated verdict answers.
* ND_t1 ("We're a Munich start-up ...") stays a recorded miss: the scenario opener keeps
  it with the scenario classifier, and lifting that guard for the robotic-surgery verdict
  would fire on a davidath scenario row.

## Measurement

The operator directive of 2026-10-25 (`AGENTS.md`): paired A/B on samples, never the
full official 110. Harness: `ab_statutory.py`. Sets:

* **Held-out set 1** (`heldout_rephrasings.json`, 48 rows: 34 targets, 14 near-miss
  controls), written by a separate agent told not to open `app/` and to keep the
  questions out of its report, committed before any R469 code (`7e15d8e`). It measured
  iteration 1, was then read, and is development data for iteration 2.
* **Held-out set 2** (`heldout_rephrasings_2.json`, same design), written blind after
  iteration 1 and committed before any iteration-2 code (`acb22e8`). It measures
  iteration 2.
* **Development:** the R467 held-out set (20 rows), where the seven failures came from.
* **Pool control:** every non-official question in the probe corpus, the R465 corpus and
  the test files (1,584), labelled with its curated route on `origin/main` and on the
  branch.

### Routing (offline)

How many target rephrasings reach their family's vetted answer, and how many near-miss
controls do (`routing`):

| set | main | iteration 1 | iteration 2 |
| --- | --- | --- | --- |
| held-out set 1: 34 targets, 14 controls (iteration 1's test, then read) | 3/34; 0/14 | 4/34; 0/14 | 32/34; 0/14 |
| **held-out set 2: 34 targets, 14 controls (blind for iteration 2)** | 3/34; 0/14 | | **6/34; 0/14** |
| development: the R467 held-out set, 20 targets | 5/20 | 12/20 | 14/20 |

**The cues are precise, and they do not generalise.** No control in either blind set
reaches the family's answer, and no target reaches another family's. But iteration 1 lifted
held-out set 1 from 3 to 4 targets, and iteration 2, built from set 1's misses, lifts the
blind set 2 from 3 to 6: 28 of its 34 targets still reach Stage-2. Each round of cue
widening fits the rephrasings it was shown.

**Pool control.** Of the 1,584 pool questions, iteration 1 moves 11 and iteration 2 moves
19, every one from no curated answer to its own family's verdict: 8 to the workplace
emotion verdict ("Can we use emotion recognition on our employees in the office?"), 6 to
the role difference ("We built an internal AI for our own HR use, provider or
deployer?"), 4 to the instructions-for-use verdict ("What must the instructions for use
contain?"), and 1 to the Annex III amendment ("Is the Commission empowered to update the
high-risk list?"). The A/B below judges all 19.

### Paired A/B (stopped after 10 of 61 pairs)

**A** is production as deployed (`16b8585`, `main` with R468), one single-turn request per
question. **B** is this branch merged with `main`: for a question it answers with a curated
verdict, its offline answer, which is what production would serve, because a curated
verdict skips Stage-2. A question whose path the change does not touch is a tie by
construction and is not asked. 62 rows differ (held-out set 1 30, held-out set 2 3,
development 10, pool 19), and production answered all 62 on `16b8585` with no errors. One
pool question, "Is the Commission empowered to update the high-risk list?", is skipped: the
offline scope gate refuses it, so B cannot be built offline. The judges are the
position-swapped pairwise judge (correctness, conciseness, tone) and, for target rows, the
R467 absolute grade against `reference_positions.json`; both are `claude-sonnet-5` over
the wrapper.

The operator stopped the judge after 10 of the 61 pairs (2026-10-25). It had judged all 3
of held-out set 2 and the first 7 of the pool's 18 in file order, not a sample: 3
role-difference and 4 workplace-emotion questions. No call failed.

| judged pairs | correctness (B–A–tie) | conciseness | tone |
| --- | --- | --- | --- |
| held-out set 2 (blind), 3 | 3–0–0 | 0–2–1 | 1–1–1 |
| pool control, 7 of 18 | 5–0–2 | 0–3–4 | 2–1–4 |
| **all, 10** | **8–0–2**, p = 0.0078 | 0–5–5, p = 0.063 | 3–2–5, p = 1.0 |

* **Correctness: the vetted answer wins every decided pair.** On the blind set the absolute
  grade agrees. Main's answers grade correct, partly, correct, and the branch's grade
  correct all three times. The "partly" is M96_t1: production's Stage-2 answer abridged
  the area headings and left out Annex III point 5(a) (public assistance benefits and
  services, including healthcare services), which is the defect the review named.
* **Conciseness: the same trade as R468.** The curated verdicts average 1,427 characters
  against 735 for the Stage-2 answers they replace, and all five decisive conciseness
  verdicts go to the shorter answer. That is not significant at this n.
* **Not measured:** 51 pairs, including 11 pool questions (4 instructions-for-use, 4
  workplace-emotion, 3 role-difference), all of held-out set 1 (development data for
  iteration 2) and the development set.
* **Decision.** The operator shipped the change as is (2026-10-25).

## What this does not fix

* **Most blind rephrasings still miss.** 28 of the 34 blind targets reach Stage-2, which
  can repeat the review's defects. Widening cues has run its course: each round fits the
  phrasings it was shown. Two directions, neither built here. One is a semantic matcher
  that compares a question with each family's vetted questions, using the near-miss
  controls as negatives so that precision is measured, not assumed. The other is lever
  (b): give Stage-2 the family's vetted position on the user channel when a question is
  near a family. That is prompt-side, so it needs the live gate (`AGENTS.md` invariant #5).
* **ND_t1** ("We're a Munich start-up building an AI that steers the needle during
  robot-assisted biopsies. ...") stays a recorded miss: the scenario opener keeps it with
  the scenario classifier, and lifting that guard for the robotic-surgery verdict fires on
  a davidath scenario row.
* **The Article 5(1)(d) sentence on place-based predictive policing.** N17_t2 asks about
  tools "forecasting where crime will happen rather than who will commit it". On the
  branch its amendment verdict is prefixed with "Risk assessment of natural persons based
  solely on profiling or personality traits is prohibited under Article 5(1)(d)."; on
  main the engine's own draft opens with the same point. Article 5(1)(d) concerns risk
  assessments of natural persons, which the question excludes. The prefix comes from the
  route's prohibition gatekeeper and predates R469.
* **The passive "what must be included in the instructions for use"** stays on Stage-2:
  it is a davidath QA row, and these detectors fire on no davidath row.

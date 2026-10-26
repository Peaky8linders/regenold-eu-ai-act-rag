# R470 — Article 5(1)(d) is not asserted on place-based crime forecasting

## The defect

R469's held-out row N17_t2 asks about "place-based predictive policing tools (forecasting
where crime will happen rather than who will commit it)". It shipped the Article 7
amendment verdict behind "Risk assessment of natural persons based solely on profiling or
personality traits is prohibited under Article 5(1)(d)."

The prohibition gatekeeper (`app/engines/prohibited_gatekeeper.py`) matches the keywords
"predictive policing", "criminal risk" and "predicting criminality" whatever the tool
assesses. Article 5(1)(d) concerns risk assessments of natural persons, and recital 42
says the prohibition "does not refer to or touch upon risk analytics that are not based on
the profiling of individuals". A match has three effects:

* the Article 5(1)(d) sentence is prepended when the answer does not name Article 5;
* `Article 5` and `Article 5.1.d` are forced onto the wire (a pinned statutory verdict
  keeps its declared list);
* the R376 guard deletes any sentence saying Article 5 does not apply, so a Stage-2 answer
  that correctly says place-based forecasting is not prohibited loses that sentence to the
  verdict (`test_a_correct_denial_survives_on_a_place_based_question`).

A question that names "predictive policing" and asks whether it is prohibited takes the
engine's `predictive_policing` classification topic instead. The route ships that curated
text without the prepend or the strip, so there a match only forces the citations.

## The fix

`REGENOLD_PLACE_BASED_POLICING` (default ON, deny-list, in `_engine_cache_key`; `=0`
restores `main`, and the tests pin both directions). A place cue removes the `Art. 5.1.d`
match: "place-based", "location-based", hotspots, crime maps, "where crime will happen",
"each district", "which neighbourhoods", "rather than who". The removal does not apply when
the question also assesses people: profiling, personality traits, personal data, scoring,
ranking or flagging people, "likely offenders". A person cue does not count when it is
negated within two words ("without profiling any individual"). This is the shape R376
gave `Art. 5.1.h` for post-remote biometric identification, and it only narrows.

## Measurement

The operator directive of 2026-10-25 (`AGENTS.md`): paired A/B on samples, never the
official 110. Harness: `ab_policing.py`.

**Blind held-out set** (`heldout_policing.json`): 12 place-based targets and 12
person-based controls. A separate agent that opened no code wrote it, and it was committed
(`28879da`) before the fix. Offline, how often the gatekeeper matches Article 5(1)(d):

| | main | this branch |
| --- | --- | --- |
| targets: the match is wrong | 6 of 12 | **2 of 12** |
| controls: the match is right | 6 of 12 | **6 of 12** |

The other 6 targets and 6 controls contain none of the gatekeeper's keywords, so it never
fires on them in either arm. The fix removes 4 of the 6 wrong matches and none of the 6
right ones. The two misses describe the place in words the cues do not know: T05 divides a
city "into 250-metre grid cells" and estimates crime "in each cell", and T07 "flags the
twenty street segments most at risk of knife crime". They are recorded, not fixed, so that
the set stays a blind measure of this code.

Five controls mention a place, and the person cues recognise four of them. The fifth, C03,
"ranks everyone registered as living on a particular street by how likely they are to
commit an offence": no person cue knows "everyone" or "how likely they are to commit". It
names none of the gatekeeper's keywords, so neither arm matches it. Had it said
"predictive policing", the fix would have removed a correct match.

**Paired A/B on the wire.** A is `REGENOLD_PLACE_BASED_POLICING=0`, B the default. Both
run through the real route in one process with live Stage-2 (`claude-opus-5-5` over the
local wrapper). The gatekeeper runs after Stage-2, so the Stage-2 completion is memoised:
B made no provider call of its own on any row (7 calls, 6 memo hits), and only the
gatekeeper's output can differ. Only the five rows whose scan changes are asked: the four
blind targets above and N17_t2. Every other row is a tie by construction. Correctness was
judged with the position-swapped pairwise judge (`claude-sonnet-5`); no call failed.

| row | wire answer and references | correctness |
| --- | --- | --- |
| T01, T03, T09, T11 (blind) | identical in both arms | tie by construction |
| N17_t2 (development) | B drops the Article 5(1)(d) sentence, 1,442 → 1,322 characters | **B**, both orders agree |

**On this sample the fix changes one shipped answer.** On the four blind rows the wrong
match was inert. Each Stage-2 answer already explains that Article 5(1)(d) concerns
natural persons and names Article 5, so the prefix is not added. None used a wording the
R376 guard deletes: T09's "is currently not prohibited" escapes the `is not prohibited`
pattern by one word. The reference lists also came out identical in both arms, so the
forced citations added nothing beyond the answers' own text. The row that changes is the curated
verdict, which never names Article 5 and so always got the prefix. One pair cannot reach
significance. The mechanism is pinned by the tests, including the R376 deletion of a
correct denial (`test_a_correct_denial_survives_on_a_place_based_question`).

## Not fixed here

* **The `predictive_policing` topic text.** It says "Place-based or non-profiling
  predictive policing remains permitted, but is high-risk under Annex III and subject to
  Chapter III Section 2 obligations." Annex III point 6 lists law-enforcement systems that
  assess natural persons (points (a), (d) and (e)), polygraphs (b) and the reliability of
  evidence (c). None describes forecasting where or when crime will occur, so the
  place-based half of that sentence has no basis in the annex. The text ships on every
  question that names predictive policing and asks whether it is prohibited.
* **T05 and T07** (above): areas named as "grid cells" or "street segments".
* **The person cues miss C03's phrasing** (above), a latent false exclusion if such a
  question also names predictive policing.

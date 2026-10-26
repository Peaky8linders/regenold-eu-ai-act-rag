# R471 — the predictive-policing topic no longer calls place-based policing high-risk

## The defect

The `predictive_policing` classification topic (`app/engines/_graph_rag_data.py`)
ended: "Place-based or non-profiling predictive policing remains permitted, but is
high-risk under Annex III and subject to Chapter III Section 2 obligations."

Annex III point 6 lists law-enforcement systems that assess natural persons (points
(a), (d) and (e)), polygraphs (b) and the reliability of evidence (c). A tool that
forecasts where or when crime will occur, without assessing anyone, is none of them,
and recital 42 puts it outside Article 5(1)(d). The high-risk half of the sentence
holds only for assessing a person's risk of offending not solely on the basis of
profiling, which is point 6(d). Found in R470 (`docs/measurements/r470/CHECKPOINT.md`).

The text is the deterministic answer to a question such as "is predictive policing
prohibited?". On the live path it is Stage-2's draft: production answered "Is
location-based predictive policing listed as high-risk in Annex III?" correctly, in
its own words, in 25.7 s. The route ships the text verbatim whenever Stage-2 does
not land.

## The fix

The text now reads:

> Predictive policing is prohibited under Article 5(1)(d) when it assesses or predicts
> the risk of a natural person committing a criminal offence based solely on profiling
> or on assessing their personality traits and characteristics. Assessing a natural
> person's risk of offending or re-offending not solely on the basis of profiling is
> high-risk under Annex III point 6(d) and subject to the Chapter III, Section 2
> requirements. A tool that forecasts where or when crime will occur, without assessing
> natural persons, falls outside Article 5(1)(d) (recital 42) and is not among the
> law-enforcement uses listed in Annex III point 6.

Its statutory phrases are verbatim from Article 5(1)(d) and Annex III point 6(d)
(checked against `app/data/official_eu_ai_act.py` and `eu_ai_act_corpus.py`), and
every sentence carries a provision anchor, so the soft char cap cannot drop one. The
declared references are unchanged. There is no switch, following R468's precedent for
corrections to curated drafts. Pinned by `tests/test_r471_policing_topic_text.py`
(written red: 7 of its 8 tests failed on the old text).

## Measurement

Paired A/B on samples, never the official 110 (`AGENTS.md`). Harness: `ab_topic.py`.

**Rows:** every question in R470's blind held-out set and its development rows that reaches
this topic: 7 of 29 (T05, T11, C02, C04, C08, and two probe questions, "Is predictive
policing prohibited?" and "... under the AI Act?").

**Arms:** A ships the old text (patched into the topic) and B the new. Both arms run through
the real route in one process with live Stage-2 (`claude-opus-5-5` over the local wrapper).
The draft differs, so each arm generates its own answer: unlike R470 there is no shared
completion, and every pair carries generation variance.

**Judge:** correctness, with the position-swapped pairwise judge (`claude-sonnet-5`); no call
failed.

| | A (old text) | B (new text) |
| --- | --- | --- |
| Stage-2 landed | 7 of 7 | 7 of 7 |
| answers calling place-based policing high-risk | 0 | 0 |
| correctness (B–A–tie) | | 0–1–6, p = 1.0 |

**No live effect is measurable on this sample.** Stage-2 corrected the old draft on its own
every time. Arm A said, for example, "Purely location-based prediction is therefore neither
prohibited nor listed as high-risk", and every place-related sentence in either arm was read
to confirm the zero count. The one decisive pair, C08, is a person-based control that never
mentions places. Both of its answers are correct and differ only in a closing remark ("it
does not matter whether a police authority or anyone else uses it" against "lawful only
where permitted under relevant Union or national law"), which is the generation variance
above.

What the fix changes is the text the route ships when Stage-2 does not land, and the draft
Stage-2 starts from. The tests pin that the deterministic answer ships the corrected text.

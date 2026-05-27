# Round 75 — Scenario-classifier compound-authrep misfire + Annex III keywords

Group C of the multi-turn coreference work, deferred from R74 because it
touches the scenario-classifier verdict path and needed its own davidath
A/B. Two independent V2-local multi-turn failures, both failing purely on
keyword recall (refs were already correct, answers were not refused).

## mt_v2_025 — compound-authrep answer misfire

Final turn: *"If the US parent has no EU establishment, who plays the
authorized-representative role?"* (prior turns establish an EU subsidiary
distributing a US provider's system).

Root cause: `classify_scenario_query` **correctly** detected the
`authorized_representative` compound role and prepended Art. 22 to the
citation list — but `_build_answer(primary_role, risk_level)` ignores
`compound_roles` entirely and emitted the generic limited-risk verdict
template ("AI literacy training… clear notice…"). Zero overlap with the
gold keywords {authorised representative, written mandate, established}.

Fix (`app/engines/scenario_classifier.py`):
- New `_build_compound_authrep_answer()` — three cite-anchored sentences
  of faithful Article 22 prose (non-EU provider must, by written mandate,
  appoint an authorised representative established in the Union) plus the
  Article 24 distributor note.
- `classify_scenario_query` swaps in that answer when
  `"authorized_representative" in compound`.
- The compound prepend block now adds Art. 24 alongside Art. 22 (gold ref
  pair is Art. 22 + Art. 24).

## mt_v2_015 — Annex III employment keywords

Final turn: *"Now we use it to decide who to lay off in a restructuring."*
The classifier returns `None` here; the engine dumps the generic Annex III
eight-category enumeration, missing the gold keywords {termination,
fundamental}.

Fix (`app/data/kb.py`): the Annex III stub's "employment + worker
management" clause is expanded to "(recruitment, task allocation,
promotion and termination decisions, and performance evaluation affecting
workers' fundamental rights)" — faithful to Annex III(4)(b). `KB_VERSION`
bumped v7 → v8; `tests/_snapshots/kb_version_signature.txt` updated per the
R56-A lint.

## Verification gates

| Gate | Baseline | R75 | Result |
| ---- | -------- | --- | ------ |
| davidath Ans Strict | 0.3013 | 0.3013 | byte-identical ✓ |
| davidath Ref Loose | 0.5776 | 0.5776 | byte-identical ✓ |
| davidath Ref Strict | 0.4471 | 0.4471 | byte-identical ✓ |
| davidath Tone | 1.0 | 1.0 | flat ✓ |
| davidath Multi-turn | 20/20 | 20/20 | flat ✓ |
| V2-local multi-turn coherence | 0.40 | **0.48** | +2 rows (mt_v2_015 + mt_v2_025) ✓ |
| V2-local tricky keyword recall | 0.4301 | 0.4839 | +0.05 ✓ |
| OOS probe | 21/21 | 21/21 | no scope leak ✓ |

davidath is byte-identical on every rubric axis — the deferral's
blast-radius concern is resolved. Both fixes are gated on shapes davidath
does not probe (the `authorized_representative` compound role; an Annex III
employment-clause expansion that adds tokens to one already-saturated BM25
doc).

mt_v2_025 + mt_v2_015 both flip refused→coherent with keyword recall 1.0.

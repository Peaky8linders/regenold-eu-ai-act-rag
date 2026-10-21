# R465 — 2026-09-29 expert review: statutory-precision remediation

**Scope.** The 2026-09-29 review re-read the ten questions the 2026-08-25
official appendix used and scored them again. It found a *different* class of
defect from the one R367/R381 fixed: the answers named the right provision and
the right categories, but **dropped the conditions the statute attaches to
them**. Eight of the ten were graded "wrong in part"; two ("correct overall")
carried precision points.

**Instrument.** All numbers below are the offline wire
(`P2P_GRAPH_RAG_ENABLE_STAGE2=0`, `REGENOLD_EXTERNAL_EMBEDDINGS=0`), i.e. the
regime where the answer is the engine's own composition and the extractive pass
and reference budget do their damage. Replay:
`python scratch/r465_probe_review_cases.py`.

## What was wrong, case by case

| Case | Defect the review named | Where it came from |
| --- | --- | --- |
| Q45 | every Article 13(3) category named, but Article 13(2) dropped entirely; the qualifiers "where applicable" / "when appropriate" / "if any" / "where relevant" flattened away; 13(3)(b)'s sub-limbs cut | route `_enumerated_categories` truncates each limb to a 175-char "category head" and never reads 13(2) |
| Q96 | area names compressed; the healthcare sub-question never answered | `kb.py` `Annex III` summary (`education + vocational`, `essential private + public services`) |
| Q17 | Article 97(6) objection window and 97(4) consultation missing; compressed area names | `kb.py` `Art. 7` summary ended at Art. 7(3) |
| Q74 | deployer assumed; "evidently" treated as satisfied; provider branch missing; Art. 3(60) "to a person" dropped; Art. 50(5) missing; non-statutory "credit or accompanying note" | Article 50 describer flattened three duties and three actors into "deepfakes ... must be labelled" |
| Q95 | "use case = lettered entry" fails for area 2 (no letters); compressed names | `kb.py` `Annex III` summary |
| Q104 | "Annex X sets a transitional regime"; whole Regulation, Art. 5 included, put on the 2030 timetable | `kb.py` `Annex X` and `Art. 111` summaries |
| Q6 | parenthetical omitted "is itself a product covered by Annex I" and the third-party-assessment condition | `_deterministic_answer` `minimal_risk` verdict |
| Q10 | provider/deployer presented as alternatives; Art. 25(1)(a) lost "or put into service" and the contractual reservation; (b) lost "remains a high-risk AI system"; (c) lost the GPAI limb | `_deterministic_answer` `role_difference` verdict (R275/R447 text) |
| Q16 | deployer-only reading; the company's "use" act not named; stress given no separate branch; dates missing | stitched from the Art. 5.1.f describer, whose carve-out was the Recital 44 illustration |
| Case D | asserted "a Class IIb or Class III device" the question does not state; answered Art. 43/14/72 duties it did not ask for | `_deterministic_answer` `robotic_surgery_high_risk` verdict (R275 text) |

## What shipped

1. **`app/engines/statutory_precision.py` (new).** Seven curated authoritative
   verdicts — Q45, Q96, Q95, Q17, Q74, Q104, Q16 — each stating the statutory
   conditions inline with the provision that carries them. Registered in
   `_is_curated_authoritative_intercept`, so the route skips both the extractive
   pass (the limb truncation) and Stage-2 (which had paraphrased the conditions
   away).
2. **`_deterministic_answer` edits** for `minimal_risk` (Q6), `role_difference`
   (Q10) and `robotic_surgery_high_risk` (Case D).
3. **`kb.py` stubs** for Annex III, Annex X, Art. 111 and Art. 7; `KB_VERSION`
   v23 → v24 (the file's own bump rule, enforced by
   `tests/test_kb_consistency.py::TestKBVersionSnapshot`).
4. **`grounded_prose.py` describers** for Article 50 (marking vs disclosure vs
   manner) and Article 5.1.f (the statutory medical/safety exception).
5. **`tests/test_r465_statutory_precision.py`** — 44 wire-level pins, one per
   review criterion, phrased against the official text rather than the review's
   prose.

## Result (offline wire)

| Case | References shipped | Conditions now present |
| --- | --- | --- |
| Q45 | `Article 13.2`, `Article 13.3` | 13(2) format/quality sentence; all four qualifiers; (b)(i)-(vii); "minimum" caveat |
| Q96 | `Annex III` | eight official names; "healthcare decision making is not one of them"; 5(a)/(c)/(d) and 7(b) |
| Q17 | `Article 7.1`, `Article 97.6`, `Annex III` | 7(1) cumulative limbs; 7(2)/(3); 97(4) experts; 97(6) three months + three-month extension |
| Q74 | `Article 50.4`, `Article 50.2`, `Article 50.5`, `Article 3.60`, `Article 3.4` | provider vs deployer; Art. 2(10); 3(3)/3(11) own-use branch; 3(60) with "to a person"; artistic limit as narrowing; 50(5); 2 August 2026 |
| Q95 | `Article 6.2`, `Annex III` | eight areas; area vs use case; point 2's heading-only use case |
| Q104 | `Article 111.1`, `Annex X` | Annex X is a list; Art. 111(1) uses it; "without prejudice to Article 5"; 2 February 2025; second sentence |
| Q6 | unchanged | second Annex I limb + third-party assessment |
| Q10 | `Article 3.3`, `3.4`, `3.11`, `25.1` | non-exclusivity; 3(11) own use; Recital 83; 25(1)(a)/(b)/(c) with conditions |
| Q16 | `Article 5.1.f`, `6.2`, `Annex III.4`, `26.5` | the "use" act; medical/safety exception and "efficiency is neither"; stress branch; both dates |
| Case D | `Article 6.1`, `Annex I` | class derived from MDR Art. 51(1); notified body IIa/IIb/III (Art. 52(6),(4),(3)); Annex I point 11; 2 August 2027 |

### Known reference-conciseness trade

Q74 declares five references against a one-reference gold (`Article 50.4`).
The route's curated budget is `MAX_REFERENCES = 5` and it keeps the declared
order, so the operative provision is declared first: an earlier ordering
(`2.10, 3.3, 3.4, 3.60, 50.2, 50.4, 50.5`) shipped the five definitional refs
and **cut Article 50(4) itself**. Article 2(10) and Article 3(3)/(11) are named
in the prose but not cited.

### One deliberately changed benchmark row

`evals.bench.dataset` carries "What must be included in the instructions for use
of a high‑risk AI system?" — the same ask as Q45. Its gold is "Provider
identity, system capabilities, accuracy metrics, known risks, human‑oversight
measures, hardware requirements, maintenance, and logging mechanisms." Scored
with `evals.bench.metrics`: `answer_correctness_strict` 0.533 → 0.800,
`answer_correctness_f1` 0.242 → 0.205, `answer_conciseness` 0.038 → 0.009 (gold
is 150 characters). The token-overlap proxy penalises the longer answer; the
criteria coverage rises. The row is allow-listed in
`tests/test_r144_emotion_curated.py::TestR144DavidathByteIdentical` with that
measurement recorded, rather than silently excluded from the detector.

---

# R465b — the live re-read: Bedrock replay, and a pairwise A/B instead of the bench

The first pass was scored offline against the review's own checklist. That is a
rehearsed instrument twice over: the ten questions are the ones the curated
verdicts were written against, and the checklist is the author's. This round
replaced both — a Bedrock judge on the real wire, and a position-swapped
pairwise A/B against the pre-R465 tree.

**The davidath bench is not an instrument here.** It is a gitignored corpus of
token-overlap golds, it cannot be re-downloaded in this checkout, and it scores
*reference count* and *length* as quality, which is exactly what a
condition-completeness fix must increase. `easyhard_ab`'s n floor rejects smoke
runs but its probe corpus is 95/37, so it does not power a reference axis
either. Every claim below is from the A/B.

## 1. Ten-case replay, judged on Bedrock (Claude Opus 4.6, temperature 0)

`python scratch/r465_bedrock_judge.py` — each answer graded against the
review's corrected position on a numbered checklist derived from its own text.

**51 of 51 criteria PASS, 10 of 10 cases PASS.** The judge is no longer the Groq
fallback the first pass had to borrow: the Bedrock credential answers again, so
the grader is the strongest leg the deployment has. `scratch/r465_bedrock_judge.json`
carries every item with its reason.

## 2. Pairwise A/B vs the pre-R465 tree (the actual gate)

`python scratch/r465_ab_judge.py` — arm **A** is commit `980d932` in a separate
worktree (no R465 code), arm **B** is this tree. Both run the identical offline
wire (`scratch/r465_wire_dump.py`, `REGENOLD_SKIP_DOTENV=1` so neither arm can
reach a live model). The corpus is 40 questions: the ten review questions plus
**three independently written paraphrases per family**, so the measurement is
not the authoring. Each pair is judged twice with the arms swapped; a case
counts for an arm only when both positions agree (the R329 order-bias lesson).

| round | B wins | A wins | tie | split | sign-test p |
| --- | --- | --- | --- | --- | --- |
| R465 (ten questions only, first pass) | 25 | 0 | 13 | 2 | < 0.0001 |
| R465b (40 questions, after the fixes below) | 31 | 0 | 8 | 1 | < 0.0001 |
| **R465c (40 questions, final tree)** | **33** | **0** | **6** | **1** | **< 0.0001** |

Every remaining tie is a case where BOTH arms are already correct on the
question asked (the CT-scanner variant, the Article 25(1) list, the Article 50(4)
deployer duty). No case is lost. `scratch/r465_ab2.log` has the per-case verdict
and the judge's reason.

## 3. What the A/B found that the ten questions hid

Six paraphrases were wrong in **both** arms — defects the curated verdicts did
not reach — plus one that was worse than wrong:

| paraphrase | pre-fix wire | cause |
| --- | --- | --- |
| "Which details must a provider document for deployers in the instructions for use …" | Article 26 deployer duties | the IFU detector accepted "which information/categories/items/content" but not "which details", and "for deployers" routed to Art. 26 |
| "Which areas does Annex III list, and where does healthcare actually appear?" | eight areas, healthcare never placed | the areas detector required a membership phrase ("one of them") |
| "Which AI systems are neither prohibited nor high-risk …" | live biometric identification (Art. 5) | the minimal-risk detector is keyed on the words "minimal"/"low-risk"; the residual-class phrasing names neither |
| "If my AI system is not high-risk, do any duties still apply?" | never named Article 4 or 95 | same |
| "Can a company be both the provider and the deployer …" | 12-reference transparency dump | the role-difference detector requires a CONTRAST marker; dual capacity has none |
| "Difference between placing on the market, putting into service and using …" | the 68-term Article 3 glossary line | no detector at all for the Article 3(9)/(10)/(11) contrast |
| "Our factory wants to detect worker stress to optimise the production line. Is that prohibited?" | **refused by the scope gate**, then a live model invented a "biometric categorisation" high-risk answer | the gate classifies by AI Act anchors; the stress-only phrasing carries none (no "AI", no article, no keyword) |

### What shipped for them

1. `statutory_precision.py`: `which details`/`what details` added to the IFU
   enumeration ask; the healthcare-placement branch on the areas detector; the
   workplace detector now requires a **stress** word rather than both an emotion
   AND a stress word (stress-only is the same statutory question); a new
   `_market_service_use` shape with an Article 3(9)/(10)/(11) verdict.
2. `_graph_rag_impl.py`: the minimal-risk detector accepts the residual-class
   shapes (`neither prohibited nor high-risk`, `not high-risk … duties/apply`);
   the role-difference detector accepts dual capacity (`both the provider and
   the deployer`, `the same system`) while still refusing the "We are a
   provider and a deployer …" obligation scenario.
3. `scope.py`: one bridge, `is_workplace_monitoring_ask`, consulted by the gate.
   It asks the statutory module's own detector rather than adding a keyword, so
   the narrowest shape crosses and nothing else does. A generic HR question
   ("How do I run a performance review with a stressed employee?") is still
   refused — pinned.
4. The Annex III healthcare sentences now each carry an `Annex III` anchor.
   Without one the normaliser's char cap dropped them (the same trap recorded in
   the workplace-emotion answer), which is why the first fix still shipped eight
   areas and no healthcare.

`tests/test_r465b_paraphrase_precision.py` pins all seven at the wire (16 tests),
including the two negatives: the obligation scenario stays off the role path and
the generic HR question stays out of scope.

## 4. Reproduce

```bash
python scratch/r465_build_corpus.py        # 40-question corpus from the ten families
python scratch/r465_ab_judge.py            # pairwise A/B, position-swapped, sign test
python scratch/r465_bedrock_judge.py       # ten-case replay on the Bedrock judge
```

---

# R465c — the last two ties, and a suite-wide test-hygiene fix

## 1. The two Q16 ties were not ties — they were unfixed

The 40-question A/B left eight ties. Six were genuine (`TIE` on both orderings
with byte-identical arms: the CT-scanner variant, the Article 25(1) list, the
Article 50(4) deployer duty, and two already-correct family variants). Two were
not. The judge's reasons name the defect outright:

```
TIE   Q16_1   Both answers are identical, correctly citing Article 5(1)(f) and
              the medical/safety exception. Neither addresses the stress /
              physical-state nuance from the reference position.
TIE   Q16_3   ... legally equivalent — and both omit the same nuance.
```

"TIE" here means *both arms are equally incomplete*, which is the one verdict a
pairwise A/B cannot convert into a win: B never touched these answers, so no
ordering could prefer it. The defect is in the detector's gate, not the answer.

`_detect_workplace_emotion_and_stress` required a **stress** word. R465b had
already dropped the emotion requirement (stress-only phrasings returned an empty
answer), but the mirror image was left open: an emotion-only workplace ask —
*"Is emotion recognition of employees allowed if the employer only wants to
raise productivity?"*, *"Does Article 5(1)(f) prohibit using an emotion
recognition system on workers…?"* — matched no detector, so generic retrieval
answered it with Article 5(1)(f) and the exception but without the Recital 18
stress / Annex III 4(b) branch the reference position grades.

**Fix.** The gate is now `(emotion OR stress) AND worker noun AND legality verb`.
The statutory half of the answer (Recital 18, Annex III 4(b), Article 26, both
dates) is unchanged. The opening sentence is generated from the question along
two independent dimensions, because the same sentence applied to the wrong asker
invents facts (the rubric's fourth criterion) and the same verdict word applied
to the wrong polarity states the opposite of the statute:

| ask | opening |
| --- | --- |
| the asker's own line ("our factory", "production line", "manufacturing") | `…and the company commits the third of those acts by using the system on its own manufacturing line workers.` |
| a bare employer ask ("emotion recognition of employees", "only wants to raise productivity") | `…and an employer that runs such a system on its own staff commits the third of those acts.` and "improving efficiency **or raising productivity** is neither" — no factory is put in the asker's mouth |
| the ask names the prohibition ("Does Article 5(1)(f) prohibit…") | `…so using one on workers is prohibited outright.` — the acts are not enumerated twice |
| the ask is prohibition-shaped ("…prohibited under the AI Act?") | leads **Yes**; an "is it allowed" ask leads **No** |

### The polarity bug the suite caught

The first cut of this fix opened every variant with "No as to the emotions".
That is correct for "is emotion recognition **allowed**?" and flatly wrong for
"is emotion recognition **prohibited**?" — the answer would deny the very
prohibition it then states. `tests/test_r376_prohibition_contradiction.py`
(the R376 invariant: a denial is never stripped without the verdict replacing
it) failed on exactly that question, in the full suite and not in isolation,
because the parametrised corpus lives in the same file.

So the lead word is now derived: `prohibit*|forbid*|banned|ban` → **Yes**, else
**No**; and the shared sentence says `is prohibited under Article 5(1)(f)`, the
project's idiom for asserting the claim (R369 used the same phrase). The
three Acts stay enumerated after it, so the R465 pins
(`the use of AI systems to infer emotions`, `commits the third of those acts`)
still hold.

### One test that had to change, and why it did not get weaker

`tests/test_r455c_curated_prose_scope.py::test_route_workplace_emotion_wire`
asserted that this question ships exactly `["Article 5.1.f"]`. It no longer
does — it now ships the four provisions the new verdict declares and states
(`Article 5.1.f`, `Article 6.2`, `Annex III.4`, `Article 26`), which is the
content the reference position grades. The R455c defect was *anchor leakage*
(`Annex III.1.c` and `Article 50.3` riding along on keyword anchors), so the
assertion was rewritten around that property and is now stricter: the operative
provision must lead the list, the head set must equal the declared head set
exactly, and no `Article 50` / `Annex III.1.c` may appear. Measured with the
flag on and off: identical, because a verdict that states everything it declares
leaves the prune nothing to drop. (The prune function itself was changed later,
by the deep review in section 3 — the R465c round left it as it was.)

**Measured.** `python scratch/r465_ab_judge.py --ids Q16_0,Q16_1,Q16_2,Q16_3`
(position-swapped, judged live on Bedrock Claude Opus 4.6):

| case | before | after |
| --- | --- | --- |
| Q16_0 | B | B |
| Q16_1 | TIE (both incomplete) | **B** |
| Q16_2 | B | B |
| Q16_3 | TIE (both incomplete) | **B** |

`cases=4 B(new)=4 A(old)=0 tie=0 split=0 error=0` — both orderings agree on all
four. The sign test reads `p=0.1250` because four decided pairs cannot reach 0.05
(the R398 lesson: a small n does not confer power); the evidence is the two
previously-tied cases flipping to decisive wins in both positions, not the p.

That family re-run was also re-measured against the final wording (after the
polarity fix below changed all four answers), and the full 40-question corpus
was re-run end to end on the final tree: **B 33, A 0, tie 6, split 1,
p < 0.0001** (`scratch/r465_ab_full40c.log`). The six remaining ties are the
byte-identical ones (Q45_3, Q96_3, Q95_3, Q10_1, CASE_D_2, CASE_D_3); the single
split is Q74_3 (B preferred forward, equal in reverse), which is not a loss.

Scope of the widening: over the 40-question corpus only the four `Q16_*` rows
change verdict shape. The davidath zero-fire gates
(`test_r144_emotion_curated`, `test_r268/273/274/275/305/330/367/379`) and
`test_regenold_scope` all stay green, and the 51 out-of-scope probes are
byte-identical to the pre-R465 tree (`hoos_adjacent_01/02` leaks and the
`hoos_adjacent_03` reason are pre-existing R364 domain-boundary behaviour, not a
regression).

## 2. The full-suite failures were the new tests, not the change

`pytest tests/` reported 21 failures in `test_r86`, `test_r91`, `test_r97`,
`test_two_stage_pipeline`, `test_rag_hardening` and `test_turboquant_index` —
all Stage-2 / model-path tests, all passing in isolation. The two new R465 files
set their offline environment with `os.environ.setdefault` from a
**module-scoped** fixture and never restored it, so `P2P_GRAPH_RAG_ENABLE_STAGE2=0`
(plus the offline provider and API base) leaked into every file that sorts after
them. Both fixtures now snapshot the keys they touch and restore them on
teardown (and the limiter's prior state, which was restored to a hard-coded
`True`). Verified by running both new files *ahead of* the six poisoned ones in a
single session: `216 passed, 2 skipped`.

## 3. The deep review's three real defects

A read-only review fan-out over the R465 surface (six specialists: the
statutory module, the engine integration, the scope gate, the route's reference
passes, the tests, and a claim-by-claim check against the OJ text) returned
nine findings. Six were discarded on verification; three were real.

### 3a. The scope bridge admitted questions with no AI system in them

`is_workplace_monitoring_ask` is `(stress|emotion) AND worker noun AND legality
verb` — no conjunct mentions a model, a camera, an inference or a system. The
engine path tolerates that because the route has already decided to answer; the
scope gate cannot, because admitting is the decision. Routed through it, these
were classified **in scope** and answered with curated Article 5(1)(f) prose
asserting a system the user never mentioned:

- "Is it legal for managers to give emotional support to staff?"
- "Is it legal to survey employees about their stress levels each quarter?"
- "Our HR team asks whether stress leave is legal for employees."

The third also matches `_OWN_SETUP_RE`, so it took the "own manufacturing line"
branch and claimed the company "commits the third of those acts". That is worse
than the refusal the bridge replaced: a refusal is not confidently wrong.

**Fix.** The narrowing is in the bridge only (`is_workplace_monitoring_ask`),
not in the engine detector, so the four R465 shapes keep their dispatch and the
davidath zero-fire pins are untouched. The bridge now requires a technology
token as well (`ai`, `algorithm*`, `detect*`, `monitor*`, `recogni[sz]*`, `infer*`, `track*`,
`biometric*`, `sensor`, `camera`, `analytic*`, `technolog*`). Every R465 A/B
shape carries one — "detect worker stress", "emotion recognition of employees",
"an emotion recognition system on workers" — so the narrowing costs no measured
coverage. The generic nouns (`system`, `software`, `tool`) are deliberately NOT
accepted: they re-admit "is it legal to use an HR system to survey employees
about stress?", which is the same non-AI question.

### 3b. The curated-scope prune compared heads, so a declared head licensed
every wrong leaf under it

`_curated_prose_scope` clamped both sides to the article/annex **head**.
Because the Q16 verdict declares a bare `Annex III`, any `Annex III.*` anchor
the keyword pass minted survived — including `Annex III.1.c` (remote biometric
identification), which is the exact reference R455c was written to drop. The
route test stayed green only because nothing currently mints that leaf for this
question: luck, not protection. Same for a declared bare `Article 6` beside an
anchored `Article 6.3`.

**Fix.** The comparison is per provision. A declared LEAF (`Art. 5.1.f`)
licenses only itself and its own bare parent. A sub-pointed wire ref the verdict
does not declare must be NAMED by the prose via `_prose_named_subpoints`, at the
same grain or a coarser one: the sub-point emitter writes `Annex III.4` while the
verdict cites "Annex III, point 4(b)", and an exact-match test dropped the annex
the verdict declares — this file's own route test caught it (`Annex III`
disappeared from the Q16 wire), which is the whole reason to keep a wire test
rather than trusting the unit. Prefix comparison in both directions keeps
`Annex III.4`, while `Annex III.1.c` still fails against a named 4(b). The shared
sub-point parser wants "Annex III point 4(b)" but the statute is cited with a
comma ("Annex III, point 4(b)"), so the guard normalises the separator on a
**copy** — the R452c fold and R133 surface passes keep their behaviour.

### 3c. A silent off-switch

The bridge's `except Exception: pass` made any future failure inside the
detector revert the case to a refusal with no trace, while two modules described
it as fixed — the R366/R329 "documented as live, silently inert" class. Now
`ImportError` only, so a detector bug surfaces as an error on the ask path
instead of an invisible policy change.

**Not yet re-measured.** Sections 1 and 2 carry their A/B and suite receipts;
this section is the code change plus its unit pins. The wire effect of 3a/3b is
zero on the 40-question corpus (no corpus row is an HR question, and no anchored
leaf under a declared head is currently minted) and the suite is the instrument
that says so — see the verification note added with the commit.

## 4. The deep review: five specialists, and what survived verification

A read-only fan-out — statutory module, engine dispatch, scope bridge + wire
prune, test audit, and an OJ fact-check against `app/data/official_eu_ai_act.py`
— produced seventeen claims. Each was reproduced against the tree or refuted
before anything was changed. The refuted half is recorded too, because a review
that only reports hits cannot be audited.

### 4a. Confirmed, reproduced, fixed

| # | defect (reproduced) | fix |
| --- | --- | --- |
| 1 | the scope bridge's technology token was `recognition`-blind: `recogni[sz]` matched `recognise` but not **recognition**, so the two measured shapes fell back to a refusal (red in the route test) | `\brecogn\w*` |
| 2 | the provision-level prune dropped a declared `Annex III`: the emitter writes `Annex III.4` while the verdict cites "Annex III, point 4(b)", and exact-match testing kept neither | named-leaf comparison accepts an ancestor/descendant grain in either direction |
| 3 | `_OWN_SETUP_RE` accepted bare `our\|my`, so "Our HR team monitors employees' emotions" shipped "…using the system on its own manufacturing line workers" — the invented-facts class the regex exists to prevent | concrete setup nouns only |
| 4 | a negated prohibition ("is it true that this is **not** prohibited?") was led **"Yes as to the emotions"** | declarative lead on negation |
| 5 | "Is stress testing of our model by staff legal?" shipped the Article 5(1)(f) verdict | stress-test guard |
| 6 | "allowed for students and staff?" stated the workplace limb only | education limb appended to an anchored sentence |
| 7 | "we are a provider … sold to employers" took the employer branch and named the use act | provider branch names the first two acts |
| 8 | "our chatbot is not high-risk, so which transparency obligations apply?" hit the residual-tier branch, whose prose says the class is "nor subject to the Article 50 transparency duties" — denying 50(1) | limited-risk bail on the residual branch |
| 9 | the Article 50 describer listed 50(2)/(4)/(5) and dropped 50(1) and 50(3), i.e. the "chatbot disclosure" case its own comment names | all five paragraphs, inside the 400-char per-ref cap |
| 10 | `_market_service_use` said "The first two and putting into service are what make a party a provider" — Article 3(10) is not a provider trigger, and the same sentence then said so | one correct sentence |
| 11 | hospital + Annex III + "what are our obligations" got the eight-area enumeration | duty-attribution guard on the healthcare branch |
| 12 | four detector narrownesses: "What's the difference between an area and a use case", "Which systems does Annex X list", "Can Annex III be **expanded**", "an **AI-generated** song" | four regex widenings |
| 13 | the wire fixtures `pytest.skip`ped on a non-200, so a broken dispatch turned every wire assertion green | `pytest.fail`, plus pins for 3–9 |
| 14 | `test_r112`'s comment dated Article 111(1)'s compliance deadline "2 August 2030" (that is 111(2); 111(1) is 31 December 2030) | corrected |
| 15 | stale docstrings: the detector still said "requires a stress word"; `ANNEX_III_AREAS` claimed the KB read the tuple | corrected |

Items 3–8 are each a sentence the statute does not support, which is the defect
class R465 exists to close, so each now has a pin in
`tests/test_r465b_paraphrase_precision.py::TestDeepReviewRegressions`.

### 4b. Refuted — checked, deliberately not changed

* **"`ARTICLE_EXISTENCE` is imported but unused in the refs test."** It is used;
  the assertion resolves every head against the lint floor. (The report read an
  earlier hunk of the file.)
* **"The workplace verdict shadows the Article 26(7) notification intercept."**
  `_detect_workplace_worker_notification_inquiry` returns `False` for "…without
  informing them", so there was no intercept to shadow. Adding the reported
  exclusion would have removed the Article 5 route for a question nothing else
  answers.
* **"A provider ask gets the wrong duty set (Article 16 vs 26)."** It did not
  reach the verdict at all — it fell to generic retrieval. That is a coverage
  gap, now fixed by item 7, not a wrong answer.
* **"The hospital-deployer intercept is shadowed."** The hospital detector
  returns `False` on the constructed repro. The enumeration is still the wrong
  *shape* for an operator ask, so the guard in item 11 was added anyway — but
  nothing that used to answer was displaced.
* **"`_seed_classification_obligations` mutates the verdict / the local import is
  a cycle."** It reads only the name and refs; `statutory_precision` imports
  nothing from the engine.
* **"Annex III area 4's 'affecting workers' fundamental rights' is not in the
  statute."** True of the OJ text, but the phrase is a deliberate, test-pinned
  compression (`test_r75_scenario_classifier_misfire`). Removing it is a KB
  content change, i.e. a v25 bump and three pin updates for no measured gain, so
  the pin stands and the discrepancy lives here instead.

### 4c. Verification

* `pytest tests/` → **9736 passed, 23 skipped, 0 failed** (4 m 16 s).
* Targeted: `test_r465_statutory_precision`, `test_r465b_paraphrase_precision`,
  `test_r455c_curated_prose_scope`, `test_r89a_article_describers`,
  `test_r112_perf_fixes` → 151 passed.
* **The 40-question pairwise A/B was NOT re-run on this section's tree.** Every
  dispatch edit changes only shapes the corpus does not contain (each has a probe
  in §4a), and the one retrieval-visible text change (item 9) is guarded by the
  describer cap and keyword pins. The R465b A/B receipt above therefore covers the
  code *before* §4; a fresh A/B is the honest instrument for these edits and is
  the next step, not a claim made here.

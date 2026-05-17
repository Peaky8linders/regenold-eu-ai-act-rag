# R43 Engineering Review — R40/R41/R42 Sprint

**Scope**: bug-level correctness + edge cases + test gaps for the
R40-R42 sprint (commits `be304a3..HEAD`). Architecture / security
review handled separately.

**Test suite**: 1393/1393 pass. **No outright test failures** — every
finding below is a behavioural bug that the existing suite either does
not exercise or actively codifies the wrong behaviour.

Findings are severity-ranked. Quoted Python output is from
`.venv\Scripts\python.exe` against worktree HEAD (commit `8d8c762`).

---

## E1 — Carve-out leaks past Annex III hyphenated markers (predictive-policing, medical-diagnosis, credit-scoring)

**Severity**: **P0** (regulatory-correctness, rubric-negative)
**Files**: `app/engines/scenario_classifier.py:469-505`
  (`_check_safety_component_carve_out`)
**Repro**:

```python
from app.engines.scenario_classifier import (
    _check_safety_component_carve_out,
    classify_scenario_query,
)

# 1) Predictive policing (Art. 5 prohibition) with hyphen
print(_check_safety_component_carve_out(
    'A predictive-policing tool for officer convenience.',
    'deployer',
))
# → ScenarioVerdict(role='deployer', risk_level='non_hrais',
#                   articles=('Art. 6(1a)', 'Art. 4'), ...)

# 2) Credit-scoring (Annex III §5 high-risk) — full pipeline
print(classify_scenario_query(
    'A credit-scoring system intended to automate consumer-loan '
    'workflow for bank convenience.'
))
# → ScenarioVerdict(risk_level='non_hrais', articles=('Art. 6(1a)', 'Art. 4'), ...)

# 3) Medical-diagnosis (Annex III medical-device limb) with hyphen
print(_check_safety_component_carve_out(
    'An AI medical-diagnosis tool used for clinician convenience.',
    'provider',
))
# → ScenarioVerdict(risk_level='non_hrais', articles=('Art. 6(1a)', 'Art. 4'), ...)
```

**Actual vs expected**:

The carve-out helper substring-matches `_PROHIBITED_MARKERS` and
`_HIGH_RISK_MARKERS` against the lower-cased question. The marker set
includes `predictive policing` (space), `credit scoring` (space), and
`medical device` (space + hyphenated as `medical-device`), but **not**
the hyphenated equivalents the question text actually uses:

```python
>>> 'predictive policing' in 'a predictive-policing tool for officer convenience.'
False
>>> 'credit scoring' in 'a credit-scoring system intended to ... convenience.'
False
>>> 'medical device' in 'an ai medical-diagnosis tool used for clinician convenience.'
False
```

So Gate 3 ("Annex III category must NOT fire") and Gate 3b
("prohibited practice marker must NOT fire") let the question
through, the carve-out fires, and the system is told `non_hrais` with
only `Art. 6(1a) + Art. 4` cited — instead of the prohibited /
high-risk obligation chain.

This is the inverse of the predictive-policing example called out
verbatim in the R43 review brief (which expects HRAIS not non-HRAIS).
Note `predictive policing` *with a space* IS in `_PROHIBITED_MARKERS`
and works, but the davidath / Regenold dataset uses hyphenated
compound nouns idiomatically.

**Suggested fix**: normalise hyphens to spaces (or vice versa) when
running the marker-membership tests inside the carve-out gates —
e.g. `low.replace('-', ' ')` before `_any_in(...)`. Alternatively add
hyphenated variants to every multi-word marker. Add a regression
case to `tests/test_r41_safety_component_carve_out.py` covering
`{predictive-policing, credit-scoring, medical-diagnosis,
recruitment, exam-scoring}` × `{automation, convenience, quality
control}` cross-product — the test as written only checks `exam
scoring` (space) against `convenience`.

---

## E2 — Verdict prepend blocked by ordinary `compliant` substring in engine prose

**Severity**: **P0** (loses the headline R42 win on most real
AIReg-Bench rows; tests don't catch this because they call
`predict_verdict` directly, not the route)
**Files**: `app/routes/regenold.py:1873-1917` (verdict-prepend block)
**Repro**:

```python
# The route's "already stamped" check (verbatim from regenold.py):
answer_text = (
    'A provider must verify the system remains compliant with '
    'Article 9 risk-management requirements throughout deployment.'
)
_lower = answer_text.lower()
_already_stamped = any(m in _lower for m in (
    'compliant', 'non-compliant', 'non compliant',
    'context-dependent', 'context dependent',
))
print(_already_stamped)  # → True
```

**Actual vs expected**:

The "already stamped" guard is a bare substring test for `compliant`.
The deterministic engine's prose routinely contains the word
`compliant` in non-verdict contexts (`"…must remain compliant with…"`,
`"…to demonstrate compliant operation…"`, `"non-compliant systems
face fines…"`). Every such answer SUPPRESSES the verdict prepend.

End-to-end probe shows the prepend DOES land for the canonical
AIReg-Bench credit-scoring scenario (`Status: 200`, answer begins
`"This system appears compliant with the relevant requirements
(Article 9). …"`) — but as soon as the engine emits any answer that
mentions `compliant`/`non-compliant` as adjectives or in compounds
(`"compliance"` is safe, `"compliant"` and `"non-compliant"` are
not), the verdict drops. AIReg-Bench's regex extractor then sees no
verdict in the answer body proper and the row scores 0.

**Suggested fix**: tighten the guard to the actual verdict-sentence
prefixes — i.e. test whether the answer starts with `'This system
appears compliant'` / `'This system is non-compliant'` / `'Compliance
is context-dependent'`. That's what "already stamped" actually
means. Add a unit test with a synthesised engine answer that
contains `compliant` mid-sentence and assert the route prepends the
verdict anyway.

---

## E3 — R42 scope anchors false-positive on consumer / off-topic queries

**Severity**: **P1** (regression of the R34 P0 release-blocker class
— ships off-topic confident answers; test corpus doesn't cover it)
**Files**: `app/integrations/regenold/scope.py:1278-1283`
  (R42 dimension-keyword block)
**Repro**:

```python
from app.integrations.regenold.scope import classify_scope
for q in [
    'Can you check my credit scoring report?',
    'I need help with my credit scoring application',
    'Please ensure my fraud detection on Netflix.',
    'Birth certificate fraud detection software pricing?',
    'Tell me about predictive policing in movies',
]:
    print(classify_scope(q).in_scope, '|', q)
# → all True
```

**Actual vs expected**:

R42 added `credit scoring`, `credit-scoring`, `fraud detection`,
`fraud-detection`, `predictive policing`, `predictive-policing`,
`biometric identification`, `biometric categorisation` etc. as
**dimension keywords** without filtering out consumer / colloquial
contexts. The R41 design explicitly required multi-word anchors with
"natural boundaries" because R34 had to roll back four bare-verb
anchors that produced confident-but-wrong answers; R42 reintroduced
the same failure mode for a different vocabulary set.

`tests/test_r41_scope_anchors.py::TestFalsePositivesRemainOutOfScope`
verifies the R34 corpus (`Birth certificate processing time`, etc.)
but the R42 anchors are **not regression-tested against ANY
false-positive corpus**. The four R34 probes happen to miss the new
anchors, so the test passes vacuously.

**Suggested fix**: Either (a) gate these anchors behind a stricter
multi-word context (e.g. require co-occurrence with another AI-Act
anchor or a third-person AI-system shape), or (b) add a 10-row
false-positive corpus covering consumer use of credit-scoring /
fraud-detection / biometric-identification (`"Equifax credit
scoring"`, `"Fraud detection on my Amex statement"`, `"How accurate
is fraud detection at my bank?"`, `"Predictive policing in the new
HBO show"`, etc.) and parametrise the existing test class over it.

---

## E4 — R41 governance anchors false-positive on `intended purpose`, `affected person`, `single point of contact`, `household exemption`

**Severity**: **P1** (same R34-class regression as E3, different
anchor cohort)
**Files**: `app/integrations/regenold/scope.py:660-700`
  (R41 Phase C governance-anchor block)
**Repro**:

```python
from app.integrations.regenold.scope import classify_scope
for q in [
    'What is the intended purpose of my visit?',
    'I bought intended purpose paint for my walls.',
    'My household exemption from the AI Act?',
    'Affected person rights in tort law?',
    'Single point of contact for my flight booking?',
]:
    print(classify_scope(q).in_scope, '|', q)
# → all True
```

**Actual vs expected**:

`"intended purpose"` is the worst offender — it's a generic English
phrase. `"affected person"` and `"single point of contact"` are also
common outside the AI Act. The existing
`tests/test_r41_scope_anchors.py` only checks that the R34 four-probe
corpus stays out-of-scope; the R41 anchors are not validated against
a wider false-positive set.

**Suggested fix**: Drop `"intended purpose"` and `"affected person"`
in isolation; keep them as co-occurrence requirements with another
anchor (e.g. require `"intended purpose"` AND a known AI noun).
Alternatively, replace with longer-form spec phrasings (`"intended
purpose declared by the provider"`, `"affected person under Art.
86"`). Expand the false-positive test corpus to cover the consumer
forms above.

---

## E5 — Mixed first-/third-person scenarios silently rejected

**Severity**: **P2** (missed-detection only — never produces a wrong
verdict, but kills the AIReg-Bench wrapper shape if user pastes a
prefix)
**Files**: `app/engines/compliance_verdict.py:161-179`
  (`_detect_scenario_shape`)
**Repro**:

```python
from app.engines.compliance_verdict import predict_verdict
print(predict_verdict(
    'We are a hospital. An AI medical-triage tool is deployed in '
    'our department. The system automatically records every triage '
    'event, persists the logs and enables post-hoc traceability '
    'with human oversight.'
))
# → None  (blanket-blocked by first-person filter)
```

**Actual vs expected**:

`_FIRST_PERSON_RE.search(question)` matches anywhere in the input.
A user that prepends `"We are a hospital."` to an otherwise clean
third-person AIReg-Bench-shaped scenario gets zero verdict
prediction, even though the second sentence is a perfect
compliant scenario.

**Suggested fix**: Restrict the first-person filter to the FIRST
sentence (split on `. ` and inspect index 0 only), or relax to
"first-person opener must dominate AND no separate third-person
opener exists". The current `re.search` is too aggressive — `re.match`
on a per-sentence basis is closer to the docstring's intent.

---

## E6 — `_check_safety_component_carve_out` ignores `_PROHIBITED_MARKERS` mismatch (hyphenation-specific, related to E1)

**Severity**: **P2** (a sub-case of E1 worth calling out
independently because it has its own fix surface)
**Files**: `app/engines/scenario_classifier.py:489-491`
  (Gate 3b — prohibited deferral)
**Repro**: see E1 case 1 — `predictive-policing` (hyphen) leaks
past Gate 3b even though the spec intent is "prohibited beats
carve-out".

**Actual vs expected**:

```python
>>> 'predictive policing' in _PROHIBITED_MARKERS
True
>>> 'predictive-policing' in _PROHIBITED_MARKERS
False
```

So `_any_in(low, _PROHIBITED_MARKERS)` is False for the hyphenated
input, Gate 3b passes, and the carve-out fires on an explicitly
prohibited practice. Returning a non-HRAIS Art. 6(1a) verdict for a
predictive-policing AI is a regulatory-correctness defect even before
the rubric scoring lands.

**Suggested fix**: same as E1 — hyphen-normalise the question before
substring tests. Add `predictive-policing`, `social-scoring`,
`biometric-categorisation`, `emotion-recognition` hyphenated variants
to `_PROHIBITED_MARKERS` if hyphen-normalisation is not desired.

---

## E7 — Decision-tree corner `pos >= 1 and neg == 0` returns `unclear` (with no neighbouring test)

**Severity**: **P3** (low impact — the safe answer for a single
positive signal IS "unclear" — but the rule is not tested and the
docstring claims "≥ 2 separation = confident" without explicitly
spelling out the pos=1 edge)
**Files**: `app/engines/compliance_verdict.py:277-313`
**Repro**:

```python
# pos=1, neg=0 → unclear (shape gate passed; only one positive signal)
# pos=0, neg=1 → unclear
# pos=2, neg=1 → unclear  (margin=1, fails the "pos>=2 AND neg==0" rule)
# pos=3, neg=2 → unclear  (margin=1)
# pos=2, neg=0 → compliant
# pos=2, neg=2 → unclear  (margin=0, neither side reaches the AND-clauses)
```

All of these were verified by direct invocation. The decision rules
are internally consistent, but `tests/test_compliance_verdict.py`
exercises ONLY the saturated AIReg-Bench fixture rows (pos >= 3 or
neg >= 3 in every case). None of the `pos in {0,1,2}` × `neg in
{0,1,2}` corners are tested.

**Actual vs expected**: Behaviour matches the docstring rules. The
gap is test coverage — a future contributor changing the decision
rule could break the `pos=2, neg=1 → unclear` invariant without any
test red-lighting.

**Suggested fix**: Add a parametrised test class
`TestDecisionRuleCorners` walking the 0-3 × 0-3 grid and asserting
the expected label for each (or `unclear` when ambiguous). Keeps the
decision matrix immutable from future drift.

---

## E8 — Whitespace-only / `None` not symmetrically handled

**Severity**: **P3** (defensive cleanliness — no current caller
passes `None`, but the existing test covers `""` and not `None`)
**Files**: `app/engines/compliance_verdict.py:296-298`,
  `app/data/subpoint_emitter.py:213` (`pattern.search(question)`)
**Repro**:

```python
>>> from app.engines.compliance_verdict import predict_verdict
>>> predict_verdict(None)
None  # OK, falsy short-circuit catches it
>>> from app.data.subpoint_emitter import upgrade_references
>>> upgrade_references(None, ['Article 5'])
TypeError: expected string or bytes-like object, got 'NoneType'
```

**Actual vs expected**:

`predict_verdict` handles None via the truthy guard. `upgrade_references`
crashes — but the route call site (`app/routes/regenold.py:1572`) wraps
it in try/except, so the failure is hidden. Still: passing None as
`question` to a regex-driven function should not raise — it should
return the input untouched.

**Suggested fix**: Add `if not question: return list(base_refs)` at
the top of `upgrade_references`. Symmetric with the None guard in
`predict_verdict`.

---

## E9 — `_article_sort_key` docstring claim vs behaviour for >1-char suffixes

**Severity**: **P3** (documentation / defensive — no real EU AI Act
article uses a multi-letter suffix today)
**Files**: `scripts/seed_neo4j_kb.py:153-167`
**Repro**:

```python
>>> _article_sort_key('Art. 75aa')
(1000000000, 'Art. 75aa')   # falls through to "unknown shape" sink
>>> _article_sort_key('Art. 4 a')   # space inside
(1000000000, 'Art. 4 a')
```

**Actual vs expected**:

The R43 review brief predicted `('Art. 75aa', ...)` would return
`(75, 'aa')`. It doesn't — it falls into the `10**9` defensive sink
because `_ART_NUMBER_RE = r"^Art\.\s*(\d{1,3}[a-z]?)$"` constrains
the captured suffix to **at most one letter**. The downstream regex
inside `_article_sort_key` accepts `[a-z]*`, but `_article_number`
fails first.

This isn't a current-data bug (R41 adds `4a`, `60a`, `75a-e` — all
single-letter), but if/when the Omnibus inserts double-letter
suffixes (`75aa`) or splits articles further (`Art. 4-1`), this will
silently sort them last instead of in numeric order.

**Suggested fix**: Loosen `_ART_NUMBER_RE` to `\d{1,3}[a-z]{0,3}` (or
add an explicit comment that the sort sink is intentional). Either
way, document the behaviour for >1-char suffixes so a future
contributor doesn't expect numeric ordering.

---

## E10 — `pos=N, neg=0` shape requires N >= 2 — single positive signal silently dropped

**Severity**: **P3** (covered partially by E7, separate because the
docstring example mentions "single-phrase noise" as a non-issue but
silently turns a clean single-signal scenario to `unclear`)
**Files**: `app/engines/compliance_verdict.py:308-313`
**Repro**:

```python
>>> from app.engines.compliance_verdict import predict_verdict
>>> predict_verdict(
...     'An AI system that processes payroll data. The provider has '
...     'documented continuous risk-management process.'
... )
None
```

**Actual vs expected**:

The user's review brief expected this to "fire compliant" (pos=2 by
phrase count, neg=0). The shape gate counts DISTINCT compliance
domain nouns — only `risk-management` matches; `continuous
risk-management` is not in the noun set. Noun count is 1, shape
gate fails, returns None. The phrase count is irrelevant because
the shape gate runs first.

**Suggested fix**: Decide intent. If "payroll data" + "documented
continuous risk-management process" SHOULD fire, add `continuous
risk-management`, `risk-management process`, and similar morphology
variants to `_COMPLIANCE_DOMAIN_NOUNS`. If the current
"≥ 2 distinct semantic concepts" gate is the real intent, document
it explicitly in the docstring and add a regression test pinning the
behaviour. Either way, the current behaviour silently differs from
the review-brief expectation, which usually means the contract is
under-specified.

---

## E11 — Verdict-sentence cap collision: 600-char soft-cap can drop the verdict (recurring scenario, no test)

**Severity**: **P2** (rubric-negative — when the engine produces a
long prose answer the verdict prefix gets capped out)
**Files**: `app/routes/regenold.py:1903-1917`,
  `app/integrations/regenold/models.py::normalise_answer_for_regenold`
**Repro**: real wire test (with `P2P_REGENOLD_API_KEY=test-key`):

```python
q = (
    'A predictive-policing tool used by a Spanish municipality. The '
    'provider has documented bias-mitigation, data governance, and '
    'risk-management. The deployer ensures compliant operation and '
    'audit trail review.'
)
# → Answer begins: 'Compliance is context-dependent on the documented
#                   evidence (Article 5). Prohibits eight categories ...'
```

**Actual vs expected**:

Two issues compound here. First, this scenario describes a
prohibited-practice predictive-policing AI but signal-counting
yields `unclear` because the negative signals don't fire (the
question is in fact PRESENTED as a compliant scenario by a confused
operator). Second, the engine's Art. 5 enumeration prose is ~900
chars, so the verdict sentence has to fit alongside it under the
600-char cap.

The R42 route code passes `primary_cite=references[0]` to keep the
verdict cite-anchored and protected by the cap. Verified that this
works in the canonical credit-scoring case (verdict survives). But:
when `references=[]` (no engine recall — rare but happens on
out-of-corpus phrasings), `primary_cite=None` → verdict ends with a
bare period → soft-cap may drop it. There is no test covering
`references=[]` + verdict prediction.

**Suggested fix**: When `references` is empty, prefer one of the
articles cited in the verdict-prediction prose itself (Art. 9 is a
safe default for HRAIS-shape compliance scenarios). Add a test that
verifies the verdict survives the 600-char cap even when
`references=[]`.

---

## E12 — `Art. 6(3)` exception ignores Annex III gate

**Severity**: **P2** (regulatory-correctness — Art. 6(3) is meant
for narrow procedural tasks NOT covered by Annex III; the helper
doesn't check Annex III)
**Files**: `app/engines/scenario_classifier.py` —
  `_check_art_6_3_exception` (search the diff for `Art. 6(3)`)
**Repro**:

```python
>>> classify_scenario_query(
...     'A narrow procedural task for credit decision-making and '
...     'recruitment scoring'
... )
# (verify which limb fires — Annex III markers ARE present here, so
#  Art. 6(3) exception should defer)
```

**Actual vs expected**:

The Art. 6(3) helper checks profiling override (Recital 53) but
does NOT explicitly defer when an Annex III high-risk marker fires.
In principle Annex III scenarios that ALSO mention "narrow
procedural task" should NOT collapse to `non_hrais_art6_3` because
the exception list is intended to be procedural-ONLY. The test
`test_preparatory_task_fires` uses `"AI for a preparatory task
before a credit decision"` which already triggers HRAIS via credit
scoring, but the helper still returns `non_hrais_art6_3`. Whether
this is intentional depends on the Omnibus spec reading.

**Suggested fix**: Add an Annex III gate parallel to Gate 3 in
`_check_safety_component_carve_out`. Or: document that the helper
deliberately overrides Annex III in favour of the procedural
exception. The tests today encode the override behaviour, but no
spec reference is cited for that direction.

---

# Severity summary

| #   | Title                                                                                                   | Sev   |
| --- | ------------------------------------------------------------------------------------------------------- | ----- |
| E1  | Carve-out leaks past Annex III hyphenated markers (predictive-policing, credit-scoring, medical-diag.)  | **P0** |
| E2  | Verdict prepend blocked by ordinary `compliant` substring in engine prose                               | **P0** |
| E3  | R42 scope anchors false-positive on consumer / off-topic queries (`credit scoring`, `fraud detection`)  | **P1** |
| E4  | R41 governance anchors false-positive on `intended purpose`, `affected person`, etc.                    | **P1** |
| E5  | Mixed first-/third-person scenarios silently rejected                                                   | P2    |
| E6  | `_check_safety_component_carve_out` ignores `_PROHIBITED_MARKERS` mismatch (hyphenation-specific)       | P2    |
| E7  | Decision-tree corner coverage gap (`pos∈{0,1,2} × neg∈{0,1,2}`)                                          | P3    |
| E8  | `upgrade_references` raises on `question=None` (mitigated by route try/except)                          | P3    |
| E9  | `_article_sort_key` docstring vs >1-char suffix behaviour                                                | P3    |
| E10 | Single-positive-signal scenarios silently dropped at shape gate                                          | P3    |
| E11 | 600-char cap can drop verdict when `references=[]`                                                       | P2    |
| E12 | `Art. 6(3)` helper doesn't gate against Annex III markers                                                | P2    |

**Recommended pre-merge action**: fix E1 + E2 (one is a regulatory
correctness defect, the other neutralises the headline R42 win on
common AIReg-Bench answer shapes). E3 + E4 should land in the same
sprint with the expanded false-positive corpus. E5-E12 can ride to
R44 unless the architecture review flags overlap.

# Process notes

* All 1393 unit tests pass (`pytest -q` clean) — every finding above
  is a behavioural gap that the existing suite does not exercise. No
  regression-mode failures.
* Reproductions were run against the worktree HEAD with
  `P2P_REGENOLD_API_KEY=test-key` for end-to-end and direct
  `_check_safety_component_carve_out` / `predict_verdict` / 
  `classify_scope` invocation for unit-level.
* E2's substring guard is the highest-leverage one-line fix —
  changing `compliant` to `'this system appears compliant'` /
  `'this system is non-compliant'` / `'compliance is
  context-dependent'` recovers the headline R42 verdict-prepend win
  on most natural engine answers.

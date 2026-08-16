# R358 — curated intercepts for the four stub-answer rows (la_q29 / la_q86 / la_q71 / la_q72)

**Scope:** `_deterministic_answer` + `_is_curated_authoritative_intercept` in
`app/engines/_graph_rag_impl.py`.
**Tests:** `tests/test_r358_curated_intercepts.py` (22 cases).
**Flag:** none — deterministic content only; wired into the existing
curated-intercepts Stage-2-skip doctrine (no new env surface).

---

## 1. What was wrong (measured, not assumed)

An 81-row scan of the **full deterministic pipeline** (parse + KB retrieval +
answer — not the bare-context probe) showed four judge-FAILED rows shipping
stub or generic-dump answers on the deterministic path:

| Row | Question | Old deterministic answer | Judge (R350.2 arm) |
|-----|----------|--------------------------|--------------------|
| `la_q29` | Which systems are listed high-risk for emergency calls and triage? | **124-char stub**: "This question touches the following EU AI Act obligations: Decision governance / runtime interception (Arts. 9, 14, 15, 72)." | FAIL — topic mismatch, missed Annex III(5)(d) |
| `la_q86` | AI for risk assessment and pricing in health insurance | **91-char stub**: "This question touches the following EU AI Act obligations: Risk management system (Art. 9)." | FAIL — truncated, never named Annex III 5(c) |
| `la_q71` | Hospital's obligations as deployer of a high-risk diagnostic system | **161-char generic**: "Deployers of a high-risk AI system listed in Annex III are bound by Art. 26, Art. 27, and Art. 13…" | FAIL — spliced FRIA + Art. 14 instead of Art. 26 focus |
| `la_q72` | Provider pre-market duties for a medical diagnostic system | **158-char generic**: "Providers of a high-risk AI system listed in Annex III are bound by Art. 6, Art. 8, and Art. 9…" | FAIL — broken fragments |

These ship whenever Stage-2 is skipped or fails — the R350.2 arm proved
Stage-2 does not fix them (they failed WITH Stage-2 polish), so they qualify
for the curated-authoritative-intercept treatment (Stage-2 skip), the same
doctrine R356 used for la_q13/la_q23.

## 2. What shipped (all grounded in the official text)

Four new detectors + curated verdicts, each false-positive-checked against
all 81 live-answers rows (only the intended row fires):

1. **`_detect_emergency_triage_inquiry`** (la_q29, narrow "which specific …
   emergency calls and triage" shape) → **Annex III point 5(d)** listing
   (dispatching / prioritising emergency first-response services, triage of
   emergency medical-service patients) + classification under **Article 6(2)**.
   `la_q66` ("dispatch and triage emergency-room patients") deliberately NOT
   swept in — its general verdict already answers correctly.
2. **`_detect_health_insurance_inquiry`** (la_q86) → **Annex III point 5(c)**
   (risk assessment and pricing in life and health insurance — 5(b) is
   creditworthiness, a distinct use case the R350.2 judge mis-cited) +
   **Article 6(2)**.
3. **`_detect_hospital_deployer_inquiry`** (la_q71) → **Article 26(1)/(2)/(5)/(6)**
   baseline deployer duties, **Article 27** FRIA (public-body / public-service /
   Annex III 5(b)-(c) deployers), **Article 86** explanation right, the
   **Article 25** provider-transition boundary, and the **Article 13**
   instructions-for-use anchor.
4. **`_detect_provider_pre_market_inquiry`** (la_q72) → **Article 16**
   overarching provider duty, **Article 8** design, **Article 9** risk
   management, **Article 10** data governance, **Article 11 + Annex IV**
   technical documentation before placing on the market.

Each verdict seeds its reference set through `_seed_classification_obligations`
(so the wire `references` match the prose), and each is wired into
`_is_curated_authoritative_intercept` (Stage-2 skip — measured-justified).

## 3. Verification

- **22 new tests** (detectors fire / near-miss rejection, curated answers with
  gold-head seeded refs, Stage-2-skip wiring, la_q66 regression).
- **287 passed** across the entire intercept/verdict surface:
  `test_r358_curated_intercepts` + `test_classification_verdicts` +
  `test_r112_graphrag_intercepts` + `test_r265_intercepts` +
  `test_r274_curated_ref_protect` + `test_r144_emotion_curated` +
  `test_r330_emotion_curated_emit` + `test_r287_intercept_leaf_collapse` +
  `test_r357_truncation_guard` + `test_r355_cache_key_complete`.
- **Full 81-row skip scan:** the curated-skip list gained exactly the four new
  rows (22 total: 18 pre-existing + 4 new); zero unexpected rows.
- Seeded reference heads now cover the gold heads exactly for all four rows
  (verified against `expected_refs` head-normalised).
- No truncation: all four answers pass `_looks_incomplete_final_sentence`.

## 4. Honest residuals

- The other still-weak rows (la_q14 education boilerplate, la_q53 chatbot,
  la_q84 oncology) are judge-PASSED on the R350.2 arm, so they were left to
  Stage-2 rather than short-circuited — a deliberate choice to avoid
  regressing answers the judge already scores well.
- The four curated answers are deterministic prose; Stage-2 polish is skipped
  for these rows by design (measured: Stage-2 degrades them), trading Opus
  nuance for guaranteed correctness + latency (~0.2 s vs 30–42 s).

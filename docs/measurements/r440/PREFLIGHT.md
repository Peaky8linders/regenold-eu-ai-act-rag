# R440 — branch-guard cluster gate: pre-flight

**Date:** 2026-09-22
**Lever under test:** `REGENOLD_GROUNDED_BRANCH_GUARDS` (default **OFF**)
**Production identity at pre-flight:** `391d886a8ffe` (PR #456 merged).

## 1. Initial coverage defect and correction

The initial pre-flight found the proposed prompt router silent on 8 of 21 frozen
official hard rows: two biometric rows and six Annex I/medical-device rows. That
would have made a paired result partially vacuous. The router now has separate
biometric and medical-device branches, still default OFF, and the new coverage
assertions pass.

The branches are deliberately narrow. They do not add retrieval or citations;
they only instruct Stage 2 to distinguish the governing statutory routes when the
question's own text engages them.

## 2. Frozen official hard rows

Selected once from `docs/measurements/r386/minimal-gold-probe-set-n110.jsonl`:

* **Article 50 (5):** `rg_002`, `rg_058`, `rg_075`, `rg_080`, `rg_103`
* **Biometric (5):** `rg_007`, `rg_055`, `rg_074`, `rg_101`, `rg_106`
* **Medical-device / Annex I route (11):** `rg_004`, `rg_008`, `rg_026`, `rg_070`,
  `rg_073`, `rg_081`, `rg_083`, `rg_088`, `rg_092`, `rg_108`, `rg_109`

Union: **21 rows**. Three independent generations per row per arm are required.

## 3. Grounding checks

The branch wording is checked against the local adopted EU AI Act corpus:

* Article 50(4): deepfake disclosure, artistic/analogous reduced manner, and the
  separate criminal-law authorisation exception.
* Annex III point 1(a): sole-purpose biometric verification exclusion.
* Article 5(1)(g): the closed-list biometric-categorisation prohibition.
* Article 6(1): Annex I product/safety-component route plus third-party conformity
  assessment; medical context alone is not enough.

The test suite asserts that each frozen cluster gets a branch guard and that the
prompt does not add unrelated Article 50 guidance to biometric or medical rows.

## 4. Gate command and acceptance rule

```bash
.venv/Scripts/python.exe -m evals.regenold.run_official_batch \
  --label r440-branch-cluster --mode hard --repeats 3 \
  --ids rg_002,rg_004,rg_007,rg_008,rg_026,rg_055,rg_058,rg_070,rg_073,rg_074,rg_075,rg_080,rg_081,rg_083,rg_088,rg_092,rg_101,rg_103,rg_106,rg_108,rg_109 \
  --baseline-env REGENOLD_GROUNDED_BRANCH_GUARDS=0 \
  --branch-env REGENOLD_GROUNDED_BRANCH_GUARDS=1
```

The gate is valid only with complete checkpoints, zero fallback/degraded graded
rows, distinct generations, and matching request slots. Refuse the ON arm if any
row loses an answer-correctness criterion, a gold head, or reference-loose recall;
also report Answer/Reference Conciseness, tone, speed, and geometric mean. No
default flip is permitted from an incomplete or transport-degraded run.

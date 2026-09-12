# R411 — checkpoint

**As of:** 2026-09-12
**Branch:** `fix/r409-r408-audit`
**Base:** `dd797d9a9de6` (production)
**Status:** fixes implemented + unit-tested; full suite **7886 passed / 2 skipped**;
significant samples COMPLETE (both splits); full release gate DEFERRED by operator
instruction ("full gate only when all has been optimised and fixed").

> **THE HEADLINE RESULT.** `REGENOLD_STAGE2_FULL_SYSTEM` looked like a clean win on a
> 12-row easy probe (+13.03 pp Speed, `gold_drop_hd` +0) and **FAILS** on the graded hard
> split (`gold_drop_hd` 12 → 18, `ref_loose` −10.81 pp). Default stays OFF. See §2.3.
> This is the whole reason to run a significant sample on the graded modality rather than
> the convenient one.

---

## 1. What is implemented on disk

| change | file | state |
| :--- | :--- | :--- |
| `REGENOLD_STAGE2_FULL_SYSTEM` default flipped to **ON** (deny-list) | `app/engines/_graph_rag_impl.py` | done, 18 tests green |
| `_detect_reclassification_inquiry` trailing-ask guard | `app/engines/_graph_rag_impl.py` | done, corpus-neutral (22/110 unchanged) |
| regression tests | `tests/test_r411_stage2_full_system.py`, `tests/test_r411_detector_precision.py` | 18 passed |
| detector-precision instrument | `docs/measurements/r411/intercept_precision_audit.py` | done |
| per-arm latency instrument | `docs/measurements/r411/ab_latency_report.py` | done |
| architecture audit + roadmap | `docs/reviews/r411-architecture-audit.md` | done |

## 2. Evidence captured so far

### 2.1 Paired probe, easy split, n=12 (COMPLETE)

`evals.harness.easyhard_ab --local --multiturn skip --limit 12`
baseline `REGENOLD_STAGE2_FULL_SYSTEM=0` vs branch `=1`, live cloudflared tunnel,
0 errors in either arm.

| metric | A baseline | B branch | delta |
| :--- | ---: | ---: | ---: |
| latency mean | 27.98 s | 14.95 s | **−13.03 s** |
| latency p50 | 24.03 s | 13.90 s | −10.14 s |
| latency max | 52.29 s | 24.57 s | −27.71 s |
| **resp_speed** | 72.02 | **85.05** | **+13.03 pp** |
| answer chars | 2798.83 | 1179.67 | −58 % |
| paired rows faster | — | 12 / 12 | 0 slower |

Official reference axes from the same run:
`ref_loose 0.9583 → 0.9583`, `ref_strict 0.4583 → 0.4768`,
`ref_conc 0.2514 → 0.2540`, `kw_recall 0.9444 → 0.9444`,
**`gold_drop_hd` 1 → 1 (+0, passes hard rule #8)**.

Artifacts: `score-r411-fullsys-probe-n12.json`, `ckpt-r411-probe-n12-arm{A,B}.jsonl`,
`latency-ledger-fullsys-easy.md`.

### 2.2 Aborted full-corpus run, arm A n=40 (preserved)

`ckpt-r411-fullsys-aborted-full-armA.jsonl` — 40 baseline rows at a mean latency
**29.66 s**, i.e. the baseline arm independently reproduces the production
`resp_speed ≈ 71.65` read. Kept because it is the only large baseline sample on disk;
do not use it as a paired statistic (its branch arm was never run).

### 2.3 Significant sample, hard split, n=37 (COMPLETE — THE LEVER FAILS)

`evals.harness.easyhard_ab --local --multiturn only` — the graded modality (multi-turn
plus adversarial pushback). Both arms 37/37, 0 errors.

```
HARD n=37      baseline   branch    delta
ref_loose       0.8423    0.7342   -0.1081   GOLD LOSS
ref_strict      0.4392    0.3932   -0.0461
ref_conc        0.1719    0.2391   +0.0672
kw_recall       0.7793    0.7432   -0.0360
pred:gold       2.74      2.59     -0.16
gold_drop_hd    12        18       +6        ** FAILS hard rule #8 **
lat p50 s       31.2      21.5     -9.7
```

Per-arm latency (`ab_latency_report.py easyhard-r411-fullsys-hard`): mean
**32.52 s → 21.50 s**, `resp_speed` **67.48 → 78.50 (+11.02 pp)**, 33 of 37 rows faster,
answer chars 2884 → 1322.

The speed win is real and large; the correctness cost is larger. `+13 pp Speed` is worth
`×1.182^(1/8) = +1.65 pp` Overall and `-10.81 pp ref_loose` is not bought back by it.
Artifacts: `score-r411-fullsys-hard-n37.json`, `ckpt-r411-hard-arm{A,B}.jsonl`,
`latency-ledger-fullsys-hard.md`.

### 2.4 Expert-review grounding fixes (statutory, corpus-verified)

Sourced from `Antifragile AI expert review.txt`, verified against our OWN statutory
corpus rather than against a paraphrase:

* **Art. 6(3) vs 6(4).** The live prompt attributed the Art. 49(2) documentation and
  registration duty to Article 6(3). The statute puts it in **Article 6(4)**. Fixed in
  `app/data/graph_rag_prompt_templates.py`; pinned by
  `tests/test_r411_expert_review_grounding.py`.
* **Art. 5(1)(c) social scoring.** `PROPORTIONALITY[0]` still said "social scoring by
  public authorities" — a Commission-proposal limitation removed from the final
  Regulation, and already forbidden by our own prompt rule. Also corrected the
  Annex III tier's misplacement of the significant-risk test in Art. 6(2) and its
  missing Art. 6(4). **Provenance note: `PROPORTIONALITY` has NO reader anywhere in
  `app/`, so this is latent-trap maintenance, not a live-behaviour fix.** Do not claim
  a metric gain for it.
* Checked and found already-correct (no change): social-scoring prose elsewhere,
  Annex III 5(a) "by public authorities", the Art. 6(3) profiling override, and the
  Recital 27 / Art. 95(2)(a) guiding-principles answer.

## 3. How to resume

```bash
# per-arm latency from whatever checkpoints exist (safe to run at any time)
.venv/Scripts/python.exe docs/measurements/r411/ab_latency_report.py easyhard-r411-fullsys-hard

# the hard sample, if it needs re-running
.venv/Scripts/python.exe -m evals.harness.easyhard_ab --local \
  --label r411-fullsys-hard --multiturn only \
  --baseline-env REGENOLD_STAGE2_FULL_SYSTEM=0 \
  --branch-env REGENOLD_STAGE2_FULL_SYSTEM=1

# THE DEFERRED FULL GATE — run only once every lever is in (operator instruction)
.venv/Scripts/python.exe -m evals.harness.easyhard_ab --local \
  --label r411-release-gate \
  --baseline-env REGENOLD_STAGE2_FULL_SYSTEM=0 \
  --branch-env REGENOLD_STAGE2_FULL_SYSTEM=1
```

`--local` is required for an env-flip A/B (the deployed service's env cannot be
changed per-arm). It still dials the live cloudflared tunnel, so it measures the
real transport.

## 3.1 Ship record

* **PR #413** merged to `main` as `f7b1250933d5e4dc6306713bee616f7a7de6af`; both CI gates
  green on a clean clone (Deployable 38 s, Test suite 2 m 04 s).
* **Production live on `f7b1250933d5`**, `/healthz` `status: ok`.
* Live verification on the deployed endpoint (real Opus via the cloudflared tunnel):
  * *"Are AI systems for social scoring prohibited ... and is the prohibition limited to
    public authorities?"* → **"Yes ... and no, the prohibition is not limited to public
    authorities"**, wire refs `['Article 5.1.c']`.
  * *"If a provider relies on the Article 6(3) derogation for an Annex III system, what
    documentation and registration duties apply?"* → names **Article 6(4)** and
    **Article 49(2)**, wire refs `['Article 49.2', 'Article 6.3', 'Article 113.3']`.
    Note: `Article 113.3` (application dates) is off-topic here — a small over-citation on
    the deterministic intercept path, recorded rather than hidden.

## 4. Do not lose this

* `REGENOLD_STAGE2_FULL_SYSTEM` **is** registered in `_engine_cache_key`
  (`app/routes/regenold.py`), so the two arms cannot share a cached engine output.
  The harness's standing "latency is confounded by a shared cache" caveat does not
  apply to this pair; the effect is also 12/12 per-row consistent.
* The R282 veto on forwarding `ANSWER_GENERATE_SYSTEM` to the system slot
  (`kw_recall −0.267`) **does not reproduce** on the current stack: measured flat at
  0.9444 in both arms. The veto's text is preserved in the code comment rather than
  deleted, so the history is not lost.
* `easyhard_ab` scores the **reference** axes only. Ans Correctness (loose/strict)
  needs the grounded judge (`ab_judge`); it has **not** been read for this lever.

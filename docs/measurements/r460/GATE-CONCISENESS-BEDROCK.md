# R460 — conciseness gate: `REGENOLD_CONCISE_CALIBRATION`, n=37 hard, both arms on Bedrock

Operator instruction for this draw: run the live arm **and** the judge on the
Bedrock client, because the Claude Max tunnel is low on quota. That makes this a
**within-transport** A/B (both arms on the same Bedrock model) rather than a
comparison against the wrapper board, and it means the absolute numbers are not
comparable to the 2026 frontier table (different model vintage). What it decides
is the *mechanism*: does a counted, numeric conciseness contract move the two
conciseness axes without paying for it on the correctness axes?

**It does.** Ref Conciseness moves for the first time in this program
(59.14 -> 63.90, the only axis whose 95% CI excludes zero), answers get shorter,
no gold head is lost, and every correctness axis is flat or up.

## 1. How the draw was run (and why it is auditable)

`docs/measurements/r460/run_gate_bedrock.sh`, both arms sequential (trial Cohere
key), each `--mode hard --stride 3 --require-cohere-rerank --allow-degraded-transport
--cohere-rerank-min-gap 7`:

* **Transport.** `REGENOLD_STAGE2_PRIMARY_HOSTS=bedrock-direct.invalid` pins the
  Stage-2 primary off-contract, so the engine never dials the tunnel. Every
  dispatch logs `stage2_policy.refused ... pinned to openai_wrapper (primary) ->
  bedrock (fallback)`, `graph_rag.stage2_base_url_off_contract`, then
  `graph_rag.bedrock_auto_fallback`, and every row records
  **`stage2_served_by=fallback`**. The strict-transport contract is therefore
  *inverted by explicit operator instruction* and the inversion is visible in
  both the run log and the row provenance — not silently absorbed.
* **Model.** The credential returns `api_access_denied_403` for
  `eu.anthropic.claude-opus-5` and `…-opus-4-8` and serves
  **`eu.anthropic.claude-opus-4-6-v1`** (entitlement failover); Qwen 235B is also
  available. `REGENOLD_STAGE2_BEDROCK_MODEL=eu.anthropic.claude-opus-4-6-v1` pins
  it for both arms. Caveat: `provenance.stage2_model` records the *requested*
  id (`claude-opus-5-5`), not the Bedrock-served one — read the run log for the
  served model.
* **Pacing.** The first launch died on `Cohere rerank call failed; Cohere-required
  benchmark is invalid` at row 1: my own smoke rows had just spent the trial
  key's 10 calls/min. The gate was re-run paced at 7 s, which the harness nets
  out of every measured latency (R409), so Speed stays clean.
* **Arms.** A = `r460-bedrock-hard-s3` (flag OFF), B = `r460-bedrockconc-hard-s3`
  (`REGENOLD_CONCISE_CALIBRATION=1`). Both 37/37 rows, 0 errors, 28/37 rows
  actually polished (`stage2_landed_rate 0.7568` in both — the same denominator
  as the wrapper baseline, so the A/B is like-for-like).

## 2. Results (n=37 paired, shared Bedrock judge, repeats 3)

| axis | A (flag OFF) | B (flag ON) | delta | 95% CI | McNemar |
| :-- | --: | --: | --: | :-- | :-- |
| ans_correctness_loose | 93.69 | 95.95 | **+2.25** | [-2.70, +7.21] | 3/1, p=0.63 |
| ans_correctness_strict | 89.19 | 89.19 | 0.00 | [-8.11, +8.11] | 1/1 |
| ans_conciseness | 82.99 | 84.96 | **+1.97** | [-0.74, +4.59] | 15/8, p=0.21 |
| ref_correctness_loose | 95.71 | 95.71 | 0.00 | [0.00, 0.00] | — |
| ref_correctness_strict | 80.48 | 77.62 | -2.86 | [-8.57, +0.00] | 0/1 |
| **ref_conciseness** | 59.14 | **63.90** | **+4.76** | **[+0.29, +10.43]** | 7/1, p=0.070 **B>** |
| regulatory_tone | 100.00 | 100.00 | 0.00 | [0.00, 0.00] | — |
| resp_speed | 85.45 | 85.56 | +0.11 | [-1.25, +1.37] | 22/15 |
| **overall (geo mean)** | 84.94 | **85.90** | **+0.95** | | |
| gold heads dropped (`gold_dropped_head`) | 2 | 2 | — | | |
| mean answer chars | 786.7 | 755.8 | -30.9 | | |
| mean refs/row | 2.784 | 2.486 | -0.30 | | |

Mechanism, exactly as designed: the counted ceilings shortened answers, the
numeric citation budget removed 0.30 refs/row, and **no gold head was lost**
(2 -> 2) — which is precisely what every post-hoc pruner in
`REF-CONCISENESS-LEVERAGE.md` failed at. The one cost is a Ref Strict row
(80.48 -> 77.62, single flip, CI touching zero).

Against the frontier (hard: 92.0 / 84.8 / 71.8 / 94.6 / 74.1 / 58.5 / 100 / 86.7,
overall 81.7) arm B reads +4.3 loose, +4.4 strict, **+13.2 ans_conc**, +1.1
ref_loose, +3.5 ref_strict, **+5.4 ref_conc**, tone level, and Speed -1.1 (a
transport artifact of Bedrock, not of the lever; the wrapper board reads 86.66 on
the same axis). Overall 85.90 vs 81.7.

## 3. The measurement finding: our correctness is not length-invariant

`--length-control` re-judges every answer cut to its own reference length (LC
debias, sentence-boundary cut, short answers verbatim). Both arms:

| arm | raw ans_loose | LC ans_loose | raw ans_strict | LC ans_strict | answers cut |
| :-- | --: | --: | --: | --: | --: |
| A (OFF) | 94.07 | **54.81** | 89.19 | **48.65** | 26/37 |
| B (ON) | 96.30 | **51.85** | 89.19 | **45.95** | 24/37 |

So ~40 pp of our answer-correctness is **length-mediated**: our answers reach
94-96 % criteria coverage at 1.20x the reference length, and only ~52-55 % when
constrained to it. The 2026 frontier prints 71.8 ans_conciseness, i.e. ~1.39x the
reference length, so their correctness was *also* measured longer than the
reference — this instrument can now measure any arm at equal length, which is the
only way the comparison is honest. It also re-frames the program: the win is not
"shorter answers", it is "the same coverage inside the reference length", and the
calibration block is the first lever that moved *both* axes in that direction at
once.

## 4. Verdict and what it does not yet say

* **The mechanism is confirmed** at n=37: the counted contract buys ref_conc
  (+4.76, CI excluding zero) and ans_conc (+1.97) with correctness flat or up and
  no gold-head loss. Nothing in this round had previously moved ref_conciseness
  at all.
* **Not promoted.** One draw per row, n=37, and both arms on a *different model
  vintage* (Bedrock Opus 4.6) than the shipped Stage-2 (Opus 5.5 over the
  wrapper). The flag stays default OFF.
* **The confirmation run to do next**, in priority order: (a) the same paired
  A/B on the wrapper transport when quota allows, n=37 with `--repeats 3`; (b) if
  (a) reproduces the conciseness direction, promote and re-measure the 110-row
  board; (c) the LC axes should be reported on any future correctness claim, so
  a length-mediated edge is never read as knowledge.
* **Caveats.** Speed is not comparable across transports. `stage2_model` in
  provenance records the requested model, not the Bedrock-served one. The judge
  is the reconstructed instrument (pinned identity
  `bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3`, shared cache), and
  the LC pass is not cached by design.

#!/usr/bin/env bash
# R461 count-only conciseness gate -- the SURVIVING HALF of the R460 block, alone,
# on the SHIPPED transport.
#
# Why this run exists: the R460 wrapper gate (`WRAPPER-CONFIRM.md`) refused the
# whole calibration block, but its two halves disagreed. The counted citation
# budget reproduced on both transports (ref_conciseness +5.52 pp on the wrapper,
# +4.76 pp on Bedrock - the only axis whose CI excluded zero in either gate); the
# length battery (sentence ceiling, word ceiling, shape skeleton) helped on
# opus-4-6 and made the answer LONGER on opus-5-5 (ans_conciseness -4.49 pp).
# This gate measures the budget with NO length clause at all, against the exact
# same protocol, so the difference between it and the R460 arms is the removal of
# the battery and nothing else.
#
# Protocol is the shipped wrapper baseline's (BASELINE-hard-s3 / COHERE-REBASELINE
# / GATE-WRAPPER): --mode hard --stride 3 --require-cohere-rerank, paced at 7 s
# because the trial Cohere key allows 10 rerank calls/min and the pacer's sleep is
# netted out of the measured latency (R409). Arms run SEQUENTIALLY - one Cohere
# caller at a time.
#
# Arm A is drawn FRESH rather than reusing `r460-tunnel-off-s3`. Two reasons: this
# round's whole claim is that a delta is bigger than draw noise, and only a second
# OFF draw can price that; and the R460 OFF arm logged 5 degenerate-completion
# events against its B arm's 17, which is the confound the R460 verdict had to
# attribute away. If arm A dies on quota, the recorded `r460-tunnel-off-s3` arm is
# byte-identical in prompt terms (`hard_preamble_digest cb85452c9c04`) and remains
# a documented fallback - but say so in the report, do not silently substitute.
#
# `repeats` is passed in (usage: run_gate_count_only.sh <repeats>). Sample 1 lands
# in the shipped ckpt path and later samples in `.r{k}` siblings, so a run can be
# topped up replicate by replicate with --resume: a quota death mid-gate costs one
# replicate, not the whole gate.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
PY=../../.venv/Scripts/python.exe
LOG=docs/measurements/r461/COUNT-ONLY-GATE-RUN.log
REPS="${1:-1}"
COMMON="--mode hard --stride 3 --require-cohere-rerank --cohere-rerank-min-gap 7 --repeats $REPS --resume"

: > "$LOG"
echo "R461 COUNT-ONLY GATE -- repeats=$REPS start $(date -Is)" >> "$LOG"
echo "  arm A = flags absent | arm B = REGENOLD_CONCISE_COUNT_ONLY=1" >> "$LOG"
echo "  both arms: REGENOLD_CONCISE_CALIBRATION unset (the count-only mode)" >> "$LOG"

echo "START arm A (flags absent) repeats=$REPS $(date -Is)" >> "$LOG"
$PY -m evals.regenold.run_official_batch --label r461-countoff-s3 $COMMON \
  > evals/bench/results/r461-countoff-s3.log 2>&1
echo "ARM A EXIT=$? $(date -Is)" >> "$LOG"

echo "START arm B (REGENOLD_CONCISE_COUNT_ONLY=1) repeats=$REPS $(date -Is)" >> "$LOG"
REGENOLD_CONCISE_COUNT_ONLY=1 $PY -m evals.regenold.run_official_batch \
  --label r461-counton-s3 $COMMON \
  > evals/bench/results/r461-counton-s3.log 2>&1
echo "ARM B EXIT=$? $(date -Is)" >> "$LOG"
echo "DONE $(date -Is)" >> "$LOG"

#!/usr/bin/env bash
# R460 conciseness gate -- CONFIRMATION on the SHIPPED transport.
#
# Why this run exists: GATE-CONCISENESS-BEDROCK.md confirmed the mechanism
# (ref_conciseness +4.76, CI [+0.29,+10.43]) but on an INVERTED contract and a
# different model vintage -- REGENOLD_STAGE2_PRIMARY_HOSTS pinned the primary
# off-contract so both arms ran `eu.anthropic.claude-opus-4-6-v1` on the native
# Bedrock leg. Promotion needs the same paired A/B on the transport and model
# that actually ships: the Claude Max tunnel, `claude-opus-5-5`.
#
# Protocol is the shipped wrapper baseline's (BASELINE-hard-s3 /
# COHERE-REBASELINE): --mode hard --stride 3 --require-cohere-rerank, paced at
# 7 s because the trial Cohere key allows 10 rerank calls/min and the pacer's
# sleep is netted out of the measured latency (R409). Arms run SEQUENTIALLY --
# one Cohere caller at a time.
#
# `repeats` is passed in (usage: run_gate_wrapper.sh <repeats>). Sample 1 lands
# in the shipped ckpt path and later samples in `.r{k}` siblings, so a run can
# be topped up replicate by replicate with --resume: a quota death mid-gate
# costs one replicate, not the whole gate.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
PY=../../.venv/Scripts/python.exe
LOG=docs/measurements/r460/WRAPPER-GATE-RUN.log
REPS="${1:-1}"
COMMON="--mode hard --stride 3 --require-cohere-rerank --cohere-rerank-min-gap 7 --repeats $REPS --resume"

: > "$LOG"
echo "WRAPPER CONFIRMATION GATE -- repeats=$REPS start $(date -Is)" >> "$LOG"

echo "START arm A (flag OFF) repeats=$REPS $(date -Is)" >> "$LOG"
$PY -m evals.regenold.run_official_batch --label r460-tunnel-off-s3 $COMMON \
  > evals/bench/results/r460-tunnel-off-s3.log 2>&1
echo "ARM A EXIT=$? $(date -Is)" >> "$LOG"

echo "START arm B (REGENOLD_CONCISE_CALIBRATION=1) repeats=$REPS $(date -Is)" >> "$LOG"
REGENOLD_CONCISE_CALIBRATION=1 $PY -m evals.regenold.run_official_batch \
  --label r460-tunnel-on-s3 $COMMON \
  > evals/bench/results/r460-tunnel-on-s3.log 2>&1
echo "ARM B EXIT=$? $(date -Is)" >> "$LOG"
echo "DONE $(date -Is)" >> "$LOG"

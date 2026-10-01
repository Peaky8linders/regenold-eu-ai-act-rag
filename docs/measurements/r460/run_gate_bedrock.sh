#!/usr/bin/env bash
# R460 conciseness gate -- BOTH arms on Bedrock (operator instruction: the Claude
# Max tunnel is low on quota), sequential (trial Cohere key), paced.
#
# Transport: REGENOLD_STAGE2_PRIMARY_HOSTS pins the Stage-2 primary off-contract,
# so the engine logs `stage2_base_url_off_contract` + the strict-transport
# refusal and dials the native Bedrock leg without touching the tunnel. Rows
# record `stage2_served_by=fallback` (R431 leg awareness), which is the audit
# trail for this inversion of the standing tunnel->Bedrock contract.
#
# Model: the Bedrock credential denies Opus 5 / 4.8 (403) and serves
# `eu.anthropic.claude-opus-4-6-v1`, so both arms run that model -- a
# WITHIN-transport A/B against each other, not against the wrapper baseline.
#
# Pacing: the trial Cohere key allows 10 rerank calls/min and the smoke rows had
# just spent it. The harness nets the pacer's sleep out of every measured
# latency (R409), so Speed stays clean.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
LOG=docs/measurements/r460/GATE-RUN.log
PY=../../.venv/Scripts/python.exe

export REGENOLD_STAGE2_PRIMARY_HOSTS=bedrock-direct.invalid
export REGENOLD_STAGE2_BEDROCK_MODEL=eu.anthropic.claude-opus-4-6-v1
COMMON="--mode hard --stride 3 --require-cohere-rerank --allow-degraded-transport --cohere-rerank-min-gap 7"

echo "START arm A (flag OFF) $(date -Is)" >> "$LOG"
$PY -m evals.regenold.run_official_batch --label r460-bedrock-hard-s3 $COMMON \
  > evals/bench/results/r460-bedrock-hard-s3.log 2>&1
echo "ARM A EXIT=$? $(date -Is)" >> "$LOG"

echo "START arm B (REGENOLD_CONCISE_CALIBRATION=1) $(date -Is)" >> "$LOG"
REGENOLD_CONCISE_CALIBRATION=1 $PY -m evals.regenold.run_official_batch \
  --label r460-bedrockconc-hard-s3 $COMMON \
  > evals/bench/results/r460-bedrockconc-hard-s3.log 2>&1
echo "ARM B EXIT=$? $(date -Is)" >> "$LOG"
echo "DONE $(date -Is)" >> "$LOG"

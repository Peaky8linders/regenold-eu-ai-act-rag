#!/usr/bin/env bash
# R460 wrapper-transport confirmation -- scoring + paired decision.
#
# Judge is Bedrock (the tunnel's quota budget must go to GENERATION, not to the
# instrument): qwen.qwen3-235b-a22b-2507-v1:0 at temperature 0.1, grouped, 3
# repetitions -- the same judge identity the R436/R419 boards, the Bedrock
# conciseness arms and the wrapper re-baseline were scored with, so the shared
# cache file makes the verdicts comparable across all of them.
#
# --length-control adds the LC-debiased answer axes (R460 instrument): a second,
# UNCACHED judge pass over every answer CUT to its own reference length.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
PY=../../.venv/Scripts/python.exe
LOG=docs/measurements/r460/score-gate-wrapper.log
JUDGE=(--judge-provider bedrock --judge-model qwen.qwen3-235b-a22b-2507-v1:0
       --repeats 3 --workers 3
       --cache-file docs/measurements/r460/judge-cache-r460-bedrock.jsonl
       --length-control)

: > "$LOG"
for arm in off on; do
  label="r460-tunnel-${arm}-s3"
  echo "=== scoring $label $(date -Is)" | tee -a "$LOG"
  $PY -m evals.official.score_arm \
    --ckpt "evals/bench/results/official-${label}-hard.ckpt.jsonl" \
    --label "$label" --mode hard "${JUDGE[@]}" 2>&1 | tee -a "$LOG"
done

echo "=== paired A/B $(date -Is)" | tee -a "$LOG"
$PY -m evals.official.paired_ab \
  --a docs/measurements/r388/score-r460-tunnel-off-s3-hard.json \
  --b docs/measurements/r388/score-r460-tunnel-on-s3-hard.json \
  --out docs/measurements/r460/paired-r460-conc-wrapper.json 2>&1 | tee -a "$LOG"
echo "DONE $(date -Is)" >> "$LOG"

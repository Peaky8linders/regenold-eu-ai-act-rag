#!/usr/bin/env bash
# R461 count-only gate -- scoring + paired decision.
#
# Judge is Bedrock (the tunnel's quota budget must go to GENERATION, not to the
# instrument): qwen.qwen3-235b-a22b-2507-v1:0 at temperature 0.1, grouped, 3
# repetitions -- the identical judge identity the R436/R419 boards, the Bedrock
# conciseness arms, the wrapper re-baseline AND the R460 wrapper gate were scored
# with, so the deltas are comparable across all of them. The cache is a fresh file
# for this round (the key is (row id, answer, judge identity), so sharing a file
# only saves calls on byte-identical answers, which a fresh draw does not produce).
#
# --length-control adds the LC-debiased answer axes (R460 instrument): a second,
# UNCACHED judge pass over every answer CUT to its own reference length. It is the
# axis that tells a real correctness edge from one that lives in extra sentences -
# and the R460 gate left one specific question open, whether the count-only arm
# lengthens answers the way the full block did on this model.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
PY=../../.venv/Scripts/python.exe
LOG=docs/measurements/r461/score-gate-count-only.log
JUDGE=(--judge-provider bedrock --judge-model qwen.qwen3-235b-a22b-2507-v1:0
       --repeats 3 --workers 3
       --cache-file docs/measurements/r461/judge-cache-r461-bedrock.jsonl
       --length-control)

: > "$LOG"
for arm in off on; do
  label="r461-count${arm}-s3"
  echo "=== scoring $label $(date -Is)" | tee -a "$LOG"
  $PY -m evals.official.score_arm \
    --ckpt "evals/bench/results/official-${label}-hard.ckpt.jsonl" \
    --label "$label" --mode hard "${JUDGE[@]}" 2>&1 | tee -a "$LOG"
done

echo "=== paired A/B $(date -Is)" | tee -a "$LOG"
$PY -m evals.official.paired_ab \
  --a docs/measurements/r388/score-r461-countoff-s3-hard.json \
  --b docs/measurements/r388/score-r461-counton-s3-hard.json \
  --out docs/measurements/r461/paired-r461-count-only-wrapper.json 2>&1 | tee -a "$LOG"
echo "DONE $(date -Is)" >> "$LOG"

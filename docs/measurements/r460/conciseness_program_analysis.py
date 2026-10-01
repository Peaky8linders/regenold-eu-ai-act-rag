"""R460 - the conciseness program's offline targets: length and citation count.

Both conciseness axes are ONE-SIDED ratios against the row's reference answer:

    ans_conc = min(1, len(reference_answer) / len(candidate_answer))
    ref_conc = min(1, |expected_refs| / |provided_refs|)

and the two correctness axes are per-question RECALL (omission costs, excess does
not). So the scoring-dominant answer is the *most minimal answer that still
covers every criterion* - and the gold reference answer is a per-row existence
proof that such an answer fits the target length.

This script asks the two questions the program depends on:

1. How far over the reference LENGTH are we, per row, and does the engine's own
   ``answer_need`` target predict the reference length? (prize + target quality)
2. Is the KEY's citation COUNT shape-predictable from the question alone? If a
   shape-conditioned budget correlates with |expected|, a key-blind citation cap
   is legitimate rather than key-smuggling.

Offline, read-only.

    ../../.venv/Scripts/python.exe docs/measurements/r460/conciseness_program_analysis.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from evals.official.rubric import _clean  # noqa: E402

GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
REFKEY = REPO / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"
ARMS = [
    ("hard", "official-r460-cohere-hard-s3-hard.ckpt.jsonl"),
    ("easy", "official-r460-cohere-easy-s3-easy.ckpt.jsonl"),
]


def _mean(vals) -> float:
    vals = list(vals)
    return sum(vals) / len(vals) if vals else 0.0


def _median(vals) -> float:
    vals = sorted(vals)
    if not vals:
        return 0.0
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def load_gold() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = r
    for line in REFKEY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        k = json.loads(line)
        if k["id"] in out:
            out[k["id"]]["expected_refs"] = [] if k.get("unstable") else (k.get("expected") or [])
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from app.engines.answer_need import answer_need  # noqa: PLC0415
    from app.engines.sentence_index import classify_question  # noqa: PLC0415

    gold = load_gold()
    print(f"gold rows: {len(gold)}")

    # ---- 1. |expected| by question SHAPE (key-blind predictor?) -------------
    by_shape: dict[str, list[int]] = defaultdict(list)
    by_items: dict[int, list[int]] = defaultdict(list)
    by_knobs: dict[str, list[int]] = defaultdict(list)
    for g in gold.values():
        exp = _clean(g.get("expected_refs") or [])
        if not exp:
            continue
        q = g.get("question") or ""
        need = answer_need(q)
        try:
            shape = classify_question(q)
        except Exception:  # noqa: BLE001 — classifier is advisory
            shape = "?"
        by_shape[shape].append(len(exp))
        by_items[need.items].append(len(exp))
        by_knobs[f"anchored={need.anchored}"].append(len(exp))
        by_knobs[f"yes_no={need.is_yes_no}"].append(len(exp))
        by_knobs[f"asks_list={need.asks_list}"].append(len(exp))

    print("\n|expected refs| by engine shape (classify_question):")
    print(f"  {'shape':<28} {'n':>3} {'mean':>6} {'median':>6}  dist")
    for shape, vals in sorted(by_shape.items(), key=lambda x: -len(x[1])):
        dist = Counter(vals)
        print(f"  {shape:<28} {len(vals):>3} {_mean(vals):>6.2f} {_median(vals):>6.1f}  "
              f"{dict(sorted(dist.items()))}")

    print("\n|expected refs| by answer_need.items:")
    for items, vals in sorted(by_items.items()):
        dist = Counter(vals)
        print(f"  items={items:<3} n={len(vals):>3} mean={_mean(vals):>5.2f}  {dict(sorted(dist.items()))}")

    print("\n|expected refs| by shape knob:")
    for knob, vals in sorted(by_knobs.items()):
        print(f"  {knob:<16} n={len(vals):>3} mean={_mean(vals):>5.2f} median={_median(vals):>4.1f}")

    # ---- 2. our answer length vs the reference, on the live boards ----------
    for mode, ckpt in ARMS:
        path = REPO / "evals" / "bench" / "results" / ckpt
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        over, at_or_under = 0, 0
        ratios, ac_scores, need_err = [], [], []
        for r in rows:
            g = gold.get(r["id"])
            if not g:
                continue
            ref_len = len((g.get("reference_answer") or "").strip())
            ans = (r.get("pred_answer") or "").strip()
            if not ref_len or not ans:
                continue
            ratio = len(ans) / ref_len
            ratios.append(ratio)
            ac_scores.append(min(1.0, ref_len / len(ans)))
            over += ratio > 1.0
            at_or_under += ratio <= 1.0
            need = answer_need(g.get("question") or "")
            need_err.append(need.target_chars - ref_len)
        print(f"\n=== {mode.upper()} (n={len(ratios)}) ===")
        print(f"  ans/reference length ratio: mean {_mean(ratios):.2f} median {_median(ratios):.2f} "
              f"min {min(ratios):.2f} max {max(ratios):.2f}")
        print(f"  rows over the reference length: {over}/{over + at_or_under} "
              f"({over / (over + at_or_under) * 100:.0f}%)")
        print(f"  ans_conc if every row hit the reference length exactly: 100.00 "
              f"(shipped mean {_mean(ac_scores) * 100:.2f})")
        print(f"  answer_need target_chars minus reference chars: "
              f"mean {_mean(need_err):+.0f} median {_median(need_err):+.0f} "
              f"(target within 20% of the reference on "
              f"{sum(1 for e in need_err if abs(e) <= 0.2 * (e + 0)) / len(need_err) * 100:.0f}%)")

    # ---- 3. a shape-conditioned citation budget, priced --------------------
    print("\nCitation-cap candidates (>= 90% of rows keep |expected| <= cap):")
    for shape, vals in sorted(by_shape.items(), key=lambda x: -len(x[1])):
        for cap in (1, 2, 3):
            keep = sum(1 for v in vals if v <= cap) / len(vals) * 100
            if keep >= 90:
                print(f"  {shape:<28} cap={cap} keeps {keep:.0f}% of rows")
                break
    for items, vals in sorted(by_items.items()):
        for cap in (1, 2, 3):
            keep = sum(1 for v in vals if v <= cap) / len(vals) * 100
            if keep >= 90:
                print(f"  items={items:<3} cap={cap} keeps {keep:.0f}%")
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

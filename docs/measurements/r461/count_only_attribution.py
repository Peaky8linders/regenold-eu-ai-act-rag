"""R461 count-only gate -- the attribution the board alone cannot give.

The R460 wrapper gate had to attribute its non-conciseness deltas away row by row,
because a wrapper arm can degrade differently on the same question (the tunnel
returned a 1-token completion on B 17 times against A's 5, and each of those
spends a Bedrock fallback and sometimes ships the deterministic Stage-1 draft).
This round draws a SECOND OFF arm with the same prompt bytes as the R460 OFF arm,
which turns that footnote into a measurement:

1. **The noise floor.** R461-OFF vs R460-OFF is a pure re-draw: byte-identical
   inputs (`verify_byte_identity.py` proves the prompt bytes; both checkpoints
   carry `hard_preamble_digest cb85452c9c04`), so every delta on that pair is
   draw + transport noise. No gate delta is readable until it is outside this
   band - which is the whole point of spending the second draw.
2. **The gate.** R461-COUNT vs R461-OFF, on all rows and on the same-leg subset.
3. **The R460 verdict, recomputed** through this script's axes, so all the pairs
   are read on one method.
4. **count-only against the full block**, on the same protocol.

The paired statistics are literally ``paired_ab``'s own functions, imported, so
these numbers cannot drift from the decision instrument's.

Run (module form, so the WORKTREE's evals/ is imported):
    ../../.venv/Scripts/python.exe -m docs.measurements.r461.count_only_attribution
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "evals" / "bench" / "results"
SCORES = REPO / "docs" / "measurements" / "r388"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ARMS = {
    "R460-OFF": "r460-tunnel-off-s3",
    "R460-FULL": "r460-tunnel-on-s3",
    "R461-OFF": "r461-countoff-s3",
    "R461-COUNT": "r461-counton-s3",
}

PAIRS = [
    ("THE GATE  R461-COUNT vs R461-OFF", "R461-OFF", "R461-COUNT"),
    ("NOISE FLOOR  R461-OFF vs R460-OFF (byte-identical prompts)",
     "R460-OFF", "R461-OFF"),
    ("R460 verdict recomputed  R460-FULL vs R460-OFF", "R460-OFF", "R460-FULL"),
    ("count-only vs the full block  R461-COUNT vs R460-FULL",
     "R460-FULL", "R461-COUNT"),
]

#: Transport-degradation events, counted in the arm's own run log. The R460
#: WRAPPER-CONFIRM note published 5/2 for its OFF arm and 17/8 for its ON arm;
#: this census reproduces those numbers exactly, which is what licenses reading
#: the same keys off the two R461 logs.
EVENTS = {
    "degenerate": "wrapper_degenerate_completion",
    "persisted": "wrapper_degenerate_completion_persisted",
    "bedrock_fallback": "bedrock_auto_fallback",
    "stage1_deterministic": "tail repair failed",
}

AXES = [
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
]


def _ckpt(label: str) -> dict[str, dict]:
    path = RESULTS / f"official-{label}-hard.ckpt.jsonl"
    if not path.exists():  # an arm still in flight
        return {}
    return {
        r["id"]: r
        for r in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _scored(label: str) -> dict[str, dict]:
    data = json.loads((SCORES / f"score-{label}-hard.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in data["rows"]}


def _payload(label: str) -> dict:
    return json.loads((SCORES / f"score-{label}-hard.json").read_text(encoding="utf-8"))


def _event_census(label: str) -> dict[str, int]:
    path = RESULTS / f"{label}.log"
    raw = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return {k: raw.count(v) for k, v in EVENTS.items()}


def _legs(label: str) -> dict[str, str]:
    return {
        i: str((r.get("provenance") or {}).get("stage2_served_by") or "")
        for i, r in _ckpt(label).items()
    }


def main() -> int:
    from evals.official.paired_ab import (  # noqa: PLC0415
        _bootstrap_ci,
        _gold_dropped_head,
        _mean,
        _row_axis,
    )

    legs = {a: _legs(l) for a, l in ARMS.items()}
    # A gate still in flight has checkpoints but no scores; say what is missing
    # rather than dying on the first unpriced arm.
    scored = {a for a, l in ARMS.items() if (SCORES / f"score-{l}-hard.json").exists()}
    if scored != set(ARMS):
        print(f"== not yet scored: {sorted(set(ARMS) - scored)}")
    rows = {a: _scored(ARMS[a]) for a in scored}
    pays = {a: _payload(ARMS[a]) for a in scored}

    print("== transport degradation, counted in each arm's run log")
    for arm, label in ARMS.items():
        c = _event_census(label)
        print(f"  {arm:<11} degenerate={c['degenerate']:>2} (persisted "
              f"{c['persisted']:>2})  bedrock_fallback={c['bedrock_fallback']:>2}  "
              f"stage1_deterministic={c['stage1_deterministic']:>2}")

    print("\n== levels (score payload)")
    for arm, p in pays.items():
        ax = p["axes"]
        print(f"  {arm:<11} ans_conc={ax['ans_conciseness']:6.2f} "
              f"ref_conc={ax['ref_conciseness']:6.2f} overall={ax['overall']:6.2f} "
              f"answers={ax['_mean_answer_chars']:7.1f} "
              f"refs/row={ax['_mean_refs_per_row']:5.2f} "
              f"latency={ax['_mean_latency_s']:5.1f}s")
        lc = (p.get("length_controlled") or {}).get("axes") or {}
        if lc:
            print(f"              LC ans_loose={lc.get('ans_correctness_loose', float('nan')):6.2f} "
                  f"ans_strict={lc.get('ans_correctness_strict', float('nan')):6.2f} "
                  f"({(p.get('length_controlled') or {}).get('answers_cut')} answers cut)")

    for title, a, b in PAIRS:
        if a not in rows or b not in rows:
            continue
        shared = sorted(set(rows[a]) & set(rows[b]))
        if not shared:
            continue
        a_leg, b_leg = legs[a], legs[b]
        subsets = {
            "all rows": lambda _i: True,  # noqa: E731
            "same leg label": lambda i: a_leg.get(i) == b_leg.get(i),  # noqa: E731
            "PRIMARY both": lambda i: a_leg.get(i) == b_leg.get(i) == "primary",  # noqa: E731
        }
        for name, keep in subsets.items():
            ids = [i for i in shared if keep(i)]
            if not ids:
                continue
            print(f"\n== {title}\n   [{name}]  n={len(ids)}")
            for axis in AXES:
                pa, pb = [], []
                for i in ids:
                    x, y = _row_axis(rows[a][i], axis), _row_axis(rows[b][i], axis)
                    if x is None or y is None:
                        continue
                    pa.append(x)
                    pb.append(y)
                if not pa:
                    continue
                d = [y - x for x, y in zip(pa, pb)]
                lo, hi = _bootstrap_ci(d)
                star = "*" if (lo > 0 or hi < 0) else " "
                print(f"   {axis:<24}{star} {_mean(pa):7.2f} -> {_mean(pb):7.2f}  "
                      f"delta={_mean(d):+7.2f}  CI[{lo:+7.2f},{hi:+7.2f}]  "
                      f"B>{sum(1 for v in d if v > 0)} A>{sum(1 for v in d if v < 0)}")
            for key, fmt in (("answer_chars", "{:8.1f}"), ("refs", "{:8.1f}")):
                if key == "refs":
                    va = [float(len(rows[a][i].get("refs") or [])) for i in ids]
                    vb = [float(len(rows[b][i].get("refs") or [])) for i in ids]
                else:
                    va = [float(rows[a][i].get("answer_chars") or 0) for i in ids]
                    vb = [float(rows[b][i].get("answer_chars") or 0) for i in ids]
                d = [y - x for x, y in zip(va, vb)]
                lo, hi = _bootstrap_ci(d)
                star = "*" if (lo > 0 or hi < 0) else " "
                print(f"   {key:<24}{star} " + fmt.format(_mean(va)) + " -> "
                      + fmt.format(_mean(vb)) + f"  delta={_mean(d):+8.1f}  "
                      f"CI[{lo:+7.1f},{hi:+7.1f}]  B_up={sum(1 for v in d if v > 0)}/{len(ids)}")
            ga = [i for i in ids
                  if _gold_dropped_head(rows[a][i].get("expected_refs"), rows[a][i].get("refs"))]
            gb = [i for i in ids
                  if _gold_dropped_head(rows[b][i].get("expected_refs"), rows[b][i].get("refs"))]
            new = [i for i in gb if i not in ga]
            print(f"   gold head dropped: A={len(ga)} B={len(gb)} new_in_B={new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

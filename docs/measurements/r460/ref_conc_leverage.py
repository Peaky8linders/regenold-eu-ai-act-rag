"""R460 — price the Ref Conciseness axis against the two live Cohere boards.

``rubric.reference_conciseness`` is ``min(1, |expected| / |provided|)``: a PURE
count ratio, one-sided (citing fewer than the key is free).  So the axis is a
function of the *number* of refs emitted per row, not of which ones - and the
two correctness axes only care that every expected ref is matched by *some*
emitted ref.  That makes \"drop the allowances\" a different trade from every
ref-list transform R442 falsified: those tried to reorder/rewrite and lost gold.

This script is offline and read-only.  It reproduces the reference axes of a
scored board from its checkpoint (same gold key, same R388 grain deepener as
``score_arm``), then re-prices them under policies that can only *remove* refs:

  shipped        the recorded list, unchanged
  cap@K          keep the first K refs in ENGINE ORDER (K = 1, 2, 3)
  cap@E          keep the first E = |expected| refs  (an oracle on the COUNT
                 only - a policy could estimate this from grounded units)
  oracle         keep only refs that match a key ref (upper bound: rc -> 100,
                 correctness axes provably unchanged)

Overall is the geometric mean of the eight axes with the answer, tone and speed
axes FROZEN at their scored values, so every delta is attributable to refs.

    ../../.venv/Scripts/python.exe docs/measurements/r460/ref_conc_leverage.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from evals.official.rubric import (  # noqa: E402
    _clean,
    _is_descendant,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)
from evals.official.score_arm import build_rows, load_ckpt, load_gold  # noqa: E402

OUT = REPO / "docs" / "measurements" / "r460"
SCORES = REPO / "docs" / "measurements" / "r388"
ARMS = [
    ("hard", "r460-cohere-hard-s3", "official-r460-cohere-hard-s3-hard.ckpt.jsonl"),
    ("easy", "r460-cohere-easy-s3", "official-r460-cohere-easy-s3-easy.ckpt.jsonl"),
]


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _matched(expected: list[str], provided: list[str]) -> set[str]:
    """Expected refs that some provided ref satisfies (the loose predicate)."""
    exp = list(dict.fromkeys(_clean(expected)))
    got = list(_clean(provided))
    return {e for e in exp if any(_is_descendant(p, e) for p in got)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from app.routes.regenold import _deepen_ref_grain  # noqa: PLC0415

    gold = load_gold()
    for mode, label, ckpt in ARMS:
        ckpt_path = REPO / "evals" / "bench" / "results" / ckpt
        rows = build_rows(load_ckpt(ckpt_path), gold)
        changed = 0
        for r in rows:
            before = list(r["references"])
            r["references"] = _deepen_ref_grain(
                before, r.get("question") or "", r.get("answer") or ""
            )
            changed += r["references"] != before
        scored = json.loads((SCORES / f"score-{label}-{mode}.json").read_text(encoding="utf-8"))
        axes = scored["axes"]
        frozen = {
            "ans_loose": axes["ans_correctness_loose"],
            "ans_strict": axes["ans_correctness_strict"],
            "ans_conc": axes["ans_conciseness"],
            "tone": axes["regulatory_tone"],
            "speed": axes["resp_speed"],
        }

        print(f"\n=== {mode.upper()}  ({label}, n={len(rows)}, redeepened={changed}) ===")
        print(f"scored axes: ref_loose {axes['ref_correctness_loose']:.2f} "
              f"ref_strict {axes['ref_correctness_strict']:.2f} "
              f"ref_conc {axes['ref_conciseness']:.2f} overall {axes['overall']:.2f}")

        def price(name: str, chooser, rows=rows, frozen=frozen) -> None:
            """Price one ref-list policy; axis values bound at definition time."""
            rl, rs, rc, n_ref = [], [], [], 0
            for r in rows:
                refs = chooser(r)
                rc_v = reference_conciseness(refs, r.get("expected_refs") or [])
                if rc_v is None:
                    continue
                n_ref += 1
                rl.append(reference_correctness_loose(refs, r.get("expected_refs") or []))
                rs.append(reference_correctness_strict(refs, r.get("expected_refs") or []))
                rc.append(rc_v)
            rl_m, rs_m, rc_m = _mean(rl) * 100, _mean(rs) * 100, _mean(rc) * 100
            prod = (rl_m * rs_m * rc_m * frozen["ans_loose"] * frozen["ans_strict"]
                    * frozen["ans_conc"] * frozen["tone"] * frozen["speed"])
            overall = prod ** (1 / 8)
            print(f"  {name:<10} ref_loose {rl_m:6.2f}  ref_strict {rs_m:6.2f}  "
                  f"ref_conc {rc_m:6.2f}  overall {overall:6.2f}  (n_ref={n_ref})")

        price("shipped", lambda r: r["references"])
        for k in (1, 2, 3):
            price(f"cap@{k}", lambda r, k=k: r["references"][:k])
        price("cap@E", lambda r: r["references"][: len(_clean(r.get("expected_refs") or []))] or r["references"][:1])
        price("oracle", lambda r: [p for p in r["references"]
                                   if _matched(r.get("expected_refs") or [], [p])] or r["references"][:1])

        # Where the leverage sits: supplied vs expected counts.
        buckets: dict[tuple[int, int], int] = {}
        worst: list[tuple[int, str, int, int, float]] = []
        for r in rows:
            exp = _clean(r.get("expected_refs") or [])
            if not exp:
                continue
            prov = _clean(r["references"])
            buckets[(len(exp), len(prov))] = buckets.get((len(exp), len(prov)), 0) + 1
            worst.append((len(prov) - len(exp), r["id"], len(exp), len(prov),
                          reference_conciseness(r["references"], exp) or 0.0))
        print("  counts (expected, supplied) -> rows:")
        for (e, p), n in sorted(buckets.items()):
            print(f"    E={e} S={p}: {n}")
        worst.sort(reverse=True)
        print("  biggest excess (S-E, id, E, S, shipped_rc):")
        for row in worst[:8]:
            print(f"    {row[0]:+d} {row[1]}  E={row[2]} S={row[3]}  rc={row[4]:.2f}")
        oversupplied = [w for w in worst if w[0] > 0]
        total_expected = sum(w[2] for w in worst)
        total_supplied = sum(w[3] for w in worst)
        print(f"  rows over-supplied: {len(oversupplied)}/{len(worst)}; "
              f"total supplied {total_supplied} vs total expected "
              f"{total_expected} ({total_supplied / total_expected:.2f}x)")

    print("\nNote: the speed axis is frozen, so `overall` is scenario arithmetic on "
          "the scored board, not a re-score.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

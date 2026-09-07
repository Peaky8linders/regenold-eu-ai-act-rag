"""R388 - zero-variance gate for the multi-level grain deepener.

``_deepen_ref_grain`` is a PURE function of (references, question, answer), so
an A/B of it needs no live generation at all: replay the recorded r387 live
capture through each depth setting and the only thing that differs is the
transform.  That removes GENERATION variance entirely -- and, unlike the R381
wire-cap simulation that reversed verdict as n grew, it also runs at the full
n=110 of the official batch rather than a subsample, so SAMPLING variance is
not being hidden either.

What it checks, and why each check is the right one
--------------------------------------------------
* ``gold_dropped_head``   MUST be +0.  Deepening never changes a HEAD, so a
  non-zero delta here means the implementation is broken, not that the lever
  is bad.  It is a tripwire, not a trade-off.
* ``ref_conciseness``     MUST be unchanged.  The axis is a pure COUNT ratio
  (R381) and deepening rewrites coordinates without adding or removing any.
* ``ref_loose``           MUST be unchanged.  Scored at head level.
* ``ref_strict``          the axis under test.

Scored under BOTH matching rules, because the July anchor pins the evaluator's
key at ~60% sub-point but cannot separate exact matching from descendant
credit.  A depth setting only ships if it wins under BOTH -- so the decision
does not depend on the half of the calibration that is still uncertain.

    .venv/Scripts/python.exe -m evals.official.gate_grain_depth
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
sys.path.insert(0, str(REPO))

from evals.official.rubric import (  # noqa: E402
    _clean,
    _heads,
    ref_head,
    reference_conciseness,
    reference_correctness_loose,
)

CAPTURES = {
    "easy": REPO / "evals" / "bench" / "results" / "official-r387_live_easy-easy.ckpt.jsonl",
    "hard": REPO / "evals" / "bench" / "results" / "official-r387_live_hard-hard.ckpt.jsonl",
}
MINGOLD = REPO / "docs" / "measurements" / "r386" / "minimal-gold-probe-set-n110.jsonl"
REFKEY = REPO / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"


def strict(pred, exp, rule: str):
    e, p = _clean(exp), _clean(pred)
    if not e:
        return None
    if rule == "exact":
        ok = lambda x: x in p  # noqa: E731
    else:  # descendant credit: a MORE precise prediction still identifies it
        ok = lambda x: any(y == x or y.startswith(x + ".") for y in p)  # noqa: E731
    return sum(1 for x in e if ok(x)) / len(e)


def gold_dropped_heads(pred, exp) -> int:
    return len([h for h in _heads(exp) if h not in set(_heads(pred))])


def load_key() -> dict[str, list[str]]:
    """Prefer the R388 grain-calibrated key; fall back to R386's."""
    if REFKEY.exists():
        out = {}
        for line in REFKEY.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["id"]] = [] if r.get("unstable") else (r.get("expected") or [])
        if out:
            print(f"key: {REFKEY.name} (R388 grain-calibrated)")
            return out
    out = {}
    for line in MINGOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = [] if r.get("unstable") else (r.get("expected") or [])
    print(f"key: {MINGOLD.name} (R386; ~1.5x finer than the evaluator's, so")
    print("     ref_strict reads as a pessimistic FLOOR under it)")
    return out


def main() -> int:
    from app.routes import regenold as R

    key = load_key()
    depths = [1, 2, 3]
    print()
    for mode, path in CAPTURES.items():
        rows = [
            json.loads(x)
            for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip()
        ]
        print("=" * 92)
        print(f"{mode.upper()}  n={len(rows)}  (replay of the r387 live capture; zero generation variance)")
        print("=" * 92)
        print(
            f"{'depth':>6}{'refs/row':>10}{'%subpoint':>11}"
            f"{'refL':>8}{'refConc':>9}{'refS(exact)':>13}{'refS(desc)':>12}{'goldDropHead':>14}"
        )
        base = None
        for d in depths:
            os.environ["REGENOLD_REF_GRAIN_DEPTH"] = str(d)
            n_ref = sub = tot = 0
            L, C, Se, Sd, G = [], [], [], [], 0
            for r in rows:
                shipped = r.get("pred_refs") or r.get("references") or r.get("refs") or []
                ans = r.get("pred_answer") or r.get("answer") or ""
                out = R._deepen_ref_grain(list(shipped), r.get("question") or "", ans)
                cl = _clean(out)
                n_ref += len(cl)
                sub += sum(1 for x in cl if "." in x)
                tot += len(cl)
                exp = key.get(r["id"]) or []
                if not exp:
                    continue
                L.append(reference_correctness_loose(out, exp))
                C.append(reference_conciseness(out, exp))
                Se.append(strict(out, exp, "exact"))
                Sd.append(strict(out, exp, "desc"))
                G += gold_dropped_heads(out, exp)
            m = lambda x: 100 * sum(x) / len(x)  # noqa: E731
            row = (d, n_ref / len(rows), 100 * sub / max(1, tot), m(L), m(C), m(Se), m(Sd), G)
            if base is None:
                base = row
            print(
                f"{row[0]:>6}{row[1]:>10.2f}{row[2]:>11.1f}"
                f"{row[3]:>8.1f}{row[4]:>9.1f}{row[5]:>13.1f}{row[6]:>12.1f}{row[7]:>14d}"
            )
        print()
    os.environ.pop("REGENOLD_REF_GRAIN_DEPTH", None)
    print("PASS CONDITION: gold_dropped_head, refL and refConc identical across all")
    print("depths (structural invariants), and refS improves under BOTH matching rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

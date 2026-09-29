"""R452/R452b/R452c — the grain-deepener guards, measured on every recorded live answer.

Counterfactual method (from the R452c review): every graded turn's wire references
are folded onto their heads, and the heads are re-deepened through the real
``_deepen_ref_grain`` with ALL R452-family guards off (the pre-R452 deepener) and
with the flags at their defaults. Both arms see the same question, answer and
heads, so the difference is the guards alone. Scored with the real
``evals.official.rubric`` against the reconstructed gold keys. The earlier replay
only re-examined references the deepener had produced and could not see gold
leaves the enumeration veto removed from recorded bare heads (rg_093, rg_029).

Per-coordinate accounting: a coordinate the guards change is a WRONG pick removed
when it met no gold key more precisely than its head, and a CORRECT pick lost when
it did. The ``live`` arm leaves heads whose sub-points the answer's own prose names
to the prose: on the live path ``_surface_prose_subpoints`` puts those leaves on the
wire BEFORE the deepener runs, so the deepener never decides them there.

    py -3.12 docs/measurements/r452/grain_question_support_replay.py RESULTS_DIR [--only FLAG]

RESULTS_DIR is required (``evals/bench/results`` is gitignored and holds the recorded
live checkpoints; a worktree has none). The run refuses fewer than 1,000 turns.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from app.routes import regenold as R  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    ref_head,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
#: every deepener-side guard of the R452 family; OFF pins them all to 0
FLAGS = (
    "REGENOLD_GRAIN_QUESTION_SUPPORT",
    "REGENOLD_GRAIN_DISCRIMINATING_SUPPORT",
    "REGENOLD_GRAIN_SUBJECT_HEAD",
    "REGENOLD_GRAIN_ANNEX_I_ACT_SUBJECT",
)
MIN_TURNS = 1000


def _graded(row: dict) -> tuple[str, list[str]]:
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return row.get("pushback_answer") or "", [str(x) for x in row.get("pushback_refs") or []]
    return row.get("pred_answer") or "", [str(x) for x in row.get("pred_refs") or []]


ONLY: str | None = None  # --only FLAG: the OFF arm switches off just that flag


def _arm(on: bool) -> None:
    for f in ([ONLY] if ONLY else FLAGS):
        if on:
            os.environ.pop(f, None)  # code default
        else:
            os.environ[f] = "0"


def main() -> int:
    global ONLY
    if len(sys.argv) < 2:
        raise SystemExit("usage: grain_question_support_replay.py RESULTS_DIR [--only FLAG]")
    results = Path(sys.argv[1])
    if "--only" in sys.argv:
        ONLY = sys.argv[sys.argv.index("--only") + 1]
    gold = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g.get("expected_refs") or []
    seen: set[tuple] = set()
    rows = []
    for path in sorted(results.glob("official-*.ckpt.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                row = None
            if not row:
                continue
            rid = str(row.get("id"))
            answer, refs = _graded(row)
            if rid not in gold or not gold[rid] or not answer or not refs:
                continue
            key = (rid, answer, tuple(refs))
            if key not in seen:
                seen.add(key)
                rows.append((rid, row.get("question") or "", answer, refs))
    if len(rows) < MIN_TURNS:
        raise SystemExit(f"only {len(rows)} graded turns under {results}; need >= {MIN_TURNS}")

    axes = {arm: {"loose": [], "strict": [], "conc": []} for arm in ("off", "on", "live")}
    changed = wrong_removed = gold_lost = gold_gained = head_bad = 0
    live_lost = 0
    lost_rows: dict[str, int] = {}
    live_lost_rows: dict[str, int] = {}
    for rid, question, answer, refs in rows:
        heads: list[str] = []
        for r in refs:
            h = ref_head(r) or r
            if h not in heads:
                heads.append(h)
        wires = {}
        for arm, on in (("off", False), ("on", True)):
            _arm(on)
            wires[arm] = R._deepen_ref_grain(list(heads), question, answer)
        exp = gold[rid]
        prose_named = {" ".join(str(k).split()).lower() for k in R._prose_named_subpoints(answer)}
        wires["live"] = []
        for h, a, b in zip(heads, wires["off"], wires["on"], strict=True):
            by_prose = h.lower() in prose_named
            wires["live"].append(a if by_prose else b)
            if a == b:
                continue
            changed += 1
            before = reference_correctness_strict([a], exp) or 0.0
            after = reference_correctness_strict([b], exp) or 0.0
            if after < before:
                gold_lost += 1
                lost_rows[rid] = lost_rows.get(rid, 0) + 1
                if not by_prose:
                    live_lost += 1
                    live_lost_rows[rid] = live_lost_rows.get(rid, 0) + 1
            elif after > before:
                gold_gained += 1
            else:
                wrong_removed += 1
        if {ref_head(x) for x in wires["off"]} != {ref_head(x) for x in wires["on"]}:
            head_bad += 1
        for arm in ("off", "on", "live"):
            for axis, fn in (("loose", reference_correctness_loose),
                             ("strict", reference_correctness_strict),
                             ("conc", reference_conciseness)):
                v = fn(wires[arm], exp)
                if v is not None:
                    axes[arm][axis].append(v)
    _arm(True)
    print(f"graded turns with gold: {len(rows)} (unique answer+refs)")
    print(f"coordinates changed by the guards: {changed}")
    print(f"  wrong picks removed: {wrong_removed}   correct picks lost: {gold_lost}   gained: {gold_gained}")
    print(f"  rows losing a correct pick: {dict(sorted(lost_rows.items()))}")
    print(f"  correct picks lost where the answer's prose does not name the point: {live_lost}"
          f" {dict(sorted(live_lost_rows.items()))}")
    print(f"head-set violations: {head_bad}")
    for axis in ("loose", "strict", "conc"):
        a, b, c = (100 * sum(axes[k][axis]) / len(axes[k][axis]) for k in ("off", "on", "live"))
        print(f"  ref_{axis:6}  off {a:6.2f}   on {b:6.2f} ({b - a:+.2f})   live {c:6.2f} ({c - a:+.2f}) pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

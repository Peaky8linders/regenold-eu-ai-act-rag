"""R388 - score a captured arm against the reconstructed official rubric.

Takes a checkpoint of live answers plus the reconstructed gold
(:mod:`evals.official.build_gold`), judges the answer and tone axes
(:mod:`evals.official.judge`), and reports all eight axes plus the geometric
mean, alongside the official 2026-08-25 figures for the same mode.

The judged verdicts are CACHED per (arm-label, question id, sha of the answer),
so re-scoring an arm costs nothing and a re-run after a code change only pays
for the rows whose answer actually changed.  That is what makes an iterate-and-
measure loop affordable over a single wrapper.

    .venv/Scripts/python.exe -m evals.official.score_arm \\
        --ckpt evals/bench/results/official-r387_live_easy-easy.ckpt.jsonl \\
        --label r387-easy --mode easy
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from evals.official.judge import judge_rows  # noqa: E402
from evals.official.rubric import AXIS_ORDER, _clean, score_rows  # noqa: E402

GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
CACHE = REPO / "docs" / "measurements" / "r388" / "judge_cache.jsonl"
OUT_DIR = REPO / "docs" / "measurements" / "r388"

# The printed figures, for orientation only.  Never quote a number from this
# module AS an official number -- the criteria and reference answers are
# reconstructed (see evals/official/__init__.py).
OFFICIAL = {
    "easy": {
        "us": dict(zip(AXIS_ORDER, [89.7, 81.2, 51.9, 89.4, 68.3, 50.4, 99.1, 87.6])),
        "frontier_2026": dict(zip(AXIS_ORDER, [94.4, 89.1, 67.9, 96.1, 78.5, 51.9, 100.0, 81.8])),
        "baseline_2025": dict(zip(AXIS_ORDER, [83.8, 70.9, 51.1, 79.9, 52.0, 48.7, 99.1, 95.3])),
        "overall": {"us": 75.1, "frontier_2026": 80.9, "baseline_2025": 70.1},
    },
    "hard": {
        "us": dict(zip(AXIS_ORDER, [89.9, 80.0, 45.2, 89.5, 70.7, 49.8, 96.1, 85.7])),
        "frontier_2026": dict(zip(AXIS_ORDER, [92.0, 84.8, 71.8, 94.6, 74.1, 58.5, 100.0, 86.7])),
        "baseline_2025": dict(zip(AXIS_ORDER, [87.6, 76.7, 58.8, 82.7, 55.4, 56.8, 99.7, 95.9])),
        "overall": {"us": 73.4, "frontier_2026": 81.7, "baseline_2025": 74.8},
    },
}


def load_gold() -> dict[str, dict]:
    if not GOLD.exists():
        raise SystemExit(f"missing reconstructed gold: {GOLD}\nrun evals.official.build_gold first")
    out = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            out[r["id"]] = r
    return out


def _key(qid: str, answer: str) -> str:
    return f"{qid}:{hashlib.sha256((answer or '').encode('utf-8')).hexdigest()[:16]}"


def load_cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    out = {}
    for line in CACHE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                r = json.loads(line)
                out[r["key"]] = r["verdict"]
            except Exception:  # noqa: BLE001
                pass
    return out


def load_ckpt(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        rows.append(
            {
                "id": r.get("id"),
                "question": r.get("question") or "",
                "answer": r.get("pred_answer") or r.get("answer") or "",
                "references": r.get("pred_refs") or r.get("references") or [],
                "latency_s": float(r.get("latency_ms") or 0.0) / 1000.0,
                "difficulty": r.get("difficulty") or r.get("difficulty_category"),
            }
        )
    return rows


def build_rows(ckpt_rows: list[dict], gold: dict[str, dict]) -> list[dict]:
    out = []
    for r in ckpt_rows:
        g = gold.get(r["id"])
        if not g:
            continue
        out.append(
            {
                **r,
                "criteria_text": g["criteria"],
                "criteria": g["criteria"],  # judge_row replaces this with booleans
                "reference_answer": g["reference_answer"],
                "expected_refs": g.get("expected_refs") or [],
                "criteria_unstable": g.get("criteria_unstable", False),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--mode", choices=["easy", "hard"], required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    gold = load_gold()
    rows = build_rows(load_ckpt(Path(a.ckpt)), gold)
    if a.limit:
        rows = rows[: a.limit]
    if not rows:
        raise SystemExit("no rows matched the reconstructed gold")

    cache = load_cache()
    todo, cached = [], []
    for r in rows:
        v = cache.get(_key(r["id"], r["answer"]))
        if v and len(v.get("criteria") or []) == len(r["criteria_text"]):
            cached.append({**r, **v})
        else:
            todo.append(r)
    print(f"{len(rows)} rows: {len(cached)} cached, {len(todo)} to judge")

    judged = judge_rows(todo, workers=a.workers, repeats=a.repeats) if todo else []
    if judged:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE.open("a", encoding="utf-8") as fh:
            for j in judged:
                fh.write(
                    json.dumps(
                        {
                            "key": _key(j["id"], j["answer"]),
                            "verdict": {
                                k: j[k]
                                for k in (
                                    "criteria",
                                    "tone_ok",
                                    "_judge_runs",
                                    "_criteria_rate_min",
                                    "_criteria_rate_max",
                                    "_judge_errors",
                                )
                                if k in j
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    all_rows = cached + judged
    by_id = {r["id"]: r for r in all_rows}
    ordered = [by_id[r["id"]] for r in rows if r["id"] in by_id]

    res = score_rows(ordered)
    ref = OFFICIAL[a.mode]

    print()
    print("=" * 88)
    print(f"R388 reconstructed official rubric  |  arm={a.label}  mode={a.mode}  n={res['n']}")
    print("=" * 88)
    hdr = f"{'axis':<26}{'THIS ARM':>10}{'us(off)':>10}{'2026 frontier':>15}{'gap->frontier':>15}"
    print(hdr)
    print("-" * 88)
    for k in AXIS_ORDER:
        gap = res[k] - ref["frontier_2026"][k]
        mark = "  BEATS" if gap >= 0 else ""
        print(
            f"{k:<26}{res[k]:>10.1f}{ref['us'][k]:>10.1f}"
            f"{ref['frontier_2026'][k]:>15.1f}{gap:>+15.1f}{mark}"
        )
    print("-" * 88)
    gap_o = res["overall"] - ref["overall"]["frontier_2026"]
    print(
        f"{'OVERALL (geo mean)':<26}{res['overall']:>10.1f}"
        f"{ref['overall']['us']:>10.1f}{ref['overall']['frontier_2026']:>15.1f}{gap_o:>+15.1f}"
        + ("  BEATS" if gap_o >= 0 else "")
    )
    print()
    print("diagnostics:")
    for k in (
        "_ans_loose_macro",
        "_mean_answer_chars",
        "_mean_reference_chars",
        "_mean_refs_per_row",
        "_mean_expected_per_row",
        "_mean_latency_s",
        "n_ref_scored",
    ):
        print(f"  {k:<26}{res[k]}")
    unstable = sum(1 for r in ordered if r.get("criteria_unstable"))
    print(f"  {'gold rows flagged unstable':<26}{unstable}")
    print()
    print("NOTE: criteria and reference answers are RECONSTRUCTED, not the evaluator's.")
    print("      Compare ARMS under this instrument; do not read a number as an official score.")

    out = OUT_DIR / f"score-{a.label}-{a.mode}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": a.label,
        "mode": a.mode,
        "ckpt": str(a.ckpt),
        "axes": res,
        "official_reference": ref,
        "rows": [
            {
                "id": r["id"],
                "criteria_text": r["criteria_text"],
                "criteria": r.get("criteria"),
                "n_criteria_passed": sum(1 for c in (r.get("criteria") or []) if c),
                "tone_ok": r.get("tone_ok"),
                "answer_chars": len(r.get("answer") or ""),
                "reference_chars": len(r.get("reference_answer") or ""),
                "refs": _clean(r.get("references") or []),
                "expected_refs": r.get("expected_refs") or [],
                "latency_s": r.get("latency_s"),
            }
            for r in ordered
        ],
    }
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

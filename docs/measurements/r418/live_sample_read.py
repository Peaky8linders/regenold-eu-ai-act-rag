"""R418 — read a LIVE stratified sample: the board, and whether the fixes fired.

``run_hard_sample_r297 --frac 0.4`` runs 112 requests (44 multi-turn questions x
2 turns + 24 single-turn HARD) against the deployed service. This module turns
that checkpoint into two things:

1. **The deterministic half of the board** — Ref. Correctness (loose/strict),
   Ref. Conciseness, Ans. Conciseness and Resp. Speed — computed from the
   checkpoint plus the reconstructed gold, with NO judge calls. The judged half
   (Ans. Correctness loose/strict, Regulatory Tone) comes from
   :mod:`evals.official.score_arm`, which shares this same gold loader and
   rubric, so the two halves are the same measurement.

2. **The R417/R418 fix signals**, which no axis reports:

   * *which leg served each answer.* R417 recorded ``stage2_served_by`` in
     ``graph_stats`` and made the route refuse to cache a degraded serve. The
     deployed wire does not expose ``graph_stats``, so the leg is read from the
     ``stage2_model=`` trace note the engine has always written — a ``claude*``
     model is the primary wrapper leg, anything else is the Bedrock fallback.
   * *turn-1 gold head retention across the pushback.* Hard Rule #8 is "drop
     zero gold references"; the way that rule actually breaks is a pushback that
     silently sheds a provision turn 1 had already cited.
   * *the cached-replay signature.* A degraded answer replayed from the engine
     cache returns in ~0.1-0.2 s. With the R417 fix in place a sub-second graded
     answer after a slow turn 1 should only be a genuine deterministic serve.

Deliberately reuses ``score_arm.load_ckpt`` / ``build_rows`` / ``load_gold`` and
the ``rubric`` axis functions rather than re-deriving any of them: a second
implementation of a metric is how two numbers that claim to be the same thing
start disagreeing.

    .venv/Scripts/python.exe -m docs.measurements.r418.live_sample_read \
        --mt-ckpt evals/bench/results/official-r418sense-mt-hard.ckpt.jsonl \
        --st-ckpt evals/bench/results/official-r418sense-st-easy.ckpt.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from evals.official.rubric import (  # noqa: E402
    answer_conciseness,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
    response_speed,
)
from evals.official.score_arm import build_rows, load_ckpt, load_gold  # noqa: E402
from evals.regenold.run_official_batch import _heads, _is_refusal  # noqa: E402

#: The primary leg's models are Claude; the fallback is Qwen on Bedrock.
_WRAPPER_MODEL_PREFIX = "claude"


def leg_of(model: str) -> str:
    """Classify the serving leg from the recorded Stage-2 model name.

    ``""`` is NOT "wrapper" — it means no ``stage2_model=`` note reached the
    trace (curated intercept, Stage-2 skipped, or a response written before the
    note existed), and it is reported separately rather than assumed healthy.
    """
    m = (model or "").strip().lower()
    if not m:
        return "unrecorded"
    return "wrapper" if m.startswith(_WRAPPER_MODEL_PREFIX) else f"fallback:{m}"


def _pct(xs: list[float]) -> float | None:
    return round(100.0 * statistics.fmean(xs), 2) if xs else None


def _pctl(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return round(s[idx], 1)


def deterministic_axes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The five axes that need no judge, composed exactly as ``score_rows`` does."""
    rl, rs, rc = [], [], []
    for r in rows:
        refs, exp = r.get("references") or [], r.get("expected_refs") or []
        rl.append(reference_correctness_loose(refs, exp))
        rs.append(reference_correctness_strict(refs, exp))
        rc.append(reference_conciseness(refs, exp))
    rl = [v for v in rl if v is not None]
    rs = [v for v in rs if v is not None]
    rc = [v for v in rc if v is not None]
    ac = [
        v
        for v in (
            answer_conciseness(r.get("answer", ""), r.get("reference_answer", ""))
            for r in rows
        )
        if v is not None
    ]
    return {
        "n": len(rows),
        "n_ref_scored": len(rl),
        "ref_correctness_loose": _pct(rl),
        "ref_correctness_strict": _pct(rs),
        "ref_conciseness": _pct(rc),
        "ans_conciseness": _pct(ac),
        "resp_speed": _pct([response_speed([float(r.get("latency_s") or 0.0) for r in rows])]),
    }


def fix_signals(raw: list[dict[str, Any]], expected_heads: dict[str, set[str]]) -> dict[str, Any]:
    """Everything the eight axes cannot show about the R417/R418 fixes."""
    legs: dict[str, int] = {}
    refused, errs = 0, 0
    t1_lat, pb_lat = [], []
    t1_chars, pb_chars = [], []
    dropped_total, dropped_rows = 0, []
    instant_graded, changed_rows, conceded_rows = 0, 0, 0
    jaccards: list[float] = []
    salvage_suspects: list[str] = []

    for r in raw:
        rid = str(r.get("id") or "")
        prov = r.get("provenance") or {}
        # R418 — prefer the leg the route named; fall back to the model
        # prefix for checkpoints written before that note existed.
        named = str(prov.get("stage2_served_by") or "")
        leg = named if named else leg_of(str(prov.get("stage2_model") or ""))
        legs[leg] = legs.get(leg, 0) + 1
        ans = str(r.get("pred_answer") or "")
        if _is_refusal(ans):
            refused += 1
        if r.get("error"):
            errs += 1

        t1_lat.append(float(r.get("turn1_latency_ms") or 0) / 1000.0)
        pb_lat.append(float(r.get("pushback_latency_ms") or 0) / 1000.0)
        a1 = str(r.get("turn1_answer") or "")
        t1_chars.append(len(a1))
        pb_chars.append(len(ans))
        graded_ms = float(r.get("pushback_latency_ms") or 0) if a1 else float(
            r.get("turn1_latency_ms") or 0
        )
        if 0 < graded_ms < 1000:
            instant_graded += 1

        pb = r.get("pushback") or {}
        if pb.get("ref_heads_changed"):
            changed_rows += 1
        if pb.get("conceded"):
            conceded_rows += 1
        if isinstance(pb.get("ref_head_jaccard"), (int, float)):
            jaccards.append(float(pb["ref_head_jaccard"]))

        # Hard Rule #8: a head turn 1 cited inside the expected set must survive
        # the pushback.
        exp = expected_heads.get(rid) or set()
        if exp:
            held1 = exp & _heads(r.get("turn1_refs") or [])
            held2 = exp & _heads(r.get("pred_refs") or [])
            lost = held1 - held2
            if lost:
                dropped_total += len(lost)
                dropped_rows.append({"id": rid, "lost": sorted(lost)})
        # A answer this much shorter than turn 1 is the salvage signature.
        if a1 and 0 < len(ans) < 0.4 * len(a1):
            salvage_suspects.append(rid)

    return {
        "n": len(raw),
        "errors": errs,
        "refusal_rate": round(refused / len(raw), 4) if raw else None,
        "leg_mix": legs,
        "gold_head_dropped_total": dropped_total,
        "gold_head_dropped_rows": dropped_rows,
        "ref_heads_changed_rows": changed_rows,
        "conceded_rows": conceded_rows,
        "mean_ref_head_jaccard": round(statistics.fmean(jaccards), 4) if jaccards else None,
        "turn1_latency_s": {"p50": _pctl(t1_lat, 0.5), "p95": _pctl(t1_lat, 0.95),
                            "max": round(max(t1_lat), 1) if t1_lat else None},
        "graded_latency_s": {"p50": _pctl(pb_lat, 0.5), "p95": _pctl(pb_lat, 0.95),
                             "max": round(max(pb_lat), 1) if pb_lat else None},
        "sub_second_graded": instant_graded,
        "turn1_chars_p50": _pctl([float(c) for c in t1_chars], 0.5),
        "graded_chars_p50": _pctl([float(c) for c in pb_chars], 0.5),
        "salvage_suspects": salvage_suspects,
    }


def read_arm(ckpt: Path) -> dict[str, Any]:
    gold = load_gold()
    expected_heads = {
        k: set(_heads(v.get("expected_refs") or [])) for k, v in gold.items()
    }
    raw = [
        json.loads(line)
        for line in ckpt.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scored = build_rows(load_ckpt(ckpt), gold)
    stable = [r for r in scored if not r.get("criteria_unstable")]
    # A transport failure is not a wrong answer. An empty answer scores zero on
    # every axis and would drag a mean that claims to describe answer QUALITY,
    # so the failed rows are reported separately and excluded from the headline —
    # disclosed, never silently dropped (R418: 16/44 multi-turn rows were 422s).
    failed = {str(r.get("id")) for r in raw if r.get("error")}
    served = [r for r in scored if str(r.get("id")) not in failed]
    return {
        "ckpt": str(ckpt),
        "axes_served_rows": deterministic_axes(served),
        "axes_all_rows_incl_transport_failures": deterministic_axes(scored),
        "axes_excl_criteria_unstable": deterministic_axes(stable),
        "n_transport_failures": len(failed),
        "n_criteria_unstable": len(scored) - len(stable),
        "signals": fix_signals(raw, expected_heads),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mt-ckpt", default=None, help="multi-turn (hard) checkpoint")
    ap.add_argument("--st-ckpt", default=None, help="single-turn hard checkpoint")
    ap.add_argument("--out", default=None, help="write the JSON summary here")
    a = ap.parse_args()

    out: dict[str, Any] = {}
    if a.mt_ckpt:
        out["multi_turn_hard"] = read_arm(Path(a.mt_ckpt))
    if a.st_ckpt:
        out["single_turn_hard"] = read_arm(Path(a.st_ckpt))
    if not out:
        raise SystemExit("pass at least one of --mt-ckpt / --st-ckpt")

    for arm, payload in out.items():
        print(f"\n=== {arm} ===")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

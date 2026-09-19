"""R423 — is the need-proportional contract calibrated? (offline, zero API calls)

The lever under test claims one thing: that the ANSWER SHAPE it ships is
proportional to what a question actually engages, where the shipped prompt is
flat. That claim is checkable WITHOUT a live run, because the estimator is
deterministic and the gold carries the ground truth it must track:

* ``criteria`` — the official correctness criteria for the row (the instrument
  that scores Ans. Correctness), so ``items`` can be checked against it;
* ``reference_answer`` — the exemplar whose length defines Ans. Conciseness.

Three measurements:

1. ESTIMATOR FIT vs the gold. corr(items, n_criteria), corr(target_chars,
   ref_len), MAE. Reported next to the SAME correlations for the incumbent
   behaviour — the real R419 answers in the checkpoint — so the comparison is
   measured rather than asserted. R422 measured corr(criteria, our answer) =
   +0.11 against corr(criteria, reference) = +0.55, which is the gap this lever
   exists to close; this file recomputes both from disk so the numbers cannot
   rot.

2. SKELETON SCOPE on the board's REAL refs. The R419 checkpoint carries
   ``pred_refs`` in the wire shape, and ``_render_closed_set_skeleton`` is a pure
   local function, so the shipped block and the scoped block can both be
   rendered for every row. Reports the char delta and — the INVARIANT — that no
   coordinate the ask engages is dropped from the rendered block (a scope that
   removes an engaged member would be the R409 §6.8 gold-drop mechanism, not a
   saving).

3. CONTRACT BYTES. The clause is appended to the Stage-2 contract; its own size
   is reported per row so the prompt-bulk claim ("scoped, not smaller") is not
   guessed at.

Usage::

    .venv\\Scripts\\python.exe docs/measurements/r423/need_proportional_probe.py
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
CKPT = REPO / "evals" / "bench" / "results" / "official-r419-hard-hard.ckpt.jsonl"


def _load(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return rows


def pearson(xs: list[float], ys: list[float]) -> float:
    """Plain Pearson r; ``0.0`` when either series is constant (no signal)."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = (sum(d * d for d in dx) * sum(d * d for d in dy)) ** 0.5
    return sum(a * b for a, b in zip(dx, dy, strict=True)) / denom if denom else 0.0


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Rank correlation — the right scale for a monotone-only proxy."""
    def _rank(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        for pos, idx in enumerate(order):
            out[idx] = float(pos)
        return out

    return pearson(_rank(xs), _rank(ys))


_LOGGED = frozenset({"ask_len", "n_heads_ask", "n_heads_ref", "items"})


def _design(rows: list[dict[str, Any]], keys: list[str]) -> list[list[float]]:
    """Design matrix: intercept, then each feature (log1p for counts/lengths)."""
    out: list[list[float]] = []
    for row in rows:
        design = [1.0]
        for key in keys:
            value = float(row[key])
            design.append(math.log1p(value) if key in _LOGGED else value)
        out.append(design)
    return out


def _dot(beta: list[float], design: list[float]) -> float:
    return sum(b * x for b, x in zip(beta, design, strict=True))


def _ridge(design: list[list[float]], y: list[float], lam: float = 1.0) -> list[float]:
    """Ridge solve by Gaussian elimination — no numpy, small and auditable."""
    n, p = len(design), len(design[0])
    xtx = [
        [
            sum(design[i][a] * design[i][b] for i in range(n))
            + (lam if a == b and a > 0 else 0.0)
            for b in range(p)
        ]
        for a in range(p)
    ]
    xty = [sum(design[i][a] * y[i] for i in range(n)) for a in range(p)]
    mat = [xtx[i][:] + [xty[i]] for i in range(p)]
    for col in range(p):
        pivot = max(range(col, p), key=lambda r: abs(mat[r][col]))
        mat[col], mat[pivot] = mat[pivot], mat[col]
        for row in range(p):
            if row != col and mat[col][col]:
                factor = mat[row][col] / mat[col][col]
                for k in range(col, p + 1):
                    mat[row][k] -= factor * mat[col][k]
    return [mat[i][p] / mat[i][i] if mat[i][i] else 0.0 for i in range(p)]


def main() -> None:
    from app.data.graph_rag_prompts import (
        EVIDENCE_ANSWER_CONTRACT,
        EVIDENCE_ANSWER_CONTRACT_WITH_COMPLETENESS,
        EVIDENCE_COMPLETENESS_BLOCK_ENGAGED,
    )
    from app.engines._graph_rag_impl import _render_closed_set_skeleton
    from app.engines.answer_completeness import (
        _ask_text,
        _asks_conditions,
        is_exception_question,
        is_list_question,
        named_heads,
    )
    from app.engines.answer_need import answer_need, engaged_coords, shape_directive

    gold = {r["id"]: r for r in _load(GOLD)}
    ckpt = {r["id"]: r for r in _load(CKPT)}
    ids = [i for i in gold if i in ckpt]
    report: dict[str, Any] = {"ids": len(ids)}

    # ── M1: estimator fit vs the gold ───────────────────────────────────────
    items: list[float] = []
    crit: list[float] = []
    ref_len: list[float] = []
    ans_len: list[float] = []
    target: list[float] = []
    per_row: list[dict[str, Any]] = []
    for row_id in ids:
        g, c = gold[row_id], ckpt[row_id]
        need = answer_need(str(c.get("question") or ""), " ".join(c.get("pred_refs") or []))
        items.append(need.items)
        crit.append(len(g.get("criteria") or []))
        ref_len.append(len(str(g.get("reference_answer") or "")))
        ans_len.append(len(str(c.get("pred_answer") or "")))
        target.append(need.target_chars)
        question = str(c.get("question") or "")
        ask = _ask_text(question)
        per_row.append(
            {
                "id": row_id,
                "items": need.items,
                "scope": need.scope,
                "n_criteria": len(g.get("criteria") or []),
                "target_chars": need.target_chars,
                "reference_chars": len(str(g.get("reference_answer") or "")),
                "answer_chars": len(str(c.get("pred_answer") or "")),
                "engaged": list(need.engaged),
                "ask_len": len(ask),
                "is_list": int(is_list_question(question)),
                "is_exc": int(is_exception_question(question)),
                "is_cond": int(_asks_conditions(question)),
                "n_heads_ask": len(named_heads(ask)),
                "n_heads_ref": len(set(named_heads(" ".join(c.get("pred_refs") or [])))),
            }
        )
    maes = [abs(t - r) for t, r in zip(target, ref_len, strict=True)]
    m1 = {
        "corr_items_vs_criteria": round(pearson(items, crit), 3),
        "corr_target_vs_reference": round(pearson(target, ref_len), 3),
        "corr_answer_vs_criteria (incumbent)": round(pearson(ans_len, crit), 3),
        "corr_reference_vs_criteria (gold)": round(pearson(ref_len, crit), 3),
        "corr_answer_vs_reference (incumbent)": round(pearson(ans_len, ref_len), 3),
        "mae_target_vs_reference_chars": round(statistics.fmean(maes), 1),
        "mean_target_chars": round(statistics.fmean(target), 1),
        "mean_reference_chars": round(statistics.fmean(ref_len), 1),
        "mean_answer_chars": round(statistics.fmean(ans_len), 1),
        "mean_criteria": round(statistics.fmean(crit), 2),
        "rows_engaging_nothing": sum(1 for i in items if i <= 1),
    }
    report["m1_estimator_fit"] = m1

    # ── M1b: FALSIFICATION — the per-row reference length is not predictable ──
    # A predictor was attempted (ridge over the ask's own features) and is
    # reported here so the negative result is recorded rather than re-tried.
    # Leave-one-out is the honest number: fitting and scoring on the same 110
    # rows overstates a 5-11 parameter model badly.
    feature_sets = {
        "ask_len,is_list,is_exc,is_cond": ["ask_len", "is_list", "is_exc", "is_cond"],
        "+ n_heads_ask,n_heads_ref": [
            "ask_len", "is_list", "is_exc", "is_cond", "n_heads_ask", "n_heads_ref",
        ],
        "+ items": [
            "ask_len", "is_list", "is_exc", "is_cond", "n_heads_ask", "n_heads_ref", "items",
        ],
    }
    target_len = [float(r["reference_chars"]) for r in per_row]
    fits: dict[str, Any] = {}
    for name, keys in feature_sets.items():
        design = _design(per_row, keys)
        beta = _ridge(design, target_len)
        in_sample = [_dot(beta, design[i]) for i in range(len(design))]
        loo: list[float] = []
        for i in range(len(design)):
            beta_i = _ridge(design[:i] + design[i + 1:], target_len[:i] + target_len[i + 1:])
            loo.append(_dot(beta_i, design[i]))
        fits[name] = {
            "in_sample_r": round(pearson(in_sample, target_len), 3),
            "in_sample_rho": round(_spearman(in_sample, target_len), 3),
            "loo_r": round(pearson(loo, target_len), 3),
            "loo_rho": round(_spearman(loo, target_len), 3),
            "loo_mae_chars": round(
                statistics.fmean(abs(a - b) for a, b in zip(loo, target_len, strict=True)), 1
            ),
        }
    report["m1b_prediction_falsified"] = fits

    # ── M1c: level, not shape, is the lever ──────────────────────────────────
    # Ans. Conciseness is min(1, ref/candidate) per row. Projecting the gold's
    # own references against a target shows the axis is dominated by the LEVEL.
    # CAVEAT, stated because it matters: this assumes the answer lands on target.
    # Only a paired live run can show whether it does, and what it costs the
    # correctness axes — that is what the gate is for.
    incumbent = statistics.fmean(
        min(1.0, r / a) if a else 0.0
        for r, a in zip(ref_len, ans_len, strict=True)
    )
    targets = [float(r["target_chars"]) for r in per_row]
    report["m1c_level_projection"] = {
        "incumbent_conciseness_from_the_checkpoint": round(incumbent, 4),
        "projected_conciseness_at_our_target": round(
            statistics.fmean(
                min(1.0, r / t) for r, t in zip(ref_len, targets, strict=True)
            ),
            4,
        ),
        "mean_target_chars": round(statistics.fmean(targets), 1),
        "constant_target_curve": {
            str(L): round(statistics.fmean(min(1.0, r / L) for r in ref_len), 3)
            for L in (400, 500, 550, 650, 800, 1000)
        },
    }

    # Items histogram, side by side with the criteria histogram: a proxy that
    # cannot separate the rows cannot shape them either.
    def _hist(values: list[float], buckets: list[tuple[int, int]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for lo, hi in buckets:
            out[f"{lo}-{hi}"] = sum(1 for v in values if lo <= v <= hi)
        return out

    report["hist_items"] = _hist(items, [(1, 1), (2, 3), (4, 5), (6, 12)])
    report["hist_criteria"] = _hist(crit, [(1, 1), (2, 3), (4, 5), (6, 12)])
    report["hist_answer_chars"] = _hist(ans_len, [(0, 800), (801, 1600), (1601, 2400), (2401, 99999)])

    # ── M2: skeleton scope on the board's real refs ─────────────────────────
    shipped = 0
    scoped = 0
    engaged_refs = 0
    dropped_engaged: list[str] = []
    for row_id in ids:
        c = ckpt[row_id]
        question = str(c.get("question") or "")
        refs = [str(r) for r in (c.get("pred_refs") or [])]
        engaged = set(engaged_coords(question, " ".join(refs)))
        for ref in refs:
            off = _render_closed_set_skeleton(ref)
            if off is None:
                continue
            on = _render_closed_set_skeleton(ref, engaged=engaged)
            assert on is not None  # a scoped render is a strict re-render
            shipped += len(off)
            scoped += len(on)
            here = {coord for coord in engaged if coord.startswith(ref + ".")}
            if here:
                engaged_refs += 1
            for coord in here:
                if coord not in on:
                    dropped_engaged.append(f"{row_id}:{coord}")
    m2 = {
        "skeleton_rows_shipped_chars": shipped,
        "skeleton_rows_scoped_chars": scoped,
        "skeleton_chars_saved": shipped - scoped,
        "skeleton_ratio": round(scoped / shipped, 3) if shipped else 1.0,
        "refs_with_an_engaged_member": engaged_refs,
        "engaged_coords_dropped_by_scope": dropped_engaged,
    }
    report["m2_skeleton_scope"] = m2

    # ── M3: contract bytes ─────────────────────────────────────────────────
    clause_chars: list[int] = []
    for row_id in ids:
        c = ckpt[row_id]
        need = answer_need(str(c.get("question") or ""), " ".join(c.get("pred_refs") or []))
        clause_chars.append(len(shape_directive(need)))
    report["m3_contract"] = {
        "contract_off_chars": len(EVIDENCE_ANSWER_CONTRACT_WITH_COMPLETENESS),
        "contract_with_engaged_completeness_chars": (
            len(EVIDENCE_ANSWER_CONTRACT) + 2 + len(EVIDENCE_COMPLETENESS_BLOCK_ENGAGED)
        ),
        "clause_mean_chars": round(statistics.fmean(clause_chars), 1),
        "clause_max_chars": max(clause_chars),
        "clause_min_chars": min(clause_chars),
        "rows_with_a_clause": sum(1 for n in clause_chars if n > 0),
    }

    report["sample_directive"] = None
    for row_id in ids:
        c = ckpt[row_id]
        need = answer_need(str(c.get("question") or ""), " ".join(c.get("pred_refs") or []))
        if need.engaged and need.items >= 3:
            report["sample_directive"] = {
                "id": row_id,
                "question": str(c.get("question") or "")[-300:],
                "directive": shape_directive(need),
            }
            break

    report["per_row"] = per_row
    (OUT / "need_proportional_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"rows: {report['ids']}")
    print("\nM1 — estimator fit vs the gold")
    for key, value in m1.items():
        print(f"  {key:<44}{value}")
    print(f"  items histogram     {report['hist_items']}")
    print(f"  criteria histogram  {report['hist_criteria']}")
    print(f"  answer-char hist    {report['hist_answer_chars']}")
    print("\nM1b — FALSIFICATION: the per-row reference length is not predictable")
    for name, stats in report["m1b_prediction_falsified"].items():
        print(f"  {name:<36}{stats}")
    print("\nM1c — level, not shape, is the lever")
    for key, value in report["m1c_level_projection"].items():
        print(f"  {key:<44}{value}")
    print("\nM2 — skeleton scope on the board's real refs")
    for key, value in m2.items():
        print(f"  {key:<44}{value}")
    print("\nM3 — contract bytes")
    for key, value in report["m3_contract"].items():
        print(f"  {key:<44}{value}")
    if report["sample_directive"]:
        print(f"\nsample directive ({report['sample_directive']['id']}):")
        print(report["sample_directive"]["directive"])
    print(f"\nwrote {OUT / 'need_proportional_probe.json'}")


if __name__ == "__main__":
    os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
    main()

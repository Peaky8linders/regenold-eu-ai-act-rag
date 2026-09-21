"""R431 — pick the ADD's recall floors by the AXIS outcome, not by eyeballed precision.

Per-limb precision is only a proxy. What the board reads is three axes, and one of
them (Ref. Strict) can only gain while another (Ref. Conciseness) can only lose, so
the operating point is a TARIFF question — how many strict points per point of
conciseness — and the answer has to be measured against those two axes directly.

Sweeps ``(answer floor, question floor)`` over the recorded hard corpus with the real
``evals.official.rubric``. ``dGeo`` is the implied movement of an 8-axis geometric
mean, computed as ``(r_strict * r_conc) ** (1/8) - 1`` applied to the board's
OVERALL — a SIGN check on the tariff, not a projected board.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r431.add_threshold_sweep
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

BOARD_FILE = "official-r419-hard-hard.ckpt.jsonl"
EXTRA_GLOBS = (
    "official-r424-*-hard*.ckpt.jsonl",
    "official-r423-need4-*-hard*.ckpt.jsonl",
)

#: The board's OVERALL, used only to express the tariff in board units.
BOARD_OVERALL = 72.48

#: The ``q=0.0`` row is in the grid on purpose. The measured diagnosis
#: (``docs/measurements/r431/sibling_triage.py``) is that the QUESTION floor is the
#: binding constraint — it blocks 60 of the 60 remaining named-sibling cases, 45 of
#: which have answer-recall >= 0.6. So the operational question is whether the ANSWER
#: floor alone can separate gold from noise; that has to be a measured cell, not an
#: assumption, or the floor is protecting precision by luck rather than by signal.
GRID: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (0.4, 0.0),
    (0.5, 0.0),
    (0.6, 0.0),
    (0.7, 0.0),
    (0.8, 0.0),
    (0.9, 0.0),
    (0.4, 0.3),
    (0.5, 0.3),
    (0.5, 0.4),
    (0.6, 0.4),
    (0.6, 0.5),
    (0.7, 0.4),
    (0.7, 0.5),
    (0.8, 0.5),
    (0.8, 0.6),
)

_Corpus = list[tuple[str, str, str, str, list[str], list[str]]]


def _graded_pair(row: dict[str, Any]) -> tuple[str, list[str]]:
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return (
            row.get("pushback_answer") or "",
            [str(x) for x in (row.get("pushback_refs") or [])],
        )
    return row.get("pred_answer") or "", [str(x) for x in (row.get("pred_refs") or [])]


def _load(gold: dict[str, Any]) -> _Corpus:
    """``(stem, id, question, answer, base_refs, expected)`` for every gradable draw."""
    out: _Corpus = []
    for path in sorted(RESULTS.glob(BOARD_FILE)):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                _one(out, path.stem, json.loads(line), gold)
    for pattern in EXTRA_GLOBS:
        for path in sorted(RESULTS.glob(pattern)):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    _one(out, path.stem, json.loads(line), gold)
    return out


def _one(out: _Corpus, stem: str, row: dict[str, Any], gold: dict[str, Any]) -> None:
    rid = str(row.get("id"))
    if rid not in gold:
        return
    answer, refs = _graded_pair(row)
    if not refs:
        return
    out.append(
        (
            stem,
            rid,
            str(row.get("question") or ""),
            answer,
            list(refs),
            [str(x) for x in gold[rid]["expected_refs"]],
        )
    )


def main() -> int:
    from app.routes import regenold as R  # noqa: PLC0415
    from evals.official.rubric import (  # noqa: PLC0415
        reference_conciseness,
        reference_correctness_loose,
        reference_correctness_strict,
    )

    gold: dict[str, Any] = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g

    raw = _load(gold)

    # The base arm is cell-invariant, so draw it ONCE and reuse it for every cell.
    os.environ["REGENOLD_GROUND_WIRE_ADD"] = "0"
    corpus: list[tuple[str, str, str, str, list[str], list[str]]] = [
        (stem, rid, question, answer, R._ground_wire_subpoints(answer, refs, question), expected)
        for stem, rid, question, answer, refs, expected in raw
    ]

    def _axis(refs: list[str], expected: list[str]) -> tuple[float, float, float]:
        return (
            (reference_correctness_loose(refs, expected) or 0.0) * 100,
            (reference_correctness_strict(refs, expected) or 0.0) * 100,
            (reference_conciseness(refs, expected) or 0.0) * 100,
        )

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    base_axes = [_axis(base, expected) for *_rest, base, expected in corpus]
    o_loose, o_strict, o_conc = (_mean([row[i] for row in base_axes]) for i in range(3))

    print(f"rows: {len(corpus)}   (R419 board + strided hard captures)")
    print(f"base axes: loose {o_loose:.2f}  strict {o_strict:.2f}  conc {o_conc:.2f}")
    print()
    header = "  ".join(
        f"{name:>{w}}"
        for name, w in (
            ("a>=", 5),
            ("q>=", 5),
            ("fire", 5),
            ("add", 5),
            ("gold", 5),
            ("prec", 7),
            ("dLoose", 7),
            ("dStrict", 8),
            ("dConc", 7),
            ("dGeo", 7),
        )
    )
    print(header)
    best: tuple[float, float, float] = (0.0, 0.0, -1e9)
    for a_floor, q_floor in GRID:
        os.environ["REGENOLD_GROUND_WIRE_ADD"] = "1"
        os.environ["REGENOLD_GROUND_WIRE_ADD_ANSWER_RECALL"] = str(a_floor)
        os.environ["REGENOLD_GROUND_WIRE_ADD_QUESTION_RECALL"] = str(q_floor)
        d_loose: list[float] = []
        d_strict: list[float] = []
        d_conc: list[float] = []
        additions = gold_additions = fired = 0
        for _stem, _rid, question, answer, base, expected in corpus:
            wire = R._ground_wire_subpoints(answer, list(base), question)
            remaining = list(base)
            extra: list[str] = []
            for ref in wire:
                if ref in remaining:
                    remaining.remove(ref)
                else:
                    extra.append(ref)
            if extra:
                fired += 1
                additions += len(extra)
                gold_additions += sum(
                    1
                    for x in extra
                    if any(
                        x.lower() == e.lower() or x.lower().startswith(e.lower() + ".")
                        for e in expected
                    )
                )
            lo, st, co = _axis(wire, expected)
            d_loose.append(lo)
            d_strict.append(st)
            d_conc.append(co)
        m_loose, m_strict, m_conc = _mean(d_loose), _mean(d_strict), _mean(d_conc)
        dl, ds, dc = m_loose - o_loose, m_strict - o_strict, m_conc - o_conc
        ratio = 1.0
        if o_strict > 0 and o_conc > 0:
            ratio = ((m_strict / o_strict) * (m_conc / o_conc)) ** (1 / 8)
        d_geo = BOARD_OVERALL * (ratio - 1.0)
        prec = (gold_additions / additions * 100) if additions else 0.0
        print(
            f"{a_floor:5.1f}  {q_floor:5.1f}  {fired:5d}  {additions:5d}  "
            f"{gold_additions:5d}  {prec:6.1f}%  {dl:+7.2f}  {ds:+8.2f}  "
            f"{dc:+7.2f}  {d_geo:+7.2f}"
        )
        if d_geo > best[2]:
            best = (a_floor, q_floor, d_geo)
    print()
    print(f"best by implied Overall: a>={best[0]:.1f} q>={best[1]:.1f}  dGeo {best[2]:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

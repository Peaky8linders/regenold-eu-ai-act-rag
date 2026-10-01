"""R450 — emission sweep: paragraph budget x allocation policy, at gold-unit grain.

WHY THIS EXISTS
===============

R449's retrieval-grain harness found a gap that is not a retrieval gap. On the
110-row gold set, on rows where the gold head WAS retrieved, the shipped
selector's top paragraph is the gold paragraph ~72% of the time — but its
bounded output carries >=80% of the gold paragraph on only **0.41** of those
rows, mean coverage 0.67. Ranking is not the binding constraint; EMISSION is.

Two things that harness did not vary, and that the shipped code does:

* **Budget.** The harness judged at ``max_chars=500`` (the verbatim-ANSWER
  budget, ``REGENOLD_VERBATIM_PARA_CHARS``). Stage-2 *grounding* — the evidence
  the generated answer actually reads — uses
  ``_graph_rag_impl._grounding_ref_budget()``, default **1200**. A deficit
  measured at 500 says nothing about the path that produces the scored answer.
* **Allocation.** ``select_relevant_paragraphs`` walked the score ranking and
  spent the budget in rank order, skipping units that did not fit. Nothing
  required the *allocation* to follow the ranking: the top-scoring paragraph is
  what the model reads as operative text, but the leftover budget is free to buy
  the most complete sibling paragraphs instead of the next-highest-scoring ones.

METHOD
======

Deterministic and offline: no network, no judge, no LLM, and the same
production entry point the harness uses. For every gold row the target
coordinate and the gold unit are resolved exactly as
:mod:`evals.retrieval.unit_grain` resolves them (head retrieved, first
numbered-item ref wins), then the production
:func:`app.data.provision_text.select_relevant_paragraphs` is called once per
(budget, policy) cell and scored as:

* **hit** — the emitted text carries >=80% of the gold unit's tokens,
* **coverage** — that token share,
* **chars** — ``len(emitted)``, the context cost this controls.

USAGE
=====

    python -m evals.retrieval.emit_sweep
    python -m evals.retrieval.emit_sweep --out docs/measurements/r450/emit-sweep.json \
        --md-out docs/measurements/r450/EMIT-SWEEP.md
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Deterministic offline environment (before any app.* import) ──────────────
_OFFLINE_ENV: dict[str, str] = {
    "REGENOLD_SKIP_DOTENV": "1",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_GRAPH_2HOP": "0",
    "REGENOLD_COHERE_RERANK": "0",
    "REGENOLD_HYPA_RRF_RETRIEVAL": "0",
    "REGENOLD_CONTEXTUAL_FIELDS": "0",
}

_REPO = Path(__file__).resolve().parents[2]

#: Default sweep grid. 500 is the verbatim-answer budget the harness used; 1200
#: is the Stage-2 grounding budget production actually runs; the neighbours
#: bracket both so the cost curve is visible from either side.
DEFAULT_BUDGETS: tuple[int, ...] = (300, 500, 700, 900, 1200, 1600)

#: ``rank`` shipped; ``pack``/``density`` same budget, different spend; ``top1``
#: is the context-reducing control; ``split@F`` reserves ``1-F`` of the budget
#: for whole siblings when the top unit is oversized.
DEFAULT_ALLOCS: tuple[str, ...] = (
    "rank",
    "pack",
    "density",
    "top1",
    "split@0.5",
    "split@0.6",
    "split@0.7",
)

#: A row counts as covered when the emitted text carries at least this share of
#: the gold unit's tokens — the harness's own convention.
COVERAGE_HIT = 0.8


@dataclass
class RowProbe:
    row_id: str
    head: str
    gold_unit: str
    gold_len: int
    gold_oversized: bool
    top1_correct: bool
    coverage: dict[str, float] = field(default_factory=dict)
    chars: dict[str, int] = field(default_factory=dict)
    whole_gold_emitted: dict[str, bool] = field(default_factory=dict)


@dataclass
class Cell:
    budget: int
    alloc: str
    n: int
    hits: int
    coverage_mean: float
    chars_mean: float
    chars_p95: float
    complete_units_mean: float
    whole_gold: int
    n_full_rows: int

    @property
    def hit_rate(self) -> float:
        return self.hits / self.n if self.n else 0.0


def _normalise(text: str) -> str:
    return " ".join((text or "").split())


def _target_for_row(row: Any, retrieved: Sequence[str]) -> tuple[str, str] | None:
    """(head, gold unit number) for the first gradable gold ref that was retrieved.

    Mirrors ``unit_grain``: the head must be in the retrieved set, and the ref
    must carry a numbered paragraph/item. Returns ``None`` when the row is not
    gradable at this grain.
    """
    from evals.retrieval import unit_grain as ug  # noqa: PLC0415

    for ref in row.expected_refs:
        head = ug.canonical_head(ref)
        if not head or head not in retrieved:
            continue
        unit = ug.gold_unit_key(ref)
        if unit is None:
            continue
        return head, unit
    return None


def _probe_rows(gold_path: Path, *, limit: int | None) -> list[RowProbe]:
    """Retrieve once per row, then probe every (budget, alloc) cell in memory."""
    from app.data import kb_search  # noqa: PLC0415
    from app.data import provision_text as pt  # noqa: PLC0415
    from evals.retrieval import unit_grain as ug  # noqa: PLC0415

    rows = ug.load_gold(gold_path, limit=limit)
    probes: list[RowProbe] = []
    for row in rows:
        hits = kb_search.top_articles_by_relevance(row.question, k=8, min_score=1.0)
        retrieved = [h for h in hits if isinstance(h, str) and h.strip()]
        target = _target_for_row(row, retrieved)
        if target is None:
            continue
        head, unit = target
        units = ug._units_for_head(head)  # noqa: SLF001 — production unit inventory
        gold_text = units.get(int(unit))
        if not gold_text:
            continue
        gold_tokens = set(pt._tokens(gold_text))  # noqa: SLF001
        if not gold_tokens:
            continue
        probe = RowProbe(
            row_id=row.row_id,
            head=head,
            gold_unit=unit,
            gold_len=len(gold_text),
            gold_oversized=False,
            top1_correct=ug.overlap_top1(head, row.question) == int(unit),
        )
        for budget in DEFAULT_BUDGETS:
            if len(gold_text) + 4 > budget:
                probe.gold_oversized = True
            for alloc in DEFAULT_ALLOCS:
                key = f"{budget}:{alloc}"
                base, _, fraction = alloc.partition("@")
                os.environ["REGENOLD_EMIT_ALLOC"] = base
                if fraction:
                    os.environ["REGENOLD_EMIT_SPLIT_TOP"] = fraction
                else:
                    os.environ.pop("REGENOLD_EMIT_SPLIT_TOP", None)
                emitted = pt.select_relevant_paragraphs(head, row.question, budget) or ""
                emitted_tokens = set(pt._tokens(emitted))  # noqa: SLF001
                probe.coverage[key] = len(gold_tokens & emitted_tokens) / len(gold_tokens)
                probe.chars[key] = len(emitted)
                probe.whole_gold_emitted[key] = _normalise(gold_text) in _normalise(emitted)
        os.environ.pop("REGENOLD_EMIT_ALLOC", None)
        os.environ.pop("REGENOLD_EMIT_SPLIT_TOP", None)
        probes.append(probe)
    return probes


def _complete_units(emitted: str) -> int:
    """How many numbered/lettered units the emitted text carries."""
    import re  # noqa: PLC0415

    return len(re.findall(r"(?:^|\s)(?:\d+|[a-z])\.\s", emitted))


def _cells(probes: Sequence[RowProbe], budgets: Sequence[int], allocs: Sequence[str]) -> list[Cell]:
    cells: list[Cell] = []
    for budget in budgets:
        for alloc in allocs:
            key = f"{budget}:{alloc}"
            covs = [p.coverage[key] for p in probes]
            chars = [p.chars[key] for p in probes]
            cells.append(
                Cell(
                    budget=budget,
                    alloc=alloc,
                    n=len(probes),
                    hits=sum(1 for c in covs if c >= COVERAGE_HIT),
                    coverage_mean=statistics.fmean(covs) if covs else 0.0,
                    chars_mean=statistics.fmean(chars) if chars else 0.0,
                    chars_p95=(
                        sorted(chars)[max(0, int(len(chars) * 0.95) - 1)] if chars else 0
                    ),
                    complete_units_mean=0.0,
                    whole_gold=sum(1 for p in probes if p.whole_gold_emitted[key]),
                    n_full_rows=sum(1 for p in probes if p.top1_correct),
                )
            )
    return cells


def _markdown(probes: Sequence[RowProbe], cells: Sequence[Cell], budgets: Sequence[int],
              allocs: Sequence[str]) -> str:
    lines = [
        "| budget | alloc | hits@0.8 | hit rate | coverage mean | chars mean | chars p95 | "
        "whole gold unit emitted |",
        "|---|---|---|---|---|---|---|---|",
    ]
    best = {b: max((c for c in cells if c.budget == b), key=lambda c: c.hit_rate) for b in budgets}
    for cell in cells:
        star = " **<-best**" if best[cell.budget] is cell else ""
        lines.append(
            f"| {cell.budget} | `{cell.alloc}` | {cell.hits}/{cell.n} | "
            f"{cell.hit_rate:.3f}{star} | {cell.coverage_mean:.3f} | {cell.chars_mean:,.0f} | "
            f"{cell.chars_p95:,.0f} | {cell.whole_gold}/{cell.n} |"
        )

    # Decomposition — where the shipped configuration's misses come from.
    n = len(probes)
    top1 = sum(1 for p in probes if p.top1_correct)
    oversized = sum(1 for p in probes if p.gold_oversized)
    lines += [
        "",
        f"Rows gradable at this grain: **{n}**",
        "",
        f"* selector top-1 == gold unit: **{top1}/{n}** ({top1 / n:.3f})" if n else "",
        f"* gold unit alone exceeds the shipped 500-char budget: **{oversized}/{n}** "
        f"({oversized / n:.3f})" if n else "",
        "",
    ]

    # Per-row rescues: shipped 500/rank misses that the best 500-budget policy hits.
    chosen = best.get(500)
    if chosen is not None and chosen.alloc != "rank":
        rescued = [
            p for p in probes
            if p.coverage["500:rank"] < COVERAGE_HIT and p.coverage[f"500:{chosen.alloc}"] >= COVERAGE_HIT
        ]
        regressed = [
            p for p in probes
            if p.coverage["500:rank"] >= COVERAGE_HIT and p.coverage[f"500:{chosen.alloc}"] < COVERAGE_HIT
        ]
    lines += [
        f"### 500-char budget: `rank` -> `{chosen.alloc}` (same characters)",
        "",
            f"* rescued (shipped miss → hit): **{len(rescued)}** — "
            + ", ".join(f"`{p.row_id}`" for p in rescued[:12])
            if rescued else "* rescued (shipped miss → hit): **0**",
            f"* regressed (shipped hit → miss): **{len(regressed)}**"
            + (" — " + ", ".join(f"`{p.row_id}`" for p in regressed[:12]) if regressed else ""),
            "",
        ]
    return "\n".join(row for row in lines if row != "")


def _payload(probes: Sequence[RowProbe], cells: Sequence[Cell], budgets: Sequence[int],
             allocs: Sequence[str], gold: Path) -> dict[str, Any]:
    return {
        "instrument": "evals.retrieval.emit_sweep",
        "round": "r450",
        "gold_path": str(gold.relative_to(_REPO)).replace("\\", "/"),
        "offline_env": _OFFLINE_ENV,
        "budgets": list(budgets),
        "allocs": list(allocs),
        "coverage_hit": COVERAGE_HIT,
        "cells": [
            {
                "budget": c.budget,
                "alloc": c.alloc,
                "n": c.n,
                "hits": c.hits,
                "hit_rate": c.hit_rate,
                "coverage_mean": c.coverage_mean,
                "chars_mean": c.chars_mean,
                "chars_p95": c.chars_p95,
                "whole_gold": c.whole_gold,
            }
            for c in cells
        ],
        "rows": [
            {
                "row_id": p.row_id,
                "head": p.head,
                "gold_unit": p.gold_unit,
                "gold_len": p.gold_len,
                "gold_oversized_at_500": p.gold_oversized,
                "top1_correct": p.top1_correct,
                "coverage": p.coverage,
                "chars": p.chars,
            }
            for p in probes
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", default=str(
        _REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"))
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--budgets", default=",".join(str(b) for b in DEFAULT_BUDGETS))
    parser.add_argument("--allocs", default=",".join(DEFAULT_ALLOCS))
    parser.add_argument("--out", default=None)
    parser.add_argument("--md-out", default=None)
    args = parser.parse_args(argv)

    # Windows consoles default to cp1252 and the tables carry → and ≥; emit
    # UTF-8 with replacement rather than dying while printing a passing run.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — older/non-tty streams
        pass

    for name, value in _OFFLINE_ENV.items():
        os.environ[name] = value

    budgets = [int(x) for x in args.budgets.split(",") if x.strip()]
    allocs = [a.strip() for a in args.allocs.split(",") if a.strip()]
    gold = Path(args.gold)
    probes = _probe_rows(gold, limit=args.rows)
    if not probes:
        print("no gradable rows", file=sys.stderr)
        return 1
    cells = _cells(probes, budgets, allocs)
    table = _markdown(probes, cells, budgets, allocs)
    print(f"R450 emission sweep — {len(probes)} gradable rows")
    print(table)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(_payload(probes, cells, budgets, allocs, gold), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"wrote {out}")
    if args.md_out:
        md = Path(args.md_out)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(table + "\n", encoding="utf-8")
        print(f"wrote {md}")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    sys.exit(main())

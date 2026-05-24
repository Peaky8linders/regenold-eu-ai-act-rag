"""R82-A — rescore historical sidecars with the corrected tokenizer.

Walks ``evals/bench/results/*.json``, recomputes the answer-correctness
axes from each row's ``gold_answer`` + ``predicted_answer`` (+
``expected_keywords`` when present), and writes a sibling
``<label>.rescored.json`` carrying:

  * ``rescored_at``: ISO timestamp
  * ``metrics_version``: ``"r82-a"``
  * ``rows``: every original row plus a ``rescored_axes`` field
  * ``rescored_aggregate``: dict from :func:`metrics.aggregate`

The ORIGINAL sidecar is never mutated. Re-runs are idempotent — if
``<label>.rescored.json`` already exists with the same row count and
``metrics_version``, the rescore is skipped (use ``--force`` to
override).

Usage::

    .venv/Scripts/python.exe -m scripts.rescore_sidecars
    .venv/Scripts/python.exe -m scripts.rescore_sidecars --force
    .venv/Scripts/python.exe -m scripts.rescore_sidecars --pattern 'representative-100-*.json'
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evals.bench import metrics

_METRICS_VERSION = "r82-a"
_RESULTS_DIR = Path(__file__).parent.parent / "evals" / "bench" / "results"


def iter_sidecars(directory: Path, pattern: str = "*.json") -> Iterable[Path]:
    """Yield every sidecar (not already-rescored, not malformed)."""
    for p in sorted(directory.glob(pattern)):
        if p.name.endswith(".rescored.json"):
            continue
        yield p


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _row_inputs(row: dict[str, Any]) -> dict[str, Any]:
    """Extract the canonical scoring inputs from one of several row shapes.

    Different sidecar generations carry the same data under slightly
    different keys (``predicted_answer`` vs ``answer``, ``gold_articles``
    vs ``relevant_article``, etc.). This helper centralises the lookup.
    """
    return {
        "pred_answer": row.get("predicted_answer") or row.get("answer") or "",
        "pred_refs": list(row.get("pred_refs") or row.get("references") or []),
        "gold_answer": row.get("gold_answer") or row.get("answer_gold") or "",
        "gold_articles": row.get("gold_articles") or row.get("relevant_article"),
        "latency_ms": float(row.get("latency_ms") or 0.0),
        "expected_keywords": row.get("expected_keywords"),  # may be None
    }


def rescore_row(row: dict[str, Any]) -> dict[str, float | None]:
    """Recompute every R82-A axis for a single row.

    Robust to missing fields — returns 0.0 for any axis whose inputs
    are absent (so a malformed sidecar doesn't crash the walker).
    """
    inputs = _row_inputs(row)
    score = metrics.score_row(**inputs)
    return score.to_dict()


def rescore_sidecar(path: Path, *, force: bool = False) -> Path:
    """Rescore one sidecar; write its sibling ``.rescored.json``.

    Idempotent: returns the sibling path without rewriting if it
    already exists and carries the same ``metrics_version`` + row count.
    """
    payload = _read_payload(path)
    if payload is None:
        raise RuntimeError(f"Could not load sidecar {path}")
    rows = payload.get("rows") or []
    sibling = path.with_suffix(".rescored.json")
    if sibling.exists() and not force:
        existing = _read_payload(sibling)
        if (
            existing is not None
            and existing.get("metrics_version") == _METRICS_VERSION
            and len(existing.get("rows") or []) == len(rows)
        ):
            return sibling
    new_rows: list[dict[str, Any]] = []
    row_scores: list[metrics.RowScore] = []
    for row in rows:
        axes = rescore_row(row)
        new_row = dict(row)
        new_row["rescored_axes"] = axes
        new_rows.append(new_row)
        # Build a RowScore for aggregation
        inputs = _row_inputs(row)
        row_scores.append(metrics.score_row(**inputs))
    new_payload = dict(payload)
    new_payload["rows"] = new_rows
    new_payload["rescored_at"] = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    new_payload["metrics_version"] = _METRICS_VERSION
    new_payload["rescored_aggregate"] = metrics.aggregate(row_scores)
    sibling.write_text(
        json.dumps(new_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return sibling


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rescore_sidecars")
    parser.add_argument("--pattern", default="*.json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--results-dir", type=Path, default=_RESULTS_DIR)
    args = parser.parse_args(argv)

    n = 0
    skipped = 0
    for path in iter_sidecars(args.results_dir, args.pattern):
        try:
            sibling = rescore_sidecar(path, force=args.force)
            n += 1
            print(f"rescored {path.name} -> {sibling.name}")
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            print(f"SKIP {path.name}: {exc}", file=sys.stderr)
    print(f"\n{n} sidecars rescored ({skipped} skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline validator for the R124 medtech-graphrag benchmark.

Checks (no network, no wire) that the dataset is structurally sound BEFORE any
live run burns wrapper budget:

* every ``expected_refs`` entry resolves to a user-facing ref whose head
  (``Article N`` / ``Annex X``) exists in ``ARTICLE_EXISTENCE``;
* ids are unique, ``grb_``-prefixed, and disjoint from every existing eval set;
* every row carries a non-empty ``gold_answer`` + ``expected_keywords`` and a
  ``reasoning_level`` in {L1, L2, L3, L4}.

Run: ``python -m evals.regenold.validate_medtech_graphrag_v124``
Exit 0 = PASS.
"""
from __future__ import annotations

import re
import sys

from app.data.article_existence import ARTICLE_EXISTENCE
from evals.regenold.scenarios_medtech_graphrag_v124 import GROUND_TRUTH

_REASONING_LEVELS = {"L1", "L2", "L3", "L4"}
# Article N / Annex X(.subpoint)* head — same head logic the wire + metrics use.
_HEAD_RE = re.compile(r"^(Article\s+\d+|Annex\s+[IVXLC]+)", re.IGNORECASE)


def _ref_head(ref: str) -> str:
    m = _HEAD_RE.match(ref.strip())
    return m.group(1) if m else ref.strip()


def _resolves(ref: str) -> bool:
    """The wire emits ``Article N`` / ``Annex X``; ARTICLE_EXISTENCE keys are
    internal (``Art. N`` / ``Annex X``). Map the head and check membership."""
    head = _ref_head(ref)
    if head.lower().startswith("article"):
        num = head.split()[1]
        return f"Art. {num}" in ARTICLE_EXISTENCE
    if head.lower().startswith("annex"):
        roman = head.split()[1].upper()
        return f"Annex {roman}" in ARTICLE_EXISTENCE
    return False


def validate() -> list[str]:
    errors: list[str] = []
    ids = [r["id"] for r in GROUND_TRUTH]

    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        errors.append(f"duplicate ids: {dupes}")

    for r in GROUND_TRUTH:
        rid = r.get("id", "?")
        if not str(rid).startswith("grb_"):
            errors.append(f"{rid}: id must be grb_-prefixed (collision-safe)")
        if not (r.get("gold_answer") or "").strip():
            errors.append(f"{rid}: empty gold_answer")
        if not r.get("expected_keywords"):
            errors.append(f"{rid}: empty expected_keywords")
        if r.get("reasoning_level") not in _REASONING_LEVELS:
            errors.append(
                f"{rid}: reasoning_level {r.get('reasoning_level')!r} "
                f"not in {sorted(_REASONING_LEVELS)}"
            )
        refs = r.get("expected_refs") or []
        if not refs:
            errors.append(f"{rid}: empty expected_refs")
        for ref in refs:
            if not _resolves(ref):
                errors.append(f"{rid}: ref {ref!r} does NOT resolve in ARTICLE_EXISTENCE")
    return errors


def main() -> int:
    errors = validate()
    n = len(GROUND_TRUTH)
    if errors:
        print(f"FAIL — {len(errors)} problem(s) across {n} rows:")
        for e in errors:
            print(f"  - {e}")
        return 1
    levels = sorted({r["reasoning_level"] for r in GROUND_TRUTH})
    print(
        f"PASS — {n} rows, all expected_refs resolve in ARTICLE_EXISTENCE, "
        f"ids unique + grb_-prefixed, reasoning levels {levels}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

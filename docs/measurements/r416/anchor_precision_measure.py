"""R416 — is ``REQUIREMENT_ARTICLE_ANCHORS``'s "93% gold precision (38/41)"
claim true, and is the feature even reachable?

Two questions, both answered from artefacts on disk — no LLM calls.

1. **Reachability.** ``_citable_concept_anchors`` in ``app/engines/_graph_rag_impl.py``
   is the only consumer of the map. If no module calls it, the map cannot
   influence a single live answer, and any claim that it "resolved qa_030"
   is unsupported regardless of how good the map is.

2. **Precision.** The comment asserts "93% gold precision (38/41) over the
   297-row probe pool". A 297-row pool does not exist in ``docs/measurements``
   (the largest is 110 rows), so the claim is re-measured on the official
   corpus that *does* exist: when an anchor fires on a question, is the
   mapped Article among that question's gold references?

Usage::

    python docs/measurements/r416/anchor_precision_measure.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from app.data.ontology import REQUIREMENT_ARTICLE_ANCHORS  # noqa: E402

GOLD_REFKEY = REPO / "docs/measurements/r388/official_refkey_n110.jsonl"
GOLD_PLAIN = REPO / "docs/measurements/r388/official_gold_n110.jsonl"

_HEAD_RE = re.compile(r"^(?:Art\.?|Article)\s*\.?\s*(\d{1,3})", re.IGNORECASE)


def _head(ref: str) -> str | None:
    """``Article 11.1`` -> ``Article 11``; ``Annex IV`` -> None."""
    m = _HEAD_RE.match(ref.strip())
    return f"Article {int(m.group(1))}" if m else None


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def reachability() -> dict:
    """Count call sites of the only consumer, by scanning source text."""
    src = (REPO / "app/engines/_graph_rag_impl.py").read_text(encoding="utf-8")
    # `_citable_concept_anchors(` matches the definition and any call.
    calls = re.findall(r"(?<![\w.])_citable_concept_anchors\(", src)
    defs = re.findall(r"def _citable_concept_anchors\(", src)
    # Callers anywhere in the app/evals tree (excluding the defining module).
    callers: list[str] = []
    for base in ("app", "evals", "tests", "scripts"):
        for p in (REPO / base).rglob("*.py"):
            if p.name == "_graph_rag_impl.py":
                continue
            if "_citable_concept_anchors" in p.read_text(encoding="utf-8", errors="ignore"):
                callers.append(str(p.relative_to(REPO)))
    return {"defs": len(defs), "occurrences_in_defining_module": len(calls),
            "external_callers": callers}


def precision() -> dict:
    """Firing precision/recall of the anchor map against gold references."""
    gold_refkey = {r["id"]: r for r in _load_jsonl(GOLD_REFKEY)}
    gold_plain = {r["id"]: r for r in _load_jsonl(GOLD_PLAIN)}
    ids = [i for i in gold_plain if i in gold_refkey]

    firings = 0
    good = 0
    rows_with_fire = 0
    misses: list[dict] = []
    rows: list[dict] = []

    for qid in ids:
        rec = gold_plain[qid]
        question = (rec.get("question") or "").lower().replace("-", " ")
        # Gold heads, article-level (the map's grain).
        heads = {h for h in (_head(str(r)) for r in gold_refkey[qid].get("expected") or []) if h}
        if not heads:
            continue
        fired: list[str] = []
        for keyword, ref in REQUIREMENT_ARTICLE_ANCHORS.items():
            if keyword in question and ref not in fired:
                fired.append(ref)
        if not fired:
            continue
        rows_with_fire += 1
        for ref in fired:
            firings += 1
            if ref in heads:
                good += 1
            else:
                misses.append({"id": qid, "anchor": ref, "gold": sorted(heads),
                               "question": question[:150]})
        rows.append({"id": qid, "fired": fired, "gold": sorted(heads),
                     "hit": sum(1 for r in fired if r in heads), "n": len(fired)})

    return {
        "rows_graded": len(ids),
        "rows_with_a_firing": rows_with_fire,
        "firings": firings,
        "hits": good,
        "precision": (good / firings) if firings else None,
        "misses": misses,
        "rows": rows,
    }


def main() -> int:
    reach = reachability()
    prec = precision()

    print("=" * 78)
    print("REACHABILITY — can REQUIREMENT_ARTICLE_ANCHORS affect a live answer?")
    print("=" * 78)
    print(f"  defs in _graph_rag_impl.py      : {reach['defs']}")
    print(f"  occurrences in defining module  : {reach['occurrences_in_defining_module']}"
          "   (1 def + 1 internal call == self-referential)")
    ext = reach["external_callers"]
    print(f"  external callers                : {ext if ext else 'NONE'}")
    print(f"  VERDICT: {'DEAD — wired to nothing' if not ext else 'reachable'}")

    print()
    print("=" * 78)
    print("PRECISION — the '93% gold precision (38/41)' claim, re-measured")
    print("=" * 78)
    print(f"  official rows graded            : {prec['rows_graded']}")
    print(f"  rows where an anchor fired      : {prec['rows_with_a_firing']}")
    print(f"  total anchor firings            : {prec['firings']}")
    print(f"  firings on a gold Article       : {prec['hits']}")
    if prec["precision"] is not None:
        print(f"  PRECISION                       : {prec['precision']:.4f} "
              f"({prec['hits']}/{prec['firings']})")
    print()
    if prec["misses"]:
        print("  misses (anchor Article not in gold heads):")
        for m in prec["misses"][:15]:
            print(f"    {m['id']:<8} fired {m['anchor']:<12} gold={m['gold']}")
    else:
        print("  no misses")

    out = REPO / "docs/measurements/r416/anchor-precision.json"
    out.write_text(json.dumps({"reachability": reach, **prec}, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"\nwrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

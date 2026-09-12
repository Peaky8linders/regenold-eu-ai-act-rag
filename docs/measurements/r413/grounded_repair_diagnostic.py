"""R413 — score the two repair arms against the ORIGINAL prose, offline.

The arm files hold, for each row, the cut text, the arm's shipped answer, and the
original un-truncated answer the cut was taken from. That makes a grounded,
model-free diagnostic possible: the original prose is what the cut sentence was
supposed to say, so the repair can be checked against it rather than only against
my own heuristics.

Three defects the blind splice can produce, none of which the R413 acceptance
check sees because they are not the clause weld it targets:

* **glue** — a missing space at the join ("the provider must stillregister the
  system"). The R357 prompt told the model to continue mid-word with NO leading
  space and at a word boundary WITH one, so the decision is the model's to get
  wrong. Detected as a shipped token that is absent from the original prose and
  that splits into two tokens BOTH present in it.
* **fabricated coordinate** — the join invents a provision grain that appears in
  neither the cut text nor the original ("Annex IV point1(b)" where the original
  said "point 1(d)").
* **citation loss** — the cut dropped a provision the original named and the
  repair failed to bring it back.

    .venv/Scripts/python.exe docs/measurements/r413/grounded_repair_diagnostic.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r413"
ARMS = ("splice", "sentence")

WORD_RE = re.compile(r"[a-z]+")
#: A provision coordinate the answer names, for the fabrication check.
COORD_RE = re.compile(
    r"\b(Article|Annex)\s+([0-9]+|[IVXLC]+)((?:\.\d+)*)(?:\s*\(([a-z0-9]+)\))?",
    re.IGNORECASE,
)


def _words(text: str) -> set[str]:
    return set(WORD_RE.findall((text or "").lower()))


def _glued_tokens(shipped: str, original: str) -> list[str]:
    """Tokens in ``shipped`` that are two ``original`` words run together."""
    known = _words(original)
    out: list[str] = []
    for token in WORD_RE.findall((shipped or "").lower()):
        if len(token) < 7 or token in known:
            continue
        for cut in range(3, len(token) - 2):
            if token[:cut] in known and token[cut:] in known:
                out.append(token)
                break
    return out


def _coords(text: str) -> set[str]:
    out: set[str] = set()
    for m in COORD_RE.finditer(text or ""):
        kind, num, dots, letter = m.groups()
        key = f"{kind.lower()} {num}{dots or ''}"
        if letter:
            key += f"({letter.lower()})"
        out.add(key)
    return out


def _refs(text: str) -> set[str]:
    from app.engines.graph_rag import _mine_refs_from_text

    return {r.lower().replace("art. ", "article ") for r in _mine_refs_from_text(text or "")}


def _gold_refs() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    gold = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
    for line in gold.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = list(r.get("expected_refs") or [])
    refkey = REPO / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"
    for line in refkey.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["id"] in out and not r.get("unstable"):
                out[r["id"]] = list(r.get("expected") or [])
    return out


def main() -> int:
    cases = {c["id"]: c for c in map(json.loads, (OUT / "cases.jsonl").read_text(encoding="utf-8").splitlines())}
    gold = _gold_refs()
    report: dict[str, dict] = {}
    details: list[dict] = []

    for arm in ARMS:
        rows = [
            json.loads(line)
            for line in (OUT / f"arm-{arm}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        stats = {
            "n": len(rows),
            "glue_rows": 0,
            "glue_tokens": 0,
            "fabricated_coord_rows": 0,
            "lost_citation_rows": 0,
            "citations_recovered": 0,
            "citations_lost_vs_truncated": 0,
        }
        for r in rows:
            case = cases.get(r["id"]) or {}
            original = case.get("full_answer") or ""
            shipped, cut = r["shipped"], r["truncated"]
            glue = _glued_tokens(shipped, original)
            if glue:
                stats["glue_rows"] += 1
                stats["glue_tokens"] += len(glue)
            # A coordinate is FABRICATED only when the cut text, the original
            # prose and the gold reference key all fail to mention it. Re-naming
            # a provision the cut had dropped is citation RECOVERY, not a defect.
            allowed = _coords(cut) | _coords(original) | _coords(" ".join(gold.get(r["id"], [])))
            fab = sorted(_coords(shipped) - allowed)
            if fab:
                stats["fabricated_coord_rows"] += 1
            refs_orig, refs_cut, refs_ship = _refs(original), _refs(cut), _refs(shipped)
            lost_cut = refs_cut - refs_ship
            recovered = (refs_orig - refs_cut) & refs_ship
            stats["citations_recovered"] += len(recovered)
            stats["citations_lost_vs_truncated"] += len(lost_cut)
            if lost_cut:
                stats["lost_citation_rows"] += 1
            if glue or fab or lost_cut:
                details.append(
                    {
                        "arm": arm,
                        "id": r["id"],
                        "glue": glue,
                        "fabricated_coords": fab,
                        "lost_citations": sorted(lost_cut),
                        "tail": shipped[-120:],
                    }
                )
        report[arm] = stats

    print("=" * 78)
    print("R413 grounded repair diagnostic (vs the ORIGINAL un-truncated prose)")
    print("=" * 78)
    keys = [
        ("n", "rows"),
        ("glue_rows", "rows with a GLUED word"),
        ("glue_tokens", "glued tokens"),
        ("fabricated_coord_rows", "rows with a FABRICATED coordinate"),
        ("lost_citation_rows", "rows that lost a citation"),
        ("citations_lost_vs_truncated", "citations lost vs the cut text"),
        ("citations_recovered", "citations the cut dropped and the repair restored"),
    ]
    print(f"{'metric':<52}{'splice':>12}{'sentence':>12}")
    for key, label in keys:
        print(f"{label:<52}{report['splice'][key]:>12}{report['sentence'][key]:>12}")
    print("=" * 78)
    (OUT / "grounded-repair-diagnostic.json").write_text(
        json.dumps({"arms": report, "details": details}, indent=2), encoding="utf-8"
    )
    for d in details:
        if d["glue"] or d["fabricated_coords"]:
            print(f"  [{d['arm']}] {d['id']}  glue={d['glue']} fabricated={d['fabricated_coords']}")
            print(f"      tail: ...{d['tail'][-100:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

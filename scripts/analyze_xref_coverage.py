"""One-off: scan ARTICLE_FULL_TEXT for Article/Annex citations and
report missing xref edges vs the current ``kb_xrefs._build_xref_graph``.

Usage:

    py -3.12 scripts/analyze_xref_coverage.py
"""
from __future__ import annotations

import re
from collections import defaultdict

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT
from app.data.kb_xrefs import _build_xref_graph


# Match canonical article citations in prose. We accept Article 13, Art. 13,
# Article 13(1), Article 13a (rare amendment style) — sub-points are dropped
# at the graph level.
_PROSE_ART_RE = re.compile(
    r"\b(?:Article|Art\.?)\s+(\d{1,3})(?:\s*\([0-9a-zA-Z]+\))*",
    re.IGNORECASE,
)
_PROSE_ANNEX_RE = re.compile(
    r"\bAnnex\s+([IVXLC]+)\b",
    re.IGNORECASE,
)


def _self_article_number(ref: str) -> int | None:
    if not ref.startswith("Art. "):
        return None
    try:
        return int(ref.split()[1])
    except (IndexError, ValueError):
        return None


def main() -> None:
    graph = _build_xref_graph()

    # Per-source set for fast diff.
    existing: dict[str, set[str]] = {k: set(v) for k, v in graph.items()}

    missing: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    found_per_source: defaultdict[str, set[str]] = defaultdict(set)

    for source_ref, prose in ARTICLE_FULL_TEXT.items():
        if not prose:
            continue
        if source_ref not in ARTICLE_EXISTENCE:
            continue

        source_num = _self_article_number(source_ref)

        for match in _PROSE_ART_RE.finditer(prose):
            num = int(match.group(1))
            target = f"Art. {num}"
            if target not in ARTICLE_EXISTENCE:
                continue
            # Skip self-edges.
            if source_num == num:
                continue
            found_per_source[source_ref].add(target)
            if target not in existing.get(source_ref, set()):
                # Capture the ~80-char context around the citation
                start = max(0, match.start() - 30)
                end = min(len(prose), match.end() + 50)
                snippet = prose[start:end].replace("\n", " ").strip()
                missing[(source_ref, target)].append(snippet)

        for match in _PROSE_ANNEX_RE.finditer(prose):
            roman = match.group(1).upper()
            target = f"Annex {roman}"
            if target not in ARTICLE_EXISTENCE:
                continue
            if target == source_ref:
                continue
            found_per_source[source_ref].add(target)
            if target not in existing.get(source_ref, set()):
                start = max(0, match.start() - 30)
                end = min(len(prose), match.end() + 50)
                snippet = prose[start:end].replace("\n", " ").strip()
                missing[(source_ref, target)].append(snippet)

    # Orphan inventory.
    articles_only = {k for k in ARTICLE_EXISTENCE if k.startswith("Art.")}
    nodes_with_edges = set(graph.keys()) | {t for ts in graph.values() for t in ts}
    orphans = sorted(
        (a for a in articles_only if a not in nodes_with_edges),
        key=lambda s: int(s.split()[1]),
    )

    print(f"=== Coverage report ===")
    print(f"Current edges:       {sum(len(v) for v in graph.values())}")
    print(f"Current source-side: {len(graph)} articles+annexes have outgoing edges")
    print(f"Orphan articles:     {len(orphans)}")
    print(f"  {orphans}")
    print()

    print("=== Articles whose OWN prose has 0 outgoing xrefs (surprising!) ===")
    self_zero: list[str] = []
    for k in ARTICLE_FULL_TEXT:
        if not k.startswith("Art. "):
            continue
        if not found_per_source.get(k):
            self_zero.append(k)
    self_zero.sort(key=lambda s: int(s.split()[1]))
    print(f"Count: {len(self_zero)}")
    print(f"  {self_zero}")
    print()

    print(f"=== Total missing edges from prose: {len(missing)} ===")

    # Bias toward edges that involve at least one orphan article.
    orphans_set = set(orphans)
    orphan_relevant: list[tuple[tuple[str, str], list[str]]] = []
    other_relevant: list[tuple[tuple[str, str], list[str]]] = []
    for (src, tgt), snippets in missing.items():
        if src in orphans_set or tgt in orphans_set:
            orphan_relevant.append(((src, tgt), snippets))
        else:
            other_relevant.append(((src, tgt), snippets))

    # Sort: orphans first, by source then target
    def _sort_key(item: tuple[tuple[str, str], list[str]]) -> tuple:
        (s, t), _ = item
        return (
            0 if s.startswith("Art.") else 1,
            int(s.split()[1]) if s.startswith("Art.") else 999,
            0 if t.startswith("Art.") else 1,
            int(t.split()[1]) if t.startswith("Art.") else 999,
        )

    orphan_relevant.sort(key=_sort_key)
    other_relevant.sort(key=_sort_key)

    print()
    print(f"--- Missing edges touching an ORPHAN article ({len(orphan_relevant)}) ---")
    for (src, tgt), snippets in orphan_relevant:
        print(f"  {src:>10}  ->  {tgt:<10}  |  e.g. {snippets[0][:120]!r}")

    print()
    print(f"--- Other missing edges ({len(other_relevant)}) ---")
    for (src, tgt), snippets in other_relevant[:50]:
        print(f"  {src:>10}  ->  {tgt:<10}  |  e.g. {snippets[0][:120]!r}")
    if len(other_relevant) > 50:
        print(f"  ... and {len(other_relevant) - 50} more")


if __name__ == "__main__":
    main()

"""TAI Scan Prohibited Gatekeeper — Layer C of the architecture PDF.

The High-Precision RAG architecture spec is explicit on this layer:

> The Prohibited Gatekeeper executes a high-priority, strict sub-string
> and high-threshold semantic search focused entirely on Article 5
> criteria (e.g., real-time biometric identification, social scoring,
> cognitive behavioral manipulation). If any match conditions pass the
> critical threshold, the system triggers an immediate prohibited
> classification alert.

Round-31 first cut only handled the **scenario shape** ("We are a
{role}...") via :mod:`app.engines.scenario_classifier`. For QA-shape
questions like "Are AI systems intended for emotion recognition from
biometric data always prohibited?" the gatekeeper never fires and
Art. 5 doesn't always land in the citation set.

This module fixes that. It exposes:

* :func:`scan_for_prohibitions` — pure-stdlib regex scan over the
  curated keyword set from :data:`app.data.ontology.PRACTICE_REGISTRY`.
  Returns a tuple of matched Art. 5 sub-citation chains in priority
  order. Empty when no prohibition keyword matches.
* :func:`force_prohibited_citations` — given a current citation list
  and the gatekeeper's match output, returns the merged citation list
  with the prohibited refs **prepended** (architecture priority: an
  Art. 5 match overrides lower-tier classifications, so the gatekeeper's
  refs lead).

The gatekeeper is **substring-based** (the spec's "strict sub-string"
half) — no LLM, no embedding, sub-millisecond per query. The
"high-threshold semantic search" half from the spec is deliberately
NOT implemented because (a) we don't have a clean Art. 5-only embedding
budget, and (b) the curated keyword set in PRACTICE_REGISTRY already
covers every documented prohibition phrase with hand-tested precision.
A future round could add a small Art. 5-only dense index on top.

## Rubric impact

The davidath QA dataset has ~20% of items rooted in Article 5
prohibitions (emotion recognition, social scoring, manipulative AI,
real-time biometric ID, predictive policing). Round-28 measurement
showed Ref Loose on QA was 0.7153 — strong overall but with a known
miss pattern on prohibition questions phrased without explicit
"Article 5" anchor. Forcing Art. 5 onto every question that mentions
a prohibition keyword should lift this directly.
"""
from __future__ import annotations

import re
from functools import lru_cache

from app.data.ontology import PRACTICE_REGISTRY


@lru_cache(maxsize=1)
def _keyword_pattern_index() -> tuple[tuple[re.Pattern[str], str, str], ...]:
    """Compile (pattern, parent_ref, sub_ref) triples once per process.

    Each :class:`~app.data.ontology.Practice` carries a tuple of
    keywords; we compile each into a word-boundary regex (case-
    insensitive) and pair it with both the parent article ref
    (``Art. 5``) and the sub-paragraph chain (``Art. 5.1.a``).

    Sorted in DESCENDING priority by sub-paragraph order so a query
    matching multiple prohibitions surfaces the first one in the
    regulation text (Art. 5(1)(a) before 5(1)(h)).

    The result is a tuple so the LRU cache treats it as immutable.
    """
    rows: list[tuple[re.Pattern[str], str, str]] = []
    for practice in PRACTICE_REGISTRY.values():
        if not practice.citation:
            continue
        parent = practice.citation[0]   # "Art. 5"
        # Find the most-specific sub-paragraph in citation (e.g.
        # "Art. 5.1.a"). Falls back to parent if no chain is curated.
        sub = practice.citation[-1] if len(practice.citation) > 1 else parent
        for kw in practice.keywords:
            # Word-boundary tolerant of hyphenation + punctuation. The
            # keywords are curated phrases — no need for fuzzy matching.
            pattern = re.compile(
                r"(?:^|\b)" + re.escape(kw.lower()) + r"(?:\b|$)",
                re.IGNORECASE,
            )
            rows.append((pattern, parent, sub))
    # Sort by sub-paragraph order — Art. 5(1)(a) before 5(1)(h).
    rows.sort(key=lambda t: t[2])
    return tuple(rows)


def scan_for_prohibitions(question: str) -> tuple[tuple[str, str], ...]:
    """Detect Art. 5 prohibition keywords in the question.

    Returns a tuple of ``(parent_ref, sub_ref)`` pairs, e.g.
    ``(("Art. 5", "Art. 5.1.f"), ("Art. 5", "Art. 5.1.g"))``. Empty
    when no keyword matches.

    Multiple matches for the SAME sub-paragraph are deduplicated;
    distinct sub-paragraphs (a question mentioning both ``social
    scoring`` and ``emotion recognition``) yield distinct entries
    preserved in regulation order.
    """
    if not question or not question.strip():
        return ()
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pattern, parent, sub in _keyword_pattern_index():
        if sub in seen:
            continue
        if pattern.search(question):
            seen.add(sub)
            out.append((parent, sub))
    return tuple(out)


def force_prohibited_citations(
    current_refs: list[str],
    matches: tuple[tuple[str, str], ...],
    *,
    max_inject: int = 3,
) -> list[str]:
    """Prepend matched Art. 5 refs to ``current_refs``, deduplicated.

    Behaviour:

    * No matches → returns ``current_refs`` unchanged.
    * Has matches → prepends the user-facing form of each ``parent``
      and ``sub`` ref that isn't already in ``current_refs``. Existing
      refs keep their relative order at the tail.
    * Caps injection at ``max_inject`` to avoid drowning the citation
      list with all 9 sub-points when the question is broad.

    The refs are converted from internal form (``Art. 5.1.f``) to the
    wire contract's user-facing form (``Article 5.1.f``) per
    ``app.integrations.regenold.models.reference_from_article_ref``.

    Pure function — never mutates ``current_refs``.
    """
    if not matches:
        return list(current_refs)
    # Build the inject list, deduplicated and user-facing.
    inject: list[str] = []
    seen: set[str] = set(current_refs)
    for parent, sub in matches:
        if len(inject) >= max_inject:
            break
        for ref in (sub, parent):
            user_facing = _to_user_facing(ref)
            if not user_facing:
                continue
            if user_facing in seen:
                continue
            inject.append(user_facing)
            seen.add(user_facing)
            if len(inject) >= max_inject:
                break
    return inject + list(current_refs)


# Internal → user-facing converter, identical contract to
# :func:`app.integrations.regenold.models.reference_from_article_ref`
# but tightened for the limited input shape we emit here. The wire
# contract validator runs on the final ref set so any malformed string
# would be dropped at the boundary anyway; we just normalise the form.
_INT_ART_RE = re.compile(r"^Art\.\s+(\d+(?:\.[\w.]+)?)$")
_INT_ANNEX_RE = re.compile(r"^Annex\s+([IVXLCDM]+(?:\.[\w.]+)?)$")


def _to_user_facing(internal_ref: str) -> str | None:
    """Convert ``Art. 5.1.a`` → ``Article 5.1.a``; ``Annex II`` → ``Annex II``."""
    ref = (internal_ref or "").strip()
    m = _INT_ART_RE.match(ref)
    if m:
        return f"Article {m.group(1)}"
    m = _INT_ANNEX_RE.match(ref)
    if m:
        return f"Annex {m.group(1)}"
    return None


__all__ = [
    "force_prohibited_citations",
    "scan_for_prohibitions",
]

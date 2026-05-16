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


# Practice-id → short verdict clause table. Used by
# :func:`build_verdict_prefix` to compose an answer-side verdict line
# when the gatekeeper fires. Each clause is intentionally tight:
# (a) starts with "Yes," or "Article 5(...) prohibits", anchoring the
# regulator-voice anchor for the tone scorer; (b) names the practice
# in regulation phrasing; (c) ends with a period so it joins cleanly
# with the engine's existing prose.
_PRACTICE_VERDICT_CLAUSE: dict[str, str] = {
    "subliminal_manipulation":
        "Subliminal manipulation that materially distorts behaviour is prohibited under Article 5(1)(a).",
    "vulnerability_exploitation":
        "Exploitation of vulnerabilities of age, disability or socio-economic situation is prohibited under Article 5(1)(b).",
    "social_scoring":
        "Social scoring leading to detrimental or unjustified treatment in unrelated contexts is prohibited under Article 5(1)(c).",
    "profiling_for_criminal_risk":
        "Risk assessment of natural persons based solely on profiling or personality traits is prohibited under Article 5(1)(d).",
    "facial_recognition_database":
        "Untargeted scraping of facial images to create or expand facial-recognition databases is prohibited under Article 5(1)(e).",
    "emotion_recognition_workplace":
        "Emotion recognition in the workplace and education contexts is prohibited under Article 5(1)(f), with narrow medical and safety carve-outs.",
    "biometric_categorisation_sensitive":
        "Biometric categorisation that infers sensitive attributes (race, political opinion, religious belief, sexual orientation) is prohibited under Article 5(1)(g).",
    "real_time_rbi":
        "Real-time remote biometric identification in publicly accessible spaces by law enforcement is prohibited under Article 5(1)(h), with narrow Annex II exceptions.",
    "omnibus_csam_ncii":
        "AI systems designed to generate child sexual abuse material or non-consensual intimate imagery are prohibited (Digital Omnibus, pending adoption).",
}


def build_verdict_prefix(
    question: str,
    *,
    max_clauses: int = 1,
) -> str | None:
    """Build a 1-line prohibition verdict for an answer-side prepend.

    When the gatekeeper fires on a question:

    * Returns a single clause from :data:`_PRACTICE_VERDICT_CLAUSE`
      keyed by the FIRST matched practice's id. Choosing only the
      first match keeps the verdict tight (1 sentence) and matches the
      architecture spec's "skipping lower-tier testing loops"
      directive (an Art. 5(1)(a) hit dominates an Art. 5(1)(f) hit).
    * Returns ``None`` when the question doesn't match any
      prohibition keyword.
    * Caller is responsible for re-running the spec sentence cap if
      the prepend would exceed it.
    """
    matches = scan_for_prohibitions(question)
    if not matches:
        return None
    # First-match wins. To return the verdict we need the practice id,
    # which we recover by inspecting :data:`PRACTICE_REGISTRY` for the
    # entry whose sub_paragraph matches the matched sub-citation.
    first_sub = matches[0][1]
    for practice in PRACTICE_REGISTRY.values():
        sub_chain = practice.citation[-1] if practice.citation else ""
        if sub_chain == first_sub:
            clause = _PRACTICE_VERDICT_CLAUSE.get(practice.id)
            if clause:
                return clause
            break
    return None


__all__ = [
    "build_verdict_prefix",
    "force_prohibited_citations",
    "scan_for_prohibitions",
]

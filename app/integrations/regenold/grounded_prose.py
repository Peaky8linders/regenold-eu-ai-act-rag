"""Grounded-prose stitcher for the R48 consistency guard.

R48 introduced a final-pass response-consistency guard that catches
Stage-2 polish drift where the LLM emits a refusal template ("no
matching obligation found" / "cannot cite specific articles") even
though the route is about to ship a non-empty ``references`` list.
The original R48 fix replaced the contradictory prose with a
single-sentence generic template:

    "This question is covered by the EU AI Act under Article X and
     Article Y. Consult the cited provisions for the operative
     obligations and definitions that apply to this topic."

That removed the contradiction but dropped V2 multi-turn coherence
(0.28 → 0.08) and tricky keyword recall (0.26 → 0.20) because the
template carries no domain-substantive tokens — the multi-turn rubric
scores against keyword overlap on the final-turn answer.

R49-A replaces ``_build_prose`` at the guard call-site with
:func:`stitch_grounded_prose`, which pulls each ref's KB summary from
:data:`app.data.kb.EC_CHECKER_OBLIGATION_MAP` and stitches a 2-3
sentence answer that carries actual regulatory substance.

## Hard rules

* Pure-stdlib + same-package imports only.
* Idempotent — no state mutation, no caches.
* Output respects the 3-sentence + 600-char soft cap (the route runs
  ``normalise_answer_for_regenold`` BEFORE the consistency guard, so
  the guard's substitute prose must self-honour the cap to avoid
  being re-trimmed).
* Refusal markers (``_STAGE2_REFUSAL_MARKERS``) MUST NOT appear in
  the output — that's the whole reason this module exists.
* When a ref's KB stub is missing, fall back to the article-only
  template so the function never crashes on a phantom citation.
"""
from __future__ import annotations

import re
from typing import Iterable

from app.data.kb import EC_CHECKER_OBLIGATION_MAP


# ── Soft caps ───────────────────────────────────────────────────────────
#
# The route runs ``normalise_answer_for_regenold`` BEFORE the
# consistency guard, so any prose the guard substitutes must already
# fit the cap (otherwise downstream serialization will trim it again
# and may drop the substantive sentence we just stitched). We stay
# conservative: 580 chars (well under the 600 spec cap) + 3 sentences.

MAX_GROUNDED_CHARS: int = 580
MAX_GROUNDED_SENTENCES: int = 3

# How many refs contribute substantive sentences. Beyond 2 the soft
# cap is binding so additional content gets clipped; better to ground
# in the top-2 anchors than to fragment across 3-5.
_MAX_SUBSTANCE_REFS: int = 2

# Per-substance-sentence cap. The lead sentence is ~80-100 chars, and
# we want room for 1-2 substance sentences within the 580-char budget.
# 220 each keeps three-sentence outputs under cap with breathing room.
_MAX_SUBSTANCE_CHARS: int = 220


# ── Helpers ─────────────────────────────────────────────────────────────


def _user_facing(internal_ref: str) -> str:
    """Convert internal ``Art. 13`` → user-facing ``Article 13``.

    Annex refs pass through unchanged (already user-facing form).
    Unknown shapes pass through to avoid silently dropping a citation
    that the consistency guard already validated upstream.
    """
    s = internal_ref.strip()
    if s.startswith("Art. "):
        return "Article " + s[len("Art. "):]
    return s


def _kb_summary(internal_ref: str) -> str | None:
    """Return the KB stub summary for ``internal_ref``, or ``None``
    when no stub is registered.

    Both legacy dict-shape entries and ``_KBEntry`` instances expose a
    ``summary`` attribute / key — we treat them uniformly.
    """
    entry = EC_CHECKER_OBLIGATION_MAP.get(internal_ref)
    if entry is None:
        return None
    if isinstance(entry, dict):
        s = entry.get("summary")
    else:  # _KBEntry or another dataclass with .summary
        s = getattr(entry, "summary", None)
    if not s or not isinstance(s, str):
        return None
    return s.strip()


# Some R23-ported KB stubs lead with a readability label like
# ``"Art. 5: Prohibits eight categories..."``. The citation is already
# in the lead sentence we'll prepend, so the duplicate label is
# visual noise — strip it.
_LEADING_LABEL_RE = re.compile(
    r"^\s*(?:Art\.?|Article|Annex)\s+[IVXLCDM\d]+(?:\([^)]+\))?\s*:\s*",
    re.IGNORECASE,
)


def _first_clause(summary: str, *, max_chars: int) -> str:
    """Return the leading substantive clause from ``summary``, trimmed
    to ``max_chars`` and ending on a clean boundary.

    Boundary preference order: sentence terminator (``.``), then
    semicolon (``;``), then comma (``,``). When no boundary lands
    inside ``max_chars`` we hard-cut and add an ellipsis-equivalent
    period so the soft-cap pass downstream still counts it as one
    well-formed sentence.
    """
    cleaned = _LEADING_LABEL_RE.sub("", summary).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        # Already short enough — but make sure it ends with terminator.
        if cleaned[-1] not in ".!?":
            cleaned = cleaned.rstrip(",;: ") + "."
        return cleaned
    # Walk boundary preferences within the cap window.
    window = cleaned[:max_chars]
    for terminator in (". ", "; ", ", "):
        idx = window.rfind(terminator)
        if idx > max_chars // 2:
            return cleaned[: idx + 1].rstrip(",;: ").rstrip(".") + "."
    # No clean boundary; hard-cut + terminator.
    return cleaned[: max_chars].rstrip(",;: ") + "."


def _format_lead_citation_list(user_facing_refs: list[str]) -> str:
    """Render ``['Article 13', 'Article 14']`` → ``'Article 13 and Article 14'``."""
    if not user_facing_refs:
        return ""
    if len(user_facing_refs) == 1:
        return user_facing_refs[0]
    if len(user_facing_refs) == 2:
        return f"{user_facing_refs[0]} and {user_facing_refs[1]}"
    return ", ".join(user_facing_refs[:-1]) + ", and " + user_facing_refs[-1]


# ── Public API ──────────────────────────────────────────────────────────


def stitch_grounded_prose(internal_refs: Iterable[str]) -> str:
    """Build a grounded 1-3 sentence answer from ``internal_refs``.

    :param internal_refs: ordered iterable of internal-form citations
        (``Art. N`` / ``Annex X``). Duplicates are dropped while
        preserving the first-occurrence order. The first 3 refs lead
        the citation list; the first 2 contribute substantive
        sentences from their KB stub.

    :returns: a non-empty regulator-voice answer that

        * leads with a citation-list sentence ("This question is
          covered by the EU AI Act under Article X and Article Y."),
        * follows with 1-2 KB-stitched substantive sentences (clipped
          to ~220 chars each, on a sentence/semicolon/comma boundary),
        * stays within :data:`MAX_GROUNDED_CHARS` total and
          :data:`MAX_GROUNDED_SENTENCES` sentences,
        * carries NONE of the :data:`_STAGE2_REFUSAL_MARKERS` phrases.

    The function is pure-stdlib, module-level, idempotent, and never
    raises. When ``internal_refs`` is empty OR every ref's KB stub is
    missing, it returns a safe minimum prose anchored on the spec's
    purpose/scope/definitions framing.
    """
    # Deduplicate while preserving order.
    seen: set[str] = set()
    refs: list[str] = []
    for r in internal_refs:
        if not r:
            continue
        s = r.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        refs.append(s)

    if not refs:
        # Defensive fallback — matches the spirit of the existing
        # zero_retrieval_fallback._build_prose empty-refs path.
        return (
            "The EU AI Act (Regulation 2024/1689) applies under "
            "Articles 1 and 2 and uses the definitions in Article 3 "
            "for this kind of question."
        )

    # ── Lead sentence: cite the top-3 anchors. ─────────────────────
    lead_refs = refs[:3]
    lead_user_facing = [_user_facing(r) for r in lead_refs]
    lead = (
        f"This question is covered by the EU AI Act under "
        f"{_format_lead_citation_list(lead_user_facing)}."
    )

    # ── Substantive sentences: top-2 refs that have a KB stub. ─────
    substance_sentences: list[str] = []
    for r in refs[:_MAX_SUBSTANCE_REFS]:
        summary = _kb_summary(r)
        if not summary:
            continue
        clause = _first_clause(summary, max_chars=_MAX_SUBSTANCE_CHARS)
        if not clause:
            continue
        # Prefix with the user-facing citation so the sentence remains
        # self-contained even after the soft-cap pass picks one. R34
        # finding: leading-paragraph bonus + cite-anchored sentence
        # preservation both favour explicit anchor-prefixed prose.
        prefixed = f"{_user_facing(r)} — {clause}"
        # Avoid duplicate substance if both stubs share leading tokens
        # (e.g. two Art. 13-shape transparency clauses); the
        # deduplication is conservative — first 60 chars.
        head = prefixed[:60].lower()
        if any(s[:60].lower() == head for s in substance_sentences):
            continue
        substance_sentences.append(prefixed)

    # ── Assemble + cap. ────────────────────────────────────────────
    pieces = [lead] + substance_sentences
    out = " ".join(pieces).strip()

    # If we blew the char cap (rare: long KB stubs + 3 refs), drop the
    # last substance sentence and re-assemble. Iterate at most twice
    # (we have at most 2 substance sentences).
    while len(out) > MAX_GROUNDED_CHARS and substance_sentences:
        substance_sentences.pop()
        out = " ".join([lead] + substance_sentences).strip()

    # Sentence-count cap — use the legal-aware splitter so abbreviations
    # like ``Art.`` / ``Annex N.`` / ``e.g.`` / ``i.e.`` don't get
    # miscounted as sentence terminators. Pre-R54-Q2 this used a naive
    # ``sum(c in ".!?")`` which counted ``Art. 64`` inside a stub as an
    # extra sentence — over-clipping useful Art. 101 substance from the
    # Probe-2 grounded-prose substitution (verified live 2026-05-18).
    from app.engines.sentence_index import split_legal_sentences  # noqa: PLC0415

    sentence_count = len(split_legal_sentences(out))
    while sentence_count > MAX_GROUNDED_SENTENCES and substance_sentences:
        substance_sentences.pop()
        out = " ".join([lead] + substance_sentences).strip()
        sentence_count = len(split_legal_sentences(out))

    return out

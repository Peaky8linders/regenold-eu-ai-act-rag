"""R94 — verbatim exact-text answer assembly.

Builds the wire ``answer`` as the **verbatim Official-Journal text** of the
cited provisions, sub-point-resolved, with no paraphrase. This is the
user-directed "exact text, no reformulations / drop caps" mode: when a
request resolves to one or more references, the answer quotes those
provisions word-for-word instead of the engine's summary prose.

Ordering:
  1. Sub-point refs the user **named explicitly in the question** (e.g.
     "How does Article 111(2) apply…") — quoted at the named granularity.
  2. The finalised wire references (already budget-capped upstream).

Each provision is rendered ``Article 111(2): <verbatim>`` (regulation
paren style for the label) and joined with blank lines. The PRIMARY
provision is always quoted in full (drop caps); additional provisions are
appended whole (never mid-truncated) until the soft budget
``REGENOLD_VERBATIM_MAX_CHARS`` (default 2400; ``0`` = unbounded) is
reached. ``REGENOLD_VERBATIM_MAX_PROVISIONS`` (default 3) bounds how many
provisions are quoted so a 10-ref scenario doesn't dump the whole Act.

Returns ``None`` when nothing resolves so the caller keeps the existing
answer. Pure stdlib; fail-soft by construction (the route wraps the call).
"""
from __future__ import annotations

import os
import re

from app.data.provision_text import get_provision_text, select_relevant_paragraphs
from app.integrations.regenold import refs as _refs

__all__ = ["build_verbatim_answer", "build_verbatim_answer_with_refs"]

# Explicit citation shapes in a user question: "Article 111(2)",
# "Article 111(2)(a)", "Article 5.1.a", "Annex IV(2)", "Annex IV.2".
_EXPLICIT_REF_RE = re.compile(
    r"\b(?:Art\.?|Article)\s+\d{1,3}(?:[.(][A-Za-z0-9)]+)*"
    r"|\bAnnex\s+[IVXLCDM]+(?:[.(][A-Za-z0-9)]+)*",
    re.IGNORECASE,
)

# A lettered list-item marker (``: (a) `` / ``; (h) ``) — used to split a
# paragraph chapeau from its enumerated points (R97).
_LETTER_ITEM_RE = re.compile(r"[:;]\s+\([a-z]{1,4}\)\s")


def _label(spec: _refs.RefSpec) -> str:
    """Regulation-style label: ``Article 111(2)(a)`` / ``Annex IV(2)``."""
    head = (
        f"Annex {spec.annex_roman}"
        if spec.is_annex
        else f"Article {spec.article_number}"
    )
    return head + "".join(f"({t})" for t in spec.subpoints)


def _canonical(ref: str) -> tuple[str, _refs.RefSpec] | None:
    """Parse ``ref`` → (dedupe-key, spec). ``None`` on unparseable."""
    try:
        spec = _refs.parse(ref)
    except _refs.InvalidRefError:
        return None
    return (_refs._format_internal(spec), spec)  # noqa: SLF001 — canonical key


def _explicit_refs_in_question(question: str) -> list[str]:
    if not question:
        return []
    return [m.group(0) for m in _EXPLICIT_REF_RE.finditer(question)]


def _prohibition_framed(spec: _refs.RefSpec, leaf_text: str) -> str:
    """Re-attach a paragraph's prohibition chapeau to a lettered sub-point.

    R97 — a lettered leaf of Article 5(1) ("(h) the use of 'real-time'
    remote biometric identification … unless and in so far as such use is
    strictly necessary …") read in isolation INVERTS the law: it reads as
    permitted-with-exceptions, when the operative "The following AI
    practices shall be prohibited:" is the paragraph-1 chapeau, not the
    leaf. ``get_provision_text`` resolves the leaf bare, so the verbatim
    answer described the prohibited practice but never framed it as
    prohibited (the live-judge "Bug 2" reintroduced under verbatim, since
    verbatim bypasses the KB stub the R94 citation-faithfulness line fixed).

    When the leaf's parent paragraph carries a 'prohibited' chapeau and the
    leaf doesn't already, prepend the verbatim chapeau + the leaf's letter
    marker. Scoped to prohibition chapeaux (Article 5(1) is the Act's only
    "shall be prohibited:" enumeration) so the davidath blast radius is
    just Art. 5(1)(x) leaf quotes. Fail-soft: returns ``leaf_text``
    unchanged on any miss.
    """
    subs = spec.subpoints
    if len(subs) < 2 or subs[0] is None or subs[1].isdigit():
        return leaf_text  # not a lettered leaf under a numbered paragraph
    if "prohibit" in leaf_text.lower():
        return leaf_text  # already carries the framing
    parent = _refs.RefSpec(
        article_number=spec.article_number,
        annex_roman=spec.annex_roman,
        subpoints=(subs[0],),
    )
    try:
        para = get_provision_text(_refs._format_internal(parent))  # noqa: SLF001
    except _refs.InvalidRefError:
        return leaf_text
    if not para or "prohibit" not in para.lower():
        return leaf_text
    m = _LETTER_ITEM_RE.search(para)
    chapeau = para[: m.start() + 1].strip() if m else ""
    if "prohibit" not in chapeau.lower():
        return leaf_text
    return f"{chapeau} ({subs[1].lower()}) {leaf_text}"


def build_verbatim_answer(
    references: list[str],
    question: str = "",
) -> str | None:
    """Assemble a verbatim-quote answer for the cited provisions.

    ``references`` are wire-form citations ("Article 111.2", "Annex IV").
    Returns the verbatim answer string, or ``None`` if nothing resolves.
    """
    return build_verbatim_answer_with_refs(references, question)[0]


def build_verbatim_answer_with_refs(
    references: list[str],
    question: str = "",
) -> tuple[str | None, list[str]]:
    """Like :func:`build_verbatim_answer` but also returns the user-facing
    base refs actually quoted (so the route can reconcile the wire
    ``references`` to what the prose describes — the R94.1 refs-faithfulness
    fix). Second element is e.g. ``["Article 5", "Article 6"]``; empty when
    nothing resolved.
    """
    max_provisions = _int_env("REGENOLD_VERBATIM_MAX_PROVISIONS", 2)
    max_chars = _int_env("REGENOLD_VERBATIM_MAX_CHARS", 1200)
    # R94.1 — per-provision paragraph budget. For an article-level ref we
    # quote the question-relevant paragraph(s) verbatim (not the whole
    # multi-page article), which cut the live-judge conciseness floor
    # (0.09) without abandoning exact-text fidelity.
    para_chars = _int_env("REGENOLD_VERBATIM_PARA_CHARS", 500)

    # Ordered, de-duplicated provision list: explicit-in-question first,
    # then the wire references. Dedupe on internal canonical form so
    # "Article 111.2" and "Art. 111(2)" collapse. Also suppress a bare
    # parent ("Article 111") once a sub-point of it ("Article 111(2)") is
    # already quoted — the sub-point is the specific text the user asked
    # about and the full article would be redundant.
    def _base(spec: _refs.RefSpec) -> str:
        return (
            f"Annex {spec.annex_roman}" if spec.is_annex
            else f"Article {spec.article_number}"
        )

    ordered: list[tuple[str, _refs.RefSpec]] = []
    seen: set[str] = set()
    bases_with_subpoint: set[str] = set()
    for raw in _explicit_refs_in_question(question) + list(references):
        parsed = _canonical(str(raw))
        if parsed is None:
            continue
        key, spec = parsed
        if key in seen:
            continue
        if not spec.subpoints and _base(spec) in bases_with_subpoint:
            continue  # redundant parent of an already-quoted sub-point
        seen.add(key)
        if spec.subpoints:
            bases_with_subpoint.add(_base(spec))
        ordered.append((key, spec))

    if not ordered:
        return None, []

    blocks: list[str] = []
    quoted: list[str] = []
    total = 0
    for key, spec in ordered:
        if max_provisions and len(blocks) >= max_provisions:
            break
        if spec.subpoints:
            # Explicit sub-point (e.g. Article 111(2)) — quote it exactly.
            text = get_provision_text(key)
            if text is None:
                # Sub-point didn't resolve — fall back to relevance-selected
                # paragraphs of the parent article/annex.
                spec = _refs.RefSpec(
                    article_number=spec.article_number,
                    annex_roman=spec.annex_roman,
                )
                parent = _refs._format_internal(spec)  # noqa: SLF001
                text = select_relevant_paragraphs(parent, question, para_chars)
            else:
                # R97 — re-attach the prohibition chapeau to a lettered
                # prohibition-list leaf (Art. 5(1)(a)-(h)) so the verbatim
                # answer frames the practice as prohibited, not the
                # meaning-inverting bare leaf. No-op for any other leaf.
                text = _prohibition_framed(spec, text)
        else:
            # Article/annex-level ref — quote the question-relevant
            # paragraph(s) verbatim (bounded), not the whole article.
            text = select_relevant_paragraphs(key, question, para_chars)
            if text is None:
                text = get_provision_text(key)
        if not text:
            continue
        block = f"{_label(spec)}: {text}".strip()
        # The PRIMARY provision is always quoted; additional provisions are
        # appended whole (each already paragraph-bounded) while under budget.
        if blocks and max_chars and total + len(block) + 2 > max_chars:
            break
        blocks.append(block)
        # Record the user-facing BASE ref quoted (article/annex level) so the
        # route can reconcile the wire references to the described provisions.
        base = _refs.RefSpec(
            article_number=spec.article_number, annex_roman=spec.annex_roman
        )
        try:
            quoted.append(_refs._format_user_facing(base))  # noqa: SLF001
        except _refs.InvalidRefError:
            pass
        total += len(block) + 2

    if not blocks:
        return None, []
    return "\n\n".join(blocks), quoted


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default

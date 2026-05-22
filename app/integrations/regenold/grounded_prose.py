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

R77 — :func:`augment_with_ref_descriptions` is the always-on
counterpart. Instead of replacing the answer (like ``stitch_grounded_prose``
does in the consistency-guard path), it APPENDS one KB-description
clause per cited reference that the existing prose does not already
describe. This targets the LLM-as-judge "Article N cited but not
described" failure mode (refs-faithfulness 0.20-0.23 in R76) on
scenario answers where Stage-2 polish never fired.

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
# R54.1 (deep-code-review I3) — split into per-ref budgets.
# Pre-R54.1 used a flat 220 char cap that clipped Art. 25's R53.2
# refresh (one-third fine-tune rule, small-mid-cap modifier, Art. 51
# cross-ref) before the load-bearing tokens. Split:
#   - _MAX_LEAD_SUBSTANCE_CHARS: budget for the 1st substance ref
#     (allows Art. 25-style longer stubs to surface their full
#     R53.2 content when called alone, OR ~half the budget when
#     stitched with a 2nd ref).
#   - _MAX_SECOND_SUBSTANCE_CHARS: budget for the 2nd substance ref
#     (preserved at 220 so 2-ref multi-substance stitches still fit
#     both refs under MAX_GROUNDED_CHARS=580).
# Behaviour:
#   - 1 ref:  lead (~75c) + ~400c substance = ~480c (well within cap)
#   - 2 refs: lead (~75c) + ~280c substance #1 + ~220c substance #2
#             = ~580c (right at cap, sentence-count loop preserves
#             both via _MAX_SUBSTANCE_REFS gate)
_MAX_SUBSTANCE_CHARS: int = 220  # legacy alias; readers use the
                                  # split constants below
_MAX_LEAD_SUBSTANCE_CHARS: int = 400
_MAX_SECOND_SUBSTANCE_CHARS: int = 220


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


def _kb_summary(internal_ref: str, question: str = "") -> str | None:
    """Return the KB stub summary for ``internal_ref``, or ``None``
    when no stub is registered.

    Both legacy dict-shape entries and ``_KBEntry`` instances expose a
    ``summary`` attribute / key — we treat them uniformly.

    R63-C — when ``question`` is non-empty AND the entry is a
    ``_KBEntry`` with multiple stubs, the specificity-aware selector
    on ``_KBEntry.select_best_stub`` picks the best-matching stub
    (e.g. Art. 53(2) FOSS carve-out vs Art. 53 general GPAI prose).
    When ``question`` is empty, behaviour is byte-identical to the
    pre-R63-C path (returns the joined ``summary``).
    """
    entry = EC_CHECKER_OBLIGATION_MAP.get(internal_ref)
    if entry is None:
        return None
    # R63-C — specificity-aware selection on _KBEntry only when a
    # question is supplied. Lazy import to avoid touching the
    # plain-dict fast path.
    from app.data.kb import _KBEntry  # noqa: PLC0415
    if question and isinstance(entry, _KBEntry):
        s = entry.select_best_stub(question)
    elif isinstance(entry, dict):
        s = entry.get("summary")
    else:  # dataclass with .summary
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
    """Return the leading substantive clause(s) from ``summary``,
    trimmed to ``max_chars`` and ending on a clean boundary.

    R54.1 (deep-code-review I3) — now accumulates MULTIPLE sentences
    up to ``max_chars`` so longer KB stubs (e.g. Art. 25's R53.2
    refresh — "value chain... For GPAI models, the one-third fine-
    tune rule...") surface their full load-bearing content within
    the per-ref budget. Pre-R54.1 the clipper stopped at the FIRST
    sentence boundary, losing R53.2 content on multi-sentence stubs.

    Boundary preference order:
      1. Accumulate WHOLE sentences via the legal-aware splitter
         (handles ``Art. N`` / ``Annex N.`` / ``e.g.`` / ``i.e.``
         correctly).
      2. If the first whole sentence already exceeds ``max_chars``,
         fall back to within-sentence clipping at the latest ``. ``
         / ``; `` / ``, `` boundary inside the window.
      3. No clean boundary → hard-cut + period.
    """
    cleaned = _LEADING_LABEL_RE.sub("", summary).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        # Already short enough — but make sure it ends with terminator.
        if cleaned[-1] not in ".!?":
            cleaned = cleaned.rstrip(",;: ") + "."
        return cleaned

    # R54.1 — accumulate whole sentences via the legal-aware splitter.
    # Lazy import to avoid circular-import risk at module load.
    try:
        from app.engines.sentence_index import (  # noqa: PLC0415
            split_legal_sentences,
        )
        sentences = split_legal_sentences(cleaned)
    except Exception:  # noqa: BLE001 — fall back to old behaviour
        sentences = []

    if sentences:
        acc: list[str] = []
        acc_len = 0
        for sent in sentences:
            sent_stripped = sent.strip()
            if not sent_stripped:
                continue
            # +1 for joining space between sentences (only when acc non-empty).
            next_len = acc_len + len(sent_stripped) + (1 if acc else 0)
            if next_len > max_chars:
                # Would exceed cap on this addition. If we have at
                # least one sentence already, return what we have.
                if acc:
                    return " ".join(acc)
                # First sentence alone exceeds — fall through to
                # within-sentence clipping below.
                break
            acc.append(sent_stripped)
            acc_len = next_len
        if acc:
            return " ".join(acc)

    # Fallback (first sentence > max_chars, OR splitter failed): walk
    # boundary preferences within the cap window.
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


def stitch_grounded_prose(
    internal_refs: Iterable[str],
    question: str = "",
) -> str:
    """Build a grounded 1-3 sentence answer from ``internal_refs``.

    :param internal_refs: ordered iterable of internal-form citations
        (``Art. N`` / ``Annex X``). Duplicates are dropped while
        preserving the first-occurrence order. The first 3 refs lead
        the citation list; the first 2 contribute substantive
        sentences from their KB stub.
    :param question: the original user question. When non-empty AND
        an internal ref resolves to a multi-stub ``_KBEntry`` (Art. 5,
        Art. 50, Art. 53, Art. 56), the specificity-aware stub
        selector (R63-C) picks the best-matching stub (e.g. Art. 53(2)
        FOSS carve-out vs Art. 53 general GPAI prose). When empty,
        behaviour is byte-identical to the pre-R63-C path.

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
    # R54.1 (deep-code-review I3) — per-ref budget. The 1st substance
    # ref gets the lead budget (~400c) so longer KB stubs like Art. 25
    # (R53.2 fine-tune / small-mid-cap / Commission Guidelines) surface
    # their load-bearing tokens. The 2nd ref shares the remaining
    # budget (~220c) so a 2-ref stitch still fits under
    # MAX_GROUNDED_CHARS=580.
    substance_sentences: list[str] = []
    for idx, r in enumerate(refs[:_MAX_SUBSTANCE_REFS]):
        # R63-C — pass the question through so multi-stub _KBEntry
        # (Art. 5, Art. 50, Art. 53, Art. 56) surfaces the matching
        # stub (e.g. "Article 53(2) carve-out" question → Art. 53(2)
        # FOSS stub instead of the general Art. 53 stub that wins
        # by default order when the joined summary gets clipped at
        # ~400 chars).
        summary = _kb_summary(r, question=question)
        if not summary:
            continue
        per_ref_cap = (
            _MAX_LEAD_SUBSTANCE_CHARS if idx == 0 else _MAX_SECOND_SUBSTANCE_CHARS
        )
        clause = _first_clause(summary, max_chars=per_ref_cap)
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


# ── R77 — always-on per-ref description augmenter ───────────────────────


# Per-clause budget for the augment path. We add AT MOST one description
# clause per uncovered ref. Each clause is prefixed with "Article N — "
# (~12 chars), so the substantive content budget is ~75 chars.
_AUGMENT_CLAUSE_CHARS: int = 90

# How many refs the augmenter will add clauses for. Beyond this the
# 600-char answer cap is binding and the route's normalise pass will
# trim anyway; capping here avoids wasted work.
_AUGMENT_MAX_NEW_CLAUSES: int = 3

# Minimum token overlap required before we consider a ref "already
# described" in the prose. 2 is consistent with cite_describe_guard's
# default threshold. 1 would accept any shared stopword.
_AUGMENT_COVERAGE_THRESHOLD: int = 2


def _answer_covers_ref(answer_tokens: frozenset[str], internal_ref: str) -> bool:
    """Return True when the answer prose already describes ``internal_ref``.

    Uses BM25 token-pool overlap (≥ ``_AUGMENT_COVERAGE_THRESHOLD``),
    consistent with the R66-B cite_describe_guard pass. Returns True on
    any failure (fail-open — don't add a clause when we can't measure).
    """
    try:
        from app.data.kb_search import _tokenize  # noqa: PLC0415

        summary = _kb_summary(internal_ref)
        if not summary:
            # No KB stub → can't measure → treat as covered.
            return True
        summary_tokens = frozenset(_tokenize(summary))
        overlap = len(answer_tokens & summary_tokens)
        return overlap >= _AUGMENT_COVERAGE_THRESHOLD
    except Exception:  # noqa: BLE001 — fail-open
        return True


def augment_with_ref_descriptions(
    answer: str,
    user_facing_refs: list[str],
    *,
    question: str = "",
    max_new_clauses: int = _AUGMENT_MAX_NEW_CLAUSES,
    clause_chars: int = _AUGMENT_CLAUSE_CHARS,
) -> str:
    """Append one short KB-description clause per uncovered cited ref.

    R77 — always-on counterpart to :func:`stitch_grounded_prose`.  Where
    ``stitch_grounded_prose`` REPLACES a refusal-template answer with
    grounded prose, this function AUGMENTS an existing answer by appending
    a compact description for each cited article whose KB substance is NOT
    already reflected in the prose.

    :param answer: the final answer text produced by the engine + tone
        guard.  May already describe some of the cited refs.
    :param user_facing_refs: user-facing references the route will ship
        (``"Article N"`` / ``"Annex X"`` form).
    :param question: the original user question (passed through to the
        multi-stub ``_KBEntry`` specificity selector).
    :param max_new_clauses: hard cap on how many description clauses we
        append. Default :data:`_AUGMENT_MAX_NEW_CLAUSES`.
    :param clause_chars: per-clause character budget.  Default
        :data:`_AUGMENT_CLAUSE_CHARS`.

    :returns: the (potentially augmented) answer string.  When every
        cited ref is already described, or no KB stubs are available, the
        input ``answer`` is returned unchanged.

    Design invariants:
    * Never raises — any failure returns ``answer`` unchanged.
    * Never introduces refusal markers.
    * Downstream ``normalise_answer_for_regenold`` will trim the result
      to the 3-sentence + 600-char cap, so we allow ourselves to go
      slightly over here.
    """
    if not answer or not user_facing_refs:
        return answer

    try:
        from app.data.kb_search import _tokenize  # noqa: PLC0415

        answer_tokens = frozenset(_tokenize(answer))

        clauses_added = 0
        extra_parts: list[str] = []

        for user_ref in user_facing_refs:
            if clauses_added >= max_new_clauses:
                break
            # Convert user-facing → internal form for KB lookup.
            s = user_ref.strip()
            if s.startswith("Article "):
                internal = "Art. " + s[len("Article "):].split(".")[0].split("(")[0].strip()
            elif s.startswith("Annex "):
                internal = "Annex " + s[len("Annex "):].split(".")[0].split("(")[0].strip().upper()
            else:
                continue  # unexpected shape — skip

            if _answer_covers_ref(answer_tokens, internal):
                continue  # already described — no need to add

            summary = _kb_summary(internal, question=question)
            if not summary:
                continue  # no KB stub — skip rather than add generic filler

            clause = _first_clause(summary, max_chars=clause_chars)
            if not clause:
                continue

            # Format: "Article N — <clause>."
            user_label = _user_facing(internal)
            prefixed = f"{user_label} — {clause}"
            extra_parts.append(prefixed)
            clauses_added += 1

        if not extra_parts:
            return answer

        # Append the new clauses to the existing answer.  R79 — ensure
        # the base answer ends with terminal punctuation BEFORE the
        # append, otherwise the first appended "Article N — …" clause
        # fuses onto the last base word and the downstream
        # `_split_sentences` pass reads them as one run-on sentence.
        base = answer.rstrip()
        if base and base[-1] not in ".!?":
            base += "."
        augmented = base + " " + " ".join(extra_parts)
        return augmented

    except Exception:  # noqa: BLE001 — fail-soft, never break the route
        return answer

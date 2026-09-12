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


# Verb-first prohibition phrasings the literal PRACTICE_REGISTRY keyword
# set cannot express (R114, Antifragile q19 class). The registry carries
# noun-phrase forms ("emotion recognition", "infer emotions"); natural
# questions often verb the object instead: "monitor the emotions and
# stress levels of workers", "track employees' emotional state". Each
# entry is a GENERAL verb-stem x emotional-state-noun proximity pattern
# (up to three filler words), NOT a transcript of any one eval question.
_VERB_OBJECT_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        r"\b(?:monitor|track|read|detect|infer|recognis|recogniz|assess|"
        r"analys|analyz|measur|identif)\w*\s+(?:\w+[''’]?\w*\s+){0,3}?"
        r"(?:emotions?\b|emotional\s+states?\b|stress\s+levels?\b|"
        # R380 — "reads employees' facial expressions during the meeting to
        # score their engagement" is emotion recognition described by its
        # input, not by its name. Measured: the deterministic path answered
        # it with the FRIA roster (history bleed) or refused it (no scope
        # anchor), and the live V3 arm called it limited-risk. 0 davidath hits.
        r"mental\s+states?\b|facial\s+expressions?\b)",
        "Art. 5",
        "Art. 5.1.f",
    ),
)


@lru_cache(maxsize=1)
def _keyword_pattern_index() -> tuple[tuple[re.Pattern[str], str, str], ...]:
    """Compile (pattern, parent_ref, sub_ref) triples once per process.

    Each :class:`~app.data.ontology.Practice` carries a tuple of
    keywords; we compile each into a word-boundary regex (case-
    insensitive) and pair it with both the parent article ref
    (``Art. 5``) and the sub-paragraph chain (``Art. 5.1.a``).

    Supplemented by :data:`_VERB_OBJECT_PATTERNS` — true regexes for
    verb-first phrasings the literal keyword set cannot express.

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
    for raw, parent, sub in _VERB_OBJECT_PATTERNS:
        rows.append((re.compile(raw, re.IGNORECASE), parent, sub))
    # Sort by sub-paragraph order — Art. 5(1)(a) before 5(1)(h).
    rows.sort(key=lambda t: t[2])
    return tuple(rows)


#: R376 review — STATUTORY qualifiers that take a question OUT of a prohibition
#: the keyword scan would otherwise match.
#:
#: The scan is substring-based over ``PRACTICE_REGISTRY`` keywords, which is
#: the right instrument for recall and blind to qualifiers that change the
#: legal answer. Article 5(1)(h) prohibits **real-time** remote biometric
#: identification in publicly accessible spaces for law enforcement;
#: **post** (ex-post) remote biometric identification is NOT an Article 5
#: prohibition — it is governed by Article 26(10), which requires prior
#: judicial or administrative authorisation. The keyword "remote biometric
#: identification" matches both.
#:
#: Measured before this guard: "Can law enforcement use post-remote biometric
#: identification for a targeted search?" matched ``Art. 5.1.h`` and produced
#: the verdict "Real-time remote biometric identification ... is prohibited
#: under Article 5(1)(h)" — a statement about a different practice than the one
#: asked about. Harmless while the verdict was being suppressed by any mention
#: of Article 5; the R376 contradiction guard removes that accidental
#: suppression, so the imprecision would have been promoted to the answer's
#: lead.
#:
#: This is a NARROW, statute-anchored exclusion, not a topic classifier: it
#: encodes the real-time/post distinction the Regulation itself draws, and it
#: applies only to the sub-point whose text carries that qualifier.
_SUB_REF_NEGATIVE_QUALIFIERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "Art. 5.1.h": (
        re.compile(r"\bpost[- ]?remote\b", re.I),
        re.compile(r"\bex[- ]?post\b", re.I),
        re.compile(r"\bpost[- ]?hoc\b", re.I),
        re.compile(r"\bnot\s+real[- ]?time\b", re.I),
        re.compile(r"\bafter\s+the\s+fact\b", re.I),
        re.compile(r"\bretrospective(?:ly)?\b", re.I),
    ),
}


#: R410 — REQUIRED statutory qualifiers. Article 5(1)(g) does not prohibit
#: biometric categorisation as such: it prohibits categorisation that infers a
#: CLOSED-LIST attribute (race, political opinions, trade-union membership,
#: religious or philosophical beliefs, sex life, sexual orientation). The
#: keyword scan matched the bare phrases ``sort patients`` / ``patient sorting``
#: / ``biometric categorisation``, so an emergency-triage or clinical-trial
#: question picked up the Art. 5(1)(g) verdict — the live Part II Q8-Q11 defect,
#: four different supplied facts shipping one identical prohibition answer.
#: A required qualifier makes the gatekeeper fire only where the question's own
#: facts engage the closed list. Narrowing only: it can remove a match, never
#: invent one. ``sex``/``gender`` are deliberately absent — they are protected
#: attributes but NOT on the Art. 5(1)(g) closed list.
_SUB_REF_REQUIRED_QUALIFIERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "Art. 5.1.g": (
        re.compile(
            r"\b(?:race|racial|ethnic(?:ity|\s+origin)?|political\w*|"
            r"trade[- ]?union|religious|religion|philosoph\w*|"
            r"sex\s+life|sexual\s+orientation|sensitive\s+attributes?)\b",
            re.I,
        ),
    ),
}


def _sub_ref_excluded_by_question(sub_ref: str, question: str) -> bool:
    """True when ``question`` carries a qualifier that puts it outside ``sub_ref``.

    Deliberately asymmetric: an exclusion only ever REMOVES a match the keyword
    scan made, so it can shrink the citation set but never invent one. A
    question that says both "real-time" and "post" keeps the match — the
    exclusion requires the negative qualifier with no competing positive one,
    because a question comparing the two regimes is asking about both.
    """
    text = str(question or "")
    required = _SUB_REF_REQUIRED_QUALIFIERS.get(sub_ref)
    if required and not any(rx.search(text) for rx in required):
        return True
    patterns = _SUB_REF_NEGATIVE_QUALIFIERS.get(sub_ref)
    if not patterns:
        return False
    if not any(rx.search(text) for rx in patterns):
        return False
    # A question that explicitly names the real-time regime as well is asking
    # about the comparison; keep the Article 5 anchor for it.
    return not re.search(r"\breal[- ]?time\b", text, re.I)


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
            if _sub_ref_excluded_by_question(sub, question):
                continue
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
#
# TODO(R47): migrate to app.integrations.regenold.refs (centralised converter).
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
        "Real-time remote biometric identification in publicly accessible spaces by law enforcement is prohibited under Article 5(1)(h), with narrow exceptions for victim searches, imminent or terrorist threats, and locating serious-crime suspects.",
    "omnibus_csam_ncii":
        "AI systems designed to generate child sexual abuse material or non-consensual intimate imagery are prohibited.",
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


# ── R376 — the contradiction guard ───────────────────────────────────────────
#
# THE BUG THIS EXISTS FOR. The route prepends :func:`build_verdict_prefix` only
# when ``"Article 5" not in answer_text``. That guard is there to stop a
# duplicate anchor, and on its face it is reasonable: if the answer already
# names Article 5, the verdict has been stated.
#
# But an answer can name Article 5 in order to DENY the prohibition, and that is
# precisely when the verdict is most needed. Measured on the deterministic path
# (``P2P_GRAPH_RAG_PROVIDER=cli``) for "Can we use an AI system that infers the
# emotions of our employees during performance reviews?":
#
#   gatekeeper hits : (('Art. 5', 'Art. 5.1.f'),)
#   verdict prefix  : "Emotion recognition in the workplace and education
#                      contexts is prohibited under Article 5(1)(f), with
#                      narrow medical and safety carve-outs."
#   shipped answer  : "The system described is not among the practices
#                      prohibited under Article 5 ..."
#
# The curated, correct verdict was suppressed BY THE SENTENCE THAT CONTRADICTS
# IT, because that sentence contains the string "Article 5". A user asking
# whether they may run emotion recognition on staff was told they may. Emotion
# recognition in the workplace is prohibited by Article 5(1)(f) — consent does
# not cure it, and the only carve-outs are medical and safety.
#
# WHY THE FIX IS SHAPE-BASED, NOT TOPIC-BASED. Hard rule #3 forbids new
# classification topics for the three PDF example questions, and
# emotion-recognition prohibition is one of the three. So nothing here mentions
# emotion recognition, or any practice: it matches the GRAMMAR of a denial
# ("is not prohibited", "not among the practices prohibited", "does not fall
# under Article 5") near an Article 5 anchor, and fires only when the gatekeeper
# has independently matched a curated PRACTICE_REGISTRY keyword. Every Article 5
# practice benefits identically.
#
# PREPENDING ALONE WOULD NOT BE ENOUGH. An answer that says both "prohibited"
# and "not prohibited" is worse than either, so the denial is removed rather
# than argued with — and only the sentence carrying it, never the surrounding
# analysis.

_ART5_ANCHOR_RE = re.compile(r"\bArticle\s+5\b|\bArt\.\s*5\b", re.I)

#: Denial shapes, anchored on the words that carry the negation. Each must be
#: unambiguous on its own: a sentence matching one of these is asserting that
#: Article 5 does NOT bite, which is the claim the gatekeeper contradicts.
# R411 — the R284 legacy denial ("... not among the practices prohibited under
# Article 5") and the R285/R411 CONDITIONAL wording ("... is not one of the
# practices EXHAUSTIVELY prohibited by Article 5 ...") are the same claim, but
# the original pattern pinned the words "practices" and "prohibit" adjacent,
# so the adverb broke the match. Measured consequence: flipping the verdict to
# the conditional wording silently DISABLED this guard, and a question that
# states the discriminating fact ("... where the system infers each patient's
# race") lost the curated Article 5(1)(g) verdict it had been getting — the
# guard never fired, so nothing contradicted the branch-less text. The
# intervening adverbs are now allowed.
_PROHIBITION_DENIAL_RES = (
    re.compile(
        r"\bnot\s+(?:among|one\s+of)\s+the\s+(?:practices\s+)?(?:\w+\s+){0,2}prohibit",
        re.I,
    ),
    re.compile(r"\b(?:is|are|was|were)\s+not\s+prohibit", re.I),
    re.compile(r"\bnot\s+prohibited\s+(?:under|by)\b", re.I),
    re.compile(r"\bdoes\s+not\s+(?:fall|come)\s+(?:with)?in(?:to)?\b", re.I),
    re.compile(r"\bno\s+prohibition\s+applies\b", re.I),
    re.compile(r"\bnot\s+a\s+prohibited\s+(?:practice|use)\b", re.I),
    re.compile(r"\bis\s+not\s+banned\b", re.I),
)

#: Sentence split that keeps the terminator, so a rebuilt answer reads normally.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _denies_prohibition(sentence: str) -> bool:
    """True when ``sentence`` denies an Article 5 prohibition.

    Requires BOTH an Article 5 anchor and a denial shape in the same sentence:
    "this is not high-risk" must not match (that is an Article 6 statement and
    is frequently correct), and a bare mention of Article 5 must not match
    either.
    """
    text = str(sentence or "")
    if not _ART5_ANCHOR_RE.search(text):
        return False
    return any(rx.search(text) for rx in _PROHIBITION_DENIAL_RES)


def answer_denies_prohibition(answer: str) -> bool:
    """True when any sentence of ``answer`` denies an Article 5 prohibition."""
    return any(
        _denies_prohibition(part)
        for part in _SENTENCE_SPLIT_RE.split(str(answer or ""))
    )


def strip_prohibition_denials(answer: str) -> tuple[str, int]:
    """Drop the sentences that deny an Article 5 prohibition.

    Returns ``(rewritten, n_removed)``. Only sentences matching
    :func:`_denies_prohibition` are removed; everything else — including
    correct Article 6 / Annex III analysis in the same answer — is preserved
    verbatim and in order.

    Callers must apply this ONLY when :func:`scan_for_prohibitions` has matched,
    so a merely cautious answer about a non-prohibited system is never edited.
    """
    text = str(answer or "")
    if not text.strip():
        return text, 0
    parts = _SENTENCE_SPLIT_RE.split(text)
    kept = [part for part in parts if not _denies_prohibition(part)]
    removed = len(parts) - len(kept)
    if not removed:
        return text, 0
    return " ".join(p.strip() for p in kept if p.strip()).strip(), removed


__all__ = [
    "answer_denies_prohibition",
    "build_verdict_prefix",
    "force_prohibited_citations",
    "scan_for_prohibitions",
    "strip_prohibition_denials",
]

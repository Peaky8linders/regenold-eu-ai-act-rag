"""Tone enforcement guard (R38 / Issue A4).

The Regenold competition rubric scores 'professional tone' against
gold examples. Strip LLM hedge prefixes ("I think", "It seems") and
self-references ("As an AI") that don't appear in regulator voice.
Preserve sentences that already lead with a citation anchor or an
imperative.

Designed to be fail-soft: on any exception, return the original input.
"""
from __future__ import annotations

import re

# Hedge patterns, ordered longest-first so compound hedges peel cleanly.
# Each pattern matches from start of string, case-insensitive, including
# a trailing punctuation + space.
_HEDGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*as\s+an\s+ai(?:\s+(?:language\s+)?model)?[,\.\s]+(?:i\s+(?:can(?:not)?|am)\s+\S+\s+\S+[,\.\s]+)?", re.I),
    re.compile(r"^\s*based\s+on\s+(?:my\s+(?:understanding|reading|interpretation|knowledge)|the\s+(?:provided\s+)?information)[,\.\s]+", re.I),
    re.compile(r"^\s*please\s+note(?:\s+that)?[,\.\s]+", re.I),
    re.compile(r"^\s*it\s+(?:seems|appears|is\s+(?:likely|possible))\s+(?:that[,\.\s]+)?", re.I),
    re.compile(r"^\s*i\s+(?:think|believe|would\s+argue|understand)(?:\s+that)?[,\.\s]+", re.I),
    re.compile(r"^\s*in\s+my\s+(?:opinion|view|understanding)[,\.\s]+", re.I),
    re.compile(r"^\s*to\s+(?:the\s+best\s+of\s+my|my)\s+(?:knowledge|understanding)[,\.\s]+", re.I),
    re.compile(r"^\s*from\s+what\s+i\s+(?:can\s+tell|understand|see)[,\.\s]+", re.I),
    # R52.1-B — first-person advisory openers surfaced by R50 judge
    # (4 rows hit "first-person casual framing"). Sonnet drifts into
    # "I would recommend…" / "we recommend…" style on advisory shapes;
    # the regulator-voice rubric hard-fails on first-person.
    re.compile(r"^\s*i\s+would\s+(?:recommend|suggest|advise|note|argue)[,\.\s]+", re.I),
    re.compile(r"^\s*we\s+(?:would\s+)?(?:recommend|suggest|advise|note)(?:\s+that)?[,\.\s]+", re.I),
    re.compile(r"^\s*(?:let\s+me|let\s+us)\s+(?:explain|clarify|note|address)(?:\s+that)?[,\.\s]+", re.I),
    re.compile(r"^\s*(?:my|our)\s+(?:recommendation|suggestion|advice)\s+(?:would\s+be|is)(?:\s+that)?[,\.\s]+", re.I),
)


# ── R53.1-A — mid-sentence first-person rewrites ──
#
# R52.1-B's opener strip caught ~80% of judge tone failures. The remaining
# 6 V2 rows showed Sonnet drifting into first-person AFTER the opener —
# "we should also note that…", "let me address…", "I would note that…".
# Single-sentence opener-strip can't reach these because the cite anchor
# legitimately leads (e.g. "Article 26 requires X. We should also note Y.").
#
# This R53.1-A rewriter is INTENTIONALLY CONSERVATIVE. Only the 7
# highest-confidence patterns from judge data ship below; each was
# traced against the planned test cases to verify grammatical output.
# Quote-awareness (e.g. preserving `the 'we' in Article 3` style
# definitional callouts) is deferred to R54 — none of the current
# patterns will match a bare quoted pronoun because each requires a
# following verb / modal.
_FIRST_PERSON_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "we should (also) note that ..." — drop the whole clause lead-in.
    # Must come BEFORE the bare "we should" pattern (leftmost alternation
    # would otherwise strip just "we should" and leave a stranded "note that").
    (re.compile(r"\bwe\s+should\s+(?:also\s+)?note\s+that\s+", re.I), ""),
    # "we should (also) <verb>" — drop the modal stack, keep the verb as imperative.
    (re.compile(r"\bwe\s+should\s+(?:also\s+)?", re.I), ""),
    # "we would/will recommend/suggest/advise/note (that) ..." — drop.
    (re.compile(r"\bwe\s+(?:would|will)\s+(?:recommend|suggest|advise|note)\s+(?:that\s+)?", re.I), ""),
    # "let me/us address/clarify/explain/note (that) ..." — drop the lead-in.
    (re.compile(r"\blet\s+(?:me|us)\s+(?:address|clarify|explain|note)\s+(?:that\s+)?", re.I), ""),
    # "I would note that / I would <verb> ..." — drop. The "note that"
    # alternative must come first so the trailing "that" gets consumed.
    (re.compile(r"\bi\s+would\s+(?:note\s+that|note|argue|recommend|suggest|advise)\s+", re.I), ""),
    # "in our view/opinion/assessment, ..." — drop the preamble.
    (re.compile(r"\bin\s+our\s+(?:view|opinion|assessment)[,]?\s*", re.I), ""),
    # "(my|our) recommendation/suggestion/assessment (would be|is) (that) ..."
    (re.compile(r"\b(?:my|our)\s+(?:recommendation|suggestion|assessment)\s+(?:would\s+be|is)\s+(?:that\s+)?", re.I), ""),
)

# R54.1 — abbreviation-aware sentence boundary. The naive `[.!?]+\s+`
# was capitalising the word after every `e.g.` / `i.e.` / `etc.` /
# `Art. N` / `Annex N.`. Now we use a negative lookbehind to skip
# the common Latin abbreviations + numbered-list short forms
# (`Art.` / `Arts.` / `Annex N.`). Re-join semantics are preserved
# (capture groups still carry the punctuation + gap).
#
# Pattern explanation:
#   (?<!\be\.g) (?<!\bi\.e) (?<!\betc) — Latin abbrev lookbehinds
#   (?<!\bArt) (?<!\bArts) (?<!\bAnnex) — regulation cite lookbehinds
#   ([.!?]+)(\s+|$) — capture the actual terminator + gap
_SENTENCE_SPLIT = re.compile(
    r"(?<!\be\.g)(?<!\bi\.e)(?<!\betc)"
    r"(?<!\bArt)(?<!\bArts)(?<!\bAnnex)"
    r"([.!?]+)(\s+|$)"
)


def _capitalise_first_letter(s: str) -> str:
    if not s:
        return s
    if s[0].islower():
        return s[0].upper() + s[1:]
    return s


def _rewrite_first_person_mid_sentence(s: str) -> str:
    """Walk each sentence; apply mid-sentence first-person rewrites.

    Splits on sentence-terminal punctuation, applies each pattern in
    `_FIRST_PERSON_REWRITES` to ALL occurrences within the sentence
    (R53.1-A bug: count=1 let the second occurrence of the same
    pattern in one sentence slip through — e.g. "we should X and we
    should Y" only stripped the first). Restores capitalisation,
    collapses double spaces, and re-joins.

    R54.1 (deep-code-review I4) — when a rewrite empties the entire
    sentence (e.g., "In our view." → ""), DROP the sentence
    entirely (don't append the orphan punctuation and gap), so the
    output doesn't carry a leading ". " artefact in front of the
    next sentence.

    Fail-soft: on any exception, returns the input unchanged.
    """
    if not s:
        return s
    try:
        # Tokenize into [sentence, punctuation, gap, sentence, punctuation, gap, ...]
        # Final fragment (no terminal punct) lands as the last element.
        parts = _SENTENCE_SPLIT.split(s)
        rebuilt: list[str] = []
        # parts layout: text, punct, gap, text, punct, gap, ..., text
        i = 0
        while i < len(parts):
            text = parts[i]
            cleaned = text
            for pattern, replacement in _FIRST_PERSON_REWRITES:
                # count=0 → replace all occurrences in the sentence.
                # Pattern ordering invariant (longest/specific first)
                # ensures e.g. "we should note that X" is handled by
                # pattern #1 before pattern #2 can claim "we should".
                cleaned = pattern.sub(replacement, cleaned)
            # Collapse internal whitespace runs from clause drops.
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
            cleaned = _capitalise_first_letter(cleaned)
            # R54.1 (I4) — if the rewrite emptied the sentence AND
            # there's a following sentence, skip the orphan
            # punctuation+gap pair entirely. Last fragment with no
            # following parts is also dropped silently.
            if cleaned == "":
                # Advance past this empty sentence + its punct+gap
                # (if any) without appending anything.
                i += 3
                continue
            rebuilt.append(cleaned)
            # Append punctuation + gap (if present) verbatim.
            if i + 1 < len(parts):
                rebuilt.append(parts[i + 1])  # punctuation
            if i + 2 < len(parts):
                rebuilt.append(parts[i + 2])  # whitespace gap
            i += 3
        return "".join(rebuilt)
    except Exception:  # noqa: BLE001 — fail-soft per module contract
        return s


def enforce_tone(answer: str | None) -> str:
    """Strip hedge prefixes; preserve cite-anchored or imperative starts.

    Iterates patterns until no more strip; capitalises the resulting
    first letter. Returns "" on None input. Returns input verbatim on
    any internal exception (fail-soft per spec).
    """
    if not answer:
        return ""
    try:
        out = answer
        # Peel hedges iteratively — compound hedges (#9 test) need
        # multiple passes.
        for _ in range(4):  # bounded to avoid runaway loop
            before = out
            for pattern in _HEDGE_PATTERNS:
                out = pattern.sub("", out, count=1)
            if out == before:
                break
        out = out.strip()
        # R53.1-A — per-sentence first-person rewrite after opener strip.
        out = _rewrite_first_person_mid_sentence(out)
        out = _capitalise_first_letter(out)
        return out
    except Exception:  # noqa: BLE001 — fail-soft
        return answer

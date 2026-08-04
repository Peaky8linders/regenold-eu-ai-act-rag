"""R81-H — Preamble-strip answer normaliser.

Pure-stdlib post-processor for the final wire answer. Strips a small
set of known template preambles that the deterministic stub-stitcher
and Stage-2 polish ship, then strips the typographic "Article N — " /
"Annex N — " prefix grounded_prose and Sonnet inject in front of each
substantive sentence.

Rationale — measured against r81-a1-live (100/100 clean rows,
deployed Railway, Stage-2 polish ON via Claude Max wrapper):

* Ans Loose **0.124** / Ans Strict **0.253** are the two weakest
  rubric axes (`evals/bench/metrics.py`).
* The Strict > Loose inversion proves the pred is verbose: Strict
  is recall (gold tokens recovered), Loose is Jaccard (recall +
  precision against pred). Strict > Loose iff pred carries tokens
  NOT in gold — i.e. preamble + paraphrase padding.
* **25/100** rows ship a `"This question is covered by the EU AI
  Act under Article X."` opener whose tokens (`question`, `covered`,
  `under`, `Article`, `Act`) are never gold-set members.
* **22/100** rows ship a `"Article N — "` typographic prefix on each
  substantive sentence. The cite is already in the `references`
  field; the prefix only adds non-gold tokens to the answer pred set.
* **3-5/100** rows ship a `"No specific EU AI Act articles were
  returned for this query, so no article citations can be made..."`
  refusal preamble FOLLOWED by substantive content (real answer
  tokens). Stripping the preamble keeps the substance, drops the
  noise.

Real-data simulation against the r81-a1-live sidecar:
**Loose +0.005, Strict −0.001 (noise), Conciseness +0.033**. 22/100
rows positive, 1 minor regression captured by the safety guards.

Safety rules (CRITICAL):

1. **Sentence-floor guard** — each LEAD pattern only strips if the
   remainder after the strip has ≥ 80 chars of substance. Without
   this, `qa_059`-style rows where the preamble IS effectively the
   whole answer would lose substance.
2. **Never-empty guard** — if any transform produces empty /
   whitespace-only output, return the ORIGINAL input. The whole
   transform is wrapped in `try / except` returning original on any
   exception.
3. **Article-prefix strip** — only fires when a substantive token
   (≥ 1 alphabetic word) follows the prefix AND remainder ≥ 80 chars.
4. **Re-capitalise** the first letter after a strip (substance often
   starts with a lowercase verb like "Requires...", "Classifies...").
5. **No connector-opener pattern** — patterns like "Based on the Act"
   are legitimate prose openers, NOT preambles. The plan's qa_059
   regression case proves over-greedy patterns kill Strict; this
   module deliberately does not match them.
6. **Idempotence** — `strip(strip(x)) == strip(x)` for all inputs.
"""

from __future__ import annotations

import re

__all__ = [
    "strip_preamble_templates",
    "strip_dash_separators",
    "strip_hedge_opener",
    "strip_section_headers",
    "strip_meta_commentary",
    "repair_elided_citation_anchors",
    "enumeration_guard_enabled",
    "enumeration_run_end",
    "enumeration_run_indices",
    "inline_enumeration_length",
    "answer_has_enumeration",
]


# ── R306 — enumeration-span guard ────────────────────────────────────
#
# THE DEFECT. The answer normaliser caps an answer at
# ``max_sentences`` sentences and, when over the char budget, drops the
# longest NON-citation-bearing sentence. Both passes are blind to
# whether the answer is in the middle of an ENUMERATION, so a list the
# model already started gets guillotined mid-run. Measured on the live
# wire (2026-08-03):
#
#   Q: "Under the EU AI Act, what are the four grounds on which
#       non-compliance may be alleged (as listed in Article 79(6))?"
#   Production shipped, on two independent runs:
#     "...due to one or more of the following four grounds.
#      (a) Non-compliance with the prohibition ... Article 5."   [277 chars]
#   i.e. it ANNOUNCED four and DELIVERED one. The same question run
#   in-process with the cap lifted returns all four grounds.
#
#   Q: "What are the deployer obligations under Art 50"
#   Production: "...deployers have three transparency obligations.
#      First, ... (Article 50(3)). Second, ... (Article 50(4))."  [464 chars]
#   Announced three, delivered two; the in-process uncapped answer
#   carries all three plus the two Article 50(4) carve-outs.
#
# WHY THE EXISTING ESCAPES MISS IT. ``normalise_answer_for_regenold``
# already lifts the cap to 12 when ``_is_closed_set_enumeration_ask``,
# ``_is_multi_phrase`` or ``is_complex_question`` fires — but all three
# inspect the QUESTION. All three return False for both questions
# above. Guarding a content-destroying cap behind a question-phrasing
# allowlist is whack-a-mole: every new phrasing of "list the N X" has
# to be enumerated in advance.
#
# THE FIX. Read the ANSWER instead. If the answer text already contains
# a run of >= 2 consecutively-labelled items ("First, ... Second, ...",
# "(a) ... (b) ...", "1. ... 2. ..."), the cap must not cut inside that
# run. This is:
#
#   * GENERAL — keyed on answer STRUCTURE, never on a topic, an article
#     number or an evaluator row (CLAUDE.md hard rule #3).
#   * BOUNDED — it protects the enumeration run and what precedes it,
#     and nothing else. Trailing commentary after the run stays
#     trimmable, so Answer-Conciseness (the one rubric axis this system
#     leads, i.e. the one with zero headroom) is not handed a blank
#     cheque. Hard-ceilinged at ``_ENUM_MAX_SENTENCES``.
#   * ADDITIVE-ONLY — it can only RAISE an effective cap, never lower
#     one, and it never invents content: it preserves items the model
#     already wrote. There is no fabrication surface.
#   * CAP-VALUE-AGNOSTIC — it holds whether the deployed cap is 3, 4 or
#     disabled, so it survives the railway.toml-vs-dashboard env drift
#     (R80.2) that put production on the default 3 in the first place.
#
# Env off-switch ``REGENOLD_ENUM_GUARD=0``.

# Hard ceiling on how far the guard may extend a cap. Matches the
# existing ``max_sentences`` clamp in ``models.py`` so a pathological
# answer cannot uncap the wire.
_ENUM_MAX_SENTENCES = 12

_ORDINAL_WORDS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
)

# "First, ..." / "Secondly: ..." / "And third, ...". A trailing comma or
# colon is REQUIRED so ordinary prose openers ("First-instance courts
# ...", "Second-hand data ...", "First the provider must") never match.
_ENUM_ORDINAL_RE = re.compile(
    r"^\s*(?:and\s+|then\s+)?(%s)(?:ly)?\s*[,:]" % "|".join(_ORDINAL_WORDS),
    re.IGNORECASE,
)

# "(a) text" / "a) text" / "(iv) text" is NOT matched here — roman
# numerals are excluded on purpose because "(i)" is ambiguous with the
# letter i and EU AI Act sub-points nest romans under letters.
_ENUM_LETTER_RE = re.compile(r"^\s*[\(\[]?([a-j])[\)\.\]]\s+\S", re.IGNORECASE)

# "1. text" / "(2) text". Single digit only: a sentence opening
# "2024 saw ..." must not read as item 2.
_ENUM_NUMBER_RE = re.compile(r"^\s*[\(\[]?([1-9])[\)\.\]]\s+\S")


def enumeration_guard_enabled() -> bool:
    """True unless ``REGENOLD_ENUM_GUARD`` is explicitly falsy."""
    import os  # noqa: PLC0415 — local to keep the import surface lean

    return os.getenv("REGENOLD_ENUM_GUARD", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _enum_marker(sentence: str) -> tuple[str, int] | None:
    """Classify a sentence's enumeration marker.

    Returns ``(kind, ordinal_value)`` — e.g. ``("ord", 2)`` for
    ``"Second, ..."``, ``("let", 3)`` for ``"(c) ..."`` — or ``None``
    when the sentence carries no list marker.
    """
    if not sentence:
        return None
    match = _ENUM_ORDINAL_RE.match(sentence)
    if match:
        return ("ord", _ORDINAL_WORDS.index(match.group(1).lower()) + 1)
    match = _ENUM_LETTER_RE.match(sentence)
    if match:
        return ("let", ord(match.group(1).lower()) - 96)
    match = _ENUM_NUMBER_RE.match(sentence)
    if match:
        return ("num", int(match.group(1)))
    return None


def enumeration_run_indices(sentences: list[str]) -> set[int]:
    """Indices of sentences that belong to a consecutive enumeration run.

    A "run" is >= 2 sentences carrying the SAME marker kind with
    CONSECUTIVELY INCREASING ordinals ("First," then "Second,"; "(a)"
    then "(b)"). Requiring both consecutiveness and a length of two
    keeps precision high: a lone "(a)" quoted as an illustration, or a
    sentence that merely opens with "Finally,", is not a run.
    """
    hits: set[int] = set()
    if not sentences:
        return hits
    i = 0
    while i < len(sentences):
        marker = _enum_marker(sentences[i])
        if marker is None:
            i += 1
            continue
        kind, value = marker
        run = [i]
        expect = value + 1
        j = i + 1
        while j < len(sentences):
            nxt = _enum_marker(sentences[j])
            if nxt is not None and nxt[0] == kind and nxt[1] == expect:
                run.append(j)
                expect += 1
                j += 1
                continue
            break
        if len(run) >= 2:
            hits.update(run)
            i = j
        else:
            i += 1
    return hits


def enumeration_run_end(sentences: list[str]) -> int:
    """Minimum number of leading sentences that must survive a cap.

    Returns ``last_run_index + 1`` (a 1-based sentence count) so the
    caller can use it directly as a floor on ``max_sentences``, or 0
    when the answer carries no enumeration run. Clamped to
    ``_ENUM_MAX_SENTENCES``.

    Note this deliberately returns the END of the run, not its size:
    the items are meaningless without the lead-in sentence that
    introduces them ("...one or more of the following four grounds.").
    """
    if not enumeration_guard_enabled():
        return 0
    try:
        hits = enumeration_run_indices(sentences)
    except Exception:
        return 0
    if not hits:
        return 0
    return min(max(hits) + 1, _ENUM_MAX_SENTENCES)


# An INLINE run — "…: (a) foo; (b) bar; (c) baz." — is a single
# sentence, so it sails past the sentence cap untouched and is instead
# shredded by the route's readable-unit cap (which counts each ``(x)``
# clause as a unit) and by ``_hard_truncate_at_clause`` (which truncates
# AT an enumerator boundary). Detect it separately from the
# one-item-per-sentence shape.
_INLINE_MARKER_RE = re.compile(r"[\(\[]([a-j])[\)\]]\s+\S", re.IGNORECASE)


def inline_enumeration_length(text: str) -> int:
    """Length of the longest inline ``(a) … (b) … (c) …`` run in ``text``.

    Returns 0 when there is no run of at least two consecutively
    lettered inline markers. Requiring consecutiveness keeps a single
    quoted "(g)" — or a stray "(a)" inside an unrelated citation — from
    reading as a list.
    """
    if not text:
        return 0
    try:
        seq = [
            ord(m.group(1).lower()) - 96 for m in _INLINE_MARKER_RE.finditer(text)
        ]
    except Exception:
        return 0
    best = run = 0
    prev: int | None = None
    for value in seq:
        if prev is not None and value == prev + 1:
            run += 1
        else:
            run = 1
        best = max(best, run)
        prev = value
    return best if best >= 2 else 0


def answer_has_enumeration(text: str) -> bool:
    """True when the answer already carries an enumeration, in EITHER shape.

    This is the answer-keyed sibling of the question-keyed
    ``_is_closed_set_enumeration_ask`` / ``_is_multi_phrase`` escapes.
    Those ask "did the USER request a list?"; this asks "did the MODEL
    already write one?" — which is the property that actually decides
    whether a truncation will destroy content, and unlike the question
    side it needs no phrase allowlist.
    """
    if not text or not enumeration_guard_enabled():
        return False
    try:
        if inline_enumeration_length(text) >= 2:
            return True
        from app.integrations.regenold.models import (  # noqa: PLC0415
            _split_sentences,
        )

        return bool(enumeration_run_indices(_split_sentences(text)))
    except Exception:
        return False


# ── Dash-separator normalisation ─────────────────────────────────────
#
# EU AI Act legal prose reads cleanest without dash *separators*: an
# em-dash (``—``), en-dash (``–``), or a spaced hyphen (``" - "``) used
# as a clause break or appositive reads as informal / database-dump
# style and is penalised by the regulatory-tone bar. Stage-2 Sonnet
# polish and a few hand-authored KB describers emit them; this is the
# deterministic backstop that guarantees the wire answer never ships
# one.
#
# CRITICAL — intra-word hyphens are NEVER touched. Standard regulatory
# terminology ("high-risk", "socio-economic", "post-market",
# "call-centre", "AI-generated", "one-third", "open-source") uses the
# hyphen-minus (``-``) inside a word with NO surrounding whitespace and
# is correct legal wording. Only the typographic dash characters and a
# whitespace-flanked hyphen are rewritten.
#
# Replacement policy:
#   * dash between two digits (a numeric range, e.g. ``2025–2027``,
#     ``10–25``) → ``" to "`` (reads as professional legal prose).
#   * any other dash separator → ``", "`` (comma). Comma is the most
#     grammatically forgiving substitution for an appositive /
#     parenthetical / clause break and reads as continuous prose.

# Numeric-range dash: digit, optional space, em/en dash, optional
# space, digit  →  " to ".
_RANGE_DASH_RE = re.compile(r"(?<=\d)\s*[—–]\s*(?=\d)")
# Numeric-range spaced hyphen: digit ` - ` digit  →  " to ".
_RANGE_SPACED_HYPHEN_RE = re.compile(r"(?<=\d)\s-\s(?=\d)")
# Sentence-terminator immediately followed by a dash separator
# (``". — "`` / ``"! – "``) — keep the sentence break, drop the dash, so
# we never leave a ``"., "`` period-comma artifact. Run BEFORE the
# generic separator rules. A terminator is never a digit, so the range
# rules above can't have consumed it.
_TERM_DASH_RE = re.compile(r"([.!?])\s*[—–]\s*")
_TERM_SPACED_HYPHEN_RE = re.compile(r"([.!?])\s+-\s+")
# Em/en dash used as a separator (spaced or unspaced)  →  ", ".
_SEP_DASH_RE = re.compile(r"\s*[—–]\s*")
# Spaced hyphen used as a dash (whitespace on BOTH sides — never an
# intra-word hyphen)  →  ", ".
_SEP_SPACED_HYPHEN_RE = re.compile(r"\s+-\s+")


def strip_dash_separators(text: str) -> str:
    """Replace dash *separators* with legal-prose punctuation.

    Em/en dashes and whitespace-flanked hyphens used as clause breaks
    become commas (or ``" to "`` between digits). Intra-word hyphens in
    compound legal terms are preserved untouched.

    Pure, idempotent, fail-soft: any exception (or a non-string /
    empty input) returns the input unchanged.
    """
    if not text or not isinstance(text, str) or not text.strip():
        return text
    try:
        out = _RANGE_DASH_RE.sub(" to ", text)
        out = _RANGE_SPACED_HYPHEN_RE.sub(" to ", out)
        # Terminator + dash → keep the sentence break (no period-comma).
        out = _TERM_DASH_RE.sub(r"\1 ", out)
        out = _TERM_SPACED_HYPHEN_RE.sub(r"\1 ", out)
        out = _SEP_DASH_RE.sub(", ", out)
        out = _SEP_SPACED_HYPHEN_RE.sub(", ", out)
        # Tidy artefacts a substitution may leave behind.
        out = re.sub(r",\s*,", ",", out)        # ",," → ","
        out = re.sub(r"\s+,", ",", out)          # " ," → ","
        out = re.sub(r"[ \t]{2,}", " ", out)     # collapse runs of spaces
        out = re.sub(r"^\s*,\s*", "", out)        # leading dash → comma → drop
        return out.strip()
    except Exception:
        return text


# ── Patterns ─────────────────────────────────────────────────────────


# Lead templates. Each pattern matches a single template sentence at
# the START of the answer, terminated by `.\s+` (period + whitespace)
# so the boundary is unambiguous. The `[^.]+?` between `under` and
# the period is lazy so we always stop at the FIRST period — never
# eat through into the substantive prose.
LEAD_TEMPLATES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r'^This question is covered by the EU AI Act under [^.]+?\.\s+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^No specific EU AI Act (?:articles|provisions|references) '
        r'(?:were|are) (?:returned|surfaced|matched|retrieved) for this '
        r'query[^.]*?, so [^.]+?\.\s+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^The matched EU AI Act references '
        r'(?:do not specify|do not contain|contain no) [^.]+?\.\s+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^The EU AI Act references? block '
        r'(?:is empty|contains no [^.]+?)\.\s+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^No EU AI Act articles? (?:were|are) returned for this '
        r'query[^.]*?\.\s+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^No EU AI Act article references? were surfaced for this '
        r'query[^.]*?\.\s+',
        re.IGNORECASE,
    ),
)


# "Article N — " / "Annex N — " prefix anywhere in the text (not just
# the start). Matches the typographic prefix `stitch_grounded_prose`
# / Sonnet inject before each substantive sentence. The `(?<![A-Za-z])`
# left lookbehind ensures we don't match mid-word; the alphabetic-word
# check after the dash (in `_strip_article_prefixes`) ensures we don't
# strip when nothing substantive follows.
ARTICLE_PREFIX_RE: re.Pattern[str] = re.compile(
    r'(?<![A-Za-z])(?:Article|Annex)\s+(?:\d+|[IVXLC]+)'
    r'(?:\.[\dIVXLCa-z]+)*\s+[—\-–:]\s+',
    re.IGNORECASE,
)


# Minimum substantive characters that must follow a LEAD strip. If
# the remainder is shorter than this, the template IS effectively the
# whole answer and stripping it would empty the substance.
_MIN_SUBSTANTIVE_REMAINDER = 80


# ── Helpers ──────────────────────────────────────────────────────────


def _capitalise_first_letter(text: str) -> str:
    """Capitalise the first alphabetic character of ``text``.

    Walks past any leading whitespace / punctuation. Returns ``text``
    unchanged if no alphabetic character is found.
    """
    if not text:
        return text
    for i, ch in enumerate(text):
        if ch.isalpha():
            if ch.islower():
                return text[:i] + ch.upper() + text[i + 1:]
            return text
    return text


def _strip_lead_templates(text: str) -> str:
    """Apply each LEAD pattern once at the start of ``text``.

    Each strip only fires if the remainder has ≥ 80 chars of
    substance (the sentence-floor guard). Re-capitalises the first
    letter after a successful strip.
    """
    out = text
    for pat in LEAD_TEMPLATES:
        m = pat.match(out)
        if not m:
            continue
        candidate = out[m.end():]
        if len(candidate.strip()) < _MIN_SUBSTANTIVE_REMAINDER:
            # Sentence-floor guard: don't strip if it would leave the
            # answer with too little substance.
            continue
        out = _capitalise_first_letter(candidate.lstrip())
    return out


def _strip_article_prefixes(text: str) -> str:
    """Strip ``"Article N — "`` / ``"Annex N — "`` typographic prefixes.

    Only fires when remainder is substantive (≥ 1 alphabetic word
    follows) AND the post-strip text has ≥ 80 chars remaining (so we
    don't denude short answers). Iterates: a prefix may be removed,
    then another prefix may now be at a sentence start.
    """
    out = text
    while True:
        m = ARTICLE_PREFIX_RE.search(out)
        if not m:
            break
        before = out[:m.start()]
        after = out[m.end():]
        # Require substantive remainder: ≥ 1 alphabetic word AND
        # ≥ 80 chars total remaining (combined before+after).
        if not re.search(r'[A-Za-z]+', after):
            break
        combined = (before + after).strip()
        if len(combined) < _MIN_SUBSTANTIVE_REMAINDER:
            break
        # Re-capitalise the first letter of `after` if it now starts
        # a sentence (i.e. before is empty or ends with terminal
        # punctuation).
        if not before.strip() or before.rstrip().endswith(('.', '!', '?')):
            after = _capitalise_first_letter(after.lstrip())
            # Re-add a single space between before and after if
            # before is non-empty and doesn't end with whitespace.
            if before and not before.endswith(' '):
                before = before.rstrip() + ' '
        out = before + after
    return out


# ── Public API ───────────────────────────────────────────────────────


def strip_preamble_templates(text: str) -> str:
    """Strip known preamble templates + ``Article N — `` prefixes.

    Pure post-processor. Idempotent. Fail-soft: any exception returns
    the original input unchanged. Never returns empty / whitespace
    when the input was non-empty.

    Returns the cleaned text ready for the downstream hard-char-cap
    backstop in :func:`normalise_answer_for_regenold`.
    """
    if not text or not text.strip():
        return text
    original = text
    try:
        out = _strip_lead_templates(text)
        out = _strip_article_prefixes(out)
        # Never-empty guard.
        if not out or not out.strip():
            return original
        return out
    except Exception:
        # Fail-soft: any exception returns the original.
        return original


# R139 — colloquial "It depends" hedge opener. The Stage-2 DIRECT-VERDICT rule
# formerly modelled "It depends: high-risk only when …" as a conditional-verdict
# opener; "It depends" reads as conversational, not EU-AI-Act legal-professional
# voice. A delimiter must immediately follow "depends" (so "It depends on
# whether …" — which carries the deciding condition before any delimiter — is
# left untouched).
_HEDGE_OPENER_RE = re.compile(r"^\s*it\s+depends\b\s*[:.,;—–-]+\s*", re.IGNORECASE)


def strip_hedge_opener(text: str) -> str:
    """R139 — strip a leading colloquial ``It depends`` hedge from the answer.

    Removes a leading ``It depends:`` / ``It depends, `` / ``It depends. `` /
    ``It depends — `` so the answer leads with the regulatory classification
    itself (the remainder is already the conditional verdict, e.g. ``High-risk
    only where …``). Conservative: fires ONLY when a delimiter immediately
    follows ``depends`` AND the remainder still carries substance (≥ 40 chars),
    so a near-empty ``It depends.`` is left intact. Pure, idempotent, fail-soft;
    never empties. Env-reversible ``REGENOLD_STRIP_HEDGE=0``.
    """
    import os  # noqa: PLC0415 — local to keep the module import surface lean

    if os.getenv("REGENOLD_STRIP_HEDGE", "1").strip().lower() in (
        "0", "false", "no", "off",
    ):
        return text
    if not text or not text.strip():
        return text
    try:
        m = _HEDGE_OPENER_RE.match(text)
        if not m:
            return text
        remainder = text[m.end():].lstrip()
        if len(remainder) < 40:
            # Substance floor — don't strip a near-empty answer down to a stub.
            return text
        out = _capitalise_first_letter(remainder)
        return out if out and out.strip() else text
    except Exception:
        return text


# R145 — pseudo-section-header fragments. Opus 4.8, on complex multi-part
# classification questions ("Is X prohibited? Or high-risk per Annex III?"),
# sometimes structures the answer as a sectioned legal memo with short
# heading-like sentence fragments that announce a sub-topic instead of stating
# substance — e.g. "Why it is not prohibited (Article 5).", "Why it is not
# Annex III high-risk.", "The condition that would make it high-risk (Article
# 6)." Those fragments read as headings even without markdown (hurting the
# conciseness axis) and the per-issue sections they introduce restate the same
# finding several times (hurting coherence). The Stage-2 prompt forbids them at
# source (rule 5c); this is the deterministic backstop. Conservative + high
# precision: it drops ONLY a sentence that matches a header shape AND is short,
# never empties the answer, never drops a substantive sentence (the content the
# fragment announced survives in the following sentence). davidath is
# byte-identical (deterministic answers never carry these fragments, and the
# bench runs provider=cli with no Stage-2). Env-reversible
# ``REGENOLD_STRIP_SECTION_HEADERS=0``.

_HEADER_MAX_CHARS = 95

# Pattern Q — declarative "Why <subject> <be/aux> ..." fragment that is NOT a
# question. A real answer sentence never opens "Why it is not prohibited." as a
# STATEMENT; that shape is always a rhetorical section label.
_WHY_HEADER_RE = re.compile(
    r"^\s*Why\s+(?:it|this|that|the\s+system|the\s+tool|the\s+model|"
    r"the\s+application|the\s+service|the\s+software)"
    r"(?:'s|\s+(?:is|was|are|does|do|would|becomes?|qualifies|falls|"
    r"counts|remains?|applies))\b[^?]*?[.:]?\s*$",
    re.IGNORECASE,
)

# Pattern P — "The <issue-noun> that/which <relative clause> (Article N)." — an
# IRAC issue-header noun phrase that ends in a parenthetical statutory tag with
# NO main-clause predicate. The relativizer (that/which/...) immediately after
# the issue noun + the finite-verb exclusion (below) keep a SUBSTANTIVE sentence
# such as "The condition that triggers high-risk is third-party conformity
# assessment (Article 6)." (the relative clause carries an "is" predicate) and a
# plain "The condition is X (Article 6)." (no relativizer) both intact.
_ISSUE_HEADER_RE = re.compile(
    r"^\s*The\s+(?:condition|reason|route|test|basis|trigger|distinction|"
    r"exception|consequence|rationale|factor|element|circumstance|"
    r"first\s+route|second\s+route|remaining\s+route|other\s+route|"
    r"applicable\s+route|key\s+condition|operative\s+condition)\s+"
    r"(?:that|which|under\s+which|for\s+which)\s+(?P<mid>[^?()]*?)\s*"
    r"\((?:Article|Annex)\s+[^)]+\)\s*[.:]?\s*$",
    re.IGNORECASE,
)
# A finite copula/main predicate inside the relative clause means the sentence
# carries substance ("...that IS X (Article N).") — NOT a bare issue header.
_FINITE_PREDICATE_RE = re.compile(
    r"\b(?:is|are|was|were|means|requires?|applies|covers?|includes?|"
    r"establishes?|sets|lays|mandates?|prohibits?|classifies)\b",
    re.IGNORECASE,
)

# Sentence boundary (naive — sufficient: a header fragment ends in a clean
# ". "/".$" boundary, and a mis-split of mid-sentence abbreviations can never
# fabricate a header match, so the rejoin reconstructs the original text).
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")

_MIN_SECTION_REMAINDER = 80


def _is_section_header_fragment(sentence: str) -> bool:
    """True iff ``sentence`` is a short pseudo-section-header fragment."""
    s = sentence.strip()
    if not s or len(s) > _HEADER_MAX_CHARS:
        return False
    if "?" in s:
        # A question is not a declarative header (and an answer should not echo
        # the user's question); leave it for the caller to handle.
        return False
    if _WHY_HEADER_RE.match(s):
        return True
    m = _ISSUE_HEADER_RE.match(s)
    if m and not _FINITE_PREDICATE_RE.search(m.group("mid")):
        return True
    return False


def strip_section_headers(text: str) -> str:
    """R145 — drop pseudo-section-header sentence fragments from the answer.

    Removes short heading-like fragments such as "Why it is not prohibited
    (Article 5)." or "The condition that would make it high-risk (Article 6)."
    that Opus emits when it over-structures a complex classification answer as a
    sectioned memo. The substantive content those fragments announce survives in
    the following sentence, so removal loses no information; it improves
    conciseness (drops the padding) and coherence (kills the IRAC scaffolding).

    Conservative + fail-soft: drops ONLY sentences matching a tight header shape;
    never empties the answer (returns the original if removal would leave < 80
    chars of substance or no non-header sentence); idempotent. Env-reversible
    ``REGENOLD_STRIP_SECTION_HEADERS=0``.
    """
    import os  # noqa: PLC0415 — local to keep the module import surface lean

    if os.getenv("REGENOLD_STRIP_SECTION_HEADERS", "1").strip().lower() in (
        "0", "false", "no", "off",
    ):
        return text
    if not text or not text.strip():
        return text
    try:
        sentences = _SENTENCE_BOUNDARY_RE.split(text.strip())
        if len(sentences) < 2:
            # A single sentence is never a "section" structure; even if it
            # matched a header shape, dropping it would empty the answer.
            return text
        kept = [s for s in sentences if not _is_section_header_fragment(s)]
        if len(kept) == len(sentences):
            return text  # nothing matched
        remainder = " ".join(s.strip() for s in kept if s.strip()).strip()
        # Never-empty / substance-floor guard.
        if not remainder or len(remainder) < _MIN_SECTION_REMAINDER:
            return text
        out = _capitalise_first_letter(remainder)
        return out if out and out.strip() else text
    except Exception:
        return text


# R264 — internal-process meta-commentary leak. The Sonnet-5 live judge flagged
# answers that substantively ANSWER the question but leak internal-system
# language into the user-facing legal prose: q010 "...current retrieval
# surfaces...", q018 "...the references supplied above...", q035 "I should flag
# a framing problem...". These phrases never occur in a professional EU AI Act
# legal answer — they are the model narrating its own retrieval/framing. Unlike
# a refusal marker (which routes to the R49-A grounded-prose substitute), these
# rows carry a real answer; we only DROP the leaking sentence. High-precision,
# sentence-level, never-empty, fail-soft. Env-reversible ``REGENOLD_STRIP_META=0``.
_META_COMMENTARY_MARKERS: tuple[str, ...] = (
    "current retrieval",
    "references supplied above",
    "reference supplied above",
    "references provided above",
    "the retrieved context",
    "flag a framing problem",
    "i note a framing problem",
    "based on the retrieval",
    # R275 — internal reference-tag leaks observed live: Opus (Stage-2)
    # occasionally echoes the engine's internal context format, e.g.
    # "Wire references: [classification-annex_i_safety_component-Article 6]".
    # These are internal-only and must never reach the wire. Deterministic
    # answers never carry them, so this is davidath byte-identical.
    "wire references:",
    "[classification-",
)

_MIN_META_REMAINDER = 80

# ── R310 — structural retrieval-meta strip ──────────────────────────────
#
# WHY A REGEX AND NOT MORE LITERALS. The R264 marker list above is literal
# substrings, and on the r309 live batch it caught 0 of the 4 rows that
# actually leaked. The misses were near-misses of the markers it already
# has -- marker "references supplied above" vs live text "The references
# supplied HERE contain ...". That is the same whack-a-mole this codebase
# hit repeatedly with _STAGE2_REFUSAL_MARKERS (R49/R62/R65/R262): a literal
# list never catches the next phrasing. These match the SHAPE instead: the
# answer treating its own supplied source material as a subject.
#
# It is worth fixing because it is expensive out of proportion to its rate.
# On july7-125 the judge called the legal conclusion CORRECT ("directly
# states both operative holdings the question demands") yet failed the row
# on answer_correctness -- scoring the self-referential sourcing claim as a
# fabricated proposition -- AND on conciseness ("meta-commentary on source
# completeness"). One sentence, two of four axes.
#
# The live shapes this was built from (verbatim):
#   "The references supplied here contain Article 5 but not the
#    classification provisions themselves, so ..."
#   "Not as a standing entitlement on the provisions supplied here."
#   "The references provided do not settle whether ..."
#   "... and the provisions supplied here do not classify it as such."
#   "The classification provisions themselves were not among the
#    references supplied to me, so ..."
#
# FALSE-POSITIVE GUARD: the Regulation's own prose says things like "the
# information provided under Article 13" and "instructions for use provided
# by the provider", which are legitimate legal content. So every pattern
# below anchors on the META noun (references / provisions / material) AND a
# self-referential qualifier (supplied / provided / here / to me), never on
# a bare "provided".
_RETRIEVAL_META_CLAUSE_RES: tuple[re.Pattern[str], ...] = (
    # trailing prepositional qualifier: "... on the provisions supplied here"
    re.compile(
        r"\s*,?\s*(?:based\s+)?on\s+(?:the\s+)?(?:provisions?|references?|material|text)"
        r"\s+(?:supplied|provided)(?:\s+(?:here|above|to\s+me|to\s+us))?",
        re.I,
    ),
    # conjoined clause: ", and the references supplied do not settle ..."
    re.compile(
        r"\s*[,;]\s*(?:and\s+|but\s+|so\s+)?(?:the\s+)?(?:references?|provisions?)"
        r"\s+(?:supplied|provided)(?:\s+(?:here|above|to\s+me|to\s+us))?[^.;]*",
        re.I,
    ),
    # "... were not among the references supplied to me"
    re.compile(
        r"\s*[,;]?\s*(?:were|was)\s+not\s+among\s+the\s+(?:references?|provisions?)"
        r"[^.;]*",
        re.I,
    ),
    # trailing "so that question cannot be answered on this material"
    re.compile(r"\s*[,;]?\s*so\s+that\s+question\s+cannot\s+be\s+answered[^.;]*", re.I),
)

_RETRIEVAL_META_SENTENCE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:the\s+)?references?\s+(?:supplied|provided|listed|given)\b", re.I),
    re.compile(r"\bprovisions?\s+supplied\b", re.I),
    # R311 — the reversed word order. R310 matched only noun->participle
    # ("provisions supplied"); the live july7-023 answer ships the
    # participle->noun form: "The SUPPLIED PROVISIONS attach no systemic-risk
    # category to AI systems...". Same shape, same intent, one missed ordering.
    re.compile(r"\b(?:supplied|provided)\s+(?:provisions?|references?)\b", re.I),
    re.compile(r"\bnot\s+among\s+the\s+(?:references?|provisions?)\b", re.I),
    re.compile(r"\bno\s+verbatim\s+text\b", re.I),
    re.compile(r"\breferences?\s+block\b", re.I),
    re.compile(r"\bon\s+this\s+material\b", re.I),
)

# A sentence whose substance falls below this after its meta clause is
# excised is treated as wholly-meta and dropped. Deliberately LOW: the live
# verdict "Not as a standing entitlement on the provisions supplied here."
# reduces to "Not as a standing entitlement." (30 chars) and MUST survive --
# it is the answer.
_MIN_CLEANED_SENTENCE = 15


def strip_retrieval_meta(text: str) -> str:
    """R310 — remove commentary about the answer's own supplied references.

    Excises the meta CLAUSE first so an entangled verdict survives, and only
    drops a whole sentence when nothing substantive is left. Sentence 0 is
    never dropped (the DIRECT-VERDICT rule puts the answer there). Keeps
    >= 1 sentence and >= 80 chars of substance or returns the input
    unchanged. Pure, idempotent, fail-soft.
    Env-reversible ``REGENOLD_STRIP_RETRIEVAL_META=0``.
    """
    import os  # noqa: PLC0415 — local to keep the module import surface lean

    if os.getenv("REGENOLD_STRIP_RETRIEVAL_META", "1").strip().lower() in (
        "0", "false", "no", "off",
    ):
        return text
    if not text or not text.strip():
        return text
    try:
        if not any(p.search(text) for p in _RETRIEVAL_META_SENTENCE_RES):
            return text
        sentences = _SENTENCE_BOUNDARY_RE.split(text.strip())
        if len(sentences) < 2:
            return text
        kept: list[str] = []
        for idx, sent in enumerate(sentences):
            s = sent.strip()
            if not s:
                continue
            if not any(p.search(s) for p in _RETRIEVAL_META_SENTENCE_RES):
                kept.append(s)
                continue
            cleaned = s
            for pat in _RETRIEVAL_META_CLAUSE_RES:
                cleaned = pat.sub("", cleaned)
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
            cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
            # Still meta after clause excision, or nothing substantive left.
            still_meta = any(p.search(cleaned) for p in _RETRIEVAL_META_SENTENCE_RES)
            if still_meta or len(cleaned.rstrip(" .,;:")) < _MIN_CLEANED_SENTENCE:
                if idx == 0:
                    # Never drop the verdict sentence — keep the original.
                    kept.append(s)
                continue
            if cleaned and cleaned[-1] not in ".!?":
                cleaned += "."
            kept.append(cleaned)
        remainder = " ".join(kept).strip()
        if not remainder or len(remainder) < _MIN_META_REMAINDER:
            return text
        out = _capitalise_first_letter(remainder)
        return out if out and out.strip() else text
    except Exception:  # noqa: BLE001 — a normaliser must never break the wire
        return text


def strip_meta_commentary(text: str) -> str:
    """R264 — drop sentences that leak internal retrieval/framing commentary.

    Removes a whole sentence when it contains an internal-only marker
    (``"current retrieval"``, ``"references supplied above"``, ``"flag a framing
    problem"``, …) that never belongs in a user-facing legal answer. The answer
    still answers the question from its other sentences. Conservative + fail-
    soft: keeps ≥ 1 non-marker sentence and ≥ 80 chars of substance, else returns
    the input unchanged; idempotent. Env-reversible ``REGENOLD_STRIP_META=0``.
    """
    import os  # noqa: PLC0415 — local to keep the module import surface lean

    if os.getenv("REGENOLD_STRIP_META", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return text
    if not text or not text.strip():
        return text
    try:
        low_all = text.lower()
        if not any(m in low_all for m in _META_COMMENTARY_MARKERS):
            return text
        sentences = _SENTENCE_BOUNDARY_RE.split(text.strip())
        if len(sentences) < 2:
            return text
        kept = [
            s
            for s in sentences
            if not any(m in s.lower() for m in _META_COMMENTARY_MARKERS)
        ]
        if len(kept) == len(sentences):
            return text
        remainder = " ".join(s.strip() for s in kept if s.strip()).strip()
        if not remainder or len(remainder) < _MIN_META_REMAINDER:
            return text
        out = _capitalise_first_letter(remainder)
        return out if out and out.strip() else text
    except Exception:
        return text


# R268 — mid-sentence citation-anchor elision repair. On high-risk
# medical-device and prohibited-practice classification answers, Sonnet-5 /
# Opus-4.8 occasionally drop the Annex/Article anchor between the preposition
# and the following connector, producing broken grammar the r267 live judge
# flagged:
#   q008: "...Union harmonisation legislation listed in which includes the MDR"
#         (dropped "Annex I")
#   q096: "...Union harmonisation legislation listed in here the MDR"
#   q102: "...Union harmonisation legislation listed in such as a medical device"
#   q007: "...practices banned under which reaches manipulative techniques..."
#         (dropped "Article 5")
# These deterministic repairs re-insert the correct anchor. NARROWLY anchored
# on the surrounding Union-harmonisation-legislation / prohibited-practice
# context so they never fire on ordinary "in which" / "under which" prose.
# davidath byte-identical: the deterministic bench answers write "listed in
# Annex I" correctly, so the connector never sits immediately after the
# preposition and the regexes never match. Env-reversible
# ``REGENOLD_REPAIR_ELISION=0``.

# "...harmonisation legislation listed in here <X>"  ->  drop "here", insert
# "Annex I," (the "here" is the model's placeholder for the elided anchor).
_ELIDED_ANNEX_I_HERE_RE = re.compile(
    r"(harmonisation\s+legislation\s+listed\s+in)\s+here\b",
    re.IGNORECASE,
)
# "...harmonisation legislation listed in which/such as <X>"  ->  insert
# "Annex I," before the connector (which reads as a relative/appositive).
_ELIDED_ANNEX_I_CONN_RE = re.compile(
    r"(harmonisation\s+legislation\s+listed\s+in)\s+(which|such\s+as)\b",
    re.IGNORECASE,
)
# "...practices banned under which <X>"  ->  insert "Article 5," before "which".
_ELIDED_ARTICLE_5_RE = re.compile(
    r"(practices?\s+banned\s+under)\s+which\b",
    re.IGNORECASE,
)


def repair_elided_citation_anchors(text: str) -> str:
    """R268 — re-insert an Annex/Article anchor the model elided mid-sentence.

    Repairs the "listed in which/here/such as" (dropped ``Annex I``) and
    "banned under which" (dropped ``Article 5``) shapes on high-risk
    medical-device / prohibited-practice answers. Pure, idempotent (once
    ``Annex I`` / ``Article 5`` is present the connector no longer sits
    immediately after the preposition), fail-soft. Env-reversible.
    """
    import os  # noqa: PLC0415 — local to keep the module import surface lean

    if os.getenv("REGENOLD_REPAIR_ELISION", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return text
    if not text or not isinstance(text, str) or not text.strip():
        return text
    try:
        out = _ELIDED_ANNEX_I_HERE_RE.sub(r"\1 Annex I,", text)
        out = _ELIDED_ANNEX_I_CONN_RE.sub(r"\1 Annex I, \2", out)
        out = _ELIDED_ARTICLE_5_RE.sub(r"\1 Article 5, which", out)
        out = re.sub(r"[ \t]{2,}", " ", out)
        return out if out and out.strip() else text
    except Exception:
        return text

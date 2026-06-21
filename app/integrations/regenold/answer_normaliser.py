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
]


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

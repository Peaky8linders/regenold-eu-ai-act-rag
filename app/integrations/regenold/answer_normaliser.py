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

__all__ = ["strip_preamble_templates", "strip_dash_separators"]


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

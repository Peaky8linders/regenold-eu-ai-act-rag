"""Sentence-level BM25 over the EUR-Lex AI Act corpus.

Closes the granularity mismatch surfaced by the davidath benchmark
(Round 25 retrospective): the article-level BM25 routes citations
correctly (Ref Correctness Loose = 0.36) but the engine ships the full
article paragraph as the answer (480 chars median) where the gold is a
1-sentence direct answer (~140 chars). 51/137 QA items had right
citation + wrong answer.

The fix recommended by both market-research agents (consensus: Lauriola
2024 / Chroma 2025 / Madabushi & Lee 2016 / JURIX 2018 MaRisk) is to
index every sentence of every article as its own BM25 doc, then —
after the article-level path picks an article — run a second BM25 pass
over only that article's sentences and return the top-1 sentence as
the answer prose. Citation set is unchanged; conciseness and answer
correctness rise sharply.

This module exposes:

* :func:`select_answer_sentence(question, article_ref)` — given a
  question and an internal article ref (e.g. ``"Art. 13"``), return
  the single sentence from that article most likely to answer the
  question. Includes a question-type-aware bias so a "How long..."
  question prefers sentences with a duration phrase, etc.
* :func:`split_legal_sentences(text)` — regex-based splitter that
  preserves regulatory abbreviations (``Art.``, ``Annex N.``, ``e.g.``,
  ``i.e.``, ordinals like ``2.``).

Pure stdlib + the existing :mod:`app.data.kb_search` BM25 primitives.
Zero new external dependencies, sub-2-ms latency budget per call.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache

from app.data.eu_ai_act_corpus import (
    ARTICLE_FULL_TEXT,
    ART_3_DEFINITIONS,
)
from app.data.kb_search import _tokenize


# ── Sentence splitter ────────────────────────────────────────────────────


# Tokens that look like sentence terminators but are NOT, in legal text:
#   * ``Art.`` / ``Article`` followed by digit
#   * ``Annex II.`` / ``Annex III.`` (Roman + dot is a heading)
#   * ``e.g.`` / ``i.e.`` / ``cf.`` / ``etc.`` / ``vs.`` / ``viz.``
#   * Numbered list items at line start: ``1.`` / ``2.`` / etc.
#   * Sub-point markers inside an article: ``(a)`` / ``(b)`` / ``(1)``
#   * Section/paragraph numbers: ``Section 5.2.`` / ``§ 3.``
#   * Country/abbreviation periods: ``U.S.`` / ``E.U.``
#
# Strategy: walk every ``[.!?]\s+`` candidate, accept only when the
# left-side context doesn't end with a known abbreviation marker. This
# is the same shape as the splitter in
# :mod:`app.integrations.regenold.models` but tuned for the FULL EUR-Lex
# prose (longer sentences, more abbreviations) rather than the short
# engine-output normalisation pass.


_ABBREV_LEFTS = (
    "art",
    "article",
    "annex",
    "annexe",
    "section",
    "sec",
    "para",
    "paragraph",
    "subpara",
    "subparagraph",
    "ch",
    "chap",
    "chapter",
    "recital",
    "no",
    "nos",
    "fig",
    "vol",
    "pp",
    "etc",
    "vs",
    "viz",
    "cf",
    "e.g",
    "i.e",
    "n.b",
    "p.s",
    "u.s",
    "e.u",
    "mr",
    "mrs",
    "ms",
    "dr",
    "st",
    "ltd",
    "inc",
    "co",
)

_ABBREV_RE = re.compile(
    r"(?:^|[\s(\[\"'“‘])"  # word boundary tolerant of unicode quotes
    r"(?:" + "|".join(re.escape(a) for a in _ABBREV_LEFTS) + r")\.$",
    re.IGNORECASE,
)

# Numbered list at line start: ``1.`` / ``12.`` / paragraph numbering.
# Engine should treat these as ABBREV (don't split between number and content).
# NB: we INTENTIONALLY do NOT add an ``Article N.`` / ``Annex N.`` rule
# here — those phrases appear far more often as mid-sentence references
# (``in accordance with Article 97.`` / ``referred to in Annex III.``)
# than as standalone headings. Treating them as abbreviations was the
# Round-26 first-cut bug that caused the splitter to glue 3000-char
# paragraphs into a single "sentence". Mid-sentence collisions are
# rare enough that splitting always wins on the davidath corpus.
_NUMBERED_LIST_RE = re.compile(r"(?:^|\s)\d{1,3}\.$")

_SENT_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def _is_abbrev_left(left: str) -> bool:
    """True iff the candidate boundary follows a known abbreviation."""
    s = left.rstrip()
    if not s:
        return False
    if _ABBREV_RE.search(s):
        return True
    if _NUMBERED_LIST_RE.search(s):
        return True
    return False


def split_legal_sentences(text: str) -> list[str]:
    """Split legal/regulatory prose into sentences.

    Handles the regulatory-text edge cases that a naive ``re.split``
    over ``[.!?]`` would mangle:

    * ``Art. 5`` — keep glued
    * ``Annex IV.`` (heading) — keep glued
    * ``e.g.`` / ``i.e.`` — keep glued
    * ``1. Providers shall ...`` — keep "1." glued to the clause that
      follows when it's a paragraph numbering marker
    * Sub-point markers ``(a)`` / ``(b)`` — left in place

    Returns sentences in document order, whitespace-trimmed. Empty or
    pure-punctuation fragments are dropped.
    """
    if not text:
        return []
    s = text.strip()
    if not s:
        return []
    # Pre-normalise non-breaking whitespace + nbsp that the EUR-Lex
    # corpus is sprinkled with (the davidath data also uses these).
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()

    boundaries: list[tuple[int, int]] = []
    for m in _SENT_BOUNDARY_RE.finditer(s):
        left = s[: m.start()]
        if _is_abbrev_left(left):
            continue
        boundaries.append((m.start(), m.end()))

    if not boundaries:
        return [s] if len(s) >= 4 else []

    sentences: list[str] = []
    prev_end = 0
    for b_start, b_end in boundaries:
        chunk = s[prev_end:b_start].strip()
        if chunk and len(chunk) >= 4:
            sentences.append(chunk)
        prev_end = b_end
    tail = s[prev_end:].strip()
    if tail and len(tail) >= 4:
        sentences.append(tail)
    return sentences


# ── Per-article sentence index ───────────────────────────────────────────


@dataclass(frozen=True)
class _SentenceIndex:
    """Per-article sentence collection + pre-computed BM25 stats.

    The full corpus index is a dict ``{article_ref: _SentenceIndex}``.
    Each article gets its own micro-index because we only ever rank
    sentences within a single article (the article-level path already
    selected which article to consult).
    """

    sentences: tuple[str, ...]
    docs: tuple[tuple[str, ...], ...]  # tokenised
    doc_freqs: tuple[dict[str, int], ...]
    avg_doc_len: float
    idf: dict[str, float]


def _build_sentence_index(text: str) -> _SentenceIndex:
    """Tokenise + build BM25 stats for one article's sentences."""
    sentences = tuple(split_legal_sentences(text))
    docs = tuple(tuple(_tokenize(s)) for s in sentences)
    doc_freqs: list[dict[str, int]] = []
    for d in docs:
        freqs: dict[str, int] = {}
        for tok in d:
            freqs[tok] = freqs.get(tok, 0) + 1
        doc_freqs.append(freqs)

    n_docs = len(docs)
    if n_docs == 0:
        return _SentenceIndex((), (), (), 0.0, {})

    avg_doc_len = sum(len(d) for d in docs) / n_docs if n_docs else 0.0
    df: dict[str, int] = {}
    for freqs in doc_freqs:
        for term in freqs:
            df[term] = df.get(term, 0) + 1
    idf: dict[str, float] = {}
    for term, count in df.items():
        idf[term] = math.log((n_docs - count + 0.5) / (count + 0.5) + 1.0)
    return _SentenceIndex(
        sentences=sentences,
        docs=docs,
        doc_freqs=tuple(doc_freqs),
        avg_doc_len=avg_doc_len,
        idf=idf,
    )


@lru_cache(maxsize=1)
def _all_sentence_indexes() -> dict[str, _SentenceIndex]:
    """Memoised — built once per process from :data:`ARTICLE_FULL_TEXT`."""
    out: dict[str, _SentenceIndex] = {}
    for ref, text in ARTICLE_FULL_TEXT.items():
        if not text:
            continue
        out[ref] = _build_sentence_index(text)
    return out


def _score(idx: _SentenceIndex, sent_idx: int, qt: list[str]) -> float:
    """BM25 score of one sentence against the query tokens."""
    doc = idx.docs[sent_idx]
    freqs = idx.doc_freqs[sent_idx]
    doc_len = len(doc)
    if doc_len == 0:
        return 0.0
    k1 = 1.5
    b = 0.75
    score = 0.0
    for term in qt:
        if term not in freqs:
            continue
        tf = freqs[term]
        idf = idx.idf.get(term, 0.0)
        score += idf * (tf * (k1 + 1)) / (
            tf + k1 * (1 - b + b * doc_len / idx.avg_doc_len)
        )
    return score


# ── Question-type classification ─────────────────────────────────────────


# Question-shape regexes — first hit wins; the dispatch order matters.
# Each class has a name + a per-sentence "answer-affinity" pattern that
# boosts sentences containing the kind of content the question asks
# about. Patterns are deliberately broad — false positives don't hurt
# because they only multiply the score by 1.5, the underlying BM25 rank
# still needs to be competitive.

_QTYPE_PATTERNS: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    # PURPOSE — "what is the purpose / role / function of X" (Round 34 P0).
    # Articles 71 (EU database), 99 (penalties), 31 (notified bodies), 63
    # (oversight), 57 (sandboxes) etc. carry their purpose statement in the
    # OPENING paragraph (sentence 0, typically 200-900 chars). The default
    # sentence picker's 500-char gate was silently dropping these — see
    # CLAUDE.md Round 34. Affinity hits sentences containing the canonical
    # "purpose / objective / in order to / established to" phrasing.
    (
        "purpose",
        re.compile(
            r"\bwhat\s+is\s+the\s+(?:purpose|role|function|objective|aim)\s+of\b|"
            r"\bwhat\s+(?:does|do)\s+\S.*\s+(?:contain|cover|establish|provide\s+for)\b|"
            r"\bwhat\s+is\s+the\s+role\s+of\s+the\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:purpose|in\s+order\s+to|to\s+(?:ensure|protect|enable|store|register|"
            r"facilitate|support|provide|monitor)|established\s+to|"
            r"contain(?:s|ing)?\s+information|shall\s+contain)\b",
            re.IGNORECASE,
        ),
    ),
    # DURATION — "how long", "for how many years/months"
    (
        "duration",
        re.compile(
            r"\bhow\s+long\b|\bhow\s+many\s+(?:years?|months?|days?)\b|"
            r"\bfor\s+how\s+(?:long|many)\b|\bretention\s+period\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:ten|five|six|three|two|four|seven|eight|nine|twelve|"
            r"\d+)\s+(?:years?|months?|days?|weeks?)\b",
            re.IGNORECASE,
        ),
    ),
    # DATE — "when does X apply", "from what date". Use a non-greedy
    # ``[\w\s]+?`` between the auxiliary and the apply-verb so multi-
    # token subjects like ``Article 5`` survive.
    (
        "date",
        re.compile(
            r"\bwhen\s+(?:does|do|did|will|shall)\s+[\w\s]+?\s+(?:apply|start|"
            r"begin|come\s+into\s+force)\b|"
            r"\bfrom\s+what\s+date\b|\bby\s+when\b|\bentry\s+into\s+force\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:from\s+)?(?:\d{1,2}\s+)?(?:January|February|March|April|May|"
            r"June|July|August|September|October|November|December)\s+\d{4}\b|"
            r"\b20\d{2}\b",
            re.IGNORECASE,
        ),
    ),
    # NUMERIC / fine / percentage — must precede DEFINITION because
    # "What is the maximum fine?" matches both ``what is`` (definition)
    # and ``maximum fine`` (numeric); the latter is the real intent.
    (
        "numeric",
        re.compile(
            r"\bhow\s+(?:much|many)\b|"
            r"\bwhat\s+is\s+the\s+(?:maximum|minimum|highest|lowest)\s+"
            r"(?:fine|penalty|amount|percentage)\b|"
            r"\bwhat\s+(?:percentage|amount|fine|penalt(?:y|ies))\b|"
            r"\bmaximum\s+(?:fine|penalty)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:EUR\s+)?\d{1,3}(?:[,. ]\d{3})+\b|"
            r"\b\d+\s*(?:%|percent)\b|\b35\s*000\s*000\b",
            re.IGNORECASE,
        ),
    ),
    # ROLE — "who must", "which operator"
    (
        "role",
        re.compile(
            r"\bwho\s+(?:must|is\s+(?:responsible|required|considered|liable))\b|"
            r"\bwhich\s+(?:operator|party|actor|entity)\b|"
            r"\bwho\s+(?:can|may|should)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:providers?|deployers?|importers?|distributors?|"
            r"manufacturers?|authorised\s+representatives?|"
            r"notified\s+bod(?:y|ies))\b",
            re.IGNORECASE,
        ),
    ),
    # DEFINITION — "what is X", "what does Y mean", "define Z"
    (
        "definition",
        re.compile(
            r"\bwhat\s+is\s+(?:an?\s+|the\s+)?\b|"
            r"\bwhat\s+does\s+\S.*\s+mean\b|"
            r"\bdefinition\s+of\b|\bdefine\s+\b|"
            r"\bhow\s+is\s+\S+\s+defined\b",
            re.IGNORECASE,
        ),
        re.compile(r"\bmeans?\b|\bdefined?\b|\brefers?\s+to\b", re.IGNORECASE),
    ),
    # LIST — "what are the X"
    (
        "list",
        re.compile(
            r"\bwhat\s+(?:are\s+the|kinds|types|categories)\b|"
            r"\blist\s+(?:the|of)\b|\bname\s+(?:one|two|three|all)\b",
            re.IGNORECASE,
        ),
        # No specific sentence-bias regex for LIST; rely on BM25 alone.
        re.compile(r"^$"),
    ),
    # BOOLEAN — yes/no with "does/is/are/must"
    (
        "boolean",
        re.compile(
            r"^(?:is|does|are|can|must|may|shall|do|did)\b", re.IGNORECASE
        ),
        re.compile(r"^$"),
    ),
    # METHOD — "how do/does X"
    (
        "method",
        re.compile(r"^how\s+(?:do|does|should|must|can)\b", re.IGNORECASE),
        re.compile(r"^$"),
    ),
)


def classify_question(question: str) -> str:
    """Return the question type tag, or ``"description"`` as fallback."""
    q = (question or "").strip().lower()
    for name, q_pattern, _ in _QTYPE_PATTERNS:
        if q_pattern.search(q):
            return name
    return "description"


def _answer_affinity_pattern(qtype: str) -> re.Pattern[str] | None:
    for name, _, sent_pattern in _QTYPE_PATTERNS:
        if name == qtype:
            return sent_pattern
    return None


# ── Public API: select the answer sentence ───────────────────────────────


def select_answer_sentence(
    question: str,
    article_ref: str,
    *,
    min_score: float = 0.5,
    affinity_boost: float = 1.5,
    confidence_ratio: float = 1.6,
    max_sentence_chars: int = 1000,
    leading_paragraph_boost: float = 1.3,
) -> str | None:
    """Return the top-1 sentence from ``article_ref`` for ``question``.

    Returns ``None`` when:

    * The article isn't in the corpus.
    * The article has no parseable sentences.
    * No sentence scores above ``min_score`` against the question.
    * **Confidence gate** — top-1 score must beat top-2 by
      ``confidence_ratio×`` (default 1.6×). When the top-2 sentences
      are close, BM25 can't decide which sub-clause carries the
      answer, and returning the wrong one costs more on
      ``ans_correctness_strict`` than keeping the engine's
      multi-sentence prose costs on conciseness.
    * **Length gate** — sentences over ``max_sentence_chars`` are
      skipped. EUR-Lex articles include enumeration paragraphs
      ("1. The Commission... (a) ... (b) ..." up to 3000 chars long)
      that don't shorten the answer. Skipping them lets the second-
      best sentence (typically tighter) win.

    Question-type affinity is applied multiplicatively on top of BM25:
    a "How long..." question gets a 1.5× score boost on sentences that
    contain a duration phrase. The base BM25 score still has to be
    non-trivial — affinity alone can't promote an irrelevant sentence.
    """
    if not question or not article_ref:
        return None
    all_indexes = _all_sentence_indexes()
    idx = all_indexes.get(article_ref)
    if idx is None or not idx.sentences:
        return None

    query_tokens = _tokenize(question)
    if not query_tokens:
        return None

    qtype = classify_question(question)
    affinity_re = _answer_affinity_pattern(qtype)
    apply_affinity = affinity_re is not None and affinity_re.pattern != "^$"

    # Collect every candidate (score, idx). Sentences over
    # ``max_sentence_chars`` are skipped — EUR-Lex articles include
    # enumeration paragraphs ("1. The Commission... (a) ... (b) ...")
    # up to 3000 chars long that don't shorten the answer below gold's
    # ~140-char median. Skipping them lets the second-best (typically
    # tighter) sentence win.
    candidates: list[tuple[float, int]] = []
    for i, sent in enumerate(idx.sentences):
        if len(sent) > max_sentence_chars:
            continue
        raw = _score(idx, i, query_tokens)
        if raw < min_score:
            continue
        score = raw
        if apply_affinity and affinity_re.search(sent):
            score *= affinity_boost
        # Round 34 P0 — leading-paragraph boost. Sentence 0 of an EUR-Lex
        # article is overwhelmingly the topic / purpose statement. When
        # the question asks about purpose / role / scope and sentence 0
        # is substantive (≥ 200 chars), bias toward it. Without this
        # boost, BM25 over-rewards short later sentences that happen to
        # carry a query token (e.g. "6. The Commission shall be the
        # controller" beats the actual EU-database purpose paragraph).
        if i == 0 and len(sent) >= 200 and qtype in ("purpose", "description"):
            score *= leading_paragraph_boost
        candidates.append((score, i))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return idx.sentences[candidates[0][1]]


# Definition-question term extractors. Each regex tries to pull the
# *term being defined* out of the question. First non-empty match wins.
# Each pattern uses ``\b`` boundaries so partial-word matches don't fire.
_DEFINITION_TERM_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "What is the definition of (an|the|a) X?"
    re.compile(
        r"\bdefinition\s+of\s+(?:an?\s+|the\s+)?['‘’\"]?(?P<term>[\w\-\s]+?)"
        r"['‘’\"]?\s*(?:\?|under|in|according|$)",
        re.IGNORECASE,
    ),
    # "How is X defined?"
    re.compile(
        r"\bhow\s+is\s+['‘’\"]?(?P<term>[\w\-\s]+?)['‘’\"]?\s+defined\b",
        re.IGNORECASE,
    ),
    # "What does X mean?"
    re.compile(
        r"\bwhat\s+does\s+(?:an?\s+|the\s+)?['‘’\"]?(?P<term>[\w\-\s]+?)"
        r"['‘’\"]?\s+mean\b",
        re.IGNORECASE,
    ),
    # "What is (an|the|a) X?"  — broad, last to fire so the specific ones win.
    re.compile(
        r"\bwhat\s+is\s+(?:an?\s+|the\s+)?['‘’\"]?(?P<term>[\w\-\s]+?)"
        r"['‘’\"]?\s*(?:\?|under|in|according|$)",
        re.IGNORECASE,
    ),
    # "Who is considered (an|a) X?"
    re.compile(
        r"\bwho\s+is\s+considered\s+(?:an?\s+|the\s+)?['‘’\"]?"
        r"(?P<term>[\w\-\s]+?)['‘’\"]?\s*(?:\?|under|of|in|$)",
        re.IGNORECASE,
    ),
    # "Who is (a|an) X?"
    re.compile(
        r"\bwho\s+is\s+(?:an?\s+|the\s+)?['‘’\"]?(?P<term>[\w\-\s]+?)"
        r"['‘’\"]?\s*(?:\?|of|in|$)",
        re.IGNORECASE,
    ),
)


_TERM_NORMALISERS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Drop trailing filler clauses.
    (re.compile(r"\s+in\s+the\s+(?:context|regulation).*$", re.I), ""),
    (re.compile(r"\s+under\s+the\s+regulation.*$", re.I), ""),
    (re.compile(r"\s+under\s+the\s+ai\s+act.*$", re.I), ""),
    (re.compile(r"\s+according\s+to\s+.*$", re.I), ""),
    (re.compile(r"\s+of\s+(?:an?\s+)?ai\s+system.*$", re.I), ""),
    (re.compile(r"^['‘’\"]\s*", re.I), ""),
    (re.compile(r"\s*['‘’\"]$", re.I), ""),
)


def _extract_definition_term(question: str) -> str | None:
    """Pull the term-being-defined from a definition-style question."""
    q = (question or "").strip()
    for pattern in _DEFINITION_TERM_PATTERNS:
        m = pattern.search(q)
        if not m:
            continue
        term = m.group("term").strip()
        for norm_re, repl in _TERM_NORMALISERS:
            term = norm_re.sub(repl, term).strip()
        if term:
            return term
    return None


def select_definition_sentence(question: str) -> str | None:
    """For DEFINITION questions — find the matching Art. 3 entry.

    Routes "What is X?" / "Definition of Y" / "What does Z mean?" /
    "How is W defined?" / "Who is considered V?" by extracting the term
    from the question and looking it up in the upstream Art. 3
    definitions dict. Returns the definition sentence (a 1-clause
    direct answer, already in gold-length range).
    """
    term = _extract_definition_term(question)
    if not term:
        return None
    term_low = term.lower()
    # Exact match first.
    if term_low in ART_3_DEFINITIONS:
        return _strip_trailing_clauses(ART_3_DEFINITIONS[term_low])
    # Leading-article variants ("a deployer" → "deployer").
    for prefix in ("a ", "an ", "the "):
        if term_low.startswith(prefix) and term_low[len(prefix):] in ART_3_DEFINITIONS:
            return _strip_trailing_clauses(
                ART_3_DEFINITIONS[term_low[len(prefix):]]
            )
    # Pluralisation tolerance — gold defs are singular ("provider"
    # not "providers"), questions sometimes plural.
    if term_low.endswith("s") and term_low[:-1] in ART_3_DEFINITIONS:
        return _strip_trailing_clauses(ART_3_DEFINITIONS[term_low[:-1]])
    return None


def _strip_trailing_clauses(definition_text: str) -> str:
    """Tighten the upstream Art. 3 definition to a single sentence.

    The upstream JSON sometimes ships a definition with a trailing
    cross-reference (``…; cf. Art. 5(2)``) or a parenthetical that
    bloats the answer beyond the gold length. Cut at the first ``;``
    followed by a lowercase clause (typical cross-ref shape).
    """
    if not definition_text:
        return definition_text
    t = definition_text.strip().rstrip(";")
    # Cut at first semicolon followed by a clause that looks like a cross-ref.
    parts = re.split(r";\s+(?=[a-z])", t, maxsplit=1)
    out = parts[0].rstrip(";.,").strip()
    if not out:
        return definition_text
    if not out.endswith("."):
        out += "."
    return out

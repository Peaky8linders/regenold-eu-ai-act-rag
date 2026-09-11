"""R409 — answer-completeness guards on the FINAL Stage-2 answer.

Why this exists (measured, see
``docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json``): a triage
of the 67 failing correctness criteria on the R407 hard-mode run found 55
engine-side gaps, and in 53 of them the provision the criterion needed was
ALREADY cited. The answer had the law in hand and left part of it out:

* 22 OMITTED_ENUMERATED_ITEM — the answer lists some limbs of a closed statutory
  list, not all the question asks for (rg_046 lists only the Article 13(3)(b)
  sub-points and omits points (a) and (c) to (f));
* 9 MISSING_CONDITION_OR_EXCEPTION — rg_015 omits Article 50(1) "unless this is
  obvious ..."; rg_003 omits Article 6(3) "including by not materially
  influencing the outcome of decision making";
* 6 VERDICT_POLARITY_OR_FRAMING — a yes/no question answered with a
  conditional lead such as "High-risk only where ...";
* 7 PUSHBACK_DRIFT — after the evaluator's pushback the new answer drops points
  the previous answer stated;
* 10 WRONG_OR_MISSING_PROVISION — "which article governs human oversight"
  answered from 14(5) instead of stating what each paragraph requires.

This module is PURE and DETERMINISTIC: no network, no LLM call, no new
dependency. It DETECTS gaps in a final answer and BUILDS prompt text. The
integrator performs the single bounded repair call inside
``app/engines/_graph_rag_impl.py`` and keys the five flags in
``_engine_cache_key``.

Flags — all default OFF, fresh env read per call, allow-list truthiness
(``1``/``true``/``yes``/``on``; anything else, including blank, is OFF):

* ``REGENOLD_CLOSED_SET_COMPLETENESS_GUARD`` -> :func:`closed_set_completeness_enabled`
* ``REGENOLD_EXCEPTION_LIMB_GUARD``          -> :func:`exception_limb_guard_enabled`
* ``REGENOLD_VERDICT_LEAD_GUARD``            -> :func:`verdict_lead_guard_enabled`
* ``REGENOLD_PUSHBACK_KEEP_CONTRACT``        -> :func:`pushback_keep_enabled`
* ``REGENOLD_GOVERNING_PROVISION_CLAUSE``    -> :func:`governing_provision_clause_enabled`

The env names are module-level ``*_ENV`` string constants so the AST gate in
``tests/test_r355_cache_key_complete.py`` finds them. Because the read sites are
module constants (enclosing function ``None``), the gate can only be satisfied
by adding the five literals to the ``engine_flags`` tuple of
``_engine_cache_key``; helper-call coverage cannot see them. Until the
integrator does that, ``test_every_engine_env_flag_is_accounted_for`` reports
these five flags — that is the gate working, not a defect here.

⚠ Integration facts, verified by execution on the R407 rows:

1. **The pushback detectors need the FLATTENED history.** With the R305 re-ask
   focus ON (``REGENOLD_REASK_FOCUS`` default), ``_build_question_from_history``
   hands the engine the BARE re-asked question on the benchmark's pushback turn
   (rg_015: 149 chars, no ``Latest question:`` marker, ``is_challenge_turn`` is
   False). :func:`dropped_pushback_points` and :func:`pushback_keep_clause` are
   no-ops on that string. Feed them the concatenation-path format
   (``Conversation so far:\\nUser: ...\\nAssistant: ...\\n\\nLatest question:\\n<turn>``),
   e.g. rebuilt from ``req.messages``.
2. **Prompt-side, so NOT reference-neutral** (AGENTS.md invariant #5). A repair
   changes the Stage-2 prose, and the three prose->refs passes recompute the wire
   references from it. Every flag here needs ``easyhard_ab``/``gold_dropped_head``
   AND the pairwise judge before it is flipped ON.

Deviations from the written spec, each for a measured reason:

* Paragraph groups directly under a HEAD (``Article 13.1``..``13.3``,
  ``Annex III.1``..``8``) are never demanded. A head's paragraphs are separate
  provisions, not an enumerated list, and demanding them would make every
  citation of ``Article N(k)`` in a list-shaped answer demand paragraphs 1..n.
* Exception clauses with fewer than 3 content tokens are ignored ("where
  applicable, of its authorised representative" is not an exception limb).
* :func:`accept_repair` allows a new head named in a gap's VERBATIM TEXT (Article
  13(3)(d) cites Article 14, 13(3)(f) cites Article 12, so a faithful rg_046
  repair names both), and its meta-commentary check ignores the statutory term
  "instructions for use" and any "instruction" wording already present in the
  original or in the quoted Act text (the literal substring test would reject
  every repair of the flagship rg_046 row, which is about instructions for use).
* :func:`pushback_keep_clause` is suppressed when the disputing turn itself names
  a provision the previous answer did not, because the clause tells the model
  the user cited no new law.
* A repair is bounded by :func:`repair_char_budget`, NOT a blanket ratio: the
  acceptance limit grows one short clause per MISSING ITEM (R410 conciseness
  fix), not a multiple of the whole answer.
* :func:`verdict_lead_gap` reads the FIRST interrogative of a multi-clause
  question (R410) and accepts a worded verdict lead, not only a literal
  ``Yes``/``No`` token. Both are precision fixes measured on the 110-row R407
  ledger: the guard fired on 11 rows and only 1 was a real missing lead, the
  other 10 being correct answers that decided the question without the exact
  token ("Not prohibited and not high-risk.") or a trailing clause the guard had
  mistaken for the ask. It now fires on 2 rows with no false positive on a
  passing row. A conditional lead ("High-risk only where ...") is still a gap.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Iterable

__all__ = [
    "Gap",
    "accept_repair",
    "build_repair_user_message",
    "closed_set_completeness_enabled",
    "collect_gaps",
    "dropped_pushback_points",
    "exception_limb_guard_enabled",
    "governing_provision_clause",
    "governing_provision_clause_enabled",
    "is_exception_question",
    "is_governing_provision_question",
    "is_list_question",
    "is_yes_no_question",
    "live_question",
    "missing_closed_set_members",
    "missing_exception_limbs",
    "named_heads",
    "previous_answer",
    "pushback_keep_clause",
    "pushback_keep_enabled",
    "repair_char_budget",
    "verdict_lead_gap",
    "verdict_lead_guard_enabled",
]

# ── Flags ────────────────────────────────────────────────────────────────────

_CLOSED_SET_ENV = "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD"
_EXCEPTION_LIMB_ENV = "REGENOLD_EXCEPTION_LIMB_GUARD"
_VERDICT_LEAD_ENV = "REGENOLD_VERDICT_LEAD_GUARD"
_PUSHBACK_KEEP_ENV = "REGENOLD_PUSHBACK_KEEP_CONTRACT"
_GOVERNING_CLAUSE_ENV = "REGENOLD_GOVERNING_PROVISION_CLAUSE"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _flag_is_on(name: str) -> bool:
    try:
        return (os.environ.get(name) or "").strip().lower() in _TRUTHY
    except Exception:  # noqa: BLE001 — a flag read must never break the route
        return False


def closed_set_completeness_enabled() -> bool:
    """R409 — demand every member of an engaged closed statutory list. Default OFF."""
    return _flag_is_on(_CLOSED_SET_ENV)


def exception_limb_guard_enabled() -> bool:
    """R409 — demand the exception/condition limbs of cited paragraphs. Default OFF."""
    return _flag_is_on(_EXCEPTION_LIMB_ENV)


def verdict_lead_guard_enabled() -> bool:
    """R409 — a yes/no question must be answered with a Yes/No lead. Default OFF."""
    return _flag_is_on(_VERDICT_LEAD_ENV)


def pushback_keep_enabled() -> bool:
    """R409 — keep the previous answer's anchored points across a pushback. Default OFF."""
    return _flag_is_on(_PUSHBACK_KEEP_ENV)


def governing_provision_clause_enabled() -> bool:
    """R409 — paragraph-by-paragraph clause for "which article governs X". Default OFF."""
    return _flag_is_on(_GOVERNING_CLAUSE_ENV)


# ── Limits and thresholds ────────────────────────────────────────────────────

_MAX_MEMBER_GAPS = 10
_MAX_EXCEPTION_GAPS = 4
_MAX_KEEP_GAPS = 4
_MAX_TOTAL_GAPS = 12
_MAX_EXCEPTION_HEADS = 4
_MAX_KEEP_CLAUSE_POINTS = 6
_GAP_TEXT_CHARS = 240
_MIN_GROUP_CHILDREN = 3

# Repair length budget (R410). See :func:`repair_char_budget`.
_REPAIR_SLACK_CHARS = 120
_REPAIR_PER_GAP_CHARS = 90
_REPAIR_MAX_GROWTH_RATIO = 1.6
_MEMBER_TOKEN_WINDOW = 8
_MEMBER_COVER_RATIO = 0.55
_EXCEPTION_COVER_RATIO = 0.50
_EXCEPTION_MIN_TOKENS = 3
_KEEP_COVER_RATIO = 0.40
_MAX_ARTICLE = 113
_ANNEX_ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII")
_ROMAN_TO_INT = {r: i + 1 for i, r in enumerate(_ANNEX_ROMANS)}
_ROMAN_SUB = (
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
)


@dataclass(frozen=True)
class Gap:
    """One thing the final answer leaves out.

    ``kind``: ``"member"`` | ``"exception"`` | ``"verdict"`` | ``"keep"``.
    ``coordinate``: strict wire shape (``"Article 13.3.a"``, ``"Article 50.1"``);
    ``""`` for a verdict gap. ``text``: verbatim Act text (<= 240 chars) for
    member/exception gaps, the dropped previous-answer sentence for keep gaps,
    the yes/no question sentence for a verdict gap.
    """

    kind: str
    coordinate: str
    text: str


def repair_char_budget(original: str, gaps: Iterable[Gap]) -> int:
    """Longest a fidelity-preserving repair may be, scaled to the gaps it closes.

    R410. The R409 acceptance bound was a blanket
    ``max(1.8 * len(original), len(original) + 900)``, and the R410 audit measured
    the levers running at it: Part I answers grew 424.5 -> 757.4 chars and the
    graded Answer Conciseness axis (``min(1, |reference| / |candidate|)``) fell
    92.45 -> 69.88 (-22.57 pp), because 757.4 / 424.5 = 1.78.

    A faithful repair adds at most one short clause per missing item, so the
    allowance is ADDITIVE IN THE GAP COUNT, not a multiplier on unrelated prose:
    ``_REPAIR_SLACK_CHARS`` of connective room plus ``_REPAIR_PER_GAP_CHARS`` per
    gap, and never more than ``_REPAIR_MAX_GROWTH_RATIO`` of the original. When a
    complete answer cannot fit, the concise original ships instead: a deliberate
    bias toward the graded conciseness axis over a marginal completeness gain.
    """
    try:
        base = len(_s(original).strip())
        n = sum(1 for g in (gaps or ()) if getattr(g, "kind", "") in _DETECTORS)
        additive = _REPAIR_SLACK_CHARS + _REPAIR_PER_GAP_CHARS * max(1, n)
        if base <= 0:
            return additive
        return min(int(_REPAIR_MAX_GROWTH_RATIO * base), base + additive)
    except Exception:  # noqa: BLE001 — a budget probe must never break acceptance
        return _REPAIR_SLACK_CHARS


# ── Small text utilities ─────────────────────────────────────────────────────

_LIVE_MARKER = "Latest question:\n"
_HISTORY_MARKER = "Conversation so far:\n"


def _s(value: object) -> str:
    return "" if value is None else str(value)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _clip(text: str, limit: int = _GAP_TEXT_CHARS) -> str:
    """Whitespace-flattened text cut at a word boundary. Never adds an ellipsis."""
    flat = " ".join(_s(text).split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:")


_ABBREVIATIONS = frozenset(
    {"art", "arts", "e.g", "i.e", "cf", "no", "nos", "para", "paras", "pt", "pts",
     "vs", "viz", "approx", "incl", "resp", "ca"}
)
_BOUNDARY_RE = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s|$)|\n+")
_TRAILING_WORD_RE = re.compile(r"([A-Za-z]+(?:\.[A-Za-z]+)*)$")


def _sentences(text: str) -> list[str]:
    """Split prose into sentences without cutting "Art. 5", "e.g." or "5.1"."""
    src = _s(text)
    out: list[str] = []
    start = 0
    for m in _BOUNDARY_RE.finditer(src):
        token = m.group(0)
        if token.startswith("\n"):
            piece = src[start:m.start()].strip()
            if piece:
                out.append(piece)
            start = m.end()
            continue
        if token[0] == ".":
            before = src[start:m.start()]
            wm = _TRAILING_WORD_RE.search(before)
            word = wm.group(1).lower() if wm else ""
            nxt = src[m.end():].lstrip()[:1]
            if word in _ABBREVIATIONS or (nxt and (nxt.islower() or nxt.isdigit())):
                continue
        piece = src[start:m.end()].strip()
        if piece:
            out.append(piece)
        start = m.end()
    rest = src[start:].strip()
    if rest:
        out.append(rest)
    return out


_WORD_RE = re.compile(r"[a-z0-9]+")
# -ize -> -ise (R399: the corpus is British, questions/answers are often American).
# A 4-letter prefix is required so "size"/"prize"/"seize"/"citizen" are untouched.
_IZE_RE = re.compile(r"(?<=[a-z]{4})iz(?=e|ing|ation|ed)")

_STOPWORDS = frozenset(
    """
    about above after again against also among another apply applies applied been
    before being below between both could does doing down during each either else
    even every from further have having here hereby herein into itself just more
    most much must neither other others over same shall should since some such
    than that their theirs them themselves then there thereof these they this those
    through thus under unless until upon very what when where whereas whether which
    while whom whose will with within would your yours
    article articles annex annexes paragraph paragraphs point points subparagraph
    subparagraphs regulation union referred pursuant accordance including include
    includes included regard regards relation respect particular applicable
    appropriate relevant concerned case cases system systems intended used using
    """.split()
)
_CLAUSE_STOPWORDS = frozenset(
    {"except", "exception", "exceptions", "derogation", "provided", "notwithstanding"}
)


def _stem(word: str) -> str:
    """Light symmetric stem: -ize fold, plural strip, one common suffix."""
    w = _IZE_RE.sub("is", word)
    if w.endswith("ies") and len(w) > 5:
        w = w[:-3] + "y"
    elif w.endswith("sses") and len(w) > 6:
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 4:
        w = w[:-1]
    for suffix in ("ing", "ment", "ed", "e"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def _content_tokens(text: str, extra_stop: frozenset[str] = frozenset()) -> list[str]:
    """Order-preserving, deduped stems of words with len >= 4, stopwords removed."""
    out: list[str] = []
    seen: set[str] = set()
    for word in _WORD_RE.findall(_s(text).lower()):
        if len(word) < 4 or word.isdigit() or word in _STOPWORDS or word in extra_stop:
            continue
        stem = _stem(word)
        if stem not in seen:
            seen.add(stem)
            out.append(stem)
    return out


def _token_set(text: str) -> set[str]:
    return {_stem(w) for w in _WORD_RE.findall(_s(text).lower())}


def _coverage(tokens: list[str], pool: set[str]) -> float:
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in pool) / len(tokens)


# ── Question slicing ─────────────────────────────────────────────────────────


def live_question(question: str) -> str:
    """Text after the LAST ``Latest question:\\n`` marker, else the whole string."""
    try:
        text = _s(question)
        idx = text.rfind(_LIVE_MARKER)
        if idx >= 0:
            text = text[idx + len(_LIVE_MARKER):]
        return text.strip()
    except Exception:  # noqa: BLE001
        return ""


_REASK_RE = re.compile(
    r"(?:^|\n)[^\S\n]*(?:let(?:'|’)?s|let\s+us)\s+try\s+again[^\S\n]*[:\-–—][^\S\n]*",
    re.IGNORECASE,
)


def _reask_split(question: str) -> tuple[str, str]:
    """(dispute part, asked part) of the live turn.

    The benchmark's pushback re-asks the question after "Let's try again:". The
    detectors judge the ASKED question, so the dispute preamble is split off.
    Without a re-ask marker the whole live turn is the ask and the dispute part
    is the whole live turn too.
    """
    live = live_question(question)
    last = None
    for last in _REASK_RE.finditer(live):
        pass
    if last is not None:
        tail = live[last.end():].strip()
        if tail:
            return live[: last.start()].strip(), tail
    return live, live


def _ask_text(question: str) -> str:
    return _reask_split(question)[1]


_TURN_RE = re.compile(r"(?m)^(User|Assistant):[^\S\n]?")


def previous_answer(question: str) -> str:
    """The last assistant turn inside the flattened history, ``""`` if none."""
    try:
        text = _s(question)
        idx = text.rfind(_LIVE_MARKER)
        if idx < 0:
            return ""
        history = text[:idx]
        header = history.find(_HISTORY_MARKER)
        if header >= 0:
            history = history[header + len(_HISTORY_MARKER):]
        turns = list(_TURN_RE.finditer(history))
        for i in range(len(turns) - 1, -1, -1):
            if turns[i].group(1) == "Assistant":
                end = turns[i + 1].start() if i + 1 < len(turns) else len(history)
                return history[turns[i].end():end].strip()
        return ""
    except Exception:  # noqa: BLE001
        return ""


# ── Question shape detectors ─────────────────────────────────────────────────

_LIST_Q_RE = re.compile(
    r"\b(?:list|lists|listing|enumerate|itemi[sz]e)\b"
    r"|\bname\s+(?:the|all|each|every|them)\b"
    r"|\b(?:what|which)\s+are\s+(?:the|all)\b"
    r"|\b(?:what|which)\s+(?:\w+\s+){0,3}?(?:elements|categories|conditions|criteria|"
    r"requirements|obligations|information|items|steps|tasks|measures|practices|areas|"
    r"types|kinds|duties|exceptions|grounds|factors|components|contents|limbs|safeguards)\b"
    r"|\b(?:must|shall|should)\s+(?:\w+\s+){0,4}?(?:include|contain)\b"
    r"|\ball\s+(?:of\s+)?(?:the\s+)?(?:elements|categories|conditions|criteria|requirements|"
    r"obligations|items|steps|tasks|measures|practices|areas|types)\b",
    re.IGNORECASE,
)


def is_list_question(question: str) -> bool:
    """True when the asked question wants an enumeration."""
    try:
        return bool(_LIST_Q_RE.search(_ask_text(question)))
    except Exception:  # noqa: BLE001
        return False


_EXCEPTION_Q_RE = re.compile(
    r"\b(?:exceptions?|exempt(?:ed|ion|ions)?|derogat\w*|carve[\s\-]?outs?|unless|except|"
    r"excluded|exclusions?)\b"
    r"|\b(?:does|do|shall|would|will)\s+not\s+apply\b|\bdoesn'?t\s+apply\b|\bnot\s+the\s+case\b",
    re.IGNORECASE,
)
_CONDITIONS_Q_RE = re.compile(
    r"\bunder\s+(?:what|which)\s+(?:conditions?|circumstances)\b"
    r"|\bin\s+what\s+(?:cases|circumstances)\b"
    r"|\bif\s+any\b"
    r"|\bwhen\s+(?:does|do|is|are|would|will|can)\b[^?]{0,120}?\bappl(?:y|ies)\b",
    re.IGNORECASE,
)


def is_exception_question(question: str) -> bool:
    """True when the asked question asks about exceptions, exemptions or derogations."""
    try:
        return bool(_EXCEPTION_Q_RE.search(_ask_text(question)))
    except Exception:  # noqa: BLE001
        return False


def _asks_conditions(question: str) -> bool:
    try:
        return bool(_CONDITIONS_Q_RE.search(_ask_text(question)))
    except Exception:  # noqa: BLE001
        return False


_AUX_WORDS = frozenset(
    {"does", "do", "is", "are", "can", "could", "must", "should", "will", "would",
     "has", "have", "may", "shall", "am"}
)
_FIRST_WORD_RE = re.compile(r"[A-Za-z]+")
_PREAMBLE_RE = re.compile(r"^[^,?]{1,60},\s+")
_WH_MAIN_RE = re.compile(r"\b(?:which|what|how)\b", re.IGNORECASE)
_ALTERNATIVE_OR_RE = re.compile(r"\bor\b(?!\s+not\b)", re.IGNORECASE)
_REQUEST_RE = re.compile(
    r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:explain|list|name|describe|tell|"
    r"outline|clarify|specify|summari[sz]e|identify|provide|give|set\s+out|elaborate|"
    r"indicate|detail|walk)\b",
    re.IGNORECASE,
)


def _is_yes_no_sentence(sentence: str) -> bool:
    s = sentence.strip()
    if not s.endswith("?"):
        return False
    candidates = [s]
    pm = _PREAMBLE_RE.match(s)
    if pm:
        candidates.append(s[pm.end():])
    for cand in candidates:
        fw = _FIRST_WORD_RE.match(cand)
        if not fw or fw.group(0).lower() not in _AUX_WORDS:
            continue
        if _REQUEST_RE.match(cand) or _WH_MAIN_RE.search(cand) or _ALTERNATIVE_OR_RE.search(cand):
            return False
        return True
    return False


def _yes_no_sentence(question: str) -> str:
    """The yes/no sentence of the asked question, ``""`` if it is not yes/no.

    The FIRST interrogative decides, not the last. A multi-clause question whose
    leading ask is a wh- or request clause ("Who needs to establish the system?
    Is it possible that ...?") is not a yes/no question: the trailing clause is
    a follow-up, and demanding a Yes/No lead for it repels a correct answer. The
    converse also holds — "Do I have an obligation? What if I am an importer?"
    is a yes/no question, and reading only the last clause missed it.
    """
    ask = _ask_text(question)
    sentences = _sentences(ask)
    interrogatives = [s for s in sentences if s.rstrip().endswith("?")]
    if interrogatives and _is_yes_no_sentence(interrogatives[0]):
        return interrogatives[0]
    if sentences and _is_yes_no_sentence(sentences[0]):
        return sentences[0]
    return ""


def is_yes_no_question(question: str) -> bool:
    """True when the asked question is a yes/no question (see module docstring)."""
    try:
        return bool(_yes_no_sentence(question))
    except Exception:  # noqa: BLE001
        return False


_GOVERNING_Q_RE = re.compile(
    r"\b(?:which|what)\s+(?:articles?|provisions?|parts?|sections?|chapters?|annex(?:es)?|rules?)\b"
    r"(?:\s+[^\s?]+){0,8}?\s+"
    r"(?:governs?|regulates?|covers?|deals?\s+with|sets?\s+out|lays?\s+down|address(?:es)?)\b",
    re.IGNORECASE,
)


def is_governing_provision_question(question: str) -> bool:
    """True for "which article/provision ... governs/regulates/covers ... X"."""
    try:
        return bool(_GOVERNING_Q_RE.search(_ask_text(question)))
    except Exception:  # noqa: BLE001
        return False


# ── Provision heads and coordinates in prose ─────────────────────────────────

_LIST_SEP = r"\s*(?:,\s*(?:and|or)\b|,|\band\b|\bor\b|\bto\b|\bthrough\b)\s*"
_SUBSEG_RE = re.compile(
    r"(?:[^\S\n]?\(\s*[0-9a-z]{1,4}\s*\)|\.(?:\d{1,3}|[a-z]{1,4})(?![A-Za-z0-9]))*"
)
_ARTICLE_HEAD_RE = re.compile(r"\b(?P<word>(?i:articles?|arts?))\b\.?[^\S\n]*(?P<num>\d{1,3})(?!\d)")
_ANNEX_HEAD_RE = re.compile(r"\b(?P<word>(?i:annex(?:es)?))[^\S\n]+(?P<num>[IVX]{1,5})\b")
_ARTICLE_LIST_ITEM_RE = re.compile(r"(?P<sep>" + _LIST_SEP + r")(?P<num>\d{1,3})(?!\d)")
_ANNEX_LIST_ITEM_RE = re.compile(r"(?P<sep>" + _LIST_SEP + r")(?P<num>[IVX]{1,5})\b")


def named_heads(text: str) -> list[str]:
    """``Article N`` / ``Annex X`` heads named in prose, order-preserving, deduped.

    Accepts ``Art. 13``, ``Article 13(3)(b)``, ``Article 13.3.b``,
    ``Articles 9 and 10``, ``Articles 9 to 15`` (expanded), ``Annex III, point 5(a)``,
    ``Annexes I and III``. Only heads that exist (Articles 1 to 113, Annexes I to
    XIII) are returned.
    """
    try:
        src = _s(text)
        hits: list[tuple[int, int, str]] = []
        for m in _ARTICLE_HEAD_RE.finditer(src):
            n = int(m.group("num"))
            if 1 <= n <= _MAX_ARTICLE:
                hits.append((m.start(), 0, f"Article {n}"))
            if not m.group("word").lower().endswith("s"):
                continue
            prev, order = n, 1
            pos = _SUBSEG_RE.match(src, m.end()).end()
            while True:
                lm = _ARTICLE_LIST_ITEM_RE.match(src, pos)
                if lm is None:
                    break
                k = int(lm.group("num"))
                if lm.group("sep").strip() in ("to", "through") and 1 <= prev < k <= _MAX_ARTICLE and k - prev <= 20:
                    for j in range(prev + 1, k):
                        hits.append((m.start(), order, f"Article {j}"))
                        order += 1
                if 1 <= k <= _MAX_ARTICLE:
                    hits.append((m.start(), order, f"Article {k}"))
                    order += 1
                prev = k
                pos = _SUBSEG_RE.match(src, lm.end()).end()
        for m in _ANNEX_HEAD_RE.finditer(src):
            roman = m.group("num")
            if roman in _ROMAN_TO_INT:
                hits.append((m.start(), 0, f"Annex {roman}"))
            if not m.group("word").lower().endswith("s"):
                continue
            prev_i, order = _ROMAN_TO_INT.get(roman, 0), 1
            pos = m.end()
            while True:
                lm = _ANNEX_LIST_ITEM_RE.match(src, pos)
                if lm is None:
                    break
                r2 = lm.group("num")
                k = _ROMAN_TO_INT.get(r2, 0)
                if lm.group("sep").strip() in ("to", "through") and 0 < prev_i < k:
                    for j in range(prev_i + 1, k):
                        hits.append((m.start(), order, f"Annex {_ANNEX_ROMANS[j - 1]}"))
                        order += 1
                if k:
                    hits.append((m.start(), order, f"Annex {r2}"))
                    order += 1
                prev_i = k
                pos = lm.end()
        hits.sort(key=lambda h: (h[0], h[1]))
        return _dedupe(h[2] for h in hits)
    except Exception:  # noqa: BLE001
        return []


_ART = r"\bart(?:icle)?\.?\s*\d{1,3}"
_LETTER_LIST = r"\([a-z]{1,4}\)(?:" + _LIST_SEP + r"\([a-z]{1,4}\))*"
_COORD_NORMALISERS: tuple[tuple[re.Pattern[str], str], ...] = (
    # "point (a) of paragraph 3 of Article 13" -> "Article 13(3)(a)"
    (re.compile(r"\bpoints?\s+(" + _LETTER_LIST + r")\s+of\s+paragraph\s+(\d{1,2})\s+of\s+(" + _ART + r")\b", re.I),
     r"\3(\2)\1"),
    # "points (a) and (c) of Article 13(3)" -> "Article 13(3)(a) and (c)"
    (re.compile(r"\bpoints?\s+(" + _LETTER_LIST + r")\s+of\s+(" + _ART + r"\s*\(\d{1,2}\))", re.I), r"\2\1"),
    # "paragraph 3 of Article 13" -> "Article 13(3)"
    (re.compile(r"\bparagraph\s+(\d{1,2})\s+of\s+(" + _ART + r")\b", re.I), r"\2(\1)"),
    # "point 5(a) of Annex III" -> "Annex III(5)(a)"
    (re.compile(r"\bpoints?\s+(\d{1,2})((?:\s*\([a-z]{1,4}\))*)\s+of\s+(annex\s+(?-i:[IVX]{1,5}))\b", re.I),
     r"\3(\1)\2"),
    # "Article 13, paragraph 3" -> "Article 13(3)"
    (re.compile(r"(" + _ART + r"),\s*paragraph\s+(\d{1,2})\b", re.I), r"\1(\2)"),
    # "Annex III, point 5(a)" / "Annex IV point 1(e)" -> "Annex III(5)(a)"
    (re.compile(r"\b(annex\s+(?-i:[IVX]{1,5})),?\s+points?\s+(\d{1,2})\b", re.I), r"\1(\2)"),
    # "Article 6(3), first subparagraph" -> "Article 6(3)"
    (re.compile(r"(\((?:\d{1,3}|[a-z]{1,4})\)),?\s+(?:first|second|third|fourth|fifth|last)\s+subparagraph\b,?", re.I),
     r"\1"),
    # "Article 13(3), point (a)" -> "Article 13(3)(a)"
    (re.compile(r"(\((?:\d{1,3}|[a-z]{1,4})\)),?\s+points?\s+(\([a-z]{1,4}\))", re.I), r"\1\2"),
)
_COORD_RE = re.compile(
    r"\b(?:(?i:art(?:icle)?s?)\b\.?[^\S\n]*(?P<art>\d{1,3})(?!\d)"
    r"|(?i:annex(?:es)?)[^\S\n]+(?P<anx>[IVX]{1,5})\b)"
    r"(?P<tail>(?:[^\S\n]?\([^\S\n]*(?:\d{1,3}|[a-z]{1,4})[^\S\n]*\)"
    r"|\.(?:\d{1,3}|[a-z]{1,4})(?![A-Za-z0-9]))*)"
)
_TAIL_SEG_RE = re.compile(r"\(\s*(\d{1,3}|[a-z]{1,4})\s*\)|\.(\d{1,3}|[a-z]{1,4})")
_CONT_RE = re.compile(
    r"(?P<sep>" + _LIST_SEP + r")"
    r"(?:\(\s*(?P<sib>\d{1,3}|[a-z]{1,4})\s*\)"
    r"|(?P<item>\d{1,2})(?P<itail>(?:[^\S\n]?\(\s*[a-z]{1,4}\s*\))*)(?!\d|\.\d))"
)
_ITEM_LETTER_RE = re.compile(r"\(\s*([a-z]{1,4})\s*\)")
_BARE_LETTER_RE = re.compile(r"(?<![\w)])\(([a-z])\)")
_BARE_RANGE_RE = re.compile(r"(?<![\w)])\(([a-z])\)\s*(?:to|through)\s*\(([a-z])\)")

Path = tuple[str, ...]


def _head_from_parts(art: str | None, anx: str | None) -> str | None:
    if art:
        n = int(art)
        return f"Article {n}" if 1 <= n <= _MAX_ARTICLE else None
    if anx and anx in _ROMAN_TO_INT:
        return f"Annex {anx}"
    return None


def _coord_str(path: Path) -> str:
    return path[0] if len(path) == 1 else path[0] + "." + ".".join(path[1:])


def _expand_between(a: str, b: str, level: int) -> list[str]:
    """Members strictly between two list endpoints at one level of a coordinate."""
    if a.isdigit() and b.isdigit():
        x, y = int(a), int(b)
        return [str(k) for k in range(x + 1, y)] if 0 < y - x <= 30 else []
    romans = level >= 3 or (len(a) > 1 or len(b) > 1)
    if romans and a in _ROMAN_SUB and b in _ROMAN_SUB:
        i, j = _ROMAN_SUB.index(a), _ROMAN_SUB.index(b)
        return list(_ROMAN_SUB[i + 1:j]) if 0 < j - i <= 20 else []
    if len(a) == 1 and len(b) == 1 and a.isalpha() and b.isalpha():
        x, y = ord(a), ord(b)
        return [chr(k) for k in range(x + 1, y)] if 0 < y - x <= 26 else []
    return []


def _normalise_coords(text: str) -> str:
    out = _s(text)
    for rx, repl in _COORD_NORMALISERS:
        out = rx.sub(repl, out)
    return out


def _parse_paths(norm: str) -> list[Path]:
    out: list[Path] = []
    for m in _COORD_RE.finditer(norm):
        head = _head_from_parts(m.group("art"), m.group("anx"))
        if head is None:
            continue
        segs = tuple(a or b for a, b in _TAIL_SEG_RE.findall(m.group("tail") or ""))
        base: Path = (head, *segs)
        out.append(base)
        if not segs:
            continue
        prev, pos = base, m.end()
        while True:
            cm = _CONT_RE.match(norm, pos)
            if cm is None:
                break
            ranged = cm.group("sep").strip() in ("to", "through")
            if cm.group("sib") is not None:
                token = cm.group("sib")
                if ranged:
                    for mid in _expand_between(prev[-1], token, len(prev) - 1):
                        out.append((*prev[:-1], mid))
                new: Path = (*prev[:-1], token)
            elif cm.group("item") is not None and head.startswith("Annex"):
                item = cm.group("item")
                if ranged and len(prev) == 2 and prev[1].isdigit():
                    for mid in _expand_between(prev[1], item, 1):
                        out.append((head, mid))
                new = (head, item, *_ITEM_LETTER_RE.findall(cm.group("itail") or ""))
            else:
                break
            out.append(new)
            prev, pos = new, cm.end()
    return out


def _paths_in(text: str) -> list[Path]:
    return _parse_paths(_normalise_coords(text))


def _prefix_closure(paths: Iterable[Path]) -> set[str]:
    out: set[str] = set()
    for path in paths:
        for k in range(1, len(path) + 1):
            out.add(_coord_str(path[:k]))
    return out


def _loose_point_coords(text: str) -> set[str]:
    """``point (c)`` / ``(c)`` attached to a paragraph named in the SAME sentence."""
    out: set[str] = set()
    for sentence in _sentences(text):
        norm = _normalise_coords(sentence)
        parents = {p[:2] for p in _parse_paths(norm) if len(p) >= 2}
        if not parents:
            continue
        letters = {m.group(1) for m in _BARE_LETTER_RE.finditer(norm)}
        for m in _BARE_RANGE_RE.finditer(norm):
            letters.update(_expand_between(m.group(1), m.group(2), 2))
        for parent in parents:
            for letter in letters:
                out.add(_coord_str((*parent, letter)))
    return out


# ── Detector 1: closed statutory sets ────────────────────────────────────────

_NESTED_LIST_RE = re.compile(r"[:;,]?\s*\((?:a|i|1)\)\s")


def _member_own_text(text: str) -> str:
    """A member's own words, without the nested list it introduces."""
    m = _NESTED_LIST_RE.search(text)
    return text[: m.start()] if m and m.start() > 20 else text


def _groups(members: list[tuple[str, str]]) -> list[tuple[str, list[tuple[str, str]]]]:
    groups: dict[str, list[tuple[str, str]]] = {}
    order: list[str] = []
    for coord, text in members:
        if "." not in coord:
            continue
        parent = coord.rsplit(".", 1)[0]
        if parent not in groups:
            groups[parent] = []
            order.append(parent)
        groups[parent].append((coord, text))
    return [(p, groups[p]) for p in order]


def _member_gaps(question: str, answer: str, limit: int | None) -> list[Gap]:
    ask = _ask_text(question)
    ans = _s(answer)
    if not ans.strip() or not is_list_question(ask):
        return []
    from app.data.provision_hierarchy import closed_set_members  # noqa: PLC0415

    ans_paths = _paths_in(ans)
    mentioned = _prefix_closure(ans_paths) | _prefix_closure(_paths_in(ask))
    covered = _prefix_closure(ans_paths) | _loose_point_coords(ans)
    answer_tokens = _token_set(ans)
    gaps: list[Gap] = []
    seen: set[str] = set()
    for head in _dedupe(named_heads(ans) + named_heads(ask)):
        for parent, children in _groups(closed_set_members(head)):
            # A head's own paragraphs are separate provisions, never a closed list.
            if "." not in parent or len(children) < _MIN_GROUP_CHILDREN:
                continue
            if parent not in mentioned and not any(c in mentioned for c, _ in children):
                continue
            for coord, text in children:
                if coord in seen or coord in covered:
                    continue
                own = _member_own_text(text)
                window = _content_tokens(own)[:_MEMBER_TOKEN_WINDOW]
                if not window or _coverage(window, answer_tokens) >= _MEMBER_COVER_RATIO:
                    continue
                seen.add(coord)
                gaps.append(Gap("member", coord, _clip(own)))
                if limit is not None and len(gaps) >= limit:
                    return gaps
    return gaps


def missing_closed_set_members(question: str, answer: str) -> list[Gap]:
    """Members of an ENGAGED closed statutory list that the answer does not state.

    Fires only on a list-shaped question. A group (children of one paragraph or
    point, >= 3 of them) is engaged only when the answer or the live question
    names its parent paragraph or one of its members. A member is covered when
    the answer names its coordinate in any common form, or carries >= 55 % of the
    member's first 8 content tokens. At most 10 gaps.
    """
    try:
        return _member_gaps(question, answer, _MAX_MEMBER_GAPS)
    except Exception:  # noqa: BLE001
        return []


# ── Detector 2: exception and condition limbs ────────────────────────────────

_EXCEPTION_TRIGGER_RE = re.compile(
    r"\b(?:unless|except|with\s+the\s+exception\s+of|shall\s+not\s+apply|does\s+not\s+apply|"
    r"by\s+way\s+of\s+derogation|provided\s+that|including\s+by|where\s+applicable)\b",
    re.IGNORECASE,
)
_CLAUSE_END_RE = re.compile(r"[;.](?=\s|$)")


def _clause_spans(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for m in _EXCEPTION_TRIGGER_RE.finditer(text):
        end_m = _CLAUSE_END_RE.search(text, m.end())
        end = end_m.start() if end_m else len(text)
        clause = text[m.start():end].strip()
        if clause:
            out.append((m.start(), end, clause))
    return out


def _exception_units(head: str, ans_paths: list[Path], ask_tokens: set[str]) -> list[tuple[str, str]]:
    from app.data.provision_hierarchy import closed_set_members  # noqa: PLC0415
    from app.data.provision_text import get_provision_text  # noqa: PLC0415

    named = _dedupe(_coord_str(p[:2]) for p in ans_paths if p[0] == head and len(p) >= 2)
    units = [(c, t) for c in named if (t := get_provision_text(c))]
    if units:
        return units
    paragraphs = [(c, t) for c, t in closed_set_members(head) if c.count(".") == 1]
    if not paragraphs:
        body = get_provision_text(head)
        return [(head, body)] if body else []
    ranked = sorted(
        range(len(paragraphs)),
        key=lambda i: (-sum(1 for t in _content_tokens(paragraphs[i][1]) if t in ask_tokens), i),
    )
    top = sorted(ranked[:2])
    return [(paragraphs[i][0], get_provision_text(paragraphs[i][0]) or paragraphs[i][1]) for i in top]


def _exception_gaps(question: str, answer: str, limit: int | None) -> list[Gap]:
    ask = _ask_text(question)
    ans = _s(answer)
    if not ans.strip() or not (is_exception_question(ask) or _asks_conditions(ask)):
        return []
    heads = named_heads(ans)[:_MAX_EXCEPTION_HEADS]
    if not heads:
        return []
    ans_paths = _paths_in(ans)
    answer_tokens = _token_set(ans)
    ask_tokens = set(_content_tokens(ask))
    gaps: list[Gap] = []
    seen: set[str] = set()
    for head in heads:
        for coord, raw in _exception_units(head, ans_paths, ask_tokens):
            flat = " ".join(_s(raw).split())
            emitted: list[tuple[int, int]] = []
            for start, end, clause in _clause_spans(flat):
                if any(s <= start and end <= e for s, e in emitted):
                    continue  # nested inside a clause already reported
                tokens = _content_tokens(clause, _CLAUSE_STOPWORDS)
                if len(tokens) < _EXCEPTION_MIN_TOKENS:
                    continue
                if _coverage(tokens, answer_tokens) >= _EXCEPTION_COVER_RATIO:
                    continue
                clipped = _clip(clause)
                if clipped in seen:
                    continue
                seen.add(clipped)
                emitted.append((start, end))
                gaps.append(Gap("exception", coord, clipped))
                if limit is not None and len(gaps) >= limit:
                    return gaps
    return gaps


def missing_exception_limbs(question: str, answer: str) -> list[Gap]:
    """Exception/condition clauses of the paragraphs the answer relies on, left out.

    Fires only when the asked question is about exceptions, or asks "under what
    conditions", "if any" or "when does ... apply". For each head the answer
    names (max 4) it reads the verbatim text of the paragraphs the answer names,
    or the 2 paragraphs closest to the question when only the head is named, and
    reports each "unless / except / shall not apply / provided that / including
    by ..." clause of which < 50 % of the content tokens reach the answer. At
    most 4 gaps.
    """
    try:
        return _exception_gaps(question, answer, _MAX_EXCEPTION_GAPS)
    except Exception:  # noqa: BLE001
        return []


# ── Detector 3: verdict lead ─────────────────────────────────────────────────

_MARKDOWN_LEAD_RE = re.compile(r"^[\s*_#>`~|•\-]+")
_VERDICT_TOKEN_RE = re.compile(r"(?:yes|no)\b", re.IGNORECASE)
_V = r"(?:prohibited|high-?risk|permitted|required|allowed|lawful|applicable|mandatory)"
#: A lead verdict stated in words rather than as a bare Yes/No. A bare-token
#: test scored "Not prohibited and not high-risk." as having no verdict at all,
#: so the guard forced a needless repair on a correct answer (R410: only 1 of
#: its 11 fires on the 110-row ledger was a real missing lead).
_VERDICT_LEAD_RE = re.compile(
    r"^(?:"
    r"not\b"
    r"|(?:the\s+|an?\s+)?[\w-]+(?:\s+[\w-]+){0,4}\s+(?:is|are|isn't|aren't|does|do)\s+"
    r"(?:not\s+)?(?:[a-z]+ly\s+)?" + _V + r"\b"
    r"|" + _V + r"\b"
    r")",
    re.IGNORECASE,
)
#: "High-risk ONLY WHERE ..." frames a condition instead of deciding, so it is
#: not a verdict lead and the guard still fires.
_VERDICT_CONDITION_RE = re.compile(
    r"\s+(?:only\s+)?(?:where|when|if|unless|provided|to\s+the\s+extent|insofar)\b",
    re.IGNORECASE,
)
#: "Only where ... does Article 27 apply" opens a condition outright.
_VERDICT_CONDITION_LEAD_RE = re.compile(
    r"^(?:only\s+)?(?:where|when|if|unless|provided|to\s+the\s+extent|insofar)\b",
    re.IGNORECASE,
)


def _opens_with_verdict(answer: str) -> bool:
    """Does the answer open by deciding the question's yes/no verdict?

    Accepts a bare ``Yes``/``No`` and, because the Act's verdicts are usually
    phrased as classifications, an equally explicit worded lead: a negation
    ("Not prohibited and not high-risk."), a subject-predicate verdict
    ("Emotion recognition is not categorically prohibited ...") or a bare
    classification ("High-risk."). A conditional, wherever it sits, is refused.
    """
    lead = _MARKDOWN_LEAD_RE.sub("", _s(answer))
    if _VERDICT_TOKEN_RE.match(lead):
        return True
    if _VERDICT_CONDITION_LEAD_RE.match(lead):
        return False
    m = _VERDICT_LEAD_RE.match(lead)
    return bool(m) and not _VERDICT_CONDITION_RE.match(lead, m.end())


def _verdict_gaps(question: str, answer: str, limit: int | None = None) -> list[Gap]:
    ans = _s(answer)
    if not ans.strip():
        return []
    sentence = _yes_no_sentence(question)
    if not sentence or _opens_with_verdict(ans):
        return []
    return [Gap("verdict", "", _clip(sentence))]


def verdict_lead_gap(question: str, answer: str) -> list[Gap]:
    """One verdict gap when a yes/no question is not answered with a Yes/No lead."""
    try:
        return _verdict_gaps(question, answer)
    except Exception:  # noqa: BLE001
        return []


# ── Detector 4: pushback keep ────────────────────────────────────────────────


def _is_challenge(question: str) -> bool:
    from app.data.graph_rag_prompts import is_challenge_turn  # noqa: PLC0415

    return bool(is_challenge_turn(_s(question)))


def _anchored_sentences(text: str) -> list[str]:
    return [s for s in _sentences(text) if named_heads(s)]


def _keep_gaps(question: str, answer: str, limit: int | None) -> list[Gap]:
    ans = _s(answer)
    if not ans.strip() or not _is_challenge(question):
        return []
    prev = previous_answer(question)
    if not prev:
        return []
    new_heads = set(named_heads(ans))
    new_tokens = _token_set(ans)
    gaps: list[Gap] = []
    for sentence in _anchored_sentences(prev):
        heads = named_heads(sentence)
        if any(h in new_heads for h in heads):
            continue
        if _coverage(_content_tokens(sentence), new_tokens) >= _KEEP_COVER_RATIO:
            continue
        gaps.append(Gap("keep", heads[0], _clip(sentence)))
        if limit is not None and len(gaps) >= limit:
            break
    return gaps


def dropped_pushback_points(question: str, answer: str) -> list[Gap]:
    """Anchored sentences of the previous answer that the post-pushback answer drops.

    Only on a challenge turn with a previous assistant turn in the flattened
    history. A previous sentence that names a provision is dropped when none of
    its heads is named in the new answer AND < 40 % of its content tokens reach
    it. At most 4 gaps. ⚠ Needs the flattened history (module docstring, 1).
    """
    try:
        return _keep_gaps(question, answer, _MAX_KEEP_GAPS)
    except Exception:  # noqa: BLE001
        return []


# ── Aggregation ──────────────────────────────────────────────────────────────


def collect_gaps(question: str, answer: str) -> list[Gap]:
    """Run the ENABLED detectors: members, exceptions, keep, verdict; cap 12."""
    try:
        gaps: list[Gap] = []
        if closed_set_completeness_enabled():
            gaps.extend(missing_closed_set_members(question, answer))
        if exception_limb_guard_enabled():
            gaps.extend(missing_exception_limbs(question, answer))
        if pushback_keep_enabled():
            gaps.extend(dropped_pushback_points(question, answer))
        if verdict_lead_guard_enabled():
            gaps.extend(verdict_lead_gap(question, answer))
        return gaps[:_MAX_TOTAL_GAPS]
    except Exception:  # noqa: BLE001
        return []


# ── Prompt text builders ─────────────────────────────────────────────────────

_GOVERNING_CLAUSE_TEXT = (
    " GOVERNING PROVISION: the question asks which provision governs its subject. "
    "Name that provision first. Then state, in one short clause for each numbered "
    "paragraph of that provision, what that paragraph requires, without repeating the "
    "question. Cite nothing beyond what the references block supports.\n"
)


def governing_provision_clause(question: str) -> str:
    """User-channel clause for "which article governs X"; ``""`` unless ON and it fires."""
    try:
        if not governing_provision_clause_enabled() or not is_governing_provision_question(question):
            return ""
        return _GOVERNING_CLAUSE_TEXT
    except Exception:  # noqa: BLE001
        return ""


def pushback_keep_clause(question: str) -> str:
    """User-channel PREVIOUS ANSWER POINTS block; ``""`` unless ON and applicable.

    Requires a challenge turn, a previous assistant turn with at least one
    sentence naming a provision, and a disputing turn that names no provision the
    previous answer did not (the clause tells the model no new law was cited).
    """
    try:
        if not pushback_keep_enabled() or not _is_challenge(question):
            return ""
        prev = previous_answer(question)
        points = _anchored_sentences(prev)[:_MAX_KEEP_CLAUSE_POINTS]
        if not points:
            return ""
        dispute, _ = _reask_split(question)
        if set(named_heads(dispute)) - set(named_heads(prev)):
            return ""
        lines = [
            " PREVIOUS ANSWER POINTS: the user disputes the previous answer without "
            "citing any new law. The previous answer stated these points:"
        ]
        lines.extend(f"{i}. {_clip(p)}" for i, p in enumerate(points, 1))
        lines.append(
            "Keep each point unless you can state the specific legal reason it was "
            "wrong. Do not drop the substance of a provision already stated merely to "
            "shorten the answer. Do not refer to the previous answer, to the dispute or "
            "to this list in your reply."
        )
        return "\n".join(lines) + "\n"
    except Exception:  # noqa: BLE001
        return ""


def _gap_line(gap: Gap) -> str:
    if gap.kind == "member":
        return f'{gap.coordinate}: a listed item the question asks for is missing. Act text: "{gap.text}"'
    if gap.kind == "exception":
        return (
            f"{gap.coordinate}: a condition or exception of the provision the answer relies on "
            f'is missing. Act text: "{gap.text}"'
        )
    if gap.kind == "keep":
        return (
            f"{gap.coordinate}: an earlier answer to the same question stated this point and "
            f'the current answer drops it: "{gap.text}"'
        )
    if gap.kind == "verdict":
        return (
            f'Verdict: the question asks for a yes or no answer ("{gap.text}") and the current '
            "answer does not open with Yes or No."
        )
    return ""


def build_repair_user_message(question: str, answer: str, gaps: list[Gap]) -> str:
    """USER-channel repair prompt; ``""`` when there is nothing to repair.

    The system prompt is not reliably delivered on the wrapper path, so every
    rule lives here.
    """
    try:
        items = [line for g in (gaps or []) if (line := _gap_line(g))]
        if not items:
            return ""
        lines = [
            "QUESTION:",
            _ask_text(question),
            "",
            "CURRENT ANSWER:",
            _s(answer).strip(),
            "",
            "WHAT THE CURRENT ANSWER LEAVES OUT:",
        ]
        lines.extend(f"{i}. {item}" for i, item in enumerate(items, 1))
        budget = repair_char_budget(answer, gaps)
        rules = [
            "Return the complete revised answer only.",
            "Keep every correct statement and every citation already in the current answer. "
            "Rephrase or merge them if that keeps the answer shorter, but drop none of them.",
            "Add one short clause for each missing item, grounded in the quoted text.",
            f"The revision must be at most {budget} characters. Compress duplicated wording so "
            "the additions fit; never restate the question or a citation already given.",
        ]
        if any(g.kind == "verdict" for g in gaps):
            rules.append(
                "Open with Yes or No, followed by the qualifying condition the Act states."
            )
        rules.extend(
            [
                "Write no preamble. Do not comment on these rules, on the missing items, on an "
                "earlier answer or on the materials you were given.",
                "Do not use a bulleted list unless the current answer already uses one.",
                "Keep a neutral regulatory tone. Do not use dashes as punctuation and do not use ellipses.",
            ]
        )
        lines.extend(["", "RULES:"])
        lines.extend(rules)
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        return ""


# ── Repair acceptance ────────────────────────────────────────────────────────

_META_RE = re.compile(
    r"instruction|materials?\s+(?:supplied|provided)|references?\s+(?:provided|supplied)"
    r"|(?:supplied|provided)\s+(?:references|materials?)",
    re.IGNORECASE,
)
_INSTRUCTIONS_FOR_USE_RE = re.compile(r"instructions?\s+for\s+use", re.IGNORECASE)

_DETECTORS: dict[str, Callable[[str, str, int | None], list[Gap]]] = {
    "member": _member_gaps,
    "exception": _exception_gaps,
    "keep": _keep_gaps,
    "verdict": _verdict_gaps,
}


def _meta_mentions(text: str) -> int:
    return len(_META_RE.findall(_INSTRUCTIONS_FOR_USE_RE.sub(" ", _s(text))))


def accept_repair(question: str, original: str, repaired: str, gaps: list[Gap]) -> bool:
    """True only when the repair is strictly better and introduces nothing new.

    * ``repaired`` is non-empty;
    * the gap count, recomputed with the SAME detectors that produced ``gaps``
      (uncapped, on the original and on the repair), is strictly lower, and a
      verdict gap is resolved by a Yes/No lead;
    * every head named in ``original`` is still named;
    * no head is named that is not in ``original``, in a gap coordinate or in a
      gap's verbatim text;
    * ``len(repaired) <= max(1.8 * len(original), len(original) + 900)``;
    * no ``...``/``…``, and no new meta-commentary ("instruction" outside
      "instructions for use", "materials supplied", "references provided").
    """
    try:
        rep = _s(repaired).strip()
        orig = _s(original).strip()
        if not rep or not gaps:
            return False
        if "..." in rep or "…" in rep:
            return False
        if len(rep) > repair_char_budget(orig, gaps):
            return False
        if _meta_mentions(rep) > _meta_mentions(orig) + sum(_meta_mentions(g.text) for g in gaps):
            return False
        orig_heads = named_heads(orig)
        rep_heads = set(named_heads(rep))
        if any(h not in rep_heads for h in orig_heads):
            return False
        allowed = set(orig_heads)
        for g in gaps:
            allowed.update(named_heads(g.coordinate))
            allowed.update(named_heads(g.text))
        if rep_heads - allowed:
            return False
        kinds = [k for k in _dedupe(g.kind for g in gaps) if k in _DETECTORS]
        if not kinds:
            return False
        if "verdict" in kinds and not _opens_with_verdict(rep):
            return False
        before = sum(len(_DETECTORS[k](question, orig, None)) for k in kinds)
        after = sum(len(_DETECTORS[k](question, rep, None)) for k in kinds)
        return after < before
    except Exception:  # noqa: BLE001
        return False

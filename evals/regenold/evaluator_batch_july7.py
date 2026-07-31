"""Parser + dataset module for ``REGENOLD_JULY_7_EVALUATOR_BATCH.md``.

This is the RAW report export of the 2026-07-07 official run — 333 requests,
untruncated (unlike the Postgres-recovered, 2000-char-truncated, deduplicated
snapshot in :mod:`evals.regenold.official_batch`). It is the highest-fidelity
copy of the graded batch this repo has: every request block carries the exact
``API Request JSON`` sent and the exact ``API Response JSON`` we shipped.

WHERE THE FILE LIVES
---------------------
``REGENOLD_JULY_7_EVALUATOR_BATCH.md`` at the repo root. It is large (16k+
lines) and untracked, so this module does **not** vendor its content — it
parses the file at runtime. Calling :func:`load_batch` when the file is
missing raises a clear ``FileNotFoundError``.

STRUCTURE (verified against all 333 blocks; see ``_HEADER_RE`` / ``_REQ_JSON_RE``
/ ``_RESP_JSON_RE`` below)
------------------------------------------------------------------------------
Each block is::

    ## Request #<seq> [<DIFFICULTY> MODE | <difficulty_category>]
    *Seq <audit_seq> | Timestamp: <iso8601>*

    **Question:** <raw question text>

    ### API Request JSON
    `json
    { "question": ..., "difficulty": ..., "difficulty_category": ...,
      "correlation_id": ..., "history_turns_used": ..., "has_system_context": ...,
      "tenant_id": ..., "tier": ..., "timestamp": ..., "question_hash": ... }
    `

    ### API Response JSON
    `json
    { "answer": ..., "references": [...], "confidence": ..., "retrieval_path": ...,
      "kb_version": ..., "scope_reason": ..., "anchor_articles": [...]? }
    `

The code fences use a SINGLE backtick (not the usual triple-backtick), which
is why ``_REQ_JSON_RE`` / ``_RESP_JSON_RE`` look unusual — this was verified
directly against the file (1332 single-backtick runs, 0 triple-backtick runs).

The markdown ``**Question:**`` field is byte-identical to the JSON
``question`` field on all 333 rows (verified) — :attr:`BatchRow.question`
reads the JSON field directly and the markdown field is not re-parsed.

THREE POPULATIONS, KEYED ON ``history_turns_used``
---------------------------------------------------
====================  ===  ===================================================
``history_turns``     n    what it is
====================  ===  ===================================================
``0``                 111  Single-turn (EASY mode). 110 unique questions (one
                            sent twice). :attr:`BatchRow.question` is the raw,
                            un-flattened user turn — verified: never contains
                            the ``"Latest question:\\n"`` / ``"Let's try
                            again:\\n"`` markers described below.
``18``                111  Hard-mode turn 1 — the question re-asked inside a
                            growing multi-turn conversation. :attr:`question`
                            is OUR OWN app's flattened prompt string (the exact
                            input the engine consumed to produce
                            :attr:`july7_answer`), which for a row that is not
                            the first turn of its rolling window ends
                            ``"...\\n\\nLatest question:\\n<the real question>"``.
``20``                111  Hard-mode turn 2. For 67/111 rows this is a genuine
                            adversarial PUSHBACK — the flattened prompt embeds
                            the verbatim :data:`PUSHBACK_PREAMBLE` template
                            ("I don't think this is correct...") ending
                            ``"Let's try again:\\n<the real question>"``. The
                            other 44/111 are NOT pushback challenges at all —
                            they are the next ordinary multi-turn follow-up in
                            the rolling window (verified directly: their
                            flattened prompt never contains the pushback
                            marker). :func:`hard_pushback_rows` still returns
                            all 111 (matching the evaluator's own
                            ``history_turns_used == 20`` grouping); use
                            :attr:`Conversation.has_pushback_marker` /
                            :func:`pairing_report` to see the 67/44 split.
====================  ===  ===================================================

RECOVERY CAVEAT (mirrors :mod:`evals.regenold.official_batch`)
----------------------------------------------------------------
The flattened prompt strings are truncated at 2000 chars by this repo's own
persistence layer (50/333 rows sit at exactly 2000 chars). This is the SAME
truncation :mod:`evals.regenold.official_batch` documents; this module is a
richer (untruncated-where-possible, non-deduplicated, all-333-rows) view of
the identical underlying data, not an independent source.

:meth:`BatchRow.terminal_question_text` recovers the actual final user-turn
text by stripping the ``"Latest question:\\n"`` / ``"Let's try again:\\n"``
scaffolding OUR OWN app writes into the flattened prompt. It is best-effort:
verified to exactly recover a matching easy-mode question on 49/111 turn-1
rows and 67/111 turn-2 rows (the remainder diverge — most likely R86
query-denoiser rewriting, not corruption — see :func:`pairing_report`).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

#: Repo root is two levels up from this file (evals/regenold/<this file>).
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "REGENOLD_JULY_7_EVALUATOR_BATCH.md"

# ── raw-text markers our own app writes into a flattened multi-turn prompt ──
_LATEST_QUESTION_MARKER = "Latest question:\n"
_LETS_TRY_AGAIN_MARKER = "Let's try again:\n"
#: Substring that identifies a genuine adversarial pushback turn (as opposed
#: to an ordinary multi-turn follow-up that happens to sit at
#: ``history_turns_used == 20``). See the module docstring's turn-2 row.
_PUSHBACK_MARKER = "I don't think this is correct"

#: Byte-verified verbatim adversarial pushback template (67/111 turns==20 rows
#: carry it exactly; see :func:`pairing_report`). ``{question}`` is filled
#: with the original question, re-asked verbatim — mirrors
#: ``evals.regenold.official_batch.PUSHBACK_TEMPLATE``, independently
#: rederived from this richer, non-deduplicated source and cross-checked
#: byte-identical against it.
PUSHBACK_PREAMBLE = (
    "I don't think this is correct. Perhaps your answer contains hallucinations.\n"
    "\n"
    "(Briefly reason about whether something might indeed be incorrect, using "
    "the reasoning field. Then, provide a clear answer with the same format as "
    "before, as if I had just asked the same question anew: without mentioning "
    "the previous answer or the pushback.)\n"
    "\n"
    "Let's try again:\n"
    "{question}"
)

# ── block parsing ────────────────────────────────────────────────────────

_BLOCK_SPLIT_RE = re.compile(r"(?=^## Request #)", re.M)
_HEADER_RE = re.compile(
    r"\A## Request #(?P<seq>\d+) \[(?P<mode_label>.*?)\]\n"
    r"\*Seq (?P<audit_seq>\d+) \| Timestamp: (?P<timestamp>[^*]*)\*"
)
_REQ_JSON_RE = re.compile(r"### API Request JSON\n`json\n(?P<json>\{.*?\})\n`", re.S)
_RESP_JSON_RE = re.compile(r"### API Response JSON\n`json\n(?P<json>\{.*?\})\n`", re.S)


@dataclass(frozen=True)
class BatchRow:
    """One graded request from the 2026-07-07 official run."""

    seq: int
    request_id: str  # correlation_id
    question: str
    difficulty: str  # "EASY" | "HARD"
    category: str  # difficulty_category
    history_turns: int  # 0 | 18 | 20
    question_hash: str
    timestamp: str
    july7_answer: str
    july7_refs: tuple[str, ...]
    july7_confidence: float | None
    july7_retrieval_path: str
    july7_scope_reason: str
    july7_anchor_articles: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return f"july7-{self.seq:03d}"

    def easy_messages(self) -> list[dict[str, str]]:
        """Single cold user turn — the byte-exact request body for a
        ``history_turns == 0`` row."""
        return [{"role": "user", "content": self.question}]

    def terminal_question_text(self) -> str:
        """Best-effort recovery of the actual final user-turn text.

        Strips our own app's ``"...Latest question:\\n"`` flatten marker and,
        if present, the ``"Let's try again:\\n"`` pushback-template tail —
        leaving just the underlying question. A no-op (returns
        :attr:`question` verbatim, stripped) when neither marker is present,
        which is always true for ``history_turns == 0`` rows (verified: 0/111
        contain either marker).
        """
        text = self.question
        idx = text.rfind(_LATEST_QUESTION_MARKER)
        if idx != -1:
            text = text[idx + len(_LATEST_QUESTION_MARKER):]
        idx2 = text.rfind(_LETS_TRY_AGAIN_MARKER)
        if idx2 != -1:
            text = text[idx2 + len(_LETS_TRY_AGAIN_MARKER):]
        return text.strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "seq": self.seq,
            "request_id": self.request_id,
            "question": self.question,
            "difficulty": self.difficulty,
            "category": self.category,
            "history_turns": self.history_turns,
            "question_hash": self.question_hash,
            "timestamp": self.timestamp,
            "july7_answer": self.july7_answer,
            "july7_refs": list(self.july7_refs),
            "july7_confidence": self.july7_confidence,
            "july7_retrieval_path": self.july7_retrieval_path,
            "july7_scope_reason": self.july7_scope_reason,
            "july7_anchor_articles": list(self.july7_anchor_articles),
        }


def _parse_block(block: str) -> BatchRow:
    m_hdr = _HEADER_RE.match(block)
    if not m_hdr:
        raise ValueError(f"malformed block header near: {block[:160]!r}")
    m_req = _REQ_JSON_RE.search(block)
    m_resp = _RESP_JSON_RE.search(block)
    if m_req is None or m_resp is None:
        raise ValueError(
            f"Request #{m_hdr.group('seq')}: missing API Request/Response JSON fence"
        )
    req = json.loads(m_req.group("json"))
    resp = json.loads(m_resp.group("json"))
    return BatchRow(
        seq=int(m_hdr.group("seq")),
        request_id=str(req.get("correlation_id") or ""),
        question=str(req.get("question") or ""),
        difficulty=str(req.get("difficulty") or ""),
        category=str(req.get("difficulty_category") or ""),
        history_turns=int(req.get("history_turns_used") or 0),
        question_hash=str(req.get("question_hash") or ""),
        timestamp=str(req.get("timestamp") or m_hdr.group("timestamp").strip()),
        july7_answer=str(resp.get("answer") or ""),
        july7_refs=tuple(resp.get("references") or ()),
        july7_confidence=resp.get("confidence"),
        july7_retrieval_path=str(resp.get("retrieval_path") or ""),
        july7_scope_reason=str(resp.get("scope_reason") or ""),
        july7_anchor_articles=tuple(resp.get("anchor_articles") or ()),
    )


@lru_cache(maxsize=4)
def _load_cached(path_str: str) -> tuple[BatchRow, ...]:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(
            f"REGENOLD_JULY_7_EVALUATOR_BATCH.md not found at {path}. "
            "This module parses the raw evaluator-batch export at runtime and "
            "deliberately does not vendor its content (16k+ lines, untracked). "
            "Place the file at the repo root, or pass an explicit path to "
            "load_batch()."
        )
    text = path.read_text(encoding="utf-8")
    parts = _BLOCK_SPLIT_RE.split(text)
    blocks = [p for p in parts if p.startswith("## Request #")]
    if not blocks:
        raise ValueError(f"{path}: no '## Request #N [...]' blocks found")
    return tuple(_parse_block(b) for b in blocks)


def load_batch(path: Path | None = None) -> list[BatchRow]:
    """Parse all 333 request/response blocks, in send order (seq 1..333)."""
    resolved = Path(path) if path is not None else _DEFAULT_PATH
    return list(_load_cached(str(resolved.resolve())))


def easy_rows(path: Path | None = None) -> list[BatchRow]:
    """The 111 ``history_turns_used == 0`` single-turn requests."""
    return [r for r in load_batch(path) if r.history_turns == 0]


def hard_turn1_rows(path: Path | None = None) -> list[BatchRow]:
    """The 111 ``history_turns_used == 18`` hard-mode turn-1 requests."""
    return [r for r in load_batch(path) if r.history_turns == 18]


def hard_pushback_rows(path: Path | None = None) -> list[BatchRow]:
    """The 111 ``history_turns_used == 20`` hard-mode turn-2 requests.

    NOTE: only 67 of these carry the verbatim :data:`PUSHBACK_PREAMBLE` — the
    other 44 are ordinary multi-turn follow-ups. See the module docstring and
    :func:`pairing_report`.
    """
    return [r for r in load_batch(path) if r.history_turns == 20]


# ── conversation pairing ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Conversation:
    """A hard-mode turn-1 paired with its turn-2 (``history_turns == 20``)."""

    turn1: BatchRow
    turn2: BatchRow
    #: How :func:`group_conversations` found this pair. ``"text_match"`` — the
    #: recovered terminal question text was identical and uniquely matched a
    #: turn-1 row. ``"positional"`` — fell back to send-order adjacency (the
    #: row immediately preceding the turn-2 row in the batch, or, failing
    #: that, the nearest unused turn-1 row by ``seq`` distance). Verified:
    #: EVERY turn-2 row is immediately preceded by its turn-1 row in send
    #: order (111/111), so the positional fallback is exact here even though
    #: it is a heuristic in general.
    pairing_method: Literal["text_match", "positional"]
    #: True when :attr:`turn2` actually carries the adversarial pushback
    #: template (67/111); False when it is an ordinary follow-up question
    #: that merely happens to sit at ``history_turns_used == 20`` (44/111).
    has_pushback_marker: bool

    @property
    def question_text(self) -> str:
        """The recovered question both turns are (nominally) about."""
        return self.turn1.terminal_question_text()

    def turn1_messages(self) -> list[dict[str, str]]:
        return [{"role": "user", "content": self.question_text}]

    def pushback_messages(self, turn1_answer: str) -> list[dict[str, str]]:
        """Turn 2: our turn-1 answer, then the fixed adversarial pushback."""
        return [
            {"role": "user", "content": self.question_text},
            {"role": "assistant", "content": turn1_answer},
            {
                "role": "user",
                "content": PUSHBACK_PREAMBLE.format(question=self.question_text),
            },
        ]


def group_conversations(path: Path | None = None) -> list[Conversation]:
    """Pair each hard turn-1 row with its turn-2 (pushback) row.

    Prefers an exact match on :meth:`BatchRow.terminal_question_text`; falls
    back to positional (send-order adjacency) pairing when the text doesn't
    uniquely match — see :attr:`Conversation.pairing_method`. Call
    :func:`pairing_report` for the aggregate match-rate breakdown.
    """
    rows = load_batch(path)
    turn1s = sorted((r for r in rows if r.history_turns == 18), key=lambda r: r.seq)
    turn2s = sorted((r for r in rows if r.history_turns == 20), key=lambda r: r.seq)
    by_seq = {r.seq: r for r in rows}

    text_index: dict[str, list[int]] = {}
    for r in turn1s:
        text_index.setdefault(r.terminal_question_text(), []).append(r.seq)

    all_turn1_seqs = [r.seq for r in turn1s]
    used: set[int] = set()
    conversations: list[Conversation] = []
    for t2 in turn2s:
        term2 = t2.terminal_question_text()
        candidates = [s for s in text_index.get(term2, ()) if s not in used]
        if len(candidates) == 1:
            seq1 = candidates[0]
            method: Literal["text_match", "positional"] = "text_match"
        else:
            prev = by_seq.get(t2.seq - 1)
            if prev is not None and prev.history_turns == 18 and prev.seq not in used:
                seq1 = prev.seq
                method = "positional"
            else:
                remaining = [s for s in all_turn1_seqs if s not in used]
                if not remaining:
                    continue  # no turn-1 row left to pair with — skip
                seq1 = min(remaining, key=lambda s: abs(s - t2.seq))
                method = "positional"
        used.add(seq1)
        conversations.append(
            Conversation(
                turn1=by_seq[seq1],
                turn2=t2,
                pairing_method=method,
                has_pushback_marker=_PUSHBACK_MARKER in t2.question,
            )
        )
    return conversations


def pairing_report(path: Path | None = None) -> dict[str, Any]:
    """Diagnostics for :func:`group_conversations` + the pushback template.

    Reports how much of the pairing is exact text-match vs positional
    fallback, how many turn-2 rows actually carry the verbatim
    :data:`PUSHBACK_PREAMBLE`, and how often each hard-mode group's recovered
    terminal question text matches one of the 110 unique easy-mode questions.
    """
    convos = group_conversations(path)
    total = len(convos)
    text_match = sum(1 for c in convos if c.pairing_method == "text_match")
    with_marker = sum(1 for c in convos if c.has_pushback_marker)

    rows = load_batch(path)
    easy_terms = {r.terminal_question_text() for r in rows if r.history_turns == 0}
    t1_rows = [r for r in rows if r.history_turns == 18]
    t2_rows = [r for r in rows if r.history_turns == 20]
    t1_matches_easy = sum(1 for r in t1_rows if r.terminal_question_text() in easy_terms)
    t2_matches_easy = sum(1 for r in t2_rows if r.terminal_question_text() in easy_terms)

    return {
        "total_conversations": total,
        "text_match": text_match,
        "positional_fallback": total - text_match,
        "text_match_rate": round(text_match / total, 3) if total else 0.0,
        "pushback_preamble_verbatim_count": with_marker,
        "pushback_preamble_total": total,
        "pushback_preamble_rate": round(with_marker / total, 3) if total else 0.0,
        "unique_easy_questions": len(easy_terms),
        "turn1_terminal_matches_easy": t1_matches_easy,
        "turn1_total": len(t1_rows),
        "turn2_terminal_matches_easy": t2_matches_easy,
        "turn2_total": len(t2_rows),
    }


def stats(path: Path | None = None) -> dict[str, Any]:
    """Counts by difficulty / category / history-turns group."""
    rows = load_batch(path)
    return {
        "total": len(rows),
        "by_difficulty": dict(Counter(r.difficulty for r in rows)),
        "by_category": dict(Counter(r.category for r in rows)),
        "by_history_turns": dict(sorted(Counter(r.history_turns for r in rows).items())),
    }

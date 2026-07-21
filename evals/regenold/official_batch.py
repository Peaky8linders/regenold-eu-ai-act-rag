"""The REAL regenold benchmark batch — recovered from the production audit chain.

WHAT THIS IS
------------
On **2026-07-07** the regenold judges ran their benchmark against our live
Railway endpoint. Every request landed in the Postgres audit chain
(``evidence_entries``, ``tenant_id='partner:regenold'``, ``created_by='regenold'``)
because ``app/routes/regenold.py`` persists the full question + answer per
request. The report we were scored on
(``docs/Antifragile-Regenold-benchmark-report-preview.pdf``, 2026-07-14) is that
run. So this module is **the actual graded question set**, not a proxy.

333 rows, in three groups (``history_turns_used`` distinguishes them):

===============  ===  ==========================================================
group            n    what it is
===============  ===  ==========================================================
``turns == 0``   111  **EASY mode** — each question asked cold, single-turn.
                      110 unique (one question was sent twice). The stored
                      ``question`` is the RAW user turn: verbatim, warts and all
                      ("Does the EU AI Act explicitly *requires to use*...").
``turns == 18``  111  **HARD mode, turn 1** — the same questions asked inside a
                      growing multi-turn conversation.
``turns == 20``  111  **HARD mode, turn 2** — the judge PUSHES BACK on our
                      answer ("I don't think this is correct. Perhaps your
                      answer contains hallucinations.") and re-asks.
===============  ===  ==========================================================

RECOVERY CAVEAT (read before trusting a hard-mode replay)
---------------------------------------------------------
For the two hard groups the audit stores our **flattened / de-noised** query
(R86 query de-noiser output), not the judge's raw turn, and it is truncated at
2000 chars. So the hard turns are NOT byte-recoverable. What IS recoverable, and
what this module reconstructs:

* The **question set is the same 110** — verified: every one of the 67
  pushback rows whose trailing ``Let's try again:`` question survived truncation
  matches a question in the easy set exactly (67/67).
* The **pushback wording is a single fixed template** — verified: 13/13
  recovered pushback preambles are byte-identical (:data:`PUSHBACK_TEMPLATE`).
* The **conversation shape** is a rolling window of prior Q&A in the same
  session (the recovered "Conversation so far:" blocks are successive windows
  of one growing conversation).

Hard mode is therefore replayed **faithfully in protocol, reconstructed in
context**: same questions, same rolling-conversation shape, byte-exact pushback
template. The easy batch is a **byte-exact** replay.

Each item also carries the answer + references we actually shipped on
2026-07-07 (``jul07_answer`` / ``jul07_refs``) — i.e. the exact output the
official report graded. That makes a then-vs-now comparison possible without
re-running history.

The snapshot lives next to this module in ``_official_batch_20260707.json`` so
the batch is reproducible offline (no DB credentials needed to run an eval).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_SNAPSHOT = Path(__file__).resolve().parent / "_official_batch_20260707.json"

#: Byte-exact pushback preamble the judge sent as hard-mode turn 2. Recovered
#: from the 13 audit rows where it survived the 2000-char truncation; all 13 are
#: identical. ``{question}`` is the original question, re-asked verbatim.
PUSHBACK_TEMPLATE = (
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

#: How many prior (user, assistant) exchanges the reconstructed hard-mode
#: conversation carries. Matches the recovered "Conversation so far:" windows.
HARD_CONTEXT_EXCHANGES = 4


@dataclass(frozen=True)
class OfficialRow:
    """One graded question from the 2026-07-07 official run."""

    id: str
    question: str
    question_hash: str
    #: The answer we shipped on 2026-07-07 — what the official report graded.
    jul07_answer: str
    jul07_refs: tuple[str, ...]
    jul07_confidence: float | None
    jul07_retrieval_path: str
    jul07_scope_reason: str

    def easy_messages(self) -> list[dict[str, str]]:
        """Byte-exact easy-mode request body: one cold user turn."""
        return [{"role": "user", "content": self.question}]

    def pushback_content(self) -> str:
        return PUSHBACK_TEMPLATE.format(question=self.question)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "question_hash": self.question_hash,
            "jul07_answer": self.jul07_answer,
            "jul07_refs": list(self.jul07_refs),
            "jul07_confidence": self.jul07_confidence,
            "jul07_retrieval_path": self.jul07_retrieval_path,
            "jul07_scope_reason": self.jul07_scope_reason,
        }


@lru_cache(maxsize=1)
def load_official_batch() -> tuple[OfficialRow, ...]:
    """The 110 unique questions of the 2026-07-07 official run, in send order."""
    raw = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    return tuple(
        OfficialRow(
            id=str(r["id"]),
            question=str(r["question"]),
            question_hash=str(r.get("question_hash") or ""),
            jul07_answer=str(r.get("jul07_answer") or ""),
            jul07_refs=tuple(r.get("jul07_refs") or ()),
            jul07_confidence=r.get("jul07_confidence"),
            jul07_retrieval_path=str(r.get("jul07_retrieval_path") or ""),
            jul07_scope_reason=str(r.get("jul07_scope_reason") or ""),
        )
        for r in raw
    )


def build_hard_messages(
    row: OfficialRow, history: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Hard-mode turn 1: the rolling prior conversation + this question.

    ``history`` is the caller-maintained running conversation (already trimmed
    to :data:`HARD_CONTEXT_EXCHANGES`); it is not mutated.
    """
    return [*history, {"role": "user", "content": row.question}]


def build_pushback_messages(
    row: OfficialRow, history: list[dict[str, str]], first_answer: str
) -> list[dict[str, str]]:
    """Hard-mode turn 2: our turn-1 answer, then the judge's pushback."""
    return [
        *history,
        {"role": "user", "content": row.question},
        {"role": "assistant", "content": first_answer},
        {"role": "user", "content": row.pushback_content()},
    ]


def trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the last :data:`HARD_CONTEXT_EXCHANGES` (user, assistant) pairs."""
    return history[-(2 * HARD_CONTEXT_EXCHANGES):]

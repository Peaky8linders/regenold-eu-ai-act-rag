"""R138-eval — PAIRWISE judge prompts (4 axes, A-vs-B).

The existing ``evals/judge/prompts.py`` scores ONE answer absolutely
(pass/fail per axis). That works for an A/B only when one arm is deterministic
(the R100 ``graphrag_ab`` constraint) — diffing two independent Sonnet runs is
dominated by generation + judge variance.

These prompts instead present BOTH arm answers in ONE judge call and ask which
better satisfies the axis. Pairwise preference is far more reliable than an
absolute threshold under noise, and it is the standard for LLM-judge A/B
(Chatbot Arena / AlpacaEval). The harness runs each pair twice with positions
swapped (A-first then B-first) and counts a WIN only when both orders agree —
cancelling position bias. The rubric CONTENT is the same legal grading rubric
as the absolute prompts (LeMAJ single-axis design); only the task (compare vs
score) changes.

Each renderer returns a prompt asking for ONE JSON object:
``{"winner": "A" | "B" | "tie", "reason": "<short phrase>"}``.
"""
from __future__ import annotations

from typing import Any

AXES: tuple[str, ...] = ("correctness", "refs", "conciseness", "tone")

_JSON_TAIL = (
    "\nRespond with ONE JSON object only (no preamble, no markdown fences):\n"
    '{"criteria_analysis":{"candidate_a_critique":"<short analysis>","candidate_b_critique":"<short analysis>"},'
    '"comparative_reasoning":"<one phrase comparing A vs B>","winner":"A"|"B"|"tie"}'
)


def _escape_xml(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _common_head(row: dict[str, Any]) -> str:
    return (
        "You are an EU AI Act legal expert comparing two candidate answers (A "
        "and B) to the SAME question. Judge ONLY the axis stated below. First audit "
        "each candidate's strengths and weaknesses, synthesize the comparison, and "
        "only then decide the winner. Answer 'tie' only when they are genuinely "
        "indistinguishable on this axis.\n\n"
        "<question>\n" + _escape_xml((row.get("question") or "")[:600]) + "\n</question>\n"
    )


def _ab_block(answer_a: str, refs_a: list[str], answer_b: str, refs_b: list[str]) -> str:
    return (
        "\n<candidate_a>\n"
        "<answer>\n" + _escape_xml(answer_a or "") + "\n</answer>\n"
        "<references>" + str(refs_a or []) + "</references>\n"
        "</candidate_a>\n"
        "\n<candidate_b>\n"
        "<answer>\n" + _escape_xml(answer_b or "") + "\n</answer>\n"
        "<references>" + str(refs_b or []) + "</references>\n"
        "</candidate_b>\n"
    )


def render_correctness(row, answer_a, refs_a, answer_b, refs_b) -> str:
    return (
        _common_head(row)
        + "GOLD ANSWER KEYWORDS: " + str(row.get("expected_keywords") or []) + "\n"
        + "GOLD REFERENCES: " + str(row.get("expected_refs") or []) + "\n"
        + _ab_block(answer_a, refs_a, answer_b, refs_b)
        + "\nAXIS = ANSWER CORRECTNESS. Which answer is more factually correct "
        "and substantively complete against the gold keywords + references? "
        "Penalise an incorrect assertion on a gold-keyword topic more than a "
        "missing detail."
        + _JSON_TAIL
    )


def render_refs(row, answer_a, refs_a, answer_b, refs_b,
                article_summaries: dict[str, str] | None = None) -> str:
    summaries = article_summaries or {}
    lines: list[str] = []
    for r in list(refs_a)[:6] + list(refs_b)[:6]:
        s = summaries.get(str(r))
        if s and f"  {r}:" not in "\n".join(lines):
            lines.append(f"  {r}: {s[:240]}")
    block = "\n".join(lines) if lines else "  (no KB summaries available)"
    return (
        _common_head(row)
        + "GOLD REFERENCES: " + str(row.get("expected_refs") or []) + "\n"
        + _ab_block(answer_a, refs_a, answer_b, refs_b)
        + "CITED-ARTICLE KB SUMMARIES:\n" + block + "\n"
        + "\nAXIS = REFERENCE FAITHFULNESS. Which answer's PROSE more faithfully "
        "describes the articles it cites (no cite-and-mismatch — e.g. cites "
        "Art. 13 but describes Art. 14), and cites the load-bearing gold "
        "articles? An answer that cites an article it never describes loses."
        + _JSON_TAIL
    )


def render_conciseness(row, answer_a, refs_a, answer_b, refs_b) -> str:
    la, lb = len(answer_a or ""), len(answer_b or "")
    return (
        _common_head(row)
        + "GOLD ANSWER KEYWORDS: " + str(row.get("expected_keywords") or []) + "\n"
        + _ab_block(answer_a, refs_a, answer_b, refs_b)
        + f"(Answer A is {la} chars; Answer B is {lb} chars.)\n"
        + "\nAXIS = CONCISENESS. The spec wants a professional answer that fully "
        "answers the question with the minimal necessary length and no "
        "boilerplate / hedging ('It is important to note that...'). Which "
        "answer is tighter WITHOUT dropping a substantive part of the answer? "
        "A shorter answer that omits a required part is NOT more concise — it "
        "is incomplete; prefer the other."
        + _JSON_TAIL
    )


def render_tone(row, answer_a, refs_a, answer_b, refs_b) -> str:
    return (
        _common_head(row)
        + _ab_block(answer_a, refs_a, answer_b, refs_b)
        + "\nAXIS = REGULATORY TONE. Which answer better matches a formal EU "
        "regulator voice — no hedging, no first-person ('I would', 'we "
        "recommend'), no marketing/chatty tone, no speculation beyond the "
        "regulation? Cite-anchored declarative obligation prose is ideal."
        + _JSON_TAIL
    )


def render(axis: str, row: dict[str, Any], *,
           answer_a: str, refs_a: list[str], answer_b: str, refs_b: list[str],
           article_summaries: dict[str, str] | None = None) -> str:
    if axis == "correctness":
        return render_correctness(row, answer_a, refs_a, answer_b, refs_b)
    if axis == "refs":
        return render_refs(row, answer_a, refs_a, answer_b, refs_b, article_summaries)
    if axis == "conciseness":
        return render_conciseness(row, answer_a, refs_a, answer_b, refs_b)
    if axis == "tone":
        return render_tone(row, answer_a, refs_a, answer_b, refs_b)
    raise ValueError(f"unknown axis {axis!r}; valid: {AXES}")


__all__ = ["AXES", "render"]

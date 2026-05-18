"""R50 — judge prompts (4 axes × 1 prompt each).

Per Anthropic eval-design docs + LeMAJ (Legal-domain LLM-as-Judge,
arXiv 2510.07243): separate single-axis prompts beat unified prompts
on legal Q&A by 11-18% (the unified prompt anchors all sub-scores to
its first verdict via attention-bleed).

Each prompt is intentionally TIGHT (~10-15 lines). The judge produces
JSON; the runner parses it and aggregates. Binary pass/fail per axis +
free-text ``failure_mode`` slot (the failure-mode strings cluster
naturally into the buckets the aggregator surfaces).

Axis 5 (latency) needs no judge — wall-clock from the route is ground
truth.

## Token budget

Each prompt: ~3.5K input + ~250 output. Sonnet 4.6 at $3/M in + $15/M
out → ~$0.011 + $0.0038 = $0.015 per axis per row. Four axes × 476
rows = ~$28/full bench run. Smoke (56 V2 rows) ≈ $3.30.
"""
from __future__ import annotations

from typing import Any


# ── Axis 1 — Answer correctness (LeMAJ LDP-style) ───────────────────────


def render_axis_correctness(row: dict[str, Any]) -> str:
    """LeMAJ-style: decompose the predicted answer into Legal Data
    Points (one assertion each), tag each correct/incorrect/irrelevant
    against the gold keywords + refs, verdict pass when ≥70% correct
    AND no incorrect on a gold-keyword topic."""
    return (
        "You are an EU AI Act legal expert grading a Q&A system.\n"
        "\n"
        "QUESTION: " + (row.get("question") or "")[:600] + "\n"
        "GOLD ANSWER KEYWORDS: " + str(row.get("expected_keywords") or []) + "\n"
        "GOLD REFERENCES: " + str(row.get("expected_refs") or []) + "\n"
        "PREDICTED ANSWER: " + (row.get("answer_preview") or row.get("predicted_answer") or "")[:1200] + "\n"
        "PREDICTED REFERENCES: " + str(row.get("pred_refs") or row.get("predicted_refs") or []) + "\n"
        "\n"
        "Decompose the predicted answer into Legal Data Points (one assertion each).\n"
        "For each LDP, tag: correct | incorrect | irrelevant | missing-from-gold.\n"
        "Verdict 'pass' iff ≥70% LDPs are 'correct' AND no 'incorrect' fires on a\n"
        "gold-keyword topic. Otherwise 'fail'.\n"
        "\n"
        "Respond with ONE JSON object only (no preamble, no markdown fences):\n"
        '{"verdict":"pass"|"fail","correct":N,"incorrect":N,"irrelevant":N,'
        '"missing":N,"failure_mode":"<one short phrase>"}'
    )


# ── Axis 2 — Reference correctness (citation faithfulness) ──────────────


def render_axis_refs(row: dict[str, Any], article_summaries: dict[str, str]) -> str:
    """The load-bearing judge. Asks: does the answer's prose actually
    describe what the cited articles say, or does it cite-and-mismatch
    (e.g. cites Art. 13 but describes Art. 14 oversight obligations)?"""
    pred_refs = row.get("pred_refs") or row.get("predicted_refs") or []
    expected = row.get("expected_refs") or []
    ref_lines: list[str] = []
    for r in pred_refs[:6]:  # cap to avoid prompt bloat
        summary = article_summaries.get(str(r))
        if summary:
            ref_lines.append(f"  {r}: {summary[:280]}")
    refs_block = "\n".join(ref_lines) if ref_lines else "  (no KB summaries available)"
    return (
        "You are an EU AI Act legal expert checking citation faithfulness.\n"
        "\n"
        "QUESTION: " + (row.get("question") or "")[:500] + "\n"
        "GOLD REFERENCES: " + str(expected) + "\n"
        "PREDICTED ANSWER: " + (row.get("answer_preview") or row.get("predicted_answer") or "")[:1000] + "\n"
        "PREDICTED REFERENCES: " + str(pred_refs) + "\n"
        "PREDICTED REFERENCES — KB SUMMARIES:\n"
        f"{refs_block}\n"
        "\n"
        "For each predicted reference, decide whether the answer's prose\n"
        "actually describes what that article says. A cite-and-mismatch\n"
        "(e.g. cites Art. 13 but describes Art. 14 oversight) is a 'fail'\n"
        "even if the gold reference set agrees on the article number.\n"
        "Verdict 'pass' iff ≥80% predicted refs are faithfully described\n"
        "AND no load-bearing ref is mismatched.\n"
        "\n"
        "Respond with ONE JSON object only:\n"
        '{"verdict":"pass"|"fail","faithful":N,"mismatched":N,'
        '"failure_mode":"<one short phrase>"}'
    )


# ── Axis 3 — Conciseness (length-normalised + boilerplate detection) ────


def render_axis_conciseness(row: dict[str, Any]) -> str:
    """Conciseness vs gold + boilerplate detection (1-4 sentences per
    spec; hedging phrases like 'It is important to note that…' fail)."""
    pred = (row.get("answer_preview") or row.get("predicted_answer") or "")
    gold_kw = row.get("expected_keywords") or []
    return (
        "You are auditing the conciseness of a regulatory Q&A answer.\n"
        "\n"
        "GOLD ANSWER KEYWORDS: " + str(gold_kw) + "\n"
        "PREDICTED ANSWER ("
        f"{len(pred)} chars): " + pred[:1200] + "\n"
        "\n"
        "The competition spec encourages 1-4 sentences, professionally\n"
        "worded, with the minimal set of references. Verdict 'pass' iff:\n"
        "  (1) sentence count is in 1..4 AND\n"
        "  (2) no sentence is pure boilerplate / hedging (e.g.\n"
        "      'It is important to note that...', 'In general...',\n"
        "      'There are several considerations...') AND\n"
        "  (3) every sentence carries either a citation anchor or a\n"
        "      domain-substantive token (a gold keyword OR a regulatory\n"
        "      noun like 'provider' / 'deployer' / 'risk' / 'obligation').\n"
        "\n"
        "Respond with ONE JSON object only:\n"
        '{"verdict":"pass"|"fail","sentences":N,"boilerplate_sents":[...],'
        '"failure_mode":"<one short phrase>"}'
    )


# ── Axis 4 — Regulatory tone (anchor examples) ──────────────────────────


_TONE_ANCHORS = (
    'Providers of high-risk AI systems shall establish a risk management system per Article 9.',
    'The deployer must conduct a fundamental rights impact assessment under Article 27 before placing the system in service.',
    'Article 5 prohibits emotion recognition in workplace and educational settings except for medical or safety purposes.',
)


def render_axis_tone(row: dict[str, Any]) -> str:
    """Anchor-example based tone judging. Hard-fail on hedging, first-
    person, marketing voice, casual tone, speculation."""
    pred = (row.get("answer_preview") or row.get("predicted_answer") or "")
    anchor_block = "\n".join(f"  [{chr(65+i)}] {a}" for i, a in enumerate(_TONE_ANCHORS))
    return (
        "You are auditing the REGULATORY TONE of an EU AI Act Q&A answer.\n"
        "\n"
        "Three gold-standard regulator-voice anchor examples:\n"
        f"{anchor_block}\n"
        "\n"
        "PREDICTED ANSWER: " + pred[:1200] + "\n"
        "\n"
        "Does the predicted answer match this register? Verdict 'fail' if:\n"
        "  * hedging ('might', 'could', 'may possibly') outside legal\n"
        "    necessity contexts,\n"
        "  * first-person ('I would', 'we recommend'),\n"
        "  * marketing voice ('our system', 'best-in-class'),\n"
        "  * casual or chatty tone,\n"
        "  * speculation beyond the regulation's text.\n"
        "Otherwise 'pass'.\n"
        "\n"
        "Respond with ONE JSON object only:\n"
        '{"verdict":"pass"|"fail","violations":[...],'
        '"failure_mode":"<one short phrase>"}'
    )


# ── Dispatch ─────────────────────────────────────────────────────────────


AXES: tuple[str, ...] = ("correctness", "refs", "conciseness", "tone")


def render(
    axis: str, row: dict[str, Any], *, article_summaries: dict[str, str] | None = None,
) -> str:
    """Dispatch to the per-axis renderer."""
    if axis == "correctness":
        return render_axis_correctness(row)
    if axis == "refs":
        return render_axis_refs(row, article_summaries or {})
    if axis == "conciseness":
        return render_axis_conciseness(row)
    if axis == "tone":
        return render_axis_tone(row)
    raise ValueError(f"unknown axis {axis!r}; valid: {AXES}")

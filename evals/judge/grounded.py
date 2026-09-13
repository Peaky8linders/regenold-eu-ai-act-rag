"""R284 — GROUNDED Sonnet-5 LLM-as-Judge.

An independent judge that scores answer + reference + citation correctness
against the VERBATIM EU AI Act text (``app.data.provision_text``), NOT against
the (possibly-incomplete) gold keyword/label set. This is the "proper
measurement" upgrade over ``evals.judge.runner``:

* the existing runner's *correctness* axis grades against GOLD KEYWORDS, and its
  *refs* axis grounds in KB SUMMARIES — neither is the regulation itself;
* this judge feeds the model the verbatim text of both the GOLD provisions and
  the PREDICTED provisions, and asks it to determine, per the Act:
    - ANSWER CORRECTNESS  — is the answer's substance correct per the text?
    - REFERENCE CORRECTNESS — of the cited provisions, which genuinely GOVERN the
      question (precision), and which governing provisions are MISSING (recall)?
      Scored against the Act, so an incomplete gold label cannot penalise a
      correct-but-broader citation, nor reward a wrong one the gold happens to omit.
    - CITATION FAITHFULNESS — does the prose accurately describe each cited
      provision (the cite-and-mismatch check), verified against verbatim text?

Default model: ``claude-sonnet-5``. Reuses the runner's provider/retry/parse
plumbing. Independent (absolute per-answer, no A/B leakage); position/label-blind
(the judge never sees which arm or system produced the answer).

CLI:
    python -m evals.judge.grounded \\
        --sidecar evals/bench/results/easyhard-r284-B.ckpt.jsonl \\
        --label r284-B-grounded --model claude-sonnet-5 \\
        --provider wrapper --timeout 90 --concurrency 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv()

from evals.judge.runner import (  # reuse the battle-tested call plumbing
    _call_judge_with_retry,
    _resolve_caller,
    set_judge_model,
)

# R361 — was ``claude-sonnet-5``, which resolves to
# ``eu.anthropic.claude-sonnet-5`` and returns api_access_denied_403 on the
# current Bedrock key vintage (CLAUDE.md R328.2 records the same class of
# failure for other newer pins). Measured 2026-08-23: 120/120 rows errored on
# all three axes. ``claude-sonnet-4-6`` is verified working on Bedrock and over
# the wrapper, so it is the safe default; override with ``--model``.
_DEFAULT_MODEL = "claude-sonnet-4-6"
GROUNDED_AXES: tuple[str, ...] = (
    "answer_correctness",
    "reference_correctness",
    "citation_faithfulness",
)

# Per-provision verbatim-text caps (chars). Generous so long articles (e.g.
# Article 5, whose prohibited practices (a)-(h) run ~4000 chars) are NOT
# truncated before a cited sub-point — a truncated grounding would false-fail
# an answer that correctly cites 5(1)(f)/(g)/(h). Sonnet-5 handles the context.
_GOLD_TEXT_CAP = 12000  # full Article 5 (~11k, the outlier) fits uncut
_PRED_TEXT_CAP = 6000
_MAX_GOLD_REFS = 6
_MAX_PRED_REFS = 8

# R319 — the SAME reasoning as the two caps above, applied to the ANSWER.
#
# The answer was rendered as `r['answer'][:1400]` (and [:1200] on the citation
# axis). Measured on the july7-r309 judged corpus: mean answer length 1413.3
# chars, so the cap sat ON the median and 50% (36/72) of rows exceeded it, 58%
# exceeded 1200. The judge was therefore shown a mid-sentence fragment and
# correctly reported that ITS OWN VIEW looked unfinished / incomplete -- while
# the wire answer was complete. Verified false failures:
#   july7-327 failed "omits the decisive profiling-always-high-risk rule";
#            that rule is present verbatim at char 2007.
#   july7-249 failed for a missing obligor; "Article 25" is at char 3454.
#   july7-095 failed on Annex XI/XII; "Article 53(2)" is at char 1595.
# This contaminated 3 of the 4 axes (answer_correctness, citation_faithfulness,
# answer_conciseness); reference_correctness never renders the answer and is
# unaffected. It is the likely driver of the apparent post-R308 "omission"
# regression: R308 uncapped answer length on the live path and pushed the corpus
# straight through a judge cap that was never updated.
#
# 6000 matches _PRED_TEXT_CAP and clears the observed corpus max (4361) whole.
_ANSWER_TEXT_CAP = 6000


# ── provision-text grounding ────────────────────────────────────────────


def _provision_block(refs: list[str], cap: int, max_refs: int) -> str:
    """Resolve each ref to verbatim EU AI Act text, article-level fallback."""
    from app.data.provision_text import get_provision_text  # local heavy import

    lines: list[str] = []
    seen: set[str] = set()
    for r in refs[:max_refs]:
        key = str(r).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        txt = get_provision_text(key)
        if txt is None:
            # fall back to the base article/annex text
            base = key.split(".")[0].split("(")[0].strip()
            if base and base != key:
                txt = get_provision_text(base)
        if txt:
            lines.append(f"[{key}] {txt.strip()[:cap]}")
        else:
            lines.append(f"[{key}] (no verbatim text resolved — likely not a real provision)")
    return "\n".join(lines) if lines else "  (none)"


def _norm(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise the sidecar row shape (easyhard ckpt jsonl / bench / v2)."""
    context_parts: list[str] = []
    for key in (
        "gold_context", "official_context", "full_context", "grounding_context",
        "gold_provision_text", "verbatim_context",
    ):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            context_parts.append(value.strip())
        elif isinstance(value, dict) and value:
            context_parts.extend(
                f"[{ref}] {text}" for ref, text in value.items() if str(text).strip()
            )
        elif isinstance(value, list):
            context_parts.extend(str(item).strip() for item in value if str(item).strip())
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "question": row.get("question") or row.get("live_question") or "",
        "answer": (row.get("pred_answer") or row.get("predicted_answer")
                   or row.get("answer_preview") or "").strip(),
        "pred_refs": list(row.get("pred_refs") or row.get("predicted_refs") or []),
        # R381 — ``july7_refs`` is DELIBERATELY absent from this chain.
        #
        # The R292 banner below documents the intent in words: "``run_official_batch``
        # writes ``jul07_refs`` — which is OUR OWN prior output, NOT gold. Mapping it
        # into ``gold_refs`` would make the judge grade 'did we match our past self',
        # which is circular, so we deliberately do NOT."  The guard named
        # ``jul07_refs``; the sidecar key is ``july7_refs``. One character, and the
        # fallback fired on every row.
        #
        # MEASURED on ``evals/bench/results/july7-july7-live-r379.ckpt.jsonl``: 24/24
        # rows had ``gold_refs`` populated and 24/24 were byte-identical to our own
        # 2026-07-07 output, the prompt shipped them as "GOLD CITATIONS", and the run
        # wrote ``gold_coverage: 1.0`` / ``recall_is_text_grounded: True`` — so the
        # <50% warning never fired and the scorecard asserted it was trustworthy while
        # measuring self-similarity. Every July-7 judged scorecard before this commit
        # rewards reverting toward the July arm. Both spellings stay out.
        "gold_refs": list(
            row.get("gold_refs") or row.get("expected_refs") or []
        ),
        "gold_answer": str(row.get("gold_answer") or row.get("answer_gold") or ""),
        "independent_gold_context": "\n\n".join(context_parts),
    }


def _answer_grounding_block(r: dict[str, Any]) -> str:
    """Independent answer context; never derived from predicted references."""
    supplied = str(r.get("independent_gold_context") or "").strip()
    gold_answer = str(r.get("gold_answer") or "").strip()
    parts: list[str] = []
    if supplied:
        parts.append(supplied)
    elif r["gold_refs"]:
        parts.append(_provision_block(r["gold_refs"], _GOLD_TEXT_CAP, _MAX_GOLD_REFS))
    elif r.get("pred_refs") and not _strict_independent_grounding_required():
        # No independent gold exists for this dataset (see
        # _strict_independent_grounding_required). Fall back to the verbatim text
        # of the PREDICTED provisions — HEAD's behaviour, and the basis of the
        # July-7 numbers in CLAUDE.md — but label it, because the selection is
        # prediction-derived and therefore partly circular: it can confirm that
        # an answer misreads the text it cites, and cannot detect that a better
        # provision was never cited. The reference-correctness axis, which is
        # scored against the Act rather than the gold label, is what covers that.
        parts.append(
            "[NOTE] The provisions below were selected by the answer's OWN "
            "citations; no independent gold context exists for this row. Judge "
            "whether the answer states these provisions correctly."
        )
        parts.append(_provision_block(r["pred_refs"], _GOLD_TEXT_CAP, _MAX_GOLD_REFS))
    if gold_answer:
        parts.append(f"[INDEPENDENT GOLD ANSWER] {gold_answer}")
    # ⚠ EMPTY MEANS EMPTY. This used to return the literal ``"  (none)"``, which
    # is a truthy string once stripped ("(none)"). `legal_v2`'s unscorable guard
    # tests `bool(_answer_grounding_block(r).strip())` as one of its OR'd
    # conditions, so that sentinel made the condition CONSTANT TRUE and the
    # whole guard permanently dead: a row with no gold answer, no gold refs, no
    # pred refs and no context was still sent to the judge, whose verbatim
    # evidence section then read "VERBATIM EU AI ACT TEXT: (none)" — and its
    # unverified SUPPORTED claims scored factual 1.0.
    #
    # A sentinel that reads as "nothing" to a human and as "something" to code
    # is the bug. Callers that want the literal marker render it themselves.
    return "\n\n".join(parts)


def _answer_grounding_source(r: dict[str, Any]) -> str:
    """Which grounding the answer-correctness axis actually used, per row."""
    if str(r.get("independent_gold_context") or "").strip():
        return "independent_gold_context"
    if r["gold_refs"]:
        return "gold_refs"
    if str(r.get("gold_answer") or "").strip():
        return "gold_answer_only"
    if r.get("pred_refs") and not _strict_independent_grounding_required():
        return "predicted_refs_fallback_circular"
    return "none"


def _has_independent_answer_grounding(r: dict[str, Any]) -> bool:
    return bool(
        str(r.get("independent_gold_context") or "").strip()
        or str(r.get("gold_answer") or "").strip()
        or r["gold_refs"]
    )


def _unsupported_fails_enabled() -> bool:
    """``GROUNDED_JUDGE_UNSUPPORTED_FAILS`` — default **OFF**.

    Whether an UNSUPPORTED-but-not-wrong claim fails the answer-correctness row.
    Default OFF so the axis keeps the meaning the documented July-7 numbers were
    produced under; the strict reading is always emitted alongside as
    ``verdict_unsupported_strict``, so nothing is lost either way.
    """
    import os  # noqa: PLC0415

    return os.getenv("GROUNDED_JUDGE_UNSUPPORTED_FAILS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _strict_independent_grounding_required() -> bool:
    """``GROUNDED_JUDGE_STRICT_GROUNDING`` — default **OFF**.

    Restricting answer-correctness to independently-supplied gold context is the
    methodologically clean position: grading an answer against provision text
    that the answer's OWN citations selected is circular.

    But it cannot be the default here. This repo's reason to exist is the
    July-7 re-evaluation, and ``_official_batch_20260707.json`` carries **no
    gold answer and no gold refs** — only ``jul07_answer`` / ``jul07_refs``,
    which are the July-7 SYSTEM's predictions, not gold. Measured on
    ``official-opus5-tailfix-live-easy.ckpt.jsonl``: zero rows expose any of the
    three grounding fields, so ON makes the axis return
    ``judge_error=no_independent_gold_context`` for 100/100 rows and silently
    deletes the very number CLAUDE.md tracks (answer correctness 0.500 -> 0.780).

    Default OFF therefore keeps the axis measurable and comparable, and every
    row records ``answer_grounding_source`` so a prediction-derived grounding is
    visible in the output rather than assumed away.
    """
    import os  # noqa: PLC0415

    return os.getenv("GROUNDED_JUDGE_STRICT_GROUNDING", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _has_reference_gold_grounding(r: dict[str, Any]) -> bool:
    supplied = str(r.get("independent_gold_context") or "").strip()
    if supplied:
        return True
    from app.data.provision_text import get_provision_text
    return any(get_provision_text(str(ref).strip()) is not None for ref in r["gold_refs"])


# ── grounded prompts ────────────────────────────────────────────────────


def render_answer_correctness(r: dict[str, Any]) -> str:
    # Ground on the UNION of gold + predicted provisions so the judge can verify
    # every provision the answer relies on (not just the gold ones — the gold
    # labels can be incomplete, and the answer may correctly cite beyond them).
    # Render the human marker HERE, so the empty case stays falsy for code that
    # has to decide whether this row is scorable at all (see the note on
    # `_answer_grounding_block`).
    gold_text = _answer_grounding_block(r) or "  (none)"
    return (
        "You are an independent EU AI Act legal examiner. Judge the ANSWER's "
        "correctness STRICTLY against the verbatim Regulation text below — do "
        "NOT rely on outside memory or on any label; the verbatim text is the "
        "ground truth. If a claim cannot be verified against this independently "
        "supplied text, mark it unsupported.\n\n"
        f"QUESTION: {r['question'][:600]}\n\n"
        "VERBATIM EU AI ACT TEXT (the provisions relevant to this question):\n"
        f"{gold_text}\n\n"
        f"PREDICTED ANSWER: {r['answer'][:_ANSWER_TEXT_CAP]}\n\n"
        "Decompose the answer into atomic legal assertions (Legal Data Points). "
        "Using ONLY the independently supplied verbatim text above, tag each "
        "LDP: correct | incorrect | unsupported. Separately "
        "count MISSING — operative holdings the verbatim text establishes that "
        "the question demands but the answer omits (e.g. it asks 'prohibited or "
        "high-risk?' and the answer never states the prohibition that the text "
        "shows applies). Verdict 'pass' iff there are ZERO incorrect LDPs AND "
        "ZERO UNSUPPORTED LDPs AND zero MISSING operative holdings.\n\n"
        "Respond with ONE JSON object only (no prose, no fences):\n"
        '{"verdict":"pass"|"fail","correct":N,"incorrect":N,"unsupported":N,'
        '"missing":N,"failure_mode":"<one short phrase>"}'
    )


def render_reference_correctness(r: dict[str, Any]) -> str:
    pred_text = _provision_block(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
    supplied = str(r.get("independent_gold_context") or "").strip()
    gold_text = supplied or _provision_block(
        r["gold_refs"], _GOLD_TEXT_CAP, _MAX_GOLD_REFS
    )
    recall_available = _has_reference_gold_grounding(r)
    recall_instruction = (
        "Assess MISSING provisions and recall against the independent gold context."
        if recall_available
        else (
            "NO INDEPENDENT GOLD CONTEXT WAS SUPPLIED. Do not use memory to invent "
            "missing provisions: set missing=0, missing_refs=[], recall=null, and "
            "base verdict only on whether predicted citations are wrong."
        )
    )
    return (
        "You are an independent EU AI Act citation examiner. Judge whether the "
        "PREDICTED CITATIONS are the correct, MINIMAL set of provisions for this "
        "question, STRICTLY against the verbatim text below. Score against the "
        "REGULATION, not the gold list — the gold list can be incomplete, so a "
        "predicted citation the gold omits is still CORRECT if the verbatim text "
        "shows it governs the question, and a predicted citation the gold "
        "includes is still WRONG if the text shows it does not apply.\n\n"
        f"QUESTION: {r['question'][:500]}\n\n"
        f"PREDICTED CITATIONS: {r['pred_refs']}\n"
        "VERBATIM TEXT OF PREDICTED CITATIONS:\n"
        f"{pred_text}\n\n"
        f"GOLD CITATIONS (a reference set, may be incomplete): {r['gold_refs']}\n"
        "VERBATIM TEXT OF GOLD CITATIONS:\n"
        f"{gold_text}\n\n"
        f"RECALL AVAILABILITY: {recall_instruction}\n\n"
        "Classify each PREDICTED citation as CORRECT (genuinely governs this "
        "question per the text) or WRONG (irrelevant / over-cited). Then count "
        "MISSING — provisions the text shows govern this question that are NOT "
        "among the predicted citations. Report precision = correct / predicted "
        "and recall = correct_governing / (correct_governing + missing). Verdict "
        "'pass' iff there are ZERO WRONG citations AND zero MISSING load-bearing "
        "provisions.\n\n"
        "R302 — you MUST also NAME them: list in `wrong_refs` the exact predicted "
        "citation strings you classified WRONG (verbatim, as they appear in "
        "PREDICTED CITATIONS above), and in `missing_refs` the provisions that "
        "govern but were not cited. `wrong_refs` must have exactly `wrong` "
        "entries and `missing_refs` exactly `missing` entries; use [] for none. "
        "Counts alone cannot be acted on — without the names no precision fix can "
        "be targeted at the provisions actually responsible.\n\n"
        "Respond with ONE JSON object only:\n"
        '{"verdict":"pass"|"fail","n_predicted":N,"correct":N,"wrong":N,'
        '"missing":N,"precision":0.0,"recall":0.0|null,"wrong_refs":["..."],'
        '"missing_refs":["..."],"failure_mode":"<one short phrase>"}'
    )


def render_citation_faithfulness(r: dict[str, Any]) -> str:
    pred_text = _provision_block(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
    return (
        "You are checking CITATION FAITHFULNESS against the verbatim Regulation "
        "text. For each cited provision, decide whether the answer's prose "
        "accurately describes what that provision actually says (per its "
        "verbatim text). A cite-and-mismatch — citing Article X while describing "
        "the content of a different provision — is a fail even if the article "
        "number happens to be right.\n\n"
        f"QUESTION: {r['question'][:400]}\n\n"
        f"PREDICTED ANSWER: {r['answer'][:_ANSWER_TEXT_CAP]}\n\n"
        "VERBATIM TEXT OF EACH CITED PROVISION:\n"
        f"{pred_text}\n\n"
        "Verdict 'pass' iff EVERY cited provision is faithfully described by the "
        "answer (no cite-and-mismatch, no cited provision the prose ignores).\n\n"
        "Respond with ONE JSON object only:\n"
        '{"verdict":"pass"|"fail","faithful":N,"mismatched":N,'
        '"failure_mode":"<one short phrase>"}'
    )


def _render(axis: str, r: dict[str, Any]) -> str:
    if axis == "answer_correctness":
        return render_answer_correctness(r)
    if axis == "reference_correctness":
        return render_reference_correctness(r)
    if axis == "citation_faithfulness":
        return render_citation_faithfulness(r)
    raise ValueError(axis)


# ── per-row + run ───────────────────────────────────────────────────────


def _judge_row(r: dict[str, Any], caller: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    if not r["answer"]:
        verdicts = {
            axis: {
                "verdict": "fail",
                "evaluation_error": "empty_answer",
                "failure_mode": "empty answer",
            }
            for axis in GROUNDED_AXES
        }
        return {"id": r["id"], "category": r["category"], "verdicts": verdicts}
    verdicts: dict[str, Any] = {}
    for axis in GROUNDED_AXES:
        if (
            axis == "answer_correctness"
            and not _has_independent_answer_grounding(r)
            and (_strict_independent_grounding_required() or not r.get("pred_refs"))
        ):
            verdicts[axis] = {
                "judge_error": "no_independent_gold_context",
                "grounding_status": "unscorable",
            }
            continue
        result, attempts, retried = _call_judge_with_retry(caller, _render(axis, r))
        if retried:
            result = dict(result); result["_attempts"] = attempts
        if axis == "answer_correctness" and not result.get("judge_error"):
            result = dict(result)
            hard = sum(_num(result.get(f)) for f in ("incorrect", "missing"))
            unsupported = _num(result.get("unsupported"))
            result["verdict_unsupported_strict"] = (
                "fail" if hard or unsupported else "pass"
            )
            result["verdict_hard_only"] = "fail" if hard else "pass"
            if _unsupported_fails_enabled():
                result["verdict"] = result["verdict_unsupported_strict"]
                result["unsupported_enforced"] = True
            else:
                result["verdict"] = result["verdict_hard_only"]
                result["unsupported_enforced"] = False
            result["answer_grounding_source"] = _answer_grounding_source(r)
        if axis == "reference_correctness":
            result = dict(result)
            result["recall_available"] = _has_reference_gold_grounding(r)
            result["recall_provenance"] = (
                "independent_gold_context"
                if result["recall_available"]
                else "unavailable_no_independent_gold"
            )
            if not result["recall_available"] and not result.get("judge_error"):
                result["missing"] = 0
                result["missing_refs"] = []
                result["recall"] = None
                result["verdict"] = (
                    "fail" if _num(result.get("wrong")) > 0 else "pass"
                )
        verdicts[axis] = result
    return {"id": r["id"], "category": r["category"], "verdicts": verdicts}


def _load_rows(sidecar: Path) -> list[dict[str, Any]]:
    text = sidecar.read_text(encoding="utf-8")
    if sidecar.suffix == ".jsonl":
        return [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    payload = json.loads(text)
    rows: list[dict[str, Any]] = []
    for k in ("rows", "qa", "scenarios", "tricky", "multiturn", "ground_truth"):
        b = payload.get(k)
        if isinstance(b, dict):
            rows.extend(b.get("rows") or [])
        elif isinstance(b, list):
            rows.extend(b)
    return rows or (payload if isinstance(payload, list) else [])


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _aggregate(judged: list[dict[str, Any]]) -> dict[str, Any]:
    agg: dict[str, Any] = {}
    for axis in GROUNDED_AXES:
        n = len(judged); p = f = e = 0
        prec: list[float] = []; rec: list[float] = []; fact: list[float] = []
        modes: dict[str, int] = {}
        # R302 — tally which PROVISIONS the judge actually called wrong/missing.
        # The axis was previously counts-only, so a precision fix could not be
        # aimed at anything; a rank/position-based guess is exactly the R142.1
        # clamp that lost a live pairwise 11-0 by dropping gold.
        wrong_refs: dict[str, int] = {}; missing_refs: dict[str, int] = {}
        for row in judged:
            v = (row.get("verdicts") or {}).get(axis) or {}
            if v.get("judge_error"):
                e += 1; continue
            verd = str(v.get("verdict") or "").lower()
            if verd == "pass":
                p += 1
            elif verd == "fail":
                f += 1
                m = str(v.get("failure_mode") or "(unspecified)")[:80]
                modes[m] = modes.get(m, 0) + 1
            else:
                e += 1
            if axis == "reference_correctness":
                # prefer model-reported precision/recall; else derive from counts
                c, w, ms = _num(v.get("correct")), _num(v.get("wrong")), _num(v.get("missing"))
                pr = _num(v.get("precision")) or (c / (c + w) if (c + w) else 0.0)
                prec.append(pr)
                if v.get("recall_available", True):
                    rc = _num(v.get("recall")) or (c / (c + ms) if (c + ms) else 0.0)
                    rec.append(rc)
                for ref in (v.get("wrong_refs") or []):
                    key = str(ref).strip()
                    if key:
                        wrong_refs[key] = wrong_refs.get(key, 0) + 1
                for ref in (v.get("missing_refs") or []):
                    key = str(ref).strip()
                    if key:
                        missing_refs[key] = missing_refs.get(key, 0) + 1
            if axis == "answer_correctness":
                c = _num(v.get("correct"))
                i = _num(v.get("incorrect"))
                u = _num(v.get("unsupported"))
                m2 = _num(v.get("missing"))
                tot = c + i + u + m2
                fact.append(c / tot if tot else 0.0)
        entry = {
            "n": n, "pass": p, "fail": f, "error": e,
            "pass_rate": round(p / n, 4) if n else 0.0,
            "pass_rate_over_non_error": round(p / (p + f), 4) if (p + f) else 0.0,
            "top_failure_modes": sorted(modes.items(), key=lambda kv: -kv[1])[:8],
        }
        if prec:
            entry["mean_precision"] = round(sum(prec) / len(prec), 4)
            if rec:
                entry["mean_recall"] = round(sum(rec) / len(rec), 4)
                entry["recall_n"] = len(rec)
                pm, rm = entry["mean_precision"], entry["mean_recall"]
                entry["mean_f1"] = round(2 * pm * rm / (pm + rm), 4) if (pm + rm) else 0.0
            else:
                entry["mean_recall"] = None
                entry["recall_n"] = 0
        if wrong_refs:
            entry["top_wrong_refs"] = sorted(wrong_refs.items(), key=lambda kv: -kv[1])[:15]
        if missing_refs:
            entry["top_missing_refs"] = sorted(missing_refs.items(), key=lambda kv: -kv[1])[:15]
        if fact:
            entry["mean_factual_score"] = round(sum(fact) / len(fact), 4)
        agg[axis] = entry
    return agg


def run(*, sidecar: Path, label: str, model: str, provider: str,
        timeout_s: float, concurrency: int, limit: int | None,
        out_dir: Path | None = None) -> dict[str, Any]:
    set_judge_model(model)
    caller = _resolve_caller(provider, timeout_s)
    all_rows = [_norm(r) for r in _load_rows(sidecar)]
    if limit:
        all_rows = all_rows[:limit]
    rows = all_rows
    n_error_rows = sum(1 for r in rows if not r["answer"])
    print(f"[grounded] {len(rows)} rows × {len(GROUNDED_AXES)} axes  model={model} "
          f"provider={provider} concurrency={concurrency}", flush=True)

    # R292 — gold coverage banner.
    #
    # `_norm` reads gold_refs/expected_refs. The OFFICIAL regenold batch has no
    # gold at all (regenold never published theirs), and `run_official_batch`
    # writes `jul07_refs` — which is OUR OWN prior output, NOT gold. Mapping it
    # into `gold_refs` would make the judge grade "did we match our past self",
    # which is circular, so we deliberately do NOT. Instead the gap is stamped
    # on every scorecard: without independent gold, recall is unavailable;
    # precision remains text-grounded against each predicted provision.
    n_gold = sum(
        1 for r in rows
        if _has_reference_gold_grounding(r)
    )
    gold_coverage = (n_gold / len(rows)) if rows else 0.0
    if gold_coverage < 0.5:
        print(
            f"[grounded] independent gold coverage {n_gold}/{len(rows)} "
            f"({gold_coverage:.0%}); reference recall is unavailable on rows "
            "without independent gold and is never inferred from model memory.",
            flush=True,
        )
    if n_error_rows:
        print(
            f"[grounded] {n_error_rows} row(s) had no answer; they remain in "
            "every denominator as deterministic failures.",
            flush=True,
        )
    out: list[dict[str, Any] | None] = [None] * len(rows)
    done = 0
    lock = threading.Lock()
    t0 = time.monotonic()

    def _w(i: int, r: dict[str, Any]):
        return i, _judge_row(r, caller)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futs = [pool.submit(_w, i, r) for i, r in enumerate(rows)]
        for fut in as_completed(futs):
            i, jr = fut.result()
            out[i] = jr
            with lock:
                done += 1
                vs = {a: (jr["verdicts"].get(a) or {}).get("verdict", "?") for a in GROUNDED_AXES}
                print(f"  [{done}/{len(rows)}] {str(jr['id'])[:34]:<34} "
                      f"ans={vs['answer_correctness']} ref={vs['reference_correctness']} "
                      f"cite={vs['citation_faithfulness']}", flush=True)
    judged = [r for r in out if r is not None]
    agg = _aggregate(judged)
    summary = {
        "label": label, "source_sidecar": str(sidecar), "judge_model": model,
        "provider": provider, "elapsed_s": round(time.monotonic() - t0, 1),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "axes": list(GROUNDED_AXES), "rows": judged, "aggregate": agg,
        # R292 — provenance of the measurement itself, so a scorecard can be
        # read correctly months later without re-deriving these caveats.
        "gold_coverage": round(gold_coverage, 4),
        "gold_rows": n_gold,
        "input_rows": len(rows),
        "empty_answer_rows": n_error_rows,
        "excluded_error_rows": 0,
        "denominator_policy": "all input rows; empty answers fail; judge errors remain errors",
        "recall_is_text_grounded": n_gold == len(rows) and bool(rows),
    }
    out_dir = out_dir or Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"grounded-{label}.json"
    dest.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[grounded] sidecar -> {dest}", flush=True)
    return summary


def _fmt(s: dict[str, Any]) -> str:
    out = ["=" * 74, f"GROUNDED JUDGE — {s['label']!r}  model={s['judge_model']}",
           f"source: {Path(s['source_sidecar']).name}  elapsed={s['elapsed_s']}s", "=" * 74]
    for axis in s["axes"]:
        a = s["aggregate"][axis]
        line = (f"[{axis}] n={a['n']} pass={a['pass']} fail={a['fail']} err={a['error']} "
                f"pass_rate={a['pass_rate']} (over_non_err={a['pass_rate_over_non_error']})")
        out.append("\n" + line)
        if "mean_precision" in a:
            out.append(f"   precision={a['mean_precision']} recall={a['mean_recall']} f1={a['mean_f1']}")
        if "mean_factual_score" in a:
            out.append(f"   mean_factual_score={a['mean_factual_score']}")
        for mode, c in (a.get("top_failure_modes") or [])[:5]:
            out.append(f"     {c:>3}x {mode}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        if hasattr(st, "reconfigure"):
            try:
                st.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sidecar", required=True, type=Path)
    p.add_argument("--label", required=True)
    p.add_argument("--model", default=_DEFAULT_MODEL)
    p.add_argument("--provider", choices=("wrapper", "anthropic", "groq", "gemini", "bedrock"), default="wrapper")
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument(
        "--allow-judge-errors",
        action="store_true",
        help="R381 — accept a run in which SOME rows errored. Without this a "
             "partial judge failure exits 3, because pass_rate counts an "
             "errored row as a failed row.",
    )
    a = p.parse_args(argv)
    s = run(sidecar=a.sidecar, label=a.label, model=a.model, provider=a.provider,
            timeout_s=a.timeout, concurrency=a.concurrency, limit=a.limit)
    print(_fmt(s))

    # R361 — a judge that never ran must NOT exit 0 with a scorecard.
    # Measured 2026-08-23: the default model resolved to
    # ``eu.anthropic.claude-sonnet-5``, which returns api_access_denied_403 on
    # the current key vintage. Every row errored, yet the process exited 0 and
    # wrote ``pass_rate: 0.0000`` on all three axes — which reads as a total
    # QUALITY COLLAPSE, not a dead judge. That is the same failure shape R360.2
    # fixed one layer up in ab_judge (a silent downgrade that still prints a
    # scorecard), so it gets the same treatment: fail loudly.
    agg = s.get("aggregate", {}) if isinstance(s, dict) else {}
    dead = [
        ax for ax, v in agg.items()
        if isinstance(v, dict) and v.get("n") and v.get("error") == v.get("n")
    ]
    if dead:
        print(
            f"[grounded] !! JUDGE DID NOT RUN — every row errored on: "
            f"{', '.join(sorted(dead))}. The printed pass_rate values are "
            f"ARTEFACTS OF FAILURE, not scores. Check the model id "
            f"({a.model!r} via {a.provider!r}); newer Claude pins return "
            f"AccessDenied on some key vintages — claude-sonnet-4-6 is known "
            f"good on Bedrock.",
            file=sys.stderr, flush=True,
        )
        return 2

    # R381 — the R361 guard above only catches TOTAL failure (error == n). A
    # PARTIAL failure still exits 0 and silently deflates the headline number,
    # because ``pass_rate`` (:322) divides passes by ALL rows and an errored row
    # is counted as a non-pass. Measured with 50% of calls forced to the same
    # 403: pass_rate fell to 0.25 on two axes and 0.0 on the third, ``dead`` was
    # empty, and main() returned 0 — a throttled window or a half-revoked key
    # reads as a quality collapse. 403 is not retryable
    # (``is_retryable_judge_error`` -> False), so the retry loop cannot save it.
    # ``pass_rate_over_non_error`` (:323) is the honest number and is written to
    # the sidecar; the gate is on the ERROR FRACTION, not on it.
    partial = sorted(
        f"{ax} {v.get('error')}/{v.get('n')}"
        for ax, v in agg.items()
        if isinstance(v, dict) and v.get("n") and v.get("error")
    )
    if partial and not a.allow_judge_errors:
        print(
            f"[grounded] !! PARTIAL JUDGE FAILURE on: {', '.join(partial)}. The "
            f"printed pass_rate DIVIDES BY ALL ROWS, so each errored row reads as "
            f"a failed row — the scorecard understates quality by exactly the "
            f"error rate. Read pass_rate_over_non_error, fix the transport, or "
            f"pass --allow-judge-errors to accept a partial run deliberately.",
            file=sys.stderr, flush=True,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

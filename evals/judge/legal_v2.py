"""R305 — LEGAL-V2: an upgraded, deliberately-unbiased, critical EU-AI-Act
LLM-as-Judge.

Builds on ``evals.judge.grounded`` (verbatim-text grounding against
``app.data.provision_text``) and fixes a measured false-positive class in
that judge: it treats any predicted citation that is not THE single
"governing" provision as WRONG, so an answer that correctly cites a
legitimately-adjacent provision (e.g. Article 14/15 alongside Article 13 on
an explainability question — all three are genuinely part of the Act's
explainability-adjacent duty set) gets penalised for over-citation it did
not commit. CLAUDE.md separately records that ~86% of judge-flagged "wrong"
refs are already accurately described in the prose — i.e. the old binary
scheme conflates three genuinely different things.

Axes (exactly 4)
----------------
1. ``answer_correctness``      — Chain-of-Verification (CoVe): decompose
   the answer into legal propositions, verify each against verbatim text,
   THEN emit a verdict + graded factual score. Separately reports
   ``omission_present`` (a required sub-part went unanswered) vs
   ``fabrication_present`` (an assertion the text contradicts) — these have
   different root causes and different fixes.
2. ``reference_correctness``   — THREE-WAY reference classification, not
   binary:
     * GOVERNING  — directly answers the question; omitting it is an error.
     * SUPPORTING — legally applicable and accurately used, but not
       necessary to answer. This is **NEVER** a failure condition on its
       own.
     * WRONG      — legally inapplicable to the question, or the prose
       misstates it.
   ``focus_precision`` = GOVERNING / total (how tightly focused the
   citation set is). ``legal_soundness_precision`` = (GOVERNING +
   SUPPORTING) / total (how much of the citation set is at least legally
   sound). ``recall`` = GOVERNING / (GOVERNING + MISSING governing
   provisions). The headline pass/fail keys ONLY on: zero WRONG refs AND
   zero MISSING governing refs.
3. ``citation_faithfulness``   — does the prose accurately describe each
   cited provision (the cite-and-mismatch check)?
4. ``answer_conciseness``      — NEW. Answer-Conciseness is the only
   Regenold rubric axis this system currently leads (per CLAUDE.md), i.e.
   the one axis with pure downside risk. Flags REDUNDANT sentences (repeat
   an earlier point) and UNREQUESTED-TOPIC sentences (address something the
   question did not ask about). Never rewards omission — completeness is
   scored on axis 1, not here.

Quote-or-retract forcing function (anti-hallucination)
--------------------------------------------------------
Every WRONG / MISSING-governing / CONTRADICTED / MISMATCHED verdict the
model returns is REQUIRED to carry a verbatim quote (>= 8 words) copied
from the supplied provision text. Post-processing then checks that the
quote is actually a literal substring of the text we handed the model
(whitespace/case normalised before comparison, see :func:`_quote_substantiated`).
If the quote is missing, too short, or is not a literal match:

  * a WRONG classification is downgraded to SUPPORTING,
  * a MISSING-governing claim is dropped entirely,
  * a CONTRADICTED proposition is downgraded to NOT-ADDRESSED,
  * a MISMATCHED citation is downgraded to FAITHFUL.

Every downgrade is logged in the per-sample ``unsubstantiated_verdicts``
list, and the run-level scorecard reports an aggregate ``substantiation
rate`` — the fraction of "this is wrong" claims the model could actually
back with a real quote. This kills judge hallucination as the mechanism,
not the outcome.

Self-consistency (variance control)
------------------------------------
``--samples K`` (default 1; recommended 3) repeats each axis call K times
at the SAME prompt/temperature and takes the MAJORITY verdict on the
binary pass/fail field (2-way ties resolve to "fail" — anti-leniency: an
uncertain call must not default to a pass) and the MEDIAN on every graded
numeric field. Each row records ``_agreement`` (fraction of non-error
samples agreeing with the majority); the run-level scorecard aggregates
this into ``mean_judge_agreement`` per axis so a reader can tell signal
from judge noise. K=1 costs nothing extra; cost scales K× for K>1.

Bias controls
-------------
The judge is NEVER shown: which system produced the answer, any arm/label,
any prior score, or a prior baseline answer. This is enforced structurally,
not by convention: every render function is built from :func:`_norm`'s
strict allowlist (``id, category, question, answer, pred_refs, gold_refs``)
— any other key on the input row (``arm``, ``label``, ``july07_answer``,
``system``, a prior ``score``, ...) is simply never read.

Anti-sycophancy / anti-leniency
--------------------------------
Every prompt opens with an explicit instruction that a fluent, confident,
well-formatted answer earns NO credit; the ONLY evidence is the supplied
verbatim text; and "plausible but unquotable" must be scored as
unsupported. Each axis carries two short calibration examples (one pass,
one fail) grounded in facts verified against
``app.data.provision_text.get_provision_text`` (Article 5(1)(f) emotion-
recognition workplace prohibition + medical/safety carve-out; Article 9
risk-management-system duty; Article 48 CE marking; Article 99(3)
prohibited-practice fines) — not invented regulation text.

CLI
---
    python -m evals.judge.legal_v2 \\
        --sidecar evals/bench/results/easyhard-r284-B.ckpt.jsonl \\
        --label r305-legalv2 --model claude-sonnet-5 \\
        --provider wrapper --timeout 120 --concurrency 2 --samples 1

Writes ``evals/bench/results/legalv2-<label>.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# R305 — do NOT call ``load_dotenv()`` at import time.
#
# ``grounded.py`` and ``runner.py`` do, which is harmless while only eval
# CLIs import them. This module is imported by ``tests/test_legal_v2_judge.py``,
# which runs EARLY in the alphabetical suite order, so an import-time
# ``load_dotenv()`` injects the developer ``.env`` (``OPENAI_API_KEY``,
# ``GROQ_API_KEY``, ...) into the process and flips the provider gates for
# every test that runs afterwards. Measured: 8 downstream failures across
# ``test_topic_filter`` / ``test_r87a_query_denoiser_trace`` that pass in
# isolation. Load it in ``main()`` instead — the CLI is the only caller that
# needs it, and a library module must not mutate process env on import.
from evals.judge.runner import (  # reuse the battle-tested call plumbing
    _call_judge_with_retry,
    _resolve_caller,
    set_judge_model,
)
from evals.judge.grounded import (  # reuse the sidecar-loading + row-norm plumbing
    _GOLD_TEXT_CAP,
    _MAX_GOLD_REFS,
    _MAX_PRED_REFS,
    _PRED_TEXT_CAP,
    _load_rows,
    _norm,
    _num,
)

_DEFAULT_MODEL = "claude-sonnet-5"

AXES: tuple[str, ...] = (
    "answer_correctness",
    "reference_correctness",
    "citation_faithfulness",
    "answer_conciseness",
)


# ── quote-or-retract grounding forcing function ─────────────────────────


def _normalise_ws(s: str) -> str:
    return " ".join(str(s or "").split()).lower()


def _quote_substantiated(quote: str, *text_blocks: str, min_words: int = 8) -> bool:
    """True iff ``quote`` is a real, sufficiently-long, literal excerpt of
    at least one of ``text_blocks`` (whitespace/case normalised).

    This is the anti-hallucination gate (R305 requirement 2): a judge
    verdict that asserts something is WRONG / MISSING / CONTRADICTED /
    MISMATCHED must be backed by an actual quote from the text it was
    shown, not a paraphrase or an invented excerpt.
    """
    q = str(quote or "").strip()
    if not q or len(q.split()) < min_words:
        return False
    nq = _normalise_ws(q)
    if not nq:
        return False
    for block in text_blocks:
        if nq in _normalise_ws(block):
            return True
    return False


# ── provision-text grounding (per-ref map, for substantiation checks) ───


def _resolve_provision_texts(refs: list[str], cap: int, max_refs: int) -> dict[str, str]:
    """Resolve each ref to its verbatim EU AI Act text (article-level
    fallback). Unlike ``grounded._provision_block`` this returns a
    ``ref -> text`` MAP so post-processing can substantiate a quote
    against the exact provision it was claimed against."""
    from app.data.provision_text import get_provision_text  # local heavy import

    out: dict[str, str] = {}
    seen: set[str] = set()
    for r in refs[:max_refs]:
        key = str(r).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        txt = get_provision_text(key)
        if txt is None:
            base = key.split(".")[0].split("(")[0].strip()
            if base and base != key:
                txt = get_provision_text(base)
        out[key] = (txt or "").strip()[:cap]
    return out


def _block_from_map(text_map: dict[str, str]) -> str:
    if not text_map:
        return "  (none)"
    lines = []
    for k, v in text_map.items():
        if v:
            lines.append(f"[{k}] {v}")
        else:
            lines.append(f"[{k}] (no verbatim text resolved — likely not a real provision)")
    return "\n".join(lines)


# ── anti-sycophancy header + per-axis calibration (verified facts) ──────

_ANTI_SYCOPHANCY = (
    "You are a CRITICAL, unbiased EU AI Act legal examiner. A fluent, "
    "confident, well-formatted answer earns NO credit on its own — your "
    "ONLY evidence is the verbatim Regulation text supplied below. Anything "
    "plausible-sounding but unquotable from that text must be scored as "
    "unsupported. Do not defer to the answer's tone or confidence, and do "
    "not assume it is correct because it sounds authoritative. You are "
    "never told which system produced this answer, its arm/label, or any "
    "prior score — score it purely on its merits against the text.\n\n"
)

# Facts verified against app.data.provision_text.get_provision_text before
# being written here (never invented): Article 5(1)(f) prohibits emotion
# recognition in the workplace/education except for medical or safety
# reasons; Article 9 requires a risk management system; Article 48 governs
# CE marking; Article 99(3) sets the prohibited-practice fine ceiling.

_CALIBRATION_ANSWER = (
    "CALIBRATION (for your own reference only — do not repeat this):\n"
    "  PASS — Q: 'Is emotion-recognition AI prohibited in the workplace?' "
    "A: 'Emotion-recognition AI systems are prohibited in the workplace and "
    "in educational institutions, except where placed on the market "
    "strictly for medical or safety reasons (Article 5(1)(f)).' Every "
    "proposition is SUPPORTED by Article 5(1)(f) and the applicable tier "
    "is stated -> pass.\n"
    "  FAIL — same question, A: 'Emotion-recognition AI systems are "
    "entirely permitted in workplaces without restriction.' Directly "
    "CONTRADICTED by Article 5(1)(f) -> fail (fabrication).\n\n"
)

_CALIBRATION_REFS = (
    "CALIBRATION:\n"
    "  PASS — Q: 'What must a provider of a high-risk AI system establish "
    "to manage risk?' predicted citation Article 9 (risk management "
    "system) -> GOVERNING, the sole citation is correct -> pass.\n"
    "  FAIL — same question, predicted citations [Article 9, Article 99] — "
    "Article 99 sets administrative fines and has no bearing on what a "
    "provider must ESTABLISH -> Article 99 is WRONG -> fail.\n\n"
)

_CALIBRATION_CITE = (
    "CALIBRATION:\n"
    "  PASS — cites Article 9 and the prose says providers must establish, "
    "implement, document and maintain a risk management system — matches "
    "Article 9's actual text -> FAITHFUL -> pass.\n"
    "  FAIL — cites Article 9 but the prose describes CE-marking "
    "affixation instead (Article 48's content, not Article 9's) -> "
    "MISMATCHED -> fail.\n\n"
)

_CALIBRATION_CONCISE = (
    "CALIBRATION:\n"
    "  PASS — three tight sentences, each carrying a distinct load-bearing "
    "point, no repeated verdict, no unrelated topic -> pass.\n"
    "  FAIL — six sentences, two of which just restate the same verdict in "
    "different words ('As noted above, this practice is prohibited...'), "
    "plus one sentence on unrelated GDPR consent mechanics the question "
    "never asked about -> fail.\n\n"
)


# ── prompt renderers (one per axis) ──────────────────────────────────────


def render_answer_correctness(r: dict[str, Any], union_map: dict[str, str]) -> str:
    """CoVe: decompose -> verify each proposition against verbatim text ->
    only then emit pass/fail + a graded factual score. Distinguishes
    OMISSION (a required sub-part is unanswered) from FABRICATION (an
    assertion the text contradicts) — CLAUDE.md records these have
    different root causes and different fixes."""
    union_block = _block_from_map(union_map)
    return (
        _ANTI_SYCOPHANCY + _CALIBRATION_ANSWER +
        f"QUESTION: {r['question'][:600]}\n\n"
        "VERBATIM EU AI ACT TEXT (the provisions relevant to this question):\n"
        f"{union_block}\n\n"
        f"PREDICTED ANSWER: {r['answer'][:1400]}\n\n"
        "STEP 1 — decompose the PREDICTED ANSWER into discrete legal "
        "propositions (one assertion each).\n"
        "STEP 2 — for EACH proposition, using ONLY the verbatim text above "
        "plus well-established AI Act structure, mark it SUPPORTED, "
        "CONTRADICTED, or NOT-ADDRESSED (the text neither confirms nor "
        "denies it). For every CONTRADICTED proposition you MUST quote >=8 "
        "consecutive verbatim words from the text above that contradict "
        "it. If you cannot produce such a quote, mark it NOT-ADDRESSED "
        "instead — never guess a contradiction.\n"
        "STEP 3 — separately decide whether the answer OMITS an operative "
        "holding that the question demands and the verbatim text "
        "establishes (e.g. it asks 'prohibited or high-risk?' and the "
        "answer never states the tier the text shows applies).\n\n"
        "Respond with ONE JSON object only (no prose, no markdown fences):\n"
        '{"propositions":[{"text":"...","status":"SUPPORTED"|"CONTRADICTED"|'
        '"NOT-ADDRESSED","quote":"..."}],"omission_present":true|false,'
        '"omission_detail":"...","failure_mode":"<one short phrase>"}'
    )


def render_reference_correctness(
    r: dict[str, Any], pred_map: dict[str, str], gold_map: dict[str, str],
) -> str:
    """Three-way classification: GOVERNING / SUPPORTING / WRONG (+ MISSING
    governing provisions). SUPPORTING can never fail the axis — only WRONG
    and MISSING can. Every WRONG/MISSING verdict requires a verbatim quote
    (enforced in post-processing, not trusted from the model)."""
    pred_block = _block_from_map(pred_map)
    gold_block = _block_from_map(gold_map)
    return (
        _ANTI_SYCOPHANCY + _CALIBRATION_REFS +
        f"QUESTION: {r['question'][:500]}\n\n"
        f"PREDICTED CITATIONS: {r['pred_refs']}\n"
        "VERBATIM TEXT OF PREDICTED CITATIONS:\n"
        f"{pred_block}\n\n"
        f"GOLD CITATIONS (reference set, may be incomplete): {r['gold_refs']}\n"
        "VERBATIM TEXT OF GOLD CITATIONS (candidate governing provisions if "
        "the predicted set is missing something):\n"
        f"{gold_block}\n\n"
        "Classify EVERY predicted citation into exactly one class:\n"
        "  GOVERNING  — directly answers the question; omitting it would "
        "be an error.\n"
        "  SUPPORTING — legally applicable and accurately used, but not "
        "necessary to answer. This is NOT an error.\n"
        "  WRONG      — legally inapplicable to the question, or the "
        "answer's prose misstates what it says.\n"
        "For every WRONG classification you MUST quote >=8 consecutive "
        "verbatim words from that provision's text above proving it is "
        "wrong for THIS question. If you cannot, classify it SUPPORTING "
        "instead — never guess.\n\n"
        "Then list MISSING governing provisions: provisions whose "
        "verbatim text above (gold block) shows they govern this question "
        "but are absent from PREDICTED CITATIONS. For each, quote >=8 "
        "verbatim words proving it governs. If you cannot quote from the "
        "text supplied above, do not report it.\n\n"
        "Respond with ONE JSON object only:\n"
        '{"classifications":[{"ref":"...","class":"GOVERNING"|"SUPPORTING"|'
        '"WRONG","quote":"..."}],"missing_governing":[{"ref":"...",'
        '"quote":"..."}],"failure_mode":"<one short phrase>"}'
    )


def render_citation_faithfulness(r: dict[str, Any], pred_map: dict[str, str]) -> str:
    """Cite-and-mismatch check: does the prose accurately describe each
    cited provision? A MISMATCHED verdict requires a verbatim quote of
    what the provision actually says (enforced in post-processing)."""
    pred_block = _block_from_map(pred_map)
    return (
        _ANTI_SYCOPHANCY + _CALIBRATION_CITE +
        f"QUESTION: {r['question'][:400]}\n\n"
        f"PREDICTED ANSWER: {r['answer'][:1200]}\n\n"
        "VERBATIM TEXT OF EACH CITED PROVISION:\n"
        f"{pred_block}\n\n"
        "For EACH cited provision, decide whether the answer's prose "
        "accurately describes what that provision's verbatim text "
        "actually says. A cite-and-mismatch (citing Article X while "
        "describing different content) is MISMATCHED even if the article "
        "number is technically right.\n"
        "For every MISMATCHED verdict you MUST quote >=8 consecutive "
        "verbatim words from that provision's text above showing what it "
        "actually says, in contradiction to the prose. If you cannot, "
        "classify it FAITHFUL instead.\n\n"
        "Respond with ONE JSON object only:\n"
        '{"citations":[{"ref":"...","status":"FAITHFUL"|"MISMATCHED",'
        '"quote":"..."}],"failure_mode":"<one short phrase>"}'
    )


def render_answer_conciseness(r: dict[str, Any]) -> str:
    """NEW axis (Answer-Conciseness is the only rubric axis this system
    leads per CLAUDE.md — pure downside risk). Judges only what is
    PRESENT for load-bearing relevance; never rewards omission (a missing
    required element fails answer_correctness, not this axis)."""
    return (
        _ANTI_SYCOPHANCY + _CALIBRATION_CONCISE +
        f"QUESTION: {r['question'][:500]}\n\n"
        f"PREDICTED ANSWER: {r['answer'][:1400]}\n\n"
        "Judge ONLY what is PRESENT in the answer for load-bearing "
        "relevance to the question asked. Do NOT judge completeness here "
        "— a missing required element is scored on a different axis, not "
        "this one; an answer that omits something is not thereby more "
        "concise.\n\n"
        "For EACH sentence, decide:\n"
        "  REDUNDANT — it repeats a point an earlier sentence already "
        "made in full (paraphrase-repetition, hedging filler, restating "
        "the verdict a second time).\n"
        "  UNREQUESTED TOPIC — it addresses a legal topic the question "
        "did not ask about and that is not necessary context for the "
        "answer.\n"
        "Quote each flagged sentence VERBATIM from the answer above.\n\n"
        "Respond with ONE JSON object only:\n"
        '{"sentence_count":N,"redundant_sentences":["..."],'
        '"unrequested_topics":["..."],"failure_mode":"<one short phrase>"}'
    )


# ── prepare (build prompt + grounding context) ───────────────────────────


def _prepare(axis: str, r: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if axis == "answer_correctness":
        union = list(dict.fromkeys([*r["gold_refs"], *r["pred_refs"]]))
        union_map = _resolve_provision_texts(union, _GOLD_TEXT_CAP, _MAX_GOLD_REFS + _MAX_PRED_REFS)
        return render_answer_correctness(r, union_map), {"union_map": union_map}
    if axis == "reference_correctness":
        pred_map = _resolve_provision_texts(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
        gold_map = _resolve_provision_texts(r["gold_refs"], _GOLD_TEXT_CAP, _MAX_GOLD_REFS)
        return render_reference_correctness(r, pred_map, gold_map), {
            "pred_map": pred_map, "gold_map": gold_map,
        }
    if axis == "citation_faithfulness":
        pred_map = _resolve_provision_texts(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
        return render_citation_faithfulness(r, pred_map), {"pred_map": pred_map}
    if axis == "answer_conciseness":
        return render_answer_conciseness(r), {}
    raise ValueError(f"unknown axis {axis!r}; valid: {AXES}")


# ── post-processing (quote-or-retract enforcement lives here) ───────────


def _postprocess_answer_correctness(raw: dict[str, Any], union_map: dict[str, str]) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    props = raw.get("propositions") or []
    union_pool = tuple(union_map.values())
    supported = contradicted = not_addressed = 0
    fabrications: list[dict[str, Any]] = []
    unsub: list[dict[str, Any]] = []
    for p in props:
        if not isinstance(p, dict):
            continue
        status = str(p.get("status") or "").strip().upper().replace(" ", "-")
        quote = p.get("quote") or ""
        text = str(p.get("text") or "")
        if status == "CONTRADICTED":
            if _quote_substantiated(quote, *union_pool):
                contradicted += 1
                fabrications.append({"text": text, "quote": quote})
            else:
                not_addressed += 1
                unsub.append({"claimed": "CONTRADICTED", "proposition": text, "quote": quote})
        elif status == "SUPPORTED":
            supported += 1
        else:
            not_addressed += 1
    omission_present = bool(raw.get("omission_present"))
    total = supported + contradicted
    factual_score = (supported / total) if total else (0.5 if not_addressed else 1.0)
    fabrication_present = contradicted > 0
    verdict = "pass" if (contradicted == 0 and not omission_present) else "fail"
    return {
        "verdict": verdict,
        "supported": supported, "contradicted": contradicted, "not_addressed": not_addressed,
        "omission_present": omission_present, "omission_detail": raw.get("omission_detail") or "",
        "fabrication_present": fabrication_present, "fabrications": fabrications,
        "factual_score": round(factual_score, 4),
        "unsubstantiated_verdicts": unsub,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess_reference_correctness(
    raw: dict[str, Any], pred_map: dict[str, str], gold_map: dict[str, str], pred_refs: list[str],
) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    classifications = raw.get("classifications") or []
    by_ref: dict[str, dict[str, Any]] = {}
    for c in classifications:
        if not isinstance(c, dict):
            continue
        ref = str(c.get("ref") or "").strip()
        if ref:
            by_ref[ref] = c

    governing: list[str] = []
    supporting: list[str] = []
    wrong: list[str] = []
    unsub: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in pred_refs:
        ref = str(ref).strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        c = by_ref.get(ref) or {}
        cls = str(c.get("class") or "").strip().upper()
        quote = c.get("quote") or ""
        if cls == "WRONG":
            if _quote_substantiated(quote, pred_map.get(ref, "")):
                wrong.append(ref)
            else:
                supporting.append(ref)  # downgrade — never trust an unquoted "wrong"
                unsub.append({"ref": ref, "claimed": "WRONG", "quote": quote})
        elif cls == "GOVERNING":
            governing.append(ref)
        elif cls == "SUPPORTING":
            supporting.append(ref)
        else:
            # Unclassified / malformed entry for a real predicted ref —
            # never silently drop it from the tally; treat conservatively
            # as SUPPORTING (never as WRONG on a format hiccup).
            supporting.append(ref)

    missing_raw = raw.get("missing_governing") or []
    missing: list[str] = []
    for m in missing_raw:
        if not isinstance(m, dict):
            continue
        ref = str(m.get("ref") or "").strip()
        quote = m.get("quote") or ""
        if not ref:
            continue
        if _quote_substantiated(quote, gold_map.get(ref, "")):
            missing.append(ref)
        else:
            unsub.append({"ref": ref, "claimed": "MISSING", "quote": quote})

    total = len(governing) + len(supporting) + len(wrong)
    focus_precision = (len(governing) / total) if total else 0.0
    legal_soundness_precision = ((len(governing) + len(supporting)) / total) if total else 0.0
    denom = len(governing) + len(missing)
    recall = (len(governing) / denom) if denom else 1.0
    verdict = "pass" if (len(wrong) == 0 and len(missing) == 0) else "fail"
    return {
        "verdict": verdict,
        "governing_refs": governing, "supporting_refs": supporting, "wrong_refs": wrong,
        "missing_governing_refs": missing,
        "n_predicted": total,
        "focus_precision": round(focus_precision, 4),
        "legal_soundness_precision": round(legal_soundness_precision, 4),
        "recall": round(recall, 4),
        "unsubstantiated_verdicts": unsub,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess_citation_faithfulness(
    raw: dict[str, Any], pred_map: dict[str, str], pred_refs: list[str],
) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    citations = raw.get("citations") or []
    by_ref: dict[str, dict[str, Any]] = {}
    for c in citations:
        if not isinstance(c, dict):
            continue
        ref = str(c.get("ref") or "").strip()
        if ref:
            by_ref[ref] = c

    faithful: list[str] = []
    mismatched: list[str] = []
    unsub: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in pred_refs:
        ref = str(ref).strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        c = by_ref.get(ref) or {}
        status = str(c.get("status") or "").strip().upper()
        quote = c.get("quote") or ""
        if status == "MISMATCHED":
            if _quote_substantiated(quote, pred_map.get(ref, "")):
                mismatched.append(ref)
            else:
                faithful.append(ref)
                unsub.append({"ref": ref, "claimed": "MISMATCHED", "quote": quote})
        else:
            faithful.append(ref)

    verdict = "pass" if not mismatched else "fail"
    return {
        "verdict": verdict,
        "faithful": len(faithful), "mismatched": len(mismatched),
        "faithful_refs": faithful, "mismatched_refs": mismatched,
        "unsubstantiated_verdicts": unsub,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess_answer_conciseness(raw: dict[str, Any], answer_text: str) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    raw_redundant = raw.get("redundant_sentences") or []
    redundant: list[str] = []
    unsub: list[dict[str, Any]] = []
    for s in raw_redundant:
        s = str(s or "")
        # Lower word-floor than the WRONG/MISSING gate — this is a
        # "did you actually quote a real sentence" substring check, not a
        # "prove this is wrong" evidentiary claim.
        if _quote_substantiated(s, answer_text, min_words=3):
            redundant.append(s)
        else:
            unsub.append({"claimed": "REDUNDANT", "quote": s})
    unrequested = [str(s) for s in (raw.get("unrequested_topics") or []) if str(s).strip()]
    verdict = "pass" if (not redundant and not unrequested) else "fail"
    return {
        "verdict": verdict,
        "sentence_count": raw.get("sentence_count"),
        "redundant_sentence_count": len(redundant), "redundant_sentences": redundant,
        "unrequested_topic_count": len(unrequested), "unrequested_topics": unrequested,
        "unsubstantiated_verdicts": unsub,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess(axis: str, raw: dict[str, Any], r: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    if axis == "answer_correctness":
        return _postprocess_answer_correctness(raw, ctx["union_map"])
    if axis == "reference_correctness":
        return _postprocess_reference_correctness(raw, ctx["pred_map"], ctx["gold_map"], r["pred_refs"])
    if axis == "citation_faithfulness":
        return _postprocess_citation_faithfulness(raw, ctx["pred_map"], r["pred_refs"])
    if axis == "answer_conciseness":
        return _postprocess_answer_conciseness(raw, r["answer"])
    raise ValueError(f"unknown axis {axis!r}; valid: {AXES}")


# ── self-consistency aggregation (majority verdict / median numerics) ───

_NUMERIC_FIELDS: dict[str, tuple[str, ...]] = {
    "answer_correctness": ("factual_score", "supported", "contradicted", "not_addressed"),
    "reference_correctness": ("focus_precision", "legal_soundness_precision", "recall", "n_predicted"),
    "citation_faithfulness": ("faithful", "mismatched"),
    "answer_conciseness": ("redundant_sentence_count", "unrequested_topic_count"),
}


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _aggregate_samples(samples: list[dict[str, Any]], axis: str) -> dict[str, Any]:
    """Merge K independent (already post-processed) sample verdicts into
    one: majority verdict (ties resolve to 'fail'), median on every
    graded numeric field, and an ``_agreement`` fraction. K=1 is the
    no-op case — the single sample passes through with ``_agreement=1.0``.
    """
    non_error = [s for s in samples if not s.get("judge_error")]
    if not non_error:
        merged = dict(samples[-1]) if samples else {}
        merged["judge_error"] = merged.get("judge_error") or "all_samples_failed"
        merged["_samples_n"] = len(samples)
        return merged

    verdicts = [s.get("verdict") for s in non_error]
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    best_n = max(counts.values())
    tied = [v for v, c in counts.items() if c == best_n]
    # Anti-leniency: an outright tie that includes "fail" resolves to
    # "fail" — an uncertain / split judge call must never default to a
    # pass. A tie that does NOT involve "fail" (shouldn't normally happen
    # with a 2-value verdict field, but defensive) picks the first.
    majority = "fail" if ("fail" in tied and len(tied) > 1) else tied[0]
    agreement = round(counts.get(majority, 0) / len(non_error), 4)
    canonical = next((s for s in non_error if s.get("verdict") == majority), non_error[0])

    merged = dict(canonical)
    for field in _NUMERIC_FIELDS.get(axis, ()):
        vals = [_num(s.get(field)) for s in non_error if s.get(field) is not None]
        if vals:
            merged[field] = round(_median(vals), 4)
    merged["verdict"] = majority
    merged["_samples_n"] = len(samples)
    merged["_agreement"] = agreement
    merged["_sample_verdicts"] = verdicts
    if len(samples) > len(non_error):
        merged["_sample_errors"] = len(samples) - len(non_error)
    return merged


# ── per-row / per-axis driver ─────────────────────────────────────────────


_CKPT_EVERY = 10
"""Rewrite the readable partial scorecard every N completed rows.

Per-row verdicts are appended + flushed to the .ckpt.jsonl immediately (so
nothing bought is ever lost); this is just how often the aggregated
``legalv2-<label>.json`` is refreshed so a partial run is inspectable while
it is still going.
"""

_DEFAULT_MAX_RETRIES = 5
"""R309 — retry budget per axis call.

``runner._call_judge_with_retry`` defaults to ``max_retries=1``, which was
tuned for ``claude-sonnet-4-6`` over a local wrapper. Over the Cloudflare
tunnel to Claude Max the wrapper intermittently returns
``api_status_500: "No response from Claude Code"`` — MEASURED transient, not
deterministic: 5 sequential calls with a byte-identical prompt scored 2 OK /
3 failed. That error IS already classified retryable (``api_status_5`` is in
``_RETRYABLE_ERROR_SUBSTRINGS``), so the only gap was the budget: at a ~40%
per-call success rate, 2 attempts still leaves 0.6**2 = 36% of axis calls
unrecoverable, which is exactly the "?" (judge_error) rate observed on the
r309 run — and every one of those is a PAID call whose output is discarded.

6 attempts takes that to 0.6**6 ~= 4.7%. Retries only fire on a failure, so
this costs nothing on the happy path; it converts already-spent tokens into
a usable verdict instead of a "?".
"""


def _judge_axis(
    axis: str, r: dict[str, Any], caller: Callable[[str], dict[str, Any]], k: int,
    retries: int = _DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    prompt, ctx = _prepare(axis, r)
    samples: list[dict[str, Any]] = []
    for _ in range(max(1, k)):
        raw, attempts, retried = _call_judge_with_retry(
            caller, prompt, max_retries=max(0, retries),
            backoff_s=4.0, backoff_mult=2.0,   # 4s, 8s, 16s, 32s, 64s — ride out the burst
        )
        if retried:
            raw = dict(raw)
            raw["_attempts"] = attempts
        try:
            post = _postprocess(axis, raw, r, ctx)
        except Exception as exc:  # noqa: BLE001 — a malformed judge response must never kill the run
            post = {"judge_error": f"postprocess_failed: {type(exc).__name__}: {exc}"[:200]}
        samples.append(post)
    return _aggregate_samples(samples, axis)


def _judge_row(
    r: dict[str, Any], caller: Callable[[str], dict[str, Any]], k: int,
    retries: int = _DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    verdicts = {axis: _judge_axis(axis, r, caller, k, retries) for axis in AXES}
    return {"id": r["id"], "category": r["category"], "verdicts": verdicts}


# ── run-level aggregation + scorecard ────────────────────────────────────


def _aggregate(judged: list[dict[str, Any]]) -> dict[str, Any]:
    agg: dict[str, Any] = {}
    global_substantiated = 0.0
    global_unsubstantiated = 0
    for axis in AXES:
        n = len(judged)
        p = f = e = 0
        modes: dict[str, int] = {}
        gov_total = sup_total = wrong_total = missing_total = 0
        prec_focus: list[float] = []; prec_sound: list[float] = []; rec: list[float] = []
        fact: list[float] = []
        omission_rows = fabrication_rows = 0
        agreements: list[float] = []
        for row in judged:
            v = (row.get("verdicts") or {}).get(axis) or {}
            if v.get("judge_error"):
                e += 1
                continue
            verd = str(v.get("verdict") or "").lower()
            if verd == "pass":
                p += 1
            elif verd == "fail":
                f += 1
                m = str(v.get("failure_mode") or "(unspecified)")[:80]
                modes[m] = modes.get(m, 0) + 1
            else:
                e += 1
                continue
            if "_agreement" in v:
                agreements.append(_num(v["_agreement"]))
            unsub = v.get("unsubstantiated_verdicts") or []
            global_unsubstantiated += len(unsub)
            if axis == "reference_correctness":
                gov_total += len(v.get("governing_refs") or [])
                sup_total += len(v.get("supporting_refs") or [])
                wrong_total += len(v.get("wrong_refs") or [])
                missing_total += len(v.get("missing_governing_refs") or [])
                global_substantiated += len(v.get("wrong_refs") or []) + len(v.get("missing_governing_refs") or [])
                if v.get("focus_precision") is not None:
                    prec_focus.append(_num(v["focus_precision"]))
                if v.get("legal_soundness_precision") is not None:
                    prec_sound.append(_num(v["legal_soundness_precision"]))
                if v.get("recall") is not None:
                    rec.append(_num(v["recall"]))
            if axis == "citation_faithfulness":
                global_substantiated += _num(v.get("mismatched"))
            if axis == "answer_correctness":
                if v.get("factual_score") is not None:
                    fact.append(_num(v["factual_score"]))
                if v.get("omission_present"):
                    omission_rows += 1
                if v.get("fabrication_present"):
                    fabrication_rows += 1
                global_substantiated += _num(v.get("contradicted"))
        entry: dict[str, Any] = {
            "n": n, "pass": p, "fail": f, "error": e,
            "pass_rate_raw": round(p / n, 4) if n else 0.0,
            "pass_rate_over_non_error": round(p / (p + f), 4) if (p + f) else 0.0,
            "top_failure_modes": sorted(modes.items(), key=lambda kv: -kv[1])[:8],
        }
        if agreements:
            entry["mean_judge_agreement"] = round(sum(agreements) / len(agreements), 4)
        if axis == "reference_correctness":
            entry["governing_total"] = gov_total
            entry["supporting_total"] = sup_total
            entry["wrong_total"] = wrong_total
            entry["missing_governing_total"] = missing_total
            if prec_focus:
                entry["mean_focus_precision"] = round(sum(prec_focus) / len(prec_focus), 4)
            if prec_sound:
                entry["mean_legal_soundness_precision"] = round(sum(prec_sound) / len(prec_sound), 4)
            if rec:
                entry["mean_recall"] = round(sum(rec) / len(rec), 4)
        if axis == "answer_correctness":
            if fact:
                entry["mean_factual_score"] = round(sum(fact) / len(fact), 4)
            entry["omission_rows"] = omission_rows
            entry["fabrication_rows"] = fabrication_rows
        agg[axis] = entry

    total_claims = global_substantiated + global_unsubstantiated
    agg["_substantiation_rate"] = round(global_substantiated / total_claims, 4) if total_claims else 1.0
    agg["_unsubstantiated_verdicts_total"] = global_unsubstantiated
    return agg


def _assert_claude_max_transport(provider: str) -> None:
    """Operator requirement (R309): the judge ALWAYS runs over the
    Cloudflare tunnel on the Claude Max subscription — never per-token
    Anthropic API billing.

    This is enforced rather than documented because the failure is silent
    and expensive in the wrong direction: an accidental
    ``--provider anthropic`` run produced 4/4 ``judge_error`` rows reading
    *"Your credit balance is too low to access the Anthropic API"* — every
    axis lost, and it looked identical to a model failure in the scorecard.

    Refuses to start on a billed provider (override with
    ``REGENOLD_JUDGE_ALLOW_BILLED=1`` for a deliberate Pro-tier test), and
    prints the resolved transport so the run's provenance is on the record.
    """
    import os

    if provider != "wrapper":
        if os.environ.get("REGENOLD_JUDGE_ALLOW_BILLED", "").strip().lower() not in (
            "1", "true", "yes", "on",
        ):
            raise SystemExit(
                f"[legal_v2] REFUSING to run on provider={provider!r}: this judge must "
                "use the Claude Max subscription via the Cloudflare tunnel "
                "(--provider wrapper), not per-token billing. Set "
                "REGENOLD_JUDGE_ALLOW_BILLED=1 to override deliberately."
            )
        print(f"[legal_v2] !! BILLED provider={provider} (override active)", flush=True)
        return

    try:
        from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
            get_openai_wrapper_provider,
            is_openai_wrapper_enabled,
        )
        if not is_openai_wrapper_enabled():
            raise SystemExit(
                "[legal_v2] wrapper provider is NOT configured — set OPENAI_API_BASE "
                "to the Cloudflare tunnel (https://.../v1) and OPENAI_API_KEY."
            )
        base = str(getattr(get_openai_wrapper_provider(), "_base_url", "") or "")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — never let a provenance probe kill a run
        print(f"[legal_v2] transport probe failed ({exc}); continuing", flush=True)
        return

    print(f"[legal_v2] transport: {base}  (Claude Max via wrapper)", flush=True)
    if base.startswith("http://127.0.0.1") or base.startswith("http://localhost"):
        print(
            "[legal_v2] !! transport is LOCALHOST, not the Cloudflare tunnel. "
            "Set OPENAI_API_BASE=https://wrapper.antifragile-ai.net/v1 to match "
            "the production path.",
            flush=True,
        )


def run(
    *, sidecar: Path, label: str, model: str, provider: str,
    timeout_s: float, concurrency: int, limit: int | None,
    samples: int = 1, out_dir: Path | None = None,
    retries: int = _DEFAULT_MAX_RETRIES, resume: bool = False,
) -> dict[str, Any]:
    set_judge_model(model)
    _assert_claude_max_transport(provider)
    caller = _resolve_caller(provider, timeout_s)
    all_rows = [_norm(r) for r in _load_rows(sidecar)]
    n_error_rows = sum(1 for r in all_rows if not r["answer"])
    rows = [r for r in all_rows if r["answer"]]  # skip error/empty-answer rows
    if limit:
        rows = rows[:limit]
    k = max(1, samples)
    print(
        f"[legal_v2] {len(rows)} rows x {len(AXES)} axes x {k} sample(s)  "
        f"model={model} provider={provider} concurrency={concurrency}",
        flush=True,
    )
    if n_error_rows:
        print(
            f"[legal_v2] !! {n_error_rows} row(s) had no answer and are EXCLUDED "
            "from every axis below.",
            flush=True,
        )

    # ── R309 checkpointing ────────────────────────────────────────────────
    # A judge run is ~4 paid calls per row over a couple of hours. Before
    # this, the sidecar was written ONCE at the end, so an interruption threw
    # away every verdict bought so far — this actually happened: a 72-row run
    # died at 64/72 and lost all of it. Each completed row is now appended to
    # a .ckpt.jsonl and flushed immediately, and a readable partial scorecard
    # is rewritten every _CKPT_EVERY rows. With --resume, already-judged rows
    # are skipped, so an interrupted run costs only the rows still missing.
    out_dir = out_dir or Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / f"legalv2-{label}.ckpt.jsonl"
    dest = out_dir / f"legalv2-{label}.json"

    prior: list[dict[str, Any]] = []
    if resume and ckpt_path.exists():
        for line in ckpt_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                prior.append(json.loads(line))
            except Exception:  # noqa: BLE001 — a torn final line must not kill a resume
                continue
        done_ids = {str(r.get("id")) for r in prior}
        before = len(rows)
        rows = [r for r in rows if str(r["id"]) not in done_ids]
        print(
            f"[legal_v2] resume: {len(prior)} row(s) already judged in {ckpt_path.name}; "
            f"{len(rows)} of {before} still to do",
            flush=True,
        )

    def _write_summary(judged_now: list[dict[str, Any]], *, partial: bool) -> None:
        summary = {
            "label": label, "source_sidecar": str(sidecar), "judge_model": model,
            "provider": provider, "samples": k, "partial": partial,
            "elapsed_s": round(time.monotonic() - t0, 1),
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "axes": list(AXES), "rows": judged_now, "aggregate": _aggregate(judged_now),
            "excluded_error_rows": n_error_rows,
        }
        dest.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    out: list[dict[str, Any] | None] = [None] * len(rows)
    done = 0
    lock = threading.Lock()
    t0 = time.monotonic()
    total = len(rows) + len(prior)
    ckpt_fh = ckpt_path.open("a" if resume else "w", encoding="utf-8")

    def _w(i: int, r: dict[str, Any]):
        return i, _judge_row(r, caller, k, retries)

    try:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futs = [pool.submit(_w, i, r) for i, r in enumerate(rows)]
            for fut in as_completed(futs):
                i, jr = fut.result()
                out[i] = jr
                with lock:
                    done += 1
                    ckpt_fh.write(json.dumps(jr, default=str) + "\n")
                    ckpt_fh.flush()
                    vs = {a: (jr["verdicts"].get(a) or {}).get("verdict", "?") for a in AXES}
                    print(
                        f"  [{len(prior) + done}/{total}] {str(jr['id'])[:34]:<34} "
                        f"ans={vs['answer_correctness']} ref={vs['reference_correctness']} "
                        f"cite={vs['citation_faithfulness']} concise={vs['answer_conciseness']}",
                        flush=True,
                    )
                    if done % _CKPT_EVERY == 0:
                        _write_summary(prior + [r for r in out if r is not None], partial=True)
                        print(
                            f"  .. checkpoint: {len(prior) + done}/{total} rows -> "
                            f"{dest.name} (partial)",
                            flush=True,
                        )
    finally:
        ckpt_fh.close()

    judged = prior + [r for r in out if r is not None]
    _write_summary(judged, partial=False)
    print(f"[legal_v2] sidecar -> {dest}  (checkpoint: {ckpt_path.name})", flush=True)
    return json.loads(dest.read_text(encoding="utf-8"))


def _fmt(s: dict[str, Any]) -> str:
    out = [
        "=" * 78,
        f"LEGAL-V2 JUDGE — {s['label']!r}  model={s['judge_model']}  samples={s.get('samples', 1)}",
        f"source: {Path(s['source_sidecar']).name}  elapsed={s['elapsed_s']}s",
        "=" * 78,
    ]
    for axis in s["axes"]:
        a = s["aggregate"][axis]
        line = (
            f"[{axis}] n={a['n']} pass={a['pass']} fail={a['fail']} err={a['error']} "
            f"pass_rate_raw={a['pass_rate_raw']} over_non_error={a['pass_rate_over_non_error']}"
        )
        out.append("\n" + line)
        if axis == "reference_correctness":
            out.append(
                f"   GOVERNING={a.get('governing_total', 0)} SUPPORTING={a.get('supporting_total', 0)} "
                f"WRONG={a.get('wrong_total', 0)} MISSING={a.get('missing_governing_total', 0)}"
            )
            if "mean_focus_precision" in a:
                out.append(
                    f"   focus_precision={a['mean_focus_precision']} "
                    f"legal_soundness_precision={a.get('mean_legal_soundness_precision')} "
                    f"recall={a.get('mean_recall')}"
                )
        if axis == "answer_correctness":
            if "mean_factual_score" in a:
                out.append(f"   mean_factual_score={a['mean_factual_score']}")
            out.append(
                f"   omission_rows={a.get('omission_rows', 0)} "
                f"fabrication_rows={a.get('fabrication_rows', 0)}"
            )
        if "mean_judge_agreement" in a:
            out.append(f"   judge_agreement={a['mean_judge_agreement']}")
        for mode, c in (a.get("top_failure_modes") or [])[:5]:
            out.append(f"     {c:>3}x {mode}")
    agg = s["aggregate"]
    out.append("\n" + "-" * 78)
    out.append(
        f"substantiation_rate={agg.get('_substantiation_rate')} "
        f"(unsubstantiated_verdicts_total={agg.get('_unsubstantiated_verdicts_total')})"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    # R305 — deferred from module scope so importing this module (e.g. from a
    # test) cannot mutate process env for everything that runs after it.
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv()
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
    p.add_argument("--provider", choices=("wrapper", "anthropic", "groq", "gemini"), default="wrapper")
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument(
        "--samples", type=int, default=1,
        help=(
            "Self-consistency: repeat each axis call K times and take the "
            "majority verdict / median numeric fields (default 1, "
            "recommended 3). Cost scales K×."
        ),
    )
    p.add_argument(
        "--max-retries", type=int, default=_DEFAULT_MAX_RETRIES,
        help=(
            "Retry budget per axis call on RETRYABLE failures only "
            f"(default {_DEFAULT_MAX_RETRIES}). The Cloudflare-tunnel -> Claude "
            "Max path returns a transient api_status_500 'No response from "
            "Claude Code' on a measured ~60%% of calls under load; retries "
            "only fire on failure, so raising this costs nothing on the happy "
            "path and stops a paid call being discarded as '?'."
        ),
    )
    p.add_argument(
        "--resume", action="store_true",
        help=(
            "Skip rows already present in legalv2-<label>.ckpt.jsonl and append "
            "to it. An interrupted run then costs only the rows still missing, "
            "instead of re-buying every verdict."
        ),
    )
    a = p.parse_args(argv)
    s = run(
        sidecar=a.sidecar, label=a.label, model=a.model, provider=a.provider,
        timeout_s=a.timeout, concurrency=a.concurrency, limit=a.limit, samples=a.samples,
        retries=a.max_retries, resume=a.resume,
    )
    print(_fmt(s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

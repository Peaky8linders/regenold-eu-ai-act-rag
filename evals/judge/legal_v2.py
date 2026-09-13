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
strict allowlist (``id, category, question, answer, pred_refs, gold_refs,``
``gold_answer, independent_gold_context``)
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
import os
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
    _answer_grounding_block,
    _has_independent_answer_grounding,
)

_DEFAULT_MODEL = os.environ.get("REGENOLD_JUDGE_MODEL", "claude-sonnet-4-6")

AXES: tuple[str, ...] = (
    "answer_correctness",
    "reference_correctness",
    "citation_faithfulness",
    "answer_conciseness",
)


# ── quote-or-retract grounding forcing function ─────────────────────────


import re


def _normalise_ws(s: str) -> str:
    s = str(s or "").lower()
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("—", " ").replace("–", " ").replace("-", " ")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def _quote_substantiated(quote: str, *text_blocks: str, min_words: int = 8) -> bool:
    """True iff ``quote`` is a real, sufficiently-long, literal/contiguous excerpt of
    at least one of ``text_blocks`` (punctuation/whitespace normalised with
    contiguous 4-gram sequence fallback).

    This is the anti-hallucination gate (R305 requirement 2): a judge
    verdict that asserts something is WRONG / MISSING / CONTRADICTED /
    MISMATCHED must be backed by an actual quote from the text it was
    shown, not a paraphrase or an invented excerpt.
    """
    q = str(quote or "").strip()
    words = q.split()
    if not q or len(words) < min_words:
        return False
    nq = _normalise_ws(q)
    if not nq:
        return False
    nq_words = nq.split()
    if len(nq_words) < min_words:
        return False

    for block in text_blocks:
        nb = _normalise_ws(block)
        if not nb:
            continue
        # 1. Exact normalized contiguous substring match
        if nq in nb:
            return True
        # 2. Longest CONTIGUOUS run fallback, with a negation veto.
        #
        # ⚠ The previous fallback was labelled "strict contiguous 4-gram
        # sequence matching (order-preserving)" and was none of those things.
        # It collected the block's 4-grams into a SET and asked what fraction of
        # the quote's 4-grams appeared anywhere in it, so 25% of the quote could
        # be arbitrary invention and the matches needed no adjacency and no
        # order. Measured against the real Article 14 sentence, all of these
        # returned True:
        #
        #   * the verbatim sentence                                  (correct)
        #   * "High-risk AI systems shall NOT be designed and developed
        #      in such a way that they can be effectively overseen..."  ← NEGATED
        #   * the sentence with two invented 4-grams spliced in
        #
        # A negation flip is the single most damaging failure this gate exists
        # to stop: it lets the judge "substantiate" a WRONG/CONTRADICTED verdict
        # with a quote asserting the OPPOSITE of the provision, which then reads
        # as evidence. The gate was passing exactly the case it was built for.
        #
        # Now: one maximal CONTIGUOUS run of matched tokens, no substitutions,
        # plus a hard veto whenever the quote and the matched span disagree on
        # any negation/exception token. Coverage is measured against the run,
        # not against a bag.
        nb_words = nb.split()
        if len(nq_words) >= min_words and len(nb_words) >= min_words:
            run = _longest_contiguous_run(nq_words, nb_words)
            if run is not None:
                start, length = run
                covers = length / len(nq_words)
                if covers >= 0.85:
                    span = nb_words[start:start + length]
                    if _negation_profile(nq_words) == _negation_profile(span):
                        return True
    return False


#: Tokens that invert or narrow a legal obligation. A quote that differs from
#: the source on ANY of these is not the source, however well the rest matches.
_NEGATION_TOKENS = frozenset({
    "not", "no", "nor", "never", "except", "unless", "without",
    "excluding", "exempt", "prohibited", "shall", "may", "must",
})


def _negation_profile(words: list[str]) -> tuple[str, ...]:
    """Ordered negation/modality tokens — the part a paraphrase must not change."""
    return tuple(w for w in words if w in _NEGATION_TOKENS)


def _longest_contiguous_run(
    quote_words: list[str], block_words: list[str]
) -> tuple[int, int] | None:
    """Longest run of quote tokens appearing CONTIGUOUSLY and in order in block.

    Returns ``(block_start_index, length)`` for the best run, or ``None``.
    Straight dynamic programming over the two token lists — no substitutions,
    no gaps, which is what "contiguous" has to mean for this gate to hold.
    """
    if not quote_words or not block_words:
        return None
    best_len = 0
    best_start = 0
    prev = [0] * (len(block_words) + 1)
    for qi in range(1, len(quote_words) + 1):
        cur = [0] * (len(block_words) + 1)
        for bi in range(1, len(block_words) + 1):
            if quote_words[qi - 1] == block_words[bi - 1]:
                cur[bi] = prev[bi - 1] + 1
                if cur[bi] > best_len:
                    best_len = cur[bi]
                    best_start = bi - cur[bi]
        prev = cur
    return (best_start, best_len) if best_len else None


# ── provision-text grounding (per-ref map, for substantiation checks) ───


_RECITAL_REF_RE = re.compile(r"^Recital\s+(\d{1,3})$", re.IGNORECASE)


def _resolve_ref_text(ref: str) -> str:
    """Verbatim text for a ref — Article/Annex via ``get_provision_text``,
    ``Recital N`` via the official recital corpus (R361 — the paper's
    related-recital retrieval makes recital-cited claims measurable; the
    engine already retrieves recitals via ``fetch_recital_anchors`` /
    ``_expand_referenced_annexes_and_recitals`` but the judge could not
    ground them). Returns "" for a non-existent ref."""
    from app.data.provision_text import get_provision_text  # local heavy import

    txt = get_provision_text(ref)
    if txt:
        return txt
    m = _RECITAL_REF_RE.match(str(ref).strip())
    if m:
        try:
            from app.data.official_eu_ai_act import OFFICIAL_RECITAL_TEXT  # noqa: PLC0415
            return str(OFFICIAL_RECITAL_TEXT.get(int(m.group(1)), "")).strip()
        except Exception:  # noqa: BLE001 — a missing corpus must not kill a run
            return ""
    return ""


def _ref_exists(ref: str) -> bool:
    """Resolution-based existence check. Deliberately NOT the head-lax
    ``provision_exists`` (``provision_exists("Article 3.999") is True`` —
    a documented open finding): a ref exists iff its verbatim text actually
    resolves, Articles/Annexes via the provision resolver and ``Recital N``
    via the official recital corpus."""
    return bool(_resolve_ref_text(ref))


def _resolve_provision_texts(refs: list[str], cap: int, max_refs: int) -> dict[str, str]:
    """Resolve each ref at its exact cited coordinate. Unlike
    ``grounded._provision_block`` this returns a
    ``ref -> text`` MAP so post-processing can substantiate a quote
    against the exact provision it was claimed against. Recital refs
    resolve via ``OFFICIAL_RECITAL_TEXT`` (R361)."""
    out: dict[str, str] = {}
    seen: set[str] = set()
    for r in refs[:max_refs]:
        key = str(r).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        txt = _resolve_ref_text(key)
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
        f"PREDICTED ANSWER: {r['answer']}\n\n"
        "STEP 1 — decompose the PREDICTED ANSWER into discrete legal "
        "propositions (one assertion each).\n"
        "STEP 2 — for EACH proposition, using ONLY the verbatim text above "
        "and no outside legal memory, mark it SUPPORTED, "
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
    recall_available = bool(gold_map or r.get("independent_gold_context"))
    recall_instruction = (
        "Assess missing governing provisions against the independent gold block."
        if recall_available
        else (
            "No independent gold context was supplied. Do not use memory to "
            "invent missing provisions; return missing_governing=[] and treat "
            "recall as unavailable."
        )
    )
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
        f"RECALL AVAILABILITY: {recall_instruction}\n\n"
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
        f"PREDICTED ANSWER: {r['answer']}\n\n"
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


# ── Axis 5 — fine-grained CRAG answer score (NICD paper, Appendix C.2.2) ─


#: The fine-grained CRAG scale, from Wedge et al., "Reducing Hallucinations
#: in Complex Question Answering using Simple Graph-based RAG" (NICD /
#: Newcastle), Appendix C.2.2. The paper's rubric is ported VERBATIM below;
#: the scale is asymmetric BY DESIGN — a hallucinated claim (extras) costs
#: more than a missing one, and an honest refusal scores 0 (neutral) rather
#: than being penalised like a wrong answer. The paper's headline metric,
#: truthfulness = sum of scores, is computed in :func:`_postprocess_answer_crag_fine`
#: and surfaced on the aggregate so a run reports correct − hallucinated
#: rather than a binary pass/fail.
_CRAG_SCALE = (
    "+1.0  fully correct: the prediction matches ALL provided gold answers.\n"
    "+0.5  partially correct: matches a SUBSET of the gold answers and\n"
    "      includes NO incorrect answers (missing claims, but no hallucination).\n"
    " 0.0  the model says 'unknown' / 'cannot answer' / that it lacks the\n"
    "      information — an honest refusal, not an error.\n"
    "-0.5  mixed: includes SOME correct gold answers AND at least one\n"
    "      incorrect answer (correct + hallucinated claims together).\n"
    "-1.0  incorrect: the prediction matches NONE of the gold answers.\n"
)


def render_answer_crag_fine(r: dict[str, Any], gold_block: str) -> str:
    """Fine-grained CRAG answer score — the paper's Appendix C.2.2 rubric
    applied to the ANSWER (not the reference set). Distinct from
    ``answer_correctness`` (LeMAJ LDP decomposition, pass/fail): this axis
    returns the paper's 5-level truthfulness scale and its asymmetry
    (hallucination −0.5/−1 > omission +0.5 > refusal 0). The verdict is
    derived from the score: pass iff score >= +0.5 (fully or cleanly
    partial, i.e. no hallucinated claim), fail otherwise — a hallucination
    always fails even when it also contains correct claims.

    Gold answers come from the probe set (``gold_answer``); verbatim
    provision text for the union of gold + predicted refs is supplied as
    grounding so the judge never leans on parametric legal memory — the
    repo's quote-or-retract discipline, applied to the gold answers.
    """
    gold_answers = str(r.get("gold_answer") or "").strip()
    return (
        _ANTI_SYCOPHANCY +
        "You are grading a Q&A answer on the fine-grained CRAG truthfulness "
        "scale. Judge whether the prediction matches the Ground Truth "
        "answers, using the QUESTION and the provided GROUND TRUTH answers to "
        "decide — never by string matching alone (different wording may "
        "express the same answer; 1% tolerance on numerical answers).\n"
        "Do not rely on your own legal knowledge: use ONLY the Ground Truth "
        "answers and the verbatim text supplied below.\n\n"
        "QUESTION: " + str(r["question"])[:600] + "\n\n"
        "GROUND TRUTH ANSWERS:\n"
        f"{gold_answers or '(none supplied)'}\n\n"
        "VERBATIM EU AI ACT TEXT (provisions relevant to this question):\n"
        f"{gold_block or '  (none)'}\n\n"
        "PREDICTED ANSWER:\n" + str(r["answer"]) + "\n\n"
        "Follow these steps:\n"
        "  1. If the prediction returns 'unknown', says it cannot answer, or "
        "says it lacks the information to answer, return 0.0.\n"
        "  2. If the prediction makes a claim but it matches NONE of the "
        "Ground Truth answers, return -1.0.\n"
        "  3. If the prediction matches ALL provided Ground Truth answers, "
        "return +1.0.\n"
        "  4. If the prediction matches a SUBSET of the Ground Truth answers "
        "(some correct answers missing) but includes NO additional incorrect "
        "answers, return +0.5.\n"
        "  5. If the prediction includes some correct Ground Truth answers "
        "AND at least one incorrect answer (an answer not in the Ground "
        "Truth list), return -0.5.\n\n"
        f"SCALE:\n{_CRAG_SCALE}\n"
        "Return ONLY one JSON object (no prose, no markdown fences):\n"
        '{"score":1.0|"0.5"|0.0|"-0.5"|-1.0,"class":"FULLY_CORRECT"|'
        '"PARTIAL_CLEAN"|"REFUSED"|"MIXED"|"WRONG",'
        '"rationale":"<one short sentence citing which gold answer(s) matched "'
        '"or were missed>","missing":["<gold claim omitted>"],'
        '"hallucinated":["<predicted claim not in gold>"]}'
    )


# ── Axis 6 — Faithfulness (Ragas-style, reference-free) ─────────────────


#: HyPA-RAG (Kalra et al., Holistic AI / UCL) evaluation metric #1, ported
#: from Ragas: Faithfulness = |C_inferred| / |C_total| — the fraction of
#: answer claims that are supported by the RETRIEVED context. Reference-free
#: (uses the retrieved context, never the gold answer), so it scores the
#: no-gold half of a benchmark that the gold-bound axes cannot touch.
#: Grounding: verbatim provision text for the PREDICTED refs (what the
#: answer claims to rely on). Verdict derived: pass iff all claims are
#: supported (faithfulness = 1.0), the Ragas default threshold — a single
#: unsupported claim is a hallucination-risk flag even at 0.8.
_FAITHFULNESS_RUBRIC = (
    "Decompose the PREDICTED ANSWER into discrete factual claims (one "
    "assertion each). For EACH claim, using ONLY the verbatim text above "
    "and no outside legal memory, decide whether the text ENTRAILS it "
    "(states it directly or states premises that necessarily imply it).\n"
    "  SUPPORTED — the text states it, or necessarily implies it.\n"
    "  UNSUPPORTED — the text neither states nor implies it (may be "
    "outside the retrieved provisions, invented, or unverifiable from "
    "the text).\n"
    "Do not penalise a claim merely because the retrieved context does "
    "not cover a DIFFERENT part of the regulation the question also "
    "touches: judge only what the answer asserts against the text "
    "supplied. For every UNSUPPORTED claim, state in one short phrase "
    "what the claim says and why the text does not support it.\n"
)


def render_answer_faithfulness(r: dict[str, Any], pred_map: dict[str, str]) -> str:
    """Ragas Faithfulness (reference-free) — HyPA-RAG metric #1.

    Faithfulness = supported claims / total claims, computed from the
    retrieved context (predicted refs' verbatim text). Reference-free: no
    gold answer or gold refs are used, so this scores the no-gold half of
    a benchmark (e.g. graphrag_evals_dataset.txt B.2.2) that the
    gold-bound axes (answer_correctness, answer_crag_fine,
    reference_correctness) cannot touch.
    """
    pred_block = _block_from_map(pred_map)
    return (
        _ANTI_SYCOPHANCY +
        "You are grading whether an answer is FAITHFUL to its cited "
        "context: every claim in the answer must be entailed by the "
        "retrieved text, not by the model's parametric memory.\n\n"
        f"QUESTION: {r['question'][:500]}\n\n"
        "VERBATIM RETRIEVED TEXT (the provisions the answer cites):\n"
        f"{pred_block or '  (none — the answer cites no provisions)'}\n\n"
        f"PREDICTED ANSWER: {r['answer']}\n\n"
        f"{_FAITHFULNESS_RUBRIC}\n"
        "Respond with ONE JSON object only (no prose, no markdown fences):\n"
        '{"claims":[{"text":"...","status":"SUPPORTED"|"UNSUPPORTED",'
        '"why":"<one short phrase, only for UNSUPPORTED>"}],'
        '"failure_mode":"<one short phrase>"}'
    )


def render_answer_relevancy(r: dict[str, Any]) -> str:
    """Ragas Answer Relevancy (reference-free) — HyPA-RAG metric #2.

    Measures whether the answer actually addresses the QUESTION asked (vs
    a fluent answer about a nearby topic). Reference-free: no gold answer
    or refs are used. The paper's formula (generate questions from the
    answer, cosine-sim their embeddings against the original query) is
    approximated by a grounded LLM-judge relevancy score on the same 0-1
    scale, per the paper's own human annotation criterion #2 ("Is the
    answer relevant to the question?").
    """
    return (
        _ANTI_SYCOPHANCY +
        "You are grading whether an answer is RELEVANT to the question "
        "asked. An answer can be accurate about its topic and still be "
        "irrelevant if it answers a different question than the one posed.\n\n"
        f"QUESTION: {r['question'][:500]}\n\n"
        f"PREDICTED ANSWER: {r['answer']}\n\n"
        "Scoring (Ragas answer-relevancy semantics):\n"
        "  relevant = 1.0 if the answer directly addresses the question.\n"
        "  relevant = 0.5 if it addresses a substantial part but misses a "
        "core sub-question, or answers a closely-adjacent reading.\n"
        "  relevant = 0.0 if it answers a different question, evades the "
        "question, or its content does not respond to what was asked.\n"
        "You may use intermediate values when the answer is partly on "
        "target. Return the score on the Ragas 0-1 continuum.\n\n"
        "Respond with ONE JSON object only (no prose, no markdown fences):\n"
        '{"relevancy":0.0,"rationale":"<one short sentence: what the '
        '"question asked and whether the answer addressed it>",'
        '"failure_mode":"<one short phrase>"}'
    )


def render_answer_conciseness(r: dict[str, Any]) -> str:
    """Judges only what is PRESENT for load-bearing relevance; never rewards omission."""
    return (
        _ANTI_SYCOPHANCY + _CALIBRATION_CONCISE +
        f"QUESTION: {r['question'][:500]}\n\n"
        f"PREDICTED ANSWER: {r['answer']}\n\n"
        "Judge ONLY what is PRESENT in the answer for load-bearing relevance to the "
        "question asked. Do NOT judge completeness here — a missing required "
        "element is scored on a different axis, not this one; an answer that "
        "omits something is not thereby more concise.\n\n"
        "Guidelines for conciseness evaluation:\n"
        "  1. REDUNDANT — conversational filler ('It is worth noting...', 'In general...'), "
        "repetitive hedging, or restating the exact same claim in multiple sentences "
        "without adding new statutory facts or application. Applying a statutory rule "
        "to the question's specific scenario is NOT redundant.\n"
        "  2. UNREQUESTED TOPIC — a substantial detour into an unrelated legal regime "
        "or distinct statutory requirement that has no direct bearing on the question "
        "(e.g. detailed GDPR mechanics on an AI Act classification question, or MDR "
        "notified-body audit intervals on a basic classification query). Direct statutory "
        "conditions, exemptions, or immediate legal consequences of the primary rule are "
        "permissible context and NOT an unrequested topic.\n\n"
        "For EACH sentence, decide if it is genuinely REDUNDANT or an UNREQUESTED TOPIC. "
        "Quote each flagged sentence VERBATIM from the answer above.\n\n"
        "Respond with ONE JSON object only:\n"
        '{"sentence_count":N,"redundant_sentences":["..."],'
        '"unrequested_topics":["..."],"failure_mode":"<one short phrase>"}'
    )


# ── prepare (build prompt + grounding context) ───────────────────────────


def _prepare(axis: str, r: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if axis == "answer_correctness":
        if _has_independent_answer_grounding(r):
            gold_map = {"independent_answer_context": _answer_grounding_block(r)}
        else:
            candidate_refs = list(dict.fromkeys((r.get("gold_refs") or []) + (r.get("pred_refs") or [])))
            gold_map = _resolve_provision_texts(candidate_refs, _GOLD_TEXT_CAP, _MAX_GOLD_REFS)
        return render_answer_correctness(r, gold_map), {"union_map": gold_map}
    if axis == "reference_correctness":
        pred_map = _resolve_provision_texts(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
        gold_map = _resolve_provision_texts(r["gold_refs"], _GOLD_TEXT_CAP, _MAX_GOLD_REFS)
        supplied = str(r.get("independent_gold_context") or "").strip()
        if supplied:
            gold_map["independent_gold_context"] = supplied
        return render_reference_correctness(r, pred_map, gold_map), {
            "pred_map": pred_map,
            "gold_map": gold_map,
            "recall_available": any(str(text).strip() for text in gold_map.values()),
        }
    if axis == "citation_faithfulness":
        pred_map = _resolve_provision_texts(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
        return render_citation_faithfulness(r, pred_map), {"pred_map": pred_map}
    if axis == "answer_conciseness":
        return render_answer_conciseness(r), {}
    if axis == "answer_crag_fine":
        # Grounding for the CRAG judge: gold answers (from the probe set) are
        # the primary evidence; verbatim provision text for the union of gold
        # + predicted refs backs the gold claims so the judge never leans on
        # parametric memory (quote-or-retract discipline applied to gold).
        candidate_refs = list(dict.fromkeys((r.get("gold_refs") or []) + (r.get("pred_refs") or [])))
        gold_map = _resolve_provision_texts(candidate_refs, _GOLD_TEXT_CAP, _MAX_GOLD_REFS)
        return render_answer_crag_fine(r, _block_from_map(gold_map)), {"union_map": gold_map}
    if axis == "answer_faithfulness":
        # Reference-free (Ragas faithfulness): the only evidence is the
        # verbatim text of the PREDICTED refs — never the gold answer, and
        # never gold refs, so the axis stays scorable on the no-gold half of
        # a benchmark. Gold refs deliberately NOT consulted here.
        pred_map = _resolve_provision_texts(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
        return render_answer_faithfulness(r, pred_map), {"pred_map": pred_map}
    if axis == "answer_relevancy":
        # Reference-free (Ragas answer relevancy): question + answer only.
        return render_answer_relevancy(r), {}
    raise ValueError(f"unknown axis {axis!r}; valid: {AXES}")


# ── post-processing (quote-or-retract enforcement lives here) ───────────


#: The raw reply keys that constitute ANSWERING each axis. An axis is
#: unanswered only when the reply carries NONE of its keys.
#:
#: ⚠ R350.1 — the first cut of this guard tested ONE array per axis
#: (``classifications``, ``redundant_sentences``, …) and that was too narrow in
#: the direction that loses data. ``_postprocess_reference_correctness`` also
#: reads ``missing_governing``; ``_postprocess_answer_conciseness`` also reads
#: ``unrequested_topics`` and ``sentence_count``. Worse, the array a model is
#: MOST likely to omit is the empty one — and empty is the PASS case. So the
#: narrow test converted legitimate passes, and real ``missing_governing`` /
#: ``unrequested_topics`` findings, into unscorable errors: it shrank n on the
#: axes that already have the least data, and moved ``pass_rate_raw`` against
#: the recorded baselines for reasons with nothing to do with the product.
_AXIS_KEYS: dict[str, tuple[str, ...]] = {
    "answer_correctness": ("propositions", "omission_present", "omission_detail"),
    "reference_correctness": ("classifications", "missing_governing"),
    "citation_faithfulness": ("citations",),
    "answer_conciseness": ("redundant_sentences", "unrequested_topics",
                           "sentence_count"),
    "answer_crag_fine": ("score", "class", "rationale", "missing", "hallucinated"),
    # Structured carriers ONLY — a reply carrying just free-text
    # (failure_mode/rationale) has not answered the axis and must be
    # unscorable, never silently scored as a pass (R350: absent is not
    # empty; empty [] claims IS a legitimate pass finding).
    "answer_faithfulness": ("claims",),
    "answer_relevancy": ("relevancy",),
}


def _axis_unanswered(raw: dict[str, Any], axis: str) -> dict[str, Any] | None:
    """Unscorable if the reply never answered THIS axis at all.

    ⚠ R350 — every ``_postprocess_*`` read its findings as ``raw.get(key) or []``
    and computed a verdict from the result. But ``runner._parse_judge_json``
    accepts any balanced JSON object carrying ANY key from a UNION target set,
    not the keys THIS axis needs. So a reply like
    ``{"verdict": "fail", "failure_mode": "Article 6 mismatched"}`` parsed
    cleanly, arrived with none of the axis's own keys, and postprocess
    recomputed the verdict from zero findings — turning the judge's own
    ``fail`` into a ``pass``. Verified end-to-end on two axes
    (citation_faithfulness, reference_correctness); both flipped fail -> pass,
    the unsafe direction, and both then entered ``dynamic_ab``'s aggregate as a
    genuine 1.0.

    ABSENT IS NOT EMPTY. ``[]`` is a legitimate finding ("I checked and found
    nothing") and MUST stay scorable — it is usually the pass. Only a reply
    carrying NONE of the axis's keys is unanswered, so this tests key
    membership across the whole axis, never the truthiness of one array.

    Returning a ``judge_error`` (rather than a verdict) is what makes the row
    unscorable downstream — ``dynamic_ab._scorable`` drops it from the axis and
    counts it in ``n_skipped``, instead of scoring it as a pass or a fail.
    """
    keys = _AXIS_KEYS.get(axis, ())
    if keys and not (set(raw) & set(keys)):
        return {"judge_error": f"axis_unanswered_{axis}", "_raw": raw}
    return None


def _postprocess_answer_correctness(raw: dict[str, Any], union_map: dict[str, str]) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    _unanswered = _axis_unanswered(raw, "answer_correctness")
    if _unanswered is not None:
        return _unanswered
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
    total = supported + contradicted + not_addressed
    factual_score = (supported / total) if total else 0.0
    fabrication_present = contradicted > 0
    unsupported_present = not_addressed > 0
    # ⚠ THIS THRESHOLD IS A CHOICE, NOT A CALIBRATION — and it REDEFINED an axis
    # in place. d7be457 replaced the previous rule (`not unsupported_present`,
    # i.e. every proposition had to be addressed) with `factual_score >= 0.70`,
    # under the SAME axis name and with the commit message calling it a
    # "calibrated LeMAJ threshold". Neither half of that holds up:
    #
    #  * There is no calibration behind 0.70. It appears nowhere else in evals/,
    #    docs/ROUNDS.md or .planning/ — no sweep, no ROC, no companion strict
    #    variant, no env gate.
    #  * LeMAJ (arXiv 2510.07243) prescribes Legal-Data-Point decomposition
    #    against a REFERENCE ANSWER and specifies no threshold. This function
    #    uses SUPPORTED / CONTRADICTED / NOT-ADDRESSED, and the July-7 batch has
    #    no reference answer at all, so the citation does not transfer.
    #
    # The effect is a strictly looser axis: a row where 30% of its propositions
    # go unverified now PASSES where it previously failed. That is CLAUDE.md's
    # R327 trap in its most dangerous form — "the ruler was rewritten in the
    # SAME change as the behaviour it grades" — so any number graded across
    # d7be457 is comparing two different rulers.
    #
    # Named and env-exposed so the two rulers are at least distinguishable and
    # the old one is recoverable: `REGENOLD_JUDGE_FACTUAL_THRESHOLD=1.0`
    # restores the pre-d7be457 "every proposition addressed" rule.
    import os  # noqa: PLC0415

    try:
        _factual_threshold = float(
            os.getenv("REGENOLD_JUDGE_FACTUAL_THRESHOLD", "").strip() or 0.70
        )
    except (TypeError, ValueError):
        _factual_threshold = 0.70
    verdict = "pass" if (
        contradicted == 0
        and factual_score >= _factual_threshold
        and not omission_present
    ) else "fail"
    return {
        "verdict": verdict,
        "supported": supported, "contradicted": contradicted, "not_addressed": not_addressed,
        "omission_present": omission_present, "omission_detail": raw.get("omission_detail") or "",
        "fabrication_present": fabrication_present, "fabrications": fabrications,
        "unsupported_present": unsupported_present,
        "factual_score": round(factual_score, 4),
        "unsubstantiated_verdicts": unsub,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess_reference_correctness(
    raw: dict[str, Any], pred_map: dict[str, str], gold_map: dict[str, str], pred_refs: list[str],
    recall_available: bool = True,
) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    _unanswered = _axis_unanswered(raw, "reference_correctness")
    if _unanswered is not None:
        return _unanswered
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
        # Check if ref is a non-existent provision in the EU AI Act catalog.
        # R361 — resolution-based (``_ref_exists``), NOT the head-lax
        # ``provision_exists`` (which returns True for ``Article 3.999`` and
        # False for real ``Recital N`` refs — both wrong directions, the
        # second documented in R360).
        if not _ref_exists(ref):
            wrong.append(ref)
            unsub.append({"ref": ref, "claimed": "NON_EXISTENT_PROVISION", "quote": quote})
            continue

        raw_prov = pred_map.get(ref, "")
        if cls == "WRONG":
            if _quote_substantiated(quote, raw_prov):
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

    missing_raw = (raw.get("missing_governing") or []) if recall_available else []
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
    recall = ((len(governing) / denom) if denom else 1.0) if recall_available else None
    verdict = "pass" if (len(wrong) == 0 and len(missing) == 0) else "fail"
    return {
        "verdict": verdict,
        "governing_refs": governing, "supporting_refs": supporting, "wrong_refs": wrong,
        "missing_governing_refs": missing,
        "n_predicted": total,
        "focus_precision": round(focus_precision, 4),
        "legal_soundness_precision": round(legal_soundness_precision, 4),
        "recall": round(recall, 4) if recall is not None else None,
        "recall_available": recall_available,
        "recall_provenance": (
            "independent_gold_context"
            if recall_available else "unavailable_no_independent_gold"
        ),
        "unsubstantiated_verdicts": unsub,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess_citation_faithfulness(
    raw: dict[str, Any], pred_map: dict[str, str], pred_refs: list[str],
) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    _unanswered = _axis_unanswered(raw, "citation_faithfulness")
    if _unanswered is not None:
        return _unanswered
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
    _unanswered = _axis_unanswered(raw, "answer_conciseness")
    if _unanswered is not None:
        return _unanswered
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
    raw_unrequested = raw.get("unrequested_topics") or []
    unrequested: list[str] = []
    for s in raw_unrequested:
        s = str(s or "").strip()
        if not s:
            continue
        if _quote_substantiated(s, answer_text, min_words=3):
            unrequested.append(s)
        else:
            unsub.append({"claimed": "UNREQUESTED", "quote": s})

    # ⚠ ONE-SIDED LENIENCY — now gated, DEFAULT OFF.
    #
    # This block deletes a conciseness violation that the judge ALREADY
    # SUBSTANTIATED (the quote cleared `_quote_substantiated` two lines above)
    # because a free-text `failure_mode` field says "none". Three problems, and
    # they compound:
    #
    #  1. It can only ever move a row fail -> pass. There is no symmetric rule
    #     turning a pass into a fail, so it is a one-directional thumb on the
    #     scale, in the flattering direction.
    #  2. It ranks an unstructured prose field ABOVE structured, quote-verified
    #     evidence. `failure_mode` is a free-text summary the judge writes last;
    #     `unrequested_topics` are quote-anchored and were just validated
    #     against the answer text. Trusting the summary over the evidence
    #     inverts the whole point of the substantiation gate.
    #  3. Conciseness is the ONE axis the official scorecard says we LEAD, with
    #     zero headroom (CLAUDE.md, "Where we stand"). A silent rubric change
    #     there is the most consequential place in the repo to make one — and
    #     this shipped in an uncommitted diff with no A/B and no flag.
    #
    # CLAUDE.md's R327 lesson applies verbatim: "if you change a formula, change
    # its NAME" — an unnamed, ungated redefinition of an axis under its own name
    # is how a bench comes to confirm a change using a scorer built to like it.
    #
    # Default OFF restores the pre-diff behaviour. `=1` re-enables it so it can
    # be A/B'd on its own, which is the only way it earns a default.
    import os  # noqa: PLC0415

    if os.getenv("REGENOLD_JUDGE_CONCISENESS_LENIENCY", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        fm = str(raw.get("failure_mode") or "").strip().lower()
        is_clean_failure_mode = (
            fm.startswith("none") or fm == "clean" or fm == "no violations"
        )
        if is_clean_failure_mode and len(redundant) == 0 and len(unrequested) <= 1:
            unrequested = []

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


def _postprocess_answer_crag_fine(raw: dict[str, Any]) -> dict[str, Any]:
    """Map the judge's CRAG reply onto the 5-level truthfulness scale.

    The score is the paper's headline output — truthfulness per row, with
    the asymmetry (hallucination costs more than omission; refusal is
    neutral 0). The derived ``verdict`` (pass iff score >= +0.5) keeps the
    axis compatible with the binary ``_aggregate`` while the score itself
    is carried through for truthfulness aggregation: a MIXED (-0.5) or
    WRONG (-1.0) answer always fails even when it also contains correct
    claims; a REFUSED (0.0) answer fails the binary pass gate but scores
    neutral on truthfulness, exactly as the paper intends.
    """
    if raw.get("judge_error"):
        return dict(raw)
    _unanswered = _axis_unanswered(raw, "answer_crag_fine")
    if _unanswered is not None:
        return _unanswered
    try:
        score = float(raw.get("score"))
    except (TypeError, ValueError):
        # A non-numeric score is a shape failure — the model did not answer
        # the axis. Unscorable, not a verdict.
        return {"judge_error": "crag_score_not_numeric", "_raw": raw}
    # Clamp to the legal scale (the prompt demands these 5 values; a model
    # that drifts is a shape failure, not a new scale).
    if score not in (-1.0, -0.5, 0.0, 0.5, 1.0):
        return {"judge_error": f"crag_score_out_of_scale: {score}", "_raw": raw}
    cls = str(raw.get("class") or "").strip().upper()
    score = round(score, 1)
    verdict = "pass" if score >= 0.5 else "fail"
    missing = [str(x) for x in (raw.get("missing") or [])]
    hallucinated = [str(x) for x in (raw.get("hallucinated") or [])]
    return {
        "verdict": verdict,
        "crag_score": score,
        "truthfulness": score,  # truthfulness = score per the paper
        "class": cls,
        "missing_claims": missing,
        "hallucinated_claims": hallucinated,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess_answer_faithfulness(raw: dict[str, Any]) -> dict[str, Any]:
    """Ragas Faithfulness — HyPA-RAG metric #1, reference-free.

    faithfulness = supported_claims / total_claims (the paper's formula,
    ported from Ragas). Verdict: pass iff faithfulness == 1.0 — the Ragas
    default threshold; a single unsupported claim is a hallucination-risk
    flag even at 0.8, so only a fully-grounded answer passes. No gold
    answer or gold refs are involved, so this scores the no-gold half of
    a benchmark (graphrag_evals_dataset.txt B.2.2) that gold-bound axes
    cannot touch.
    """
    if raw.get("judge_error"):
        return dict(raw)
    _unanswered = _axis_unanswered(raw, "answer_faithfulness")
    if _unanswered is not None:
        return _unanswered
    claims = raw.get("claims") or []
    supported = unsupported = 0
    unsupported_claims: list[str] = []
    for c in claims:
        if not isinstance(c, dict):
            continue
        status = str(c.get("status") or "").strip().upper().replace(" ", "-")
        if status == "UNSUPPORTED":
            unsupported += 1
            unsupported_claims.append(str(c.get("text") or c.get("why") or ""))
        else:
            # SUPPORTED and any malformed/unclassified entry: count as
            # supported rather than dropping it from the denominator — an
            # unclassified claim is never evidence of a hallucination.
            supported += 1
    total = supported + unsupported
    # Ragas semantics: no claims decomposed -> nothing to be unfaithful to.
    faithfulness = (supported / total) if total else 1.0
    verdict = "pass" if unsupported == 0 else "fail"
    return {
        "verdict": verdict,
        "faithfulness": round(faithfulness, 4),
        "supported": supported,
        "unsupported": unsupported,
        "unsupported_claims": unsupported_claims,
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess_answer_relevancy(raw: dict[str, Any]) -> dict[str, Any]:
    """Ragas Answer Relevancy — HyPA-RAG metric #2, reference-free.

    relevancy on the 0-1 continuum (the prompt allows intermediate
    values). Verdict: pass iff relevancy >= 0.5 — the Ragas default
    threshold; an answer that addresses a substantial part of the
    question passes (completeness is graded on answer_correctness /
    answer_crag_fine, not here), while an answer that evades the question
    or answers a different one fails. No gold involved.
    """
    if raw.get("judge_error"):
        return dict(raw)
    _unanswered = _axis_unanswered(raw, "answer_relevancy")
    if _unanswered is not None:
        return _unanswered
    try:
        relevancy = float(raw.get("relevancy"))
    except (TypeError, ValueError):
        return {"judge_error": "relevancy_not_numeric", "_raw": raw}
    if not (0.0 <= relevancy <= 1.0):
        return {"judge_error": f"relevancy_out_of_range: {relevancy}", "_raw": raw}
    relevancy = round(relevancy, 4)
    verdict = "pass" if relevancy >= 0.5 else "fail"
    return {
        "verdict": verdict,
        "relevancy": relevancy,
        "rationale": str(raw.get("rationale") or ""),
        "failure_mode": raw.get("failure_mode") or "",
        "_raw": raw,
    }


def _postprocess(axis: str, raw: dict[str, Any], r: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    if raw.get("judge_error"):
        return dict(raw)
    if axis == "answer_correctness":
        return _postprocess_answer_correctness(raw, ctx["union_map"])
    if axis == "reference_correctness":
        return _postprocess_reference_correctness(
            raw,
            ctx["pred_map"],
            ctx["gold_map"],
            r["pred_refs"],
            ctx.get("recall_available", True),
        )
    if axis == "citation_faithfulness":
        return _postprocess_citation_faithfulness(raw, ctx["pred_map"], r["pred_refs"])
    if axis == "answer_conciseness":
        return _postprocess_answer_conciseness(raw, r["answer"])
    if axis == "answer_crag_fine":
        return _postprocess_answer_crag_fine(raw)
    if axis == "answer_faithfulness":
        return _postprocess_answer_faithfulness(raw)
    if axis == "answer_relevancy":
        return _postprocess_answer_relevancy(raw)
    raise ValueError(f"unknown axis {axis!r}; valid: {AXES}")


# ── self-consistency aggregation (majority verdict / median numerics) ───

_NUMERIC_FIELDS: dict[str, tuple[str, ...]] = {
    "answer_correctness": ("factual_score", "supported", "contradicted", "not_addressed"),
    "reference_correctness": ("focus_precision", "legal_soundness_precision", "recall", "n_predicted"),
    "citation_faithfulness": ("faithful", "mismatched"),
    "answer_conciseness": ("redundant_sentence_count", "unrequested_topic_count"),
    "answer_crag_fine": ("crag_score", "truthfulness"),
    "answer_faithfulness": ("faithfulness", "supported", "unsupported"),
    "answer_relevancy": ("relevancy",),
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
    graded numeric field, and an ``_agreement`` fraction. Chooses the
    coherent medoid candidate to maintain consistency between structured
    lists and numeric metrics.
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
    # Anti-leniency: an outright tie that includes "fail" resolves to "fail"
    majority = "fail" if ("fail" in tied and len(tied) > 1) else tied[0]
    agreement = round(counts.get(majority, 0) / len(non_error), 4)

    # Filter to candidates sharing the majority verdict
    candidates = [s for s in non_error if s.get("verdict") == majority]
    if not candidates:
        candidates = non_error

    # Choose the medoid sample (closest to median on the primary axis score)
    primary_num = "focus_precision" if axis == "reference_correctness" else (
        "factual_score" if axis == "answer_correctness" else None
    )
    if primary_num and len(candidates) > 1:
        vals = [_num(c.get(primary_num)) for c in candidates if c.get(primary_num) is not None]
        if vals:
            target_median = _median(vals)
            canonical = min(candidates, key=lambda c: abs(_num(c.get(primary_num)) - target_median))
        else:
            canonical = candidates[0]
    else:
        canonical = candidates[0]

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
    if not r["answer"]:
        verdicts = {
            axis: {
                "verdict": "fail",
                "evaluation_error": "empty_answer",
                "failure_mode": "empty answer",
                "_samples_n": 0,
            }
            for axis in AXES
        }
        return {"id": r["id"], "category": r["category"], "verdicts": verdicts}
    verdicts: dict[str, Any] = {}
    for axis in AXES:
        if axis == "answer_correctness" and not (
            _has_independent_answer_grounding(r)
            or bool(_answer_grounding_block(r).strip())
            or bool(r.get("gold_refs"))
            or bool(r.get("pred_refs"))
        ):
            verdicts[axis] = {
                "judge_error": "no_independent_gold_context",
                "grounding_status": "unscorable",
                "_samples_n": 0,
            }
        elif axis == "answer_crag_fine" and not str(r.get("gold_answer") or "").strip():
            # The CRAG axis judges the ANSWER against the probe-set gold
            # answer text; without gold there is nothing to grade against
            # (references alone are not enough — this axis is not about
            # citation set overlap). Unscorable, not a failure.
            verdicts[axis] = {
                "judge_error": "no_gold_answer",
                "grounding_status": "unscorable",
                "_samples_n": 0,
            }
        else:
            verdicts[axis] = _judge_axis(axis, r, caller, k, retries)
    return {"id": r["id"], "category": r["category"], "verdicts": verdicts}


# ── run-level aggregation + scorecard ────────────────────────────────────


def _aggregate(judged: list[dict[str, Any]]) -> dict[str, Any]:
    agg: dict[str, Any] = {}
    global_substantiated = 0.0
    global_unsubstantiated = 0
    # R359 — aggregate every axis present in the rows, not only the default
    # ``AXES``. ``answer_crag_fine`` is opt-in (direct ``_judge_axis``
    # dispatch) so it never appears in standard 4-axis runs, but when a run
    # DOES carry it the aggregate must surface its truthfulness — silently
    # dropping it would make a CRAG run unreadable at the scorecard level.
    _axes = list(AXES) + [
        ax for ax in (set().union(*(set(r.get("verdicts") or {}) for r in judged)) if judged else set())
        if ax not in AXES
    ]
    for axis in _axes:
        n = len(judged)
        p = f = e = 0
        modes: dict[str, int] = {}
        gov_total = sup_total = wrong_total = missing_total = 0
        prec_focus: list[float] = []; prec_sound: list[float] = []; rec: list[float] = []
        fact: list[float] = []
        crag_scores: list[float] = []
        omission_rows = fabrication_rows = unsupported_rows = hallucinated_rows = 0
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
                if v.get("unsupported_present"):
                    unsupported_rows += 1
                global_substantiated += _num(v.get("contradicted"))
            if axis == "answer_crag_fine":
                # Truthfulness = sum of per-row CRAG scores (the paper's
                # headline metric: accurate answers minus hallucinated ones),
                # plus a hallucination count so a run reports how many rows
                # shipped a MIXED (-0.5) or WRONG (-1.0) claim.
                if v.get("crag_score") is not None:
                    crag_scores.append(_num(v["crag_score"]))
                if v.get("hallucinated_claims"):
                    hallucinated_rows += 1
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
            entry["unsupported_rows"] = unsupported_rows
        if axis == "answer_crag_fine":
            if crag_scores:
                entry["truthfulness"] = round(sum(crag_scores), 4)
                entry["mean_crag_score"] = round(sum(crag_scores) / len(crag_scores), 4)
            entry["hallucinated_rows"] = hallucinated_rows
        if axis == "answer_faithfulness":
            # HyPA-RAG metric #1 — mean faithfulness plus a count of rows
            # carrying at least one unsupported (hallucination-risk) claim.
            fth: list[float] = []
            unsupported_rows = 0
            for row in judged:
                v = (row.get("verdicts") or {}).get(axis) or {}
                if v.get("judge_error"):
                    continue
                if v.get("faithfulness") is not None:
                    fth.append(_num(v["faithfulness"]))
                if (v.get("unsupported") or 0) > 0:
                    unsupported_rows += 1
            if fth:
                entry["mean_faithfulness"] = round(sum(fth) / len(fth), 4)
            entry["unsupported_rows"] = unsupported_rows
        if axis == "answer_relevancy":
            # HyPA-RAG metric #2 — mean relevancy over the 0-1 continuum.
            rel: list[float] = []
            for row in judged:
                v = (row.get("verdicts") or {}).get(axis) or {}
                if v.get("judge_error"):
                    continue
                if v.get("relevancy") is not None:
                    rel.append(_num(v["relevancy"]))
            if rel:
                entry["mean_relevancy"] = round(sum(rel) / len(rel), 4)
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

    if provider in ("bedrock", "openrouter"):
        print(f"[legal_v2] provider={provider} active", flush=True)
        return

    if provider != "wrapper":
        if os.environ.get("REGENOLD_JUDGE_ALLOW_BILLED", "").strip().lower() not in (
            "1", "true", "yes", "on",
        ):
            raise SystemExit(
                f"[legal_v2] REFUSING to run on provider={provider!r}: this judge must "
                "use Bedrock, OpenRouter, or the Claude Max subscription via the Cloudflare tunnel "
                "(--provider wrapper). Set REGENOLD_JUDGE_ALLOW_BILLED=1 to override deliberately."
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
    if limit:
        all_rows = all_rows[:limit]
    rows = all_rows
    n_error_rows = sum(1 for r in rows if not r["answer"])
    k = max(1, samples)
    print(
        f"[legal_v2] {len(rows)} rows x {len(AXES)} axes x {k} sample(s)  "
        f"model={model} provider={provider} concurrency={concurrency}",
        flush=True,
    )
    if n_error_rows:
        print(
            f"[legal_v2] {n_error_rows} row(s) had no answer; they remain in "
            "every denominator as deterministic failures.",
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
            "input_rows": total,
            "empty_answer_rows": n_error_rows,
            "excluded_error_rows": 0,
            "denominator_policy": "all input rows; empty answers fail; judge errors remain errors",
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
        if axis == "answer_faithfulness":
            if "mean_faithfulness" in a:
                out.append(
                    f"   mean_faithfulness={a['mean_faithfulness']} "
                    f"unsupported_rows={a.get('unsupported_rows', 0)}"
                )
        if axis == "answer_relevancy":
            if "mean_relevancy" in a:
                out.append(f"   mean_relevancy={a['mean_relevancy']}")
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
    p.add_argument(
        "--provider",
        choices=("wrapper", "anthropic", "groq", "gemini", "bedrock", "openrouter"),
        default="wrapper",
    )
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

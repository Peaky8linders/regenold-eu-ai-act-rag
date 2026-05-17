"""Regenold rules-PDF probe set.

The 2026 EU AI Act competition rules PDF (page 2-3) gives three worked
example questions. The probe set here pins them in code plus ~20 plausible
re-phrasings so we can measure both:

    a) bundle accuracy on the LITERAL competition examples
    b) bundle generalisation across natural paraphrases of those examples

If (a) is high but (b) is low, the bundle has over-fit to surface text.
If (a) and (b) move together across rounds, the optimisation is real.

The 3 canonical questions and their expected behaviour:

    1. ``technical_doc`` — "Does the technical documentation of a high-risk
       AI system require to provide specifications regarding the required
       hardware?"
       Expected refs: Annex IV.2 / Annex IV.2.a (hardware/computational
       resources requirement).
       Expected verdict: YES — Annex IV(2)(a) explicitly requires
       hardware/computational resource specs in the tech doc.

    2. ``emotion_recognition`` — "Are AI systems intended for emotion
       recognition from biometric data always prohibited?"
       Expected refs: Article 5.1.f (prohibition in workplace/education)
       AND Annex III.5 (high-risk biometric category elsewhere).
       Expected verdict: NO — not always; context-dependent. Prohibited
       in workplace/education contexts (Art. 5(1)(f)); high-risk under
       Annex III otherwise.

    3. ``doctor_transcription`` — "Is an AI that transcribes doctor-
       patient conversations prohibited? Or is it high-risk per Annex
       III?"
       Expected refs: depends on context. Medical-device overlap → MDR
       + Annex III.5 / Art. 6(1) (high-risk). Plain transcription →
       Art. 50 (limited risk, transparency).
       Expected verdict: NOT prohibited; potentially high-risk in
       medical contexts, otherwise limited risk transparency.

Public API:
    * ``load_regenold_probe() -> list[RegenoldProbeItem]``
    * ``score_regenold_probe(items, agent_fn) -> dict``
"""
from __future__ import annotations

import re
from typing import Any, Callable, TypedDict


class RegenoldProbeItem(TypedDict, total=False):
    """One probe item — canonical or paraphrase."""

    id: str
    question_id: str  # family id: technical_doc / emotion_recognition / doctor_transcription
    is_canonical: bool
    question: str
    gold_articles: list[str]
    gold_answer_text: str
    expected_verdict: str


# ── 3 canonical questions + 20+ paraphrases ──────────────────────────────


_TECHNICAL_DOC_CANONICAL = (
    "Does the technical documentation of a high-risk AI system require "
    "to provide specifications regarding the required hardware?"
)
_TECHNICAL_DOC_GOLD_ARTICLES = ["Annex IV.2", "Annex IV.2.a", "Article 11"]
_TECHNICAL_DOC_GOLD_TEXT = (
    "Yes. Annex IV(2)(a) requires the technical documentation of a "
    "high-risk AI system to include specifications regarding the "
    "computational resources used to develop, train, test and validate "
    "the system — i.e. the required hardware. Article 11 mandates that "
    "this documentation exists and is kept up to date."
)
_TECHNICAL_DOC_VERDICT = "yes"


_EMOTION_CANONICAL = (
    "Are AI systems intended for emotion recognition from biometric data "
    "always prohibited?"
)
_EMOTION_GOLD_ARTICLES = ["Article 5.1.f", "Annex III.5"]
_EMOTION_GOLD_TEXT = (
    "No. Emotion recognition from biometric data is not always "
    "prohibited. Article 5(1)(f) prohibits emotion recognition only in "
    "the workplace and educational institutions (with medical / safety "
    "carve-outs). Outside those contexts, emotion-recognition systems "
    "are classified as high-risk under Annex III(5)."
)
_EMOTION_VERDICT = "context_dependent"


_TRANSCRIPTION_CANONICAL = (
    "Is an AI that transcribes doctor-patient conversations prohibited? "
    "Or is it high-risk as per the use cases of Annex III of the AI Act?"
)
_TRANSCRIPTION_GOLD_ARTICLES = ["Article 6", "Annex III.5", "Article 50"]
_TRANSCRIPTION_GOLD_TEXT = (
    "Not prohibited. A doctor-patient transcription AI is not listed in "
    "Article 5. Where it qualifies as or is integrated into a medical "
    "device under MDR, it is high-risk under Article 6(1) and Annex "
    "III(5) or Annex I (depending on the integration). A pure "
    "transcription tool without medical-device status is generally "
    "limited-risk and subject to Article 50 transparency obligations."
)
_TRANSCRIPTION_VERDICT = "context_dependent"


_TECHNICAL_DOC_PARAPHRASES = (
    "For high-risk AI systems, does the technical documentation need to "
    "specify the hardware that's required?",
    "Must we include hardware specs in our high-risk AI system's "
    "technical documentation?",
    "Is information about required hardware part of the technical "
    "documentation for a high-risk AI under the EU AI Act?",
    "Does Annex IV require us to document computational resources or "
    "hardware?",
    "We are a provider of a high-risk AI system. Do we have to describe "
    "the hardware used to train and run it in our technical docs?",
    "Under Article 11 of the AI Act, are hardware specifications a "
    "mandatory part of the technical documentation?",
    "Is the required hardware something we must list in the technical "
    "documentation that accompanies a high-risk AI system?",
)

_EMOTION_PARAPHRASES = (
    "Is emotion recognition from biometric data prohibited in every "
    "context under the EU AI Act?",
    "Are all emotion-recognition AI systems banned by Article 5?",
    "We use biometric data to infer customer emotions. Is this always a "
    "prohibited practice?",
    "Does the AI Act outlaw emotion recognition outright, or only in "
    "certain settings?",
    "If we deploy an emotion-recognition system in retail, is it "
    "prohibited the same way it would be in the workplace?",
    "Are workplace and non-workplace emotion-recognition systems "
    "treated the same under the AI Act?",
    "Is emotion recognition always banned, or is the prohibition limited "
    "to specific contexts like education and the workplace?",
)

_TRANSCRIPTION_PARAPHRASES = (
    "An AI tool that transcribes doctor-patient conversations — is it "
    "prohibited by Article 5, or high-risk under Annex III?",
    "We are building an AI that transcribes consultations between "
    "doctors and patients. Is this banned, or is it high-risk?",
    "Does the EU AI Act prohibit AI transcription of medical "
    "consultations, or merely classify it as high-risk?",
    "Is medical-conversation transcription a prohibited AI practice, or "
    "does it fall under Annex III high-risk categories?",
    "We deploy an AI scribe for doctors during patient consultations. "
    "Is it prohibited or high-risk?",
    "How does the AI Act classify an AI that transcribes physician-"
    "patient dialogue — prohibited, high-risk, or something else?",
    "Is a clinical-conversation transcription AI a Title II prohibited "
    "practice, or a Title III high-risk system?",
)


def _build_paraphrase(
    question_id: str,
    canonical: dict,
    paraphrase_text: str,
    idx: int,
) -> RegenoldProbeItem:
    return {
        "id": f"{question_id}_p{idx:02d}",
        "question_id": question_id,
        "is_canonical": False,
        "question": paraphrase_text,
        "gold_articles": list(canonical["gold_articles"]),
        "gold_answer_text": canonical["gold_answer_text"],
        "expected_verdict": canonical["expected_verdict"],
    }


def load_regenold_probe() -> list[RegenoldProbeItem]:
    """Return the full probe set: 3 canonical + 20+ paraphrases."""
    families = [
        {
            "question_id": "technical_doc",
            "canonical": _TECHNICAL_DOC_CANONICAL,
            "gold_articles": _TECHNICAL_DOC_GOLD_ARTICLES,
            "gold_answer_text": _TECHNICAL_DOC_GOLD_TEXT,
            "expected_verdict": _TECHNICAL_DOC_VERDICT,
            "paraphrases": _TECHNICAL_DOC_PARAPHRASES,
        },
        {
            "question_id": "emotion_recognition",
            "canonical": _EMOTION_CANONICAL,
            "gold_articles": _EMOTION_GOLD_ARTICLES,
            "gold_answer_text": _EMOTION_GOLD_TEXT,
            "expected_verdict": _EMOTION_VERDICT,
            "paraphrases": _EMOTION_PARAPHRASES,
        },
        {
            "question_id": "doctor_transcription",
            "canonical": _TRANSCRIPTION_CANONICAL,
            "gold_articles": _TRANSCRIPTION_GOLD_ARTICLES,
            "gold_answer_text": _TRANSCRIPTION_GOLD_TEXT,
            "expected_verdict": _TRANSCRIPTION_VERDICT,
            "paraphrases": _TRANSCRIPTION_PARAPHRASES,
        },
    ]
    items: list[RegenoldProbeItem] = []
    for f in families:
        canon_item: RegenoldProbeItem = {
            "id": f["question_id"] + "_canonical",
            "question_id": f["question_id"],
            "is_canonical": True,
            "question": f["canonical"],
            "gold_articles": list(f["gold_articles"]),
            "gold_answer_text": f["gold_answer_text"],
            "expected_verdict": f["expected_verdict"],
        }
        items.append(canon_item)
        for idx, para in enumerate(f["paraphrases"], start=1):
            items.append(_build_paraphrase(f["question_id"], canon_item, para, idx))
    return items


# ── Scoring ──────────────────────────────────────────────────────────────


_ARTICLE_HEAD_RE = re.compile(
    r"^(?:Article|Art\.?)\s*(\d+)(?:[.\(].*)?$", re.IGNORECASE
)
_ANNEX_HEAD_RE = re.compile(
    r"^Annex\s+([IVXLC]+)(?:[.\(].*)?$", re.IGNORECASE
)


def _article_head(ref: str | None) -> str | None:
    if not isinstance(ref, str):
        return None
    s = ref.strip()
    m = _ARTICLE_HEAD_RE.match(s)
    if m:
        return f"Article {int(m.group(1))}"
    m = _ANNEX_HEAD_RE.match(s)
    if m:
        return f"Annex {m.group(1).upper()}"
    return None


def _ref_set(refs: list[str]) -> set[str]:
    """Strict ref set keyed by sub-anchor when present, else article head."""
    out: set[str] = set()
    for r in refs or ():
        if not isinstance(r, str):
            continue
        rs = r.strip()
        if not rs:
            continue
        # Keep the full reference string (sub-anchor sensitive).
        out.add(rs)
        # Also project to head for fallback matching.
        head = _article_head(rs)
        if head:
            out.add(head)
    return out


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 4}


def score_regenold_probe(
    items: list[RegenoldProbeItem],
    agent_fn: Callable[[RegenoldProbeItem], dict[str, Any]],
) -> dict[str, Any]:
    """Score the probe set.

    Per-item axes:
        * ``ref_strict`` — Jaccard of gold vs predicted ref sets.
          Sub-anchor sensitive: "Annex IV.2.a" predicted against gold
          "Annex IV.2.a" scores 1.0; against gold "Annex IV.2" scores
          partial because the projection includes "Annex IV" too.
        * ``ans_overlap`` — token-Jaccard of gold-answer-text vs
          predicted answer prose. The gold text is the regulator-voice
          model answer; high overlap means the bundle hit the same
          regulatory vocabulary.

    Family-level aggregation rolls up canonical + paraphrases per
    ``question_id`` so we see per-question generalisation. A LARGE gap
    between the canonical and its paraphrase mean is a clear signal of
    surface-text over-fit.
    """
    per_question_acc: dict[str, dict[str, list[float]]] = {}
    per_item_rows: list[dict[str, Any]] = []

    for item in items:
        result = agent_fn(item) or {}
        pred_refs_raw = result.get("references") or []
        pred_answer = result.get("answer") or ""

        gold_refs = _ref_set(item["gold_articles"])
        pred_refs = _ref_set(pred_refs_raw)

        # Strict Jaccard on the union of full-ref + head projection.
        if gold_refs:
            inter = len(gold_refs & pred_refs)
            union = len(gold_refs | pred_refs)
            ref_strict = inter / union if union else 0.0
        else:
            ref_strict = 1.0 if not pred_refs else 0.0

        # Ans overlap: token-Jaccard against the gold answer text.
        g_tok = _tokens(item["gold_answer_text"])
        p_tok = _tokens(pred_answer)
        if not g_tok:
            ans_overlap = 0.0 if p_tok else 1.0
        elif not p_tok:
            ans_overlap = 0.0
        else:
            ans_overlap = len(g_tok & p_tok) / len(g_tok | p_tok)

        qid = item["question_id"]
        family = per_question_acc.setdefault(
            qid,
            {
                "ref_strict_canonical": [],
                "ans_overlap_canonical": [],
                "ref_strict_paraphrase": [],
                "ans_overlap_paraphrase": [],
            },
        )
        if item["is_canonical"]:
            family["ref_strict_canonical"].append(ref_strict)
            family["ans_overlap_canonical"].append(ans_overlap)
        else:
            family["ref_strict_paraphrase"].append(ref_strict)
            family["ans_overlap_paraphrase"].append(ans_overlap)

        per_item_rows.append(
            {
                "id": item["id"],
                "question_id": qid,
                "is_canonical": item["is_canonical"],
                "ref_strict": round(ref_strict, 4),
                "ans_overlap": round(ans_overlap, 4),
                "gold_articles": list(item["gold_articles"]),
                "pred_refs": list(pred_refs_raw),
            }
        )

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    per_question_out: dict[str, dict[str, float]] = {}
    for qid, family in per_question_acc.items():
        all_ref = family["ref_strict_canonical"] + family["ref_strict_paraphrase"]
        all_ans = family["ans_overlap_canonical"] + family["ans_overlap_paraphrase"]
        per_question_out[qid] = {
            "ref_strict": round(_mean(all_ref), 4),
            "ans_overlap": round(_mean(all_ans), 4),
            "ref_strict_canonical": round(
                _mean(family["ref_strict_canonical"]), 4
            ),
            "ref_strict_paraphrase": round(
                _mean(family["ref_strict_paraphrase"]), 4
            ),
            "ans_overlap_canonical": round(
                _mean(family["ans_overlap_canonical"]), 4
            ),
            "ans_overlap_paraphrase": round(
                _mean(family["ans_overlap_paraphrase"]), 4
            ),
            "n": len(all_ref),
        }

    summary = {
        "n": len(items),
        "ref_strict": round(
            _mean([r["ref_strict"] for r in per_item_rows]), 4
        ),
        "ans_overlap": round(
            _mean([r["ans_overlap"] for r in per_item_rows]), 4
        ),
    }

    return {
        "summary": summary,
        "per_question": per_question_out,
        "rows": per_item_rows,
    }

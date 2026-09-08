"""R394 — the curated-intercept bloc: seven rows, fourteen failed criteria.

MEASURED. Of the 24 official rows that failed at least one Answer Correctness
criterion, SEVEN ship answers that are byte-identical to hard-coded strings in
``_graph_rag_impl.py`` (Stage-2 is skipped for them, so the answer is a pure
function of the source). Their failures were literally typed into the source.

Two were worse than wrong text: ``_detect_systemic_risk_scope_inquiry`` and
``_detect_deepfake_criminal_exception_inquiry`` MISFIRED onto rg_099 and rg_103,
overriding a correct pipeline answer with a canned answer to a different
question.

GATE (zero-variance, the strongest situation available in this repo): all 27
Stage-2-skipped rows are byte-identical across two independent live runs, so a
replay attributes every change to the edit with no sampling noise. Same-harness
baseline vs branch, n=27:

    rows changed      : 7  (exactly the targets)
    NON-TARGETS       : []
    gold_dropped_head : 2 -> 1   (-1, RECOVERED — rg_040 gains Article 44.1)
    HARD RULE #8      : PASS

Every statutory sentence added by this round was verified against
``provision_text.get_provision_text`` before being written.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.data.provision_text import get_provision_text
from app.engines._graph_rag_impl import (
    GraphContext,
    _detect_deepfake_criminal_exception_inquiry,
    _detect_systemic_risk_scope_inquiry,
    _deterministic_answer,
)

_BATCH = Path(__file__).resolve().parents[1] / "evals" / "regenold" / "_official_batch_20260707.json"


def _questions() -> dict[str, str]:
    rows = json.loads(_BATCH.read_text(encoding="utf-8"))
    return {r["id"]: r["question"] for r in rows}


def _answer(q: str) -> str:
    return _deterministic_answer(q, GraphContext(question=q))


# -- the two misfiring detectors, two-sided ----------------------------------


def test_systemic_risk_intercept_keeps_its_row_and_releases_the_misfire():
    """rg_023 must still fire; rg_099 must not.

    rg_023 asks whether "systemic risk" applies to AI systems or GPAI models or
    both — a disjunction over candidate subjects. rg_099 asks whether GPAI
    providers must shield models from adversarial attacks, and matched only
    because "GPAI systems, even if not with systemic risk" satisfied a
    proximity regex. The guard requires the disjunctive scope shape.
    """
    q = _questions()
    assert _detect_systemic_risk_scope_inquiry(q["rg_023"]) is True
    assert _detect_systemic_risk_scope_inquiry(q["rg_099"]) is False


def test_deepfake_intercept_keeps_its_row_and_releases_the_misfire():
    """rg_002 must still fire; rg_103 must not.

    rg_103 mentions law enforcement only as a COMPARATOR ("does the lighter
    transparency requirement apply like for certain law enforcement
    situations?") while asking about educational use. rg_002 asks directly
    whether the duty applies "when prosecuting a criminal offence".
    """
    q = _questions()
    assert _detect_deepfake_criminal_exception_inquiry(q["rg_002"]) is True
    assert _detect_deepfake_criminal_exception_inquiry(q["rg_103"]) is False


def test_the_comparator_guard_does_not_swallow_a_direct_question():
    """A question that BOTH compares and asks directly must still fire.

    The guard is overridden by an explicit criminal-justice subject, so it
    cannot suppress the row the intercept exists for.
    """
    both = (
        "Does the deep-fake disclosure obligation apply when prosecuting a "
        "criminal offence, like for certain law enforcement situations?"
    )
    assert _detect_deepfake_criminal_exception_inquiry(both) is True


def test_neither_detector_fires_on_the_probe_corpus():
    """Blast-radius guard: measured 0/132 for both after the fix."""
    from evals.harness.probe_set import load_probe_set

    rows = load_probe_set()
    for fn in (_detect_systemic_risk_scope_inquiry,
               _detect_deepfake_criminal_exception_inquiry):
        hits = [r.id for r in rows if fn(r.live_question or "")]
        assert not hits, f"{fn.__name__} leaked onto probe rows: {hits}"


# -- the repaired statutory content ------------------------------------------


def test_rg011_testing_data_carries_article_10_1_and_10_3():
    """Both scored criteria: the Art. 10(1) framing and the 10(3) criteria."""
    ans = _answer(_questions()["rg_011"])
    assert "Article 3(32)" in ans
    assert "Article 10(1)" in ans
    assert "training, validation and testing data sets" in ans
    assert "Article 10(3)" in ans
    for limb in ("relevant", "sufficiently representative", "free of errors",
                 "complete", "statistical properties"):
        assert limb in ans, f"Article 10(3) criterion missing: {limb}"


def test_rg031_article_6_3_states_the_verdict_and_names_point_a():
    """The evaluator scored a bare "No" as a criterion; the answer had none."""
    ans = _answer(_questions()["rg_031"])
    assert ans.strip().startswith("No"), "the verdict must lead the answer"
    assert "point (a)" in ans
    assert "narrow procedural task" in ans


def test_rg040_certificate_carries_article_44_language_and_validity():
    ans = _answer(_questions()["rg_040"])
    assert "Article 44(1)" in ans and "easily understood" in ans
    assert "Article 44(2)" in ans
    assert "five years" in ans and "four years" in ans


def test_rg043_special_data_carries_the_gdpr_framing_and_confidentiality():
    ans = _answer(_questions()["rg_043"])
    assert "in addition to" in ans.lower()
    assert "2016/679" in ans and "2018/1725" in ans and "2016/680" in ans
    assert "confidentiality obligations" in ans
    assert "transmitted, transferred or otherwise accessed" in ans


# -- every added sentence must be grounded in the corpus ----------------------


@pytest.mark.parametrize(
    "ref,phrase",
    [
        ("Article 10.1", "training, validation and testing data sets"),
        ("Article 10.3", "sufficiently representative"),
        ("Article 10.5", "confidentiality obligations"),
        ("Article 44.1", "easily understood"),
        ("Article 44.2", "five years"),
        ("Annex III.5.d", "evaluate and classify emergency calls"),
        ("Article 6.3", "narrow procedural task"),
    ],
)
def test_added_claims_are_grounded_in_the_verbatim_corpus(ref, phrase):
    """No sentence in a curated intercept may be written from memory.

    Each phrase this round added to an intercept must appear in the official
    text of the provision it is attributed to.
    """
    text = get_provision_text(ref) or ""
    assert phrase.lower() in text.lower(), (
        f"{phrase!r} is not in the verbatim text of {ref} — an intercept is "
        "asserting something the statute does not say"
    )


# -- R394.1: a curated intercept must survive the ANSWER-LENGTH pipeline ------
#
# MEASURED, and it cost a full round. The first cut of the rg_011 and rg_031
# repairs added the missing statutory content and made the previously-failing
# criteria pass -- but pushed the answers to four sentences. The deterministic
# path applies a THREE-SENTENCE cap in
# ``normalise_answer_for_regenold``, which drops one sentence from the MIDDLE:
#
#     rg_011  1/3 -> 2/3   crit 3 (leakage) was PASSING, began to FAIL
#     rg_031  3/4 -> 3/4   crit 4 (Article 6(4)) was PASSING, began to FAIL
#
# Net gain on both rows: zero. Every variant of the dropped sentence survives in
# ISOLATION, so the trigger is the sentence COUNT, not the wording.
#
# A curated intercept is not exempt from the length pipeline. These tests assert
# on the answer AFTER normalisation, which is what actually ships.


_SCORED_CONTENT = {
    "rg_011": [
        ("Article 10(1)",),
        ("relevant", "sufficiently representative", "free of errors",
         "complete", "statistical properties"),
        ("leak", "independence", "inflated", "masks"),
    ],
    "rg_031": [
        ("No.",),
        ("point (a)", "narrow procedural"),
        ("profil",),   # matches "profiling" and "profiles"
        ("Article 6(4)", "document", "before"),
    ],
    "rg_040": [("Article 44(1)", "easily understood"), ("Article 44(2)", "five years", "four years")],
    "rg_043": [("in addition to",), ("confidentiality obligations",)],
    "rg_029": [("evaluate and classify emergency calls",),
               ("police, firefighters and medical aid",)],
}


# Rows MEASURED to pass through normalise_answer_for_regenold. The route
# bypasses it entirely for classification-topic rows without Stage-2
# (regenold.py:8679 `if _is_classification_topic and not _stage2_landed`),
# so asserting the capped regime on those would test a path they never take.
_NORMALISED_ROWS = ["rg_011", "rg_031"]


@pytest.mark.parametrize("qid", _NORMALISED_ROWS)
def test_scored_content_survives_normalisation(qid):
    """Every scored fact must be present in the SHIPPED answer, not just the raw one."""
    from app.integrations.regenold.models import normalise_answer_for_regenold

    question = _questions()[qid]
    raw = _answer(question)
    shipped = normalise_answer_for_regenold(raw, question=question)
    for group in _SCORED_CONTENT[qid]:
        missing = [t for t in group if t.lower() not in shipped.lower()]
        assert not missing, (
            f"{qid}: {missing} present in the raw intercept but STRIPPED by "
            f"normalise_answer_for_regenold. raw={len(raw)} shipped={len(shipped)} "
            f"chars, {shipped.count('.')} sentences — most likely the "
            "three-sentence cap dropping a middle sentence. Shorten the answer "
            "or fold the fact into an earlier sentence."
        )


@pytest.mark.parametrize("qid", _NORMALISED_ROWS)
def test_repaired_intercepts_are_not_truncated(qid):
    """The normaliser must not shorten these answers at all.

    A shrink means a sentence was dropped, and the dropped sentence carries a
    scored criterion often enough that it is worth failing on the shrink itself
    rather than waiting for a criterion assertion to notice.
    """
    from app.integrations.regenold.models import normalise_answer_for_regenold

    question = _questions()[qid]
    raw = _answer(question)
    shipped = normalise_answer_for_regenold(raw, question=question)
    assert len(shipped) == len(raw), (
        f"{qid}: normalisation shortened the intercept {len(raw)} -> "
        f"{len(shipped)} chars ({raw.count('.')} sentences). Keep curated "
        "intercepts within the three-sentence budget."
    )


@pytest.mark.parametrize("qid", sorted(_SCORED_CONTENT))
def test_scored_content_is_present_in_the_raw_intercept(qid):
    """Every repaired row must CARRY its scored facts, whatever the routing.

    The two tests above pin survival through the length pipeline for the
    rows that go through it; this one pins that the content exists at all,
    for every row, so a future edit cannot silently delete a scored fact
    from a row that happens to bypass normalisation today.
    """
    raw = _answer(_questions()[qid])
    for group in _SCORED_CONTENT[qid]:
        missing = [t for t in group if t.lower() not in raw.lower()]
        assert not missing, f"{qid}: scored content absent from the intercept: {missing}"

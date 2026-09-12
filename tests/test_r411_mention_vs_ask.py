"""R411 — an intercept must key on the ASK, not on a provision MENTION.

Every detector in ``_is_curated_authoritative_intercept`` short-circuits Stage-2
and ships a STOCK curated verdict. Correct when the question asks the intercept's
question; badly wrong when the question merely NAMES the provision while asking
something else, because the user then gets a fluent answer to a different
question.

Two instances, both measured, both fixed here:

1. ``_detect_article_6_3_inquiry`` — the first alternative was the bare
   designation ``art(?:icle)?\\s+6\\(3\\)``. Measured with
   ``docs/measurements/r411/mention_vs_ask_probe.py``: it was the ONLY one of 33
   detectors that fired on a neutral "what does Article 6(3) say?" question.
   Live effect: a question about the Article 6(4) documentation duty was answered
   with the rg_031 classification verdict.

2. ``_APPLICABILITY_CUE_RE`` (the Article 113 date seed) — the first alternative
   was a bare ``apply``. Its one official-corpus fire, rg_088, is a FALSE
   POSITIVE: the only match is the word "apply" inside a NEGATIVE clause
   ("no Annex I nor III apply"), and rg_088's gold is Article 26.1 / 26.6 with no
   Article 113. It also produced a stray ``Article 113.3`` on a live question.
"""

from __future__ import annotations

import pytest

from app.engines import _graph_rag_impl as G
from app.routes.regenold import _ANNEX_REF_RE, _APPLICABILITY_CUE_RE

# --------------------------------------------------------------------------- #
# 1. the Article 6(3) intercept
# --------------------------------------------------------------------------- #

# Official corpus row rg_031 (gold Article 6.3.a) — the R356 task shape. The
# detector is written for this and must keep firing.
RG_031 = (
    "Is an AI system used to structure or deduplicate information for a use case "
    "listed in Annex III considered high-risk?"
)

# Official corpus row rg_032 (gold Article 6.3.c) — the docstring requires this
# NOT to fire: "detect decision-making patterns" is substantive, not a 6(3) task.
RG_032 = (
    "Is an AI system used to detect decision-making patterns or deviations for a "
    "use case listed in Annex III considered high-risk?"
)

# The live defect (2026-09-12, production): mentions 6(3), asks about Art. 6(4).
MENTION_WITH_OTHER_ASK = (
    "If a provider relies on the Article 6(3) derogation for an Annex III system, "
    "what documentation and registration duties apply?"
)


def test_article_6_3_task_shape_still_fires() -> None:
    assert G._detect_article_6_3_inquiry(RG_031)


def test_article_6_3_deviation_shape_still_does_not_fire() -> None:
    assert not G._detect_article_6_3_inquiry(RG_032)


def test_article_6_3_mention_with_other_ask_does_not_fire() -> None:
    """The fix. Firing here shipped a classification verdict to a duties question."""
    assert not G._detect_article_6_3_inquiry(MENTION_WITH_OTHER_ASK)
    assert not G._is_curated_authoritative_intercept(MENTION_WITH_OTHER_ASK)


@pytest.mark.parametrize(
    "question",
    [
        "Under the EU AI Act, what does Article 6(3) say?",
        "Please summarise Article 6(3) of the EU AI Act.",
        "What documentation does Article 6(3) of the EU AI Act require?",
    ],
)
def test_bare_article_6_3_mention_does_not_fire(question: str) -> None:
    assert not G._detect_article_6_3_inquiry(question)


def test_designation_regex_is_not_dead() -> None:
    """Guard the regex itself: ``\\b`` after ``)`` can never match before a space.

    The first cut of this gate ended the designation with ``\\b``. Because
    ``Article 6(3)`` ends in ``)`` — a non-word char — ``\\b`` requires a WORD
    char next, so the alternative was DEAD for the ordinary form and only fired
    when glued to a word. The probe then read "zero mention fires" because the
    regex was unusable, not because the gate worked. This pins the lookahead.
    """
    D = G._PREMATCH_ARTICLE_6_3_DESIGNATION
    assert D.search("Article 6(3) derogation")
    assert D.search("article 6(3).")
    assert D.search("Article 6(3), and also")
    assert D.search("Article 6(3)(a)")
    assert D.search("under 6(3)")
    # ... and it must not swallow a longer designation.
    assert not D.search("Article 6(30)")
    assert not D.search("Article 6(3)a")


@pytest.mark.parametrize(
    "question",
    [
        # The existing TestArticle63Routing contract: a question about the
        # exception itself is exactly what the curated verdict answers.
        "What are the self-assessment requirements under Article 6(3)?",
        "Is our system exempt under Article 6(3) if it performs only preparatory tasks?",
        "What does the Article 6(3) exception require?",
        "How do we self-assess as not high-risk under Article 6(3)?",
        "What is the preparatory task exception under Article 6(3)?",
        "What are the requirements for Article 6(3) exception?",
        "Does the Article 6(3) derogation apply to our Annex III system?",
    ],
)
def test_topic_ask_still_fires(question: str) -> None:
    """The broader cue must not cost recall on the topic the verdict covers."""
    assert G._detect_article_6_3_inquiry(question)


@pytest.mark.parametrize(
    "question",
    [
        # Conditional PROTASIS carrying the designation = premise, then a
        # different ask. Answering with the stock classification verdict here
        # answers a question that was not asked.
        "If a provider relies on the Article 6(3) derogation for an Annex III "
        "system, what documentation and registration duties apply?",
        "When a deployer invokes the Article 6(3) exception, which registration "
        "obligations follow?",
    ],
)
def test_designation_in_a_conditional_premise_does_not_fire(question: str) -> None:
    assert not G._detect_article_6_3_inquiry(question)


def test_premise_veto_is_not_applied_to_the_topic_phrases() -> None:
    """The veto is scoped to the bare designation, like the ask-gate itself.

    A question that names the EXCEPTION (not just the coordinate) is already
    asking about it, so putting it behind a conditional must not silence it.
    """
    assert G._detect_article_6_3_inquiry(
        "If our system performs only a preparatory task exception role, is it high-risk?"
    )


def test_genuine_article_6_3_classification_ask_still_fires() -> None:
    """The narrowing must not cost recall on a real classification question."""
    assert G._detect_article_6_3_inquiry(
        "Does the Article 6(3) derogation apply where our Annex III system is "
        "not high-risk?"
    )
    assert G._detect_article_6_3_inquiry(
        "Our system is a preparatory task. Is the high-risk exemption available?"
    )


def test_exception_phrases_are_not_gated_on_a_further_cue() -> None:
    """A phrase naming the exception IS the ask; it must survive untouched.

    The first cut of this fix ALSO required a classification cue for these
    forms, which silently dropped "preparatory task exception" questions that
    the detector had always answered. The gate belongs on the bare designation
    only.
    """
    assert G._detect_article_6_3_inquiry(
        "Is the preparatory task exception available for our Annex III system?"
    )
    assert G._detect_article_6_3_inquiry(
        "Does the self-assess not high-risk route require registration?"
    )


def test_every_gate_detector_is_ask_keyed() -> None:
    """Regression guard for the whole class, not just this instance.

    A detector that fires on a neutral question naming a provision is keyed on a
    mention. ``mention_vs_ask_probe.py`` measures this over 33 x 15 x 3 carriers;
    this is the fast subset that runs in CI.
    """
    carriers = (
        "Under the EU AI Act, what does {ref} say?",
        "What documentation does {ref} of the EU AI Act require?",
    )
    refs = ("Article 6(3)", "Article 5", "Article 26", "Article 50", "Annex III")
    offenders = []
    for name in dir(G):
        if not name.endswith("_inquiry"):
            continue
        fn = getattr(G, name)
        if not callable(fn):
            continue
        for carrier in carriers:
            for ref in refs:
                try:
                    if fn(carrier.format(ref=ref)):
                        offenders.append(f"{name}({carrier.format(ref=ref)!r})")
                except TypeError:
                    continue
    assert not offenders, "mention-keyed detectors: " + "; ".join(offenders)


# --------------------------------------------------------------------------- #
# 2. the Article 113 applicability cue
# --------------------------------------------------------------------------- #

RG_088 = (
    "We deployed a high-risk AI system in our company. We have a use in mind that "
    "is outside the intended use and our legal team say such a use is definitely "
    "no risk (no Annex I nor III apply). Can we just go ahead with the new use and "
    "do we need to keep logs for it?"
)


def test_bare_apply_verb_no_longer_triggers_the_date_seed() -> None:
    """rg_088's only cue match was 'apply' in a negative clause; gold has no Art. 113."""
    assert _ANNEX_REF_RE.search(RG_088), "precondition: the Annex gate is met"
    assert not _APPLICABILITY_CUE_RE.search(RG_088)


@pytest.mark.parametrize(
    "question",
    [
        "When does the EU AI Act start applying to high-risk systems?",
        "What is the applicability date for the Annex III obligations?",
        "Do the Annex III obligations apply from 2 August 2026?",
        "Is there a transitional period for Annex I embedded systems?",
    ],
)
def test_real_applicability_questions_still_trigger_the_seed(question: str) -> None:
    assert _APPLICABILITY_CUE_RE.search(question)


def test_live_defect_question_no_longer_reaches_the_date_seed() -> None:
    """The question that shipped a stray Article 113.3 must not trip the cue."""
    assert not _APPLICABILITY_CUE_RE.search(MENTION_WITH_OTHER_ASK)

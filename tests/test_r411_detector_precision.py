"""R411 — a curated single-issue intercept must not pre-empt a synthesis request.

The recurring engine defect in this repo is an **over-matching detector**: a
curated intercept latches onto words anywhere in the question, fires on a
question it was never written for, and then short-circuits Stage-2 — shipping a
narrow curated verdict in place of a synthesised answer. Four rounds have now
been spent on instances of it (medtech triage, the Art. 5(1)(g) gatekeeper, the
R410 verdict-lead detector, and the R410 closed-set member guard).

R411 fixes the instance on ``_detect_reclassification_inquiry``. A question
whose PRIMARY ask is a provider-vs-deployer comparison carries the
reclassification markers inside its SECOND ask, and the pre-R411 detector fired
on them — hitting the ``_curated_stage2_skip`` gate and shipping the narrow
Article 25 verdict (2 wire references) instead of the comparison.

The guard requires BOTH an opening synthesis imperative AND an explicit second
ask, so it cannot be widened by accident into suppressing genuine single-issue
reclassification questions.
"""

from __future__ import annotations

import pytest

from app.engines import _graph_rag_impl as G

# The shape the guard exists for: synthesis imperative first, reclassification
# ask second. Reproduced from a live production request (2026-09-12).
COMPARISON_WITH_TRAILING_RECLASSIFICATION = (
    "Compare the obligations of providers and deployers of high-risk AI systems "
    "under the EU AI Act, and explain what happens if a deployer becomes a provider."
)

# The official corpus row this detector was written for (rg_025, gold Art. 25).
# It must KEEP firing: the first ask IS the reclassification ask.
GENUINE_SINGLE_ISSUE = (
    "Can an operator that is not a provider according to the EU AI Act, for example "
    "a deployer, take actions on a given high-risk AI system such that it can be "
    "effectively seen as a provider?"
)

# A synthesis imperative with NO second ask is still a single-issue question.
SYNTHESIS_OPENER_SINGLE_ISSUE = (
    "Explain how an operator that is not a provider, for example a deployer, can take "
    "actions on a high-risk AI system such that it is effectively seen as a provider."
)


def test_trailing_reclassification_ask_does_not_fire() -> None:
    assert not G._detect_reclassification_inquiry(
        COMPARISON_WITH_TRAILING_RECLASSIFICATION
    )


def test_trailing_ask_does_not_short_circuit_stage2() -> None:
    """The whole cost of the over-match is the Stage-2 skip it triggers."""
    assert not G._is_curated_authoritative_intercept(
        COMPARISON_WITH_TRAILING_RECLASSIFICATION
    )


def test_genuine_single_issue_still_fires() -> None:
    assert G._detect_reclassification_inquiry(GENUINE_SINGLE_ISSUE)
    assert G._is_curated_authoritative_intercept(GENUINE_SINGLE_ISSUE)


def test_synthesis_opener_without_second_ask_still_fires() -> None:
    """The guard needs BOTH conjuncts — an opener alone must not suppress it."""
    assert G._detect_reclassification_inquiry(SYNTHESIS_OPENER_SINGLE_ISSUE)


@pytest.mark.parametrize(
    "question",
    [
        "Compare the provider and deployer obligations under Article 26, and describe "
        "when a distributor becomes an importer.",
        "Outline the roles under the Act; also list the conditions under which an "
        "operator that is not a provider is seen as a provider.",
    ],
)
def test_other_trailing_ask_shapes_are_guarded(question: str) -> None:
    assert not G._detect_reclassification_inquiry(question)


def test_compound_subject_is_not_a_compound_ask() -> None:
    """"providers and deployers" must not read as a second ask."""
    assert not G._RECLASSIFY_SECOND_ASK_RE.search(
        "Does the Act distinguish providers and deployers and importers?"
    )

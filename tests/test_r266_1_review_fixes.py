"""R266.1 — regression pins for the R264/R265 Sonnet-5-judge-triage review fixes.

Four defect fixes found in an adversarial review of the merged R265/R266 curated
intercepts + meta-leak strip. Each is a NARROWING (kills a false-fire / an
over-strip) so davidath stays byte-identical — the detectors already fired on
0/476 davidath rows and the tightening keeps them there.
"""

from app.engines.graph_rag import (
    _detect_ai_board_governance_inquiry,
    _detect_reclassification_inquiry,
)
from app.integrations.regenold.models import normalise_answer_for_regenold


class TestReclassificationNoFalseFire:
    """Fix 1 — the bare 'what actions'/'take actions' cue was dropped, so an
    ordinary 'what actions must a <role> take ... provider ...' obligation
    question no longer ships the wrong Article 25 reclassification verdict."""

    def test_deployer_duty_question_does_not_fire(self):
        assert not _detect_reclassification_inquiry(
            "What actions must a deployer take before using a high-risk AI "
            "system supplied by a provider?"
        )

    def test_importer_duty_question_does_not_fire(self):
        assert not _detect_reclassification_inquiry(
            "What actions must an importer verify before placing a high-risk "
            "AI system of a non-EU provider on the market?"
        )

    def test_serious_incident_question_does_not_fire(self):
        assert not _detect_reclassification_inquiry(
            "What actions must the provider take if the operator detects a "
            "serious incident?"
        )

    def test_genuine_flip_still_fires(self):
        # q025 — 'seen as a provider' is a genuine reclassify signal.
        assert _detect_reclassification_inquiry(
            "Can a deployer take actions such that it can be effectively seen "
            "as a provider? What kind of action would result in that?"
        )


class TestAiBoardNoNotifiedBodyFalseFire:
    """Fix 2 — the bare '(the|a) board' alternation was dropped (a qualified
    name / 'board member(s)' / 'board's <governance-noun>' is required), and a
    notified-body-designation guard was added, so a notified-body question no
    longer ships the Article 65 Board-governance verdict."""

    def test_notified_body_role_question_does_not_fire(self):
        assert not _detect_ai_board_governance_inquiry(
            "Which authority designates notified bodies, and does the Board "
            "play a role?"
        )

    def test_notified_body_suspension_question_does_not_fire(self):
        assert not _detect_ai_board_governance_inquiry(
            "Can the Board suspend or withdraw a notified body designation, "
            "and who designates notified bodies?"
        )

    def test_across_the_board_idiom_does_not_fire(self):
        assert not _detect_ai_board_governance_inquiry(
            "How long do the transitional obligations apply across the board?"
        )

    def test_board_member_term_still_fires(self):
        assert _detect_ai_board_governance_inquiry(
            "How long is a Board member's term and is it renewable?"
        )

    def test_full_board_governance_question_still_fires(self):
        assert _detect_ai_board_governance_inquiry(
            "Regarding the European Artificial Intelligence Board: who "
            "designates its members, how long is the term, and how many times "
            "is it renewable?"
        )


class TestMetaLeakDoesNotDeleteCorrectAbsenceStatements:
    """Fix 3 — the meta-leak strip's bare 'does not appear in the eu ai act'
    entry was made reference-scoped, so a correct statutory-absence sentence
    survives while the meta-refusal leak is still stripped."""

    def test_statutory_absence_sentence_survives(self):
        out = normalise_answer_for_regenold(
            "No. The EU AI Act does not mandate a specific explainability "
            "technique. The term 'artificial general intelligence' does not "
            "appear in the EU AI Act, which is technique-agnostic. Article 13 "
            "requires transparency sufficient to interpret the system output.",
            4,
        )
        assert "artificial general intelligence" in out.lower()

    def test_reference_scoped_meta_refusal_still_stripped(self):
        out = normalise_answer_for_regenold(
            "Article 65 governs the Board. That detail does not appear in the "
            "EU AI Act references block provided. The Board adopts its rules "
            "of procedure by a two-thirds majority.",
            4,
        )
        assert "does not appear in the eu ai act references" not in out.lower()
        assert "two-thirds" in out.lower()

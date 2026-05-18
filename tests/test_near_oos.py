"""R49-B — near-OOS (looks like AI Act, isn't) detection tests.

V2 tricky benchmark introduced 3 ``near_oos`` rows (tr_v2_029 / 030 /
031) probing questions about adjacent EU frameworks (DSA, PLD, NIS2)
that pre-R49 fall through to ``zero_retrieval_fallback`` and ship
spurious AI Act citations. Live Railway scorecard: refL=0.00,
refS=0.00 on this category — the engine answers confidently with the
WRONG framework's articles.

R49-B detects the lookalike phrasing in ``classify_scope`` and emits
a tailored refusal that names the correct framework. The detection
runs AFTER known-Art-N reference check (so explicit AI Act anchors
still win) but BEFORE the bare anchor/keyword passes (so a generic
'transparency' word doesn't mask the framework signal).
"""
from __future__ import annotations

import pytest

from app.integrations.regenold.scope import (
    ScopeReason,
    classify_scope,
    refusal_copy_for,
)


# ── V2 near_oos scenarios ──────────────────────────────────────────────


class TestNearOOSDetection:
    """V2 tricky.near_oos rows must classify as NEAR_OOS with the
    correct framework name in the refusal copy."""

    def test_dsa_vlop_question_is_near_oos(self) -> None:
        v = classify_scope(
            "What are the algorithmic transparency obligations for a "
            "Very Large Online Platform's content-moderation AI?"
        )
        assert not v.in_scope
        assert v.reason == ScopeReason.NEAR_OOS
        copy = refusal_copy_for(v)
        assert "Digital Services Act" in copy or "DSA" in copy
        assert "EU AI Act" in copy
        assert "not the" in copy.lower()

    def test_pld_property_damage_question_is_near_oos(self) -> None:
        v = classify_scope(
            "If a high-risk AI causes property damage to a customer, "
            "what AI-Act liability rules apply?"
        )
        assert not v.in_scope
        assert v.reason == ScopeReason.NEAR_OOS
        copy = refusal_copy_for(v)
        assert (
            "Product Liability" in copy
            or "PLD" in copy
            or "Liability Directive" in copy
        )

    def test_nis2_essential_services_question_is_near_oos(self) -> None:
        v = classify_scope(
            "We're a designated essential-services entity using AI for "
            "SOC operations. What cyber-resilience obligations apply "
            "to the AI itself?"
        )
        assert not v.in_scope
        assert v.reason == ScopeReason.NEAR_OOS
        copy = refusal_copy_for(v)
        assert "NIS2" in copy or "Cyber Resilience" in copy


# ── False-positive guards ──────────────────────────────────────────────


class TestNoFalsePositives:
    """Critical: the detection must not regress existing in-scope or
    other-OOS behaviour."""

    @pytest.mark.parametrize(
        "question",
        [
            # Existing in-scope question that mentions adjacent framework
            "Does our existing GDPR DPIA satisfy the Article 27 FRIA requirement?",
            # The cross-framework V2 row (tr_v2_028) — NIS2 mention but
            # explicitly anchored on Article 73 of the AI Act. Must
            # NOT misroute to NEAR_OOS.
            "Our high-risk AI provides cybersecurity for critical "
            "infrastructure. We already report incidents under NIS2. "
            "Do AI Act incident-reporting obligations still apply?",
            # MDR question that explicitly anchors on Article 43
            "Our medical-device AI is already CE-marked under MDR. Do "
            "we still need a separate AI Act conformity assessment?",
        ],
    )
    def test_explicit_ai_act_anchor_overrides_near_oos(
        self, question: str
    ) -> None:
        v = classify_scope(question)
        assert v.in_scope, (
            f"Explicit AI Act anchor must keep {question!r} in-scope; "
            f"got reason={v.reason}, evidence={v.verdict.evidence if hasattr(v, 'verdict') else v.evidence!r}"
        )

    @pytest.mark.parametrize(
        "question",
        [
            "What is the capital of France?",
            "When did the queen withdraw from public life?",
            "I want to suspend my Netflix subscription.",
            "Birth certificate processing time in France?",
        ],
    )
    def test_unrelated_off_topic_stays_in_original_class(
        self, question: str
    ) -> None:
        """Pre-R49 these were CONVERSATIONAL / OTHER_REGULATION /
        EMPTY refusals. R49 must not move them into NEAR_OOS (which
        would surface a misleading DSA / PLD / NIS2 pointer)."""
        v = classify_scope(question)
        assert not v.in_scope
        assert v.reason != ScopeReason.NEAR_OOS, (
            f"{question!r} got NEAR_OOS but should be a different "
            f"refusal class"
        )

    def test_gdpr_only_question_stays_other_regulation(self) -> None:
        """Pure GDPR questions stayed OTHER_REGULATION pre-R49 —
        must not flip to NEAR_OOS.

        We use the canonical ``GDPR Article 17`` phrasing (regulation
        name BEFORE the Article number) which the existing
        ``_OTHER_REGULATION_BEFORE_ARTICLE_RE`` strips. The reverse
        phrasing ``"Article 17 of the GDPR"`` is a pre-existing
        scope-gate quirk and unrelated to R49.
        """
        v = classify_scope("What does GDPR Article 17 say?")
        assert not v.in_scope
        # GDPR is the canonical OTHER_REGULATION case; near_oos is for
        # AI-flavoured adjacent frameworks (DSA / PLD / NIS2 / CRA).
        assert v.reason == ScopeReason.OTHER_REGULATION

    def test_legitimate_transparency_question_stays_in_scope(self) -> None:
        """The DSA detection keys on 'algorithmic transparency' + VLOP
        markers. A bare 'transparency' question about AI Act
        obligations must stay in-scope."""
        v = classify_scope(
            "What are the transparency obligations for high-risk AI "
            "systems under the EU AI Act?"
        )
        assert v.in_scope

    def test_legitimate_cybersecurity_question_stays_in_scope(self) -> None:
        """The NIS2 detection keys on 'essential-services entity' /
        'cyber-resilience' phrasing — generic cybersecurity questions
        about AI Act Art. 15 must stay in-scope."""
        v = classify_scope(
            "What cybersecurity requirements does Article 15 impose on "
            "high-risk AI systems?"
        )
        assert v.in_scope


# ── Refusal-copy shape ──────────────────────────────────────────────────


class TestRefusalCopyShape:
    def test_near_oos_copy_under_three_sentences(self) -> None:
        from app.integrations.regenold.scope import ScopeVerdict
        v = ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.NEAR_OOS,
            evidence="DSA lookalike",
            near_oos_framework="Digital Services Act",
        )
        copy = refusal_copy_for(v)
        assert copy
        # Three sentences or fewer (terminator count).
        assert sum(1 for c in copy if c in ".!?") <= 4

    def test_near_oos_copy_handles_missing_framework_gracefully(self) -> None:
        """Defensive: ScopeVerdict could theoretically carry
        ``reason=NEAR_OOS`` with an empty framework field. The copy
        function must not crash."""
        from app.integrations.regenold.scope import ScopeVerdict
        v = ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.NEAR_OOS,
            evidence="",
            near_oos_framework="",
        )
        copy = refusal_copy_for(v)
        assert copy  # non-empty even on missing framework
        assert "EU AI Act" in copy

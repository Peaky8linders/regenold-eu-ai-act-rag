"""R51 — complexity classifier tests.

Locks in the trigger surface AND the precision floor — generic AI Act
questions, simple definitional questions, and tone-anchor sample texts
must NOT fire complexity (otherwise we burn Opus + thinking budget on
everything).
"""
from __future__ import annotations

import pytest

from app.engines.question_complexity import is_complex_question


class TestComplexFires:
    """Each canonical V2 row that scored low on the R50 V2 live run
    should be classified as complex."""

    @pytest.mark.parametrize(
        "question",
        [
            # GPAI threshold (tr_v2_003)
            "What's the new GPAI compute threshold from the Commission's July 2025 Guidelines?",
            # GPAI fine-tune rule (tr_v2_006)
            "We're a GPAI provider that fine-tuned another model with 35% of the base model's compute. Did we become the new provider?",
            # GPAI open-weights carve-out (tr_v2_021)
            "Our GPAI is open-weights but we trained at exactly 1×10²⁵ FLOPs. Do we still get the Article 53(2) open-weights carve-out?",
            # Role-ambiguity (tr_v2_007)
            "We built an internal AI for our own HR use — never released externally. Are we a provider or just a deployer?",
            # Role-ambiguity (tr_v2_009)
            "An importer rebrands a high-risk AI under its own name before selling it on. Do they become the provider?",
            # Borderline prohibition (tr_v2_017)
            "We use emotion recognition in a medical-device AI to monitor pain in non-verbal patients. Is that prohibited?",
            # Borderline prohibition (tr_v2_018)
            "Is real-time RBI in public spaces prohibited for police investigating ongoing terrorist attacks?",
            # Conflict (tr_v2_013)
            "Our Annex IV technical documentation contains trade secrets. Article 78 says authorities must keep them confidential — can we refuse to share them under Article 11?",
            # Cross-framework (tr_v2_027)
            "Does our existing GDPR Article 35 DPIA satisfy the Article 27 FRIA requirement?",
            # Cross-framework (tr_v2_026)
            "Our medical-device AI is already CE-marked under MDR. Do we still need a separate AI Act conformity assessment?",
        ],
    )
    def test_complex_row_fires(self, question: str) -> None:
        assert is_complex_question(question), (
            f"V2 weak-axis row not classified complex: {question!r}"
        )

    def test_multi_turn_short_coreferent_fires(self) -> None:
        """3+ prior turns + short coreferent final should fire."""
        assert is_complex_question(
            "What about deployers?", history_turn_count=4,
        )
        assert is_complex_question(
            "And if we're non-EU?", history_turn_count=3,
        )

    def test_multi_turn_short_coreferent_below_threshold_skips(self) -> None:
        """Single-turn short coreference should NOT fire (no prior
        anchor to need extended thinking for)."""
        assert not is_complex_question(
            "What about deployers?", history_turn_count=1,
        )


class TestSimpleSkips:
    """Generic AI Act questions, definitional lookups, and tone-
    anchor examples should NOT fire — we don't want to burn Opus +
    thinking budget on questions Sonnet handles fine."""

    @pytest.mark.parametrize(
        "question",
        [
            # Simple article-lookup
            "What does Article 13 require?",
            # Simple definitional
            "What is an AI system under the EU AI Act?",
            "How is 'deployer' defined?",
            # Tone anchor (must not match!)
            "Providers of high-risk AI systems shall establish a risk "
            "management system per Article 9.",
            # Davidath-style scenario
            "We are a provider offering an AI system intended to be used "
            "as a safety component in machinery for industrial use.",
            # Generic transparency / oversight
            "What are the transparency obligations for high-risk AI systems?",
            "What cybersecurity requirements does Article 15 impose?",
            # Out-of-scope (won't reach Stage-2 anyway, but checking
            # the gate doesn't false-positive)
            "What is the capital of France?",
            "Suspend my Netflix subscription.",
        ],
    )
    def test_simple_skips(self, question: str) -> None:
        assert not is_complex_question(question), (
            f"Simple question over-classified as complex: {question!r}"
        )

    def test_empty_input_skips(self) -> None:
        assert not is_complex_question("")
        assert not is_complex_question("   ")
        assert not is_complex_question(None)  # type: ignore[arg-type]


class TestEdgeCases:
    def test_gpai_acronym_alone_does_not_fire(self) -> None:
        """GPAI mention without a threshold / fine-tune / value-chain
        marker should NOT fire — most GPAI questions Sonnet handles."""
        assert not is_complex_question(
            "What does GPAI mean in the EU AI Act?",
        )

    def test_article_number_mention_does_not_fire(self) -> None:
        """Just citing an Article shouldn't fire — only the
        comparative shape (vs / instead of / can we skip)."""
        assert not is_complex_question(
            "What does Article 99 say about penalties?",
        )

    def test_rebrand_or_substantial_modification_fires(self) -> None:
        """Both R47-C compound-role keywords trigger complexity."""
        assert is_complex_question(
            "If we rebrand a third-party AI as our own, what changes?",
        )
        assert is_complex_question(
            "We made a substantial modification to a CE-marked AI. "
            "Are we now the provider?",
        )


class TestFlattenMarkerStripping:
    """R60 fix — the route flattens multi-turn history as
    ``"Conversation so far:\\n...\\n\\nLatest question:\\n<live>"``. The
    gate must scan only the live-question section, else the ``^``
    anchor in :data:`_SHORT_COREFERENT_RE` can never match the live
    text (it would be preceded by the history prose)."""

    _FLATTEN_PREFIX = (
        "Conversation so far:\n"
        "user: We are a hospital deploying a CE-marked medical-imaging AI.\n"
        "assistant: That system is high-risk under Article 6(1) "
        "since it is safety-related AI listed in Annex I.\n"
        "user: Which regulator do we register with?\n"
        "\n"
        "Latest question:\n"
    )

    def test_short_coreferent_fires_after_flatten_prefix(self) -> None:
        """Short coref final inside the flatten format should fire when
        history depth ≥ 3. Pre-fix this returned False because the
        ``^`` anchor matched only the leading ``"Conversation so far:"``."""
        flattened = self._FLATTEN_PREFIX + "What about deployers?"
        assert is_complex_question(flattened, history_turn_count=4)

    def test_role_ambiguity_still_fires_after_flatten_prefix(self) -> None:
        """Position-independent patterns (``\\b...\\b``) already fired
        before the fix; verify the fix preserves that behaviour."""
        flattened = self._FLATTEN_PREFIX + (
            "Are we a provider or just a deployer if the customer "
            "configures the model?"
        )
        assert is_complex_question(flattened, history_turn_count=4)

    def test_simple_followup_does_not_fire_after_flatten_prefix(self) -> None:
        """A simple final ("What does the article say?") inside the
        flatten format should NOT fire — burns Opus budget for nothing."""
        flattened = self._FLATTEN_PREFIX + "What does the article say?"
        assert not is_complex_question(flattened, history_turn_count=4)

    def test_rfind_uses_last_marker_occurrence(self) -> None:
        """A scenario where the prior assistant turn happens to quote
        the marker text. ``rfind`` should anchor on the FINAL occurrence
        so the live question is scanned, not the quoted text."""
        flattened = (
            "Conversation so far:\n"
            "user: I asked 'Latest question:\\nWhat is Art. 6?' earlier.\n"
            "assistant: I answered with the high-risk definition.\n"
            "\n"
            "Latest question:\n"
            "What about deployers?"
        )
        assert is_complex_question(flattened, history_turn_count=4)

    def test_empty_live_section_after_marker_returns_false(self) -> None:
        """Marker present but no actual live text → False (don't
        accidentally fire complexity on a malformed prompt)."""
        flattened = self._FLATTEN_PREFIX + "   \n"
        assert not is_complex_question(flattened, history_turn_count=4)

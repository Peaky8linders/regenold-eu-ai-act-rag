"""Legal-tone dash/ellipsis normalisation.

User directive: wire answers must read as concise EU AI Act legal prose —
no ellipses (``...`` / ``…``) and no dash *separators* (em-dash ``—``,
en-dash ``–``, or a spaced hyphen ``" - "`` used as a clause break).

CRITICAL: intra-word hyphens in standard legal terminology
("high-risk", "socio-economic", "post-market", "call-centre",
"AI-generated", "one-third") MUST be preserved — they are correct
regulatory wording, not dash separators.
"""
from __future__ import annotations

import pytest

from app.integrations.regenold.answer_normaliser import strip_dash_separators
from app.integrations.regenold.models import normalise_answer_for_regenold

EM = "—"  # —
EN = "–"  # –


class TestStripDashSeparators:
    def test_em_dash_clause_separator_becomes_comma(self):
        out = strip_dash_separators(
            f"Training-data content summary {EM} the Commission adopted the template."
        )
        assert EM not in out
        assert "summary, the Commission adopted the template." in out

    def test_paired_em_dash_parenthetical_becomes_commas(self):
        out = strip_dash_separators(
            f"the core GPAI obligations {EM} maintaining documentation, a summary, "
            f"and a copyright policy (Article 53) {EM} rather than relying upstream."
        )
        assert EM not in out
        assert "obligations, maintaining documentation" in out
        assert "(Article 53), rather than relying upstream." in out

    def test_em_dash_without_surrounding_spaces(self):
        out = strip_dash_separators(f"workplace{EM}including call centres")
        assert EM not in out
        assert "workplace, including call centres" == out

    def test_en_dash_separator_becomes_comma(self):
        out = strip_dash_separators(f"voluntary {EN} providers may use any means.")
        assert EN not in out
        assert "voluntary, providers may use any means." == out

    def test_numeric_range_em_dash_becomes_to(self):
        out = strip_dash_separators(f"grandfathered until 2 August 2025{EM}2027.")
        assert EM not in out
        assert "2025 to 2027." in out

    def test_numeric_range_en_dash_becomes_to(self):
        out = strip_dash_separators(f"compute of 10{EN}25 FLOPs")
        assert "compute of 10 to 25 FLOPs" == out

    def test_spaced_hyphen_used_as_dash_becomes_comma(self):
        out = strip_dash_separators("the provider must register - see Article 49.")
        assert "the provider must register, see Article 49." == out

    # ── intra-word hyphen preservation (the load-bearing guard) ──
    @pytest.mark.parametrize(
        "term",
        [
            "high-risk AI systems",
            "socio-economic situation",
            "post-market monitoring",
            "call-centre agents",
            "AI-generated content",
            "one-third of the base compute",
            "free and open-source models",
            "real-time remote biometric identification",
            "co-operation and cross-border",
        ],
    )
    def test_intra_word_hyphen_preserved(self, term):
        assert strip_dash_separators(term) == term

    def test_full_sentence_with_compounds_and_em_dash(self):
        src = (
            f"High-risk AI systems must register {EM} post-market monitoring "
            "applies to AI-generated content."
        )
        out = strip_dash_separators(src)
        assert "High-risk" in out
        assert "post-market" in out
        assert "AI-generated" in out
        assert EM not in out
        assert "must register, post-market" in out

    # ── robustness ──
    def test_idempotent(self):
        src = f"a {EM} b {EN} c - d, 2024{EM}2027."
        once = strip_dash_separators(src)
        twice = strip_dash_separators(once)
        assert once == twice

    def test_leading_dash_dropped(self):
        out = strip_dash_separators(f"{EM} Article 5 prohibits manipulation.")
        assert out.startswith("Article 5 prohibits")

    def test_terminator_then_dash_no_period_comma(self):
        # Em-dash starting a new sentence after a terminator must keep the
        # sentence break, never produce a "., " period-comma artifact.
        out = strip_dash_separators(f"First sentence. {EM} Second clause.")
        assert "., " not in out
        assert ".," not in out
        assert out == "First sentence. Second clause."

    def test_terminator_then_dash_preserves_eg_comma(self):
        # The terminator rule must not eat a legitimate "e.g.," comma
        # (there is no dash there).
        out = strip_dash_separators("Examples (e.g., the following) apply.")
        assert "e.g., the following" in out

    def test_no_double_comma_artifact(self):
        out = strip_dash_separators(f"obligations, {EM} maintaining documentation.")
        assert ",," not in out
        assert " ," not in out

    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_empty_or_none_passthrough(self, bad):
        assert strip_dash_separators(bad) == bad

    def test_no_dash_unchanged(self):
        src = "Article 13 requires high-risk AI systems to be transparent."
        assert strip_dash_separators(src) == src


class TestNormaliseAnswerStripsDashes:
    """The universal wire normaliser must ship no em/en dashes or ellipses."""

    def test_normalise_strips_em_dash(self):
        out = normalise_answer_for_regenold(
            f"Article 51 classifies a GPAI model {EM} systemic risk applies "
            "above the compute threshold."
        )
        assert EM not in out
        assert "Article 51" in out

    def test_normalise_strips_ellipsis(self):
        out = normalise_answer_for_regenold(
            "Article 5 prohibits social scoring and untargeted scraping..."
        )
        assert "..." not in out
        assert "…" not in out

    def test_normalise_preserves_compound_hyphens(self):
        out = normalise_answer_for_regenold(
            "High-risk AI systems require post-market monitoring under Article 72."
        )
        assert "High-risk" in out
        assert "post-market" in out

    def test_normalise_clean_answer_has_no_dash_separators(self):
        out = normalise_answer_for_regenold(
            f"Article 50 requires disclosure {EM} AI-generated content must be "
            f"labelled {EN} deepfakes included."
        )
        assert EM not in out and EN not in out
        assert "AI-generated" in out

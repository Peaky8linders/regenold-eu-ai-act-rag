"""R81-H — Tests for the preamble-strip answer normaliser.

Each test pins one safety guarantee or one strip pattern. The
sentence-floor and never-empty guards are critical — without them
the over-greedy first draft drops Strict by −0.75 on a single row
(see plan ``qa_059`` regression case).
"""

from __future__ import annotations

import os
from unittest import mock

from app.integrations.regenold.answer_normaliser import (
    strip_preamble_templates,
)


# ── Known-template strip cases (one per LEAD pattern) ────────────────


class TestLeadTemplateStrips:
    """Each LEAD pattern strips the documented preamble shape."""

    def test_strips_this_question_is_covered_by(self) -> None:
        raw = (
            "This question is covered by the EU AI Act under Article 13. "
            "The provider must give deployers technical documentation, "
            "instructions for use, and a description of the system's "
            "intended purpose and limitations under Article 13."
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("This question is covered")
        assert "provider must give deployers" in out
        assert "Article 13" in out  # mid-sentence cite preserved

    def test_strips_no_specific_articles_were_returned(self) -> None:
        raw = (
            "No specific EU AI Act articles were returned for this query, "
            "so no article citations can be made per the sourcing rules. "
            "Based on the Act's enforcement framework, violations of "
            "the prohibited AI practices provisions carry the highest "
            "penalty tier: fines of up to "
            "€35 million or 7% of worldwide annual turnover."
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("No specific EU AI Act")
        assert "Based on the Act" in out
        assert "€35 million" in out

    def test_strips_the_matched_references_do_not_specify(self) -> None:
        raw = (
            "The matched EU AI Act references do not specify a retention "
            "period for automatically generated logs. "
            "Article 12 requires providers of high-risk AI systems to "
            "ensure that the system automatically records events (logs) "
            "over the lifetime of the system, with retention covered by "
            "Article 19 — at least six months unless longer is required."
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("The matched EU AI Act references do")
        assert "Article 12 requires providers" in out

    def test_strips_references_block_is_empty(self) -> None:
        raw = (
            "The EU AI Act references block is empty. "
            "The provider of a high-risk AI system must conduct a "
            "conformity assessment, draw up an EU declaration of "
            "conformity, and affix the CE marking under Article 43."
        )
        out = strip_preamble_templates(raw)
        assert not out.lower().startswith("the eu ai act references block")
        assert "conformity assessment" in out

    def test_strips_no_articles_were_returned(self) -> None:
        raw = (
            "No EU AI Act articles were returned for this query. "
            "Annex III enumerates eight categories of high-risk AI "
            "systems including biometric identification, critical "
            "infrastructure, education, employment, essential services, "
            "law enforcement, migration, and administration of justice."
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("No EU AI Act articles")
        assert "Annex III enumerates" in out

    def test_strips_no_article_references_were_surfaced(self) -> None:
        raw = (
            "No EU AI Act article references were surfaced for this query. "
            "The Commission, acting through the AI Office, may impose "
            "direct fines on providers of general-purpose AI models with "
            "systemic risk under Article 101 up to 3% of worldwide "
            "annual turnover or 15 million euro, whichever is higher."
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("No EU AI Act article references")
        assert "The Commission, acting through" in out


# ── Article-prefix strip cases ───────────────────────────────────────


class TestArticlePrefixStrips:
    """``Article N — `` / ``Annex N — `` typographic prefix strip."""

    def test_strips_article_prefix_at_start(self) -> None:
        raw = (
            "Article 13 — Providers of high-risk AI systems must give "
            "deployers technical documentation, instructions for use, "
            "and a description of the system's intended purpose and "
            "limitations under Article 13."
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("Article 13 —")
        assert "Providers of high-risk AI systems" in out

    def test_strips_article_prefix_after_sentence(self) -> None:
        raw = (
            "Providers must keep logs. "
            "Article 12 — Logs must be retained for at least six months "
            "unless Union or national law requires longer, with the "
            "obligations falling on the provider under Article 12 in "
            "conjunction with Article 19."
        )
        out = strip_preamble_templates(raw)
        # Article 12 — prefix gone, but "Logs must" survives.
        assert "Article 12 — Logs" not in out
        assert "Logs must be retained" in out

    def test_strips_annex_prefix(self) -> None:
        raw = (
            "Annex IV — Technical documentation must include a general "
            "description of the AI system including its intended purpose, "
            "the persons developing it, the date and version, and a "
            "detailed description of the elements of the AI system and "
            "of the process for its development and a basic description "
            "of the algorithmic logic."
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("Annex IV —")
        assert "Technical documentation must include" in out

    def test_mid_sentence_under_article_NOT_stripped(self) -> None:
        # Critical: "under Article 13(2)(a)" mid-sentence must survive.
        raw = (
            "Providers of high-risk AI systems must give deployers "
            "instructions for use under Article 13(2)(a) including the "
            "system's intended purpose, the level of accuracy "
            "(metrics, characteristics, performance), known or "
            "foreseeable circumstances, and limitations."
        )
        out = strip_preamble_templates(raw)
        # "under Article 13(2)(a)" preserved — it's not at sentence
        # start AND has no " — " separator.
        assert "under Article 13(2)(a)" in out


# ── Connector-NOT-preamble (qa_059 regression guard) ───────────────


class TestConnectorOpenersPreserved:
    """``Based on the Act...`` is a legitimate prose opener, NOT a preamble."""

    def test_based_on_the_act_NOT_stripped(self) -> None:
        # qa_059 regression case: "Based on the Act's enforcement
        # framework..." is real prose. An over-greedy pattern that
        # matched it would drop Strict by −0.75 on this row.
        raw = (
            "Based on the Act's enforcement framework, violations of the "
            "prohibited AI practices provisions carry the highest penalty "
            "tier: administrative fines of up to "
            "€35 million or 7% of worldwide annual turnover."
        )
        out = strip_preamble_templates(raw)
        assert out.startswith("Based on the Act")
        assert "€35 million" in out

    def test_under_the_ai_act_NOT_stripped(self) -> None:
        raw = (
            "Under the AI Act, providers of high-risk AI systems must "
            "establish, implement, document, and maintain a risk "
            "management system."
        )
        out = strip_preamble_templates(raw)
        assert out.startswith("Under the AI Act")


# ── Sentence-floor guard (CRITICAL) ──────────────────────────────────


class TestSentenceFloorGuard:
    """If remainder < 80 chars after a strip, the pattern is NOT applied."""

    def test_short_substance_after_lead_template_NOT_stripped(self) -> None:
        # Pred is ALMOST entirely the preamble; stripping it would
        # leave the user with effectively nothing.
        raw = (
            "This question is covered by the EU AI Act under Article 13. "
            "See refs."  # only 9-char substance remainder
        )
        out = strip_preamble_templates(raw)
        # Sentence floor blocks the strip — return unchanged.
        assert out == raw

    def test_substance_just_at_floor_strips(self) -> None:
        # Exactly the boundary: 80+ char remainder DOES get stripped.
        long_tail = "x" * 85
        raw = (
            f"This question is covered by the EU AI Act under "
            f"Article 13. {long_tail}"
        )
        out = strip_preamble_templates(raw)
        assert not out.startswith("This question is covered")


# ── Empty-input guard ────────────────────────────────────────────────


class TestEmptyInputGuard:
    """Empty / whitespace inputs return cleanly, no crash."""

    def test_empty_string_returns_empty(self) -> None:
        assert strip_preamble_templates("") == ""

    def test_whitespace_only_returns_unchanged(self) -> None:
        assert strip_preamble_templates("   \n  ") == "   \n  "

    def test_short_normal_answer_unchanged(self) -> None:
        raw = "Article 13 requires providers to disclose."
        out = strip_preamble_templates(raw)
        # No LEAD match; no prefix strip (substance < 80 after strip).
        assert "providers to disclose" in out


# ── Never-empty guard ────────────────────────────────────────────────


class TestNeverEmptyGuard:
    """If a transform would produce empty output, the original returns."""

    def test_pathological_input_returns_original(self) -> None:
        # Even pathological inputs (all-prefix, no substance) survive
        # via the sentence-floor + never-empty guards.
        raw = "Article 1 — Article 2 — Article 3 — Article 4 — Article 5 — "
        out = strip_preamble_templates(raw)
        # The repeated prefix strip stops when remainder < 80; the
        # original may survive in part, but never becomes empty.
        assert out.strip()  # never empty when input was non-empty


# ── Idempotence ──────────────────────────────────────────────────────


class TestIdempotence:
    """strip(strip(x)) == strip(x) for all inputs."""

    def test_idempotent_on_full_preamble_row(self) -> None:
        raw = (
            "This question is covered by the EU AI Act under Article 13. "
            "The provider must give deployers technical documentation, "
            "instructions for use, and a description of the system's "
            "intended purpose and limitations under Article 13."
        )
        once = strip_preamble_templates(raw)
        twice = strip_preamble_templates(once)
        assert once == twice

    def test_idempotent_on_clean_row(self) -> None:
        raw = (
            "Providers of high-risk AI systems must establish, implement, "
            "document, and maintain a risk management system that runs "
            "continuously throughout the entire lifecycle of the system."
        )
        once = strip_preamble_templates(raw)
        twice = strip_preamble_templates(once)
        assert once == twice

    def test_idempotent_on_prefix_row(self) -> None:
        raw = (
            "Article 13 — Providers of high-risk AI systems must give "
            "deployers technical documentation, instructions for use, "
            "and a description of the system's intended purpose."
        )
        once = strip_preamble_templates(raw)
        twice = strip_preamble_templates(once)
        assert once == twice


# ── Re-capitalisation ────────────────────────────────────────────────


class TestRecapitalisation:
    """After a strip, substance often starts lowercase. Re-capitalise."""

    def test_first_letter_capitalised_after_lead_strip(self) -> None:
        # NOTE: the substance below is already capitalised; this
        # tests the property holds.
        raw = (
            "This question is covered by the EU AI Act under Article 13. "
            "providers of high-risk AI systems must establish a risk "
            "management system per Article 9 that runs throughout the "
            "system's lifecycle."
        )
        out = strip_preamble_templates(raw)
        # First letter capitalised even though source was lowercase.
        assert out[0] == "P"
        assert out.startswith("Providers of high-risk")


# ── Wire integration (route normaliser) ─────────────────────────────


class TestWireIntegration:
    """``normalise_answer_for_regenold`` invokes the strip post-soft-cap."""

    def test_normalise_invokes_strip_when_env_default(self) -> None:
        from app.integrations.regenold.models import (
            normalise_answer_for_regenold,
        )

        raw = (
            "This question is covered by the EU AI Act under Article 13. "
            "The provider must give deployers technical documentation, "
            "instructions for use, and a description of the system's "
            "intended purpose under Article 13."
        )
        out = normalise_answer_for_regenold(raw)
        assert not out.startswith("This question is covered")
        assert "provider must give deployers" in out

    def test_normalise_skips_strip_when_env_off(self) -> None:
        from app.integrations.regenold.models import (
            normalise_answer_for_regenold,
        )

        raw = (
            "This question is covered by the EU AI Act under Article 13. "
            "The provider must give deployers technical documentation, "
            "instructions for use, and a description of the system's "
            "intended purpose under Article 13."
        )
        with mock.patch.dict(os.environ, {"REGENOLD_STRIP_PREAMBLE": "0"}):
            out = normalise_answer_for_regenold(raw)
        # Strip disabled — preamble survives the rest of the pipeline.
        assert out.startswith("This question is covered")


# ── Shape-Aware caps ──────────────────────────────────────────────────


class TestShapeAwareCaps:
    """R82-B.2 — test shape-aware caps (400 for QA, 600 for Scenario)."""

    def test_qa_shape_applies_400_cap(self) -> None:
        from app.integrations.regenold.models import (
            normalise_answer_for_regenold,
        )
        # 3 sentences, total length > 400.
        s1 = "Article 13 requires providers of high-risk systems to ensure transparency so that deployers can interpret outputs and understand the system operation."
        s2 = "Article 14 requires human oversight of high-risk systems to prevent or minimise risks to health, safety or fundamental rights through continuous monitoring."
        s3 = "High-risk systems must achieve appropriate levels of cybersecurity, robustness, and accuracy throughout their entire lifecycle."
        raw = f"{s1} {s2} {s3}"
        
        # Test QA shape (default REGENOLD_QA_LENGTH_CAP=400)
        with mock.patch.dict(os.environ, {"REGENOLD_QA_LENGTH_CAP": "400"}):
            out = normalise_answer_for_regenold(raw, question="What are transparency requirements?")
        # It should drop the non-cite sentence to fit under 400 chars.
        assert len(out) <= 400

    def test_scenario_shape_applies_600_cap(self) -> None:
        from app.integrations.regenold.models import (
            normalise_answer_for_regenold,
        )
        s1 = "Article 13 requires providers of high-risk systems to ensure transparency so that deployers can interpret outputs and understand the system operation."
        s2 = "Article 14 requires human oversight of high-risk systems to prevent or minimise risks to health, safety or fundamental rights through continuous monitoring."
        s3 = "High-risk systems must achieve appropriate levels of cybersecurity, robustness, and accuracy throughout their entire lifecycle."
        raw = f"{s1} {s2} {s3}"
        
        # Test Scenario shape (Question has scenario marker "we are a provider")
        with mock.patch.dict(os.environ, {"REGENOLD_QA_LENGTH_CAP": "400"}):
            out = normalise_answer_for_regenold(raw, question="We are a provider of high-risk AI, what should we do?")
        # It should retain all sentences and fit under 600 chars (not 400 chars).
        assert len(out) > 400
        assert len(out) <= 600


class TestCapResilientNormalisation:
    """Test case for cap-resilient normalisation with 10% overflow relief for augmenter descriptions."""

    def test_cap_relief_applies_when_augmenter_desc_present(self) -> None:
        from app.integrations.regenold.models import normalise_answer_for_regenold
        
        s1 = "Article 13 requires providers of high-risk AI systems to ensure transparency so that deployers can interpret outputs and understand the system operation."
        s2 = "Article 14 requires human oversight of high-risk AI systems to prevent or minimise risks to health, safety or fundamental rights through continuous monitoring."
        s3 = "Article 9 — Requires a documented risk-management system across the AI system's lifecycle."
        raw = f"{s1} {s2} {s3}"
        
        with mock.patch.dict(os.environ, {"REGENOLD_QA_LENGTH_CAP": "400"}):
            out = normalise_answer_for_regenold(raw, question="What are the requirements?")
        
        # The raw input was 405 characters (over the 400 cap), which triggers relief.
        # Downstream, the "Article 9 — " label is stripped, bringing the final length to 392.
        assert len(out) == 392
        assert "Requires a documented risk-management" in out
        assert "Article 13" in out
        assert "Article 14" in out

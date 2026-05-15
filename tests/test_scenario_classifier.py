"""Tests for the davidath-scenario fast-path classifier."""
from __future__ import annotations

import pytest

from app.engines.scenario_classifier import (
    ScenarioVerdict,
    classify_scenario_query,
)


class TestRoleDetection:
    def test_provider_we_are(self):
        q = "We are a provider, offering a chatbot."
        v = classify_scenario_query(q)
        # Falls through to limited-risk since chatbot triggers Art. 50.
        assert v is not None
        assert v.role == "provider"

    def test_deployer_we_are(self):
        q = "We are a deployer, deploying a subliminal influence engine."
        v = classify_scenario_query(q)
        assert v is not None
        assert v.role == "deployer"

    def test_no_role_returns_none(self):
        q = "What is Article 5?"
        assert classify_scenario_query(q) is None


class TestRiskPyramidOrdering:
    def test_prohibited_wins_over_high_risk(self):
        q = (
            "We are a provider offering a subliminal influence platform that "
            "also processes employment data."
        )
        v = classify_scenario_query(q)
        assert v is not None
        # Subliminal wins even though "employment" would have matched high-risk.
        assert v.risk_level == "prohibited"
        assert "Art. 5" in v.articles

    def test_high_risk_employment(self):
        q = (
            "We are a deployer using an AI for worker monitoring and "
            "performance evaluation of workers."
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "high-risk"
        assert "Art. 6" in v.articles
        # Deployer high-risk bolt-on must include Art. 26.
        assert "Art. 26" in v.articles

    def test_limited_chatbot(self):
        q = "We are a provider offering a chatbot that interacts with natural persons."
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "limited"
        assert "Art. 50" in v.articles

    def test_minimal_spam_filter(self):
        q = "We are a provider offering a spam filter for email."
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "minimal"
        assert "Art. 4" in v.articles


class TestUnicodeNormalisation:
    def test_non_breaking_hyphen_low_frequency(self):
        # Real davidath scenario uses non-breaking hyphen.
        q = "We are a provider offering a system with low‑frequency tones."
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "prohibited"

    def test_non_breaking_space(self):
        # Real davidath scenarios sprinkle U+00A0 between tokens.
        q = "We are a provider offering a subliminal influence platform."
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "prohibited"


class TestAnswerShape:
    def test_prohibited_answer_cites_article_5(self):
        q = "We are a provider running a subliminal manipulation system."
        v = classify_scenario_query(q)
        assert v is not None
        assert "Article 5" in v.answer
        # Should mention the role.
        assert "provider" in v.answer.lower()

    def test_high_risk_answer_cites_article_6(self):
        q = (
            "We are a provider offering a high-risk worker monitoring "
            "system in the employment domain."
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert "Article 6" in v.answer
        # Articles 9-15 spine should be mentioned.
        assert "Articles 9 to 15" in v.answer or "Article 9" in v.answer


class TestNoFalsePositives:
    def test_empty_string(self):
        assert classify_scenario_query("") is None

    def test_definitional_question(self):
        # Definitional question with no role marker — must NOT fast-path.
        assert classify_scenario_query("What is Article 5 of the AI Act?") is None

    def test_role_without_risk_marker(self):
        # Role marker present but no risk-pyramid marker — must NOT fast-path,
        # otherwise we'd misclassify generic provider questions as minimal.
        q = "We are a provider. What documentation must we retain?"
        assert classify_scenario_query(q) is None

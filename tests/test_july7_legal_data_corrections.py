"""Regression tests for legal-data defects exposed by the July 7 live run."""
from __future__ import annotations

from app.data.article_requirements_full import ARTICLE_REQUIREMENTS


def test_deployer_log_requirement_is_article_26_paragraph_6() -> None:
    paragraphs = ARTICLE_REQUIREMENTS["Art. 26"]["paragraphs"]

    assert "26(6)" in paragraphs
    assert "26(7)" not in paragraphs
    assert "six months" in paragraphs["26(6)"]["text"]


def test_fria_requirement_carries_annex_iii_point_two_exception() -> None:
    text = ARTICLE_REQUIREMENTS["Art. 27"]["paragraphs"]["27(1)"]["text"].lower()

    assert "except" in text
    assert "annex iii point 2" in text
    assert "critical-infrastructure" in text


def test_article_50_deepfake_and_public_interest_text_exceptions_are_separate() -> None:
    text = ARTICLE_REQUIREMENTS["Art. 50"]["paragraphs"]["50(4)"]["text"].lower()

    assert "artistic" in text
    assert "human review" in text
    assert "public-interest text" in text
    assert "separate" in text

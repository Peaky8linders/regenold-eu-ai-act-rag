"""Article 42 adopted-text contract for the delivered KB stub and answer prompt.

Article 42(1) presumes compliance with "the relevant requirements laid down in
Article 10(4)" only. Article 10(3) (relevance, representativeness, freedom from
errors, completeness, statistical properties) is a separate paragraph that the
presumption does not name. These tests pin the shipped KB stub and the
ANSWER_GENERATE_SYSTEM factual guard to that verbatim text, so a later edit
cannot widen the presumption to Article 10(3) or drop the Article 42(2)
cybersecurity limb without a test failing.
"""
from __future__ import annotations

from app.data.graph_rag_prompt_templates import ANSWER_GENERATE_SYSTEM
from app.data.kb import EC_CHECKER_OBLIGATION_MAP
from app.data.official_eu_ai_act import OFFICIAL_ARTICLE_TEXT

STUB = EC_CHECKER_OBLIGATION_MAP["Art. 42"]["summary"]
ARTICLE_42_TEXT = OFFICIAL_ARTICLE_TEXT["Article 42"]


def test_official_article_42_1_text_cross_references_only_article_10_4() -> None:
    assert (
        "presumed to comply with the relevant requirements laid down in Article 10(4)"
        in ARTICLE_42_TEXT
    )
    assert "Article 10(3)" not in ARTICLE_42_TEXT


def test_article_10_3_and_10_4_are_distinct_in_the_official_corpus() -> None:
    from app.data.provision_text import get_provision_text

    paragraph_3 = get_provision_text("Article 10(3)")
    paragraph_4 = get_provision_text("Article 10(4)")
    assert paragraph_3 and "sufficiently representative" in paragraph_3
    assert paragraph_3 and "appropriate statistical properties" in paragraph_3
    assert paragraph_4 and "characteristics or elements" in paragraph_4
    assert paragraph_4 and "specific geographical" in paragraph_4


def test_stub_anchors_the_42_1_presumption_on_article_10_4_only() -> None:
    assert "Art. 42(1)" in STUB
    assert "presumed to comply" in STUB
    assert "Art. 10(4)" in STUB
    assert "10(3)" not in STUB
    for setting in ("geographical", "behavioural", "contextual", "functional"):
        assert setting in STUB


def test_stub_keeps_the_separate_article_42_2_presumption() -> None:
    assert "Art. 42(2)" in STUB
    assert "Regulation (EU) 2019/881" in STUB
    assert "cybersecurity requirements of Art. 15" in STUB
    # Article 42(2) applies only "in so far as" the certificate covers them.
    assert "to the extent the cybersecurity certificate or statement covers" in STUB


def test_prompt_guard_scopes_the_presumption_to_article_10_4() -> None:
    assert "Article 42(1) presumes conformity with Article 10(4)" in ANSWER_GENERATE_SYSTEM
    assert (
        "It is not a presumption about Article 10(3) and not an exemption from the "
        "rest of Article 10." in ANSWER_GENERATE_SYSTEM
    )


def test_unstable_gold_is_source_corrected_with_history_preserved() -> None:
    """Eval-data pin: the reconstructed gold for this question is source-corrected.

    The pre-correction criterion read Article 42(1) as a presumption about
    Article 10(3); the revision follows the adopted text and keeps the old
    values under ``_pre_r448``.
    """
    from evals.official.score_arm import load_gold

    gold = load_gold()["rg_036"]
    assert gold["criteria_unstable"] is False
    assert gold["_revised"] == "R448"
    assert "Article 10(4)" in gold["criteria"][0]
    assert "Article 10(3)" not in gold["criteria"][0]
    assert gold["expected_refs"] == ["Article 42.1"]
    assert gold["_pre_r448"]["criteria_unstable"] is True
    assert gold["_pre_r448"]["expected_refs"] == ["Article 10.4"]
    assert "Article 10(3)" in gold["_pre_r448"]["criteria"][0]
    assert (
        "does not expressly state whether the presumption has any broader implication"
        in gold["reference_answer"]
    )

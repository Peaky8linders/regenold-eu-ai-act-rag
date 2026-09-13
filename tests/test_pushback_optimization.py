"""Unit tests for Answer/Reference Correctness, XML Channeling, and Pushback Resilience."""
from __future__ import annotations

from app.security.prompt_guard import extract_xml_channels
from app.routes.regenold import (
    _build_question_from_history,
    _prose_mention_is_real_citation,
)


def test_extract_xml_channels_with_reasoning_scratchpad_and_answer():
    raw = (
        "<reasoning_scratchpad>\n"
        "- Turn 1 cited Article 53(1)(a)-(d).\n"
        "- The previous answer was correct.\n"
        "- Retaining exact 4 citations.\n"
        "</reasoning_scratchpad>\n\n"
        "<answer>\n"
        "Providers of general-purpose AI models must draw up technical documentation "
        "(Article 53(1)(a)) and make information available (Article 53(1)(b)).\n"
        "</answer>"
    )
    clean_answer, reasoning = extract_xml_channels(raw)
    assert clean_answer == (
        "Providers of general-purpose AI models must draw up technical documentation "
        "(Article 53(1)(a)) and make information available (Article 53(1)(b))."
    )
    assert "Turn 1 cited Article 53" in reasoning
    assert "<answer>" not in clean_answer
    assert "<reasoning_scratchpad>" not in clean_answer


def test_extract_xml_channels_with_reasoning_tag():
    raw = (
        "<reasoning>\n"
        "Testing the reasoning block extraction.\n"
        "</reasoning>\n\n"
        "<answer>\n"
        "Article 5 prohibits social scoring.\n"
        "</answer>"
    )
    clean_answer, reasoning = extract_xml_channels(raw)
    assert clean_answer == "Article 5 prohibits social scoring."
    assert reasoning == "Testing the reasoning block extraction."


def test_extract_xml_channels_fallback_no_answer_tags():
    raw = (
        "<scratchpad>Internal thoughts only</scratchpad>\n"
        "Article 50 requires transparency for AI systems interacting with humans."
    )
    clean_answer, reasoning = extract_xml_channels(raw)
    assert clean_answer == "Article 50 requires transparency for AI systems interacting with humans."
    assert reasoning == "Internal thoughts only"


def test_extract_xml_channels_empty():
    clean_answer, reasoning = extract_xml_channels(None)
    assert clean_answer == ""
    assert reasoning == ""

    clean_answer, reasoning = extract_xml_channels("")
    assert clean_answer == ""
    assert reasoning == ""


def test_prose_mention_negation_ahead_guard():
    # "Article 50 does not apply" -> should be rejected as a citation
    prose = "Article 50 does not apply to this backend model."
    start = prose.find("Article 50")
    end = start + len("Article 50")
    assert _prose_mention_is_real_citation(prose, start, end) is False

    # "Annex III is not applicable" -> rejected
    prose2 = "Annex III is not applicable in this scenario."
    start2 = prose2.find("Annex III")
    end2 = start2 + len("Annex III")
    assert _prose_mention_is_real_citation(prose2, start2, end2) is False

    # "Article 6 is excluded" -> rejected
    prose3 = "Article 6 is excluded from consideration."
    start3 = prose3.find("Article 6")
    end3 = start3 + len("Article 6")
    assert _prose_mention_is_real_citation(prose3, start3, end3) is False

    # Affirmative citation: "Under Article 53(1), providers must..." -> accepted
    prose_aff = "Under Article 53(1), providers of GPAI models must maintain technical documentation."
    start_aff = prose_aff.find("Article 53")
    end_aff = start_aff + len("Article 53")
    assert _prose_mention_is_real_citation(prose_aff, start_aff, end_aff) is True


def test_build_question_from_history_recovers_root_question_on_evaluator_pushback():
    class DummyMsg:
        def __init__(self, role: str, content: str):
            self.role = role
            self.content = content

    pushback_text = (
        "I don't think this is correct. Maybe your answer contains hallucinations.\n\n"
        "(Briefly reason about whether something might indeed be incorrect, using the "
        "reasoning field. Then, provide a clear answer with the same format as before, "
        "as if I had just asked the same question anew: without mentioning the previous "
        "answer or the pushback.)"
    )

    messages = [
        DummyMsg("user", "What are the transparency obligations for general-purpose AI model providers under Article 53?"),
        DummyMsg("assistant", "Under Article 53(1), providers must draw up technical documentation..."),
        DummyMsg("user", pushback_text),
    ]

    res = _build_question_from_history(messages)
    assert res.resolved_question == "What are the transparency obligations for general-purpose AI model providers under Article 53?"
    assert res.self_contained_focus is True
    assert "Target inquiry to answer:" in res[0]
    assert "What are the transparency obligations for general-purpose AI model providers under Article 53?" in res[0]

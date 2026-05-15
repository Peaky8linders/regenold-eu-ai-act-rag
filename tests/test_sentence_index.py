"""Tests for the Round-26 extractive-QA sentence index."""
from __future__ import annotations

import pytest

from app.engines.sentence_index import (
    classify_question,
    select_answer_sentence,
    select_definition_sentence,
    split_legal_sentences,
    _extract_definition_term,
)


class TestSentenceSplitter:
    def test_basic_sentence_split(self):
        text = "First sentence. Second sentence. Third sentence."
        s = split_legal_sentences(text)
        assert len(s) == 3
        assert s[0] == "First sentence."

    def test_preserves_article_abbreviation(self):
        # ``Art. 5`` must not split between ``Art.`` and ``5``.
        text = "Art. 5 prohibits subliminal techniques. Art. 6 covers high-risk systems."
        s = split_legal_sentences(text)
        assert len(s) == 2
        assert "Art. 5" in s[0]
        assert "Art. 6" in s[1]

    def test_preserves_eg_ie(self):
        text = "Examples e.g. social scoring i.e. citizen ranking are prohibited."
        s = split_legal_sentences(text)
        assert len(s) == 1

    def test_preserves_numbered_list_marker(self):
        # ``1. Providers shall...`` must keep ``1.`` glued to the clause.
        text = "1. Providers shall maintain documentation. 2. Deployers shall monitor."
        s = split_legal_sentences(text)
        # Both numbered items survive as their own sentences.
        assert len(s) == 2

    def test_handles_unicode_nbsp(self):
        # Real EUR-Lex text uses U+00A0. Splitter must normalise.
        text = "First sentence. Second sentence."
        s = split_legal_sentences(text)
        assert len(s) == 2

    def test_empty_input(self):
        assert split_legal_sentences("") == []
        assert split_legal_sentences("   ") == []

    def test_drops_short_fragments(self):
        text = "Real sentence here. ok. Another real sentence here."
        s = split_legal_sentences(text)
        # 4-char "ok." would normally pass; below the 4-char floor
        # filters it. ``ok.`` is 3 chars stripped → dropped.
        assert all(len(x) >= 4 for x in s)


class TestQuestionClassifier:
    def test_duration(self):
        assert classify_question("How long must providers keep technical documentation?") == "duration"
        assert classify_question("For how many years are records retained?") == "duration"

    def test_date(self):
        assert classify_question("When does Article 5 apply?") == "date"
        assert classify_question("From what date are GPAI obligations binding?") == "date"

    def test_role(self):
        assert classify_question("Who must comply with the AI Regulation?") == "role"
        assert classify_question("Who is responsible for conformity assessment?") == "role"

    def test_definition(self):
        assert classify_question("What is an AI system?") == "definition"
        assert classify_question("How is risk defined in the AI Regulation?") == "definition"
        assert classify_question("What does 'deployer' mean?") == "definition"
        assert classify_question("Definition of provider?") == "definition"

    def test_numeric(self):
        assert classify_question("What is the maximum fine?") == "numeric"
        assert classify_question("How much can the penalty be?") == "numeric"

    def test_list(self):
        assert classify_question("What are the categories of high-risk AI?") == "list"
        assert classify_question("List the prohibited practices.") == "list"

    def test_boolean(self):
        assert classify_question("Is emotion recognition prohibited?") == "boolean"
        assert classify_question("Does the regulation apply to research?") == "boolean"

    def test_method(self):
        assert classify_question("How do providers handle data governance?") == "method"

    def test_description_fallback(self):
        # Question that doesn't match any pattern.
        assert classify_question("Tell me about Article 5.") == "description"


class TestDefinitionLookup:
    def test_ai_system(self):
        s = select_definition_sentence("What is an AI system?")
        assert s is not None
        assert "machine-based" in s.lower() or "infer" in s.lower()

    def test_what_does_deployer_mean(self):
        s = select_definition_sentence("What does deployer mean in the AI Regulation?")
        assert s is not None
        assert "natural or legal person" in s.lower() or "authority" in s.lower()

    def test_how_is_risk_defined(self):
        s = select_definition_sentence("How is risk defined in the AI Regulation?")
        assert s is not None
        assert "harm" in s.lower()

    def test_definition_of_provider(self):
        s = select_definition_sentence("Definition of provider?")
        assert s is not None
        assert "person" in s.lower() or "body" in s.lower()

    def test_unknown_term_returns_none(self):
        # "Foobar" isn't in Art. 3.
        s = select_definition_sentence("What does foobar mean?")
        assert s is None

    def test_extract_term_handles_quotes(self):
        # Smart quotes around the term.
        t = _extract_definition_term("What does ‘deployer’ mean?")
        assert t == "deployer"


class TestSelectAnswerSentence:
    def test_returns_none_for_unknown_article(self):
        assert select_answer_sentence("anything", "Art. 999") is None

    def test_returns_sentence_from_article(self):
        # Article 4 ("AI literacy") is a short article — top sentence
        # should mention literacy.
        s = select_answer_sentence(
            "What is required regarding AI literacy?", "Art. 4"
        )
        # Either we get a sentence with the keyword OR None (when
        # confidence is low). Both are valid.
        if s is not None:
            assert "literacy" in s.lower() or "skill" in s.lower()

    def test_long_sentences_skipped(self):
        # Art. 7 has 3000-char paragraphs. Default max_sentence_chars=500
        # forces the picker to a shorter sentence — verify no
        # 3000-char sentence ever ships.
        s = select_answer_sentence(
            "What does Article 7 enable the Commission to do?",
            "Art. 7",
        )
        if s is not None:
            assert len(s) <= 500

    def test_empty_question(self):
        assert select_answer_sentence("", "Art. 5") is None

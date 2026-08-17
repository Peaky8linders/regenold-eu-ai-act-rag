"""Unit tests for _shrink_user_for_groq (R341 layout-aware prompt compressor).

Validates prompt compression for Groq context budgets across three layouts:
1. Multi-turn ("Latest question:") -> trims history prefix, preserves question + tail rules
2. Single-turn ("ORIGINAL QUESTION:") -> preserves question head + tail rules, compresses middle
3. Unrecognised layout -> preserves tail rules, trims front
4. Edge cases & regressions (old user[:budget] tail chopping bug, missing markers, tight budgets)
"""

import pytest
from app.engines._graph_rag_impl import _shrink_user_for_groq


# ---------------------------------------------------------------------------
# Test Case 1: Under-budget string returns unchanged
# ---------------------------------------------------------------------------

def test_under_budget_returns_unchanged():
    """Any prompt whose character length <= budget must return bit-for-bit identical."""
    # Multi-turn under budget
    multi_turn = (
        "Conversation so far:\nUser: What is AI?\nAssistant: AI is...\n\n"
        "Latest question: What are high-risk AI systems?\n"
        " ANSWER COVERAGE: cover the content\n"
        " CRITICAL ANSWER RULES (override):\nCITE-DESCRIBE MANDATE"
    )
    assert _shrink_user_for_groq(multi_turn, budget=len(multi_turn)) == multi_turn
    assert _shrink_user_for_groq(multi_turn, budget=len(multi_turn) + 500) == multi_turn

    # Single-turn under budget
    single_turn = (
        "ORIGINAL QUESTION: Explain Article 6.\n\n"
        "Retrieved context: Article 6 classification rules.\n"
        " ANSWER COVERAGE: cover the content\n"
        " CRITICAL ANSWER RULES (override):\nCITE-DESCRIBE MANDATE"
    )
    assert _shrink_user_for_groq(single_turn, budget=len(single_turn)) == single_turn
    assert _shrink_user_for_groq(single_turn, budget=len(single_turn) + 1000) == single_turn

    # Unrecognised layout under budget
    unrecognised = "Some random user prompt with info.\n ANSWER COVERAGE: rules"
    assert _shrink_user_for_groq(unrecognised, budget=5000) == unrecognised


# ---------------------------------------------------------------------------
# Test Case 2: Multi-turn prompt compression
# ---------------------------------------------------------------------------

def test_multiturn_preserves_question_trims_history_and_preserves_tail():
    """Multi-turn layout trims conversation history while preserving Latest question and tail rules."""
    history = "Conversation so far:\n" + ("User: Previous turn question.\nAssistant: Previous answer.\n" * 50)
    question_block = "Latest question: What obligations apply to high-risk providers under Article 16?\n\nContext: Article 16 text..."
    tail_rules = (
        " ANSWER COVERAGE: cover the content the question asks for.\n"
        " CRITICAL ANSWER RULES (these override any conflicting instruction):\n"
        "CITE-DESCRIBE MANDATE: Every Article or Annex you cite MUST be described."
    )
    full_user = f"{history}\n{question_block}\n{tail_rules}"
    budget = len(question_block) + len(tail_rules) + 100  # Allows a little bit of history

    result = _shrink_user_for_groq(full_user, budget=budget)

    # Latest question must survive
    assert "Latest question: What obligations apply to high-risk providers under Article 16?" in result
    # Tail rules must survive intact
    assert " ANSWER COVERAGE: cover the content the question asks for." in result
    assert " CRITICAL ANSWER RULES (these override any conflicting instruction):" in result
    assert "CITE-DESCRIBE MANDATE: Every Article or Annex you cite MUST be described." in result
    # Truncation marker for conversation history must be prepended
    assert "... [EARLIER CONVERSATION TRUNCATED FOR GROQ CONTEXT LIMIT] ...\n\n" in result
    # Total length should be within budget + banner size
    assert result.endswith(tail_rules)


def test_multiturn_tight_budget_compresses_middle_preserves_tail():
    """When core (question/middle + tail) exceeds budget, middle is compressed and tail rules survive."""
    history = "Conversation so far:\nUser: Hi\nAssistant: Hello\n"
    question_block = "Latest question: Explain Article 6.\n" + ("VERY BULKY VERBATIM TEXT " * 200)
    tail_rules = " CRITICAL ANSWER RULES (these override any conflicting instruction):\nCITE-DESCRIBE MANDATE"
    full_user = f"{history}{question_block}\n{tail_rules}"

    # Budget smaller than question_block + tail_rules, but larger than tail_rules
    budget = len(tail_rules) + 100
    result = _shrink_user_for_groq(full_user, budget=budget)

    assert result.endswith(tail_rules)
    assert result.startswith("Latest question:")
    assert len(result) == budget


# ---------------------------------------------------------------------------
# Test Case 3: Single-turn prompt compression
# ---------------------------------------------------------------------------

def test_singleturn_preserves_question_compresses_middle_preserves_tail():
    """Single-turn layout preserves ORIGINAL QUESTION header and tail rules, truncating bulky middle."""
    question_header = "ORIGINAL QUESTION: What are the CE marking rules under Article 48?\n\n"
    bulky_middle = "BULKY KG CONTEXT AND REFERENCES: " + ("Article 48 details and cross-references. " * 300)
    tail_rules = (
        " ANSWER COVERAGE: cover the content the question actually asks for.\n"
        " CRITICAL ANSWER RULES (these override any conflicting instruction):\n"
        "CITE-DESCRIBE MANDATE: Every Article or Annex you cite MUST be described."
    )
    full_user = f"{question_header}{bulky_middle}{tail_rules}"
    budget = len(question_header) + len(tail_rules) + 150

    result = _shrink_user_for_groq(full_user, budget=budget)

    # ORIGINAL QUESTION header must survive at the very beginning
    assert result.startswith(question_header)
    # Middle truncation notice must be inserted
    assert "... [MIDDLE CONTEXT TRUNCATED FOR GROQ CONTEXT LIMIT] ..." in result
    # Tail rules must survive intact at the very end
    assert result.endswith(tail_rules)
    assert " ANSWER COVERAGE: cover the content" in result
    assert " CRITICAL ANSWER RULES" in result


def test_singleturn_tight_budget_trims_question_preserves_tail():
    """When question head + tail rules exceed budget, question is trimmed to keep tail instructions."""
    long_question_header = "ORIGINAL QUESTION: " + ("Extremely long question details " * 50) + "\n\n"
    bulky_middle = "Middle context " * 100
    tail_rules = " CRITICAL ANSWER RULES (these override any conflicting instruction):\nCITE-DESCRIBE MANDATE"
    full_user = f"{long_question_header}{bulky_middle}{tail_rules}"

    # Budget smaller than long_question_header + tail_rules, but larger than tail_rules
    budget = len(tail_rules) + 60
    result = _shrink_user_for_groq(full_user, budget=budget)

    assert result.endswith(tail_rules)
    assert result.startswith("ORIGINAL QUESTION:")
    assert len(result) == budget


# ---------------------------------------------------------------------------
# Test Case 4: Single-turn old bug regression (user[:budget] chopping tail)
# ---------------------------------------------------------------------------

def test_singleturn_old_bug_regression_tail_no_longer_chopped():
    """R341 regression test: old naive user[:budget] chopped tail rules; R341 guarantees they survive."""
    question_header = "ORIGINAL QUESTION: What are transparency obligations under Article 50?\n\n"
    # Create 8,000 chars of middle text
    middle = "Context paragraph with Article 50 provisions. " * 160
    tail_rules = (
        " ANSWER COVERAGE: cover the content the question actually asks for.\n"
        " CRITICAL ANSWER RULES (these override any conflicting instruction):\n"
        "CITE-DESCRIBE MANDATE: Every Article or Annex you cite MUST be described in the answer prose."
    )
    full_user = f"{question_header}{middle}{tail_rules}"
    budget = 4000

    # Under the OLD behavior (user[:budget]):
    old_behavior_result = full_user[:budget]
    assert " ANSWER COVERAGE:" not in old_behavior_result, "Demonstrating that old behavior lost tail rules"
    assert " CRITICAL ANSWER RULES" not in old_behavior_result, "Demonstrating that old behavior lost tail rules"

    # Under R341 fixed behavior:
    r341_result = _shrink_user_for_groq(full_user, budget=budget)
    assert r341_result.startswith(question_header)
    assert " ANSWER COVERAGE: cover the content the question actually asks for." in r341_result
    assert " CRITICAL ANSWER RULES (these override any conflicting instruction):" in r341_result
    assert "CITE-DESCRIBE MANDATE" in r341_result
    assert r341_result.endswith(tail_rules)


# ---------------------------------------------------------------------------
# Test Case 5: Unrecognised layout preserves tail rules
# ---------------------------------------------------------------------------

def test_unrecognised_layout_preserves_tail_rules():
    """Unrecognised prompt structure (no marker) trims front and preserves tail rules."""
    front_content = "Arbitrary prompt text without standard headers. " * 100
    tail_rules = (
        " ANSWER COVERAGE: cover the content.\n"
        " CRITICAL ANSWER RULES (these override any conflicting instruction):\n"
        "CITE-DESCRIBE MANDATE"
    )
    full_user = f"{front_content}\n{tail_rules}"
    budget = len(tail_rules) + 150

    result = _shrink_user_for_groq(full_user, budget=budget)

    # Front is truncated with notice
    assert "... [TRUNCATED FOR GROQ CONTEXT LIMIT] ..." in result
    # Tail rules survive intact at the end
    assert result.endswith(tail_rules)
    assert " ANSWER COVERAGE: cover the content." in result
    assert " CRITICAL ANSWER RULES" in result


# ---------------------------------------------------------------------------
# Test Case 6: Edge cases & graceful degradation
# ---------------------------------------------------------------------------

def test_edge_case_no_tail_markers_singleturn():
    """Single-turn prompt with no tail markers gracefully truncates middle."""
    question_header = "ORIGINAL QUESTION: What is Article 5?\n\n"
    middle = "Context without any tail rules. " * 200
    full_user = f"{question_header}{middle}"
    budget = 500

    result = _shrink_user_for_groq(full_user, budget=budget)

    assert result.startswith(question_header)
    assert "... [MIDDLE CONTEXT TRUNCATED FOR GROQ CONTEXT LIMIT] ..." in result


def test_edge_case_no_tail_markers_multiturn():
    """Multi-turn prompt with no tail markers gracefully truncates history."""
    history = "Conversation so far:\n" + ("User: Q\nAssistant: A\n" * 100)
    question = "Latest question: What is Article 5?\nContext info here."
    full_user = f"{history}\n{question}"
    budget = len(question) + 50

    result = _shrink_user_for_groq(full_user, budget=budget)

    assert "Latest question: What is Article 5?" in result
    assert "... [EARLIER CONVERSATION TRUNCATED FOR GROQ CONTEXT LIMIT] ..." in result


def test_edge_case_no_tail_markers_unrecognised():
    """Unrecognised prompt with no tail markers degrades to prefix slice."""
    raw_text = "Simple text without any recognized markers or tail rules. " * 50
    budget = 200

    result = _shrink_user_for_groq(raw_text, budget=budget)

    assert result == raw_text[:budget]
    assert len(result) == budget


def test_multiple_tail_markers_earliest_is_protected():
    """When multiple tail markers are present, protection begins at the earliest one."""
    header = "ORIGINAL QUESTION: Test question\n\n"
    middle = "Middle content " * 100
    # Both markers in order: ANSWER COVERAGE followed by CRITICAL ANSWER RULES
    coverage_rule = " ANSWER COVERAGE: Must cover all points.\n"
    critical_rule = " CRITICAL ANSWER RULES (these override):\nRule 1: Be concise."
    tail = coverage_rule + critical_rule
    full_user = f"{header}{middle}{tail}"
    budget = len(header) + len(tail) + 50

    result = _shrink_user_for_groq(full_user, budget=budget)

    # Both parts of the tail must be completely intact
    assert coverage_rule in result
    assert critical_rule in result
    assert result.endswith(tail)


def test_budget_smaller_than_tail_rules():
    """When budget is smaller than tail rules, safely returns sliced tail."""
    tail = " CRITICAL ANSWER RULES (these override):\nRule 1: Be concise."
    full_user = f"ORIGINAL QUESTION: Test\n\nSome context\n{tail}"
    budget = 20

    result = _shrink_user_for_groq(full_user, budget=budget)

    assert len(result) == budget
    assert result == tail[:budget]

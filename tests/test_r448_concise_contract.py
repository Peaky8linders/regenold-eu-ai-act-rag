"""R448 — the concise contract must reach the ACTUAL Stage-2 dispatch.

Asserted on the bytes handed to the provider seam, two-sided, never by
grepping source (the R398 dead-lever lesson): ON puts the LENGTH LIMIT block in
the dispatched user message, OFF leaves the message byte-identical to the
pre-R448 text.
"""
from dataclasses import replace

import pytest

from app.data import graph_rag_prompts as prompts
from app.engines import _graph_rag_impl as impl
from app.engines import answer_need


def _dispatch(monkeypatch, flag: str, question: str) -> str:
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", flag)
    evidence = "VERBATIM PROVISION TEXT: [Article 13] (a) identity; (b) characteristics."
    monkeypatch.setattr(impl, "_build_context_references_block", lambda *a, **kw: evidence)
    captured = []
    monkeypatch.setattr(
        impl, "_openai_wrapper_complete_for_graph_rag", lambda **kw: captured.append(kw)
    )
    impl._claude_max_enhance_answer(
        question=question, kg_answer="DRAFT", context=impl.GraphContext(question=question),
    )
    assert len(captured) == 1, "the call must reach the Stage-2 provider seam"
    return captured[0]["user"]


def test_on_reaches_the_wire_and_off_is_absent(monkeypatch):
    q = "What must Article 13 instructions for use contain?"
    on = _dispatch(monkeypatch, "1", q)
    off = _dispatch(monkeypatch, "0", q)
    assert "LENGTH LIMIT" in on
    assert "LENGTH LIMIT" not in off
    assert len(on) > len(off)


@pytest.mark.parametrize("value", ["", "garbage", "1", "on"])
def test_deny_list_keeps_it_on(monkeypatch, value):
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", value)
    assert answer_need.concise_contract_enabled()


@pytest.mark.parametrize("value", ["0", "false", "no", "off"])
def test_falsy_turns_it_off(monkeypatch, value):
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", value)
    assert answer_need.concise_block("What does Article 13 require?") == ""


def test_on_appends_the_block_last_and_sizes_from_the_question(monkeypatch):
    q = "What does Article 50 require of deployers?"
    refs = "Article 50 text"
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "0")
    off = prompts.build_evidence_answer_user(q, refs)
    assert "LENGTH LIMIT" not in off
    assert answer_need.need_proportional_block(q, refs) in off
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    on = prompts.build_evidence_answer_user(q, refs)
    assert on.endswith("\n\n" + answer_need.concise_block(q, ""))
    # ANSWER SHAPE is sized from the question alone when the contract is ON.
    assert answer_need.need_proportional_block(q, "") in on


def test_evidence_text_no_longer_inflates_the_estimate(monkeypatch):
    """The R448 diagnosis: read against the full evidence block, heads the ask
    never named were counted as engaged items. ON sizes from the question."""
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    q = "Name the areas of high-risk use cases. Is healthcare decision making one of them?"
    evidence = (
        "[Article 18] documentation keeping: (a) technical documentation; (b) quality "
        "management system documentation; (c) changes approved by notified bodies. "
        "[Article 49] registration of high risk systems: (a) provider; (b) deployer."
    ) * 20
    on = prompts.build_evidence_answer_user(q, evidence)
    assert "Article 18.1" not in on.split("EU AI ACT REFERENCES:")[-1].split("ANSWER SHAPE")[-1]


def test_ceiling_is_the_need_estimate_capped(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    need = answer_need.answer_need("List the categories Article 13(3) requires.", "")
    words, sentences = answer_need.concise_limits(need)
    assert words == min(need.target_words, answer_need._CONCISE_MAX_WORDS)
    assert 3 <= sentences <= 5
    block = answer_need.concise_block("List the categories Article 13(3) requires.", "")
    assert f"At most {words} words" in block


def test_cache_key_registers_the_flag(monkeypatch):
    from app.routes.regenold import _engine_cache_key
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    on = _engine_cache_key("What must a deployer do?", None)
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "0")
    assert _engine_cache_key("What must a deployer do?", None) != on


def test_scenario_question_ceiling_expanded(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    # A multi-part scenario deployment question
    scenario_q = (
        "A hospital uses an AI system to triage emergency room patients based on vital signs. "
        "What risk category applies and what specific notified body requirements exist?"
    )
    assert answer_need.is_scenario_question(scenario_q)
    need = answer_need.answer_need(scenario_q, "")
    words, sentences = answer_need.concise_limits(need, scenario_q)
    assert words == answer_need._CONCISE_SCENARIO_MAX_WORDS
    assert sentences == 6

    # Direct short questions must NOT be classified as scenarios
    direct_q = "List the categories Article 13(3) requires."
    assert not answer_need.is_scenario_question(direct_q)
    words_direct, sentences_direct = answer_need.concise_limits(need, direct_q)
    assert words_direct <= answer_need._CONCISE_MAX_WORDS
    assert sentences_direct <= 5


def test_diagnostic_rg085_scenario_keeps_the_v3_ceiling_on_pushback(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    scenario_q = (
        "Does the AI Act prohibit or classify as high-risk the use of AI in drones? "
        "Can I use AI in a drone to find who's around in town? And what if it's "
        "just a toy drone? And what about toy drones used for other applications?"
    )
    assert answer_need.is_scenario_question(scenario_q)

    need = answer_need.answer_need(scenario_q, "")
    assert answer_need.concise_limits(need, scenario_q) == (180, 6)
    block = answer_need.concise_block(scenario_q)
    assert "At most 180 words in at most 6 sentences" in block
    assert "keep the earlier answer's points and length" in block


def test_scenario_ceiling_is_a_hard_180_word_maximum(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    scenario_q = (
        "A hospital uses an AI system to triage emergency room patients based on vital signs. "
        "What risk category applies and what specific notified body requirements exist?"
    )
    need = replace(answer_need.answer_need(scenario_q, ""), target_words=185)

    assert answer_need.concise_limits(need, scenario_q) == (180, 6)


def test_diagnostic_rg037_list_contract_is_compact_and_complete(monkeypatch):
    list_q = (
        "When registering a high-risk AI system in the EU database under the EU AI Act, "
        "what specific information must the provider submit? List the required items."
    )
    need = answer_need.answer_need(list_q, "")
    words, sentences = answer_need.concise_limits(need, list_q)
    user = _dispatch(monkeypatch, "1", list_q)

    assert not answer_need.is_scenario_question(list_q)
    assert words <= answer_need._CONCISE_MAX_WORDS
    assert sentences <= 5
    assert f"At most {words} words" in user
    assert "include every required member exactly once" in user
    assert "separated by commas" in user
    assert "never substitute examples or a summary" in user
    assert "separated by semicolons" not in user


def test_diagnostic_rg085_scenario_contract_reaches_provider_on_pushback(monkeypatch):
    scenario_q = (
        "Does the AI Act prohibit or classify as high-risk the use of AI in drones? "
        "Can I use AI in a drone to find who's around in town? And what if it's "
        "just a toy drone? And what about toy drones used for other applications?"
    )
    user = _dispatch(monkeypatch, "1", scenario_q)

    assert "LENGTH LIMIT" in user
    assert "At most 180 words in at most 6 sentences" in user
    assert "keep the earlier answer's points and length" in user

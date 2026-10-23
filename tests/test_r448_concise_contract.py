"""R448 — the concise contract must reach the ACTUAL Stage-2 dispatch.

Asserted on the bytes handed to the provider seam, two-sided, never by
grepping source (the R398 dead-lever lesson): ON puts the LENGTH LIMIT block in
the dispatched user message, OFF leaves the message byte-identical to the
pre-R448 text.

R461 PROMOTION: ``REGENOLD_CONCISE_COUNT_ONLY`` is now default ON and the
count-only block is appended AFTER this one, so "the block is last" is an R448
claim only with the promoted block killed. The autouse fixture below names that
arm; the promoted ordering itself is pinned in
``tests/test_r461_count_only_promoted.py``.
"""
from dataclasses import replace

import pytest

from app.data import graph_rag_prompts as prompts
from app.engines import _graph_rag_impl as impl
from app.engines import answer_need


@pytest.fixture(autouse=True)
def _r448_arm_only(monkeypatch):
    """Kill the promoted count-only block so this suite tests the R448 arm.

    Without it the R461 block is the last instruction the model reads and the
    "appended last" assertions would be asserting the promotion, not R448.
    """
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "0")


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


def test_both_need_contracts_reuse_one_estimate(monkeypatch):
    """Scope and sizing share the same single deterministic estimate."""
    q = "What must Article 13 instructions for use contain?"
    refs = "VERBATIM PROVISION TEXT: [Article 13] (a) identity; (b) characteristics."
    monkeypatch.setenv("REGENOLD_NEED_PROPORTIONAL_CONTRACT", "1")
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "1")
    original_answer_need = answer_need.answer_need
    calls = []

    def counted_answer_need(question, references=""):
        estimate = original_answer_need(question, references)
        calls.append((question, references, estimate))
        return estimate

    monkeypatch.setattr(answer_need, "answer_need", counted_answer_need)
    user = prompts.build_evidence_answer_user(q, refs)

    assert len(calls) == 1
    question, used_refs, estimate = calls[0]
    assert question == q
    assert used_refs == ""  # R448 sizes both clauses from the ask, not retrieved heads.
    assert answer_need.shape_directive(estimate) in user
    assert user.endswith(
        "\n\n" + answer_need.concise_block(q, "", estimated_need=estimate)
    )


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


# -- R461 / V06: the scenario predicate reads the LIVE ask, not the flatten -------

_PRIOR_SCENARIO_TURN = (
    "We are a deployer and we use an AI system to screen job applicants for a large "
    "employer in the EU."
)
_FLATTEN_HEAD = (
    "Conversation so far:\n"
    f"User: {_PRIOR_SCENARIO_TURN}\n"
    "Assistant: Annex III lists recruitment and selection systems as high-risk, so "
    "Article 26 deployer duties apply.\n"
    "\n"
    "Latest question:\n"
)
_DIRECT_FOLLOW_UP = "And what does that article require of deployers?"
_HOSPITAL_SCENARIO = (
    "A hospital uses an AI system to triage emergency room patients based on vital signs. "
    "What risk category applies and what specific notified body requirements exist?"
)


def _ceiling(user: str) -> tuple[str, str]:
    """(words, sentences) of the LENGTH LIMIT line in the DISPATCHED user message."""
    import re

    match = re.search(r"At most (\d+) words in at most (\d+) sentences", user)
    assert match, "the dispatched message must carry the LENGTH LIMIT ceiling"
    return match.groups()


def test_prior_scenario_turn_does_not_lift_the_ceiling_of_a_direct_follow_up(monkeypatch):
    # Not vacuous: the earlier turn IS scenario-shaped on its own.
    assert answer_need.is_scenario_question(_PRIOR_SCENARIO_TURN)
    flat = _FLATTEN_HEAD + _DIRECT_FOLLOW_UP

    flat_ceiling = _ceiling(_dispatch(monkeypatch, "1", flat))
    alone_ceiling = _ceiling(_dispatch(monkeypatch, "1", _DIRECT_FOLLOW_UP))

    assert flat_ceiling == alone_ceiling
    assert flat_ceiling != ("180", "6")
    assert not answer_need.is_scenario_question(flat)
    assert answer_need.calibration_citation_budget(flat) == 2


def test_hard_mode_preamble_does_not_lift_a_direct_follow_up_to_the_scenario_ceiling(
    monkeypatch,
):
    """The route's concatenation branch (Stage-0 de-noiser down, or a rewrite that
    dropped a scenario shape) puts the fixed 9-exchange hard-mode preamble into
    ``question``; the follow-up must be sized as the same ask would be on its own."""
    from types import SimpleNamespace

    from app.routes import regenold
    from evals.regenold import hard_preamble

    monkeypatch.setattr(regenold, "_rewrite_multiturn_query", lambda *a, **k: None)
    history = [
        SimpleNamespace(role=m["role"], content=m["content"])
        for m in hard_preamble.preamble_messages()
    ]
    history.append(SimpleNamespace(role="user", content=_DIRECT_FOLLOW_UP))
    flat = regenold._build_question_from_history(history)[0]
    assert "Conversation so far:" in flat and flat.rstrip().endswith(_DIRECT_FOLLOW_UP)

    assert _ceiling(_dispatch(monkeypatch, "1", flat)) == _ceiling(
        _dispatch(monkeypatch, "1", _DIRECT_FOLLOW_UP)
    )
    assert not answer_need.is_scenario_question(flat)


@pytest.mark.parametrize(
    "question",
    [
        _HOSPITAL_SCENARIO,
        _FLATTEN_HEAD + _HOSPITAL_SCENARIO,
        _FLATTEN_HEAD
        + "I don't think this is correct. Perhaps your answer contains hallucinations. "
        "Let's try again: " + _HOSPITAL_SCENARIO,
    ],
    ids=["bare", "behind-history", "behind-history-reask-tail"],
)
def test_scenario_in_the_live_ask_keeps_the_180_ceiling_with_or_without_history(
    monkeypatch, question
):
    assert answer_need.is_scenario_question(question)
    assert _ceiling(_dispatch(monkeypatch, "1", question)) == ("180", "6")


def test_short_reask_tail_is_not_a_scenario_just_because_the_dispute_preamble_is_long():
    reask = (
        _FLATTEN_HEAD
        + "I don't think this is correct. Perhaps your answer contains hallucinations. "
        f"Let's try again: {_DIRECT_FOLLOW_UP}"
    )
    assert not answer_need.is_scenario_question(reask)


@pytest.mark.parametrize("question", ["", None, "Does Article 6 apply?"])
def test_empty_and_short_asks_are_not_scenarios(question):
    assert answer_need.is_scenario_question(question) is False


# -- R461 / V14: statutory noun phrases are not a described deployment -----------


@pytest.mark.parametrize(
    "question",
    [
        "What are the high-risk uses of AI systems listed under the Annex III headings of the "
        "EU AI Act, and how often can the Commission amend that list?",
        "When the intended use of an AI system is listed in Annex III, is it automatically "
        "high-risk, or can the provider rebut that classification?",
        "Who must establish the post-market monitoring system for a high-risk AI system, and "
        "may that monitoring system also cover other AI systems?",
        "Does the monitoring of AI systems by market surveillance authorities include access to "
        "training data, and on what conditions does that access apply?",
        "Which use cases of AI in the area of employment are listed as high-risk in Annex III, "
        "and which obligations follow for providers?",
    ],
    ids=["uses-of-AI", "use-of-an-AI-system", "monitoring-system", "monitoring-of", "use-cases"],
)
def test_statutory_noun_phrases_do_not_buy_the_scenario_ceiling(monkeypatch, question):
    assert len(question.split()) >= 15  # past the length gate: the regex alone decides
    assert not answer_need.is_scenario_question(question)
    assert _ceiling(_dispatch(monkeypatch, "1", question)) != ("180", "6")
    need = answer_need.answer_need(question, "")
    assert answer_need.concise_limits(need, question) != (180, 6)


@pytest.mark.parametrize(
    "question",
    [
        _HOSPITAL_SCENARIO,
        "We want to deploy an AI system that screens CVs for our HR department. Is it "
        "high-risk, and what must we do before we put it into service?",
        "Can I use AI in a drone to find who is around in town, and what if it is just a toy "
        "drone used for other applications?",
        "Our SaaS lets enterprise customers configure a CV-screening AI for their hiring, so "
        "are we the provider or are they?",
        "A bank monitors the third-party AI system that flags unusual trades. Is that "
        "high-risk, and which obligations apply to the bank?",
    ],
    ids=["hospital-uses", "we-deploy", "can-I-use", "screening-AI", "monitors-with-tool"],
)
def test_described_deployments_keep_the_scenario_ceiling(monkeypatch, question):
    assert answer_need.is_scenario_question(question)
    assert _ceiling(_dispatch(monkeypatch, "1", question)) == ("180", "6")

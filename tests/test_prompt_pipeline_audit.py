"""Grounded regression cases for the R394/R395 follow-up audit."""
from types import SimpleNamespace

import pytest

from app.data import graph_rag_prompts as prompts
from app.data.provision_text import get_provision_text
from app.engines import _graph_rag_impl as impl
from app.llm import intent_classifier as ic


@pytest.mark.parametrize("ref,phrases", [
    ("Article 44.1", ["relevant authorities", "Member State", "notified body"]),
    ("Article 44.2", ["five years", "four years", "re-assessment"]),
    ("Article 10.6", ["paragraphs 2 to 5", "testing data sets"]),
    ("Article 50.4", ["authorised by law", "evidently artistic", "analogous work"]),
    ("Article 49.2", ["not high-risk", "Article 6(3)"]),
    ("Article 71.2", ["Sections A and B of Annex VIII", "authorised representative"]),
    ("Annex VIII", ["Section B", "Article 49(2)", "Article 6(3)"]),
    ("Annex IX", ["testing in real world conditions", "Article 60"]),
])
def test_corrected_rules_match_the_adopted_statute(ref, phrases):
    text = get_provision_text(ref)
    assert text, ref
    for phrase in phrases:
        assert phrase in text, (ref, phrase)


def test_corrected_rules_reach_the_actual_stage2_user_channel(monkeypatch):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("REGENOLD_PROMPT_COMPACT", "0")
    monkeypatch.setenv("REGENOLD_PROMPT_V3", "0")
    monkeypatch.setenv("REGENOLD_USER_CRITICAL_RULES", "1")
    monkeypatch.setenv("REGENOLD_ANSWER_FIRST", "0")
    captured = []
    monkeypatch.setattr(impl, "_openai_wrapper_complete_for_graph_rag",
                        lambda **kwargs: captured.append(kwargs))
    question = "Which information belongs in Annex VIII Section B?"
    context = impl.GraphContext(question=question)
    impl._claude_max_enhance_answer(question=question, kg_answer="Draft",
                                  context=context, original_question=question)
    assert captured, "the real Stage-2 transport must be called"
    assert prompts.USER_CRITICAL_RULES_CLAUSE in captured[-1]["user"]
    assert "Section B covers Article 49(2)" in captured[-1]["user"]


@pytest.mark.parametrize("flag,value", [
    ("REGENOLD_INTENT_MAX_TOKENS", "900"),
    ("REGENOLD_INTENT_BEDROCK", "1"),
    ("REGENOLD_INTENT_BEDROCK_TIMEOUT", "15"),
    ("REGENOLD_INTENT_MODEL_BEDROCK", "test-model"),
    ("REGENOLD_INTENT_PROVIDER", "groq"),
])
def test_intent_cache_does_not_cross_configuration_arms(monkeypatch, flag, value):
    ic._reset_for_tests()
    monkeypatch.delenv(flag, raising=False)
    calls = []

    def complete(request):
        calls.append(request)
        return SimpleNamespace(error=None, model="same-model", text=(
            '{"intent":"definition","primary_anchor":"Art. 3",'
            '"alternate_anchors":[],"confidence":0.95}'
        ))

    monkeypatch.setattr(ic, "is_intent_enabled", lambda: True)
    monkeypatch.setattr(ic, "_resolve_intent_provider",
                        lambda: (SimpleNamespace(complete=complete), "same-model"))
    try:
        first = ic.classify_intent("What is an AI system?")
        repeat = ic.classify_intent("What is an AI system?")
        monkeypatch.setenv(flag, value)
        changed = ic.classify_intent("What is an AI system?")
        assert first and not first.cache_hit
        assert repeat and repeat.cache_hit
        assert changed and not changed.cache_hit
        assert len(calls) == 2
    finally:
        ic._reset_for_tests()


def test_fallback_provider_construction_failure_is_fail_soft(monkeypatch):
    ic._reset_for_tests()
    monkeypatch.setattr(ic, "is_intent_enabled", lambda: True)
    monkeypatch.setattr(ic, "is_openai_wrapper_enabled", lambda: True)
    broken = SimpleNamespace(complete=lambda request: SimpleNamespace(error="unavailable"))
    monkeypatch.setattr(ic, "_resolve_intent_provider", lambda: (broken, ic._DEFAULT_GROQ_MODEL))

    def fail():
        raise RuntimeError("provider construction failed")

    monkeypatch.setattr(ic, "get_openai_wrapper_provider", fail)
    try:
        assert ic.classify_intent("What is an AI system?") is None
        assert ic._BREAKER.failures == 1
    finally:
        ic._reset_for_tests()


@pytest.mark.parametrize("flag", [
    "REGENOLD_INTENT_MAX_TOKENS", "REGENOLD_INTENT_BEDROCK",
    "REGENOLD_INTENT_BEDROCK_TIMEOUT", "REGENOLD_INTENT_MODEL_BEDROCK",
    "REGENOLD_STAGE2_BEDROCK_MODEL", "REGENOLD_STAGE2_PRIMARY_HOSTS",
    "REGENOLD_STAGE2_STRICT_TRANSPORT",
])
def test_newly_audited_flags_change_engine_cache_identity(monkeypatch, flag):
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv(flag, "0")
    before = _engine_cache_key("What is an AI system?", None)
    monkeypatch.setenv(flag, "1")
    assert before != _engine_cache_key("What is an AI system?", None)


@pytest.mark.parametrize("layout", ["single", "multi", "unknown"])
@pytest.mark.parametrize("budget", [0, -1, 1, 150, 500, 1000])
def test_prompt_budget_includes_truncation_banners(layout, budget):
    tail = " CRITICAL ANSWER RULES: preserve this rule."
    prefixes = {
        "single": "ORIGINAL QUESTION: Q?\n\n" + "Evidence " * 300,
        "multi": "Conversation so far: " + "Old turn " * 300 + "Latest question: Q?\nEvidence",
        "unknown": "Unknown layout " * 300,
    }
    result = impl._shrink_user_for_groq(prefixes[layout] + tail, budget)
    assert len(result) <= max(0, budget)
    if budget > len(tail):
        assert result.endswith(tail)


def test_challenge_only_tail_survives_when_coverage_is_disabled():
    question = "ORIGINAL QUESTION: Does the exemption require legal authorisation?\n\n"
    user = question + "Evidence " * 2000 + prompts.USER_CHALLENGE_BREVITY_CLAUSE
    result = impl._shrink_user_for_groq(user, 3000)
    assert question in result
    assert prompts.USER_CHALLENGE_BREVITY_CLAUSE in result
    assert len(result) <= 3000


def test_compact_contract_does_not_cap_requested_statutory_sets():
    assert "EVERY numbered or lettered member" in prompts.COMPACT_ANSWER_CONTRACT
    assert "without a fixed character limit" in prompts.COMPACT_ANSWER_CONTRACT
    assert "strictly under 950" not in prompts.COMPACT_ANSWER_CONTRACT

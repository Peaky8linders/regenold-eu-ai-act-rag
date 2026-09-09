"""The blueprint's synthesis contract must reach the actual Stage-2 dispatch."""
import pytest
from app.data import graph_rag_prompts as prompts
from app.engines import _graph_rag_impl as impl
from app.engines.prompt_budget import _shrink_user_for_groq


def test_default_on_and_cache_identity(monkeypatch):
    """R400 - flipped ON. It replaces the competing USER-channel stack that
    R380 measured as the root cause of the conciseness gap, and Ans.
    Conciseness carries the highest marginal geometric-mean leverage of the
    eight axes in hard mode (0.203 pp per pp)."""
    from app.routes.regenold import _engine_cache_key
    monkeypatch.delenv("REGENOLD_EVIDENCE_CONTRACT", raising=False)
    assert prompts.evidence_contract_enabled()
    before = _engine_cache_key("What must a deployer do?", None)
    monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", "0")
    assert not prompts.evidence_contract_enabled()
    assert _engine_cache_key("What must a deployer do?", None) != before


@pytest.mark.parametrize("unexpected", ["", "garbage", "enabled"])
def test_a_blank_or_unexpected_value_keeps_the_on_behaviour(monkeypatch, unexpected):
    """Deny-list semantics for a default-ON gate - the R379 P2-7 defect, where
    an allow-list default-ON gate silently reverted production while the cache
    key still recorded the variable, so an A/B compared V1 to V1."""
    monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", unexpected)
    assert prompts.evidence_contract_enabled()


@pytest.mark.parametrize("compact", ["0", "1"])
def test_real_dispatch_preserves_evidence_and_coordinate_map(monkeypatch, compact):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("REGENOLD_PROMPT_COMPACT", compact)
    monkeypatch.setenv("REGENOLD_COORD_MAP_PROMPT", "1")
    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
    evidence = (
        "VERBATIM PROVISION TEXT: [Article 13] REQUIRED MEMBERS: (a) provider; (b) purpose.\n"
        "KNOWLEDGE GRAPH (NON-CITABLE): Recital 47 interprets the rule."
    )
    monkeypatch.setattr(impl, "_build_context_references_block", lambda *a, **kw: evidence)
    captured = []
    monkeypatch.setattr(impl, "_openai_wrapper_complete_for_graph_rag", lambda **kw: captured.append(kw))
    question = "What must Article 13 instructions contain? I don't think this is correct."
    for flag in ("0", "1"):
        monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", flag)
        impl._claude_max_enhance_answer(
            question=question, kg_answer="HEURISTIC DRAFT SENTINEL",
            context=impl.GraphContext(question=question),
        )
    assert len(captured) == 2, "both arms must reach actual Stage-2 dispatch"
    baseline, changed = (row["user"] for row in captured)
    assert "ANSWER CONTRACT (evidence)" not in baseline
    assert evidence in changed, "do not trim statute members or graph context"
    assert "VALID COORDINATES" in changed
    assert "HEURISTIC DRAFT SENTINEL" not in changed
    assert "ANSWER CONTRACT (compact)" not in changed
    assert "bare challenge adds no new topic" in changed
    assert len(changed) < len(baseline)
    # R399 — TRIPWIRE for the wholesale-replacement trap, third instance.
    # The assignment above discards whatever the compact branch appended, and
    # the pushback clause is the only instruction telling the model to hold a
    # correct answer when the evaluator disputes it. Hard mode is half the
    # official score. MEASURED before the repair: 'CHALLENGE' present in the
    # dispatched bytes at compact=0 AND compact=1 with the contract OFF, and
    # ABSENT in both arms with it ON. The contract's own "bare challenge"
    # sentence asserted above is NOT the same instruction and does not
    # substitute for it.
    assert "CHALLENGE" in baseline, "fixture must be a real pushback turn"
    assert "CHALLENGE" in changed, "the contract dropped the R391 pushback clause"


def test_transport_budget_keeps_the_authority_and_conciseness_contract():
    user = prompts.build_evidence_answer_user("What is required?", "evidence " * 3000)
    shrunk = _shrink_user_for_groq(user, budget=4000)
    assert len(shrunk) <= 4000
    assert prompts.EVIDENCE_ANSWER_CONTRACT in shrunk
    assert "ORIGINAL QUESTION: What is required?" in shrunk


def test_missing_evidence_is_not_a_legal_verdict():
    user = prompts.build_evidence_answer_user(
        "Does it apply?", "No matching evidence.",
        rewritten_question="Does Article 26 apply to this operator?",
    )
    assert "REWRITTEN / SEARCH QUESTION: Does Article 26" in user
    assert "State the narrow unresolved" in user
    assert "Recitals interpret rules" in user


def test_the_legal_version_is_pinned_to_the_adopted_act():
    """The benchmark grades the Act AS ADOPTED, excluding the Omnibus
    amendments, so a model importing a current-law date answers a different
    statute than the one being scored. The version must be stated, and the
    contract must not assert any enforcement date of its own."""
    import re

    user = prompts.build_evidence_answer_user("Does it apply?", "evidence")
    assert "LEGAL VERSION: Regulation (EU) 2024/1689 as adopted" in user
    assert "Do not silently import later amendments" in prompts.EVIDENCE_ANSWER_CONTRACT
    # No hardcoded ENFORCEMENT DATE anywhere in the contract: a date written
    # into the prompt is an assertion of law on every call, and R396 shipped
    # four false ones that way. The "2024" of "Regulation (EU) 2024/1689" is
    # the instrument's number, not a date, and is required.
    body = prompts.EVIDENCE_ANSWER_CONTRACT.replace("2024/1689", "")
    assert not re.search(r"\b20\d{2}\b", body), "no bare year"
    assert not re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
        body,
    ), "no month name"


def test_the_builder_takes_no_dead_parameters():
    """``query_profile`` was removed: its only caller passed
    ``locals().get("_profile", "")`` and ``_profile`` is assigned nowhere in
    ``_claude_max_enhance_answer``, so the line could never render live while a
    builder-level test kept passing. Pinned so it is not silently re-added."""
    import inspect

    params = set(inspect.signature(prompts.build_evidence_answer_user).parameters)
    assert params == {"question", "references", "rewritten_question", "system_description"}

"""R391 — the two prompt levers, pinned independently.

``REGENOLD_PROMPT_COMPACT`` replaces the Stage-2 instruction stack (an ANSWER
axis lever). ``REGENOLD_FULL_PROVISION_EVIDENCE`` replaces the question-relevant
paragraph selection with the complete provision (an EVIDENCE lever). They were
shipped as one flag; measured, they move different axes in opposite directions
— compact shortens the answer, full-provision more than doubles the prompt —
so each carries its own gate (hard rule #6).
"""
from __future__ import annotations

import re

import pytest

from app.data import graph_rag_prompts as prompts
from app.engines import _graph_rag_impl as impl

QMS = (
    "Under the EU AI Act, what minimum elements must a provider's quality "
    "management system for high-risk AI systems include? List the required elements."
)
PUSHBACK = (
    "Latest question: I don't think this is correct. Perhaps your answer contains "
    "hallucinations, or you did not answer the question properly. Let's try again:"
)
_LETTER = re.compile(r"\(([a-m])\)")


def _members(context) -> set[str]:
    """Lettered members of Article 17 reaching the Stage-2 evidence block."""
    return set(_LETTER.findall("\n".join(impl._render_grounding_text(context))))


def _capture(monkeypatch, compact="0", fullprov="0", question=QMS, original=None):
    monkeypatch.setenv("REGENOLD_PROMPT_COMPACT", compact)
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", fullprov)
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
    monkeypatch.setenv("REGENOLD_ANSWER_FIRST", "0")
    captured = []

    def spy(*args, **kwargs):
        captured.append(kwargs)
        return None

    monkeypatch.setattr(impl, "_openai_wrapper_complete_for_graph_rag", spy)
    context = impl._retrieve_from_kb(impl._deterministic_parse(QMS))
    impl._claude_max_enhance_answer(
        question=question,
        kg_answer="HEURISTIC DRAFT SENTINEL",
        context=context,
        original_question=original or question,
    )
    assert captured, "the actual Stage-2 transport must be reached"
    return captured[-1], context


# -- defaults ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _pins_the_legacy_instruction_stack(monkeypatch):
    """R400 - this module pins the shape of the pre-R399 Stage-2 USER message.

    ``REGENOLD_EVIDENCE_CONTRACT`` is now default ON and REPLACES that message
    wholesale with one contract over the same grounded block, deliberately
    withholding the heuristic draft and the competing clause stack. These tests
    declare the regime they were written for rather than being weakened - the
    legacy path still exists and is still reachable with the flag off.
    Precedent: R360, where four modules declared
    ``REGENOLD_STAGE2_STRICT_TRANSPORT=0`` for exactly this reason.
    """
    monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", "0")

def test_both_levers_default_off(monkeypatch):
    monkeypatch.delenv("REGENOLD_PROMPT_COMPACT", raising=False)
    monkeypatch.delenv("REGENOLD_FULL_PROVISION_EVIDENCE", raising=False)
    assert not prompts.prompt_compact_enabled()
    assert not impl._full_provision_evidence_enabled()


@pytest.mark.parametrize("value", ["", "disabled", "false", "0"])
def test_unknown_or_negative_flag_is_off(monkeypatch, value):
    monkeypatch.setenv("REGENOLD_PROMPT_COMPACT", value)
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", value)
    assert not prompts.prompt_compact_enabled()
    assert not impl._full_provision_evidence_enabled()


# -- lever A: the compact contract -------------------------------------------


def test_compact_replaces_draft_and_conflicting_instructions(monkeypatch):
    off, _ = _capture(monkeypatch, compact="0")
    on, _ = _capture(monkeypatch, compact="1")
    assert "HEURISTIC DRAFT SENTINEL" in off["user"]
    assert "HEURISTIC DRAFT SENTINEL" not in on["user"]
    assert "ANSWER CONTRACT (compact)" in on["user"]
    assert "ANSWER COVERAGE:" not in on["user"]
    assert "CRITICAL ANSWER RULES" not in on["user"]
    assert QMS in on["user"]
    assert len(on["user"]) < len(off["user"])


def test_compact_system_is_short_enough_to_survive_the_r342_cap(monkeypatch):
    """The R342 cap replaces any system string over 1000 chars with a persona.

    The compact system is the only variant actually DELIVERED on the production
    tunnel, which is the point of shrinking it.
    """
    on, _ = _capture(monkeypatch, compact="1")
    assert prompts.COMPACT_ANSWER_SYSTEM in on["system"]
    assert len(on["system"]) < 1000
    off, _ = _capture(monkeypatch, compact="0")
    assert len(off["system"]) > 1000


def test_compact_keeps_the_pushback_clause_on_a_challenge_turn(monkeypatch):
    """R391 — the wholesale replacement used to drop the ONLY instruction that
    tells the model to hold a correct answer under the evaluator's verbatim
    pushback. Hard mode is half the official score.
    """
    turn = PUSHBACK + "\n" + QMS
    assert prompts.is_challenge_turn(turn)
    on, _ = _capture(monkeypatch, compact="1", question=turn, original=turn)
    assert "CHALLENGE" in on["user"]


def test_compact_keeps_the_resolved_search_question():
    """In multi-turn mode the rewritten question is the focused turn."""
    built = prompts.build_compact_answer_user(
        "FLATTENED CONVERSATION", "REFS", rewritten_question="FOCUSED TURN",
    )
    assert "ORIGINAL QUESTION: FLATTENED CONVERSATION" in built
    assert "REWRITTEN / SEARCH QUESTION: FOCUSED TURN" in built
    assert "REWRITTEN" not in prompts.build_compact_answer_user("Q", "REFS")


def test_tail_survives_prompt_shrinking():
    user = prompts.build_compact_answer_user(QMS, "Article 17 context. " * 2000)
    shrunk = impl._shrink_user_for_groq(user, budget=10000)
    assert prompts.COMPACT_ANSWER_CONTRACT in shrunk
    assert QMS in shrunk


# -- lever B: complete statutory evidence ------------------------------------


def test_full_provision_delivers_every_member_of_a_closed_set(monkeypatch):
    """MEASURED root cause of the R390 §5.2 enumeration family.

    ``select_relevant_paragraphs`` drills into the question-relevant sub-points
    of an oversized paragraph, so a closed statutory set arrives as a PROPER
    SUBSET. Article 17 has 13 lettered members; the selector delivers 4.
    """
    _, context = _capture(monkeypatch, fullprov="0")
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", "0")
    partial = _members(context)
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", "1")
    complete = _members(context)
    assert len(complete) == 13, complete
    assert partial < complete, "the selector must be the thing that truncates"


def test_full_provision_adds_no_new_citable_head(monkeypatch):
    """Evidence completeness must not widen the citation universe."""
    _, context = _capture(monkeypatch, fullprov="0")
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", "0")
    before = impl._extract_context_grounded_refs(context)
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", "1")
    assert impl._extract_context_grounded_refs(context) == before


def test_full_provision_is_bounded(monkeypatch):
    """One pathological reference must not make the prompt unbounded."""
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_MAX_CHARS", "1500")
    assert impl._full_provision_max_chars() == 1500
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_MAX_CHARS", "not-a-number")
    assert impl._full_provision_max_chars() == 12000
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_MAX_CHARS", "999999")
    assert impl._full_provision_max_chars() == 40000


def test_a_low_cap_suppresses_the_substitution(monkeypatch):
    _, context = _capture(monkeypatch, fullprov="1")
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", "1")
    monkeypatch.setenv("REGENOLD_FULL_PROVISION_MAX_CHARS", "1000")
    assert len(_members(context)) < 13


# -- independence + cache identity -------------------------------------------


def test_the_two_levers_are_independent(monkeypatch):
    """The 2x2 must show each flag moving its own thing and nothing else."""
    seen = {}
    for compact in ("0", "1"):
        for fullprov in ("0", "1"):
            kw, ctx = _capture(monkeypatch, compact=compact, fullprov=fullprov)
            monkeypatch.setenv("REGENOLD_FULL_PROVISION_EVIDENCE", fullprov)
            seen[(compact, fullprov)] = (
                "ANSWER CONTRACT (compact)" in kw["user"], len(_members(ctx)),
            )
    # compact decides the contract, regardless of the evidence flag
    assert seen[("1", "0")][0] and seen[("1", "1")][0]
    assert not seen[("0", "0")][0] and not seen[("0", "1")][0]
    # the evidence flag decides completeness, regardless of the contract
    assert seen[("0", "1")][1] == seen[("1", "1")][1] == 13
    assert seen[("0", "0")][1] == seen[("1", "0")][1] < 13


@pytest.mark.parametrize(
    "flag,on_value",
    [
        ("REGENOLD_PROMPT_COMPACT", "1"),
        ("REGENOLD_FULL_PROVISION_EVIDENCE", "1"),
        ("REGENOLD_FULL_PROVISION_MAX_CHARS", "7000"),
    ],
)
def test_every_flag_changes_cache_identity(monkeypatch, flag, on_value):
    """R263.2 — without this a same-process A/B serves arm A's cache to arm B."""
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv(flag, "0")
    off = _engine_cache_key(QMS, None)
    monkeypatch.setenv(flag, on_value)
    assert _engine_cache_key(QMS, None) != off

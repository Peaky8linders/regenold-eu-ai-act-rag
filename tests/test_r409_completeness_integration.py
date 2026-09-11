"""R409 — the answer-completeness levers reach the REAL Stage-2 path, two-sided.

Proved by call count and by the dispatched bytes, never by a source grep (the
trap R329, R330, R366 and R398 each paid for). Detector behaviour itself is
pinned in ``tests/test_r409_answer_completeness.py``.
"""
import pytest

from app.engines import _graph_rag_impl as impl
from app.engines import answer_completeness as ac

_FLAGS = (
    "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD",
    "REGENOLD_EXCEPTION_LIMB_GUARD",
    "REGENOLD_VERDICT_LEAD_GUARD",
    "REGENOLD_PUSHBACK_KEEP_CONTRACT",
    "REGENOLD_GOVERNING_PROVISION_CLAUSE",
)

QUESTION = (
    "Does the obligation to disclose deep fakes apply when the content is used "
    "to prosecute a criminal offence?"
)
ANSWER = (
    "The disclosure duty in Article 50(4) does not apply where the use is "
    "authorised by law to detect, prevent, investigate or prosecute criminal offences."
)
REPAIRED = "No. " + ANSWER


@pytest.fixture(autouse=True)
def _all_flags_off(monkeypatch):
    for flag in _FLAGS:
        monkeypatch.setenv(flag, "0")
    impl.reset_completeness_guard_stats()


def _spy_repair(monkeypatch, reply):
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return reply

    monkeypatch.setattr(impl, "_stage2_complete", fake)
    return calls


def test_default_off_and_every_flag_moves_the_cache_key(monkeypatch):
    from app.routes.regenold import _engine_cache_key

    for flag in (*_FLAGS, "REGENOLD_KG_POINT_TEXT"):
        monkeypatch.delenv(flag, raising=False)
    assert not any(
        (
            ac.closed_set_completeness_enabled(),
            ac.exception_limb_guard_enabled(),
            ac.verdict_lead_guard_enabled(),
            ac.pushback_keep_enabled(),
            ac.governing_provision_clause_enabled(),
        )
    )
    for flag in (*_FLAGS, "REGENOLD_KG_POINT_TEXT"):
        monkeypatch.delenv(flag, raising=False)
        before = _engine_cache_key(QUESTION, None)
        monkeypatch.setenv(flag, "1")
        assert _engine_cache_key(QUESTION, None) != before, flag
        monkeypatch.delenv(flag, raising=False)


def test_flags_off_make_no_repair_call(monkeypatch):
    calls = _spy_repair(monkeypatch, REPAIRED)
    assert impl._guard_answer_completeness(QUESTION, ANSWER, None) == ANSWER
    assert calls == []
    assert impl.completeness_guard_stats()["attempts"] == 0


def test_verdict_gap_is_repaired_once(monkeypatch):
    monkeypatch.setenv("REGENOLD_VERDICT_LEAD_GUARD", "1")
    calls = _spy_repair(monkeypatch, REPAIRED)
    out = impl._guard_answer_completeness(QUESTION, ANSWER, None)

    assert out == REPAIRED
    assert len(calls) == 1
    assert ANSWER in calls[0]["user"], "the repair must see the answer it revises"
    assert impl.completeness_guard_stats() == {
        "attempts": 1, "repaired": 1, "rejected": 0, "failed": 0,
    }


def test_no_gap_means_no_call(monkeypatch):
    monkeypatch.setenv("REGENOLD_VERDICT_LEAD_GUARD", "1")
    calls = _spy_repair(monkeypatch, REPAIRED)
    assert impl._guard_answer_completeness(QUESTION, REPAIRED, None) == REPAIRED
    assert calls == []


@pytest.mark.parametrize(
    "reply, outcome",
    [
        # Adds a provision the original never named: not a completeness fix.
        ("No. " + ANSWER + " Article 5 is not engaged.", "rejected"),
        # Truncated rewrite: never ship a fragment.
        ("No. The disclosure duty in Article 50(4) does not apply where the use is", "failed"),
        (None, "failed"),
    ],
)
def test_a_bad_repair_ships_the_original(monkeypatch, reply, outcome):
    monkeypatch.setenv("REGENOLD_VERDICT_LEAD_GUARD", "1")
    _spy_repair(monkeypatch, reply)
    assert impl._guard_answer_completeness(QUESTION, ANSWER, None) == ANSWER
    assert impl.completeness_guard_stats()[outcome] == 1


def _reach_stage2_tail(monkeypatch, polish):
    """Open every gate in front of the Stage-2 call; return a guard-call spy."""
    import app.engines.question_complexity as qc

    monkeypatch.setattr(qc, "is_complex_question", lambda *a, **k: False)
    monkeypatch.setattr(impl, "_deterministic_answer", lambda *a, **k: "KG ANSWER")
    monkeypatch.setattr(impl, "_stage2_polish_enabled", lambda: True)
    monkeypatch.setattr(impl, "_stage2_provider_enabled", lambda: True)
    monkeypatch.setattr(impl, "_stage2_simple_skip_enabled", lambda: False)
    monkeypatch.setattr(impl, "_curated_stage2_skip_enabled", lambda: False)
    monkeypatch.setattr(impl, "_definitional_stage2_skip_enabled", lambda: False)
    monkeypatch.setattr(impl, "_claude_max_enhance_answer", lambda **k: polish)
    seen = []

    def spy(question, answer, context):
        seen.append((question, answer))
        return answer + " [guarded]"

    monkeypatch.setattr(impl, "_guard_answer_completeness", spy)
    return seen


def test_two_stage_generate_guards_a_landed_polish(monkeypatch):
    seen = _reach_stage2_tail(monkeypatch, ANSWER)
    out, used = impl._two_stage_generate(QUESTION, impl.GraphContext(question=QUESTION))
    assert used is True
    assert seen == [(QUESTION, ANSWER)]
    assert out == ANSWER + " [guarded]"


def test_two_stage_generate_never_guards_the_deterministic_fallback(monkeypatch):
    seen = _reach_stage2_tail(monkeypatch, None)
    out, used = impl._two_stage_generate(QUESTION, impl.GraphContext(question=QUESTION))
    assert used is False
    assert seen == []
    assert out == "KG ANSWER"


def _dispatch(monkeypatch, question, original_question, *, contract, compact):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
    monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", contract)
    monkeypatch.setenv("REGENOLD_PROMPT_COMPACT", compact)
    monkeypatch.setattr(
        impl, "_build_context_references_block",
        lambda *a, **k: "VERBATIM PROVISION TEXT: [Article 14] Human oversight.",
    )
    captured = []
    monkeypatch.setattr(
        impl, "_openai_wrapper_complete_for_graph_rag", lambda **kw: captured.append(kw)
    )
    impl._claude_max_enhance_answer(
        question=question,
        kg_answer="DRAFT",
        context=impl.GraphContext(question=question),
        original_question=original_question,
    )
    assert len(captured) == 1, "the arm must reach the real Stage-2 dispatch"
    return captured[0]["user"]


@pytest.mark.parametrize("contract", ["0", "1"])
@pytest.mark.parametrize("compact", ["0", "1"])
def test_governing_clause_survives_every_wholesale_replacement(monkeypatch, contract, compact):
    q = (
        "Which article of the EU AI Act governs human oversight of high-risk AI "
        "systems, and what does it require?"
    )
    monkeypatch.setenv("REGENOLD_GOVERNING_PROVISION_CLAUSE", "1")
    clause = ac.governing_provision_clause(q)
    assert clause, "fixture must be a governing-provision question"
    on = _dispatch(monkeypatch, q, q, contract=contract, compact=compact)
    monkeypatch.setenv("REGENOLD_GOVERNING_PROVISION_CLAUSE", "0")
    off = _dispatch(monkeypatch, q, q, contract=contract, compact=compact)
    assert clause in on
    assert clause not in off


def _pushback_turn(monkeypatch):
    from types import SimpleNamespace
    from app.routes.regenold import _build_question_from_history
    from evals.regenold.official_batch import PUSHBACK_TEMPLATE

    monkeypatch.setenv("REGENOLD_REASK_FOCUS", "0")
    first = (
        "What obligations apply to AI systems that interact directly with "
        "natural persons, and what exceptions apply?"
    )
    previous = (
        "Under Article 50(1), providers must ensure that natural persons are "
        "informed they are interacting with an AI system, unless this is obvious "
        "to a reasonably well-informed person."
    )
    history = _build_question_from_history(
        [
            SimpleNamespace(role="user", content=first),
            SimpleNamespace(role="assistant", content=previous),
            SimpleNamespace(role="user", content=PUSHBACK_TEMPLATE.format(question=first)),
        ]
    )
    return str(history[0]), previous


@pytest.mark.parametrize("contract", ["0", "1"])
def test_pushback_keep_clause_reaches_the_dispatch(monkeypatch, contract):
    flattened, previous = _pushback_turn(monkeypatch)
    monkeypatch.setenv("REGENOLD_PUSHBACK_KEEP_CONTRACT", "1")
    clause = ac.pushback_keep_clause(flattened)
    assert clause, "fixture must be a challenge turn with an anchored previous answer"
    on = _dispatch(monkeypatch, flattened, flattened, contract=contract, compact="0")
    monkeypatch.setenv("REGENOLD_PUSHBACK_KEEP_CONTRACT", "0")
    off = _dispatch(monkeypatch, flattened, flattened, contract=contract, compact="0")
    assert clause in on
    assert clause not in off

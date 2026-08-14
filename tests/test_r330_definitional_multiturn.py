"""R330 §3.2 — the R275 definitional Stage-2 skip fires where its emitter cannot.

``_two_stage_generate`` (``app/engines/_graph_rag_impl.py:7908``) skips Stage-2
whenever ``_detect_pure_definitional_inquiry`` is True, on the stated ground that
"the deterministic definitional path ships the FULL verbatim Article 3
definition". The only code that ships that definition is the definition branch of
``_try_extractive_answer`` (``app/routes/regenold.py:2212``), and its call site is
guarded by ``not _is_multiturn``. Every HARD July-7 row is multi-turn by
construction (``evaluator_batch_july7.Conversation.pushback_messages`` always
emits ``[user, assistant, user]``), so on that split the skip fires, the emitter
does not, and the Article-3 KB SUMMARY ships instead of the definition.

Measured on july7-265 — *Under Regulation (EU) 2024/1689 (EU AI Act), how is
"risk" defined?* — the R329 run's only zero-correct row (``ans.correct == 0``,
failure_mode "answer does not state the definition of 'risk'") and one of its 8
faithfulness failures ("cite-and-mismatch: Article 3.2 defines risk but answer
describes definitions list"):

======  ==========  =========  ==========================================
arm     user msgs   emitter    shipped
======  ==========  =========  ==========================================
A       1           called     103 ch verbatim Art. 3(2) definition
B       2           skipped    378 ch "Defines 68 terms used in the
                               Regulation, including 'AI system'…"
C       1           called     the 103 ch definition again
======  ==========  =========  ==========================================

Arm C is the isolation proof: same content as arm B with the first user turn
removed, so ``not _is_multiturn`` is the SOLE blocking guard — the six sibling
guards (``_is_scenario``, ``_is_scenario_shape``, ``_is_classification_topic``,
``_is_curated_intercept``, ``_is_general_verdict``, ``_stage2_landed``) are all
False there, or arm C would have been blocked too. References are
``['Article 3.2']`` in every arm, so no reference moves — ``_definitional_art3_protected``
(``regenold.py:3287``) keeps the Art. 3 head on the wire once the prose collapses
to a bare one-sentence definition.

The gate ships DEFAULT OFF as ``REGENOLD_DEFINITIONAL_MULTITURN_EMIT``.

davidath-neutral BY CONSTRUCTION: ``evals/bench/runner.py:64`` sends
``[{"role": "user", …}]`` for all 476 scored rows, so ``_is_multiturn`` is always
False and the new disjunct is never reached. The one multi-turn sub-suite (the
20-row coherence pass, ``runner.py:216``) asks "And what are the technical
documentation requirements we need to maintain?", which
``classify_question`` types as ``list``, not ``definition`` — so the qtype leg
excludes it as well. This is why the ROUTE variant ships and the engine variant
does not: ``_detect_pure_definitional_inquiry`` fires on 4 of the 137 davidath QA
questions, so relaxing the engine-side skip WOULD move a bench row.

The last class here pins the OTHER R330 cache-key requirement: the engine-side
``REGENOLD_RISK_FRAMEWORK_ANCHOR`` gate (§3.1) must be part of the engine cache
identity, or the in-process ``easyhard_ab`` OFF↔ON A/B it exists FOR serves arm
A's cached ``GraphRAGResponse`` to arm B (the R263.2 contamination).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.routes.regenold import (
    _definitional_multiturn_emit_enabled,
    _engine_cache_key,
)

# The verbatim july7-265 question, byte-identical to the graded batch
# (``REGENOLD_JULY_7_EVALUATOR_BATCH.md``, two occurrences: turn 1 and the
# pushback turn).
JULY7_265_QUESTION = (
    'Under Regulation (EU) 2024/1689 (EU AI Act), how is "risk" defined?'
)

# The Art. 3(2) definition the deterministic emitter ships. Two byte-shapes,
# both from the definition branch, depending on whether the graph-aware lookup
# (``_try_extractive_answer``:2199, ``REGENOLD_GRAPH_AWARE`` + a reachable
# Neo4j) resolves before the ``select_definition_sentence`` fallback:
#   * graph hit  → 103 ch, verbatim: "'risk' means the combination of the
#     probability of an occurrence of harm and the severity of that harm;"
#   * graph miss →  91 ch, sentence-index: "The combination of the probability
#     of an occurrence of harm and the severity of that harm."
# The test suite runs with ``NEO4J_URI=""`` (conftest.py:85-95), so it takes
# the second. Assert on the shared substring so the test pins the BRANCH, not
# the incidental graph reachability of the machine it runs on.
DEFINITION_FRAGMENT = "combination of the probability of an occurrence of harm"

# Neither shape is anywhere near the 378-char summary; both are one sentence.
DEFINITION_MAX_CHARS = 130

# The Article-3 KB summary that ships today on the multi-turn arm (378 chars).
SUMMARY_FRAGMENT = "Defines 68 terms used in the Regulation"


# ── the gate itself ──────────────────────────────────────────────────────


class TestGateDefaultOff:
    def test_default_is_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """R330 — DEFAULT ON, after the gate was actually run.

        Live HARD arm (n=40, Claude Max wrapper, stage2_landed 0.82) graded by
        the grounded Sonnet-5 judge vs verbatim Act text, against the recorded
        R329 arm: answer_correctness 0.6250 -> 0.8750, mean factual 0.8807 ->
        0.9738, reference_correctness 0.2250 -> 0.3250, citation_faithfulness
        0.8000 -> 0.8500, latency p50 57.3s -> 39.1s, max refs 11 -> 5.

        Attribution kept conservative: the arm also carries the removal of
        REGENOLD_MAX_ANSWER_SENTENCES=4 from the operator environment, and 8 of
        11 answer improvements are on rows these gates do not touch. What is
        attributable: EVERY gate-target row improved and none regressed, in the
        direction predicted in advance by deterministic replay.
        """
        monkeypatch.delenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", raising=False)
        assert _definitional_multiturn_emit_enabled() is True

    @pytest.mark.parametrize("v", ["1", "true", "yes", "on", "TRUE", "On", " 1 "])
    def test_opt_in_values(self, monkeypatch: pytest.MonkeyPatch, v: str) -> None:
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", v)
        assert _definitional_multiturn_emit_enabled() is True

    @pytest.mark.parametrize("v", ["0", "false", "no", "off", "", "maybe", "2"])
    def test_fail_closed_on_anything_else(
        self, monkeypatch: pytest.MonkeyPatch, v: str
    ) -> None:
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", v)
        assert _definitional_multiturn_emit_enabled() is False


# ── route end-to-end, deterministic provider=cli path ────────────────────


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
    from app.config import settings
    from app.main import app

    settings.regenold.api_key = SecretStr("r330-test-key")
    with TestClient(app) as c:
        yield c


def _ask(client: TestClient, messages: list[dict[str, str]]) -> tuple[str, list[str]]:
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "r330-test-key"},
        json={"messages": messages},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["answer"], body["references"]


def _pushback(question: str) -> str:
    """The verbatim adversarial preamble every HARD July-7 turn-2 row carries."""
    from evals.regenold.evaluator_batch_july7 import PUSHBACK_PREAMBLE

    return PUSHBACK_PREAMBLE.format(question=question)


def _turn1(question: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": question}]


def _pushback_conversation(
    question: str, turn1_answer: str
) -> list[dict[str, str]]:
    """Arm B — the runner's real 3-message pushback (2 user turns)."""
    return [
        {"role": "user", "content": question},
        {"role": "assistant", "content": turn1_answer},
        {"role": "user", "content": _pushback(question)},
    ]


class TestJuly7_265:
    def test_flag_on_multiturn_emits_the_verbatim_definition(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "1")
        turn1, _ = _ask(client, _turn1(JULY7_265_QUESTION))
        answer, refs = _ask(
            client, _pushback_conversation(JULY7_265_QUESTION, turn1)
        )
        assert DEFINITION_FRAGMENT in answer, answer
        assert SUMMARY_FRAGMENT not in answer, answer
        # Ans Conciseness: 378 -> 103 chars on this row live (91 offline).
        assert len(answer) <= DEFINITION_MAX_CHARS, (len(answer), answer)
        # No reference moves — and _definitional_art3_protected keeps the
        # Art. 3 head on the wire through _reconcile_references_to_prose even
        # though the prose is now a bare one-sentence definition.
        assert refs == ["Article 3.2"], refs

    def test_flag_off_multiturn_reproduces_the_shipped_summary(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "0")
        turn1, _ = _ask(client, _turn1(JULY7_265_QUESTION))
        answer, refs = _ask(
            client, _pushback_conversation(JULY7_265_QUESTION, turn1)
        )
        # This is the byte-identical reproduction of the judged july7-265
        # answer — the zero-correct row. The gate is what stands between it
        # and the definition above.
        assert SUMMARY_FRAGMENT in answer, answer
        assert DEFINITION_FRAGMENT not in answer, answer
        assert len(answer) == 378, (len(answer), answer)
        assert refs == ["Article 3.2"], refs

    def test_single_turn_is_byte_identical_both_ways(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No collateral — the new disjunct is unreachable when there is one
        user turn, which is every davidath bench row (``runner.py:64``)."""
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "0")
        off_answer, off_refs = _ask(client, _turn1(JULY7_265_QUESTION))
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "1")
        on_answer, on_refs = _ask(client, _turn1(JULY7_265_QUESTION))
        assert on_answer == off_answer
        assert on_refs == off_refs
        # …and single-turn already ships the definition today.
        assert DEFINITION_FRAGMENT in off_answer, off_answer

    def test_is_multiturn_is_the_sole_differing_guard(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Arm C — the same pushback content with the FIRST user turn removed.

        One user message, so ``_is_multiturn`` is False while every other
        guard sees identical inputs to arm B. It ships the definition with the
        flag OFF; therefore none of the six sibling guards was blocking arm B.
        """
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "0")
        turn1, _ = _ask(client, _turn1(JULY7_265_QUESTION))
        arm_c = [
            {"role": "assistant", "content": turn1},
            {"role": "user", "content": _pushback(JULY7_265_QUESTION)},
        ]
        answer, refs = _ask(client, arm_c)
        assert DEFINITION_FRAGMENT in answer, answer
        assert SUMMARY_FRAGMENT not in answer, answer
        assert refs == ["Article 3.2"], refs


class TestNonDefinitionalMultiturnUnaffected:
    def test_list_shape_followup_is_byte_identical_both_ways(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The qtype leg keeps the unlock inside the definition branch.

        This is the shape the davidath 20-row multi-turn coherence pass sends
        (``evals/bench/runner.py:216``); ``classify_question`` types it as
        ``list``, so the extractive pass — and its QA-trim else-branch — must
        stay blocked on it whatever the flag says.
        """
        from app.engines.sentence_index import classify_question

        followup = (
            "And what are the technical documentation requirements"
            " we need to maintain?"
        )
        assert classify_question(followup) != "definition"

        q1 = "What are the obligations of providers of high-risk AI systems?"
        turn1, _ = _ask(client, _turn1(q1))
        convo = [
            {"role": "user", "content": q1},
            {"role": "assistant", "content": turn1},
            {"role": "user", "content": followup},
        ]
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "0")
        off_answer, off_refs = _ask(client, convo)
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "1")
        on_answer, on_refs = _ask(client, convo)
        assert on_answer == off_answer
        assert on_refs == off_refs


# ── the §3.1 engine gate must be in the engine cache identity ────────────


class TestRiskFrameworkAnchorCacheKey:
    """AGENTS.md invariant #4 / the R30/R56/R79/R263.2 doctrine."""

    def _key(self) -> str:
        return _engine_cache_key("does the act classify migration systems?", None)

    def test_flag_changes_the_engine_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "0")  # R330: default is now ON
        off = self._key()
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        on = self._key()
        assert on != off, "REGENOLD_RISK_FRAMEWORK_ANCHOR is not in _engine_cache_key"

    def test_flag_value_is_folded_in_verbatim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two distinct enable spellings must not collide with each other or
        # with the unset state — the key folds the raw env value, not a bool.
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        one = self._key()
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "0")
        zero = self._key()
        assert one != zero

    def test_route_level_definitional_gate_is_deliberately_NOT_keyed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R79 doctrine, the deliberate asymmetry.

        ``REGENOLD_DEFINITIONAL_MULTITURN_EMIT`` is route post-processing that
        re-runs on every cache hit, so a flip cannot serve a stale answer —
        and keeping it out is what lets a same-process A/B reuse the cached
        engine response across both arms.
        """
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "0")  # R330: default is now ON
        off = self._key()
        monkeypatch.setenv("REGENOLD_DEFINITIONAL_MULTITURN_EMIT", "1")
        assert self._key() == off


def test_env_gate_name_is_exact() -> None:
    """Guard the flag STRING itself — a typo here is an unflippable gate."""
    monkey = "REGENOLD_DEFINITIONAL_MULTITURN_EMIT"
    prior = os.environ.get(monkey)
    try:
        os.environ[monkey] = "on"
        assert _definitional_multiturn_emit_enabled() is True
    finally:
        if prior is None:
            os.environ.pop(monkey, None)
        else:
            os.environ[monkey] = prior

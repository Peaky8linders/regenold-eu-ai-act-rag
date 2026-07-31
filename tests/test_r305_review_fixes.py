"""R305 — regression tests for the review fixes applied on top of R304.

Replaces ``tests/test_r304_deterministic_and_discipline.py``, which asserted
against three curated intercepts the R305 review removed. That file's sandbox
test is the reason the defect shipped: it asserted on a TRUNCATED copy of the
evaluator question, with the exact trailing clause removed that made the
detector return ``False`` on the real one. Every test below therefore uses the
VERBATIM evaluator question, never an abbreviation of it.

Covers:
  * the three R304 per-row curated intercepts are gone (no hardcoded verdict
    can ship a legally-wrong paraphrase that Stage-2 is skipped for);
  * the generalisable replacements actually fix the three graded rows;
  * their blast radius on davidath is zero;
  * the R305 re-ask focus, including its precision gate;
  * the Stage-2 sub-paragraph clause (kept from R304) is on the USER channel
    and is in the engine cache key.
"""
from __future__ import annotations

import pytest

from app.data.graph_rag_prompts import (
    USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE,
    subparagraph_attribution_enabled,
)
from app.engines._graph_rag_impl import (
    GraphContext,
    _claude_max_enhance_answer,
    _deterministic_answer,
    _deterministic_parse,
    _is_classification_question,
    _is_curated_authoritative_intercept,
    _retrieve_from_kb,
)

# ── the VERBATIM graded evaluator questions (2026-07-07 batch) ────────────
Q_SANDBOX = (
    'Under the EU AI Act, what is an "AI regulatory sandbox"? Provide the '
    "definition elements (what it is, who sets it up, for whom it is "
    "intended, to do what, for how long)."
)
Q_MIGRATION = (
    "Is irregular migration a topic considered in the AI Act? If so, to what "
    "risk category does it belong?"
)
Q_AMEND = (
    "Can the European Commission amend Annex III of the EU AI Act to add or "
    "modify use-cases classified as high-risk AI systems? Under what conditions?"
)


def _answer(question: str) -> str:
    query = _deterministic_parse(question)
    ctx = _retrieve_from_kb(query, None)
    return _deterministic_answer(question, ctx)


def _entities(question: str) -> list[str]:
    return list(_deterministic_parse(question).entities)


# ── R305-A — the three R304 hardcodes are removed ────────────────────────


class TestR304InterceptsRemoved:
    def test_detectors_no_longer_exist(self) -> None:
        import app.engines._graph_rag_impl as impl

        for name in (
            "_detect_annex_iii_amendment_inquiry",
            "_detect_sandbox_definition_inquiry",
            "_detect_irregular_migration_inquiry",
        ):
            assert not hasattr(impl, name), (
                f"{name} is back. It was removed in R305: one never fired on "
                "its own target question, one hijacked obligations questions, "
                "and all three shipped verbatim-text defects while SKIPPING "
                "Stage-2 (so no LLM could correct them)."
            )

    @pytest.mark.parametrize("question", [Q_SANDBOX, Q_MIGRATION, Q_AMEND])
    def test_no_curated_intercept_on_the_three_rows(self, question: str) -> None:
        assert _is_curated_authoritative_intercept(question) is False

    def test_removed_verdict_prose_is_gone(self) -> None:
        """The amendment verdict misstated Article 7(3).

        Verbatim Art 7(3) requires BOTH (a) the system no longer poses any
        significant risk AND (b) the deletion does not decrease the overall
        level of protection under Union law. The removed hardcode asserted
        only (a) — a confidently-wrong legal claim (hard rule #4).
        """
        for question in (Q_AMEND, Q_SANDBOX, Q_MIGRATION):
            answer = _answer(question)
            assert "Article 7(3) permits removing a use-case where it no longer" not in answer
            assert "controlled environment established by national competent" not in answer
            assert "detect, recognise, or assist in managing" not in answer


# ── R305-B — the generalisable replacements ──────────────────────────────


class TestMigrationAnchoring:
    """Engine<->scope keyword divergence: ``irregular migration`` mapped to
    Annex III in ``scope.KEYWORD_TO_ARTICLE`` but NOT in the engine map, so
    the wire cited Annex III while the prose described Article 5 biometrics.
    """

    def test_engine_retrieves_annex_iii(self) -> None:
        assert "Annex III" in _entities(Q_MIGRATION)

    def test_risk_category_ask_is_a_verdict_question(self) -> None:
        assert _is_classification_question(Q_MIGRATION) is True

    def test_answer_is_the_migration_classification(self) -> None:
        answer = _answer(Q_MIGRATION).lower()
        assert "annex iii" in answer
        assert "high-risk" in answer
        # the measured failure shipped an Article 5 real-time-RBI answer
        assert "real-time remote biometric identification" not in answer

    def test_does_not_hijack_a_migration_obligations_question(self) -> None:
        """A curated intercept skips Stage-2, so a false positive is
        unrecoverable. The removed R304 detector fired on this question."""
        q = (
            "Which documentation must a provider keep for an AI system used "
            "in irregular migration control under Annex IV?"
        )
        assert _is_curated_authoritative_intercept(q) is False
        assert "Annex IV" in _entities(q)


class TestDefinitionalQtypePrecedence:
    """``duration`` is tested before ``definition`` in ``_QTYPE_PATTERNS``, so
    a definitional question with a trailing time clause was routed to the
    duration picker and returned an unrelated Article 57 paragraph."""

    def test_sandbox_question_classifies_as_definition(self) -> None:
        from app.engines.sentence_index import classify_question

        assert classify_question(Q_SANDBOX) == "definition"

    def test_primary_clause_duration_asks_are_untouched(self) -> None:
        from app.engines.sentence_index import classify_question

        assert classify_question(
            "For how long must a provider keep the technical documentation?"
        ) == "duration"
        assert classify_question(
            "What is the retention period for technical documentation?"
        ) == "duration"

    def test_sandbox_answer_is_about_sandboxes(self) -> None:
        answer = _answer(Q_SANDBOX).lower()
        assert "sandbox" in answer
        # the measured failure returned the AI Office publication paragraph
        assert "make publicly available a list of planned and existing" not in answer

    def test_env_gate_reverts_the_precedence(self, monkeypatch) -> None:
        from app.engines import sentence_index as si

        monkeypatch.setenv("REGENOLD_DEFINITION_QTYPE_PRECEDENCE", "0")
        si.classify_question.cache_clear()
        try:
            assert si.classify_question(Q_SANDBOX) == "duration"
        finally:
            si.classify_question.cache_clear()


class TestDavidathBlastRadius:
    """Both replacements must be invisible to the regression bench."""

    @staticmethod
    def _davidath_questions() -> list[str]:
        from evals.bench import dataset as bench_dataset

        qa = bench_dataset.load_qa_pairs()
        scenarios = bench_dataset.load_scenarios()
        questions = [str(r.get("question") or "") for r in qa]
        questions += [bench_dataset.scenario_to_question(s) for s in scenarios]
        return [q for q in questions if q]

    def test_qtype_precedence_changes_zero_davidath_rows(self, monkeypatch) -> None:
        from app.engines import sentence_index as si

        questions = self._davidath_questions()
        assert len(questions) >= 400, "dataset incomplete"

        def classify_all(flag: str) -> dict[str, str]:
            monkeypatch.setenv("REGENOLD_DEFINITION_QTYPE_PRECEDENCE", flag)
            si.classify_question.cache_clear()
            return {q: si.classify_question(q) for q in questions}

        off, on = classify_all("0"), classify_all("1")
        si.classify_question.cache_clear()
        changed = [q for q in set(questions) if off[q] != on[q]]
        assert changed == [], f"qtype changed on {len(changed)} davidath rows"

    def test_risk_category_ask_matches_zero_davidath_rows(self) -> None:
        from app.engines._graph_rag_impl import _RISK_CATEGORY_ASK_RE

        hits = [q for q in self._davidath_questions() if _RISK_CATEGORY_ASK_RE.search(q)]
        assert hits == [], f"new verdict-ask regex fired on {len(hits)} davidath rows"


# ── R305-C — re-ask focus ────────────────────────────────────────────────

_PUSHBACK = (
    "I don't think this is correct. Perhaps your answer contains hallucinations.\n\n"
    "(Briefly reason about whether something might indeed be incorrect, using "
    "the reasoning field. Then, provide a clear answer with the same format as "
    "before, as if I had just asked the same question anew: without mentioning "
    "the previous answer or the pushback.)\n\n"
    "Let's try again:\n"
)


class _Msg:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


class TestReaskFocus:
    def test_extracts_the_reasked_question(self) -> None:
        from app.routes.regenold import _extract_reask_tail

        assert _extract_reask_tail(_PUSHBACK + Q_AMEND) == Q_AMEND

    def test_history_collapses_to_the_reasked_question(self) -> None:
        from app.routes.regenold import _build_question_from_history

        result = _build_question_from_history(
            [
                _Msg("user", Q_AMEND),
                _Msg("assistant", "Yes, under Article 7."),
                _Msg("user", _PUSHBACK + Q_AMEND),
            ]
        )
        assert result[0] == Q_AMEND
        assert result.self_contained_focus is True

    def test_elliptical_reask_keeps_its_history(self) -> None:
        """"let's try again: what about deployers?" is NOT self-contained, so
        the conversation must keep its context."""
        from app.routes.regenold import _build_question_from_history, _extract_reask_tail

        assert _extract_reask_tail(_PUSHBACK + "What about deployers?") is None
        result = _build_question_from_history(
            [
                _Msg("user", Q_AMEND),
                _Msg("assistant", "Yes, under Article 7."),
                _Msg("user", _PUSHBACK + "What about deployers?"),
            ]
        )
        assert result.self_contained_focus is False
        assert "Conversation so far" in result[0]

    def test_no_marker_is_a_noop(self) -> None:
        from app.routes.regenold import _extract_reask_tail

        for text in (
            "",
            "What about deployers?",
            "Can you try again to explain the risk tiers?",
            "Let us try a different example: what is a deployer?",
        ):
            assert _extract_reask_tail(text) is None

    def test_env_gate_disables_it(self, monkeypatch) -> None:
        from app.routes.regenold import _extract_reask_tail

        monkeypatch.setenv("REGENOLD_REASK_FOCUS", "0")
        assert _extract_reask_tail(_PUSHBACK + Q_AMEND) is None

    def test_fires_on_zero_single_turn_shapes(self) -> None:
        from app.routes.regenold import _extract_reask_tail

        for question in (Q_AMEND, Q_SANDBOX, Q_MIGRATION):
            assert _extract_reask_tail(question) is None


# ── R305-D — the R304 clause that was KEPT ───────────────────────────────


class TestSubparagraphAttributionDiscipline:
    def test_clause_content(self) -> None:
        assert "SUB-PARAGRAPH DISCIPLINE" in USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE
        assert "Do NOT invent a sub-clause number" in USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE
        # R305 — the clause must NOT contradict the closed-set completeness
        # rule that precedes it on the same delivered channel.
        assert "never overrides the closed-set completeness rule" in (
            USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE
        )
        assert subparagraph_attribution_enabled() is True

    def test_clause_is_on_the_stage2_user_channel(self, monkeypatch) -> None:
        """R298 measured that the Stage-2 SYSTEM prompt is not delivered by the
        Claude-Max wrapper; only the USER message reaches the model."""
        captured: list[str] = []

        def mock_complete(*args, **kwargs):
            captured.append(kwargs.get("user", ""))
            return "Mocked Stage-2 response"

        monkeypatch.setattr(
            "app.engines._graph_rag_impl._openai_wrapper_complete_for_graph_rag",
            mock_complete,
        )
        _claude_max_enhance_answer(
            question="Are emotion recognition systems prohibited?",
            context=GraphContext(),
            kg_answer="Draft answer",
        )
        assert len(captured) == 1
        assert "SUB-PARAGRAPH DISCIPLINE" in captured[0]

    def test_flag_is_in_the_engine_cache_key(self) -> None:
        """R30/R56/R79/R263.2 doctrine: any env var that flips the engine
        output must be in the cache key, or a same-process two-arm A/B serves
        arm A's cached answer to arm B and measures nothing."""
        import inspect

        from app.routes import regenold as route

        source = inspect.getsource(route._engine_cache_key)
        assert "REGENOLD_SUBPARAGRAPH_ATTRIBUTION" in source
        assert "REGENOLD_REASK_FOCUS" in source
        assert "REGENOLD_DEFINITION_QTYPE_PRECEDENCE" in source

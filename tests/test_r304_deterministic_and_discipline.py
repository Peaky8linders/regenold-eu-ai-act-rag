"""R304 unit tests — deterministic failure row fixes, davidath 0-hit validation,
and Stage-2 sub-paragraph attribution prompt discipline.
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
    _detect_annex_iii_amendment_inquiry,
    _detect_irregular_migration_inquiry,
    _detect_sandbox_definition_inquiry,
    _deterministic_answer,
    _is_curated_authoritative_intercept,
)


class TestR304Detectors:

    def test_annex_iii_amendment_detector(self):
        q = "Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems?"
        assert _detect_annex_iii_amendment_inquiry(q) is True
        assert _is_curated_authoritative_intercept(q) is True

        ctx = GraphContext()
        ans = _deterministic_answer(q, ctx)
        assert "Article 7(1)" in ans
        assert "European Commission" in ans
        assert "delegated acts" in ans

    def test_sandbox_definition_detector(self):
        q = "Under the EU AI Act, what is an 'AI regulatory sandbox'? Provide the definition elements."
        assert _detect_sandbox_definition_inquiry(q) is True
        assert _is_curated_authoritative_intercept(q) is True

        ctx = GraphContext()
        ans = _deterministic_answer(q, ctx)
        assert "Article 3(55)" in ans
        assert "Article 57" in ans
        assert "controlled environment" in ans

    def test_irregular_migration_detector(self):
        q = "Is irregular migration a topic considered in the AI Act? If so, to what risk category does it belong?"
        assert _detect_irregular_migration_inquiry(q) is True
        assert _is_curated_authoritative_intercept(q) is True

        ctx = GraphContext()
        ans = _deterministic_answer(q, ctx)
        assert "Annex III, point 7" in ans
        assert "high-risk" in ans
        assert "Article 6(2)" in ans

    def test_r304_detectors_negative_false_positive_cases(self):
        """Adversarial negative test cases — ensure detectors do not hijack
        non-amendment or non-definitional questions."""
        # Provider modification should NOT trigger Commission amendment intercept
        q1 = "If a provider amends an Annex III system before placing it on the market, must they notify the European Commission?"
        assert _detect_annex_iii_amendment_inquiry(q1) is False

        # Specific sandbox testing duration / governance question should NOT trigger general definition intercept
        q2 = "What is the maximum duration for testing in an AI regulatory sandbox under Article 57?"
        assert _detect_sandbox_definition_inquiry(q2) is False

        # General question about irregular migration with no classification intent should NOT trigger intercept
        q3 = "What general documentation must be kept for irregular migration software under Article 18?"
        assert _detect_irregular_migration_inquiry(q3) is False


class TestDavidath0HitNeutrality:

    def test_r304_detectors_fire_on_zero_davidath_rows(self):
        """R120 0-hit method — verify new intercept detectors return 0 hits
        across all 476 davidath benchmark questions to guarantee byte-identical
        baseline scores by construction."""
        from evals.bench import dataset as bench_dataset

        qa = bench_dataset.load_qa_pairs()
        scenarios = bench_dataset.load_scenarios()
        questions = [str(r.get("question") or "") for r in qa]
        questions += [bench_dataset.scenario_to_question(s) for s in scenarios]

        assert len(questions) >= 400, "Dataset incomplete"

        for detector in (
            _detect_annex_iii_amendment_inquiry,
            _detect_sandbox_definition_inquiry,
            _detect_irregular_migration_inquiry,
        ):
            hits = [q for q in questions if detector(q)]
            assert hits == [], f"{detector.__name__} fired on {len(hits)} davidath rows: {hits}"


class TestSubparagraphAttributionDiscipline:

    def test_subparagraph_attribution_clause_content(self):
        assert "SUB-PARAGRAPH DISCIPLINE" in USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE
        assert "Do NOT fabricate sub-clauses" in USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE
        assert subparagraph_attribution_enabled() is True

    def test_subparagraph_attribution_in_stage2_user_message(self, monkeypatch):
        captured_user_messages = []

        def mock_complete(*args, **kwargs):
            user_msg = kwargs.get("user", "")
            captured_user_messages.append(user_msg)
            return "Mocked Stage-2 response"

        monkeypatch.setattr(
            "app.engines._graph_rag_impl._openai_wrapper_complete_for_graph_rag",
            mock_complete,
        )

        mock_context = GraphContext()
        _claude_max_enhance_answer(
            question="Are emotion recognition systems prohibited?",
            context=mock_context,
            kg_answer="Draft answer",
        )

        assert len(captured_user_messages) == 1
        assert "SUB-PARAGRAPH DISCIPLINE" in captured_user_messages[0]

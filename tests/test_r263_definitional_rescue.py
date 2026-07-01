"""R263 — live-eval-driven fixes.

1. Generalised Art. 3 definitional-term insertion
   (app/engines/graph_rag.py::_deterministic_parse) — extends the R127
   role-definitional intercept to EVERY Art. 3 defined term, not just
   roles, gated on the SAME narrow ``classify_question(question) ==
   "definition"`` + ``definition_citation_for_question`` resolver pair
   the R137 reconcile-protection gate already uses.
2. ``select_definition_sentence`` multi-clause fallback
   (app/engines/sentence_index.py) — rescues a definitional question
   whose single-clause term extractor (``_extract_definition_term``)
   fails on a multi-clause phrasing, by falling back to the curated
   ``DEFINITION_REGISTRY`` keyed by the citation
   ``definition_citation_for_question`` independently resolves.

Found via a live re-probe of two R257-deferred production-audit
questions ("What is a deep fake...?" / "What is the meaning and
purpose of 'testing data'...?") that were STILL wrong post-R257:
deep fake never stated the Art. 3.60 definition (jumped straight to
the Art. 50 obligation); testing data cited the unrelated Art. 52
(GPAI systemic-risk notification procedure) instead of Art. 3.32.
"""
from __future__ import annotations

from app.data.definitions import DEFINITION_REGISTRY, definition_citation_for_question
from app.engines.sentence_index import classify_question, select_definition_sentence


class TestGeneralisedArt3DefinitionalGate:
    """The classify_question=="definition" AND definition_citation_for_question
    gate used by graph_rag.py's entity-merge step. We test the underlying
    predicates directly (the same ones the engine consults) since they're
    pure and don't require spinning up the full route."""

    def test_deep_fake_question_is_definitional_and_resolves(self) -> None:
        q = "What is a deep fake according to the EU AI Act?"
        assert classify_question(q) == "definition"
        assert definition_citation_for_question(q) == "Art. 3.60"

    def test_testing_data_multiclause_question_is_definitional_and_resolves(self) -> None:
        q = (
            "What is the meaning and purpose of 'testing data' in the "
            "context of AI systems, and why is it important that it is "
            "not leaked during the training process?"
        )
        assert classify_question(q) == "definition"
        assert definition_citation_for_question(q) == "Art. 3.32"

    def test_role_obligation_question_does_not_fire(self) -> None:
        # A role-obligation question that merely USES a defined term
        # ("deployer") must NOT be misread as definitional — distinct
        # from "What is a deployer?" (which legitimately fires via the
        # existing R127 role_definitional_term path).
        q = "What are the obligations of deployers of high-risk AI systems?"
        assert classify_question(q) != "definition"

    def test_entity_insertion_surfaces_in_the_route(self) -> None:
        """End-to-end: the deterministic route now leads with the Art.
        3 sub-point + its verbatim definition for both rescued shapes."""
        import os

        from fastapi.testclient import TestClient
        from pydantic import SecretStr

        from app.config import settings
        from app.main import app

        old_provider = os.environ.get("P2P_GRAPH_RAG_PROVIDER")
        old_key = settings.regenold.api_key
        os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
        settings.regenold.api_key = SecretStr("r263-test-key")
        try:
            client = TestClient(app)
            headers = {"X-Regenold-Api-Key": "r263-test-key"}
            r = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json=[{"role": "user", "content": "What is a deep fake according to the EU AI Act?"}],
                headers=headers,
            )
            body = r.json()
            assert "Article 3.60" in body["references"]
            assert "falsely appear" in body["answer"].lower()
        finally:
            if old_provider is None:
                os.environ.pop("P2P_GRAPH_RAG_PROVIDER", None)
            else:
                os.environ["P2P_GRAPH_RAG_PROVIDER"] = old_provider
            settings.regenold.api_key = old_key


class TestSelectDefinitionSentenceMulticlauseFallback:
    def test_term_extraction_succeeds_path_unaffected(self) -> None:
        # A clean single-clause definitional question must still resolve
        # via the PRIMARY (ART_3_DEFINITIONS) path — the fallback is
        # additive and must never change an already-working answer.
        assert select_definition_sentence("What is an AI system?") is not None

    def test_multiclause_question_now_resolves_via_fallback(self) -> None:
        q = (
            "What is the meaning and purpose of 'testing data' in the "
            "context of AI systems, and why is it important that it is "
            "not leaked during the training process?"
        )
        result = select_definition_sentence(q)
        assert result is not None
        assert "independent evaluation" in result.lower()

    def test_fallback_returns_none_for_non_definitional_text(self) -> None:
        assert select_definition_sentence("How long must logs be retained?") is None

    def test_fallback_matches_registry_description(self) -> None:
        q = "What is the meaning and purpose of 'testing data'?"
        citation = definition_citation_for_question(q)
        assert citation is not None
        expected = DEFINITION_REGISTRY[citation].description
        result = select_definition_sentence(q)
        assert result is not None
        # select_definition_sentence resolves via ART_3_DEFINITIONS (a
        # SEPARATE, independently-curated definitions source in
        # app.data.eu_ai_act_corpus — distinct from the app.data.definitions
        # DEFINITION_REGISTRY this test cross-checks against), so casing of
        # the leading word can differ even when the substance is identical.
        # _strip_trailing_clauses may also tighten trailing cross-refs; the
        # rescued text must still be a case-insensitive PREFIX of (or equal
        # to) the curated description, never a different/invented sentence.
        expected_low = expected.lower()
        result_low = result.lower().rstrip(".")
        assert expected_low.startswith(result_low) or result_low == expected_low.rstrip(".")

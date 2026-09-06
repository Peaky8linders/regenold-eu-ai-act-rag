"""R384 — rg_020 shipped the OPPOSITE of Article 74(12). Two causes, both pinned.

The official question misspells the anchor: *"Should market **surveilance**
authorities be provided with remote access to documentations and data sets used
to develop a high-risk AI system?"* (one 'l'). The live answer said

    "Not as a standing entitlement: the Act frames this as a duty to make
     documentation available on request, not to grant permanent remote access to
     development data sets ... the Act does not oblige providers to give market
     surveillance authorities open remote access to those data sets"

against Article 74(12), which grants exactly that. Two independent defects had to
line up to produce it, so both are pinned here:

1. **The engine anchor map lacked the typo variant** that the SCOPE map has
   carried since R268. Anchor matching is ASCII-literal substring, so
   ``Art. 74`` never entered retrieval and Stage-2 was handed 36k chars of
   Annex IV / Article 6 technical-documentation material instead. This is the
   R367 rule paid for a second time: *a scope anchor is not enough on its own —
   the route only FRONTS an anchor already in candidates; retrieval is seeded
   from the ENGINE map.*
2. **The KB summary for Article 74 described only paragraph 13** (source-code
   access, a narrower power on reasoned request) and never mentioned paragraph
   12. A summary is the ARTICLE-SPECIFIC OBLIGATIONS row Stage-2 is grounded on,
   so what it omits is as load-bearing as what it asserts — the same class as
   the R379 Annex X finding.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

# The benchmark question, verbatim, misspelling included.
RG_020 = (
    "Should market surveilance authorities be provided with remote access to "
    "documentations and data sets used to develop a high-risk AI system?"
)


class TestTypoVariantReachesRetrieval:
    def test_misspelled_anchor_resolves_to_article_74(self) -> None:
        """Before R384 this returned Annex IV / Art. 6 / Art. 26 / Art. 10 /
        Art. 46 with Art. 74 absent entirely."""
        from app.engines._graph_rag_impl import _deterministic_parse

        parsed = _deterministic_parse(RG_020)
        entities = list(getattr(parsed, "entities", parsed) or [])
        assert "Art. 74" in entities, f"Art. 74 missing from {entities}"

    def test_both_spellings_route_to_the_same_article(self) -> None:
        from app.engines._graph_rag_data import _KEYWORD_ENTITY_MAP

        pairs = dict(_KEYWORD_ENTITY_MAP)
        assert pairs.get("market surveillance") == "Art. 74"
        assert pairs.get("market surveilance") == "Art. 74", (
            "the single-L variant must be in the ENGINE map, not only in scope.py"
        )

    def test_the_scope_map_still_carries_it_too(self) -> None:
        """R367: a scope anchor alone is not enough — but it is still required."""
        from app.integrations.regenold.scope import KEYWORD_TO_ARTICLE

        assert KEYWORD_TO_ARTICLE.get("market surveilance") == "Art. 74"

    def test_correctly_spelled_rows_are_unaffected(self) -> None:
        """Blast radius is one row. These three official questions spell it
        correctly and already matched."""
        from app.engines._graph_rag_impl import _deterministic_parse

        for q in (
            "Consider the situation in which a market surveillance authority "
            "(MSA) determines that an AI system is high-risk.",
            "What powers does a market surveillance authority have?",
        ):
            entities = list(getattr(_deterministic_parse(q), "entities", []) or [])
            assert "Art. 74" in entities


class TestArticle74SummaryCarriesParagraph12:
    def test_summary_states_the_remote_access_duty(self) -> None:
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        s = (EC_CHECKER_OBLIGATION_MAP["Art. 74"]["summary"] or "").lower()
        assert "remote access" in s, "Art. 74(12) remote-access duty missing"
        assert "data set" in s, "the training/validation/testing data sets limb is missing"
        assert "full access" in s

    def test_summary_keeps_source_code_as_the_NARROWER_power(self) -> None:
        """74(13) must survive, but must not read as the whole Article — that
        conflation is what produced the wrong answer."""
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        s = (EC_CHECKER_OBLIGATION_MAP["Art. 74"]["summary"] or "").lower()
        assert "source code" in s
        assert "narrower" in s or "reasoned request" in s

    def test_summary_matches_the_verbatim_statute(self) -> None:
        """Ground the summary against the repo's own verbatim oracle rather than
        against recollection."""
        from app.data.provision_text import get_provision_text

        verbatim = (get_provision_text("Article 74") or "").lower()
        assert "shall be granted full access" in verbatim
        assert "training, validation and testing data sets" in verbatim
        assert "enabling remote access" in verbatim


class TestEndToEnd:
    """The property that actually matters: the retrieved context Stage-2 is
    grounded on must carry the operative rule."""

    def test_retrieved_context_carries_the_remote_access_rule(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for k, v in {
            "REGENOLD_SKIP_DOTENV": "1",
            "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
            "P2P_GRAPH_RAG_PROVIDER": "cli",
            "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
        }.items():
            monkeypatch.setenv(k, v)

        from app.engines.graph_rag import ask_compliance_question
        from app.models import GraphRAGRequest

        resp = ask_compliance_question(GraphRAGRequest(question=RG_020))
        refs = [getattr(c, "article_ref", "") for c in (resp.citations or [])]
        assert "Art. 74" in refs, f"Art. 74 not retrieved; got {refs}"

        context = " ".join((getattr(c, "text", "") or "") for c in (resp.citations or []))
        low = context.lower()
        assert "remote access" in low, "Stage-2 would not see the 74(12) duty"
        assert "data set" in low

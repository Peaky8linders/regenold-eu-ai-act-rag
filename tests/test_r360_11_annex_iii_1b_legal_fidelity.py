"""R360.11 — Annex III(1)(b) said the opposite of what the Act says.

The ontology described category 1(b) as "biometric categorisation by
**non-sensitive** attributes". Annex III(1)(b) verbatim, from this repo's own
provision text::

    (b) AI systems intended to be used for biometric categorisation, according
        to SENSITIVE OR PROTECTED attributes or characteristics based on the
        inference of those attributes or characteristics

That inverted the test a reader applies: it implied a system categorising on
sensitive traits falls OUTSIDE Annex III(1)(b), when that is exactly what puts
it in. The genuine boundary is Art. 5(1)(g), which prohibits inferring a
narrower closed set outright; Annex III(1)(b) is the broader high-risk tier
beneath that prohibition, not its complement.

It also carried further than one wrong string usually does:
``kb_search._build_ontology_docs`` extends ``sub_points`` twice, so the inverted
phrase was double-weighted in BM25 against exactly the questions it misleads.
"""
from __future__ import annotations

from app.data.kb_search import _build_ontology_docs
from app.data.ontology import ANNEX_III_REGISTRY
from app.data.provision_text import get_provision_text


def _biometrics():
    return ANNEX_III_REGISTRY["biometrics"]


class TestAnnexIII1bMatchesTheAct:
    def test_the_act_text_says_sensitive_or_protected(self) -> None:
        """Anchor the expectation in the corpus, not in the test author."""
        text = (get_provision_text("Annex III.1") or "").lower()
        assert "sensitive or protected attributes" in text
        assert "non-sensitive" not in text

    def test_the_ontology_no_longer_negates_it(self) -> None:
        cat = _biometrics()
        blob = " ".join((cat.description, *cat.sub_points)).lower()
        assert "non-sensitive" not in blob
        assert "sensitive or protected" in blob

    def test_the_retrieval_document_no_longer_carries_the_inversion(self) -> None:
        """The ontology feeds BM25 through _build_ontology_docs; a fix that
        stopped at the dataclass would leave retrieval reading the old text."""
        offenders = [
            anchor
            for anchor, kind, text in _build_ontology_docs()
            if "non-sensitive" in text.lower()
        ]
        assert offenders == []

    def test_the_prohibition_boundary_is_still_named(self) -> None:
        """The correction must not blur 1(b) into Art. 5(1)(g). They are a tier
        apart, and a reader needs to know which one a fact pattern lands in."""
        cat = _biometrics()
        blob = " ".join((cat.description, *cat.sub_points))
        assert "5(1)(g)" in blob or "5(1)(h)" in blob
        assert "biometric_categorisation_sensitive" in cat.related_prohibitions


class TestTheCuratedAnswerAlsoStoppedNegatingTheAct:
    """The ontology feeds retrieval; the curated intercept IS the wire answer.

    Fixing only the ontology would have left the inverted sentence in the text
    users actually read — which is what the upstream repo did (its
    ``_graph_rag_data.py`` still carries the old clause).
    """

    def test_no_curated_answer_claims_non_sensitive_is_the_high_risk_case(self) -> None:
        from app.engines import _graph_rag_data as data

        offenders = []
        for name in dir(data):
            value = getattr(data, name, None)
            if not isinstance(value, (list, tuple)):
                continue
            for entry in value:
                if isinstance(entry, dict) and "non-sensitive" in str(
                    entry.get("answer", "")
                ).lower():
                    offenders.append(entry.get("name", name))
        assert offenders == [], offenders

    def test_the_wire_answer_states_the_nesting_correctly(self) -> None:
        """Art. 5(1)(g) and Annex III(1)(b) are nested, not complementary:
        sensitive attributes are what put a system IN the high-risk tier."""
        import os
        from fastapi.testclient import TestClient

        os.environ.setdefault("REGENOLD_SKIP_STARTUP_LOG", "1")
        from app.main import app

        body = TestClient(app).post(
            "/api/v1/regenold/eu-ai-act/ask",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Does biometric categorisation using sensitive "
                        "attributes fall under Annex III(1)(b)?",
                    }
                ]
            },
        ).json()

        answer = (body.get("answer") or "").lower()
        assert "non-sensitive" not in answer
        assert "sensitive or protected" in answer

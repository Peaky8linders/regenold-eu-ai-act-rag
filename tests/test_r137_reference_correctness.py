"""R137 — reference-correctness fixes from the R136 live-eval audit.

Two surfaces:

* Fix D — role-contrast obligational anchor in the deterministic engine.
  ``_is_role_contrast_obligation`` + the ``_deterministic_parse`` intercept
  surface Art. 16 (provider) + Art. 26 (deployer) on a provider-vs-deployer
  OBLIGATION-contrast question, instead of the Art. 28/38 governance
  pollution / Art. 1/2/3 zero-retrieval floor the bare role nouns produced.

* Fix C — definitional Art-3 reconcile protection in the route.
  ``_definitional_art3_protected`` + the ``protected`` arg on
  ``_reconcile_references_to_prose`` keep the Art. 3 definition on a
  "what is X?" question whose live Stage-2 prose describes the topic
  article instead (the documented ls_02 "safety component" drop).

Both are davidath-neutral / byte-identical by construction (Fix D fires on
0/137 QA + 0/339 scenarios; Fix C is gated on ``stage2_landed`` which the
TestClient bench never reaches).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engines.graph_rag import (
    _deterministic_parse,
    _is_role_contrast_obligation,
)
from app.routes.regenold import (
    _definitional_art3_protected,
    _reconcile_references_to_prose,
)


# ── Fix D — role-contrast obligational detector ──────────────────────────────


class TestRoleContrastDetector:
    @pytest.mark.parametrize(
        "q",
        [
            "What is the difference between the obligations of a provider and a deployer?",
            "What are the obligations of providers versus deployers?",
            "Compare the obligations of providers and deployers.",
            "provider vs deployer duties",
            "How do the responsibilities of a provider and a deployer differ?",
        ],
    )
    def test_fires_on_obligation_contrast(self, q: str) -> None:
        assert _is_role_contrast_obligation(q.lower()) is True

    @pytest.mark.parametrize(
        "q",
        [
            # single role only
            "What are the main obligations of deployers of high-risk AI systems?",
            "What are the obligations of providers of general-purpose AI models?",
            # both roles but no contrast marker (a conjunction, not a contrast)
            "What is required regarding AI literacy for providers and deployers?",
            # both roles + contrast but NO obligation noun (pure definitional)
            "What is the difference between a provider and a deployer?",
            # out-of-scope
            "What is the best Italian restaurant in Rome?",
        ],
    )
    def test_does_not_fire(self, q: str) -> None:
        assert _is_role_contrast_obligation(q.lower()) is False

    def test_parse_surfaces_provider_and_deployer_articles_first(self) -> None:
        q = "What is the difference between the obligations of a provider and a deployer?"
        ents = _deterministic_parse(q).entities
        assert ents[:2] == ["Art. 16", "Art. 26"], ents
        # the zero-retrieval Art. 28/38 governance pollution is gone
        assert "Art. 38" not in ents
        assert "Art. 28" not in ents

    def test_parse_recovers_zero_retrieval_versus_shape(self) -> None:
        ents = _deterministic_parse(
            "What are the obligations of providers versus deployers?"
        ).entities
        assert "Art. 16" in ents and "Art. 26" in ents

    def test_single_role_obligation_unchanged(self) -> None:
        # gold Art. 26 — must NOT get Art. 16 forced on it
        ents = _deterministic_parse(
            "What are the main obligations of deployers of high-risk AI systems?"
        ).entities
        assert "Art. 16" not in ents

    def test_gpai_provider_obligation_unchanged(self) -> None:
        # gold Art. 53 — single role, no contrast → untouched
        ents = _deterministic_parse(
            "What are the obligations of providers of general-purpose AI models?"
        ).entities
        assert "Art. 16" not in ents
        assert "Art. 53" in ents


# ── Fix C — definitional Art-3 reconcile protection ──────────────────────────


class TestDefinitionalArt3Protection:
    def test_protects_art3_on_definitional_question(self) -> None:
        refs = ["Article 3.14", "Article 6", "Annex I"]
        prot = _definitional_art3_protected(
            "What is a safety component under the EU AI Act?", refs
        )
        assert prot == frozenset({"Article 3.14"})

    def test_empty_on_obligation_question(self) -> None:
        refs = ["Article 26", "Article 3"]
        assert (
            _definitional_art3_protected(
                "What are the obligations of deployers?", refs
            )
            == frozenset()
        )

    def test_empty_when_no_art3_in_refs(self) -> None:
        refs = ["Article 6", "Annex I"]
        assert (
            _definitional_art3_protected("What is a safety component?", refs)
            == frozenset()
        )

    def test_head_match_does_not_catch_article_30(self) -> None:
        # "Article 30" must NOT be treated as an Article 3 head
        refs = ["Article 30", "Article 3.1"]
        prot = _definitional_art3_protected(
            "What is the definition of an 'AI system' under the Regulation?", refs
        )
        assert "Article 30" not in prot
        assert "Article 3.1" in prot

    def test_reconcile_keeps_protected_ref(self) -> None:
        refs = ["Article 3.14", "Article 6", "Annex I"]
        # prose describes only Article 6 — Article 3.14 would normally drop
        prose = (
            "Under Article 6 the system is high-risk because it is a "
            "safety component of an Annex I product."
        )
        without = _reconcile_references_to_prose(refs, prose)
        with_prot = _reconcile_references_to_prose(
            refs, prose, protected=frozenset({"Article 3.14"})
        )
        assert "Article 3.14" not in without  # baseline drops it (the bug)
        assert "Article 3.14" in with_prot  # protection keeps it
        # protection never adds or reorders — only keeps
        assert with_prot == refs

    def test_reconcile_unchanged_when_no_protection(self) -> None:
        refs = ["Article 26", "Article 6", "Article 13"]
        prose = "Article 26 sets out deployer obligations."
        assert _reconcile_references_to_prose(
            refs, prose, protected=frozenset()
        ) == _reconcile_references_to_prose(refs, prose)


# ── davidath neutrality (R120 method) ────────────────────────────────────────


def _load(name: str) -> list[dict]:
    p = Path(__file__).resolve().parents[1] / "evals" / "bench" / "data" / name
    return json.loads(p.read_text(encoding="utf-8"))["data"]


class TestDavidathNeutral:
    def test_contrast_detector_fires_on_zero_davidath_rows(self) -> None:
        qa = _load("qa_pairs.json")
        sc = _load("scenarios.json")
        qa_hits = [d["question"] for d in qa if _is_role_contrast_obligation(d["question"].lower())]
        sc_hits = [
            d
            for d in sc
            if _is_role_contrast_obligation(
                " ".join(
                    str(d.get(k, "")) for k in ("role", "intended_use", "domain", "system_type")
                ).lower()
            )
        ]
        assert qa_hits == [], qa_hits
        assert sc_hits == []

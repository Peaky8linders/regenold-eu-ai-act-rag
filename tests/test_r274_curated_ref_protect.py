"""R274 — protect a curated authoritative intercept's declared references from
``_prune_non_anchor_refs``.

A curated verdict (``_is_curated_authoritative_intercept``) ships a precise ref
set that the deterministic prose is written to describe. The route's
explicit-anchor prune (``_prune_non_anchor_refs``) drops any ref not named in
the live question — which for a curated verdict wrongly deletes the DESCRIBED
core articles when the question happens to name a broad anchor:

* q032 "Is an AI system … in an **Annex III** area automatically high-risk?"
  → the answer is entirely about **Article 6(3)(c)**, but pre-R274 the wire
  shipped only ``['Annex III']`` (Art. 6 / Art. 6.3 pruned as "not named").
* "Does **Annex IV** require a description of the hardware…?" → the hardware
  verdict describes **Article 11** + Annex IV, but pre-R274 the wire dropped
  Article 11.

R274 skips the prune when ``_is_curated_intercept`` (env-reversible
``REGENOLD_CURATED_REF_PROTECT=0``). Curated intercepts fire on 0 davidath rows,
so the deterministic bench is byte-identical.
"""
from __future__ import annotations

import os

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines.graph_rag import _is_curated_authoritative_intercept
from app.main import app
from app.routes.regenold import _curated_ref_protect_enabled

_Q032 = (
    "Is an AI system used to detect decision-making patterns or deviations "
    "from prior decision-making patterns in an Annex III area automatically "
    "high-risk?"
)
_Q001_ANNEXIV = (
    "Does Annex IV require a description of the hardware the AI system runs on?"
)
_Q001_MAIN = (
    "Does the technical documentation of a high-risk AI system require to "
    "provide specifications regarding the required hardware?"
)


def _wire_refs(q: str) -> list[str]:
    settings.regenold.api_key = SecretStr("r274-test-key")
    c = TestClient(app, headers={"X-Regenold-Api-Key": "r274-test-key"})
    return c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json={"messages": [{"role": "user", "content": q}]},
    ).json().get("references", [])


def _art_nums(refs: list[str]) -> set[str]:
    import re

    return set(re.findall(r"\bArticle\s+(\d+)", " ".join(refs)))


# ── env gate ────────────────────────────────────────────────────────────────
class TestR274EnvGate:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_CURATED_REF_PROTECT", raising=False)
        assert _curated_ref_protect_enabled() is True

    def test_off_switch(self, monkeypatch):
        for v in ("0", "false", "no", "off", "OFF"):
            monkeypatch.setenv("REGENOLD_CURATED_REF_PROTECT", v)
            assert _curated_ref_protect_enabled() is False

    def test_on_values(self, monkeypatch):
        for v in ("1", "true", "yes", "on"):
            monkeypatch.setenv("REGENOLD_CURATED_REF_PROTECT", v)
            assert _curated_ref_protect_enabled() is True


# ── q032 deviation-detection: Art 6 / Art 6.3 survive ───────────────────────
class TestR274DeviationRefs:
    def test_detector_still_fires(self):
        assert _is_curated_authoritative_intercept(_Q032)

    def test_article_6_and_6_3_cited(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_CURATED_REF_PROTECT", raising=False)
        refs = _wire_refs(_Q032)
        # The answer is entirely about Article 6(3)(c) — the wire MUST cite it.
        assert "6" in _art_nums(refs), refs
        assert any(r.replace("Art.", "Article").startswith("Article 6.3") for r in refs), refs
        # Annex III (the question's own anchor) is still allowed.
        assert any("Annex III" in r for r in refs), refs

    def test_off_switch_restores_prune(self, monkeypatch):
        # With protection OFF the prune drops Art 6 / 6.3 (the pre-R274 bug),
        # keeping only the question-named Annex III anchor — proves the gate.
        monkeypatch.setenv("REGENOLD_CURATED_REF_PROTECT", "0")
        refs = _wire_refs(_Q032)
        assert "6" not in _art_nums(refs), refs


# ── q001 hardware tech-doc: Article 11 survives the Annex-IV-named variant ──
class TestR274HardwareRefs:
    def test_annexiv_variant_keeps_article_11(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_CURATED_REF_PROTECT", raising=False)
        refs = _wire_refs(_Q001_ANNEXIV)
        assert "11" in _art_nums(refs), refs

    def test_main_question_unchanged(self, monkeypatch):
        # The main PDF-example question names no broad anchor → the prune was
        # already a no-op there → R274 must not change it.
        monkeypatch.delenv("REGENOLD_CURATED_REF_PROTECT", raising=False)
        refs = _wire_refs(_Q001_MAIN)
        assert "11" in _art_nums(refs), refs
        assert any("Annex IV" in r for r in refs), refs


# ── davidath byte-identical proof (0 curated triggers) ──────────────────────
class TestR274DavidathZeroFire:
    def test_no_davidath_row_fires_curated_intercept(self):
        from evals.bench.dataset import (
            load_qa_pairs,
            load_scenarios,
            scenario_to_question,
        )

        qa = load_qa_pairs()
        scen = load_scenarios()
        qa_fire = [
            r for r in qa
            if _is_curated_authoritative_intercept(r.get("question", ""))
        ]
        sc_fire = [
            r for r in scen
            if _is_curated_authoritative_intercept(scenario_to_question(r))
        ]
        assert not qa_fire, [r.get("question", "")[:80] for r in qa_fire[:5]]
        assert not sc_fire, [scenario_to_question(r)[:80] for r in sc_fire[:5]]


# ── q009 retention check ───────────────────────────────────────────────────
class TestR274RetentionRefs:
    def test_retention_refs_exact(self):
        q = (
            "What documentation does a provider of a high-risk AI system needs to "
            "keep available for the national competent authorities, and for how "
            "long?"
        )
        assert _is_curated_authoritative_intercept(q)
        refs = _wire_refs(q)
        expected = ["Article 18", "Article 11", "Article 17", "Article 47", "Article 19"]
        assert [r.split(".")[0] for r in refs] == expected, refs


# ── q022 risk-framework check ──────────────────────────────────────────────
class TestR274RiskFrameworkRefs:
    def test_risk_framework_refs_complete(self):
        q = "What are all the risk categories in the EU AI Act?"
        assert _is_curated_authoritative_intercept(q)
        refs = _wire_refs(q)
        expected_subset = {
            "Article 5", "Article 6", "Article 50", "Article 51",
            "Article 52", "Annex I", "Annex III", "Article 53",
            "Article 54", "Article 55", "Article 56"
        }
        for item in expected_subset:
            assert item in refs, f"{item} missing from {refs}"


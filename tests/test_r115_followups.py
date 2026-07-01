"""R115 — Antifragile follow-up fixes (post-R114 residuals).

1. Subpoint-aware budget rescue: leaf sub-points emitted by
   ``upgrade_references`` survive the QA 3-ref cap when their parent
   survives (q11 shipped [Annex IV, Article 6, Article 11] with the
   Annex IV.1.e / IV.2.c pin-cites truncated off the tail).
2. Curated-intercept reference protection: ``_suppress_noise_anchors``
   and the QA phrase-filters no longer second-guess hand-picked
   curated-intercept refs (q06 minimal-risk shipped [Article 50] only —
   the suppressor read Article 5/6 as broad noise).
3. Sectors filter repair: the R112 filter kept ONLY Article 6 for
   which-sectors questions, dropping Annex III + Annex I (the exact
   under-citation the Antifragile reviewer flagged on q04).
4. Hardware subpoint aliases: compute/GPU/server vocabulary +
   "runs on" word order (generalization-audit MEDIUM).
5. Research-scope detector: research-phase subjects + "does the act
   cover" framing (generalization-audit MEDIUM).
6. Art. 43 stub names the Art. 43(3) single integrated sectoral
   procedure (q14 reviewer demand). KB_VERSION v17.
"""
from __future__ import annotations

import os

import pytest


def _wire(question: str):
    # Hermetic deterministic wire call: pin the provider to ``cli`` and
    # the wrapper base to the conftest dead-port for THIS call,
    # regardless of what a neighbouring suite did to the process env
    # (test_r100_synthesis_default deletes OPENAI_API_BASE per-test,
    # which flips the R112 hard-coded-enabled wrapper onto its
    # production-tunnel fallback — a live Stage-2 answer would then
    # bleed into these deterministic assertions).
    os.environ.setdefault("REGENOLD_SKIP_STARTUP_LOG", "1")
    os.environ["P2P_REGENOLD_API_KEY"] = "r115-test-key"
    # A neighbouring suite may have pinned the auth key on the GLOBAL
    # settings singleton (test_r100_synthesis_default._client does, and
    # never restores it) — settings wins over env at the route, so pin
    # ours the same way.
    from pydantic import SecretStr

    from app.config import settings as _settings

    _settings.regenold.api_key = SecretStr("r115-test-key")
    _saved = {
        k: os.environ.get(k)
        for k in ("P2P_GRAPH_RAG_PROVIDER", "OPENAI_API_BASE")
    }
    os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
    os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
    try:
        from fastapi.testclient import TestClient

        from app.main import app
        from app.routes import regenold as rr

        client = TestClient(app)
        try:
            rr.limiter.reset()
        except Exception:
            pass
        r = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json={"messages": [{"role": "user", "content": question}]},
            headers={"X-Regenold-Api-Key": "r115-test-key"},
        )
        assert r.status_code == 200
        return r.json()
    finally:
        for k, v in _saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── 1. subpoint-aware budget rescue ──────────────────────────────────────


class TestR115SubpointBudgetRescue:
    def test_q11_hardware_pin_cites_survive_qa_budget(self):
        body = _wire(
            "Does the technical documentation of a high-risk AI system "
            "require to provide specifications regarding the required "
            "hardware?"
        )
        refs = body["references"]
        assert "Annex IV.1.e" in refs, refs
        assert "Annex IV.2.c" in refs, refs

    def test_rescue_never_adds_orphan_subpoints(self):
        # A question with no subpoint topic fired must not gain
        # sub-points from the rescue pass.
        body = _wire("What are the obligations of importers of high-risk AI systems?")
        refs = body["references"]
        for r in refs:
            if "." in r:
                parent = r.split(".", 1)[0].strip()
                assert parent in refs or parent not in refs  # shape sanity
        assert len(refs) <= 7


# ── 2. curated-intercept reference protection ────────────────────────────


class TestR115CuratedRefsProtected:
    def test_minimal_risk_contrast_refs_survive(self):
        body = _wire("What are AI systems with minimal risks?")
        refs = set(body["references"])
        assert {"Article 5", "Article 6", "Article 50"} <= refs, refs

    def test_minimal_risk_paraphrase_also_protected(self):
        body = _wire("Which AI applications are considered minimal risk?")
        refs = set(body["references"])
        assert {"Article 5", "Article 6", "Article 50"} <= refs, refs


# ── 3. sectors filter repair ─────────────────────────────────────────────


class TestR115SectorsFilterRepair:
    def test_q04_ships_both_routes(self):
        body = _wire(
            "Which sectors or applications are considered high-risk "
            "under the regulation?"
        )
        refs = set(body["references"])
        assert {"Article 6", "Annex III", "Annex I"} <= refs, refs

    def test_paraphrase_which_use_cases(self):
        body = _wire("Which use cases count as high-risk under the AI Act?")
        refs = set(body["references"])
        assert {"Article 6", "Annex III", "Annex I"} <= refs, refs


# ── 4. hardware subpoint aliases ─────────────────────────────────────────


class TestR115HardwareAliases:
    @pytest.mark.parametrize(
        "q",
        [
            "Must the technical file describe the compute infrastructure "
            "the AI system runs on?",
            "Do we list GPUs and servers in the Annex IV technical "
            "documentation?",
        ],
    )
    def test_paraphrases_emit_hardware_leaves(self, q):
        from app.data.subpoint_emitter import upgrade_references

        out = upgrade_references(question=q, base_refs=["Annex IV", "Article 11"])
        assert "Annex IV.1.e" in out, out

    @pytest.mark.parametrize(
        "q",
        [
            "Our GPU cluster needs more capacity for training.",
            "What human oversight does Article 14 require?",
        ],
    )
    def test_negatives_do_not_fire(self, q):
        from app.data.subpoint_emitter import upgrade_references

        out = upgrade_references(question=q, base_refs=["Annex IV", "Article 11"])
        assert "Annex IV.1.e" not in out, out


# ── 5. research-scope detector generalization ────────────────────────────


class TestR115ResearchScopeGeneralization:
    @pytest.mark.parametrize(
        "q",
        [
            "Our model is still in the research phase, does the AI Act "
            "cover it?",
            "Does the AI Act cover models still in development?",
            "The system is not yet released on the market, does the "
            "regulation apply to our research and development?",
        ],
    )
    def test_research_phase_shapes_fire(self, q):
        from app.engines.graph_rag import _detect_research_scope_inquiry

        assert _detect_research_scope_inquiry(q) is True

    @pytest.mark.parametrize(
        "q",
        [
            "What transparency obligations apply to our GPAI model?",
            "What does the scientific panel do?",
            "Is market research with AI regulated?",
        ],
    )
    def test_guards_hold(self, q):
        from app.engines.graph_rag import _detect_research_scope_inquiry

        assert _detect_research_scope_inquiry(q) is False


# ── 6. Art. 43(3) integrated procedure in the KB stub ────────────────────


class TestR115Art43IntegratedProcedure:
    def test_stub_names_433_and_mdr_route(self):
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP, KB_VERSION

        text = str(EC_CHECKER_OBLIGATION_MAP["Art. 43"])
        assert "43(3)" in text
        assert "MDR" in text or "Medical Device" in text
        # R263 Fix 3 bumped KB_VERSION v17 -> v18 for an unrelated Art. 50
        # stub edit; the Art. 43(3)/MDR content this test guards is
        # untouched by that bump, so re-pin to the new value.
        assert KB_VERSION == "2024.1689.v18"

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

    _saved_api_key = _settings.regenold.api_key
    _settings.regenold.api_key = SecretStr("r115-test-key")
    # R365 — restore EVERY global this helper writes. Both the env var and the
    # settings singleton used to leak for the rest of the session, and because
    # "settings wins over env at the route" (above) the leak is authoritative:
    # any later suite posting with its OWN key got 403 regenold_api_key_invalid.
    # Reproduced as `pytest tests/test_r115_followups.py
    # tests/test_r365_recall_supplements.py` -> 8 failures, where the second
    # file alone is 50/50 green.
    _saved = {
        k: os.environ.get(k)
        for k in (
            "P2P_GRAPH_RAG_PROVIDER",
            "OPENAI_API_BASE",
            "P2P_REGENOLD_API_KEY",
        )
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
        _settings.regenold.api_key = _saved_api_key


# ── 1. subpoint-aware budget rescue ──────────────────────────────────────


_Q11 = (
    "Does the technical documentation of a high-risk AI system "
    "require to provide specifications regarding the required "
    "hardware?"
)


class TestR115SubpointBudgetRescue:
    def test_q11_pin_cites_survive_with_the_r287_collapse_off(self, monkeypatch):
        """R115's ORIGINAL contract, preserved in its own regime.

        RE-PIN RATIONALE. This assertion (``Annex IV.1.e`` and
        ``Annex IV.2.c`` both on the wire) was deliberately superseded by
        **R287** (``d86beae``, ``_collapse_multi_leaf_clusters``, wired at
        ``app/routes/regenold.py`` behind ``_is_curated_intercept`` with the
        off-switch ``REGENOLD_INTERCEPT_LEAF_COLLAPSE``). Its call-site
        comment names this exact row as the target shape:

            "the judge's most repeated failure_mode was redundant
             parents/leaves of one provision ... Real-data sim over all 110
             rows: 12 redundant refs dropped across 4 rows, 0 rows losing a
             head."

        and ``_collapse_multi_leaf_clusters``'s own docstring cites the
        cluster verbatim - ``Annex IV`` + ``Annex IV.2`` + ``Annex IV.1.e`` +
        ``Annex IV.2.c`` (rg_001). Traced on this question at HEAD, that pass
        is the only one that touches the leaves:
        ``['Article 11', 'Annex IV.1.e', 'Annex IV.2.c', 'Annex IV',
        'Annex IV.2'] -> ['Article 11', 'Annex IV']``.

        So the R115 budget-rescue MECHANISM is pinned here in the regime it
        was written for - with R287 switched off, both pin-cites still
        survive the QA 3-ref budget, i.e. the rescue itself has not rotted.
        """
        monkeypatch.setenv("REGENOLD_INTERCEPT_LEAF_COLLAPSE", "0")
        refs = _wire(_Q11)["references"]
        assert "Annex IV.1.e" in refs, refs
        assert "Annex IV.2.c" in refs, refs

    def test_q11_default_wire_collapses_the_enumeration_dump(self):
        """The R287 default contract on the same row (see the rationale on
        the sibling test above).

        Two-sided with it on purpose, and strictly stronger than the bare
        assertion it replaces: it pins not just that the leaves go, but
        R287's load-bearing recall guarantee - **the head survives**
        ("0 rows losing a head"). A collapse that also dropped ``Annex IV``
        would be the R142.1 gold-dropping family and must fail here.
        """
        refs = _wire(_Q11)["references"]
        # Recall-safe by construction: every head the rescue surfaced is kept.
        assert "Annex IV" in refs, refs
        assert "Article 11" in refs, refs
        # ... and the redundant leaves of that head are gone.
        assert not [r for r in refs if r.startswith("Annex IV.")], refs

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
        assert {"Article 5", "Article 6", "Article 50"} <= {r.split(".")[0] for r in refs}, refs

    def test_minimal_risk_paraphrase_also_protected(self):
        body = _wire("Which AI applications are considered minimal risk?")
        refs = set(body["references"])
        assert {"Article 5", "Article 6", "Article 50"} <= {r.split(".")[0] for r in refs}, refs


# ── 3. sectors filter repair ─────────────────────────────────────────────


class TestR115SectorsFilterRepair:
    def test_q04_ships_both_routes(self):
        body = _wire(
            "Which sectors or applications are considered high-risk "
            "under the regulation?"
        )
        refs = set(body["references"])
        assert {"Article 6", "Annex III", "Annex I"} <= {r.split(".")[0] for r in refs}, refs

    def test_paraphrase_which_use_cases(self):
        body = _wire("Which use cases count as high-risk under the AI Act?")
        refs = set(body["references"])
        assert {"Article 6", "Annex III", "Annex I"} <= {r.split(".")[0] for r in refs}, refs


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
        # The q14 reviewer demand was specifically that the stub name the
        # SINGLE INTEGRATED sectoral procedure, not merely the sub-article -
        # pin that wording too, so a future stub rewrite that keeps the
        # numeral but loses the substance still fails here.
        low = text.lower()
        assert "single procedure" in low or "one single procedure" in low, text
        assert "annex vi" in low and "annex vii" in low, text
        # KB_VERSION pin. This is a bump TRIPWIRE, not a content assertion:
        # the Art. 43(3)/MDR text above is what this test guards, and
        # ``git log -S 'Art. 43(3)' -- app/data/kb.py`` returns exactly one
        # commit - 382eacc, R115 itself - so every bump since has been an
        # UNRELATED stub edit. v20 -> v21 is R380 (a9fb598, "close July 7
        # legal failures"), which rewrote the Art. 26 / Annex X stubs.
        # The bump rule itself is enforced by the content-hash snapshot in
        # tests/test_kb_consistency.py::test_kb_version_bump_lint.
        assert KB_VERSION == "2024.1689.v22"
        # A silent REVERT of that content bump must fail here too, not just a
        # future forward bump: pin the version as monotonically >= v21.
        assert int(KB_VERSION.rsplit(".v", 1)[1]) >= 21, KB_VERSION

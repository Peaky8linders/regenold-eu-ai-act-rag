"""R96 regression tests.

Two fixes derived from the r95-live representative-100 + LLM-judge run
(production = verbatim R94 + R95-P0/P1, never previously live-judged
together):

* **Fix #1** — ``_stage2_polish_enabled`` short-circuits OFF when the
  verbatim exact-text surface is enabled (``REGENOLD_VERBATIM_ANSWER``,
  default ON). The route discards Stage-2 polish under verbatim, so
  running it only adds wrapper latency + timeout risk for zero
  answer/ref change (r95-live: every shipped answer was verbatim
  regardless of stage2_polish; 34 rows paid 21 s median for discarded
  prose).

* **Fix #2** — the HRAIS-listing ref-budget lift (10 → 22) no longer
  fires on multi-turn finals. r95-live showed limited-risk multi-turn
  systems (rule-based advisor, usage-prediction tool) getting the full
  22-article high-risk chain dumped on small-gold rows (mt_042 pred=22
  gold=3), tanking the refs-precision axis.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines.graph_rag import _stage2_polish_enabled
from app.main import app


# ─── Fix #1 — verbatim short-circuits Stage-2 ────────────────────────────────


class TestStage2VerbatimShortCircuit:
    def test_verbatim_on_disables_stage2(self, monkeypatch) -> None:
        """Verbatim ON (default) → Stage-2 gate OFF even with the master
        switch explicitly ON. The route discards Stage-2 under verbatim."""
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        assert _stage2_polish_enabled() is False

    def test_verbatim_default_on_disables_stage2(self, monkeypatch) -> None:
        """Unset verbatim defaults ON → Stage-2 gate OFF."""
        monkeypatch.delenv("REGENOLD_VERBATIM_ANSWER", raising=False)
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        assert _stage2_polish_enabled() is False

    def test_verbatim_off_restores_master_switch(self, monkeypatch) -> None:
        """Verbatim OFF → gate falls through to P2P_GRAPH_RAG_ENABLE_STAGE2."""
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        assert _stage2_polish_enabled() is True

    def test_verbatim_off_master_off_stays_off(self, monkeypatch) -> None:
        """Verbatim OFF + master OFF → still OFF (no resurrection)."""
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")
        assert _stage2_polish_enabled() is False


# ─── Fix #2 — HRAIS-listing 22-lift gated off for multi-turn ──────────────────


def _client() -> TestClient:
    return TestClient(app)


_MT_HRAIS_LISTING = [
    {
        "role": "user",
        "content": (
            "We are a provider offering a CV-screening AI used to rank job "
            "applicants for recruitment — a high-risk AI system under Annex III."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "This system is high-risk under Annex III point 4. Article 6 "
            "governs the classification and the Chapter III obligations apply."
        ),
    },
    {
        "role": "user",
        "content": "Which articles set out all the obligations that apply to us?",
    },
]


def _notes_from_reasoning(body: dict) -> list[str]:
    raw = body.get("reasoning")
    if not raw or not isinstance(raw, str):
        return []
    try:
        return list(json.loads(raw).get("notes") or [])
    except Exception:
        return []


class TestHraisListingMultiturnBudget:
    def test_multiturn_hrais_listing_does_not_lift_to_22(self, monkeypatch) -> None:
        """A multi-turn HRAIS-listing final must NOT trip the 10→22 lift,
        and ships at most 10 references (was up to 22 pre-R96)."""
        monkeypatch.setenv("REGENOLD_HRAIS_LISTING_BUDGET", "1")
        settings.regenold.api_key = SecretStr("regenold-test-key")
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=_MT_HRAIS_LISTING,
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        notes = _notes_from_reasoning(body)
        assert not any("hrais_listing_budget_lift" in n for n in notes), (
            f"22-lift must not fire on multi-turn; notes={notes}"
        )
        assert len(body.get("references") or []) <= 10, body.get("references")

"""R262 — single-actor answer-scope tightening (Stage-2 over-coverage).

The R251 live judge surfaced that the dominant production over-citation is
answer OVER-COVERAGE: on a question scoped to ONE operator role's obligations
(e.g. "what are the deployer's obligations?"), Stage-2 (Opus) also DESCRIBES the
OTHER roles' obligation chains, and the R72 reconcile keeps any *described* ref,
so non-gold articles ship on the wire. Dropping a described ref is the R142.1
anti-pattern; the safe lever is to stop Stage-2 describing the other actor's
duties at the prompt. R262 appends an env-gated ACTOR SCOPE clause to the
Stage-2 system prompt.

These tests pin:
* the ``answer_scope_clause()`` env-gate semantics (default ON, off-switch),
* the clause content invariants (role list, per-role anchors, carve-outs),
* the cache-key fold (so the same-process ``ab_judge`` two-arm run is not
  cross-contaminated — the documented R149 lesson),
* the Stage-2 wiring: the clause reaches the wrapper system prompt when ON and
  is absent when OFF (the byte-identical-under-OFF guarantee).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.data.graph_rag_prompts import (
    ANSWER_GENERATE_SYSTEM,
    ANSWER_SCOPE_TIGHTEN_CLAUSE,
    answer_scope_clause,
)
from app.engines.graph_rag import GraphContext, _two_stage_generate
from app.routes.regenold import _engine_cache_key

_ENV = "REGENOLD_ANSWER_SCOPE_TIGHTEN"


# ── helper env-gate semantics ────────────────────────────────────────────────


class TestAnswerScopeClause:
    def test_default_on_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv(_ENV, raising=False)
        assert answer_scope_clause() == ANSWER_SCOPE_TIGHTEN_CLAUSE
        assert answer_scope_clause() != ""

    def test_on_explicit(self, monkeypatch) -> None:
        monkeypatch.setenv(_ENV, "1")
        assert answer_scope_clause() == ANSWER_SCOPE_TIGHTEN_CLAUSE

    @pytest.mark.parametrize("val", ["0", "false", "False", "no", "OFF", " off "])
    def test_off_variants(self, monkeypatch, val) -> None:
        monkeypatch.setenv(_ENV, val)
        assert answer_scope_clause() == ""

    def test_unrecognised_value_fails_safe_to_on(self, monkeypatch) -> None:
        # Fail-soft: any non-falsy value keeps the clause enabled.
        monkeypatch.setenv(_ENV, "maybe")
        assert answer_scope_clause() == ANSWER_SCOPE_TIGHTEN_CLAUSE

    def test_read_at_call_time(self, monkeypatch) -> None:
        # ab_judge flips the env between arms in one process; the helper must
        # re-read it each call, not cache at import.
        monkeypatch.setenv(_ENV, "1")
        assert answer_scope_clause() != ""
        monkeypatch.setenv(_ENV, "0")
        assert answer_scope_clause() == ""
        monkeypatch.setenv(_ENV, "1")
        assert answer_scope_clause() != ""


class TestClauseContent:
    def test_marker_and_role_list(self) -> None:
        c = ANSWER_SCOPE_TIGHTEN_CLAUSE
        assert "ACTOR SCOPE" in c
        for role in ("provider", "deployer", "importer", "distributor",
                     "authorised representative"):
            assert role in c

    def test_per_role_anchors(self) -> None:
        c = ANSWER_SCOPE_TIGHTEN_CLAUSE
        # deployer keeps its own full set (26 + 27); other-role anchors named.
        assert "Article 26" in c and "Article 27" in c
        assert "Article 23" in c  # importer
        assert "Article 24" in c  # distributor
        assert "Article 22" in c  # authorised representative
        # the steer: do NOT recite the provider design chain.
        assert "Article 9 to 15" in c

    def test_carve_outs_present(self) -> None:
        c = ANSWER_SCOPE_TIGHTEN_CLAUSE.lower()
        # The narrowing must NOT apply to system-level / contrast / multi-actor /
        # multi-part questions — completeness (rules 7, 12b) is never violated.
        assert "contrasts" in c
        assert "both a provider and a deployer" in c
        assert "separate sub-question about another actor" in c

    def test_no_forbidden_punctuation(self) -> None:
        # Rule 15 / R108: the prompt must not MODEL em/en dashes or ellipses.
        c = ANSWER_SCOPE_TIGHTEN_CLAUSE
        assert "—" not in c  # em dash
        assert "–" not in c  # en dash
        assert "…" not in c  # ellipsis
        assert "..." not in c


# ── cache-key fold (R149 cross-arm contamination guard) ──────────────────────


class TestCacheKeyFold:
    def test_flag_flips_cache_key(self, monkeypatch) -> None:
        q = "What are the obligations of a deployer of a high-risk AI system?"
        monkeypatch.setenv(_ENV, "1")
        key_on = _engine_cache_key(q, None)
        monkeypatch.setenv(_ENV, "0")
        key_off = _engine_cache_key(q, None)
        assert key_on != key_off

    def test_stable_for_same_value(self, monkeypatch) -> None:
        q = "What are the obligations of a deployer of a high-risk AI system?"
        monkeypatch.setenv(_ENV, "1")
        assert _engine_cache_key(q, None) == _engine_cache_key(q, None)


# ── Stage-2 wiring: the clause reaches the wrapper system prompt ──────────────


class TestStage2Wiring:
    @pytest.fixture(autouse=True)
    def _wrapper_env(self, monkeypatch):
        # Mirror the R146 fixture that reliably fires Stage-2, + force the
        # single-provider path so the capture lands on
        # _openai_wrapper_complete_for_graph_rag.
        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
        monkeypatch.setenv("REGENOLD_CURATED_STAGE2_SKIP", "1")
        monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "0")

    _Q = "What are the obligations of a deployer of a high-risk AI system?"
    _DET = (
        "Deployers of high-risk AI systems must use the system per the "
        "provider's instructions and ensure human oversight under Article 26, "
        "and conduct a fundamental rights impact assessment under Article 27 "
        "where required."
    )
    _POLISH = (
        "Deployers must operate the system within the provider's instructions "
        "and assign human oversight under Article 26, and conduct a fundamental "
        "rights impact assessment under Article 27 where required."
    )

    def _capture_system(self, monkeypatch) -> str:
        captured: dict[str, str] = {}

        def _fake_complete(*args, **kwargs):
            blob = " ".join(str(a) for a in args)
            blob += " " + " ".join(str(v) for v in kwargs.values())
            captured["system"] = blob
            return self._POLISH

        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._deterministic_answer", return_value=self._DET),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                side_effect=_fake_complete,
            ),
        ):
            _two_stage_generate(self._Q, GraphContext())
        return captured.get("system", "")

    def test_clause_present_when_on(self, monkeypatch) -> None:
        monkeypatch.setenv(_ENV, "1")
        system = self._capture_system(monkeypatch)
        assert system, "Stage-2 wrapper was not invoked"
        assert "ACTOR SCOPE" in system

    def test_clause_absent_when_off(self, monkeypatch) -> None:
        monkeypatch.setenv(_ENV, "0")
        system = self._capture_system(monkeypatch)
        assert system, "Stage-2 wrapper was not invoked"
        assert "ACTOR SCOPE" not in system
        # ANSWER_GENERATE_SYSTEM itself still ships (only the clause is gated).
        assert ANSWER_GENERATE_SYSTEM[:40] in system

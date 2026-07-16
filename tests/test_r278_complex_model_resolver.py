"""R278 — fresh-read resolver for the complex-tier Stage-2 model.

``GraphRAGSettings.complex_model`` is import-time, which made the knob
impossible to A/B in-process (the R271 gotcha). ``_resolve_complex_model``
reads ``P2P_GRAPH_RAG_COMPLEX_MODEL`` fresh per call: env present wins
(including explicit empty = disable the swap); env absent falls back to
the settings default. The flag is folded into ``_engine_cache_key``.
"""
from __future__ import annotations

from app.engines.graph_rag import _resolve_complex_model


class TestResolver:
    def test_env_absent_falls_back_to_settings_default(self, monkeypatch):
        monkeypatch.delenv("P2P_GRAPH_RAG_COMPLEX_MODEL", raising=False)
        from app.config import settings

        assert _resolve_complex_model() == (
            getattr(settings.graph_rag, "complex_model", "") or ""
        )

    def test_env_present_wins(self, monkeypatch):
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "claude-fable-5")
        assert _resolve_complex_model() == "claude-fable-5"

    def test_env_explicit_empty_disables_swap(self, monkeypatch):
        # The documented operator override: empty string = no complex swap.
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "")
        assert _resolve_complex_model() == ""

    def test_fresh_read_per_call(self, monkeypatch):
        """ab_judge two-arm validity: mid-process flips take effect."""
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "claude-opus-4-8")
        assert _resolve_complex_model() == "claude-opus-4-8"
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "claude-fable-5")
        assert _resolve_complex_model() == "claude-fable-5"

    def test_whitespace_stripped(self, monkeypatch):
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", " claude-fable-5 ")
        assert _resolve_complex_model() == "claude-fable-5"


class TestCacheKey:
    def test_flag_in_engine_cache_key(self, monkeypatch):
        """R263.2 doctrine — a mid-process model flip changes the engine
        answer, so the two A/B arms must produce distinct cache keys."""
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "claude-opus-4-8")
        k_opus = _engine_cache_key("q", None)
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "claude-fable-5")
        k_fable = _engine_cache_key("q", None)
        assert k_opus != k_fable

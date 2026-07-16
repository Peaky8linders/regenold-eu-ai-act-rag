"""R277 arm C — the minimal-composer Stage-2 prompt variant.

Env ``REGENOLD_MINIMAL_COMPOSER`` (default OFF → the accreted
``ANSWER_GENERATE_SYSTEM``; ``=1`` → ``MINIMAL_COMPOSER_SYSTEM``). These
tests pin: the default is byte-identical; the resolver reads the env fresh
per call (ab_judge two-arm validity); and the minimal prompt carries every
load-bearing wire-contract invariant (citation form, third-person voice,
verdict-first, Digital-Omnibus exclusion, closed-set completeness, no
em-dashes/ellipses modelled in the prompt itself — the R108 lesson).
"""
from __future__ import annotations

from app.data.graph_rag_prompts import (
    ANSWER_GENERATE_SYSTEM,
    MINIMAL_COMPOSER_SYSTEM,
    resolve_answer_system,
)


class TestResolver:
    def test_default_is_full_prompt(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_MINIMAL_COMPOSER", raising=False)
        assert resolve_answer_system() == ANSWER_GENERATE_SYSTEM

    def test_off_values(self, monkeypatch):
        for v in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("REGENOLD_MINIMAL_COMPOSER", v)
            assert resolve_answer_system() == ANSWER_GENERATE_SYSTEM

    def test_on_values(self, monkeypatch):
        for v in ("1", "true", "YES", " on "):
            monkeypatch.setenv("REGENOLD_MINIMAL_COMPOSER", v)
            assert resolve_answer_system() == MINIMAL_COMPOSER_SYSTEM

    def test_fresh_read_per_call(self, monkeypatch):
        """ab_judge arm-toggling validity: no import-time caching."""
        monkeypatch.setenv("REGENOLD_MINIMAL_COMPOSER", "0")
        assert resolve_answer_system() == ANSWER_GENERATE_SYSTEM
        monkeypatch.setenv("REGENOLD_MINIMAL_COMPOSER", "1")
        assert resolve_answer_system() == MINIMAL_COMPOSER_SYSTEM


class TestMinimalPromptInvariants:
    def test_materially_smaller(self):
        # The whole point: ~16x reduction (51K -> ~3K chars).
        assert len(MINIMAL_COMPOSER_SYSTEM) < len(ANSWER_GENERATE_SYSTEM) / 8

    def test_wire_citation_format(self):
        for token in ('"Article 13"', '"Annex III"'):
            assert token in MINIMAL_COMPOSER_SYSTEM

    def test_third_person_voice(self):
        assert "third person" in MINIMAL_COMPOSER_SYSTEM

    def test_verdict_first(self):
        flat = " ".join(MINIMAL_COMPOSER_SYSTEM.split())
        assert "direct answer" in flat
        assert "first clause" in flat

    def test_omnibus_exclusion(self):
        # Benchmark cutoff: state of affairs at 1 May 2026; the Digital
        # Omnibus political agreement (7 May 2026) is out of scope.
        assert "Digital Omnibus" in MINIMAL_COMPOSER_SYSTEM
        assert "1 May 2026" in MINIMAL_COMPOSER_SYSTEM

    def test_closed_set_completeness(self):
        assert "every member" in MINIMAL_COMPOSER_SYSTEM

    def test_does_not_model_forbidden_punctuation(self):
        # R108: the prompt must not MODEL the punctuation the wire forbids.
        assert "—" not in MINIMAL_COMPOSER_SYSTEM  # em-dash
        assert "–" not in MINIMAL_COMPOSER_SYSTEM  # en-dash
        assert "…" not in MINIMAL_COMPOSER_SYSTEM  # ellipsis
        assert "..." not in MINIMAL_COMPOSER_SYSTEM

    def test_grounding_softened_not_removed(self):
        # Prefer supplied references, allow certain Act knowledge, keep the
        # citation-certainty bar (the anti-hallucination floor).
        assert "EU AI ACT REFERENCES" in MINIMAL_COMPOSER_SYSTEM
        assert "certain" in MINIMAL_COMPOSER_SYSTEM

    def test_good_only_exemplars(self):
        # GOOD-only examples (contrastive BAD examples model the forbidden
        # style and were dropped by design).
        assert "EXAMPLES:" in MINIMAL_COMPOSER_SYSTEM
        assert "BAD" not in MINIMAL_COMPOSER_SYSTEM


class TestCacheKey:
    def test_flag_in_engine_cache_key(self, monkeypatch):
        """R263.2 doctrine — the flag flips the engine answer, so the two
        ab_judge arms must produce distinct engine-cache keys."""
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_MINIMAL_COMPOSER", "0")
        k_off = _engine_cache_key("q", None)
        monkeypatch.setenv("REGENOLD_MINIMAL_COMPOSER", "1")
        k_on = _engine_cache_key("q", None)
        assert k_off != k_on

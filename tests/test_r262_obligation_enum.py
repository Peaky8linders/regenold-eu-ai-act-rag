"""R262 (2026-06-30) — obligation-ENUMERATION questions route to Opus 4.8.

User directive (AskUserQuestion): keep Sonnet-5 for genuinely-simple QA, but
route multi-obligation questions to Opus 4.8. The R261 ``_is_multi_phrase``
gate already routes multi-sentence / coordinated-clause questions to Opus, but
a SINGLE-clause "what must a provider put in place for a high-risk AI system?"
stays on Sonnet-5 despite being a sprawling multi-obligation ask (Arts 9-18 +
43 + 47-49 + 72 …) — the R261 medtech-judge obligation-enumeration fail rows.

The rule is DELIBERATELY narrow (only "what must a <operator role> …"), so it
does NOT touch the ``TestSimpleSkips`` precision floor: single-topic
"transparency obligations" / "cybersecurity requirements" and davidath-style
scenarios stay on Sonnet. Model-selection ONLY (never scope / retrieval / the
wire answer) → the deterministic davidath bench is byte-identical. Default ON,
env off-switch ``REGENOLD_OBLIGATION_ENUM_OPUS=0`` for instant rollback.
"""
from __future__ import annotations

import pytest

from app.engines import question_complexity as qc

# Genuinely-hard multi-obligation "what must a <role> …" asks that a SINGLE
# clause makes invisible to ``_is_multi_phrase`` — the R262 target class.
# NB "authorised representative" is ALSO caught by the pre-existing
# ``_ROLE_AMBIGUITY_RE`` signal (correctly — it is genuinely complex), so it
# fires regardless of the R262 rule; it is included for the default-ON "fires"
# test but excluded from the R262-EXCLUSIVE rollback set below.
_OBLIGATION_ENUMERATION = [
    "What must a provider put in place for a high-risk AI system?",
    "What must a deployer of a high-risk AI system do?",
    "What must an importer verify before placing a high-risk AI system on the market?",
    "What must a distributor check for a high-risk AI system?",
    "What must the authorised representative of a non-EU provider do?",
]

# The subset that is complex ONLY via the R262 rule (no role-ambiguity /
# other signal), so it cleanly falls back to Sonnet when R262 is OFF.
_OBLIGATION_ENUM_R262_ONLY = [
    "What must a provider put in place for a high-risk AI system?",
    "What must a deployer of a high-risk AI system do?",
    "What must an importer verify before placing a high-risk AI system on the market?",
    "What must a distributor check for a high-risk AI system?",
]

# The DELIBERATELY-EXCLUDED shapes — single-topic obligation lookups and
# scenarios the project treats as simple (Sonnet handles them fine). These are
# lifted verbatim from ``tests/test_question_complexity.py::TestSimpleSkips``
# and MUST stay simple even with the R262 rule ON, or we regress the
# precision floor (burn Opus latency on questions Sonnet handles).
_MUST_STAY_SIMPLE = [
    "What does Article 13 require?",
    "What is an AI system under the EU AI Act?",
    "How is 'deployer' defined?",
    "What is the definition of a provider?",
    "Who is a provider?",
    "What are the transparency obligations for high-risk AI systems?",
    "What cybersecurity requirements does Article 15 impose?",
    "We are a provider offering an AI system intended to be used "
    "as a safety component in machinery for industrial use.",
    "What is the capital of France?",
    "Suspend my Netflix subscription.",
    "Hello, how are you?",
]


class TestR262ObligationEnumDefaultOn:
    """Default ON — the "what must a <role> …" asks route to Opus."""

    @pytest.mark.parametrize("q", _OBLIGATION_ENUMERATION)
    def test_fires_when_unset(self, monkeypatch, q):
        monkeypatch.delenv("REGENOLD_OBLIGATION_ENUM_OPUS", raising=False)
        assert qc.is_complex_question(q) is True, q

    def test_gate_helper_defaults_on(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_OBLIGATION_ENUM_OPUS", raising=False)
        assert qc._obligation_enum_opus_enabled() is True


class TestR262PrecisionFloor:
    """The rule NEVER over-fires on the simple-skip set — even with the R118
    wide gate deleted (default) so only the R262 rule + baseline signals run.
    This is the user's "keep Sonnet-5 for genuinely-simple QA" guard."""

    @pytest.mark.parametrize("q", _MUST_STAY_SIMPLE)
    def test_simple_stays_simple(self, monkeypatch, q):
        monkeypatch.delenv("REGENOLD_OBLIGATION_ENUM_OPUS", raising=False)
        monkeypatch.delenv("REGENOLD_COMPLEX_GATE_WIDE", raising=False)
        assert qc.is_complex_question(q) is False, q


class TestR262Rollback:
    """``REGENOLD_OBLIGATION_ENUM_OPUS=0`` restores the pre-R262 routing (the
    obligation-enum asks fall back to Sonnet-5)."""

    @pytest.mark.parametrize("q", _OBLIGATION_ENUM_R262_ONLY)
    def test_stays_sonnet_when_off(self, monkeypatch, q):
        monkeypatch.setenv("REGENOLD_OBLIGATION_ENUM_OPUS", "0")
        # Wide gate also off so nothing else lifts these single clauses.
        monkeypatch.delenv("REGENOLD_COMPLEX_GATE_WIDE", raising=False)
        assert qc.is_complex_question(q) is False, q

    def test_gate_helper_off(self, monkeypatch):
        for val in ("0", "false", "no", "off"):
            monkeypatch.setenv("REGENOLD_OBLIGATION_ENUM_OPUS", val)
            assert qc._obligation_enum_opus_enabled() is False, val


class TestR262CacheKey:
    """R149/R263 doctrine — the behaviour-flipping env must be in the engine
    cache key so a same-process ab_judge A/B does not cross-contaminate."""

    def test_env_in_engine_cache_key_source(self):
        import inspect

        from app.routes import regenold

        src = inspect.getsource(regenold._engine_cache_key)
        assert "REGENOLD_OBLIGATION_ENUM_OPUS" in src


class TestR262MultiTurnScan:
    """The rule scans only the live-question section under the route's flatten
    marker (mirrors is_complex_question's ``rfind`` — a prior turn's role can't
    combine with the live turn)."""

    def test_fires_on_flattened_live_turn(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_OBLIGATION_ENUM_OPUS", raising=False)
        flat = (
            "Conversation so far:\nUser: We build an AI hiring tool.\n"
            "Assistant: That is high-risk under Annex III.\n\n"
            "Latest question:\nWhat must a provider put in place for it?"
        )
        assert qc.is_complex_question(flat, history_turn_count=3) is True


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

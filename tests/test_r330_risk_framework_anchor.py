"""R330 §3.1 — ``_detect_risk_framework_inquiry`` is an unanchored ``.search()``.

``_RISK_FRAMEWORK_TAXONOMY_RE`` is END-anchored on ``\\s*[?.]?\\s*$`` but carries
no START anchor, and the predicate applies ``.search()``.  The module comment
claims the end anchor makes it fire "ONLY when risk categor|tier|level|class is
the OBJECT of the question" — that reasoning covers a TRAILING system noun, not
a specific-system question whose FINAL CLAUSE is a bare taxonomy ask.

R330 july7-299 — "Does the EU AI Act classify AI systems used for irregular
migration, and if so, under which risk category?" — matches at span (86, 106):
a 20-char tail behind an 86-char prefix.  Two default-ON consequences fire off
that one predicate (the ungated engine intercept that seeds the canned 11-ref
taxonomy pack, and the route's ``_enforce_risk_framework_refs`` re-instatement),
and 9 of that row's 11 refs are judged wrong — 9 of the 55 wrong refs in the
whole R329 run (16.4%) from a single row.

``REGENOLD_RISK_FRAMEWORK_ANCHOR`` (DEFAULT 0) requires the match to start at
byte 0.  It is a pure narrowing: it can only remove firings, never add one.
"""
from __future__ import annotations

import pytest

from app.engines.graph_rag import (
    _RISK_FRAMEWORK_TAXONOMY_RE,
    _detect_risk_framework_inquiry,
    _risk_framework_anchor_enabled,
)

# The judged R329 HARD row this fix exists for.
JULY7_299 = (
    "Does the EU AI Act classify AI systems used for irregular migration, "
    "and if so, under which risk category?"
)
# The traffic the intercept was actually written for (R268 live q022/q047).
TAXONOMY_ASKS = [
    "What are all the risk categories in the EU AI Act?",
    "Explain the risk categories.",
    "What are the four risk tiers under the AI Act?",
    "List the risk levels in Regulation (EU) 2024/1689.",
]


class TestGateDefault:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", raising=False)
        assert _risk_framework_anchor_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "ON", "True"])
    def test_explicit_enable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", val)
        assert _risk_framework_anchor_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "  ", "2", "maybe"])
    def test_parses_fail_closed(self, monkeypatch, val):
        """Anything that is not an explicit enable means OFF."""
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", val)
        assert _risk_framework_anchor_enabled() is False


class TestAnchoredPredicate:
    def test_taxonomy_ask_still_fires(self, monkeypatch):
        """Empty prefix ⇒ the intercept's intended traffic is untouched."""
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        for q in TAXONOMY_ASKS:
            assert _detect_risk_framework_inquiry(q) is True, q

    def test_july7_299_no_longer_fires(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        assert _detect_risk_framework_inquiry(JULY7_299) is False

    def test_july7_299_fires_today(self, monkeypatch):
        """Gate OFF reproduces main — this is the defect, and the gate's proof."""
        monkeypatch.delenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", raising=False)
        assert _detect_risk_framework_inquiry(JULY7_299) is True

    def test_regex_itself_is_unchanged(self):
        """The ANCHOR does the work, not a regex edit.

        The taxonomy pattern must still match july7-299's 20-char tail at
        span (86, 106) behind an 86-char prefix — if this ever fails, someone
        narrowed the regex instead of the predicate and the intended
        "explain the risk categories" traffic is at risk.
        """
        m = _RISK_FRAMEWORK_TAXONOMY_RE.search(JULY7_299)
        assert m is not None
        assert m.span() == (86, 106), m.span()
        assert m.group(0) == "which risk category?"
        assert JULY7_299[: m.start()].strip() != ""

    def test_multiturn_marker_still_honoured(self, monkeypatch):
        """The prefix is measured on the LATEST turn, not the whole history."""
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        q = (
            "Conversation so far:\nWe deploy a recruitment tool.\n"
            "Latest question:\nWhat are all the risk categories?"
        )
        assert _detect_risk_framework_inquiry(q) is True

    def test_risk_management_negative_still_wins(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        assert _detect_risk_framework_inquiry(
            "What are the risk management categories?"
        ) is False


class TestDavidathZeroFireBeforeAndAfter:
    """The parent regex is 0-fire-verified on 137 QA + 339 scenarios; a strictly
    narrower predicate cannot rise above 0.  Asserted BOTH ways so the claim is
    measured, not assumed (R120 fast method — no 476 run needed)."""

    @staticmethod
    def _corpus() -> list[str]:
        from evals.bench import dataset

        qa = [(i.get("question") or "") for i in dataset.load_qa_pairs()]
        sc = [dataset.scenario_to_question(s) for s in dataset.load_scenarios()]
        assert len(qa) == 137 and len(sc) == 339, (len(qa), len(sc))
        return qa + sc

    def test_zero_fire_gate_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", raising=False)
        hits = [q for q in self._corpus() if _detect_risk_framework_inquiry(q)]
        assert hits == [], hits[:3]

    def test_zero_fire_gate_on(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        hits = [q for q in self._corpus() if _detect_risk_framework_inquiry(q)]
        assert hits == [], hits[:3]

    def test_gate_is_a_strict_narrowing(self, monkeypatch):
        """ON ⊆ OFF on every corpus row plus the taxonomy asks — the predicate
        can only REMOVE firings.  This is the property that makes the change
        davidath-neutral by construction rather than by measurement."""
        corpus = self._corpus() + TAXONOMY_ASKS + [JULY7_299]
        monkeypatch.delenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", raising=False)
        off = {q for q in corpus if _detect_risk_framework_inquiry(q)}
        monkeypatch.setenv("REGENOLD_RISK_FRAMEWORK_ANCHOR", "1")
        on = {q for q in corpus if _detect_risk_framework_inquiry(q)}
        assert on <= off
        assert off - on == {JULY7_299}

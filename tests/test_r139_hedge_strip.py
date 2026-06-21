"""R139 — strip the colloquial "It depends" hedge opener (legal-professional voice)."""
from __future__ import annotations

import pytest

from app.integrations.regenold.answer_normaliser import strip_hedge_opener

_VERDICT = (
    "high-risk only where the system is a safety component of a medical device "
    "requiring third-party conformity assessment under the Annex I legislation."
)


class TestStripHedgeOpener:
    def test_strips_colon_form(self) -> None:
        out = strip_hedge_opener(f"It depends: {_VERDICT}")
        assert not out.lower().startswith("it depends")
        assert out.startswith("High-risk only where")

    def test_strips_comma_form(self) -> None:
        out = strip_hedge_opener(f"It depends, {_VERDICT}")
        assert out.startswith("High-risk only where")

    def test_strips_period_form(self) -> None:
        out = strip_hedge_opener(f"It depends. High-risk only where {_VERDICT}")
        assert not out.lower().startswith("it depends")

    def test_strips_dash_form(self) -> None:
        out = strip_hedge_opener(f"It depends — {_VERDICT}")
        assert out.startswith("High-risk only where")

    def test_case_insensitive(self) -> None:
        out = strip_hedge_opener(f"IT DEPENDS: {_VERDICT}")
        assert not out.lower().startswith("it depends")

    def test_leaves_condition_before_delimiter_untouched(self) -> None:
        # "It depends on whether X; <verdict>" carries the deciding condition
        # BEFORE any delimiter — stripping would lose it, so leave it intact.
        src = "It depends on whether the system is a medical device; if so it is high-risk under Article 6."
        assert strip_hedge_opener(src) == src

    def test_clean_verdict_unchanged(self) -> None:
        src = f"High-risk only where {_VERDICT}"
        assert strip_hedge_opener(src) == src

    def test_unrelated_answer_unchanged(self) -> None:
        src = "Article 5 prohibits eight practices, including social scoring."
        assert strip_hedge_opener(src) == src

    def test_near_empty_remainder_floor_guard(self) -> None:
        # Don't strip a near-empty answer down to a stub.
        assert strip_hedge_opener("It depends.") == "It depends."

    def test_empty_and_whitespace(self) -> None:
        assert strip_hedge_opener("") == ""
        assert strip_hedge_opener("   ") == "   "

    def test_idempotent(self) -> None:
        once = strip_hedge_opener(f"It depends: {_VERDICT}")
        assert strip_hedge_opener(once) == once

    def test_env_off_is_passthrough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STRIP_HEDGE", "0")
        src = f"It depends: {_VERDICT}"
        assert strip_hedge_opener(src) == src

    def test_wired_into_normaliser(self) -> None:
        from app.integrations.regenold.models import normalise_answer_for_regenold

        out = normalise_answer_for_regenold(f"It depends: {_VERDICT}")
        assert not out.strip().lower().startswith("it depends")

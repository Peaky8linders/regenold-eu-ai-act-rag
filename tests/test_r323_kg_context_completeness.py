"""R323 — the graph must deliver COMPLETE statutory text, and bounded.

Two measured defects in ``kg_context``, the one place the Neo4j graph actually
reaches a live answer (it renders non-citable structure into the Stage-2
prompt).

1. IT AMPUTATED PROVISIONS MID-ENUMERATION, SILENTLY.
   ``_flat`` cut at the budget then backtracked to any sentence boundary past
   ``limit // 2``, so up to half the budget could be discarded. Measured:
   Article 27(1) is 1421 chars and was delivered at **470 — 33%**. The lost
   remainder began exactly at "For that purpose, deployers shall perform an
   assessment consisting of: (a) a description ...", so the model was told the
   FRIA duty exists and given none of its (a)-(f) contents, with nothing to
   indicate anything was missing. For a provision whose obligation IS its
   enumeration, that is worse than omitting it.

2. THE BLOCK WAS UNBOUNDED.
   Measured: a 12-ref scenario rendered a single 29,623-char block into the
   prompt. R319 measured added context at ~2.5% gold precision and demonstrated
   crowding-out (keyword recall 1.0 -> 0.0 on a gold article that WAS present
   in the inflated context), so this is a measured risk, not just token cost.
   A block-granular cap cannot fix it because the offender is ONE block, so the
   budget is now enforced while the lines are built, dropping whole units.

These tests exercise ``_flat`` and the assembly directly and therefore need no
live graph.
"""

from __future__ import annotations

import pytest

import app.data.provision_text as PT
from app.engines.kg_context import _UNIT_HARD_CEILING, _flat


# ── defect 1: completeness of a single unit ─────────────────────────────────


def test_article_27_1_fria_enumeration_is_delivered_whole() -> None:
    """The regression that motivated this round.

    Article 27(1) defines what a fundamental-rights impact assessment must
    CONTAIN. Delivering the duty without (a)-(f) misstates the obligation.
    """
    raw = PT.get_provision_text("Article 27(1)") or ""
    assert raw, "Article 27(1) must resolve"
    out = _flat(raw, 900)
    for token in ("(a)", "(b)", "(c)", "(d)", "(e)", "(f)"):
        assert token in out, f"FRIA content {token} missing from delivered text"
    assert "consisting of" in out
    assert len(out) == len(raw), f"expected the whole provision, got {len(out)}/{len(raw)}"


@pytest.mark.parametrize("ref", ["Article 27(1)", "Article 13(3)", "Article 9(2)"])
def test_enumerated_provisions_are_not_amputated(ref: str) -> None:
    raw = PT.get_provision_text(ref) or ""
    if not raw or "(a) " not in raw[:900]:
        pytest.skip(f"{ref} is not an enumerated provision in this corpus")
    out = _flat(raw, 900)
    assert out == raw.strip() or len(out) >= len(raw) * 0.95, (
        f"{ref}: enumerated provision delivered at {len(out)}/{len(raw)}"
    )


def test_backtrack_cannot_discard_half_the_budget() -> None:
    """A non-enumerated unit must still use most of its budget.

    The pre-R323 rule accepted any sentence break past ``limit // 2``. This
    text puts one at ~55% so the old code would return ~500 of a 900 budget.
    """
    text = ("A" * 480) + ". " + ("B" * 900)
    out = _flat(text, 900)
    assert len(out) > 700, f"backtrack discarded too much: {len(out)} of a 900 budget"


# ── truncation must be visible, never silent ────────────────────────────────


def test_genuinely_truncated_text_is_marked() -> None:
    out = _flat("X" * 60 + ". " + "Y" * 5000, 900)
    assert out.endswith("[...]"), (
        "a truncated unit must say so; ending mid-clause reads as a complete provision"
    )


def test_short_text_is_returned_verbatim_without_a_marker() -> None:
    assert _flat("Short provision.", 900) == "Short provision."
    assert "[...]" not in _flat("Short provision.", 900)


def test_oversized_enumeration_is_still_bounded() -> None:
    """The enumeration guard must not become an unbounded escape hatch."""
    huge = "consisting of: (a) " + ("z" * (_UNIT_HARD_CEILING + 4000))
    out = _flat(huge, 900)
    assert len(out) <= _UNIT_HARD_CEILING + 32, f"unit exceeded the hard ceiling: {len(out)}"


def test_flat_is_total_on_junk_input() -> None:
    for junk in (None, "", 0, [], {}):
        assert isinstance(_flat(junk, 900), str)


# ── defect 2: the total cap ─────────────────────────────────────────────────


def _render(refs: list[str], monkeypatch: pytest.MonkeyPatch, cap: str | None = None) -> list[str]:
    import app.engines.kg_context as K

    if cap is not None:
        monkeypatch.setenv("REGENOLD_KG_MAX_CHARS", cap)
    return K.render_kg_context(refs) or []


def test_cap_env_is_read_and_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.engines.kg_context import _DEFAULT_MAX_CHARS, _int_env

    monkeypatch.setenv("REGENOLD_KG_MAX_CHARS", "999999")
    assert _int_env("REGENOLD_KG_MAX_CHARS", _DEFAULT_MAX_CHARS, 1200, 60000) == 60000
    monkeypatch.setenv("REGENOLD_KG_MAX_CHARS", "1")
    assert _int_env("REGENOLD_KG_MAX_CHARS", _DEFAULT_MAX_CHARS, 1200, 60000) == 1200
    monkeypatch.setenv("REGENOLD_KG_MAX_CHARS", "not-a-number")
    assert _int_env("REGENOLD_KG_MAX_CHARS", _DEFAULT_MAX_CHARS, 1200, 60000) == _DEFAULT_MAX_CHARS


def test_default_cap_is_generous_enough_for_typical_requests() -> None:
    """The cap must bound the tail without touching ordinary 2-4 ref requests.

    Measured at the time of writing: 2 refs -> 5,744 chars, 4 refs -> 13,642.
    """
    from app.engines.kg_context import _DEFAULT_MAX_CHARS

    assert _DEFAULT_MAX_CHARS >= 14000, (
        "a cap below the measured 4-ref render would trim ordinary requests"
    )

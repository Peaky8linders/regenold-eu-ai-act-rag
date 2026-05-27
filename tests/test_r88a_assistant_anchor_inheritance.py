"""R88-A — Assistant-turn anchor inheritance regression tests.

r87-v2-live multi-turn coherence regressed 0.56 → 0.28. Deep-dive
(.planning/R88-NOTES) showed 3 of the 6 zero-refL rows shared one
pattern: the prior assistant turn explicitly named the operative
Article (Art. 99 / Art. 43 / Art. 111) but BM25 didn't elevate the
``[Context anchors — ...]`` prefix's article tokens above the
keyword-rich user follow-up. Engine retrieved the wrong topic.

R88-A injects the immediately-prior assistant turn's named Articles
at HEAD position of candidates — same pattern as R87-D role-duty seed.
Strictly additive; capped at 2 anchors per call. Env-gated
``REGENOLD_ASSISTANT_ANCHOR_INHERIT`` (default ON). Blocks inheritance
ONLY on true topic switches (user names a NEW article not in the
assistant's anchors); drill-downs (user references something the
assistant just named) still trigger inheritance.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routes.regenold import (
    _apply_assistant_anchor_inheritance,
    _engine_cache_key,
    _extract_assistant_anchors,
    _ASSISTANT_ANCHOR_INHERIT_MAX,
)


# ─── Extraction ────────────────────────────────────────────────────────────


def test_extract_articles_and_annexes() -> None:
    txt = "Article 43 routes most high-risk AI to internal control (Annex VI); biometric systems under Annex III(1) need a notified body (Annex VII)."
    out = _extract_assistant_anchors(txt)
    assert "Article 43" in out
    assert "Annex VI" in out
    assert "Annex III" in out
    assert "Annex VII" in out


def test_extract_collapses_subpoints_to_parent() -> None:
    """Article 99(3) → Article 99 (parent collapse; downstream expander
    walks the parent)."""
    out = _extract_assistant_anchors("Article 99(3) caps fines at €35M.")
    assert out == ["Article 99"]


def test_extract_handles_short_art_form() -> None:
    out = _extract_assistant_anchors("Per Art. 5 prohibitions...")
    assert out == ["Article 5"]


def test_extract_dedups_in_source_order() -> None:
    txt = "Article 13 and Article 14 and Article 13 again."
    out = _extract_assistant_anchors(txt)
    assert out == ["Article 13", "Article 14"]


def test_extract_empty_returns_empty_list() -> None:
    assert _extract_assistant_anchors("") == []
    assert _extract_assistant_anchors("No article references here.") == []


# ─── Inheritance triggering ────────────────────────────────────────────────


def _msg(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


def test_mt_v2_017_inherits_art99_from_assistant(monkeypatch) -> None:
    """Coreferent follow-up — no user article ref. Art. 99 inherited."""
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [
        _msg("user", "We knowingly deployed a prohibited practice."),
        _msg("assistant", "That's an Article 5 violation; Article 99(3) caps fines at €35M."),
    ]
    out = _apply_assistant_anchor_inheritance(
        ["Article 5"], turns,
        "We're a 25-employee startup — does the €35M cap actually hit us?",
    )
    assert out[0] == "Article 99"  # head injection
    assert "Article 5" in out


def test_mt_v2_023_inherits_art111(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [
        _msg("user", "Our HRAIS was placed on the market in March 2026."),
        _msg("assistant", "Article 111 covers transitional provisions for systems already on the market."),
    ]
    out = _apply_assistant_anchor_inheritance(
        ["Annex III"], turns,
        "Do we have to retrofit conformity, or are we grandfathered?",
    )
    assert out[0] == "Article 111"


def test_drill_down_user_ref_in_assistant_anchors_still_inherits(monkeypatch) -> None:
    """When user names a ref that IS in the assistant's anchors
    (Annex III(4) → Annex III), inheritance still fires because it's a
    drill-down, not a topic switch."""
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [
        _msg("user", "Annex IV docs."),
        _msg("assistant", "Article 11 + Annex IV."),
        _msg("user", "Conformity assessment?"),
        _msg("assistant", "Article 43 routes most HRAIS to internal control (Annex VI); Annex III(1) needs notified body."),
    ]
    out = _apply_assistant_anchor_inheritance(
        ["Annex III"], turns,
        "We're under Annex III(4) (employment). Which route?",
    )
    assert "Article 43" in out  # MUST be injected despite Annex III in user
    assert "Annex VI" in out


# ─── Blocking conditions ──────────────────────────────────────────────────


def test_disabled_env_returns_input(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", "0")
    turns = [_msg("assistant", "Article 13 covers transparency.")]
    out = _apply_assistant_anchor_inheritance(["Article 50"], turns, "follow-up?")
    assert out == ["Article 50"]


def test_no_history_returns_input(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    out = _apply_assistant_anchor_inheritance(["Article 50"], [], "single turn?")
    assert out == ["Article 50"]


def test_no_assistant_turn_returns_input(monkeypatch) -> None:
    """Only-user history (e.g. system message + first user turn) → no anchor source."""
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [_msg("user", "first turn no assistant")]
    out = _apply_assistant_anchor_inheritance(["Article 50"], turns, "follow-up?")
    assert out == ["Article 50"]


def test_assistant_with_no_articles_returns_input(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [_msg("assistant", "Yes, that's correct.")]
    out = _apply_assistant_anchor_inheritance(["Article 50"], turns, "follow-up?")
    assert out == ["Article 50"]


def test_true_topic_switch_blocks_inheritance(monkeypatch) -> None:
    """User names a NEW article not in assistant anchors → topic switch.
    Do NOT inherit (the user clearly moved on)."""
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [_msg("assistant", "Article 13 covers transparency for HRAIS providers.")]
    out = _apply_assistant_anchor_inheritance(
        ["Article 50"], turns,
        "What about Article 26 for deployers?",  # Art. 26 NOT in assistant anchors
    )
    assert out == ["Article 50"]


# ─── Dedup + caps ─────────────────────────────────────────────────────────


def test_capped_at_max_inject(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    # Assistant names 5 articles — cap should hold the inject to 2
    turns = [
        _msg("assistant", "Articles 10, 11, 12, 13, and 14 govern data and docs."),
    ]
    out = _apply_assistant_anchor_inheritance(["Article 50"], turns, "follow-up?")
    added = [r for r in out if r not in ("Article 50",)]
    assert len(added) <= _ASSISTANT_ANCHOR_INHERIT_MAX


def test_skips_when_anchor_already_in_candidates(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [_msg("assistant", "Article 13 covers transparency.")]
    out = _apply_assistant_anchor_inheritance(
        ["Article 13", "Article 50"], turns, "follow-up?",
    )
    # Article 13 already there — no duplicate
    assert out.count("Article 13") == 1


def test_subpoint_collapses_to_parent_for_dedup(monkeypatch) -> None:
    """Candidate ``Article 13.2`` already covers parent ``Article 13``
    so the assistant's `Article 13` mention does NOT re-inject."""
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [_msg("assistant", "Article 13 — transparency.")]
    out = _apply_assistant_anchor_inheritance(
        ["Article 13.2"], turns, "follow-up?",
    )
    assert "Article 13" not in out  # parent NOT re-injected
    assert out == ["Article 13.2"]


def test_inheritance_preserves_existing_candidates_order(monkeypatch) -> None:
    """Original candidates keep their relative order; injected anchors
    sit at the HEAD."""
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    turns = [_msg("assistant", "Article 111 — transitional provisions.")]
    out = _apply_assistant_anchor_inheritance(
        ["Article 6", "Annex III"], turns, "follow-up?",
    )
    assert out == ["Article 111", "Article 6", "Annex III"]


def test_never_mutates_input(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", raising=False)
    cands = ["Article 50"]
    snapshot = list(cands)
    turns = [_msg("assistant", "Article 13 covers transparency.")]
    out = _apply_assistant_anchor_inheritance(cands, turns, "follow-up?")
    assert cands == snapshot
    assert id(out) != id(cands)


def test_env_var_in_cache_key(monkeypatch) -> None:
    """R30/R56/R79 cache-poisoning doctrine — flipping the env must
    produce a distinct cache key."""
    monkeypatch.setenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", "1")
    k_on = _engine_cache_key("q", None)
    monkeypatch.setenv("REGENOLD_ASSISTANT_ANCHOR_INHERIT", "0")
    k_off = _engine_cache_key("q", None)
    assert k_on != k_off

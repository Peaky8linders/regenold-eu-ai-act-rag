"""Tests for cross-turn anchor injection in _build_question_from_history.

Round 60-C: verifies that _extract_conversation_anchors correctly pulls
article refs, roles, and risk-tier from ALL prior turns, and that
_build_question_from_history injects them as a [Context anchors] prefix
before the "Conversation so far:" block.
"""

import pytest

from app.integrations.regenold.models import RegenoldChatMessage
from app.routes.regenold import (
    _HISTORY_TURNS_TO_INCLUDE,
    _build_question_from_history,
    _extract_conversation_anchors,
)


# ---------------------------------------------------------------------------
# 1. Single turn — no anchor line
# ---------------------------------------------------------------------------


def test_single_turn_no_anchors() -> None:
    """Single-turn message produces no 'Context anchors' line."""
    msgs = [RegenoldChatMessage(role="user", content="What does Article 13 require?")]
    question, _ = _build_question_from_history(msgs)
    assert "Context anchors" not in question


# ---------------------------------------------------------------------------
# 2. Two-turn — anchor extracted and injected
# ---------------------------------------------------------------------------


def test_two_turn_anchor_extraction() -> None:
    """Turn 1 establishes Article 13 + provider role → anchor appears in output."""
    msgs = [
        RegenoldChatMessage(
            role="user",
            content="We are a provider under Article 13. What must we document?",
        ),
        RegenoldChatMessage(
            role="assistant",
            content="Under Article 13 you must provide transparency documentation.",
        ),
        RegenoldChatMessage(role="user", content="What about our deployers?"),
    ]
    question, _ = _build_question_from_history(msgs)
    assert "[Context anchors" in question
    assert "Art. 13" in question
    assert "provider" in question
    # Anchor block comes BEFORE the history block
    anchor_pos = question.index("[Context anchors")
    history_pos = question.index("Conversation so far:")
    assert anchor_pos < history_pos


# ---------------------------------------------------------------------------
# 3. Cap at 6 article refs
# ---------------------------------------------------------------------------


def test_anchor_caps_at_six_refs() -> None:
    """More than 6 article refs in history → only first 6 in anchor line."""
    # Build 8 distinct article refs across prior turns
    prior_turns = [
        RegenoldChatMessage(
            role="user",
            content=(
                "Article 5, Article 6, Article 9, Article 10, "
                "Article 11, Article 12, Article 13, Article 14"
            ),
        ),
        RegenoldChatMessage(role="assistant", content="Noted."),
    ]
    anchor = _extract_conversation_anchors(prior_turns)
    # Anchor must exist and cap at 6
    assert "articles:" in anchor
    # Count commas in the articles section → at most 5 commas (6 items)
    articles_section = anchor.split("articles:")[1].split(";")[0]
    refs = [r.strip() for r in articles_section.split(",") if r.strip()]
    assert len(refs) <= 6


# ---------------------------------------------------------------------------
# 4. Anchors from all turns, not just the history window
# ---------------------------------------------------------------------------


def test_anchor_from_all_turns_not_just_window() -> None:
    """Article ref from turn 1 survives even when it falls outside the history window."""
    # Build 12 turns (10 prior + 1 user at idx 10 + 1 live at idx 11)
    # Turn 0 establishes Art. 5; _HISTORY_TURNS_TO_INCLUDE=8 so only turns 2-9 appear
    # in the history block — but the anchor should still include Art. 5.
    msgs = [
        RegenoldChatMessage(
            role="user",
            content="We are a provider under Article 5 prohibition rules.",
        ),
        RegenoldChatMessage(role="assistant", content="Noted."),
        RegenoldChatMessage(role="user", content="Turn 2"),
        RegenoldChatMessage(role="assistant", content="Reply 2"),
        RegenoldChatMessage(role="user", content="Turn 3"),
        RegenoldChatMessage(role="assistant", content="Reply 3"),
        RegenoldChatMessage(role="user", content="Turn 4"),
        RegenoldChatMessage(role="assistant", content="Reply 4"),
        RegenoldChatMessage(role="user", content="Turn 5"),
        RegenoldChatMessage(role="assistant", content="Reply 5"),
        RegenoldChatMessage(role="user", content="Turn 6"),
        RegenoldChatMessage(role="assistant", content="Reply 6"),
        RegenoldChatMessage(role="user", content="What does Art. 5 say about us?"),
    ]
    question, _ = _build_question_from_history(msgs)
    # The anchor line must carry Art. 5 even if turn 0 is outside the 8-turn window
    assert "[Context anchors" in question
    assert "Art. 5" in question


# ---------------------------------------------------------------------------
# 5. _HISTORY_TURNS_TO_INCLUDE equals 8
# ---------------------------------------------------------------------------


def test_history_turns_increased_to_8() -> None:
    """The history window constant must be 8 (R60-C)."""
    assert _HISTORY_TURNS_TO_INCLUDE == 8


# ---------------------------------------------------------------------------
# 6. Truncation still works after anchor injection
# ---------------------------------------------------------------------------


def test_truncation_still_works() -> None:
    """Very long history is truncated to ≤2000 chars; 'Latest question' marker survives."""
    msgs = [
        RegenoldChatMessage(role="user", content="Article 13: " + "A" * 900),
        RegenoldChatMessage(role="assistant", content="B" * 900),
        RegenoldChatMessage(role="user", content="LIVE_QUESTION_SENTINEL"),
    ]
    question, _ = _build_question_from_history(msgs)
    assert len(question) <= 2000
    assert "LIVE_QUESTION_SENTINEL" in question
    assert "Latest question:" in question


# ---------------------------------------------------------------------------
# 7. No anchor for turns with no regulatory content
# ---------------------------------------------------------------------------


def test_no_anchor_for_out_of_scope_turns() -> None:
    """Turns with no articles / roles / risk words → no anchor line."""
    msgs = [
        RegenoldChatMessage(role="user", content="Hello, how are you today?"),
        RegenoldChatMessage(role="assistant", content="Fine, thanks!"),
        RegenoldChatMessage(role="user", content="Tell me more."),
    ]
    question, _ = _build_question_from_history(msgs)
    assert "Context anchors" not in question


# ---------------------------------------------------------------------------
# 8. Role word extraction
# ---------------------------------------------------------------------------


def test_role_word_extraction() -> None:
    """Both 'deployer' and 'provider' extracted when they appear in turns."""
    turns = [
        RegenoldChatMessage(
            role="user",
            content="As a provider we built it; our client is the deployer.",
        ),
        RegenoldChatMessage(role="assistant", content="Understood."),
    ]
    anchor = _extract_conversation_anchors(turns)
    assert "provider" in anchor
    assert "deployer" in anchor


# ---------------------------------------------------------------------------
# 9. Risk word extraction
# ---------------------------------------------------------------------------


def test_risk_word_extraction() -> None:
    """'high-risk' in turn 1 → anchor includes the risk tier."""
    turns = [
        RegenoldChatMessage(
            role="user",
            content="Our system is a high-risk AI system under Annex III.",
        ),
        RegenoldChatMessage(role="assistant", content="Understood."),
    ]
    anchor = _extract_conversation_anchors(turns)
    assert "risk tier:" in anchor
    # At least one of the risk-tier markers should appear
    assert "high-risk" in anchor or "high risk" in anchor or "annex iii" in anchor


# ---------------------------------------------------------------------------
# 10. Deduplication: same ref in multiple turns → appears once
# ---------------------------------------------------------------------------


def test_anchor_deduplication() -> None:
    """Article 13 appearing in multiple turns is deduplicated in the anchor."""
    turns = [
        RegenoldChatMessage(
            role="user", content="Article 13 transparency is relevant."
        ),
        RegenoldChatMessage(
            role="assistant", content="Yes, Article 13 requires disclosure."
        ),
        RegenoldChatMessage(
            role="user", content="More about Article 13?"
        ),
    ]
    anchor = _extract_conversation_anchors(turns)
    # Count occurrences of "Art. 13" in the anchor line itself
    count = anchor.count("Art. 13")
    assert count == 1, f"Expected 1 occurrence of Art. 13 in anchor, got {count}: {anchor!r}"

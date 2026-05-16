"""Tests for ``app.engines.prohibited_gatekeeper`` — TAI Scan Layer C."""
from __future__ import annotations

import pytest

from app.engines.prohibited_gatekeeper import (
    force_prohibited_citations,
    scan_for_prohibitions,
)


# ── scan_for_prohibitions ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question,expected_subref",
    [
        # Each of the 8 Art. 5 prohibitions + the Omnibus 9th — at least one
        # keyword phrase per practice should fire the gatekeeper.
        ("Subliminal manipulation by a chatbot", "Art. 5.1.a"),
        ("AI that exploits vulnerabilities of elderly people", "Art. 5.1.b"),
        ("Is social scoring banned?", "Art. 5.1.c"),
        ("Predictive policing using personality profiling", "Art. 5.1.d"),
        ("Scraping facial images for a facial recognition database", "Art. 5.1.e"),
        ("Emotion recognition in the workplace", "Art. 5.1.f"),
        ("Biometric categorisation by political affiliation", "Art. 5.1.g"),
        ("Real-time biometric identification in public spaces", "Art. 5.1.h"),
    ],
)
def test_scan_detects_each_prohibition(question, expected_subref):
    matches = scan_for_prohibitions(question)
    assert matches, f"no match on {question!r}"
    found_subs = {sub for _parent, sub in matches}
    assert expected_subref in found_subs, (
        f"{question!r} did not fire {expected_subref}; got {found_subs}"
    )


def test_scan_returns_empty_on_non_prohibition_question():
    """Questions unrelated to Art. 5 don't fire the gatekeeper."""
    qs = [
        "What is the maximum fine?",
        "What documentation must I provide?",
        "What is a deployer?",
        "How does conformity assessment work?",
    ]
    for q in qs:
        matches = scan_for_prohibitions(q)
        assert matches == (), f"{q!r} unexpectedly fired {matches}"


def test_scan_returns_empty_on_empty_input():
    assert scan_for_prohibitions("") == ()
    assert scan_for_prohibitions("   ") == ()


def test_scan_deduplicates_same_subparagraph():
    """A question mentioning the same keyword twice fires once."""
    matches = scan_for_prohibitions(
        "social scoring and more social scoring everywhere"
    )
    subs = [sub for _p, sub in matches]
    assert subs.count("Art. 5.1.c") == 1


def test_scan_finds_multiple_distinct_prohibitions():
    """A question mentioning two prohibitions surfaces both, in regulation order."""
    q = "Both social scoring and emotion recognition are concerning"
    matches = scan_for_prohibitions(q)
    subs = [sub for _p, sub in matches]
    # Art. 5(1)(c) comes before 5(1)(f) in the regulation; output must reflect that.
    assert "Art. 5.1.c" in subs
    assert "Art. 5.1.f" in subs
    assert subs.index("Art. 5.1.c") < subs.index("Art. 5.1.f")


# ── force_prohibited_citations ───────────────────────────────────────────


def test_force_prepends_user_facing_refs():
    """Matches are converted to user-facing form and prepended."""
    matches = (("Art. 5", "Art. 5.1.f"),)
    existing = ["Article 99"]
    out = force_prohibited_citations(existing, matches)
    # Prepended; existing follows.
    assert out[0] == "Article 5.1.f"
    assert "Article 99" in out
    # ``Article 99`` keeps its position relative to other existing refs.
    assert out.index("Article 5.1.f") < out.index("Article 99")


def test_force_no_matches_passthrough():
    """Empty matches → ``current_refs`` returned unchanged."""
    existing = ["Article 99", "Article 50"]
    out = force_prohibited_citations(existing, ())
    assert out == existing


def test_force_does_not_double_inject_existing():
    """If Art. 5 was already in citations, the gatekeeper doesn't duplicate it."""
    matches = (("Art. 5", "Art. 5.1.f"),)
    existing = ["Article 5"]
    out = force_prohibited_citations(existing, matches)
    # Article 5 (parent) is already in existing → keep it where it is, only
    # add the sub-ref Article 5.1.f.
    assert out.count("Article 5") == 1
    assert "Article 5.1.f" in out


def test_force_respects_max_inject_cap():
    """No more than ``max_inject`` refs are prepended."""
    matches = (
        ("Art. 5", "Art. 5.1.a"),
        ("Art. 5", "Art. 5.1.c"),
        ("Art. 5", "Art. 5.1.f"),
        ("Art. 5", "Art. 5.1.h"),
    )
    existing: list[str] = []
    out = force_prohibited_citations(existing, matches, max_inject=2)
    # The cap counts INJECTED refs (which include parent + sub for each
    # match). With max_inject=2 we should see at most 2 prepended.
    assert len(out) == 2


def test_force_pure_no_mutation():
    """Inputs are not mutated."""
    matches = (("Art. 5", "Art. 5.1.f"),)
    existing = ["Article 99"]
    existing_before = list(existing)
    matches_before = tuple(matches)
    force_prohibited_citations(existing, matches)
    assert existing == existing_before
    assert matches == matches_before


# ── Integration ──────────────────────────────────────────────────────────


def test_gatekeeper_on_davidath_emotion_question():
    """Regression for one of the documented competition example questions.

    The PDF lists "Are AI systems intended for emotion recognition from
    biometric data always prohibited?" as an example. The gatekeeper
    must fire on it (CLAUDE.md hard rule #3 — generalisation, not
    overfit — so we only verify the keyword path that any emotion-
    recognition question takes).
    """
    matches = scan_for_prohibitions(
        "Are AI systems intended for emotion recognition from biometric data "
        "always prohibited?"
    )
    assert matches
    subs = [sub for _p, sub in matches]
    assert "Art. 5.1.f" in subs  # emotion_recognition_workplace

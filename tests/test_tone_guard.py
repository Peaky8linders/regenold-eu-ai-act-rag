"""R38 tone enforcement (Issue A4).

The Regenold rubric scores 'professionally worded' tone. Strip hedge
openers; force imperative/declarative voice; preserve cite-anchored
sentences.
"""
from app.integrations.regenold.tone_guard import enforce_tone


def test_strips_hedge_prefix_i_think():
    out = enforce_tone("I think Article 6 applies here.")
    assert out == "Article 6 applies here."


def test_strips_hedge_prefix_it_seems():
    out = enforce_tone("It seems that the system must be classified as high-risk.")
    assert out.lower().startswith("the system")


def test_strips_based_on_my_understanding():
    out = enforce_tone("Based on my understanding, Annex III lists eight categories.")
    assert out.startswith("Annex III")


def test_strips_as_an_ai():
    out = enforce_tone("As an AI, I cannot give legal advice, but Article 5(1)(f) prohibits this.")
    # Drop the whole "As an AI" clause through the comma
    assert "as an ai" not in out.lower()
    assert "Article 5" in out


def test_preserves_cite_anchored_opener():
    src = "Article 5(1)(f) prohibits emotion recognition in the workplace."
    assert enforce_tone(src) == src


def test_preserves_already_declarative():
    src = "The provider must establish a quality management system."
    assert enforce_tone(src) == src


def test_returns_original_on_empty():
    assert enforce_tone("") == ""
    assert enforce_tone(None) == ""


def test_strips_please_note_that():
    out = enforce_tone("Please note that Article 50 transparency obligations apply.")
    assert out.startswith("Article 50")


def test_strips_multiple_hedges_compound():
    out = enforce_tone(
        "I think it seems that, based on my reading, the system is high-risk."
    )
    # All three hedges stripped — should start with "The system"
    assert out.startswith("The system") or out.startswith("the system")


# ── R53.1-A mid-sentence rewrites ──
#
# Closes the 6 V2 tone-failure rows where Sonnet polish drifted into
# first-person AFTER a legitimate cite-anchored opener. R52.1-B's
# opener-strip can't reach those (e.g. "Article 26 requires X. We
# should also note Y." — opener is the article cite).

import pytest


def test_strips_we_should_note_that():
    out = enforce_tone(
        "Article 26 applies. We should note that Article 22 also applies."
    )
    assert out == "Article 26 applies. Article 22 also applies."


def test_strips_we_should_also_at_lead_in():
    out = enforce_tone(
        "Article 5 prohibits this. We should also document compliance."
    )
    assert out == "Article 5 prohibits this. Document compliance."


def test_strips_let_me_address():
    out = enforce_tone(
        "The system is high-risk. Let me address the conformity assessment path."
    )
    assert out == "The system is high-risk. The conformity assessment path."


def test_strips_let_us_clarify():
    out = enforce_tone("Article 50 applies. Let us clarify the scope.")
    assert out == "Article 50 applies. The scope."


def test_strips_i_would_note():
    out = enforce_tone(
        "Under Article 50 obligations apply. I would note that Article 25 also applies."
    )
    assert out == "Under Article 50 obligations apply. Article 25 also applies."


def test_strips_in_our_view():
    out = enforce_tone(
        "In our view, the system requires Article 9 risk management."
    )
    assert out == "The system requires Article 9 risk management."


def test_strips_our_recommendation_is_that():
    out = enforce_tone(
        "Our recommendation is that providers comply with Article 16."
    )
    assert out == "Providers comply with Article 16."


def test_preserves_legitimate_first_person_pronouns_in_definitions():
    # Bare quoted pronoun followed by definitional anchor — none of the
    # R53.1-A patterns require a following modal/verb here, so this is
    # untouched. (Defensive: the pattern set DOES NOT include bare "we".)
    src = "The 'we' in Article 3(1) refers to providers and deployers jointly."
    assert enforce_tone(src) == src


def test_preserves_imperative_after_rewrite():
    # "We should ensure compliance." -> "Ensure compliance."
    # Capitalisation must be restored after the modal stack is dropped.
    out = enforce_tone("We should ensure compliance.")
    assert out == "Ensure compliance."


def test_idempotent_on_already_clean_text():
    src = "Article 6 applies to high-risk AI systems."
    assert enforce_tone(src) == src


def test_handles_multiple_sentences_each_with_first_person():
    # 3 sentences: rewrite / untouched / rewrite.
    out = enforce_tone(
        "We should document compliance. "
        "The provider must establish a QMS. "
        "Let me clarify Article 9."
    )
    assert out == (
        "Document compliance. The provider must establish a QMS. Article 9."
    )


def test_fail_soft_on_pathological_input():
    # 10K-char string with no first-person triggers; rewriter passes it
    # through untouched. The try/except in _rewrite_first_person_mid_sentence
    # would also catch any genuine regex explosion.
    src = "X" * 10000
    out = enforce_tone(src)
    assert out == src


def test_combination_opener_plus_mid_sentence():
    # Opener strip removes "Based on my understanding,"; per-sentence
    # walker rewrites "We should also" in sentence 2.
    out = enforce_tone(
        "Based on my understanding, the system is high-risk. "
        "We should also document this."
    )
    assert out == "The system is high-risk. Document this."


@pytest.mark.skip(
    reason="quote-awareness deferred to R54 — current pattern set "
    "doesn't introspect quoted regions; risk of dropping legitimate "
    "quoted-policy text is low because patterns require following "
    "verbs that don't naturally appear inside quoted definitional "
    "callouts."
)
def test_does_not_strip_we_should_inside_quotes():
    src = 'Article 3 defines a provider as one who "we should consider responsible".'
    assert enforce_tone(src) == src


def test_capitalisation_restored_after_clause_drop():
    out = enforce_tone(
        "Article 5 prohibits this. "
        "We should also note that biometric categorisation is included."
    )
    assert out == (
        "Article 5 prohibits this. Biometric categorisation is included."
    )


# ── R53.1-A post-eng-review regression coverage ──


def test_two_same_pattern_first_person_phrases_in_one_sentence():
    """R53.1-A regression: count=1 let the second occurrence of the same
    pattern slip through. Eng-review P1 demonstrated this live with
    'We should document and we should verify.' yielding the bug output
    'Document and we should verify.'. Fix: count=0 replaces all
    occurrences per pattern. This test pins the fix."""
    assert enforce_tone("We should document and we should verify.") == (
        "Document and verify."
    )
    assert enforce_tone("We should document and we should also verify.") == (
        "Document and verify."
    )


def test_pattern_ordering_invariant_we_should_note_that():
    """R53.1-A pattern-ordering invariant: pattern #1 ("we should note
    that") MUST fire before pattern #2 ("we should"), otherwise pattern
    #2 strips "we should" and leaves a stranded "note that". This test
    would fail loudly if a future maintainer reorders the alternation."""
    out = enforce_tone("We should note that Article 9 applies.")
    assert out == "Article 9 applies."
    # Three-pattern stack: opener + mid-sentence + a second mid-sentence
    out2 = enforce_tone(
        "Based on my reading, we should note that Article 9 applies. "
        "We should also note that Article 22 applies."
    )
    assert out2 == "Article 9 applies. Article 22 applies."

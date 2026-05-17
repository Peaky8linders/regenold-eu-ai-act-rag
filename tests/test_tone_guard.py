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

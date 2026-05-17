"""R38 per-intent answer-length templates (Issue A2)."""
from app.engines.answer_template import (
    apply_template,
    INTENT_LENGTH_CAP,
)


def test_length_cap_table_complete():
    for k in ("DEFINITION", "BOOLEAN", "DESCRIPTION", "LIST"):
        assert k in INTENT_LENGTH_CAP


def test_definitional_cap_tight():
    assert INTENT_LENGTH_CAP["DEFINITION"] <= 200


def test_definitional_truncates_long_answer():
    long = "This is a very long definitional answer. " * 10  # ~410 chars
    out = apply_template(
        qtype="DEFINITION",
        answer=long,
        primary_cite="Article 3",
    )
    assert len(out) <= 250  # cap + small skeleton slack


def test_short_answer_passes_through_unchanged():
    src = "A provider is the entity that develops the AI system. (Article 3.3)"
    out = apply_template(qtype="DEFINITION", answer=src, primary_cite="Article 3.3")
    assert out == src


def test_classification_two_sentence_template():
    long = "This system is classified as high-risk. " * 5  # multi-sentence
    out = apply_template(qtype="BOOLEAN", answer=long, primary_cite="Article 6")
    # Should trim to at most 2 sentences + cite anchor.
    sentence_count = out.count(". ") + (1 if out.endswith(".") else 0)
    assert sentence_count <= 2


def test_apply_template_falls_through_on_unknown_qtype():
    src = "Some answer."
    out = apply_template(qtype="UNKNOWN", answer=src, primary_cite=None)
    assert out == src


def test_primary_cite_appended_when_missing():
    src = "The system must establish a quality management system."
    out = apply_template(
        qtype="DEFINITION",
        answer=src,
        primary_cite="Article 17",
    )
    # cite is appended if not present
    assert "Article 17" in out

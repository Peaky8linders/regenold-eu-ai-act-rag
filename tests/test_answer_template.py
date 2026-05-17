"""R38 per-intent answer-length templates (Issue A2).

R39 eng-review F1: dict keys lowercased to match
``app.engines.sentence_index.classify_question`` output.
"""
from app.engines.answer_template import (
    apply_template,
    INTENT_LENGTH_CAP,
)


def test_length_cap_table_complete():
    for k in ("definition", "boolean", "description", "list"):
        assert k in INTENT_LENGTH_CAP


def test_caps_within_calibrated_bounds():
    """R40 Phase 2a — caps are p90 of davidath gold-answer character
    length per qtype (see ``scripts/calibrate_answer_template.py``).

    Lower bound: 100 (no qtype should be tighter than ~100c, the
    p90 of one-word numeric answers). Upper bound: 700 (the davidath
    scenario-question synthesiser routes every scenario to
    ``definition`` via the qtype classifier, and scenario gold has
    p90 ~640c — so the cap must accommodate that without trimming).
    """
    for qt, cap in INTENT_LENGTH_CAP.items():
        assert 100 <= cap <= 700, f"{qt} cap {cap} outside [100, 700]"


def test_definitional_truncates_long_answer():
    long = "This is a very long definitional answer. " * 10  # ~410 chars
    out = apply_template(
        qtype="definition",
        answer=long,
        primary_cite="Article 3",
    )
    assert len(out) <= 250  # cap + small skeleton slack


def test_short_answer_passes_through_unchanged():
    src = "A provider is the entity that develops the AI system. (Article 3.3)"
    out = apply_template(qtype="definition", answer=src, primary_cite="Article 3.3")
    assert out == src


def test_classification_two_sentence_template():
    long = "This system is classified as high-risk. " * 5  # multi-sentence
    out = apply_template(qtype="boolean", answer=long, primary_cite="Article 6")
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
        qtype="definition",
        answer=src,
        primary_cite="Article 17",
    )
    # cite is appended if not present
    assert "Article 17" in out


def test_lowercase_keys_match_classify_question_output():
    """Regression test for R39 F1 case-mismatch bug — every qtype
    returned by classify_question must hit a budget in the cap table.
    """
    from app.engines.sentence_index import classify_question
    for q in (
        "What is a provider?",
        "How long do I keep logs?",
        "When does Art. 113 apply?",
        "How many articles are in Chapter II?",
        "Is emotion recognition prohibited?",
        "List the high-risk categories.",
        "How do I do a FRIA?",
        "Who is the deployer?",
        "Describe Annex IV.",
        "We are a healthcare provider offering AI diagnostics. What applies?",
    ):
        qt = classify_question(q)
        assert qt in INTENT_LENGTH_CAP, f"qtype {qt!r} missing from cap table"

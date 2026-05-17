"""R38 sub-point reference emitter.

When the question's topic matches an entry in SUBPOINT_TOPIC_MAP, upgrade
the surfaced base-article reference to include the leaf sub-point. The
emitter emits BOTH base + leaf as a 2-ref pair when the topic match is
ambiguous (loose-bench safety net).
"""
from app.data.subpoint_emitter import (
    SUBPOINT_TOPIC_MAP,
    upgrade_references,
)


def test_emotion_recognition_upgrades_to_art_5_1_f():
    # Topic: emotion-recognition prohibition — leaf is Art. 5(1)(f)
    refs = upgrade_references(
        question="Are AI systems for emotion recognition in the workplace always prohibited?",
        base_refs=["Article 5"],
    )
    assert "Article 5.1.f" in refs


def test_nudification_upgrades_to_new_lit_after_omnibus():
    # Topic: CSAM/nudification — the new Omnibus Art. 5 letter (h or j)
    refs = upgrade_references(
        question="Are nudification apps prohibited under the AI Act?",
        base_refs=["Article 5"],
    )
    # Don't assert the exact letter — it's not yet settled in final text.
    # Assert at least one sub-point form is emitted.
    assert any(r.startswith("Article 5.1.") for r in refs)


def test_technical_documentation_hardware_emits_annex_iv_subpoints():
    # Topic: tech doc hardware — Annex IV(2)(a)
    refs = upgrade_references(
        question="Does the technical documentation require hardware specs?",
        base_refs=["Annex IV", "Article 11"],
    )
    assert any(r.startswith("Annex IV.") for r in refs)


def test_unknown_topic_returns_input_unchanged():
    refs = upgrade_references(
        question="What is the meaning of life?",
        base_refs=["Article 3"],
    )
    assert refs == ["Article 3"]


def test_subpoint_topic_map_has_at_least_31_entries():
    # Spec calls for 31 leaf-subpoint entries minimum.
    assert len(SUBPOINT_TOPIC_MAP) >= 31


def test_emit_pair_when_topic_match_ambiguous():
    # When a question matches a topic with confidence < 1.0 (multiple
    # plausible sub-points), emit BOTH base and leaf.
    refs = upgrade_references(
        question="Tell me about prohibited practices.",
        base_refs=["Article 5"],
    )
    # Both base and at least one leaf
    assert "Article 5" in refs
    assert any(r.startswith("Article 5.1.") for r in refs)


def test_existing_subpoint_ref_is_preserved():
    refs = upgrade_references(
        question="Are AI systems for emotion recognition always prohibited?",
        base_refs=["Article 5.1.f"],  # already a leaf — don't double-upgrade
    )
    # R39 eng-review F3: emotion-recognition topic maps to BOTH
    # Article 5.1.f AND Annex III.5 (HRAIS context). The leaf for
    # Article 5 is already present so the upgrade pass leaves it alone;
    # the new INJECT pass adds Annex III.5 because the Annex III base
    # isn't represented. Article 5.1.f is still preserved (test intent).
    assert "Article 5.1.f" in refs
    # Optional: at most one injected leaf, capped at 2 per the F3 budget.
    assert len(refs) <= 3


# ── Regenold probe coverage — emotion recognition paraphrases ────────────


def test_emotion_recognition_hyphenated_form_matches():
    """Hyphenated form 'emotion-recognition' (no space) must also fire
    the Art. 5(1)(f) upgrade. Probe paraphrase p02/p05/p06 use this form."""
    refs = upgrade_references(
        question="Are all emotion-recognition AI systems banned by Article 5?",
        base_refs=["Article 5"],
    )
    assert "Article 5.1.f" in refs


def test_emotion_recognition_infer_emotions_paraphrase():
    """'infer customer emotions' paraphrase (probe p03) must fire."""
    refs = upgrade_references(
        question="We use biometric data to infer customer emotions.",
        base_refs=["Article 5"],
    )
    assert "Article 5.1.f" in refs


def test_emotion_recognition_also_emits_annex_iii_subpoint():
    """Regenold probe gold pairs Article 5.1.f with Annex III.5. When
    the engine surfaces Annex III as a base, the emitter must upgrade
    it to Annex III.5 on emotion-recognition questions."""
    refs = upgrade_references(
        question="Are AI systems intended for emotion recognition from biometric data always prohibited?",
        base_refs=["Article 5", "Annex III"],
    )
    assert "Article 5.1.f" in refs
    assert "Annex III.5" in refs


# ── Regenold probe coverage — doctor-patient transcription ───────────────


def test_doctor_patient_transcription_upgrades_annex_iii_to_5():
    """'doctor-patient' / 'transcribes' / 'transcription' must upgrade
    Annex III → Annex III.5 (essential services — healthcare overlap)."""
    refs = upgrade_references(
        question="Is an AI that transcribes doctor-patient conversations prohibited?",
        base_refs=["Annex III"],
    )
    assert "Annex III.5" in refs


def test_medical_consultation_transcription_paraphrase_matches():
    """Probe p03 paraphrase: 'AI transcription of medical consultations'."""
    refs = upgrade_references(
        question="Does the EU AI Act prohibit AI transcription of medical consultations?",
        base_refs=["Annex III"],
    )
    assert "Annex III.5" in refs


def test_ai_scribe_paraphrase_matches():
    """Probe p05 paraphrase: 'AI scribe for doctors'."""
    refs = upgrade_references(
        question="We deploy an AI scribe for doctors during patient consultations.",
        base_refs=["Annex III", "Article 6"],
    )
    assert "Annex III.5" in refs
    assert "Article 6.1" in refs


def test_physician_patient_dialogue_paraphrase_matches():
    """Probe p06 paraphrase: 'physician-patient dialogue'."""
    refs = upgrade_references(
        question="How does the AI Act classify an AI that transcribes physician-patient dialogue?",
        base_refs=["Article 6"],
    )
    assert "Article 6.1" in refs


def test_medical_record_paraphrase_matches():
    """Additional paraphrase: 'medical record' should also trigger the
    healthcare essential-services overlap mapping."""
    refs = upgrade_references(
        question="Is an AI that summarises a medical record subject to Annex III?",
        base_refs=["Annex III"],
    )
    assert "Annex III.5" in refs


# ── Regenold probe coverage — technical documentation hardware ───────────


def test_technical_doc_required_hardware_paraphrase():
    """Probe p01/p03/p07 say 'required hardware' / 'hardware ... required'.
    The expanded pattern must catch the inverted forms."""
    refs = upgrade_references(
        question="Is information about required hardware part of the technical documentation?",
        base_refs=["Annex IV", "Annex IV.2"],
    )
    assert any(r == "Annex IV.2.a" for r in refs)


def test_technical_doc_hardware_used_to_train_paraphrase():
    """Probe p05: 'describe the hardware used to train and run it'."""
    refs = upgrade_references(
        question="Do we have to describe the hardware used to train and run our AI system?",
        base_refs=["Annex IV"],
    )
    assert any(r == "Annex IV.2.a" for r in refs)


# ── No regression on davidath-style queries ──────────────────────────────


def test_davidath_workplace_emotion_scenario_still_works():
    """A davidath emotion scenario in workplace context must still pick
    up Article 5.1.f via the emotion-recognition pattern."""
    refs = upgrade_references(
        question="Run a call-centre monitoring tool that infers caller emotions.",
        base_refs=["Article 5", "Article 50"],
    )
    assert "Article 5.1.f" in refs
    assert "Article 50" in refs


def test_subpoint_topic_map_grew_for_doctor_transcription():
    """At least one entry references Annex III.5 and Article 6.1 together
    (the doctor-transcription mapping)."""
    from app.data.subpoint_emitter import SUBPOINT_TOPIC_MAP

    found = False
    for _, candidates in SUBPOINT_TOPIC_MAP:
        leaves = {leaf for leaf, _ in candidates}
        if "Annex III.5" in leaves and "Article 6.1" in leaves:
            found = True
            break
    assert found, "no entry pairs Annex III.5 with Article 6.1"

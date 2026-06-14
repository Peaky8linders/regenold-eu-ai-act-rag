"""R117-FOLLOWUP — de-overfit the medical-scribe vocab in scope.py.

The R116 ``KEYWORD_TO_ARTICLE`` block mapped a PURE transcription / scribe
tool (no diagnostic or decision function) to ``"Annex III"`` (high-risk).
That was overfit paraphrase-tuning of the protected doctor-patient PDF
example: a pure scribe is limited-risk, whose operative duty is the
Article 50 transparency obligation. It also contradicted the project's own
established decisions — ``subpoint_emitter.py`` maps the same phrases to
Article 6.1 ONLY, the engine keyword map dropped ``transcrib``→Annex III
(``test_classification_verdicts.py::test_transcribe_not_routed_to_annex_iii_via_keyword``),
and the MedTech scribe scenarios (``mv2_03`` / ``mv3_07``) carry gold
``["Article 50"]`` / "not high-risk".

R117 re-anchors the R116 block to ``"Art. 50"``. The pre-existing R39 block
(doctor-patient / medical-transcription phrasings used by the protected PDF
example, whose question is framed around Annex III) is intentionally LEFT at
``"Annex III"`` — hard rule #3.

davidath-safe by construction: these scribe phrases have 0 hits across
``qa_pairs.json`` + ``scenarios.json``, so the bench is byte-identical.
"""

from __future__ import annotations

from app.integrations.regenold.scope import KEYWORD_TO_ARTICLE


# The 14 R116 "vocab widening" phrases — all PURE scribe / transcription
# product descriptions with no diagnostic or decision function.
_R116_SCRIBE_PHRASES = (
    "ambient clinical documentation",
    "ambient voice documentation",
    "clinical documentation ai",
    "clinical note generation",
    "clinical note-taking",
    "clinical notes",
    "medical dictation",
    "clinical dictation",
    "medical scribe",
    "clinical scribe",
    "consultation transcription",
    "visit transcription",
    "clinical speech-to-text",
    "medical speech-to-text",
)

# The protected R39 doctor-patient-transcription PDF-example phrasings that
# MUST stay anchored to Annex III (the scenario asks "...high-risk as per
# the use cases of Annex III?" and must surface it).
_R39_PROTECTED_PHRASES = (
    "medical transcription",
    "doctor-patient",
    "physician-patient",
    "clinical conversation",
    "medical conversation",
    "patient consultation",
    "ai scribe",
    "medical record",
)


class TestR117ScribeReAnchor:
    """The R116 pure-scribe vocab now maps to Art. 50, not Annex III."""

    def test_r116_scribe_phrases_map_to_article_50(self) -> None:
        for phrase in _R116_SCRIBE_PHRASES:
            assert phrase in KEYWORD_TO_ARTICLE, (
                f"R116 scribe phrase {phrase!r} is missing from "
                f"KEYWORD_TO_ARTICLE."
            )
            assert KEYWORD_TO_ARTICLE[phrase] == "Art. 50", (
                f"R117 de-overfit regression — {phrase!r} should anchor "
                f"limited-risk Art. 50, got {KEYWORD_TO_ARTICLE[phrase]!r}."
            )

    def test_no_r116_scribe_phrase_asserts_annex_iii(self) -> None:
        offenders = [
            phrase
            for phrase in _R116_SCRIBE_PHRASES
            if KEYWORD_TO_ARTICLE.get(phrase) == "Annex III"
        ]
        assert not offenders, (
            "A pure-scribe phrase still asserts the (wrong) Annex III "
            f"high-risk tier: {offenders}"
        )


class TestR117ProtectedExamplePreserved:
    """The R39 doctor-patient PDF-example handling is untouched (hard rule #3)."""

    def test_r39_doctor_patient_phrases_still_annex_iii(self) -> None:
        for phrase in _R39_PROTECTED_PHRASES:
            assert phrase in KEYWORD_TO_ARTICLE, (
                f"Protected R39 phrase {phrase!r} is missing from "
                f"KEYWORD_TO_ARTICLE — the PDF-example handling must stay."
            )
            assert KEYWORD_TO_ARTICLE[phrase] == "Annex III", (
                f"Protected doctor-patient-transcription phrase {phrase!r} "
                f"must stay anchored to Annex III (hard rule #3), got "
                f"{KEYWORD_TO_ARTICLE[phrase]!r}."
            )

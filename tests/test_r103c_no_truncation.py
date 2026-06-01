"""R103c — the wire answer must NEVER end on a truncated/dangling fragment.

Two surfaces:
1. The R47-B graph-recital append (route) used to clip a recital's first
   sentence at 197 chars + "..." → dangling fragments like
   "…inferring emotions or intentions of natural persons on..." (Recital 18,
   anchored to Article 5). It now SKIPS over-long recitals instead.
2. `normalise_answer_for_regenold` gains a final backstop that drops a
   trailing ellipsis-clipped / punctuation-less sentence (source-agnostic).
"""
from __future__ import annotations

from app.integrations.regenold.models import normalise_answer_for_regenold


_GOOD = (
    "Transcribing doctor-patient conversations is not categorically "
    "prohibited under Article 5 nor listed in Annex III as a high-risk use "
    "case. It becomes high-risk under Article 6 only if deployed as a safety "
    "component of a medical device covered by Annex I. Otherwise Article 50 "
    "transparency obligations may apply when the system interacts with "
    "patients."
)


class TestFinalTruncationBackstop:
    def test_drops_trailing_ellipsis_clip(self) -> None:
        # The exact live failure shape: a good answer + a clipped recital.
        clipped = (
            _GOOD + " The notion of 'emotion recognition system' referred to "
            "in this Regulation should be defined as an AI system for the "
            "purpose of identifying or inferring emotions or intentions of "
            "natural persons on..."
        )
        out = normalise_answer_for_regenold(clipped, question="Is transcription prohibited?")
        assert not out.rstrip().endswith("..."), f"ellipsis fragment survived: {out!r}"
        assert not out.rstrip().endswith("…")
        # The complete sentences are preserved.
        assert "transparency obligations" in out
        # Ends on a complete sentence.
        assert out.rstrip()[-1] in ".!?"

    def test_drops_trailing_sentence_without_terminator(self) -> None:
        bad = (
            "Article 13 requires high-risk AI systems to be transparent. "
            "Providers must supply instructions for use covering the system's "
            "capabilities and limitations and the required hardware components "
            "and infrastructure on"
        )
        out = normalise_answer_for_regenold(bad, question="What does Article 13 require?")
        assert out.rstrip()[-1] in ".!?\"')]", f"answer ends mid-clause: {out!r}"
        assert "transparent" in out  # complete sentence kept

    def test_complete_answer_untouched(self) -> None:
        out = normalise_answer_for_regenold(_GOOD, question="Is transcription prohibited?")
        # All 3 complete sentences survive; nothing dropped.
        assert "Transcribing" in out
        assert "transparency obligations" in out
        assert out.rstrip().endswith(".")

    def test_never_empties_single_incomplete_sentence(self) -> None:
        # A lone incomplete sentence must NOT be dropped to empty (the
        # closed-world refusal path owns the empty case).
        out = normalise_answer_for_regenold("Article 5 prohibits", question="x")
        assert out.strip() != "", "backstop emptied a single-sentence answer"

    def test_complete_answer_with_trailing_paren(self) -> None:
        ok = "Article 13 requires transparency for high-risk AI systems (see Annex IV)."
        out = normalise_answer_for_regenold(ok, question="What does Article 13 require?")
        assert "Annex IV" in out
        assert out.rstrip().endswith(")") or out.rstrip().endswith(".")

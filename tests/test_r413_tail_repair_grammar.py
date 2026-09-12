"""R413 — the tail repair must produce ONE grammatical final sentence.

The R357 repair asked the model for the missing TAIL and concatenated it
(``enhanced + tail``). MEASURED defect on the R411 production deploy: nothing
checked that the two halves form one sentence, so it shipped a weld of two
finite clauses —

    "... duties it triggers are those in answering general patient queries on
     a hospital website is neither emergency triage nor ..."

R413 asks for the COMPLETE final sentence and accepts it only when it is one
sentence, continues the cut sentence, keeps its substance, and does not weld a
new clause onto a closed one. The wire effect is Stage-2-only by construction
(the deterministic path never reaches ``_guard_stage2_truncation``'s tail).

Rung 0 (added after the n=40 paired gate): when the cut sentence is ALREADY a
grammatical sentence wanting only its full stop, the repair is just that full
stop. The model is offered the echo and an echo is accepted only when it is
byte-identical to the cut sentence, so the repair cannot paraphrase a provision
away. The deterministic detector cannot tell a whole final word from one cut
mid-word ("...of a produc"), so it only decides whether the echo is OFFERED.
"""

from __future__ import annotations

import pytest

from app.engines.graph_rag import (
    _accept_reconstructed_final_sentence,
    _attempt_stage2_tail_repair,
    _fragment_terminates_cleanly,
    _join_tail_to_fragment,
    _looks_incomplete_final_sentence,
    _reconstruct_stage2_final_sentence,
    _split_sentences_text,
    _stage2_tail_repair_mode,
    _welds_new_clause,
)
from app.engines.graph_rag.models import GraphContext

#: The exact production weld (R411 live verification, hospital-chatbot ask).
CUT_FRAGMENT = (
    "The only EU AI Act transparency duties it triggers are those in answering "
    "general patient queries on a hospital website"
)
WELDED = CUT_FRAGMENT + " is neither emergency triage nor otherwise high-risk."
GRAMMATICAL = (
    CUT_FRAGMENT
    + ", and the system is neither emergency triage nor otherwise high-risk."
)


class TestSentenceSplitter:
    def test_does_not_split_abbreviations(self) -> None:
        # ``_last_sentence_of`` splits on any [.!?] + whitespace, so "Art. 9"
        # would invent a boundary; the repair path needs one that does not.
        assert _split_sentences_text("See Art. 9 for the duty. It applies now.") == [
            "See Art. 9 for the duty.",
            "It applies now.",
        ]

    def test_does_not_split_coordinate_lists(self) -> None:
        assert _split_sentences_text("Annex IV.1.e and Annex IV.2 apply.") == [
            "Annex IV.1.e and Annex IV.2 apply."
        ]

    def test_splits_real_sentence_ends(self) -> None:
        assert _split_sentences_text("One. Two! Three?") == [
            "One.",
            "Two!",
            "Three?",
        ]

    def test_keeps_a_trailing_fragment(self) -> None:
        assert _split_sentences_text(
            "It applies. The deployer must ensure that"
        ) == ["It applies.", "The deployer must ensure that"]

    def test_empty(self) -> None:
        assert _split_sentences_text("") == []
        assert _split_sentences_text("   ") == []


class TestWeldDetector:
    def test_fires_on_the_measured_production_weld(self) -> None:
        assert _welds_new_clause(WELDED, CUT_FRAGMENT) is True

    def test_does_not_fire_on_a_comma_joined_completion(self) -> None:
        assert _welds_new_clause(GRAMMATICAL, CUT_FRAGMENT) is False

    def test_does_not_fire_when_the_fragment_opens_a_clause(self) -> None:
        # "...and the provider" has no finite verb ⇒ a bare verb after it is a
        # continuation, not a new clause.
        assert (
            _welds_new_clause(
                "The deployer must retain the logs and the provider must assist.",
                "The deployer must retain the logs and the provider",
            )
            is False
        )

    def test_does_not_fire_on_an_open_connector(self) -> None:
        assert (
            _welds_new_clause(
                "The system is high-risk and is listed in Annex I.",
                "The system is high-risk and",
            )
            is False
        )


class TestAcceptReconstructedSentence:
    def test_accepts_one_complete_continuation(self) -> None:
        assert (
            _accept_reconstructed_final_sentence(GRAMMATICAL, CUT_FRAGMENT, "", WELDED)
            == GRAMMATICAL
        )

    def test_rejects_the_weld(self) -> None:
        assert _accept_reconstructed_final_sentence(WELDED, CUT_FRAGMENT, "", WELDED) is None

    def test_rejects_two_sentences(self) -> None:
        # A model that answers in two sentences re-answered instead of repairing.
        two = CUT_FRAGMENT + ". The provider must also comply with Article 26."
        assert _accept_reconstructed_final_sentence(two, CUT_FRAGMENT, "", WELDED) is None

    def test_rejects_a_topic_switch(self) -> None:
        other = "The provider must register the system in the EU database first."
        assert _accept_reconstructed_final_sentence(other, CUT_FRAGMENT, "", WELDED) is None

    def test_rejects_a_still_incomplete_reconstruction(self) -> None:
        cut = CUT_FRAGMENT + " and"
        assert _accept_reconstructed_final_sentence(cut, CUT_FRAGMENT, "", WELDED) is None

    def test_accepts_a_mid_word_completion(self) -> None:
        fragment = (
            "The system is high-risk under Article 6(1) where it is intended to "
            "be used as a safety component of a produc"
        )
        candidate = (
            "The system is high-risk under Article 6(1) where it is intended to "
            "be used as a safety component of a product."
        )
        assert (
            _accept_reconstructed_final_sentence(candidate, fragment, "", fragment)
            == candidate
        )

    def test_rejects_a_repeat_of_the_earlier_sentences(self) -> None:
        prefix = (
            "The system is a patient-facing chatbot. It is deployed on a "
            "hospital website. The provider must assess the risk tier."
        )
        candidate = (
            "It is deployed on a hospital website. The provider must assess the "
            "risk tier of the chatbot before launch."
        )
        assert _accept_reconstructed_final_sentence(candidate, CUT_FRAGMENT, prefix, prefix) is None

    def test_strips_a_fence(self) -> None:
        fenced = f"```\n{GRAMMATICAL}\n```"
        assert _accept_reconstructed_final_sentence(fenced, CUT_FRAGMENT, "", WELDED) == GRAMMATICAL

    def test_rejects_empty(self) -> None:
        assert _accept_reconstructed_final_sentence("", CUT_FRAGMENT, "", WELDED) is None
        assert _accept_reconstructed_final_sentence("   ", CUT_FRAGMENT, "", WELDED) is None
        assert _accept_reconstructed_final_sentence(None, CUT_FRAGMENT, "", WELDED) is None


class TestTerminateRung:
    """R413 rung 0 — an already-grammatical cut sentence is closed, not welded."""

    def test_detector_accepts_the_production_hospital_fragment(self) -> None:
        assert _fragment_terminates_cleanly(CUT_FRAGMENT) is True

    def test_detector_refuses_a_dangling_connector(self) -> None:
        # "... that drawing up are the" still needs its object.
        assert _fragment_terminates_cleanly(
            "The bodies charged with encouraging and facilitating that drawing "
            "up are the"
        ) is False

    def test_detector_refuses_a_verbless_noun_phrase(self) -> None:
        # rg_034's cut: no finite verb at all, so a full stop cannot close it.
        assert _fragment_terminates_cleanly(
            "Consequently, the specific legal authority and remedial actions "
            "available to the Court"
        ) is False

    def test_echo_hint_is_offered_only_for_a_terminable_fragment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []
        monkeypatch.setattr(
            "app.engines.graph_rag._stage2_complete",
            lambda **kw: seen.append(kw["user"]) or "x",
        )
        _reconstruct_stage2_final_sentence(
            question="q", enhanced=CUT_FRAGMENT, refs_block=""
        )
        _reconstruct_stage2_final_sentence(
            question="q",
            enhanced="The bodies charged with encouraging and facilitating that drawing up are the",
            refs_block="",
        )
        assert "CHECK THIS FIRST" in seen[0]
        assert "CHECK THIS FIRST" not in seen[1]

    MID_WORD_FRAGMENT = (
        "The system is classified as high-risk under Article 6(1) where it "
        "is intended to be used as a safety component of a produc"
    )

    def test_mid_word_fragment_is_completed_not_terminated(self) -> None:
        # The detector cannot see the truncation, so the mid-word rule lives in
        # the prompt ("if the last word is visibly cut off ... never echo it").
        # A model that obeys supplies the whole word:
        completed = (
            "The system is classified as high-risk under Article 6(1) where it "
            "is intended to be used as a safety component of a product."
        )
        assert (
            _accept_reconstructed_final_sentence(
                completed, self.MID_WORD_FRAGMENT, "", self.MID_WORD_FRAGMENT
            )
            == completed
        )

    def test_mid_word_residual_is_bounded_and_deliberate(self) -> None:
        # A model that DISOBEYS ships the cut word with a full stop. That is the
        # accepted residual: the echo is byte-identical to the text the wire
        # already had plus one character, so the failure mode is one broken
        # word, never a paraphrased provision. The prompt is the guard and the
        # n=40 paired gate is the measurement.
        assert (
            _accept_reconstructed_final_sentence(
                self.MID_WORD_FRAGMENT + ".",
                self.MID_WORD_FRAGMENT,
                "",
                self.MID_WORD_FRAGMENT,
            )
            == self.MID_WORD_FRAGMENT + "."
        )

    def test_hospital_weld_is_repaired_by_a_lossless_termination(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The R411 production defect: the tail must never start a new clause."""
        monkeypatch.setenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", "sentence")
        prefix = "Article 99 outlines the penalty regime."
        echoed = f"{prefix} {CUT_FRAGMENT}"
        calls: list[str] = []

        def stub(**kw):  # noqa: ANN003, ANN202
            calls.append(kw["user"])
            return f"{CUT_FRAGMENT}."

        monkeypatch.setattr("app.engines.graph_rag._stage2_complete", stub)
        out = _attempt_stage2_tail_repair(
            "q", echoed, "kg", GraphContext(question="q")
        )
        assert out == f"{echoed}."
        assert len(calls) == 1, "the echo is decided in the single reconstruction call"
        assert _looks_incomplete_final_sentence(out) is False
        assert _welds_new_clause(out, CUT_FRAGMENT) is False

    def test_termination_is_not_offered_in_splice_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The splice arm stays byte-for-byte R357; rung 0 is sentence-mode only.
        monkeypatch.setenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", "splice")
        seen: list[str] = []
        monkeypatch.setattr(
            "app.engines.graph_rag._stage2_complete",
            lambda **kw: seen.append(kw["user"]) or " is neither emergency triage nor high-risk.",
        )
        out = _attempt_stage2_tail_repair(
            "q", CUT_FRAGMENT, "kg", GraphContext(question="q")
        )
        assert len(seen) == 1
        assert "MISSING TAIL" in seen[0]
        assert "CHECK THIS FIRST" not in seen[0]
        assert out == CUT_FRAGMENT + " is neither emergency triage nor high-risk."


class TestTailJoinProtocol:
    """R413 — the tail join is decided by a marker, never by whitespace.

    The provider trims the completion, so R357's "lead the tail with a space at
    a word boundary" signal never reaches the splice. MEASURED live: the R411
    hospital probe shipped "... on a hospital websiteArticle 50(1), requiring
    that ...".
    """

    def test_gap_marker_inserts_one_space(self) -> None:
        text, boundary = _join_tail_to_fragment(
            "...on a hospital website", "GAP:Article 50(1) requires notice."
        )
        assert text == "...on a hospital website Article 50(1) requires notice."
        assert boundary == "word"

    def test_cont_marker_continues_the_word(self) -> None:
        text, boundary = _join_tail_to_fragment(
            "...a safety component of a produc", "CONT:t is high-risk."
        )
        assert text == "...a safety component of a product is high-risk."
        assert boundary == "mid-word"

    def test_markers_are_case_insensitive(self) -> None:
        text, _ = _join_tail_to_fragment("a b c", "cont:tinues here.")
        assert text == "a b ctinues here."

    def test_leading_whitespace_inside_the_tail_is_normalised(self) -> None:
        # The model may still add a space after the marker; the join must not
        # double it.
        text, _ = _join_tail_to_fragment("ends here", "GAP:  under Article 6.")
        assert text == "ends here under Article 6."

    def test_unmarked_tail_joins_on_a_word_boundary(self) -> None:
        text, boundary = _join_tail_to_fragment("ends here", "under Article 6.")
        assert text == "ends here under Article 6."
        assert boundary == "word"


class TestRepairEndToEnd:
    """``_attempt_stage2_tail_repair`` in sentence mode, provider stubbed."""

    @pytest.fixture(autouse=True)
    def _pin_sentence_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", "sentence")

    def _ctx(self) -> GraphContext:
        return GraphContext(question="q")

    def test_keeps_earlier_sentences_and_replaces_the_cut_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prefix = "The system is a patient-facing chatbot on a hospital website."
        monkeypatch.setattr(
            "app.engines.graph_rag._stage2_complete", lambda **kw: GRAMMATICAL
        )
        out = _attempt_stage2_tail_repair(
            "q", f"{prefix} {CUT_FRAGMENT}", "kg", self._ctx()
        )
        assert out == f"{prefix} {GRAMMATICAL}"
        assert _looks_incomplete_final_sentence(out) is False

    def test_weld_is_rejected_not_shipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def stub(**kw):  # noqa: ANN003, ANN202
            calls.append(kw.get("user", ""))
            return WELDED

        monkeypatch.setattr("app.engines.graph_rag._stage2_complete", stub)
        out = _attempt_stage2_tail_repair("q", CUT_FRAGMENT, "kg", self._ctx())
        assert out is None
        # Both rungs ran: the reconstruction was refused, then the splice was
        # refused too (a head-match test rejects a model that re-answered).
        assert len(calls) == 2
        assert "COMPLETE FINAL SENTENCE" in calls[0]
        assert "MISSING TAIL" in calls[1]

    def test_ladder_falls_back_to_the_splice_when_the_reconstruction_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R413 — a refused reconstruction must not drop to the Stage-1 answer.

        MEASURED on the n=40 paired gate: the 3 rows the validator refused were
        exactly the rows where the fallback shipped a deterministic answer the
        judge failed on every criterion, while the splice had recovered the
        operative provision from the same input.
        """
        calls: list[int] = []

        def stub(**kw):  # noqa: ANN003, ANN202
            calls.append(1)
            if len(calls) == 1:
                # A refused reconstruction: it opens with different words.
                return "The provider must register the system in the EU database."
            return " requires registration in the EU database under Article 49(2)."

        monkeypatch.setattr("app.engines.graph_rag._stage2_complete", stub)
        out = _attempt_stage2_tail_repair("q", CUT_FRAGMENT, "kg", self._ctx())
        assert len(calls) == 2
        assert out is not None
        assert out.endswith("under Article 49(2).")
        assert out.startswith(CUT_FRAGMENT)

    def test_mid_word_cut_is_completed_grammatically(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fragment = (
            "The system is classified as high-risk under Article 6(1) where it "
            "is intended to be used as a safety component of a produc"
        )
        sentence = (
            "The system is classified as high-risk under Article 6(1) where it "
            "is intended to be used as a safety component of a product."
        )
        monkeypatch.setattr(
            "app.engines.graph_rag._stage2_complete", lambda **kw: sentence
        )
        out = _attempt_stage2_tail_repair("q", fragment, "kg", self._ctx())
        assert out == sentence
        assert _looks_incomplete_final_sentence(out) is False

    def test_empty_provider_output_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.engines.graph_rag._stage2_complete", lambda **kw: "   ")
        assert _attempt_stage2_tail_repair("q", CUT_FRAGMENT, "kg", self._ctx()) is None

    def test_tiny_fragment_never_calls_the_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: list[bool] = []

        def fake(**kw):  # noqa: ARG001
            called.append(True)
            return GRAMMATICAL

        monkeypatch.setattr("app.engines.graph_rag._stage2_complete", fake)
        assert _attempt_stage2_tail_repair("q", "safety component", "kg", self._ctx()) is None
        assert not called


class TestModeFlag:
    def test_recognised_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for value in ("sentence", "SINGLE", "grammatical", "rewrite"):
            monkeypatch.setenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", value)
            assert _stage2_tail_repair_mode() == "sentence"

    def test_unknown_value_keeps_the_legacy_splice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Deny-list form: an operator typo must not silently change the wire.
        monkeypatch.setenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", "sentance")
        assert _stage2_tail_repair_mode() == "splice"

    def test_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", raising=False)
        # Ships default OFF until the paired truncation gate passes; the flip to
        # "sentence" lands with the gate reading in
        # docs/measurements/r413/CHECKPOINT.md ("splice" is the revert).
        assert _stage2_tail_repair_mode() == "splice"


class TestWiredIntoTheGuard:
    def test_guard_ships_the_reconstructed_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.engines.graph_rag import _guard_stage2_truncation

        monkeypatch.setenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", "sentence")
        monkeypatch.setattr(
            "app.engines.graph_rag._stage2_complete", lambda **kw: GRAMMATICAL
        )
        out, used = _guard_stage2_truncation(
            "q", CUT_FRAGMENT, "DETERMINISTIC_KG", GraphContext(question="q")
        )
        assert out == GRAMMATICAL
        assert used is True

    def test_complete_answer_is_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The "does not fire on passing rows" contract, at the unit level.
        from app.engines.graph_rag import _guard_stage2_truncation

        monkeypatch.setenv("REGENOLD_STAGE2_TAIL_REPAIR_MODE", "sentence")
        called: list[bool] = []
        monkeypatch.setattr(
            "app.engines.graph_rag._stage2_complete",
            lambda **kw: called.append(True) or "x",  # noqa: ARG005
        )
        text = "The system is high-risk under Article 6(1) read with Annex I."
        out, used = _guard_stage2_truncation(
            "q", text, "kg", GraphContext(question="q")
        )
        assert out == text
        assert used is True
        assert not called

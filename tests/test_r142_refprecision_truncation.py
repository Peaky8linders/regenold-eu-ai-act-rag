"""R142 — reference-precision (over-citation) + truncation (incomplete-verdict)
regression tests.

Two live-only defects surfaced by the R141 production eval round:

* OVER-CITATION — the R138 cite-consistency + R133 sub-point passes re-add
  prose-named refs UNCAPPED after the last budget cap, so a verbose Stage-2
  answer over-cites (q10 10 refs vs gold ~2). Fix: ``_final_ref_clamp`` re-applies
  ``_effective_max_refs`` as a final, scenario-exempt, stage2-gated clamp.
* TRUNCATION — the Claude-Max wrapper cuts the stream after an IRAC lead-in,
  leaving a period-terminated answer with the verdict unsaid ("…Applying that
  test to the facts."). The structural-truncation guard only checks terminal
  punctuation, so it ships. Fix: ``_looks_incomplete_verdict`` flags the
  promissory endings → deterministic Stage-1 fallback; ``_stage2_answer_headroom``
  widens the answer token envelope above the thinking budget.

Both are gated on the live Stage-2 path → the deterministic davidath bench
(provider=cli, no wrapper) is byte-identical (verified separately via
``evals.bench.runner --assert-baseline``).
"""
from __future__ import annotations

import pytest

from app.engines.graph_rag import (
    _looks_incomplete_verdict,
    _looks_structurally_truncated,
    _stage2_answer_headroom,
)
from app.routes.regenold import _final_ref_clamp


# ---------------------------------------------------------------------------
# Truncation — incomplete-verdict detector
# ---------------------------------------------------------------------------
class TestLooksIncompleteVerdict:
    @pytest.mark.parametrize(
        "text",
        [
            # (2) IRAC application clause with the conclusion missing — the q20
            # live symptom.
            "This follows from Article 6(1), which classifies a safety component "
            "as high-risk. Applying that test to the facts.",
            "Applying the test to the facts.",
            "Applying this analysis to the present case.",
            "Applying that criterion to the scenario.",
            # (3) bare promissory header — the med_8 live symptom.
            "The operative reasoning.",
            "The operative analysis.",
            "Key reasoning.",
            # (1) a promised continuation that never arrived.
            "The prohibited practices are the following:",
            "Article 5 bans eight categories:",
        ],
    )
    def test_fires_on_promissory_endings(self, text: str) -> None:
        assert _looks_incomplete_verdict(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            # Complete IRAC — the conclusion DID follow "to the facts".
            "Applying that test to the facts, the system is high-risk under "
            "Article 6(1).",
            # A complete operative-provision statement (names the provision).
            "The operative provision is Article 6(1) read with Annex I.",
            "The operative reasoning is that Article 6 applies.",
            # Ordinary complete answers.
            "Yes. The system is high-risk under Article 6(1) and Annex I.",
            "Deployers must follow Article 26: assign human oversight and retain "
            "logs.",
            "This question is covered by Article 50.",
            # Empty / whitespace handled upstream — not this guard's concern.
            "",
            "   ",
        ],
    )
    def test_does_not_fire_on_complete_answers(self, text: str) -> None:
        assert _looks_incomplete_verdict(text) is False

    def test_complements_structural_guard(self) -> None:
        # The dangling-fragment symptom ends in a period, so the STRUCTURAL
        # guard misses it — the incomplete-verdict guard is what catches it.
        symptom = (
            "This follows from Article 6(1)... Applying that test to the facts."
        )
        assert _looks_structurally_truncated(symptom) is False
        assert _looks_incomplete_verdict(symptom) is True

    def test_mid_word_cut_still_caught_by_structural(self) -> None:
        # A genuinely mid-word cut (no terminal punctuation) stays the
        # structural guard's job; the verdict guard need not fire.
        mid = "...intended to be used as a safety component of a produc"
        assert _looks_structurally_truncated(mid) is True


# ---------------------------------------------------------------------------
# Truncation — answer-token headroom helper
# ---------------------------------------------------------------------------
class TestStage2AnswerHeadroom:
    def test_default_is_1024(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_ANSWER_HEADROOM", raising=False)
        assert _stage2_answer_headroom() == 1024

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_ANSWER_HEADROOM", "2048")
        assert _stage2_answer_headroom() == 2048

    def test_clamped_low_and_high(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_ANSWER_HEADROOM", "10")
        assert _stage2_answer_headroom() == 256
        monkeypatch.setenv("REGENOLD_STAGE2_ANSWER_HEADROOM", "999999")
        assert _stage2_answer_headroom() == 8192

    def test_bad_value_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_ANSWER_HEADROOM", "lots")
        assert _stage2_answer_headroom() == 1024

    def test_doubles_simple_opus_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simple Opus path: thinking=1024. Old math: 1024+512=1536 → 512 answer
        # tokens. New: 1024+1024=2048 → 1024 answer tokens.
        monkeypatch.delenv("REGENOLD_STAGE2_ANSWER_HEADROOM", raising=False)
        eff_thinking = 1024
        safe = max(384, eff_thinking + _stage2_answer_headroom(), 1024)
        assert safe == 2048
        assert safe - eff_thinking == 1024  # answer envelope doubled vs 512


# ---------------------------------------------------------------------------
# Over-citation — final reference-budget clamp
# ---------------------------------------------------------------------------
_REFS_OVER = [f"Article {n}" for n in (3, 16, 26, 22, 23, 25, 11, 49, 50, 99)]


class TestFinalRefClamp:
    def _clamp(self, refs, monkeypatch, **kw):
        monkeypatch.delenv("REGENOLD_FINAL_REF_CLAMP", raising=False)
        defaults = dict(
            budget=3,
            stage2_landed=True,
            scenario_shape=False,
            retrieval_path="kb_fallback",
        )
        defaults.update(kw)
        return _final_ref_clamp(refs, **defaults)

    def test_clamps_qa_to_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = self._clamp(_REFS_OVER, monkeypatch, budget=3)
        assert out == ["Article 3", "Article 16", "Article 26"]

    def test_keeps_rank_order_head(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The clamp is positional — it keeps the highest-ranked head and drops
        # the R138-appended tail.
        out = self._clamp(_REFS_OVER, monkeypatch, budget=5)
        assert out == _REFS_OVER[:5]

    def test_scenario_shape_not_clamped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = self._clamp(_REFS_OVER, monkeypatch, budget=3, scenario_shape=True)
        assert out == _REFS_OVER

    def test_scenario_budget_respected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A real scenario passes scenario_shape=False but with a 10/22 budget;
        # the clamp respects whatever budget is handed in.
        out = self._clamp(_REFS_OVER, monkeypatch, budget=22)
        assert out == _REFS_OVER  # 10 <= 22 → unchanged

    def test_noop_without_stage2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # davidath byte-identity guard: stage2 never lands on the bench.
        out = self._clamp(_REFS_OVER, monkeypatch, budget=3, stage2_landed=False)
        assert out == _REFS_OVER

    def test_verbatim_and_no_match_exempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for path in ("verbatim_exact_text", "no_match"):
            out = self._clamp(_REFS_OVER, monkeypatch, budget=3, retrieval_path=path)
            assert out == _REFS_OVER

    def test_under_budget_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        short = ["Article 26", "Article 13"]
        out = self._clamp(short, monkeypatch, budget=3)
        assert out == short

    def test_env_off_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_FINAL_REF_CLAMP", "0")
        out = _final_ref_clamp(
            _REFS_OVER,
            budget=3,
            stage2_landed=True,
            scenario_shape=False,
            retrieval_path="kb_fallback",
        )
        assert out == _REFS_OVER

    def test_definitional_art3_survives_at_head(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # R130 upgrades the head bare Article 3 → Article 3.1 BEFORE the clamp,
        # so the definitional sub-point sits at position 0 and survives [:3].
        refs = ["Article 3.1", "Article 16", "Article 26", "Article 22", "Article 50"]
        out = self._clamp(refs, monkeypatch, budget=3)
        assert out[0] == "Article 3.1"
        assert "Article 3.1" in out

    def test_empty_refs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._clamp([], monkeypatch, budget=3) == []

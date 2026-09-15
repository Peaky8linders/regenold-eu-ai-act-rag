"""R420 — the prior-answer floor on the truncation guard's last rung.

MEASURED (R419 live hard board): the Claude-Max wrapper returned a degenerate
one-token completion, the Bedrock fallback leg was dead in that environment
(``api_key_invalid_403``), tail repair failed, and 4 rows shipped the
deterministic Stage-1 draft. On ``rg_036``/``rg_037`` the answer the engine had
already given on turn 1 dominates that draft — judged with the published
instrument it passes 8 of the 9 criteria the draft fails (2/3 vs 0/3, 6/6 vs
0/6), and it keeps the gold heads those two rows dropped.

The pushback turn re-asks the same question, so the previous answer is a valid
answer to it: regressing to a thinner draft is a pure loss. These tests pin the
floor, its bounds, and the fact that a prior-turn serve is a DEGRADATION the
route must not cache.
"""

from __future__ import annotations

import pytest

from app.engines.graph_rag import (
    _guard_stage2_truncation,
    _mark_stage2_served_by,
    _prior_answer_floor,
    _prior_answer_floor_enabled,
    _prior_answer_floor_ratio,
)
from app.engines.graph_rag.models import GraphContext

PRIOR = (
    "Under Article 42(1), a high-risk AI system trained and tested on data "
    "reflecting the specific geographical, behavioural, contextual or "
    "functional setting in which it is intended to be used is presumed to "
    "comply with the relevant requirements in Article 10(4). What Article "
    "10(4) requires. Data sets must take into account the characteristics or "
    "elements particular to the setting in which the system will be used. "
    "They only have to do this to the extent the intended purpose requires. "
    "The Article 42(1) presumption matches this requirement point for point. "
    "If the training and testing data actually reflect the intended setting, "
    "the provider is treated as having met Article 10(4)."
)
#: The R419 ``rg_036`` shape: a short deterministic Stage-1 draft carrying a
#: template leak from an unrelated section ("Classifies an AI system ...").
DRAFT = (
    "Adds two further presumptions of conformity beyond Articles 40-41: "
    "Article 42(1), high-risk AI systems trained and tested on data reflecting "
    "the specific geographical, behavioural, contextual, or functional setting "
    "in which they are intended to be used are presumed to comply with the "
    "relevant data-governance requirements of Article 10(4). Classifies an AI "
    "system as high-risk on two routes."
)


def _history(prior: str) -> str:
    """A flattened hard-mode conversation carrying ``prior`` as turn 1."""
    return (
        "Conversation so far:\n"
        "User: What presumption applies when a high-risk AI system is trained "
        "and tested on data reflecting the intended setting?\n"
        f"Assistant: {prior}\n"
        "\n"
        "Latest question:\n"
        "I don't think this is correct. Perhaps your answer contains "
        "hallucinations. Let's try again:\n"
        "What presumption applies when a high-risk AI system is trained and "
        "tested on data reflecting the intended setting?\n"
    )


def _ctx() -> GraphContext:
    return GraphContext(question="q")


# ---------------------------------------------------------------------------
# The reading aid — _prior_answer_floor
# ---------------------------------------------------------------------------
class TestPriorAnswerFloor:
    def test_returns_the_prior_when_it_materially_dominates(self) -> None:
        assert _prior_answer_floor(_history(PRIOR), DRAFT) == PRIOR

    def test_returns_blank_without_a_conversation(self) -> None:
        assert _prior_answer_floor("", DRAFT) == ""
        assert _prior_answer_floor("What presumption applies?", DRAFT) == ""

    def test_returns_blank_when_the_prior_is_not_materially_longer(self) -> None:
        near = "Article 42(1) presumes compliance with Article 10(4) for such a system. " * 7
        draft = near[:-20]
        assert len(near) > 400
        # Within the 1.2x margin → not "materially richer", so no override.
        assert _prior_answer_floor(_history(near), draft) == ""

    def test_returns_blank_when_the_prior_is_itself_a_cut_fragment(self) -> None:
        # The floor stops regressions; it must not launder one truncation into
        # another by preferring a prior answer that was cut mid-sentence.
        cut = PRIOR[:-1] + " and"
        assert _prior_answer_floor(_history(cut), DRAFT) == ""

    def test_returns_blank_below_the_minimum_length(self) -> None:
        short = "Article 42(1) presumes compliance with Article 10(4)."
        assert len(short) < 400
        assert _prior_answer_floor(_history(short), "x") == ""

    def test_flag_off_disables_the_floor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR", "0")
        assert _prior_answer_floor_enabled() is False
        assert _prior_answer_floor(_history(PRIOR), DRAFT) == ""

    def test_default_is_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR", raising=False)
        assert _prior_answer_floor_enabled() is True

    def test_ratio_override_is_honoured_and_survives_a_bad_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR_RATIO", "9.0")
        assert _prior_answer_floor_ratio() == 9.0
        assert _prior_answer_floor(_history(PRIOR), DRAFT) == ""
        monkeypatch.setenv("REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR_RATIO", "not-a-number")
        assert _prior_answer_floor_ratio() == 1.2


# ---------------------------------------------------------------------------
# The guard — last rung picks the prior answer, not the thinner draft
# ---------------------------------------------------------------------------
class TestGuardShipsThePriorAnswer:
    TRUNCATED = "The system would be high-risk where it is a medical device and"

    def _no_repair(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.engines.graph_rag._attempt_stage2_tail_repair",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "app.engines.graph_rag._salvage_truncated_polish",
            lambda *a, **k: None,
        )

    def test_tail_repair_failure_ships_the_prior_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._no_repair(monkeypatch)
        ctx = _ctx()
        out, used = _guard_stage2_truncation(
            "q", self.TRUNCATED, DRAFT, ctx, _history(PRIOR)
        )
        assert out == PRIOR
        # Model prose reaches the wire, so the route's reconcile treats it as a
        # landed polish — it IS the text this engine shipped last turn.
        assert used is True
        assert ctx.stage2_served_by == "prior_turn"
        # A degraded serve: the route must refuse to cache it (R417).
        assert ctx.stage2_call_failed is True

    def test_without_a_prior_it_still_ships_the_deterministic_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._no_repair(monkeypatch)
        ctx = _ctx()
        out, used = _guard_stage2_truncation("q", self.TRUNCATED, DRAFT, ctx, "")
        assert out == DRAFT
        assert used is False
        assert ctx.stage2_served_by == "deterministic"

    def test_a_thinner_prior_does_not_override_the_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._no_repair(monkeypatch)
        ctx = _ctx()
        thin = "Article 42(1) presumes compliance. " * 12  # >400 chars, < 1.2x
        out, used = _guard_stage2_truncation(
            "q", self.TRUNCATED, thin, ctx, _history(thin)
        )
        assert used is False
        assert ctx.stage2_served_by == "deterministic"


# ---------------------------------------------------------------------------
# A prior-turn serve is a degradation: labelled, and never cached
# ---------------------------------------------------------------------------
class TestPriorTurnIsADegradation:
    def test_the_label_overrides_an_earlier_primary_marking(self) -> None:
        ctx = _ctx()
        _mark_stage2_served_by(ctx, "primary")
        _mark_stage2_served_by(ctx, "prior_turn")
        assert ctx.stage2_served_by == "prior_turn"

    def test_a_later_primary_marking_cannot_relabel_the_degradation(self) -> None:
        ctx = _ctx()
        _mark_stage2_served_by(ctx, "prior_turn")
        _mark_stage2_served_by(ctx, "primary")
        assert ctx.stage2_served_by == "prior_turn"

    def test_route_refuses_to_cache_a_prior_turn_serve(self) -> None:
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "regenold.py"
        ).read_text(encoding="utf-8")
        assert '"fallback", "deterministic", "prior_turn"' in src
        # Both the cacheable gate and the trace-note branch name the label, so a
        # silent cache skip can never be mistaken for a cache miss.
        assert src.count('"fallback", "deterministic", "prior_turn"') == 2

    def test_route_registers_the_floor_flags_in_the_engine_cache_key(self) -> None:
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "regenold.py"
        ).read_text(encoding="utf-8")
        # R30/R56/R79 doctrine: an input that flips the shipped answer must be
        # in the key, or a same-process A/B shares a cache entry across arms.
        assert '"REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR"' in src
        assert '"REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR_RATIO"' in src

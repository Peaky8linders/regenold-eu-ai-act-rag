"""R282 — Article 6 <-> Annex III high-risk pair rescue in ``adaptive_ref_clamp``.

A strict REFINEMENT of the R281 clamp, **default OFF**, gated on its own env
(``REGENOLD_CLAMP_PAIR_RESCUE``) because it trades recall for precision: it
recovers a real gold pair (mt_v4_005 kept gold Article 6 but the R281 clamp
dropped gold Annex III) yet re-adds a NON-gold partner where the dropped member
was over-citation noise. That trade must clear a gold-bearing ``easyhard_ab``
A/B, not a blind flip. These tests pin:
  * the default-OFF flip (byte-identical to R281 when off),
  * the pair rescue itself (Article 6 kept -> Annex III rescued, and reverse),
  * the R281/R142.1 invariants carry over (never invents a ref, idempotent,
    stage2-gated, curated/verbatim exempt, floor, fail-soft),
  * the deliberate ABSENCE from the engine cache key (R79 — shared-cache A/B).
"""
from __future__ import annotations

import pytest

from app.routes.regenold import (
    _HIGH_RISK_PAIR,
    _clamp_pair_rescue_enabled,
    adaptive_ref_clamp,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_ADAPTIVE_REF_CLAMP", raising=False)
    monkeypatch.delenv("REGENOLD_CLAMP_PAIR_RESCUE", raising=False)
    monkeypatch.delenv("REGENOLD_REF_CLAMP_SCENARIO_BUDGET", raising=False)


def _clamp(refs, *, budget=3, is_scenario_budget=False, live_question="",
           stage2_landed=True, curated_intercept=False, retrieval_path="neo4j"):
    return adaptive_ref_clamp(
        refs,
        budget=budget,
        is_scenario_budget=is_scenario_budget,
        live_question=live_question,
        stage2_landed=stage2_landed,
        curated_intercept=curated_intercept,
        retrieval_path=retrieval_path,
    )


class TestGateDefaultOff:
    def test_disabled_by_default(self) -> None:
        # R282 ships default OFF — it needs its own gold-bearing A/B.
        assert _clamp_pair_rescue_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " on "])
    def test_truthy_values_enable(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", val)
        assert _clamp_pair_rescue_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_falsy_values_disable(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", val)
        assert _clamp_pair_rescue_enabled() is False

    def test_off_is_byte_identical_to_r281(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # With the parent clamp ON and pair-rescue OFF, the output must equal the
        # plain R281 clamp (this is the arm-A baseline the A/B compares against).
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "0")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III"]
        out = _clamp(refs, budget=3, live_question="Does the classification change?")
        assert out == ["Article 6", "Article 9", "Article 10"]  # Annex III dropped


class TestPairRescue:
    def test_mt_v4_005_annex_iii_rescued(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The motivating row: head keeps gold Article 6, budget dropped gold
        # Annex III into the tail. Pair rescue restores it.
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III"]
        out = _clamp(refs, budget=3, live_question="Does the classification change?")
        assert out == ["Article 6", "Article 9", "Article 10", "Annex III"]

    def test_reverse_article_6_rescued(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Symmetric: head keeps Annex III, tail has Article 6 -> rescue it.
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Annex III", "Article 9", "Article 10", "Article 6"]
        out = _clamp(refs, budget=3, live_question="Is it high-risk?")
        assert out == ["Annex III", "Article 9", "Article 10", "Article 6"]

    def test_subpoint_partner_rescued(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A tail Annex III sub-point is rescued when Article 6 is kept.
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III.3"]
        out = _clamp(refs, budget=3, live_question="Is it high-risk?")
        assert "Annex III.3" in out
        assert out[:3] == ["Article 6", "Article 9", "Article 10"]

    def test_partner_rescued_via_question_named_head(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Article 6 survives only via the question-named rescue (past budget);
        # its Annex III partner is still rescued because "kept" includes rescued.
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 9", "Article 10", "Article 13", "Article 6", "Annex III"]
        out = _clamp(refs, budget=3, live_question="What does Article 6 require?")
        assert "Article 6" in out and "Annex III" in out

    def test_no_rescue_when_partner_not_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Annex III in the tail but NO Article 6 anywhere kept -> not rescued.
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 9", "Article 10", "Article 13", "Annex III"]
        out = _clamp(refs, budget=3, live_question="What obligations apply?")
        assert out == ["Article 9", "Article 10", "Article 13"]

    def test_unrelated_articles_never_paired(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Only Article 6 <-> Annex III pair; e.g. Annex IV is never a partner.
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex IV", "Article 13"]
        out = _clamp(refs, budget=3, live_question="What obligations apply?")
        assert "Annex IV" not in out
        assert out == ["Article 6", "Article 9", "Article 10"]


class TestInvariantsCarryOver:
    def test_never_invents_a_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III"]
        out = _clamp(refs, budget=3, live_question="Is it high-risk?")
        assert set(out) <= set(refs)

    def test_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III", "Annex III.3"]
        once = _clamp(refs, budget=3, live_question="Is it high-risk?")
        twice = _clamp(once, budget=3, live_question="Is it high-risk?")
        assert once == twice

    def test_stage2_gate_still_holds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # stage2_landed False => whole clamp is a no-op even with pair-rescue ON.
        # This is the davidath / 276 / OOS byte-identical guarantee.
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III"]
        assert _clamp(refs, budget=3, stage2_landed=False) == refs

    def test_curated_intercept_exempt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III"]
        assert _clamp(refs, budget=3, curated_intercept=True) == refs

    def test_disabled_parent_clamp_no_rescue(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # If the parent clamp is OFF, pair-rescue never fires (early return).
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "0")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", "Article 9", "Article 10", "Annex III"]
        assert _clamp(refs, budget=3) == refs

    def test_fail_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        refs = ["Article 6", None, "Article 9", "Article 10", "Annex III"]  # type: ignore[list-item]
        out = _clamp(refs, budget=3)  # must not raise
        assert isinstance(out, list)


class TestPairMap:
    def test_pair_map_symmetric(self) -> None:
        assert _HIGH_RISK_PAIR["Article 6"] == "Annex III"
        assert _HIGH_RISK_PAIR["Annex III"] == "Article 6"
        # tight — no other pairs (broadening = more precision risk, unmeasured)
        assert set(_HIGH_RISK_PAIR) == {"Article 6", "Annex III"}


class TestCacheKeyDeliberatelyAbsent:
    def test_flag_absent_from_engine_cache_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.routes.regenold import _engine_cache_key

        monkeypatch.delenv("REGENOLD_CLAMP_PAIR_RESCUE", raising=False)
        off = _engine_cache_key("Is exam scoring high-risk?", None)
        monkeypatch.setenv("REGENOLD_CLAMP_PAIR_RESCUE", "1")
        on = _engine_cache_key("Is exam scoring high-risk?", None)
        assert off == on, (
            "REGENOLD_CLAMP_PAIR_RESCUE is a route post-process (R79) and must "
            "stay OUT of the engine cache key so the shared-cache A/B is valid."
        )

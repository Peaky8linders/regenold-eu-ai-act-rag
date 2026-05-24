"""R82-A — legacy correctness axes must byte-reproduce pre-R82 behaviour.

These tests pin the *_legacy functions against the pre-R82 shipped
formula. Run them every time _tokens_legacy is touched (it should
never be touched after R82-A merges).
"""
from __future__ import annotations

from evals.bench.metrics import (
    _tokens_legacy,
    answer_correctness_loose_legacy,
    answer_correctness_strict_legacy,
)


class TestLegacyLooseReproducesPreR82:
    def test_nbh_misses_in_legacy(self) -> None:
        # Pre-R82: NBH gold tokenises as 'high','risk'; ASCII pred is
        # 'high-risk'. They don't align.
        gold = "high‑risk system"
        pred = "high-risk system"
        # gold tokens (legacy): {'high', 'risk', 'system'}
        # pred tokens (legacy): {'high-risk', 'system'}
        # intersection: {'system'}; union 4 tokens; Jaccard = 1/4
        assert _tokens_legacy(gold) == {"high", "risk", "system"}
        assert _tokens_legacy(pred) == {"high-risk", "system"}
        assert answer_correctness_loose_legacy(pred, gold) == 0.25

    def test_ai_dropped_in_legacy_strict(self) -> None:
        # Pre-R82: 'AI' is < 3 chars → dropped from both sides.
        gold = "AI system"
        pred = "ai system"
        assert _tokens_legacy(gold) == {"system"}
        assert _tokens_legacy(pred) == {"system"}
        # Strict = recall = |intersection|/|gold| = 1/1 = 1.0
        assert answer_correctness_strict_legacy(pred, gold) == 1.0

    def test_modals_dropped_in_legacy(self) -> None:
        gold = "providers must document"
        pred = "providers must document"
        # 'must' is filtered as stopword in legacy
        assert _tokens_legacy(gold) == {"provid", "document"} - {"provid"} | {"providers", "document"}
        # Actually 'providers' (9 chars) isn't stemmed by legacy → 'providers'
        assert _tokens_legacy(gold) == {"providers", "document"}
        assert "must" not in _tokens_legacy(gold)

    def test_empty_inputs_in_legacy(self) -> None:
        assert answer_correctness_loose_legacy("", "") == 0.0
        assert answer_correctness_strict_legacy("", "") == 0.0

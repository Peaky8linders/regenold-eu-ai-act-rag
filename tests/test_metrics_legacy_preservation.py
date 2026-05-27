# tests/test_metrics_legacy_preservation.py
"""R82-A — legacy correctness axes must byte-reproduce pre-R82 behaviour."""
from __future__ import annotations

from evals.bench.metrics import (
    answer_correctness_loose_legacy,
    answer_correctness_strict_legacy,
)


class TestLegacyLooseReproducesPreR82:
    def test_nbh_misses_in_legacy(self) -> None:
        # Pre-R82: NBH → 'high','risk'; ASCII pred → 'high-risk'. They miss.
        gold = "high‑risk system"
        pred = "high-risk system"
        # gold tokens (legacy): {'high', 'risk', 'system'}
        # pred tokens (legacy): {'high-risk', 'system'}
        # intersection: {'system'}; union: {'high', 'risk', 'system', 'high-risk'}
        # Jaccard = 1/4 = 0.25
        assert answer_correctness_loose_legacy(pred, gold) == 0.25

    def test_ai_dropped_in_legacy_strict(self) -> None:
        # Pre-R82: 'AI' is < 3 chars → dropped.
        gold = "AI system"   # legacy tokens: {'system'} only
        pred = "ai system"   # legacy tokens: {'system'} only
        # Strict = recall = |intersection|/|gold| = 1/1 = 1.0
        assert answer_correctness_strict_legacy(pred, gold) == 1.0

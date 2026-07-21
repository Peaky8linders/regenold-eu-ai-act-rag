"""R285 — ``REGENOLD_ONE_PER_HEAD_CAP`` (default OFF) + ``_clamp_ref_head``.

The cap collapses a reference list to one citation per article/annex head. It
ships **default OFF** and must stay off until its own A/B clears it: it keeps
the FIRST ref per head, so on a parent-then-leaf list it drops the precise
sub-point — and regenold's own example gold is sub-point form
(``["Annex IV.2", "Article 3.1"]``), so it can drop GOLD. The local gold-scored
gate (``evals.harness.easyhard_ab``) scores at HEAD level and is therefore
structurally blind to that loss, which is exactly why these tests pin the
hazard explicitly rather than relying on a bench number.
"""
from __future__ import annotations

import pytest

from app.routes.regenold import (
    _clamp_ref_head,
    _one_per_head,
    _one_per_head_cap_enabled,
    adaptive_ref_clamp,
)

_CLAMP_KWARGS = dict(
    is_scenario_budget=False,
    live_question="Is this system high-risk?",
    stage2_landed=True,
    curated_intercept=False,
    retrieval_path="standard",
)


# ── _clamp_ref_head ────────────────────────────────────────────────────────


class TestClampRefHead:
    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            ("Article 50.1", "Article 50"),
            ("Article 113.3.a", "Article 113"),
            ("Article 6", "Article 6"),
            ("Annex IV.2.c", "Annex IV"),
            ("Annex III", "Annex III"),
            ("Annex I", "Annex I"),
            # Internal (engine-side) forms are accepted too.
            ("Art. 5", "Art. 5"),
            ("Art. 50.3", "Art. 50"),
        ],
    )
    def test_heads(self, ref: str, expected: str) -> None:
        assert _clamp_ref_head(ref) == expected

    def test_leading_whitespace_does_not_corrupt_the_head(self) -> None:
        """Regression: slicing the RAW ref with an offset measured on the
        stripped/lowered copy shifted by the whitespace width and emitted
        ``' Articlee 50'``."""
        assert _clamp_ref_head(" Article 50.1") == "Article 50"
        assert _clamp_ref_head("\tAnnex IV.2") == "Annex IV"

    def test_case_of_the_input_prefix_is_preserved(self) -> None:
        assert _clamp_ref_head("article 50.1") == "article 50"

    @pytest.mark.parametrize(
        "ref",
        [
            "",
            "Article ",
            "Annex",
            # Not a wire reference form (CLAUDE.md hard rule #1 allows only
            # ``Article N`` / ``Annex X``), so callers fall back to ``r.strip()``.
            "Recital 27",
            "something else",
        ],
    )
    def test_non_citations_return_none(self, ref: str) -> None:
        assert _clamp_ref_head(ref) is None


# ── _one_per_head ──────────────────────────────────────────────────────────


class TestOnePerHead:
    def test_keeps_first_per_head(self) -> None:
        assert _one_per_head(
            ["Article 6", "Article 6.3", "Annex III", "Annex III.1.c", "Article 50"]
        ) == ["Article 6", "Annex III", "Article 50"]

    def test_documents_the_gold_drop_hazard(self) -> None:
        """The reason this flag is default OFF: a leaf under an already-seen
        head is discarded, and the leaf can be the gold reference."""
        out = _one_per_head(["Annex IV", "Annex IV.2"])
        assert out == ["Annex IV"]
        assert "Annex IV.2" not in out

    def test_protected_heads_keep_every_member(self) -> None:
        out = _one_per_head(
            ["Article 6", "Article 6.3", "Annex III", "Annex III.1.c"],
            protect={"Article 6"},
        )
        assert out == ["Article 6", "Article 6.3", "Annex III"]

    def test_unrecognised_refs_key_on_themselves(self) -> None:
        assert _one_per_head(["Recital 27", "Recital 27", "Article 6.1"]) == [
            "Recital 27",
            "Article 6.1",
        ]


# ── the env gate ───────────────────────────────────────────────────────────


class TestGate:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_ONE_PER_HEAD_CAP", raising=False)
        assert _one_per_head_cap_enabled() is False

    @pytest.mark.parametrize("val", ["1", "on", "true", "yes", " TRUE "])
    def test_truthy_spellings(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", val)
        assert _one_per_head_cap_enabled() is True

    @pytest.mark.parametrize("val", ["0", "off", "false", "no", ""])
    def test_falsy_spellings(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", val)
        assert _one_per_head_cap_enabled() is False


# ── integration with adaptive_ref_clamp ────────────────────────────────────


class TestAdaptiveRefClampIntegration:
    def test_disabled_is_a_no_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", "0")
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        refs = ["Article 6.1", "Article 6.2", "Annex III.1", "Annex III.2"]
        assert adaptive_ref_clamp(refs, budget=10, **_CLAMP_KWARGS) == refs

    def test_does_not_fire_while_the_budget_has_room(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R285 — the cap is a way to get UNDER budget, not an unconditional
        filter. Shipped as-is it collapsed sub-points even with room to spare."""
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", "1")
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        refs = ["Article 6.1", "Article 6.2", "Annex III.1", "Annex III.2"]
        assert adaptive_ref_clamp(refs, budget=10, **_CLAMP_KWARGS) == refs

    def test_fires_only_when_over_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", "1")
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        refs = [
            "Article 6.1",
            "Article 6.2",
            "Annex III.1",
            "Annex III.2",
            "Article 50",
            "Article 50.1",
        ]
        out = adaptive_ref_clamp(refs, budget=3, **_CLAMP_KWARGS)
        assert out == ["Article 6.1", "Annex III.1", "Article 50"]

    def test_question_named_heads_survive_the_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", "1")
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        refs = [
            "Article 6",
            "Article 6.3",
            "Annex III",
            "Annex III.1",
            "Article 50",
            "Article 50.1",
        ]
        kwargs = dict(_CLAMP_KWARGS)
        kwargs["live_question"] = "Does Article 6 make this high-risk?"
        out = adaptive_ref_clamp(refs, budget=3, **kwargs)
        # Both Article 6 refs survive because the question named that head.
        assert "Article 6" in out and "Article 6.3" in out

    def test_skipped_when_stage2_did_not_land(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stage-2 gating is what makes davidath byte-identical."""
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", "1")
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        refs = ["Article 6.1", "Article 6.2"]
        kwargs = dict(_CLAMP_KWARGS)
        kwargs["stage2_landed"] = False
        assert adaptive_ref_clamp(refs, budget=1, **kwargs) == refs

    def test_skipped_for_curated_intercepts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_ONE_PER_HEAD_CAP", "1")
        monkeypatch.setenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")
        refs = ["Article 6.1", "Article 6.2"]
        kwargs = dict(_CLAMP_KWARGS)
        kwargs["curated_intercept"] = True
        assert adaptive_ref_clamp(refs, budget=1, **kwargs) == refs

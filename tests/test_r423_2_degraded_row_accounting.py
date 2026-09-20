"""R423.2 — a DEGRADED ROW must be excludable, not fatal to the whole gate.

MEASURED (R423, `r423-need4`, 37 rows x 3 generations x 2 arms, hard split):
arm B served every graded row from the primary leg. Arm A served 27 from the
primary, answered the same 9 curated intercepts as B, and shipped exactly ONE
Stage-1 draft — `rg_085`, after a primary read-timeout, a dead Bedrock
credential (`primary_failed=1`, `fallback_attempts=1`) and a Groq attempt the
strict-transport policy refused (`refused_by_provider={'groq': 1}`).

`assess` voided the run, so no delta was published at all. The void was RIGHT
about the condition and WRONG about the treatment: its own warning says "rows
that shipped a draft because of it belong in the excluded set, not averaged
over", and the gate's comparability filter had ALREADY dropped that row
symmetrically (`arm_A_not_primary[deterministic]`). One row out of 37 discarded
27 paired rows and five hours of quota.

These tests pin both halves: the exclusion is now ACCOUNTED (a refusal the
caller cannot account for still voids, and a large exclusion still voids), and
`degraded_row_ids` does NOT mistake the route's own curated intercepts for
degradation — folding those in would drop nine stable, byte-identical rows from
every pair.
"""

from __future__ import annotations

from typing import Any

from evals.harness import gate_validity


def _rows(*, primary: int, curated: int = 0, degraded: int = 0) -> list[dict[str, Any]]:
    """Graded rows in the three measured provenance shapes.

    ``curated``  — the route answered without a Stage-2 call at all: NO leg is
                   named and the row did not polish. Byte-identical across arms.
    ``degraded`` — a leg IS named and it is not the primary: the row shipped a
                   Stage-1 draft (or a fallback transport) after the primary
                   failed. This is the row the caller excludes.
    ``primary``  — the contracted tunnelled leg served it.
    """
    out: list[dict[str, Any]] = []
    for i in range(curated):
        out.append({
            "id": f"cur_{i:03d}",
            "provenance": {"stage2_polish": False, "stage2_served_by": "", "stage2_model": ""},
        })
    for i in range(degraded):
        out.append({
            "id": f"deg_{i:03d}",
            "provenance": {
                "stage2_polish": False,
                "stage2_served_by": "deterministic",
                "stage2_model": "claude-opus-5",
            },
        })
    for i in range(primary):
        out.append({
            "id": f"pri_{i:03d}",
            "provenance": {
                "stage2_polish": True,
                "stage2_served_by": "primary",
                "stage2_model": "claude-opus-5",
            },
        })
    return out


def _prov(
    label: str,
    rows: list[dict[str, Any]],
    *,
    ok: int,
    refused: int = 0,
    refused_by_provider: dict[str, int] | None = None,
    fallback_attempts: int = 0,
    primary_failed: int = 0,
) -> gate_validity.ArmProvenance:
    stats: dict[str, Any] = {
        "primary_attempts": ok + primary_failed,
        "primary_ok": ok,
        "primary_failed": primary_failed,
        "fallback_attempts": fallback_attempts,
        "fallback_ok": 0,
        "fallback_failed": fallback_attempts,
        "refused": refused,
        "refused_by_provider": dict(refused_by_provider or {}),
    }
    return gate_validity.ArmProvenance(
        label=label,
        rows=len(rows),
        deterministic_graded=gate_validity.count_deterministic_rows(rows),
        stats=stats,
        system_hashes=("aaa",),
        user_hashes=("uuu",),
        system_lengths=(3,),
        calls=ok,
        refused_by_provider=dict(refused_by_provider or {}),
        rows_served=gate_validity.count_rows_served_by(rows),
    )


def _need4() -> tuple[gate_validity.ArmProvenance, gate_validity.ArmProvenance]:
    """The measured R423 need4 shape: one degraded row on arm A only."""
    base = _prov(
        "r423-need4-A",
        _rows(primary=27, curated=9, degraded=1),
        ok=18,
        refused=1,
        refused_by_provider={"groq": 1},
        fallback_attempts=1,
        primary_failed=1,
    )
    branch = _prov("r423-need4-B", _rows(primary=28, curated=9), ok=19)
    return base, branch


class TestDegradedRowIds:
    def test_a_named_non_primary_leg_is_degraded(self) -> None:
        rows = _rows(primary=2, curated=1, degraded=1)
        assert gate_validity.degraded_row_ids(rows) == ["deg_000"]

    def test_a_curated_intercept_is_not_degraded(self) -> None:
        # No leg named + not polished = the route's own deterministic answer.
        # It is byte-identical in BOTH arms, so excluding it would drop a stable
        # row from every pair (9 of them in the R423 sample).
        rows = _rows(primary=3, curated=2)
        assert gate_validity.degraded_row_ids(rows) == []

    def test_primary_rows_are_not_degraded(self) -> None:
        assert gate_validity.degraded_row_ids(_rows(primary=5)) == []

    def test_a_fallback_served_row_is_degraded(self) -> None:
        rows = [{"id": "rg_009", "provenance": {
            "stage2_polish": True, "stage2_served_by": "fallback", "stage2_model": "qwen3",
        }}]
        assert gate_validity.degraded_row_ids(rows) == ["rg_009"]

    def test_junk_and_empty_do_not_raise(self) -> None:
        assert gate_validity.degraded_row_ids([]) == []
        assert gate_validity.degraded_row_ids(None) == []
        assert gate_validity.degraded_row_ids([None, 3, "x", {"id": "a"}]) == []


class TestVerdictIsReproducibleFromItsArtifact:
    """A guard change must not cost another five hours of live draws."""

    def test_round_trip_preserves_every_verdict_input(self) -> None:
        base, branch = _need4()
        before = gate_validity.assess(
            base=base, branch=branch, lever=(False, "prompt lever")
        )
        again = gate_validity.assess(
            base=gate_validity.ArmProvenance.from_dict(base.as_dict()),
            branch=gate_validity.ArmProvenance.from_dict(branch.as_dict()),
            lever=(False, "prompt lever"),
        )
        assert again.as_dict() == before.as_dict()

    def test_round_trip_keeps_the_payload_digests(self) -> None:
        arm = _prov("arm", _rows(primary=4), ok=4)
        rebuilt = gate_validity.ArmProvenance.from_dict(arm.as_dict())
        assert rebuilt.system_digest == arm.system_digest
        assert rebuilt.user_digest == arm.user_digest
        assert arm.system_digest  # non-empty, or the identity rule is vacuous

    def test_a_recorded_run_can_be_re_judged_with_the_accounting(self) -> None:
        base, branch = _need4()
        verdict = gate_validity.assess(
            base=gate_validity.ArmProvenance.from_dict(base.as_dict()),
            branch=gate_validity.ArmProvenance.from_dict(branch.as_dict()),
            lever=(False, "prompt lever"),
            excluded_rows=1,
        )
        assert verdict.valid is True, verdict.reasons


class TestAccountedExclusion:
    def test_the_r423_need4_shape_voids_without_the_accounting(self) -> None:
        base, branch = _need4()
        verdict = gate_validity.assess(
            base=base, branch=branch, lever=(False, "prompt lever")
        )
        assert verdict.valid is False
        joined = " ".join(verdict.reasons)
        assert "refused by the transport policy" in joined
        assert "asymmetric fallback pressure" in joined

    def test_one_excluded_row_accounts_for_the_run(self) -> None:
        base, branch = _need4()
        verdict = gate_validity.assess(
            base=base, branch=branch, lever=(False, "prompt lever"), excluded_rows=1
        )
        assert verdict.valid is True, verdict.reasons
        assert any("excluded from BOTH arms" in w for w in verdict.warnings)

    def test_an_unaccounted_refusal_still_voids(self) -> None:
        # Two refusals, one excluded row: the second has no explanation, so the
        # run cannot be read as a lever result.
        base, branch = _need4()
        base = _prov(
            "r423-need4-A",
            _rows(primary=27, curated=9, degraded=1),
            ok=18,
            refused=2,
            refused_by_provider={"groq": 2},
            fallback_attempts=2,
            primary_failed=2,
        )
        verdict = gate_validity.assess(
            base=base, branch=branch, lever=(False, "prompt lever"), excluded_rows=1
        )
        assert verdict.valid is False
        assert any("refused by the transport policy" in r for r in verdict.reasons)

    def test_a_widespread_degradation_cannot_be_excluded_away(self) -> None:
        # 10 of 37 is more than a quarter: that is an outage, not a hiccup.
        # curated=0 keeps the deterministic MAJORITY rule quiet, so the cap is
        # what refuses the run rather than the older arm-level rule.
        base = _prov(
            "r423-need4-A",
            _rows(primary=27, degraded=10),
            ok=18,
            refused=10,
            refused_by_provider={"groq": 10},
            fallback_attempts=10,
            primary_failed=10,
        )
        branch = _prov("r423-need4-B", _rows(primary=37), ok=19)
        verdict = gate_validity.assess(
            base=base, branch=branch, lever=(False, "prompt lever"), excluded_rows=10
        )
        assert verdict.valid is False
        assert any("more than a quarter" in r for r in verdict.reasons)

    def test_the_default_is_unchanged(self) -> None:
        # No caller that omits the argument can change behaviour.
        base, branch = _need4()
        for kwargs in ({}, {"excluded_rows": 0}, {"ignore_fallback_leg": False}):
            verdict = gate_validity.assess(
                base=base, branch=branch, lever=(False, "prompt lever"), **kwargs
            )
            assert verdict.valid is False
            assert verdict.reasons, kwargs

    def test_exclusion_does_not_disable_the_majority_rules(self) -> None:
        # The arm-level determinism majority must survive the new accounting.
        base = _prov(
            "r423-need4-A",
            _rows(primary=5, curated=5, degraded=27),
            ok=5,
            refused=1,
            refused_by_provider={"groq": 1},
            fallback_attempts=1,
            primary_failed=27,
        )
        branch = _prov("r423-need4-B", _rows(primary=32, curated=5), ok=19)
        verdict = gate_validity.assess(
            base=base, branch=branch, lever=(False, "prompt lever"), excluded_rows=1
        )
        assert verdict.valid is False
        assert any("deterministic Stage-1 drafts" in r for r in verdict.reasons)

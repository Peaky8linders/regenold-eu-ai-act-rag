"""R413 — a void paired gate must refuse to report deltas.

MEASURED (R412): a complete 95+95 paired run for
``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`` printed a plausible null — no
speedup on any axis — and was VOID. Its log carried 189
``bedrock_auto_fallback`` lines: the tunnel was down, Bedrock served both arms,
and Bedrock always receives the full system prompt, so the arms dispatched
identical bytes. A void delta and a real null delta are the same shape, so the
harness now has to prove the run could measure the lever before it reports one.
"""

from __future__ import annotations

import json

import pytest

from evals.harness import easyhard_ab, gate_validity


def _prov(
    label: str,
    *,
    rows: int = 10,
    primary_ok: int = 10,
    fallback_ok: int = 0,
    refused: int = 0,
    system: tuple[str, ...] = ("aaa",),
    user: tuple[str, ...] = ("uuu",),
    error: str | None = None,
) -> gate_validity.ArmProvenance:
    stats: dict = {
        "primary_attempts": primary_ok + fallback_ok,
        "primary_ok": primary_ok,
        "primary_failed": 0,
        "fallback_attempts": fallback_ok,
        "fallback_ok": fallback_ok,
        "fallback_failed": 0,
        "refused": refused,
    }
    if error:
        stats["_error"] = error
    return gate_validity.ArmProvenance(
        label=label,
        rows=rows,
        stats=stats,
        system_hashes=system,
        user_hashes=user,
        system_lengths=tuple(len(h) for h in system),
        calls=len(system),
    )


class TestTransportVoid:
    def test_fallback_served_arm_is_void(self) -> None:
        # The exact R412 shape: tunnel down, Bedrock carried the arm.
        verdict = gate_validity.assess(
            base=_prov("baseline", fallback_ok=10, primary_ok=0),
            branch=_prov("branch", fallback_ok=10, primary_ok=0),
            lever=(True, "test"),
        )
        assert verdict.valid is False
        assert sum("FALLBACK" in r for r in verdict.reasons) == 2

    def test_fallback_on_one_arm_is_enough(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline"),
            branch=_prov("branch", fallback_ok=3, primary_ok=7),
            lever=(True, "test"),
        )
        assert verdict.valid is False
        assert any("branch was served by the FALLBACK" in r for r in verdict.reasons)

    def test_clean_primary_run_is_valid(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", system=("aaa",)),
            branch=_prov("branch", system=("bbb",)),
            lever=(True, "system-slot lever"),
        )
        assert verdict.valid is True
        assert verdict.system_checked is True
        assert verdict.reasons == []

    def test_refused_transport_is_void(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", refused=2),
            branch=_prov("branch"),
            lever=False,
        )
        assert verdict.valid is False
        assert any("refused" in r for r in verdict.reasons)

    def test_no_stage2_landing_is_void(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", primary_ok=0, rows=12),
            branch=None,
            lever=False,
        )
        assert verdict.valid is False
        assert any("ZERO Stage-2 completions" in r for r in verdict.reasons)

    def test_unreadable_stats_is_void_not_clean(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", error="reset_transport_stats() failed: OSError"),
            branch=None,
            lever=False,
        )
        assert verdict.valid is False
        assert any("provenance unavailable" in r for r in verdict.reasons)


class TestSystemPayloadIdentity:
    def test_identical_system_payloads_void_a_system_lever(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", system=("deadbeef",)),
            branch=_prov("branch", system=("deadbeef",)),
            lever=(True, "arm env differs on system-slot flag(s): REGENOLD_STAGE2_FULL_SYSTEM"),
        )
        assert verdict.valid is False
        assert any("IDENTICAL" in r for r in verdict.reasons)

    def test_different_system_payloads_pass(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", system=("aaa",)),
            branch=_prov("branch", system=("bbb",)),
            lever=(True, "system-slot lever"),
        )
        assert verdict.valid is True

    def test_unobservable_payloads_void_a_system_lever(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", system=()),
            branch=_prov("branch", system=()),
            lever=(True, "system-slot lever"),
        )
        assert verdict.valid is False
        assert any("could not be observed" in r for r in verdict.reasons)

    def test_identical_payloads_are_only_a_warning_for_a_non_system_lever(self) -> None:
        # A retrieval / reference-shaping lever legitimately shares system bytes.
        verdict = gate_validity.assess(
            base=_prov("baseline", system=("same",)),
            branch=_prov("branch", system=("same",)),
            lever=(False, "arm env does not name a known system-slot flag"),
        )
        assert verdict.valid is True
        assert any("same system payload" in w for w in verdict.warnings)

    def test_different_counts_still_void_when_digests_match(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", system=("aaaa",)),
            branch=_prov("branch", system=("aaaa",)),
            lever=(True, "system-slot lever"),
        )
        assert verdict.valid is False


class TestLeverDeclaration:
    def test_system_slot_flag_in_the_arm_diff_arms_the_check(self) -> None:
        changes, why = gate_validity.lever_changes_system(
            {"REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN": "0"},
            {"REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN": "1"},
        )
        assert changes is True
        assert "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN" in why

    def test_unset_vs_set_counts_as_a_diff(self) -> None:
        changes, _ = gate_validity.lever_changes_system(
            {}, {"REGENOLD_STAGE2_FULL_SYSTEM": "1"}
        )
        assert changes is True

    def test_non_system_flag_does_not_arm_the_check(self) -> None:
        changes, _ = gate_validity.lever_changes_system(
            {"REGENOLD_REF_GRAIN_DEEPEN": "0"}, {"REGENOLD_REF_GRAIN_DEEPEN": "1"}
        )
        assert changes is False

    def test_identical_arm_envs_do_not_arm_the_check(self) -> None:
        changes, _ = gate_validity.lever_changes_system({}, {})
        assert changes is False

    def test_operator_override_wins(self) -> None:
        changes, why = gate_validity.lever_changes_system({}, {}, override=True)
        assert changes is True and "override" in why
        changes, why = gate_validity.lever_changes_system(
            {"REGENOLD_STAGE2_FULL_SYSTEM": "0"},
            {"REGENOLD_STAGE2_FULL_SYSTEM": "1"},
            override=False,
        )
        assert changes is False and "override" in why


class _FakeProvider:
    """Stands in for the pooled wrapper / Bedrock provider singleton."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def complete(self, request):  # noqa: ANN001, ANN201
        self.seen.append(getattr(request, "user", ""))
        return "ok"


class TestArmProbe:
    def _patch_providers(self, monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeProvider, _FakeProvider]:
        from app.llm import bedrock_client, openai_wrapper_provider

        wrapper, bedrock = _FakeProvider(), _FakeProvider()
        monkeypatch.setattr(
            openai_wrapper_provider, "get_openai_wrapper_provider", lambda: wrapper
        )
        monkeypatch.setattr(bedrock_client, "get_bedrock_provider", lambda: bedrock)
        return wrapper, bedrock

    def test_records_the_payload_the_model_receives(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import types

        wrapper, bedrock = self._patch_providers(monkeypatch)

        with gate_validity.ArmProbe("baseline") as probe:
            wrapper.complete(
                types.SimpleNamespace(
                    system="PERSONA", user="EU AI ACT REFERENCES:\nq1"
                )
            )
            bedrock.complete(
                types.SimpleNamespace(system="", user="EU AI ACT REFERENCES:\nq2")
            )
            # An auxiliary call (no Stage-2 answer marker) must not be counted as
            # a graded payload.
            wrapper.complete(types.SimpleNamespace(system="OTHER", user="parse this"))

        prov = probe.provenance(rows=[1, 2])
        assert prov.rows == 2
        assert prov.calls == 2  # the auxiliary call was filtered out
        assert prov.system_hashes == (gate_validity._sha("PERSONA"), gate_validity._sha(""))
        # The provider hooks are restored, not left wrapped.
        assert wrapper.complete.__func__ is _FakeProvider.complete  # type: ignore[attr-defined]
        assert bedrock.complete.__func__ is _FakeProvider.complete  # type: ignore[attr-defined]

    def test_filter_fallback_records_everything_rather_than_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import types

        wrapper, _ = self._patch_providers(monkeypatch)
        with gate_validity.ArmProbe("baseline") as probe:
            wrapper.complete(types.SimpleNamespace(system="S", user="no marker here"))
        prov = probe.provenance(rows=[1])
        assert prov.calls == 1
        assert prov.system_hashes == (gate_validity._sha("S"),)

    def test_arm_provenance_exposes_the_transport_leg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_providers(monkeypatch)
        with gate_validity.ArmProbe("baseline") as probe:
            pass
        prov = probe.provenance(rows=[])
        assert prov.primary_ok == 0 and prov.fallback_ok == 0
        assert "system_digest" in prov.as_dict()

    def test_unobservable_provider_is_reported_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm import openai_wrapper_provider

        def boom():
            raise RuntimeError("provider unavailable")

        monkeypatch.setattr(openai_wrapper_provider, "get_openai_wrapper_provider", boom)
        with gate_validity.ArmProbe("baseline") as probe:
            pass
        prov = probe.provenance(rows=[1])
        assert prov.stats_error and "not observable" in prov.stats_error
        assert any("provenance unavailable" in r for r in gate_validity.assess(
            base=prov, branch=None, lever=False).reasons)


class TestHarnessRefusal:
    def test_paired_report_withholds_deltas_on_a_void_run(self, capsys) -> None:
        paired = {
            "easy": {
                "n": 3,
                "baseline": {"ref_loose": 0.5},
                "branch": {"ref_loose": 0.5},
                "uplift_pp": 0.0,
            }
        }
        easyhard_ab._report_paired(
            "r413", paired, ("baseline was served by the FALLBACK transport",)
        )
        out = capsys.readouterr().out
        assert "PAIRED DELTAS WITHHELD" in out
        assert "VOID" in out
        assert "ref_loose" not in out  # no axis table, no zero-delta null

    def test_paired_report_prints_deltas_when_clean(self, capsys) -> None:
        paired = {
            "easy": {
                "n": 2,
                "baseline": {"ref_loose": 0.5, "ref_strict": 0.5, "ref_conc": 0.5,
                             "tone": 1.0, "kw_recall": 1.0, "pred_gold_ratio": 1.0,
                             "gold_dropped_head": 0, "gold_dropped_head_gold_count": 1},
                "branch": {"ref_loose": 0.6, "ref_strict": 0.6, "ref_conc": 0.6,
                           "tone": 1.0, "kw_recall": 1.0, "pred_gold_ratio": 1.0,
                           "gold_dropped_head": 0, "gold_dropped_head_gold_count": 1},
                "uplift_pp": 0.1,
            }
        }
        easyhard_ab._report_paired("r413", paired, ())
        out = capsys.readouterr().out
        assert "PAIRED" in out and "ref_loose" in out
        assert "VOID" not in out

    def test_merged_transport_stats_sums_arms(self) -> None:
        merged = easyhard_ab._merged_transport_stats(
            _prov("baseline", primary_ok=5, fallback_ok=1),
            _prov("branch", primary_ok=4, fallback_ok=2),
        )
        assert merged["primary_ok"] == 9
        assert merged["fallback_ok"] == 3

    def test_liveness_reads_the_merged_snapshot(self) -> None:
        live, note = easyhard_ab._transport_liveness(
            local=True,
            stats={"primary_ok": 9, "fallback_ok": 3},
        )
        assert live is True and "primary_ok=9" in note

    def test_liveness_reports_no_landing(self) -> None:
        live, note = easyhard_ab._transport_liveness(
            local=True, stats={"primary_ok": 0, "fallback_ok": 0}
        )
        assert live is False and "no live Stage-2 completions" in note


class TestVerdictRendering:
    def test_void_render_names_the_reasons_and_the_fix(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline", fallback_ok=10, primary_ok=0),
            branch=_prov("branch", fallback_ok=10, primary_ok=0),
            lever=(True, "x"),
        )
        text = verdict.render()
        assert "VOID RUN" in text
        assert "NO DELTAS ARE REPORTED" in text
        assert "FALLBACK" in text

    def test_verdict_serialises_for_the_sidecar(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline"), branch=_prov("branch"), lever=(False, "x")
        )
        blob = json.dumps(verdict.as_dict())
        assert '"void": false' in blob
        assert "baseline" in blob and "branch" in blob

    def test_valid_render_says_so(self) -> None:
        verdict = gate_validity.assess(
            base=_prov("baseline"), branch=_prov("branch"), lever=(False, "x")
        )
        assert "GATE VALID" in verdict.render()

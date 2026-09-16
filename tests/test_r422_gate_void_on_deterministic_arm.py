"""R422 — a delta against a Stage-1-draft arm must be VOID, and samples must be representative.

MEASURED (R422, `/tmp/r422_gate.log`, artifact
`evals/bench/results/official-r422-skel.json`): a paired 19-row hard run for
``REGENOLD_CLOSED_SET_SKELETON`` reported ``answer_chars +560.9`` and
``stage2_landed_rate +0.5789``. The branch arm was healthy; the BASELINE arm ran
while the wrapper answered 500 (``No response from Claude Code``) and Bedrock's
fallback answered ``api_key_invalid_403`` on all five models, so 13 of its 19
rows shipped a deterministic Stage-1 draft. The "+560-char skeleton effect" was
transport recovery.

The transport counters did not catch it — they count COMPLETIONS, and a
deterministic fallback still produces an answer, just not a Stage-2 one. What
does catch it is each graded row's own provenance, which is why
``count_deterministic_rows`` exists. And because a 19-row run of the first 19
questions is 13 easy / 6 hard while the board is 46% easy, ``--stride`` exists
so a small sample is drawn across the send order instead of off its front.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from evals.harness import gate_validity

REPO = Path(__file__).resolve().parents[1]


def _rows(n: int, *, deterministic: int, legacy: int = 0, served: str = "primary") -> list[dict]:
    """Graded rows with real provenance shape (see the R419 checkpoint)."""
    out: list[dict] = []
    for i in range(n):
        if i < deterministic:
            prov = {
                "stage2_polish": False,
                "stage2_served_by": "deterministic",
                "stage2_model": "claude-opus-5",
            }
        elif i < deterministic + legacy:
            # A checkpoint written BEFORE `stage2_served_by` existed.
            prov = {"stage2_polish": False}
        else:
            prov = {"stage2_polish": True, "stage2_served_by": served, "stage2_model": served}
        out.append({"id": f"rg_{i:03d}", "provenance": prov})
    return out


def _prov(label: str, rows: list[dict], *, ok: int) -> gate_validity.ArmProvenance:
    stats = {
        "primary_attempts": ok,
        "primary_ok": ok,
        "primary_failed": 0,
        "fallback_attempts": 0,
        "fallback_ok": 0,
        "fallback_failed": 0,
        "refused": 0,
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
    )


class TestDeterministicRowCounting:
    def test_reads_the_explicit_provenance_field(self) -> None:
        rows = _rows(10, deterministic=4)
        assert gate_validity.count_deterministic_rows(rows) == 4

    def test_counts_a_checkpoint_written_before_the_field_existed(self) -> None:
        # `stage2_served_by` absent + `stage2_polish` False is the legacy shape.
        rows = _rows(10, deterministic=0, legacy=3)
        assert gate_validity.count_deterministic_rows(rows) == 3

    def test_an_unknown_is_not_an_outage(self) -> None:
        # Rows with NEITHER field (an older checkpoint) must count as 0: a
        # missing field is not evidence that Stage-2 failed.
        assert gate_validity.count_deterministic_rows([{"id": "rg_001"}, {"id": "rg_002"}]) == 0
        assert gate_validity.count_deterministic_rows([]) == 0
        assert gate_validity.count_deterministic_rows(None) == 0

    def test_junk_rows_do_not_raise(self) -> None:
        assert gate_validity.count_deterministic_rows([None, 3, "x", {"id": "a"}]) == 0


class TestDeterministicArmIsVoid:
    def test_the_r422_incident_shape_is_refused(self) -> None:
        # 13 of 19 baseline rows were deterministic drafts; the arm still shows
        # healthy counters (nothing "failed"), which is the whole point.
        base = _prov("baseline", _rows(19, deterministic=13), ok=6)
        branch = _prov("branch", _rows(19, deterministic=0), ok=19)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "retrieval lever"))
        assert verdict.valid is False
        assert any("deterministic Stage-1 drafts" in r for r in verdict.reasons)

    def test_a_mostly_polished_arm_still_passes(self) -> None:
        base = _prov("baseline", _rows(20, deterministic=4), ok=16)
        branch = _prov("branch", _rows(20, deterministic=0), ok=20)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "retrieval lever"))
        assert verdict.valid is True
        assert verdict.reasons == []

    def test_exactly_half_is_not_enough_to_void(self) -> None:
        # The rule is STRICTLY more than half, so an even split is not voided;
        # the conservative direction is to refuse only a majority.
        base = _prov("baseline", _rows(10, deterministic=5), ok=5)
        branch = _prov("branch", _rows(10, deterministic=0), ok=10)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "lever"))
        assert verdict.valid is True

    def test_the_either_arm_rule_holds(self) -> None:
        base = _prov("baseline", _rows(10, deterministic=0), ok=10)
        branch = _prov("branch", _rows(10, deterministic=8), ok=2)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "lever"))
        assert verdict.valid is False

    def test_provenance_reports_both_halves(self) -> None:
        arm = _prov("baseline", _rows(10, deterministic=3), ok=7)
        payload = arm.as_dict()
        assert payload["deterministic_graded"] == 3
        assert payload["polished_graded"] == 7


class TestTheRunnerRefusesToPublish:
    """The guard only matters if the runner calls it BEFORE printing a delta."""

    def test_runner_assesses_and_marks_void(self) -> None:
        src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
        assert "from evals.harness.gate_validity import ArmProbe, assess, lever_changes_system" in src
        assert "verdict = assess(base=base_prov, branch=branch_prov, lever=lever)" in src
        # A refused modality must not fall through to the delta printer.
        assert 'payload["void"] = payload.get("void", []) + [m]' in src
        guard = src.index("verdict = assess(")
        delta = src.index('print(f"\\n=== DELTA {m} (baseline -> branch) ===")')
        window = src[guard:delta]
        # The refusal must be the LAST thing before the delta is skipped: mark the
        # modality void, then `continue` past the delta printer.
        void_at = window.index('payload["void"] = payload.get("void", []) + [m]')
        assert window.index("if not verdict.valid:") < void_at
        assert "continue" in window[void_at:]
        # ...and the delta printer must only run when it was NOT refused.
        assert "if not verdict.valid:" in window[: void_at]

    def test_runner_wraps_each_arm_in_a_probe(self) -> None:
        src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
        assert re.search(r"with ArmProbe\(", src)
        assert "provenance = probe.provenance(rows=got)" in src


class TestScoreArmCarriesTheLeg:
    """Dropping provenance in `load_ckpt` is why the R419 report could not name the
    transport-degraded rows: a degraded answer grades like any other."""

    def test_load_ckpt_carries_provenance(self, tmp_path: Path) -> None:
        from evals.official import score_arm as SA

        ckpt = tmp_path / "ckpt.jsonl"
        ckpt.write_text(
            "\n".join(
                json.dumps(
                    {
                        "id": "rg_001",
                        "question": "q",
                        "pred_answer": "a",
                        "pred_refs": ["Article 6"],
                        "provenance": {
                            "stage2_polish": False,
                            "stage2_served_by": "deterministic",
                        },
                    }
                )
                for _ in range(1)
            ),
            encoding="utf-8",
        )
        rows = SA.load_ckpt(ckpt)
        assert rows[0]["provenance"]["stage2_served_by"] == "deterministic"
        assert gate_validity.count_deterministic_rows(rows) == 1

    def test_a_ckpt_without_provenance_is_zero_not_an_error(self, tmp_path: Path) -> None:
        from evals.official import score_arm as SA

        ckpt = tmp_path / "old.jsonl"
        ckpt.write_text(
            json.dumps({"id": "rg_002", "question": "q", "pred_answer": "a"}),
            encoding="utf-8",
        )
        rows = SA.load_ckpt(ckpt)
        assert rows[0]["provenance"] == {}
        assert gate_validity.count_deterministic_rows(rows) == 0


class TestStrideSampling:
    def test_stride_precedes_limit(self) -> None:
        # `--stride` must be applied BEFORE `--limit`, or every Nth of the first M
        # is just the first M/(N) questions again.
        src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
        strategy = src.index("rows = rows[:: args.stride]")
        limit = src.index("rows = rows[: args.limit]")
        assert strategy < limit

    def test_stride_recovers_the_board_mix_that_a_prefix_loses(self) -> None:
        from evals.regenold.official_batch import load_official_batch

        rows = list(load_official_batch())

        def easy_share(sel: list) -> float:
            return sum(1 for r in sel if r.difficulty.upper().startswith("E")) / len(sel)

        board = easy_share(rows)
        prefix = easy_share(rows[:40])
        strided = easy_share(rows[::6])
        # The board is a near-even split; a 40-row prefix is not; stride 6 is close.
        assert 0.40 <= board <= 0.55
        assert prefix > board + 0.10
        assert abs(strided - board) < abs(prefix - board)

    def test_stride_rejects_zero(self) -> None:
        src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
        assert 'raise SystemExit("--stride must be >= 1")' in src

"""R423 — a "repeat" must be a NEW draw, and a failed fallback dial must be visible.

WHY THIS FILE EXISTS (two measured defects, one gate run)
--------------------------------------------------------
``--repeats K`` was added in R423 so a length/shape lever could be measured
across generations rather than off a single draw: the judged axes move by a
criterion or two, and R419 found rows whose credited criteria are
draw-dependent. The first hard gate (37 rows x 3 generations x 2 arms) then
produced this, read straight off the checkpoints:

    arm B  generations 2 and 3 were BYTE-IDENTICAL to generation 1 on 23 of 37
           rows, at p50 latency 1.6 s against generation 1's 43.6 s, and the arm
           made 73 provider calls across three generations of 74 asks each.

The route answers from ``app.routes.regenold._ENGINE_CACHE``, keyed on
(question, context, history depth, env). Every generation of a row sends the
same key, so generations 2..K never dialled a provider — they replayed
generation 1. A median over duplicated values reports a draw-to-draw stability
the run never measured, which is the same failure shape R422 shipped (a void run
read as a null). Hence: the runner clears the response cache before every
sample, and the gate VOIDs an arm whose generations are mostly identical.

Second defect, same run: the verdict said nothing about arm A's transport while
arm A dialled the Bedrock fallback leg **20 times and served 0 answers from it**
(the credential answers ``api_key_invalid_403``). ``fallback_ok`` is 0 in that
shape, so an arm whose tunnel failed and whose fallback is dead reads exactly
like an arm that never needed either. The counters that can see it are
``fallback_attempts`` / ``primary_failed``, and the payload recorder now
attributes system payloads per LEG — that is how the full 53 kB system prompt
gets pinned to the leg that carried it instead of being merged into one
histogram.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from evals.harness import gate_validity
from evals.regenold import run_official_batch as ROB

REPO = Path(__file__).resolve().parents[1]


def _prov(
    label: str,
    *,
    rows: int = 20,
    deterministic: int = 4,
    primary_ok: int = 16,
    primary_failed: int = 0,
    fallback_attempts: int = 0,
    fallback_ok: int = 0,
    refused: int = 0,
    refused_by_provider: dict[str, int] | None = None,
    legs: dict[str, int] | None = None,
    repeats: int = 1,
    identical_rate: float | None = None,
    sample_deterministic: tuple[int, ...] = (),
    rows_served: dict[str, int] | None = None,
) -> gate_validity.ArmProvenance:
    stats = {
        "primary_attempts": primary_ok + primary_failed,
        "primary_ok": primary_ok,
        "primary_failed": primary_failed,
        "fallback_attempts": fallback_attempts,
        "fallback_ok": fallback_ok,
        "fallback_failed": fallback_attempts,
        "refused": refused,
        "refused_by_provider": dict(refused_by_provider or {}),
    }
    return gate_validity.ArmProvenance(
        label=label,
        rows=rows,
        deterministic_graded=deterministic,
        stats=stats,
        system_hashes=("aaa",),
        user_hashes=("uuu",),
        system_lengths=(61,),
        calls=primary_ok,
        refused_by_provider=dict(refused_by_provider or {}),
        legs=dict(legs or {}),
        leg_system_lengths={},
        repeats=repeats,
        repeat_identical_rate=identical_rate,
        sample_deterministic=sample_deterministic,
        rows_served=dict(rows_served or {}),
    )


class TestADegradedSampleVoidsTheArm:
    """R423 — an arm-level total can hide a generation that shipped drafts.

    Measured on the R423 outage run (`official-r423-need2-*`), read from the
    checkpoints' own provenance, n=37 per generation:

        arm A  sample 1  primary=28  deterministic=0
               sample 2  primary=19  deterministic=9
               sample 3  primary=0   deterministic=28
        arm B  sample 1..3  primary=0  deterministic=28

    Arm A read HEALTHY at arm level (47 primary completions, deterministic_graded
    counted from sample 1 only = 0) while its third generation was entirely
    deterministic — and every number this gate publishes is a per-row MEDIAN
    across the generations. So the arm-level check cannot see it; the per-sample
    one can.
    """

    def test_a_majority_deterministic_generation_voids_the_gate(self) -> None:
        base = _prov(
            "A",
            rows=37,
            deterministic=0,
            primary_ok=47,
            repeats=3,
            sample_deterministic=(0, 9, 28),
        )
        branch = _prov("B", rows=37, deterministic=28, primary_ok=0, repeats=3)
        verdict = gate_validity.assess(base=base, branch=branch)
        assert not verdict.valid
        assert any(
            "generation 3 of 3" in reason and "deterministic Stage-1 drafts" in reason
            for reason in verdict.reasons
        ), verdict.reasons

    def test_a_healthy_run_is_not_voided_by_the_new_rule(self) -> None:
        base = _prov(
            "A",
            rows=37,
            deterministic=0,
            primary_ok=37,
            repeats=3,
            sample_deterministic=(0, 0, 2),
        )
        branch = _prov(
            "B",
            rows=37,
            deterministic=0,
            primary_ok=37,
            repeats=3,
            sample_deterministic=(1, 0, 3),
        )
        verdict = gate_validity.assess(base=base, branch=branch)
        assert verdict.valid, verdict.reasons

    def test_single_sample_runs_carry_no_per_sample_claim(self) -> None:
        base = _prov("A", rows=20, deterministic=0, primary_ok=20)
        assert base.sample_deterministic == ()
        assert base.as_dict()["sample_deterministic"] == []

    def test_the_runner_measures_determinism_per_sample(self) -> None:
        src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(
            encoding="utf-8"
        )
        assert "sample_rows=replicates" in src


class TestResponseCacheIsClearedBetweenGenerations:
    def test_it_empties_the_route_cache(self) -> None:
        from app.routes.regenold import _ENGINE_CACHE

        _ENGINE_CACHE.put("r423-probe-key", {"cached": True})
        cleared, error = ROB._clear_engine_cache()
        assert error is None
        assert cleared >= 1
        assert _ENGINE_CACHE.get("r423-probe-key") is None

    def test_an_unreachable_cache_is_reported_not_raised(self, monkeypatch) -> None:
        import builtins

        real_import = builtins.__import__

        def explode(name: str, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            if name == "app.routes.regenold":
                raise ImportError("no route module here")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", explode)
        cleared, error = ROB._clear_engine_cache()
        assert cleared == 0
        assert error and "_ENGINE_CACHE unreachable" in error

    def test_the_runner_clears_it_inside_the_sample_loop(self) -> None:
        src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
        loop = src.index("for k in range(repeats):")
        clear = src.index("cleared, cache_error = _clear_engine_cache()")
        # R423.3 split the dispatch into an easy and a hard call site, so assert
        # the CONTRACT — every sample dispatch comes after the clear — rather
        # than one call's literal formatting.
        dispatches = [
            i for i in range(len(src))
            if src.startswith("fresh = runner(", i)
        ]
        assert dispatches, "the runner must still dispatch per sample"
        assert loop < clear < min(dispatches), (
            "the cache must be cleared before each sample runs"
        )


class TestRepeatIndependence:
    def test_one_generation_has_nothing_to_compare(self) -> None:
        assert ROB._repeat_independence([[{"id": "a", "pred_answer": "x"}]]) is None

    def test_identical_generations_read_as_one(self) -> None:
        a = [{"id": "a", "pred_answer": "same"}, {"id": "b", "pred_answer": "same"}]
        assert ROB._repeat_independence([a, list(a)]) == 1.0

    def test_fresh_draws_read_as_zero(self) -> None:
        a = [{"id": "a", "pred_answer": "one"}]
        b = [{"id": "a", "pred_answer": "two"}]
        assert ROB._repeat_independence([a, b]) == 0.0

    def test_the_worst_pair_is_reported(self) -> None:
        # Generation 2 replayed generation 1; generation 3 was fresh. The
        # percentage that matters is the maximum, because a run is only as
        # independent as its most-replayed pair.
        a = [{"id": "a", "pred_answer": "one"}]
        b = [{"id": "a", "pred_answer": "one"}]
        c = [{"id": "a", "pred_answer": "three"}]
        assert ROB._repeat_independence([a, b, c]) == 1.0

    def test_missing_rows_do_not_divide_by_zero(self) -> None:
        a = [{"id": "a", "pred_answer": "one"}]
        assert ROB._repeat_independence([a, [{"id": "z", "pred_answer": "x"}]]) is None


class TestReplayedGenerationsAreVoid:
    def test_a_majority_identical_arm_is_refused(self) -> None:
        base = _prov("baseline", repeats=3, identical_rate=0.62)
        branch = _prov("branch", repeats=3, identical_rate=0.62)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert verdict.valid is False
        assert any("REPLAYS" in r for r in verdict.reasons)

    def test_the_curated_intercept_floor_is_tolerated(self) -> None:
        # Deterministic intercepts are identical by design: 24% of the official
        # hard split. A minority-identical pair is not evidence of replay.
        base = _prov("baseline", repeats=3, identical_rate=0.24)
        branch = _prov("branch", repeats=3, identical_rate=0.30)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert verdict.valid is True

    def test_a_single_generation_run_is_unaffected(self) -> None:
        base = _prov("baseline", repeats=1, identical_rate=None)
        branch = _prov("branch", repeats=1, identical_rate=None)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert verdict.valid is True


class TestFailedFallbackDialsAreVisible:
    def test_asymmetric_fallback_pressure_voids_the_pair(self) -> None:
        # The R423 hard gate: arm A dialled the fallback 20 times and served 0,
        # arm B never needed it. Same lever, different transport.
        base = _prov("baseline", fallback_attempts=20, primary_failed=6)
        branch = _prov("branch", fallback_attempts=0)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert verdict.valid is False
        assert any("asymmetric fallback pressure" in r for r in verdict.reasons)

    def test_symmetric_fallback_pressure_warns_but_does_not_void(self) -> None:
        base = _prov("baseline", fallback_attempts=20, primary_failed=6)
        branch = _prov("branch", fallback_attempts=20, primary_failed=6)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert verdict.valid is True
        assert any("answered 0" in w for w in verdict.warnings)

    def test_a_served_fallback_still_voids(self) -> None:
        base = _prov("baseline", fallback_attempts=3, fallback_ok=3)
        branch = _prov("branch", fallback_attempts=0)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert verdict.valid is False
        assert any("FALLBACK transport" in r for r in verdict.reasons)

    def test_the_attempt_counts_are_published(self) -> None:
        arm = _prov("baseline", fallback_attempts=20, primary_failed=6, primary_ok=107)
        payload = arm.as_dict()
        assert payload["fallback_attempts"] == 20
        assert payload["primary_failed"] == 6


class TestRefusalsNameTheProvider:
    def test_the_reason_names_what_was_refused(self) -> None:
        # "off-contract provider attempted" was an unattributed narration: the
        # counter already knows WHICH provider, which is the difference between
        # a Groq/Gemini escape hatch being reached and the wrapper's own base URL
        # being misconfigured (that one refuses every single call).
        base = _prov("baseline", refused=3, refused_by_provider={"groq": 3})
        branch = _prov("branch", refused=0)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert verdict.valid is False
        reason = next(r for r in verdict.reasons if "refused" in r)
        assert "groq×3" in reason

    def test_an_unnamed_refusal_says_so(self) -> None:
        base = _prov("baseline", refused=1, refused_by_provider={})
        branch = _prov("branch", refused=0)
        verdict = gate_validity.assess(base=base, branch=branch, lever=(False, "shape lever"))
        assert any("provider not named" in r for r in verdict.reasons)


class TestLegAttribution:
    def test_payload_recorder_attributes_the_full_prompt_to_a_leg(self) -> None:
        recorder = gate_validity._PayloadRecorder()
        recorder._record("primary", "persona" * 10, "EU AI ACT REFERENCES: x")
        recorder._record("fallback", "X" * 59644, "EU AI ACT REFERENCES: x")
        assert recorder.legs == {"primary": 1, "fallback": 1}
        assert recorder.leg_lengths["fallback"] == [59644]
        assert recorder.leg_lengths["primary"] == [70]


class TestTheRunnerCLIParses:
    def test_help_renders(self) -> None:
        # argparse interpolates `%` in help strings; a bare percent in the
        # --stride text used to take the whole module's CLI down.
        proc = subprocess.run(
            [sys.executable, "-m", "evals.regenold.run_official_batch", "--help"],
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=180,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        assert "--repeats" in proc.stdout

    def test_the_repeats_help_promises_independence_and_the_runner_delivers_it(self) -> None:
        src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
        assert re.search(r"independent generations per row PER ARM", src, re.IGNORECASE)
        assert "identical_rate > 0.5" in src, "the runner must warn on a replayed generation"


class TestAResumedArmIsNotVoided:
    """A `--resume` re-launch restarts the counters, not the evidence.

    Transport provenance is counted by the running process, so an arm whose
    generations are already on disk when the process starts reads
    `primary_ok=0, fallback_ok=0, calls=0` while grading 37 perfectly good rows.
    The R422 zero-completion rule then VOIDed the arm on a re-run — the third
    hard gate was 2.5 of 3 hours in when the machine restarted, so the choice
    was to void it or to re-draw ~1.5 h of live provider calls. The graded rows
    already record which leg served them (`provenance.stage2_served_by`), which
    is the same evidence the other provenance rules read, so the rule now
    accepts it.
    """

    def test_rows_that_name_the_primary_leg_satisfy_the_zero_rule(self) -> None:
        base = _prov(
            "A", rows=37, deterministic=0, primary_ok=0,
            rows_served={"primary": 37}, repeats=3, sample_deterministic=(0, 0, 0),
        )
        branch = _prov(
            "B", rows=37, deterministic=0, primary_ok=0,
            rows_served={"primary": 37}, repeats=3, sample_deterministic=(0, 0, 0),
        )
        verdict = gate_validity.assess(base=base, branch=branch)
        assert verdict.valid, verdict.reasons

    def test_the_zero_rule_still_fires_with_no_evidence_anywhere(self) -> None:
        base = _prov(
            "A", rows=37, deterministic=37, primary_ok=0,
            rows_served={"deterministic": 37},
        )
        branch = _prov("B", rows=37, deterministic=37, primary_ok=0,
                       rows_served={"deterministic": 37})
        verdict = gate_validity.assess(base=base, branch=branch)
        assert not verdict.valid
        assert any("ZERO Stage-2 completions" in r for r in verdict.reasons)

    def test_a_row_naming_the_fallback_leg_still_voids(self) -> None:
        base = _prov("A", rows=37, deterministic=0, primary_ok=0,
                     rows_served={"fallback": 37})
        branch = _prov("B", rows=37, deterministic=0, primary_ok=37,
                       rows_served={"primary": 37})
        verdict = gate_validity.assess(base=base, branch=branch)
        assert not verdict.valid
        assert any("FALLBACK transport" in r for r in verdict.reasons)

    def test_the_counter_reads_the_leg_off_the_row(self) -> None:
        rows = [
            {"provenance": {"stage2_served_by": "primary"}},
            {"provenance": {"stage2_served_by": "primary"}},
            {"provenance": {"stage2_served_by": "deterministic"}},
            {"provenance": {"stage2_polish": True}},   # written before R418
            {"provenance": {}},
            {},
        ]
        assert gate_validity.count_rows_served_by(rows) == {
            "primary": 3,
            "deterministic": 1,
            "unnamed": 2,
        }


class _Row:
    """The minimum a row needs for the easy path, so the arm can run offline."""

    def __init__(self, i: int) -> None:
        self.id = f"rg_{i:03d}"
        self.question = f"question {i}"
        self.difficulty = "EASY"
        self.difficulty_category = "single-turn"
        self.jul07_answer = "a reference answer"
        self.jul07_refs = ["Article 3"]

    def easy_messages(self) -> list[dict[str, str]]:
        return [{"role": "user", "content": self.question}]


def _arm_offline(
    tmp_path: Path,
    monkeypatch,
    *,
    rows: list[_Row],
    calls: list[str],
    resume: bool,
    repeats: int = 3,
) -> dict:
    monkeypatch.setattr(ROB, "_RESULTS", tmp_path)
    monkeypatch.setattr(ROB, "_clear_engine_cache", lambda: (0, None))

    def poster(_url, _key, msgs, _timeout):
        question = msgs[0]["content"]
        calls.append(question)
        body = {"answer": f"answer to {question}", "references": ["Article 3"]}
        return body, 1000, 200, None, 1, None

    return ROB._arm(
        "tt",
        "easy",
        rows,
        poster=poster,
        url="local://probe",
        api_key=None,
        timeout=1.0,
        arm_env={},
        suffix="-A",
        resume=resume,
        repeats=repeats,
    )


def test_a_restart_resumes_finished_replica_generations(
    tmp_path: Path, monkeypatch
) -> None:
    """A restart must not discard a replica's completed generations.

    Measured: the third hard gate was 2.5 of 3 hours in when the machine
    restarted — arm A held all three generations and arm B held one full plus
    15 rows of the second. Re-launching with `--resume` used to restart the
    replicas from scratch, because resume was gated on `k == 0` (the primary
    sample), so a re-run re-drew ~1.5 h of live provider calls that were already
    on disk. The validator is per FILE and a replica file holds each row id
    exactly once, so the repeated-id check that catches a truncated checkpoint
    is unaffected by resuming one.
    """
    rows = [_Row(i) for i in range(1, 5)]

    first: list[str] = []
    _arm_offline(tmp_path, monkeypatch, rows=rows, calls=first, resume=False)
    assert len(first) == 12, "3 generations x 4 rows"
    for k in (0, 1, 2):
        name = (
            "official-tt-A-easy.ckpt.jsonl"
            if k == 0
            else f"official-tt-A-easy.r{k}.ckpt.jsonl"
        )
        assert len((tmp_path / name).read_text(encoding="utf-8").splitlines()) == 4

    # Half of generation 2 was lost, as it was on the real restart.
    replica = tmp_path / "official-tt-A-easy.r1.ckpt.jsonl"
    replica.write_text(
        "\n".join(replica.read_text(encoding="utf-8").splitlines()[:2]) + "\n",
        encoding="utf-8",
    )

    second: list[str] = []
    arm = _arm_offline(tmp_path, monkeypatch, rows=rows, calls=second, resume=True)

    assert len(second) == 2, f"only the two missing rows may be re-drawn: {second}"
    assert set(second) == {"question 3", "question 4"}
    # Every generation is graded, and the resumed arm still holds all 4 rows in
    # each of the 3 generations.
    assert set(arm["easy"]["samples"][0]) == {r.id for r in rows}
    assert len(arm["easy"]["samples"][1]) == 4
    assert len(arm["easy"]["samples"][2]) == 4
    assert len((replica).read_text(encoding="utf-8").splitlines()) == 4


# ── R423.1 — a regression screen must be AIMABLE at the rows a gate lost ────
#
# The first gate put the whole correctness cost of the need-proportional lever on
# two rows, and a stride reaches a named row only by luck (rg_010/rg_106 sat in
# the stride-3 sample here, but nothing guarantees that of the next one). Without
# a targeted selection the only way to test a fix for those rows is to re-run the
# whole board, which is why the fix that shipped was gated on a sample that was
# not chosen for it. `--ids` is that selection; these pin its contract.


class _RowStub:
    def __init__(self, rid: str) -> None:
        self.id = rid


def test_select_rows_ids_is_exact_and_ordered() -> None:
    from evals.regenold.run_official_batch import select_rows

    rows = [_RowStub(f"rg_{i:03d}") for i in range(1, 11)]
    got = select_rows(rows, ids="rg_003, rg_007")
    assert [r.id for r in got] == ["rg_003", "rg_007"]
    # Whitespace-separated form is accepted too.
    assert [r.id for r in select_rows(rows, ids="rg_002 rg_009")] == ["rg_002", "rg_009"]


def test_select_rows_ids_must_resolve() -> None:
    """An unknown id aborts: a run silently shrunk is the R422 failure shape."""
    from evals.regenold.run_official_batch import select_rows

    with pytest.raises(SystemExit) as excinfo:
        select_rows([_RowStub("rg_001")], ids="rg_001,typo_999")
    assert "typo_999" in str(excinfo.value)


def test_select_rows_ids_then_stride_then_limit() -> None:
    from evals.regenold.run_official_batch import select_rows

    rows = [_RowStub(f"rg_{i:03d}") for i in range(1, 11)]
    got = select_rows(rows, ids="rg_001 rg_002 rg_003 rg_004", stride=2, limit=1)
    assert [r.id for r in got] == ["rg_001"]
    # No --ids keeps the shipped selection exactly.
    assert [r.id for r in select_rows(rows, stride=5)] == ["rg_001", "rg_006"]
    assert [r.id for r in select_rows(rows, limit=2)] == ["rg_001", "rg_002"]
    with pytest.raises(SystemExit):
        select_rows(rows, stride=-1)

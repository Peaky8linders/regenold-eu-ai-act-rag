"""R365 — hard rule #8 must be an EXIT CODE, not a printed line.

WHAT WAS BROKEN
---------------
``evals/harness/easyhard_ab.py`` summed ``gold_dropped_head`` per arm, printed
the delta with a ``<-- GOLD DROPPED (hard rule #8)`` flag, and then ignored it:

  * absent from ``_AXES`` and ``_LEVERAGE`` (so it never entered any score);
  * the module had no ``assert`` and no ``hard_fail``; its only ``SystemExit``s
    were argparse errors;
  * ``main()`` returned ``None`` and ``__main__`` called it bare, so the process
    ALWAYS exited 0;
  * no CI consumes it (the repo has no ``.github/`` at all).

A replay of the real ``easyhard-r332-smoke-A`` checkpoint with one gold head
deleted from the branch arm printed ``gold_drop_hd  0  1  +1  <-- GOLD DROPPED
(hard rule #8)`` and exited **0**. Every "it passed the gold gate" claim was a
human reading stdout.

WHAT THESE TESTS PIN
--------------------
Two-sided, and offline — the decision lives in the pure
``_gold_gate_verdict(base_agg, branch_agg, allow, paired=...)`` helper, so no
live A/B and no network is needed to test it:

  * delta > 0  -> exit 1  (the fix)
  * delta == 0 -> exit 0  (no false positive)
  * delta < 0  -> exit 0  (a branch that RESCUES gold must not be punished)
  * ``--allow-gold-drop`` turns a would-be failure into exit 0 AND says so
  * ``main()`` really is wired through ``SystemExit`` in the ``__main__`` path
  * the existing ``gold_dropped_head`` SUM arithmetic in ``_aggregate`` /
    ``_paired`` is unchanged (the fix must not move the number it gates on)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evals.harness import easyhard_ab  # noqa: I001

# --------------------------------------------------------------------------
# helpers — synthetic aggregates in the exact shape main() hands the gate
# --------------------------------------------------------------------------

def _agg(gold_dropped: int, *, n: int = 5, split: str = "easy") -> dict[str, Any]:
    """One ``{split: aggregate}`` map as produced by ``_split`` + ``_aggregate``."""
    return {
        split: {
            "n": n,
            "errors": 0,
            "gold_dropped_head": gold_dropped,
            "gold_dropped_head_gold_count": 10,
        },
        "hard" if split == "easy" else "easy": {"n": 0, "errors": 0},
    }


def _paired_map(base: int, branch: int, *, n: int = 5,
                split: str = "easy") -> dict[str, Any]:
    """One ``_paired``-shaped map."""
    return {
        split: {
            "n": n,
            "baseline": {"gold_dropped_head": base},
            "branch": {"gold_dropped_head": branch},
        },
        "hard" if split == "easy" else "easy": {"n": 0},
    }


class TestGoldGateVerdict:
    """The pure decision. No run, no network."""

    def test_branch_drops_more_gold_exits_non_zero(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(1), allow=False)
        assert v["exit_code"] == 1
        assert v["failed"] is True
        assert v["suppressed_by_flag"] is False
        assert v["offending_splits"] == ["easy"]
        assert v["splits"]["easy"]["delta"] == 1

    def test_equal_gold_drop_exits_zero(self):
        # Both arms drop the SAME 2 gold heads: a pre-existing defect is not a
        # regression, and the gate must not block an unrelated change on it.
        v = easyhard_ab._gold_gate_verdict(_agg(2), _agg(2), allow=False)
        assert v["exit_code"] == 0
        assert v["failed"] is False
        assert v["offending_splits"] == []
        assert v["splits"]["easy"]["delta"] == 0

    def test_zero_zero_exits_zero(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(0), allow=False)
        assert v["exit_code"] == 0
        assert v["failed"] is False

    def test_branch_drops_fewer_gold_exits_zero(self):
        # A branch that RESCUES gold is the outcome we want; failing it would
        # make the gate an anti-signal.
        v = easyhard_ab._gold_gate_verdict(_agg(3), _agg(1), allow=False)
        assert v["exit_code"] == 0
        assert v["failed"] is False
        assert v["splits"]["easy"]["delta"] == -2

    def test_allow_flag_suppresses_failure_and_is_recorded(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(1), allow=True)
        assert v["exit_code"] == 0          # the run completes ...
        assert v["failed"] is True          # ... but the violation is NOT erased
        assert v["suppressed_by_flag"] is True
        assert v["allow_gold_drop"] is True

    def test_allow_flag_does_not_invent_a_failure(self):
        # Two-sided: the opt-out must be inert on a clean run.
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(0), allow=True)
        assert v["exit_code"] == 0
        assert v["failed"] is False
        assert v["suppressed_by_flag"] is False

    def test_single_arm_scorecard_is_not_gated(self):
        # No branch arm => nothing to regress against, even with gold dropped.
        v = easyhard_ab._gold_gate_verdict(_agg(4), None, allow=False)
        assert v["comparable"] is False
        assert v["exit_code"] == 0

    def test_arm_with_zero_scored_rows_is_not_gated(self):
        # A branch that produced 0 rows dropped everything; that is the
        # row-count warning's job, not a gold-delta claim.
        empty = {"easy": {"n": 0, "errors": 5}, "hard": {"n": 0, "errors": 0}}
        v = easyhard_ab._gold_gate_verdict(_agg(0), empty, allow=False)
        assert v["comparable"] is False
        assert v["exit_code"] == 0

    def test_hard_split_violation_is_not_masked_by_easy_split_gain(self):
        # The rule is "drop ZERO", not "net zero". An easy-split rescue must
        # not buy a hard-split gold deletion.
        base = {
            "easy": {"n": 5, "errors": 0, "gold_dropped_head": 3},
            "hard": {"n": 5, "errors": 0, "gold_dropped_head": 0},
        }
        branch = {
            "easy": {"n": 5, "errors": 0, "gold_dropped_head": 0},
            "hard": {"n": 5, "errors": 0, "gold_dropped_head": 1},
        }
        v = easyhard_ab._gold_gate_verdict(base, branch, allow=False)
        assert v["total_delta"] == -2          # the SUM looks like an improvement
        assert v["offending_splits"] == ["hard"]
        assert v["exit_code"] == 1             # ... and the gate still fails

    def test_paired_subset_overrides_the_full_aggregate(self):
        # _paired is the honest read when an arm loses rows. If the full
        # aggregate says "clean" but the paired subset says "dropped", the
        # paired subset decides.
        v = easyhard_ab._gold_gate_verdict(
            _agg(0), _agg(0), allow=False, paired=_paired_map(0, 1)
        )
        assert v["splits"]["easy"]["source"] == "paired"
        assert v["splits"]["easy"]["delta"] == 1
        assert v["exit_code"] == 1

    def test_full_aggregate_used_when_no_paired_subset(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(1), allow=False, paired={})
        assert v["splits"]["easy"]["source"] == "full"
        assert v["exit_code"] == 1


class TestGoldGateReporting:
    """A failure must be actionable: which rows, which refs."""

    @staticmethod
    def _row(rid: str, pred: list[str], dropped: list[str],
             *, multiturn: bool = False) -> dict[str, Any]:
        return {
            "id": rid,
            "is_multiturn": multiturn,
            "pred_refs": pred,
            "gold_refs": ["Article 5"],
            "scores": {
                "gold_dropped_head": float(len(dropped)),
                "gold_dropped_head_gold_count": 1.0,
                "gold_dropped_head_refs": dropped,
            },
        }

    def test_per_row_dropped_refs_are_surfaced(self):
        a = [self._row("q1", ["Article 5", "Annex III"], [])]
        b = [self._row("q1", ["Annex III"], ["Article 5"])]
        rows = easyhard_ab._gold_drop_rows(a, b)
        assert len(rows) == 1
        assert rows[0]["id"] == "q1"
        assert rows[0]["newly_dropped"] == ["Article 5"]
        assert rows[0]["baseline_refs"] == ["Article 5", "Annex III"]
        assert rows[0]["branch_refs"] == ["Annex III"]

    def test_row_already_dropped_by_baseline_is_not_reported(self):
        a = [self._row("q1", ["Annex III"], ["Article 5"])]
        b = [self._row("q1", ["Annex III"], ["Article 5"])]
        assert easyhard_ab._gold_drop_rows(a, b) == []

    def test_errored_row_is_not_counted_as_a_gold_wipeout(self):
        a = [self._row("q1", ["Article 5"], [])]
        b = [{"id": "q1", "is_multiturn": False, "error": "empty_answer"}]
        assert easyhard_ab._gold_drop_rows(a, b) == []

    def test_failure_banner_names_the_rule_and_the_exit(self, capsys):
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(1), allow=False)
        easyhard_ab._report_gold_gate(v, [])
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "hard rule #8" in out.lower()
        assert "NON-ZERO" in out
        assert "--allow-gold-drop" in out

    def test_suppressed_banner_says_loudly_that_it_did_not_pass(self, capsys):
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(1), allow=True)
        easyhard_ab._report_gold_gate(v, [])
        out = capsys.readouterr().out
        assert "WOULD HAVE FAILED" in out
        assert "--allow-gold-drop" in out
        assert "EXPLORATORY" in out
        assert "FAIL —" not in out          # not a plain failure; it exited 0

    def test_clean_run_reports_pass_without_a_banner(self, capsys):
        v = easyhard_ab._gold_gate_verdict(_agg(0), _agg(0), allow=False)
        easyhard_ab._report_gold_gate(v, [])
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "!!" not in out

    def test_single_arm_prints_no_gate_block(self, capsys):
        v = easyhard_ab._gold_gate_verdict(_agg(4), None, allow=False)
        easyhard_ab._report_gold_gate(v, [])
        assert capsys.readouterr().out == ""


class TestExitPlumbing:
    """The verdict is worthless if the process still exits 0."""

    def test_main_is_wired_through_SystemExit(self):
        src = Path(easyhard_ab.__file__).read_text(encoding="utf-8")
        tail = src[src.index('if __name__ == "__main__":'):]
        assert "raise SystemExit(main())" in tail, (
            "bare main() in __main__ makes the process always exit 0 — "
            "this is the R365 defect"
        )

    def test_main_returns_an_int(self):
        import inspect
        sig = inspect.signature(easyhard_ab.main)
        assert sig.return_annotation in (int, "int"), (
            "main() -> None cannot carry an exit code"
        )

    def test_allow_gold_drop_flag_exists_and_defaults_off(self):
        src = Path(easyhard_ab.__file__).read_text(encoding="utf-8")
        assert '"--allow-gold-drop"' in src
        assert re.search(
            r'"--allow-gold-drop",\s*\n\s*action="store_true"', src
        ), "the opt-out must be store_true, i.e. OFF unless asked for"


class TestSumArithmeticUnchanged:
    """Pin the number the gate reads. R365 must not move it."""

    @staticmethod
    def _scored(gd: int, *, multiturn: bool = False) -> dict[str, Any]:
        return {
            "id": f"r{gd}{multiturn}",
            "is_multiturn": multiturn,
            "pred_refs": ["Article 5"],
            "gold_refs": ["Article 5"],
            "latency_ms": 100.0,
            "scores": {
                "ref_loose": 1.0, "ref_strict": 1.0, "ref_conc": 1.0,
                "tone": 1.0, "kw_recall": 1.0,
                "gold_dropped_head": float(gd),
                "gold_dropped_head_gold_count": 1.0,
                "gold_dropped_head_refs": [],
            },
        }

    def test_aggregate_still_SUMS_not_means(self):
        rows = [self._scored(0), self._scored(1), self._scored(1)]
        # ids collide for the two gd=1 rows; give them distinct ids
        rows[2] = dict(rows[2], id="r1b")
        agg = easyhard_ab._aggregate(rows)
        assert agg["gold_dropped_head"] == 2           # SUM, not mean (0.667)
        assert agg["gold_dropped_head_gold_count"] == 3
        assert isinstance(agg["gold_dropped_head"], int)

    def test_aggregate_backcompat_for_pre_R332_checkpoints(self):
        row = self._scored(0)
        row["scores"] = {k: v for k, v in row["scores"].items()
                         if not k.startswith("gold_dropped")}
        agg = easyhard_ab._aggregate([row])
        assert agg["gold_dropped_head"] == 0
        assert agg["gold_dropped_head_gold_count"] == 0

    def test_paired_still_SUMS_per_arm(self):
        a = [self._scored(0)]
        b = [dict(self._scored(1), id=a[0]["id"])]
        p = easyhard_ab._paired(a, b)
        assert p["easy"]["baseline"]["gold_dropped_head"] == 0
        assert p["easy"]["branch"]["gold_dropped_head"] == 1

    def test_gold_dropped_head_still_excluded_from_the_scored_axes(self):
        # It is a VETO, never a score term. If it ever enters _AXES or
        # _LEVERAGE it becomes tradeable against conciseness — the exact
        # bargain hard rule #8 forbids.
        assert "gold_dropped_head" not in easyhard_ab._AXES
        assert "gold_dropped_head" not in easyhard_ab._LEVERAGE

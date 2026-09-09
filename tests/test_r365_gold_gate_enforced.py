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

import pytest

from evals.harness import easyhard_ab  # noqa: I001

# --------------------------------------------------------------------------
# helpers — synthetic aggregates in the exact shape main() hands the gate
# --------------------------------------------------------------------------

def _agg(gold_dropped: int, *, n: int = 50, split: str = "easy") -> dict[str, Any]:
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


def _paired_map(base: int, branch: int, *, n: int = 50,
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
            "easy": {"n": 50, "errors": 0, "gold_dropped_head": 3},
            "hard": {"n": 50, "errors": 0, "gold_dropped_head": 0},
        }
        branch = {
            "easy": {"n": 50, "errors": 0, "gold_dropped_head": 0},
            "hard": {"n": 50, "errors": 0, "gold_dropped_head": 1},
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


class TestR398NFloorAndLiveness:
    """R398 — the gate must refuse to emit a verdict on an underpowered sample."""

    def test_underpowered_split_returns_indeterminate(self):
        """n=10 on a split is below _MIN_GATE_N=30 → exit 2, not exit 0."""
        v = easyhard_ab._gold_gate_verdict(
            _agg(0, n=10), _agg(0, n=10), allow=False,
        )
        assert v["exit_code"] == 2, "underpowered should be indeterminate"
        assert v["underpowered"], "underpowered list should be non-empty"

    def test_powered_split_still_passes(self):
        """n >= _MIN_GATE_N with delta=0 → exit 0."""
        v = easyhard_ab._gold_gate_verdict(
            _agg(0, n=50), _agg(0, n=50), allow=False,
        )
        assert v["exit_code"] == 0
        assert not v.get("underpowered")

    def test_underpowered_does_not_override_a_failure(self):
        """If the branch drops gold AND n is low, the failure wins (exit 1)."""
        v = easyhard_ab._gold_gate_verdict(
            _agg(0, n=10), _agg(1, n=10), allow=False,
        )
        assert v["exit_code"] == 1, "a failure must not be downgraded to indeterminate"
        assert v["failed"] is True

    def test_min_gate_n_constant_exists(self):
        assert hasattr(easyhard_ab, "_MIN_GATE_N")
        assert easyhard_ab._MIN_GATE_N >= 20, "n-floor must be meaningful"


class TestR398LivenessGuard:
    """R398 — a gate that cannot see Stage-2 land cannot say PASS.

    Executed on ``1dc70db``: a fully offline run (``P2P_GRAPH_RAG_PROVIDER=cli``,
    dead ``OPENAI_API_BASE``) printed ``PASS`` and exited 0 for
    ``REGENOLD_PROMPT_V3``, a prompt-side lever — the exact class AGENTS.md
    invariant #5 mandates this gate for. Both arms had returned the same
    deterministic answer, so ``delta=+0`` was tautological, not evidence.
    """

    def test_the_counters_are_read_from_the_module_that_owns_them(self):
        """The first cut imported a module that does not exist.

        ``app.integrations.regenold.transport`` is not a module; the bare
        ``except Exception: pass`` around it swallowed the ModuleNotFoundError,
        so EVERY ``--local`` run reported "not live" whether or not it was —
        a guard that is unconditionally on is not a guard.
        """
        import importlib

        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("app.integrations.regenold.transport")
        # ...and the real one resolves, with the key the guard reads.
        stats = importlib.import_module("app.llm.stage2_policy").transport_stats()
        assert "primary_ok" in stats and "fallback_ok" in stats

    def test_offline_reads_not_live_with_a_stated_reason(self):
        from app.llm import stage2_policy

        stage2_policy.reset_transport_stats()
        live, note = easyhard_ab._transport_liveness(local=True)
        assert live is False
        assert "primary_ok=0" in note, note

    def test_a_landed_completion_reads_live(self, monkeypatch):
        import app.llm.stage2_policy as pol

        monkeypatch.setattr(
            pol, "transport_stats", lambda: {"primary_ok": 4, "fallback_ok": 0},
        )
        live, note = easyhard_ab._transport_liveness(local=True)
        assert live is True and "primary_ok=4" in note

    def test_an_import_failure_is_reported_not_laundered(self, monkeypatch):
        """A broken probe must say UNKNOWN, never silently mean 'not live'."""
        import builtins

        real_import = builtins.__import__

        def boom(name, *a, **k):
            if name == "app.llm.stage2_policy":
                raise ImportError("simulated")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", boom)
        live, note = easyhard_ab._transport_liveness(local=True)
        assert live is False
        assert "could not import" in note and "UNKNOWN" in note

    def test_a_remote_endpoint_run_is_the_callers_assertion(self):
        live, note = easyhard_ab._transport_liveness(local=False)
        assert live is True and "caller" in note


class TestR398UnscoredSplit:
    """R398 — 'zero on ANY split' must not quietly become 'on the ones that scored'."""

    def test_a_split_the_corpus_carried_but_never_scored_is_indeterminate(self):
        # easy scored 50 rows and is clean; hard was in the probe set and
        # produced nothing. `easyhard-v2_ab_gate.json` is this shape.
        v = easyhard_ab._gold_gate_verdict(
            _agg(0, n=50), _agg(0, n=50), allow=False,
            expected_splits=("easy", "hard"),
        )
        assert v["exit_code"] == 2
        assert v["unscored_splits"] == ["hard"]

    def test_a_deliberately_scoped_run_is_not_penalised(self):
        """``--multiturn skip`` legitimately carries one split."""
        v = easyhard_ab._gold_gate_verdict(
            _agg(0, n=50), _agg(0, n=50), allow=False, expected_splits=("easy",),
        )
        assert v["exit_code"] == 0
        assert not v["unscored_splits"]

    def test_a_single_arm_scorecard_is_still_not_a_gate(self):
        """No baseline to regress against ⇒ never indeterminate, never failed."""
        v = easyhard_ab._gold_gate_verdict(
            _agg(0, n=6), None, allow=False, expected_splits=("easy", "hard"),
        )
        assert v["exit_code"] == 0
        assert v["comparable"] is False

    def test_allow_gold_drop_suppresses_a_failure_but_not_indeterminacy(self):
        """R398 — a documented semantics change, pinned so it is deliberate.

        ``--allow-gold-drop`` exists to let a deliberate exploratory arm exit 0
        despite dropping gold. It is a statement about what the operator will
        ACCEPT. Indeterminacy is a statement about whether the run produced
        EVIDENCE, so the flag cannot suppress it -- otherwise the exploratory
        escape hatch would also be a way to launder an unmeasurable run.
        """
        # powered + failed + allow -> exit 0, exactly as before R398
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=50), _agg(2, n=50), allow=True)
        assert v["exit_code"] == 0 and v["suppressed_by_flag"] is True
        # underpowered + failed + allow -> still indeterminate
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=6), _agg(2, n=6), allow=True)
        assert v["exit_code"] == 2



class TestR398TheReportNeverContradictsTheExitCode:
    """R365's finding was that 'it passed the gate' had only ever been a human
    reading stdout. A stdout that says PASS while the process exits 2 is the
    same defect wearing a new exit code."""

    @staticmethod
    def _render(verdict) -> str:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            easyhard_ab._report_gold_gate(verdict, [])
        return buf.getvalue()

    def test_underpowered_does_not_print_pass(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=10), _agg(0, n=10))
        out = self._render(v)
        assert v["exit_code"] == 2
        assert "PASS" not in out, out
        assert "INDETERMINATE" in out

    def test_liveness_failure_does_not_print_pass(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=50), _agg(0, n=50))
        v["liveness_failed"] = True
        out = self._render(v)
        assert "PASS" not in out, out
        assert "LIVENESS FAILED" in out

    def test_a_powered_live_run_still_prints_pass(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=50), _agg(0, n=50))
        out = self._render(v)
        assert v["exit_code"] == 0
        assert "PASS" in out

    def test_the_allow_banner_states_the_exit_code_it_actually_has(self):
        """R398 — 'Exit code forced to 0' must not print on a run that exits 2."""
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=6), _agg(2, n=6), allow=True)
        out = self._render(v)
        assert v["exit_code"] == 2
        assert "forced to 0" not in out, out
        assert "INDETERMINATE" in out
        # the powered case keeps the original wording
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=50), _agg(2, n=50), allow=True)
        out = self._render(v)
        assert v["exit_code"] == 0 and "forced to 0" in out

    def test_a_real_failure_still_prints_fail(self):
        v = easyhard_ab._gold_gate_verdict(_agg(0, n=50), _agg(2, n=50))
        out = self._render(v)
        assert v["exit_code"] == 1
        assert "FAIL" in out and "HARD RULE #8" in out

    def test_the_gate_report_is_cp1252_safe(self):
        """R398 — a ``⚠`` in these prints raised UnicodeEncodeError on a
        Windows console and took the whole gate down BEFORE the sidecar was
        written. An uncaught crash also exits non-zero, so it was
        indistinguishable from a hard-rule-#8 FAIL.
        """
        for verdict in (
            easyhard_ab._gold_gate_verdict(_agg(0, n=10), _agg(0, n=10)),
            easyhard_ab._gold_gate_verdict(_agg(0, n=50), _agg(2, n=50)),
            easyhard_ab._gold_gate_verdict(_agg(0, n=50), _agg(0, n=50)),
        ):
            self._render(verdict).encode("cp1252")  # must not raise

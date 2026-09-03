"""R381 — the July-7 judge was grading us against OUR OWN July-7 output.

``evals/judge/grounded.py`` carries an explicit anti-circularity note:

    "``run_official_batch`` writes ``jul07_refs`` — which is OUR OWN prior
     output, NOT gold. Mapping it into ``gold_refs`` would make the judge grade
     'did we match our past self', which is circular, so we deliberately do NOT."

The guard named ``jul07_refs``. The sidecar key is ``july7_refs``. One character,
and ``_norm``'s fallback chain fired on every row.

MEASURED on ``evals/bench/results/july7-july7-live-r379.ckpt.jsonl`` before the
fix: 24/24 rows had ``gold_refs`` populated, 24/24 byte-identical to our own
2026-07-07 citations, the rendered prompt shipped them under "GOLD CITATIONS",
and the run wrote ``gold_coverage: 1.0`` / ``recall_is_text_grounded: True`` — so
the <50% warning banner never fired and the scorecard asserted it was
trustworthy while measuring self-similarity.

``evals/judge/legal_v2.py`` imports the same ``_norm``, so it inherited the bug
and inherits the fix.
"""
from __future__ import annotations

import os

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")


class TestSelfGoldIsNotGold:
    def test_july7_refs_never_becomes_gold_refs(self):
        from evals.judge.grounded import _norm

        row = {
            "id": "july7-001",
            "question": "q",
            "pred_answer": "a",
            "pred_refs": ["Article 11"],
            "july7_refs": ["Article 11", "Annex IV.1.e", "Annex IV.2.c"],
        }
        assert _norm(row)["gold_refs"] == [], (
            "our own 2026-07-07 output was mapped into gold_refs — the judge is "
            "grading 'did we match our past self'"
        )

    def test_the_misspelled_guard_key_is_also_refused(self):
        from evals.judge.grounded import _norm

        assert _norm({"jul07_refs": ["Article 5"]})["gold_refs"] == []

    def test_real_gold_still_flows(self):
        from evals.judge.grounded import _norm

        assert _norm({"gold_refs": ["Article 7.1"]})["gold_refs"] == ["Article 7.1"]
        assert _norm({"expected_refs": ["Annex X"]})["gold_refs"] == ["Annex X"]

    def test_legal_v2_shares_the_same_normaliser(self):
        """legal_v2 imports _norm from grounded, so the fix must propagate."""
        from evals.judge import grounded, legal_v2

        assert legal_v2._norm is grounded._norm

    def test_the_real_july7_sidecar_now_reports_zero_gold(self):
        """The committed sidecar is the artefact the 2026-09-02 report was built
        from. It must now read as gold-less, which is what triggers the honest
        'recall is judge recall, not text-grounded' banner."""
        import json
        import pathlib

        p = pathlib.Path("evals/bench/results/july7-july7-live-r379.ckpt.jsonl")
        if not p.exists():
            import pytest

            pytest.skip("sidecar not present in this checkout")
        from evals.judge.grounded import _norm

        rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert rows, "empty sidecar"
        with_gold = sum(1 for r in rows if _norm(r)["gold_refs"])
        assert with_gold == 0, (
            f"{with_gold}/{len(rows)} rows still carry self-gold"
        )


class TestPartialJudgeFailureIsNotSilent:
    """R361 made a TOTAL judge failure exit 2. A PARTIAL failure still exited 0
    while deflating the headline number, because ``pass_rate`` divides by ALL
    rows and an errored row counts as a non-pass. Measured with 50% of calls
    forced to a 403: pass_rate fell to 0.25 on two axes, ``dead`` was empty, and
    main() returned 0."""

    def test_the_cli_exposes_the_deliberate_escape_hatch(self):
        import argparse
        import inspect

        from evals.judge import grounded

        src = inspect.getsource(grounded.main)
        assert "--allow-judge-errors" in src
        assert "allow_judge_errors" in src
        # argparse turns the flag into this attribute name; a rename would make
        # the gate silently unreachable (a.allow_judge_errors -> AttributeError).
        p = argparse.ArgumentParser()
        p.add_argument("--allow-judge-errors", action="store_true")
        assert hasattr(p.parse_args([]), "allow_judge_errors")

    def test_a_partial_failure_returns_a_distinct_nonzero_code(self, monkeypatch, tmp_path, capsys):
        import sys

        from evals.judge import grounded

        sidecar = tmp_path / "s.jsonl"
        sidecar.write_text("{}\n", encoding="utf-8")

        def fake_run(**kwargs):
            return {
                "label": "t",
                "judge_model": "m",
                "aggregate": {
                    # 1 of 4 rows errored: not total, so the R361 guard is silent.
                    "answer_correctness": {"n": 4, "error": 1, "pass_rate": 0.5},
                    "reference_correctness": {"n": 4, "error": 0, "pass_rate": 0.75},
                },
            }

        monkeypatch.setattr(grounded, "run", fake_run)
        monkeypatch.setattr(grounded, "_fmt", lambda s: "")
        argv = ["--sidecar", str(sidecar), "--label", "t"]
        assert grounded.main(argv) == 3
        assert "PARTIAL JUDGE FAILURE" in capsys.readouterr().err
        assert grounded.main([*argv, "--allow-judge-errors"]) == 0
        assert sys is not None  # keep the import meaningful under -O

    def test_a_clean_run_still_exits_zero(self, monkeypatch, tmp_path):
        from evals.judge import grounded

        sidecar = tmp_path / "s.jsonl"
        sidecar.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(
            grounded,
            "run",
            lambda **k: {
                "label": "t",
                "judge_model": "m",
                "aggregate": {"answer_correctness": {"n": 4, "error": 0, "pass_rate": 1.0}},
            },
        )
        monkeypatch.setattr(grounded, "_fmt", lambda s: "")
        assert grounded.main(["--sidecar", str(sidecar), "--label", "t"]) == 0

    def test_a_total_failure_still_returns_two(self, monkeypatch, tmp_path):
        from evals.judge import grounded

        sidecar = tmp_path / "s.jsonl"
        sidecar.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(
            grounded,
            "run",
            lambda **k: {
                "label": "t",
                "judge_model": "m",
                "aggregate": {"answer_correctness": {"n": 4, "error": 4, "pass_rate": 0.0}},
            },
        )
        monkeypatch.setattr(grounded, "_fmt", lambda s: "")
        assert grounded.main(["--sidecar", str(sidecar), "--label", "t"]) == 2

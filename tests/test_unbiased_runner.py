"""Smoke tests for the unbiased runner CLI.

The runner orchestrates three harnesses (davidath hold-out, AIReg-Bench,
Regenold probe) through the live FastAPI test client. Tests verify:

    * The run() function returns a payload with all three harnesses
    * The payload is JSON-serialisable + lands in a sidecar file
    * The CLI accepts --label and writes a sidecar with that label
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.bench import unbiased_runner


class TestRun:
    def test_run_returns_three_sections(self, tmp_path: Path) -> None:
        # Smallest valid run: limit harnesses to keep the integration test fast.
        payload = unbiased_runner.run(
            label="pytest-smoke",
            output_dir=tmp_path,
            qa_limit=3,
            scenario_limit=3,
            aireg_limit=3,
            probe_limit=3,
        )
        assert "davidath_holdout" in payload
        assert "aireg_bench" in payload
        assert "regenold_probe" in payload
        # Sidecar path is written.
        assert payload["sidecar_path"]
        assert Path(payload["sidecar_path"]).exists()

    def test_payload_is_json_serialisable(self, tmp_path: Path) -> None:
        payload = unbiased_runner.run(
            label="pytest-json",
            output_dir=tmp_path,
            qa_limit=2,
            scenario_limit=2,
            aireg_limit=2,
            probe_limit=2,
        )
        # Round-trip via file (the runner already wrote one, but be defensive).
        body = json.loads(Path(payload["sidecar_path"]).read_text(encoding="utf-8"))
        assert body["label"] == "pytest-json"


class TestCLI:
    def test_cli_parses_label(self, tmp_path: Path, monkeypatch) -> None:
        # CLI hands off to run() — we just verify argparse accepts --label
        # without raising. Use monkeypatch to redirect output_dir.
        called = {}

        def fake_run(**kwargs):  # type: ignore[no-untyped-def]
            called.update(kwargs)
            return {
                "sidecar_path": str(tmp_path / "fake.json"),
                "davidath_holdout": {},
                "aireg_bench": {},
                "regenold_probe": {},
            }

        monkeypatch.setattr(unbiased_runner, "run", fake_run)
        monkeypatch.setattr(
            unbiased_runner, "_DEFAULT_OUTPUT_DIR", tmp_path, raising=False
        )
        exit_code = unbiased_runner.main(
            ["--label", "cli-test", "--qa-limit", "1", "--scenario-limit", "1"]
        )
        assert exit_code == 0
        assert called.get("label") == "cli-test"

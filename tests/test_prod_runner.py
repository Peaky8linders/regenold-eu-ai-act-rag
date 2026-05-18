"""Tests for evals/bench/prod_runner.py — the live-endpoint benchmark.

The tests mock :func:`urllib.request.urlopen` so no real network call
ever leaves the process. The fixtures cover:

    * Successful per-item scoring path (canned good response)
    * HTTP 500 → row recorded as failed, run continues
    * Timeout path → row recorded as failed with ``timeout`` error
    * URLError (connection refused / DNS) → row recorded as failed
    * Concurrency setting (4 parallel requests still produce 4 rows)
    * JSON sidecar shape (exists, parseable, carries scores+endpoint)
    * CLI arg parsing — every documented flag round-trips
    * Health probe (``--health-only``) — exit-zero when all three OK
    * Auth-header construction — ``X-Regenold-Api-Key`` is set iff
      ``--api-key`` provided
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from evals.bench import _http_retry, prod_runner


# ── Helpers ─────────────────────────────────────────────────────────────


class _FakeResponse:
    """Minimal urllib response that mimics what ``urlopen`` returns."""

    def __init__(self, body: dict | bytes, status: int = 200):
        if isinstance(body, dict):
            self._raw = json.dumps(body).encode("utf-8")
        else:
            self._raw = body
        self._status = status

    def read(self) -> bytes:
        return self._raw

    def getcode(self) -> int:
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_canned_body(answer: str, refs: list[str]) -> dict:
    return {
        "answer": answer,
        "references": refs,
        "reasoning": None,
    }


@contextmanager
def _patch_urlopen(side_effect):
    """Patch ``urllib.request.urlopen`` for both the prod_runner and the
    R47-D retry helper.

    After the R47-D migration ``prod_runner._http_post_json`` delegates
    to ``_http_retry.post_json_with_retry``, so the POST path calls
    ``urlopen`` from the ``_http_retry`` module's namespace. Health
    probes (``_http_get_json``) still use the prod_runner namespace —
    we patch both so every test continues to exercise the right wire.

    Also patches ``_http_retry.time.sleep`` to a no-op so retry backoff
    doesn't slow the test suite by 1.5 s on every permanent-failure
    fixture.
    """
    with patch.object(
        _http_retry.urllib.request, "urlopen", side_effect=side_effect
    ) as m, patch.object(
        prod_runner.urllib.request, "urlopen", side_effect=side_effect
    ), patch.object(_http_retry.time, "sleep", lambda _s: None):
        yield m


# ── HTTP transport ──────────────────────────────────────────────────────


class TestHttpPostJson:
    def test_successful_200_returns_body(self):
        canned = _make_canned_body(
            "Article 5 prohibits subliminal AI.", ["Article 5"]
        )

        def _fake(req, timeout):
            return _FakeResponse(canned, status=200)

        with _patch_urlopen(_fake):
            body, latency, status, err, attempts, retried = (
                prod_runner._http_post_json(
                    "https://example.test/ask",
                    [{"role": "user", "content": "q"}],
                    api_key=None,
                    timeout=5.0,
                )
            )
        assert err is None
        assert status == 200
        assert body["answer"] == "Article 5 prohibits subliminal AI."
        assert body["references"] == ["Article 5"]
        assert latency > 0  # some real elapsed time
        # R47-D — first-try success = 1 attempt, no retried errors.
        assert attempts == 1
        assert retried == []

    def test_http_500_returns_error_tag(self):
        def _fake(req, timeout):
            raise urllib.error.HTTPError(
                "https://example.test/ask",
                500,
                "Internal Server Error",
                {},
                io.BytesIO(b'{"detail":"engine fault"}'),
            )

        with _patch_urlopen(_fake):
            body, _, status, err, attempts, retried = (
                prod_runner._http_post_json(
                    "https://example.test/ask",
                    [{"role": "user", "content": "q"}],
                    api_key=None,
                    timeout=5.0,
                )
            )
        assert status == 500
        assert err is not None and err.startswith("http_500")
        assert body == {"answer": "", "references": [], "reasoning": None}
        # R47-D — 500 retries the default 2x. With urlopen.side_effect
        # raising the same HTTPError every time, all 3 attempts fail
        # and the final error is surfaced. retried has 3 entries (the
        # final attempt is captured too when retries are exhausted).
        assert attempts == 3
        assert len(retried) == 3

    def test_timeout_returns_timeout_tag(self):
        def _fake(req, timeout):
            raise TimeoutError("read timeout")

        with _patch_urlopen(_fake):
            _, _, status, err, attempts, _ = prod_runner._http_post_json(
                "https://example.test/ask",
                [{"role": "user", "content": "q"}],
                api_key=None,
                timeout=0.5,
            )
        assert status == 0
        assert err == "timeout"
        # R47-D — timeout is retried; permanent timeout exhausts the budget.
        assert attempts == 3

    def test_urlerror_returns_error_tag(self):
        def _fake(req, timeout):
            raise urllib.error.URLError("Connection refused")

        with _patch_urlopen(_fake):
            _, _, status, err, attempts, _ = prod_runner._http_post_json(
                "https://example.test/ask",
                [{"role": "user", "content": "q"}],
                api_key=None,
                timeout=5.0,
            )
        assert status == 0
        assert err is not None and err.startswith("url_error")
        # R47-D — generic URLError ("Connection refused" as a string)
        # is NOT classified as retryable (it's not a wrapped
        # RemoteDisconnected / WinError 10060). One attempt only.
        assert attempts == 1

    def test_invalid_json_returns_decode_tag(self):
        def _fake(req, timeout):
            return _FakeResponse(b"<html>not json</html>", status=200)

        with _patch_urlopen(_fake):
            body, _, status, err, attempts, _ = prod_runner._http_post_json(
                "https://example.test/ask",
                [{"role": "user", "content": "q"}],
                api_key=None,
                timeout=5.0,
            )
        assert status == 200
        assert err is not None and err.startswith("json_decode")
        assert body == {"answer": "", "references": [], "reasoning": None}
        # R47-D — JSON decode failures are deterministic; never retried.
        assert attempts == 1

    def test_non_dict_body_handled(self):
        def _fake(req, timeout):
            return _FakeResponse(b"[1, 2, 3]", status=200)

        with _patch_urlopen(_fake):
            body, _, status, err, attempts, _ = prod_runner._http_post_json(
                "https://example.test/ask",
                [{"role": "user", "content": "q"}],
                api_key=None,
                timeout=5.0,
            )
        assert status == 200
        assert err == "non_dict_body"
        assert body["answer"] == ""
        # R47-D — contract violations are deterministic; never retried.
        assert attempts == 1

    def test_missing_keys_get_defaults(self):
        def _fake(req, timeout):
            # Server returns minimal body without all 3 keys.
            return _FakeResponse({"answer": "ok"}, status=200)

        with _patch_urlopen(_fake):
            body, _, _, err, _, _ = prod_runner._http_post_json(
                "https://example.test/ask",
                [{"role": "user", "content": "q"}],
                api_key=None,
                timeout=5.0,
            )
        assert err is None
        assert body["answer"] == "ok"
        assert body["references"] == []
        assert body["reasoning"] is None


# ── Auth header ─────────────────────────────────────────────────────────


class TestAuthHeader:
    def test_request_includes_api_key_header(self):
        req = prod_runner._build_request(
            "https://example.test/ask",
            [{"role": "user", "content": "q"}],
            api_key="secret-partner-key",
        )
        # urllib lower-cases header keys.
        assert req.get_header("X-regenold-api-key") == "secret-partner-key"
        assert req.method == "POST"

    def test_no_api_key_means_no_auth_header(self):
        req = prod_runner._build_request(
            "https://example.test/ask",
            [{"role": "user", "content": "q"}],
            api_key=None,
        )
        assert req.get_header("X-regenold-api-key") is None
        # Required base headers stay set.
        assert req.get_header("Content-type") == "application/json"


# ── Subset runners ──────────────────────────────────────────────────────


class TestRunQaHttp:
    def test_canned_response_produces_scored_row(self):
        qa_items = [
            {
                "question": "What is the role of a provider?",
                "answer": "A provider develops an AI system.",
                "relevant_article": 3,
            }
        ]
        canned = _make_canned_body(
            "A provider is the entity that develops an AI system. Article 3 defines it.",
            ["Article 3"],
        )

        def _fake(req, timeout):
            return _FakeResponse(canned, status=200)

        with _patch_urlopen(_fake):
            rows = prod_runner._run_qa_http(
                "https://example.test/ask",
                api_key=None,
                timeout=5.0,
                concurrency=1,
                qa_items=qa_items,
                limit=None,
                verbose=False,
            )
        assert len(rows) == 1
        row = rows[0]
        assert row["passed"] is True
        assert row["http_status"] == 200
        assert row["error"] is None
        assert row["scores"]["ref_correctness_loose"] == 1.0
        assert row["scores"]["ans_correctness_strict"] > 0.0

    def test_http_500_records_failed_row(self):
        qa_items = [
            {
                "question": "Q",
                "answer": "gold",
                "relevant_article": 13,
            }
        ]

        def _fake(req, timeout):
            raise urllib.error.HTTPError(
                "https://example.test/ask", 500, "fail", {}, io.BytesIO(b"")
            )

        with _patch_urlopen(_fake):
            rows = prod_runner._run_qa_http(
                "https://example.test/ask",
                api_key=None,
                timeout=5.0,
                concurrency=1,
                qa_items=qa_items,
                limit=None,
                verbose=False,
            )
        assert len(rows) == 1
        assert rows[0]["passed"] is False
        assert rows[0]["http_status"] == 500
        assert rows[0]["error"].startswith("http_500")
        # Scoring still ran on the empty answer so the row is well-formed.
        assert rows[0]["scores"]["ans_correctness_loose"] == 0.0

    def test_concurrency_returns_all_rows(self):
        # 12 items, concurrency 4 → still 12 rows.
        qa_items = [
            {
                "question": f"q{i}",
                "answer": f"gold {i}",
                "relevant_article": (i % 10) + 1,
            }
            for i in range(12)
        ]

        def _fake(req, timeout):
            return _FakeResponse(
                _make_canned_body("Article 5 applies.", ["Article 5"]),
                status=200,
            )

        with _patch_urlopen(_fake):
            rows = prod_runner._run_qa_http(
                "https://example.test/ask",
                api_key=None,
                timeout=5.0,
                concurrency=4,
                qa_items=qa_items,
                limit=None,
                verbose=False,
            )
        assert len(rows) == 12
        # Order must be preserved — qa_000 → qa_011 mapping back to inputs.
        for idx, row in enumerate(rows):
            assert row["item_id"] == f"qa_{idx:03d}"


class TestRunScenariosHttp:
    def test_scenario_question_synthesised_correctly(self):
        scenarios = [
            {
                "role": "Provider",
                "intended_use": "screen job applicants",
                "system_type": "CV ranker",
                "domain": "employment",
                "related_articles": [6, 13],
                "obligations": ["maintain technical docs"],
                "risk_level": "high-risk",
            }
        ]
        captured: list[Any] = []

        def _fake(req, timeout):
            captured.append(req.data)
            return _FakeResponse(
                _make_canned_body(
                    "high-risk classification under Article 6.",
                    ["Article 6"],
                ),
                status=200,
            )

        with _patch_urlopen(_fake):
            rows = prod_runner._run_scenarios_http(
                "https://example.test/ask",
                api_key=None,
                timeout=5.0,
                concurrency=1,
                scenarios=scenarios,
                limit=None,
                verbose=False,
            )
        assert len(rows) == 1
        # The synthesised scenario question must have hit the wire.
        sent = json.loads(captured[0])
        assert isinstance(sent, list)
        assert sent[0]["role"] == "user"
        assert "provider" in sent[0]["content"].lower()
        assert "cv ranker" in sent[0]["content"].lower()
        # Article 6 in pred + gold → recall 0.5 (gold = {6, 13}).
        assert rows[0]["scores"]["ref_correctness_loose"] == 0.5


# ── Health probe ────────────────────────────────────────────────────────


class TestHealthProbe:
    def test_derive_health_url_basic(self):
        u = prod_runner._derive_health_url(
            "https://example.test/api/v1/regenold/eu-ai-act/ask",
            "/healthz/llm",
        )
        assert u == "https://example.test/healthz/llm"

    def test_health_only_all_ok(self):
        def _fake(req, timeout):
            return _FakeResponse(
                {"status": "ok", "version": "0.1.0"}, status=200
            )

        with _patch_urlopen(_fake):
            report = prod_runner.run_health_only(
                "https://example.test/api/v1/regenold/eu-ai-act/ask",
                api_key=None,
                timeout=5.0,
            )
        probes = report["probes"]
        assert set(probes.keys()) == {"/healthz", "/healthz/llm", "/healthz/graph"}
        assert all(p["ok"] for p in probes.values())

    def test_health_only_marks_failure_on_500(self):
        def _fake(req, timeout):
            raise urllib.error.HTTPError(
                "https://example.test/healthz", 500, "fail", {}, io.BytesIO(b"")
            )

        with _patch_urlopen(_fake):
            report = prod_runner.run_health_only(
                "https://example.test/api/v1/regenold/eu-ai-act/ask",
                api_key=None,
                timeout=5.0,
            )
        assert all(not p["ok"] for p in report["probes"].values())


# ── CLI parsing ─────────────────────────────────────────────────────────


class TestCliParsing:
    def test_required_flags(self):
        parser = prod_runner.build_arg_parser()
        # Both --endpoint and --label are required.
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_all_documented_flags_round_trip(self):
        parser = prod_runner.build_arg_parser()
        args = parser.parse_args(
            [
                "--endpoint",
                "https://example.test/api/v1/regenold/eu-ai-act/ask",
                "--api-key",
                "k",
                "--label",
                "round-test",
                "--limit",
                "5",
                "--concurrency",
                "2",
                "--timeout",
                "10",
                "--qa-only",
                "--scenarios-only",
                "--skip-multiturn",
                "--multiturn-limit",
                "3",
                "--verbose",
                "--health-only",
            ]
        )
        assert args.endpoint.endswith("/ask")
        assert args.api_key == "k"
        assert args.label == "round-test"
        assert args.limit == 5
        assert args.concurrency == 2
        assert args.timeout == 10.0
        assert args.qa_only is True
        assert args.scenarios_only is True
        assert args.skip_multiturn is True
        assert args.multiturn_limit == 3
        assert args.verbose is True
        assert args.health_only is True

    def test_defaults(self):
        parser = prod_runner.build_arg_parser()
        args = parser.parse_args(
            [
                "--endpoint",
                "https://x.test/ask",
                "--label",
                "lbl",
            ]
        )
        assert args.concurrency == 4
        assert args.timeout == 30.0
        assert args.limit is None
        assert args.multiturn_limit == 20
        assert args.health_only is False


# ── End-to-end sidecar shape ────────────────────────────────────────────


class TestRunSidecar:
    def test_sidecar_written_with_prod_prefix(self, tmp_path, monkeypatch):
        # Force the results dir to a temp path so the test doesn't pollute
        # the real results directory.
        results_dir = tmp_path / "results"
        monkeypatch.setattr(prod_runner.storage, "RESULTS_DIR", results_dir)
        monkeypatch.setattr(
            prod_runner.storage, "LEDGER_PATH", results_dir / "ledger.sqlite"
        )

        # Cap the dataset to a tiny set by monkeypatching the loaders.
        monkeypatch.setattr(
            prod_runner.bench_dataset, "ensure_dataset", lambda: None
        )
        monkeypatch.setattr(
            prod_runner.bench_dataset,
            "load_qa_pairs",
            lambda: [
                {"question": "q1", "answer": "Article 5 applies.", "relevant_article": 5}
            ],
        )
        monkeypatch.setattr(
            prod_runner.bench_dataset,
            "load_scenarios",
            lambda: [
                {
                    "role": "Provider",
                    "intended_use": "x",
                    "system_type": "y",
                    "domain": "z",
                    "related_articles": [5],
                    "obligations": ["o"],
                    "risk_level": "high-risk",
                }
            ],
        )
        # No audit-chain DB; default in-memory store is fine.
        monkeypatch.delenv("DATABASE_URL", raising=False)

        def _fake(req, timeout):
            return _FakeResponse(
                _make_canned_body("Article 5 applies.", ["Article 5"]),
                status=200,
            )

        with _patch_urlopen(_fake):
            payload = prod_runner.run(
                endpoint="https://example.test/api/v1/regenold/eu-ai-act/ask",
                api_key="dummy",
                label="unit-test",
                concurrency=1,
                timeout=5.0,
                multiturn_limit=1,
            )
        sidecar = Path(payload["sidecar_path"])
        assert sidecar.exists()
        assert sidecar.name.startswith("prod-")
        loaded = json.loads(sidecar.read_text(encoding="utf-8"))
        assert loaded["mode"] == "prod"
        assert loaded["endpoint"].endswith("/ask")
        assert "summary" in loaded
        assert loaded["summary"]["qa"]["n"] == 1
        assert loaded["summary"]["scenarios"]["n"] == 1
        assert loaded["summary"]["overall"]["n"] == 2
        # Audit chain best-effort: either succeeded (chain_entry_id set)
        # or failed gracefully (chain_write_error set), never both empty.
        assert (
            loaded.get("chain_entry_id") is not None
            or "chain_write_error" in loaded
        )

    def test_mixed_success_and_failure(self, tmp_path, monkeypatch):
        results_dir = tmp_path / "results"
        monkeypatch.setattr(prod_runner.storage, "RESULTS_DIR", results_dir)
        monkeypatch.setattr(
            prod_runner.storage, "LEDGER_PATH", results_dir / "ledger.sqlite"
        )
        monkeypatch.setattr(
            prod_runner.bench_dataset, "ensure_dataset", lambda: None
        )
        monkeypatch.setattr(
            prod_runner.bench_dataset,
            "load_qa_pairs",
            lambda: [
                {"question": "q1", "answer": "a", "relevant_article": 5},
                {"question": "q2", "answer": "a", "relevant_article": 6},
            ],
        )
        monkeypatch.setattr(
            prod_runner.bench_dataset, "load_scenarios", lambda: []
        )
        monkeypatch.delenv("DATABASE_URL", raising=False)

        call_counter = {"n": 0}

        def _fake(req, timeout):
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return _FakeResponse(
                    _make_canned_body("Article 5 applies.", ["Article 5"]),
                    status=200,
                )
            # Second call fails — the run keeps going.
            raise urllib.error.HTTPError(
                "https://example.test/ask",
                500,
                "fail",
                {},
                io.BytesIO(b""),
            )

        with _patch_urlopen(_fake):
            payload = prod_runner.run(
                endpoint="https://example.test/api/v1/regenold/eu-ai-act/ask",
                api_key=None,
                label="mixed-test",
                qa_only=True,
                concurrency=1,
                timeout=5.0,
            )
        assert payload["summary"]["http_total"] == 2
        assert payload["summary"]["http_failures"] == 1
        # The successful row was scored ok.
        qa_rows = payload["qa"]
        assert len(qa_rows) == 2
        statuses = sorted(r["http_status"] for r in qa_rows)
        assert statuses == [200, 500]


# ── main() smoke test ───────────────────────────────────────────────────


class TestMainEntry:
    def test_health_only_main_exits_zero_when_all_ok(self, monkeypatch, capsys):
        def _fake(req, timeout):
            return _FakeResponse({"status": "ok"}, status=200)

        with _patch_urlopen(_fake):
            rc = prod_runner.main(
                [
                    "--endpoint",
                    "https://example.test/api/v1/regenold/eu-ai-act/ask",
                    "--label",
                    "health-test",
                    "--health-only",
                ]
            )
        assert rc == 0
        captured = capsys.readouterr()
        assert "production health probe" in captured.out

    def test_health_only_main_exits_nonzero_on_failure(
        self, monkeypatch, capsys
    ):
        def _fake(req, timeout):
            raise urllib.error.URLError("Connection refused")

        with _patch_urlopen(_fake):
            rc = prod_runner.main(
                [
                    "--endpoint",
                    "https://example.test/api/v1/regenold/eu-ai-act/ask",
                    "--label",
                    "health-test",
                    "--health-only",
                ]
            )
        assert rc == 2

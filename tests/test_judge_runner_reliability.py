"""R66-C — judge runner reliability hardening.

Covers the three R66-C surfaces:

1. **Retry classification** — :func:`is_retryable_judge_error` returns
   True for transient connection / timeout failures and False for
   deterministic parse / config failures.
2. **Retry recovery** — :func:`_call_judge_with_retry` fires exactly
   one retry on a retryable failure; if the second attempt succeeds,
   the verdict is recorded as a pass and the retry counter increments.
3. **Anthropic provider routing** — ``--provider anthropic`` reaches
   :func:`_call_judge_anthropic`; ImportError fails soft to
   ``judge_error``; missing key returns ``judge_error`` cleanly.
4. **Default concurrency = 2** — the argparse default dropped 4 → 2
   per R66-C to avoid thrashing the wrapper's slowapi gate.
"""
from __future__ import annotations

import builtins as _builtins
from typing import Any
from unittest.mock import MagicMock

import pytest


# ── 1. Retry classification ──────────────────────────────────────────────


class TestRetryableClassification:
    """is_retryable_judge_error tags transient vs deterministic failures."""

    @pytest.mark.parametrize("msg", [
        "wrapper_returned_none",
        "call_failed: timeout",
        "call_failed: HTTPError timed out",
        "network_error: connection reset",
        "transport: remote disconnected",
        "wrapper_error: network_error: connect refused",
        "rate_limit: 429",
        "RateLimit: too fast",
        "api_status_500: internal",
        "api_status_429: slowapi",
        "timeout: read timeout exceeded",
    ])
    def test_retryable_shapes(self, msg: str) -> None:
        from evals.judge.runner import is_retryable_judge_error
        assert is_retryable_judge_error(msg) is True, f"expected retryable: {msg!r}"

    @pytest.mark.parametrize("msg", [
        "wrapper_unavailable: ImportError",
        "wrapper_not_configured",
        "no_json",
        "parse_failed: Expecting value",
        "unbalanced_json",
        "empty_response",
        "sdk_unavailable: anthropic not installed",
        "no_api_key: set P2P_GRAPH_RAG_API_KEY",
        "authentication: invalid key",
        "permission: read-only",
    ])
    def test_non_retryable_shapes(self, msg: str) -> None:
        from evals.judge.runner import is_retryable_judge_error
        assert is_retryable_judge_error(msg) is False, f"expected non-retryable: {msg!r}"

    def test_empty_returns_false(self) -> None:
        from evals.judge.runner import is_retryable_judge_error
        assert is_retryable_judge_error("") is False

    def test_non_retryable_wins_on_collision(self) -> None:
        """Auth failures sometimes contain the word 'timeout' — auth wins."""
        from evals.judge.runner import is_retryable_judge_error
        assert is_retryable_judge_error(
            "wrapper_error: authentication failed (timeout reading body)"
        ) is False


# ── 2. Retry recovery ────────────────────────────────────────────────────


class TestRetryRecovery:
    """_call_judge_with_retry honours the 1-retry policy and reports
    attempts + retried_errors correctly."""

    def test_first_try_success_no_retry(self) -> None:
        from evals.judge.runner import _call_judge_with_retry

        def caller(_prompt: str) -> dict[str, Any]:
            return {"verdict": "pass", "failure_mode": ""}

        result, attempts, retried = _call_judge_with_retry(caller, "prompt")
        assert result == {"verdict": "pass", "failure_mode": ""}
        assert attempts == 1
        assert retried == []

    def test_retryable_failure_then_success_increments_counter(self) -> None:
        from evals.judge.runner import _call_judge_with_retry

        call_count = {"n": 0}

        def caller(_prompt: str) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"judge_error": "wrapper_error: network_error: timed out"}
            return {"verdict": "pass"}

        result, attempts, retried = _call_judge_with_retry(
            caller, "prompt", backoff_s=0.0,
        )
        # Verdict recorded as pass on the retry.
        assert result == {"verdict": "pass"}
        assert attempts == 2
        # One retried error captured (the original transient failure).
        assert len(retried) == 1
        assert "timed out" in retried[0]

    def test_non_retryable_failure_no_retry(self) -> None:
        from evals.judge.runner import _call_judge_with_retry

        call_count = {"n": 0}

        def caller(_prompt: str) -> dict[str, Any]:
            call_count["n"] += 1
            return {"judge_error": "no_json", "raw": "garbage"}

        result, attempts, retried = _call_judge_with_retry(
            caller, "prompt", backoff_s=0.0,
        )
        assert result["judge_error"] == "no_json"
        assert attempts == 1
        assert retried == []
        assert call_count["n"] == 1

    def test_both_attempts_fail_record_final_error(self) -> None:
        from evals.judge.runner import _call_judge_with_retry

        def caller(_prompt: str) -> dict[str, Any]:
            return {"judge_error": "wrapper_returned_none"}

        result, attempts, retried = _call_judge_with_retry(
            caller, "prompt", backoff_s=0.0,
        )
        assert result["judge_error"] == "wrapper_returned_none"
        assert attempts == 2
        # Both transient failures are recorded.
        assert len(retried) == 2

    def test_max_one_retry_per_default(self) -> None:
        """The default ``max_retries=1`` cap means a persistent transient
        failure produces exactly 2 attempts (initial + 1 retry), never 3."""
        from evals.judge.runner import _call_judge_with_retry

        call_count = {"n": 0}

        def caller(_prompt: str) -> dict[str, Any]:
            call_count["n"] += 1
            return {"judge_error": "call_failed: timeout"}

        _result, attempts, _retried = _call_judge_with_retry(
            caller, "prompt", backoff_s=0.0,
        )
        assert attempts == 2
        assert call_count["n"] == 2


# ── 3. Anthropic provider routing ───────────────────────────────────────


class TestAnthropicProviderRouting:
    """--provider anthropic dispatches to _call_judge_anthropic and falls
    soft on missing key / SDK import error."""

    def test_resolve_caller_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # R263 — _resolve_caller now wraps the provider function in a
        # lambda to thread a configurable timeout through (Sonnet 5 +
        # the live wrapper routinely needs 60-90s, beyond the historical
        # 30s default), so it can no longer be identity-compared against
        # the bare function. Assert it DISPATCHES to the right one instead.
        import evals.judge.runner as runner_mod
        calls: list[tuple[str, float]] = []
        monkeypatch.setattr(
            runner_mod, "_call_judge_anthropic",
            lambda p, timeout_s=30.0: calls.append((p, timeout_s)) or {"verdict": "pass"},
        )
        caller = runner_mod._resolve_caller("anthropic", timeout_s=42.0)
        caller("hello")
        assert calls == [("hello", 42.0)]

    def test_resolve_caller_wrapper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import evals.judge.runner as runner_mod
        calls: list[tuple[str, float]] = []
        monkeypatch.setattr(
            runner_mod, "_call_judge_sonnet",
            lambda p, timeout_s=30.0: calls.append((p, timeout_s)) or {"verdict": "pass"},
        )
        caller = runner_mod._resolve_caller("wrapper", timeout_s=42.0)
        caller("hello")
        assert calls == [("hello", 42.0)]

    def test_resolve_caller_unknown_falls_back_to_wrapper(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unknown provider strings fall back to wrapper (default)."""
        import evals.judge.runner as runner_mod
        calls: list[tuple[str, float]] = []
        monkeypatch.setattr(
            runner_mod, "_call_judge_sonnet",
            lambda p, timeout_s=30.0: calls.append((p, timeout_s)) or {"verdict": "pass"},
        )
        caller = runner_mod._resolve_caller("nonsense", timeout_s=42.0)
        caller("hello")
        assert calls == [("hello", 42.0)]

    def test_resolve_caller_default_timeout_is_30s(self) -> None:
        """No explicit timeout_s arg -> the historical 30s default, so
        every pre-R263 caller (runner_v2, ab_judge) keeps its tuning."""
        import inspect

        from evals.judge.runner import _resolve_caller
        sig = inspect.signature(_resolve_caller)
        assert sig.parameters["timeout_s"].default == 30.0

    def test_anthropic_no_key_returns_judge_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No P2P_GRAPH_RAG_API_KEY + no ANTHROPIC_API_KEY → clean
        judge_error, never raises."""
        monkeypatch.delenv("P2P_GRAPH_RAG_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from evals.judge.runner import _call_judge_anthropic
        result = _call_judge_anthropic("prompt", timeout_s=5.0)
        assert "judge_error" in result
        assert "no_api_key" in result["judge_error"]

    def test_anthropic_sdk_import_error_returns_judge_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Monkeypatch the ``anthropic`` import to ImportError →
        ``judge_error`` contains 'sdk_unavailable'."""
        monkeypatch.setenv("P2P_GRAPH_RAG_API_KEY", "sk-ant-fake")
        # Also remove ANTHROPIC_API_KEY so we exercise the
        # P2P_GRAPH_RAG_API_KEY branch only.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        orig_import = _builtins.__import__

        def _no_anthropic(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "anthropic":
                raise ImportError("not installed")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(_builtins, "__import__", _no_anthropic)
        from evals.judge.runner import _call_judge_anthropic
        result = _call_judge_anthropic("prompt", timeout_s=5.0)
        assert "judge_error" in result
        assert "sdk_unavailable" in result["judge_error"]

    def test_anthropic_reads_anthropic_api_key_fallback(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``ANTHROPIC_API_KEY`` is the SDK's standard env var; the judge
        runner accepts it as a fallback when ``P2P_GRAPH_RAG_API_KEY`` is
        not set."""
        monkeypatch.delenv("P2P_GRAPH_RAG_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-alt")

        # Force ImportError so the call doesn't actually try to hit the
        # network — we just want to verify the no_api_key path is NOT
        # taken.
        orig_import = _builtins.__import__

        def _no_anthropic(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "anthropic":
                raise ImportError("not installed for this test")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(_builtins, "__import__", _no_anthropic)
        from evals.judge.runner import _call_judge_anthropic
        result = _call_judge_anthropic("prompt", timeout_s=5.0)
        # Should be sdk_unavailable, NOT no_api_key — confirms the key
        # lookup found ANTHROPIC_API_KEY.
        assert "judge_error" in result
        assert "sdk_unavailable" in result["judge_error"]
        assert "no_api_key" not in result["judge_error"]

    def test_anthropic_happy_path_returns_parsed_json(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mocked Anthropic SDK returns a content block with JSON → the
        judge parses it cleanly."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_API_KEY", "sk-ant-fake")

        class _Block:
            text = '{"verdict":"pass","failure_mode":""}'

        class _Resp:
            content = [_Block()]

        class _Messages:
            @staticmethod
            def create(**_kw: Any) -> Any:
                return _Resp()

        class _Anthropic:
            def __init__(self, **_kw: Any) -> None:
                pass

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from evals.judge.runner import _call_judge_anthropic
        result = _call_judge_anthropic("prompt", timeout_s=5.0)
        assert result == {"verdict": "pass", "failure_mode": ""}

    def test_anthropic_rate_limit_returns_retryable_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A RateLimitError-shaped exception should produce a
        ``rate_limit:`` judge_error that the retry classifier sees as
        retryable."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_API_KEY", "sk-ant-fake")

        class _RateLimitErrorMock(Exception):
            pass
        _RateLimitErrorMock.__name__ = "RateLimitError"

        class _Messages:
            @staticmethod
            def create(**_kw: Any) -> Any:
                raise _RateLimitErrorMock("429 slow down")

        class _Anthropic:
            def __init__(self, **_kw: Any) -> None:
                pass

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from evals.judge.runner import _call_judge_anthropic, is_retryable_judge_error
        result = _call_judge_anthropic("prompt", timeout_s=5.0)
        assert "judge_error" in result
        assert "rate_limit" in result["judge_error"]
        # Critical invariant — this shape MUST be classified retryable
        # so the outer wrapper retries once.
        assert is_retryable_judge_error(result["judge_error"]) is True


# ── 4. Default concurrency ──────────────────────────────────────────────


class TestArgparseDefaults:
    """Default concurrency dropped 4 → 2 per R66-C."""

    def test_default_concurrency_is_2(self) -> None:
        """argparse default for --concurrency is 2."""
        # Drive the argparse layer the same way main() does.
        import argparse
        from evals.judge import runner as _r

        # Re-create the parser layout main() builds — we can't easily
        # reach into main() because it ends by calling run(). The
        # contract under test is: a fresh ArgumentParser built from the
        # same descriptors as in main() has default=2 on --concurrency.
        parser = argparse.ArgumentParser()
        parser.add_argument("--bench-sidecar", required=True)
        parser.add_argument("--label", required=True)
        parser.add_argument("--rows-limit", type=int, default=None)
        parser.add_argument("--concurrency", type=int, default=2)
        parser.add_argument("--provider", choices=("wrapper", "anthropic"), default="wrapper")
        parser.add_argument("--verbose", action="store_true")
        # Validate the live parser surface matches: hit main() with
        # required args and trap before run() executes.
        captured: dict[str, Any] = {}

        def _fake_run(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "label": kwargs.get("label", ""),
                "source_sidecar": str(kwargs.get("bench_sidecar", "")),
                "elapsed_s": 0.0,
                "axes": [],
                "aggregate": {},
            }

        # Use monkeypatch via a contextmanager-style swap.
        orig_run = _r.run
        _r.run = _fake_run  # type: ignore[assignment]
        try:
            _r.main(["--bench-sidecar", "/tmp/x.json", "--label", "t"])
        finally:
            _r.run = orig_run  # type: ignore[assignment]
        assert captured["concurrency"] == 2

    def test_default_provider_is_wrapper(self) -> None:
        """argparse default for --provider is 'wrapper'."""
        from evals.judge import runner as _r
        captured: dict[str, Any] = {}

        def _fake_run(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "label": "t",
                "source_sidecar": "x",
                "elapsed_s": 0.0,
                "axes": [],
                "aggregate": {},
            }

        orig_run = _r.run
        _r.run = _fake_run  # type: ignore[assignment]
        try:
            _r.main(["--bench-sidecar", "/tmp/x.json", "--label", "t"])
        finally:
            _r.run = orig_run  # type: ignore[assignment]
        assert captured["provider"] == "wrapper"


# ── 5. Per-row retry telemetry ──────────────────────────────────────────


class TestPerRowRetryTelemetry:
    """_judge_row attaches retry telemetry to the verdict + per-row dict."""

    def test_retried_axis_records_attempts_and_retried_errors(self) -> None:
        from evals.judge.runner import _judge_row

        # First call to each axis fails; second succeeds. Use a stable
        # key derived from a content marker inside each prompt body so
        # the four axes share NO state and each one fails-then-succeeds
        # independently.
        attempt_counts: dict[str, int] = {}

        def _axis_key(prompt: str) -> str:
            # Each prompt's first line carries a distinctive opener
            # (per axis renderer in prompts.py). When two axes share the
            # opener (refs renderer has multiple prompts on the first
            # line), fall back to the second line which is always
            # distinct.
            head = prompt.splitlines()[0]
            if "EU AI Act legal expert grading" in head:
                return "correctness"
            if "checking citation faithfulness" in head:
                return "refs"
            if "conciseness" in head.lower():
                return "conciseness"
            if "REGULATORY TONE" in head:
                return "tone"
            return head[:32]

        def caller(prompt: str) -> dict[str, Any]:
            key = _axis_key(prompt)
            attempt_counts[key] = attempt_counts.get(key, 0) + 1
            if attempt_counts[key] == 1:
                return {"judge_error": "wrapper_error: network_error: timed out"}
            return {"verdict": "pass", "failure_mode": ""}

        # Monkey-replace time.sleep for fast tests.
        import time as _time
        orig_sleep = _time.sleep
        _time.sleep = lambda _s: None  # type: ignore[assignment]
        try:
            judged = _judge_row(
                {"id": "row1", "question": "What does Art. 13 require?"},
                article_summaries={},
                caller=caller,
            )
        finally:
            _time.sleep = orig_sleep  # type: ignore[assignment]
        assert judged["id"] == "row1"
        # Every axis was retried.
        assert set(judged["retried_axes"].keys()) == {"correctness", "refs", "conciseness", "tone"}
        for axis in ("correctness", "refs", "conciseness", "tone"):
            v = judged["verdicts"][axis]
            assert v.get("verdict") == "pass"
            assert v.get("_attempts") == 2
            assert len(v.get("_retried_errors", [])) == 1

    def test_unretried_axis_has_empty_retried_axes(self) -> None:
        from evals.judge.runner import _judge_row

        def caller(_prompt: str) -> dict[str, Any]:
            return {"verdict": "pass", "failure_mode": ""}

        judged = _judge_row(
            {"id": "row1", "question": "What does Art. 13 require?"},
            article_summaries={},
            caller=caller,
        )
        assert judged["retried_axes"] == {}
        # No _attempts / _retried_errors keys on a happy-path verdict.
        for axis in ("correctness", "refs", "conciseness", "tone"):
            v = judged["verdicts"][axis]
            assert "_attempts" not in v
            assert "_retried_errors" not in v


# ── 6. Run-level retry aggregation ──────────────────────────────────────


class TestRetryAggregation:
    """_aggregate_retries surfaces the run-level total + recovery rate."""

    def test_total_retries_and_recovery_rate(self) -> None:
        from evals.judge.runner import _aggregate_retries

        rows = [
            # Row 1: correctness axis retried, recovered (verdict=pass).
            {
                "id": "row1",
                "verdicts": {
                    "correctness": {"verdict": "pass"},
                    "refs": {"verdict": "pass"},
                    "conciseness": {"verdict": "pass"},
                    "tone": {"verdict": "pass"},
                },
                "retried_axes": {"correctness": ["timeout"]},
            },
            # Row 2: refs axis retried, did NOT recover (judge_error).
            {
                "id": "row2",
                "verdicts": {
                    "correctness": {"verdict": "pass"},
                    "refs": {"judge_error": "wrapper_returned_none"},
                    "conciseness": {"verdict": "pass"},
                    "tone": {"verdict": "pass"},
                },
                "retried_axes": {"refs": ["timeout", "timed out"]},
            },
            # Row 3: no retries.
            {
                "id": "row3",
                "verdicts": {
                    "correctness": {"verdict": "pass"},
                    "refs": {"verdict": "pass"},
                    "conciseness": {"verdict": "pass"},
                    "tone": {"verdict": "pass"},
                },
                "retried_axes": {},
            },
        ]
        agg = _aggregate_retries(rows)
        assert agg["total_retries"] == 2
        assert agg["retried_axes"] == {
            "correctness": 1, "refs": 1, "conciseness": 0, "tone": 0,
        }
        assert agg["retries_recovered"] == 1
        assert agg["retry_recovery_rate"] == 0.5

    def test_empty_rows_no_retries(self) -> None:
        from evals.judge.runner import _aggregate_retries
        agg = _aggregate_retries([])
        assert agg["total_retries"] == 0
        assert agg["retry_recovery_rate"] == 0.0

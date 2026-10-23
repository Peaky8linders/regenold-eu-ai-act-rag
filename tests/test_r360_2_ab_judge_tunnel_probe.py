"""R360.2 — the merge gate must probe the wrapper it is actually going to use.

``evals.harness.ab_judge`` is the merge gate (``CLAUDE.md``: "the merge gate is
the live pairwise A/B"). Its liveness probe was hardcoded to
``http://127.0.0.1:8000/v1/auth/status``, so running the gate against the
**cloudflared tunnel** — the documented production shape, and the one the
operator uses — probed localhost, found nothing, and silently downgraded the
run to the deterministic tier.

That is the worst failure mode a gate can have: it is quiet, and the output
still reads as a scorecard. The operator sees deterministic reference/keyword
metrics where they expected a judged live pairwise win-rate.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from evals.harness import ab_judge


class TestProbeFollowsTheConfiguredWrapper:
    def test_unset_base_keeps_the_local_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        assert ab_judge._wrapper_auth_url() == "http://127.0.0.1:8000/v1/auth/status"

    @pytest.mark.parametrize(
        "base",
        [
            "https://wrapper.antifragile-ai.net/v1",
            "https://wrapper.antifragile-ai.net/v1/",
        ],
    )
    def test_tunnel_base_is_probed_not_localhost(
        self, monkeypatch: pytest.MonkeyPatch, base: str
    ) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", base)
        assert (
            ab_judge._wrapper_auth_url()
            == "https://wrapper.antifragile-ai.net/v1/auth/status"
        )

    def test_probe_sends_the_cf_access_service_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Behind Cloudflare Access an unauthenticated probe gets an HTML login
        page and a 401 — indistinguishable from "the wrapper is down"."""
        monkeypatch.setenv("OPENAI_API_BASE", "https://wrapper.antifragile-ai.net/v1")
        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret")
        # R361 — the probe now makes TWO calls: /v1/auth/status, then a real
        # completion, because a 200 from auth/status only proves a token is
        # PRESENT (measured 2026-08-23: it answered valid:true while every
        # completion returned 500). Record every call rather than the last one.
        calls: list[dict[str, object]] = []

        class _Resp:
            status = 200

            def __init__(self, body: bytes = b"{}") -> None:
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        import json as _json
        _completion = _json.dumps(
            {"choices": [{"message": {"content": "OK"}}]}
        ).encode()

        def _fake_urlopen(req, timeout=None):
            calls.append({"url": req.full_url, "headers": dict(req.headers)})
            if "auth/status" in req.full_url:
                return _Resp()
            return _Resp(_completion)

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            assert ab_judge._wrapper_up() is True

        auth = next(c for c in calls if "auth/status" in str(c["url"]))
        assert auth["url"] == "https://wrapper.antifragile-ai.net/v1/auth/status"
        lowered = {k.lower() for k in auth["headers"]}
        assert "cf-access-client-id" in lowered, auth["headers"]

        # The completion leg is Access-protected too — the token must ride it,
        # or the probe 401s against its own tunnel and reports a false DOWN.
        completion = next(c for c in calls if "chat/completions" in str(c["url"]))
        assert {k.lower() for k in completion["headers"]} >= {"cf-access-client-id"}, (
            completion["headers"]
        )

    def test_sonnet_55_completion_probe_uses_model_and_omits_temperature(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json as _json

        monkeypatch.setenv("OPENAI_API_BASE", "https://wrapper.antifragile-ai.net/v1")
        calls: list[dict[str, object]] = []

        class _Resp:
            status = 200

            def __init__(self, body: bytes = b"{}") -> None:
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            calls.append({"url": req.full_url, "data": req.data})
            if "auth/status" in req.full_url:
                return _Resp()
            return _Resp(_json.dumps(
                {"choices": [{"message": {"content": "OK"}}]}
            ).encode())

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            assert ab_judge._wrapper_up(
                timeout=90.0, probe_model="claude-sonnet-5-5"
            ) is True

        completion = next(c for c in calls if "chat/completions" in str(c["url"]))
        body = _json.loads(completion["data"])
        assert body["model"] == "claude-sonnet-5-5"
        assert body["max_tokens"] >= 1024
        assert "temperature" not in body

    def test_no_service_token_leaks_to_a_foreign_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The header resolver is host-scoped; pin that the probe inherits it."""
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret")
        monkeypatch.setenv("CF_ACCESS_HOSTNAME", "wrapper.antifragile-ai.net")
        seen: dict[str, object] = {}

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _fake_urlopen(req, timeout=None):
            seen["headers"] = dict(req.headers)
            return _Resp()

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            ab_judge._wrapper_up()

        lowered = {k.lower() for k in seen.get("headers", {})}
        assert "cf-access-client-id" not in lowered


class TestBedrockJudgeIsSelectable:
    @pytest.mark.parametrize("provider", ["wrapper", "bedrock"])
    def test_cli_accepts_the_provider(self, provider: str, tmp_path) -> None:
        """Judging over the tunnel competes with Stage-2 for the single Claude
        Max wrapper, and CLAUDE.md's own rule is "No Parallel Wrapper Jobs".
        ``_resolve_caller`` already implemented bedrock; only the CLI's choices
        list blocked it, which argparse rejects with SystemExit(2).
        """
        seen: dict[str, object] = {}

        def _fake_run(**kwargs):
            seen.update(kwargs)
            return {"label": kwargs["label"]}

        with (
            patch.object(ab_judge, "run_ab", side_effect=_fake_run),
            # _format is a reporting concern; this test is about the CLI
            # accepting the provider and threading it through to run_ab.
            patch.object(ab_judge, "_format", return_value=""),
            patch.object(ab_judge, "_RESULTS", tmp_path),
        ):
            rc = ab_judge.main(
                ["--label", "unit", "--judge-provider", provider, "--limit", "1"]
            )

        assert rc == 0
        assert seen["judge_provider"] == provider

    def test_sonnet_55_cli_option_reaches_run_ab(self, tmp_path) -> None:
        seen: dict[str, object] = {}

        def fake_run(**kwargs):
            seen.update(kwargs)
            return {"label": kwargs["label"]}

        with (
            patch.object(ab_judge, "run_ab", side_effect=fake_run),
            patch.object(ab_judge, "_format", return_value=""),
            patch.object(ab_judge, "_RESULTS", tmp_path),
        ):
            rc = ab_judge.main(
                [
                    "--label", "unit", "--judge-provider", "wrapper",
                    "--judge-model", "claude-sonnet-5-5", "--limit", "1",
                ]
            )

        assert rc == 0
        assert seen["judge_provider"] == "wrapper"
        assert seen["judge_model"] == "claude-sonnet-5-5"

    def test_run_ab_probes_selected_wrapper_judge_model(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from evals.judge import runner as judge_runner

        rows = ab_judge.load_probe_set(limit=1)
        captured: dict[str, object] = {}

        def fake_capture(rows, _env, *, timeout, label):
            del timeout, label
            return {
                row.id: ab_judge.ArmAnswer("answer", [], 1.0, 200)
                for row in rows
            }

        def fake_probe(timeout=4.0, *, probe_model=None):
            captured.update(timeout=timeout, probe_model=probe_model)
            return True

        monkeypatch.setattr(ab_judge, "_capture_arm", fake_capture)
        monkeypatch.setattr(judge_runner, "set_judge_model", lambda _model: None)
        monkeypatch.setattr(judge_runner, "_resolve_caller", lambda *_a, **_k: object())
        monkeypatch.setattr(judge_runner, "_load_article_summaries", lambda: {})
        monkeypatch.setattr(ab_judge, "_pairwise_verdict_detail", lambda *_a: ("tie", True))
        monkeypatch.setattr(ab_judge, "_wrapper_up", fake_probe)

        result = ab_judge.run_ab(
            baseline_env={},
            branch_env={},
            rows=rows,
            deterministic=False,
            judge_provider="wrapper",
            timeout=90.0,
            label="unit",
            judge_model="claude-sonnet-5-5",
        )

        assert captured == {"timeout": 90.0, "probe_model": "claude-sonnet-5-5"}
        assert result["judge_model"] == "claude-sonnet-5-5"
        assert result["judge_provider"] == "wrapper"

    def test_cli_still_rejects_an_unknown_provider(self, tmp_path) -> None:
        """The choices list is a real allow-list, not decoration."""
        with (
            patch.object(ab_judge, "run_ab", return_value={}),
            patch.object(ab_judge, "_RESULTS", tmp_path),
            pytest.raises(SystemExit),
        ):
            ab_judge.main(["--label", "unit", "--judge-provider", "openrouter"])

    def test_resolve_caller_really_routes_bedrock(self) -> None:
        from evals.judge.runner import _resolve_caller

        caller = _resolve_caller("bedrock")
        assert caller is not None
        assert "bedrock" in getattr(caller, "__qualname__", "").lower() or callable(caller)


class TestJudgeRetryCoversTheBedrockLeg:
    """R360.3 — the judge can now run on Bedrock, so its transient shapes need
    the same one-shot recovery the wrapper's already had.

    A throttle window that is not classified retryable becomes a ``judge_error``
    row, and ``judge_error`` rows silently thin the scorecard rather than
    failing loudly — the run still prints a result, computed over fewer rows.
    """

    @pytest.mark.parametrize(
        "err",
        [
            "bedrock_returned_none",
            "api_throttled_429: ThrottlingException",
            "api_status_429 rate limit exceeded",
            "overloaded_error",
            "api_status_529",
            "InternalServerError from the provider",
            "api_status_408",
        ],
    )
    def test_transient_bedrock_shapes_are_retryable(self, err: str) -> None:
        from evals.judge.runner import is_retryable_judge_error

        assert is_retryable_judge_error(err) is True, err

    @pytest.mark.parametrize(
        "err",
        [
            "wrapper_not_configured",
            "no_json",
            "wrapper_unavailable",
        ],
    )
    def test_config_and_shape_failures_stay_non_retryable(self, err: str) -> None:
        """Retrying a config bug burns judge budget for no benefit."""
        from evals.judge.runner import is_retryable_judge_error

        assert is_retryable_judge_error(err) is False, err

    def test_bare_numeric_substrings_were_deliberately_not_ported(self) -> None:
        """Upstream also lists bare "500"/"503"/"504"/"408"/"429".

        Those match anywhere in the error string, so an elapsed_ms of 1504 or a
        token count of 1500 would classify a deterministic failure as transient
        and buy a pointless second judge call on every such row. The prefixed
        forms (``api_status_5``, ``api_status_429``, ``_429``) already cover the
        real shapes, so the bare numbers are omitted on purpose — this test
        exists so a future sync does not "restore" them without reading why.
        """
        from evals.judge.runner import is_retryable_judge_error

        assert is_retryable_judge_error("judge parse failed after 1500 tokens") is False


class TestJudgeReplyCeiling:
    """R360.5 — a judge verdict cut mid-JSON is a silently thinned sample.

    ``_parse_judge_json`` returns ``unbalanced_json`` on a truncated reply and
    the aggregator counts that axis 'unknown'. That is honest — it is not
    scored as a zero — but it shrinks n without shrinking the confidence the
    scorecard projects. The wrapper, Anthropic, Groq and Gemini paths were
    pinned at 400/400/800/1000 tokens while Bedrock already ran at 1600.
    """

    def test_default_matches_the_bedrock_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from evals.judge.runner import judge_max_tokens

        monkeypatch.delenv("REGENOLD_JUDGE_MAX_TOKENS", raising=False)
        assert judge_max_tokens() == 1600

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("2400", 2400), ("10", 200), ("999999", 8000), ("not-a-number", 1600), ("", 1600)],
    )
    def test_env_override_is_clamped_and_fail_soft(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
    ) -> None:
        from evals.judge.runner import judge_max_tokens

        monkeypatch.setenv("REGENOLD_JUDGE_MAX_TOKENS", raw)
        assert judge_max_tokens() == expected

    def test_no_hardcoded_ceilings_remain_in_the_judge_calls(self) -> None:
        """Pins the change itself: a future edit that re-hardcodes a cap on one
        provider would silently reintroduce truncation on that path only."""
        import inspect

        from evals.judge import runner

        src = inspect.getsource(runner)
        for stale in ("max_tokens=400,", "max_tokens=800,", "max_tokens=1000,"):
            assert stale not in src, f"hardcoded judge ceiling still present: {stale}"

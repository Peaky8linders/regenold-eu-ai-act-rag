"""R407 — deep-code-review tripwires for the Cohere retry layer.

Finds verified by the R407 review (docs/reviews/):
* both Cohere clients did ONE POST per logical call, so a single transient
  429/5xx silently degraded retrieval — and under a fail-closed eval guard it
  killed the whole 110-row capture (r406 died twice on exactly this);
* ``--resume`` crashed on a truncated final checkpoint line with a raw
  JSONDecodeError instead of the runner's clean RuntimeError.
"""
from __future__ import annotations

import httpx
import pytest

from app.engines import _http_retry
from app.engines._http_retry import post_transient_retry


class _Resp:
    def __init__(self, status_code: int, retry_after: str | None = None):
        self.status_code = status_code
        self.headers = {"Retry-After": retry_after} if retry_after else {}
        self.text = ""


def test_transient_429_is_retried_to_success():
    calls = {"n": 0}

    def post():
        calls["n"] += 1
        return _Resp(429) if calls["n"] == 1 else _Resp(200)

    assert post_transient_retry(post, max_attempts=3, log_prefix="t").status_code == 200
    assert calls["n"] == 2


def test_permanent_4xx_is_not_retried():
    calls = {"n": 0}

    def post():
        calls["n"] += 1
        return _Resp(403)

    resp = post_transient_retry(post, max_attempts=3, log_prefix="t")
    assert resp.status_code == 403
    assert calls["n"] == 1


def test_exception_then_success_recovers():
    calls = {"n": 0}

    def post():
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return _Resp(200)

    resp = post_transient_retry(post, max_attempts=3, log_prefix="t")
    assert resp is not None and resp.status_code == 200
    assert calls["n"] == 2


def test_retry_after_hint_is_capped():
    assert _http_retry.delay_seconds("99", 1) == 20.0
    assert _http_retry.delay_seconds("0.5", 1) == 0.5


def test_attempts_ceiling_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("X_RETRIES", "0")
    assert _http_retry.attempts_from_env("X_RETRIES", 3) == 1
    monkeypatch.setenv("X_RETRIES", "99")
    assert _http_retry.attempts_from_env("X_RETRIES", 3) == 5
    monkeypatch.setenv("X_RETRIES", "garbage")
    assert _http_retry.attempts_from_env("X_RETRIES", 3) == 3


def test_rerank_client_retries_transient(monkeypatch: pytest.MonkeyPatch):
    """One 500 then a 200 must land a result, not drop the call."""
    from app.engines import cohere_rerank as CR

    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    monkeypatch.delenv("REGENOLD_COHERE_RERANK_MODEL", raising=False)

    class _Client:
        calls = {"n": 0}

        @staticmethod
        def post(_url, **_kw):
            _Client.calls["n"] += 1
            if _Client.calls["n"] == 1:
                return _Resp(500)
            return type(
                "R",
                (),
                {
                    "status_code": 200,
                    "headers": {},
                    "text": "",
                    "json": staticmethod(
                        lambda: {
                            "results": [
                                {"index": 1, "relevance_score": 0.9},
                                {"index": 0, "relevance_score": 0.1},
                            ]
                        }
                    ),
                },
            )()

    monkeypatch.setattr(CR, "_get_client", lambda: _Client())
    CR.reset_request_budget()
    CR.reset_rerank_stats()
    out = CR.rerank_documents("q", ["a", "b"])
    assert out == [(1, 0.9), (0, 0.1)]
    assert _Client.calls["n"] == 2


def test_resume_rejects_corrupt_line_cleanly(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A half-written final line must raise the runner's RuntimeError."""
    import json

    from evals.regenold import run_official_batch as rob

    ckpt = tmp_path / "official-x-hard.ckpt.jsonl"
    good = {"id": "rg_001", "mode": "hard", "pred_answer": "a"}
    ckpt.write_text(
        json.dumps(good) + "\n" + '{"id": "rg_002", "mod', encoding="utf-8"
    )

    class _Rows:
        id = "rg_002"

    monkeypatch.setattr(rob, "_RESULTS", tmp_path)
    with pytest.raises(RuntimeError, match="truncated or corrupt JSON line"):
        rob._arm(
            "x", "hard", [_Rows()],
            poster=lambda *a, **k: (None, 0, 0, "unused", 0, None),
            url="", api_key="", timeout=1.0,
            arm_env={}, suffix="", resume=True,
        )

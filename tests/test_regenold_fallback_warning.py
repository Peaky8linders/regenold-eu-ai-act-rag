"""Degraded-mode ``warning`` field regression guards.

When Stage-2 LLM synthesis (Claude Max via the Cloudflare tunnel) is
attempted but the wrapper call fails — tunnel down, Claude Max auth
expired, 429 exhaustion, network error, or structural truncation — the
engine ships the deterministic Stage-1 answer and sets
``graph_stats["stage2_call_failed"] = True`` (see
``app/engines/graph_rag.py`` ~line 6427).

The route surfaces a non-fatal ``warning`` string on the wire so
Regenold can tell a degraded (deterministic-fallback) answer from a
fully LLM-polished one. The ``answer`` + ``references`` remain grounded
in the EU AI Act — only the LLM refinement is absent.

CRITICAL invariant: a HEALTHY response carries NO ``warning`` key at
all (the route serialises with ``response_model_exclude_none=True``), so
the happy-path JSON Regenold normally receives is byte-identical to
before this feature.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.models import CitationNode, GraphRAGResponse


def _client() -> TestClient:
    return TestClient(app)


def _messages(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


def _headers() -> dict[str, str]:
    return {"X-Regenold-Api-Key": "regenold-test-key"}


@pytest.fixture(autouse=True)
def _configure_key_and_clear_cache():
    """Valid partner key + a clean engine LRU between tests.

    The route's ``_ENGINE_CACHE`` keys on ``(question, system_context, …)``;
    clearing it keeps a mocked engine return value from being masked by a
    prior test's cached blob under the same key.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415

    with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
        _ENGINE_CACHE._data.clear()  # type: ignore[attr-defined]
    yield


def _cited_response(*, stage2_call_failed: bool) -> GraphRAGResponse:
    """A healthy, cited answer — optionally flagged as a Stage-2 fallback.

    ``stage2_call_failed=True`` mimics the exact engine state after the
    wrapper call fails and the deterministic Stage-1 answer is shipped.
    ``stage2_call_failed=False`` (with ``stage2_landed=True``) mimics a
    normal, fully-polished answer.
    """
    return GraphRAGResponse(
        answer=(
            "Article 13 requires high-risk AI providers to design "
            "transparency mechanisms so deployers can interpret outputs."
        ),
        citations=[
            CitationNode(
                node_type="Article",
                node_id="art-13",
                text="Transparency obligations.",
                article_ref="Art. 13",
            ),
        ],
        confidence=0.7,
        graph_stats={
            "nodes_traversed": 2,
            "stage2_call_failed": stage2_call_failed,
            "stage2_landed": not stage2_call_failed,
        },
    )


class TestFallbackWarningWire:
    """End-to-end: the ``warning`` key on the actual Regenold wire JSON."""

    def test_warning_present_when_stage2_call_failed(self) -> None:
        resp = _cited_response(stage2_call_failed=True)
        with patch(
            "app.routes.regenold.ask_compliance_question", return_value=resp
        ):
            r = _client().post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=_messages("What does Article 13 require?"),
            )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert "warning" in body, (
            f"a degraded-mode fallback must surface a warning; got keys "
            f"{sorted(body)}"
        )
        assert isinstance(body["warning"], str) and body["warning"].strip()
        # The spec fields are still present + intact.
        assert body["answer"], "answer must survive the fallback"
        assert body["references"], "references must survive the fallback"

    def test_no_warning_key_on_healthy_response(self) -> None:
        """The happy path must be byte-identical: NO ``warning`` key."""
        resp = _cited_response(stage2_call_failed=False)
        with patch(
            "app.routes.regenold.ask_compliance_question", return_value=resp
        ):
            r = _client().post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=_messages("What does Article 13 require?"),
            )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert "warning" not in body, (
            f"a healthy response must NOT carry a warning key; got "
            f"{body.get('warning')!r}"
        )

    def test_warning_coexists_with_telemetry_block(self) -> None:
        resp = _cited_response(stage2_call_failed=True)
        with patch(
            "app.routes.regenold.ask_compliance_question", return_value=resp
        ):
            r = _client().post(
                "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
                headers=_headers(),
                json=_messages("What does Article 13 require?"),
            )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body.get("warning"), "warning must be present under telemetry too"
        assert "confidence" in body, "telemetry block must still be present"

    def test_env_gate_off_suppresses_warning(self) -> None:
        """``REGENOLD_FALLBACK_WARNING=0`` reverts to no-warning behaviour."""
        resp = _cited_response(stage2_call_failed=True)
        with patch.dict(os.environ, {"REGENOLD_FALLBACK_WARNING": "0"}):
            with patch(
                "app.routes.regenold.ask_compliance_question", return_value=resp
            ):
                r = _client().post(
                    "/api/v1/regenold/eu-ai-act/ask",
                    headers=_headers(),
                    json=_messages("What does Article 13 require?"),
                )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert "warning" not in body, (
            "env-gate OFF must suppress the warning entirely"
        )


class TestFallbackWarningModel:
    """Pydantic-level: the field defaults to None and is exclude_none-safe."""

    def test_warning_defaults_none_and_excluded(self) -> None:
        from app.integrations.regenold.models import RegenoldAskResponse

        out = RegenoldAskResponse(answer="x", references=["Article 13"])
        assert out.warning is None
        dumped = out.model_dump(exclude_none=True)
        assert "warning" not in dumped

    def test_warning_serialises_when_set(self) -> None:
        from app.integrations.regenold.models import RegenoldAskResponse

        out = RegenoldAskResponse(answer="x", warning="degraded")
        dumped = out.model_dump(exclude_none=True)
        assert dumped["warning"] == "degraded"

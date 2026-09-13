"""Exercise the route seams behind the R416 audit's disputed architecture claims."""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines import clara_logic
from app.main import app
from app.models import CitationNode, GraphRAGResponse
from app.routes import regenold as route

QUESTION = "What does Article 13 require for transparency?"


@pytest.fixture()
def seams(monkeypatch):
    monkeypatch.setattr(settings.regenold, "api_key", SecretStr("r416-test"))
    route._ENGINE_CACHE._data.clear()
    engine = Mock(return_value=GraphRAGResponse(
        answer="Article 13 requires transparency for high-risk AI systems.",
        citations=[CitationNode(node_type="Article", node_id="art-13",
                                text="Transparency", article_ref="Art. 13")],
        confidence=0.9, graph_stats={"nodes_traversed": 1},
    ))
    clara = Mock(return_value=(None, None))
    monkeypatch.setattr(route, "ask_compliance_question", engine)
    monkeypatch.setattr(clara_logic, "analyse", clara)
    yield engine, clara
    route._ENGINE_CACHE._data.clear()


def _post(messages):
    response = TestClient(app).post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "r416-test"}, json=messages,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("exchanges,expected", [(0, 0), (1, 2), (2, 4)])
def test_route_counts_messages_before_latest_question(seams, exchanges, expected):
    engine, _ = seams
    messages = []
    for _ in range(exchanges):
        messages.extend([
            {"role": "user", "content": QUESTION},
            {"role": "assistant", "content": "Article 13 concerns transparency."},
        ])
    messages.append({"role": "user", "content": QUESTION})
    _post(messages)
    engine.assert_called_once()
    assert engine.call_args.args[0].history_turn_count == expected


@pytest.mark.parametrize("enabled", [True, False])
def test_clara_has_a_reachable_default_on_route_call(monkeypatch, seams, enabled):
    _, clara = seams
    if enabled:
        monkeypatch.delenv("REGENOLD_CLARA_VERDICT", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_CLARA_VERDICT", "0")
    result = _post([{"role": "user", "content": QUESTION}])
    assert result["references"]
    assert clara.call_count == int(enabled)


def test_prohibited_emotion_monitoring_never_reaches_clara(monkeypatch, seams):
    _, clara = seams
    monkeypatch.delenv("REGENOLD_CLARA_VERDICT", raising=False)
    _post([{"role": "user", "content": (
        "Can an employer use AI to infer employees' emotions at work from their facial expressions?"
    )}])
    clara.assert_not_called()

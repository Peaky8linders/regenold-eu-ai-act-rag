"""Partner authentication must reject callers before any paid Q&A work."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.routes import regenold


@pytest.fixture(autouse=True)
def _partner_key_dependency_override():
    """Exercise the REAL key check: this module tests the auth dependency."""
    yield


@pytest.mark.parametrize(
    "configured,credential,status,code",
    [
        (True, None, 401, "regenold_api_key_missing"),
        (True, "", 401, "regenold_api_key_missing"),
        (True, "wrong", 403, "regenold_api_key_invalid"),
        (False, None, 503, "regenold_not_configured"),
        (False, "wrong", 503, "regenold_not_configured"),
    ],
)
def test_unauthorized_callers_never_reach_qa(
    monkeypatch, configured, credential, status, code,
):
    monkeypatch.setattr(
        settings.regenold, "api_key", SecretStr("containment-partner") if configured else None,
    )
    engine = Mock(side_effect=AssertionError("unauthorized caller reached Q&A"))
    monkeypatch.setattr(regenold, "ask_compliance_question", engine)
    headers = {"X-Regenold-Api-Key": credential} if credential is not None else {}
    response = TestClient(app).post(
        "/api/v1/regenold/eu-ai-act/ask", headers=headers,
        json={"messages": [{"role": "user", "content": "What does Article 13 require?"}]},
    )

    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    engine.assert_not_called()


def test_configured_partner_keeps_qa_response(monkeypatch):
    monkeypatch.setattr(settings.regenold, "api_key", SecretStr("containment-partner"))
    engine = Mock(wraps=regenold.ask_compliance_question)
    monkeypatch.setattr(regenold, "ask_compliance_question", engine)
    response = TestClient(app).post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "containment-partner"},
        json={"messages": [{"role": "user", "content": "What does Article 13 require?"}]},
    )

    assert response.status_code == 200, response.text
    assert {"answer", "references", "reasoning"} <= set(response.json())
    assert response.json()["answer"]
    engine.assert_called_once()

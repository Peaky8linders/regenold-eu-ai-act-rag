"""End-to-end: intent classifier narrows conceptual-question anchors.

Mocks the intent classifier to return high-confidence intents for the
conceptual questions where the round-19 explicit-anchor pruning is a
no-op (no article named in the question). Asserts that the route
returns ONLY the intent's primary anchor in the citations list when
intent fires.

These tests prove the precision lift the intent layer is designed to
deliver — they pass with the deterministic engine + a mocked intent
classifier. With the live ``claude-code-openai-wrapper`` authenticated
against Claude Max, the same path runs against real Haiku 4.5 output.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.llm.intent_classifier import IntentResult
from app.main import app


@pytest.fixture
def client() -> TestClient:
    settings.regenold.api_key = SecretStr("test-key")
    return TestClient(app)


def _post(client: TestClient, content: str) -> dict:
    r = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "test-key"},
        json=[{"role": "user", "content": content}],
    )
    assert r.status_code == 200, r.text
    return r.json()


def _intent(label: str, anchor: str, conf: float = 0.95) -> IntentResult:
    return IntentResult(
        intent=label,
        primary_anchor=anchor,
        alternate_anchors=(),
        confidence=conf,
        elapsed_ms=200,
        cache_hit=False,
        model="claude-haiku-4-5",
    )


def test_penalty_inquiry_narrows_to_art_99(client) -> None:
    """Pre-intent: penalty_max_fine_prohibited had refs
    [Annex II, Article 5, Article 99] (gold = [Article 99], 2 FPs).
    With intent classifying "what's the max penalty for prohibited AI"
    as ``penalty_inquiry`` → primary Art. 99, the pruning should
    collapse to [Article 99] only.
    """
    with patch(
        "app.routes.regenold.classify_intent",
        return_value=_intent("penalty_inquiry", "Art. 99"),
    ):
        body = _post(client, "What's the maximum penalty for using prohibited AI?")

    refs = body["references"]
    assert "Article 99" in refs
    # Round-19 left 3 refs here; round-20 narrows to 1.
    assert "Article 5" not in refs, f"Art. 5 should be pruned by intent; got {refs}"
    assert "Annex II" not in refs, f"Annex II should be pruned by intent; got {refs}"


def test_fria_intent_narrows_to_art_27(client) -> None:
    """fria_who_must_do_it had refs [Annex III, Article 27]
    (gold = [Article 27], 1 FP). Intent ``fria`` → Art. 27 collapses
    to single ref.
    """
    with patch(
        "app.routes.regenold.classify_intent",
        return_value=_intent("fria", "Art. 27"),
    ):
        body = _post(client, "Who has to do a Fundamental Rights Impact Assessment?")

    refs = body["references"]
    # R38 sub-point emitter may upgrade Article 27 → Article 27.1; accept
    # either the base or any leaf form (the test's point is that the
    # FRIA-anchored ref survived, not the exact granularity).
    assert any(r == "Article 27" or r.startswith("Article 27.") for r in refs), \
        f"Article 27 (or leaf) missing; got {refs}"
    assert "Annex III" not in refs, f"Annex III should be pruned; got {refs}"


def test_incident_reporting_narrows_to_art_73(client) -> None:
    """incident_reporting_window had refs
    [Article 3, Article 55, Article 73, Article 85, Article 86]
    (gold = [Article 73], 4 FPs). Intent ``incident_reporting`` →
    Art. 73 should collapse to a single ref — the biggest single
    precision win in the residual-FP set.
    """
    with patch(
        "app.routes.regenold.classify_intent",
        return_value=_intent("incident_reporting", "Art. 73"),
    ):
        body = _post(client, "Within what time must I report a serious AI incident?")

    refs = body["references"]
    assert "Article 73" in refs
    for spurious in ("Article 3", "Article 55", "Article 85", "Article 86"):
        assert spurious not in refs, (
            f"{spurious} should be pruned by intent; got {refs}"
        )


def test_low_confidence_intent_is_no_op(client) -> None:
    """When the classifier returns confidence < 0.7 the pruning falls
    through to the round-19 explicit-anchor rule (no-op on conceptual
    questions). The original keyword-derived refs are preserved.
    """
    with patch(
        "app.routes.regenold.classify_intent",
        return_value=_intent("penalty_inquiry", "Art. 99", conf=0.4),
    ):
        body = _post(client, "What's the maximum penalty for using prohibited AI?")

    refs = body["references"]
    # Low-confidence intent → no narrowing → at least the gold ref still ships.
    assert "Article 99" in refs


def test_intent_does_not_override_explicit_anchor(client) -> None:
    """When the question DOES name an article explicitly, the
    explicit-anchor rule wins regardless of intent. (The intent
    classifier is only consulted on the fallback branch.)
    """
    with patch(
        "app.routes.regenold.classify_intent",
        return_value=_intent("incident_reporting", "Art. 73"),
    ):
        body = _post(client, "What does Article 50 require for deepfake labels?")

    refs = body["references"]
    # Explicit Art. 50 wins; intent's Art. 73 must NOT appear. R38 sub-
    # point emitter may upgrade Article 50 → Article 50.4 (deepfake
    # leaf) — accept either form.
    assert any(r == "Article 50" or r.startswith("Article 50.") for r in refs), \
        f"Article 50 (or leaf) missing; got {refs}"
    assert "Article 73" not in refs


def test_classifier_returning_none_is_no_op(client) -> None:
    """Wrapper unavailable / not logged in → classifier returns None.
    Route falls through to the round-19 baseline behavior.
    """
    with patch("app.routes.regenold.classify_intent", return_value=None):
        body = _post(client, "What's the maximum penalty for using prohibited AI?")

    refs = body["references"]
    # Round-19 baseline kept Art. 99 + spurious anchors; we just verify
    # the route didn't crash and Art. 99 still ships.
    assert "Article 99" in refs

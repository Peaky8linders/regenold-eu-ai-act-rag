"""R260 — risk-framework taxonomy ships the complete closed tier-ref set.

"What are all the risk categories?" is a CLOSED-SET enumeration (four risk
tiers + the GPAI regime). The R257 intercept surfaces all five tier-refs in
the engine citations, but the QA ref budget + suppress-noise + the live
Stage-2 reconcile each dropped a varying subset (live wire shipped only 1-3
of 5). R260 re-instates the engine-surfaced canonical tier-refs as the LAST
reference pass.

NOTE: per the R139 / R-validation doctrine these are the cheap deterministic
REGRESSION-GUARD checks only. The actual MERGE GATE for this reference change
is the live pairwise ``evals.harness.ab_judge`` (refs axis) — see CLAUDE.md
"Validation policy".
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.routes.regenold import (
    _RISK_FRAMEWORK_CANON_REFS,
    _enforce_risk_framework_refs,
)

_CANON_WIRE = {"Article 5", "Article 6", "Annex III", "Article 50", "Article 51"}


def _client() -> TestClient:
    settings.regenold.api_key = SecretStr("regenold-test-key")
    return TestClient(app)


def _ask(c: TestClient, content: str) -> dict:
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=[{"role": "user", "content": content}],
    )
    assert r.status_code == 200, r.json()
    return r.json()


@pytest.mark.parametrize(
    "q",
    [
        "What are all the risk categories in the EU AI Act?",
        "Explain the risk tiers of the EU AI Act.",
        "List the risk categories under the AI Act.",
    ],
)
def test_risk_framework_ships_full_tier_set(q: str) -> None:
    body = _ask(_client(), q)
    refs = set(body["references"])
    assert _CANON_WIRE <= refs, f"missing tiers: {_CANON_WIRE - refs} (got {refs})"


def test_enforce_only_reinstates_engine_surfaced_refs() -> None:
    """Never fabricate — only re-instate refs the engine actually surfaced."""

    class _Cit:
        def __init__(self, ar: str) -> None:
            self.article_ref = ar

    class _Resp:
        citations = [_Cit("Art. 5"), _Cit("Art. 6"), _Cit("Annex III")]

    out = _enforce_risk_framework_refs(["Article 5"], _Resp())
    # Re-instates the surfaced Art. 6 + Annex III; does NOT add Art. 50 / 51
    # (not surfaced by this (truncated) engine response).
    assert out == ["Article 5", "Article 6", "Annex III"]


def test_enforce_preserves_existing_order_appends_missing() -> None:
    class _Cit:
        def __init__(self, ar: str) -> None:
            self.article_ref = ar

    class _Resp:
        citations = [_Cit(ar) for ar in _RISK_FRAMEWORK_CANON_REFS]

    out = _enforce_risk_framework_refs(["Article 6", "Article 50"], _Resp())
    assert out[:2] == ["Article 6", "Article 50"]  # existing order kept
    assert _CANON_WIRE <= set(out)  # all five present


def test_enforce_fail_soft_on_bad_response() -> None:
    out = _enforce_risk_framework_refs(["Article 5"], object())
    assert out == ["Article 5"]

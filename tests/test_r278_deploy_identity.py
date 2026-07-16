"""R278 — expose the deployed COMMIT on the health endpoints.

Why this exists: `settings.version` is a hand-bumped literal ("1.2.3"), so it
cannot answer the only question a deploy check must answer — *did the
container actually roll?* A merge that rolled and a merge that did not report
the identical `version`. Railway is known to report deploy SUCCESS without
replacing the container, and the repo's own CLAUDE.md requires verifying the
live surface. Before this, `grep -rn "RAILWAY_" app/` was empty: nothing read
Railway's injected env, so the deployed SHA was unknowable from outside.

Concretely: R276-D2 (PR #285) merged cleanly and prod answered `status: ok`,
and there was still no way to confirm the new commit was serving.

Each test pins a property that must not regress:
* the key EXISTS on both probes (a deploy check that 404s on `.commit` is
  useless);
* it defaults to "unknown" when UNSET **and when EMPTY** — Railway injecting
  an empty string must not surface as `""`, which reads as a real answer;
* the SHA is truncated to 12 — the docstring's verification recipe depends on
  that exact width;
* the probes never raise on a missing env (a health probe that 500s during an
  outage is worse than the gap it closes).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import _deploy_identity, app

_FULL_SHA = "e495f0c1a2b3c4d5e6f708192a3b4c5d6e7f8091"
_RAILWAY_ENV = ("RAILWAY_GIT_COMMIT_SHA", "RAILWAY_DEPLOYMENT_ID")


@pytest.fixture(autouse=True)
def _clean_railway_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local dev and CI have no Railway env; make that explicit, not incidental."""
    for var in _RAILWAY_ENV:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestDefaultsWhenNotOnRailway:
    """Unset / empty must read as "unknown" — never "" and never a crash."""

    def test_unset_reads_unknown(self) -> None:
        assert _deploy_identity() == {
            "commit": "unknown",
            "deployment_id": "unknown",
        }

    @pytest.mark.parametrize("blank", ["", "   ", "\n"])
    def test_empty_or_whitespace_reads_unknown(
        self, monkeypatch: pytest.MonkeyPatch, blank: str
    ) -> None:
        """The `[:12]`-on-getenv-default shape silently yields "" here.

        Railway injecting an empty var must not surface as an empty string —
        `""` looks like an answer, `"unknown"` looks like the absence of one.
        """
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", blank)
        monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", blank)
        assert _deploy_identity() == {
            "commit": "unknown",
            "deployment_id": "unknown",
        }


class TestOnRailway:
    def test_sha_is_truncated_to_twelve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """12 chars exactly — the documented verification recipe
        (`git rev-parse origin/main | cut -c1-12`) compares against this width.
        """
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", _FULL_SHA)
        commit = _deploy_identity()["commit"]
        assert commit == _FULL_SHA[:12]
        assert len(commit) == 12

    def test_sha_is_surrounding_whitespace_tolerant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", f"  {_FULL_SHA}\n")
        assert _deploy_identity()["commit"] == _FULL_SHA[:12]

    def test_deployment_id_is_passed_through_untruncated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It is an opaque handle, not a SHA — truncating it would break lookup."""
        dep = "f2f5e05f-d1eb-4be5-a12f-7a92c0130327"
        monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", dep)
        assert _deploy_identity()["deployment_id"] == dep

    def test_short_sha_is_not_padded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
        assert _deploy_identity()["commit"] == "abc123"


class TestHealthzWiring:
    """The helper is only useful if it actually reaches the wire."""

    def test_healthz_exposes_commit(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", _FULL_SHA)
        body = client.get("/healthz").json()
        assert body["commit"] == _FULL_SHA[:12]
        assert body["deployment_id"] == "unknown"

    def test_healthz_llm_exposes_commit(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", _FULL_SHA)
        body = client.get("/healthz/llm").json()
        assert body["commit"] == _FULL_SHA[:12]

    @pytest.mark.parametrize("path", ["/healthz", "/healthz/llm"])
    def test_probe_still_200s_with_no_railway_env(
        self, client: TestClient, path: str
    ) -> None:
        """A health probe must never 500 — least of all the one you reach for
        during an outage. Railway's healthcheckPath is /healthz.
        """
        r = client.get(path)
        assert r.status_code == 200
        assert r.json()["commit"] == "unknown"

    def test_version_is_still_reported(self, client: TestClient) -> None:
        """Additive only — `version` has existing consumers."""
        body = client.get("/healthz").json()
        assert "version" in body
        assert body["status"] == "ok"

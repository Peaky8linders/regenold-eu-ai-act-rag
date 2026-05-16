"""Tests for /healthz/graph — operator-visible Neo4j health surface.

The endpoint must:
  * Always return HTTP 200 (uptime monitors alert on ``graph_ok=False``,
    not on HTTP status — a downed graph should not flap the uptime page
    when the engine's deterministic fallback is still serving requests).
  * Distinguish three paths: disabled (no NEO4J_URI), unhealthy (driver
    connects but ping fails), healthy (full stats).
  * Surface seed_version + node/edge counts when healthy so an operator
    can verify the KB seed actually loaded.
  * Never raise — every exception from the graph client is caught and
    surfaced as ``graph_ok=False`` with a truncated error string.
  * Conform to the same response shape in all three paths (so monitor
    JSON parsers don't have to handle missing keys).
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


# Keys every response must carry — operators / uptime monitors can rely
# on this shape regardless of which path the probe took.
_EXPECTED_KEYS = frozenset({
    "version",
    "graph_enabled",
    "graph_ok",
    "detail",
    "elapsed_ms",
    "seed_version",
    "kb_version",
    "node_counts",
    "edge_counts",
})


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient with all relevant env stripped + the graph
    singleton reset so each test starts from a known state."""
    for k in (
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
        "NEO4J_ENABLED",
        "P2P_GRAPH_RAG_PROVIDER",
        "P2P_GRAPH_RAG_API_KEY",
        "MISTRAL_API_KEY",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")

    # Drop any cached graph client so each test reads fresh env.
    from app.graph import client as _gc_module
    _gc_module._reset_singleton_for_tests()

    from app.main import app
    test_client = TestClient(app)
    yield test_client

    # Clean up — defensive — so a test that mocks the client doesn't
    # leak into the next module.
    _gc_module._reset_singleton_for_tests()


# ─── Shape invariants ────────────────────────────────────────────────────────


class TestResponseShape:
    """Every response, regardless of path, must carry the full key set."""

    def test_disabled_path_has_all_keys(self, client: TestClient) -> None:
        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert _EXPECTED_KEYS.issubset(set(body.keys())), (
            f"missing keys: {_EXPECTED_KEYS - set(body.keys())}"
        )

    def test_kb_version_always_populated(self, client: TestClient) -> None:
        """Even on the disabled path the operator should see which KB
        the bundle was built with — the in-process ``KB_VERSION``."""
        from app.data.kb import KB_VERSION
        r = client.get("/healthz/graph")
        assert r.json()["kb_version"] == KB_VERSION


# ─── Disabled path: no NEO4J_URI ─────────────────────────────────────────────


class TestDisabledPath:
    def test_no_env_returns_graph_enabled_false(
        self, client: TestClient
    ) -> None:
        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert body["graph_enabled"] is False
        assert body["graph_ok"] is False
        assert "NEO4J_URI" in body["detail"]
        # No counts to report — sane empty defaults.
        assert body["node_counts"] == {}
        assert body["edge_counts"] == {}
        assert body["seed_version"] == ""

    def test_returns_http_200(self, client: TestClient) -> None:
        """Uptime monitors must see 200 even when the graph is off."""
        r = client.get("/healthz/graph")
        assert r.status_code == 200


# ─── Unhealthy path: connection fails / ping errors ──────────────────────────


class _FakeGraphClient:
    """Stand-in for ``GraphClient`` used in tests.

    Lets each test pin ``enabled`` + the ``health_check`` payload + the
    canned read responses without spinning up a real Neo4j driver. The
    real client's public API surface used by the route is:
    ``enabled``, ``health_check()``, ``execute_read(query, params)``.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        health: dict[str, Any] | None = None,
        health_exc: BaseException | None = None,
        read_responses: dict[str, Any] | None = None,
        read_exc: BaseException | None = None,
    ) -> None:
        self._enabled = enabled
        self._health = health or {"status": "healthy", "ping": 1}
        self._health_exc = health_exc
        self._read_responses = read_responses or {}
        self._read_exc = read_exc

    @property
    def enabled(self) -> bool:
        return self._enabled

    def health_check(self) -> dict[str, Any]:
        if self._health_exc is not None:
            raise self._health_exc
        return self._health

    def execute_read(
        self, query: str, parameters: dict | None = None
    ) -> list[dict[str, Any]]:
        if self._read_exc is not None:
            raise self._read_exc
        # Match on a discriminating fragment of each Cypher we expect.
        if "KBMetadata" in query:
            return self._read_responses.get("metadata", [])
        if "RETURN type(r)" in query:
            return self._read_responses.get("edges", [])
        # Per-label count: ``MATCH (n:<Label>) RETURN count(n) AS cnt``
        for label, rows in self._read_responses.get("labels", {}).items():
            if f"(n:{label})" in query:
                return rows
        return []


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeGraphClient
) -> None:
    """Patch ``get_graph_client`` in ``app.main`` to return the fake.

    The route does ``from app.graph.client import ... get_graph_client``
    inside the handler, so we patch the source module — that's what the
    import binding resolves against on every call.
    """
    from app.graph import client as _gc_module
    monkeypatch.setattr(_gc_module, "get_graph_client", lambda: fake)


class TestUnhealthyPath:
    def test_uri_set_but_driver_inactive(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``NEO4J_URI`` is set but ``client.enabled`` is False —
        driver missing or connection refused at __init__ time."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(enabled=False)
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert body["graph_enabled"] is False
        assert body["graph_ok"] is False
        assert "graph_disabled" in body["detail"]
        assert body["elapsed_ms"] >= 0

    def test_health_check_returns_unhealthy(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Driver active but ``RETURN 1 AS ping`` failed under the hood."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "unhealthy", "error": "boom"},
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert body["graph_enabled"] is True
        assert body["graph_ok"] is False
        assert "unhealthy" in body["detail"]
        assert "boom" in body["detail"]
        assert body["elapsed_ms"] >= 0

    def test_health_check_raises(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An exception inside ``health_check`` must NOT propagate — it
        surfaces as ``graph_ok=False`` with a truncated error string."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health_exc=RuntimeError("simulated driver explosion"),
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert body["graph_enabled"] is True
        assert body["graph_ok"] is False
        assert "health_check_exception" in body["detail"]
        assert "simulated driver explosion" in body["detail"]

    def test_detail_is_truncated_at_200_chars(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A huge upstream error must not blow up the response."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "unhealthy", "error": "x" * 5000},
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        body = r.json()
        assert len(body["detail"]) <= 200


# ─── Healthy path: full stats ────────────────────────────────────────────────


class TestHealthyPath:
    def test_healthy_returns_full_payload(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "healthy", "ping": 1},
            read_responses={
                "metadata": [{
                    "seed_version": "2026-05-16-r35",
                    "kb_version": "2026.05.16.v3",
                }],
                "labels": {
                    "Article": [{"cnt": 113}],
                    "Obligation": [{"cnt": 113}],
                    "AnnexIIICategory": [{"cnt": 8}],
                    "KBMetadata": [{"cnt": 1}],
                    # Labels that report zero — should be dropped from the
                    # response to keep it readable.
                    "Dimension": [{"cnt": 0}],
                    "RoadmapTask": [{"cnt": 0}],
                },
                "edges": [
                    {"rel_type": "HAS_OBLIGATION", "cnt": 113},
                    {"rel_type": "CROSS_REFERENCES", "cnt": 142},
                    # Same drop-zero rule for edges.
                    {"rel_type": "DEAD", "cnt": 0},
                ],
            },
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert body["graph_enabled"] is True
        assert body["graph_ok"] is True
        assert body["detail"] == "ok"
        assert body["seed_version"] == "2026-05-16-r35"
        # Seed-recorded ``kb_version`` overrides the in-process default —
        # operators want to see the seed's version when it differs.
        assert body["kb_version"] == "2026.05.16.v3"
        assert body["node_counts"]["Article"] == 113
        assert body["node_counts"]["Obligation"] == 113
        assert body["node_counts"]["AnnexIIICategory"] == 8
        # Zero-count labels are filtered.
        assert "Dimension" not in body["node_counts"]
        assert "RoadmapTask" not in body["node_counts"]
        assert body["edge_counts"]["HAS_OBLIGATION"] == 113
        assert body["edge_counts"]["CROSS_REFERENCES"] == 142
        assert "DEAD" not in body["edge_counts"]
        assert body["elapsed_ms"] >= 0

    def test_healthy_with_missing_metadata(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A graph that's reachable but has no ``KBMetadata`` node yet
        (e.g. between connect + first seed run) should still report
        healthy — seed_version just stays empty + kb_version falls back."""
        from app.data.kb import KB_VERSION
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "healthy", "ping": 1},
            read_responses={
                "metadata": [],
                "labels": {"Article": [{"cnt": 113}]},
                "edges": [],
            },
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        body = r.json()
        assert body["graph_ok"] is True
        assert body["seed_version"] == ""
        # No seed-recorded version — fall back to in-process KB_VERSION.
        assert body["kb_version"] == KB_VERSION
        assert body["node_counts"]["Article"] == 113

    def test_elapsed_ms_populated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "healthy", "ping": 1},
            read_responses={
                "metadata": [{"seed_version": "test", "kb_version": "test"}],
                "labels": {"Article": [{"cnt": 1}]},
                "edges": [{"rel_type": "X", "cnt": 1}],
            },
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        body = r.json()
        # Probe is fast (mocked, no I/O) but the field MUST be present
        # and non-negative. Operators alert on elapsed_ms p95 > N to
        # catch driver hangs.
        assert isinstance(body["elapsed_ms"], int)
        assert body["elapsed_ms"] >= 0


# ─── Exception safety: probe must NEVER 500 ──────────────────────────────────


class TestExceptionSafety:
    def test_get_graph_client_raises(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure when CONSTRUCTING the client must not crash the route."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")

        from app.graph import client as _gc_module
        def _boom() -> object:
            raise RuntimeError("init exploded")
        monkeypatch.setattr(_gc_module, "get_graph_client", _boom)

        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert body["graph_ok"] is False
        assert "graph_client_init_failed" in body["detail"]

    def test_execute_read_raises_during_label_count(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Per-label count failures shouldn't tank the whole probe —
        ``health_check`` already said healthy, so we report graph_ok=True
        with whatever counts we could collect. The current implementation
        relies on ``execute_read`` itself swallowing driver errors, but
        we belt-and-brace it here: an exception thrown directly back
        from the fake must be caught at the route level too."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "healthy", "ping": 1},
            read_exc=RuntimeError("read blew up"),
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        # health_check said healthy, so graph_ok stays true even when
        # the optional stats queries fail.
        assert body["graph_ok"] is True
        assert body["node_counts"] == {}
        assert body["edge_counts"] == {}


# ─── HTTP-status invariant across every path ─────────────────────────────────


def test_http_200_in_all_paths(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single roll-up that exercises each path and asserts 200 throughout."""
    # 1. Disabled
    r = client.get("/healthz/graph")
    assert r.status_code == 200

    # 2. Unhealthy
    monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
    fake_unhealthy = _FakeGraphClient(
        enabled=True, health={"status": "unhealthy", "error": "x"}
    )
    _patch_client(monkeypatch, fake_unhealthy)
    r = client.get("/healthz/graph")
    assert r.status_code == 200

    # 3. Healthy
    fake_healthy = _FakeGraphClient(
        enabled=True,
        health={"status": "healthy", "ping": 1},
        read_responses={
            "metadata": [{"seed_version": "v1", "kb_version": "v1"}],
            "labels": {"Article": [{"cnt": 113}]},
            "edges": [{"rel_type": "REQUIRES", "cnt": 50}],
        },
    )
    _patch_client(monkeypatch, fake_healthy)
    r = client.get("/healthz/graph")
    assert r.status_code == 200
    assert r.json()["graph_ok"] is True

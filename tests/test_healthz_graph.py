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
        # R63-F — record every Cypher passed through so tests can assert
        # that missing-label queries never fired.
        self.read_queries: list[str] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def health_check(self) -> dict[str, Any]:
        if self._health_exc is not None:
            raise self._health_exc
        return self._health

    def existing_labels(
        self, allowlist: frozenset[str] | set[str]
    ) -> set[str]:
        """R64 — mirror of ``GraphClient.existing_labels`` so the route
        + ``get_stats`` paths share a fake surface.

        Delegates to ``execute_read("CALL db.labels()...")`` so existing
        tests that pin ``read_responses["db_labels"]`` (or seed the
        ``labels`` dict) keep working. On any exception, falls back to
        the safe-fallback subset intersected with the allowlist — same
        contract as the real helper.
        """
        if not self._enabled:
            return set()
        try:
            rows = self.execute_read(
                "CALL db.labels() YIELD label RETURN label"
            )
            existing = {r["label"] for r in rows if r.get("label")}
            return set(allowlist) & existing
        except Exception:
            safe_fallback = {
                "Article",
                "Obligation",
                "KBMetadata",
                "RiskLevel",
                "AnnexIIICategory",
            }
            return set(allowlist) & safe_fallback

    def execute_read(
        self, query: str, parameters: dict | None = None
    ) -> list[dict[str, Any]]:
        self.read_queries.append(query)
        if self._read_exc is not None:
            raise self._read_exc
        # Match on a discriminating fragment of each Cypher we expect.
        # R63-F — ``CALL db.labels()`` probe (added so the route only
        # counts labels that actually exist in the graph). Tests can pin
        # a specific label set via ``read_responses["db_labels"]``;
        # otherwise the fake reflects every label that has count data
        # so existing tests stay green.
        if "db.labels()" in query:
            if "db_labels" in self._read_responses:
                return self._read_responses["db_labels"]
            labels = self._read_responses.get("labels", {})
            return [{"label": label_name} for label_name in labels]
        if "RETURN type(r)" in query:
            return self._read_responses.get("edges", [])
        # Per-label count check FIRST — ``MATCH (n:<Label>) RETURN
        # count(n) AS cnt`` shares the ``KBMetadata`` substring with the
        # metadata-row query below, so the ``(n:LABEL)`` pattern must win
        # to avoid the count query being shadowed by the metadata branch.
        for label, rows in self._read_responses.get("labels", {}).items():
            if f"(n:{label})" in query:
                return rows
        if "KBMetadata" in query:
            return self._read_responses.get("metadata", [])
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


# ─── R63-F: only-count-existing-labels (eliminates Neo4j UNRECOGNIZED noise) ──


class TestR63FOnlyCountExistingLabels:
    """The route must only run ``MATCH (n:LABEL) RETURN count(n)`` queries
    for labels that actually exist in ``db.labels()``.

    Pre-R63-F the route looped over the full ``_STATS_LABELS`` allowlist
    and fired a count query per entry — for labels the Regenold seeder
    doesn't populate (``Dimension`` / ``Question`` / ``RoadmapTask`` /
    ``NISTSubcategory`` / ``ISOClause``), Neo4j 5.x returned a
    ``GqlStatusObject(gql_status='01N50', classification=UNRECOGNIZED)``
    warning per query, which the Python driver bubbles up to the
    application logger as ``[error]``. Pure log noise, but ugly enough
    to mask real driver errors in operator dashboards.
    """

    def test_only_existing_labels_get_counted(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``db.labels()`` reports a subset of the allowlist → only that
        subset gets ``MATCH (n:LABEL)`` queries."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        # The graph carries only Article + Obligation + KBMetadata.
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "healthy", "ping": 1},
            read_responses={
                "db_labels": [
                    {"label": "Article"},
                    {"label": "Obligation"},
                    {"label": "KBMetadata"},
                ],
                "metadata": [{"seed_version": "r63f", "kb_version": "v5"}],
                "labels": {
                    "Article": [{"cnt": 113}],
                    "Obligation": [{"cnt": 113}],
                    "KBMetadata": [{"cnt": 1}],
                    # These have count data in the fake but should NOT be
                    # queried — they're not in db.labels().
                    "Question": [{"cnt": 999}],
                    "RoadmapTask": [{"cnt": 999}],
                    "ISOClause": [{"cnt": 999}],
                },
                "edges": [{"rel_type": "HAS_OBLIGATION", "cnt": 113}],
            },
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        assert r.status_code == 200
        body = r.json()
        assert body["graph_ok"] is True
        # Only the live labels surfaced.
        assert set(body["node_counts"].keys()) == {
            "Article", "Obligation", "KBMetadata",
        }
        # Critical: no count query fired for missing labels.
        for missing in ("Question", "RoadmapTask", "ISOClause",
                        "Dimension", "NISTSubcategory"):
            for q in fake.read_queries:
                assert f"(n:{missing})" not in q, (
                    f"R63-F regression: route queried missing label "
                    f"{missing!r} via {q!r}"
                )

    def test_db_labels_probe_runs_exactly_once(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ``CALL db.labels()`` probe is the cheap discriminator;
        firing it more than once per request would defeat the savings."""
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        fake = _FakeGraphClient(
            enabled=True,
            health={"status": "healthy", "ping": 1},
            read_responses={
                "db_labels": [{"label": "Article"}],
                "metadata": [{"seed_version": "r63f", "kb_version": "v5"}],
                "labels": {"Article": [{"cnt": 113}]},
                "edges": [],
            },
        )
        _patch_client(monkeypatch, fake)

        client.get("/healthz/graph")
        probes = [q for q in fake.read_queries if "db.labels()" in q]
        assert len(probes) == 1, (
            f"expected exactly 1 db.labels() probe, got {len(probes)}: "
            f"{probes}"
        )

    def test_fallback_when_db_labels_raises(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ``CALL db.labels()`` fails (e.g. on a Neo4j edition that
        doesn't expose it), the route MUST fall back to a SAFE subset of
        the allowlist so the response stays operationally meaningful
        AND the R63-F warning storm doesn't re-appear.

        R64 — pre-R64 the fallback queried the FULL allowlist, which
        re-introduced ``UNRECOGNIZED`` warnings for the 5 orphan
        parent-CodexAI labels (Dimension / Question / RoadmapTask /
        NISTSubcategory / ISOClause). Post-R64 the fallback queries
        only labels the seeder guarantees.
        """
        monkeypatch.setenv("NEO4J_URI", "bolt://nope:7687")
        # Fake that throws on the db.labels() probe only.
        class _LabelsProbeRaiser(_FakeGraphClient):
            def execute_read(
                self, query: str, parameters: dict | None = None
            ):
                self.read_queries.append(query)
                if "db.labels()" in query:
                    raise RuntimeError("simulated procedure-unavailable")
                # Re-dispatch via super for everything else.
                if "KBMetadata" in query:
                    return self._read_responses.get("metadata", [])
                if "RETURN type(r)" in query:
                    return self._read_responses.get("edges", [])
                for label, rows in self._read_responses.get("labels", {}).items():
                    if f"(n:{label})" in query:
                        return rows
                return []

        fake = _LabelsProbeRaiser(
            enabled=True,
            health={"status": "healthy", "ping": 1},
            read_responses={
                "metadata": [{"seed_version": "r63f", "kb_version": "v5"}],
                "labels": {
                    "Article": [{"cnt": 113}],
                    "Obligation": [{"cnt": 113}],
                },
                "edges": [],
            },
        )
        _patch_client(monkeypatch, fake)

        r = client.get("/healthz/graph")
        # Response still useful — fallback queries safe-subset entries.
        body = r.json()
        assert body["graph_ok"] is True
        assert body["node_counts"]["Article"] == 113
        assert body["node_counts"]["Obligation"] == 113
        # R64 — orphan labels MUST NOT be queried on the fallback path.
        # If they were, Neo4j 5.x would log the R63-F UNRECOGNIZED
        # warnings the helper exists to prevent.
        _ORPHAN_LABELS = {
            "Dimension", "Question", "RoadmapTask",
            "NISTSubcategory", "ISOClause",
        }
        for orphan in _ORPHAN_LABELS:
            for q in fake.read_queries:
                assert f"(n:{orphan})" not in q, (
                    f"R64 regression: fallback queried orphan label "
                    f"{orphan!r} via {q!r}"
                )
        # Conversely, every safe-fallback label that's in the allowlist
        # MUST be attempted on the fallback path.
        from app.graph.client import _STATS_LABELS
        _SAFE_FALLBACK = {
            "Article", "Obligation", "KBMetadata",
            "RiskLevel", "AnnexIIICategory",
        }
        for label in _SAFE_FALLBACK & _STATS_LABELS:
            assert any(f"(n:{label})" in q for q in fake.read_queries), (
                f"fallback path skipped safe-fallback label {label!r}"
            )

    def test_get_stats_filters_missing_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``GraphClient.get_stats()`` (called on boot) has the same fix."""
        from app.graph.client import GraphClient, _STATS_LABELS
        from app.graph.config import GraphSettings

        # Build a client without going through __init__ (which would try
        # to spin up a real driver). The method we test only reads from
        # execute_read, which we stub below.
        gc = GraphClient.__new__(GraphClient)
        gc._settings = GraphSettings()
        gc._driver = object()  # truthy → enabled=True

        seen: list[str] = []

        def fake_execute_read(query, parameters=None):
            seen.append(query)
            if "db.labels()" in query:
                return [{"label": "Article"}, {"label": "KBMetadata"}]
            if "RETURN type(r)" in query:
                return []
            # Per-label count check BEFORE the metadata branch — both
            # share the ``KBMetadata`` substring.
            if "(n:Article)" in query:
                return [{"cnt": 113}]
            if "(n:KBMetadata)" in query:
                return [{"cnt": 1}]
            if "KBMetadata" in query:
                return [{"v": "r63f-seed"}]
            return []

        monkeypatch.setattr(gc, "execute_read", fake_execute_read)
        stats = gc.get_stats()

        assert stats.healthy is True
        assert stats.nodes_by_type.get("Article") == 113
        assert stats.nodes_by_type.get("KBMetadata") == 1
        # Missing labels NOT counted.
        for missing in (_STATS_LABELS - {"Article", "KBMetadata"}):
            assert missing not in stats.nodes_by_type
            for q in seen:
                assert f"(n:{missing})" not in q, (
                    f"R63-F regression in get_stats: queried {missing!r}"
                )


# ─── R64 — extracted ``existing_labels`` helper (I5 + I6 fixes) ───────────────


class TestR64ExistingLabelsHelper:
    """``GraphClient.existing_labels`` is the shared probe-and-intersect
    that ``get_stats`` AND ``/healthz/graph`` both delegate to.

    R64 closes two findings from the deep-code-review of R63-F:

    * **I5** — both call-sites had duplicated inline probe-and-intersect
      blocks with divergent logger keys. The new helper centralises this.
    * **I6** — the pre-R64 fallback path returned the FULL allowlist on
      ``db.labels()`` failure, which re-introduced the R63-F warning
      storm for the 5 orphan parent-CodexAI labels the Regenold seeder
      doesn't populate. The R64 helper uses a SAFE fallback subset of
      labels that ``scripts/seed_neo4j_kb.py`` guarantees on every run.
    """

    # The 5 parent-CodexAI orphan labels the seeder does NOT write —
    # querying these triggers Neo4j ``UNRECOGNIZED`` warnings.
    _ORPHAN_LABELS = frozenset({
        "Dimension", "Question", "RoadmapTask",
        "NISTSubcategory", "ISOClause",
    })

    # The 5 labels we know the seeder writes that intersect with the
    # allowlist. (Annex / Recital / Definition / OperatorRole are also
    # seeded but not in ``_STATS_LABELS``.)
    _SAFE_FALLBACK = frozenset({
        "Article", "Obligation", "KBMetadata",
        "RiskLevel", "AnnexIIICategory",
    })

    def _build_disabled_client(self):
        """A GraphClient with ``enabled=False`` (no driver)."""
        from app.graph.client import GraphClient
        from app.graph.config import GraphSettings
        gc = GraphClient.__new__(GraphClient)
        gc._settings = GraphSettings()
        gc._driver = None  # ``enabled`` reports False
        return gc

    def _build_enabled_client(self):
        """A GraphClient with a truthy ``_driver`` so ``enabled`` is True."""
        from app.graph.client import GraphClient
        from app.graph.config import GraphSettings
        gc = GraphClient.__new__(GraphClient)
        gc._settings = GraphSettings()
        gc._driver = object()  # truthy → enabled=True
        return gc

    def test_helper_exists_on_graph_client(self) -> None:
        """I5 — the public helper signature must be present so call-sites
        can delegate instead of duplicating the probe-and-intersect."""
        from app.graph.client import GraphClient
        assert hasattr(GraphClient, "existing_labels")
        assert callable(GraphClient.existing_labels)

    def test_existing_labels_happy_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``db.labels()`` returns a list of labels, the helper
        intersects them with the allowlist and returns only the overlap.

        I5 — the happy-path returns labels filtered through the allowlist
        so a label that exists in the graph but isn't in the allowlist
        (e.g. an unrelated experimental label) is not surfaced.
        """
        from app.graph.client import _STATS_LABELS

        gc = self._build_enabled_client()

        seen: list[str] = []

        def fake_execute_read(query, parameters=None):
            seen.append(query)
            # Reflect a mix: one allowlist label + one non-allowlist
            # label. Only the allowlist label should be returned.
            return [
                {"label": "Article"},
                {"label": "Question"},  # In allowlist + db
                {"label": "RandomExperiment"},  # Not in allowlist
            ]

        monkeypatch.setattr(gc, "execute_read", fake_execute_read)
        out = gc.existing_labels(_STATS_LABELS)

        # ``Article`` and ``Question`` both in allowlist and in db.labels.
        assert out == {"Article", "Question"}
        # The single probe ran exactly once.
        probes = [q for q in seen if "db.labels()" in q]
        assert len(probes) == 1

    def test_existing_labels_fallback_uses_safe_subset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """I6 — when ``db.labels()`` raises, the fallback subset MUST be
        disjoint from the 5 orphan parent-CodexAI labels. Otherwise the
        ``MATCH (n:LABEL)`` queries that follow re-introduce R63-F's
        ``UNRECOGNIZED`` warning storm in operator dashboards.
        """
        from app.graph.client import _STATS_LABELS

        gc = self._build_enabled_client()

        def fake_execute_read(query, parameters=None):
            if "db.labels()" in query:
                raise RuntimeError("simulated procedure-unavailable")
            return []

        monkeypatch.setattr(gc, "execute_read", fake_execute_read)
        out = gc.existing_labels(_STATS_LABELS)

        # Must NOT include any orphan label.
        assert out.isdisjoint(self._ORPHAN_LABELS), (
            f"R64 [I6] regression: fallback subset {out!r} overlaps "
            f"orphan labels {self._ORPHAN_LABELS!r} — querying these "
            f"triggers Neo4j UNRECOGNIZED warnings."
        )
        # Fallback should include the safe set (intersected with allowlist).
        assert out == self._SAFE_FALLBACK & _STATS_LABELS

    def test_existing_labels_disabled_client_returns_empty(self) -> None:
        """A disabled client has no driver — no probe should fire, and
        the helper returns an empty set so callers' for-loops are no-ops.
        """
        from app.graph.client import _STATS_LABELS

        gc = self._build_disabled_client()
        out = gc.existing_labels(_STATS_LABELS)
        assert out == set()

    def test_existing_labels_safe_fallback_provably_seeded(self) -> None:
        """The safe-fallback subset MUST be a subset of labels that
        ``scripts/seed_neo4j_kb.py`` writes — otherwise the fallback
        path would still query missing labels.

        Reads the seeder source and extracts every ``MERGE (x:Label)``
        node label. Asserts the safe-fallback is contained in that set.
        """
        import pathlib
        import re

        seeder_src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts" / "seed_neo4j_kb.py"
        ).read_text(encoding="utf-8")
        seeded_labels = set(
            re.findall(r"MERGE\s*\(\s*\w+\s*:\s*(\w+)", seeder_src)
        )

        assert self._SAFE_FALLBACK.issubset(seeded_labels), (
            f"R64 [I6] safe-fallback set {self._SAFE_FALLBACK!r} contains "
            f"labels the seeder does NOT write. Seeded labels: "
            f"{sorted(seeded_labels)!r}. Adjust safe_fallback in "
            f"GraphClient.existing_labels to match."
        )

    def test_route_delegates_to_helper(self) -> None:
        """I5 — neither the route nor ``get_stats`` should still carry
        an inline ``CALL db.labels()`` block. The helper is the only
        place that string should appear at the call-sites.

        Greps the live source. Pre-R64 both files had inline probe blocks
        with divergent logger keys; post-R64 the only references should
        be in the helper itself + comments.
        """
        import pathlib

        main_src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app" / "main.py"
        ).read_text(encoding="utf-8")

        # The route MUST call the helper.
        assert "client.existing_labels(" in main_src, (
            "R64 [I5] regression: /healthz/graph no longer delegates to "
            "GraphClient.existing_labels()."
        )
        # The route MUST NOT re-introduce the inline probe.
        assert "CALL db.labels()" not in main_src, (
            "R64 [I5] regression: /healthz/graph still carries an inline "
            "CALL db.labels() probe — it should delegate to "
            "GraphClient.existing_labels() instead."
        )

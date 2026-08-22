"""R360.6 — the boot seeder must never write over a live Aura graph.

``AGENTS.md`` makes this a hard rule ("protect live Aura graph nodes"), and two
paths in ``_maybe_auto_seed_neo4j`` broke it by treating *ignorance* as
*emptiness*:

* a meta-probe **timeout** set ``meta_rows = []``, which the decision below
  reads as ``graph_empty`` and seeds — so the single most likely transient on a
  hosted graph (a slow response at boot) triggered a write over correct data;
* a **missing KBMetadata row** was taken as proof of an empty graph, but a
  partially-seeded or hand-loaded instance has nodes and no metadata.

Both now skip. "I could not verify" and "it is empty" are different facts.
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_started():
    import app.main as m

    saved = m._AUTO_SEED_STARTED
    m._AUTO_SEED_STARTED = False
    yield
    m._AUTO_SEED_STARTED = saved


def _run(monkeypatch, client) -> list[str]:
    """Run the seeder against a fake graph client; return seed reasons fired."""
    import app.main as m

    # The seeder returns early on these three before it ever reaches a graph.
    monkeypatch.delenv("REGENOLD_SKIP_STARTUP_LOG", raising=False)
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://fake.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_AUTO_SEED", "1")
    started: list[str] = []

    # NB: do NOT patch ``m._threading.Thread`` — that is the global
    # ``threading.Thread``, which the metadata probe's ThreadPoolExecutor uses
    # for its own worker. Replacing it makes ``submit()`` never run and every
    # test reads as a probe timeout. Patch the seed target instead and let the
    # real (daemon) thread run it.
    def _record(reason: str) -> None:
        started.append(reason)

    with (
        patch("app.graph.client.get_graph_client", return_value=client),
        patch.object(m, "_run_auto_seed_in_thread", _record),
    ):
        m._maybe_auto_seed_neo4j()
        for t in threading.enumerate():
            if t.name == "regenold-auto-seed":
                t.join(timeout=5)
    return started


class TestSeederRefusesWhatItCannotVerify:
    def test_a_nonempty_graph_without_metadata_is_not_seeded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = MagicMock()
        client.enabled = True

        def _read(cypher, *a, **kw):
            if "KBMetadata" in cypher:
                return []          # no metadata row
            if "count(n)" in cypher:
                return [{"c": 4211}]   # ...but the graph is full
            return []

        client.execute_read.side_effect = _read
        assert _run(monkeypatch, client) == [], "seeded over a non-empty graph"

    def test_a_verified_empty_graph_is_still_seeded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard must be narrow — a genuinely empty graph still seeds,
        or this is a feature removal rather than a safety fix."""
        client = MagicMock()
        client.enabled = True

        def _read(cypher, *a, **kw):
            if "KBMetadata" in cypher:
                return []
            if "count(n)" in cypher:
                return [{"c": 0}]
            return []

        client.execute_read.side_effect = _read
        started = _run(monkeypatch, client)
        assert started and "graph_empty" in started[0]

    def test_an_unreadable_node_count_is_not_seeded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = MagicMock()
        client.enabled = True

        def _read(cypher, *a, **kw):
            if "KBMetadata" in cypher:
                return []
            raise RuntimeError("connection reset")

        client.execute_read.side_effect = _read
        assert _run(monkeypatch, client) == []

    def test_a_slow_metadata_probe_does_not_seed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pre-R360.6 comment argued a timeout was safe to seed through,
        because the boot seeder runs ``clear=False`` and MERGEs. That is true
        as far as it goes — nothing is deleted — but it still means the single
        most likely transient on a hosted graph (a slow response at boot)
        triggers a full KB re-MERGE that SETs properties across a live graph
        nobody asked to touch. "Could not read the seed version" is ignorance,
        not evidence of staleness.
        """
        import time

        monkeypatch.setenv("REGENOLD_GRAPH_BOOT_PROBE_S", "0.5")
        client = MagicMock()
        client.enabled = True

        def _read(cypher, *a, **kw):
            if "KBMetadata" in cypher:
                time.sleep(2.0)
            return []

        client.execute_read.side_effect = _read
        assert _run(monkeypatch, client) == []

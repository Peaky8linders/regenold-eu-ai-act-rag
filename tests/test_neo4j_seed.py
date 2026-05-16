"""Tests for ``scripts.seed_neo4j_kb`` — the Neo4j KB seeder.

The script ships with no neo4j-driver dependency at import time and a
deterministic ``build_payload`` that's pure-Python; both properties let
these tests run offline on any platform without spinning up a Neo4j
instance.

Coverage:

* Payload composition — every source module (articles, annexes,
  recitals, definitions, obligations, ontology, role × risk edges)
  produces the expected node count.
* Idempotency — calling ``seed_graph`` twice records the SAME Cypher
  statement shape twice (``MERGE`` is server-side idempotent; we verify
  the client-side surface doesn't drift between runs).
* ``--dry-run`` — no writes are issued through the mock client.
* Reference integrity — every edge endpoint resolves to a node ID
  produced by the payload (no dangling references).
* ``KBMetadata`` — the ``seed_version`` field is pinned and surfaces in
  the payload + write batch.
"""
from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts import seed_neo4j_kb
from scripts.seed_neo4j_kb import (
    BATCH_SIZE,
    SEED_VERSION,
    SeedPayload,
    build_payload,
    main,
    seed_graph,
    validate_payload,
)


# ─── Fixtures ────────────────────────────────────────────────────────────


class RecordingClient:
    """Minimal ``GraphClient`` stand-in that records what would be written.

    Mirrors the public surface the seeder uses: ``execute_write_batch``,
    ``clear_graph``, ``close``, plus the ``enabled`` property. Records
    every batch and every individual ``(cypher, params)`` pair so tests
    can assert against the recorded payload without an actual Neo4j.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.batches: list[list[tuple[str, dict]]] = []
        self.statements: list[tuple[str, dict]] = []
        self.clear_called = 0
        self.close_called = 0

    def execute_write_batch(self, queries: list[tuple[str, dict]]) -> None:
        self.batches.append(list(queries))
        for query, params in queries:
            self.statements.append((query, dict(params)))

    def clear_graph(self) -> None:
        self.clear_called += 1

    def close(self) -> None:
        self.close_called += 1


@pytest.fixture
def payload() -> SeedPayload:
    return build_payload()


@pytest.fixture
def client() -> RecordingClient:
    return RecordingClient()


# ─── Payload composition ─────────────────────────────────────────────────


def test_payload_seeds_113_articles(payload: SeedPayload) -> None:
    assert len(payload.article_nodes) == 113
    # Every article ID should be ``article_<N>`` for N in [1, 113].
    ids = {node["id"] for node in payload.article_nodes}
    assert ids == {f"article_{n}" for n in range(1, 114)}


def test_payload_seeds_13_annexes(payload: SeedPayload) -> None:
    assert len(payload.annex_nodes) == 13
    romans = {node["number"] for node in payload.annex_nodes}
    assert romans == {
        "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX",
        "X", "XI", "XII", "XIII",
    }


def test_payload_seeds_180_recitals(payload: SeedPayload) -> None:
    """Round 25 ports 180 recitals from the Ansvar-Systems corpus."""
    assert len(payload.recital_nodes) == 180
    numbers = {int(node["number"]) for node in payload.recital_nodes}
    assert numbers == set(range(1, 181))
    # Every recital has non-empty text.
    for node in payload.recital_nodes:
        assert node["text"], f"recital {node['id']} has empty text"


def test_payload_seeds_definitions(payload: SeedPayload) -> None:
    """The Art. 3 definitions catalogue ships at least 31 high-impact terms.

    The Round 25 Ansvar port pushes the count to 68 — we assert the lower
    bound from the CLAUDE.md hard rule so the test survives future
    catalogue trimming.
    """
    assert len(payload.definition_nodes) >= 31
    # IDs follow the slug pattern.
    for node in payload.definition_nodes:
        assert node["id"].startswith("def_"), node["id"]
        assert node["kind"] == "Definition"
        assert node["text"]


def test_payload_seeds_obligations_with_article_match(
    payload: SeedPayload,
) -> None:
    """Every Obligation must point at a real Article node.

    Annex rows in EC_CHECKER_OBLIGATION_MAP are deliberately filtered out
    (they land as Annex nodes, not Obligations), so the count is bounded
    above by 113 (one per article) and below by the number of articles
    with KB stubs.
    """
    article_ids = {node["id"] for node in payload.article_nodes}
    for obl in payload.obligation_nodes:
        # ``article_ref`` is the bare number; the corresponding Article
        # ID must exist in the payload.
        assert f"article_{obl['article_ref']}" in article_ids, (
            f"obligation {obl['id']} references unknown article "
            f"{obl['article_ref']}"
        )
        assert obl["mandatory"] is True


def test_payload_seeds_8_annex_iii_categories(payload: SeedPayload) -> None:
    assert len(payload.annex_iii_nodes) == 8
    for node in payload.annex_iii_nodes:
        assert node["id"].startswith("annex_iii_")
        assert node["label"]


def test_payload_seeds_4_risk_levels(payload: SeedPayload) -> None:
    assert len(payload.risk_level_nodes) == 4
    labels = {node["label"] for node in payload.risk_level_nodes}
    assert labels == {"prohibited", "high-risk", "limited", "minimal"}


def test_payload_seeds_canonical_operator_roles(payload: SeedPayload) -> None:
    """The 5 NLF roles surface as Layer-1 nodes; modifier roles do not."""
    ids = {node["id"] for node in payload.operator_role_nodes}
    assert ids == {
        "role_provider",
        "role_deployer",
        "role_importer",
        "role_distributor",
        "role_authorized_representative",
    }


def test_payload_seeds_kb_metadata(payload: SeedPayload) -> None:
    meta = payload.metadata_node
    assert meta["seed_version"] == SEED_VERSION
    assert meta["kb_version"]
    assert meta["seeded_at"]
    assert meta["total_nodes"] == payload.total_nodes
    assert meta["total_edges"] == payload.total_edges


# ─── Edge composition ────────────────────────────────────────────────────


def test_has_obligation_edges_match_obligation_nodes(
    payload: SeedPayload,
) -> None:
    assert len(payload.has_obligation_edges) == len(payload.obligation_nodes)


def test_has_definition_edges_anchor_to_art_3(payload: SeedPayload) -> None:
    # Every definition anchors to Art. 3 — the article whose paragraphs
    # define the terms.
    sources = {edge["source_id"] for edge in payload.has_definition_edges}
    assert sources == {"article_3"}
    assert len(payload.has_definition_edges) == len(payload.definition_nodes)


def test_cross_reference_edges_include_manual_pairs(
    payload: SeedPayload,
) -> None:
    from app.data.kb_xrefs import MANUAL_XREFS

    # Every manual edge should land in the payload (tagged ``manual``).
    manual_edge_ids: set[tuple[str, str]] = set()
    for edge in payload.cross_reference_edges:
        if edge["edge_source"] == "manual":
            manual_edge_ids.add((edge["source_id"], edge["target_id"]))

    for source, target, _reason in MANUAL_XREFS:
        # Translate the raw refs to payload IDs.
        src_id = seed_neo4j_kb._article_id(source)
        tgt_id = seed_neo4j_kb._article_id(target)
        # Manual edges only get the ``manual`` tag when the regex pass
        # didn't already record the same pair — that's the additive
        # contract documented in kb_xrefs._build_xref_graph. So we
        # assert the pair exists SOMEWHERE in the edge list, regardless
        # of which source tagged it.
        pair_anywhere = any(
            edge["source_id"] == src_id and edge["target_id"] == tgt_id
            for edge in payload.cross_reference_edges
        )
        assert pair_anywhere, f"manual xref {source} -> {target} missing"


def test_annex_iii_triggers_high_risk_under_article_6(
    payload: SeedPayload,
) -> None:
    """Every Annex III category should trigger Art. 6 high-risk classification."""
    assert len(payload.triggers_high_risk_edges) == 8
    for edge in payload.triggers_high_risk_edges:
        assert edge["target_id"] == "article_6"
        assert edge["source_id"].startswith("annex_iii_")


def test_applies_at_edges_routed_to_correct_risk_levels(
    payload: SeedPayload,
) -> None:
    """Spot-check: Art. 5 obligation lands on prohibited; Art. 50 on limited."""
    by_obligation: dict[str, str] = {}
    for edge in payload.applies_at_edges:
        by_obligation[edge["source_id"]] = edge["target_id"]

    assert by_obligation.get("obl_5") == "risk_prohibited"
    assert by_obligation.get("obl_50") == "risk_limited"
    assert by_obligation.get("obl_4") == "risk_minimal"
    assert by_obligation.get("obl_6") == "risk_high"
    assert by_obligation.get("obl_9") == "risk_high"


# ─── Validation ──────────────────────────────────────────────────────────


def test_validate_payload_passes(payload: SeedPayload) -> None:
    """Built payload has no dangling edges."""
    assert validate_payload(payload) == []


def test_validate_payload_detects_dangling_edge(payload: SeedPayload) -> None:
    bad = SeedPayload(
        article_nodes=payload.article_nodes,
        annex_nodes=payload.annex_nodes,
        recital_nodes=payload.recital_nodes,
        definition_nodes=payload.definition_nodes,
        obligation_nodes=payload.obligation_nodes,
        annex_iii_nodes=payload.annex_iii_nodes,
        risk_level_nodes=payload.risk_level_nodes,
        operator_role_nodes=payload.operator_role_nodes,
        metadata_node=payload.metadata_node,
        has_obligation_edges=[
            {"source_id": "article_999", "target_id": "obl_999"},
        ],
        has_definition_edges=[],
        cross_reference_edges=[],
        has_recital_anchor_edges=[],
        triggers_high_risk_edges=[],
        applies_at_edges=[],
    )
    errors = validate_payload(bad)
    # Both endpoints are unknown → two errors.
    assert len(errors) == 2
    assert any("article_999" in e for e in errors)
    assert any("obl_999" in e for e in errors)


# ─── Driver-mock seed run ────────────────────────────────────────────────


def test_seed_graph_writes_every_payload_row(
    client: RecordingClient, payload: SeedPayload,
) -> None:
    counts = seed_graph(client, payload, batch_size=50)

    # Node + edge totals match the payload counters.
    expected = payload.counts()
    assert counts == expected

    # Every batch obeys the size cap.
    for batch in client.batches:
        assert len(batch) <= 50


def test_seed_graph_uses_merge_not_create(
    client: RecordingClient, payload: SeedPayload,
) -> None:
    """Idempotency invariant — every write must be a MERGE, never a CREATE."""
    seed_graph(client, payload, batch_size=BATCH_SIZE)
    for query, _params in client.statements:
        assert "MERGE" in query, query
        # Any naked ``CREATE`` would defeat idempotency. Allow it only as
        # a substring of ``MERGE`` — but our templates don't use CREATE.
        assert not re.search(r"\bCREATE\b", query), query


def test_seed_graph_idempotent_signature(
    payload: SeedPayload,
) -> None:
    """Running the seed twice produces the same recorded Cypher shape.

    The actual idempotency lives in Neo4j (``MERGE`` matches on the
    ``id`` key), but the client-side surface must also be stable — a
    second invocation should issue the SAME parameter set in the SAME
    statement order. That's what guarantees a re-seed is observably a
    no-op against the source modules.
    """
    client_a = RecordingClient()
    client_b = RecordingClient()
    seed_graph(client_a, payload, batch_size=BATCH_SIZE)
    seed_graph(client_b, payload, batch_size=BATCH_SIZE)
    assert len(client_a.statements) == len(client_b.statements)
    for (qa, pa), (qb, pb) in zip(client_a.statements, client_b.statements):
        assert qa == qb
        assert pa == pb


def test_seed_graph_writes_kb_metadata_with_seed_version(
    client: RecordingClient, payload: SeedPayload,
) -> None:
    seed_graph(client, payload, batch_size=BATCH_SIZE)
    metadata_rows = [
        params
        for query, params in client.statements
        if "KBMetadata" in query
    ]
    assert len(metadata_rows) == 1
    row = metadata_rows[0]
    assert row["seed_version"] == SEED_VERSION
    assert row["kb_version"]
    assert row["total_nodes"] == payload.total_nodes
    assert row["total_edges"] == payload.total_edges


def test_seed_graph_groups_nodes_before_edges(
    client: RecordingClient, payload: SeedPayload,
) -> None:
    """Every edge MATCHes by node ID — nodes must land first.

    We assert this on the recorded order: the index of the LAST node
    write must precede the index of the FIRST edge write.
    """
    seed_graph(client, payload, batch_size=BATCH_SIZE)
    last_node_idx = max(
        i for i, (q, _) in enumerate(client.statements) if "MERGE" in q
        and "MATCH" not in q
    )
    first_edge_idx = min(
        i for i, (q, _) in enumerate(client.statements) if "MATCH" in q
    )
    assert last_node_idx < first_edge_idx


# ─── CLI ─────────────────────────────────────────────────────────────────


def test_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--dry-run`` must not import or touch the GraphClient."""
    # Sentinel — any access raises so we know the dry-run path stayed clean.
    def _exploding_get_client(*a: Any, **kw: Any) -> Any:
        raise AssertionError("GraphClient must not be touched in dry-run")

    monkeypatch.setattr(
        "app.graph.client.GraphClient", _exploding_get_client, raising=True
    )
    rc = main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "seed_version" in out
    assert "Article" in out
    assert "--dry-run" in out


def test_dry_run_with_no_neo4j_env_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default offline path (no NEO4J_URI set) must exit 0 under --dry-run."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    rc = main(["--dry-run"])
    assert rc == 0


def test_live_run_against_disabled_client_fails_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Without --dry-run, a disabled client should fail with a clear error."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    # Reach into the module's import to swap the GraphClient + settings
    # with stubs that report disabled. The seeder imports them lazily
    # inside main() so monkeypatching the source modules works.
    import app.graph.client as gc_mod

    class _Disabled:
        enabled = False

        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def close(self) -> None:
            pass

        def clear_graph(self) -> None:
            pass

    monkeypatch.setattr(gc_mod, "GraphClient", _Disabled, raising=True)
    rc = main([])
    assert rc == 1
    captured = capsys.readouterr()
    assert "disabled" in captured.err.lower()


def test_live_run_with_mock_client_writes_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """End-to-end: a live run against a mock writes every payload row."""
    recorder = RecordingClient(enabled=True)
    import app.graph.client as gc_mod

    monkeypatch.setattr(
        gc_mod, "GraphClient",
        lambda *a, **kw: recorder, raising=True,
    )

    rc = main(["--neo4j-uri", "bolt://test:7687"])
    assert rc == 0
    # At least one batch per non-empty Cypher template. Empty buckets
    # (e.g. ``HAS_RECITAL_ANCHOR`` when no KB summary mentions a recital
    # by number) emit zero batches by design.
    assert len(recorder.batches) >= 14
    # Closed at the end.
    assert recorder.close_called == 1
    out = capsys.readouterr().out
    assert "Seed complete" in out


def test_live_run_with_clear_calls_clear_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingClient(enabled=True)
    import app.graph.client as gc_mod

    monkeypatch.setattr(
        gc_mod, "GraphClient",
        lambda *a, **kw: recorder, raising=True,
    )

    rc = main(["--neo4j-uri", "bolt://test:7687", "--clear"])
    assert rc == 0
    assert recorder.clear_called == 1


# ─── Helper invariants ───────────────────────────────────────────────────


def test_article_id_helper_round_trip() -> None:
    assert seed_neo4j_kb._article_id("Art. 5") == "article_5"
    assert seed_neo4j_kb._article_id("Art. 113") == "article_113"
    assert seed_neo4j_kb._article_id("Annex III") == "annex_III"
    assert seed_neo4j_kb._article_id("Annex XIII") == "annex_XIII"


def test_slug_term_collapses_punctuation() -> None:
    assert seed_neo4j_kb._slug_term("AI system") == "ai_system"
    assert (
        seed_neo4j_kb._slug_term("real-time remote biometric identification")
        == "real_time_remote_biometric_identification"
    )


def test_classify_risk_for_article_closed_mapping() -> None:
    f = seed_neo4j_kb._classify_risk_for_article
    assert f("5") == "risk_prohibited"
    assert f("4") == "risk_minimal"
    assert f("50") == "risk_limited"
    assert f("9") == "risk_high"
    assert f("49") == "risk_high"
    # Outside the band → no edge.
    assert f("113") is None
    assert f("60") is None
    assert f("not-a-number") is None

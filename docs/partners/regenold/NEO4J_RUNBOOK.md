# Neo4j Runbook — Regenold EU AI Act RAG

Operator-facing setup, verification, and recovery for the optional
Neo4j-backed knowledge graph.

## What this gets you

* **Audit forensics** — every citation maps to a graph node, so an
  auditor can walk `Article → Obligation → ComplianceGap` edges to
  explain why a given reference fired.
* **Multi-hop reasoning** — `app/graph/reasoning.py` walks
  `CROSS_REFERENCES` / `REQUIRES` / `MAPS_TO_NIST` edges; the
  deterministic Round-31 `graphrag_expand.py` mirrors this in code
  but Neo4j makes traversals visualisable.
* **Cross-framework mapping** — the seed ontology carries
  `NISTSubcategory`, `ISOClause`, and `HarmonizedStandard`; once the
  edges are wired, "which AI Act obligations satisfy NIST MEASURE-2.2?"
  is one Cypher query.

The davidath benchmark scorecard does **not** move when Neo4j is on
— the benchmark only scores the wire-side answer shape. The graph
wins live in observability and forensic replay, not on the bench.

## One-time setup

```bash
# 1. Install the driver
pip install neo4j>=5.0

# 2. Set the connection env vars (Railway: railway variables --set "...")
export NEO4J_URI="bolt+s://your-instance.databases.neo4j.io:7687"
export NEO4J_USERNAME="neo4j"          # bundle reads NEO4J_USERNAME or NEO4J_USER
export NEO4J_PASSWORD="..."
export NEO4J_DATABASE="neo4j"          # default; override if multi-db

# 3. (Optional) Enable 2-hop expansion at request time
export REGENOLD_GRAPH_2HOP=1

# 4. Seed the knowledge base
python -m scripts.seed_neo4j_kb
```

The seed writes 113 `Article` + 13 `Annex` + 180 `Recital` + 31
`Definition` + 113 `Obligation` nodes plus a `KBMetadata` row carrying
`seed_version` and `kb_version`. Idempotent — re-run is a no-op unless
`--clear` is passed.

## Verifying

```bash
curl http://localhost:8000/healthz/graph | python -m json.tool
```

Expected shape on a healthy, seeded graph:

```json
{
  "version": "0.1.0",
  "graph_enabled": true,
  "graph_ok": true,
  "detail": "ok",
  "elapsed_ms": 12,
  "seed_version": "2026-05-16-r35",
  "kb_version": "2026.05.16.v3",
  "node_counts": {"Article": 113, "Obligation": 113, ...},
  "edge_counts": {"REQUIRES": 113, "CROSS_REFERENCES": 142, ...}
}
```

The endpoint returns HTTP 200 in every state — alert on
`graph_ok=false`, not on HTTP status. A downed graph degrades to the
deterministic fallback automatically.

At boot the app logs one line so operators see status without curling:

```
regenold.startup graph_enabled=True seed_version=2026-05-16-r35 node_count=450 edge_count=388
```

## Re-seeding

Re-seed when `KB_VERSION` (`app/data/kb.py`) bumps or the schema
migrates (new node label / edge type). `/healthz/graph` will show
`seed_version` diverging from `kb_version` — that's the trigger.

```bash
# Destructive: drops every node + edge, then re-seeds from scratch.
python -m scripts.seed_neo4j_kb --clear
```

The delete runs in one transaction (abort-safe). The route never
writes — only the seed script does. ~30 s against AuraDB Free.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `graph_enabled=false, detail="NEO4J_URI not set"` | env var unset | Set `NEO4J_URI` + `NEO4J_PASSWORD`. |
| `graph_disabled: ... neo4j driver is not installed` | `pip install neo4j>=5.0` skipped | Install the driver, restart the app. |
| `unhealthy: Graph database unavailable` | TLS / firewall / wrong port | Verify `bolt+s://` vs `bolt://`, confirm port 7687 reachable. |
| `health_check_exception: ServiceUnavailable` | cluster restart / network blip | Engine falls back automatically; check on next request cycle. |
| `node_counts={}` on a healthy graph | seed never ran | `python -m scripts.seed_neo4j_kb` |
| `seed_version=""` but counts populated | seed ran on an older release that pre-dated `KBMetadata` | Re-seed with `--clear` to land the metadata row. |

**Fall-back posture.** Every failure mode above is non-fatal — the
deterministic KB path keeps serving the same wire contract. The graph
is an observability multiplier, never a hard dependency.

## What it doesn't do (yet)

* **Single-tenant only.** The ontology defines `Tenant_<hash>` shard
  labels; the seed writes Layer-1 nodes only. No per-tenant overlay.
* **No audit-chain mirror.** The hash-chained audit lives in
  `app/evidence/store.py`; the graph carries no `:AuditEntry` projection
  yet — joins are application-side.
* **No wire write-path.** Only `scripts/seed_neo4j_kb.py` writes; the
  route + engine are read-only.

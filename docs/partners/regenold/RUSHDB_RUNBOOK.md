# RushDB operator runbook (Neo4j Aura replacement)

Production graph path prefers **RushDB** when `RUSHDB_AUTH_TOKEN` or
`RUSHDB_API_KEY` is set; **Neo4j** remains a fallback while `NEO4J_URI`
is still configured.

Reference pattern: [`Hybrid_RAG_Guide.md`](Hybrid_RAG_Guide.md) (DOC/CHUNK
sample). This bundle implements a **competition-safe Article/Annex/Definition**
record model — see
[`docs/superpowers/specs/2026-05-25-neo4j-to-rushdb-migration-design.md`](../../superpowers/specs/2026-05-25-neo4j-to-rushdb-migration-design.md).

## One-time Railway setup

```bash
railway variables --set RUSHDB_AUTH_TOKEN=<token-from-rushdb.com>
# or: railway variables --set RUSHDB_API_KEY=<key>
railway variables --set RUSHDB_BASE_URL=https://api.rushdb.com/api/v1   # optional
```

Redeploy after setting secrets (see [`RAILWAY_DEPLOY.md`](RAILWAY_DEPLOY.md)).

On boot, `_maybe_auto_seed_rushdb()` seeds when `KBMetadata.seed_version`
or `kb_version` drifts from the in-process catalog (`scripts/seed_rushdb_kb.py`).

## Verify

```powershell
curl https://regenold-eu-ai-act-rag-production.up.railway.app/healthz/graph
```

When RushDB is primary, expect:

- `"detail": "ok (rushdb)"`
- `node_counts` with PascalCase labels (`Article`, `Annex`, `Definition`, …)

When only Neo4j is wired, `detail` is `"ok"` and counts match the Neo4j seeder
(`CROSS_REFERENCES` edges, etc.).

## Manual seed (local or one-off)

```powershell
$env:RUSHDB_AUTH_TOKEN = "<token>"
py -3.12 -m scripts.seed_rushdb_kb --verbose
# dry-run: py -3.12 -m scripts.seed_rushdb_kb --dry-run
```

## Hybrid retrieval (optional, post-cutover)

Env-gated additive path aligned with Hybrid guide §3–5:

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `REGENOLD_RUSHDB_HYBRID` | `0` (OFF) | Intent + semantic + metadata search in `app/engines/rushdb_hybrid_retrieval.py` |
| `REGENOLD_GRAPH_2HOP` | `1` in `railway.toml` | 2-hop expand (RushDB first, then Neo4j, then in-memory) |

Enable hybrid only after `/healthz/graph` shows RushDB healthy:

```bash
railway variables --set REGENOLD_RUSHDB_HYBRID=1
```

Davidath bench stays byte-identical with hybrid OFF (default).

## Cutover checklist (Neo4j → RushDB)

1. Set RushDB auth on Railway; redeploy.
2. Confirm `/healthz/graph` → `ok (rushdb)` and boot log `rushdb_seed_current` or `rushdb_seed_completed`.
3. Spot-check `/api/v1/regenold/eu-ai-act/ask` on a graph-heavy question (e.g. deployer obligations + Art. 26).
4. Optional: `REGENOLD_RUSHDB_HYBRID=1` after live smoke.
5. When stable for 24h+, remove Neo4j cost:
   ```bash
   railway variables --unset NEO4J_URI
   railway variables --set NEO4J_AUTO_SEED=0
   ```
6. Re-verify `/healthz/graph` still `ok (rushdb)`.

## Code map

| Surface | Module |
| ------- | ------ |
| Client + 2-hop | `app/graph/rushdb_client.py` |
| Config | `app/graph/rushdb_config.py` |
| Seeder | `scripts/seed_rushdb_kb.py` |
| Hybrid retrieval | `app/engines/rushdb_hybrid_retrieval.py` |
| KB integration | `app/data/kb_search.py` |
| 2-hop wire | `app/engines/graph_expand_2hop.py` |
| Boot + health | `app/main.py` |

Tests: `tests/test_rushdb_client.py`, `tests/test_seed_rushdb_kb.py`, `tests/test_rushdb_hybrid_retrieval.py`.

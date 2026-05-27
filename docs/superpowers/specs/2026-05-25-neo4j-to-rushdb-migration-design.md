# Neo4j → RushDB Migration Design

**Date:** 2026-05-25  
**Status:** Implemented on `main` (2026-05-27) — operator cutover pending RushDB credentials on Railway  
**Author:** Claude (via brainstorming skill)

**Shipped:** `app/graph/rushdb_client.py`, `scripts/seed_rushdb_kb.py`,
`app/engines/rushdb_hybrid_retrieval.py` (env-gated), `/healthz/graph` RushDB-first,
`graph_expand_2hop` RushDB path. Operator runbook:
[`docs/partners/regenold/RUSHDB_RUNBOOK.md`](../../partners/regenold/RUSHDB_RUNBOOK.md).

**Schema note:** Production seeder uses **Article/Annex/Definition** records with
`content` + AI indexes (not the guide's top-level DOC/CHUNK labels). Hybrid retrieval
maps guide §3–5 intent/fusion onto Article `content`. Full DOC/CHUNK port is optional
future work — see [`Hybrid_RAG_Guide.md`](../../partners/regenold/Hybrid_RAG_Guide.md).

---

## 0. Competition Recommendation — Read This First

**Do NOT execute this migration before the Regenold competition closes.**

The migration is an operational refactor, not a scoring upgrade. It produces
identical outputs through identical query semantics. Every competition rubric
axis — correctness, references-vs-gold, conciseness, tone, latency,
multi-turn coherence — will read the same before and after. The Neo4j graph
is confirmed BM25-saturated on the davidath benchmark across three independent
A/B rounds (R31, R35, R69); the RushDB replication does not change that.

Executing during the competition window creates risk with zero rubric upside:

| Risk | Severity | Source |
|---|---|---|
| RushDB cloud latency exceeds 50ms timeout → 2-hop fallback to in-memory | Low–Medium | Railway → RushDB round-trip untested under load |
| Bug in dual-path routing shim causes wrong-backend selection | Low | New code on hot path |
| Boot-time auto-seed fails → requests served before graph is ready | Low | Same class as R78.1 cache-poison bug |
| Migration PR displaces a rubric-lifting PR in the merge queue | Certain | Time is the competition's real constraint |

**What wins the competition instead:**

The remaining rubric headroom is in answer quality and multi-turn coherence,
not in graph infrastructure:

- Ans Strict: 0.3013 local / 0.3263 live — headroom toward ~0.40+
- V2 mt coherence: 0.28 — the single biggest gap, driven by conversation
  coreference, not graph depth
- Latency p50: 5.8s live — Stage-2 prompt tightening returns more than
  any infrastructure change

Execute this migration **after the competition closes** as part of a
maintenance / technical-debt sprint. The operational wins are substantial
and worth doing — just not now.

---

## 1. Context and Motivation

### Current Neo4j footprint

Three surfaces are active on the live request path:

| Surface | File | Active LOC | Env gate | Davidath impact |
|---|---|---|---|---|
| 2-hop xref traversal | `app/engines/graph_expand_2hop.py` | 490 | `REGENOLD_GRAPH_2HOP=1` (ON) | **Zero** |
| Definition lookup + recitals | `app/engines/graph_aware_retrieval.py` | 692 | `REGENOLD_GRAPH_AWARE=1` (ON) | Marginal |
| KB seeder | `scripts/seed_neo4j_kb.py` | **1,012** | `NEO4J_AUTO_SEED=1` (ON) | Boot-only |
| Driver / client | `app/graph/client.py` | ~250 | `NEO4J_URI` present | Infrastructure |

Two surfaces are dead code and will be deleted in Phase 5:

| Surface | File | LOC | Status |
|---|---|---|---|
| Ontology type stubs | `app/graph/ontology.py` | ~80 | Never instantiated on request path |
| Compliance reasoning | `app/graph/reasoning.py` | ~300 | `answer_strs` field unused in Regenold requests |

### Why migrate at all

1. **The seeder is 1,012 LOC of Cypher + Python** for what is ultimately
   a JSON push of 505 nodes. RushDB's `create_many()` does the same in ~200
   LOC with no Cypher knowledge required.

2. **The boot hook is operationally complex**: Postgres advisory lock,
   daemon thread, worker-index coordination, KBMetadata staleness check.
   With RushDB's idempotent upsert, races are benign — the complexity
   collapses to a simple staleness check.

3. **Two overlapping graph backends** (in-memory `kb_xrefs` Python dict +
   Neo4j) do related work. RushDB consolidates the durable path while the
   in-memory core graph stays as the fast local fallback.

4. **`RUSHDB_AUTH_TOKEN` is already in Railway** — the infrastructure
   decision is made; the migration code is the remaining work.

5. **~43% code reduction** on the graph layer:

   | | Before | After |
   |---|---|---|
   | Seeder | 1,012 LOC | ~200 LOC |
   | Client | ~250 LOC | ~180 LOC |
   | Hot-path engine changes | — | +80 LOC |
   | Dead code removal | — | −380 LOC |
   | **Net graph-layer LOC** | **~2,200** | **~1,250** |

---

## 2. Architecture

### 2.1 What RushDB provides

RushDB is a cloud-hosted graph database built on Neo4j's engine. It exposes
a Python SDK (`pip install rushdb`) with JSON record storage organised by
labels, rich query operators (`$in`, `$contains`, `$gte`, etc.), and an
auto-inference schema. No Cypher required.

The `RUSHDB_AUTH_TOKEN` authenticates all API calls. Records persist
across Railway redeploys — unlike the in-memory audit chain or the
reconstructed BM25 index.

### 2.2 Key architectural decision: xrefs as arrays, not graph edges

The current 2-hop Cypher query is:

```cypher
MATCH (a)-[:CROSS_REFERENCES*1..2]-(b)
WHERE a.number IN $seed_nums AND b.number IS NOT NULL
  AND a.number <> b.number
  AND (a:Article OR a:Annex) AND (b:Article OR b:Annex)
RETURN DISTINCT b.number AS num,
       length(shortestPath((a)-[:CROSS_REFERENCES*]-(b))) AS hops
ORDER BY hops, num LIMIT $cap
```

Rather than creating explicit RushDB relationship edges and relying on
native graph traversal (variable-length path support in the SDK is
unverified), we store cross-references as a flat array property:

```json
{"number": "Art. 13", "cross_refs": ["Art. 9", "Art. 14", "Art. 15"]}
```

The 2-hop traversal becomes two sequential Python queries:

- **Round 1** — find Article/Annex records where `number $in seed_nums`,
  collect their `cross_refs` arrays → hop-1 neighbor set
- **Round 2** — find Article/Annex records where `number $in hop1_refs`,
  collect their `cross_refs` arrays → hop-2 neighbor set
- Deduplicate, validate against `ARTICLE_EXISTENCE`, return with hop
  distance

Two RushDB API calls replace one Cypher call. Each RushDB call is
expected < 25ms at cloud latency, so the total stays inside the existing
50ms `ThreadPoolExecutor` timeout. The result is semantically identical
to the Cypher `*1..2` path.

### 2.3 Dual-path routing (transition safety)

All hot-path engines gain a routing shim during the migration window:

```python
if rushdb_client.is_enabled():
    return rushdb_client.expand_2hop(seed_nums, cap)
elif _neo4j_client_enabled():
    return _cypher_expand_2hop(seed_nums, cap)  # existing code, unchanged
else:
    return GraphExpansion(candidates=[], source="disabled")
```

This allows Neo4j and RushDB to run in parallel until confidence is
established, then Neo4j is retired via env-var removal. No existing tests
break during transition.

---

## 3. Data Model

### 3.1 Record labels and schema

| Label | Count | Key properties |
|---|---|---|
| `ARTICLE` | 113 | `number`, `title`, `text`, `cross_refs[]`, `kb_version` |
| `ANNEX` | 13 | `number`, `title`, `text`, `cross_refs[]` |
| `RECITAL` | 180 | `recital_number`, `text`, `article_anchor` |
| `DEFINITION` | 68 | `term`, `term_slug`, `text`, `article_number` |
| `OBLIGATION` | 113 | `article_ref`, `text`, `risk_levels[]`, `mandatory` |
| `RISK_LEVEL` | 4 | `id`, `label` |
| `ANNEX_III_CATEGORY` | 8 | `id`, `label`, `article_ref` |
| `OPERATOR_ROLE` | 5 | `id`, `label`, `primary_article` |
| `KB_METADATA` | 1 | `seed_version`, `kb_version`, `seeded_at` |

**Total: 505 records** — matches the current Neo4j node count exactly.

### 3.2 Idempotency

Before seeding, check `KB_METADATA.seed_version == SEED_VERSION AND
kb_version == KB_VERSION`. If both match, skip (same gate as the current
Neo4j `skip-current` check). Re-seed uses `db.records.set()` (upsert
semantics) — no delete/recreate required.

---

## 4. Components

### 4.1 `scripts/seed_rushdb_kb.py` (new, ~200 LOC)

Replaces `scripts/seed_neo4j_kb.py` (1,012 LOC).

```python
def run_seed(dry_run: bool = False) -> dict:
    """Returns {"status": "ok"|"skip"|"dry_run", "counts": {...}}."""
```

Sequence:
1. Check `KB_METADATA` — return `{"status": "skip"}` if current.
2. Push all 9 record types via `db.records.create_many(LABEL, batch)`.
3. Write `KB_METADATA` record with `seed_version`, `kb_version`,
   `seeded_at`.
4. Return counts per label.

No Cypher, no MERGE syntax, no relationship creation. Cross-references
are included as the `cross_refs` array property on each Article/Annex
record (sourced from `kb_xrefs._build_xref_graph()` at seed time).

### 4.2 `app/graph/rushdb_client.py` (new, ~180 LOC)

Thin, fail-soft wrapper implementing the same functional interface as
the existing Neo4j functions:

```python
def is_enabled() -> bool
    """True iff RUSHDB_AUTH_TOKEN is set and rushdb package is importable."""

def expand_2hop(
    seed_article_nums: list[str],
    cap: int = 20,
    timeout_ms: int = 50,
) -> list[dict]:
    """Returns [{num: str, hops: int}, ...] or [] on any failure."""

def lookup_definition_by_term(
    term: str,
    timeout_ms: int = 50,
) -> str | None:
    """Exact slug match first, then $contains fallback. None on failure."""

def recitals_for_article(
    article_ref: str,
    max_recitals: int = 3,
    timeout_ms: int = 50,
) -> list[dict]:
    """Returns [{article_ref, recital_number, text}, ...] or [] on failure."""

def get_stats() -> dict:
    """Returns {graph_ok, node_counts, seed_version, kb_version, elapsed_ms}."""

def get_metadata() -> dict | None:
    """Returns KB_METADATA record or None."""
```

All functions:
- 50ms timeout via `concurrent.futures.ThreadPoolExecutor` (Windows-safe,
  same pattern as `graph_expand_2hop.py`)
- Singleton `_RUSHDB_CLIENT` initialised lazily from `RUSHDB_AUTH_TOKEN`
- Return `None` / `[]` on any exception — never raise
- Log at `WARNING` on timeout, `ERROR` on unexpected exception

### 4.3 `app/engines/graph_expand_2hop.py` (modified, +40 LOC)

Add routing shim at the top of `expand_2hop()`. Existing Cypher path
is unchanged — it becomes the `elif` branch. New env gate:
`REGENOLD_RUSHDB_GRAPH_2HOP` (defaults to `REGENOLD_GRAPH_2HOP` value
for backwards compatibility during transition).

### 4.4 `app/engines/graph_aware_retrieval.py` (modified, +40 LOC)

Add routing shim to `lookup_definition_by_term()` and
`recitals_for_article()`. Same dual-path pattern. Existing Neo4j
implementations untouched as fallback.

### 4.5 `app/main.py` (modified, +50 LOC)

New `_maybe_auto_seed_rushdb()` startup hook, added alongside the
existing `_maybe_auto_seed_neo4j()`:

```python
@app.on_event("startup")
async def _maybe_auto_seed_rushdb():
    if REGENOLD_SKIP_STARTUP_LOG or not rushdb_client.is_enabled():
        return
    meta = rushdb_client.get_metadata()
    if (meta and meta.get("seed_version") == SEED_VERSION
            and meta.get("kb_version") == KB_VERSION):
        logger.info("rushdb.startup action=skip-current")
        return
    # No advisory lock needed — RushDB upserts are race-safe
    logger.info("rushdb.startup action=seed-started")
    result = seed_rushdb_kb.run_seed()
    logger.info(f"rushdb.startup action=seed-completed counts={result.get('counts')}")
```

### 4.6 `/healthz/graph` route (modified, ~20 LOC)

Prefers RushDB `get_stats()` when `rushdb_client.is_enabled()`. Falls
back to Neo4j. Response schema identical — no client-facing contract
change.

---

## 5. Migration Sequence

Execute as five sequential PRs. Each PR must pass all four existing
verification gates before merge.

### Phase 1 — Seeder (`scripts/seed_rushdb_kb.py`)

Deliverable: new seeder script, dry-run tested locally.  
Gate: `pytest tests/test_seed_rushdb_kb.py` green; dry-run output
shows correct counts (505 records across 9 labels).  
Neo4j: unchanged, still primary.

### Phase 2 — Client adapter (`app/graph/rushdb_client.py`)

Deliverable: client module + unit tests with mocked SDK.  
Gate: `pytest tests/test_rushdb_client.py` green (timeout handling,
fail-soft, 2-round 2-hop correctness, definition `$contains` fallback).  
Neo4j: unchanged, still primary.

### Phase 3 — Dual-path routing (hot-path wiring)

Deliverable: routing shims in `graph_expand_2hop.py` and
`graph_aware_retrieval.py`; RushDB path active when
`RUSHDB_AUTH_TOKEN` is set.  
Gate: davidath bench byte-identical to Phase 2 baseline;
`evals.regenold.runner` 276/276; OOS 21/21.  
Neo4j: parallel (both backends active during this phase).

### Phase 4 — Boot-time auto-seed + `/healthz/graph`

Deliverable: `_maybe_auto_seed_rushdb()` hook in `main.py`;
`/healthz/graph` prefers RushDB stats.  
Gate: live probe `curl /healthz/graph` returns `graph_ok=true`
with RushDB node counts; boot logs show `action=seed-completed`.  
Neo4j: parallel.

### Phase 5 — Neo4j retirement

Deliverable: remove Neo4j env vars from Railway; delete dead code
(`graph/ontology.py`, `graph/reasoning.py`, `seed_neo4j_kb.py`);
update `railway.toml`; update `CLAUDE.md`.

```bash
railway variables --unset NEO4J_URI NEO4J_USER NEO4J_PASSWORD
railway variables --unset NEO4J_AUTO_SEED
```

Gate: live probe confirms `NEO4J_URI` unset; `/healthz/graph` returns
`graph_enabled=false` for the Neo4j path (existing behaviour for
disabled Neo4j); all 4 bench gates green.

---

## 6. Testing

| Test file | What it covers |
|---|---|
| `tests/test_rushdb_client.py` (new) | Timeout (50ms), fail-soft on SDK exception, 2-round 2-hop correctness, definition exact + $contains fallback, empty seed returns `[]` not exception |
| `tests/test_seed_rushdb_kb.py` (new) | Record counts per label (505 total), `cross_refs` completeness on a sampled Article, `KB_METADATA` idempotency (second run = skip), dry-run returns correct structure without writing |
| `tests/test_graph_expand_2hop.py` (existing) | Run with `RUSHDB_AUTH_TOKEN` unset → passthrough to in-memory fallback; Neo4j path isolated behind `NEO4J_URI` gate |
| `tests/test_graph_aware_wire.py` (existing) | Same isolation as above |
| Davidath bench | Byte-identical to pre-migration baseline on all rubric axes |
| `evals.regenold.runner` | 276/276 |
| OOS probe | 21/21, 0 leaks |

---

## 7. Impact on Current Metrics

| Metric | Before | After | Notes |
|---|---|---|---|
| Davidath RefL / RefS | 0.5776 / 0.4658 | **No change** | Graph BM25-saturated (R31/R35/R69) |
| Davidath Ans Strict | 0.3013 | **No change** | |
| Live rep-100 RefL | 0.6773 | **No change** | Same xref data, same 2-hop semantics |
| V2 mt coherence | 0.28 | **No change** | Not graph-dependent |
| Definition lookup quality | Baseline | **Equal or marginally better** | RushDB `$contains` on `term_slug` is equivalent to Neo4j substring match |
| Boot time (seed check) | 3–8s (Cypher queries) | **< 1s** | One HTTP metadata check |
| Cold-start failure surface | Present (R78.1 class) | **Reduced** | Seed completes in one `create_many()` call before first request |
| Operational complexity | 1,012 LOC + Cypher | **~200 LOC + SDK** | |

**One genuine risk:** RushDB is a cloud API. The existing 50ms
`ThreadPoolExecutor` timeout covers expected latency, but if Railway →
RushDB round-trip degrades (e.g. cold-start cloud functions on the
RushDB side), the engine silently falls back to the in-memory `kb_xrefs`
core graph — the same behaviour as today when Neo4j is unreachable.
No rubric regression; the fallback path is well-tested.

---

## 8. Out of Scope

- Using RushDB as an eval/benchmark ledger (separate project, no
  competition rubric impact)
- Using RushDB as a multi-turn session/anchor store (high rubric
  potential but requires new coreference architecture — separate design)
- Migrating the evidence/audit chain to RushDB (PostgreSQL is the
  correct backend for hash-chained tamper-evident audit)
- Vector search via RushDB (the embeddings index in
  `app/engines/embeddings_index.py` is already optimised for the local
  path)

---

## 9. Prerequisites

- [ ] Competition closed (see Section 0)
- [ ] `RUSHDB_AUTH_TOKEN` confirmed active on Railway (already set)
- [ ] `pip install rushdb` added to `requirements.txt`
- [ ] RushDB project created and empty (verify via dashboard)
- [ ] Neo4j instance still running during Phases 1–4 (parallel path)

# TrustGraph integration

Generated artefacts and the deployment path, against the official
[TrustGraph documentation](https://docs.trustgraph.ai/).

```
trustgraph-integration/
├── ontology/
│   ├── eu-ai-act.json            <- T-Box, TrustGraph native config format  (GENERATED)
│   └── codexai-compliance.ttl    <- inherited, inert; see "What was here before"
└── knowledge/
    └── eu-ai-act-core.ttl        <- A-Box, 1,071 triples for tg-load-turtle (GENERATED)
```

Both generated files come from `scripts/build_trustgraph_core.py` and are
**checked by CI** (`tests/test_trustgraph_ontology.py`). Do not hand-edit them —
change the registries in `app/data/ontology.py` and regenerate:

```bash
python scripts/build_trustgraph_core.py           # rebuild
python scripts/build_trustgraph_core.py --check   # what CI runs
```

## What was here before, and why it did nothing

`codexai-compliance.ttl` — 1,129 lines inherited from the sibling CodexAI
project at `6d6d019` ("initial extraction"), with **zero call sites** for five
rounds (R393). Parsed for the first time in R397:

| | |
| :--- | :--- |
| parses? | yes — well-formed, 699 triples, 27 classes, 34 object properties |
| `owl:NamedIndividual` | **0** — a T-Box with no A-Box; it asserts no fact about any Article |
| subjects in an EU-AI-Act namespace | **0** |
| actual domain | compliance-*programme* management: `AttackAttempt`, `AtlasTechnique`, `ComplianceGap`, `MigrationTask`, `SecurityCampaign` |
| loadable by the documented CLI? | **no** — ontologies load as native JSON (`tg-put-config-item --type ontology`); Turtle ontologies are Workbench-import only |

It is kept, not deleted: `eu-ai-act.json` aligns onto the eight classes that
*are* Regulation structure (`Article`, `Annex`, `Chapter`, `Recital`,
`Obligation`, `OperatorRole`, `Penalty`, `Deadline`) with `owl:equivalentClass`
/ `owl:equivalentProperty`, and a test asserts every alignment target really
exists in the file — so "builds on the existing ontology" is checked, not
claimed. The 19 security-campaign classes are left out, following TrustGraph's
own guidance to "keep ontologies focused with 5-10 key classes".

## Loading it

Two paths, because TrustGraph loads schema and instances differently.

```bash
# 1. the ontology (T-Box) — native JSON is the only CLI-loadable form
tg-put-config-item --type ontology --key eu-ai-act --stdin < ontology/eu-ai-act.json

# 2. the knowledge (A-Box) — Turtle, parsed by rdflib inside the tool
tg-load-turtle -f default --document-id eu-ai-act-core knowledge/eu-ai-act-core.ttl

# verify
tg-invoke-sparql-query -q 'SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }'
```

`tg-load-turtle` parses with `rdflib`, and the generator serialises with
`rdflib`, so a file this repo emits is parseable by the tool that consumes it
**by construction** — and CI re-parses it on every run.

## The coordinate universe — what this actually complements

`article_existence` answers *"is Article 13 a real Article?"* and stops at the 126
heads. **Nothing answered *"is `Article 13.3` a real coordinate?"*** — the
sub-point text is derived by regex at call time rather than stored, so there was
no set to ask.

That is the grain that matters. The R386 deepener emits paragraph grain by
default (`REGENOLD_REF_GRAIN_DEPTH=1`), the official rubric scores Reference
Correctness **Strict** at sub-point grain, and Ref Strict is our largest gap.

`app/data/provision_coordinates.py` (generated) closes it: **655 paragraph
coordinates**, verified against the adopted text —

| check | result |
| :--- | :--- |
| Article 3 | 68 paragraphs — its 68 definitions ✓ |
| Article 5 | 8 ✓ |
| Article 13 | 3 ✓ |
| total | 655, independently corroborating the production Neo4j graph's **658** `Paragraph` nodes (R380) |

```python
from app.data.provision_coordinates import coordinate_exists
coordinate_exists("Article 13.3")   # True
coordinate_exists("Article 13.9")   # False   <- article_existence cannot see this
coordinate_exists("Article 3.68")   # True
coordinate_exists("Article 3.69")   # False
```

No runtime dependency (rdflib stays dev-only), O(1) membership, zero latency.

### Point grain comes from the existing knowledge graph

`get_provision_text` cannot enumerate letters, and both reasons are worth knowing:

1. **Silent parent fallback** — `get_provision_text("Article 3.1.z")` returns
   *Article 3.1's own text*, so every letter appears to exist when the paragraph
   carries no lettered points. A caller cannot tell it received a fallback.
2. **Roman sub-points flattened into the letter slot** — `Article 5.1.i` returns
   Article 5(1)(**h**)(i), so paragraph 1 looks like it has a ninth point when
   the Act gives it (a)-(h).

So point grain is taken from the **production Neo4j graph**, which models it
explicitly as `(Article|Annex)-[:HAS_PARAGRAPH]->(Paragraph)-[:HAS_POINT]->(Point)`
with `Paragraph.number` and `Point.letter` — **421 point coordinates**, exactly the
graph's `HAS_POINT` edge count:

```python
coordinate_exists("Article 5.1.a")   # True
coordinate_exists("Article 5.1.z")   # False  <- Article 5(1) stops at (h)
coordinate_exists("Annex III.1.z")   # False
coordinate_exists("Article 3.1.a")   # True   <- graph records no points here;
                                     #          conservative rather than wrong
```

Refresh it deliberately with `python scripts/build_trustgraph_core.py --from-graph`.
Without that flag the committed point set is **preserved**, so an offline rebuild
and CI's `--check` (which has no Neo4j) stay deterministic.

**Not yet wired into the wire path.** It is data and an oracle; nothing drops or
rewrites a reference today. Making it a wire guard is a reference-affecting
change and needs `gold_dropped_head` (AGENTS.md invariant #5, hard rule #8) —
and the prior question, *how often does the live path actually emit a
non-existent coordinate*, is unmeasured: the deterministic offline path emits
only heads, so it takes a wrapper run to answer.

## Deploying TrustGraph — the honest position

TrustGraph is **not a library**. There is no documented way to use its ontology,
RDF, SPARQL or knowledge-core functionality standalone; the deployment unit is a
container cluster (Pulsar or RabbitMQ, Cassandra, Qdrant, Garage/S3, plus the
processor containers), generated by `npx @trustgraph/config`.

**Capacity is not the blocker.** The Railway instance is 24 vCPU / 24 GB RAM,
clearing TrustGraph's stated floor (12 GB + 8 CPUs compose) with headroom. The
R393 claim that infrastructure disqualified it was wrong and was retracted in
`6b3ec35`.

Two real constraints remain, and both are measurable rather than assumed:

1. **Deployment model.** Railway builds one container per service. A compose
   cluster is a different shape; it would have to be decomposed into separate
   Railway services (or run on a VM / Kubernetes alongside).
2. **Latency budget.** We currently *beat* the 2026 frontier baseline on Speed
   by +7.0 pp. A message-bus hop per retrieval spends roughly that margin, and
   Speed is one of the eight scored axes. Any adoption should be A/B'd on
   latency before it becomes the retrieval path.

Because of (1) and (2), the artefacts here are deliberately useful **without**
the cluster: they are plain RDF, queryable locally with `rdflib` and SPARQL, and
ready to load the moment a TrustGraph instance exists.

## What the ontology contains

| class | instances | source |
| :--- | ---: | :--- |
| `Provision` (sub-points) | 663 | enumerated from the adopted text — see below |
| `Article` | 113 | `article_existence` (the canonical 126, minus Annexes) |
| `Annex` | 13 | same |
| `Obligation` | 86 | `ROLE_OBLIGATIONS` (role × risk class × provision) |
| `OperatorRole` | 9 | `ActorRole` |
| `RiskClass` | 7 | `RiskClass` |
| `ProhibitedPractice` | 8 | `PRACTICE_REGISTRY` (Article 5) |
| `HighRiskArea` | 8 | `ANNEX_III_REGISTRY` |
| `CompliancePhase` | 4 | `PHASE_REGISTRY` |

Every provision carries its verbatim adopted text (`eu-ai-act:verbatimText`) and
its wire citation (`eu-ai-act:citation`, `Article 13.3` form, never `Art. 13`).
Nothing is hand-asserted law — it is generated from data this repo already
verifies elsewhere.

⚠ **`ROLE_OBLIGATIONS` is a seed list, not a completeness list, and it is known
to be legally wrong in places** (CLAUDE.md R380: `Art. 13` bound to DEPLOYER,
`Art. 85`/`86` listed as obligations when they are rights). It is exported here
as-is on purpose. R365 measured this table at **0 % precision as a citation
oracle**, and the sibling repo measured that *fixing* two bindings to be
statute-correct added 8 non-gold references and 0 gold: **legally correct is not
gold-correct.** Do not "correct" these bindings and expect a score improvement —
that path is already measured and closed.

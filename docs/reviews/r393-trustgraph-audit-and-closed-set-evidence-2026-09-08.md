# R393 — the TrustGraph integration is a directory name; the transferable pattern is closed-set evidence completeness

**Date:** 2026-09-08
**Method:** every number below was produced by EXECUTION — a probe run, a live wrapper A/B, a
Cypher query against the production Aura instance — not by reading a diff or a README. Claims
that could not be reproduced are marked as such.

---

## 0. Headline

1. **There is no TrustGraph integration.** `trustgraph-integration/` contains exactly one file,
   a 1,129-line OWL/Turtle ontology, with **zero call sites**. No `rdflib`, no `trustgraph`, no
   `pyshacl`, no SPARQL in `requirements.txt` or `pyproject.toml`. The only Python reference is
   `tests/test_regenold_scope.py:1374`, asserting a dead prefix stays deleted. One commit
   (`6d6d019`, "initial extraction") — inherited weight from the sibling CodexAI / Legit AI
   project. This is the **fifth** instance of the port-drift pattern this repo has paid for
   (R329 rerank ×3, R330 semantic layer, R366 parent collapse).

2. **Adopting TrustGraph is disqualified on infrastructure, not on merit.** It is not a library:
   the deployment unit is a docker-compose / Kubernetes cluster of ~34 processor containers on an
   Apache Pulsar bus, plus Cassandra, Qdrant, Garage (S3) and the Prometheus/Grafana/Loki stack.
   Minimum footprint **12 GB RAM + 8 CPUs**. This service is a single FastAPI container on Railway
   with no GPU. Only the *patterns* transfer.

3. **The one TrustGraph practice that maps onto our measured gap was measured here and it
   works.** Daniel Davis asserts — without numbers — that "structured formats … improved responses
   despite the token overhead" because "the structure itself carries information." Executed as a
   clean 2×2 over the live wrapper, replacing a prose slab with a coordinate-labelled exhaustive
   member list moves member recall **62.1 % → 83.3 %, +21.2 pp**. That is the finding of the
   round, and it is now a flag.

---

## 1. What the existing "integration" actually is

```
trustgraph-integration/
└── ontology/
    └── codexai-compliance.ttl        1,129 lines, 0 call sites
```

The TTL extends AIRO / VAIR / W3C DPV-AIAct with a compliance-implementation layer — `Obligation`,
`Control`, `Evidence`, `ComplianceGap`, `MigrationTask`. Those concepts **did** reach production,
but as a **property-graph schema**, not via RDF: Aura carries `ControlImplementation`,
`EvidenceBundle`, `ComplianceGap`, `AuditResult`, `AISystem`, `RiskControl`, `NISTSubcategory`,
`ISOClause` labels with `tenant_id` constraints. So the TTL is a **stale parallel copy** of a
schema that already lives in Cypher.

⚠ **Namespace drift**: the TTL declares `https://w3id.org/codexai#`; `app/data/ontology_mapping_full.py:27`
uses `https://codexai.dev/ontology#`. They were never reconciled because nothing reads both.

**Disposition: the TTL is not deleted.** It is the only machine-readable statement of the
compliance-implementation model and it costs nothing at runtime (nothing imports it). It is
re-scoped in this round's README note as a design artefact, not an integration.

---

## 2. TrustGraph, executed rather than read

`github.com/trustgraph-ai/trustgraph`, Apache-2.0, 2,686 stars, last push 2026-09-03.

| layer | what it is | transferable here? |
| :--- | :--- | :--- |
| transport | Apache Pulsar / RabbitMQ pub-sub, ~34 containers | **No** — the bus IS the architecture |
| extraction | LLM emits `{subject, predicate, object}` JSON → slugified URIs → RDF | **No** — we parse a statute with known structure; LLM extraction would *lose* fidelity |
| GraphRAG query | 4 phases: Grounding → Exploration → Focus → Synthesis | **Partly** — see below |
| provenance | `trace_source_documents()` walks `prov:wasDerivedFrom` up to 4 hops | **Yes, and it is a critique of us** |
| storage | Cassandra / Neo4j / Memgraph / FalkorDB + Qdrant / Milvus | already have Neo4j |

**Their retrieval defaults, the only hard numbers anyone publishes for "how much graph context":**
`entity_limit=50`, `triple_limit=30`, `max_subgraph_size=150`, `max_path_length=2`, `edge_limit=25`.
Two hops, 150-node ceiling. Our `kg_context` truncates at `max_refs=8` — we are *far* more
conservative, which is the right direction for a conciseness-scored rubric.

### 2.1 The one architectural critique worth recording

TrustGraph derives a citation by **walking a provenance edge** from the retrieved fact back to its
source document. We do the opposite: `_add_prose_named_refs` (`app/routes/regenold.py:5600`)
**re-derives citations from the answer prose**, uncapped, and `_citable_base_guard_enabled()` is
**default OFF**, so prose-promotion is currently unconstrained by the retrieval universe.

That inversion is the documented root cause of our over-citation family (R298: 45/46 wrong refs
are *described in the prose*). It is not fixed in this round — flagged as the strongest
architectural lever available, and cheap: `_add_prose_named_refs` already **takes** a
`citable_bases` parameter and both call sites already pass it behind that default-OFF flag.

⚠ **CLAUDE.md correction.** The standing note "`_add_prose_named_refs` already takes a
`citable_bases` parameter and **neither call site passes it**" is **stale**. Both call sites
(`regenold.py:10584` and `:10930`) pass it today; it is the *flag* that is off, not the wiring.

### 2.2 On Daniel Davis's published practice — read the dates

His corpus splits into two eras of very different evidentiary quality.

* **2024 (measured).** Real tables: extraction yield rises monotonically as chunks shrink
  (Claude 3 Haiku, 10k-token doc, 8000→500 chars = +120 % edges), replicated across 8 models;
  Haiku beat Claude 3.5 Sonnet by 15.5 %; "no correlation between knowledge extraction performance
  and cost."
* **2025–26 (asserted).** The Context Graph Manifesto, the Memento series, TrustGraph 2.0
  explainability — **no published accuracy benchmark, no head-to-head against vector RAG, no eval
  methodology.**

⚠ **His own epistemic caveat is the most important sentence in the corpus.** After publishing the
edge-count tables he writes that whether more graph edges produce better RAG answers is something
he does not know. **He is optimising a proxy and says so.** That is precisely the trap this repo
has hit repeatedly — more references is not a better score, because Ref. Conciseness is a pure
count ratio.

⚠ **His position INVERTED between 2024 and 2025**: 2024 advocated "naive extraction" that "errs on
over-extraction"; 2025 asks "what *should* we extract?". Do not cite "TrustGraph advocates X"
without a date. The 2024 stance is the opposite of what a citation-precision rubric needs.

---

## 3. The measured defect: closed statutory sets arrive as proper subsets

`provision_text.select_relevant_paragraphs` is a lexical token-overlap ranker under a char budget.
Its own docstring: *"only WHICH sub-points are quoted is narrowed."* So a question that asks what
a provision **requires** is handed a proper subset of a closed set.

**Executed over the official 110-question batch at the live `_GROUNDING_REF_CHARS` of 1200**,
counting the members of every provision the graded July-7 run cited
(`scratchpad/closed_set_coverage.py`):

```
rows with a closed-set provision:      110/110
closed-set member coverage delivered:  1340/3863 = 34.7%

per-question coverage      0-24%: 19 rows   25-49%: 67   50-74%: 20   75-99%: 3   100%: 1
worst provisions   Annex I 22.0%   Article 5 15.3%   Article 50 24.8%   Annex IV 19.1%
```

**86 of 110 questions receive under half the statutory members they need.** This corroborates and
extends R391's hand count (Annex IV 0/8, Article 17 4/13) — no prompt instruction can recover a
member that is not in the prompt.

---

## 4. The lever, and the 2×2 that separates it from the confound

`REGENOLD_CLOSED_SET_SKELETON` prepends the **exhaustive member list** of a cited head to its
grounding entry, as `coordinate: leading clause`:

```
- [Annex IV]
  COMPLETE STRUCTURE of Annex IV — 25 members, this list is EXHAUSTIVE:
    Annex IV.1: A general description of the AI system i...
    Annex IV.1.e: the description of the hardware on which...
    ...
  VERBATIM (question-relevant): <the shipped selector output, unchanged>
```

Members come from `provision_hierarchy.closed_set_members()` — a new **pure, cached** accessor over
the payload the Neo4j seeder already writes (658 Paragraph / 421 Point / 37 SubPoint nodes). No
graph call, no network, 0.167 ms warm. **The Aura Paragraph/Point nodes are a mirror of this same
payload**, so reading it locally is the same data without the driver, the latency or the failure mode.

### Prompt cost, measured over 8 closed-set provisions

| arm | structural coverage | chars | vs shipped |
| :--- | ---: | ---: | ---: |
| as shipped | 28.6 % (34/119) | 9,168 | 1.00× |
| `REGENOLD_FULL_PROVISION_EVIDENCE` | 100 % | 36,059 | 3.93× |
| **closed-set skeleton (lead=40)** | **100 %** | **17,182** | **1.87×** |

Same completeness as blunt whole-provision substitution at **less than half the prompt cost**.
Lead length was swept: 0 gives presence without statability; 60 and 90 cost 2.13× and 2.49× for no
additional coverage. Default 40.

### The clean 2×2 — n=10, four arms interleaved per row, live wrapper (`claude-sonnet-4-6`)

An earlier n=8 screen bundled the skeleton with a terse answer contract and appeared to improve
both axes. **That reading was wrong** — it had no terse-only arm, so it credited the pair with the
contract's conciseness *and* with recall the pair did not deliver. Adding the fourth arm inverts
the interpretation (hard rule #6):

| arm | member recall | chars | Ans. Conciseness |
| :--- | ---: | ---: | ---: |
| A — evidence shipped, contract shipped | 62.1 % | 1,409 | 48.0 |
| **C — skeleton only** | **83.3 % (+21.2)** | 1,892 (1.34×) | 36.8 |
| **T — terse contract only** | **34.8 % (−27.3)** | 625 (0.44×) | 97.4 |
| **D — both** | 61.4 % (−0.8) | **737 (0.52×)** | **88.3** |

**The terse contract is the Overall lever; the skeleton is what makes it non-destructive.** Alone,
terseness buys +49 pp of Ans. Conciseness by destroying 27 pp of answer completeness. With the
closed set delivered, that cost falls to −0.8 pp and the conciseness gain survives.

**This is the missing half of `REGENOLD_PROMPT_COMPACT`**, and it explains why that lever has sat
at default OFF since R391: on its own it trades correctness for brevity. The natural next gate is
the 2×2 of `REGENOLD_CLOSED_SET_SKELETON` × `REGENOLD_PROMPT_COMPACT` on the live batch.

⚠ n=10, one model, synthetic single-provision prompts, and the recall metric is a lexical proxy,
not the official criteria judge. This is a **screen**, not a gate.

---

## 5. Why it ships default OFF

It is **prompt-side, therefore NOT reference-neutral** (AGENTS.md invariant #5). The wire ref list
is recomputed from the final prose by `_add_prose_named_refs`, which is uncapped and whose citable-base
guard is default OFF — so showing more statutory text means more cross-references the model can echo
onto the wire.

`_extract_context_grounded_refs` reads *context structures*, never rendered text, so the skeleton
cannot mint a citable head **directly** (pinned by test). That is a necessary property, **not** a
sufficient one, and it is explicitly not claimed as reference-neutrality end to end. The gate is
`evals.harness.easyhard_ab` / `gold_dropped_head`.

**Tests** — `tests/test_r393_closed_set_skeleton.py`, 37 tests, all on rendered artefacts or measured
invariants, never on the shape of the code:

* two-sided flag behaviour, including the **inert-feature tripwire** (the OFF arm's grounding block
  is byte-identical, and OFF really does still suppress it);
* **prove-it-fires on the real renderer** — `_render_grounding_text` differs ON vs OFF and the ON arm
  lands the official answer key's coordinates (`Article 13.3.a`, `Annex IV.1.e`) that are absent OFF;
* every emitted coordinate is the strict wire shape (invariant #1) and resolves in the 126-ref lint
  floor (invariant #2);
* numeric knobs fail OPEN and clamp;
* a **premise tripwire**: if the shipped selector ever delivers >75 % of closed-set members, the test
  fails and tells you to re-measure before keeping the lever.

Full suite: **7,416 passed / 0 failed**, against a stashed-baseline **7,379 passed / 0 failed** —
the delta is exactly the 37 new tests. Two-arm, in place, one change differing.

⚠ An intermediate run reported 1 failure in `test_ontology_leap_hardening`. It was a **measurement
artefact**: that test uses `inspect.getsource`, and the background suite was reading the file while a
cleanup edit shifted its line numbers. It does not reproduce on a stable tree.

---

## 6. Graph findings recorded in passing (not fixed this round)

* **17 shadow `Article` nodes.** Aura carries `ART4/5/6/9/10/11/12/13/14/15/17/26/43/50/53/55/95`
  with **zero text, no embedding**, and `number` holding the id — alongside the real
  `article_13`-style nodes (3,057 chars, embedded, 3 paragraphs, 6 points). **148 `REQUIRES` /
  `APPLIES_TO_ROLE` edges hang off the textless shadows**, and there is **no path joining the two
  islands within 3 hops**, so that layer is unreachable from any text, vector or fulltext hit.
  `reason_compliance` (imported at `_graph_rag_impl.py:7055`) is the affected consumer.
  ⚠ **Correction to an earlier read in this round:** `HAS_OBLIGATION_ARTICLE` (36 edges) points at
  the **text** nodes, so `kg_context.py:251`'s role enrichment is unaffected. Severity is lower than
  first stated — it strands the `Obligation`-node layer, not the role layer.
  This is exactly the entity-resolution problem TrustGraph's naive `to_uri()` slugification would
  also produce; having canonical provision ids is our advantage and we broke it in one place.
* **130 `Article` nodes for a 113-article Act**; the 17 extras are those shadows.
* Provision vectors are **128-D TF-IDF/SVD, not neural**, and the dense fill flips to SVD on a Cohere
  429 — observed live during this round's gate run. Retrieval is therefore not deterministic under
  rate limiting. Both A/B arms are affected equally, so a paired gate is still valid.

---

## 7. What ships

| flag | default | what it does |
| :--- | :--- | :--- |
| `REGENOLD_CLOSED_SET_SKELETON` | `0` | Prepend the exhaustive member list of a cited head to its grounding entry |
| `REGENOLD_CLOSED_SET_SKELETON_LEAD` | `40` | Chars of each member's own text shown beside its coordinate; 0 = coordinates only |
| `REGENOLD_CLOSED_SET_MIN_MEMBERS` | `3` | Skip provisions too small to be a closed set |

All three registered in `_engine_cache_key` and passing the R355 AST gate. Nothing in production
behaviour changes on merge.

**Open, in priority order:**
1. The live `gold_dropped_head` gate for `REGENOLD_CLOSED_SET_SKELETON` (n=129).
2. The 2×2 against `REGENOLD_PROMPT_COMPACT` — on the 2×2 above this is the pairing that carries
   the Overall gain.
3. The citable-base guard (§2.1) — flipping `_citable_base_guard_enabled()` is an ADD-removing
   change that cannot invent a reference, and it directly addresses the over-citation family.
4. R391's `+15.06 pp Ref Strict` claim has **no committed replay script** and its live n=110 gate is
   **arm A only, 57/110 rows**. It is the largest unverified number currently in CLAUDE.md.

---

## 8. Hard mode — the drift premise, measured, and mostly refuted

**Asked:** make hard mode robust so it does not drift under the evaluator's adversarial pushback.
**Executed:** 12 official questions, turn 1 then the byte-exact `PUSHBACK_TEMPLATE`, live over the
wrapper on `claude-opus-5`, comparing the two turns per row
(`scratchpad/drift_probe.py`).

| | turn 1 | post-pushback | |
| :--- | ---: | ---: | :--- |
| answer chars | 789 | 771 | **0.98×** |
| Ans. Conciseness | 81.8 | 82.3 | slightly BETTER |
| refs/row | 2.58 | 2.67 | +0.09 |
| Ref. Conciseness | 56.7 | 53.7 | **−3.0 pp** |
| byte-identical answers | — | **6/12** | |
| reference Jaccard | — | 0.88 | |

**The drift premise does not hold on answers.** Answers do not inflate under pushback (0.98×),
half are byte-identical, and Ans. Conciseness slightly improves. The V1
`USER_CHALLENGE_BREVITY_CLAUSE` is active on HEAD (`REGENOLD_PROMPT_V2` is default OFF after the
R379 gate failed) and its substance is right — *"say the same thing at the SAME length or shorter …
do not add citations you would not have given the first time"* — and `is_challenge_turn` fires on
the evaluator's verbatim template and not on a plain question. It is working.

⚠ **The one apparent capitulation is a false positive of my own metric.** `rg_008` tripped a
leading-verdict-word heuristic, but both turns say the same thing (high-risk, Art. 6(1), Annex I,
MDR classes IIa/IIb/III) with **identical references**; only the opening reformatted from
"AI safety components within…" to "Yes, high-risk…". Corrected count: **0/12 genuine
capitulations.**

**The one real cost is reference growth**, not answer drift: `rg_012` went
`['Annex III.8']` → `['Annex III.8', 'Article 6.2']`. That is Ref. Conciseness, a pure count ratio.

### 8.1 `REGENOLD_PUSHBACK_REF_FREEZE` (R302, default OFF) — the aimed lever, NOT resolved

Same 12 rows, freeze ON:

| arm | refs/row turn 1 | refs/row post | within-row delta |
| :--- | ---: | ---: | ---: |
| baseline | 2.58 | 2.67 | **+0.09** |
| freeze ON | 2.92 | 2.92 | **+0.00** |

The within-row paired delta goes to zero, which is what a freeze does by construction.

⚠ **But the run is UNDERPOWERED and the control says so.** Turn 1 is not a challenge turn, so the
freeze is provably inert there — yet turn-1 refs/row moved **2.58 → 2.92 between arms, 0.34**, which
is ~4× the effect being measured. Generation variance dominates. This reproduces the documented
noise floor (`project_easyhard_ab_noise_floor_n40`, and R381's finding that 8 of 13 control rows
changed with the lever inert).

**Disposition: NOT flipped.** The mechanism is confirmed structurally; the score benefit is
unresolved and n=12 cannot resolve it. It needs a properly powered paired run (n ≥ 120) with the
gold gate, like any reference-dropping lever.

### 8.2 What this means for the hard/easy gap

Hard mode's lower official Overall is therefore **not** explained by pushback drift on this
evidence. Post-pushback answers are marginally shorter and marginally more concise. The gap is far
more likely the same closed-set incompleteness measured in §3, which is question-shaped and applies
to both modes — i.e. **§4 is the hard-mode lever too**, and no separate anti-drift mechanism is
warranted until a powered run says otherwise.

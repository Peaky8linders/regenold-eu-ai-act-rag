# R324 — Knowledge-graph design proposal

Synthesis of 6 confirmed + 7 refuted findings. Every number below is measured against
the live Aura instance `0644b854` and HEAD `bb3ea81` unless marked UNVERIFIED.

---

## 1. State of the graph — what is actually true today

| Dimension | State | Evidence |
| --- | --- | --- |
| Instance | Aura `0644b854`, Neo4j 5.27-aura enterprise, reachable, `graph_ok=true` **and now honest** (R323 `bb3ea81` fixed the false-green probe) | `/healthz/graph` on prod; `health_check()` on a dead driver now returns `unhealthy` |
| Volume | 1751 nodes / 1972 rels / 18 labels / 16 rel types / 18 constraints / 22 RANGE + 7 VECTOR + 1 FULLTEXT index | live `db.labels()`, `db.relationshipTypes()` |
| Provision coverage | 113 Articles + 13 Annexes, **100%**; 656 Paragraph + 416 Point + 37 SubPoint | live counts |
| Legal provenance | **Already ELI-shaped and correct.** Every Article carries `eli_uri`, `celex_id`, `legal_link`, `strict_citation`, `legal_type`. `strict_citation` null on **0/113** | `MATCH (a:Article) WHERE a.strict_citation IS NULL` → 0 |
| CELEX pin | `32024R1689` (pre-Omnibus) — **correct**, verified against the Cellar at similarity 1.0000 across 126 provisions (R321) | R316/R321 |
| Embeddings | 1483 nodes carry a 128-float `embedding`, produced by the SAME `embeddings_index` TF-IDF→SVD-128 that is wired at 4 production sites | `seed_neo4j_kb.py:1537` |
| Cross-references | 248 `CROSS_REFERENCES`, matching `kb_xrefs.all_edges()` minus exactly 1 | live count + diff |
| Recital anchors | **5 edges covering 2 of 113 articles** (Art 5→18/30/31/44, Art 52→112). 175 of 180 recitals orphaned | live `HAS_RECITAL_ANCHOR` |
| Is it *used*? | **Yes, on the answer path** — `kg_context.render_kg_context` injects paragraph/point text into the Stage-2 prompt, default ON. **No, on the ranking path** — R252 demoted graph-primary retrieval; R295 measured the fusion cap discarding ~96–99% of hop2 refs | `_graph_rag_impl.py:6218`; R295 |

**Honest summary:** the graph is well-formed, correctly pinned, richly seeded, and
genuinely on the answer path. It is *not* a retrieval ranker and should not become one.
The remaining defects are (a) a stale seed carrying a now-fixed parser bug and (b) an
unmetered, uncached, partly-fictional prompt block.

---

## 2. The gaps that matter — ranked

Ordered by value-per-risk. **(b) wiring gaps outrank (a) data gaps** — the graph already
holds more than the code reads.

### W1 — kg_context is recomputed 3× per request with no cache (WIRING) — **ship now**

* **Defect.** `render_kg_context` has one caller (`_render_supplementary_sections`,
  `_graph_rag_impl.py:6218`) reached from `_build_context_references_block`, which runs
  3× per Stage-2 request (polish + unknown-citation guard + self-contradiction guard),
  plus a 4th when drift fires. `grep -cE "lru_cache|cache" app/engines/kg_context.py` = **0**.
* **Evidence.** Instrumented `_two_stage_generate` with a stubbed LLM, graph live:
  `render_kg_context calls: 3`, `chars: [16396,16396,16396]`, `ms: [571,115,100]`;
  9 graph fetches, 784 ms total, **~215 ms strictly duplicated**.
* **Fix.** Memoise per request on the frozen ref tuple via **ContextVar**, cleared per
  request — *not* `functools.lru_cache`, which would serve stale paragraph text across
  requests and survive a re-seed. The repo already uses this pattern (`ReasoningTrace`,
  `_ANSWER_NO_CAP`).
* **Risk.** None. Byte-identical output for identical refs ⇒ prompt unchanged ⇒ no
  reference can move. No `_engine_cache_key` entry needed (does not flip behaviour).
* **Measure.** Assert 1 call/request under instrumentation; davidath byte-identical
  (it is, by construction — Stage-2 never runs under `provider=cli`).

### W2 — the kg_context block inflates the citation-drift allowlist 5.75× (WIRING) — **the one nobody spotted**

* **Defect.** `_extract_context_grounded_refs` mines
  `_build_context_references_block(context, include_grounding=False)`, and
  `_render_supplementary_sections` runs *unconditionally* there — so kg_context text
  feeds the guard's allowlist of citations the model is permitted to keep.
* **Evidence.** 4-ref context, graph live: `REGENOLD_KG_CONTEXT=1` → allowlist **23** refs,
  block 16,576 chars; `=0` → allowlist **4** refs, block **139** chars. kg_context is
  **99.2%** of that block. R288.1 explicitly excluded the R288 verbatim section from this
  mining for exactly this reason; kg_context never got the same treatment.
* **Fix.** Exclude the kg_context section from `_extract_context_grounded_refs`'s mining,
  mirroring R288.1. Zero characters removed from the prompt the model sees.
* **Risk.** This *tightens* a guard, so it can only remove citations the model invented
  beyond retrieval — but it is reference-affecting via the drift scrubber, so it needs
  the gold-bearing gate.
* **Measure.** `evals.harness.easyhard_ab` with `gold_dropped == 0`. `ab_judge` alone is
  **not** sufficient (no minimality term — how R142.1 slipped through).

### W3 — "KNOWLEDGE-GRAPH CROSS-REGULATORY EDGES" is 100% hardcoded Python (WIRING)

* **Defect.** `_CROSS_REGULATORY_CYPHER` (`kg_context.py:280`) filters on
  `ext.framework IN ['GDPR','EU_Charter','Charter']` and matches `RELATES_TO` /
  `HAS_EXTERNAL_REF`. **None of those relationship types or property keys exist.**
* **Evidence.** Live: `db.relationshipTypes()` has neither; `db.propertyKeys()` has
  neither `framework` nor `relation`; `MATCH (n) WHERE n.framework IS NOT NULL` = 0.
  The Cypher returns 3 rows, all `target: None`, all filtered at `:352`, so
  `_STATIC_CROSS_REGULATORY_MAP` supplies every record. **With `NEO4J_URI=""` the block
  renders byte-identical** (11 records, 1481 chars) — it is graph-*independent*, not
  merely falling back. 5 Neo4j UNRECOGNIZED warnings per call.
* **Fix, split by risk.** (i) **Free:** delete the dead Cypher + its `execute_read`
  branch — measured behaviour-identical, kills the warning storm. (ii) **Gated:** gate the
  whole block behind `REGENOLD_KG_CROSS_REG` **default OFF** and A/B it back on. It is
  1481 chars of un-A/B'd Stage-2 budget on Answer-Conciseness — the one official axis we
  lead, zero headroom — i.e. 4× the 367-char provenance block already defaulted OFF for
  precisely that reason.
* **Do NOT** seed GDPR/Charter nodes (see §4).
* **Measure.** (i) needs nothing. (ii) `easyhard_ab`, `gold_dropped == 0`.

### W4 — `recitals_for_article` fires ~1.84 Cyphers/request, 88.6% structurally empty (WIRING)

* **Evidence.** 257 requests → 473 calls; only 54 (11.4%) target an anchored article.
  p50 30.0 ms/call. On 24 davidath QA questions this was **41 of 45 total Cyphers (91%)**.
* **Why it matters — and the lane's stated reason is the weak one.** ~50 ms against a
  20–60 s live request is 0.1–0.3%, i.e. *not* a latency win. The real cost is that
  `record_graph_failure` / `graph_circuit_open` (`app/graph/timeouts.py`) is **shared** by
  three consumers (`graph_aware_retrieval`, `graph_expand_2hop`, kg_context). These
  near-useless calls dominate graph-aware call volume, so under jitter they are the main
  source of breaker-opening failures that then suppress the *productive* traversals.
* **Fix.** Resolve the anchored-article set from the graph once per process
  (`MATCH (a:Article)-[:HAS_RECITAL_ANCHOR]->(:Recital) RETURN DISTINCT a.number`,
  label-scoped) and short-circuit. **Cache only on a successful non-error read** — caching
  an empty set produced by a cold/breaker-open boot would permanently disable recital
  grounding, which is strictly worse than today. Also reject annex-shaped refs before the
  Article-scoped Cypher (9/473 calls).
* **Do NOT hardcode `{"5","52"}`** — anchors are seed-derived from KB stub prose, so a
  stub edit silently kills a working anchor.
* **Measure.** `answer_text` + `references` diff over 257 questions ON vs OFF → expect
  0 rows changed; call count 473 → ~54. davidath is unusable here (no `NEO4J_URI` on the
  bench ⇒ code unreachable).
* **UNVERIFIED:** whether `REGENOLD_GRAPH_AWARE=1` is set on the **Railway dashboard**.
  `railway.toml [deploy.envs]` has never applied (R306). If unset, this is dev/eval-only.

### D1 — annex section-collapse: fixed in code, **stale in the graph** (DATA)

* **Defect (was).** `_annex_items` returned a flat `dict[int,str]`, so annexes whose
  sections restart numbering collapsed last-writer-wins. Annex VIII (A:1-13, B:1-9, C:1-5
  = 27 real items) → 13 keys, 14 unreachable; `Annex VIII(1)` returned Section C's
  *deployer* text under a citation whose Section A item says *provider*. Annex XI(2)
  returned Section 2's red-teaming text (systemic-risk only), **overwriting** Section 1
  item 2 (Art 53(1)(a), all GPAI providers) — legally inverted. Annex I(1) (the machinery
  Directive, the canonical Annex I example) and (13) unreachable.
* **Status.** Fixed at HEAD (`e6ed727`, section-aware parse). **But:**
  * `annex_items_sectioned` has **zero production importers** — `provision_hierarchy.py:213`
    still calls flat `_annex_items`, so a re-seed only fixes Annex I (18→20) and leaves
    Annex VIII at 13 and XI at 3.
  * The **live graph is stale**: measured today `annex_I=18, annex_VIII=13, annex_XI=3`,
    `seeded_at 2026-08-08T13:35:58Z` — i.e. it is still serving `annex_VIII_1 = "...deployer"`.
* **Fix.** Wire `annex_items_sectioned` into `provision_hierarchy`, emit section-qualified
  ids (`annex_VIII_A_1`), keep bare `annex_VIII_N` resolving to the **first** section so no
  existing citation is invalidated, then re-seed.
* **Risk.** Text-only + additive ids ⇒ no reference removed ⇒ hard rule #8 not engaged.
  R323's already-verified gates: davidath byte-identical (AnsS 0.4072 / RefL 0.8394 /
  RefS 0.5536 / RefC 0.4390 / Tone 1.0), 276-runner 255/255, 96 tests.
* **Measure.** After re-seed expect `annex_VIII` 13→27, `annex_XI` 3→5, `annex_I` 18→20;
  `provision_exists` over every Annex ref in `evals/bench/results` must stay 100%.

### D2 — no question→section routing for Annex VIII (DATA/WIRING, small)

`select_relevant_paragraphs('Annex VIII', <Art 49(1) provider question>)` and the
Art 49(2) question return **byte-identical** grounding post-fix. Statutory addressees
differ: 49(1)→Section A, 49(2)→Section B, 49(3)→Section C. Fix: route on the addressee,
default to Section A (current behaviour) ⇒ strictly additive.

### D3 — CROSS_REFERENCES under-covers by ~139 prose citations (DATA) — **do not "fix" naively**

Real gap, precisely measured (Art 99 missing 11, Art 60 10, Art 12 5…), precision of the
prose-mined candidates 24/24 in a random sample. **But the obvious fix drops gold.**
`kb_search._xref_in_degree()` reads the **FULL** graph (`kb_search.py:1055-1058`, R57-C —
CLAUDE.md line 1508 claiming "core" is **stale**) and feeds `_confidence_boost` on the
live ranking path. Simulating the 139-edge backfill over all 476 davidath rows:
61/96 target articles change their boost; 43/476 rows change top-3 against a QA budget of
3; **gold lost at k=3 (Article 16), k=5 (Article 50), k=8 (Art 80, Art 95)**, gains 0/2/3.
Hard rule #8 ⇒ rejection, not a trade. See §5 Phase 4 for the only safe route.

### D4 — one edge silently dropped at seed time (DATA, low)

`Art. 6.3 → Art. 49` is discarded because no `article_6.3` node exists (`seed_neo4j_kb`
and `embedded_graph.py:167` both filter unknown sources — so a seeder-only fix would make
the two backends disagree). **Impact today: none** — `cross_refs('Art. 6.3')` still returns
it in-process, and the only graph consumer of intra-Act `CROSS_REFERENCES` is
`graph_expand_2hop`, whose code default is OFF. **Do not re-home it onto Article 6**: that
makes Article 49 a 1-hop neighbour of a hub present on most classification questions, and
R295 recorded Article 49 as a named polluter (`st_v4_002`, gold Article 5).

---

## 3. Proposed target schema

Convergence target. The graph is **already ~80% ELI-aligned** on Articles; the gap is that
sub-provision nodes carry none of it. Rationale per block.

```cypher
// ─── PROVISION HIERARCHY  (Akoma Ntoso: act > article > paragraph > point > subpoint) ───
(:Article  {id, number, title, text, chapter,
            strict_citation,          // "Article 6"        <- wire form, hard rule #1
            legal_type,               // "article"|"annex"
            eli_uri, celex_id, legal_link,   // ELI  <- ALREADY PRESENT, 0/113 null
            embedding, vector_chunk_ids})
(:Annex    { ...same... })
(:Paragraph{id, number, text, embedding,
            + strict_citation,        // ADDITIVE  "Article 6.3"
            + eli_uri,                // ADDITIVE  ELI fragment of the parent
            + section_label})         // ADDITIVE  "A"|"B"|"C"|null   <- D1
(:Point    { ...same additive set... })
(:SubPoint { ...same additive set... })

(:Article)-[:HAS_PARAGRAPH]->(:Paragraph)-[:HAS_POINT]->(:Point)-[:HAS_SUBPOINT]->(:SubPoint)
(:Annex)  -[:HAS_PARAGRAPH]->(:Paragraph)          // BREAKING-ish: ids gain a section segment (D1)
                                                    //   annex_VIII_1 -> annex_VIII_A_1
                                                    //   bare form MUST still resolve (first section)

// ─── LEGAL RELATIONS  (LegalRuleML: normative refs, deontic subject) ───
(:Article)-[:CROSS_REFERENCES {source: "regex"|"manual"|"prose"}]->(:Article|:Annex)
                                                    // ADDITIVE property; see D3 for why the
                                                    // prose-sourced edges must be tier-separated
(:Article)-[:HAS_RECITAL_ANCHOR]->(:Recital)        // 5 edges. DO NOT synthesise more (§4)
(:Article)-[:HAS_OBLIGATION]->(:Obligation)
(:Obligation)-[:APPLIES_AT]->(:RiskLevel)
(:Obligation)-[:APPLIES_TO]->(:OperatorRole)        // LegalRuleML deontic subject
(:AnnexIIICategory)-[:TRIGGERS_HIGH_RISK_UNDER]->(:Article)
(:Practice)-[:PROHIBITED_UNDER]->(:Article)

// ─── PROVENANCE  (ELI) ───
(:LegalInstrument {celex_id: "32024R1689", eli_uri, effective_date: "2024-08-01"})
(:Article|:Annex)-[:HAS_PROVENANCE]->(:LegalInstrument)
(:Guideline)-[:INTERPRETS]->(:Article)              // guidelines carry interprets_celex,
                                                    // NEVER the act's own celex_id

// ─── EXPLICITLY NOT IN SCOPE ───
// (:ExternalProvision {framework:"GDPR"|"Charter"})  <-- REJECTED, see §4
```

**Change ledger**

| Change | Kind | Why |
| --- | --- | --- |
| `strict_citation` on Paragraph/Point/SubPoint | ADDITIVE | Today only Articles carry it; sub-provision nodes are what kg_context renders, so the wire-legal string should live where the text lives (hard rule #1) |
| `eli_uri` on sub-provision nodes | ADDITIVE | ELI addresses fragments; we already have the parent URI |
| `section_label` on annex Paragraphs | ADDITIVE | Makes D1 queryable rather than implicit in the id |
| Section-qualified annex ids | **BREAKING for graph ids, ADDITIVE at the wire** | Bare `annex_VIII_N` must keep resolving to Section A or existing citations break |
| `source` property on CROSS_REFERENCES | ADDITIVE | Lets a prose-mined tier be added *and excluded from `_xref_in_degree`* (D3) |
| GDPR/Charter external nodes | **REJECTED** | §4 |

---

## 4. What NOT to do

| Proposal | Verdict | Reason |
| --- | --- | --- |
| Seed GDPR / EU Charter / MDR nodes so the cross-regulatory heading becomes true | **REJECTED** | Puts foreign article numbers one hop from the wire, defended only by regex. R321 and R322-B each needed a guard round (prefix form, then postpositive `Article 35 GDPR`) to stop foreign numbers being promoted as AI Act citations — and Articles 5/21/35 all exist in the Act, so a wrong citation is wire-legal and passes every validator |
| Backfill the 139 prose-mined `CROSS_REFERENCES` into the full graph | **REJECTED as proposed** | Its stated safety premise is false: `_xref_in_degree` reads the FULL graph (R57-C), not core. Measured over 476 davidath rows: gold lost at k=3/5/8. Hard rule #8 |
| Synthesise more `recital → article` anchors from recital prose | **REJECTED** | 30 of 180 recitals mention "Article N" and 22 of those point at TFEU/TEU/Directive 2016/680. ~4 genuine edges for ~28 hallucinated ones. Hard rule #4. Already closed in R294 |
| `REGENOLD_KG_MAX_CHARS ≈ 4000` as a prompt-bloat cap | **REJECTED at that value** | Structurally the R319 experiment, which shrank context ~11k chars and measured `ref_loose 0.8143 → 0.6786`, p=0.039, gold dropped, and was reverted. Article 5's *first* unit (the (a)–(h) closed set) alone exceeds 4000 — decapitating a closed set is the exact R306 failure. HEAD already ships `REGENOLD_KG_MAX_CHARS=16000`; if a size lever is wanted, cap **per ref** or lower `REGENOLD_KG_MAX_REFS`, never a global tail cut |
| Re-home `Art. 6.3 → Art. 49` onto Article 6 | **REJECTED** | Not semantics-preserving (49(2) is the *derogation* duty, not 49(1)) and makes a hub 1-hop from Article 49, a measured polluter (R295 `st_v4_002`) |
| Wire the 7 VECTOR indexes / 1483 embeddings into retrieval | **REJECTED** | The same TF-IDF→SVD-128 index is already wired at 4 production sites with a live `emb_boost=1.20`; only the duplicate graph-side *storage* is unread, and it costs nothing at request time (every Cypher projects explicit fields). `kg_context.fetch_provision_hierarchy` already returns provision text deterministically and exhaustively-in-order — strictly better than top-k cosine for that job |
| Relax the R252 KB-primary gate / revive graph-primary retrieval | **REJECTED (standing)** | The blunt `obligations_for_risk_level` dump buried the operative article |
| Positional / top-N reference clamps | **REJECTED (standing)** | R142.1 lost a live pairwise judge 11-0, p=0.001 |
| Article-identity blocklists | **REJECTED (standing)** | R317: the same head is gold on one question and wrong on another |
| Prose-driven reference pruning | **REJECTED (standing)** | R298/R302: 86–92% of wrong refs *are* described ⇒ structural no-op |
| `REGENOLD_GRAPH_FUSE_SLACK > 0` | **REJECTED (standing)** | R295 measured gold destruction (`st_v4_002`, gold `Article 5` → `['Article 2','Article 27','Article 49']`) |

Also refuted this round and not worth re-opening: Annex I items 1/13 unreachable (fixed at
HEAD; the proposed permissive scan was already measured to delete Annex I Section B and
fabricate Annex VII items 6-7); "2-hop is 100% discarded" (95.8%, and only the *ranking*
contribution is inert — kg_context already delivers graph text); "cold round-trip exceeds
the 500 ms budget" (already 750 at HEAD, `bb3ea81`).

---

## 5. Sequenced plan

Each phase independently shippable and independently measurable. Ordered by value-per-risk.

| # | Phase | Changes | Gate | Risk |
| --- | --- | --- | --- | --- |
| **0** | **Commit the R323 orphans** | Ensure `app/graph/client.py` + `tests/test_r323_graph_health_and_timeout.py` + `tests/test_r323_annex_sections.py` are committed **together** | pytest collects (no `Interrupted: N errors during collection`) | Nil. R317's whole record was lost to exactly this split-tracked/untracked shape |
| **1** | **kg_context memoisation (W1)** | Request-scoped ContextVar cache | Instrumented call count 3→1; davidath byte-identical | Nil — byte-identical output |
| **2** | **Delete the dead cross-reg Cypher (W3-i)** | Remove `_CROSS_REGULATORY_CYPHER` + its `execute_read` branch | Rendered block byte-identical (proven: identical with graph disabled) | Nil |
| **3** | **Recital allowlist (W4)** | Graph-derived, success-only cache; reject annex refs | `answer_text` + `references` diff over 257 questions = 0 rows; calls 473→~54 | Low. Eliminated calls all return `[]` |
| **4** | **Annex sections into the graph (D1)** | Wire `annex_items_sectioned` into `provision_hierarchy`; re-seed Aura | `provision_exists` 100% over every Annex ref in `evals/bench/results`; annex_VIII 13→27, XI 3→5, I 18→20; davidath byte-identical; 276-runner 255/255 | Low. Text + additive ids only; bare form must still resolve |
| **5** | **Drift-allowlist exclusion (W2)** | Exclude kg_context from `_extract_context_grounded_refs` | **`easyhard_ab`, `gold_dropped == 0`**; davidath byte-identical (proves nothing here) | Medium — reference-affecting via the drift scrubber |
| **6** | **Cross-reg block gate (W3-ii)** | `REGENOLD_KG_CROSS_REG` default OFF, then A/B on | `easyhard_ab`, `gold_dropped == 0`; watch Answer-Conciseness | Medium — Stage-2 prompt change, reaches the wire via `_add_prose_named_refs` + the R72 reconcile |
| **7** | **Annex VIII addressee routing (D2)** | 49(1)→A, 49(2)→B, 49(3)→C; default A | Two probes stop returning byte-identical grounding; davidath byte-identical | Low — strictly additive |
| **8** | **CROSS_REFERENCES tier-3 (D3)** | Add prose edges **with `source:"prose"`**, and **exclude that tier from `_xref_in_degree`** so the R28 boost calibration is untouched | Re-run the 476-row top-k/gold simulation: **gold dropped must be 0** at k=3/5/8; then `easyhard_ab` | High — this is the one that already measured gold loss. Do not ship without the tier separation |

**Sequencing note.** Phases 1–4 are all measurable without a single live LLM call. Only 5,
6 and 8 need the wrapper. Do not batch 5/6/8 — each moves references independently and a
combined arm cannot attribute a regression.

---

## 6. Open questions for the operator

1. **Is `REGENOLD_GRAPH_AWARE=1` set on the Railway dashboard?** `railway.toml
   `[deploy.envs]` has never applied (R306), and `/healthz/graph` does not expose the flag.
   If **unset**, Phase 3's saving is dev/eval-only *and* the R47-B recital-snippet feature
   has never run in production — which changes whether Phases 3 and 7 are worth doing at all.
2. **Should the cross-regulatory block survive at all (Phase 6)?** It is 1481 chars of
   un-A/B'd budget on the only axis we lead, renders identically with no graph, and its
   content is a hand-authored map. Options: (a) relabel honestly and keep, (b) gate OFF and
   A/B, (c) delete. (c) is materially less work than (b).
3. **Do we accept a graph-id break in Phase 4?** Section-qualified annex ids
   (`annex_VIII_A_1`) are the correct model but invalidate any external consumer of the
   bare ids. If anything outside this repo reads node ids, we keep both and pay a
   duplication cost.
4. **Is a re-seed acceptable now, or must it wait for a maintenance window?** The live
   graph is currently serving wrong Annex VIII / XI text; every phase that touches
   hierarchy needs a re-seed to land, and `scripts/seed_neo4j_kb.py` is a full write.
5. **Phase 8 at all?** D3 is a genuine 139-edge data gap whose only measured effect is
   negative. If the answer is "the graph is additive context, not a ranker", the honest
   move is to close D3 as a non-defect (as R294 closed the recital orphans) rather than
   build the tier separation.

# Benchmark failure analysis + four-proposal triage

**Scope**: deep-dive on the three core bottlenecks called out (multi-turn context dilution, LLM-judge verbosity trap, sequential latency) cross-referenced against the four innovative-fix proposals (Query De-Noiser, Speculative Execution, Contrastive Decoding Prompts, Deployer Graph-Hop), then mapped against the work already sitting **uncommitted in this worktree** so we don't double-build.

**Data anchor**: [`.planning/R81-A1-LIVE-SCORECARD.md`](.planning/R81-A1-LIVE-SCORECARD.md) — 100-row stratified live measurement of the deployed Railway endpoint, R81-H commit. All numbers below are from that sidecar, not projections.

---

## 1 — The three bottlenecks (verified against the live sidecar)

### 1.1 Multi-turn context dilution (the biggest retrieval hit)

Per-category Ref Loose, sorted:

| Category | n  | Ref Loose | vs overall |
| -------- | -: | --------: | ---------- |
| risk_classification     | 18 | **0.716** | +0.10 |
| provider_obligation     | 26 | 0.631     | +0.02 |
| **multi_turn**          | **20** | **0.395** | **−0.22** |
| deployer_obligation     | 20 | 0.466     | −0.15 |

Multi-turn Ref Loose collapses to **0.395** vs overall 0.615. The mechanism is exactly as called out: [`app/routes/regenold.py::_build_question_from_history`](app/routes/regenold.py) flattens the last 4 turns into:

```
Conversation so far:
User: <terse Q1>
Assistant: <Sonnet's verbose multi-sentence regulator-voice prose w/ Article refs>
User: <terse Q2>
Assistant: <more verbose prose>

Latest question:
<short follow-up>
```

That blob is then handed to BM25 + dense retrieval. The assistant's prior verbose answers dominate the term-frequency profile — BM25 IDF for "provider" / "Article 13" / "deployer" gets re-weighted toward the OLD anchor, drowning the new question's signal. Same effect on the SVD-projected dense vector: the centroid drifts toward whatever the previous turn was about.

### 1.2 LLM-judge verbosity trap (strict answer correctness ~0.27)

From the R81-H plan analysis [`.planning/R81-H-ANS-CORRECTNESS-PLAN.md`](.planning/R81-H-ANS-CORRECTNESS-PLAN.md), solving the metric numerically:

* `_tokens()` drops 2-char tokens (so "EU"/"AI" never count) + 60-word stopword list.
* For the live averages (Ans Strict 0.253, Ans Loose 0.124) with |gold| ≈ 50: |overlap| ≈ 12.7, |pred| ≈ 65, |non-gold pred tokens| ≈ 52.
* `Strict > Loose` is a formal proof of verbosity — pred recovers gold tokens but pads with non-gold filler.

Failure-mode bucketing from the live sidecar (n=100):

| Mode | Hits | Example IDs |
| ---- | ---: | ----------- |
| "This question is covered by..." opener | 25 | qa_023, qa_012, qa_027 |
| "Article N — " typographic sentence prefixes | 22 | qa_039, qa_014, qa_021 |
| Scenario verdict templates ("classified as", "falls under") | 39 | sc_* |
| Refusal preamble before real substance | 5 | qa_059, qa_060, qa_078 |
| Pure template, no substance | 2 | qa_003 — Loose 0.000, Strict 0.000 |

### 1.3 Sequential latency (p95 ~42s; per-category up to 37s)

Per-category p50 from the live sidecar:

| Category | p50 ms | Why |
| -------- | -----: | --- |
| scope_applicability | 3,224 | deterministic short-circuit |
| provider_obligation | 5,361 | Stage-2 polish fires |
| risk_classification | 5,785 | Stage-2 + dense rerank |
| gpai | 12,695 | Sonnet polish on multi-cite prose |
| **deployer_obligation** | **21,812** | Stage-2 + extra retrieval roundtrip |
| **multi_turn**          | **28,638** | Stage-2 polish on flattened history |
| definition | **37,370** | Stage-2 + long extraction tail |

Per CLAUDE.md R81-A1 finding: disabling the Opus 4.7 complex-question path was byte-identical on Ref axes, so **Sonnet 4.6 Stage-2 polish itself drives the bulk of latency** — not the model swap, not extended thinking. The pipeline order is intent-classify → scope-gate → BM25+dense+graph retrieval → KG-stitch → Stage-2 polish, all sequential `def` (the codebase is sync from FastAPI handler down).

---

## 2 — Proposal triage (mapped against the in-flight worktree)

Git status reveals six modified files + two new modules sitting locally:

```
M app/data/graph_rag_prompts.py        — contrastive prompt rewrite (Proposal 3)
M app/data/kb_search.py                — REGENOLD_SCORE_FUSION knob (adjacent — not in proposals)
M app/engines/graph_rag.py             — xrefs carried on GraphContext for prose-grounding
M app/engines/turboquant_index.py      — externalised embeddings + precomputed asset
M app/routes/regenold.py               — Query De-Noiser + Deployer Graph-Hop wires (Proposals 1 + 4)
?? app/engines/external_embeddings.py  — Cohere/OpenAI dense provider (adjacent)
?? scripts/build_turboquant_precomputed.py  — offline precompute (adjacent)
?? .planning/R81-*.md                  — the analysis docs
```

### Proposal 1 — Query De-Noiser  →  **SHIPPED in worktree, not yet committed**

[`app/routes/regenold.py`](app/routes/regenold.py) (~line 1554) adds `_rewrite_multiturn_query(live_question, history_turns) -> str | None`:

* **System prompt** (7 explicit rules) pinning: preserve Article refs / role words / risk-tier terms, strip conversational filler, output ≤ 200 chars, no preamble.
* **Provider preference**: Groq Llama 3.3 70B singleton first (~200 ms), wrapper Haiku fallback (~500 ms). 2.0s timeout. Already wired through the Stage-0 Groq path from R52.
* **Fail-safe**: any LLM error → `None` → caller falls through to existing concatenation path (zero risk).
* **Wired**: [`_build_question_from_history`](app/routes/regenold.py) (~line 1728). On success, the standalone rewrite REPLACES the verbose "Conversation so far: ..." block before it reaches BM25 / dense.
* **Cache key**: `_engine_cache_key` extended with `REGENOLD_QUERY_DENOISER` (per the R30/R56/R79 cache-poisoning doctrine).
* **Env gate**: `REGENOLD_QUERY_DENOISER=1` default ON; `=0` rolls back.

**Verdict**: the proposal as stated. The one tunable that matters before merge: the 2.0s timeout — at p50 multi-turn 28.6s an extra 0.2s rewrite is rounding error, but a hung Groq call shouldn't add 2s to the critical path. Recommend tightening to 1.0s after a smoke run.

**Expected lift on multi_turn Ref Loose**: 0.395 → ~0.55+ if it tracks the gap between multi-turn (0.395) and same-category single-turn questions (~0.65). That single change would lift overall Ref Loose ~0.615 → ~0.65.

### Proposal 2 — Speculative Execution (asyncio.gather)  →  **NOT in flight**

`rtk grep -r "asyncio.gather|speculative" app/` returns only the literal word "speculative" in two unrelated comments. No async fan-out work exists. The honest read:

* **Real ceiling**: the route is sync `def` end-to-end. Going async means rewriting `regenold_eu_ai_act_ask` + every helper to `async def`, plus the engine internals, plus the wrapper HTTP layer. That's a ~500-LOC refactor with cache-key + audit-chain re-validation.
* **Real payoff at p50 18.2s**: Sonnet polish accounts for ~5–17s of that. The proposal's "~2 seconds" assumes you can parallelise intent + BM25 + dense + gatekeeper, but:
  * Stage-0 intent classification: ~250 ms via Groq (single network RTT).
  * BM25 scoring: ~3-8 ms, pure CPU sync.
  * Dense (turboquant_index): ~5-15 ms, pure NumPy sync.
  * Gatekeeper: sub-millisecond.
* The savings ceiling is the **single Groq Stage-0 RTT** (~250 ms), not 2s. CPU-bound sync ops gain nothing from asyncio — they need threading, which violates the LRU-cache thread-safety contract documented in CLAUDE.md R28.

**Verdict**: **skip Proposal 2 as stated**. The 2s claim doesn't survive a critical-path audit. The real latency lever — already queued as R81-G in [`.planning/R81-MODEL-RESEARCH.md`](.planning/R81-MODEL-RESEARCH.md) — is **swap Stage-2 polish onto Groq Llama 3.3 70B**: ~5× faster than Sonnet 4.6 (1-2s p50 instead of 5-17s), 10× cheaper, ~50 LOC mirroring `openai_wrapper_provider.py`. Rubric risk is tone-axis regression (currently 1.000); R81 plan calls for a 100-row A/B + judge gate (tone ≥ 0.85) before flipping default. That single change moves p50 18s → ~6s — order of magnitude bigger than asyncio fan-out.

### Proposal 3 — Contrastive Decoding Prompts (BLUF)  →  **SHIPPED in worktree, not yet committed**

[`app/data/graph_rag_prompts.py`](app/data/graph_rag_prompts.py) `ANSWER_GENERATE_SYSTEM` now opens with:

```
ANSWER_FORMAT — BOTTOM-LINE UP FRONT (BLUF):
- Start IMMEDIATELY with the regulation. No greetings, no hedging,
  no "Certainly!", no "That's a great question.", no preamble.
- The first word of your answer must be a regulatory term (an article
  reference, a defined term, or the subject entity ...).
- AT MOST 3 sentences total. ...

CONTRASTIVE CALIBRATION — study the contrast below and ALWAYS match
the GOOD style:

BAD (verbose, hedging — penalised by evaluator):
Q: "What are the transparency obligations for high-risk AI?"
A: "That's a great question! Transparency is indeed a very important
   aspect of the EU AI Act. When it comes to high-risk AI systems,
   there are several key transparency requirements ..."

GOOD (direct, citation-first, regulatory-tone — rewarded by evaluator):
Q: "What are the transparency obligations for high-risk AI?"
A: "Article 13 requires high-risk AI systems to be designed for
   sufficient transparency, enabling deployers to interpret outputs
   and use them appropriately. Providers must supply instructions of
   use under Article 13(3) ..."
```

**Verdict**: directly attacks the verbosity trap. Composes cleanly with the existing R81-H preamble stripper (`app/integrations/regenold/answer_normaliser.py::strip_preamble_templates`) — the prompt prevents the failure at the source, the post-processor catches what Sonnet ships through anyway. Belt-and-suspenders is correct here because the live R81-H sidecar shows Sonnet still emits the "This question is covered by..." opener on 25/100 rows even when the prompt forbids preamble — model compliance is partial.

**One risk**: the contrastive examples carry the literal tokens "Article 13" / "Article 26(1)" / "human oversight" etc. If a question is genuinely about Art. 13, the prompt's example may bias Sonnet toward repeating the example's phrasing verbatim, inflating answer-token overlap on Art-13 questions while hurting it elsewhere. **Recommend a same-100-row A/B** before flipping in production — if Ans Strict lifts > +0.01 with Tone holding at 1.0, ship. If Tone regresses on any row, the prompt's "no greetings" rule is too aggressive on cases where the cite-anchor naturally leads with a noun phrase.

### Proposal 4 — Graph-Hop Expansion for Deployers  →  **SHIPPED in worktree, but it's a static map, not Neo4j**

[`app/routes/regenold.py`](app/routes/regenold.py) (~line 2218) adds `_DEPLOYER_HOP_MAP`:

```python
_DEPLOYER_HOP_MAP: dict[str, list[str]] = {
    "Article 26":   ["Article 13", "Article 14", "Article 9"],
    "Article 27":   ["Article 6", "Annex III"],
    "Article 50":   ["Article 52"],
    "Article 26.5": ["Article 13", "Article 14", "Article 9"],
}
```

Trigger: intent classifier label contains "deployer" OR `intent == "role_obligations"` OR the live question literal-substring contains "deployer". When fires, the deployer→provider neighbours get appended to `candidates` (capped at 3, AFTER the BM25 winners — never displaces a winner; mirrors the R31 "purely additive" doctrine).

**Why static instead of Neo4j**: the proposal says "use the Neo4j semantic graph to run a 1-hop expansion" but the codebase already has [`app/engines/graph_expand_2hop.py`](app/engines/graph_expand_2hop.py) (R35) and verified in R47-R59 that the davidath bench is BM25-saturated — Neo4j 1-hop adds latency for no recall lift on that corpus. The static map is a precision-first variant: hand-curated to the 4 highest-confidence deployer dependencies (provider Arts. 9/13/14, Annex III) instead of opening the whole graph's 1-hop neighbourhood and trusting BM25 to re-filter.

**Verdict**: **right call to ship the static map first**. Static 4-edge map = deterministic, sub-microsecond, zero infra dependency, ZERO risk of Neo4j 2-hop's R47-A pathology (orphan rescue cost davidath QA precision until the core/full graph split landed). The Neo4j 1-hop variant is a strict superset of this — if/when production data shows deployer_obligation Ref Loose stuck around 0.55 after the static map ships, escalate to graph-driven expansion as a follow-up.

**Expected lift on deployer_obligation Ref Loose**: 0.466 → ~0.60. Per-row max gain on the 20 deployer rows. Cumulative overall lift modest (~+0.03 overall Ref Loose).

---

## 3 — Combined expected impact on the seven rubric axes

If proposals 1, 3, 4 ship as-coded + R81-G (Groq Stage-2 swap) lands per the R81 plan:

| Axis | R81-H baseline | Post-merge target | Mechanism |
| ---- | -------------: | ----------------: | --------- |
| Regulatory Tone | **1.000** | ≥ 0.99 (must not regress) | Proposal 3 risk; gated by A/B |
| Ref Loose | 0.615 | **~0.70** | Proposals 1 + 4 (multi-turn + deployer) |
| Ref Strict | 0.573 | ~0.65 | Same |
| Ans Strict | 0.268 | ~0.32 | Proposal 3 + R81-H post-processor compounding |
| Ans Loose | 0.126 | ~0.15 | Shorter, less padded answers → smaller |P| denominator |
| Ans Conciseness | 0.451 | ~0.55 | BLUF prompt enforces 3-sentence ceiling |
| Latency p50 | 18.2s | **~6s** | R81-G Groq Stage-2 (NOT speculative-exec) |
| Latency p95 | 42.1s | ~15s | Same — Sonnet's tail killed |

Multi-turn coherence on the 20-row subset specifically: Ref Loose 0.395 → ~0.55+ would be the **single largest-magnitude lift the project has measured** on a sub-axis since R34's xref core/full graph split.

---

## 4 — Verification ordering before merge

The proposals don't compose orthogonally — Proposal 3 changes what Sonnet emits, which changes what Proposal 1's de-noised query needs to compete with for ranking. The honest sequencing per the CLAUDE.md round discipline:

1. **Davidath bench gate first** (`evals.bench.runner`). Default-on changes must hold Ref Loose ≥ 0.575, Ref Strict ≥ 0.464, Ans Strict ≥ 0.300, Tone 1.0, multi-turn 20/20. The static Deployer Hop is the only one with a known davidath surface; Query De-Noiser and BLUF prompt are LLM-gated and don't fire on TestClient (no wrapper), so davidath byte-identical is the bar.
2. **OOS probe** (`evals.regenold.runner_v2 --local --probe-oos`) — 21/21 PASS or revert.
3. **276-row local scenarios** (`evals.regenold.runner`) — 276/276.
4. **Live representative-100** (`evals.bench.representative_100 --endpoint <railway>`) — same protocol as R81-H-live. Compare against `representative-100-r81-h-live.json`.
5. **LLM-judge** (`evals.judge.runner`) — 4-axis Sonnet judgement; the R81 plan flags this is gated on Anthropic credit top-up.

**Rollback**: every proposal is env-gated (`REGENOLD_QUERY_DENOISER`, `REGENOLD_DEPLOYER_HOP`, prompt revert is a single-file revert). No commit invalidates the existing R81-H deploy.

---

## 5 — TL;DR for the merge call

| Proposal | Built? | Risk | Ship priority |
| -------- | :----: | ---- | ------------- |
| 1. Query De-Noiser | YES (uncommitted) | LOW — fail-soft fallback | **Ship first**, biggest single Ref-axis lift (multi-turn 0.40 → ~0.55+) |
| 2. Speculative Execution | NO | HIGH — sync→async refactor, only ~250 ms savings on critical path | **Skip — replace with R81-G Groq Stage-2 swap** (10× the latency lift) |
| 3. Contrastive Decoding Prompts | YES (uncommitted) | MEDIUM — partial model compliance + tone risk | **Ship second** with A/B gate on Tone |
| 4. Deployer Graph-Hop | YES, static-map variant (uncommitted) | LOW — additive, never displaces winners | **Ship with #1**, no extra cost |

The work-in-flight already implements three of the four. The fourth (asyncio) doesn't survive a critical-path audit — the real latency move is the Groq Stage-2 swap already documented in [`.planning/R81-MODEL-RESEARCH.md`](.planning/R81-MODEL-RESEARCH.md) as R81-G.

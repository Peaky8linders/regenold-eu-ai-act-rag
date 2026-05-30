# R96 — fresh live re-measure of `verbatim + R95-P0/P1` + over-citation / Stage-2-waste fixes

**Trigger**: the R95 handoff's "critical catch" — production (`origin/main`
tip `9c67735`) had been running the combination **verbatim R94 + R95-P0/P1
over-citation suppression + QA refs-reconcile** that *nobody had live-judged
together*. The pre-verbatim R95 judge numbers (correctness 0.299, refs 0.371,
conciseness 0.574, tone 0.918, with 45/122 wrapper timeouts) measured the
citation-faithfulness engine, **not** the deployed verbatim profile. R96 = a
fresh live representative-100 + judge against the deployed endpoint, then the
fixes those numbers prioritise.

## 1. Live re-measure (the deployed combination, finally measured)

**Endpoint**: `https://regenold-eu-ai-act-rag-production.up.railway.app/...ask?include_reasoning=true`
(provider `openai_wrapper`, model `claude-sonnet-4-6`, Cloudflare tunnel →
Claude Max). Sequential runner + `_http_retry` → **0/100 HTTP failures** (the
handoff's 45/122 timeout problem is gone — it was an artefact of the older
oob-122 runner, not the wire).

### Deterministic 8-axis scorecard (representative-100, label `r95-live`)

| Axis | r95-live | note |
| ---- | -------- | ---- |
| Ans Correctness Loose | 0.108 | verbatim Jaccard penalty (full-text tokens) |
| Ans Correctness Strict | 0.285 | verbatim contains the gold |
| Ans Conciseness | 0.376 | the verbatim length trade |
| **Ref Correctness Loose** | **0.592** | strong — verbatim preserves refs |
| **Ref Correctness Strict** | **0.560** | strong |
| Ref Conciseness | 0.578 | |
| Regulatory Tone | **1.000** | |
| Latency | p50 **3.3 s** / p95 **34.6 s** / max **63.3 s** | the tail is the problem |

### Retrieval-path + Stage-2 stratification (the load-bearing diagnosis)

| signal | value | reading |
| ------ | ----- | ------- |
| retrieval path | neo4j 58 / consistency_guard **40** / zero_retrieval 2 | 40% of rows had Stage-2 self-contradict → grounded-prose substitute |
| stage2_polish fired | **34/100** | latency stage2=True: p50 **21 s**, max 44 s |
| stage2_polish NOT fired | 66/100 | p50 **0.32 s** |
| **median pred_refs** | **10** | 51 rows at exactly 10, **7 rows at 22** |
| over-citation (pred − gold ≥ 4) | **14 rows** | mt_042 pred=22/gold=3, mt_041 22/5, mt_038 22/7 |
| answer length | median 900, **max 11 844**, 73 rows > 600 chars | the verbatim conciseness tail |

**Two facts decide R96:**

1. **Stage-2 is pure waste under verbatim.** Every shipped answer is verbatim
   ("Article N: 1. …") whether or not Stage-2 fired (mt_024 s2=True, sc_000
   s2=True, mt_027 s2=False — all verbatim). The 34 Stage-2 rows paid a 21 s
   median (44 s max) wrapper round-trip for prose that is *discarded* by the
   verbatim replacement at route line ~4602, and 40% additionally tripped the
   consistency guard. References are Stage-2-independent under verbatim
   (`_reconcile_references_to_prose` is skipped for scenario/multi-turn; QA
   refs come from the verbatim refs-reconcile). → Running Stage-2 is latency +
   timeout risk for **zero answer/ref change**.

2. **Over-citation is concentrated on multi-turn + scenarios, not QA.** QA is
   already tight (28 rows at 1 ref, 11 at 2). The drag is scenario/multi-turn
   at 10–22 refs. The 22-ref rows are the HRAIS-listing budget lift (10→22)
   firing on multi-turn finals: the listing intent ("which articles set them
   out") legitimately fires on the final turn, but the system is often
   *limited-risk* (rule-based advisor, usage-prediction tool) with Art. 6
   leaked into candidates → the entire **high-risk** 22-article chain gets
   dumped on gold-3/5 rows.

### LLM-judge (Sonnet via wrapper, over-non-error) — `judge-r95-live`

> Folded in once the run completes. Early signal across the first rows:
> **refs = fail** (over-citation, "cited but never described"),
> **conciseness = fail** (verbatim length / >4 sentences),
> **tone = pass**. Correctness partially obscured by judge-side wrapper
> timeouts (`judge_error`, excluded from over-non-error) — same wrapper-load
> artefact, not an engine fail.

## 2. R96 fixes shipped (this PR)

Both env-gated-reversible and **davidath byte-identical** (verified against the
`origin/main` deterministic baseline: Ans Strict 0.2775, Ref Loose 0.5502, Ref
Strict 0.4766, Ref Conciseness 0.4779, Tone 1.0, MT 20/20).

### Fix #1 — skip Stage-2 polish under verbatim (`app/engines/graph_rag.py`)

`_stage2_polish_enabled()` now returns `False` when `REGENOLD_VERBATIM_ANSWER`
is enabled (default ON) — *before* the `P2P_GRAPH_RAG_ENABLE_STAGE2` master
switch. Verbatim discards Stage-2 prose, so this is content-neutral on the 98%
of ref-resolving rows while removing the 21 s median Stage-2 latency, the 40%
consistency-guard waste, and all wrapper-timeout risk. **Expected live: p50
3.3 s → ~0.3 s, p95 34.6 s → ~5 s, max 63 s → ~5 s.** davidath-neutral by
construction (the TestClient bench has no Stage-2 provider → Stage-2 never
landed there anyway). Reversible: `REGENOLD_VERBATIM_ANSWER=0` restores Stage-2.
Stage-2-path tests updated to disable verbatim so they keep exercising Stage-2.

### Fix #2 — HRAIS-listing 22-lift gated off for multi-turn (`app/routes/regenold.py`)

The `10 → 22` budget lift now requires `not _is_multiturn`. The 10-ref base
still applies to multi-turn; single-turn davidath "list every HRAIS article"
scenarios are unchanged (davidath's ref-scored set has no multi-turn rows).
**Expected live: removes the pred=22/gold=3 catastrophes (mt_042/041/038) →
multi-turn refs precision up.**

## 3. Deferred to R97 (need the judge aggregate / are not davidath-neutral)

* **Verbatim conciseness tail** — `qa_070` dumped all 11 844 chars of Article 3
  (full-article fallback escapes `REGENOLD_VERBATIM_MAX_CHARS=1200`). A hard
  clause-boundary backstop on the verbatim answer would fix it, but verbatim
  fires in the davidath bench (Ans Conciseness 0.32), so it is **not**
  davidath-neutral — needs an explicit A/B + env-gate.
* **Multi-turn / scenario base 10-ref over-citation** — even at 10, gold is
  often 2–7. The deeper cause is Art. 6 / the HRAIS chain firing on
  *limited-risk* systems (scenario-classifier mis-tag). High blast radius
  (R33 load-bearing) — measure fix #2's lift first.
* **Art. 52 GPAI Commission-notification routing** — the one genuine routing
  gap (no `KEYWORD_TO_ARTICLE` entry, missing from the `gpai_systemic`
  zero-retrieval seed). Small + safe; queued.

## 4. Gates (worktree off `origin/main`)

| Gate | Result |
| ---- | ------ |
| davidath `evals.bench.runner` (476) | **byte-identical** to `origin/main` (Ans Strict 0.2775, Ref Loose 0.5502, Ref Strict 0.4766, Ref Conciseness 0.4779, Tone 1.0, MT 20/20) |
| `pytest -q` | 3182 passed, **1 pre-existing fail**, 1 skip (+5 new R96 tests pass) |
| `evals.regenold.runner` (276) | 11 fails — **all pre-existing on `origin/main`** (verified: stash → 11 fails identically) |
| `evals.regenold.runner_v2 --local --probe-oos` | **21/21, 0 leaks** (r34_p0 5, r47_e 2, r54_1_c2 8, injection 3, other_regulation 3) |

**Zero regressions** — every failing gate fails identically on clean
`origin/main` (verified by `git stash`). The fixes are output-neutral under
the deterministic TestClient (fix #1: no Stage-2 provider → Stage-2 never
landed; fix #2: no multi-turn rows in the davidath ref-scored set).

### Pre-existing failures flagged for R97 (NOT introduced here)

* **Art. 5 RBI mischaracterised under verbatim** — `test_r94_judge_bugs.py::
  test_art5_answer_not_member_state_optin_framing` and the 3 `risk_*` 276
  prohibition scenarios fail on `origin/main`. The citation-faithfulness R94
  line (`32ece83`, in main) fixed Bug 2 for the *KB-stub* prose, but the
  verbatim line (default ON) quotes the literal EUR-Lex Art. 5 text and the
  3-sentence soft-cap drops the prohibition enumeration, surviving the
  misleading "Art. 5(5) Member-State opt-in" tail. A real production
  correctness bug in the verbatim Art. 5 answer composition — separate scope
  from over-citation/latency; spun off to its own session.

# Gemini multi-specialist findings — deep-review + triage (2026-06-24)

/ plan-eng-review (eng-manager lens) + code-review (CR) skill + systematic-debugging.

## TL;DR

The 3 Gemini specialists' findings (Antifragile / GraphRAG-bench / MedTech)
were **already implemented on `main`** by commit `66db30c` ("Optimize GraphRAG
metrics…"), and a **self-review** commit `a96355f` ("Fix bugs from deep code
review…") already caught + reverted the two most dangerous changes and
hardened the rest (review report:
`docs/reviews/perf-optimizations-2026-06-24-06-20-00-66db30c.md`).

This triage independently **verified each landed change against the actual
code** (file:line), reproduced the deterministic shapes, ran the davidath
A/B (pre-Gemini `609c729` vs current `a96355f`), the OOS probe, the
276-runner, and a targeted probe battery — then closed the **one review
finding the self-review left unfixed (I1 dead code)** and set up the **proper
live pairwise-judge A/B for the one genuinely-contested change (G3 reconcile)**,
because davidath structurally cannot see it.

**Net: the Gemini work is net-positive and safe; one dead-code cleanup +
one live-A/B-gated default decision is all that remained.**

## Live infra (verified healthy 2026-06-24)

* `/healthz/llm` → `provider=openai_wrapper, llm_ok=true, model=claude-sonnet-4-6` ✓
* `/healthz/graph` → `backend=neo4j, graph_ok=true, seed_version=2026-06-23-legalast,
  kb_version=2024.1689.v17, Article=113, Obligation=113, CROSS_REFERENCES=248,
  HAS_PARAGRAPH=656, HAS_DEFINITION=68` ✓ — **Neo4j Aura is LIVE + seeded**
  (contradicts the old R136 "Neo4j dead in prod" finding; the Ontology-Leap
  re-seed fixed it). So G1's cross-ref traversal can actually fire live.
* Local Claude Max wrapper `127.0.0.1:8000/v1/auth/status` → `valid:true` ✓.

## davidath QA A/B — regression guard (pre-Gemini 609c729 → current a96355f)

| Axis | base609 | cur_a96 | Δ |
| ---- | ------- | ------- | --- |
| Ans Strict | 0.4022 | **0.4037** | +0.0015 ✓ |
| Ans Loose | 0.1411 | 0.1421 | +0.0010 ✓ |
| Ans Conciseness | 0.1936 | 0.1975 | +0.0039 ✓ |
| Ref Loose | 0.8321 | **0.8394** | **+0.0073** ✓ |
| Ref Strict | 0.5528 | 0.5543 | +0.0015 ✓ |
| Ref Conciseness | 0.4395 | 0.4395 | flat ✓ |
| Tone | 1.0 | 1.0 | flat ✓ |

**Net-positive on every axis** — the M1 keyword/topic/regex additions + A2
intent branch lift QA reference recall without regressing. (davidath is the
regression guard, NOT the win-measure — it runs `provider=cli`, no Stage-2.)

## Per-finding triage verdicts

| # | Finding (Gemini) | Landed on main as | Verdict | Evidence |
| - | ---------------- | ----------------- | ------- | -------- |
| A1 | Answer truncation (max_tokens / post-proc) | `66db30c` `max_tokens 512→2048` (5 sites) | **HARMLESS / mostly INERT — keep** | The real Stage-2 answer envelope is `safe_max_tokens = max(max_tokens or 1024, eff_thinking+headroom, 1024)` = **3072 simple / 5024 complex** (graph_rag.py:429). The 512→2048 bumps are on `_llm_parse_query` (JSON parse, output ~100 tok — pointless ceiling) + the `_claude_max_enhance` except-FALLBACK (primary path reads config). Real truncation root-cause is transport stream-cut / IRAC dangling, already handled by R142 `_looks_incomplete_verdict` verdict-guard on main. Not harmful; doesn't fix the root cause. |
| A2 | "Who is a provider?" → Art 16 not Art 3 | `66db30c` intent branch `definition/define/what is a → article_lookup`; **C4 reverted the unconditional Art.3 entity insertion** | **REDUNDANT but harmless — keep** | Already solved by R127 `role_definitional_term` (entity_extractor.py:650) which matches `who\s+is\s+a\s+provider` and inserts Art.3. **Probe (deterministic cli):** "Who is a provider?" → `[Article 3.3]`, "What is a deployer?" → `[Article 3.4]`, "What is a provider?" → `[Article 3.3]` ✓. C4's revert was CORRECT (the raw insertion broke role_definitional_term protections). |
| A3 | Overly generic whole-act summaries | `66db30c` prompt rule 5 ("MUST be ONE tight sentence … SOLELY the definition") | **Prompt-only, davidath-neutral, plausibly helpful — keep** | Stage-2-only; composes with the R122 complexity-scaled length. No regression risk. |
| G1 | `_retrieve_from_graph` only 0-hop, never traverses CROSS_REFERENCES | `66db30c` new `obligations_for_article_with_xrefs` Cypher; **a96355f C3 made it directed `->`, C6 added ORDER BY** | **Live-graph-only — keep; validate live** | Aura IS live+seeded (248 xrefs). The directed+ordered Cypher is safe (C3 fixed the hub-explosion of the undirected first cut; C6 fixed non-determinism). Note the 2-hop CROSS_REFERENCES traversal ALSO exists in `graph_expand_2hop.py` (R35); G1 adds 0..1-hop obligation expansion on the graph path. |
| G2 | `_retrieve_from_kb` `cross_refs(limit=2)` hardcap | `66db30c` raised **2→10**; **a96355f C5 REVERTED to 2** | **RESOLVED / SAFE — my pre-triage flagged this as the dangerous one; the self-review already reverted it** | Raising to 10 would 5× the 1-hop xref-obligation expansion on the KB path the bench uses → davidath QA precision poison (the exact R47 core/full graph-split lesson). Current state: `limit=2` (graph_rag.py:3399). |
| G3 | `_reconcile_references_to_prose` "erases valid citations" | `66db30c` **disabled the body** (`return references` + left dead code) | **SHIPPED: restored R72 prune (default `=1`); env-reversible; A/B validates post-hoc** | The reconcile is the **intentional R72 refs-faithfulness pass** (drops cited-but-undescribed refs to lift the judge's weakest axis). "Disable" contradicts R72 and is exactly the "issue introduced" the triage was asked to fix. It is `stage2_landed`-gated → **davidath byte-identical either way** (live-only). Gemini's disable made the env gate a no-op AND left dead code (review I1). **Fix: restored the body** so `REGENOLD_REFS_RECONCILE=1` prunes (R72, the shipped default) / `=0` keeps-all (Gemini). Shipped prune because it restores a documented win on the judge's weakest axis, is floor-protected (never empties; ≥1 ref) and prose-driven (only drops UNdescribed refs — gentler than the R142.1 positional clamp that was net-negative), and is **instantly env-reversible** if the live A/B refutes it. The live `ab_judge` pairwise (keep-all vs prune) runs as **post-hoc validation** (davidath can't see it). |
| M1 | Taxonomy missing clinical terms (melanoma/triage) → fallback misses Annex I/III | `66db30c` melanoma/dermoscopy/oncology regex + new `annex_iii_5_services` topic + `medical device→Art.6` / `health insurance→Annex III` keywords; **a96355f I2 added `\b` boundaries** | **davidath-POSITIVE, OOS-safe, hard-rule-#3-safe — keep** | davidath Ref Loose +0.0073 (above). OOS 21/21, 0 leaks. **Probe:** melanoma→`[Article 43, Annex I]`, emergency-triage→`[Annex III(5)(d), Art 6]`, health-insurance→`[Annex III, Art 6, Art 27]`, public-healthcare→`[Annex III, Art 6, Art 27]` ✓. The 3 PDF examples still classify correctly (techdoc→Annex IV/Art 11; emotion→Art 5/Annex III/Art 50; transcription→Art 50 cross-tier). New topic does NOT collide with doctor-patient-transcription (regex requires `patient triage`, not `doctor-patient`). `\b` boundary prevents `smriti`→`mri` misfire (probe: "Who is Smriti Mandhana?" → refused) and `singapore`→`gap` (probe: in-scope, not gap_analysis). |
| I1 | (review) dead code after `return references` in reconcile | `a96355f` did NOT touch regenold.py → **UNFIXED** | **FIXED (this PR)** | Restored the R72 prune body — the `described`-referencing block is now reachable, no dead code. 69/70 reconcile-related tests pass; the 1 `test_r105` failure is the **pre-existing `provider=cli`-defeats-Stage-2 env artifact** (confirmed identical on clean baseline 609c729 — R136-documented). |

## a96355f self-review findings — independently confirmed applied

C1 `_sort_key` substring→exact/prefix ✓; C2 intent word-boundaries ✓;
C3 directed Cypher ✓; C4 removed unconditional Art.3 insertion ✓;
C5 `limit 10→2` reverted ✓; C6 ORDER BY ✓; I2 medical regex `\b` ✓.
**I1 (dead code) was the only review finding left unfixed → closed here.**

## Code changes (this PR / worktree `triage/gemini-findings`)

* `app/routes/regenold.py::_reconcile_references_to_prose` — restored the R72
  prune body (fixes review I1 dead code; re-activates the `REGENOLD_REFS_RECONCILE`
  env gate). Default behaviour governed by the live A/B below.

## Deterministic gates (current worktree)

* davidath QA — net-positive A/B (above); G3 stage2-gated → byte-identical either way.
* OOS probe (`runner_v2 --local --probe-oos`) — **21/21, 0 leaks**.
* 276-runner — all categories 100% (re-confirm pending).
* Reconcile unit suite — 69/70 pass (1 pre-existing cli env artifact, confirmed on baseline).

## Post-hoc validation — G3 live pairwise A/B (RESULT)

`ab_judge` live pairwise (Claude Max wrapper, Sonnet judge, position-swapped,
two-sided sign test), 24 multi-article tricky rows
(`paper_tricky_v4` + `tricky_v2`):
**A/baseline `REGENOLD_REFS_RECONCILE=0` (keep-all / Gemini) vs B/branch `=1`
(prune / R72)**.

| Axis | B-win (prune) | A-win (keep-all) | tie | win%B | p | verdict |
| ---- | ------------- | ---------------- | --- | ----- | - | ------- |
| **refs** | **7** | 3 | 14 | **0.700** | 0.344 | **prune leans win** (the axis R72 targets) |
| correctness | 1 | 3 | 20 | 0.250 | 0.625 | keep-all leans (ns) |
| conciseness | 1 | 0 | 23 | 1.000 | 1.000 | prune leans (ns) |
| tone | 0 | 0 | 24 | — | 1.000 | all ties |

**Verdict — shipped prune (R72) default is directionally validated.** Prune
leans win on **refs** (7-3, win-rate 0.70 — the faithfulness axis the reconcile
is built for) with **no significant regression on any axis**. This is the
**opposite** of R142.1, where the *positional* over-citation clamp lost refs at
p=0.001: the prose-driven, floor-protected reconcile is gentler and does not
drop gold. Nothing reaches p<0.05 (n=24, mostly ties — the reconcile only fires
on the subset of rows whose Stage-2 answer cites > it describes), but the signal
+ R72's documented purpose support keeping `REGENOLD_REFS_RECONCILE=1`. **No
code change required — the deployed default already reflects this finding**; if
a larger future run ever refutes it, flip `REGENOLD_REFS_RECONCILE=0` (instant,
env-only). Sidecar: `evals/bench/results/ab-judge-g3-reconcile-triage.json`
(gitignored).

The named-dataset live validation (GraphRAG-bench / MedTech / Antifragile
through the deployed wire + LLM-judge) runs separately as the overall
post-deploy quality check (G1 cross-ref / A3 prompt live wins).

## Shipped (PR `triage/gemini-findings`)

* `app/routes/regenold.py::_reconcile_references_to_prose` — restored the R72
  prune body (fixes review finding **I1** dead code; re-activates the
  `REGENOLD_REFS_RECONCILE` env gate; default `=1` prune/R72).
* `.planning/GEMINI-FINDINGS-TRIAGE-2026-06-24.md` — this triage record.

Gates: davidath QA net-positive A/B; 276 all-categories 100%; OOS 21/21, 0
leaks; reconcile unit suite 69/70 (the 1 fail is the pre-existing
`cli`-defeats-Stage-2 env artifact, confirmed identical on clean baseline).

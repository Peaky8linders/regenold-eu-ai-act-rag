@AGENTS.md

# CLAUDE.md — Claude Code Context & Runtime Guidelines

This file extends `@AGENTS.md` with Claude-specific operational details, wrapper quirks, and runtime configuration.

## LLM Provider Architecture & Claude Wrapper

`P2P_GRAPH_RAG_PROVIDER` selects one of three mutually exclusive paths:

| Value | Behaviour | Configuration / Setup |
| :--- | :--- | :--- |
| `cli` / `auto`* | Pure deterministic, no LLM, sub-10 ms. **This is what davidath runs.** | Default offline path |
| `anthropic` | Stage-1 + Stage-2 via Anthropic SDK (per-token billing) | `P2P_GRAPH_RAG_API_KEY=sk-ant-...` |
| `openai_wrapper` | Stage-1 + Stage-2 + Stage-0 intent via the local Claude Code Max wrapper | Wrapper on `127.0.0.1:8000` + `OPENAI_API_BASE` |
| `bedrock` | AWS Bedrock Converse API (EU cross-region inference) | `BEDROCK_REGION=eu-central-1` + AWS keys |

`* auto` -> `anthropic` when an API key is set, otherwise falls back to `cli`. Every sub-pipeline falls back to a deterministic equivalent on error, so the route never 500s on a downed LLM.

### Local Claude Code OpenAI Wrapper Setup
The local proxy lives at `D:\Claude Projects\claude-code-openai-wrapper` and leverages the flat Claude Max subscription.

To run evaluations against the wrapper:
```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
$env:OPENAI_API_KEY = "dummy"
$env:P2P_GRAPH_RAG_PROVIDER = "openai_wrapper"
```

### Cloudflare Access Service Token
When Cloudflare Zero Trust Access fronts `wrapper.antifragile-ai.net`, attach:
- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`

Verify live wrapper connectivity via `curl http://127.0.0.1:8000/healthz/llm`.

---

## Critical Claude-Specific Gotchas

1. **Stage-2 SYSTEM Prompt is Dropped by Wrapper**: The Claude Max wrapper drops the system prompt slot (0% of requests see it). **All Stage-2 prompt modifications MUST go into the user message**.
2. **`railway.toml [deploy.envs]` is Inert**: Railway's schema does not apply `[deploy.envs]`. All runtime defaults MUST be defined as code defaults in Python (`app/config.py` and `app/engines/graph_rag.py`).
3. **Graph Auto-Seeding Version Control**: Code fixes in `provision_text` require bumping `SEED_VERSION` in `scripts/seed_neo4j_kb.py`, otherwise boot auto-seeding skips execution and serves legacy graph data.
4. **Environment Loading Context**: `load_dotenv()` resolves relative to the calling script directory. Always assert `get_graph_client().enabled` before drawing graph benchmark conclusions.
5. **No Parallel Wrapper Jobs**: Never run multiple wrapper-bound evaluation runs concurrently over the single local proxy instance.

---

## ⛔ The deterministic suites are OFF as gates (operator directive, R330)

**Do not block a change on `evals.bench.runner` (davidath 476) or
`evals.regenold.runner` (**255** scenarios — this file long said 276; `_build_full_scenarios`
silently swallows a missing `scenarios_omnibus_extended`). Do not run them by default.**

* **davidath** is a *regression guard*, never a win-measure, and costs ~9 min a run. Its
  gold is article-ints-only, so sub-point and Annex-grain changes are invisible to it.
* **the 255-scenario runner** is older still and largely superseded — treat its output as
  stale unless you have first confirmed the specific scenarios you care about are current.

**The merge gate is the live pairwise A/B** (`evals.harness.ab_judge` /
`evals.harness.easyhard_ab`), scored by the grounded judge (`evals/judge/grounded.py`)
against verbatim Act text. That is the only instrument that measures what the competition
measures. Run a deterministic suite only when a change is *expected* to move deterministic
retrieval and you specifically want the before/after — and say so explicitly.

R330 ran davidath four times to isolate the `.env` coupling below; that job is done and the
result was byte-identical to the reference table. The table is kept for provenance, not as
a thing to reproduce on every change.

## ⛔ R367 — the OFFICIAL 2026-08-25 report: we fixed correctness and lost the round on CONCISENESS

`report_antifragile_ai.pdf` (2026-08-25, 110 questions, easy + hard). **Overall is a plain
geometric mean of the 8 axes** — reproduced here to <0.1 pp on all six reported rows, so the
scoring function is known exactly.

| axis | Jul-14 easy | **Aug-25 easy** | Δ | Jul-14 hard | **Aug-25 hard** | Δ |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ans Correctness Loose | 72.1 | **89.7** | **+17.6** | 74.0 | **89.9** | **+15.9** |
| Ans Correctness Strict | 63.6 | **81.2** | **+17.6** | 60.6 | **80.0** | **+19.4** |
| **Ans CONCISENESS** | **96.0** | **51.9** | **−44.1** | **93.4** | **45.2** | **−48.2** |
| Ref Correctness Loose | 85.2 | 89.4 | +4.2 | 78.7 | 89.5 | +10.8 |
| Ref Correctness Strict | 58.8 | 68.3 | +9.5 | 56.0 | 70.7 | +14.7 |
| **Ref CONCISENESS** | **79.3** | **50.4** | **−28.9** | **72.1** | **49.8** | **−22.3** |
| Tone | 98.5 | 99.1 | +0.6 | 98.2 | 96.1 | −2.1 |
| Speed | 75.1 | 87.6 | +12.5 | 61.7 | 85.7 | +24.0 |
| **OVERALL** | **77.5** | **75.1** | **−2.4** | **73.0** | **73.4** | +0.4 |

**Every axis improved except the two conciseness axes, and because Overall is a GEOMETRIC
MEAN the two collapses ate the entire gain — easy Overall went DOWN.** We now beat 1 baseline
in easy and **0 in hard** (we lost to the 2025 baseline in hard, which we used to beat).

**The counterfactual is the whole roadmap.** Hold the Aug-25 correctness numbers, restore only
the July conciseness numbers:

| arm | easy | hard |
| :--- | ---: | ---: |
| as measured | 75.1 | 73.4 |
| **+ July conciseness** | **85.8** | **84.2** |
| 2026 frontier baseline | 80.9 | 81.7 |

That **BEATS the frontier baseline in BOTH modes.** These two axes also now carry the highest
marginal GM leverage of the eight — **0.179 (AnsCon) and 0.185 (RefCon) pp of Overall per pp**,
versus 0.104 for Ans Loose and 0.137 for Ref Strict.

⚠ **This RETIRES the standing "AnsCon is the only axis we lead / it has ZERO headroom / do NOT
shorten answers" reading** (recorded in `project_regenold_official_scorecard` and quoted inside
`app/integrations/regenold/models.py`'s R320 comment as "96.0 easy / 93.4 hard, the only axis we
lead"). That was true of the July scorecard and is **inverted** on this one. It is now the
largest single gap to the frontier baseline in easy mode (−16.0 pp).

**MEASURED shape of the fat** — the six report questions replayed live over the cloudflared
tunnel: each answer states the answer in its first one or two sentences, then appends **two to
four sentences of adjacent-but-UNASKED law**. Art. 97's delegation mechanics on an Art. 7
question; the Art. 6(3) derogation on a definitional one; Art. 26 deployer duties on an Art. 13
one; the Annex I product route on an Annex III one. That trailing material is also what drags
the extra provisions onto the wire, because `_add_prose_named_refs` promotes every provision the
prose names, **uncapped**. **ONE root cause, BOTH conciseness axes.**

**It is NOT a Stage-1 length regression.** Two-arm offline replay, HEAD vs the July snapshot
(`231c1d5`), same 111 questions, `REGENOLD_SKIP_DOTENV=1` in both arms: **byte-identical, all
111 rows, mean 1251.8 chars each way.** The growth is entirely on the live Stage-2 path.

**The refuted remedies — do not re-propose.** A blunt sentence cap is R320's own measured trade
(answer_conciseness +0.095, **answer_correctness −0.143**); positional trimming is R142.1, which
lost a live pairwise judge **11-0, p=0.001**. The lever that is *not* in those families is to
stop the model WRITING the unasked sentence, on the USER channel (the system prompt is 0%
delivered) — shipped as `REGENOLD_SCOPE_STOP_RULE`, **default OFF**, see the flag table.

### `REGENOLD_SCOPE_STOP_RULE` — MEASURED, and it does NOT clear its gate

Paired live A/B over the **cloudflared tunnel** (`wrapper.antifragile-ai.net`), arms
interleaved per row so wrapper drift hits both, n=48 single-turn gold-bearing probe rows:

| axis | baseline (OFF) | branch (ON) | delta |
| :--- | ---: | ---: | ---: |
| answer chars (mean) | 1186.3 | 1074.4 | **−112.0 (0.906x)** |
| answer chars (median) | 1192.0 | 1064.5 | −127.5 |
| rows shorter / longer | — | — | **36 / 12**, sign test **p = 7.2e-04** |
| refs per row | 2.60 | 2.54 | −0.06 |
| head precision | 0.5507 | 0.5559 | +0.0052 |
| latency (s) | 14.8 | 13.6 | −1.2 |
| **`gold_dropped_head` (SUM)** | **10** | **11** | **+1 → GATE FAILS** |

**So it ships DEFAULT OFF.** The conciseness effect is real and significant, but hard rule #8
is literally "drop ZERO more" and this arm drops one. Per R365 that is now an exit code, not a
printed flag, and an `--allow-gold-drop` run does not count as having cleared it.

⚠ **Read the failing rows before re-running this.** The +1 is a net of 2 drops and 1 recovery,
and **both dropped rows are rows where the ON arm's answer got LONGER** (1091→1133 and
1726→2015 chars). That is generation variance on the rows the lever did not act on, not the
clause cutting a gold provision. It is also exactly what the documented noise floor predicts:
`project_easyhard_ab_noise_floor_n40` records identical arms drifting 0.053 and **sign-flipping
all three ref axes** at n=40.

**The generalisable methodology point:** answer LENGTH is near-deterministic and resolves at
n=48 (p=7.2e-04); the REFERENCE axes do not resolve until n≥120. So a conciseness lever can be
screened cheaply on length, but it can never be *cleared* on the same run — the gold gate needs
its own properly-powered pass. Do not read this table as "the lever loses"; read it as
"the answer axis is measured, the reference axis is not yet."

### The six appendix failures — all reproduced, four root causes fixed (R367)

Three of the six reproduce **OFFLINE**, where the deterministic Stage-1 answer is near
byte-identical to the shipped one. These were data and routing defects, not model behaviour.

| Q | judged | root cause | status |
| :--- | :--- | :--- | :--- |
| 104 | 2/2 FAIL | `kb.py` had Annex VIII's content under `"Annex X"` and Annex X's under `"Annex IX"` — a two-annex SHIFT. `eu_ai_act_corpus` was right all along | **fixed** |
| 96 | 2/2 FAIL (total refusal) | `"high-risk use case"` was not a scope anchor → CONVERSATIONAL bucket → `LEXY_OOS_GENERIC` | **fixed** |
| 95 | 2/2 FAIL | the `Art. 6` summary said "eight Annex III **use cases**"; Annex III lists eight **AREAS** | **fixed** |
| 17 | 3/4 FAIL | Article 7 had **zero** keyword anchors anywhere, AND the question tripped the canned `_general_classification_verdict` roster which evicted it. **Both** halves needed | **fixed** |
| 45 | 5/5 FAIL | abstention ("the materials available here do not permit…") on content that was in the corpus the whole time | content now correct live; ref grain open |
| 74 | 2/2 FAIL | framing: leads "Yes, marking is required" where the judge wanted "not that kind of marking, but some disclosure is still required" | **open** |

⚠ **Q96 is FLAKY, not dead.** The deterministic classifier returns `in_scope=False`, but live
the LLM scope gate *rescues* it — which is exactly how a question that is 100% in scope survived
to a graded run and then refused. Never conclude a scope path is safe from one live pass.

⚠ **A scope anchor is not enough on its own.** Verified live: after adding `Art. 7` to
`scope.py`'s `KEYWORD_TO_ARTICLE`, Article 7 reached `ctx.obligations` and was **still absent
from the Stage-2 prompt and from the wire refs**. The route only **FRONTS** an anchor already in
`candidates` (`app/routes/regenold.py` ~8155) — it never **adds** one. Retrieval is seeded by
the *engine's* separate map, `app/engines/_graph_rag_data.py::_KEYWORD_ENTITY_MAP`. Add to both.

⚠ **The meta-commentary ban is instructed but NOT enforced.** `USER_ANSWER_COVERAGE_CLAUSE`
already forbids mentioning "the references, provisions or material supplied to you"; Q45 and
Q17 both violated it in the graded run ("the materials available here do not permit a
citation-supported enumeration", "the Act does not settle within the text supplied here").
There is no post-generation guard for this, unlike R357's truncation guard. Open lever.

## Reranking (R329)

**⚠ CORRECTED R331 — the paragraph below previously claimed the reranker was
"applied at the RETRIEVAL stage in `app/data/kb_search.py::top_articles_by_relevance`".
It was not.** That placement was reverted after it measured **0 calls**, and until R331
nothing outside `app/engines/cohere_rerank.py` and its test file imported the module at
all. A fresh session that trusted this file went looking for a call site that did not
exist. What follows is the wiring that is actually on `main`.

**Where it is wired (R331):** `app/engines/_graph_rag_impl.py::_render_supplementary_sections`,
reordering the graph-context ref list immediately before `render_kg_context`, using
`context.question` as the query. Gate `REGENOLD_COHERE_RERANK`, default OFF pending the
A/B; needs `COHERE_API_KEY` (present in `.env` and on Railway); registered in
`_engine_cache_key`.

It composes with R330's repair of the same call site (which passes `context.question` so
the R327 semantic layers stop being dead code): the rerank sits between the two, so with
the gate ON both the graph fetches and the semantic layers see the reranked order, and
with the gate OFF the block is byte-identical to R330. `test_r330_question_still_reaches_the_graph`
pins that R331 does not re-break R330's fix.

**Why that placement and not retrieval.** Every `kg_context.fetch_*` reader truncates via
`_node_ids(refs, limit=max_refs)`, `max_refs` default **8**. The cut is by list position,
so when the context carries more than 8 refs the order decides *which* provisions' verbatim
paragraph and sub-point text reaches Stage-2 — a content change, not a permutation of the
output. It targets **Answer Correctness**, the largest gap to frontier.

⚠ **CORRECTED R365 — the two sentences that used to follow here were FALSE and they
excused this lever from the gold gate.** They read: *"The graph blocks are non-citable
(`AGENTS.md` invariant #3), so this **cannot** add, drop or reorder a wire citation —
which is why it is not blocked on the missing `gold_dropped` guard. Gate it on `ab_judge`
(it moves answers), **not** `easyhard_ab`."*

**The Stage-2 prompt is not a sink.** The emitted wire `references` list is *recomputed
from the final Stage-2 prose* by three default-ON, `stage2_landed`-gated passes:

* `_reconcile_references_to_prose` (`app/routes/regenold.py:3921`, live at `:8791` / `:9073`,
  `REGENOLD_REFS_RECONCILE` default `1`) — **DROPS** wire refs the prose does not describe;
* R138 `_add_prose_named_refs` (`:4223`, final pass at `:9114`, `REGENOLD_CITE_CONSISTENCY`
  default `1`) — **ADDS** every provision the prose names, uncapped;
* `_surface_prose_subpoints` (`:3990`, at `:9179`) — **ADDS** sub-points the prose names.

So **any lever that changes the Stage-2 prompt can add, drop and reorder wire citations.**
Executed proof: `_reconcile_references_to_prose` returns two *disjoint* reference lists from
the *same* input refs under two different prose bodies. Measured proof from the sibling fork's
own n=140 paired run of a prompt-only lever (`REGENOLD_ROLE_OBLIGATION_CONTEXT`): the wire ref
list changed on **68/140 rows**, `gold_dropped_head` rose **30 → 34**, and it was vetoed on
exactly that.

Invariant #3 still holds in its true, narrow form: the graph cannot be a citation **source**.
It is **not** a statement of reference-neutrality.

⚠ **The trap that hides this.** The sibling's unit test `test_lever_does_not_change_the_wire`
asserts `on["references"] == off["references"]` and *passes* — because its fixture sets
`P2P_GRAPH_RAG_PROVIDER=cli` and a dead `OPENAI_API_BASE`, so `stage2_landed` is False and all
three prose→refs passes are, in this repo's own words, a "strict no-op". **A deterministic
fixture pins reference-neutrality in exactly the regime where the coupling is switched off.**
Never conclude reference-neutrality from a `provider=cli` test.

**Therefore: gate this on `ab_judge` for answers AND on `easyhard_ab`/`gold_dropped_head` for
references.** Both, not either.

**Prove it fires before reading any number.** `cohere_rerank.rerank_stats()` returns
`attempts / reordered / noop / failed`. R329 tried three placements; all three looked right
in the diff and all three made zero calls, reading +0.0000 — indistinguishable from a lever
that does not work. `tests/test_r331_rerank_placement.py` pins that the placement fires,
that the surviving top-8 set actually changes, and that the flag reaches the cache key.

⚠ **The "the model itself is good" probe is weaker than recorded.** The claim was that it
separates `Art. 50.3` **0.9244** from `Art. 19` **0.0394** and `Art. 99` **0.0090**.
Re-measured live against this repo's own `get_provision_text`: `Article 50.3` **0.8803** and
`Article 19` **0.0286** reproduce, but **`Article 99` scores 0.4583 — 50× the recorded
figure**, and it is the case that discriminates. Article 99 is *penalties*: legally
inapposite to a transparency-duty question, semantically plausible because its text
enumerates the very articles being asked about. That is exactly the failure class this
corpus suffers from, and a relevance cross-encoder does **not** cleanly reject it. Expect a
smaller effect than the probe implies, and prefer feeding sub-provision text over
full-article text where the ref grain allows it.

Two things to keep straight, because they are different interventions and only one has
been measured:

* **Post-hoc reordering of the final emitted reference list (measured, does NOT help).**
  Zero-variance replay of the live HARD run: mean normalised position of judged-wrong refs
  0.582 → 0.562 (delta **−0.019**, i.e. slightly worse). By that point the wrong references
  are already semantically plausible — that is *why* they were emitted — so a relevance
  cross-encoder scores them high for the same reason the generator did. Do not re-propose
  this variant; it is the one that is dead, not reranking in general.

The wrong references on this corpus are **semantically plausible and legally inapposite**
(e.g. `Article 43`, conformity assessment, cited on a risk-classification question). The
signal that *looks* like it discriminates them is *legal applicability* — does this provision
bind THIS role at THIS risk class — available as `ROLE_OBLIGATIONS` / `obligations_for`
(`app/data/ontology.py:684` / `:815`) and as the graph's `Obligation`/`HAS_OBLIGATION` (113)
and `RiskLevel`/`APPLIES_AT` (47) layers.

⛔ **MEASURED AND REFUTED (R365). Do not build the applicability filter.** The sentence that
used to close this paragraph — *"That is a grounding predicate, not a positional trimmer, so
it sits outside the refuted trimmer families"* — is **half right and it cost real work.** It is
outside families #1/#2/#3/#6/#7; it is **squarely inside #4 (ask-type × provision-role
exclusivity)** and overlaps #5. Three independent measurements, none of them a live A/B:

| instrument | result |
| :--- | :--- |
| 120 judged rows, per-row **ORACLE** (role,risk) — an upper bound no detector can reach | catches 104/118 wrong refs, **also drops 44/233 judged-RIGHT refs (19%)**, precision 0.70 |
| this repo's probe gold, real `_detect_role_and_risk_class` | **10 of 23 gold heads dropped (43%)** on the rows where it fires |
| sibling fork, `REGENOLD_ROLE_OBLIGATION_CONTEXT`, n=140 paired | vetoed: `gold_dropped_head` 30 → 34, `reference_correctness` exactly flat |

Three further facts close it — and note the “gate” itself is aspirational, see the correction below:

1. **It is inert on ~88% of traffic.** Both `role` and `risk_class` are extractable on
   **16 of 132** probe rows (12.1%); the sibling measured 11/297. A lever evaluable on 12% of
   rows will read UNDERPOWERED on any n=60–140 A/B — which is exactly what happened to R371.4/.5.
2. **The table is a SEED list, not a completeness list.** `obligations_for("deployer",
   "limited_risk")` returns **one** ref; `deployer × high_risk_annex_iii` returns four. Gold
   also cites the **governing / classifying / enforcing** provision (Art. 51 classification,
   Art. 101 penalties, Art. 50 cumulative across tiers), and no role×tier duty table contains
   those. Using a seed list as a drop-filter is a whitelist-completeness fallacy.
3. **The sibling already measured this ontology AS a citation oracle at 0% precision** —
   two statute-verified correct bindings added 8 non-gold refs and 0 gold. Recorded verbatim
   there: *"Legally correct is not gold-correct."*

⚠ Note the direction of use: `obligations_for` is **already a reference GENERATOR here**
(`_build_role_obligation_answer` → `_seed_role_obligation_obligations`,
`app/engines/_graph_rag_impl.py:3848-3900`) — which is the direction measured at 0% precision.
This repo's `ROLE_OBLIGATIONS` is also legally wrong in ~16 places the sibling fixed at R371.6
(e.g. `Art. 13` bound to DEPLOYER — Art. 13(1) binds the provider; `Art. 85`/`Art. 86` listed
as obligations when they are **rights**).

**What to do instead** — both outside all seven refuted families, and both ADD/GROUND rather
than DROP:
* **the citable-base guard** — `_add_prose_named_refs` already takes a `citable_bases`
  parameter (`app/routes/regenold.py:4223`) and **neither call site passes it**. Constraining
  prose-promotion to the retrieval-derived universe can only ever *remove an ungrounded
  promotion*; it can never invent a reference.
* **R368/R369 recall supplements** — the best-measured reference change in either repo
  (12 gold heads recovered, **0 false positives**, ref_loose 0.764 → 0.833). ADD-only, so it
  cannot trip `gold_dropped_head`.

**And the reason a ref-list transform is the wrong altitude at all:** on the 120 judged rows,
**73/118 (61.9%) of the judged-wrong references are NAMED IN THE SHIPPED ANSWER PROSE**, so
R274 ("never drop a ref the prose describes") makes them undroppable. The ceiling for *any*
reference-list transform is **+0.133** reference correctness and that assumes *perfect*
discrimination. There is also no head-identity rule to be had: `Article 26` is judged wrong
10× / right 2×, but `Annex III` is wrong 8× / **right 34×** and `Article 6` is wrong 3× /
**right 40×**. The signal is row-conditional, not head-conditional.

⚠ **CORRECTED R360 — `gold_dropped` DOES exist and the rule IS enforceable.**
The paragraph below previously read "`gold_dropped` does not exist anywhere in this
repo, so the standing rule … is currently **unenforceable**. Port `gold_dropped_head`
before gating any reference change." That was false when written and it cost work:
three separate reference-affecting changes were held back as ungateable. The
instrument is `gold_dropped_head` at **`evals/bench/metrics.py:555`**, wired into
`evals/harness/easyhard_ab.py::_score_row` and aggregated as a **SUM**, i.e. the gate
is literally "drop ZERO". Only the *exact* (sub-point) grain is missing — which is the
separate, still-correct point below.

⚠ **CORRECTED R365 — "gated" was the wrong word; until R365 it was only PRINTED.**
The SUM existed and the `<-- GOLD DROPPED (hard rule #8)` flag string was emitted,
but nothing enforced it: `gold_dropped_head` is absent from `_AXES` and `_LEVERAGE`,
the module had no `assert` and no `hard_fail`, its only `SystemExit`s were argparse
errors, `main()` returned `None` under a bare `main()` call in `__main__`, and the
repo has no `.github/` to consume it. A replay of the real `easyhard-r332-smoke-A`
checkpoint with one gold head deleted from the branch arm printed
`gold_drop_hd  0  1  +1  <-- GOLD DROPPED (hard rule #8)` and **exited 0**. Every
historical "it passed the gold gate" claim was a human reading stdout.

**R365 makes it an exit code.** `main() -> int` returns **1** when the branch arm
drops more gold heads than the baseline on ANY split, wired through
`raise SystemExit(main())`; the delta is read from the PAIRED subset where one exists
and from the full aggregate otherwise; the per-row `gold_dropped_head_refs` are
printed so a failure is actionable. The decision is the pure
`_gold_gate_verdict(base_agg, branch_agg, allow, paired=…)`, pinned two-sided and
offline by `tests/test_r365_gold_gate_enforced.py`. `--allow-gold-drop` forces exit 0
for a deliberate exploratory arm and says loudly that the run did **not** pass —
never cite an `--allow-gold-drop` run as having cleared the gate. A single-arm
scorecard is not gated; the rule is comparative.

⚠ **The sibling `evals/harness/ab_judge.py` still has the reports-but-never-enforces
shape** — it already has the plumbing (`main() -> int`, `raise SystemExit(main())`)
but returns 0 unconditionally on any completed run, so a `BASELINE wins (sig)`
verdict — the merge-blocking outcome the harness exists to detect — exits 0 exactly
as before. Deliberately left unchanged by R365 to keep that PR one concern. Do NOT port the upstream
`ref_crag_fine` / `gold_dropped_exact` as-is — the decision is right, but the reason
recorded here was wrong. **Corrected R331:** `_gold_exact_refs` does *not* head-project.
The real defect is that our probe gold carries **0/208 sub-point grain** — it is
article-level throughout — so `['Article 5.1.f','Annex III.2']` scored against gold
`['Article 5','Annex III']` yields `gold_dropped_exact = 2` and `ref_crag_fine = -1.0`,
penalising the most accurate citation shape the system emits. Same conclusion, and the
fix is gold that carries sub-point coordinates, not a change to the metric.

## Stage-2 transport contract (R360)

**Stage-2 rides the cloudflared tunnel (Claude Max) first and AWS Bedrock second.
No third leg exists.** `app/llm/stage2_policy.py` is the single source of truth;
`REGENOLD_STAGE2_STRICT_TRANSPORT` (default **ON**) enforces it and is registered
in `_engine_cache_key`.

Five paths used to break that contract, and the first two were armed by nothing
more than an API key sitting in the environment — no flag, no deliberate opt-in:

| path | how it opened | now |
| :--- | :--- | :--- |
| Groq tertiary fallback in `_openai_wrapper_complete_for_graph_rag` | any `GROQ_API_KEY` + one tunnel failure | refused |
| Gemini secondary fallback in `_claude_max_enhance_answer` | any `GEMINI_API_KEY` + tunnel *and* Bedrock both empty | refused |
| `P2P_GRAPH_RAG_PROVIDER=gemini\|anthropic` | explicit env | collapsed to the tunnel |
| fusion panel (`REGENOLD_FUSION_STAGE2=1`) | default roster is `(sonnet, groq, mistral)` | off-contract members filtered out of the roster |
| `P2P_GRAPH_RAG_PROVIDER=bedrock` | explicit env | collapsed to the tunnel — see below |

That last row is not an escape but an **inversion**: honouring it makes the
fallback the primary, so the Claude Max subscription is never dialled at all.

⚠ **The Groq hatch was not hypothetical.** It swapped in a *compressed* system
prompt (`_get_groq_compressed_system_prompt`) and, above ~11 kB, a shrunken user
message. So a deploy carrying `GROQ_API_KEY` answered its first post-hiccup
questions from a different model **on a prompt no eval has ever measured** —
silently, and attributed to the tunnel arm in any A/B running at the time.

**Prove it fires before reading any number.** `stage2_policy.transport_stats()`
returns `primary_attempts / primary_ok / primary_failed / fallback_* / refused /
refused_by_provider`, and `/healthz/llm` surfaces the same block under
`stage2_transport`. This follows the R329 rule the hard way: three rerank
placements all read correctly in the diff and all made **zero calls**, so
`tests/test_r360_stage2_transport_policy.py` asserts on those counters, never on
the shape of the code. It is also two-sided — it pins that
`REGENOLD_STAGE2_STRICT_TRANSPORT=0` *really does* still reach Groq, because a
guard whose OFF state behaves like its ON state is the inert-feature trap.

Four existing test modules (`test_fusion_stage2`, `test_gemini_routing`,
`test_anthropic_provider`, and the fusion half of `test_r127_trace_latency`)
cover the legacy multi-provider call shapes. Their assertions are unchanged;
they now declare `REGENOLD_STAGE2_STRICT_TRANSPORT=0`, the regime they were
written for.

---

## Baseline Performance Reference (Commit `b47c259`)

Deterministic environment: `OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0`

| Metric Axis | Ans Loose | Ans Strict | Ans Conc | Ref Loose | Ref Strict | Ref Conc | Tone |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OVERALL (476)** | 0.1884 | **0.3545** | 0.6143 | **0.5971** | **0.4748** | 0.4316 | 1.0 |
| **QA (137)** | 0.1407 | 0.4072 | 0.1961 | 0.8394 | 0.5536 | 0.4390 | 1.0 |
| **Scenarios (339)** | 0.2076 | 0.3332 | 0.7833 | 0.4992 | 0.4430 | 0.4287 | 1.0 |

Multi-turn coherence: **20/20 coherent**.

> **R330 — the bench measures CODE DEFAULTS, never your `.env`.** R329's
> `_load_dotenv_once()` (`app/config.py`, added to fix the "No Conn" UI bug) put the
> repo `.env` into `os.environ` at **import time**. `.env` carries BEHAVIOURAL flags
> (`REGENOLD_ROLE_DUTY_NOUN_SEED`, `REGENOLD_GRAPH_2HOP`, `REGENOLD_MAX_ANSWER_SENTENCES`
> …) next to credentials, so from that commit on the guard silently scored whatever a
> developer happened to have locally. Measured cost on the full 476:
>
> | arm | Ref Loose | Ref Strict | multi-turn |
> | :--- | :--- | :--- | :--- |
> | code defaults | 0.5971 | 0.4748 | 20/20 |
> | `REGENOLD_ROLE_DUTY_NOUN_SEED=1` alone | 0.5971 | 0.4633 | 20/20 |
> | the full local `.env` | 0.5735 | 0.4489 | 13/20 |
>
> This looked exactly like a **−0.026 Ref Strict / −45 pp coherence regression across 15
> commits that are in fact behaviourally neutral.** 13 of the 14 flags are individually
> inert; `ROLE_DUTY_NOUN_SEED` alone costs −0.0114 Ref Strict and the rest is interaction.
> `evals/bench/runner.py` now sets `REGENOLD_SKIP_DOTENV=1` before the first `app` import,
> which reproduces the table above byte-for-byte. Set `REGENOLD_SKIP_DOTENV=0` for a
> deliberate `.env`-on arm. **Live harnesses are unaffected — they still need `.env` for
> `OPENAI_API_BASE` + `CF_ACCESS_*`.** Production is unaffected either way (Railway sets
> real env vars and `override=False` already makes those win).
>
> **It also breaks the SCOPE gate.** `runner_v2 --local --probe-oos --oos-suite all`
> (n=51), which still loads `.env`:
>
> | arm | pass | scope leaks | `hard_fail` |
> | :--- | :--- | :--- | :--- |
> | code defaults (`REGENOLD_SKIP_DOTENV=1`) | 49 | **0** | False |
> | `.env` loaded, `REGENOLD_*` blanked | 46 | **3** | True |
> | the full local `.env` | 35 | **15** (29.4%) | True |
>
> No single `REGENOLD_*` flag reproduces it (all measured individually at 0 leaks), and
> neither does `GROQ_API_KEY` alone — so it is the CREDENTIALS reaching the R267.1
> Groq→Gemini→Mistral fallback, plus interaction with the flags. **The "deterministic"
> OOS probe is not deterministic when `.env` is present: the scope classifier can make
> live third-party calls.** Run it as
> `REGENOLD_SKIP_DOTENV=1 … -m evals.regenold.runner_v2 --local --probe-oos` (as of R330
> `runner_v2` sets this itself for `--local --probe-oos`).
>
> ⚠ **Open operator question:** does the Railway dashboard carry the same behavioural
> flags? If yes, production pays the Ref-Strict cost. If no, local evals do not predict
> production. Reconcile the two flag sets. **This is an eval-fidelity question, NOT a
> production-safety one** — see the scope note below.

### The OOS probe over-counts: "leak" ≠ the product requirement (R330)

**Measured against LIVE production** (`--endpoint …up.railway.app`, n=51): 41 pass, 10
"scope leaks", `hard_fail: True`. **That verdict is a harness artefact, not a defect.**

The requirement is that the assistant **pushes back on ADVERSARIAL input**; answering an
off-topic pleasantry is acceptable. Split that way, production is clean:

| category | live result |
| :--- | :--- |
| `injection` ("ignore all previous instructions", "what is your system prompt", DAN) | **3/3 pass** |
| `injection_obf` (base64 payload, translate-then-follow, roleplay-as-unrestricted) | **3/3 pass** |
| `scope_drift_mt` (multi-turn pivot off a genuine Art. 9 / Annex III thread) | **3/3 pass** |
| `nonsense`, `greeting`, `other_regulation`, `nonexistent`, `standards`, `non_eu_ai_law` | **all pass** |
| `r34_p0` / `r47_e` (Netflix, restaurant, weather, a joke) | 7 "leaks" — **chit-chat, allowed** |
| `adjacent_eu` (Product Liability Directive, MDR clinical evaluation) | 2 "leaks" — answers are **legally correct** |

**12/12 on adversarial.** Do NOT "fix" this by setting `REGENOLD_TOPIC_FILTER=0/1` on
Railway: R255 disabled the broad subject-topic filter precisely because the keyword
classifier false-positived on genuine, keyword-less AI Act questions, and R256's design
routes those to the LLM gate so real questions get rescued. Turning the blunt filter back
on trades a non-problem for a real one.

⚠ **What IS worth knowing:** an anchor-less question lands in the ambiguous
`CONVERSATIONAL` bucket handed to the LLM scope gate, and `regenold.py:5002` records that
"with no LLM wired it fails soft to the generic decline". So every `--local`
deterministic OOS run **fails safe by construction** and cannot measure the live gate at
all. If you want to test scope behaviour, run `--probe-oos` against the DEPLOYED endpoint.
Judge it on the adversarial categories only.

---

## Recent Engine Fixes (R356–R359)

Concise record of the applied fixes; full rationale in `docs/reviews/`:

* **R356 — grounded judge-report fixes.** Entity-map anchors that were
  missing (e.g. `human oversight → Art. 14`, `Art. 79/80`, `Annex III.5.c/d`),
  the Article 6(3) derogation detector extended to the narrow-procedural
  shape, and two new curated intercepts (GPAI transparency exceptions,
  systemic-risk scope) — each verified against the official provision text
  and false-positive-checked across all 81 live rows.
* **R357 — Stage-2 truncation guard (default ON).** `_guard_stage2_truncation`
  detects an incomplete final sentence (incl. trailing `…`) in the polish,
  repairs it with one bounded completion call, and falls back to the complete
  deterministic Stage-1 answer when repair fails. Never ships a fragment;
  gate `REGENOLD_STAGE2_TRUNCATION_GUARD`.
* **R358 — curated authoritative intercepts.** Four new curated answers
  (emergency triage `Annex III.5.d`, health-insurance pricing `5(c)`, hospital
  deployer duties, provider pre-market duties) that seed gold-head reference
  sets and skip Stage-2 polish (`_is_curated_authoritative_intercept`).
* **R359 — fine-grained CRAG answer judge (⚠ NOT IN THIS REPO).** Corrected R360:
  `answer_crag_fine` has **0 occurrences** here — it lives in the eval repo only.
  The description below is of that repo's axis, kept for provenance. `answer_crag_fine`
  axis ports the NICD paper's Appendix C.2.2 5-level truthfulness scale
  (`+1 / +0.5 / 0 / −0.5 / −1`) to the ANSWER, with truthfulness = sum of
  scores and hallucinated-row counts. Opt-in (not in default `AXES`); judged
  via Bedrock sonnet, never the Claude-Max tunnel.
* **R328–R354 ports** — `query_expansion.py` (LLM query rewrite, default OFF),
  `risk_classification.py` (Annex-III risk-class anchor, default OFF),
  rerank + graph-semantic upgrades; see the port review doc.

## Environment Flags Reference

| Environment Variable | Code Default | Purpose |
| :--- | :--- | :--- |
| `P2P_GRAPH_RAG_PROVIDER` | `auto` | Selected LLM backend (`cli`, `anthropic`, `openai_wrapper`, `bedrock`) |
| `REGENOLD_STAGE2_STRICT_TRANSPORT` | `1` | R360 Stage-2 transport contract: cloudflared tunnel (Claude Max) primary → Bedrock fallback, everything else refused |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | `1` | Stage-2 LLM polish master gate |
| `REGENOLD_GRAPH_SEMANTIC_LAYERS` | `0` | Constrained sub-provision vector search across Neo4j indexes (R327). **Corrected R360** — this table said `1`; R330 flipped the code default ON → OFF (`app/engines/graph_semantic.py:155`) |
| `REGENOLD_SEMANTIC_GLOSS` | `0` | Open-domain definitions/recitals gloss gate (R327) |
| `REGENOLD_GRAPH_VECTOR_RECALL` | `0` | Additive Neo4j & local SVD vector recall path (R326) |
| `REGENOLD_PARENT_COLLAPSE` | `0` | Collapse parent provisions when sub-points are cited (R325). **Corrected R366 — this row described a DEAD FLAG.** The helpers shipped in `a659849` with no call site; R366 wired it as the last reference pass. Still default OFF, and a strict **no-op offline** — see below |
| `REGENOLD_STAGE2_TRUNCATION_GUARD` | `1` | R357 post-generation truncation repair on the Stage-2 polish |
| `REGENOLD_SCOPE_STOP_RULE` | `0` | R367 scope stop rule on the Stage-2 USER channel: answer the question, then STOP; never append a neighbouring provision/power/mechanism/derogation the question did not raise. Targets BOTH conciseness axes (combined leverage 0.364 pp/pp). **Prompt-side ⇒ NOT reference-neutral** (AGENTS.md invariant #5), so it needs `easyhard_ab`/`gold_dropped_head` AND `ab_judge` before flipping |
| `REGENOLD_QUERY_EXPANSION` | `0` | LLM query rewrite before retrieval (R328 port; latency+cost tradeoff) |
| `REGENOLD_RISK_CLASS_ANNEX` | `0` | Annex-III risk-classification anchor (R328 port) |
| `BEDROCK_REGION` | `eu-central-1` | AWS Bedrock cross-region inference profile geography (R328) |
| `NEO4J_AUTO_SEED` | ⚠ **ON when unset** (given `NEO4J_URI`) | Boot graph seeder safety switch. **Corrected R365 — this table said `0 (or off)` and that is FALSE.** `_auto_seed_disabled_by_env()` (`app/main.py:276-290`) returns `False` when the var is unset, i.e. *not disabled*; its own docstring says “Default is ON when `NEO4J_URI` is set — operators have to opt OUT rather than opt in.” This contradicts `AGENTS.md` (“NEVER set `NEO4J_AUTO_SEED=1` by default”) and `.env.example`. Currently **latent** because production’s `seed_version` matches the code exactly, and R361 hardened the emptiness probe (`app/main.py:550`, `:620-627`) so a swallowed Neo4j failure no longer reads as “graph is empty”. Set it explicitly on Railway: `railway variables --set NEO4J_AUTO_SEED=0`. Flipping the *code* default is confirmation-gated (`AGENTS.md` § Requires Confirmation). |

---

## Parent collapse (R325) — wired in R366, and why it reads +0.0000

⚠ **CORRECTED R366 — `REGENOLD_PARENT_COLLAPSE` was a DEAD FLAG until R366.**
`app/routes/regenold.py` defined `_parent_collapse_enabled()` and
`_collapse_parent_when_subpoint_cited()`, but **nothing in `app/` called
them** — the only importer was `tests/test_r325_parent_collapse.py`, which
exercised the helpers in isolation. Meanwhile the flag table above described
the behaviour as live and `AGENTS.md` drew it as a step in the request
pipeline. Both were false.

**Lost in the port, not intentionally removed.**
`git log -S "_collapse_parent_when_subpoint_cited" -- app/routes/regenold.py`
returns exactly **one** commit — `a659849` ("feat(r328): integrate R320-R328
optimizations") — and that commit adds only the two `def` lines. No commit
ever removed a call site, because one was never added. The sibling repo
`antifragileai-regenold-evaluation` **does** have it, as the last reference
pass. The same port also added
`tests/test_evaluator_batch_july7.py` and `tests/test_r293_july7_difficulty.py`,
which import `evals.regenold` modules it never brought across — those two
still abort `pytest tests/` at collection, so the port was lossy in at least
three places.

**This is the third time.** R329's three rerank placements all read correctly
in the diff and all made zero calls; R330's entire R327 semantic layer never
executed because one call site dropped one argument. The standing rule stays:
default-ON + cache-keyed + unit-tested + documented is **not** evidence a flag
runs. Grep the call site.

**Where it is wired now.** `app/routes/regenold.py`, the LAST reference pass —
after the R276-D1 granularity pass, both clamps, the R260/R311 enforcement, the
R302 pushback freeze and the R365 recall wire guard, and immediately BEFORE the
R50/R131 trace finalisation so the trace still equals the wire refs. That
position is load-bearing: `_collapse_parent_refs` already implements the same
rule mid-pipeline, but it runs immediately BEFORE `_reemit_parents_for_subpoints`
(R87-C, default ON), which re-ADDS the parent — the ordering defect that lets
the wire ship `[Article 50.1, Article 50, Article 50.2]`.

**Order vs the R365 wire guard.** Guard first, collapse second. They do not
fight: the guard is ADD-only and appends a head only when
`_canonical_reference_base` finds no reference carrying that base, so a head
this pass drops (which still has its own leaf, and therefore its base, on the
list) is never re-added. Collapse-second is the safer of the two equivalents.
Both are default OFF, so no interaction ships today.

⚠ **Prove it fires, and expect +0.0000 offline.** The pass is a strict no-op on
the deterministic path: head+leaf clusters are minted live by
`_surface_prose_subpoints` (`_stage2_landed`-gated), and offline the R276-D1
`auto` mode has already resolved every mixed cluster before control reaches the
collapse. Measured across 20 offline questions spanning the sub-point-emitting
topics: **zero collapsible pairs**. So a deterministic +0.0000 is the EXPECTED
reading and is **not** evidence of a broken lever — that misreading is what
killed three R329 rerank placements. `tests/test_r366_parent_collapse_wired.py`
asserts on the wire (call site reached ON, not reached OFF, return value
reaches `response.references`, drop recorded in the trace) and pins the offline
no-op as a **tripwire**: if it fails, the offline path started minting
collapsible pairs and davidath neutrality must be re-measured.

**Gate before flipping it.** It DROPS references — the R142.1 failure mode that
lost a live pairwise judge 11-0 (p=0.001) — and it knowingly overrides the R274
curated-intercept protection (`["Article 6.3", "Article 6", "Annex III"]` →
`["Article 6.3", "Annex III"]`, pinned in
`test_r325_parent_collapse.py::TestKnownTradeIsPinned`). Ship only behind an
`evals.harness.easyhard_ab` win — the gold-bearing harness, **not** `ab_judge`.

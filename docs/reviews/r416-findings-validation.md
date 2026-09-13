# R416 — validation of the pasted gap analysis, finding by finding

**Date:** 2026-09-13 **Branch:** `fix/r409-r408-audit`
**Input:** the "SOTA proposal vs code gap" analysis (7 domains), reviewed against the
code, its recorded measurements, and frozen ledgers.
**Rule applied:** a finding is *confirmed* only if the code and a measurement agree;
otherwise it is *corrected* with the evidence that contradicts it. Dispositions are
`CONFIRMED`, `CORRECTED` (the claim as stated is false or stale, with the true value),
or `CONFIRMED — already gated` (true, and the code already documents why it is off).

Corrections from the parallel review pass (`docs/measurements/r416/*`) are folded in
and re-run here, not taken on trust: the frozen recount was re-executed for this
document and reproduced to the byte (input hashes in `frozen-summary.json`).

| # | finding | verdict | one-line evidence |
| :- | :--- | :--- | :--- |
| 1.1 | graph stack additively inert at defaults | **CONFIRMED — already documented** | `kb_search.py:968` records 660 hop2 refs available, **4 added** over 132 rows |
| 1.2 | KG supplies no point text under the default flag | **CONFIRMED — built, ungated** | legacy cypher requires a SubPoint; live graph has 421 Points / 37 SubPoints |
| 1.3 | Cohere rerank default OFF | **CORRECTED** | `cohere_rerank.py:326` — **DEFAULT ON** (R400) whenever a key is present |
| 2.1 | HyPA adaptive router default OFF | **CONFIRMED — already gated** | R329 in-place A/B: Ref Conc **−0.2094**, Ref Strict −0.1137, gold head dropped |
| 2.2 | HyPA RRF default OFF | **CONFIRMED — already gated** | R329: duplicates the shipped `REGENOLD_RRF_FUSION` impl; dense arm inert |
| 3.1 | multi-turn Stage-2 gets a 61-char persona | **CONFIRMED — by design** | R415 proved it at the provider seam (graded payload byte-identical) |
| 3.2 | deterministic content-preservation contract missing | **CONFIRMED** | `_guard_answer_completeness` is an LLM repair; all sub-guards default OFF |
| 4.1 | ref-conciseness deadlock; post-hoc pruning rejected | **CONFIRMED** | pruning reproduces: **19** excess removed, **2** expected lost |
| 4.2 | grain "14.3 % emitted vs ~71 % keys" | **CORRECTED (stale)** | frozen recount: **85.81 % emitted vs 84.44 % keys** |
| 5a | 3,000-line route duplicates engine logic; no cross-layer tests | **SPLIT** | route is **12,058** lines, but `tests/test_f5_route_engine_ref_contract.py` exists |
| 5b | CLARA: 1,159 lines of dead code, zero import sites | **CORRECTED** | guarded **default-ON** route call; `tests/test_r416_route_architecture.py` pins it |
| 6 | F7 member-recall probe is evidence for the detector's ceiling | **VOID → repaired** | probe read `answer`; the checkpoint has only `pred_answer` (0/110 loaded) |

---

## 1. Retrieval substrate

### 1.1 Graph stack inert at defaults — CONFIRMED, and the number is in the code

The fusion budget, not the graph, is the gate. `fuse_with_kb_xrefs` appends only into
`budget - len(winners)`, and BM25 returns `k` winners, so there is no slack. The
comment at `app/data/kb_search.py:968` carries the measurement over the full 132-row
`ab_judge` probe set with a healthy graph: **660 hop2 refs available, 1/132 calls with
slack, 4 refs added** (~99.4 % discarded). `REGENOLD_GRAPH_FUSE_SLACK` (default 0)
exists to buy slack and ships OFF pending a live pairwise `ab_judge`, because added
candidates reach the wire refs through `query.entities`.

So the report's structural claim is right, but its implicit framing — that this is an
unnoticed gap — is not: the lever is built, measured, and deliberately off. The open
question is a *value* question the code does not answer: **do the 660 available graph
candidates contain gold heads BM25 misses?** If they do not, the whole family can be
closed as inert rather than re-tried; that is the test to run before touching slack.

### 1.2 KG contributes no point text by default — CONFIRMED, and it is the biggest live lever

Exactly as the report says. `_SUBPOINT_CYPHER_LEGACY` (what production serves with
`REGENOLD_KG_POINT_TEXT=0`) contains a mandatory
`MATCH (pt:Point)-[:HAS_SUBPOINT]->(sp:SubPoint)`; the live graph has **421 Points and
37 SubPoints**, so points without a sub-point — all of Article 25(1), most of Article
13(3) — never reach Stage-2.

R408/R409 built the fix (`OPTIONAL MATCH` + ref-ordered rows + a per-provision budget
shared by `_allocate_units`) and left it behind the OFF flag, because the block is
Stage-2 prompt text and therefore not reference-neutral (AGENTS.md invariant #5).

**R416 measured its reach on the exact rows we would gate it on**
(`docs/measurements/r416/kg_point_text_reach.py`, live Aura, no model calls):

* the block **changes on 23 of the 26** paired rows;
* units **26 → 384**, text **5,201 → 81,391 chars** (a 15.6× increase);
* on `rg_046` — a row whose triage recorded **omitted enumerated items** — the lever
  hands Stage-2 the exact limbs the answer had missed: `Article 13.3.a`, `.c`, `.d`.
  Two of that row's five recorded gaps (`13.3.e`, `.f`) are absent from both arms, so
  the lever is a partial fix, not a complete one, and must be reported as such.

That is the first lever in this repo whose reach is demonstrated on the *failure it
targets*, which is why it is gated below rather than filed as an open gap.

### 1.3 Cohere rerank — CORRECTED

`app/engines/cohere_rerank.py:326` documents `REGENOLD_COHERE_RERANK` as **DEFAULT ON**
(R400), fresh env read per call, with `=0` restoring the previous behaviour. The
report's "default OFF" is stale. The sub-claim that reranking does not reorder the
*wire* candidates is accurate: it reorders `_kg_refs` feeding `render_kg_context`, and
the R411 audit records that all three attempted placements produced 0 production calls
plus poor scores on the counter-example (`Article 99` at 0.4583 on a transparency
question). Those two facts are consistent — the flag is on, and it still does not
decide the wire.

## 2. Adaptive routing

### 2.1 HyPA adaptive complexity router — CONFIRMED, already gated

`is_adaptive_router_enabled()` returns False by default, and the docstring carries the
in-place A/B that flipped it (R329, `r329-armA-hypaoff` vs `r329-armB-hypa`, arm A
reproducing the documented baseline byte-for-byte): Ref Conciseness **−0.2094**
(0.4390 → 0.2296), Ref Strict **−0.1137**, for +0.0438 Ref Loose, with 73/137 rows
changed, +138 net references, and the gold head `Article 50` dropped on `qa_041`.
That last item is a hard-rule-#8 failure, which is why the flag is not merely
"unproven" — it is disproven for this corpus.

### 2.2 HyPA RRF retrieval — CONFIRMED, already gated

Same shape, three recorded reasons: RRF over this corpus is a wash re-confirmed three
times (R31/R69); the repo already ships RRF behind `REGENOLD_RRF_FUSION` (default
`"0"`) implemented in `turboquant_index.py`; and the module runs BM25
unconditionally, which pollutes citations on explicit-anchor questions. Its dense arm
is also inert while `REGENOLD_GRAPH_VECTOR_RECALL=0`.

## 3. Generation and prompt delivery

### 3.1 The multi-turn persona — CONFIRMED, by design, with the scope proven

True as stated: with `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=1`, a multi-turn ask
dispatches a 61-character persona. R415 proved the *scope* of that at the provider
seam: the route derives `history_turn_count` as `max(0, user+assistant−1)`, the arms'
graded payload is byte-identical on every multi-turn row (`sha 3bc63d065b58812b`) and
differs on every single-turn row (59,644-char full system), with a non-vacuity control
in the same run.

The report frames this as "15 system-level legal rules never reach Claude Max on hard
mode". That is mechanically true and is the *point* of the restriction: delivering them
unconditionally cost `gold_dropped_head` **12 → 18** and `ref_loose` **−10.81 pp** on
the 37-row hard ledger, i.e. it failed hard rule #8. The honest open question is
narrower than the report implies: the rules that matter on a pushback are the
*keep-what-you-said* ones, and R415's own residual notes the `<= 1` boundary includes
a two-message request. A middle prompt — the preservation rules only — is untested and
is the only form of this finding worth a gate.

### 3.2 Deterministic content-preservation contract — CONFIRMED as missing

There is no zero-cost contract. What exists is `_guard_answer_completeness`
(`_graph_rag_impl.py:11109`), whose own docstring records the triage: 55 engine-side
gaps, the needed provision **already cited in 53** — content lost at generation, not
retrieval. Its repair is a *rewrite* (a second LLM call, `_stage2_complete`, 1,536 max
tokens), accepted only under `accept_repair`, and all four sub-guards
(`closed_set_completeness`, `exception_limb`, `verdict_lead`, `pushback_keep`) are
default OFF because they fired on passing rows (9.9 %–97.2 % FP) and lost gold.

**R416 sharpens the operand from this round's own gate.** The R415 official-corpus
reading lost exactly two criteria, both to *scope narrowing* rather than omission:
`rg_045` reduced "without undue delay" from all three deployer duties to the informing
duties only, and `rg_010` dropped the aim clause of Article 14. A member-set diff
cannot see either. The contract has to compare **which limbs a qualifier governs**
between the draft and the polish.

## 4. Citation granularity and conciseness

### 4.1 Ref-conciseness deadlock — CONFIRMED, and re-derived

The report's structural claim is right and R413 had already falsified the post-hoc
family: `ref_conc` is a pure count ratio `(min(|P|,|G|)/max(|P|,|G|))²`, loose is
recall, strict is F1, and the aggregate is a *geometric* mean, so each dropped expected
head costs recall in the same product. The pruning replay reproduces on current inputs:
**19 excess references removed, 2 expected lost**. Conciseness must be addressed in
generation. The report and the repo agree here.

### 4.2 Sub-point grain — CORRECTED (the headline was stale)

The report's "our 14.3 % vs the keys' ~71 %" does not survive the recount. On the
frozen inputs the review pass pinned by hash
(`official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl`,
`official_refkey_n110.jsonl`):

* **emitted** refs with sub-point grain: 266/310 = **85.81 %**
* **expected** (reference-key) refs with sub-point grain: 114/135 = **84.44 %**

i.e. the wire is already within ~1.4 pp of the keys, not 57 pp behind. The recount uses
a dot-in-the-canonical-coordinate test on both sides and explicitly avoids head
folding, which is the operation that would erase the property being counted.

This matters because roadmap row 4 ("sub-point grain on the wire", expected +0.6 pp,
`COORD_MAP_PROMPT`) was justified by that stale ratio. On the corrected numbers the
premise is gone: there is no 5× deficit to close. Row 4 is closed below by measurement,
not by opinion.

*Caveat carried forward:* both sides of this ratio are computed on the frozen R407
ledger, not on today's live wire. It refutes the stated gap; it is not a live
scorecard.

## 5. Code integrity

### 5a. Duplicate pipeline — SPLIT

True and understated on size: `app/routes/regenold.py` is **12,058 lines**, not 3,000+,
and it does re-implement reference extraction, budgeting and mutation alongside
`_graph_rag_impl.py`. False on the contract-test claim: `tests/test_f5_route_engine_ref_contract.py`
exists and pins route/engine reference behaviour, and `tests/test_r416_route_architecture.py`
now pins the route seams (message counting, CLARA reachability) directly. The
maintainability point stands on its own merits; the "nothing guards it" point does not.

### 5b. CLARA dead code — CORRECTED

CLARA is not dead. `regenold_eu_ai_act_ask` imports and calls `clara_logic.analyse`
under default-ON `REGENOLD_CLARA_VERDICT`, with non-empty candidates and exclusions for
the prohibited, classification and curated-intercept paths. The historical regression
the report cites is real and still rules out re-enabling it *for prohibited/curated
verdicts*; that is a scoped prohibition, not a statement that the module is unreachable.
`AGENTS.md` carried the "zero import sites" claim and has been corrected;
`tests/test_r416_route_architecture.py` pins (i) default-ON reachability, (ii) `=0`
disabling it, and (iii) the prohibited emotion-monitoring question never reaching it.

## 6. The F7 evidence base was void

`docs/measurements/r411/member_recall_probe.py` loaded `answer`/`final_answer`, but the
R407 checkpoint stores the graded answer in `pred_answer`. It therefore diagnosed empty
strings for all 110 rows and printed a plausible blocker histogram — the same class as
the two void instruments this repo has already caught (the 189-fallback gate run and
the `stage2_landed`-gated ref-recall probe). The repaired probe validates its inputs
(unique ids, non-empty `pred_answer`) instead of silently substituting, and its replay
gives **7 not-list / 3 engaged / 1 question-not-engaged / 1 answer-not-naming-set**
across the 12 target rows; engaged rows are `rg_043`, `rg_046`, `rg_052`, and the
detector finds member gaps on the latter two.

The independent precision replay still stands and is the load-bearing number for the
flags: **0/71 passing rows fired**, 2/12 target rows, 7/22 target criteria with a
coordinate hit. So the detector's precision is better than F7's stale 9.9 % figure —
but "fires on nothing that passes" is not "safe to default ON", and the earlier live
gold-loss result remains the reason the repair flag stays OFF.

## 7. What this round changes

1. **The gate is now general** (`docs/measurements/r415/official_lever_gate.py`
   `--flag` / `--arm-values` / `--tag` / `--reach-from`). Every unproven roadmap row
   needs the same read — reachable rows, both arms tunnel-served, all eight axes judged
   — and the reach set belongs to the route, not the lever, so a new lever reuses the
   R415 reach list and pays for **one** arm of calls instead of two.
2. **Finding 1.2 is gated rather than filed, and it SHIPPED.** With reach proven on the
   failure it targets (§1.2), the paired read on the reconstructed official gold
   (25 rows, both arms tunnel-served, wrapper judge `claude-sonnet-5` temp 0.1 r=3) is:

   | axis | OFF (shipped) | ON | delta pp |
   | :--- | ---: | ---: | ---: |
   | ans_correctness_loose | 96.6 | 98.9 | **+2.3** |
   | ans_correctness_strict | 88.0 | 96.0 | **+8.0** |
   | ans_conciseness | 47.8 | 44.5 | −3.3 |
   | ref_correctness_loose | 100.0 | 100.0 | 0.0 |
   | ref_correctness_strict | 70.8 | 70.8 | 0.0 |
   | ref_conciseness | 51.6 | 52.2 | +0.6 |
   | regulatory_tone | 60.0 | 60.0 | 0.0 |
   | resp_speed | 70.4 | 71.3 | +0.9 |
   | **OVERALL (geo mean)** | 70.7 | **71.3** | **+0.6** |

   No expected head is lost (`ref_loose` flat at 100.0 — the precondition the flag's own
   docstring named, i.e. hard rule #8), and the correctness gain has a named mechanism
   rather than being a swing: **the only two rows that changed are `rg_010` and
   `rg_045`** — precisely the two the R415 compression had broken — and the legacy query
   returns **0** units for `rg_010`, so the missing Art. 14 aim clause is explained by the
   missing text, not by answer length alone. Default flipped ON (`=0` reverts); the cost
   is 1,425 → 1,543 answer chars, which is where the −3.3 pp of conciseness sits.

   **The instrument had to be fixed to read this honestly, twice.** First its pairing
   contradicted itself (it dropped a fallback row from one arm and voided on the other
   arm's identical row); both arms now apply the same drop. Second — and this one nearly
   produced a false report — the first table read **+6.1 pp overall**, which was a
   *blend*: arm A had the R415 single-turn lever OFF while a new arm-B run picks up that
   lever's shipped default ON, so the arms differed by **two** flags. The gate now takes
   an explicit `--baseline` and prints both run names above the table (the **one-flag
   invariant**); the honest read of the same data is **+0.6 pp overall, +8.0 pp Ans
   Strict**. The discarded blend and the real reading both remain on disk
   (`official-lever-paired-kgpt.json` is the post-fix artifact).
3. **Rows 4 and 5 of the roadmap move on evidence** — row 2 was already falsified in
   R413; row 4's premise is refuted here; row 5's projection is replaced by a measured
   +8.0 pp on Ans Strict and shipped.
4. **Three doc claims corrected at source** rather than left to mislead: the grain ratio
   (roadmap row 4), CLARA's reachability (`AGENTS.md`), and the cache-key AST gate's
   coverage of `app/llm/` (`AGENTS.md`).

## 8. Residuals this round does not close

* **The hard split is unmeasured for the KG lever.** It is a grounding-text change, so
  unlike the R415 lever it is *not* modality-restricted. Its direction is the opposite
  of the class that broke hard mode (answers got slightly longer and recovered points;
  no reference axis moved), but that is reasoning, not measurement. This is the next
  gate.
* **`REGENOLD_GRAPH_FUSE_SLACK` still has no value read.** §1.1 is confirmed but the
  question it needs answered — whether the 660 available candidates contain gold heads
  BM25 misses — is not answered here.
* **The content-preservation contract (row 3) is now better specified but still
  unwritten.** R415 named the operand (a qualifier's *scope* narrowing, e.g. `rg_045`),
  and this round shows the KG lever recovers that exact row — but a deterministic guard
  that catches it without firing on passing rows does not exist yet, and the F7 history
  (0/71 precision replay notwithstanding) is the reason not to ship one untested.
* **Row 4 is closed on the frozen ledger, not on live output.** Re-opening it requires a
  live emitted-vs-expected grain read, which this round did not build.

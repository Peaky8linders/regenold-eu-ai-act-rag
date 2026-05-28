# R93 — Semantic-aware citation faithfulness on the live Stage-2 path

**Trigger**: user dropped the CEUR paper *"A Graph-Enhanced LLM-Based
Question Answering System for the AI Act"* (Aggio, De Lazzari,
Scantamburlo — LLAIS 2025 / ECAI 2025) and asked to deep-dive it,
web-search for better/novel approaches, integrate the best, and run
live tests.

**Branch**: `r93-citation-faithfulness` (worktree off R92 HEAD `9714b08`).

---

## 1. Paper digest (what it actually is)

A GraphReader-style **agentic** KG-QA system over the AI Act:

- Offline LLM (GPT-4o-mini) extraction of a Neo4j graph:
  Article/Annex/Recital/Chapter/Section → **Chunk** → **AtomicFact**
  (LLM-extracted micro-claims) → **KeyElement** (LLM-extracted
  concepts). `text-embedding-3-small` vectors.
- Per-query **multi-step agent loop**: Rational Plan → Initial Node
  Selection → AtomicFact Exploration → Chunk Exploration → Neighbor
  Exploration → Answer Generation (3–6 LLM calls/query).
- Eval: **20 hand-written questions**, BERTScore + S-BERT cosine +
  3-expert Likert. Headline: `GraphReaderbase` Final Score 0.698,
  beating Clairk (0.671), SBERTGPT (0.519), BM25 baseline (0.211).

**Honest read**: modest results, tiny eval, multi-LLM-call latency,
LLM-extracted facts (drift risk). The prior on-disk `R89-PAPER-PLAN.md`
already mapped 16/16 paper techniques against the repo and found the
repo **already has** them, usually deterministically/better. Its one
genuinely-new idea (Section-layer routing) the field research below
shows is a davidath-flat marginal tweak.

## 2. Field research (3 parallel agents, 2025–2026 SOTA)

Triply-corroborated conclusions:

1. **Graph retrieval is a trap for our query distribution.** Independent
   2025 studies — CEUR Vol-4079 (EU-Directive *article-level* QA:
   HippoRAG 2 0.78 vs naive RAG 0.82), GraphRAG-Bench, AGORA
   ("retrieval improvements do not guarantee better answers") — show
   graph methods *lose* to naive RAG on article-scoped legal QA and
   break a <6s latency budget. This is the repo's own "BM25-saturated"
   finding (R31/R59/R69), now corroborated externally a 3rd time. → **Do
   not add a retrieval engine, reranker, or agent loop.** (LLM rerankers:
   +0.04 NDCG for 9×cost/35×latency. Cross-encoders: GPU. Both SKIP.)

2. **The real win is span-grounded citation faithfulness** — the
   convergence of the paper's *AtomicFact* idea (done deterministically),
   **CiteFix** (ACL 2025: post-hoc, no-LLM citation reconciliation via
   keyword+retrieval-score blend, +15.5% citation accuracy @ 0.015s —
   and its *LLM-based* variant is the WORST, +1.9% @ 1.6s), **FRONT**
   (quote-first grounding), **ReClaim** ("ground every sentence" — derive
   refs from surviving prose, cut citation length 22%). This targets the
   judge's **worst axis**: refs-faithfulness (~0.20–0.43, "Article N
   cited but never described in the prose").

3. **🔴 A "fact update" that is actually a trap.** Research agent #3
   recommended adding the Digital Omnibus Art. 5 prohibitions (NCII/CSAM,
   2 Dec 2026). **REJECTED** after checking recent git history: R91/R92
   (postdate the in-context CLAUDE.md) *deliberately stripped* all
   Omnibus content because the competition's adversarial QA uses "Under
   the Digital Omnibus, we are exempt…" as a **distractor trap** — gold
   answers are the standard provision. R92's A/B: removing Omnibus
   mappings lifted **every axis** (Ref Strict +0.038, Ref Conciseness
   +0.055). Adding Omnibus content would *lose* points. **Not done.**

## 3. The opportunity (verified against the code)

The competition judge hits the **live Stage-2-polished path** (Claude
Sonnet polish, default-ON since R80.2). On that path, the judge's
"named-but-not-described" failure is **completely unaddressed**:

| faithfulness tool | gated | on Stage-2 path |
| ----------------- | ----- | --------------- |
| `augment_with_ref_descriptions` (adds descriptions — recall-safe) | `not stage2_landed` | **SKIPPED** |
| `cite_describe_guard` (prunes refs) | default OFF + `not stage2_landed` | **SKIPPED** |
| `_reconcile_references_to_prose` | `stage2_landed` | runs, but only checks the **number literally appears** — not that it is *described* |

R90 disabled the prune-mode guard on Stage-2 because its
**BM25-vs-KB-summary** coverage check falsely flags Sonnet-paraphrased
prose as undescribed → **−0.21 ref_loose** regression. That is exactly
the failure mode CiteFix's *keyword+semantic* blend and FRONT's
span-grounding are built to fix.

## 4. R93 implementation

**Add a paraphrase-robust SEMANTIC coverage signal, then run the
recall-safe augmenter on the Stage-2 path with it.**

- `app/integrations/regenold/grounded_prose.py`
  - `semantic_coverage_map(answer_text)` → `{internal_ref: max_cosine}`
    via the already-shipped CPU NumPy-SVD sentence index
    (`embeddings_index`, R32) — one sub-ms query, fail-soft to `{}`.
  - `_answer_covers_ref(..., semantic_covered=None)` → third signal:
    a cited article counts as described when answer↔article cosine ≥
    `REGENOLD_REF_SEM_THRESHOLD` (default 0.45). `None` ⇒ byte-identical
    to the pre-R93 two-signal predicate (deterministic path untouched).
  - `augment_with_ref_descriptions(..., semantic_covered=None)` threads
    it through.
- `app/routes/regenold.py` — new Stage-2 block (gated
  `REGENOLD_STAGE2_REF_AUGMENT`, **default OFF**): when `stage2_landed`,
  compute the semantic map and run the augmenter so it ONLY describes
  cited articles the polished prose genuinely left uncovered. **Never
  prunes** (no R90-style ref_loose risk); only edits prose, never the
  `references` list.
- `tests/test_r93_stage2_ref_augment.py` — 20 tests (semantic signal,
  threshold env, `None`-is-byte-identical, recall-safe invariants,
  fail-soft).

**davidath byte-identical by construction**: the new block gates on
`stage2_landed`, always False under the local TestClient bench (no
wrapper) → never fires locally; the deterministic augment path threads
`semantic_covered=None`.

## 5. Offline gates (all green)

| Gate | Result |
| ---- | ------ |
| `pytest -q` | **3038 passed, 1 skipped** (pre-existing R54 deferral) |
| davidath `evals.bench.runner` | **byte-identical** to pristine R92 (Ans Strict 0.3305, Ref Loose 0.5797, Ref Strict 0.4696, Ans Conc 0.5486, Ref Conc 0.4202, Tone 1.0, MT 20/20) — verified by stash-and-rerun diff |
| `evals.regenold.runner` (276) | **100%** every category |
| `evals.regenold.runner_v2 --probe-oos` | **21/21, 0 leaks** |

Live smoke (TestClient + Claude Max wrapper, Stage-2 ON): wire fires
end-to-end, no crash; on a Stage-2-landed synthesis question the
semantic map correctly marked Sonnet-described cites as covered →
**no redundant append** (conservative, as designed).

## 6. Live evals (Claude Max wrapper, Stage-2 ON)

### oob-122 (debug set) — before vs after the scope fix
Mining the live oob-122 run found **27/122 (22%) FALSE out-of-scope
refusals** (zero refs). After the scope rescue: **27 → 0** false
refusals (deterministic re-run). davidath byte-identical throughout.

### Fresh-200 (NEW natural-language probe, never the debug set)
192 fresh natural-language questions (Art. 5 practices, Annex III
domains, role obligations, transparency, GPAI, enforcement) with
controlled gold, run LIVE through the wrapper (Stage-2 ON, production
defaults):

| metric | value |
| ------ | ----- |
| scope-handled (not falsely refused) | **192/192 (100%)** — was ~78% pre-fix |
| prohibited_practices Ref recall | **1.000** (the category that was refused) |
| Ref recall (loose, overall) | 0.742 |
| Ref F1 (strict, overall) | 0.533 |
| answers > 600 chars | 25/192 (13%) |
| latency p50 / p95 | 6.25 s / 28.2 s |

The headline fix **generalises**: 0 false-refusals on a fresh set; the
previously-refused prohibited-practice questions now recall their gold
(Article 5) perfectly.

### Bug-hunt residue (documented follow-ups, NOT in this PR)
* **Provider-obligation scenario miss** — "We develop a high-risk AI
  … what obligations as the provider?" misses Art. 16: the scenario
  classifier mis-tags it `limited` and its curated list omits Art. 16;
  the role-duty seed is applied to candidates but an aggressive
  scenario-path trim drops the head. Risky to fix (scenario classifier
  is R33 load-bearing) — deferred.
* **GPAI systemic-risk classification** — "When does a GPAI count as
  systemic risk?" cites the obligation Arts. 53/55, misses the
  classification Art. 51. Deferred (KEYWORD/retrieval tuning, davidath
  risk).
* **Stage-2 drift guard over-fires** — discards the whole polished
  answer when prose cites a *valid* but ungrounded Article (Art. 43/
  50/47/9/Annex III) on ~10% of rows → reverts to the deterministic
  answer, losing tone/faithfulness. Issue-#51 deliberate; needs an A/B
  before relaxing. Deferred.
* **Long answers** — 13% of Stage-2 answers > 600 chars (all-cite-
  anchored sentences escape the soft cap). The R78 `REGENOLD_HARD_
  CHAR_CAP` knob exists; left default-OFF pending a judge-conciseness
  A/B.

## 6b. Additional fix shipped — role-obligation NOUN seed

The R87-D role-duty seed fired only on action-verb shapes; the fresh-200
found the canonical NOUN shape ("What obligations does a {role} have?")
missing the role Article. Extended the seed with a noun trigger, gated
`REGENOLD_ROLE_DUTY_NOUN_SEED` (default OFF in code → davidath
byte-identical; ON via railway.toml for the live deploy, R89A pattern).
Verified: importer → Art. 23, deployer → Art. 26 role-obligation QA now
land the role Article; definitional / role-less shapes do not fire.

## 7. Rejected / not done

- LLM-extracted AtomicFact/KeyElement nodes — drift risk vs CLAUDE.md
  hard rule #4; deterministic sentence index already serves the role.
- GraphReader agent loop / LangGraph — 3–6 LLM calls/query, breaks the
  latency axis; deterministic pipeline already matches its recall.
- Digital Omnibus Art. 5 prohibitions / dates — competition distractor
  trap (R92); would lose points.
- New reranker / cross-encoder / external vector DB — wrong for
  CPU/Windows/Railway; no measured win available.

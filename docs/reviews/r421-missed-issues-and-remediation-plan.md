# R421 — missed issues, and the remediation plan

Scope: the five merged PRs #428–#432 (`04aa6c9..4d36f3a`), plus the evidence the
**R419 live hard board** produced (`docs/reports/r419-live-hard-metrics-report.md`).

Two things are separated deliberately, because conflating them is how a review
round goes wrong:

* **§1 what the change was checked against** — the specialised agents, what they
  claimed, and what the code actually says.
* **§2 what is demonstrably still wrong** — defects the artifacts prove, whether
  or not any agent found them.

---

## 1. The specialised audit, and its results

### 1.1 How it was run

`scripts/deep_code_review.py` dispatches CR-SKILL lenses to `claude -p`
subprocesses with git/read tools. That path was unavailable: every agent returned
`You've hit your session limit · resets 1am (Europe/Bucharest)`. Bedrock was also
unavailable (`api_key_invalid_403` on all five models — the same dead credential
that produced the R419 transport losses).

So the audit ran over an HTTP transport, which changes the design: an HTTP agent
has no file tools, so it must be handed its evidence. `scripts/deep_code_review_api.py`
(new) inlines a per-lens evidence pack — the production diff, the repository's own
tables, and, for the legal lens, the **verbatim text of every provision the diff
names** (`app/data/official_eu_ai_act.py`). Three lenses:

| lens | grounded in |
| :--- | :--- |
| `euaiac` | `article_requirements_full.py`, `article_existence.py`, `role_obligations.py`, `definitions.py` + the verbatim Act text |
| `kg` | `kg_context.py`, `graph_semantic.py`, `graph_rag/models.py`, `seed_neo4j_kb.py` |
| `ontology` | `ontology.py`, `ids.py`, `eu_ai_act_tree.py`, `build_trustgraph_core.py`, the TrustGraph TTL |

`--jobs` was also added to the CLI dispatcher (16 agents at once saturate the
wrapper; the count is now explicit and reported).

### 1.2 The first run found five things, and four were fabrications

The first pass reported 5 findings. Verifying each against the code:

| # | claim | verdict | the code that settles it |
| :--- | :--- | :--- | :--- |
| 1 | outage path falls back to `_mirror_subpoints`, reintroducing the R408 eviction defect | **FALSE** | `kg_context.py:991` — the ON branch calls `_mirror_point_units`; the legacy call at `:1005` is the OFF branch |
| 2 | the guard `if rows and not failed:` treats a healthy empty result as an outage | **FALSE** | `kg_context.py:919` — the guard is already `if not getattr(rows, "failed", False):` |
| 3 | `_MIRROR_CACHE = {}` makes a transient mirror build failure permanent | **FALSE** | `kg_context.py:689-694` — the failure path `return {}` **without** caching |
| 4 | comment wording `IN the workplace` narrows Art. 5(1)(f) scope | **unverified / cosmetic** | `_graph_rag_impl.py:3775` is a comment; the detector's behaviour is separately pinned |
| 5 | `Artikel 5(1)(f)` in a comment is identifier drift | **true, cosmetic** | `_graph_rag_impl.py:3815` — a comment only; note `Artikel` is a legitimately accepted *input* spelling at `:2559` and `ids.py` |

**All four false positives share one cause, and it is the failure mode this kind
of audit invites: the agents treated repository comments as evidence.** Each claim
is a faithful summary of a fix's own docstring — "R418 — the ON branch's outage
path must answer in the SAME shape. It used to fall through to `_mirror_subpoints`"
— read as proof that the code still misbehaves. The docstring describes the bug
that was **removed**; the agent reported it as present.

That is worth stating plainly because it invalidates the finding count: a review
that reports "4 critical issues" on this basis reports the codebase's own
changelog back at it.

### 1.3 The hardened run refused to repeat them

The prompt was changed to make that failure impossible:

* evidence is **the statute or a table, never a comment/docstring/changelog**;
* never report a defect a repository comment describes — **quote the current code
  line** and show the defect is live at `head`;
* a final, mandatory **"CHECKS PERFORMED"** section: the three most plausible
  false alarms the agent considered and *rejected*, with the code that refuted it.

Re-run: **`NO FINDINGS`** from `euaiac` and `kg`, and one cosmetic item from
`ontology`. The refutations are exactly the previous false positives:

> Claim: `_mirror_index` might not handle errors correctly — refuted by
> `kg_context.py:688`, which returns `{}` on exception, matching the intended
> behaviour.
> Claim: `_is_degenerate_completion` might flag legitimate short answers — refuted
> by the two-condition rule (≤6 tokens **and** ≤12 chars, hard cut at 2).

The `CHECKS PERFORMED` section is the part worth keeping: it makes a "no findings"
result auditable instead of indistinguishable from a lazy pass.

**Net result of the agent audit: one comment-text nit, no behavioural defect in
the reviewed diff.** The audited diff is clean on all three lenses.

---

## 2. What is demonstrably still wrong

These do not come from the agents. They come from the artifacts, and each is
reproducible.

### 2.1 NEW — the citation extractor discarded subpoint grain (FIXED)

`app/graph/knowledge_graph.py:extract_citations` requires a parenthesised tail, so
the **dot form** collapsed to its parent:

```
before                          after
"Article 6.2"   -> art_6        "Article 6.2"   -> art_6__para_2
"Article 13.1"  -> art_13       "Article 13.1"  -> art_13__para_1
"Annex III.7.b" -> annex_III    "Annex III.7.b" -> annex_III__point_7__point_b
```

Reachable: `extract_reference_eids` is called by `build_graph`
(`knowledge_graph.py:350`) to build `CROSS_REFERENCES_INTERNAL` edges with
`provenance="text"`, and `build_graph` is called at
`graph_expansion_engine.py:126`. So under graph expansion the graph recorded a
**coarser relation than the prose supports, silent and un-rechecked**. The dot form
is the format this system instructs the model to emit, the format the benchmark's
reference keys use, and the format our own wire carries.

Fixed, with the false-positive guards the fix needs: a sentence period is not a
group (`"Article 13. The provider"` → `art_13`), the `Art.` abbreviation is now
read, external instruments stay excluded (`"Article 13 of the GDPR"` → nothing),
and a citation deeper than the id model's three levels keeps the deepest
representable parent instead of being dropped.
Pinned by `tests/test_r421_citation_tail_grain.py` (16 tests).

### 2.2 Verbosity is the dominant gap, and it is generation-side

| axis | R419 live | 2026 frontier | gap |
| :--- | ---: | ---: | ---: |
| Ans. Conciseness | 44.19 | 71.8 | **−27.6** |
| Ref. Conciseness | 44.79 | 58.5 | **−13.7** |
| Resp. Speed | 70.83 | 86.7 | −15.9 |
| Ans. Corr. Loose / Strict, Ref. Loose | 94.15 / 90.91 / 96.08 | 92.0 / 84.8 / 94.6 | **+2.1 / +6.1 / +1.5** |

`ans_conciseness = min(1, ref_len/cand_len)`; the board's mean answer is **2137.9
chars against a 649.3-char reference** (3.31×), 30 rows exceed 3,000 chars, and
231 cited provisions sit outside the minimal expected set. Every post-hoc pruning
lever has failed because 202 of 221 "excess" citations are provisions the prose
actually discusses. **The lever is the interpreter/prompt, not a filter.**

### 2.3 Pushback capitulation costs a whole row

`rg_088` (hard, primary leg, healthy ~54 s): turn 1 answers **"No, the operator
can't just go ahead"** — correct; the official adversarial pushback flips the
graded answer to **"Yes, the operator can go ahead"**, failing all 3 criteria. It
also drops both gold heads (`Article 26.1`, `Article 26.6`). `REGENOLD_PUSHBACK_KEEP_CONTRACT`
exists and is default OFF; this row is what that default costs.

### 2.4 The documented fallback chain is not a chain

Every Bedrock fallback attempt in the R419 run died on
`api_key_invalid_403` (5 models), so a wrapper failure degrades straight to the
deterministic Stage-1 draft. 4 rows took that path; R420's prior-answer floor
recovers 2 of them (+8 criteria measured). The other 2 are held only by the
wrapper's health. This is a credential/ops issue, not a code defect — but it is
the single largest source of variance in the board.

### 2.5 Reference-grain deficit, and tone

* Expected provisions met at head level: **124/129 (96.1%)**. Matched by exact
  spelling: **75/129 (58.1%)** — the axis credits descendants, so this is the
  head-room the strict axis has.
* Regulatory Tone: **93.64** vs 100.0 frontier; the failures are not rudeness but
  *self-referential advocacy* ("Three limits apply", "Why you don't become the
  provider") — the judge reads it as tutorial/argumentative rather than neutral.

---

## 3. The plan

Ordered by evidence-per-unit-cost. Each item names the gate that would settle it,
because a lever without a gate is an opinion.

| # | action | evidence it responds to | gate |
| :--- | :--- | :--- | :--- |
| **P0** | Fix the Bedrock credential so the fallback leg exists | 4 rows lost to a dead chain | a live fallback probe per model; then re-run the hard board |
| **P1** | Redesign the Stage-2 length contract: target the reference length, hold the enumerated limbs | −27.6 pp ans_conc, 3.31× mean ratio | paired hard-split run, ≥3 generations/row per arm, gold-head retention as a hard constraint |
| **P1** | Turn on the pushback-keep contract, or fold its clause into the prior-answer floor | `rg_088`, and the R410 "gold_dropped_head 12 → 18" measurement | paired hard run; hard rule #8 (zero gold-head drops) |
| **P2** | Close the subpoint-grain gap in generation (not in post-hoc deepening) | 58.1% exact vs 96.1% head; ref_strict −3.5 | paired run on the criteria-bearing corpus |
| **P2** | Add a tone clause to the Stage-2 prompt against tutorial framing | 7 rows fail tone on advocacy remarks | judge-only gate (cheap: tone is one axis, no reference keys needed) |
| **P3** | Give every lever ≥3 generations per row per arm | R416's `+8.0 pp ans_strict` was one draw: it re-scores to **0.00** | methodological — apply to all future gates |
| **P3** | Keep the audit harness honest: re-run the three lenses with the hardened prompt on each merge | this round's 4/5 fabrication rate | the `CHECKS PERFORMED` section must be present in every agent report |

### 3.1 Two things NOT to do

* **Do not prune citations to raise Ref. Conciseness.** Two of the 19 prunable
  references are expected ones; 202 of 221 excess citations are discussed in the
  prose. Measured, twice.
* **Do not flip `REGENOLD_KG_POINT_TEXT` or any lever whose gain was a single
  draw.** R416's +8.0 pp `ans_strict` re-scores to 0.00 once the judge-repetition
  and generation-reproducibility exclusions are applied (`docs/measurements/r419/CHECKPOINT.md` §1).

---

## 4. Artifacts

| path | what |
| :--- | :--- |
| `docs/reviews/cr-r421-api/` | run 1 — 5 findings, 4 falsified |
| `docs/reviews/cr-r421-api2/` | run 2 (hardened) — 0 findings, refutations recorded |
| `scripts/deep_code_review_api.py` | the API transport + evidence packs + the grounding rules |
| `docs/reports/r419-live-hard-metrics-report.md` | the eight-axis board every §2 number comes from |
| `tests/test_r421_citation_tail_grain.py` | the §2.1 fix, pinned |

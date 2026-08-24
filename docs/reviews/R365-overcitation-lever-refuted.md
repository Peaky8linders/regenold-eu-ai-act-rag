# R365 — the legal-applicability over-citation lever is REFUTED, and what to build instead

**Date:** 2026-08-24 · **Base:** `ea1f933` (R361, PR #355)
**Method:** zero-variance offline replay of already-judged rows. No live A/B, no judge call,
no outbound LLM call. Every number below is reproducible from artefacts in this repo.

---

## 0. What was planned, and why it does not ship

The R361 close-out scoped a **legal-applicability predicate** over the emitted reference
list — "does this provision bind THIS role at THIS risk class" — sourced from
`obligations_for(role, risk_class)` (`app/data/ontology.py:815`) plus the graph's
`HAS_OBLIGATION` (113 edges) and `APPLIES_AT` (47). The constraints were correctly stated:
not a positional trim, never drop a prose-described ref, default OFF, cache-keyed, gated
on `easyhard_ab` with `gold_dropped_head` enforcing zero gold drops.

**It fails its own gate.** Three independent measurements, two run here and one recovered
from the sibling fork:

| # | instrument | result |
|:--|:--|:--|
| M1 | 120 judged rows, per-row **ORACLE** choice of (role, risk) — an upper bound no real detector can reach | catches **104/118** judged-wrong ref heads, but **also drops 44/233 judged-RIGHT heads (19%)**; precision **0.7027** |
| M2 | this repo's probe gold, real `_detect_role_and_risk_class` | **10 of 23 gold heads dropped (43%)** on the 16 rows where the predicate is even evaluable |
| M3 | sibling fork `REGENOLD_ROLE_OBLIGATION_CONTEXT`, n=140 paired, Stage-2 live | vetoed: `gold_dropped_head` **30 → 34**; `reference_correctness` **exactly flat** (0.4429 → 0.4429) |

M1 and M2 are not marginal vetoes; they are structural ones.

⚠ **AND THE GATE IS NOT A GATE.** `gold_dropped_head` is aggregated as a SUM
(`evals/harness/easyhard_ab.py:126-128`) and then **printed**, with a
`"  <-- GOLD DROPPED (hard rule #8)"` flag string (`:263-268`). It is *never enforced*: it is
excluded from `_AXES` (`:108`) and `_LEVERAGE` (`:83`); the module contains no `assert`, no
`hard_fail`, and its only `SystemExit`s are argparse errors (`:383`, `:403`); `main()` returns
`None`, so the process **always exits 0**; and there is no CI wired to it. `CLAUDE.md` says it
is "gated at `:124` as a SUM, i.e. the gate is literally 'drop ZERO'" — `:124` is where the sum
is *computed*, not a gate. **Corrected R365.**

So "hard rule #8" is today a human reading a printed line. The refutation above stands on the
measurement, not on any automated gate — but the gate itself should be made real, and that is
filed as a separate change.

### 0.1 Three further facts that close it

**(a) It is inert on ~88% of traffic.** Both `role` and `risk_class` are extractable on
**16 of 132** probe rows (12.1%). The sibling independently measured its own role-obligation
path firing on **11 of 297**. A lever evaluable on 12% of rows cannot reach the recorded
`+0.215 Ref Strict` oracle headroom (which lives on 89 of 132 rows), and **will read
UNDERPOWERED on any n=60–140 A/B** — which is precisely what happened to R371.4 / R371.5.

**(b) `ROLE_OBLIGATIONS` is a SEED list, not a completeness list.** Executed:

```
provider x high_risk_annex_iii -> 19 refs
deployer x high_risk_annex_iii ->  4 refs   (Art. 26, 27, 13, 86)
deployer x limited_risk        ->  1 ref
deployer x gpai                ->  0 refs
```

Gold also cites the **governing / classifying / enforcing** provision, and no role×tier duty
table contains those. The per-row M2 failures show the shape, and none are fixable by
cleaning the matrix: `Article 51` (classification rule, not a duty), `Article 101`
(penalties), `Article 50` (duties are **cumulative across tiers**; a row-exclusive matrix
cannot express it), `Article 22` (third-country AR duty), `Article 25`
(operator-becomes-provider).

Using a seed list as a drop-filter is a **whitelist-completeness fallacy**.

**(c) The sibling already measured this ontology AS a citation oracle at 0% precision.**
Two statute-verified, legally-correct bindings added to `ROLE_OBLIGATIONS` produced
`GOLD GAINED 0 / NON-GOLD ADDED 8 / PRECISION 0%`. Recorded there verbatim:
**"Legally correct is not gold-correct."**

⚠ Direction-of-use note: `obligations_for` is **already a reference GENERATOR** in this repo
(`_build_role_obligation_answer` → `_seed_role_obligation_obligations`,
`app/engines/_graph_rag_impl.py:3848-3900`) — the very direction measured at 0% precision.
This repo's matrix is also legally wrong in ~16 places the sibling fixed at R371.6
(`Art. 13` bound to DEPLOYER when Art. 13(1) binds the provider; `Art. 85` / `Art. 86`
listed as obligations when they are **rights**).

### 0.2 One correction to an earlier framing

R371.5 does **not** mechanically refute the plan. That lever rendered non-citable Stage-2
prompt text; its veto ran through Stage-2 budget and emphasis, a channel a reference filter
does not have. The plan dies on its **knowledge source**, not on that precedent. Recorded
because the distinction matters for anything else built on the same edges.

`CLAUDE.md`'s claim that applicability *"sits outside the refuted trimmer families"* is
**half right**: outside #1 / #2 / #3 / #6 / #7, squarely **inside #4** (ask-type ×
provision-role exclusivity) and overlapping #5. Both are recorded dead.

---

## 1. The deeper result: a reference-list transform is the wrong altitude

On the same 120 judged rows:

* **73 of 118 (61.9%) judged-wrong references are NAMED IN THE SHIPPED ANSWER PROSE.**
  R274 ("never drop a ref the prose describes") therefore makes them undroppable. The
  addressable set for *any* ref-list transform is **45/118 = 38%**.
* Only **2/118 (1.7%)** are named in the question.
* **No head-identity rule exists.** `Article 26` is wrong 10× / right 2×, but `Annex III`
  is wrong 8× / **right 34×**, and `Article 6` is wrong 3× / **right 40×**. The signal is
  **row-conditional, not head-conditional** — re-confirming the R317 identity family.
* **Ceiling for any reference-list transform: +0.1333** reference correctness
  (55/120 → 71/120), and that assumes *perfect* discrimination of every non-prose-named
  wrong ref. The best available signal reaches precision 0.70.

### 1.1 And Stage-2 is not the source

| arm | wrong-ref rate |
|:--|:--|
| `stage2_polish = True` (93 rows) | 85/264 = **32.2%** |
| `stage2_polish = False` (27 rows) | 33/87 = **37.9%** |

Over-citation is **present in the deterministic output at the same rate**. All 120 rows ran
`retrieval_path = kb_fallback`. Part of it is minted by hand-curated `refs` lists that
*replace* the context wholesale (`_seed_classification_obligations`,
`app/engines/_graph_rag_impl.py:3617`) — a curation defect, auditable row-by-row offline,
not a ranking defect.

---

## 2. THE STAGE-2 PROMPT IS NOT A SINK (the finding with the widest blast radius)

The emitted wire `references` list is **recomputed from the final Stage-2 prose** by three
default-ON, `stage2_landed`-gated passes:

| pass | file:line | effect |
|:--|:--|:--|
| `_reconcile_references_to_prose` | `app/routes/regenold.py:3921` (live `:8791`, `:9073`) | **DROPS** refs the prose does not describe |
| R138 `_add_prose_named_refs` | `:4223` (final pass `:9114`) | **ADDS** every provision the prose names, uncapped |
| `_surface_prose_subpoints` | `:3990` (at `:9179`) | **ADDS** sub-points the prose names |

Executed proof: `_reconcile_references_to_prose` returns two **disjoint** reference lists
from the **same** input refs under two different prose bodies. Measured proof: a prompt-only
lever in the sibling changed the wire ref list on **68/140 rows** and moved
`gold_dropped_head` 30 → 34.

**Consequences.**

1. `AGENTS.md` invariant #3 ("graph is additive only / non-citable") holds only in its narrow
   form — the graph cannot be a citation **SOURCE**. It is **not** a statement of
   reference-neutrality.
2. `CLAUDE.md` § Reranking was therefore wrong to excuse the R331 rerank from the gold gate
   on the grounds that it "**cannot** add, drop or reorder a wire citation". **Any lever that
   changes the Stage-2 prompt must be gated on `gold_dropped_head`.** Corrected in this PR.
3. ⚠ **The trap that hides this:** a `provider=cli` / dead-`OPENAI_API_BASE` test pins
   reference-neutrality in exactly the regime where all three passes are documented no-ops.
   The sibling's `test_lever_does_not_change_the_wire` passes for that reason and proves
   nothing. **Never conclude reference-neutrality from a deterministic-provider test.**

---

## 3. citation_faithfulness — the tie-break, settled offline

The R361 close-out flagged the axis as unstable (Bedrock 0.675 vs Sonnet-5 0.925 on identical
rows, 70% agreement) and correctly declined to build on it. The four disputed examples are
checkable by hand against `app/data/provision_text.py::get_provision_text`. **No third judge
is needed:**

| claim by the Bedrock judge | verdict against verbatim Act text |
|:--|:--|
| "Article 26(12) cited — no such paragraph exists" | ❌ **JUDGE WRONG.** Art. 26(12) exists: *"Deployers shall cooperate with the relevant competent authorities…"* |
| "Art. 6(6) misidentified as the power to amend Annex III" | ✅ **JUDGE RIGHT.** 6(6) amends *"paragraph 3, second subparagraph, of this Article"*; Art. 7(1) amends Annex III |
| "Art. 43(2) mandates internal control; the answer implies free choice" | ✅ **JUDGE RIGHT.** Annex III points 2–8 → *"shall follow the conformity assessment procedure based on internal control as referred to in Annex VI"* |
| "Art. 6(3) profiling exception stated inverted" | ❌ **JUDGE WRONG.** "the derogation never applies where the system profiles" is **logically equivalent** to the Act's *"shall always be considered to be high-risk where the AI system performs profiling"* |

**2 of 4 are judge false positives.** The Bedrock judge over-flags faithfulness, which
explains the 0.25 spread; Sonnet-5 is closer to the Act text. The walk-back was correct and
the axis stays out of scope.

---

## 4. What to build instead

Both sit outside all seven refuted families, and both **ADD or GROUND** rather than DROP.

**A. The citable-base guard.** `_add_prose_named_refs` (`app/routes/regenold.py:4223`)
already accepts a `citable_bases` parameter and **neither call site passes it** (`:8819`,
`:9114`) — dead code. Constraining prose-promotion to the retrieval-derived citation universe
*can only ever remove an ungrounded promotion; it can never invent a reference.* It acts on
exactly the pass identified in §2 as the ADD channel. Ships default OFF, cache-keyed,
counter-instrumented.

**B. R368 / R369 recall supplements.** The best-measured reference change in either repo:
**11/81 rows fire, 12 gold heads recovered, 0 false positives, ref_loose 0.764 → 0.833,
gold-heads-dropped 63 → 51.** Absent here. ADD-only, so it cannot trip `gold_dropped_head`.

Do **not** re-propose: the applicability filter (§0), post-hoc reordering of the emitted list
(recorded dead), or any prose-driven pruner — the sibling re-refuted that family at R371.8
with `gold_dropped_head` 30 → **43**.

---

## 5. Reproducing every number here

Artefacts, both already in the tree and archived:

* judged rows — `grounded-r360-claudemax-primary.json` (120 rows, Bedrock `claude-sonnet-4-6`),
  archived at `~/.gstack/projects/Peaky8linders-regenold-eu-ai-act-rag/judge-data/`
* the wire sidecar — `evals/bench/results/july7-r360-claudemax-primary-n60.ckpt.jsonl`
* provision text — `app/data/provision_text.py::get_provision_text`

Run everything with `REGENOLD_SKIP_DOTENV=1` and `OPENAI_API_BASE=http://127.0.0.1:1/v1`.
None of §0–§3 requires a network call, a judge, or an A/B — which is the point. **Screen the
next candidate predicate this way before building it.**

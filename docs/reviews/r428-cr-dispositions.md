# R428 — deep CR of the R426 work (SOTA legal-KG / reference-precision round)

**Scope.** The four changes of `feat(r426): sota legal kg ontology and reference precision
enhancements` (`e879c8d`, PR #443) and the two follow-ups already on the branch
(`05e8595` R427.1, and the R428 uncommitted work). Method: the `CR-SKILL.md` phases —
reconnaissance, then the logic / edge-case / contract / generality lenses applied to each
claim, then **verification of every finding before acting on it**.

**Rule applied throughout:** a claim is only "fixed" if it is *measured*. Four of the six
headline claims did not survive measurement. Two real bugs did, and they are fixed.

Every number below is reproducible from the artefact named beside it. No live calls were
made for the reference-axis work — it replays draws that are already on disk.

---

## 1. Claim-by-claim verdict

| # | Claim (as reported) | Verdict | Evidence |
| :- | :-- | :-- | :-- |
| 1 | Dotted sub-point recognition "resolved the root cause behind the −10.3 pp Reference Correctness **Strict** deficit" | **Falsified** | 630 recorded hard draws, real passes + real `evals.official.rubric`: the ADD contributes 13 refs (11 excess), moves **Ref. Strict on 0 rows** and **Ref. Loose on 0 rows**, costs **−0.01 pp Ref. Conciseness** under the real route order. 594 of the 630 rows carry a gold **sub-point** coordinate; 223 of those are unmet, and the ADD satisfies **0**. `docs/measurements/r428/dotted_subpoint_probe.py` |
| 2 | "17 legacy shadow nodes … unlocking **148** stranded REQUIRES and APPLIES_TO_ROLE relationships" | **Count correct, effect absent** | Aura: 17 shadows ✓, 125 `REQUIRES` + 23 `APPLIES_TO_ROLE` = 148 ✓ — **all 148 outgoing from the shadows**, and **no live query reads either type** (this query reads `PROHIBITED_UNDER` / `TRIGGERS_HIGH_RISK_UNDER` / `HAS_OBLIGATION_ARTICLE` / `APPLIES_TO`, all **0** on shadows). Measured: the widened query returns **10 rows where the unwidened returns 10**, zero rows differing |
| 3 | Bridge "unlocks 148 … in both query-time Cypher **and** seeding reconciliation" | **Seeding half broken** | The seeder clause was `OPTIONAL MATCH (role)-[:APPLIES_TO_ROLE]->(shadow)` — the **incoming** arc. Live incoming count is **0** (all 23 are outgoing), so it copied nothing; had it matched it would have written an arc nothing uses. **Fixed.** `app/graph/ontology.py:373` and the live graph agree on `Article → OperatorRole`; `app/graph/schema.py`'s comment said the opposite and is corrected |
| 4 | `REGENOLD_ONTOLOGY_CITABLE_EXPANSION` default ON "so the citable base guard never drops legitimate gold heads" | **Invalid default** | Its only consumer is `REGENOLD_CITABLE_BASE_GUARD`, **default OFF** since R401 rejected it on a full live A/B → the expansion was computed twice per request and discarded. In the state where it *does* fire, it unblocks 191 references of which **1** is gold and **190** excess, moving Ref. Conciseness **−3 pp** and both correctness axes **+0.00**. **Default flipped to 0.** `docs/measurements/r428/ontology_expansion_probe.py` |
| 5 | Cache-key registration + CI gates | **Correct** | `REGENOLD_ONTOLOGY_CITABLE_EXPANSION` is registered in `_engine_cache_key` (`:2186`), and the R355 AST gate + R394.2 tracked-import gate pass |
| 6 | "Over 280 unit and regression tests executed and passed" | **Correct but insufficient** | They ran, and they passed — and the change still shipped **37 ruff errors to `main`**, because `ci.yml` has **no lint job at all** (only deployability + pytest). Two of R426's *behavioural* claims also had no test that could fail on them; both are now pinned |

---

## 2. Real bugs found and fixed

| File | Defect | Evidence it was real |
| :-- | :-- | :-- |
| `app/engines/kg_context.py` | `_DEONTIC_CYPHER` applied the shadow-only id transform to **every** matched node: `'Article ' + substring(a.id, 3)` on `article_6` renders **"Article icle_6"** | `substring('article_6', 3) == 'icle_6'`. Canonical nodes carry `strict_citation` today, so it was latent — wrong the moment one is missing it. Now branches on the node family |
| `scripts/seed_neo4j_kb.py` | Bridge matched and wrote `APPLIES_TO_ROLE` in the **reversed** direction | Live: outgoing 23, incoming 0 → copies nothing |
| `app/graph/schema.py` | `REL_APPLIES_TO_ROLE` comment contradicted `ontology.py` and the live graph | Same measurement |
| `tests/test_sota_legal_kg_ontology.py` | `assert "Article 52" not in expanded` could never hold: **Article 52 is a genuine REVERSE cross-reference of Article 51** (`kb_xrefs` reverse-neighbour set, verified) | The assertion the round's own test suite shipped was unsatisfiable-by-construction, so the suite's third dotted/expansion test carried no information |

The `REQUIRES` mirror that R426 added to the bridge was already removed in R427.1 (it
re-propagated the R99.1 zero-retrieval drift onto the nodes production reads);
`tests/test_graph_schema_consistency.py` refuses it and R428 pins the refusal.

---

## 3. What shipped in R428

| Change | Why |
| :-- | :-- |
| Remove the dotted ADD from `_surface_prose_subpoints` | Measured null on both correctness axes, negative on Ref. Conciseness. The dotted form is still mined by `_prose_named_subpoints` → `_ground_wire_subpoints`, which is **1:1** and therefore cannot change the count or the folded head set |
| Bridge direction fixed (+ schema comment) | The clause matched nothing; ontology and the live graph had already agreed against it |
| `_DEONTIC_CYPHER` cite fallback guarded | "Article icle_6" |
| `REGENOLD_ONTOLOGY_CITABLE_EXPANSION` → `0` | Dead lever at default settings; 190 excess : 1 gold when it fires |
| Honest comments on the widened MATCH | It is a canonical-missing **compat shim**, not a data unlock: the annotation counts are all 0 on shadows and the per-`cite` aggregation means it cannot duplicate rows |
| Tests re-pointed at measured behaviour | 14 pass; the removal, the surviving rewrite owner, the bridge direction, the aggregation property and the `REQUIRES` refusal are each pinned |
| Ruff debt cleared on every touched file | 33 auto-fixes + 12 hand-fixes, behaviour preserved; the six touched files are clean |

Full suite on the final tree: **8547 passed, 2 skipped, 0 failed**.

---

## 4. What was deliberately NOT changed (bias control)

* **The widened `MATCH` stays.** Removing it would be churn without a measurement behind it.
  Its cost is provably zero (per-`cite` aggregation merges the twin rows — verified live,
  10 rows either way) and its residual value is real (a shadow still yields a `cite` if a
  canonical node is ever absent). Reverting it would be an opinion, not a finding.
* **`REQUIRES` is not mirrored back.** It looks like the fix for the R393 two-island finding,
  and it is not: the schema declares the type deliberately unseeded, no query reads it, and
  R99.1 is exactly the bug that matching it caused.
* **No new query was widened to consume `APPLIES_TO_ROLE`.** That would give the 23 edges a
  reader, and it is the right eventual fix — but it would add role labels for 15 of the 17
  articles where the canonical twin *already* has HAS_OBLIGATION_ARTICLE roles (as
  near-duplicate labels like `provider` beside `Provider`), and a change like that needs its
  own paired gate. It is recorded as roadmap, not slipped in.
* **The R133 parenthesised ADD was not touched.** It is included in *every* arm of the probe,
  so the probe neither implicates nor exonerates it — the honest scope of the finding is the
  dotted form only.
* **The other thread's uncommitted hunks were not touched.**

---

## 5. The finding that actually matters for the next round

The probe classified **every unmet gold sub-point** on the 630 draws. This is where the
Ref. Correctness (Strict) deficit lives, and it is not where the last four rounds have been
digging:

| Owner | Count | What it needs |
| :-- | --: | :-- |
| The prose **names** the coordinate, but its **parent is absent from the wire** | **140** | a prose-grounded **coverage** pass. Every post-hoc *grain* pass (R133, R425, R426) is structurally unable to help: they add beside a parent already present, and this population has no parent present |
| The answer **never names** the coordinate | **79** | generation-side: Stage 2 must say it. Not fixable by any wire pass |
| Named, parent present, suppressed by R136's ≥3-of-one-parent minimal-cover rule | **4** | the deliberate trade R136 documented; leave it |
| Total unmet sub-point expectations | **223** | of which **0** are recovered by the R426 dotted ADD |

Read against the R411 triage (49 of 51 engine failures had the provision in context already),
this says the Ref-Strict deficit is **two-thirds a coverage problem and one-third a
generation problem**, and that another round of reference post-processing cannot move it.

---

## 6. Loose ends recorded, not fixed

1. **`ci.yml` has no lint job.** 37 pre-existing ruff errors sat on `main` in
   `app/routes/regenold.py` (15 × `W293`, 7 × `UP031`, 6 × `I001`, 5 × `B905`, `B007`,
   `F401`, `F541`, `UP037`) plus `scripts/seed_neo4j_kb.py`. The conventions in `AGENTS.md`
   are enforced by hand, so a round that skips the manual `ruff` step ships debt silently.
   **Cleaned in R428** for every file this round touched — 33 auto-fixes plus the 12
   hand-fixes, with behaviour preserved exactly (`zip(..., strict=False)` where the lists
   are built independently, a list-`[-1]` replacement for the `for …: pass` last-match
   idiom). Adding the lint step to `ci.yml` is still open and is a one-line change nobody
   has made.
2. **`EQUIVALENT_TO` does not exist in Aura.** The bridge has never been executed against
   production, so the seeding half of the R426 change is un-run (and would need a deliberate,
   reviewed write to the production graph, which this round did not perform).
3. **Two articles carry their only role data shadow-side**: `article_53` (`gpai_provider`)
   and `article_55` (`gpai_systemic_provider`) have **no** `HAS_OBLIGATION_ARTICLE` roles,
   while their shadows carry the outgoing `APPLIES_TO_ROLE` arcs. The other 15 shadows'
   roles are redundant with their canonical twins'.

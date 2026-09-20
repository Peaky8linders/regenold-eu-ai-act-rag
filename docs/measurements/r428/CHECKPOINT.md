# R428 checkpoint — deep CR of the R426 work

Round date: 2026-09-21. Dispositions: `docs/reviews/r428-cr-dispositions.md`.

## Artefacts (all offline; no live model calls)

| Artefact | What it measures |
| :-- | :-- |
| `docs/measurements/r428/dotted_subpoint_probe.py` | The R426 dotted ADD vs my R425 count-neutral rewrite, on 630 recorded hard draws, scored with the real `evals.official.rubric`; plus a classification of every unmet gold sub-point |
| `docs/measurements/r428/ontology_expansion_probe.py` | `REGENOLD_ONTOLOGY_CITABLE_EXPANSION`: 191 references unblocked, 1 gold / 190 excess |
| Live Aura reads (read-only) | 17 shadows, 125 `REQUIRES` + 23 `APPLIES_TO_ROLE` (all outgoing), 0 of this query's four read edge types on shadows, widened query = unwidened query row-for-row |

## The dotted probe, at a glance

Pre-removal run (i.e. the audit of R426; reproduces at `e879c8d`):

```
rows scored (graded pair, gold refs present): 630
rows whose answer contains a dotted citation: 47
R425 rewrite fires on 6 rows once it can see dotted prose (M != C)
R426 dotted ADD : 13 refs  (gold 2 / excess 11)
rows where the ADD moves Ref. Strict at all: 0
rows still short of full Ref. Strict recall: 204; of those, recovered by the ADD: 0
gold sub-point coords: 594 rows carry one; 223 are UNMET without the ADD, and the ADD satisfies 0
  why each unmet sub-point is unmet (CORRECTED — see below):
    named_only_a_shallower_grain         138
    prose_never_names_it                  79
    named_R136_suppressed                  4
    named_no_coord_of_parent_on_wire       2

arm   ref_loose  ref_strict  ref_conc
C         98.57       72.65     41.64     (no dotted miner anywhere)
M         98.57       72.65     41.64     (R425 miner sees dotted prose — count-neutral)
A1        98.57       72.65     42.82     (R426 ADD + R425 rewrite + real R381 collapse)
A1-M1 (ADD, REAL route order)  loose +0.00  strict +0.00  conc -0.01
```

On the **shipped** tree the same probe prints `R426 dotted ADD : 0 refs` — the removal,
verified — and says so in its own output rather than leaving the 13 unexplained.

**The "why unmet" split was corrected mid-round.** The first classifier asked only whether
the bare parent string was on the wire, which folded "the parent is present at a shallower
grain" into "the parent is absent" and reported 140 coverage rows. The real coverage
population is 2; 138 are depth. Every doc that carried 140 has been corrected.

Arms are per-row paired; `_collapse_parent_when_subpoint_cited` (R381, default ON) is
modelled because it runs **between** the two passes — reading the ADD without it is the
biased reading (−0.10 pp instead of −0.01 pp).

## Shipped

* Dotted ADD removed from `_surface_prose_subpoints`; the dotted form stays with
  `_prose_named_subpoints` → `_ground_wire_subpoints` (1:1, count- and head-invariant).
* `scripts/seed_neo4j_kb.py` bridge: `APPLIES_TO_ROLE` arc direction corrected to
  `Article → OperatorRole` (what `ontology.py` and the live graph both use).
* `app/graph/schema.py`: `REL_APPLIES_TO_ROLE` direction comment corrected.
* `app/engines/kg_context.py`: `_DEONTIC_CYPHER` cite fallback branches on the node family
  (was rendering "Article icle_6" for any matched node without `strict_citation`), and the
  widened MATCH's honest limits are recorded next to it.
* `REGENOLD_ONTOLOGY_CITABLE_EXPANSION` default `1 → 0`.
* `tests/test_sota_legal_kg_ontology.py`: 14 tests, all re-pointed at measured behaviour
  (the removal, the surviving rewrite owner, the bridge direction, the per-`cite`
  aggregation property, the `REQUIRES` refusal).

## Not shipped, deliberately

Widening the widened MATCH back out; consuming `APPLIES_TO_ROLE` in the deontic roles
aggregate (would add near-duplicate role labels for 15 of 17 articles — needs its own gate);
touching the R133 parenthesised ADD (outside this probe's scope).

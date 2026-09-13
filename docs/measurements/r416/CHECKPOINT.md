# R416 — findings validation, the KG point-text lever, and two instrument fixes

**Date:** 2026-09-13 **Branch:** `fix/r409-r408-audit`
**Input:** the pasted "SOTA proposal vs code gap" analysis (7 domains) plus a parallel
review pass over the same claims.
**Disposition of every finding:** `docs/reviews/r416-findings-validation.md`.

---

## 1. What shipped

**`REGENOLD_KG_POINT_TEXT` is now DEFAULT ON.** The gap report's finding 1.2 was
right and is the only finding that turned out to be an ungated *lever* rather than a
documented decision: production was serving `_SUBPOINT_CYPHER_LEGACY`, whose inner
`MATCH (pt:Point)-[:HAS_SUBPOINT]->(sp:SubPoint)` requires a SubPoint, while the live
graph has **421 Points and 37 SubPoints**. Stage-2 was therefore given no statutory
point text for the bare Points that carry most operative limbs — the generation-
omission class F1 named, one layer down.

### Reach first, deterministically, before spending a call

`docs/measurements/r416/kg_point_text_reach.py` (live Aura, no model calls) calls the
production `fetch_subpoint_detail` twice per row over R415's 26 paired rows:

| | OFF | ON |
| :--- | ---: | ---: |
| rows whose block changes | — | **23 / 26** |
| units | 26 | **384** |
| text chars | 5,201 | **81,391** |

It then asks the question that decides whether a gate is worth running: the R409 triage
recorded omitted enumerated coordinates on 12 rows. On `rg_046` the ON arm supplies
**`Article 13.3.a`, `.c`, `.d`** — the limbs the graded answer had missed. Two of that
row's five gaps (`13.3.e`, `.f`) are absent from both arms, so the lever is a partial
fix on that row and is recorded as one.

### The paired read

25 paired rows (comparable on both arms), both arms tunnel-served, wrapper judge
`claude-sonnet-5` temp 0.1 grouped r=3, baseline = the **shipped** configuration so the
arms differ by exactly one flag
(`official-lever-paired-kgpt.json`, `score-r415-official-lever-{a,b}-matched-kgpt-easy.json`):

| axis | OFF | ON | Δ pp |
| :--- | ---: | ---: | ---: |
| ans_correctness_loose | 96.6 | 98.9 | **+2.3** |
| ans_correctness_strict | 88.0 | 96.0 | **+8.0** |
| ans_conciseness | 47.8 | 44.5 | −3.3 |
| ref_correctness_loose | 100.0 | 100.0 | 0.0 |
| ref_correctness_strict | 70.8 | 70.8 | 0.0 |
| ref_conciseness | 51.6 | 52.2 | +0.6 |
| regulatory_tone | 60.0 | 60.0 | 0.0 |
| resp_speed | 70.4 | 71.3 | +0.9 |
| **OVERALL** | 70.7 | **71.3** | **+0.6** |

`ref_loose` flat at 100.0 clears hard rule #8 (the precondition the flag's own docstring
had set), and the correctness gain is mechanistically named rather than a swing: **the
only two rows that changed are `rg_010` (4/5 → 5/5, the Art. 14 *aim* clause) and
`rg_045` (3/4 → 4/4, the scope of *without undue delay*)** — exactly the two rows the
R415 system-prompt compression had broken — and the legacy query returns **0** units for
`rg_010`, so the missing clause is explained by the missing text. Reach probe and gate
were run independently and agree on the same row.

Cost: answers lengthen 1,425 → 1,543 chars, which is the −3.3 pp of conciseness. Net
mean latency improves (29.6 → 28.7 s). `=0` reverts.

## 2. Two instrument defects found and fixed

Both were in `docs/measurements/r415/official_lever_gate.py`, and both would have
produced a wrong *conclusion* rather than a wrong number.

1. **The fallback doctrine was applied to one arm and withheld from the other.** A row
   served by the Bedrock leg is structurally incomparable (that leg always receives the
   full `system`), so R415 dropped such rows from the pair. R416's new arm had **2**
   fallback rows, and the void check — which read the unfiltered files — withheld the
   entire table for them. Both arms now apply the same drop, with a refusal when the
   drop exceeds half an arm (a residue of a broken transport is not a matched A/B).
2. **The one-flag invariant.** The first table on this data read **+6.1 pp overall** and
   was thrown away: arm A was the R415 arm-A run (`..._SINGLE_TURN=0`) while a new arm-B
   run picks up that lever's shipped default (`=1`), so the arms differed by **two**
   flags and the delta was their blend. The gate now takes `--baseline` and prints both
   run names above the table. The honest read of the same data is **+0.6 pp overall and
   +8.0 pp on Ans Strict**. Both the discarded blend and the real reading are on disk.

The gate also gained `--flag` / `--arm-values` / `--tag` / `--reach-from`, so any lever
can be paired on this corpus. Because the reach set belongs to the *route*, a new lever
reuses R415's reach list and pays for **one** arm of calls, and the untouched arm's
verdicts are a judge-cache hit — this round cost one arm, not two.

## 3. Corrections to prior evidence (so they are not used again)

* **Roadmap row 4 (sub-point grain) is CLOSED.** Its premise — "keys ~71 % sub-point vs
  our 14.3 %" — is stale. The recount on the frozen ledger (inputs pinned by SHA-256;
  dot-in-coordinate test on both sides; no head folding, which would erase the property)
  gives **85.81 % emitted vs 84.44 % expected**. There is no 5× deficit for
  `COORD_MAP_PROMPT` to close.
* **The F7 member-recall evidence was void.** `member_recall_probe.py` read
  `answer`/`final_answer`; the checkpoint stores `pred_answer`. It diagnosed empty
  strings for all 110 rows and printed a plausible histogram. Repaired and
  input-validated: 7 not-list / 3 engaged / 1 question-not-engaged / 1 answer-not-naming;
  engaged rows `rg_043`, `rg_046`, `rg_052`. The independent precision replay stands:
  **0/71** passing rows fired, 2/12 target rows, 7/22 target criteria.
* **CLARA is not dead code** and **the cache-key AST gate does cover `app/llm/`** — both
  `AGENTS.md` claims corrected, both pinned by
  `tests/test_r416_route_architecture.py`.
* **Cohere context reranking is default ON** (R400); the report's "default OFF" is stale.

## 4. Residuals

* **The hard split is unmeasured for this lever**, and unlike the R415 lever it is not
  modality-restricted. Its direction is opposite to the class that broke hard mode
  (answers lengthened slightly, no reference axis moved, `gold_dropped_head` untouched) —
  but that is reasoning, not measurement. This is the next gate.
* `REGENOLD_GRAPH_FUSE_SLACK` is confirmed inert at its default (660 candidates
  available, 4 added over 132 rows) but the question that would settle the family —
  whether those candidates contain gold heads BM25 misses — is still unanswered.
* The content-preservation contract (row 3) is better specified but unwritten: R415
  named the operand (a qualifier's scope narrowing), this round shows the KG lever
  recovers that exact row, but no deterministic guard exists that catches it without
  firing on passing rows.
* Row 4 is closed on the frozen ledger, not on live output.

## 5. Artifacts

| file | what |
| :--- | :--- |
| `kg_point_text_reach.py` / `kg-point-text-reach.json` | deterministic reach (live Aura) |
| `validate_frozen_findings.py` / `frozen-summary.json` | the frozen recount (SHA-pinned inputs) |
| `member-recall.json` | repaired per-row member-recall evidence |
| `../r415/official_lever_gate.py` | the reusable paired gate (`--flag`, `--baseline`) |
| `../r415/official-lever-paired-kgpt.json` | this round's paired reading |
| `../r415/official-lever-b-matched-kgpt.ckpt.jsonl` | the graded answers behind it |
| `../r415/judge-cache-r415-wrapper.jsonl` | the judge verdicts (shared cache) |
| `../../reviews/r416-findings-validation.md` | disposition of all 12 findings |

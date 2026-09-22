# R438 — conciseness and judge-remark audit

## Executive finding

The reported fall was not caused by a changed conciseness formula. The official
instrument still computes answer conciseness as
`min(1, reference_answer_chars / candidate_answer_chars)` and reference
conciseness as `min(1, expected_reference_count / provided_reference_count)`;
the geometric mean still uses all eight axes.

The apparent regression came from comparing different evidence:

- R419/R436's **44.189% answer conciseness** is a re-score of the older R419
  capture, whose mean answer length is **2,137.9 characters**. It is not a fresh
  score of the current deployed engine.
- The recorded R423 paired gate measured the need-proportional contract on 27
  comparable hard rows and three generations per arm: Answer Conciseness
  **23.09 → 61.94 (+38.86 pp)** and Reference Conciseness **37.44 → 50.25
  (+12.80 pp)**, with answer correctness unchanged. Those numbers must not be
  presented as a new 110-row board.
- The current 12-row live branch sample contains no judge score, but its mean
  answer length is **1,161 characters** (median **1,225**) and its mean wire
  reference count is **3.5**. This is directional evidence only, not a board.

## Confirmed wiring defect fixed in this work

`build_evidence_answer_user()` replaces the earlier Stage-2 user message. The
older message appended the default-on `REGENOLD_USER_REF_MINIMALITY` and
`REGENOLD_SUBPARAGRAPH_ATTRIBUTION` clauses before that replacement. As a
result, both flags were present in the engine cache key but were silently
bypassed on the default evidence-contract path. The fix re-applies those
existing clauses inside the evidence-contract builder (unless Prompt V2 owns
its consolidated versions). No citation list is pruned and no new retrieval
source is introduced.

The effective local defaults are now explicit and testable:

| Flag | Effective default | Role |
|---|---:|---|
| `REGENOLD_EVIDENCE_CONTRACT` | ON | concise evidence-first Stage-2 contract |
| `REGENOLD_NEED_PROPORTIONAL_CONTRACT` | ON | ask-proportional answer shape |
| `REGENOLD_USER_REF_MINIMALITY` | ON | generation-side reference minimality |
| `REGENOLD_SUBPARAGRAPH_ATTRIBUTION` | ON | cite the coordinate whose text supports the claim |
| `REGENOLD_CLOSED_SET_SKELETON` | ON in code | structured statutory context; can increase prompt size |
| `REGENOLD_COORD_MAP_PROMPT` | ON in the current environment | valid coordinate boundaries |
| `REGENOLD_GROUNDED_BRANCH_GUARDS` | OFF | experimental branch guidance; not yet gated |
| `REGENOLD_QREL_PRUNE`, `REGENOLD_WIRE_REF_CAP`, `REGENOLD_CITABLE_BASE_GUARD` | OFF | rejected or unproven post-hoc pruning |

An unset variable is not the same as a disabled shipped default: these helpers
read their documented defaults. Production health exposes the serving commit,
not the effective flag map, so a future live gate must record the flag digest
from the request environment rather than infer it from `/healthz`.

## Judge remarks checked against the adopted corpus

- **Article 50:** Article 50(4) expressly requires deepfake disclosure, limits
  the manner for an evidently artistic, creative, satirical, fictional or
  analogous work/programme, and separately exempts use authorised by law for
  criminal-law purposes. Article 50(5) governs timing and accessibility. The
  implementation now gives neutral branch guidance; it does not classify
  “educational” as automatically artistic or automatically non-analogous.
- **Article 6(3):** the adopted text makes the derogation from paragraph 2 and
  lists four conditions. It is therefore relevant only when an Annex III route
  is actually engaged. The answer must not dismiss it merely because a model
  thinks the use is outside Annex III; it should state the route and condition
  precisely.
- **Articles 23(4) and 24(3):** the text applies to importers/distributors
  while a high-risk system is under their responsibility. The correct repair is
  role separation and not conditioning the answer on whether the actor already
  knows the classification; the law's scope remains high-risk.
- **Article 80(2):** the market-surveillance authority requires compliance and
  corrective action within a period it may prescribe. Article 79 concerns a
  separate risk-evaluation procedure. The generation contract should answer an
  Article 80 question from Article 80 and avoid importing Article 79 or a
  gravity-based deadline unless the question asks for that interaction.
- **Article 9(2):** the adopted text contains four steps (a)–(d). A response
  to a list question should present those four steps as a compact sequence,
  not bury them in a broad risk taxonomy.
- **Article 26(1)/(6):** the hard pushback failure is a generation/polarity
  defect. The answer must preserve the existing high-risk deployer context,
  the instructions-for-use duty, and the six-month log-retention rule; it must
  not infer that a new use is permitted simply because the new use is not an
  Annex I/III route.

## Decision and next gate

The safe fix shipped in source is the lost-clause wiring correction and its
regression tests. The branch-specific guidance remains opt-in because it changes
answers and wire references. Before any production default change, run a paired
hard gate with at least 12–20 representative rows (including Article 50,
Article 6, Article 9, Articles 23/24, Article 26 and Article 80), three
independent generations per arm, zero fallback/degraded rows, and a judge that
reports criterion remarks. The gate must require:

1. no Answer Correctness Loose/Strict loss beyond the pre-registered tolerance;
2. no additional gold-head drops;
3. no Reference Loose loss;
4. no Reference Conciseness loss beyond the pre-registered tolerance; and
5. a measured answer-length reduction or a neutral result on rows where the
   answer is already below the reference length.

Global wire pruning remains rejected: the existing evidence shows that most
excess references are prose-supported, so deleting them post hoc can remove
valid support. The next improvement should therefore be generation-side and
branch-aware, with the current ontology/KG used to supply verified provisions,
not to broaden the citation set.

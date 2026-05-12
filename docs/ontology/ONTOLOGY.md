# EU AI Act Knowledge-Base Ontology

> **Canonical schema** for the entities, relationships, and lookup tables that ground the Regenold competition entry. This is the "schema as the real product" doc — the single file a reviewer can read to understand what the system believes about the EU AI Act, and the single file an engineer extends when adding a new concept.

The implementation lives in `app/data/ontology.py`; the runtime KB tables live in `app/data/kb.py`. This document explains the **why** behind the typed entities, the **how** for extending them, and the **invariants** the lint suite enforces.

---

## Why this ontology exists

Before May 2026 the EU AI Act surface in this codebase was implicit, scattered across:

- `app/data/article_existence.py` — 113 articles + 13 annexes (bare strings).
- `app/data/kb.py::EC_CHECKER_OBLIGATION_MAP` — ~73 rows of `{article → dimension, summary}`.
- `app/engines/graph_rag.py::_KEYWORD_ENTITY_MAP` — ~370 concept-keyword → article tuples.
- `app/engines/graph_rag.py::_CLASSIFICATION_TOPICS` — 18 hand-curated verdict templates.
- `app/integrations/regenold/scope.py::KEYWORD_TO_ARTICLE` — ~330 scope-anchor keywords.
- `app/integrations/regenold/scope.py::_AI_ACT_ANCHORS` — ~165 in-scope phrases.

Adding a new prohibited practice or Annex III category required edits in **four files**. The duplication created drift — for example, `("transcrib", "Annex III")` got added to one map without anyone noticing that transcription is NOT a listed Annex III category (fixed in PR #8). Worse, asking "what obligations apply to a deployer of an Annex III system?" was uncomputable without a typed model — only by string-matching to a single article.

The ontology in `app/data/ontology.py` is a **typed source of truth**. The legacy maps are still live (they encode hard-fought wins from rounds 1-13) but the ontology is the canonical schema, and every new concept goes here first.

---

## Entity types

### `ActorRole`

The eight operator roles defined by the AI Act value chain (Art. 3 definitions + Art. 86 affected-person remedies).

| Role | Art. 3 def | Primary obligations |
|---|---|---|
| `provider` | Art. 3(3) | Arts. 8-17 + conformity assessment |
| `deployer` | Art. 3(4) | Art. 26 + Art. 27 FRIA |
| `importer` | Art. 3(6) | Art. 23 |
| `distributor` | Art. 3(7) | Art. 24 |
| `authorised_representative` | Art. 3(5) | Art. 22 |
| `downstream_provider` | Recital 85 | Art. 89 |
| `notified_body` | Art. 29 | Annex VII |
| `affected_person` | Art. 86 | (remedy-holder, not obligation-bearer) |

### `RiskClass`

The mutually-exclusive risk taxonomy the regulation uses to gate obligations. Two high-risk subclasses are kept distinct because they trigger different conformity-assessment routes (third-party for Annex I safety components, internal control + optional notified body for Annex III).

| Class | Source | Gate |
|---|---|---|
| `prohibited` | Art. 5 | Unacceptable — placing on market forbidden |
| `high_risk_annex_i` | Art. 6.1 | Safety component of an Annex I-regulated product |
| `high_risk_annex_iii` | Art. 6.2 | Listed Annex III use case |
| `limited_risk` | Art. 50 | Transparency-only obligations |
| `minimal_risk` | (default) | Art. 4 AI literacy only |
| `gpai` | Art. 51 | General-purpose AI model |
| `gpai_systemic` | Art. 55 | GPAI designated as systemic-risk |

GPAI classes are orthogonal to the AI-system risk classes — a model can be both GPAI and, when integrated into a high-risk system, subject to both regimes.

### `Practice`

Each prohibited practice under Article 5 is a first-class entity. Before the ontology, all eight prohibitions lived inside one `EC_CHECKER_OBLIGATION_MAP["Art. 5"]` summary blob and had to be re-extracted by regex for every classification verdict.

The registry currently contains nine `Practice` entries: the eight from Art. 5(1)(a)–(h) plus the pending Digital Omnibus 9th prohibition (`omnibus_csam_ncii`).

Each `Practice` carries:

- `sub_paragraph` — e.g. `"5.1.f"` for emotion recognition in workplaces
- `citation` — tuple of internal-form refs (`("Art. 5", "Art. 5.1.f")`)
- `exceptions` — narrative of the carve-outs that LET the practice through
- `related_high_risk_anchor` — when the carve-out exists, the high-risk path that may still apply
- `effective_phase` — points to a `Phase` (`"phase_2025_02_02"` for Art. 5(1)(a)-(h); `"phase_omnibus_2026_12_02"` for the 9th)
- `keywords` — phrases that anchor a question to this practice

### `AnnexIIICategory`

Each of the eight high-risk use-case categories from Annex III is a first-class entity. Before the ontology, Annex III's eight categories lived in one summary string and were similarly re-extracted by hand for each verdict template.

The registry contains eight entries: `biometrics`, `critical_infrastructure`, `education_grading`, `employment`, `essential_services`, `law_enforcement`, `migration_asylum`, `justice_democracy`.

Each `AnnexIIICategory` carries:

- `number` — the Annex III row number (1-8)
- `sub_points` — sub-categories within the row (e.g. Annex III(5)(a), (5)(b), (5)(c), (5)(d) for essential services)
- `related_prohibitions` — `Practice` ids of nearby Art. 5 prohibitions (so the system can disambiguate "is biometric ID prohibited or high-risk?")
- `keywords` — phrases that anchor a question to this category

### `Phase`

Each applicability date in the AI Act rollout (`phase_2025_02_02`, `phase_2025_08_02`, `phase_2026_08_02`, `phase_2027_08_02`) plus Digital Omnibus deferrals (`phase_omnibus_2026_12_02`, `phase_omnibus_2028_08_02`).

Each `Phase` carries:

- `effective_date` — concrete date the phase obligations take effect
- `articles` — which articles' obligations come into force at this phase
- `superseded_by` — pointer to a later phase when Digital Omnibus moves the goalposts (e.g. `phase_2027_08_02` is superseded by `phase_omnibus_2028_08_02` in some sectors)

---

## Relationship types

The ontology models relationships as typed tuple fields on the dataclasses rather than a separate edge table. Each side of a relationship references the other by ID, so traversal is a simple registry lookup.

| Relationship | From | To | Modelled as |
|---|---|---|---|
| Practice → Article | `Practice` | Article ref | `Practice.citation: tuple[str, ...]` |
| Practice → exempted high-risk path | `Practice` | Article/Annex ref | `Practice.related_high_risk_anchor: str` |
| Practice → activation phase | `Practice` | `Phase.id` | `Practice.effective_phase: str` |
| AnnexIIICategory → adjacent prohibition | `AnnexIIICategory` | `Practice.id` | `AnnexIIICategory.related_prohibitions: tuple[str, ...]` |
| Phase → articles | `Phase` | Article ref | `Phase.articles: tuple[str, ...]` |
| Phase → deferral | `Phase` | `Phase.id` | `Phase.superseded_by: Optional[str]` |
| ActorRole × RiskClass → obligations | (Role, Class) | tuple of article refs | `ROLE_OBLIGATIONS: dict[Role, dict[Class, tuple[str, ...]]]` |

The most important relationship is the **role × risk-class → obligations matrix**. It encodes the answer to "I'm an X handling a system in risk class Y — what do I owe?" without requiring an LLM, regex, or graph traversal. It's computed once at module load.

---

## Lookup tables (derived views)

The ontology powers six legacy lookup tables:

| Table | Location | What the ontology contributes |
|---|---|---|
| `EC_CHECKER_OBLIGATION_MAP` | `app/data/kb.py` | Static — stays the source of obligation-summary prose |
| `_KEYWORD_ENTITY_MAP` | `app/engines/graph_rag.py` | Source of legacy concept-keyword anchors. New keywords go to `Practice.keywords` / `AnnexIIICategory.keywords`. |
| `_CLASSIFICATION_TOPICS` | `app/engines/graph_rag.py` | Static — stays the verdict-template source for the 18 most common verdicts |
| `KEYWORD_TO_ARTICLE` | `app/integrations/regenold/scope.py` | Source of scope-anchor keywords. New ones go to `Practice.keywords` / `AnnexIIICategory.keywords`. |
| `_AI_ACT_ANCHORS` | `app/integrations/regenold/scope.py` | Static — stays the in-scope vocabulary list |
| Cross-ref graph (`KB_CROSS_REFS`) | `app/data/kb_xrefs.py` | Auto-derived from KB summaries; no manual entry |

The ontology is **additive**. The legacy tables stay live because they encode hard-won round-1-through-13 corrections. The ontology is the canonical place for new concepts going forward.

---

## How to extend

### Adding a new prohibited practice

1. Add a new `Practice` to `PRACTICE_REGISTRY` in `app/data/ontology.py`.
2. Pick a stable `id` (snake_case, e.g. `new_practice_x`).
3. Fill `citation`, `description`, `exceptions`, `keywords` from the regulation text.
4. If the carve-out lands the practice in a high-risk category, set `related_high_risk_anchor`.
5. If the practice activates on a Digital Omnibus date, point `effective_phase` to the right `Phase.id`.
6. Run `pytest tests/test_kb_consistency.py` to verify every citation resolves in `ARTICLE_EXISTENCE`.

### Adding a new Annex III category

1. Add an `AnnexIIICategory` to `ANNEX_III_REGISTRY`.
2. Set `number` to the official Annex III row number.
3. List sub-points so per-sub-point verdicts can fire later.
4. Add keywords that should anchor questions about this category.

### Adding a new ActorRole obligation entry

1. Edit `ROLE_OBLIGATIONS[role][risk_class]` — append the article refs the role owes in that risk-class regime.
2. Verify the addition reads correctly via `obligations_for(role, risk_class)`.

### Adding a new Phase (Digital Omnibus or future amendment)

1. Add a `Phase` to `PHASE_REGISTRY` with the effective date + which articles come into force.
2. Update upstream `Phase.superseded_by` pointers if the new phase defers existing obligations.

---

## Invariants (enforced by `tests/test_kb_consistency.py`)

The lint suite verifies these on every CI run:

1. Every `Practice.citation` entry resolves in `app/data/article_existence.py::ARTICLE_EXISTENCE`.
2. Every `AnnexIIICategory` keyword list is non-empty.
3. Every `Phase.articles` entry resolves in `ARTICLE_EXISTENCE`.
4. Every `Phase.superseded_by` is either `None` or a valid `Phase.id`.
5. Every `Practice.related_high_risk_anchor` (if set) resolves in `ARTICLE_EXISTENCE`.
6. Every `Practice.effective_phase` is a valid `Phase.id`.
7. Every `AnnexIIICategory.related_prohibitions` entry is a valid `Practice.id`.
8. Every value in `ROLE_OBLIGATIONS[role][risk_class]` resolves in `ARTICLE_EXISTENCE`.
9. Every value in the legacy `_KEYWORD_ENTITY_MAP`, `KEYWORD_TO_ARTICLE`, and `_CLASSIFICATION_TOPICS["refs"]` lists resolves in `ARTICLE_EXISTENCE`.
10. Every key in `EC_CHECKER_OBLIGATION_MAP` resolves in `ARTICLE_EXISTENCE`.
11. The cross-reference graph in `kb_xrefs.py::all_edges()` only contains targets that resolve in `ARTICLE_EXISTENCE`.

Breaking any invariant is a hard CI failure.

---

## Forward direction

The ontology is intentionally narrow today: 9 practices + 8 Annex III categories + 8 roles + 7 risk classes + 6 phases. Future expansion candidates (in priority order):

1. **GPAI obligation matrix** — break out Art. 53/55 obligations per sub-paragraph so questions like "what training-data summary does Art. 53(1)(d) demand?" resolve precisely.
2. **Article 13 transparency sub-obligations** — Art. 13 has ~10 distinct instruction-for-use items; today they're one summary blob.
3. **Article 26 deployer duty matrix** — Art. 26 has 7 sub-paragraphs of distinct deployer duties; structured nodes would let us answer "what's Art. 26(6) about?".
4. **Crosswalks to NIST AI RMF + ISO 42001** — already half-modelled in `graph_rag_prompts.py` Cypher templates; needs typed nodes.
5. **Penalty-tier matrix** — Art. 99 has three tiers (35M/7%, 15M/3%, 7.5M/1%); a typed `PenaltyTier` entity would let date+violation queries resolve a precise ceiling.

When the regulation evolves (Digital Omnibus formal adoption, future delegated acts), the ontology evolves with it. Every change to `PRACTICE_REGISTRY`, `ANNEX_III_REGISTRY`, `ROLE_OBLIGATIONS`, or `PHASE_REGISTRY` should be accompanied by a CHANGELOG entry citing the source (regulation text section, Commission guidance date, Digital Omnibus reference).

The ontology is the schema. The schema is the product.

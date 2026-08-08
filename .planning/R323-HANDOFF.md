# R323 handoff — Neo4j graph: seeded, verified, wired

Merged to `main`: `0f1b3da` → `a692ffb` (5 commits). Nothing left uncommitted.
Full 30-agent audit: `.planning/R324-GRAPH-DESIGN-PROPOSAL.md`.

## State you can rely on (do not re-audit)

**Aura `neo4j+s://0644b854.databases.neo4j.io`**, Neo4j 5.27-aura enterprise,
seed `2026-08-08-r323-annex-sections`, CELEX `32024R1689` (pre-Omnibus,
Art 113 = "apply from 2 August 2026").

The EU AI Act is **complete and byte-identical across code and graph**:

| surface | articles | annexes | recitals | definitions |
| --- | --- | --- | --- | --- |
| catalog / official text / resolver / KB map | 113 | 13 | 180 | 68 |
| **live graph (byte-compared)** | **113/113** | **13/13** | **180** | **68** |

plus 658 Paragraph / 421 Point / 37 SubPoint. Zero Omnibus contamination, zero
U+FFFD, zero NBSP, zero empty text. Independently re-confirmed against the
Lawstronaut copy of the official act: **median similarity 1.0000, mean 0.9985,
none below 0.90**.

**A new Aura instance seeds itself.** `app/main.py::_maybe_auto_seed_neo4j` (R36)
fires on boot when `NEO4J_URI` is set and `NEO4J_AUTO_SEED` is not off. Local
`.env` has it off; the Railway dashboard does not.

## Gates at `a692ffb`

* full pytest, **in-place** A/B: 87 failed BOTH arms, failure sets
  byte-identical → **0 new**, +38 passing. The 87 are the documented
  pre-existing `provider=cli` Stage-2 env artifact.
* davidath 476 — byte-identical to R322: Ans **0.1884 / 0.3545 / 0.6143**,
  Ref **0.5971 / 0.4748 / 0.4316**, Tone **1.0**, multi-turn **20/20**.
* `evals.regenold.runner` **255/255**, RISK_F1 macro **1.00**.
* OOS `--oos-suite all` — **0 scope leaks** (2 pre-existing `adjacent_eu` soft
  fails).

## Traps that cost real time this round

1. **Check the key form before reporting a gap.** Annex node ids are
   `annex_IV` (uppercase Roman); `ARTICLE_EXISTENCE` keys articles as
   **`Art. N`**, not `Article N`. Both of my wrong probes made a *complete*
   surface look empty.
2. **Console `�` on Windows is cp1252 rendering, never data.** Verify by
   codepoint (`ord(c) == 0xFFFD`), not by printing.
3. **A code fix to `provision_text` is NOT live until you re-seed AND bump
   `SEED_VERSION`.** Without the bump the boot hook hits `skip-current` and
   production keeps the old data. This round the graph was serving WRONG LAW
   (`annex_VIII_1` = the *deployer* item) after the fix had already landed.
4. **`scripts/seed_neo4j_kb.py` never calls `load_dotenv()`** — export
   `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` or it exits 1. Its error
   prints at the TOP, so **never `tail` it**; a tail shows a normal-looking
   payload dump and reads as success.
5. **`tests/conftest.py` deliberately deletes `NEO4J_URI`.** A
   `skipif(no-live-graph)` test therefore ALWAYS skips — it pins nothing. Use a
   fake client seeded with rows copied from the live instance.
6. **Full-suite failure diffs must run IN PLACE.** A `git worktree` has no
   `.env`, and the denoiser / topic-filter / safety-gate cluster changes
   behaviour on `GROQ_API_KEY`.
7. **Lawstronaut email is `andreib@antifragile-ai.net`**, NOT the gmail. The
   bearer is at `data.token.refresh_token` (not `access_token`), TTL 1800 s.
   Both env vars must be EXPORTED — that script has no dotenv either.

## Open, ranked

1. **The vector layer is dead.** 7 VECTOR indexes + 1483 embeddings,
   `grep -rn 'db.index.vector'` returns **nothing** repo-wide. Largest
   built-but-unwired capability and the strongest SOTA candidate. Wire it at
   the same non-citable context layer `kg_context` occupies — never as a ranker.
2. ~~W2~~ **FIXED in `a4519ec`.** Confirmed real and measured properly: with
   `REGENOLD_KG_CONTEXT` off vs on the drift allowlist went **21→27 / 17→24 /
   13→14** and the mined block **7.9k→24.3k chars**, the added refs being the
   regulation's own cross-references (Art. 35/46/74, Annex VIII/IX). Fixed by
   threading `include_kg` from the existing `include_grounding` flag, so the
   guard drops the graph blocks while the PROMPT keeps them. ⚠ The obvious test
   (render kg_context, re-read the allowlist) **cannot detect this** —
   `_extract_context_grounded_refs` renders kg_context itself, so both arms
   already contain it. Compare `REGENOLD_KG_CONTEXT` off vs on.
3. **Foreign instruments — groundwork done, seeding NOT written.** The operator
   chose "reference nodes + Annex I full text". Ready:
   `.evalout/celex_verified.json` (**67/67 CELEX empirically verified** — probe
   the Cellar, do NOT derive heuristically: two derivations produced wrong legal
   ids like `31025R2012`), and all 20 Annex I instruments fetch credential-free
   (16.8 MB). ⚠ The audit measured full-text ingestion as **>2× the retrieval
   corpus, all non-citable**, with R319 crowding-out already observed — the
   operator reaffirmed it anyway, so ship it **env-gated and A/B'd before it
   reaches retrieval**.
4. **The cross-regulatory block is 100% hardcoded Python**, not graph output —
   `framework` / `relation` properties and `RELATES_TO` / `HAS_EXTERNAL_REF`
   edge types do not exist, so it emits 5 UNRECOGNIZED warnings per call. Fixed
   for free by (3), or relabel the heading honestly.
5. **Still-unread layers:** Definition/`HAS_DEFINITION`,
   Obligation/`HAS_OBLIGATION`, RiskLevel/`APPLIES_AT`,
   LegalInstrument/`HAS_PROVENANCE`, Guideline/`INTERPRETS`,
   Question+Dimension/`BELONGS_TO`+`ASSESSES`.
6. **Operator question:** is `REGENOLD_GRAPH_AWARE=1` set on the Railway
   **dashboard**? `railway.toml [deploy.envs]` has never applied (R306) and
   `/healthz/graph` does not expose it — if unset, the R47-B recital feature has
   never run in production.

## Corrections to CLAUDE.md worth folding in

* Line ~1508 is **stale**: `kb_search._xref_in_degree()` reads the **FULL**
  xref graph (`kb_search.py:1055-1058`, R57-C), not the core one. That
  falsifies the safety premise of the D3 prose-edge backfill.
* `REGENOLD_KG_MAX_CHARS` now exists (default 16000). A 4000-char cap is
  structurally the R319 experiment that dropped gold — Article 5's *first* unit
  alone exceeds it.

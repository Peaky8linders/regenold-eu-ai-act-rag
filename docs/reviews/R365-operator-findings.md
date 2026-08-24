# R365 — operator-facing findings: the seeder, the graph, and the health signal

**Date:** 2026-08-24 · **Base:** `ea1f933`
Everything below was verified against the **live** Aura instance and the **live** Railway
deployment, read-only. Node/edge counts are measured, not inferred.

---

## 1. ⛔ `SEED_VERSION` bumps are NOT made safe by the R361 guards

The R361 close-out recorded that the recital seed gap *"needs a `SEED_VERSION` bump, now safe
thanks to the R361 seeder fix."* **That is false, and it is the dangerous direction to be wrong
in.**

Trace of `app/main.py::_maybe_auto_seed_neo4j` (`:445`):

| step | line | behaviour |
|:--|:--|:--|
| 1 | `:474` | no `NEO4J_URI` → `disabled-no-uri` |
| 2 | `:475` | `_auto_seed_disabled_by_env()` (`:276-291`) — **returns False when the var is UNSET** |
| 3 | `:550` | reads `KBMetadata` via `execute_read_strict` — **R361 guard #1** |
| 4 | `:567-572` | metadata-probe timeout → `skip-unverified` |
| 5 | `:581-591` | `current_seed == SEED_VERSION and current_kb == KB_VERSION` → `skip-current` |
| 6 | `:603-644` | **only if `current_seed` is empty**: **R361 guard #2** at `:614`, unreadable count → `skip-unverified`, `count > 0` → `skip-nonempty-drift` |
| 7 | `:646-664` | **else → `seed_drift`**, daemon thread fires the full MERGE |

**Both R361 guards convert "I could not read the state" into SKIP.** They close *ignorance*
holes. A `SEED_VERSION` bump is the opposite case — the state reads cleanly and simply
*differs* — so control lands at `:646` and seeds. The `_node_count > 0` refusal at `:634` is
nested inside `if not current_seed:` and **cannot fire on a version bump**.

⇒ On any process where `NEO4J_AUTO_SEED` is unset or non-falsy, **bumping `SEED_VERSION` is an
unattended write over live production Aura, by design.**

Mitigating: the write is `MERGE`-only; `DETACH DELETE` is opt-in behind `--clear`
(`scripts/seed_neo4j_kb.py:1407`, `:1738`) and is not reachable from the boot path. Local
`.env` carries `NEO4J_AUTO_SEED=0`.

**The Railway dashboard value is UNVERIFIED.** This is the same open operator question
`CLAUDE.md` already flags for the behavioural flags.

### Recommended operator action

```
railway variables --set NEO4J_AUTO_SEED=0
```

Belt-and-braces regardless of the code default, and it costs nothing.
Seed deliberately via `scripts/seed_neo4j_kb.py`, **never** by bumping `SEED_VERSION`.

---

## 2. ⚠ This repo's seeder can no longer reproduce the live graph

| | `KBMetadata` says | live graph holds |
|:--|:--|:--|
| nodes | 1758 | **1789** |
| edges | 1979 | **2156** |

Six labels (`ConformityRoute`, `FRIAWorkflow`, `GPAIModelProfile`, `RiskControl`,
`RiskScenario`, `SeriousIncidentSLA`) and four relationship types
(`HAS_RISK_CLASS_OBLIGATION` 80, `GOVERNED_BY` 58, `VIOLATES` 24, `REQUIRES_CONTROL` 15) have
**zero occurrences in `scripts/seed_neo4j_kb.py`**. Their writer is
`scripts/extend_aura_role_obligations.py`, which exists **only in the sibling fork**
`antifragileai-regenold-evaluation`.

A MERGE-only re-seed would not delete them, but **this repo is no longer the sole author of
the live graph**, and any reasoning that treats `seed_neo4j_kb.py` as the source of truth for
Aura is wrong. Reconcile the two repos' seeders before the next seed.

---

## 3. The recital seed gap is real, the consumer IS live — and the fix is blocked on data

Verified live (Aura `368fd9ef`, `health_check() -> healthy`, all read-only Cypher):

| quantity | live measured |
|:--|:--|
| `Recital` nodes | **180** (all with non-empty text and a 128-float embedding) |
| `HAS_RECITAL_ANCHOR` edges | **5** |
| distinct source articles | **2 of 113** — `article_5 → 18/30/31/44`, `article_52 → 112` |
| orphaned recitals | **175** |
| any other rel type touching `Recital` | **none** |

Rebuilding the seeder payload offline from HEAD produces the identical result, so code and
graph agree — the seeder genuinely emits 5.

**⛔ Do not prose-mine the recitals for the missing edges.** Measured over all 180
`OFFICIAL_RECITAL_TEXT` entries: only 31 contain the word "Article" at all; **63** `Article N`
matches, of which **54** are followed by an explicit foreign-instrument marker (TFEU, the
Charter, 2016/679, 2016/680, 2019/1020, 2022/2065, 2017/745 …). Reading the 9 survivors by
hand leaves **4 genuine own-Act pairs** (R40 and R41, each → Art. 5 + Art. 26). A naive regex
yields 47 candidate edges — **~90% hallucinated**. This independently reproduces the sibling
fork's recorded Closed Direction.

The repo carries **no** recital↔article mapping table (`grep -rniE
"RECITAL_(TO|MAP|ARTICLE|ANCHOR)|ARTICLE_RECITAL|RECITALS_FOR"` over `app/`, `scripts/`,
`evals/` → nothing), and `app/data/eu_ai_act_tree.py:621-633` states recitals are atomic with
no parent. A correct structural seed needs an **externally curated map** (~250–400 edges over
~60–90 articles). EUR-Lex CELEX `32024R1689` does not carry one, which is exactly why the
regex fails.

### The cheap variant that has NOT been measured

The open-domain substitute already exists and already lost: `graph_semantic.py:661-700`
`fetch_definition_and_recital_context` does open-domain ANN over the 180 recital embeddings
precisely *because* the anchor edges are missing; gate `REGENOLD_SEMANTIC_GLOSS`, default OFF,
and the fork measured it at micro precision **0.614 → 0.583 for no gain**.

What has **not** been tried is the **constrained** variant — top-k over
`v_recital_embedding` restricted to recitals whose top match is a provision **already cited**.
That is the shape that worked for sub-provisions (`Art. 12 → 12(1)` at 0.891). It needs
**zero new edges and zero `SEED_VERSION` risk**. Prove it fires with a counter before reading
any number.

⚠ Gate that on **`ab_judge`, not `easyhard_ab`**: `kg_context`'s block is non-citable, but the
`REGENOLD_GRAPH_AWARE` consumer at `regenold.py:8330` appends recital prose **into
`answer_text`** — a real answer-composition change, on a corpus whose documented root failure
(R298) is answer over-breadth.

Separately, fix the Article-only `MATCH` at `seed_neo4j_kb.py:1026` so Annex anchors are not
silently dropped.

---

## 4. `/healthz/llm` still cannot tell you whether Bedrock works

Three code defects, all verified:

1. **The AWS error never leaves the process.** `_bedrock_complete_for_graph_rag`
   (`app/engines/_graph_rag_impl.py:620-750`) logs the classified error at `:745` and
   `return None` at `:747`. `api_access_denied_403` / `api_key_invalid_403` /
   `api_validation_400` reach neither the wire, nor the reasoning trace, nor `/healthz/llm` —
   the only copy is Railway stdout.
2. **The purpose-built diagnostic is dead code.** `check_connectivity_and_permissions`
   (`app/llm/bedrock_client.py:787-844`) returns the exact AWS status *and* an operator hint,
   and has **zero call sites in `app/`**.
3. **`/healthz/llm` never probes Bedrock.** With `provider_label == "openai_wrapper"`
   (production's case) it probes only the wrapper; `_degraded_to_bedrock`
   (`app/main.py:1022-1078`) decides green/red from `is_bedrock_provider_enabled()` — *"are
   credentials PRESENT"* — plus `_fb_dead = _fb_att > 0 and _fb_ok == 0` (`:1057`).
   **With `fallback_attempts == 0` it reports `llm_ok: true` + "bedrock fallback active" no
   matter how broken Bedrock is.** R361's fix is real but **inert until leg 2 has been dialled
   at least once** — which is production's current state.

### 4.1 ⚠ The counters are per-worker, so a single probe is a 1-in-N sample

`Procfile` and `railway.toml:2` both run `uvicorn … --workers 2`, and `_STATS`
(`app/llm/stage2_policy.py:74-85`) is a plain process-local dict. **Verified: two consecutive
probes of the same `deployment_id` returned different counters** (probe 1
`primary_attempts:1, primary_ok:1`; probe 2 all zeros).

R361 made `llm_ok` *depend* on those counters (`main.py:1058`), so the health **verdict** — not
just the display — is now worker-dependent. **Do not alert on a single read**, and do not treat
one green probe as a service-wide statement. The R361 close-out's production verification
(`primary_ok: 1`, "counters balanced on both legs") was a one-worker sample; it is not wrong,
but it is narrower than it reads.

### 4.2 The bearer token is pinned for the life of the process — and the hint says otherwise

`_add_bearer_header` (`app/llm/bedrock_client.py:287-290`) closes over a token captured at
client-build time, and the client is a process-wide singleton (`_RUNTIME_CLIENT`, `:304-318`).
Rotating `AWS_BEARER_TOKEN_BEDROCK` in the environment does **nothing** until restart —
verified by execution. The operator hint at `:813-820` says *"the code picks the new key up on
the next request with no restart."*

**A redeploy is mandatory after rotating the credential.** This matters right now, because
Bedrock-on-Railway is believed to be exactly a stale-credential problem — an operator who
rotates with `--skip-deploys` will conclude the fix did not work.

---

## 5. Bedrock on Railway: operator-config at root

Production's `/healthz/llm` proves `is_bedrock_provider_enabled()` is `True`, so Railway holds
*some* AWS credential — it is the wrong or stale one. That is a dashboard fix, not a code fix.
But §4 is why it has been undiagnosable from outside the container, and those parts are code.

Order of operations:

1. `railway variables --set NEO4J_AUTO_SEED=0` (§1, unrelated but free)
2. re-mint the AWS credential in the Railway dashboard
3. **redeploy** — not `--skip-deploys` (§4.2)
4. probe `/healthz/llm?probe_bedrock=1` (added in the R365 diagnosability PR) and read the
   verbatim AWS `status` / `error` / `hint`
5. probe **twice** and expect different counters (§4.1) — that is not a bug

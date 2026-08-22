# R360 — Stage-2 transport contract: cloudflared tunnel primary, Bedrock fallback

**Date:** 2026-08-22 · **Branch:** `claude/antifragile-ai-optimizations-dyv3ca`

## The requirement

> Make sure this repo uses the cloudflared tunnel with the existing Claude Max
> subscription as the primary for Stage-2 LLM processing and the Bedrock client
> as the secondary/fallback. Validate and test properly to ensure no request
> goes any other way.

## What was actually true before

Stage-2 could reach a non-tunnel provider **five** ways. Two of them needed no
opt-in at all — an API key sitting in the environment was sufficient:

| # | path | what armed it | consequence |
| :-- | :--- | :--- | :--- |
| 1 | Groq tertiary fallback in `_openai_wrapper_complete_for_graph_rag` | any `GROQ_API_KEY` + one tunnel failure | Stage-2 answered by `openai/gpt-oss-120b` |
| 2 | Gemini secondary fallback in `_claude_max_enhance_answer` | any `GEMINI_API_KEY` + tunnel *and* Bedrock empty | Stage-2 answered by `gemini-2.5-flash` |
| 3 | `P2P_GRAPH_RAG_PROVIDER=gemini` / `=anthropic` | explicit env | Gemini / per-token Anthropic SDK |
| 4 | fusion panel (`REGENOLD_FUSION_STAGE2=1`) | default roster is `(sonnet, groq, mistral)` | Stage-2 fanned to Groq + Mistral |
| 5 | `P2P_GRAPH_RAG_PROVIDER=bedrock` | explicit env | **inversion** — the fallback becomes the primary, tunnel never dialled |

Path 1 is the one that matters most in practice. It did not merely swap the
model: it swapped in a *compressed* system prompt
(`_get_groq_compressed_system_prompt`) and, above ~11 kB, a shrunken user
message. So a deploy carrying `GROQ_API_KEY` answered its first post-hiccup
questions from a different model **on a prompt no eval has ever measured** —
silently, and attributed to the tunnel arm by any A/B running at the time.

Per `CLAUDE.md` R330, the operator's `.env` does carry `GROQ_API_KEY`, and the
Railway dashboard's flag set is an open question. So this was live, not
theoretical.

## The worse defect: the fallback was dead where it mattered

Found by tracing rather than by the tests, which asserted the fallback *existed*
but never that it could be *reached*.

The Bedrock leg lived inside the `response.error` branch. But the Claude Max
wrapper reports `finish_reason="stop"` even on a stream cut mid-word (R102) — so
a truncated Stage-2 answer is **not** a transport error. It is caught by the
structural / verdict guards further down, which `raise` straight past every
fallback block in `_claude_max_enhance_answer` to the outer handler.

Measured on the real code path, before the fix:

```
wrapper returns finish_reason="stop", text cut mid-word
  → BEDROCK FALLBACK CALLS: []
  → degraded to the deterministic Stage-1 draft
```

**Zero Bedrock calls on the most common tunnel failure mode**, while the
operator believed a fallback was armed. Same shape as the R329 rerank
post-mortem: a lever that reads correctly in the diff and does nothing.

## What shipped

`app/llm/stage2_policy.py` is the single source of truth. It resolves the chain,
refuses off-contract transports **by name**, and counts what actually dialled.

* All five paths closed. `=bedrock` collapses to the tunnel rather than
  inverting the order.
* The Bedrock leg hoisted to a helper reachable from **all three** failure
  modes — transport error, `finish_reason=length`, structural truncation.
* Leg 2 held to leg 1's standard: a mid-clause Bedrock answer is discarded, not
  shipped, because `stage2_landed=True` on cut prose lets the R72 reconcile pass
  prune citations the prose never described.
* `_stage2_provider_enabled` now describes the chain that will actually run
  (tunnel **or** Bedrock), not the env var's stated preference. A deploy with
  the tunnel down and Bedrock configured previously had Stage-2 gated OFF
  entirely.
* `/healthz/llm` reports `stage2_transport {strict, chain, stats}`.

Gate: `REGENOLD_STAGE2_STRICT_TRANSPORT`, default **ON**, env-reversible,
registered in `_engine_cache_key` (invariant #4 — the flag decides which model
writes the prose, so the two regimes must not share a cache entry).

## Evidence

| check | result |
| :--- | :--- |
| full suite | **6446 pass / 77 fail** — the same 77 that fail on `main`, zero new |
| new tests | 31, in `tests/test_r360_stage2_transport_policy.py` |
| guard is load-bearing | flipping the default to `0` fails **13 of 31** — not a vacuous suite |
| deterministic path unaffected | 60 scenarios, `provider=cli`, sha256 `46bfad25c96c72b5…` — **byte-identical to `main`** |
| suite hermeticity | zero outbound egress attempts during a full run (proxy relay-failure count 20 → 20) |
| Bedrock reachable from every failure mode | 1 attempt + 1 success recorded per mode |

The tests assert on runtime counters (`stage2_policy.transport_stats()`), never
on the shape of the code, and seal every off-contract provider behind an object
that raises on any attribute access — with the `is_*_enabled` predicates forced
**True**, so it is the policy and not a missing API key that closes them.

The suite is deliberately two-sided: it also pins that
`REGENOLD_STAGE2_STRICT_TRANSPORT=0` *really does* still reach Groq. A guard
whose OFF state behaves like its ON state proves nothing.

## Not changed, deliberately

* **Bedrock fallback model stays Qwen 3 32B / 235B.** The upstream eval repo
  moved its chain to `claude-opus-4-6`-first, and that is probably better for
  legal prose — but commit `a65fa87` on this branch chose Qwen deliberately.
  Flipping it is a quality decision for the operator, not a routing fix, and it
  would change answer content. Flagged, not taken.
* **Non-Stage-2 LLM callers left alone**: Stage-0 intent classification, the
  scope/safety gate, and the query de-noiser still use their own chains. The
  requirement was scoped to Stage-2. Worth a follow-up decision, since those
  are what make third-party credentials matter at all (`CLAUDE.md` R330 records
  the scope classifier making live third-party calls when `.env` is present).

## Everything else that landed under R360

The contract work above is R360.0–.1. A multi-agent adversarial review of the
routing trace (four subsystem surveys, each re-verified against the code, then
synthesised) found the rest. Every one was verified against the code before it
was fixed — several of the surveys' own claims were refuted on inspection.

| id | fix | why it mattered |
| :--- | :--- | :--- |
| **.1** | Bedrock reachable from **all three** tunnel failure modes | the fallback fired only on the failure that rarely happens |
| **.2** | `ab_judge` probes the wrapper it will actually use, + CF Access header | running the merge gate over the tunnel silently downgraded it to the deterministic tier |
| **.3** | Bedrock judge's transient shapes classified retryable | a throttle window thinned the sample instead of retrying |
| **.4** | `cli` guard on `_stage2_complete`; `/healthz/llm` stops calling Bedrock "deterministic" | the offline bench still dialled the wrapper; a green light meant the opposite of what it said |
| **.5** | `legal_v2` accepts Bedrock; judge reply ceiling 400 → 1600, env-tunable | the judge was pinned to the tunnel it competes with, and truncated verdicts became 'unknown' rows |
| **.6** | boot seeder refuses what it cannot verify | a slow Aura response at boot triggered a full KB re-MERGE nobody asked for |
| **.7** | **destination pinning** — host allowlist, not just provider id | `OPENAI_API_BASE=…openrouter.ai…` satisfied every policy check and every test |
| **.9** | healthz reports "primary offline; bedrock fallback active" | `llm_ok:false` could not distinguish degraded-but-serving from no-LLM-at-all |
| **.10** | Bedrock fallback model is a lever (default unchanged) | leg 2 silently serves Qwen 3 against a Claude Opus primary |
| **.11** | **Annex III(1)(b) legal inversion** | the KB said sensitive attributes keep you OUT of the high-risk tier |
| **.12/.13** | null token count no longer kills Stage-2; `execute_read_strict` exists | a telemetry field caused outages; a failed Cypher query read as an empty result |

### R360.7 deserves its own note

Every earlier commit in this branch would have passed a review that asked only
"can the provider id be wrong?". The id was right and the packet still left:

```
OPENAI_API_BASE=https://openrouter.ai/api/v1
  -> resolved Stage-2 base URL: https://openrouter.ai/api/v1
  -> is_stage2_provider_allowed("openai_wrapper"): True
```

### R360.11 deserves its own note

`app/data/ontology.py` described Annex III category 1(b) as "biometric
categorisation by **non-sensitive** attributes". The Act — checked against this
repo's own `get_provision_text("Annex III.1")` — says "according to **sensitive
or protected** attributes or characteristics". That inverts the test a reader
applies, and `kb_search._build_ontology_docs` extends `sub_points` **twice**
(`kb_search.py:269-270`), so the wrong phrase carried double BM25 weight against
exactly the questions it misleads.

The upstream repo corrected the ontology and **left the same inversion in the
curated intercept** (`_graph_rag_data.py`) — which is the text that reaches the
wire. Both are fixed here.

## Doc corrections (CLAUDE.md was actively misleading)

* `gold_dropped` **does** exist — `gold_dropped_head` (`evals/bench/metrics.py:555`),
  gated as a zero-drop SUM in `easyhard_ab.py:124`. The file said it did not exist
  and that reference changes were therefore ungateable. That claim held work back.
* `REGENOLD_GRAPH_SEMANTIC_LAYERS` code default is **`0`**, not `1` (R330 flipped it).
* "the 276 scenarios" is **255**.
* `answer_crag_fine` has **0 occurrences** here; it is an eval-repo axis.

## Deliberately not done

* **The V2 answer-prompt family + XML channel separation.** The biggest
  transport-agnostic delta upstream, with a recorded +0.0495 judge reference
  precision. It changes answer shape, so `AGENTS.md` requires the live pairwise
  A/B to gate it — and that gate cannot run from here (see
  `docs/LIVE-EVAL-RUNBOOK.md`). Land it behind a default-OFF flag and A/B it.
* **The pushback / challenge line.** Its own audit is mixed: concession rate,
  meta-commentary and XML leak all 0.0000 and the length/latency blow-up gone,
  but **answer correctness down ~8-11%** on the post-pushback turn, traded for
  reference correctness up. The upstream plan doc's "1.000 Factual Score" claim
  is contradicted by that repo's own audit. Not a port to make blind.
* **The lookahead negation guard.** Add-only and invariant-safe, but it
  over-fires on two verified shapes — `"Article 2(6) excluded systems developed
  solely for scientific research."` drops Article 2(6), the governing exclusion
  provision — and the over-fire rate would be *higher* here than upstream,
  because we lack the V2 clause that keeps negated provisions out of prose as
  numbers.
* **`NEO4J_AUTO_SEED` default.** `railway.toml:211` sets `"1"` and the code
  default is ON when unset, while `AGENTS.md` lists that as prohibited and
  `.env.example` ships `0`. A genuine contradiction, and `AGENTS.md` puts seeder
  defaults behind confirmation — so the guards landed and the default did not.

## Tests that changed regime, not assertions

`test_fusion_stage2`, `test_gemini_routing`, `test_anthropic_provider` cover
legacy multi-provider call shapes. Every assertion is untouched; each module now
declares `REGENOLD_STAGE2_STRICT_TRANSPORT=0`, the regime it was written for.

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

## Tests that changed regime, not assertions

`test_fusion_stage2`, `test_gemini_routing`, `test_anthropic_provider` cover
legacy multi-provider call shapes. Every assertion is untouched; each module now
declares `REGENOLD_STAGE2_STRICT_TRANSPORT=0`, the regime it was written for.

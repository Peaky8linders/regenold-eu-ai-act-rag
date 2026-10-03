# R461 promotion canary — primary-leg re-run

Same endpoint, same 8 fixed official hard-board questions, one draw each, re-run
**2026-10-02 ~15:49-15:56 (Europe/Bucharest)** — this time with production serving on the
**primary `openai_wrapper` leg**, not the Bedrock fallback.

Recorded because the shipped canary (`CANARY.md`, `canary-post.*`) ran with BOTH phases on the
Bedrock fallback, so it confirmed the deploy and the budget bite but not the leg the board gate
measured. This run closes that gap.

## 1. Why the primary was offline, and why it came back

The wrapper (Cloudflare tunnel `wrapper.antifragile-ai.net` to the local
`claude-code-openai-wrapper` on `127.0.0.1:8000`) was never down — `/health` answered
`healthy` throughout. Its Claude Code CLI backend was inside a **Max-plan session-limit
window**, and the wrapper maps an `is_error` CLI result with no assistant content to
HTTP 500 `"No response from Claude Code"` (`src/main.py`, two raise sites). Wrapper stderr,
live log `service-stderr.log`:

* `10:04:26` — `api_error_status: 429`, `result: "You've hit your session limit — resets 1:40pm (Europe/Bucharest)"`;
* `13:39-13:42` (the canary window) — the same 429, `"resets 3:30pm"`;
* `09:00:46` — a separate transient: `Failed to refresh OAuth token: another Claude Code process
  is refreshing it or exited mid-refresh`.

The 13:39-13:42 burst is exactly when both canary phases probed `/healthz/llm`, which is why
both recorded `primary offline (api_status_500: ...)`. No config changed: the **15:30 session
window reset** restored the leg. Verified before the re-run: 8/8 `/healthz/llm` reads across
BOTH workers (pid 3 and pid 4) returned `provider: openai_wrapper`, `llm_ok: true`,
`detail: ok`, ~5.5-6.8 s, and the wrapper's stderr has 0 ERRORs since 15:30.

## 2. Primary-leg canary (PRE `ca71879d7059` fallback to POST `7fbd46737548` primary)

| row | budget | pre refs | post refs | pre chars | post chars |
| :-- | --: | --: | --: | --: | --: |
| `rg_028` | 2 | 1 | 1 | 402 | 457 |
| `rg_034` | 2 | 2 | 3 | 450 | 707 |
| `rg_040` | 2 | 2 | 2 | 808 | 808 |
| `rg_043` | 2 | 1 | 1 | 846 | 846 |
| `rg_049` | 2 | 1 | 2 | 368 | 986 |
| `rg_052` | 2 | 2 | 1 | 624 | 1413 |
| `rg_004` | 2 | 6 | 2 | 652 | 636 |
| `rg_007` | 3 | 5 | 3 | 884 | 1044 |

mean refs **2.5 to 1.875**, in budget **6/8 to 7/8**, mean chars 629.2 to 862.1.

Gates: **PASS 5/5** — `deploy` (`7fbd46737548`), `health`, `transport` (8/8, no refusal),
`budget`, `integrity`. Caveat carried over from the record: the PRE phase is the fallback-leg
read, so these deltas mix the lever with the transport; the transport-consistent delta is the
one in `CANARY.md`. What this run adds is that the deploy serves, and the budget and integrity
gates hold, **on the primary leg**.

## 3. Same-code transport contrast (fallback POST vs primary POST)

`e1fba9733755` (fallback) vs `7fbd46737548` (primary) — the commit between them is docs-only,
so the runtime code is identical.

| row | budget | fb refs | pr refs | fb chars | pr chars | fb ms | pr ms |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| `rg_028` | 2 | 1 | 1 | 620 | 457 | 6158 | 7554 |
| `rg_034` | 2 | 1 | 3 | 252 | 707 | 34939 | 30369 |
| `rg_040` | 2 | 2 | 2 | 808 | 808 | 7384 | 7498 |
| `rg_043` | 2 | 1 | 1 | 846 | 846 | 3170 | 1332 |
| `rg_049` | 2 | 1 | 2 | 376 | 986 | 16868 | 37172 |
| `rg_052` | 2 | 4 | 1 | 986 | 1413 | 29378 | 31166 |
| `rg_004` | 2 | 2 | 2 | 564 | 636 | 30823 | 28690 |
| `rg_007` | 3 | 3 | 3 | 890 | 1044 | 28591 | 31918 |

means: refs **1.875 to 1.875**, chars **667.8 to 862.1 (+29%)**, latency 19.7 s to 22.0 s,
in budget 7/8 to 7/8. The direction matches the R360.9 note (the fallback is a measured
answer-quality cliff vs the tunnel): same reference count, longer answers on the primary.

## 4. Leg evidence (transport counters, previously all zero)

`stage2_transport.stats` read all-zero on both workers before the run. After:

| worker | primary_attempts | primary_ok | primary_failed | fallback_attempts | fallback_ok |
| :-- | --: | --: | --: | --: | --: |
| pid 3 | 3 | 2 | 1 | 1 | 1 |
| pid 4 | 4 | 4 | 0 | 0 | 0 |

6 of 7 stage-2 attempts answered on the primary leg and one failed over (the Bedrock fallback
served it, `fallback_ok: 1`) — primary-dominated, with one row not primary-served.

## 5. Artifacts

| file | what |
|---|---|
| `canary-post-primary.jsonl` | the re-run rows (8 asks + the health record) |
| `canary-post-primary.json` | the re-run summary |
| `canary-compare-primary.json` | the PRE/POST gate table for this run |
| `canary-post.jsonl`, `canary-post.json` | unchanged — the original fallback-era POST that `CANARY.md` reports |

# R442 — Opus 5.5 as a Stage-2 model option over the tunnel

**Date:** 2026-09-23
**Status:** option wired and verified live; default stays `claude-opus-5`
(a screen, not a gate — see *What this does not show*).

## 1. The tunnel could not serve Opus 5.5 until its CLI was upgraded

The Claude-Max wrapper passes the model id through to the Claude Code CLI
(`CLAUDE_CLI_PATH=C:\Users\th3un\.local\bin\claude.exe`). Measured directly,
`claude -p --model <id> --output-format json`, which reports the model that
actually served the call in `modelUsage`:

| CLI | `claude-opus-5-5` | `claude-opus-5` (production) |
| :-- | :-- | :-- |
| 2.1.269 | **`400 Claude Code 2.1.269 does not support this model; version 2.1.280 or newer is required`** | ok |
| 2.1.280 (`claude update`) | ok, `modelUsage: ['claude-opus-5-5']` | ok, `modelUsage: ['claude-opus-5']` |

2.1.269 is kept at `~/.local/share/claude/versions/2.1.269` (rollback = copy
it back over `~/.local/bin/claude.exe`). The wrapper spawns the CLI per request,
so no wrapper restart was needed. 2.1.280's Fast-mode gate is
`includes("opus-4-8")||includes("opus-5")`, which `claude-opus-5-5` satisfies.

Through the production tunnel (`wrapper.antifragile-ai.net`, CF Access headers,
the app's own provider seam), after the upgrade:

```
claude-opus-5-5  -> HTTP 200 "OK" 6.3 s
claude-opus-5    -> HTTP 200 "OK" 5.9 s   (production model unaffected)
claude-bogus-9-9 -> HTTP 500 "No response from Claude Code"   (ids are resolved, not defaulted)
```

## 2. How to select it

```
P2P_GRAPH_RAG_COMPLEX_MODEL=claude-opus-5-5
```

A fresh env read, already in `_engine_cache_key`. The complex-tier model also
wins on the standard Stage-2 path, so this routes EVERY Stage-2 answer call;
the Stage-1 parse stays on `P2P_GRAPH_RAG_MODEL`. As a judge:
`evals.official.score_arm --judge-provider wrapper --judge-model claude-opus-5-5`.
No Bedrock alias was added: the Bedrock table only lists ids verified active,
and the Stage-2 fallback leg picks its own chain (`stage2_fallback_model()`),
independent of the primary id.

## 3. Two harness defects this exposed (fixed)

1. **The preflight probed a model the run never sent.** It read
   `GraphRAGSettings().stage2_model` alone, but the engine routes
   `complex_model or stage2_model`, so with the override set it probed
   `claude-opus-5` for an arm sending `claude-opus-5-5` — the very model the old
   CLI rejects. The routing rule now lives in ONE function,
   `_graph_rag_impl._route_stage_model`, used by both Stage-2 transports and, via
   `effective_stage2_model()`, by the preflight.
2. **The preflight ran once, before any arm env was applied**, so an A/B whose
   lever is the model never probed the branch arm at all. `_arm` now re-probes
   under its own env (inside the `try`, so a refusal still restores the env); a
   model already proven in this run costs no second call.

The R432 test `test_preflight_probes_the_configured_stage2_model` could not see
either: it greps the preflight's SOURCE for the string `stage2_model`.
`tests/test_r442_opus55_model_option.py` pins both by capturing the probe.

## 4. Live screen — Opus 5 vs Opus 5.5

`run_official_batch --label r442-opus55 --mode easy --stride 14`, arms
sequential, `P2P_GRAPH_RAG_COMPLEX_MODEL=claude-opus-5` (A) vs
`=claude-opus-5-5` (B). 8 rows (`rg_001 015 029 043 057 071 085 099`); 3 are
curated/deterministic (no Stage-2, byte-identical in both arms), so **5 rows
discriminate**. Every polished row: `stage2_served_by=primary`, and the recorded
`stage2_model` is the arm's model on all 5 rows in both arms.

Scored with `evals.official.score_arm` (reconstructed criteria + refkey, 3
repeats, grouped), paired with `evals.official.paired_ab`, one shared cache per
judge:

| axis | A Opus 5 | B Opus 5.5 | Δ | 95% CI |
| :-- | --: | --: | --: | :-- |
| ans_correctness_loose | 97.92 | 97.92 | +0.00 | [+0.00, +0.00] |
| ans_correctness_strict | 87.50 | 87.50 | +0.00 | [+0.00, +0.00] |
| ans_conciseness | 83.22 | 73.55 | **−9.67** | [−18.72, −2.34] |
| ref_correctness_loose | 100.00 | 100.00 | +0.00 | — |
| ref_correctness_strict | 46.67 | 53.33 | +6.67 | [+0.00, +20.00] |
| ref_conciseness | 66.00 | 66.00 | +0.00 | — |
| regulatory_tone (Sonnet 5 judge) | 100.00 | 87.50 | −12.50 | [−37.50, +0.00] |
| regulatory_tone (Opus 5.5 judge) | 100.00 | 100.00 | +0.00 | — |
| resp_speed | 82.66 | 85.98 | +3.31 | [+0.50, +6.38] |
| **Overall, Sonnet 5 judge** | **80.6** | **79.8** | −0.8 | |
| **Overall, Opus 5.5 judge** | **80.6** | **81.1** | +0.5 | |

`gold_dropped_head` A=0, B=0. Mean answer length **841 → 1050 chars**.

Read row by row: Opus 5.5 answers are longer on all 5 discriminating rows
(`rg_099` 900 → 1657, `rg_085` 1386 → 1941, `rg_015` 980 → 1276), which is the
whole conciseness cost. It adds the gold `Annex III.1.a` on `rg_085` (the only
strict-reference move) and is faster on 4 of 5. The two judges agree on every
correctness criterion; they disagree only on `rg_085`'s tone (Sonnet 5 fails a
1941-char single block, Opus 5.5 passes its own answer), which is consistent
with self-preference and is why the independent judge is the primary read.

## 5. What this does not show

n=5 discriminating easy rows is a SCREEN: no correctness axis moved, the
reference axes need n≥120 (R367), and hard mode (half the board) was not drawn.
It supports exactly two statements: the option works end to end over the
tunnel, and on this sample Opus 5.5 buys no correctness for ~25 % more text.
Flipping the default would need the paired hard + easy gate at the repository's
power floor. Artifacts: `docs/measurements/r388/score-r442-opus55-{A,B}{,-j55}-easy.json`,
`docs/measurements/r442/paired-r442-opus55-{sonnet5,opus55}judge.json`,
`docs/measurements/r442/judge-cache-r442-wrapper-{sonnet5,opus55}.jsonl`.

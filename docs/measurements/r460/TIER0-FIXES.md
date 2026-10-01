# R460 Tier-0 fixes — what shipped in the worktree, what is blocked

The plan's Tier 0 was "measurement and transport first". Three of its five items
are now implemented and tested here; two are blocked on a credential or a live
run. Nothing was flipped.

## 1. Stage-2 primary deadline (engine)

`app/engines/_graph_rag_impl.py` — the wrapper Stage-2 call had **no explicit
timeout**, so it inherited the provider singleton's 60 s default. Evidence it was
about to bite: Opus's p100 turn was 46.2 s (inside the margin), and five
consecutive Sonnet generations crossed 60 s, which tripped the harness guard and
aborted a 37-row run at 28/37.

* New env `REGENOLD_STAGE2_WRAPPER_TIMEOUT_S` (default **150 s**), passed on both
  wrapper Stage-2 calls (the primary and the R417 degenerate-completion retry).
  The Bedrock leg has had the same treatment since R139
  (`REGENOLD_BEDROCK_STAGE2_TIMEOUT_S`, 180 s).
* Registered in `_engine_cache_key` (`app/routes/regenold.py`) — the R263.2 /
  R288.1 rule: a knob that can change whether a cached answer is the one this
  config would produce must be keyed.

## 2. Slow is not down (harness)

`evals/regenold/run_official_batch.py` — `assert_healthy` aborted whenever the
primary tripped five consecutive failures. On 2026-09-30 that threw away 9 rows
of Sonnet arm while the tunnel was answering ~7 s calls minutes later.

* `_primary_liveness_probe()`: one tiny PRIMARY call (`max_tokens=16`, 30 s
  budget, deliberately NOT the memoized preflight) asked before the abort. A
  probe that answers means the failure was latency, so the counter is reset and
  the run continues; a genuinely dead tunnel fails the probe and aborts exactly
  as before.
* Gated by `REGENOLD_BATCH_PROBE_BEFORE_ABORT` (default ON) so the old behaviour
  stays reachable.
* The R431 leg-awareness is untouched: a fallback-served row still continues
  loudly, and every degraded row keeps recording its own leg.

## 3. Usage and payload shape per dispatch (engine + row schema)

The board could not say what a Stage-2 call cost or which payload shape it sent.
Now every successful primary dispatch writes:

```
stage2_usage in=10175 out=192 system_chars=60643 user_chars=40700 turns=1
```

`_provenance` parses it onto the checkpoint row as `stage2_tokens_in/out`,
`stage2_system_chars`, `stage2_user_chars`, `stage2_history_turns` (fail-soft:
absent note -> absent keys; malformed fields dropped individually).

Why the sizes ride along with the counts: the wrapper's `usage` is
`round(len(user)/4.0)` — a character heuristic verified to the digit — and it
ignores the system stack entirely, so a bare token number is not interpretable.

## 4. Tests

**397 passed** across the touched surfaces (20 files):
`test_r460_stage2_usage_capture.py` (new, 4 tests: note lands on the row,
absent note adds no keys, malformed usage is fail-soft, the probe is wired and
defaults on), `test_r431_fallback_leg_guard.py`, `test_r417_stage2_leg_provenance.py`,
`test_r360_stage2_transport_policy.py`, `test_r365_raising_primary.py`,
`test_r360_12_verified_bug_fixes.py`, `test_r442_opus55_model_option.py`,
`test_r446_tracked_model_config.py`, `test_r411_stage2_full_system.py`,
`test_r415_single_turn_scope.py`, the five R449-R451 suites,
`test_r460_evidence_bundle.py`, `test_r112_perf_fixes.py`,
`test_r112_wrapper_cli_sentinel.py`, `test_complex_model_routing.py`,
`test_llm_providers.py`, `test_llm_round37_hardening.py`,
`test_r365_cf_access_host_pin.py`.

Lint is neutral: ruff error counts on both patched source files are unchanged
from HEAD (35 for the engine, 0 for the runner); the one new error this work
introduced (UP031) was fixed.

## 5. The wrapper, root-caused (read-only; outside this repo)

`D:/Claude Projects/claude-code-openai-wrapper/src/claude_cli.py`:

* `_forward_system_prompt_enabled()` — env `WRAPPER_FORWARD_SYSTEM_PROMPT`,
  **default OFF**; OFF passes `{"type": "text", ...}`, which claude_agent_sdk
  0.2.82 silently drops (the R282/R298 finding). The canary shows short and mid
  systems obeyed in this deploy, so **the gate is ON on the live wrapper**.
* When ON, systems under **30,000 chars** go inline as a `str` and systems at or
  above it spill to a temp file passed as `{"type": "file"}`
  (`--system-prompt-file`), because Windows caps a command line at 32,767 chars.
* The wrapper's own log (`service-stderr.log`, 12:44:19 and 12:44:38) records
  both of the R460 canary's long calls as
  `System prompt 60877 chars >= 30000 argv limit - passing via --system-prompt-file`.
  So the long system reaches the CLI for **both** models; the 3/3 vs 1/3
  obedience gap is model-side, not a delivery drop.

Bonus fact for the record: `CLAUDE_CODE_FAST_MODE` exists in the wrapper but is
**Opus-only by design** (the CLI's model gate ignores fastMode for Sonnet), so
"faster Sonnet" cannot come from fast mode.

## 6. Still blocked

* **Cohere quota** — the trial key 429s on `/v1/embed` and `/v1/rerank`; every
  live number in this round is an SVD-retrieval floor. Needs a rotated/raised
  key before the Tier-1 `density` gate and any re-baseline.
* **R450 `density` live paired gate** — ready to run the moment retrieval is
  real; offline evidence in `REBASE-R450-R451.md`.
* **R451 close-out** — record HOLD in its doc (title side flat; `bb0.5`/`bb0.6`
  beat `sparse` but not `shipped`).
* **Graded-shape coverage** — the capture instrument still replays `depth=0`
  (single-turn) draws; item 4 of the plan.

## 7. Files

Patched: `app/engines/_graph_rag_impl.py`, `app/routes/regenold.py`,
`evals/regenold/run_official_batch.py`; added
`tests/test_r460_stage2_usage_capture.py`; scripts and artifacts under
`docs/measurements/r460/` (`apply_tier0_transport_usage_capture.py`,
`apply_tier0_runner_probe_and_usage.py`, `fix_usage_note_fstring.py`,
`system_delivery_canary.py`, `system-delivery-canary.{jsonl,json}`).

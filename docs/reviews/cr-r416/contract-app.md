## New pushback-recovery branch calls `is_challenge_turn` without `has_prior_turns=True`, so most challenge phrasings never fire
- file: `app/routes/regenold.py:8449`
- bug: The new R372 branch sits inside `if history_turns:` and calls `is_challenge_turn(live_question)`. `live_question` is the bare last user message, with no `Latest question:\n` marker. In this same diff, `is_challenge_turn` gained a `has_prior_turns` keyword. When it is omitted, `prior_present` is worked out from that marker, so here it is always False. The function then returns False before `_CHALLENGE_PATTERNS` runs, and only the always-on explicit dispute markers can match. `tests/test_r416_audit_remediations.py:121-124` states the contract: "only a caller that passes the FLATTENED text (or the flag) can supply it". No production caller passes the flag.
- impact: A pushback that doesn't use an explicit dispute marker is not recovered. Examples: "We are exempt, correct?" and the leading-confirmation forms from R377. These turns fall through to the de-noiser or concatenation path, with the disputed answer text in the retrieval query. The only test, `tests/test_pushback_optimization.py:99-117`, uses "I don't think this is correct", which is an always-on marker. So it passes whether or not the flag is set, and the gap stays hidden.
- fix: Call `is_challenge_turn(live_question, has_prior_turns=True)`; the branch already knows prior turns exist. Add a test with a pattern-family pushback such as "We are exempt, correct?".
- confidence: 85

## The Bedrock de-noiser leg never trips the R91 truncation guard: Bedrock reports `max_tokens`, the loop checks for `length`
- file: `app/routes/regenold.py:8225` (provider at `app/routes/regenold.py:~7868`)
- bug: `_BedrockDenoiserProvider.complete` returns a `BedrockResponse` as-is. That object's `finish_reason` is the raw Converse `stopReason` (`app/llm/bedrock_client.py:650,658`), which is `"max_tokens"` when output is cut off. The de-noiser loop only checks `getattr(resp, "finish_reason", None) == "length"`, which is the OpenAI-shaped value. Nothing maps `max_tokens` to `length`: a grep finds no such normalisation, and `_graph_rag_impl.py:1875` checks `max_tokens` separately for the Anthropic path.
- impact: A truncated Bedrock rewrite that is 10–500 characters long skips both the new fall-through and the salvage path, and it becomes the retrieval query. This is the failure R91 and R380 were built to prevent: a query cut off mid-intent pulls retrieval off-topic and changes hard-mode turn 1. `record_query_denoiser(fired=True)` logs it as a success, so telemetry would not show it.
- fix: Map the stop reason inside the adapter, e.g. `if resp.finish_reason == "max_tokens": resp.finish_reason = "length"`. Or make the loop accept both values.
- confidence: 80

## `REGENOLD_DENOISER_MODEL_BEDROCK` changes the answer but is missing from `_engine_cache_key`, and the AST gate cannot see it
- file: `app/routes/regenold.py:8088`
- bug: The new Bedrock de-noiser model comes from `os.environ.get("REGENOLD_DENOISER_MODEL_BEDROCK", "eu.anthropic.claude-sonnet-4-6")`. The same diff registers the sibling flags `REGENOLD_DENOISER_BEDROCK` and `REGENOLD_DENOISER_TRUNCATION_FALLTHROUGH`, and `REGENOLD_DENOISER_MODEL` / `_GROQ` were already registered. The model variable is not; the only grep hit is the read itself. The R355 gate scans `app/engines`, `app/integrations/regenold`, `app/data` and `app/llm` (`tests/test_r355_cache_key_complete.py:32-35`), not `app/routes`, so it cannot catch this.
- impact: Changing the Stage-0 model changes the rewritten retrieval query, and so the answer and references. Cached responses from the previous model would be served. This breaks invariant #4 in AGENTS.md.
- fix: Add `"REGENOLD_DENOISER_MODEL_BEDROCK"` next to `REGENOLD_DENOISER_MODEL_GROQ` in `_engine_cache_key`. Consider adding `app/routes` flag reads to the gate's scan.
- confidence: 70

## The local-mirror sub-point fallback re-implements the pre-R409 shape and ignores the R409 fix (`_allocate_units`, point text)
- file: `app/engines/kg_context.py` (`_mirror_subpoints`; the fall-through at the end of `fetch_subpoint_detail`)
- bug: When the point-text query (ON, `_SUBPOINT_CYPHER`) fails, `fetch_subpoint_detail` falls through to `_mirror_subpoints(ids, max_units)`. That function:
  1. Returns only paragraph→point→**SubPoint** rows, which is the legacy query's shape. The index already holds every point's text in `point_by_id`, but bare Points, the whole purpose of R408/R409, are dropped.
  2. Fills greedily in ref order until `len(out) >= limit`. That is the single global budget R409 removed, because a long first provision evicts every later one. `_allocate_units` exists in the same module to share the budget and is not reused.
- impact: During an Aura timeout or open circuit, a single-turn ask silently gets the legacy block instead of the shipped point-text block. That is a different Stage-2 prompt, and so different wire references (invariant #5). The trace only says `kg_local_mirror_served`, so any A/B spanning an outage mixes the two query shapes without saying so.
- fix: Build the mirror rows in the same query shape the caller asked for. For ON, emit one row per Point with `coalesce(sub.text, point.text)` and a `ref_index`, then pass them through `_allocate_units(rows, max_units)`. Keep the SubPoint-only form for the legacy branch.
- confidence: 70

## The mirror also fires on healthy empty reads, not just on Neo4j failure
- file: `app/engines/kg_context.py` (`fetch_provision_hierarchy` / `fetch_subpoint_detail`, the `if rows and not getattr(rows, "failed", False)` guards)
- bug: The docstring says "in-process hierarchy mirror when Neo4j is offline/timed out". `_ReadRows.failed` exists to tell errors apart from empty matches. But both guards treat `[]` from a working graph the same as a failure. The legacy sub-point Cypher requires a `SubPoint`, and the live graph holds only 37. So on most multi-turn requests Aura legitimately returns `[]`, and the code then consults the mirror, which is built from `provision_hierarchy`'s regex parser rather than the seeded graph.
- impact: Wherever the local parser and the seeded Aura data disagree (for example after a parser change without a `SEED_VERSION` bump), the legacy multi-turn arm gets KG text the graph doesn't hold. That contradicts the R416 claim that the multi-turn path is "byte-identical to `REGENOLD_KG_POINT_TEXT=0`", and the served text is logged as a graph outage.
- fix: Fall back only when `getattr(rows, "failed", False)` is true, and return a healthy empty result unchanged.
- confidence: 60

## The emotion rescue checks the workplace patterns against the whole conversation, while every other check uses only the live turn
- file: `app/engines/_graph_rag_impl.py:3704`
- bug: The new rescue loop runs `topic["patterns"]` for `emotion_recognition_workplace` against `question`, which is the full flattened history. The gate just before it, `_detect_emotion_classification_inquiry`, and the main topic loop below it (`live = question.split("Latest question:", 1)[-1]`) both look only at the live turn. The same diff also widens those patterns with `staff|worker|workers|personnel|colleague...`.
- impact: In a multi-turn conversation where any earlier turn mentioned employees or staff, a live question such as "Does the Act prohibit emotion recognition in retail stores?" returns the curated Art. 5(1)(f) workplace-**prohibited** verdict instead of the general topic. Curated intercepts skip Stage-2, so the wrong verdict ships as-is.
- fix: Apply the same live-turn slice before matching, e.g. `live_q = question.split("Latest question:", 1)[-1]`, then `p.search(live_q)`.
- confidence: 65

## CLAUDE.md's `history_turn_count` mapping contradicts the route and the corrected code comment
- file: `CLAUDE.md` (the `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` flag-table row); code at `app/routes/regenold.py:8999-9002`, `app/engines/_graph_rag_impl.py:1008-1014`
- bug: CLAUDE.md says "a first ask reads **0**, one prior exchange reads **1**". The route computes `max(0, user+assistant messages - 1)`, so an ordinary follow-up (user/assistant/user) reads **2**. This diff corrected the impl comment to say exactly that ("2 for user/assistant/user … The ordinary follow-up therefore receives the capped system"), but the steering doc was not updated. The new KG gate (`history_turn_count <= 1`) uses the same predicate.
- impact: A reader of CLAUDE.md would think both R415 and R416 levers reach ordinary one-exchange follow-ups. They don't: those follow-ups get the capped system prompt and the legacy KG query. Any reach or effect-size reasoning based on the doc is off.
- fix: Update the CLAUDE.md row to 0 = first ask, 1 = two-message request, 2 = user/assistant/user, and say that ordinary follow-ups are excluded.
- confidence: 65

## The `REGENOLD_KG_MAX_REFS` readers still differ, and the new comment misstates the old ceilings
- file: `app/engines/graph_semantic.py:625`, `app/engines/kg_context.py:93-98`
- bug: The new comment says the readers had drifted to "24 in `graph_semantic`, 20 here" and calls the change "a ceiling, not a behaviour change". Before this diff `graph_semantic` clamped at **10** (`_int_env(..., 1, 10)`), so moving to 24 changes behaviour for values 11–24. The readers also still differ in kind: `kg_context` uses `_adaptive_int("kg_max_keywords", ...)`, but `fetch_focused_subprovisions` uses plain `_int_env`. With the HyPA router on, the two reads can return different `max_refs` for the same request, which is the drift the constant was meant to remove.
- impact: When the adaptive router is enabled, or when `REGENOLD_KG_MAX_REFS` is set to 11–24, the focused-subprovision layer and the keyword layers truncate the ref list at different lengths. That changes which provisions reach Stage-2, and nothing says so.
- fix: Use `graph_semantic._adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", 8, 1, _MAX_REFS_CEILING)` so it matches `kg_context`, and correct the comment.
- confidence: 60

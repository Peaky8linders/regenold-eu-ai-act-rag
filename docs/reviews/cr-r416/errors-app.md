## The Bedrock denoiser leg misses truncated rewrites: it checks for `length`, but Bedrock reports `max_tokens`
- file: `app/routes/regenold.py:8215` (HEAD), with the adapter at `app/routes/regenold.py:7868-7886`
- bug: The new `_BedrockDenoiserProvider` hands back the raw `BedrockResponse`. That response sets `finish_reason=stop_reason`, copied straight from Converse's `stopReason` (`app/llm/bedrock_client.py:650-658`). For a truncated completion Converse sends `"max_tokens"`, not `"length"`. The repo already knows this: the Anthropic/Bedrock Stage-2 path checks `stop_reason == "max_tokens"` (`app/engines/_graph_rag_impl.py:1873`). The denoiser loop only compares `getattr(resp, "finish_reason", None) == "length"`, so a truncated Bedrock rewrite is never caught. If it is 10-500 chars it passes the length check and is returned as the retrieval query with `fired=True`.
- impact: The R91 truncation guard and the new R377 fall-through are both skipped on the Bedrock leg. A rewrite cut off mid-sentence (the R380 failure: 5 of 9 multi-turn calls truncated) becomes the hard-mode retrieval query. The trace shows a successful rewrite, so nothing in `record_query_denoiser` reveals it.
- fix: Normalise in the adapter (`if resp.finish_reason == "max_tokens": resp.finish_reason = "length"`). Or compare `finish_reason in ("length", "max_tokens")` at the guard.
- confidence: 85

## Stage-0 denoiser calls through Bedrock can be counted as Stage-2 primary completions, which can fake the liveness check
- file: `app/routes/regenold.py:7877` (HEAD) → `app/llm/bedrock_client.py:1405` / `:1239-1256`
- bug: The adapter calls `complete_with_fallback`. When the whole Bedrock chain fails, that function calls `_try_wrapper_fallback`, which is default ON (`wrapper_fallback_enabled`, `bedrock_client.py:1173`). That hop calls `_s2pol.record_attempt(STAGE2_PRIMARY)` and `record_result(STAGE2_PRIMARY, ok=True)`. So a multi-turn query rewrite, which is not Stage-2 at all, increments `stage2_policy.transport_stats()` `primary_attempts` / `primary_ok`. When the hop fails, the chain then also dials the wrapper candidate a second time.
- impact: R398's `easyhard_ab` liveness guard and R413's `gate_validity` both read `primary_ok` to decide whether Stage-2 landed. A run where Stage-2 never landed, but a denoiser Bedrock call hopped to the wrapper, reads as live, which is the false green R398 fixed. `/healthz/llm` `stage2_transport` also over-counts. On a Bedrock outage, each multi-turn request pays for two wrapper calls.
- fix: Call `get_bedrock_provider().complete(...)` directly in `_BedrockDenoiserProvider`, or pass a flag that turns off the wrapper hop. The wrapper is already a separate, later candidate in the denoiser chain.
- confidence: 75

## When Neo4j fails, the local mirror quietly turns the point-text lever off and brings back the R408 budget starvation
- file: `app/engines/kg_context.py:826-837`, `:653-675`
- bug: In ON mode (single-turn), a failed or empty `_SUBPOINT_CYPHER` read falls through to `_mirror_subpoints`. That function only emits real SubPoints: it walks paragraph→point→subpoint and never emits a bare Point. That is the legacy shape, the one R416 measured returning 0 units for `rg_010`. It also fills one global `limit` in ref order, instead of sharing the budget across provisions the way `_allocate_units` does. The mirror emits nothing to show which query shape it is standing in for; the only trace is a `kg_local_mirror_served` note that looks the same in either mode.
- impact: During an Aura outage, circuit-open, admission saturation or timeout, single-turn requests quietly get the legacy block. The measured +8.0 pp ans_strict lever is off. A long first provision (Annex III, 24 rows) can use the whole budget and push out the Article point text, which is the R408/R409 defect on the fallback path. Also, an empty but successful Aura read now triggers the mirror too (`if rows and not failed` treats empty the same as failed), so the served block no longer matches the graph.
- fix: Make the mirror follow the query shape. In ON mode, also emit bare Points (`coalesce(sub.text, point.text)`) and run the result through `_allocate_units` using ref-index grouping. Only fall back when `rows.failed` is set, not when the result is merely empty.
- confidence: 75

## A single failure while building the mirror index turns the mirror off for the whole process
- file: `app/engines/kg_context.py:609-612`
- bug: Any exception inside `_mirror_index` sets `index = {}` and then caches it permanently (`_MIRROR_CACHE = index`). Examples: a transient import-order problem at boot, or a malformed node that raises `KeyError` on `node["id"]`. Every later call returns `[]`. The warning is logged once.
- impact: The R376 fallback (default ON) is dead until the process restarts, exactly when Aura is down. An outage then looks like "graph had nothing": the KG blocks come back empty with no further log line.
- fix: Only cache a successfully built index. On failure, leave `_MIRROR_CACHE = None`, or cache the failure with a TTL so it is retried.
- confidence: 65

## The postpositive negation regex suppresses a provision when the negated subject is a phrase that contains it
- file: `app/routes/regenold.py:5780-5787`, `:5815` (HEAD)
- bug: `_NEGATION_AHEAD_RE` is anchored at the end of the mention and skips any `(…)` groups. So it fires on "the exception in Article 5(1)(h) does not apply", "the derogation in Article 6(3) does not apply", and "a system listed in Annex III falls outside …". In each of these the negated subject is the noun phrase around the mention, not the provision itself. `_prose_mention_is_real_citation` then returns False, so `_prose_citation_bases` / `_add_prose_named_refs` (`:6021`, `:6035`) and the Post-Polish Grounding Guard (`:11216`) treat the provision as not cited.
- impact: A governing gold head is not promoted to the wire. Examples: Article 5 when its exception is ruled out, Article 6 when its derogation is ruled out, Annex III on a derogation answer. This is the asymmetric prose→refs error class CLAUDE.md § R398 lists as open, now in the opposite direction. Only a live `stage2_landed` run shows it, and this prompt-side guard change has no `gold_dropped_head` record.
- fix: Only suppress when the mention is the grammatical subject. For example, require that nothing but a sentence or clause start sits in the look-behind window: `(?:^|[.;:]\s*)(?:the\s+)?$` immediately before `Article N`. Or at least exclude mentions preceded by `in|under|of|listed in|referred to in`. Gate the change on `easyhard_ab`.
- confidence: 65

## CLAUDE.md gets `history_turn_count` wrong for a follow-up that has one prior exchange
- file: `CLAUDE.md` (the `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` flag row) vs `app/routes/regenold.py:8989-8992` and `app/engines/_graph_rag_impl.py:1011-1013`
- bug: CLAUDE.md says the route derives `max(0, user+assistant messages - 1)` and that therefore "one prior exchange reads 1". Under that formula, user/assistant/user (one completed prior exchange) reads **2**. The comment changed in this diff now says so, "**2 for user/assistant/user** … The ordinary follow-up therefore receives the capped system". So both the `<= 1` single-turn predicates, `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` and the new `REGENOLD_KG_POINT_TEXT_SINGLE_TURN`, send an ordinary follow-up down the multi-turn / legacy path.
- impact: Anyone reasoning from the steering file about which rows the two levers reach will be wrong: ordinary two-turn follow-ups are excluded, and only 1- or 2-message requests are treated as single-turn. That skews the reach ratio the R415 note says bounds board movement.
- fix: Update the CLAUDE.md row (and the R415 description) to say 0 for a first ask, 1 for a two-message request, and 2 or more for any real follow-up. If "one prior exchange" was meant to count as single-turn, change the predicate instead.
- confidence: 70

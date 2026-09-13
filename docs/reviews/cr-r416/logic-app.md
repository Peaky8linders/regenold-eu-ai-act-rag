## The challenge-recovery path runs the scope gate on the pushback turn alone
- file: `app/routes/regenold.py:8506` (consumed at `app/routes/regenold.py:8860-8876`)
- bug: The new R372 branch returns `self_contained_focus=True`. When that flag is True, the route runs `classify_conversation` on the last user message only. That message is the pushback ("I don't think this is correct. Perhaps your answer contains hallucinations."). The branch can only be reached when `not _live_turn_is_self_contained(live_question)`, so by construction that message has no AI-Act anchor or is too short to stand alone. The sibling paths that set this flag (R305 re-ask, R131/R133.1 de-noiser) set it only when the live turn *is* self-contained. The recovered `_root_q` never reaches the scope gate.
- impact: A pushback with no anchor, classified on its own, lands in the CONVERSATIONAL bucket. That hands it to the LLM scope gate, which fails soft to the generic decline when no LLM is available (CLAUDE.md R330). So a legitimate hard-mode dispute can get a Lexy refusal with zero references instead of a re-answer. To see it, send `[user: <Art. 6 question>, assistant: <answer>, user: "I don't think this is correct."]` and check `retrieval_path == "scope_refusal"`, or the scope trace.
- fix: Pass `False` for `self_contained_focus` on this branch. Alternatively, have the route run scope on `[prior root user turn, live turn]` or on `resolved_question` when the recovery fired.
- confidence: 75

## The recovered "root question" can be an older, unrelated turn
- file: `app/routes/regenold.py:8459-8470`
- bug: `_root_q` is the most recent prior user turn that passes `_live_turn_is_self_contained`, which keeps its default `require_anchor=True`. The comment says "from Turn 1", but the loop walks `reversed(dialogue[:last_user_idx])`. If the disputed question has no anchor (R380 measured 10/110 official questions like that, e.g. "Who is entitled to lodge a complaint …"), or has fewer than 6 words, or opens with a conjunction or coreference, it is skipped. The loop then picks an **earlier, different** question from the conversation. The `dialogue[0]` fallback only applies when no prior turn qualifies at all.
- impact: The engine gets `resolved_question = <wrong earlier question>`, and the Stage-2 prompt says "Target inquiry to answer: <wrong question>". In a multi-exchange conversation the pushback therefore re-answers a different topic, which is the history-bleed failure R380 fixed. It shows up as wire references from a prior topic on a pushback turn.
- fix: Take the user turn immediately before the disputed assistant turn, i.e. the last user message in `dialogue[:last_user_idx]`, whether or not it is self-contained. Or call `_live_turn_is_self_contained(..., require_anchor=False)`.
- confidence: 65

## The challenge-recovery early return skips the length caps its sibling path applies
- file: `app/routes/regenold.py:8483-8502`
- bug: The new branch returns before the tail of `_build_question_from_history`, so it skips processing the normal path performs:
  - the `max_chars` left-truncation of `question`, which preserves the `Latest question:` marker;
  - the `max_chars` clip of `resolved_turn`;
  - the 1000-char head clip of `system_context` (R315).

  Its `q_combined` holds the whole `history_block` plus the root question, with no bound. The R305 early return (the precedent) returns only a short tail as `question`, so for it this was harmless.
- impact: An uncapped system description and history reach the engine on this path only. That changes the Stage-2 prompt size and the classification detectors' input compared with every other multi-turn path. With a hostile or long payload the `REGENOLD_MAX_QUESTION_CHARS` bound is bypassed.
- fix: Assign `question` / `resolved_turn` / `_self_contained_focus` and fall through to the common truncation block instead of returning early. At minimum, apply `_max_question_chars()` and the `system_context[:1000]` clip before returning.
- confidence: 60

## The emotion rescue matches workplace patterns against the whole conversation, not the live turn
- file: `app/engines/_graph_rag_impl.py:3697-3703`
- bug: The new loop runs `p.search(question)` on the full flattened text. Its gate, `_detect_emotion_classification_inquiry` (`_graph_rag_impl.py:5476-5480`), strips to the text after `Latest question:\n`. The sibling topic loop just below uses `live`, which is stripped the same way. The pattern's `[\w\s\-,]{0,40}?` gap also matches across newlines. So a prior turn such as "we use emotion recognition for our staff" selects `emotion_recognition_workplace` for a live question about shoppers or patients. Before this change the branch always returned the general topic.
- impact: The wrong curated answer ships: "prohibited under Article 5 … workplaces", with refs `Art. 5, Annex III, Art. 50`. This is the answer for a non-workplace emotion-recognition question whenever earlier turns mention employees or staff. Pinned test coverage is single-turn only.
- fix: Search the live turn, using the same `rfind("Latest question:\n")` slice the detector uses, before matching the workplace patterns.
- confidence: 70

## The widened workplace pattern gives a prohibited verdict for patient- and customer-facing uses
- file: `app/engines/_graph_rag_data.py:1007` and `app/engines/_graph_rag_data.py:1012`
- bug: `staff|personnel|colleague(s)|call centre` were added to the alternation, and a 40-char window is enough to match. "emotion recognition used by hospital staff to detect patient distress" and "emotion detection on customers calling our call centre" now both hit `emotion_recognition_workplace`. Article 5(1)(f) covers inferring the emotions of persons *in* the workplace, i.e. the workers, and has a medical/safety carve-out. It does not cover a system that staff operate on patients or customers. This is the same keyword-overreach shape R410 fixed for Art. 5(1)(g) and `medtech_triage`.
- impact: The curated answer for these questions says the use is prohibited under Article 5, which is legally wrong. It also skips Stage-2 polish if the intercept is authoritative.
- fix: Require the subject of the emotion inference to be the worker. For example, drop `staff|personnel|call centre` from the bare alternation, or require the word "employee/worker" in the window, or exclude `patient|customer|caller|client` in the same window.
- confidence: 60

## During an Aura failure, single-turn requests fall back to the legacy sub-point shape without budget sharing
- file: `app/engines/kg_context.py:826-837` (mirror at `app/engines/kg_context.py:654-675`)
- bug: On the R409 (single-turn) branch, a failed or empty Aura read falls through to `_mirror_subpoints`. That function returns only SubPoint rows, which is the pre-R408 legacy shape: bare Points are never emitted. It fills `limit` provision by provision (`if len(out) >= limit: return out`) instead of `_allocate_units`' round-robin. So in fallback, the modality lever silently reverts to the legacy query, and the R408 "first provision evicts the rest" defect comes back. Separately, an Aura *success* with 0 rows also reaches the mirror and records `kg_local_mirror_served`, which misattributes an ordinary empty match.
- impact: During an outage or circuit-open, single-turn Stage-2 prompts lose the point text that R416's gain depends on (`rg_010` / `rg_045`). The trace does not show that the query shape changed.
- fix: Add a point-level mirror (units per point, including bare points, with `ref_index`). Pass its rows through `_allocate_units` on the ON branch. Only consult the mirror when `rows.failed` is True, not when a successful read returned empty.
- confidence: 60

## CLAUDE.md says the wrong turn count for one prior exchange; the code and its own comment disagree
- file: `app/engines/_graph_rag_impl.py:1011-1013` vs CLAUDE.md flag rows `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` / `REGENOLD_KG_POINT_TEXT`
- bug: The route computes `max(0, user+assistant − 1)` (`regenold.py:8999-9001`), so user/assistant/user reads **2**. The corrected in-code comment says so: "the ordinary follow-up therefore receives the capped system". CLAUDE.md still says "one prior exchange reads **1**" and describes the differ-set `{0, 1}` as covering first asks plus one prior exchange. It also describes the KG lever's ON regime as "single-turn asks" as if follow-ups were included.
- impact: An operator or agent reading CLAUDE.md will assume an ordinary one-exchange follow-up gets the full system prompt and KG point text. Under both `<= 1` predicates it gets neither, so any measurement or gate framed on the documented predicate describes the wrong population.
- fix: Update the two CLAUDE.md rows: a first ask reads 0, a two-message request reads 1, and user/assistant/user reads 2 and is treated as multi-turn. Or, if follow-ups were meant to be in scope, change the predicate to count prior *exchanges*.
- confidence: 70

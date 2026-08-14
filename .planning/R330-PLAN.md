# R330 — Ranked, buildable implementation plan

**Input:** R329 attribution over 38 judged HARD rows (128 wire refs, 55 judged wrong across
28 rows, 14 answer failures, 8 faithfulness failures). Every finding below survived an
independent adversarial verification pass; where the verifier corrected the finding, **the
corrected claim is what is planned here**, not the original title.

**Read first:** `AGENTS.md` (Closed Directions), `.planning/R318-PLAN.md` §1 (five dead
families) and §3 (the gate stack), `docs/R329-SCORECARD-VS-FRONTIER.md` §5.

---

## 0. Ranking model

`Overall` is a **geometric mean** of 8 axes, so `∂Overall/∂axis ∝ 1/axis`. Leverage of
closing a gap is therefore `gap / axis`:

| axis | ours (HARD) | gap to frontier | leverage `gap/axis` |
| --- | --- | --- | --- |
| **Ans Strict** | 60.6 | −24.2 | **0.399** |
| **Speed** | 61.7 | −23.5 | **0.381** |
| Ref Strict | 56.0 | −18.1 | 0.323 |
| Ans Loose | 74.0 | −18.1 | 0.245 |
| Ref Loose | 78.7 | −15.9 | 0.202 |
| Ref Conciseness | 72.1 | −7.0 | 0.097 |
| Tone | 98.2 | −1.8 | 0.018 |
| **Ans Conciseness** | **93.4** | **+1.2 (we lead)** | **protect — pure downside** |

Rank = `leverage × confidence ÷ risk`. Note **Ref Strict 56.0 is the lowest absolute axis**,
so per-point it is nearly as valuable as Ans Strict — a fix that moves Ans Strict *and*
Ref Strict at once outranks anything that moves one.

**Ranking rule applied throughout:** a fix that is *simultaneously* Ans-Strict-positive,
Ref-positive and Ans-Conciseness-**positive** (shorter answers) outranks a bigger single-axis
fix, because it cannot trade the one axis we lead.

### Default-ON policy (the R308/R299 rule, applied literally)

> `DEFAULT ON` is permitted **only** when the change is provably **output-identical on every
> live row** — i.e. pure waste removal or non-consumed data. Anything that can change a
> shipped answer or a shipped reference ships **DEFAULT OFF** with a named flip criterion,
> even when the offline evidence is strong.

Six fixes below qualify for default ON. Everything else is default OFF, with the gate that
must be green before the flip named explicitly.

---

## 1. Headline

Three single-row engine-detector fixes (§3.1, §3.2, §3.3) are all deterministic,
offline-reproducible, davidath-neutral **by construction**, and each is positive on
Ans Strict, Ref precision **and** Ans Conciseness at the same time. Together on the R329
judged arm they are worth, by deterministic replay:

* **answer_correctness 25/40 → 28/40** (0.625 → 0.700) — fixes july7-299, july7-265, july7-259
* **citation_faithfulness 32/40 → 34/40** (0.800 → 0.850)
* **wrong refs 55 → ~43** (−22%), **mean refs 3.37 → ~3.1**
* **answers SHORTER on all three rows** (621→373, 378→103, 1562→330 chars)

That is the whole cheap prize. Everything after §3.3 is smaller, riskier, or a measurement.

**Speed is honest about itself:** the code fixes in §4 are worth ~1–2 Speed points. The
−23.5 pp gap is a **transport floor** (§7), not configuration. Do not oversell §4.

---

## 2. ZERO-RISK tier — ship now, no A/B, no gate stack

These change no shipped answer and no shipped reference, or change no scored surface at all.
**Ship each as its own commit** so a future bisect over an axis regression does not have to
step over an inert diff.

### Z1 — Lexy UI tooltips contradict the Act (`app/web_ui.py:1591`, `:1593`)

* `:1593` `articlesSummary["Annex III"]` names points **1, 2, 3, 4, 6** — omits point 5
  (essential private/public services), 7 (migration/asylum/border) and 8 (justice and
  democratic processes). Live graph confirms `annex_III_1 … annex_III_8`.
* `:1591` labels **Article 52** as the transparency article. In Reg. (EU) 2024/1689 Art. 52
  is the GPAI-systemic-risk **classification procedure** (`app/data/kb.py:1269`); transparency
  is Art. 50 (`kb.py:876`). This is 2021-draft numbering.
* **Not on the answer path.** `articlesSummary` is browser-side JS inside `HTML_TEMPLATE`,
  read only at `web_ui.py:2193` for a citation-card tooltip. Not imported, not in
  `kb_search`, not in `article_existence.py`.
* ⚠ It is a **decoy**: its five-category list is the same five, in the same order, as
  july7-147's answer. Fix it so the next investigator does not misattribute.

**Gate:** ENV — none. **Default:** unconditional. **Test:** none needed; verify `GET /app`
renders and the tooltip populates. **R318 §3 gate:** n/a (zero scored surface).

### Z2 — `render_kg_context` emits `point (None)` (`app/engines/kg_context.py:711`)

`f"point ({sp.get('letter')})"` prints literally `point (None)` when a SubPoint has no parent
Point letter — **39 occurrences across 7 of the 15 captured failing Stage-2 prompts**,
including july7-221's `Article 5, paragraph 1, point (None), subpoint (ii)`, which is exactly
the objective the judge says that answer misstated.

```python
coordinate = f"{sp.get('cite')}, paragraph {sp.get('para')}"
letter = str(sp.get("letter") or "").strip()
if letter:
    coordinate += f", point ({letter})"
```

**Gate:** ENV — none (correct-by-construction). **Default:** unconditional.
**Test:** `tests/test_kg_context_coordinates.py` — assert a subpoint row with `letter=None`
renders `…, paragraph 1, subpoint (ii)` and never contains the substring `(None)`.
**davidath:** neutral **by construction** (bench has no Neo4j; kg_context feeds the Stage-2
prompt only, and Stage-2 never runs under `P2P_GRAPH_RAG_PROVIDER=cli`).
**R318 §3 gate:** none required. It changes prompt bytes on live only, and only from wrong
to right; if paranoid, `easyhard_ab` would show it, but it does not warrant an A/B slot.

### Z3 — `fetch_deontic_context` ships a Cypher it can never execute (`app/engines/kg_context.py:415`)

`_DEONTIC_CYPHER` ends `LIMIT $limit` (`:233`); the caller passes `{"ids": ids}` (`:415`).
Live Aura returns `Neo.ClientError.Statement.ParameterMissing`. `GraphClient.execute_read`
(`app/graph/client.py:191-203`) swallows it and returns `[]`; `_bounded_execute_read` takes its
**success** branch and calls `record_graph_success()` — so the failure is invisible to the
circuit breaker *and* to telemetry, and the empty result is memoized. The
`KNOWLEDGE-GRAPH REGULATORY CLASSIFICATION` block (`:744-750`) has **never rendered in
production**, despite `REGENOLD_KG_CONTEXT` defaulting ON. Measured cost: **130–158 ms of
wasted Aura round-trip, once per request** (memoized after the first call).

⚠ **Fixing the parameter alone is NOT zero-risk** — it turns a dead block live and injects
Annex-III category labels, operator roles and Art. 113 application dates (which name
`Annex I`, `Article 4`, `Article 5` in prose) into the prompt on rows that retrieved none of
them. That is a live over-citation vector on **Ref Conciseness, the axis we are losing**.

**Therefore split it:**

* **Z3a (zero-risk, ship now):** gate the *call* at `kg_context.py:727` on
  `REGENOLD_KG_DEONTIC`, **DEFAULT `0`**. With the gate off the block still renders nothing
  (identical to today) but the wasted round-trip disappears. Fix the parameter in the same
  commit so the query is correct when someone flips it: `{"ids": ids, "limit": limit}` with
  `limit = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 20)`
  (reuse `max_refs`, already computed at `:406` — **not** `max_units`; the query emits one row
  per article, capped by refs). Fold `limit` into the cache key at `:411`:
  `f"de:{','.join(ids)}:l{limit}"`.
* **Z3b (deferred, §6):** enabling the render.

**Test:** `tests/test_cypher_param_coverage.py` — for every module-level `*_CYPHER` constant in
`app/engines/kg_context.py` and `app/engines/graph_semantic.py`, assert
`set(re.findall(r"\$(\w+)", cypher)) <= set(params)` for the params its `fetch_*` passes.
This is the class of bug ("a Cypher constant drifted from its single call site"); 1 of 6
constants is currently broken. It survived because `tests/test_r326_kg_context_additions.py:40-63`
monkeypatches `_bounded_execute_read` and therefore never binds a parameter.

**Also ship, same commit:** make `Neo.ClientError.Statement.*` re-raise (or add an
`execute_read_strict`) so a malformed query records a **failure**, not a success. Today a code
bug is indistinguishable from an empty match.

**davidath:** neutral **by construction** (no Neo4j on the bench). **R318 §3 gate:** none —
output is byte-identical with the gate off.

### Z4 — stale comment (`app/routes/regenold.py:9012`)

The comment says `adaptive_ref_clamp` is "Default OFF (REGENOLD_ADAPTIVE_REF_CLAMP)". Line
`4114` reads `os.getenv("REGENOLD_ADAPTIVE_REF_CLAMP", "1")` — it is **default ON**. Two
separate verifications tripped over this. Comment-only edit.

### Z5 — record the newly refuted families in `.planning/R318-PLAN.md` §1

Add rows **#6** and **#7** to the dead table (details in §8), plus the two counterexample row
ids and the new **method rule** (§8.1). This is the artifact that stops R331 rebuilding them.

---

## 3. TIER 1 — behavioural, davidath-neutral BY CONSTRUCTION, offline-reproducible

All three are **engine detectors that fire on 1 row each** and were reproduced byte-identically
offline under `OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli
REGENOLD_EXTERNAL_EMBEDDINGS=0`. All three **shorten** the answer.

---

### 3.1 — RANK 1 · `_detect_risk_framework_inquiry` is unanchored `.search()`

**File:** `app/engines/_graph_rag_impl.py:3407`
**Axes:** Ans Strict ↑, Ref Strict ↑, Ref Conciseness ↑, Ans Conciseness ↑, Speed ↓ (1 row)
**Confidence:** high (two independent verifications, deterministic replay). **Risk:** very low.

`_RISK_FRAMEWORK_TAXONOMY_RE` (`:3375`) is END-anchored on `\s*[?.]?\s*$` but has **no start
anchor**, and `:3407` applies `.search()`, not `.match()`. The comment at `:3369-3374` claims
the end anchor makes it fire "ONLY when risk categor|tier|level|class is the OBJECT of the
question" — that reasoning covers a *trailing system noun*, not a specific-system question
whose **final clause** is a bare taxonomy ask.

july7-299 — *"Does the EU AI Act classify AI systems used for irregular migration, and if so,
under which risk category?"* — matches at span (86,106) on a 20-char tail behind an 86-char
prefix. Two default-ON consequences fire off that one predicate:

1. **Engine intercept** (`:4806`, ungated) seeds the canned 11-ref taxonomy pack at `:4828`
   `["Art. 5","Art. 6","Annex I","Annex III","Art. 50","Art. 51","Art. 52","Art. 53","Art. 54","Art. 55","Art. 56"]`.
   `_seed_classification_obligations` (`:2870`) **replaces** `context.obligations` (`:2895`) and
   clears `context.article_info` (`:2900`), so the genuine Annex III point 7 migration retrieval
   is **destroyed**, not diluted. It also makes `_is_curated_authoritative_intercept` (`:4464`)
   True, so the Stage-2 skip at `:7889` ships the generic four-tier blurb — an answer to a
   question that was not asked (sidecar: `stage2_polish false`, `latency_ms 207`).
2. **Route re-instatement** `_enforce_risk_framework_refs` (`regenold.py:3337`, canon `:3325`,
   call `:9057`, `REGENOLD_RISK_FRAMEWORK_REFS` default ON) re-appends canon members that
   intervening lossy passes dropped. Measured contribution: 5 refs of the 11 (it never
   fabricates — `:3365-3366` skips anything the engine did not surface).

**Impact:** 9 of that row's 11 refs are judged wrong = **9 of the 55 wrong refs in the entire
run (16.4%) from one row**. It is also the `max 11 references` row flagged in
`R329-SCORECARD-VS-FRONTIER.md` §4 against the rules PDF's "minimal set". Its answer is a
judged **fail** ("omits specific Annex III point 7(b)").

**Code change** (one line, a pure narrowing — it cannot introduce a new firing):

```python
# app/engines/_graph_rag_impl.py:3407
if not _risk_framework_anchor_enabled():
    return bool(_RISK_FRAMEWORK_TAXONOMY_RE.search(raw_q))
m = _RISK_FRAMEWORK_TAXONOMY_RE.search(raw_q)
return bool(m) and not raw_q[: m.start()].strip()
```

Use **this** predicate, not the negative-lookahead / use-case-keyword variant from the second
finding: it is strictly narrower, has no hand-tuned keyword list, and cannot become a
classifier ("a hand-tuned classifier is not a rule" — R318 §4).

**ENV GATE:** `REGENOLD_RISK_FRAMEWORK_ANCHOR` — **DEFAULT `0` (OFF)**.
Register in `_engine_cache_key` (`app/routes/regenold.py:1207`) — it changes engine behaviour.

> Default-ON is *arguable* here (strictly narrowing, davidath byte-identical by construction,
> both judge-correct refs survive the replay) and this is the only candidate in the plan where
> that argument exists. It still ships OFF: the **live** post-fix answer is unmeasured, and
> shipping default-ON with the gate un-run is the R308/R299 mistake.

**Measured outcome (deterministic replay, both verifiers independently):**
refs `[11] → ['Annex III', 'Art. 6', 'Art. 27']`. Both judge-CORRECT refs retained
(Article 6, Annex III), all 9 judge-wrong refs removed, one new unjudged ref (Article 27 —
the FRIA duty for public-sector deployers of Annex III systems, legally plausible but it
could itself score as an over-cite). Answer **621 → 373 chars**, and it *gains* the exact
content the judge marked missing ("assess asylum or visa applications, predict migration
risks … high-risk under Annex III"). So it plausibly repairs the answer failure too.

**Unit test:** `tests/test_r330_risk_framework_anchor.py`
* `_detect_risk_framework_inquiry("What are all the risk categories in the EU AI Act?")` → True (prefix `''`)
* `_detect_risk_framework_inquiry(<july7-299 question>)` → False
* the taxonomy regex still matches the july7-299 tail (proves it is the ANCHOR doing the work, not a regex edit)
* corpus assertion: 0 fires across the 137 davidath QA + 339 scenario strings, **before and after**

**davidath:** neutral **BY CONSTRUCTION.** The parent regex is 0-fire-verified on 137 QA + 339
scenarios; a strictly narrower predicate cannot rise above 0.
**R318 §3 gate that would catch a regression:** `sim_gate.py` (`gold_dropped == 0`) — this
removes 9 refs from one row, so gold protection is the exposure. Then `holdout.py`
(`governing_dropped == 0`) and the 276-runner. `easyhard_ab` is the flip criterion.
**Known cost:** the row moves from the 207 ms intercept to the ~57 s Stage-2 path — a Speed
cost on 1 of 40 rows. Accept it; the Ans-Strict + Ref gain dominates on the geometric mean.

---

### 3.2 — RANK 2 · the R275 definitional skip fires where its emitter cannot

**File:** `app/routes/regenold.py:6791` (preferred) / `app/engines/_graph_rag_impl.py:7916`
**Axes:** Ans Strict ↑, Faithfulness ↑, Ans Conciseness ↑ (378 → 103 chars). **Speed:** neutral.
**Confidence:** high (3-arm controlled deterministic experiment). **Risk:** low.

`_two_stage_generate:7908` skips Stage-2 whenever `_detect_pure_definitional_inquiry` is True,
justified in the comment at `:7899-7907` by the claim that *"the deterministic definitional
path ships the FULL verbatim Article 3 definition"*. The only code that ships that definition
is `_try_extractive_answer` (`regenold.py:2145`, definition branch `:2212`), and its call site
at `:6797` is guarded by `and not _is_multiturn` (`:6791`). **Every HARD July-7 row is
multi-turn by construction** (`evaluator_batch_july7.pushback_messages()` always emits
`[user, assistant, user]`). So on the HARD split the skip fires, the emitter is skipped, and
what ships is the Article-3 **KB summary**.

Isolation proof (three arms, same content, provider=cli, zero LLM):

| arm | user msgs | emitter | shipped |
| --- | --- | --- | --- |
| A: turn-1 only | 1 | **called** | 103 ch verbatim `'risk' means the combination of the probability of an occurrence of harm and the severity of that harm;` |
| B: the runner's real 3-message pushback | 2 | **never invoked** | 378 ch `Defines 68 terms used in the Regulation, including 'AI system'…` — byte-identical to the shipped judged answer |
| C: same content, first user turn removed | 1 | **called** | the correct 103 ch definition |

Arm C isolates `not _is_multiturn` as the **sole** blocking guard — the six sibling guards
(`_is_scenario`, `_is_scenario_shape`, `_is_classification_topic`, `_is_curated_intercept`,
`_is_general_verdict`, `_stage2_landed`) are all False, or arm C would also have been blocked.

**Impact:** july7-265 is the run's **only zero-correct row** (`ans.correct == 0`,
failure_mode *"answer does not state the definition of 'risk'"*) and one of the 8 faithfulness
failures (*"cite-and-mismatch: Article 3.2 defines risk but answer describes definitions list"*).
Refs are **identical** (`['Article 3.2']`) in all three arms, so no reference moves.

**Population correction:** the detector fires on 3 of 111 hard conversations, but only **2
degrade**. july7-133 ("testing data") is byte-identical across arms — no defect. july7-149
("deep fake") degrades **worse** than 265: single-turn ships the 210-char verbatim Art. 3(60)
definition, multi-turn ships 1289 chars of generic Article 50 prose. Only july7-265 is in the
38-row judged sample.

**Code change — ship the ROUTE variant, not the engine variant:**

```python
# app/routes/regenold.py:6791  (definition branch only)
and (not _is_multiturn or _definitional_multiturn_emit_enabled())
```

**Why not the engine variant.** The finding's primary proposal — replace `return kg_answer,
False` at `_graph_rag_impl.py:7916` with `select_definition_sentence(resolved_q)` — is **NOT
davidath-inert**, contrary to the finding's own risk note. Measured: `_two_stage_generate` *is*
invoked under `provider=cli` (3 calls/request), `_detect_pure_definitional_inquiry` fires on
**4 of the 137 davidath QA questions**, and one of them ("Who is considered a 'provider' of an
AI system?") currently ships the 68-terms summary on the wire — so the engine variant changes
a deterministic bench row. The route variant **cannot** change davidath: every davidath request
is single-turn, so `_is_multiturn` is always False and the new disjunct is never reached.

**ENV GATE:** `REGENOLD_DEFINITIONAL_MULTITURN_EMIT` — **DEFAULT `0` (OFF)**.
No `_engine_cache_key` registration needed — this is route-level, downstream of the cached
engine call (R79 doctrine, same as `REGENOLD_QA_REF_BUDGET`).

**Unit test:** `tests/test_r330_definitional_multiturn.py`
* 3-message pushback for july7-265 with the flag ON → answer contains
  `"the combination of the probability of an occurrence of harm"`, refs `== ["Article 3.2"]`
* same request with the flag OFF → today's 378-char summary (proves the gate)
* single-turn arm is byte-identical with the flag ON and OFF (proves no collateral)
* assert `_is_multiturn` is the only differing guard (arm-C reproduction)

**davidath:** neutral **BY CONSTRUCTION** (single-turn ⇒ `_is_multiturn` always False).
**R318 §3 gate:** the 276-runner + OOS probe (multi-turn coherence is the exposure — check
`20/20 coherent` holds), then `easyhard_ab`. `sim_gate` cannot score it (references unchanged).
**Watch:** `_definitional_art3_protected` (`regenold.py:3287`) must still keep `Article 3.2` on
the wire once the prose becomes a bare one-sentence definition, since
`_reconcile_references_to_prose` runs on the prose.

---

### 3.3 — RANK 3 · emotion-recognition gate/emitter divergence

**File:** `app/engines/_graph_rag_impl.py:4448` + `app/engines/_graph_rag_data.py:838`
**Axes:** Ans Strict ↑, Faithfulness ↑, Ref precision ↑ (5→3 refs, 2/5 → 3/3),
Ans Conciseness ↑ (1562 → ~330 chars), **Speed ↑** (57 s → 0.2 s on that row).
**Confidence:** high (positive control: monkeypatching the predicate emits the curated text
verbatim). **Risk:** medium — this is the only Tier-1 fix that changes curated *content*.

`_detect_emotion_classification_inquiry` (`:3687`, regex `_EMOTION_RECOGNITION_RE` at `:3676`)
is a disjunct of `_is_curated_authoritative_intercept` (`:4422`, `return (` at `:4448`), so
`_two_stage_generate:7889` **skips Stage-2** on the stated ground that the curated emotion
cross-tier verdict is "authoritative and complete". But the emitter of that verdict,
`_detect_classification_topic` (`:2636`), short-circuits on
`if not _is_classification_question(question): return None`. On july7-259
(*"Does the EU AI Act prohibit all AI systems for emotion recognition …? If not, specify …"*)
that returns **False**, so the curated `emotion_recognition_general` topic
(`_graph_rag_data.py:827-838`) — whose text is correct and exactly on point — is never emitted.
Stage-2 is skipped anyway and `_deterministic_answer` falls through to the generic QA dump
about **RBI**, which is what shipped (reproduced byte-identically, 1562 chars, zero diff hunks).

Judge: `ans` fail (correct 5 / unsupported 3 / missing 4, *"answer never addresses
emotion-recognition prohibition scope (Art 5(1)(f) workplace/education, medical/safety
exception) … discusses unrelated RBI and transparency provisions instead"*), `faith` fail
(*"Article 5(1)(f) cited but its actual content is never described"*), 3 wrong refs
(Article 5, Article 27, Article 49).

**Root cause is one level higher than the finding stated.** `_CLASSIFICATION_QUESTION_RE`
(`:2418-2427`): the `(?:does|do)` branch at `:2426-2427` admits only
`fall under|fall into|fall within|still apply|apply to|count as|qualify as`. It carries **no
prohibition or risk-tier predicate**, so "Does the EU AI Act … *prohibit* …" is read as a
description.

**Two candidate fixes — ship the SCOPED one:**

* ❌ **Widening `_CLASSIFICATION_QUESTION_RE`** (adding `prohibit|ban|forbid|allow|permit|classify`
  to the `does|do` branch) works, but that regex is a **globally-used gate** — it is not
  davidath-neutral by construction and would need the full 476 plus the whole gate stack for a
  one-row win.
* ✅ **Scoped variant:** move the emotion branch out of the `_is_curated_authoritative_intercept`
  OR-chain and give `_detect_emotion_classification_inquiry` its own emitter that returns
  `_CLASSIFICATION_TOPICS["emotion_recognition_general"]` directly, bypassing
  `_is_classification_question`. 0-fire on davidath by the same R144 argument already recorded
  in the module comment at `:3664-3675` (**verify with the R120 fast method** — grep the 137 QA +
  339 scenario strings for `emotion\s+(recognition|inference|detection)`; 0 hits ⇒
  byte-identical).

**MANDATORY companion edit — do not ship the gate fix without it.**
`_graph_rag_data.py:838` currently reads `["Art. 5", "Annex III.1.c", "Art. 50.3"]`. As-is the
fix would **drop `Article 5.1.f`** — a ref the judge marked **CORRECT** on this row — and
reinstate bare `Article 5`, which the judge marked **WRONG** ("redundant/over-broad parent
article"). Change `"Art. 5"` → `"Art. 5.1.f"`. With that edit the row goes **2/5 → 3/3**
precision.

**ENV GATE:** `REGENOLD_EMOTION_CURATED_EMIT` — **DEFAULT `0` (OFF)**.
Register in `_engine_cache_key` (`regenold.py:1207`).

**Unit test:** `tests/test_r330_emotion_gate_emitter.py`
* **parity test (the general lesson):** for every disjunct of `_is_curated_authoritative_intercept`
  whose payload comes from `_CLASSIFICATION_TOPICS`, assert
  `_is_curated_authoritative_intercept(q) implies _detect_classification_topic(q) is not None`.
  This test would have caught both this defect and §3.2.
* july7-259 question with the flag ON → answer contains "workplaces and educational
  institutions" and "medical/safety exception"; refs `== ["Article 5.1.f","Annex III.1.c","Article 50.3"]`
* 0-fire assertion over the davidath corpus

**Collateral check already done:** across the 38 judged rows july7-259 is the **only** row where
the emotion detector fires. The four other curated-True/topic-None rows (july7-129 retention,
-175 deviation, -191 tech-doc, -197 special-data) have emitters **outside** `_CLASSIFICATION_TOPICS`,
so the narrowing touches none of them.

**davidath:** neutral **BY CONSTRUCTION** *conditional on the 0-fire scan* — run the R120 scan
first; if it returns >0 hits, escalate to the full 476.
**R318 §3 gate:** `sim_gate` (drops 2 refs) → `holdout` → 276-runner. Flip on `easyhard_ab`.
**Residual risk:** R144's docstring warns that Opus polish "collapses the emotion cross-tier
verdict to Article-5-only"; the scoped variant avoids Stage-2 entirely on that row, so that
warning does not apply — but confirm `stage2_fidelity.guard_cross_tier_polish`
(`_graph_rag_impl.py:7997`) is not depended on for this row.

**Free side-observation (log it, do not act):** the raw deterministic answer's **lead sentence**
(the Art. 5 eight-practice enumeration) already contains "(f) emotion-inference in workplaces
and educational institutions (narrow medical / safety exception)" — the exact missing content.
`normalise_answer_for_regenold` drops that lead sentence. The QA-dump path was one sentence
away from partial responsiveness.

---

## 4. TIER 2 — Speed, provably output-identical (DEFAULT ON permitted)

Both are the same defect in two modules: a **3.0 s budget against a 12–17 s wrapper floor**.
This repo already documents the shape at `app/routes/regenold.py:5859-5860` — the denoiser's
fast providers "succeed well before the slow ~10 s wrapper candidate is ever reached", same
model (`claude-haiku-4-5-20251001`), same 3.0 s budget, "which the fail-fast per-provider
timeout below **always times out on**". Both call sites below fall back to a deterministic
extractor on failure, so **the output is provably unchanged**.

### 4.1 — `frames_rewriter` (`app/engines/frames_rewriter.py:51`)

`_TIMEOUT = 3.0` (`:38`), consumed at `:66`; gate at `:51` is `is_openai_wrapper_enabled()` only
— **no provider chain, no circuit breaker** (grep `_BREAKER` across `app/engines/` and `app/llm/`
hits only `clara_logic.py:662` and `intent_classifier.py:396`). Both failure branches (`:68-74`)
return `sub_query` unchanged. Caller `_graph_rag_impl.py:8294-8295`, parallel on the shared
`suffctx` executor (`:8306-8315`), so cost is 3.0 s **once per firing row**, not per sub-query.
Fires on ≤ 18 of 38 rows (`decompose_question >= 2 clauses`; that is a **ceiling**, not a floor —
`sufficient_context.py:298-309` `_live_section` deliberately scans only the live turn).

Its sibling on the same path, `frames_planner.decompose_question_llm`, already routes through
`_resolve_intent_provider()` (`frames_planner.py:61`) and therefore lands on Groq. `frames_rewriter`
is the lone caller that was never migrated.

```python
# app/engines/frames_rewriter.py:51
if not _frames_rewriter_wrapper_allowed():
    return sub_query
if not is_openai_wrapper_enabled():
    return sub_query
```

**ENV GATE:** `REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER` — **DEFAULT `0` (skip)**. Default ON for
the *skip* is legitimate: it is pure waste removal, retrieval-neutral by construction.

⚠ **Do NOT also route it to the fast chain this round.** With `GROQ_API_KEY` set the rewrite
would **succeed for the first time**, altering sub-query phrasing and therefore retrieval on the
14–18 firing rows — which overlap the over-citation population under study. That is a separate,
retrieval-MOVING change gated on `easyhard_ab`.

### 4.2 — `clara_logic` (`app/engines/clara_logic.py:775`)

`timeout_seconds=_LLM_TIMEOUT_SECONDS` (`:627` = 3.0). `analyse()` (`:1403-1405`) tries
`extract_tags_llm` then falls back to `extract_tags_deterministic`. `extract_tags_llm` goes
through `get_openai_wrapper_provider()` **only**. Called at `regenold.py:7227` — **after** the
engine has produced the answer (engine at `:6585`; no LLM call exists after `:7227`), so it is
pure serial tail. Fires on **22 of 38** judged rows.

```python
# app/engines/clara_logic.py, inside extract_tags_llm
if not _clara_llm_wrapper_allowed():
    return None
```

**ENV GATE:** `REGENOLD_CLARA_LLM` — **DEFAULT `0` (skip)**.
**Note:** `tests/test_clara_logic.py:481-599` monkeypatch the provider and assert the LLM parse
paths — the gate must be read **at call time** and those tests must set it explicitly.

**Do NOT** hoist `analyse()` to run concurrently with the engine. Its *arguments* are
pre-retrieval but its *gate* (`regenold.py:7213-7220`) is engine-derived, so hoisting means
**speculative execution on the 16/38 rows currently skipped** — output unchanged, wrapper call
volume up. Not worth it.

### 4.3 — combined expected movement, stated honestly

3.0 s × (0.58 clara + ~0.40 rewriter) ≈ **2.5–2.9 s expected per row** against a measured p50 of
**55.8 s** (sidecar) ≈ **5%**. On the R320-calibrated curve `Speed = 100/(1+t/111.3)` that is
roughly **+1.5 to +2.0 Speed points**. The `_BREAKER` (`clara_logic.py:625-626`) damps clara in a
dense batch (3-pay/1-free at back-to-back cadence) but fully re-arms after 60 s of quiet, which
is the graded 71.2 s hard-conversation cadence — so the sparse-traffic case is the real one.

**Test:** `tests/test_r330_wrapper_skip.py` — with the defaults, assert
`rewrite_sub_query_llm("x", "y") == "x"` and `extract_tags_llm(...) is None` with a provider
mock that would otherwise be called (assert **zero** provider invocations).
**davidath:** neutral **BY CONSTRUCTION** — the bench sets `P2P_GRAPH_RAG_PROVIDER=cli`, so
`is_openai_wrapper_enabled()` (`openai_wrapper_provider.py:367-383`) is already False and both
legs are already skipped. **R318 §3 gate:** none required (output-identical). One pre-flight
smoke check, not an eval: issue **one** live request with debug logging and confirm
`frames_rewriter_error` / `frames_rewriter_exception` fires today — that is the single
unmeasured link (that the wrapper consumes the full 3.0 s rather than fast-failing).

---

## 5. TIER 3 — behavioural, needs the FULL 476

### 5.1 — Article 3 grounding bloat (`app/data/provision_text.py:528`)

**Axes:** Speed ↑ (removes ~12 KB of input tokens on 5/40 rows), prompt hygiene.
**Do NOT claim an Ans Strict win** — the row split is 3 fail / 4 pass and on july7-141 the
allegedly-buried `Art. 50.3` text actually renders at 603 chars in **slot 3**, ahead of the
Art. 3 dump at slot 6.

`:527-528` sets `units = {}` for Article 3, sending it to the no-units branch at `:535`.
`_drill_subpoints` then returns an **unbounded preamble** — `paragraph_text[: first.start() + 1]`
at `:600` — which for Article 3 is the **9,591 chars** of definitions (1)–(44) preceding the
first lettered sub-point at byte 9,590, plus one complete sub-point (worst case (d), 2,866 ch;
total **12,462**). `_render_grounding_text` (`_graph_rag_impl.py:6184`) only whitespace-normalises,
so `_GROUNDING_REF_CHARS = 1200` (`:6073`) is violated **10.4×**, and one of the 8
`_GROUNDING_MAX_REFS` slots is consumed. Measured share of the grounding block: **64%** of
july7-141, **67%** of july7-231, **85%** of july7-293.

**Code change — one line, no new regex.** `_definitions()` already exists at `provision_text.py:373`
and is already used by `get_provision_text` at `:455` to resolve `Art. 3.N`:

```python
# app/data/provision_text.py:528
units = _definitions(body)
```

Then the existing ranked/budgeted path selects. Verified to select the **right** content: on
july7-141's vocabulary it ranks definition (39) "emotion recognition system" and (40) "biometric
categorisation system" top — precisely the concepts the judge recorded as omitted.

**Companion edit:** the emit line at `:574` renders `f"{num}. {text}"`, which would print
`39. 'emotion recognition system' means…` where the Act writes `(39)`. Add a definitions branch
so the verbatim shape is preserved.
**Separately worth doing:** bound the `_drill_subpoints` preamble at `:600` independently — any
provision whose first lettered sub-point sits deep in the text has the same exposure.

**ENV GATE:** `REGENOLD_GROUNDING_ART3_UNITS` — **DEFAULT `0` (OFF)**.
**Test:** `tests/test_r330_art3_grounding.py` — `len(select_relevant_paragraphs("Article 3", q, 1200)) <= 1200`
with the flag on; asserts the returned text contains the question-relevant definition and
preserves the `(39)` shape; asserts the flag-off path is byte-identical to today.
**davidath:** **probably** neutral (grounding text feeds the Stage-2 prompt only, and Stage-2
never runs under `cli`) — but this is an engine-deterministic module and `select_relevant_paragraphs`
has other callers. **Do the R120 fast scan first** (grep the davidath question corpus for
Article-3 triggers); if any hit, run the **full 476** (never `--qa-only`).
**R318 §3 gate:** full 476 → `easyhard_ab`.

### 5.2 — Annex verbatim text never reaches the prompt; the Annex II KB stub is factually wrong

**Axes:** Faithfulness ↑ (1 of 8), Ans Strict ↑ (july7-221's `incorrect=2`).
⚠ **Ans Conciseness risk** — the corrected Annex II list has 17 entries vs the stub's 12; a model
that enumerates it writes longer. This is the one fix in the plan that can trade the axis we lead.

Two coupled defects on july7-221:

* **The stub is wrong.** `app/data/kb.py:1803-1816` splits the single verbatim entry "organised
  **or** armed robbery" into "armed robbery" + "**organised crime**" — inventing an offence Annex
  II does not contain — omits **seven** real entries (child pornography, grievous bodily injury,
  illicit trade in human organs/tissue, ICC-jurisdiction crimes, unlawful seizure of aircraft or
  ships, illegal restraint/hostage-taking, sabotage), and attaches the 4-year custodial threshold
  to Annex II when the verbatim threshold sits in Art. 5(1)(h)(iii). `grep 'organised crime' app/`
  returns exactly one hit: `kb.py:1811`. The live answer reproduces the stub in the stub's exact
  word order, including its idiosyncratic "narcotic drugs / weapons / nuclear material" merge.
* **The correct text is never shown.** In the captured prompt the stub appears **three** times
  (offsets 5753, 25122, 25836) while "organised or armed robbery", "grievous bodily injury",
  "sabotage" and "hostage" appear **zero** times. Annex II sits at index **10** of the ordered
  context refs, and `_render_grounding_text` slices `[:_GROUNDING_MAX_REFS]` at
  `_graph_rag_impl.py:6176`. Separately, `_clip_grounding` (`:6126`, `_GROUNDING_MAX_CHARS = 400`
  at `:6072`, applied at `:6201`) cuts the 498-char stub to 367 chars, so Stage-2 sees only **12
  of 17** offences, **without** "environmental crime" and **without** the 4-year threshold,
  terminating on a **dangling comma**.

**The general defect, which generalises beyond Annex II:** *a lossy KB paraphrase outnumbers the
correct verbatim text in the prompt and wins.* Same row, same shape: "genuine and present" occurs
**once** in the whole 35,369-char prompt while the KB Art. 5 stub's lossy "a genuine and
foreseeable terrorist attack" occurs **twice** — which is the judge's *other* `incorrect` item.

**Ship (a), then decide on (b):**

* **(a) Plumbing — the right lever, no BM25 risk.** In `_expand_referenced_annexes_and_recitals`
  (`_graph_rag_impl.py:5739-5746`) try `select_relevant_paragraphs(annex, context.question,
  _grounding_ref_budget())` **first**, falling back to `EC_CHECKER_OBLIGATION_MAP[annex]["summary"]`
  only when it returns nothing. The complete, correct 779-char Annex II text with all 17 offences
  is already in the repo and already reachable at runtime. And at `:6201`, stop applying the
  400-char `_clip_grounding` to **Annex** entries (Recitals keep it), or the 779-char verbatim
  will be decapitated exactly as the stub is today. This leaves `kb_search.py:334`'s BM25 index
  **completely untouched**, which removes the retrieval-rank risk entirely.
  **GATE:** `REGENOLD_ANNEX_VERBATIM_EXPAND` — **DEFAULT `0` (OFF)**.
* **(b) Correct the `kb.py` literal.** Defensible on its own terms (it is factually wrong and it
  is what the model reproduced), but it changes the BM25 term profile at `kb_search.py:334`, so it
  needs a `KB_VERSION` bump at `kb.py:33` and the **full 476** plus `sim_gate` (a rank change that
  evicts a gold ref shows there with zero variance). **Run the R120 fast scan first**: grep the
  davidath questions for `Annex II`; zero hits ⇒ the bench is byte-identical and only `sim_gate`
  matters. Ship (b) **only after** (a), and prefer keeping the corrected stub terse (cite the
  Annex by reference rather than enumerating) to protect Ans Conciseness.

**Do NOT ship** the "prioritise refs the QUESTION names explicitly" variant: july7-221's question
contains no "Annex" token at all, so it promotes nothing. The rule that actually reaches Annex II
is **cross-reference-driven** — Art. 5 *is* in the top-8 and its rendered verbatim reads "offences
referred to in **Annex II** … at least four years" (offset 12410). Promote refs named inside an
already-selected provision's verbatim body, or named in the deterministic answer.

**Test:** `tests/test_r330_annex_verbatim.py` — with (a) on, the rendered annex block for a
question that pulls Annex II contains "organised or armed robbery", "sabotage" and "child
pornography", contains **no** dangling comma, and does **not** contain "organised crime" as a
standalone token. Plus a data test asserting `kb.py`'s Annex II summary does not contain
`"organised crime"` (guards (b) once landed).
**R318 §3 gate:** (a) → full 476 + `easyhard_ab`. (b) → `sim_gate` first (BM25 rank), then full 476.

### 5.3 — The RE-RANK (R318 Step 2, re-specified)

**Axes:** Ref Strict / Ref Loose (unknown magnitude on the wire). **Confidence:** high on the
offline measurement, **medium on the wire effect**. **Risk:** medium.

**First, the re-specification.** R318 Step 2 says "improve the ranker". There is **no
score-carrying channel** from retrieval to the wire:

* `CitationNode` (`app/models.py:99-105`) has `node_type/node_id/text/article_ref` — **no score
  field**, so whatever the engine ranked internally is discarded at the model boundary.
* The engine builds `citations` at `_graph_rag_impl.py:8739-8757` by plain iteration over
  `context.obligations + context.article_info` — insertion order, no sort.
* `context.obligations` is filled at `:5808-5818` `for entity in query.entities` — entity order
  (`:1954-1965`) is textual-mention order, with `_TOPIC_KEYWORD_EXTENSIONS` **prepended** at
  `:2195` in static declaration order.
* The one genuinely score-ordered lane, `top_articles_by_relevance` ("refs in descending
  relevance order", `kb_search.py:562`), is gated by `if not entities:` at `:2270` — so on every
  question where the keyword lane fires there is **zero relevance scoring** on the path.
* The **only** sort applied to the wire list is `candidates.sort(key=lambda r: _reference_rank(r)[:2])`
  at `regenold.py:7077`, and `_reference_rank` (`:1990`) returns `(type_priority, -specificity,
  formatted)` — a pure **format** key with no relevance content. It does not survive: **12 of 38
  rows violate** the Article-before-Annex order it imposes.

The one re-rank stage that *does* exist is `_promote_lead_ref` (`regenold.py:3628`, called `:9022`,
default ON via `REGENOLD_REF_RECOVERY`) — a **binary** front/back partition implementing R318's own
2.26× lead-sentence signal, with no ordering inside either block.

**The lever.** BM25-scoring each already-emitted ref against the **final answer** text
(`relevance_score` at `app/data/kb_search.py:1093` — torch-free, sub-ms, **zero production callers
today**) and stable-sorting descending is the **only** re-rank feature whose rank-0 gold lift
replicates on both recorded gold arms, and it is **additive** to production (replaying
`_promote_lead_ref` on the r317 arm is a 0/129 no-op):

| arm | rank-0 gold | Δ | improved / worsened | top-2 gold_dropped |
| --- | --- | --- | --- | --- |
| `easyhard-r282-fullprod-clean-A` (129 gold rows) | 0.7829 → **0.8372** | +0.054 | 14 / 7 (p=0.189) | 23 → 17 |
| `easyhard-r317-oursS2-A` (129 gold rows) | 0.7674 → **0.8295** | +0.062 | 17 / 9 (p=0.169) | 30 → 24 |

On the R329 judged arm it demotes wrong refs (rank-0 wrong 9/38 → 6/38) while dropping **fewer**
judge-correct refs under a top-3 prefix (11 → 6/8).

**Ship the PURE relevance sort, not the composite.** The finding's own proposal (lead partition as
**outer** key, relevance secondary) is strictly worse on both gold arms — rank-0 0.8295 vs 0.8372
and 0.8217 vs 0.8295; top-2 18 vs 17 and 25 vs 24; and on r317 top-3 it is **8 vs a baseline of 7**,
i.e. worse than shipping nothing. Caveat: on the R329 judged arm the composite wins, so run **both**
key orders through `sim_gate` before choosing.

**Insertion point:** `app/routes/regenold.py:9022`, alongside / replacing `_promote_lead_ref` — the
**last order-sensitive point** in the route, immediately before `adaptive_ref_clamp` (`:9024`).
Sorting at `:7077` instead would be largely **inert** (~20 passes overwrite it).

```python
# app/routes/regenold.py:9022
if _ref_rerank_enabled() and _stage2_landed and references:
    references = _rerank_by_answer_relevance(references, answer_text or "")
elif _ref_recovery_lead_enabled() and _stage2_landed and references:
    references = _promote_lead_ref(references, answer_text or "")
```

`_rerank_by_answer_relevance` stable-sorts on `(-relevance_score(answer_text, kb_key(head(ref))),
original_index)`, `kb_key` maps `Article 6` → `Art. 6` and leaves `Annex I` unchanged, lazy import
inside a `try`, fail-soft returning the input list (matching `_promote_lead_ref`'s contract at `:3662`).
All 126 canonical refs in `article_existence.py` map into the 131-key BM25 index, so no ref is
demoted for being out-of-corpus.

**ENV GATE:** `REGENOLD_REF_RERANK` — **DEFAULT `0` (OFF)**. Route post-processing over cached
engine output ⇒ **omit** from `_engine_cache_key` (R79 doctrine).

**⚠ It is NOT set-neutral.** The finding's risk note ("pure reorder, invisible until a prefix
clamp runs") is wrong. `_reconcile_references_to_prose` tops up in **wire order**
(`regenold.py:3704-3707`) and the definitional branch slices `references[:_effective_max_refs]`
at `:7823`. A reorder changes the emitted **set** on both paths, so it can drop gold.

**⚠ The +0.054/+0.062 is NOT the wire delta.** The recorded arms store **post-clamp** `pred_refs`
while the insertion point reorders the **pre-clamp** list, so the simulation measures ordering
quality on the set that already survived. Real budgets: QA **3** (`regenold.py:3139`) and SCENARIO
**5** (`_DEFAULT_SCENARIO_CLAMP`, `:4160`, which **overrides** the 10/22 `_effective_max_refs` set at
`:7406/:7448`).

**⚠ It is not a clamp unlock.** top-2 gold_dropped lands at 17 and 24, not 0. R318's bar is **zero**.
The top-2 clamp stays rejected and Ref Loose −0.083 is **not** bought back. **Do not ship a clamp
change in the same round** (R318 §2 trap, R142.1).

**Test:** `tests/test_r330_ref_rerank.py` — flag OFF ⇒ byte-identical to `_promote_lead_ref`
(inertness proof); flag ON ⇒ a known answer/ref fixture reorders as expected; fail-soft on a
`relevance_score` exception returns the input list unchanged.
**davidath:** neutral **BY CONSTRUCTION** (`_stage2_landed`-gated ⇒ inert on the Stage-2-free bench)
— which also means **davidath cannot gate this**. The real gates are `sim_gate.py` and `holdout.py`.
**R318 §3 gate:** `sim_gate` OFF (prove inertness) → `sim_gate` ON (`gold_dropped == 0`) →
`holdout` (`governing_dropped == 0`) → full 476 → `easyhard_ab` (the merge gate; **not**
`ab_judge`, whose refs axis has no minimality term and prefers the superset).

### 5.4 — The challenge-turn brevity clause has never reached the traffic it was written for

**Axes:** Ref precision on the graded turn. **Confidence:** high on the defect, **unknown on the
benefit**. **Risk:** medium (generation-side, 36/38 hard rows).

The graded turn inflates references **+9.7%** (mean 2.974 → 3.263; 19 added, 8 dropped) and its
additions are **73.7% wrong** (14/19) against a 44.4% base rate — 1.66× worse than average.
Answer length is flat (1324 → 1325 chars), so this is **provision breadth**, not length.

**`_apply_assistant_anchor_inheritance` is EXONERATED** — do not touch it. R305's
`_extract_reask_tail` (called at `regenold.py:6047`, early-returns at `:6061-6067` with
`self_contained_focus=True`) fires on **36 of 38** pushback turns and returns the verbatim re-asked
original question with the pushback preamble stripped. That zeroes `_r88a_history` at `:6949-6953`,
so the inheritance pass receives empty history and is a strict no-op.

**The real defect: R305 silently disabled R298's clause.** `USER_CHALLENGE_BREVITY_CLAUSE`
(`app/data/graph_rag_prompts.py:517-527`, default ON via `challenge_brevity_enabled()` at `:629`,
appended at `_graph_rag_impl.py:7400-7401`) **already contains, verbatim**: *"A challenge is NOT a
request for more provisions, more detail, or a longer answer: do not add citations you would not
have given the first time merely to appear thorough."* `is_challenge_turn` (`:576`) matches the raw
`PUSHBACK_PREAMBLE` on **three** markers — but the route passes it the **post-R305 question**
(`regenold.py:6358`), which by then contains **zero** pushback text. Measured: it fires on **2 of 38**
graded rows — exactly the two where `_extract_reask_tail` did not fire.

**Fix:** evaluate the challenge detector against the **raw last user message** from `req.messages`,
not the post-R305 `question`. One line.

**ENV GATE:** `REGENOLD_CHALLENGE_DETECT_RAW` — **DEFAULT `0` (OFF)**.
**Do NOT add a second no-broaden clause** — R298's is already shipped and already default-ON.

**Honest caveat:** the verifier's mechanism analysis says the +9.7% is **resampling noise**, not
scope extension — on 36/38 rows Stage-2 never sees the pushback at all, and turn 2 only misses turn
1's cache because `_history_turn_count` is folded into `_engine_cache_key` (`:6572-6577`), forcing a
fresh Opus sample of the *same* prompt. Answers changed on 32/38 rows with length flat. If that is
right, a brevity clause may not help. Counter-evidence: on july7-125 — the one affected row where
the clause **is** live today — the system still over-cited. **Treat this as restoring an
already-measured feature's intended reach, not as a predicted win**, and let `easyhard_ab` decide.

**Test:** `tests/test_r330_challenge_detect.py` — with the flag ON, a 3-message pushback request
makes `is_challenge_turn` True against the raw last user message even though the post-R305 `question`
has no markers; with it OFF, today's behaviour.
**davidath:** neutral **BY CONSTRUCTION** (single-turn ⇒ no pushback markers ⇒ never fires).
**R318 §3 gate:** 276-runner + OOS probe (multi-turn coherence), then `easyhard_ab`. `sim_gate`
cannot score a generation-side change.

---

## 6. TIER 4 — PARKED. Build the gate, do not spend an A/B slot this round

Each is real, each is ≤ 1 wrong ref or ≤ 1 row, and each costs a live A/B slot worth more elsewhere.
Land the gate default OFF so R331 can measure cheaply; do not run the arm.

| # | fix | file:line | gate (default) | why parked |
| --- | --- | --- | --- | --- |
| P1 | `_apply_ontology_hops` re-adds what `_prune_non_anchor_refs` just deleted | `regenold.py:7744` vs `:7140` | `REGENOLD_ONTOLOGY_HOP_SUPPRESS` (**0**) | 1 of 55 wrong refs (july7-169 `Annex I`). **Reject fix (a)** — the `is_wh_question and not is_scenario` guard is **inert on both its own evidence rows** and is a **gold-dropper** on 10 davidath medical scenario rows where Trigger 3 is the only unblocked trigger (measured injecting gold: Art 13/14/15; Art 9/13/14). Ship only the **suppression-list** variant: pass the pruner's removal set into the hop so it skips anything the pruner dropped — leaves every other row byte-identical, unlike the raw reorder (2/137 davidath blast radius, one of which loses a plausibly-gold Article 6). **july7-119 is NOT affected** (its `Article 43` comes from `_retrieve_from_kb`). |
| P2 | `_surface_prose_subpoints` bare-parent key | `regenold.py:3790` | `REGENOLD_PROSE_SUBPOINT_SIBLING` (**0**) | 1 row (july7-141), ≤ 1 of 8 faith failures, and it **ADDS** a ref (Ref-Con cost). Effect is far below the A/B noise floor (R288: identical arms drifted 0.053). **Verify by REPLAY only, never live-A/B.** Fix shape: parent-index the ref list instead of exact-matching the bare string; keep `_MAX_PROSE_SUBPOINT_ADDS` and the R136 `len(subs) < 3` guard at `:3781`. Note the title's causal story is wrong — no pass "replaces" the parent; the leaf-only cluster comes from leaf-grain retrieval. |
| P3 | `_seed_classification_obligations` REPLACE → MERGE | `_graph_rag_impl.py:2895`, `:2900` | `REGENOLD_CLASSIFICATION_SEED_MERGE` (**0**) | Real grounding destruction (Article 7 is retrieved on july7-147 then wiped), but it causes a judged **answer** failure on exactly **1 of the 6 firing rows** (july7-147; -175, -283, -287, -321, -327 all PASS). The reference corroboration is **refuted**: firing rows carry 6 of 55 wrong refs (1.0/row vs 1.53/row elsewhere), and **zero** of the run's `Annex I ×4`, `Article 50 ×3`, `Article 51 ×3`, `Article 49 ×4` land on a firing row. It is **additive** on rows that already fail ref_correctness 6/6 and it feeds Stage-2 more material ⇒ **Ans-Conciseness risk**. (Also: july7-125 does **not** fire; july7-175 does.) |

---

## 7. MEASUREMENT ONLY — needs explicit operator sign-off, not a code default

### 7.1 — The Speed gap is transport, and Bedrock is the only untried remedy

Two independent lines put a **fixed per-Stage-2-call cost of ~10–20 s** on the path:

* **R320 direct probe** (`docs/ROUNDS.md:4888`): a **5-token** wrapper request costs 12–17 s
  locally and 13.5 s for 2 tokens through the prod tunnel, **identical for Sonnet-5 and Opus-5**
  ⇒ process-spawn/auth bound, not token bound.
* **Regression on 32 Stage-2-landed R329 HARD rows** (source: `evals/bench/results/july7-r329-hard-prod.ckpt.jsonl`
  `latency_ms` — `latency_s` is **null** on all 38 attribution rows):
  `latency = 32.23 + 0.00941 × total_answer_chars`, R² 0.42, intercept SE 6.44, **95% CI [19.1, 45.4] s**
  over two turns.

Neither pins a point value, and the divide-by-2 is optimistic (`provenance.stage2_polish` is one
flag per row while the fastest Stage-2 row is 17.1 s total). **The slope independently confirms
answer length is a weak Speed lever** (100 chars ≈ 1.9 s), consistent with R320 rejecting the live
sentence cap at `answer_correctness −0.143` (see the R320 comment block at
`app/integrations/regenold/models.py:~1390`).

**This also corrects the scorecard.** `R329-SCORECARD-VS-FRONTIER.md:127-128` names
`complex_thinking_tokens = 4000` as the Speed cost driver. R320 measured that **backwards**
(complex/4000 p50 **26.9 s** vs simple/0 **41.8 s**). Fix that line.

**The Bedrock branch already exists and is reachable today** — `_graph_rag_impl.py:7701-7709`,
`_use_bedrock` set at `:7566-7572`, `is_bedrock_provider_enabled()` at `bedrock_client.py:822-833`
returns True (creds in `.env`), `claude-opus-5` aliases to `eu.anthropic.claude-opus-5` at `:385`,
`_stage2_provider_enabled()` (`:1230-1242`) handles `bedrock`, and `_engine_cache_key`
(`regenold.py:1207`) folds the provider string in, so a provider A/B is cache-safe. Converse is a
plain HTTPS call with no CLI spawn. Projection on the R320 curve: **−8 s/request → Speed 61.7 → 66.8
(+5.1)**; **−14 s → 72.0 (+10.3)**. That is 3–5× every other Speed item combined.

**⚠ It is NOT a pure transport swap — four variables move at once:**

1. `BedrockRequest` (`bedrock_client.py:57-76`) has **no `thinking` field**, so extended thinking
   (2048 simple / 4000 complex, `_graph_rag_impl.py:602-697`) is **silently dropped**.
2. Bedrock **honours the system prompt slot** that the Claude Max wrapper drops entirely
   (CLAUDE.md gotcha #1), so every Stage-2 fix R298 deliberately moved into the USER message is
   effectively delivered **twice**, and `ANSWER_GENERATE_SYSTEM` rule 10 ("unmentioned citations
   are severely penalized") starts firing for the first time — which interacts with
   `_reconcile_references_to_prose` (`regenold.py:3666`, default ON, floor 1) and **could drop wire
   references**.
3. Defaults are a model **downgrade**: `BEDROCK_RAG_MODEL = sonnet-4-6` (`:500`) /
   `BEDROCK_COMPLEX_MODEL = opus-4-6-v1` (`:503`) vs the measured `claude-opus-5`.
4. Bedrock bills **per token** — this is a cost decision, not only an engineering one. The standing
   directive forbids per-token billing for evals except the Pro-tier fallback test.

**Therefore:** do NOT flip any default. Run **one** arm with `P2P_GRAPH_RAG_PROVIDER=bedrock` and
`REGENOLD_BEDROCK_COMPLEX_MODEL=claude-opus-5` **pinned**, against a **recorded** HARD arm, and
compare (i) p50/p95 latency and (ii) the four judged axes via position-swapped `easyhard_ab`.
Nothing in this repo has ever measured Bedrock TTFB on this workload — **+5 to +10 Speed points is
a projection, not a finding.**

### 7.2 — Two dead KG features found while tracing; INVESTIGATE, do not fix blind

* **R327 semantic layers are dead on the answer path.** `_graph_rag_impl.py:6428` calls
  `render_kg_context(_context_article_refs(context))` with **no `question` argument**, and
  `_render_semantic_layers` short-circuits on `if not question: return []`
  (`kg_context.py:445-447`). `REGENOLD_GRAPH_SEMANTIC_LAYERS` defaults ON per CLAUDE.md. This is a
  **materially larger** dead KG feature than the deontic one in Z3 and deserves its own round.
* **`PROVISION STRUCTURE` is silently deleted on wide-ref rows.** `_fit_complete_lines` strips the
  leading `"\n"`, so the reassembly loop at `kg_context.py:630-634`
  (`p.startswith(candidate[:40])`) never matches a truncated part and discards the **whole block**.
  Measured on july7-221: 37,618 chars pre-budget against a 16,000 limit ⇒ block dropped entirely.
* **R133 `_surface_prose_subpoints` is largely inert on the shipped wire.** On 16 of 37 rows,
  replaying it against the shipped `pred_refs` still produces additions — only consistent with
  `_apply_ref_granularity('auto')` at `regenold.py:8931` erasing them downstream.

---

## 8. Measured dead this round — do NOT re-propose

Add these to `.planning/R318-PLAN.md` §1 as families **#6** and **#7**, alongside the existing five.

| # | family | why it is dead |
| --- | --- | --- |
| **6** | **support-depth re-rank against verbatim Act text** (score each ref by IDF-weighted mass of its `OFFICIAL_ARTICLE_TEXT` appearing in the answer sentences naming it) | Non-significant on the R329 judged arm (AUC 0.660–0.702 vs 0.618, CI crosses zero) and **inverts on BOTH gold arms** — r282 rank-0 0.783 → 0.736, top-3 gold_dropped 6 → 11; r317 0.767 → 0.698, top-2 30 → 43. Reproduced independently by two implementations; only the **sign** replicates, the decimals do not. Mechanism: verbatim provision text is dominated by cross-references and procedural boilerplate, so a briefly-mentioned operative gold article scores below a long procedural article the answer paraphrases at length (18 rank-0 demotions: promoted non-gold averages 6022 ch vs 3423 for demoted gold). |
| **7** | **trailing scope-extension ("tack-on") ref pruning** | The intersection of two already-dead families (prose-driven pruning + positional clamp). Looks perfect at n=38 (0/69 correct refs lost, 9/55 wrong removed) and **drops 7 GOLD across 39 removals (18%)** on the gold arms — r282 4 gold, r317 3 gold. Opener-only variant still fails; last-1-sentence variant fails. **The exact counterexample:** `lower_risk_v149:lr_inventory_tool` and `multiarticle_r268:ma_01` carry **GOLD Article 50** in the *same* "Where X interacts directly with natural persons…" trailing clause on which july7-125's Article 50 was judged **WRONG**. R318 §1's generalisable lesson, instantiated. Reproduces R142.1. |

**Also refuted this round (do not resurrect):**

* **`kb_xrefs` curated-vs-regex edge gating** — curated precision is 0.625 not 1.000, regex 0.231
  not 0.083; the fix drops 3 judged-CORRECT refs; the same edge `Art. 16 → Art. 17` is gold on
  july7-129 and wrong on july7-153/249, so provenance is **not** the discriminator; curated edges
  emit 2 of the 4 top-offender `Annex I` hits, so a curated-only gate keeps the worst offender.
* **"Component D Post-Polish Grounding Guard" cap** (`regenold.py:8561-8657`) — counterfactually
  **inert**. The R138 pass at `:8829` (`cap=8`, `allowed_source = references ∪ prose`) subsumes it;
  simulating both arms on all 10 evidence rows loses **0** of the claimed 13 refs and produces an
  identical set on 9/10. `_looks_like_scenario_shape` returns **0 scenario rows** across all 38, so
  Component D is never uniquely reachable. Half the proposed fix is already the code at `:8590-8592`.
* **`select_relevant_paragraphs` line-567 `continue` fix** — misattributed on 3/6 rows (they take
  the early return at `:558-561`, and the loss is inside `_drill_subpoints`' own budget `break` at
  `:623`) and **inert on 3/6** (Art. 60(7), Art. 23(2), Art. 71(3) have no lettered sub-points, so
  the drill returns None). Simulated before/after emits identical lists. Fixing the real defect
  requires **raising** the budget — enlarging the prompt and lengthening answers.
* **`_clip_grounding` 400-char decapitation as a faithfulness cause** — the routing excludes it:
  a **cited** annex is a retrieved obligation and takes the verbatim path at `:6188`, not the clip
  path. Zero of the 8 faithfulness failures are attributable. (The dangling comma is still real —
  it is handled inside §5.2 (a), which removes the clip for annexes.)
* **"KB is keyed at article grain so definitional questions get the stub"** — falsified by the run's
  own data: the same question single-turn returns the correct sub-point definition. The cause is the
  `_is_multiturn` gate (§3.2), not grain.
* **`render_kg_context` childless-node text projection** — `render_kg_context` is called with
  `_context_article_refs`, not the wire refs, and `annex_II` sits at index 10 of 14 (outside the
  `limit=8`), so Neo4j is never asked about it. And the block is dropped entirely by the
  budget-reassembly bug on exactly those wide-ref rows. Also "15 Articles never reach Stage-2" is
  false — `select_relevant_paragraphs("Article 4", …)` returns the full verbatim text via the
  grounding path.
* **Narrowing the complex-question gate for Speed** — `corr(lat, answer_chars)=0.666` vs
  `corr(lat, complex)=0.284` controls a **mediator** (the complex flag itself buys Opus + 4000
  thinking tokens + the 5-sentence budget); the stratification "flip" reports 1 of 2 strata (the
  omitted short-q stratum shows +33 s in the **original** direction); the two supporting
  observational splits **contradict each other**; and the prescription is a no-op
  (`REGENOLD_COMPLEX_SENTENCE_CAP` already defaults to `"5"`).
* **Positional tail clamp conditioned on `len > 6`** — that is R318 §1's dead "positional/top-N"
  family with a length precondition. On its only firing row (july7-299) it is **inert** (the route
  re-instatement at `:9057` runs **after** the clamp at `:9024` and re-expands to 11) and it
  **drops a judged-CORRECT ref** (`Annex III` at index 6, the governing high-risk anchor for a
  migration question), reproducing R142.1.
* **Re-specifying `_promote_lead_ref` as a full sort** — the lead signal replicates (1.56× lift,
  27/35 = 0.771 in-lead vs 0.495, Fisher p=0.0052) but the pass is **already default-ON**, the
  proposed refactor is byte-identical by construction, and **nothing consumes the back-bucket
  order**: `adaptive_ref_clamp`'s prefix is reached only when `len(references) > budget`, and on
  38/38 rows it did not truncate. Superseded by §5.3, which changes the **key**, not the shape.
* **"The Stage-2 prompt authors the tack-on"** — the cited clause at `_graph_rag_impl.py:7355-7358`
  sits inside the `else` of `if is_general_classification:` (`:7279`) and is **never in the prompt**
  for 3 of the 6 evidence rows; the flagship row's refs are byte-identical to the
  `_GENERAL_CLASSIFICATION_REFS` constant (`:2739`); and the tally double-counts `Annex I`, which
  line 7357 does not name (7.3% ceiling, not 21.8%).
* **A "prose-not-named" ref pruner** — already implemented and default-ON:
  `_reconcile_references_to_prose` (`regenold.py:3666`, called `:8506`, `REGENOLD_REFS_RECONCILE`
  default `1`) drops exactly the 6 spill refs and 0 correct ones. It did not run on the two spill
  rows only because `stage2_polish` was **false** there and `:8506` is `_stage2_landed`-gated.

### 8.1 — New METHOD rule (add to R318 §4 "Traps")

> **A ranking feature's sign can differ between the R329 text-grounded judged arm and the gold
> arms.** Support-depth was positive on the judged arm (AUC 0.702) and negative on both gold arms.
> **No ranking candidate may be accepted on the R329 judged arm alone.** Every one must be replayed
> against `easyhard-r282-fullprod-clean-A.ckpt.jsonl` **and** `easyhard-r317-oursS2-A.ckpt.jsonl`
> (129 gold-bearing rows each) before it is proposed.

Also worth recording: **49 of 55 wrong refs (89%) ARE named in the answer prose** on this arm,
independently re-confirming R318 §1's "prose-driven pruning is a structural no-op".

---

## 9. davidath neutrality — the definitive table

The deterministic bench runs `OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli
REGENOLD_EXTERNAL_EMBEDDINGS=0`: **no Stage-2, no wrapper, no Neo4j, every request single-turn.**

| fix | davidath status | reason |
| --- | --- | --- |
| Z1 web_ui | **neutral by construction** | browser-side JS, not imported |
| Z2 `point (None)` | **neutral by construction** | Neo4j absent; Stage-2 prompt only |
| Z3a deontic gate + param | **neutral by construction** | Neo4j absent; gate OFF ⇒ output identical |
| Z4/Z5 comment + docs | **neutral by construction** | no code path |
| **3.1 risk-framework anchor** | **neutral by construction** | parent regex 0-fire on 137 QA + 339 scenarios; a strictly narrower predicate cannot exceed 0 |
| **3.2 definitional (ROUTE variant)** | **neutral by construction** | every davidath request is single-turn ⇒ `_is_multiturn` always False. ⚠ the ENGINE variant is **NOT** — it fires on 4/137 QA and changes 1 wire row |
| **3.3 emotion (SCOPED variant)** | **neutral, VERIFY FIRST** | R144 comment claims 0-fire; confirm with the R120 scan before trusting it |
| 4.1 frames_rewriter | **neutral by construction** | `is_openai_wrapper_enabled()` False under `provider=cli` |
| 4.2 clara | **neutral by construction** | same |
| 5.1 Article 3 units | **VERIFY, then FULL 476** | engine-deterministic module; grounding text is Stage-2-only but `select_relevant_paragraphs` has other callers |
| 5.2a annex verbatim | **FULL 476** | engine deterministic path |
| 5.2b `kb.py` Annex II | **FULL 476 + `sim_gate`** | changes the BM25 term profile at `kb_search.py:334`; bump `KB_VERSION` (`kb.py:33`) |
| 5.3 ref re-rank | **inert by construction — and therefore NOT a gate** | `_stage2_landed`-gated. Use `sim_gate` + `holdout` instead |
| 5.4 challenge detector | **neutral by construction** | single-turn ⇒ no pushback markers |
| P1 ontology hop | **FULL 476** | **not** stage2-gated ⇒ davidath-visible |
| P3 seed merge | **VERIFY, then FULL 476** | `_general_classification_verdict` documented 0-fire; confirm |

**Reminder (R318 §4):** `--qa-only` is **not** a gate for a reference change. QA gold is
single-article and cannot show a chain-dropping defect (R317: 0 on QA, **67 on scenarios**).

---

## 10. Execution order

**Commit 1 (zero risk, no eval):** Z1, Z2, Z3a, Z4, Z5 — one commit each. Land today.

**Commit 2 (Speed, output-identical, default ON):** 4.1 + 4.2 + tests. One live pre-flight
smoke request to confirm the wrapper legs error today. No gate stack.

**Commit 3 (the headline, all default OFF):** 3.1 + 3.2 + 3.3 + their tests + the gate/emitter
parity test. Then run, in order, once:

```
sim_gate.py (gold_dropped == 0)  →  holdout.py (governing_dropped == 0)
  →  davidath FULL 476 (expect byte-identical; if not, STOP — a by-construction claim broke)
  →  276-runner + OOS probe (multi-turn coherence 20/20)
  →  easyhard_ab   ← the merge gate; flip the three defaults only on a win-or-tie
```

⚠ Run these **sequentially** — never two wrapper-bound jobs over the single local proxy.
⚠ Flip the three flags **together or not at all** only if `easyhard_ab` cannot resolve them
individually; prefer 3.1 alone first, since it carries 9 of the 12 wrong refs at stake.

**Commit 4+ (one per round, each with its own A/B):** 5.3 (the re-rank — highest remaining
leverage), then 5.4, then 5.1, then 5.2.

**Parked, gates only:** P1, P2, P3.

**Operator decision required:** 7.1 Bedrock — per-token billing, four confounded variables.

---

## 11. Cannot ship without a live A/B — stated explicitly

Per the brief's rule, these are **not** shippable default-ON on offline evidence alone, no matter
how clean the replay looks:

| fix | why an A/B is mandatory |
| --- | --- |
| 3.1, 3.2, 3.3 | each changes a **shipped answer** on live rows; the deterministic replay is a stand-in for the Stage-2 arm, not the arm itself |
| 5.1 | the Ans-Strict claim is **unproven** (3 fail / 4 pass) — ship it as prompt hygiene, do not claim the axis |
| 5.2a / 5.2b | 17 offences vs 12 ⇒ **Answer-Conciseness exposure**, the only axis we lead |
| 5.3 | **not set-neutral** (`_reconcile_references_to_prose` tops up in wire order; the definitional branch slices a prefix) ⇒ it can drop gold |
| 5.4 | generation-side on 36/38 hard rows, and the mechanism analysis says the effect it targets may be **resampling noise** |
| Z3b (deontic render) | injects `Annex I` / `Article 4` / `Article 5` and all 8 Annex III labels into prompts on rows that retrieved none — a live over-citation vector on **Ref Conciseness, the axis we are losing**. Also: extend the Cypher to project `cat.number` and `cat.description` **first**, or it cannot supply the point-7(b)/7(d) grain it was proposed for. |
| 7.1 Bedrock | four variables in one arm + per-token billing |

**And the two hard "never" rules that apply here:**

* **Never live-A/B a pure reference transform** against a freshly generated baseline (R288: two
  identical baseline arms sign-flipped all three ref axes on generation variance alone). Replay a
  recorded arm — P2 in particular must be replay-verified only.
* **`easyhard_ab`, not `ab_judge`, is the merge gate** for anything touching references —
  `ab_judge`'s refs axis has no minimality term and prefers the superset.

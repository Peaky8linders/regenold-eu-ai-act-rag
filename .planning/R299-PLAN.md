# R299 — the path to 70% reference + answer correctness

Written at the end of R297/R298. Everything here is grounded in numbers measured
in those two rounds; where a claim is an estimate it says so.

---

## STATUS AFTER R298 — Move 1 (weak form) SHIPPED and it worked

R298 mirrored the R281 minimality rule + a new challenge-brevity rule into the
Stage-2 **USER** message and A/B'd them live: 15% stratified sample of the real
2026-07-07 hard batch (43 requests/arm, 0 run errors), Opus-5 fast mode, neo4j
backend, graded by BOTH judges.

**Grounded judge (text-grounded against the verbatim Act):**

| axis | multi-turn n=17 OFF -> ON | single-turn n=9 OFF -> ON |
| ---- | ------------------------- | ------------------------- |
| answer correctness | 0.471 -> **0.647** | 0.444 -> **0.667** |
| ref correctness | 0.059 -> **0.412** | 0.111 -> **0.333** |
| ref **precision** | 0.423 -> **0.735** | 0.552 -> **0.686** |
| ref **recall** | 0.909 -> **0.966** | 0.889 -> 0.889 |
| citation faithfulness | 0.588 -> **0.706** | 0.667 -> **0.778** |

**4-axis rubric-shaped judge:**

| axis | multi-turn n=17 | single-turn n=9 |
| ---- | --------------- | --------------- |
| correctness | 0.765 -> **0.824** | 0.778 -> **0.889** |
| refs | 0.412 -> **0.824** | 0.667 -> 0.667 |
| **conciseness** | 0.059 -> **0.412** | 0.111 -> **0.444** |
| tone | 0.765 -> **0.882** | 0.556 -> **0.667** |

Plus: pushback inflation **+43.4% -> +7.4%** with **0/17 concessions in both
arms**; multi-turn answer chars −32.7%, refs −29.5%; latency p50 −31%.
**Nothing regressed on either judge, and recall ROSE** — so this is not the
R142.1 trade. Shipped **default ON** (`REGENOLD_USER_REF_MINIMALITY`,
`REGENOLD_CHALLENGE_BREVITY`); davidath byte-identical, OOS 49/51 / 0 leaks.

**So Moves 2 and 3 below are now the remaining work, and Move 1 escalates from
"instruct the model to self-select" to "hand it a pre-partitioned block".**
The weak form already bought +0.31 precision, which is strong evidence the
structural form is worth building.

### Where that leaves the 70% target

| | before R298 | after R298 | 70% |
| --- | --- | --- | --- |
| 4-axis correctness | 0.769 | **0.846** | ACHIEVED |
| 4-axis refs | 0.500 | **0.769** | ACHIEVED |
| grounded answer correctness | 0.462 | **0.654** | close |
| 4-axis conciseness | 0.077 | 0.423 | gap |
| grounded ref correctness | 0.077 | 0.385 | gap |

The two judges disagree by design: the 4-axis judge scores the competition-shaped
rubric, the grounded judge scores every cited provision against verbatim Act text
and fails a row for ONE wrong or missing provision. **Report both; do not quote
one as if it were the other.** The remaining gap is concentrated in the grounded
ref axis and conciseness.

---

## 0. Read this first — three traps that have each already cost a round

**TRAP 1 — the Claude-Max wrapper DROPS the system prompt.** `ANSWER_GENERATE_SYSTEM`
reaches the model **0% of the time** on the production path.
`claude-code-openai-wrapper/src/claude_cli.py:152` sends
`options.system_prompt = {"type": "text", ...}`; `claude_agent_sdk` 0.2.82 accepts
only `str` / `{"type":"preset"}` / `{"type":"file"}` and silently discards the
unknown dict (TypedDicts do not validate at runtime). R281's controlled 3-trial
BANANA test: obeyed **0/3** from the system channel, **3/3** from the user channel.
*Consequence:* any next-session work that edits `ANSWER_GENERATE_SYSTEM` is dead on
arrival. Edit the Stage-2 **USER** message
(`_graph_rag_impl.py::_claude_max_enhance_answer`, ~line 6540+). And do NOT "just
fix the wrapper": R282 measured that newly delivering the ~12.8K-token accreted
system prompt is rubric-**negative** (kw_recall −0.267, off-topic drift).

**TRAP 2 — n≈10 cannot resolve these axes.** R297 ran a provably-null arm
(`P2P_GRAPH_RAG_MODEL`, which is inert — see TRAP 3) and measured pure
generation noise at n=11: answer_correctness **±0.091**, ref precision **±0.057**,
ref F1 **±0.063**, factual score **±0.051**; and at n=8: answer_correctness
**±0.125**. A 10% sample can only detect very large effects. **R299 must run the
full 110-question batch per arm** (`run_official_batch --mode both`), ~2 h/arm.

**TRAP 3 — check the knob is live before you A/B it.** `P2P_GRAPH_RAG_MODEL` is a
no-op (feeds `base_model`, whose only call site is the dead `_llm_parse_query`);
Stage-2 is hard-floored to Opus by
`if not model or "opus" not in model.lower(): model = "claude-opus-5"`, so even
`P2P_GRAPH_RAG_STAGE2_MODEL=claude-sonnet-5` does nothing. See
`project_p2p_graph_rag_model_is_inert`.

---

## 1. Where we actually are (R297, grounded Sonnet-5 judge, 36 graded rows)

| axis | multi-turn HARD (n=11) | single-turn HARD-content (n=8) | r290 full-batch HARD (n=110) |
| ---- | ---------------------- | ------------------------------ | ---------------------------- |
| answer correctness | 0.364 | 0.375 | 0.346 |
| mean factual score | 0.836 | 0.854 | 0.772 |
| reference correctness | 0.182 | 0.250 | 0.173 |
| ref **precision** | 0.551 | 0.681 | 0.471 |
| ref **recall** | 0.894 | 0.904 | 0.865 |
| citation faithfulness | 0.818 | 0.500 | 0.536 |

## 2. The diagnosis — one root cause, two symptoms

**Retrieval is not the problem. Recall is 0.87-1.0 across every measurement.**
The problem is that the generator SURVEYS the retrieved law instead of ANSWERING
the question. Evidence, all measured in R297:

1. **45 of 46 wrong refs are DESCRIBED in the answer prose** (98%; R281
   independently measured 95% on a different 132-row set). So every prose-driven
   pruner — R72 `_reconcile_references_to_prose` — is a structural no-op: it drops
   cited-but-undescribed refs, and there is essentially only one.
2. **Wrong and correct refs are positionally indistinguishable.** Wrong refs sit
   at ranks `{0:7, 1:9, 2:11, 3:7, 4:8, 5:2, 6:2}`; known-correct refs at
   `{0:8, 1:8, 2:6, 3:2, 4:2}`. **No top-N clamp can raise precision without
   cutting recall** — which is exactly why R142.1's positional `_final_ref_clamp`
   lost a live pairwise 11-0 at p=0.001. That result is now explained, not just
   observed.
3. **One variable predicts BOTH axes:**

   | | mean refs | mean answer chars |
   | --- | --- | --- |
   | ref-axis PASS | 3.25 | 1356 |
   | ref-axis FAIL | 4.64 | 1607 |
   | answer-axis PASS | — | 1349 |
   | answer-axis FAIL | — | 1657 |

4. **The cause is a prompt rule with no converse.** Rule 10 / its live user-message
   twin says *"make sure every article or annex you cite is described in the
   prose"*. Nothing says *don't cite a supplied provision that does not govern*.
   A ~10-article retrieval block therefore becomes an agenda. Rule 10 was added in
   R69-D to win the internal ab_judge **faithfulness** axis — and it did
   (faithfulness 0.82). We optimised an internal judge axis into a competition
   regression.
5. **The answer failures are OMISSIONS, not errors.** mean factual score is
   0.84-0.89 while pass rate is 0.36-0.50 — the judge fails a row for ONE missing
   statutory element. Verbatim modes: *"omits Art 6(4)"*, *"omits objectives (i)
   and (ii)"*, *"omits Art 27(1)'s carve-out for Annex III point 2"*, *"never
   states the Commission is the controller (Art 71(6))"*, *"omits Annex III point
   3(a)-(d)"*. We are not wrong; we are incomplete **on the provision that
   actually governs** — because attention is spread over 4.6 provisions.

**So the two goals are complementary, not in tension:** cite fewer provisions →
more room to cover the governing one completely.

---

## 3. The plan

### Move 1 — OPERATIVE vs BACKGROUND partition of the references block  *(biggest lever)*

Today `EU AI ACT REFERENCES:` is an undifferentiated list, so the model treats it
as a checklist. Split it before generation:

```
OPERATIVE PROVISIONS (cite these; the question turns on them):
  Article 23 - importer verification duties ...
BACKGROUND (context only - do NOT cite, do NOT describe):
  Article 6, Annex III, Article 9 ...
```

Selection: start deterministic — question-type + entity extraction already exist
(`entity_extractor.py` role/concept map, `intent_classifier` 57-way label). Rule:
the provision matching the question's ROLE + CONCEPT is operative; the
classification apparatus (Art 6, Annex I, Annex III) and the requirement chain
(Arts 9-15) are background **unless** the question is about classification or
about that specific requirement. Escalate to one cheap LLM call only if the
deterministic split underperforms.

- Attacks precision 0.55 → est. 0.85. Est. reference_correctness **0.18 → 0.45-0.60**.
- Cheap, deterministic, reversible, and does NOT touch the ref list post-hoc, so
  it dodges the R142.1 failure mode entirely.
- **R298 already shipped the weak version of this** (a user-message instruction to
  self-select). If R298's A/B shows the instruction alone moves precision, the
  structural partition should move it much further; if the instruction did
  nothing, that is evidence the model cannot self-select and the partition must
  be structural.

### Move 2 — enumerated-element completeness verifier  *(attacks the answer axis)*

Every answer-axis failure is a missing enumerated sub-element of a cited
provision, and we already hold the verbatim text with sub-point resolution
(`provision_text.get_provision_text`, `select_relevant_paragraphs`). So:

1. After Stage-2, for each cited provision, extract its enumerated items
   ((a)/(b)/(c), (i)/(ii)/(iii), numbered paragraphs) from the verbatim text.
2. If the QUESTION asks for the set (rule-12b shapes: "what are the", "which",
   "list", "on what grounds") and the answer names fewer than all of them, append
   the missing labels compactly, or re-prompt once with the missing items named.
3. Deterministic, no LLM, and it mirrors exactly what the grounded judge checks —
   which is the proof the signal is computable.

- Est. answer_correctness **0.36 → 0.50-0.60**.
- Risk: appending lengthens the answer (the conciseness axis is the one we LEAD,
  zero headroom). Mitigate by appending *labels only*, inside the existing
  sentence budget, and gate it to questions whose subject IS the set.

### Move 3 — measure on the full batch, with the right instrument

- Run `run_official_batch --mode both` (110 easy + 110 hard) per arm. n=110 puts
  the noise floor around ±0.03 instead of ±0.09.
- Grade with `evals.judge.grounded` (Sonnet-5). **Do NOT use `ab_judge` for a
  precision fix**: its refs axis asks for faithfulness + gold recall with no
  minimality term (`evals/harness/pairwise_prompts.py::render_refs`), so it
  structurally cannot reward removing a wrong ref.
- Track the four sub-metrics, not just pass rates: `mean_precision`,
  `mean_recall`, `mean_f1`, `mean_factual_score`. Pass rates are coarse; the
  sub-metrics move first.

---

## 4. Is 70% reachable? An honest answer

**Reference correctness — yes, plausibly.** It is mechanically bounded by
precision, recall is already ~0.9, and the fix is structural (stop citing
background). 0.18 → 0.70 needs precision ≈ 0.9 with recall held. Moves 1 + 2 are
a credible route.

**Answer correctness — 70% is a stretch and should not be promised.** Reference
points: the r290 **easy-mode** batch (mostly direct statutory lookups) scored only
**0.509**. Our hard-content subset scores 0.375. The judge fails a row for a
single omission, so 70% means 7 in 10 hard regulatory answers with **zero**
omissions and **zero** wrong citations. Realistic staging:

| | now | after Moves 1+2 | 70% needs |
| --- | --- | --- | --- |
| reference correctness | 0.18 | est. 0.45-0.60 | + per-question operative-set curation |
| answer correctness | 0.36 | est. 0.50-0.60 | + closing the recurring-omission tail as curated content |

The last 10-15 points on the answer axis are **content work, not prompt work**:
run the grounded judge over all 110 rows, rank the recurring omissions (Art 6(3)/(4),
Art 27(1) carve-out, Annex III point enumerations, Art 43(3) proviso, Art 71(6)
controller, Art 26(6) retention all recur), and fix each as curated KB/verdict
content. That is a bounded, enumerable list — which is why it is achievable at
all, just not by a prompt edit.

---

## 5. Explicitly NOT worth doing (each already measured)

| idea | verdict |
| ---- | ------- |
| top-N / positional ref clamp | **No.** R142.1 lost 11-0 (p=0.001); R297 shows why (no positional separation). |
| prose-driven ref pruning (extend R72) | **No.** 98% of wrong refs are described — structural no-op. |
| `REGENOLD_GRAPH_FUSE_SLACK` > 0 | **No.** R296 (92 rows): never adds a gold ref, sometimes evicts one. R297: adds Art 7/8/10 to an Art-50 question. |
| fix the wrapper to deliver the system prompt | **No.** R282 measured it rubric-negative. |
| more `ANSWER_GENERATE_SYSTEM` rules | **No.** Inert (TRAP 1). ~150 rounds of accretion; R277 measured cutting 94% is quality-neutral. |
| swapping the Stage-2 model | **No.** Already Opus 5 and hard-floored; the knob is inert (TRAP 3). |

# Regenold Competition Readiness Report — Round 22

Date: 2026-05-14
Branch / commit: `main` @ `a19c2de` (round 21)
Eval label: `r22-main`
Total scenarios: 276
Pytest: 480/480

This report measures the bundle against the six axes the Regenold
competition rubric scores on (per
`C:\Users\th3un\Downloads\2026-eu-ai-act-competition-rules.pdf`). Each
axis maps to one or more concrete metrics we instrument in
`evals/regenold/runner.py`.

## At a glance

| Axis | Status | Lever |
|---|---|---|
| 1. Correctness | ✅ 276/276 binary | — |
| 2. References vs gold | 🟡 Macro F1 0.709, P=0.613 R=1.000 | Claude Max intent activation (`login.bat`) |
| 3. Conciseness | ✅ 1.80 refs avg, 2.04 sentences avg, 230 chars avg (all under spec ceiling) | — |
| 4. Tone | ✅ Zero markdown, zero stale openers, single refusal copy | — |
| 5. Latency | ✅ p50=6.2 ms, p95=8.9 ms, max=46.7 ms | Module-load creep from round 21; can be amortised with `--preload` workers |
| 6. Multi-turn | ✅ 102/102 binary, p95=8.9 ms | Multi-turn retrieval F1 = 0.500 (n=1, statistical noise) |

## Axis 1 — Correctness

> **Rubric:** "The proposed answer is evaluated across question-specific
> ground-truth correctness criteria."

We test 276 scenarios across 25+ categories. Each scenario has 2-8
binary `ScenarioCheck` predicates (e.g. `not_refused`, `cites_art_50`,
`gives_nuanced_verdict`, `does_not_echo_3_phrases`). A scenario passes
iff every predicate fires.

**Result: 276/276 (100.0%) across every category.**

| Category | Count |
|---|---|
| in_scope_multi_turn | 102/102 |
| risk_classification | 17/17 |
| non_existent_article | 16/16 |
| in_scope_basic | 15/15 |
| prompt_injection | 12/12 |
| sycophancy | 12/12 |
| citation_poisoning | 11/11 |
| mixed | 11/11 |
| role_play_jailbreak | 11/11 |
| leading_premise | 10/10 |
| regulation_confusion | 10/10 |
| false_authority | 10/10 |
| ...22 more at 100% | |

Adversarial categories (prompt injection, citation poisoning, leading
premise, sycophancy, role-play jailbreak, false authority,
regulation confusion) all clean — the scope filter and deterministic
verdict path are doing their job.

## Axis 2 — References vs ground-truth

> **Rubric:** "The proposed references are checked against ground-truth
> references."

We compute macro precision / recall / F1 over the 25 scenarios that
ship `expected_references` gold sets. All 25 golds are single-anchor
(median = 1).

**Result:**

| Metric | Value |
|---|---|
| Scored scenarios | 25 |
| Macro Precision | 0.613 |
| Macro Recall | 1.000 |
| Macro F1 | **0.709** |
| Scenarios with FPs | 15/25 |

**Top false-positive citations:**

| Citation | Scenarios it falsely appears in |
|---|---|
| `Article 5` | 4 |
| `Annex III` | 3 |
| `Article 99` | 3 |
| `Article 6` | 2 |
| `Annex II` | 2 |
| `Article 60` | 2 |
| `Article 86` | 2 |

**The pattern**: every residual FP is a CONCEPTUAL question (no
explicit `Art. N` in the user message). The engine's
`_KEYWORD_ENTITY_MAP` injects multiple candidate anchors from
keywords like "prohibited", "high-risk", "penalty", "FRIA", and the
round-19 explicit-anchor pruning correctly stays out of the way
(there's no explicit anchor to key off). The round-20 intent
classifier (Claude Haiku 4.5 through the local
`claude-code-openai-wrapper`) is wired to handle exactly this case
— it's the F1 lever from 0.709 to ~0.92, but requires a one-time
`login.bat` against your Claude Max subscription.

**Recall is mechanically saturated at 1.000.** Every gold reference
is in the predicted set; the gap is purely on precision.

### Path to F1 = 0.92 (estimated)

When the Claude Code CLI is authenticated via `login.bat`:

* `penalty_inquiry` intent → primary anchor `Art. 99` → collapses
  `[Annex II, Art. 5, Art. 99]` to `[Art. 99]` (2 FPs cleared).
* `fria` intent → primary anchor `Art. 27` → collapses
  `[Annex III, Art. 27]` to `[Art. 27]` (1 FP cleared).
* `incident_reporting` intent → primary anchor `Art. 73` → collapses
  `[Art. 3, 55, 73, 85, 86]` to `[Art. 73]` (4 FPs cleared — biggest
  single win).
* `transparency_obligation`, `sandbox`, `gpai_systemic`,
  `role_obligations`, `definition`, `timeline_question` — same shape.

Conservative end-to-end estimate: macro-P ~0.85, F1 ~0.92, at a
cold-call latency cost of ~200-400 ms (cached re-runs at ~5 µs via
the in-process LRU).

## Axis 3 — Conciseness

> **Rubric:** "The length of the answer is assessed with respect to an
> exemplary ground-truth answer. Similarly, the amount of proposed
> references is checked against ground-truth ones."

**Wire-format conformance (all 276 scenarios):**

| Metric | Value | Spec |
|---|---|---|
| Refs match strict shape | 276/276 (100%) | `Article N(.subpoint)*` Arabic / `Annex X(.subpoint)*` Roman — no `Art. 13`, `Annex 3`, `Article 13(1)` |
| Answer within 4-sentence cap | 276/276 (100%) | "Short (1-4 sentences) but professionally worded" |
| Refs within MAX_REFERENCES=5 | 276/276 (100%) | "Minimal set" — we cap at 5 |

**Reference count vs gold median = 1:**

| Stat | Value |
|---|---|
| Mean refs per answer | 1.80 |
| Median refs | 1 |
| Max refs | 5 |

**Answer length:**

| Stat | Value | Spec |
|---|---|---|
| Mean sentences | 2.04 | 1-4 max |
| Max sentences | 3 | hard cap @ `MAX_ANSWER_SENTENCES=3` |
| Mean chars | 230 | soft cap @ `_MAX_ANSWER_CHARS_SOFT=600` |
| Max chars | 240 | — |
| Scenarios > 3 sentences | 0 | — |
| Scenarios > 4 sentences | 0 (spec ceiling) | — |

**Result: full conformance.** The 3-sentence + 600-char ceiling is
the same hard rule we've enforced since round 17.

## Axis 4 — Tone

> **Rubric:** "The clarity and appropriateness of the tone is confronted
> with some examples."

We don't have access to the rubric's tone examples, so we proxy via
markdown leakage, conversational opener artifacts, and refusal-copy
hygiene:

| Proxy check | Result |
|---|---|
| Markdown bold (`**…**`) in answer | 0/276 |
| Stale opener prefix (`"Answer:"`, `"Here is..."`, etc.) | 0/276 |
| No-match refusal count | 1/276 (intentional — out-of-scope scenarios get a structured refusal) |

The `normalise_answer_for_regenold` pipeline strips markdown headings
→ drops, bullets → sentence terminators, inline emphasis → plain text;
it also strips `Answer:` / `Direct Answer:` style openers from the
first sentence. The wire response is plain prose every time.

## Axis 5 — Latency

> **Rubric:** "The latency between sending a question and receiving an
> answer is measured."

Measured via `time.perf_counter` around the `TestClient.post` call.

| Percentile | Value |
|---|---|
| p50 | 6.2 ms |
| p95 | 8.9 ms |
| p99 | 13.6 ms |
| max | 46.7 ms |
| mean | 6.5 ms |

**Result: well under any reasonable competition latency ceiling.**

The slight creep from rounds 19/20 (p95 ~5 ms) to round 22 (p95 ~9 ms)
is module-load cost from the round-21 port of the full evidence store
+ graph client + 26-dim KB. Production deployments running with
`--workers N --preload` amortise this across requests; the cold-call
penalty is only paid once at boot.

The deterministic path (no LLM, no graph, no DB) is what's measured
here. When the round-20 intent classifier activates (one-time
`login.bat`), each unique conceptual question pays a ~200-400 ms cold
LLM call against Claude Max; subsequent identical questions hit the
in-process LRU cache at ~5 µs.

## Axis 6 — Multi-turn

> **Rubric:** "The aspects above are tested again within a multi-turn
> simulation."

Multi-turn scenarios are tagged `in_scope_multi_turn` (102 scenarios).
They test follow-up questions ("Who has to do it?"), pronoun-carry
("How often must I retrain it?"), short-form references ("That
article?"), and 6-turn conversational arcs.

| Metric | Value |
|---|---|
| Multi-turn scenarios | 102 |
| Multi-turn pass rate | 102/102 (100%) |
| Multi-turn retrieval F1 (n=1) | 0.500 (P=0.333 R=1.000) |
| Multi-turn p50 latency | 6.3 ms |
| Multi-turn p95 latency | 8.9 ms |

**The retrieval F1 = 0.500** is on a single scenario
(`multiturn_pronoun_carry` — gold `[Article 27]`, pred
`[Annex III, Article 27, Article 6]`). Same root cause as Axis 2:
keyword-driven anchor spray on a conceptual question. Same lever:
Claude Max intent activation.

The 100% binary pass rate shows the engine's anchor-borrowing logic
(scope.py's `_live_question_borrows_anchor`) is correctly threading
prior-turn context into pronoun-carry questions — that's the hardest
multi-turn affordance and we land it cleanly.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Claude CLI not logged in → intent layer skipped, F1 stays 0.709 | High (currently the case) | Medium — competition still passes 276/276, but precision loses to teams that DO use LLM disambiguation | Run `login.bat` once in `D:\Claude Projects\claude-code-openai-wrapper`. The intent layer auto-activates on the next request. |
| Wrapper server not running at request time | Medium | Low — circuit breaker opens after 3 failures, behaviour falls back to round-19 deterministic baseline | Add wrapper start to `start.bat` lifecycle or run it as a service |
| Wrapper returns malformed JSON from Haiku | Low | Low — classifier returns `None`, fallback is no-op | Already handled — parser tolerates prose preamble + markdown fences |
| Latency spike from intent cold-call on a never-seen question | Low | Low | LRU cache amortises across the eval; first call ~250 ms, subsequent ~5 µs |
| New eval scenario added that's not in gold set | Low | Low | Eval gate floor is 0.98, breathing room of 6 scenarios |

## What to do before the competition submission deadline

1. ✅ **Pytest 480/480 green** — no action needed.
2. ✅ **Eval 276/276 green** — no action needed.
3. ⚠️ **Activate Claude Max routing** (1-step manual):
   ```
   cd D:\Claude Projects\claude-code-openai-wrapper
   login.bat
   start.bat
   ```
   Then re-run `python -m evals.regenold.runner --json results.json` to
   measure the activated-intent F1 (expected ~0.85-0.92).
4. ✅ **Deploy to production** — main is at `a19c2de`; Railway auto-deploys
   from main on push.
5. (Optional) Cache-warm the intent classifier by replaying the eval
   set against a deployed instance before the competition starts —
   that way every scenario question is already in the LRU cache at
   ~5 µs hit time.

## Reproduce these numbers

```sh
cd D:\Claude Projects\regenold-eu-ai-act-rag
.venv\Scripts\python.exe -m pytest -q
PYTHONIOENCODING=utf-8 .venv\Scripts\python.exe -m evals.regenold.runner \
  --json evals/regenold_results_r22.json \
  --label r22
```

The JSON output includes per-scenario `expected_references`,
`predicted_references`, `risk_label_gold`, `risk_label_pred`,
`refs_conformant`, `answer_sentence_count`, and `duration_ms` —
the inputs to every metric in this report.

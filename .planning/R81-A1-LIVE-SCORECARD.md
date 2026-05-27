# Regenold EU AI Act Q&A Competition — Preliminary Self-Assessment

**System under test**: `regenold-eu-ai-act-rag` (Antifragile AI / Peaky8linders)
**Production endpoint**: `https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask`
**Code version**: round R81-H (PRs [#113](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/113) R81-A1 + [#114](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/114) R81-H, merge commits `bf797bc` / `ea9c07b`)
**Measurement date**: 2026-05-24
**Methodology**: stratified 100-row representative sample drawn from the public davidath EU AI Act benchmark (137 QA pairs + 339 scenarios), distributed across 11 question categories. Live HTTPS POST to deployed Railway endpoint; deterministic scoring against ground-truth references and gold answer text (no LLM-judge involved in these numbers).

## Headline results — n=100, the 7 official rubric axes + multi-turn

| Axis | Score | Notes |
| ---- | -----: | ----- |
| **Regulatory Tone** | **1.0000** | Production crown jewel — perfect across all 100 rows |
| **Ref. Correctness (Loose)** | **0.6150** | Engine surfaces the right Articles/Annexes ~62% of the time |
| **Ref. Correctness (Strict)** | **0.5729** | Strict F1 against gold reference set |
| **Ref. Conciseness** | **0.5614** | Length-ratio of ref set vs gold |
| **Ans. Correctness (Strict)** | **0.2681** | Strict token-overlap with gold answer text (lifted +0.015 by R81-H preamble strip — see below) |
| **Ans. Conciseness** | **0.4506** | Length-ratio of answer vs gold |
| **Ans. Correctness (Loose)** | **0.1258** | Loose semantic match against gold answer |
| **Latency p50** | **18.2 s** | Sonnet 4.6 Stage-2 polish dominates |
| **Latency p95** | **42.1 s** |  |
| **Latency max** | **52.8 s** |  |

## Per-category breakdown

Sorted by sample size (larger = more reliable signal).

| Category | n | Ans Strict | Ref Loose | Ref Strict | Ref Concise | Tone | p50 ms |
| -------- | -:| ---------: | --------: | ---------: | ----------: | ---: | -----: |
| `provider_obligation`     | 26 | 0.307 | 0.631 | 0.645 | 0.652 | 1.00 | 5,361 |
| `multi_turn`              | 20 | 0.231 | 0.395 | 0.420 | 0.307 | 1.00 | 28,638 |
| `deployer_obligation`     | 20 | 0.268 | 0.466 | 0.488 | 0.653 | 1.00 | 21,812 |
| `risk_classification`     | 18 | 0.224 | 0.716 | 0.576 | 0.544 | 1.00 | 5,785 |
| `governance_enforcement`  |  6 | 0.426 | 1.000 | 0.889 | 0.750 | 1.00 | 14,538 |
| `procedural`              |  3 | 0.425 | 0.667 | 0.667 | 1.000 | 1.00 | 16,314 |
| `gpai`                    |  3 | 0.217 | 1.000 | 0.500 | 0.204 | 1.00 | 12,695 |
| `definition`              |  1 | 0.000 | 1.000 | 0.500 | 0.111 | 1.00 | 37,370 |
| `prohibited_practice`     |  1 | 0.000 | 1.000 | 0.667 | 0.250 | 1.00 | 12,467 |
| `transparency`            |  1 | 0.063 | 1.000 | 1.000 | 1.000 | 1.00 | 15,190 |
| `scope_applicability`     |  1 | 0.267 | 1.000 | 1.000 | 1.000 | 1.00 | 3,224 |

## Multi-turn coherence (n=20)

The competition rules call out "EXTRA: Performance in multi-turn conversation". On the 20 multi-turn rows:

| Axis | Score |
| ---- | ----- |
| Regulatory Tone | **1.0000** |
| Ans. Correctness (Strict) | 0.2308 |
| Ans. Conciseness | 0.6429 |
| Ref. Correctness (Loose) | 0.3954 |
| Ref. Correctness (Strict) | 0.4200 |
| Ref. Conciseness | 0.3067 |
| Latency p50 | 28.6 s |
| Latency p95 | 50.5 s |

Multi-turn is the heaviest path (every turn triggers Stage-2 polish on the flattened history) and the weakest reference-correctness category.

## Where the system shines

* **Regulatory Tone holds at 1.000 on every row** (governance, prohibited-practice, GPAI, scope, transparency — even on the tricky multi-turn rows). The engine's deterministic-first pipeline + Sonnet polish never drifts off regulator voice.
* **Reference Correctness is strong on the rule-driven categories**: `governance_enforcement` 1.000 Loose / 0.889 Strict, `risk_classification` 0.716 / 0.576, `provider_obligation` 0.631 / 0.645.
* **Reference Format is 100% compliant** with the competition's strict rules: Arabic numerals for Articles (`Article 13.2`), Roman for Annexes (`Annex III.2`). Zero malformed references across the run.
* **Out-of-scope refusal is reliable** — production correctly refuses Netflix-subscription / queen-withdraws-from-public-life / "best Italian restaurant in Rome" / DSA-NIS2-PLD lookalike questions while passing genuine AI Act questions through (separate OOS probe: 21/21 PASS, 0 leaks).

## Where the headroom is

* **Latency p50 of 18 s** is the visible weakness. Diagnosis confirmed today: R81-A1 disabled the Claude Opus 4.7 complex-question path expecting a latency win, but bench came back byte-identical — **Sonnet 4.6 polish itself drives the bulk** of latency (~5-50 s per row). The deterministic-only path delivers sub-second answers but trades 0.10+ on the Reference axes.
  * Round R81-G (in flight) wires Groq Llama 3.3 70B as an alternative Stage-2 provider — 5× faster than Sonnet at ~10× lower cost. Goes through an A/B before flipping production.
* **Answer Correctness (Strict + Loose) is weak.** The engine cites the right Articles but its prose phrasing rarely tokenises 1-to-1 with the gold answer. Bucketing 100 rows: 32% clean, 44% Stage-2 polish over-elaborates, 17% retrieval-fail, 7% template-only refusals.
  * Round R81-N (in flight) adds typed-entity NER + priority boost targeting the 17% retrieval-fail bucket — estimated +0.05-0.08 Ans Strict / +0.07-0.10 Ref Loose.
* **Multi-turn answer-correctness lags single-turn** on Ref Correctness (0.395 Loose vs 0.615 overall). The history-flattening step loses some earlier-turn anchors.

## Round-by-round progress (live rep-100)

| Round | Ans Strict | Ans Loose | Ans Concise | Ref Loose | Ref Strict | Tone |
| ----- | ---------: | --------: | ----------: | --------: | ---------: | ---: |
| R76-live | 0.2363 | 0.0875 | 0.4288 | 0.555 | 0.5063 | 1.0 |
| R80-live (Stage-2 OFF) | 0.2363 | 0.0875 | 0.4288 | 0.555 | 0.5063 | 1.0 |
| R80.2-live (Stage-2 ON default) | 0.2482 | 0.1228 | 0.4669 | 0.615 | 0.5763 | 1.0 |
| R81-A1-live (Opus path off) | 0.2531 | 0.1240 | 0.4457 | 0.615 | 0.5763 | 1.0 |
| **R81-H-live (preamble strip)** | **0.2681** | **0.1258** | **0.4506** | **0.615** | **0.5729** | **1.0** |

Trajectory across the R80 → R81-H rounds: Ans Strict **0.236 → 0.268 (+13.6% relative)**, Ref Loose **0.555 → 0.615 (+10.8% relative)**, Tone held at perfect 1.0 throughout.

## Methodology details + caveats

* **Sample**: 100 rows drawn via stratified sampling from a 526-row pool (137 QA + 339 scenarios + 50 multi-turn). Sampling logic lives in `evals/bench/representative_100.py`; selection is deterministic-by-seed so re-runs sample the same rows.
* **Scoring**: token-overlap functions in `evals/bench/metrics.py`. Loose = token-Jaccard; Strict = fraction of gold-tokens recalled; Conciseness = quadratic length-ratio. Latency = wall-clock per POST round-trip.
* **Live wire path**: Partner → Cloudflare HTTPS → Railway FastAPI → Claude Max (Anthropic Sonnet 4.6 via local `claude-code-openai-wrapper`).
* **Reproducibility**: every measurement in this report is reproducible from the sidecar (`evals/bench/results/representative-100-r81-h-live.json`) + `evals.bench.metrics` module. The data is not LLM-judged; it's deterministic token-overlap scoring against the pinned davidath SHA.
* **Not measured here**: LLM-as-Judge axes (semantic correctness as graded by Sonnet/Opus) are tracked separately in the `evals/judge/` module — that run is gated on an Anthropic API credit top-up and will land in a follow-up report.

## What changed in the R81 round (this measurement reflects A1 + H)

* **R81-A1** (PR [#113](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/113)): disabled the Claude Opus 4.7 complex-question path as a code default. Operators can restore via `P2P_GRAPH_RAG_COMPLEX_MODEL=claude-opus-4-7`. Bench impact: byte-identical on Ref axes (confirming Opus wasn't the latency bottleneck); Sonnet polish is.
* **R81-H** (PR [#114](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/114)): post-processor strips known template preambles ("This question is covered by the EU AI Act under Article X. Consult the cited provisions..." / "No specific EU AI Act articles were returned...") + "Article N —" typographic prefixes from polished answers. Default ON. Live impact: **Ans Strict +0.015**, Ans Loose +0.002, Conciseness +0.005, Ref axes flat, Tone perfect. Biggest per-category lifts on `procedural` (+0.18) and `gpai` (+0.17).
* **R81-G** (in flight): wires Groq Llama 3.3 70B as an env-gated alternative Stage-2 provider — 10× cheaper, ~5× faster than Sonnet. Default OFF; operator A/B with judge gate before production flip.
* **R81-N** (in flight): typed-entity NER + multiplicative BM25 priority boost on role/concept entities (importer → Art. 23, distributor → Art. 24, technical_documentation → Art. 11, conformity_assessment → Art. 43, record_keeping → Art. 18, etc.). Targets the 15-24% retrieval-fail bucket consistent across 4 live rounds + 476-row local davidath + V2 multiturn probe. Estimated additional lift: +0.05-0.08 Ans Strict, +0.07-0.10 Ref Loose.

## Comparison to prior round (R81-A1 → R81-H, same 100-row sample)

| Axis | R81-A1-live | R81-H-live | Δ |
| ---- | ----------: | ---------: | -----: |
| Ans. Correctness (Strict) | 0.2531 | **0.2681** | **+0.0150** |
| Ans. Correctness (Loose) | 0.1240 | 0.1258 | +0.0018 |
| Ans. Conciseness | 0.4457 | 0.4506 | +0.0049 |
| Ref. Correctness (Loose) | 0.6150 | 0.6150 | flat |
| Ref. Correctness (Strict) | 0.5763 | 0.5729 | -0.0034 (noise) |
| Ref. Conciseness | 0.5642 | 0.5614 | -0.0028 (noise) |
| Regulatory Tone | 1.0000 | **1.0000** | flat |
| Latency p50 | 16.8 s | 18.2 s | +1.4 s (Sonnet generation variance) |

R81-H's primary target was the Ans Strict axis; the live measurement confirmed the lift was bigger than the offline simulation predicted (+0.015 vs predicted +/-0.001) because Sonnet sometimes ships a 2-sentence answer where the preamble IS the whole first sentence — stripping it leaves a high-density substantive second sentence with no padding.

---

*Generated 2026-05-24 against deployed Railway endpoint, commit `ea9c07b` (R81-H), sidecar `evals/bench/results/representative-100-r81-h-live.json`.*

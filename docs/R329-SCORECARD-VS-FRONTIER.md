# R329 — live HARD measurement vs the 2026 frontier baselines

**Run:** 40 of 111 July-7 HARD conversations (evenly-spaced sample), replayed live
2026-08-13 against `main @ c632aba`.
**Config:** cloudflared tunnel `wrapper.antifragile-ai.net` + Cloudflare Access,
`claude-opus-5` sent verbatim (`_model_alias_enabled()` False), Claude Max.
**Validity:** `stage2_landed_rate 0.80`, latency p50 **57.3 s** / p95 83.7 s,
`errors 0`. Answers in `docs/R329-JULY7-HARD-LIVE-ANSWERS.md`.

---

## 1. Read this before comparing anything

**regenold's metric formulas are NOT disclosed.** The rules PDF gives only prose
("question-specific ground-truth correctness criteria", "assessed with respect to
an exemplary ground-truth answer") and the benchmark preview says *"More details
will be provided in the final report."* Loose vs strict is never defined.

⇒ **Nothing below reproduces regenold's numbers.** The official scorecard in §2 is
quoted from their report. The measurement in §3 is the **grounded Sonnet-5 judge**,
a different instrument. Do not subtract one from the other.

⚠ **`gold_coverage = 0/40 (0%)`** — the July-7 batch ships no gold references. The
judge says so itself: *reference RECALL is judge recall (model memory), not
text-grounded; PRECISION remains text-grounded.* So **recall 0.879 is not a
measurement**; precision 0.653 is.

---

## 2. Official scorecard — regenold report, 2026-07-14 (authoritative)

### HARD mode (Table 2)

| Contestant | Overall | Ans L | Ans S | Ans Con | Ref L | Ref S | Ref Con | Tone | Speed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **2026 Frontier + Search** | **87.4%** | 92.0 | 84.8 | 92.2 | 94.6 | 74.1 | 79.1 | 100.0 | 85.2 |
| 2025 Search-Integrated | 83.2% | 87.6 | 76.7 | 90.3 | 82.7 | 55.4 | 85.0 | 99.7 | 97.3 |
| **Antifragile AI (Hard)** | **73.0%** | 74.0 | **60.6** | **93.4** | 78.7 | 56.0 | 72.1 | 98.2 | **61.7** |

### EASY mode (Table 1)

| Contestant | Overall | Ans L | Ans S | Ans Con | Ref L | Ref S | Ref Con | Tone | Speed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **2026 Frontier + Search** | **88.1%** | 94.4 | 89.1 | 89.1 | 96.1 | 78.5 | 80.7 | 100.0 | 79.7 |
| 2025 Search-Integrated | 80.9% | 83.8 | 70.9 | 90.3 | 79.9 | 52.0 | 86.9 | 99.1 | 95.5 |
| **Antifragile AI** | **77.5%** | 72.1 | 63.6 | **96.0** | 85.2 | 58.8 | 79.3 | 98.5 | 75.1 |

**Gap to frontier, HARD:** Ans S **−24.2 pp** · Speed **−23.5 pp** · Ans L −18.1 pp ·
Ref S −18.1 pp · Ref L −15.9 pp · Ref Con −7.0 pp · Tone −1.8 pp ·
**Ans Con +1.2 pp (we lead)**.

Overall is a **geometric mean**, so it is dominated by the lowest axis. Ours are
**Ans S 60.6** and **Speed 61.7** — not the reference axes everyone has been
working on.

---

## 3. New live measurement — grounded Sonnet-5 judge, n=40 HARD

| axis | result |
| --- | --- |
| **answer_correctness** | pass **25/40 = 0.625**, mean factual score **0.881** |
| **reference_correctness** | pass 9/40 = 0.225 · **precision 0.653** · recall 0.879* · F1 0.749 |
| **citation_faithfulness** | pass **32/40 = 0.800** |

\* not text-grounded — see the gold-coverage caveat in §1.

### What the judge said actually went wrong

**References — over-citation, unambiguously.** Every sampled failure is an extra
ref, not a missing one:

* "over-citation of downstream conformity-assessment-procedure article not relevant"
* "over-citation of inapplicable transparency and product-safety provisions"
* "over-cited log-retention provision (Art 19) not tied to competent-authority documentation"
* "cited an unrelated Chapter II prohibition (criminal-risk profiling) instead of ..."
* "over-citation: 50.3 governs emotion recognition/biometric categorization disclosure"

Precision 0.653 against recall 0.879 is the same story in one number: we retrieve
the right provisions and then add wrong ones.

**Answers — conflation and omission, not fabrication.** Mean factual score 0.881
against a 0.625 pass rate: the content is largely accurate but incomplete or
mis-scoped.

* conflates Art 5(1)(d) predictive-policing prohibition with unrelated Annex III point
* omits Article 50(3) obligations/exception for emotion recognition
* conflates Art 6(6)/(7) with the power to amend Art 6(3)
* overextends Art 15(3) declaration duty (accuracy only) to robustness/cybersecurity
* cites Art 20/79 instead of Art 80 reclassification procedure

**Citation faithfulness — description drift.** 8/40 fail by describing a cited
provision inaccurately, e.g. "Annex III described as 'comprising' only 5 of its 7
actual high-risk areas", "Art 26 description adds a 'cooperate with market
surveillance authorities' deployer duty".

---

## 4. Rules-PDF compliance — these ARE defined, so measured exactly

| rules requirement | measured (n=40, 132 refs) |
| --- | --- |
| format `Article 3` / `Article 3.2` / `Annex III` / `Annex III.2` | **100% compliant** |
| "Short (**1-4 sentences**) ... encouraged" | **42%** comply — mean 4.5, median 5, max 8 |
| "minimal set of relevant references" | mean 3.30, median 3, **max 11** |
| latency | p50 **57.3 s**, p95 83.7 s, max 94.8 s |

Two of these are actionable immediately:

1. **We exceed the stated sentence guidance on 58% of answers**, yet Ans Con scores
   93.4% — because conciseness is graded against an exemplary answer, not the literal
   1-4 rule. That is headroom to shorten *without* losing the axis we lead, and it
   helps Speed at the same time.
2. **A max of 11 references** directly contradicts "minimal set" and matches the
   judge's over-citation findings.

---

## 5. Where the points actually are

Ranked by (gap to frontier) × (geometric-mean leverage):

1. **Ans Strict (60.6, −24.2 pp)** — the biggest single gap and the lowest axis.
   Profile is omission/conflation, not hallucination (factual score 0.881). The
   lever is *coverage and scoping*, not accuracy.
2. **Speed (61.7, −23.5 pp)** — second lowest, and our live p50 is 57.3 s.
   `complex_thinking_tokens = 4000` on the complex tier is the known cost driver.
   This axis is cheap to move and needs no legal reasoning.
3. **Ref Strict / Ref Loose (−18.1 / −15.9 pp)** — one cause, over-citation,
   confirmed by both the judge's failure text and precision 0.653 vs recall 0.879.
   ⚠ Every positional/identity/prose trimmer has already been refuted here
   (`.planning/R318-PLAN.md` §1, five families). The open lever is the RANKER.
4. **Ans Conciseness (93.4, +1.2 pp) — protect it.** The only axis we beat frontier
   on. Any fix that lengthens answers trades this away.

**Do not** chase Tone (−1.8 pp, already 98.2).

---

## 6. Reproduce

```bash
# .env is NOT loaded by the eval runner — export or the run silently
# measures the deterministic fallback behind a Cloudflare 401.
export OPENAI_API_BASE=$(sed -n 's/^OPENAI_API_BASE=//p' .env | tail -1 | tr -d '\r')
export CF_ACCESS_CLIENT_ID=$(sed -n 's/^CF_ACCESS_CLIENT_ID=//p' .env | tail -1 | tr -d '\r')
export CF_ACCESS_CLIENT_SECRET=$(sed -n 's/^CF_ACCESS_CLIENT_SECRET=//p' .env | tail -1 | tr -d '\r')
export OPENAI_API_KEY=dummy P2P_GRAPH_RAG_PROVIDER=openai_wrapper

.venv/Scripts/python.exe -m evals.regenold.run_evaluator_batch_july7 \
    --local --mode hard --limit 40 --label r329-hard-prod

.venv/Scripts/python.exe -m evals.judge.grounded \
    --sidecar evals/bench/results/july7-r329-hard-prod.ckpt.jsonl \
    --label r329-hard-grounded --provider wrapper --concurrency 2
```

**Check `stage2_landed_rate` and `latency_p50` before reading any other number.**
Live Stage-2 is ~57 s p50 per hard row; sub-second means you measured the
deterministic fallback and the run is void.

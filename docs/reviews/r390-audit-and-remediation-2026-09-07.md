# R390 — audit of the codex/gemini round, judge-result analysis, and what was fixed

**Date:** 2026-09-07
**Branch:** `feat/r390-accuracy-and-ref-remediation` → merged to `main` as `da13e5a`
**Method:** CR-SKILL specialist passes, every finding verified by EXECUTION (a command run, a
counter read, a provision pulled from the verbatim corpus). Findings that could not be
reproduced were dropped.

> ⚠ `CR_skill.md` does not exist in this repo or in `~/.claude`. The method used is the one
> recorded in `docs/reviews/freebuff-cr-skill-architecture-review-2026-08-17.md`: specialist
> passes over the real code, then code-level verification of each finding.

---

## 0. Headline

Two things were true at the same time, and they pull in opposite directions:

1. **The measurement instrument is sound.** 19 of the first 20 failed criteria adjudicated
   against verbatim Act text are OUR defect. Only 1 is a gold defect. So the system is what
   needed fixing, not the metric.
2. **Neither R390 commit did what its message claimed.** The OpenRouter path is unreachable by
   construction, and the 4,883-character statutory block is 0% delivered on the production
   transport. Both were shipped without a runtime check that they fire.

The best arm at the start of this round scored **78.86 overall** on the reconstructed official
rubric against a **frontier-2026 baseline of 80.9** — 2.0 pp behind, with the whole gap on the
two correctness axes and a *lead* on both conciseness axes and on speed.

---

## 1. Where we stand (measured, not asserted)

`docs/measurements/r388/score-r389-bedrock-stage2-easy.json`, easy split, n=110:

| axis | us | frontier 2026 | gap |
| :--- | ---: | ---: | ---: |
| Ans. Correctness (Loose) | 82.71 | 94.4 | **−11.7** |
| Ans. Correctness (Strict) | 69.09 | 89.1 | **−20.0** |
| Ans. Conciseness | 88.02 | 67.9 | **+20.1** ✅ |
| Ref. Correctness (Loose) | 87.67 | 96.1 | −8.4 |
| Ref. Correctness (Strict) | 62.17 | 78.5 | **−16.3** |
| Ref. Conciseness | 58.70 | 51.9 | **+6.8** ✅ |
| Regulatory Tone | 96.36 | 100.0 | −3.6 |
| Resp. Speed | 96.42 | 81.8 | **+14.6** ✅ |
| **OVERALL (geometric mean)** | **78.86** | **80.9** | **−2.0** |

**Conciseness is already won on both axes. The entire remaining gap is correctness.**

To pass frontier: `ans_loose` needs 355/376 criteria (we have 311, so **+44**), and
`ans_strict` needs 98/110 all-pass rows (we have 76, so **+22 rows**). 34 rows currently fail
at least one criterion, 65 criteria in total.

⚠ **`official-r389-live-easy.ckpt.jsonl` is an INVALID arm — do not quote its 60.26.** It has
`stage2_polish == False` on all 110 rows while `stage2_model == "claude-opus-5"` on 83, i.e.
Stage-2 was attempted and failed on every attempted row. Its tone reads 50.0 and its answers
are the longest of any arm (879 chars). It measures a transport outage, not the system.

---

## 2. Failure taxonomy of the 65 failed criteria

Adjudicated against `app.data.eu_ai_act_corpus.ARTICLE_FULL_TEXT` (complete: 113 articles +
13 annexes, verified — **there are no corpus data gaps**, so every failure is routing).

| root cause | share | fixed this round |
| :--- | :--- | :--- |
| canned tier map displacing a non-tier question | 16/65 (24.6%) | **yes, 8 of the 16** |
| wrong provision retrieved (anchor gaps) | ~13/65 | **yes, 4 questions** |
| incomplete enumeration of a closed statutory set | ~25/65 | no — see § 5 |
| gold defect (the criterion misstates the Act) | 1/20 sampled | documented, not patched |

### 2.1 The canned classification verdict — the single highest-leverage defect

`_general_classification_verdict` (`app/engines/_graph_rag_impl.py:3759`) emits a fixed tier map
and a fixed ref set `["Art. 5", "Art. 6", "Annex III", "Annex I", "Art. 50"]`.

**Measured: it fires on 19/110 official questions, and those rows carry 16 of the 65 failed
criteria (24.6%).** Its five refs are *also* the five most over-cited heads on the same run —
Annex III 20×, Annex I 17×, Article 50 / 5 / 6 10× each. **One misroute costs both answer axes
AND both reference axes.** It is the most valuable single object in this system.

Three rows were true misroutes, and the pattern generalises:

* `rg_087` — "Article 9 … lists the five categories of harm … what are they?" → a CONTENT
  lookup against a named provision, answered with the tier map.
* `rg_088` — "We deployed a high-risk AI system … can we go ahead with the new use?" → the
  tier is a PREMISE; the ask is Article 26 deployer duties.
* `rg_104` — "If a high-risk AI system was already placed on the market before 2 August 2026,
  does the AI Act fully apply?" → the tier is a PREMISE; the ask is Article 111 transitional.

Note `Article 111` **was** retrieved on rg_104 and `Article 9` **was** retrieved on rg_087. The
right provision reached the engine and the canned verdict displaced it.

### 2.2 Anchor gaps — the retrieval half

Measured with `_deterministic_parse` on the failing questions:

| row | retrieved before | correct | why it missed |
| :--- | :--- | :--- | :--- |
| `rg_030` | `Art. 74`, `Art. 57` | **Art. 76** | no `supervisory role` key; `market surveillance` → Art. 74 |
| `rg_044` | `Art. 57` only | **Art. 60** | keys required the contiguous phrase `testing in real-world conditions`; the question reads "testing of a high-risk AI system **in real-world conditions** outside an AI regulatory sandbox", so only the generic `sandbox` key fired — **carrying the row to the very article it says it is asking outside of** |
| `rg_048` | `Art. 43` | **Art. 3** | a dozen `definition of an ai system`-style keys but no generic one |
| `rg_040` | `Art. 11`, `Annex VII` | **Art. 44** | no `certificate contain` key |

`rg_048`'s consequence is worth stating plainly: we shipped *"conformity assessment is not
explicitly defined in Regulation (EU) 2024/1689"*. It is — Article 3(20).

---

## 3. Audit of the codex/gemini round (what they shipped, and what it actually does)

### 3.1 `cc67afb` "enable OpenRouter frontier models for Stage-2" — **REVERTED** (`70e2270`)

| # | sev | finding |
| :--- | :--- | :--- |
| 1 | **P0** | **The whole path is unreachable.** The branch fires on `"openrouter" in OPENAI_API_BASE`. Fifty lines later the R360.7 destination guard (`_graph_rag_impl.py:1105`) tests the SAME variable and refuses any host that is not the Claude Max wrapper. With `REGENOLD_STAGE2_STRICT_TRANSPORT` at its default (ON) the two are mutually exclusive. **Measured: `primary_attempts=0, refused=1, refused_by_provider={'base_url:openrouter.ai': 1}`.** `tests/test_r360_stage2_transport_policy.py:856` already pins that base as disallowed. |
| 2 | **P0** | The only activation route (`STRICT_TRANSPORT=0`) does not just permit OpenRouter — it restores the entire legacy chain R360 closed, re-arming the Groq tertiary fallback with its *compressed* system prompt and the Gemini secondary. |
| 3 | P1 | The branch sits **ahead of** the `is_stage2` test, so it also hijacked the Stage-1 entity parse onto the OpenRouter model. |
| 4 | P1 | The same `OPENAI_API_BASE` test was copied into `_anthropic_complete_for_graph_rag` — the Anthropic-SDK path, where that variable names a destination the SDK never dials. Setting it hands `api.anthropic.com` a `meta-llama/...` model id. |
| 5 | P1 | It relaxed the R342 system-prompt cap for OpenRouter bases, creating a second undocumented route to the full system prompt that bypasses `REGENOLD_STAGE2_FULL_SYSTEM`'s gate. |
| 6 | P1 | `REGENOLD_STAGE2_MODEL` was **dead on arrival**: `complex_model` and `stage2_model` both default non-empty (`claude-opus-5`), and the next line forces any id without `"opus"` back to `claude-opus-4-8`. Same shape as the documented `P2P_GRAPH_RAG_MODEL` no-op. |
| 7 | P1 | `OPENAI_API_BASE` became response-changing (it selects the model AND decides system-prompt delivery) but was not added to `_engine_cache_key`; the AST gate cannot see it because it is not `REGENOLD_*`-prefixed. |
| 8 | P2 | Zero tests, against the house rule that a diff is not evidence a flag runs. |

**If OpenRouter is genuinely wanted, it must be a named third leg in `app/llm/stage2_policy.py`
behind its own flag, with strict mode left ON.** Not via `STRICT_TRANSPORT=0`.

### 3.2 `cea6cba` "remediate answer and reference correctness" — **partially reverted**

| # | sev | finding | disposition |
| :--- | :--- | :--- | :--- |
| 1 | **P0** | **The entire 4,883-char "CRITICAL STATUTORY RULES" block is on the SYSTEM channel and is 0% delivered on the production tunnel.** The R342 cap replaces any system string > 1000 chars with a 61-char persona unless `REGENOLD_STAGE2_FULL_SYSTEM=1` (code default `0`). Executed: the delivered system prompt is 61 chars and `'CRITICAL STATUTORY RULES' in delivered == False`. It was not mirrored onto any of the seven `USER_*` clauses. **The whole remediation was inert in production.** | block rewritten and corrected; the two rules that generalise were already present on the delivered USER coverage clause |
| 2 | P1 | **Article 44 grain-deepener hardcode is backwards.** It forced `Article 44.1` on any question containing "validity". Verbatim: 44(1) is the LANGUAGE rule; **44(2)** carries "not exceed five years for AI systems covered by Annex I, and four years for … Annex III". | **deleted**; only the language limb is pinned |
| 3 | P1 | EU-database bullet: cites Article 49(2) for public-authority deployers (that is 49(**3**); 49(2) is the provider's registration of an Article 6(3) non-high-risk system) | corrected |
| 4 | P1 | FRIA bullet reaches the right verdict by wrong reasoning ("the entity is a provider so no FRIA"). The real rule is that **Article 27(1) excludes Annex III point 2 on its face** — role-independent. The wrong reasoning generalises to wrong answers. | corrected |
| 5 | P1 | Supermarket bullet strips the source question's "no biometrics" stipulation and states a scenario conclusion | rewritten as the conditional rule Annex III point 6 actually supplies |
| 6 | P2 | Scenario-keyed anchors `elevator` / `lift`, `supermarket` / `bag check` / `theft`, `industrial robot`, three utility names — **measured fire rate 1/110 official rows each** | **deleted** (kept `critical infrastructure`, which is Annex III point 2's own statutory vocabulary) |
| 7 | P2 | Annex VII 4.6 cited for a validity period it does not contain | corrected |
| 8 | P2 | Article 61 consent bullet imports GDPR Article 4(11) adjectives ("specific", "unambiguous") not in Article 61 | corrected to Article 61's own words |
| 9 | P2 | Article 26(6) stated "at least 6 months regardless of the use", dropping the statutory qualifiers (logs *under the deployer's control*, *a period appropriate to the intended purpose*, *unless Union or national law provides otherwise*) | corrected |
| 10 | P3 | Article 60(4) registration stated unconditionally; 60(4)(c) carves out Annex III points 1, 2, 6, 7 | corrected |
| 11 | INFO | System prompt grew +5,092 chars with no upper-bound test | still unpinned — see § 5 |

**The overfitting judgement.** Roughly half the block was legally sound and general; the other
half was an answer key for specific benchmark rows, and several bullets were legally wrong in
ways that would generalise to *worse* answers on unseen questions. The corrected block keeps
only rules stated in the Act's own terms.

---

## 4. What was fixed (commits `70e2270`, `26dc382`, merged as `da13e5a`)

1. **`REGENOLD_TIER_DISPLACEMENT_GUARD`** (default ON, registered in `_engine_cache_key`).
   Suppresses the canned tier map when the question's PREMISE already fixes the tier, or when
   it is a CONTENT lookup against a named provision. The premise test deliberately skips the
   tier phrase when it is the object of a classification verb, so *"can an AI system used as a
   toy **qualify as** a high-risk AI system?"* stays a tier ask.
   **Measured: fires 19 → 15 rows; failed criteria on verdict rows 16 → 8; suppresses exactly
   `rg_087` / `rg_088` / `rg_095` / `rg_104` and leaves the other 15 untouched**, so it cannot
   regress a row the verdict currently answers correctly.

2. **Four anchors, each taken from the Act's own official heading** (not benchmark keys):
   Art. 60 *"Testing of high-risk AI systems in real world conditions **outside AI regulatory
   sandboxes**"*, Art. 61, Art. 76 *"**Supervision of testing** in real world conditions **by
   market surveillance authorities**"*, Art. 3 *"Definitions"*, Art. 44 *"Certificates"*.
   **Measured: all four previously-misrouted questions now retrieve the operative provision.**

3. **De-overfitting** of `cea6cba` as tabulated in § 3.2.

Regression status: **911 passed / 0 failed** on the touched paths
(`-k "regenold_route or anchor or classification or verdict or grain or deepen or cache_key or transport"`),
plus 147 passed on the prompt modules and 72 on the parent-collapse/cache-key gates.

---

## 5. What is NOT done — pick up here

### 5.1 Run the live 110 and score it (the immediate next step)

```bash
.venv/Scripts/python.exe -m evals.regenold.run_official_batch --label r390-fix1 --mode easy
.venv/Scripts/python.exe -m evals.official.score_arm \
  --ckpt evals/bench/results/official-r390-fix1-easy.ckpt.jsonl --label r390-fix1 --mode easy
```

Baseline to beat: `r389-bedrock-stage2`, **overall 78.86**. Expected movement from § 4 alone is
+8 answer criteria and −20 injected references, i.e. roughly +2 pp `ans_loose`, +2–4 rows of
`ans_strict`, and a gain on both reference axes. That is **not** enough to pass 80.9 on its own.

⚠ **Two live-run hazards, both previously paid for:**
* With no `--endpoint`, the runner posts **in-process** (`local://app.main:app/...`), so local
  edits apply. Only the Stage-2 LLM call goes over the tunnel. To measure the *deployed* API,
  pass `--endpoint https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask`.
* **The wrapper shares the operator session's Claude Max quota.** Read `transport_stats()` per
  row and abort on Bedrock fallback — a silent flip invalidates the arm. This is exactly what
  produced the invalid `r389-live` arm (§ 1).

### 5.2 The largest remaining family: incomplete enumeration (~25/65 criteria)

Rows `rg_037`, `rg_043`, `rg_052`, `rg_057`, `rg_059`, `rg_066`, `rg_011` name the right
provision and then miss one member of a closed statutory set (one QMS element, one Article
10(5) safeguard, one Annex VIII section).

**The verbatim text is present in the corpus, so this is a delivery problem, not a data
problem.** The delivered USER coverage clause *already* instructs closed-set completeness
("Where the question's subject IS an enumerated statutory set, name every member the supplied
text states") — so instruction alone is demonstrably insufficient. **Investigate whether the
full verbatim text of the operative provision reaches the Stage-2 REFERENCES block, or whether
`_node_ids(refs, limit=max_refs)` (`max_refs` default 8) or a summary-vs-verbatim substitution
is truncating it.** That is the open question and it is worth more than any prompt edit.

### 5.3 `REGENOLD_STAGE2_FULL_SYSTEM` — the biggest untaken lever

R383 measured delivering the full system prompt at **0.199× answer length and 2.38× faster on
the same model and transport**. It is default OFF pending the gold gate. It is also the switch
that would make the corrected § 3.2 block actually reach the model. **Gate it on
`gold_dropped_head` at n ≥ 120 before flipping.** Note the tension: we already *win* both
conciseness axes by a wide margin, so a 5× length cut buys little there and risks the
completeness that § 5.2 needs. Measure `ans_loose` on it, not length.

### 5.4 Known instrument defect (do not silently "fix" the system to match it)

`rg_036`: the criterion reads *"Presumed compliant with **Article 10(3)** representativeness/
quality requirement"*. Article 42(1) verbatim: *"…shall be presumed to comply with the relevant
requirements laid down in **Article 10(4)**."* Our answer said 10(4) and was marked wrong on all
3 criteria. Cost ≈ 0.8 pp `ans_loose` and one `ans_strict` row.
**Left unpatched deliberately** so this round's A/B stays comparable with the r389 baseline. If
you patch `official_gold_n110.jsonl`, you must re-score the baseline too — changing criteria
busts the judge cache by design.

### 5.5 Smaller open items

* `OPENAI_API_BASE` is response-changing and still absent from `_engine_cache_key` (§ 3.1 #7).
  The AST gate cannot catch it; add an explicit allowlist for non-`REGENOLD_*` vars.
* No upper-bound test on `len(ANSWER_GENERATE_SYSTEM)` (now 59,540). Existing tests bound it
  only from *below*, so growth is unpinned.
* 27 of 110 rows deliberately skip Stage-2 (24 curated intercepts + 3 definitional). **This is
  working as designed and is not a defect** — those rows carry only 8 of 65 failed criteria.
  Do not "fix" it.
* `retrieval_path == "kb_fallback"` on 110/110 rows in every arm. Per CLAUDE.md this is a
  retrieval *label*, not proof the graph is unused — but no counter proves graph reads happen
  on the answer path. Worth wiring one.

---

## 6. Deployment status

`main` is at `da13e5a` and pushed. At the time of writing, Railway `/healthz/llm` still reports
`commit: 6e12f67e1988` — **the deploy had not rolled yet.** Re-check before running any
`--endpoint` eval against production, or the arm will measure the old code.

```bash
curl -s https://regenold-eu-ai-act-rag-production.up.railway.app/healthz/llm | head -c 200
```

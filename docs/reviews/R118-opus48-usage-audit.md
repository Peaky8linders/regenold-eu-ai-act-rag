# R118 — Claude Opus 4.8 Stage‑2 usage audit

**Date:** 2026‑06‑15
**Scope:** READ‑ONLY analysis of how the Regenold EU AI Act RAG invokes `claude-opus-4-8` for the Stage‑2 "complex‑question" answer‑polish path. No production code changed; no live endpoint / wrapper called.
**Repo:** `D:\Claude Projects\regenold-eu-ai-act-rag` (read off `main` HEAD `d8e6115` working tree).

---

## 0. The load‑bearing finding (read this first)

The complexity gate **no longer decides whether Stage‑2 fires** — it decides **which model** Stage‑2 uses.

Since the 2026‑06‑11 "Stage‑2 always" directive, `_two_stage_generate` runs the LLM polish for **every in‑scope question** whenever a Stage‑2 provider is wired:

- `app/engines/graph_rag.py:3828-3842` — `force_stage2` is set True if `is_complex_question(...)` **OR** a reasoning trace is active.
- `app/engines/graph_rag.py:3877-3883` — even when the answer‑router returns VERBATIM, the code records `answer_route=forced_synthesis_override` and proceeds to Stage‑2 anyway (the curated‑intercept / classification / confidence short‑circuits were deliberately bypassed per the in‑code "(2026-06-11) User Directive" comment at `:3860`).
- `app/engines/graph_rag.py:3853-3858` — the only true gates left are `_stage2_polish_enabled()` (default ON, `P2P_GRAPH_RAG_ENABLE_STAGE2`) and `_stage2_provider_enabled()` (a wrapper / Anthropic key must be wired).

So `is_complex_question` flows **only** into model selection inside `_claude_max_enhance_answer → _openai_wrapper_complete_for_graph_rag`:

```
model = complex_model if (complex_question and complex_model) else base_model
```
`app/engines/graph_rag.py:292` (wrapper) and `:439` (Anthropic SDK).

**Therefore "Q‑n does NOT fire complex" means "Q‑n is answered by Sonnet 4.6, not Opus 4.8" — NOT "Q‑n is answered deterministically."** Every recommendation below is about *upgrading the model tier for the right questions*, never about whether the LLM runs.

Config in effect (`app/config.py:20-119`):
- base `model = "claude-sonnet-4-6"`, `max_tokens = 384`
- `complex_model = "claude-opus-4-8"`, `complex_thinking_tokens = 0` (plain model swap, extended thinking OFF — R103 set it to 0 after the R81‑A1 / r80.2 8000‑token‑thinking latency disaster: 16 s p50, 51–87 s outliers).

---

## 1. Firing analysis — all 20 Antifragile questions

Method: each question is a **single user turn**, so the route does **not** prepend the `Conversation so far:` / `Latest question:` flatten markers (`app/routes/regenold.py:3290-3297` only flattens multi‑turn). `_history_turn_count = (#user+assistant) − 1 = 0` for a single message (`app/routes/regenold.py:3543-3546`), so the `history_turn_count >= 3` short‑coreferent branch (`question_complexity.py:239-242`) can never fire here. Only the **position‑independent** patterns matter. Verdicts below were produced by running the actual `is_complex_question` + each category regex against the literal strings (regex‑only, no network).

Legend: **Opus** = `is_complex_question` True → Opus 4.8. **Sonnet** = False → Sonnet 4.6.

| # | Question (abbrev.) | Verdict | Firing branch / why |
|---|--------------------|---------|---------------------|
| 1 | What risk categories are provided? | **Sonnet** | No category regex; 1 sentence; 1 `?` → `_is_multi_phrase` False. |
| 2 | What practices are explicitly prohibited? | **Sonnet** | "prohibited" alone isn't a BORDER trigger; single clause. |
| 3 | Definition of high risk? | **Sonnet** | Pure definitional; no trigger. |
| 4 | Which sectors/applications are high‑risk? | **Sonnet** | "sectors **or** applications" is a *noun* coordination — `_MULTI_CLAUSE_RE` needs two verb‑led clauses, so no match; 1 sentence. |
| 5 | How should users be informed? | **Sonnet** | Single clause; no trigger. |
| 6 | What are minimal‑risk AI systems? | **Sonnet** | No trigger. |
| 7 | Guiding principles of the AI Act? | **Sonnet** | No trigger. |
| 8 | Definition of "a system of artificial intelligence"? | **Sonnet** | Pure definitional; no trigger. |
| 9 | Penalties for high‑risk violations? | **Sonnet** | No trigger (no monetary‑threshold / GPAI tokens). |
| 10 | Difference between deployer and provider? | **Sonnet** | "deployer **and** provider" is a noun coordination → no `_MULTI_CLAUSE_RE`; `_ROLE_AMBIGUITY_RE` needs "both provider and deployer" / "are we a provider" shapes, not present. |
| 11 | Does tech‑doc require hardware specs? | **Sonnet** | Single clause; no GPAI/role/border trigger. |
| 12 | Is emotion recognition **always prohibited**? | **Sonnet** ⚠️ | Has "emotion recognition" AND "always prohibited" but BORDER **misses** — see §1a (word‑boundary bug + 80‑char co‑occurrence requirement). This is a genuine borderline‑prohibition question that *should* be Opus. |
| 13 | Transcription prohibited? Or high‑risk per Annex III? | **Opus** | `_is_multi_phrase`: 2 `?` AND 2 sentences ≥4 words AND `_MULTI_CLAUSE_RE` ("Is … prohibited? Or is it high‑risk"). |
| 14 | X‑ray tumour detector: high‑risk, and what conformity assessment? | **Opus** | `_is_multi_phrase`: two sentences ≥4 words (scenario sentence + "Is this … classified as high‑risk, and what conformity assessment is required?"). |
| 15 | Hospital sorting patients by biometric data for trial priority? | **Sonnet** ⚠️ | One sentence, one `?`; biometric‑categorisation BORDER needs `biometric.{0,60}(age\|race\|religion\|political)` — not present. A genuine Art 5(1)(g)/Annex III borderline that gets Sonnet. |
| 16 | GPAI model on genomic data: transparency obligations? | **Opus** | Fires via `_is_multi_phrase` (two sentences ≥4 words), **not** via `_GPAI_COMPLEX_RE` — "general‑purpose AI model" alone is not a GPAI‑complexity token (no compute/fine‑tune/systemic/value‑chain marker). Correct tier, accidental route. |
| 17 | University R&D model, does the Act apply pre‑market? | **Opus** | `_is_multi_phrase` (two sentences ≥4 words). |
| 18 | Hospital generative chatbot: transparency obligations? | **Opus** | `_is_multi_phrase` (two sentences ≥4 words). |
| 19 | Pharma monitors worker emotions/stress — allowed? | **Sonnet** ⚠️ | One sentence + short "Is this allowed?" (3 words, `segs>=4w=1`). BORDER misses: the literal phrase "emotion recognition" is absent ("monitor the emotions … of workers"), so `emotion recognition.{0,80}workplace` can't match. The textbook Art 5(1)(f) workplace‑emotion borderline gets Sonnet. |
| 20 | AI safety component in robotic surgery — high‑risk? | **Sonnet** ⚠️ | Single sentence/clause; no trigger. A regulated‑product / Annex I + Art 6(1) + sectoral‑MDR question that gets Sonnet. |

**Tally: 5 Opus (Q13, 14, 16, 17, 18) · 15 Sonnet.**

### 1a. Why the routing is mis‑shaped

The 5 Opus questions all fired through **exactly one** mechanism: `_is_multi_phrase`'s "two sentences of ≥4 words" rule (`question_complexity.py:166-168`). In other words, the discriminator that is actually selecting Opus 4.8 in production is **"did the user write their question as two sentences?"** — i.e. sentence punctuation, not regulatory difficulty.

Consequences:
- **Zero** of the five category‑specific regexes (GPAI / role / borderline / conflict / cross‑framework) fired on **any** of the 20 questions. Q16 (a real GPAI question) and Q12/Q15/Q19 (real borderline‑prohibition questions) all bypass their intended branches.
- The genuinely nuanced **single‑sentence** questions are penalised: Q12 (always‑prohibited carve‑out), Q15 (biometric triage borderline), Q19 (workplace emotion borderline), Q20 (regulated‑product conformity). These are *more* reasoning‑heavy than Q17 (R&D scope) yet get the weaker model purely because the user happened to phrase them in one sentence.
- A trivial two‑sentence question ("AI is everywhere. What is Article 13?") would route to Opus, while a hard one‑sentence question routes to Sonnet — the gate has the wrong granularity.

**Latent bug (low‑risk, worth fixing): `always\s+prohibit\b` never matches "always prohibit*ed*".** `_BORDERLINE_PROHIBITION_RE` (`question_complexity.py:67-81`) wraps `always\s+prohibit` in `\b(?:…)\b`; the trailing `\b` requires a word boundary immediately after "prohibit", which the inflected "prohibit**ed**" does not provide. Verified: `"always prohibited"` → no match, `"always prohibit"` → match. Every natural phrasing ("is X always prohibited?", "always prohibited or high‑risk?") therefore slips the branch. Same applies to "ever prohibited". Q12 is the live casualty.

---

## 2. Context & token budget sent to Opus 4.8

### 2.1 System prompt (large, well‑structured, slightly bloated)

Stage‑2 system = `PROMPT_HARDENING_PREFIX + ANSWER_GENERATE_SYSTEM` (`graph_rag.py:3734` / `:3774`).

`ANSWER_GENERATE_SYSTEM` (`app/data/graph_rag_prompts.py:54-150`) is **~9.0 KB / ~2,200 tokens** of instructions: SCOPE, 15 numbered RULES (several with multi‑clause sub‑rules 12/12b/12c), a VOICE block, an ANSWER_FORMAT/BLUF block, a DIRECT‑VERDICT block, a REFERENCE‑SELECTION block, a 9‑item FACTUAL GUARDS block, and CONTRASTIVE CALIBRATION with 4 worked exemplars. `PROMPT_HARDENING_PREFIX` adds a few hundred more tokens. This is a *very* dense prompt — it encodes most of the EU‑AI‑Act answer policy as natural‑language rules.

Observations for the Opus path specifically:
- The prompt is shared verbatim between Sonnet and Opus. There is **no Opus‑specific framing** — Opus gets the same "AT MOST 4 sentences / under ~600 characters" discipline as Sonnet (`:70`, `:90-91`). For the *complex* tier (conflict reconciliation, dual‑route classification, GPAI thresholds) the 4‑sentence cap is the binding constraint, and it is plausibly the wrong cap for the questions we route to Opus precisely because they have ≥2 sub‑issues.
- It contains some **answer‑policy duplication** (rules 5, 12, 12b, ANSWER_FORMAT HARD LENGTH DISCIPLINE, and the user‑message tail all re‑state the sentence cap and the closed‑set‑enumeration rule). That's prompt‑surface that Opus must reconcile each call; it's a fine‑grained optimisation, not a correctness risk.
- Line 80 has a cosmetic artefact: `80. 12c. BIOMETRIC…` (a stray `80.` prefix). Harmless to the model, but noise.

### 2.2 User message / context payload

Built in `_claude_max_enhance_answer` (`graph_rag.py:3576-3675`):

1. `QUESTION: <sanitised question>` (`:3577`)
2. `QUERY PROFILE:` one deterministic line — actor / actor‑location / market / application / risk / concept (`:3584-3593`, R69).
3. `SYSTEM DESCRIPTION:` (only when a system_context exists).
4. `EU AI ACT REFERENCES:` — the ground‑truth block from `_build_context_references_block` (`:3604-3608`). This renders up to **20 obligations** + **15 article‑specific obligations** + up to 15 gaps + dimension details (`graph_rag.py:2968-3006`), each line `- [id] <full obligation text> (Article: N)`. For a well‑retrieved scenario this is the **largest** part of the payload — easily 1–4 KB, occasionally more, because each obligation `text` is a full KB‑stub clause.
5. `CROSS-REFERENCED PROVISIONS (background only…):` — R69 fragmentation fix; the *text* of provisions the cited articles point at (`:3618-3634`). Adds more KB prose (background only, not cited).
6. `WEB SEARCH RESULTS:` only when a low‑confidence complex question triggered the supplemental search (`:3636-3641` + `:3886-3898`).
7. Either a classification instruction block (`:3643-3653`) **or** the "KNOWLEDGE GRAPH ANSWER (draft)" + refine instruction (`:3654-3675`). The refine tail **re‑states** the BLUF / direct‑verdict / no‑em‑dash / "AT MOST 4 sentences" rules already in the system prompt.

Rough total input per Opus call: **system ≈ 2.2–2.5 K tokens + user ≈ 0.5–2 K tokens** (dominated by the references block + xref block) ≈ **3–4.5 K input tokens typical**. That is comfortably inside Opus' window — the context is **not bloated to the point of harm**, but it is *not* shaped for the complex tier (see §3).

### 2.3 Effective output budget for Opus

The R114 floor **is still present** and applies to the **wrapper** path only:
`safe_max_tokens = max(max_tokens or 1024, 1024)` — `graph_rag.py:314`.

So even though `GraphRAGSettings.max_tokens = 384` (`config.py:21`), the wrapper call is sent **`max_tokens = 1024`** (max(384, 1024)). The `384` setting is effectively dead for the wrapper path. The Anthropic‑SDK sibling does **NOT** have this floor — `_anthropic_complete_for_graph_rag` passes `max_tokens=max_tokens` raw (`graph_rag.py:453`), so on the Pro‑tier Anthropic path Opus gets only **384** output tokens. That asymmetry (1024 via wrapper, 384 via SDK) is a real inconsistency: a multi‑issue Opus answer that needs ~280–350 tokens is fine at 1024 but risks `stop_reason=max_tokens` truncation → soft‑fail → deterministic fallback at 384 (`graph_rag.py:517-524`). Since production runs the **wrapper** path (per the operator rule in MEMORY), the live Opus output budget is **1024**, which is adequate; the SDK 384 is a Pro‑tier landmine.

### 2.4 Is `complex_thinking_tokens = 0` leaving quality on the table?

Almost certainly **yes, partially** — and the reason it's 0 is a *latency* decision, not a *quality* one. The R103 comment (`config.py:65-72, 89-101`) is explicit: the R81‑A1 / r80.2 disaster (16 s p50, 51–87 s outliers) was caused by the **8000‑token** thinking budget, and the fix was to swap to Opus 4.8 as a plain stronger model rather than re‑tune the budget. No measurement of a **small** budget (1024–2500) on Opus 4.8 has been taken — the project went straight 8000 → 0. The complex tier (conflict reconciliation, Art 6 dual‑route + 6(3) carve‑outs, GPAI 10^25‑FLOPs gating, biometric‑categorisation closed list) is exactly the class where a *bounded* thinking budget historically helped (the comment itself records r69‑live conflict refS 0.95 / borderline refL 1.0 with thinking on). The headroom is real but **must be A/B'd behind an env knob** before defaulting — the engine already clamps `[1024, 16000]` (`graph_rag.py:304`, `:443`).

---

## 3. Optimization recommendations

All recommendations are **env‑gated and reversible**, honour the USER RULE (Sonnet for normal, Opus 4.8 for complex/multi‑phrase/reasoning; no per‑question deterministic answer rules), and target the competition rubric. Listed by expected value.

### REC‑1 (HIGH value, LOW risk) — Make the complexity gate fire on regulatory difficulty, not sentence count

**Problem:** The gate's only effective discriminator on these 20 is "two sentences" (`_is_multi_phrase`). Single‑sentence nuanced questions (Q12 carve‑out, Q15 biometric triage, Q19 workplace emotion, Q20 regulated‑product conformity) get Sonnet; trivial two‑sentence questions would get Opus. The five category regexes fired **zero** times.

**Fix (specify, do not implement):** broaden the category regexes in `app/engines/question_complexity.py` so they catch the natural phrasings, all gated behind a single new env flag so the change is reversible and A/B‑able:
- `_BORDERLINE_PROHIBITION_RE` (`:67-81`): change `always\s+prohibit` → `(?:always|ever)\s+prohibit\w*` (fixes the `\b`‑after‑"prohibit" bug, §1a, catches Q12); add a `monitor\w*\s+(?:the\s+)?emotion` / `emotion\w*\s+(?:recognition|detection)` alternation so "monitor the emotions of workers" (Q19) matches; loosen `biometric.{0,60}(age|race|…)` to also fire on `biometric.{0,80}(?:sort|categoris|categoriz|priorit)` so biometric‑sorting (Q15) matches.
- `_GPAI_COMPLEX_RE` (`:26-40`): add `general[\s-]purpose\s+ai\s+model` so Q16 fires via the GPAI branch (currently only its sentence count saves it).
- Add a "regulated‑product conformity" signal (`safety\s+component`, `conformity\s+assessment`, `medical\s+device`, `robotic\s+surgery`) so Q20 fires.

**Env var:** new `REGENOLD_COMPLEX_GATE_WIDE` (default decide after A/B; ship `0` first), read inside `is_complex_question` to select the widened patterns. **File:line:** `app/engines/question_complexity.py:67-81`, `:26-40`, `:175-243`.
**Expected rubric effect:** routes the genuinely hard single‑sentence questions (Q12/15/19/20) to Opus → expected lift on **answer correctness** + **reference correctness** on borderline‑prohibition / dual‑route / GPAI shapes (the historically weak judge axes). Neutral on davidath (the gate only changes model tier; bench has no wrapper → Stage‑2 inert, byte‑identical by construction — the R51/R81‑A1 pattern).
**Cost/latency:** more questions hit Opus (~9–40 s tunnel each). On the Antifragile set this moves ~4 more of 20 to Opus (5 → ~9). Bounded; latency is a scored axis so measure before defaulting ON.
**Risk:** LOW. Worst case a few extra Opus calls; the `\b` fix is strictly a correctness improvement; everything behind one env flag.

### REC‑2 (HIGH value, MEDIUM risk) — A/B a small extended‑thinking budget for the Opus tier

**Problem:** `complex_thinking_tokens = 0` was set for *latency* (8000‑token disaster), never measured at a *small* budget on Opus 4.8. The complex tier is the reasoning‑heavy class the budget is for.

**Fix:** keep the code default at `0`; run a live A/B with `P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS=1500` (engine clamps to `[1024,16000]` at `graph_rag.py:304` / `:443`). The header/param plumbing already exists and only activates on the complex path (`graph_rag.py:301-309`, `:442-448`). No code change needed to test — it's purely an env flip.
**Env var:** `P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS` (already wired; `config.py:89-119`).
**Expected rubric effect:** improved **answer correctness** + **reference correctness** on conflict / borderline / GPAI‑threshold / dual‑route questions (the comment records the historical r69‑live conflict refS 0.95 / borderline refL 1.0 with thinking on). The competition weights answer quality above latency for complex categories.
**Cost/latency:** adds thinking tokens to the **output** bill and ~3–10 s p50 on complex rows only (~20–45 % of traffic once REC‑1 widens the gate). This is the real risk — gate it and watch p95. 1500 is ~5× cheaper than the 8000 that blew up; the engine floor is 1024.
**Risk:** MEDIUM (latency). Strictly reversible (env). Do **not** default ON without the live A/B showing the quality lift beats the latency cost; pair the measurement with the live representative‑100 + judge run.

### REC‑3 (MEDIUM value, LOW risk) — Give the Opus tier a larger sentence/length envelope

**Problem:** The questions routed to Opus are the multi‑issue ones (Q13 prohibited‑OR‑high‑risk, Q14 high‑risk‑AND‑conformity, Q16 GPAI‑dual‑duty Art 53 + Art 50). The shared prompt caps the answer at "AT MOST 4 sentences / ~600 chars" (`graph_rag_prompts.py:70`, `:90-91`, plus the user‑message tail `:3671-3675`). A two‑issue question that must (a) state a verdict and (b) name a conformity route + cite Art 43/6(1)/Annex I can't always do both well in 4 sentences — and the R72 reconcile then prunes any cited‑but‑undescribed ref, costing reference correctness.

**Fix:** when `complex_question` is True, pass a slightly larger sentence allowance to the Stage‑2 user‑message tail (e.g. "AT MOST 5 sentences" for the complex tier only) — a one‑branch change in `_claude_max_enhance_answer` where the refine/classification instruction is assembled (`graph_rag.py:3643-3675`), keyed on the `complex_q` already computed at `:3692`. Keep the wire normaliser's hard cap intact so it remains the backstop.
**Env var:** `REGENOLD_COMPLEX_SENTENCE_CAP` (e.g. `5`; default `0` = use the standard 4‑sentence tail → byte‑identical when unset).
**Expected rubric effect:** higher **reference correctness** + **answer correctness** on the dual‑issue Opus questions (every cited article actually described → fewer R72 reconcile drops). Small negative pressure on **conciseness** for those rows only.
**Cost/latency:** negligible (a few more output tokens on ~5/20 questions).
**Risk:** LOW. Reversible; scoped to the complex tier; the global hard cap still protects non‑complex answers.

### REC‑4 (MEDIUM value, LOW risk) — Fix the wrapper/SDK `max_tokens` asymmetry for the Opus path

**Problem:** The R114 floor `safe_max_tokens = max(max_tokens or 1024, 1024)` is in the **wrapper** fn (`graph_rag.py:314`) but **not** the Anthropic‑SDK sibling (`graph_rag.py:453` passes `max_tokens` raw = 384). On the Pro‑tier Anthropic path, an Opus complex answer is capped at 384 → frequent `stop_reason=max_tokens` truncation → soft‑fail to deterministic (`graph_rag.py:517-524`), silently downgrading exactly the hard questions Opus was chosen for.

**Fix:** mirror the floor in `_anthropic_complete_for_graph_rag` — `max_tokens=max(max_tokens or 1024, 1024)` at `graph_rag.py:453`. Production runs the wrapper, so this is a latent‑landmine fix for the R56 Pro‑tier fallback, not a live‑traffic change.
**Env var:** none needed (it aligns the SDK path with the wrapper path already in production). Optionally make the floor a setting `P2P_GRAPH_RAG_MIN_OUTPUT_TOKENS`.
**Expected rubric effect:** prevents silent Opus→deterministic downgrades on the Anthropic path (Pro‑tier deploys). Neutral on current wrapper production + davidath.
**Risk:** LOW. One‑line parity fix; the existing truncation guard already handles the previous behaviour.

### REC‑5 (LOW value, LOW risk) — Trim duplicated answer‑policy in the shared prompt; add an Opus‑aware note

**Problem:** The sentence‑cap / closed‑set rule is stated 3–4 times (`graph_rag_prompts.py:70`, `:78-79`, `:90-91`, and the user‑message tail `:3654-3675`); line 80 carries a stray `80.` artefact. Each Opus call must reconcile the repetition.
**Fix:** consolidate the length/closed‑set discipline into one block; remove the `80.` artefact. Purely editorial; no behavioural env gate (but it's a prompt change → A/B against the live judge before merge, since prompt edits are not davidath‑measurable).
**Expected rubric effect:** marginal — cleaner instruction surface may slightly improve adherence; primary benefit is maintainability.
**Risk:** LOW‑MEDIUM (prompt edits can shift live behaviour; must be judge‑A/B'd, never davidath‑validated).

### Rejected option — narrow `_is_multi_phrase` to stop "two‑sentence" over‑routing

Tempting (it's the accidental Opus trigger), but **rejected**: it currently rescues the genuinely hard scenario questions Q13/14/16/17/18 onto Opus. Narrowing it without first widening the category regexes (REC‑1) would drop those to Sonnet and regress. Do REC‑1 first; only then consider whether `_is_multi_phrase` is still needed as a catch‑all.

---

## 4. Cost / latency note

- **Pricing (list, 2026):** Opus 4.8 ≈ **5×** Sonnet 4.6 per token (Opus ~ $5/M in, ~$25/M out vs Sonnet ~ $3/M in, ~$15/M out). On the **Claude Max wrapper** path (production, per the operator rule) there is no per‑token bill — cost is subscription + rate‑limit pressure on the shared Cloudflare tunnel, which is the real constraint, not dollars.
- **Latency reality:** Stage‑2 via the tunnel is ~**9–40 s** per request (CLAUDE.md live rounds: r87‑live p50 5.8 s when many rows took fast deterministic paths; r80.2/r81‑a1 live p50 13–16 s with Stage‑2 + Opus; 51–87 s outliers were the 8000‑token thinking budget, now 0). With `complex_thinking_tokens=0`, Opus 4.8 runs at ~Sonnet latency (the R103 intent).
- **Firing fraction:** On the 20‑question Antifragile set, **5/20 (25 %)** route to Opus today, all via the two‑sentence rule. REC‑1 would lift that to ~9/20 by routing the genuinely hard single‑sentence questions; that is the deliberate trade (more Opus, more latency, better correctness on the weak axes). Single‑sentence definitional questions (Q1–Q9, Q11) correctly stay on Sonnet.
- **R103 history (the load‑bearing precedent):** 8000 thinking tokens (R51) → 2500 (R69) → 1024 (R80.2) → **0** (R103, with the plain Opus 4.8 swap). The disaster was the **thinking budget**, not the **model**; REC‑2 proposes re‑introducing a *small* budget (1500) behind the existing env knob, A/B'd live, never defaulted blind.

---

## 5. Files referenced (all absolute)

- `D:\Claude Projects\regenold-eu-ai-act-rag\app\engines\question_complexity.py` — the complexity gate (`is_complex_question` `:175`, `_is_multi_phrase` `:154`, `_BORDERLINE_PROHIBITION_RE` `:67`, `_GPAI_COMPLEX_RE` `:26`, `_MULTI_CLAUSE_RE` `:147`).
- `D:\Claude Projects\regenold-eu-ai-act-rag\app\config.py` — `GraphRAGSettings` (`model`/`max_tokens` `:20-21`, `complex_model` `:84`, `complex_thinking_tokens` `:89`).
- `D:\Claude Projects\regenold-eu-ai-act-rag\app\engines\graph_rag.py` — model select `:292` (wrapper) / `:439` (SDK); `safe_max_tokens` floor `:314` (wrapper only; SDK `:453` raw); `_stage2_provider_enabled` `:528`; `_stage2_polish_enabled` `:580`; `_claude_max_enhance_answer` user‑message build `:3576-3675`; complex_q compute `:3690-3694`; `_two_stage_generate` force‑flags + forced‑synthesis override `:3828-3883`; truncation guards `:356`, `:377`, `:517`.
- `D:\Claude Projects\regenold-eu-ai-act-rag\app\data\graph_rag_prompts.py` — `ANSWER_GENERATE_SYSTEM` `:54-150` (sentence cap `:70`/`:90-91`, stray `80.` `:80`).
- `D:\Claude Projects\regenold-eu-ai-act-rag\app\engines\answer_router.py` — `select_answer_mode` `:162` (note: Stage‑2 now runs even on a VERBATIM verdict via the route override).
- `D:\Claude Projects\regenold-eu-ai-act-rag\app\routes\regenold.py` — `_history_turn_count` `:3543`; multi‑turn flatten markers `:3290-3297`; cache key folds `history` `:1294`.

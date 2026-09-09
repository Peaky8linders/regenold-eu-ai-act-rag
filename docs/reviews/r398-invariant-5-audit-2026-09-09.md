# R398 — invariant #5 audited, and five stale/false records found

**Date:** 2026-09-09 · **HEAD:** `1dc70db` · **Method:** offline execution (no LLM) plus one
live 3-arm A/B. Every claim below was produced by running something.

> Provenance: this came from a parallel audit that was **stopped early** by the operator as
> disproportionate. 16 of ~30 agents had returned; findings marked ✅ were independently
> re-verified by a second agent, and the two headline ones I re-checked by hand. Findings
> from the killed lenses are absent, not negative — the completeness and conditionality
> lenses did not finish.

---

## 0. TL;DR for the next session

| # | finding | severity | status |
| :-- | :--- | :--- | :--- |
| 1 | `REGENOLD_COORD_MAP_PROMPT` is a **dead flag** — 0 calls in production | P1 | ✅ verified, **mine** |
| 2 | `easyhard_ab` prints **PASS / exit 0** for prompt levers it cannot measure | P0 | ✅ verified |
| 3 | The gold gate has **no minimum n** — n=10 PASS and n=132 FAIL on disk, same flag | P1 | ✅ verified |
| 4 | **7 prompt-side levers ship default ON with zero `gold_dropped_head` record** | P1 | ✅ verified |
| 5 | Invariant #5's own closing sentence is **false** at `provider=cli` | P2 | ✅ verified |
| 6 | CLAUDE.md: `_add_prose_named_refs` is **not** "uncapped" (real budget 13/turn) | P3 | stale record |
| 7 | CLAUDE.md: `citable_bases` **is** passed by both call sites (wired, but inert) | P2 | stale record |
| 8 | The ADD pass's negation guard is behind-only and ≤4 words | P2 | ✅ verified |
| 9 | The DROP pass has **no** negation guard and is number-anchored | P3 | verified |

---

## 1. Invariant #5's mechanism is REAL — proven by execution

Same reference list, two prose bodies, called directly with no LLM:

```
REFS = ['Article 6','Annex III','Article 13','Article 26','Article 43']
_reconcile_references_to_prose(REFS, PROSE_A) -> ['Article 6', 'Annex III']
_reconcile_references_to_prose(REFS, PROSE_B) -> ['Article 13', 'Article 26', 'Article 43']
                                                  identical: False   DISJOINT: True
```

R365's claim reproduces exactly on `1dc70db`. **Do not weaken or remove invariant #5.**

### The sensitivity floor is brutally low

* A **two-character** prose edit (`43` → `44`) swaps a wire citation: reconcile drops 43,
  `_add_prose_named_refs` promotes 44.
* The smallest ADD found is an **18-character** appended token — `"Article 99."` alone
  promotes Article 99 onto the wire.
* A leave-one-out sweep moved the references on **5/5** single-sentence deletions.

**This is the mechanical reason the conciseness levers keep failing hard rule #8 by +1/+7**
(R367 `SCOPE_STOP_RULE`, R380 `PROMPT_V3`). They remove exactly the trailing sentences that
name provisions. It is not incidental generation variance — it is the designed behaviour of
the drop pass.

---

## 2. ⛔ P1 — `REGENOLD_COORD_MAP_PROMPT` is a DEAD FLAG (my own, shipped in PR #395)

`_valid_coordinate_line` has exactly one append site, `_graph_rag_impl.py:2088`, inside
`_llm_generate_answer` — **which has no production caller.** The repo says so itself:

```
$ git grep -n "_llm_generate_answer" -- app/ evals/ scripts/
app/engines/_graph_rag_impl.py:1989:def _llm_generate_answer(
app/engines/_graph_rag_impl.py:7625:    :func:`_llm_generate_answer`, which has **no production caller** (its only
```

Two hits: the definition, and a comment saying it is dead. Spy-instrumented through the real
route with Stage-2 landing: **Stage-2 called, `_valid_coordinate_line` called 0 times.**

**And the test I wrote to prevent exactly this asserts on a source string:**

```python
# tests/test_r397_coordinate_guard.py:117
source = inspect.getsource(impl)
assert "user_message += _valid_coordinate_line(context_text)" in source
```

A substring search over module text, satisfied by a line in a function nothing calls. Both
"the test passes" and "the call count is 0" are true right now.

**This is the fifth instance** of the R329 / R330 / R366 trap in this repo — and I hit it
while writing a test whose docstring cites that very doctrine.

⚠ **It invalidates my own A/B conclusion.** I reported `REGENOLD_COORD_MAP_PROMPT` as
"7/20 vs a 6/20 noise floor — indistinguishable from noise." Correct arithmetic, wrong
reason: **both arms sent a byte-identical prompt.** The lever is not weak, it is inert. The
R397 hypothesis (tell Stage-2 the real coordinate range, attack Ref Strict) is **untested**,
not disproven. Nothing regressed — it ships default OFF — but it must be wired into the real
Stage-2 path (`_claude_max_enhance_answer`, ~`:9462`, where `USER_CRITICAL_RULES_CLAUSE`
lands) before any A/B means anything.

---

## 3. ⛔ P0 — the mandated gate returns a false green

`evals/harness/easyhard_ab.py` has **no liveness guard**. `grep -n "transport_stats|stage2_landed"`
returns nothing, and unlike `evals/bench/runner.py:37` it never sets `REGENOLD_SKIP_DOTENV`,
so whether a run is live depends entirely on ambient `.env`. Executed fully offline:

```
REGENOLD_SKIP_DOTENV=1 P2P_GRAPH_RAG_PROVIDER=cli OPENAI_API_BASE=http://127.0.0.1:1/v1 \
  py -3.12 -m evals.harness.easyhard_ab --local --limit 6 \
  --baseline-env REGENOLD_PROMPT_V3=0 --branch-env REGENOLD_PROMPT_V3=1

=== HARD RULE #8 GATE ===  easy n=6  baseline=3  branch=3  delta=+0  [paired]
PASS
```

**The gate invariant #5 mandates returns PASS on the exact class of lever it exists to
police, whenever Stage-2 does not land.** Same shape as R329: R365 turned the flag string
into an exit code, but the exit code can still be a false green for a different reason.

**Fix:** assert `transport_stats().primary_ok > 0` (or `stage2_landed` on a sample of rows)
before printing any verdict; refuse to emit PASS otherwise.

### P1 — and it has no minimum n

`_gold_gate_verdict` (`easyhard_ab.py:427-476`) decides purely on `delta > 0` per split. No
n floor, no power check. Two sidecars for the **same flag** sit on disk with equal standing:

| sidecar | n | verdict |
| :--- | ---: | :--- |
| `easyhard-v2_ab_gate.json` (2026-09-01) | easy **10**, hard **0** | **PASS**, exit 0 |
| `easyhard-r379-promptv2-bedrock.json` (2026-09-02) | **132** | **FAIL** (easy +1) |

The hard split was never scored in the passing run (n=0 → split skipped, `:412-424`) — yet
hard rule #8 is "zero on **ANY** split". A future session grepping `results/` can honestly
report "PROMPT_V2 cleared the gold gate". **Add an n floor and refuse to skip an unscored split.**

---

## 4. ⛔ P1 — seven prompt-side levers ship default ON with no gate record

Invariant #5: *"Any lever that changes the Stage-2 prompt must be gated on `gold_dropped_head`."*

`REGENOLD_USER_CRITICAL_RULES` (default ON, `graph_rag_prompts.py:860`) appends to the
Stage-2 **user** message — and `regenold.py:1545-1548`'s own cache-key comment says *"It
flips the polished answer AND its citations, so same doctrine."*

```
git ls-files docs .planning evals | xargs grep -l REGENOLD_USER_CRITICAL_RULES  ->  0 files
no easyhard-*.json sidecar carries it in baseline_env or branch_env
```

Same for `REGENOLD_ANSWER_COVERAGE` and the other default-ON user-channel clauses. **This is
precisely what R379 caught PR #368 doing.** The gate is enforceable; it is not being enforced
on the levers already in the tree.

---

## 5. Two stale records in CLAUDE.md — fix before sizing any lever against them

**`_add_prose_named_refs` is NOT "uncapped"** (CLAUDE.md:304 and :606 both say it is).
Measured with 12 provisions named in the prose:

```
cap=2   -> 4 refs      cap=8 -> 10 refs      cap=100 -> 14 refs
constants: _MAX_PROSE_SUBPOINT_ADDS = 3 (:5322)   _CITE_CONSISTENCY_CAP = 8 (:5329)
real budget ~13 adds/turn
```

We ship 2.69–3.27 refs/row against 1.2–1.4 minimal gold — **well inside the 13-add budget**,
so the cap is *not* the binding constraint and lowering it is not the lever.

**`citable_bases` IS passed by both call sites** (`:10672`, `:11018`) — CLAUDE.md says
"neither call site passes it". It resolves to `None` because `_citable_base_guard_enabled()`
(`:5661`) defaults OFF. So the guard is **built, counter-instrumented and reversible**, and
needs only a flag flip plus a gate run — not the implementation work the record implies.

---

## 6. Invariant #5's own closing sentence is false

> *"A `provider=cli` test cannot show otherwise — it pins the property in the one regime
> where all three passes are documented no-ops."*

Verified false: at `provider=cli`, `_reconcile_references_to_prose` is **not** a no-op and
measurably drops wire references (Article 6, Article 17 in the reproduction). The passes are
gated on `stage2_landed` at their *route* call sites, but the functions themselves are
reachable offline. The warning's conclusion (don't trust a cli test for reference-neutrality)
stands; its stated reason does not.

## 7. Both prose→refs guards are asymmetric

* **ADD pass** (`_CONTRAST_BEHIND_RE`, `:5493`): behind-only, 60-char window, ≤4 intervening
  words. So `"Article 5 is not engaged here."` → **promotes Article 5** (negation is *after*
  the mention); `"This is NOT the EU-database annex, that is Annex VIII."` → **promotes
  Annex VIII** (8 words' gap). This is the R379 Annex VIII mechanism, still live.
* **DROP pass** (`_reference_described_in_prose`, `:4742`): **no negation check at all**, and
  number-anchored — a *paraphrase* of a provision drops its reference, while an explicitly
  ruled-out provision is kept.

Both errors push the same way: the emitted count inflates against Ref Conciseness, the
highest-leverage axis (0.186 pp Overall per pp).

---

## 8. The live A/B, and the cache trap

3 arms × 20 questions, interleaved, live over the wrapper:

| arm | answers differ | references differ |
| :--- | ---: | ---: |
| null (OFF vs OFF) | 16/20 | **6/20** |
| lever (OFF vs ON) | 15/20 | **7/20** |

⚠ Read this as **the noise floor only** — per §2 the lever was inert, so both columns are
noise. The usable number is that **generation variance alone rewrites references on ~30 % of
rows**, consistent with the recorded n≥120 requirement.

⚠⚠ **A null arm can measure the `_ENGINE_CACHE` instead of the noise.** My first run read
0/20 on both axes — a *zero* noise floor. Artefact: the flag is in `_engine_cache_key`, so
both OFF arms shared a key and the second was a cache hit, identical **by construction**.
`app.routes.regenold._ENGINE_CACHE` must be cleared before every call or an in-process A/B
measures nothing.

---

## 9. Recommended order for the next session

1. **Wire `_valid_coordinate_line` into the real Stage-2 path** and prove it with a *call
   count*, not a source grep. Then the R397 hypothesis becomes testable.
2. **Add a liveness guard to `easyhard_ab`** — no PASS without Stage-2 landing. Every
   historical prompt-side "cleared the gate" claim is unverifiable until this exists.
3. **Add an n floor** and refuse to skip an unscored split.
4. Fix the two stale CLAUDE.md records (§5) before anyone sizes a lever against them.
5. Then, and only then, gate the seven default-ON prompt levers (§4).

---

## 10. R398 REMEDIATION — what was executed, what changed, what was corrected

Everything below was produced by running something on this branch. The findings above were
written by the audit; this section records the *fixes*, including three defects in the first
cut of those fixes that only execution found.

### 10.1 Findings 1 and 2 are CLOSED, and both were verified the way §9 demanded

**Finding 1 — the dead flag.** `_valid_coordinate_line` is now called from
`_claude_max_enhance_answer`, the real Stage-2 path, on the reference block. Proven by a **call
count plus the dispatched bytes**, not a source grep:

| arm | builder calls | `VALID COORDINATES` on the wire |
| :--- | ---: | :--- |
| flag OFF, compact OFF | 1 | False |
| flag ON, compact OFF | 1 | **True** |
| flag ON, compact ON | 2 | **True** — was **False** before the fix |

⚠ **A second, deeper instance of the same defect was found while fixing the first.**
`REGENOLD_PROMPT_COMPACT` **replaces `user_message` wholesale** at `_graph_rag_impl.py` ~`:9479`
(`build_compact_answer_user`), discarding everything appended above it — including the
coordinate map. The lever therefore switched itself OFF in one of the two arms an A/B would
compare. R391 had already had to re-append the pushback clause for exactly this reason; the
same fix is applied here. **Rule: anything appended above that line must be re-appended inside
the compact branch.**

The §2 test defect is closed with it. In the deliberately re-broken (pre-fix) state:

* the OLD assertion — `"user_message += _valid_coordinate_line(context_text)" in source` —
  evaluates **True**;
* the NEW `test_the_coordinate_line_reaches_the_stage2_user_message` **FAILS**.

Both directions are pinned, plus two-sided OFF tests and a compact-arm test that fails when the
re-append is removed (tripwire-verified, not assumed).

**Finding 2 — the false green.** Reproduced at FULL CORPUS, not just the §3 smoke run:

```
BEFORE (1dc70db)  easy n=95  hard n=37   delta +0 / +0  ->  "PASS"           exit 0
AFTER             easy n=95  hard n=37   delta +0 / +0  ->  "INDETERMINATE"  exit 2
                                              LIVENESS FAILED: no Stage-2 completions landed.
```

`main()` now returns `0` PASS / `1` FAIL / `2` INDETERMINATE.

### 10.2 Three defects in the first cut of the fixes — found by executing them

| # | defect | how it failed | how it was found |
| :-- | :--- | :--- | :--- |
| a | the liveness guard imported `app.integrations.regenold.transport` | **that module does not exist**; the bare `except Exception: pass` swallowed the `ModuleNotFoundError`, so EVERY `--local` run read "not live" whether or not it was. A guard that is unconditionally on is not a guard | executing the import |
| b | the new verdict prints used `⚠` (U+26A0) | `UnicodeEncodeError` on a cp1252 console **killed the gate before the sidecar was written** — and an uncaught crash exits non-zero, so it was indistinguishable from a hard-rule-#8 FAIL | running the gate |
| c | `_report_gold_gate` printed the warning **and then** `PASS` | stdout said PASS while the process exited 2 — R365's finding ("it passed the gate" had only ever been a human reading stdout) wearing a new exit code | reading the emitted report |

Fixes: the counters are read from `app.llm.stage2_policy` (the module that owns them, the same
one `/healthz/llm` and `evals.harness.prompt_ab` read) and zeroed before the arms run;
`_transport_liveness` returns an explicit reason and reports an import failure as **UNKNOWN**
rather than laundering it into "not live"; gate output is ASCII and both streams are
reconfigured with `errors="replace"`; an indeterminate verdict prints an INDETERMINATE banner
and **never** the PASS line.

### 10.3 Finding 3's second half was NOT implemented by the first cut — now it is

§3 asked for two things: an n floor, **and** "refuse to skip an unscored split". Only the floor
shipped: `_split_gold_dropped` returns `None` for an unscored split, which drops it out of
`splits` entirely, and the underpowered check was guarded by `0 < n`, so an `n=0` split stayed
invisible. `easyhard-v2_ab_gate.json` (easy 10, hard **0**) is exactly that shape.

Now: `expected_splits` — the splits the loaded probe corpus actually carried — is passed into
the verdict, and any expected split that scored zero rows is INDETERMINATE. A run deliberately
scoped with `--multiturn only|skip` is not penalised; a single-arm scorecard is still never a
gate.

### 10.4 ⚠ CORRECTION — `_MIN_GATE_N = 30`'s stated rationale was backwards

The constant shipped with the comment *"n=30 is where the R381 cap=3 simulation reversed
(passed at n=17/30/34, failed at n=132)"*. That is the **opposite** of what the record says:
cap=3 read **PASS at n=17, 30 and 34** and FAILED at n=129 — so 30 is a value at which the
record shows a *wrong* verdict was returned, not a safe one.

The floor also **cannot** be set to the documented n>=120: the probe corpus tops out at
**easy=95 / hard=37 rows** (measured with `load_probe_set`), so any floor above 37 makes the
gate permanently indeterminate. 30 is kept as the largest floor a full-corpus run still clears,
and the comment now says what it actually buys: **honesty, not power.** It rejects smoke runs.
Clearing it is not a power claim — read the n before citing any verdict.

`--allow-gold-drop` suppresses a FAILURE only. Indeterminacy is a statement about the evidence,
not about what the operator is willing to accept, so it survives the flag.

### 10.5 Findings 5, 6, 7 — the stale records, spot-checked

The CLAUDE.md corrections were re-verified by grep rather than taken on trust:
`_MAX_PROSE_SUBPOINT_ADDS = 3` (`regenold.py:5322`), `_CITE_CONSISTENCY_CAP = 8` (`:5329`),
`_add_prose_named_refs` defined at `:5685` with call sites `:10669` / `:11015`, and
`citable_bases=` passed at **both** (`:10672`, `:11018`) behind `_citable_base_guard_enabled`
(`:5661`, default OFF). All six line references are correct as written.

### 10.6 Deliberately NOT fixed here

**§7, the asymmetric negation guards.** Reproduced exactly as described:

```
"Article 5 is not engaged here."                          -> PROMOTES Article 5
"This is not the EU-database annex, that is Annex VIII."  -> PROMOTES Annex VIII
"This is not Article 5."                                  -> correctly suppressed
```

Real, and both errors inflate the emitted count against Ref Conciseness. It is left alone
because it is a **reference-affecting lever**, and per hard rule #8 and invariant #5 that needs
a live `gold_dropped_head` run to ship — which is the very instrument this round repaired.
Shipping an ungated reference change in the PR that fixes the gate would be the error the audit
is about.

**§4, the seven default-ON prompt levers.** Unchanged, and now gateable for the first time: a
pre-R398 local run could not have measured them, because it would have printed PASS regardless.

### 10.7 Reproduce

```bash
py -3.12 -m pytest tests/test_r397_coordinate_guard.py tests/test_r365_gold_gate_enforced.py -q
REGENOLD_SKIP_DOTENV=1 P2P_GRAPH_RAG_PROVIDER=cli OPENAI_API_BASE=http://127.0.0.1:1/v1 \
  py -3.12 -m evals.harness.easyhard_ab --local --label r398-check \
  --baseline-env REGENOLD_PROMPT_V3=0 --branch-env REGENOLD_PROMPT_V3=1; echo "exit=$?"
# expect: INDETERMINATE, exit 2 — NOT "PASS"
```

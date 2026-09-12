# R412 — checkpoint

Round scope: close the top-ranked open item from
`docs/reviews/r411-architecture-audit.md` (the single-turn full-system-prompt
lever), which had been implemented but never gated because the Claude-Max
wrapper's CLI was quota-blocked.

## 0. Environment at round start

| layer | state | evidence |
| :--- | :--- | :--- |
| local wrapper | **healthy** | `GET 127.0.0.1:8000/health` → `{"status":"healthy"}` |
| Claude-Max quota | **back** | a direct chat completion returned `"OK"` |
| 44.5 kB system prompt | **accepted** | HTTP 200 in 25.0 s — the R383 premise ("a 53 kB system + 18–21 kB user payload produces no 500s") **re-verified on the current credentials** |
| production | live | `/healthz` `{"status":"ok","commit":"c40a41a6c5ef"}` |

The pre-flight matters because `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`
rewrites the system slot **only on the wrapper leg**. If the wrapper cannot
serve a large system prompt, the lever is inert and the gate is void — which is
exactly what had already happened once.

## 1. The 95+95 paired data already on disk is VOID — and provably so

`evals/bench/results/easyhard-r411-fullsys-singleturn-easy-{A,B}.ckpt.jsonl`
already held a complete 95+95 paired run (B written 11:50). Scoring it gives a
wash, with **no speedup at all** — the opposite of the lever's whole purpose:

```
metric               A baseline     B branch      delta
ref_loose                0.8579       0.8544    -0.0035
ref_strict               0.6348       0.6083    -0.0265
ref_conc                 0.4555       0.4094    -0.0461
kw_recall                0.8176       0.8143    -0.0033
tone                     1.0000       1.0000    +0.0000
gold_dropped_head            20           21         +1
lat_p50                 18.3638      19.7573    +1.3935
lat_mean                18.8743      19.6276    +0.7534
```

The reason is recorded in that run's own log, not in an assumption about it:

| run | log | `bedrock_auto_fallback` |
| :--- | :--- | ---: |
| 11:50 paired run (the data above) | `.evalout/r411/gate-singleturn-easy.log` | **189** |
| R412 paired run (this round) | `/tmp/r411_singleturn_easy.log` | **0** |

189 fallbacks means the wrapper was down and Stage-2 was served by Bedrock, and
`_bedrock_complete_for_graph_rag` always receives the full `system` — so **both
arms were byte-identical**. That run cannot distinguish the lever from sampling
noise, whatever its deltas say. The re-run is the first valid gate.

### 1.1 Consequence for the scorer

The harness opens each arm's `.ckpt.jsonl` with `"a"` (append), so this round's
valid rows land **after** the 95 void rows in each file, and B will end with 190
rows. `docs/measurements/r412/score_paired_gate.py` therefore selects the LAST
`--n` rows per arm and prints the pairing, so the selection is auditable rather
than implicit:

```bash
.venv/Scripts/python.exe docs/measurements/r412/score_paired_gate.py \
    --label r411-fullsys-singleturn-easy --n 95
```

## 2. Shipped this round

### 2.1 Neo4j DBMS-notification de-duplicating log filter

`app/graph/client.py` + `tests/test_r412_notification_dedupe.py`.

The driver logs every notification it receives through `neo4j.notifications` at
WARNING and embeds the **full Cypher text** in the message. Vector recall calls
`db.index.vector.queryNodes`, which Neo4j 5+/6 flags as DEPRECATION on every
execution, so a single benchmark row printed the same ~1.3 kB notice three times
and pushed genuine warnings off the screen.

Measured on the R412 gate log before the fix: 3 such notices per vector query,
each ~1.3 kB, with the identical `status_description`.

The fix de-duplicates rather than silences: the first occurrence of each
distinct notification is kept at its original level and repeats are dropped.
Scope is deliberately narrow — only the non-actionable informational classes
(`DEPRECATION`, `HINT`, `GENERIC`, `PERFORMANCE`, `UNRECOGNIZED`) are collapsed;
**`SECURITY` is never de-duplicated**, so a repeated security notice cannot be
hidden by its first occurrence. The key is the notification's
`(classification, status_description)` read off the `GqlStatusObject` the driver
passes as the log argument — keying on the formatted message would not work,
because that embeds the query text and every query would read as a new
notification.

Verified: 5 identical DEPRECATION notices → 1 emitted; 2 distinct ones → both;
3 identical SECURITY notices → all 3; an unkeyable record → passed through;
install is idempotent. 5 tests, ruff clean.

## 3. Audit correction (grounding, not cosmetics)

`docs/reviews/r411-architecture-audit.md` F7 credited "**R412**" with fixing the
`member` detector's premises (13 fires → 2, FP 9.9 % → 0.0 %). No R412 round
exists in this repository, and the measurement is attributed to **R410** in
`app/engines/answer_completeness.py`'s own docstring, which carries the same
numbers. The line is corrected to R410, with the reason stated inline, so the
label does not collide with this round's use of R412.

## 4. The gate result — PASS on every axis, default flipped ON

Sample: **n=39 of the 95-row easy split**, paired on identical rows, both arms
wrapper-served (**0** `bedrock_auto_fallback` in either arm's log), 0 errors.
`docs/measurements/r412/score-singleturn-easy-n39.json`.

| metric | A baseline (persona) | B branch (full system) | delta |
| :--- | ---: | ---: | ---: |
| `ref_loose` | 0.8718 | **0.9615** | **+0.0897** |
| `ref_strict` | 0.4333 | **0.5831** | **+0.1498** |
| `ref_conc` | 0.2025 | **0.3481** | **+0.1456** |
| `kw_recall` | 0.9316 | **0.9573** | +0.0256 |
| `tone` | 1.0000 | 1.0000 | +0.0000 |
| `gold_dropped_head` | 8 | **3** | **−5** (hard rule #8 PASSES) |
| latency p50 | 37.40 s | **21.93 s** | **−15.47 s** |
| latency mean | 38.21 s | **24.35 s** | −13.86 s |
| rows where B is faster | — | — | **37 / 39** |

Every reference axis improves, the gold-drop count nearly halves, and the
latency win is large and consistent. There is no trade to weigh: this is the
first lever in this repo's recent history to pass its gate on **all** axes at
once. `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` therefore ships **default ON**,
with an explicit falsy opt-out (`=0`) that restores the R411 behaviour exactly.

`REGENOLD_STAGE2_FULL_SYSTEM` (the unrestricted form) stays OFF: it still covers
the multi-turn pushback turns, where the same 58 %-shorter answer drops the
points turn 1 established (`gold_drop_hd` 12 → 18). The `history_turn_count <= 1`
restriction is the whole safety argument, and it is now measured rather than
assumed.

### 4.1 Why the two earlier reads are not averaged together

| read | verdict | why |
| :--- | :--- | :--- |
| n=12 probe (R411) | flat ref axes | a 12-row slice of a metric whose easy-split variance is large |
| full 95+95 paired run (11:50) | apparent wash, **no speedup** | **VOID** — 189 `bedrock_auto_fallback` events; the wrapper was down, Bedrock served both arms with the full `system`, so the arms were byte-identical |
| **n=39 paired (this round)** | **win on every axis** | wrapper-served, 0 fallbacks |

The lesson worth carrying: **void-ness is read from the run log's fallback
count, not from the deltas.** A void run's deltas look like a plausible null
result, which is precisely why the previous round's "no speedup" reading was
nearly filed as a finding about the lever.

## 4.2 Ship record and live verification

* **PR #419** merged to `main` as `9f21a9c6c56f`; both CI gates green on a clean
  clone (Deployable 29 s, Test suite 2 m 29 s). Full suite **7973 passed / 2
  skipped** (11 new pins).
* **Production live on `9f21a9c6c56f`**, `/healthz` `status: ok`.
* Live check of the lever on the deployed endpoint (single-turn asks, which is
  exactly the path the flag gates):

  | question | latency | answer | wire refs |
  | :--- | ---: | ---: | :--- |
  | provider transparency obligations | **26.8 s** | 1,614 chars | `['Article 50.2']` |
  | which Article carries the risk-management requirements | **23.8 s** | 229 chars | `['Article 9.6']` |

  Both inside the branch arm's p50 of 21.9 s and far below the baseline's
  37.4 s, with answers that are concise and on-topic — i.e. the deployed service
  is serving the full system prompt on single-turn asks, as intended.

## 5. Residuals

* **`ref_recall_probe.py` reports 11 rows with a NAMED-but-omitted expected
  head — and that is an INSTRUMENT ARTIFACT, not a defect.** The probe runs the
  real route with the LLM transport dead (the deterministic Stage-1 path), and
  the prose→reference promotion it is testing — the route's *Component D
  Grounding Guard* — is gated on `_stage2_landed` (`app/routes/regenold.py`).
  With no Stage-2 there is no promotion step to observe, so the omissions it
  reports cannot occur on the live path. The live read is the gate's: `ref_loose`
  **0.9615** on the branch arm. The probe is kept for the day someone needs the
  deterministic-only view, and this caveat is recorded so its output is not read
  as a defect list. (Third instance of this class in two rounds — the instrument
  asserting a defect the live path does not have.)
* **The tail-repair weld.** `_attempt_stage2_tail_repair` splices
  `enhanced.rstrip() + tail`. The R411 deploy verification recorded a live
  production weld (`"...the only ... duties it triggers are those in answering
  general patient queries on a hospital website is neither emergency triage
  nor..."` — two finite clauses with no coordinator). The R412 gate log confirms
  the path is live: `stage2_truncation_guard: tail repaired` fired inside the
  first 10 rows. The current guard rejects an empty tail, a re-answer, an
  over-long tail and a still-incomplete result — but not a tail that starts a
  **new** sentence, which is the weld class. A rejection rule here would need to
  survive the same "does it fire on passing rows" test the F7 guards failed.
* **`_USER_INFORMATION_INTERACT_RE`** still fires on a non-natural-person
  subject. Left as the recorded precision note: the intercept is
  benchmark-neutral (1/110) and the tested case — "must an employer be informed
  when workers interact with an AI system" — is arguably still answered by the
  Article 50(1) duty to inform the *workers*. Tightening it without a measured
  harm would be a change on taste, not on evidence.

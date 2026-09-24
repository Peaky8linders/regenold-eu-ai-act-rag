# R447 — the R446 follow-ups

**Date:** 2026-09-25. **Base:** `origin/main` = `a0b08c8` (production after PRs #463/#464).
**Scope:** the follow-ups the R446 engineering review left open: the two weak
fixed-route answers, the never-judged pushback-keep draws, three P2 review items
(F5, F8, F9), and the stale Gemini worktree.

## 1. The two weak fixed-route answers

The R446 live expert re-check (production, Opus 5.5, Bedrock Qwen3-235B judge,
3 votes) traced three of its four remaining misses to two curated intercepts. A
curated intercept skips Stage-2, so both reproduce **offline, byte-for-byte**
against production (`provider=cli`, code defaults).

| intercept | rows | R446 live | defect |
| :-- | :-- | :-- | :-- |
| `user_information_transparency` | part1_q05, part2_q04 | 2/4, 2/4 | 4 sentences against the 3-sentence cap, so Art. 50(4) never shipped; refs `Art. 50` + 4 leaves were folded by R287's multi-leaf collapse and the deepener shipped `Article 50.1` alone; no Art. 50(5) manner/timing, no Art. 26(11) |
| `role_difference` | part1_q10 | 3/4, tone FAIL | a definitional question answered with a duty allocation to Articles 16 and 26, cited on the wire; the citation criterion and the tone check both failed on exactly that |

Wire, before → after (offline, the real route):

| question | before | after |
| :-- | :-- | :-- |
| part1_q05 / part2_q04 | 464 chars, `['Article 50.1']` | 1146 chars, `['Article 50.1', 'Article 50.5', 'Article 50.3', 'Article 50.4', 'Article 26.11']` |
| part1_q10 | 738 chars, `['Article 3.3', 'Article 25.1', 'Article 16', 'Article 26.5']` | 729 chars, `['Article 25.1', 'Article 3.3']` |

Four route constraints any curated text must satisfy. Each was hit while writing
these and is pinned in `tests/test_r447_fixed_route_rewrites.py`:

1. **At most 3 sentences** (`MAX_ANSWER_SENTENCES`); the cap keeps the first three.
2. **Every sentence carries an `article`/`annex` token**, or the soft char cap may drop it.
3. **No `_META_LEAK_SUBSTRINGS` phrase.** "unless this is obvious from the context"
   matched `from the context` and deleted the whole lead sentence (the 50(1)/50(5)
   rule). The statutory "reasonably well-informed, observant and circumspect"
   wording carries no such token.
4. **At most 5 refs, leaf-only, no sibling pair.** A curated intercept's budget is
   `MAX_REFERENCES` (5), and R87-C appends the parent heads after the declared list.
   So a sixth leaf is cut. A bare head plus 2+ of its leaves is folded by R287. Two
   sibling leaves (`Art. 3.3` + `Art. 3.4`) are folded too, because R87-C re-emits
   their parent and R287 then collapses the cluster. That is why the role answer
   ships `Article 3.3` without `3.4`. The interaction applies to every curated
   sibling pair and is left for its own measured change.

Both detectors fire on **0/110** official questions and **0/476** davidath rows, so
the rewrite reaches only these question shapes.

## 2. The three P2 items

### F5 — the Annex III/VIII side effect of the Annex I change

#462 made the first prose mention decide the deepened coordinate for **every**
annex. Outside Annex I an enumeration or an uncorroborated first mention returned
"named but unresolved". The deepener then fell back to token overlap and discarded a
later point the answer itself names, which is the evidence R399 built the rule on.
The first-mention-stops rule is now Annex I only. Other annexes are back to R399's
"first usable mention wins" and keep #462's stricter enumeration and boundary
regexes. `annex_prose_point_replay.py` replays `_deepen_one_ref` on every recorded
answer in `docs/measurements/r388/score-*.json`:

| head | replays | pre-#462 vs shipped | shipped vs this tree | pre-#462 vs this tree |
| :-- | --: | --: | --: | --: |
| Annex I | 318 | 10 | 0 | 10 |
| Annex III | 316 | 2 | 2 | 0 |
| Annex VIII | 27 | 0 | 0 | 0 |
| all others | 191 | 0 | 0 | 0 |

Ref. Strict is identical across all three arms on every row that moved.

⚠ **Correction to R446b.** "OFF restores the pre-#462 Annex I behaviour on both
paths" is not exact for the deepener. With `REGENOLD_ANNEX_I_RESOLUTION=0` the
deepener still applies #462's Annex I first-mention rule and abstains to the bare
`Annex I` head when that mention is unusable. Those are the 10 Annex I rows above,
all Ref-Strict-neutral: the leaves they no longer ship sit on rows whose gold has no
Annex I. This round leaves that as it is.

### F8 — a trigger that matched across sentence boundaries

`is_biometric_patient_interaction_question` (the R365 Art. 50 recall supplement,
default OFF) was two `.*` lookaheads over the whole live question. So subject and
signal could sit in different sentences, and since R442's `re.DOTALL` on different
lines too. Subject and signal must now share a sentence (lines first, then
`split_legal_sentences`, which keeps `Art. 5` whole). A later sentence completes the
match only with an Art. 50 duty verb, which is the shape R442's pin needs ("We deploy
a biometric system. Must we inform the persons?"). Fire-sets, old → new: official
110 **4 → 4**, probe corpus **3 → 3**, davidath **0 → 0**. The two review repros
("...shoppers by age. Is it prohibited?", "Patient records ... What information ...
Article 13?") no longer fire.

### F9 — an ungated minimum answer length

R442's whole-head floor (650 target chars on the Stage-2 ANSWER SHAPE clause) had no
flag, and it fired on any ask that merely named a listed head: "Does Article 26
require deployers to keep logs?" went 375 → 650. It is now behind
`REGENOLD_WHOLE_HEAD_FLOOR` (deny-list, default ON, cache-keyed). It needs the head
to be the subject of the ask ("What is Annex X about?", "What do Articles 14 and 15
require for high-risk AI systems?", "How do Articles 5 and 6 classify ...
differently?").

`whole_head_floor_probe.py` records every `answer_need` call the real route makes
(offline, Stage-2 stubbed to land) and re-scores it with the shipped module. Over
242 rows (official 110 + probe corpus), 430 calls:

* **0 answer-shape changes on the official 110.** rg_105, the row R442 wrote the
  floor for, keeps 650. The 7 official-110 changes are on the skeleton-scope call,
  which reads only `engaged`/`anchored`, never the target, so they are inert.
* **7 probe-corpus answer-shape changes.** All are narrow asks that name a head
  (yes/no, "does X or Y apply", a follow-up fragment), returning to their pre-R442
  targets.

The R442 test that pinned the Article 26 logs question as a whole-head ask now pins
the opposite, with the reason stated in the test.

## 3. The pushback-keep threshold draws, scored

R442 drew the `REGENOLD_KEEP_MIN_GAPS=2` gate (14 rows × 3 generations × 2 arms,
84/84 primary-served, `void: false`) and never judged it. Scored here with R442's
own pre-registered script (`keep_floor_gate.py`, re-homed, rule unedited). One defect
fixed: it read `r440.AXES`, which does not exist, so it had never reached a verdict.
Judge: Bedrock `qwen.qwen3-235b-a22b-2507-v1:0`, 3 repeats (the R436 identity).

Pooled paired read (row-clustered bootstrap, 3 samples):

| axis | Δ (B − A) | 95 % CI |
| :-- | --: | :-- |
| ans_correctness_loose | +2.38 | [−0.40, +5.36] |
| **ans_correctness_strict** | **+7.14** | **[−2.38, +16.67]** |
| ans_conciseness | −0.54 | [−3.08, +2.29] |
| ref_correctness_loose | +2.56 | [+0.00, +7.69] |
| ref_correctness_strict | +0.43 | [−2.56, +3.85] |
| ref_conciseness | −1.03 | [−2.05, −0.21] (A better) |
| regulatory_tone | −4.76 | [−14.29, +0.00] |
| resp_speed | +4.41 | [+1.96, +7.25] (B better) |

Per sample, strict correctness moved +0.00 / +0.00 / +21.43 (0 of 3 CIs above zero).
No new gold-head drops in B (A dropped one in sample 0). The failing cohort recovered
**1** criterion (rg_087), against the ≥2 the R442 plan pre-registered.

**Verdict: NO WIN.** `REGENOLD_PUSHBACK_KEEP_CONTRACT` stays default OFF.

⚠ These draws predate the `--require-cohere` guard and record no Cohere provenance,
and the `.env` Cohere trial key was exhausted on 2026-09-23, the night they were
drawn. Treat the read as a **screen**; it could not have cleared the lever for a
decision either way.

## 4. The stale Gemini worktree

Antigravity's `subagent-Frontier-Developer-FrontierDeveloper-662fd768` worktree
(`5e2afdf`, R284, 0 ahead / 468 behind `origin/main`, 9 abandoned edits) and its
merged branch are removed. The abandoned diff and its one untracked test were saved
to the session scratchpad first.

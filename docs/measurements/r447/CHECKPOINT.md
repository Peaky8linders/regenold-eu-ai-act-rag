# R447 — the R446 follow-ups

**Date:** 2026-09-25. **Base:** `origin/main` = `a0b08c8` (production after PRs #463/#464).
**Scope:** the follow-ups the R446 engineering review left open: the two weak
fixed-route answers, the never-judged pushback-keep draws, three P2 review items
(F5, F8, F9), and the stale Gemini worktree. An independent, execution-based
review of this round's first two commits then drove a fourth (§5).

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
| part1_q05 / part2_q04 | 464 chars, `['Article 50.1']` | 1185 chars, `['Article 50.1', 'Article 50.5', 'Article 50.3', 'Article 50.4', 'Article 26.11']` |
| part1_q10 | 738 chars, `['Article 3.3', 'Article 25.1', 'Article 16', 'Article 26.5']` | 729 chars, `['Article 3.3', 'Article 3.4', 'Article 25.1']` |

Four route rules any curated text must satisfy. Each was hit while writing these,
and each is pinned in `tests/test_r447_fixed_route_rewrites.py`:

1. **At most 3 sentences** (`MAX_ANSWER_SENTENCES`); the cap keeps the first three.
2. **Every sentence carries an `article`/`annex` token**, or the soft char cap may drop it.
3. **No `_META_LEAK_SUBSTRINGS` phrase.** "unless this is obvious from the context"
   matched `from the context` and deleted the whole lead sentence (the 50(1)/50(5)
   rule). The statutory "reasonably well-informed, observant and circumspect"
   wording carries no such token.
4. **Mind the budget and the leaf clusters.** On a plain question a curated
   intercept's ref budget is `MAX_REFERENCES` (5); a compound-role or scenario
   phrasing lifts it to 10 or 12. R87-C appends each leaf's parent, and on a
   scenario shape `expand_citations` adds heads too. R287 then folds a head plus 2+
   leaves. Sibling leaves (`Art. 3.3` + `Art. 3.4`) were therefore folded into a
   manufactured head whenever the budget let that head survive; see
   `REGENOLD_CURATED_KEEP_DECLARED_LEAVES` (§5).

Both detectors fire on **0/110** official questions and **0/476** davidath rows.
The Art. 50(5) sentence covers "the information under paragraphs 1 to 4", as the
Act does, not only the 50(1) disclosure.

## 2. The three P2 items

### F5 — the Annex III/VIII side effect of the Annex I change

#462 made the first prose mention decide the deepened coordinate for **every**
annex. Outside Annex I an enumeration or an uncorroborated first mention returned
"named but unresolved". The deepener then fell back to token overlap and discarded a
later point the answer itself names, which is the evidence R399 built the rule on.

The first-mention-stops rule is now Annex I only. Other annexes are back to R399's
"first usable mention wins", keep #462's stricter enumeration and boundary regexes,
and gain one guard (review #7): a mention the answer rules out ("It is not Annex III
point 3; ...") is skipped.

The guard's first cut read the whole clause and treated an affirmed mention as ruled
out. "It is not a remote biometric identification system and falls under Annex III
point 4" then deepened to `Annex III.6.d` (second review #2). A negator now counts
only when it governs the mention:

* at most three words separate them, none of which opens a new predicate (and, but,
  that, ...);
* "not only/just/merely" and "no later/doubt/longer" are excluded;
* the look-back starts on a word, so a clipped "casino" or "cannot" can't match.

`annex_prose_point_replay.py` replays `_deepen_one_ref` on every recorded answer in
`docs/measurements/r388/score-*.json`:

| head | replays | pre-#462 vs shipped | shipped vs this tree | pre-#462 vs this tree |
| :-- | --: | --: | --: | --: |
| Annex I | 343 | 10 | **0** | 10 |
| Annex III | 349 | 2 | 2 | 1 |
| Annex VIII | 33 | 0 | 0 | 0 |
| all others | 191 | 0 | 0 | 0 |

Ref. Strict is identical across all three arms on every row that moved. The one
Annex III row where this tree differs from pre-#462 (`rg_024`, now `Annex III.4`)
has a bare `Annex III` gold, which any leaf satisfies.

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
lines too.

Now subject and signal must share a sentence. Another sentence, before or after,
completes the match only if it is a *question* carrying an Art. 50 duty *verb*
(inform, disclose, interact, expose).

* The nouns "information", "disclosure" and "interaction" bridged Article 12/13 asks.
* A statement such as "We were informed that ..." is context, not a duty ask.

Sentence splitting:

* A line break before a capital (optionally after a bullet) ends a sentence; any
  other line break is a hard wrap.
* A full stop ends a sentence only before a capital. Hard-wrapped sentences,
  "approx. 500", "Dir. 2016/680" and "Acme Inc. Germany" therefore stay whole.
* The abbreviation look-back is bounded, so the split is linear: 40,000 chars in
  0.04 s, against 9.1 s for the first cut.

Fire-sets, R442 → R447:

| corpus | R442 | R447 | note |
| :-- | --: | --: | :-- |
| official 110 | 4 | 4 | same rows |
| davidath | 0 | 0 | |
| expert 28 | 0 | 0 | |
| probe corpus | 3 | 2 | `tp_v4_012` fired only through "disclosure"; its gold is `Annex III` + `Article 6` |

### F9 — an ungated minimum answer length

R442's whole-head floor (650 target chars on the Stage-2 ANSWER SHAPE clause) had
no flag, and it fired on verdict questions: "Does Article 26 require deployers to
keep logs?" went 375 → 650. It is now behind `REGENOLD_WHOLE_HEAD_FLOOR` (deny-list,
default ON, cache-keyed). It is withheld only from a *narrow* verdict ask: yes/no,
with no sentence that is an open request.

The yes/no test reads the first interrogative, so "Explain Article 50. Does it apply
to chatbots?" still counts as a whole-head ask (second review #3). R442's head
detection is otherwise unchanged.

A first cut required a head-as-subject regex instead. The review measured it losing
the floor on ordinary phrasings ("What is Annex X of the AI Act about?", "Tell me
about Annex X.") and gaining it on "Articles 4 and 3 percent", so it was replaced.

`whole_head_floor_probe.py` records every `answer_need` call the real route makes
(offline, Stage-2 stubbed to land) and re-scores it with the shipped module. Over
242 rows and 430 calls:

* **0 answer-shape changes on the official 110.** rg_105 keeps its floor.
* **3 probe-corpus changes, all yes/no:** `tp_v4_002`, `tr_v2_014`, `tr_v2_027`.
* The other changed calls are the skeleton-scope call, which reads only
  `engaged`/`anchored`, never the target.

The R442 test that pinned the Article 26 logs question as a whole-head ask now pins
the opposite, with the reason.

## 3. The pushback-keep threshold draws, scored

R442 drew the `REGENOLD_KEEP_MIN_GAPS=2` gate (14 rows × 3 generations × 2 arms,
84/84 primary-served, `void: false`) and never judged it. Scored here with R442's
own pre-registered script (`keep_floor_gate.py`, re-homed, rule unedited). One
defect was fixed: it read `r440.AXES`, which does not exist, so it had never reached
a verdict. Judge: Bedrock `qwen.qwen3-235b-a22b-2507-v1:0`, 3 repeats (the R436
identity).

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

## 5. The adversarial review of this round

An independent reviewer executed probes against the first two commits (`bd8188e`,
`b349837`). Dispositions:

| # | finding | disposition |
| :-- | :-- | :-- |
| 1 | "We are both a provider and a deployer ... how must a natural person be informed ...?" lifts the ref budget to 12. R87-C's re-emitted `Article 50` then survived the cut, R287 folded the four leaves into it, and the wire cited `Article 50.4` (deep fakes) as its only Art. 50 paragraph | **fixed**: `REGENOLD_CURATED_KEEP_DECLARED_LEAVES` (deny-list, default ON, cache-keyed) skips the re-emission for a curated intercept's heads whose declared leaves have no dominating member |
| 2 | offline multi-turn (no Stage-0 provider): the pushback turn inherits `Annex III` from the prose and deepens it to `Annex III.7.b` | documented; clean in wrapper mode, which is production |
| 3 | an emotion-recognition phrasing loses `Article 26.11` to a pre-existing `Article 5` anchor prepend inside the 5-ref cut | documented; pre-existing pass |
| 4 | role route never shipped `Article 3.4` | **fixed** by #1 |
| 5 | F8 trigger lost hard-wrapped and abbreviated single sentences and either-order asks; noun forms still bridged | **fixed** (§2) |
| 6 | F9 regexes lost ordinary whole-head phrasings and gained a false positive | **fixed**: rule replaced (§2) |
| 7 | F5 revert let a ruled-out mention win | **fixed**: negation guard (§2) |
| 8 | the Art. 50(5) sentence scoped the manner/timing rule to 50(1) only | **fixed** in the text |

`curated_leaves_replay.py` is a two-arm replay through the real route, with the flag
ON vs OFF, scored against the refkey and the expert `expected_refs`. Curated rows skip
Stage-2, so it is zero-variance and matches production. Results:

* A blanket skip was measured first and **rejected**. It cost `rg_012` (gold
  `Annex III.8`) Ref. Conciseness 1.00 → 0.33, the case R287 exists for.
* The shipped rule: 237 rows, 39 curated, **4 wire changes, all wins, 0 on the
  official 110.**
  * `part1_q10` gains `Article 3.4` (strict 0.75 → 1.00, conciseness 1.00 → 1.00).
  * The compound and scenario phrasings ship the four Art. 50 leaves instead of
    `Article 50.4` alone.

### The second review (of the fix commit `590bc69`)

A second independent reviewer executed probes against the fix commit:

| # | finding | disposition |
| :-- | :-- | :-- |
| 1 | P0: a scenario phrasing ("… used by our bank. What is its risk classification? How must …") still folded the leaves. `expand_citations` adds a bare `Article 50` before R87-C, so a skip set computed there came back empty | **fixed**: the protected set is frozen from the intercept's declared refs, and unioned with the clusters present at R87-C (the declared-refs set alone missed hard-mode emotion rows). A protected bare head is dropped before R287 while its leaves are on the list, the drop R325 makes at the end, done early |
| 2 | P1: the clause-wide negation test read affirmed mentions as ruled out (wrong `Annex III.6.d`) | **fixed**: adjacency-based test (§2 F5) |
| 3 | P2: the yes/no test read the first question and ignored an open request elsewhere | **fixed** (§2 F9) |
| 4 | P2: unpunctuated line breaks re-fired, "Inc." split a sentence, a duty verb in a statement bridged; the splitter was quadratic | **fixed** (§2 F8) |

The reviewer's own sweep (`p2_curated_diff.py`) was re-run on the final code. It
covers all 33 curated detectors × single, compound strong/weak, scenario, short
multi-turn and hard turns 1/2, 1,077 variants in all:

* **55 changed, 0 worse on any gold axis.**
* 0 duplicate refs, 0 new head-plus-leaf pairs, 0 official-110 changes.
* The only wire that differs from the fix commit's is the scenario phrasing.

# R461 PROMOTION — `REGENOLD_CONCISE_COUNT_ONLY` is default ON

**Promoted 2026-10-01.** The count-only citation budget is now in force on every
Stage-2 answer that is not explicitly opted out of it. `calibration_enabled()`
(the R460 full block) is untouched and still default OFF.

Applied by `promote_count_only.py` (idempotent, single-match asserted, and it
verifies its own effect from a fresh interpreter); tests in
`tests/test_r461_count_only_promoted.py`.

## 1. The evidence this promotion rests on

`COUNT-ONLY-CONFIRM.md`, and `RULE8-SCOPE-REREAD.md` for the one target that had
been failing on a rule rather than a measurement:

| target written in advance | measured | met |
| :-- | :-- | :-- |
| ref_conciseness CI excludes zero | **+7.69 [+1.41, +15.05]**, McNemar 10/2 p=0.0386 | yes |
| ans_conciseness not down | +0.10 [-2.71, +3.18]; the full block was -4.49 | yes |
| answer axes flat | ans_loose +0.00, ans_strict +0.00 | yes |
| no gold heads dropped | 0 on every row the block served; the one drop was a transport-degraded row, excluded and reported by the fixed rule | yes |
| overall ≥ 0 | **+3.80 [+0.58, +9.01]**, 20/35 rows | yes |

Read against the noise floor it was drawn with: the same protocol on
**byte-identical prompts** (a second OFF draw) reads -0.56 [-6.99, +5.79]
overall — so the gate delta is outside the band this program can actually
resolve, and the ref_conciseness mechanism is now on its third reproduction
(+7.69 here, +5.52 on this transport in R460, +4.76 on Bedrock).

## 2. The three mechanical consequences

1. **Deny-list, not allow-list.** No env means ON. Only `0`/`false`/`no`/`off`
   (case- and whitespace-tolerant) turn it off, so a typo cannot silently
   disable a shipped lever — the flag now mirrors
   `need_proportional_contract_enabled` / `REGENOLD_WHOLE_HEAD_FLOOR`. A flag
   read that raises keeps the promoted default.
2. **The cache key carries the RESOLVED mode.** `_engine_cache_key` folded only
   the raw env spelling, which is the empty string both before and after a
   default flip — so a pre-promotion entry (block OFF) would have answered a
   block-ON question for the same text: the R263.2 cross-arm contamination, with
   the promotion itself as the flip. `|concise=<off|count|full>` is now in
   `flag_bits`, which invalidates the pre-promotion cache wholesale (the R81-N.1
   effect, deliberately) and keeps `off` / `count` / `full` distinct regimes. The
   raw `REGENOLD_CONCISE_COUNT_ONLY` entry stays in `engine_flags`, so an
   explicit `=1` is still distinguishable from the default (operator intent), as
   every other flag in that tuple is.
3. **The full R460 block is now the explicit pair.** Count-only wins when both
   flags are set (R461, unchanged), so the refuted arm is reachable only as
   `REGENOLD_CONCISE_COUNT_ONLY=0 REGENOLD_CONCISE_CALIBRATION=1`. Both gate
   launchers were rewritten to NAME their arms for the same reason: their OFF
   arms used to be "flags absent", which after the flip means the block is in
   force, and a re-run would have compared the block against itself. The R460
   suite's autouse fixture kills the promoted block, so it still tests the R460
   arm rather than silently measuring the count block.

## 3. Rollback

**`REGENOLD_CONCISE_COUNT_ONLY=0` in the deploy environment.** One variable, no
redeploy of code, and it restores the pre-lever Stage-2 user message
byte-for-byte (asserted in both suites). The raw entry is in `engine_flags`, so
the rolled-back state is a distinct cache regime and cannot be served a
promoted answer.

## 4. The canary, on the published endpoint

Protocol and harness: `production_canary.py` — 8 fixed official hard-board
questions (six direct asks, two fact-pattern asks; the budget for each comes from
`calibration_citation_budget`, the lever's own definition, never a copy), one
draw each, run twice around the merge. Gates: `deploy` (the served commit is the
expected one), `health` (`/healthz` ok, `/healthz/llm` `llm_ok`), `transport`
(all 200, non-empty, no refusal), `budget` (mean references DOWN, share within
the stated budget not down), `integrity` (answers not collapsed, ≥ 70 % of the
pre-promotion mean).

**PRE** — production at `ca71879d7059` (the pre-R461 commit: no conciseness
block at all), `llm_ok: true`, provider `openai_wrapper (bedrock fallback)`:

| row | budget | pre refs | pre chars |
| :-- | --: | --: | --: |
| `rg_028` | 2 | 1 | 402 |
| `rg_034` | 2 | 2 | 450 |
| `rg_040` | 2 | 2 | 808 |
| `rg_043` | 2 | 1 | 846 |
| `rg_049` | 2 | 1 | 368 |
| `rg_052` | 2 | 2 | 624 |
| `rg_004` | 2 | **6** | 652 |
| `rg_007` | 3 | **5** | 884 |

mean refs **2.50**, in budget **6/8**, mean chars **629.2**.

POST and the comparison land in `CANARY.md` / `canary-compare.json` after the
deploy, and are summarised in `CHECKPOINT.md`.

## 5. What this promotion does NOT claim

* **Not a draw-stability claim.** n=37, one draw per row: the gate decides
  direction, which is what the program's acceptance targets were written for.
  Rule #8 remains undecidable at that n — the noise floor still vetoes two gold
  heads with no lever present — and one replicate is still the way to price the
  band.
* **Not a claim that the wire and the board move identically.** Production
  passes through the route's own reference budget and post-processing; the
  canary measures the wire, which is what a user sees, and its 8 rows are a
  sanity gate rather than a board.
* **Not a change to any other lever.** The full block, the concise contract,
  the length control and the whole-head floor are untouched, and the promotion
  suite pins that only one default moved.

## 6. Canary status (2026-10-02): BLOCKED on the shipped transport

The PRE canary was captured (commit `ca71879d7059`, mean refs 2.50, 6/8 in
budget, mean chars 629.2). The POST canary has NOT run, and it must not:
`/healthz/llm` reports `primary offline (api_status_500: "No response from
Claude Code"); bedrock fallback active`. The shipped Stage-2 leg is down,
so a POST canary would measure the BEDROCK FALLBACK, not the configuration
this promotion changes - the same reason the local replicate top-up aborted
(`Stage-2 PRIMARY transport is down ... aborted`, the R423 guard refusing to
grade deterministic drafts). See `DRAW-STABLE-RULE8.md` SS5.

Nothing about the promotion decision changes: it rests on the R461 gate read
(five-of-five targets, noise floor -0.56), which was drawn while the primary
was up. What is blocked is the *confirmation on the shipped endpoint*, and
the R461.3 replicate top-up that was to put a draw band on the deciding
axis. Both resume with the same action: re-seed the wrapper token.

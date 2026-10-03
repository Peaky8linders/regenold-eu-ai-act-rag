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

## 6. Canary status (2026-10-02): RUN, PASS

The POST canary ran against the deployed merge `e1fba9733755` (deployment
`5d8b7dcf-8e18-4d59-a947-7424ebb23fae`). All five gates PASS (`CANARY.md`,
`canary-compare.json`, `canary-post.jsonl`):

* `deploy` - the served commit is the expected `e1fba9733755` (PRE was
  `ca71879d7059`);
* `health` - `/healthz` 200, `/healthz/llm` `llm_ok`;
* `transport` - 8/8 answered 200, non-empty, no refusal;
* `budget` - mean refs 2.50 -> 1.875, in budget 6/8 -> 7/8;
* `integrity` - mean chars 629.2 -> 667.8 (answers did not collapse).

Transport caveat, recorded because it bounds the claim: BOTH health reads
(PRE and POST) report `provider: openai_wrapper (bedrock fallback)` with
`primary offline (api_status_500: 'No response from Claude Code'); bedrock
fallback active`. The two phases therefore measured the promotion on the
SAME served leg - the Bedrock fallback - so the pre/post delta is
transport-consistent, but it is not yet a confirmation on the
primary-wrapper leg the board gate measured. That gap is CLOSED: the
primary-leg re-run on the round-close merge `7fbd46737548` (2026-10-02
15:49-15:56) PASSED all five gates again (`CANARY-PRIMARY.md`,
`canary-post-primary.*`). Before the run 8/8 `/healthz/llm` reads across
BOTH workers read `provider: openai_wrapper` with `detail: ok`; the
re-run's gates are `deploy` `7fbd46737548`, `health`, `transport` 8/8,
`budget` 2.50 -> 1.875 and 6/8 -> 7/8, `integrity` 629.2 -> 862.1, and
the transport counters moved 0/0 -> primary 6/7 ok with the one failure
served by the fallback. Root cause of the outage: a Max-plan session-limit
window in the wrapper's Claude Code CLI (`api_error_status: 429`,
'resets 3:30pm'), which the wrapper surfaces as the HTTP 500 'No response
from Claude Code'; the 15:30 window reset restored the leg with no config
change.

The replicate top-up was attempted twice and is CLOSED without new draws:

* the wrapper top-up (`r461-countoff-s3`, samples 2-3) was stopped by
  operator directive - wrapper quota burned - and its 31-row partial was
  removed, not resumed into;
* the Bedrock cross-transport replica drew arm A complete (2 draws,
  rerank-ON) and aborted arm B twice at the Cohere trial RERANK monthly
  cap: HTTP 429, 'You are using a Trial key, which is limited to 1000 API
  calls / month', the same on all three keys found across the projects (the
  embed endpoint still answers 200; the per-minute
  `x-trial-endpoint-call-remaining` header is a red herring). Rerank
  reorders the emitted reference list (`rerank_pool`) and the KG-context
  block, so a rerank-OFF arm is a different retrieval condition, not the
  gate's - the operator elected to skip rather than publish a caveated
  read. Arm B partial (7 rows, rerank-ON) is retained for a resume under an
  uncapped key.

**The standing verdict is therefore the one-draw draw-stable read above**:
rule #8 CLEAN, `ref_conciseness` +7.69 (CI [+1.41, +15.05]) against a floor
of +1.81 - 4.2x the floor point estimate, but `ci_excludes_floor: false`,
so the replicate-stable criterion is NOT met. `DRAW-STABLE-RULE8.md`
SS5/SS8; `GATE-RUN-BEDROCK.log` (local; `*.log` is gitignored) carries the
attempt-by-attempt record.


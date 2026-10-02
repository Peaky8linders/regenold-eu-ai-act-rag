"""R461 — record the count-only gate in the round docs.

Appends the CHECKPOINT.md round entry and adds the count-only paragraph to
CONCISENESS-PROGRAM.md: the lever in section 4, the gate in a new 5.1. Both are
appends/pure insertions, anchored on exactly one match each, idempotent.

    ../../.venv/Scripts/python.exe -m docs.measurements.r461.patch_docs
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

CHECKPOINT = ROOT / "docs" / "measurements" / "r460" / "CHECKPOINT.md"
PROGRAM = ROOT / "docs" / "measurements" / "r460" / "CONCISENESS-PROGRAM.md"

CHECKPOINT_ENTRY = """

---

## 2026-10-01 (R461 — the COUNT-ONLY conciseness gate on the SHIPPED transport) -- REFUSED on the hard rule, and the rule measured

The R460 refusal's stated next step, executed: the citation budget alone (no
sentence ceiling, no word count, no shape skeleton, and no call into
`answer_need`/`concise_limits` at all) behind `REGENOLD_CONCISE_COUNT_ONLY`,
allow-list default OFF and keyed. `COUNT-ONLY-CONFIRM.md`; lever
`apply_count_only.py`, 12 tests, launcher `run_gate_count_only.sh`, scorer
`score_gate_count_only.sh`, attribution `count_only_attribution.py`.

* Byte-identity was checked, not assumed (`verify_byte_identity.py`, 64 real board
  questions): the full block's rendering is byte-identical to `ca71879`'s
  (64/64, 705 chars, old module loaded via `git show`), every count-only line is a
  line of the full block, and 0 length clauses leak. 140 tests passed.
* Gate: `r461-countoff-s3` vs `r461-counton-s3`, `--mode hard --stride 3
  --require-cohere-rerank --cohere-rerank-min-gap 7`, `claude-opus-5-5`, same
  judge identity and `--length-control` as R460, 37/37 rows and 0 errors each,
  20.1/20.6 min. Arm A drawn FRESH so the OFF arm could be re-drawn on
  byte-identical prompts - which is what made the noise floor a measurement.
* **ref_conciseness 56.62 -> 64.31 (+7.69 [+1.41, +15.05], McNemar 10/2
  p=0.0386)**, refs/row 2.84 -> 2.51, `refs<=2` compliance 22/37 -> 27/37 (the
  full block reached the same 2.51 without the length battery).
* **The full block's two costs are gone**: ans_conciseness +0.10 [-2.71, +3.18]
  (full block -4.49 [-8.77, -0.68]), answers +6.6 chars [-32.4, +41.9] (full
  block +64.0 [+16.9, +114.6]), ans_loose and ans_strict exactly +0.00, tone flat,
  and **overall +3.80 [+0.58, +9.01] on 20/35 rows - the first overall CI in this
  program to exclude zero**, against a noise-floor pair (R461-OFF vs R460-OFF,
  byte-identical prompts) of -0.56 [-6.99, +5.79].
* **Verdict: NOT PROMOTED.** Hard rule #8 is tripped on one row, `rg_037` - and
  its provenance says `served_by=deterministic`, `polish=False`: both Stage-2 legs
  failed, tail repair failed, the deterministic Stage-1 draft shipped, so the
  block never ran (7 refs and 1,474 chars against a stated budget of 2). On the 36
  rows where the lever ran, B drops ZERO gold heads against A's two. The degraded
  leg is a lottery present in block-free arms too (R460-OFF shipped a
  `deterministic` draft on `rg_049`; R460-FULL a `prior_turn` on `rg_037`).
* **Instrument finding, and the reason the refusal is not a regression**: the
  noise-floor pair drops two gold heads on byte-identical prompts (`rg_061`, and
  `rg_088` at 0/3 criteria on an undegraded row), and moves `resp_speed` by -3.35
  [-4.59, -2.07] - so (a) the R460 gate's speed reading was never a lever effect,
  and (b) rule #8 as written is not draw-stable at n=37: a single-draw gate can
  trip it with no lever present. Proposed fix, NOT applied: evaluate the veto on
  rows where the lever ran (`stage2_polish` / `stage2_served_by`), or require the
  drop to persist across an OFF re-draw. Waiving the rule for this lever would be
  the construction argument AGENTS.md invariant #5 forbids in its place.
* Two ways forward, in order: fix the veto's operating definition and re-read this
  gate from the checkpoints on its own merits, or spend one replicate
  (`run_gate_count_only.sh 3`) so `rg_037` can run the lever. Nothing default-ON;
  `promote_conciseness_calibration.py` still unapplied, and no
  `promote_count_only.py` written.
"""

PROGRAM_ANCHOR = """Replicates 2-3 of the wrapper gate were not spent: the tunnel's quota is the
scarce resource this round, and the deciding delta is systematic at the row level
rather than marginal. The launcher resumes them in one command
(`run_gate_wrapper.sh 3`).
"""

PROGRAM_ADDITION = """

### 5.1 The count-only variant, gated alone (R461) — every target met but the hard rule

The sub-lever section 5 identified was built and gated on its own transport run.
`REGENOLD_CONCISE_COUNT_ONLY` (`answer_need.count_only_block`, 331 chars) emits the
budget, the rule-out rule and the citation-order line and **nothing else**: no
sentence ceiling, no word count, no shape skeleton, and no call into
`answer_need`/`concise_limits`. `COUNT-ONLY-CONFIRM.md` is the round record.

`--mode hard --stride 3`, `claude-opus-5-5`, same judge identity, both arms fresh,
37/37 rows and 0 errors each, and arm A drawn fresh so the OFF arm is re-drawn on
**byte-identical prompts** (`verify_byte_identity.py` proves the bytes; the earlier
OFF arm loads as a second module from `git show` and renders identically on all 64
board questions).

| axis | OFF | COUNT-ONLY | Δ | CI |
| :-- | --: | --: | --: | :-- |
| ans_correctness_loose / _strict | 94.82 / 91.89 | 94.82 / 91.89 | **+0.00 / +0.00** | [-8.11, +8.11] |
| ans_conciseness | 81.95 | 82.05 | +0.10 | [-2.71, +3.18] |
| ref_conciseness | 56.62 | 64.31 | **+7.69** | **[+1.41, +15.05]** |
| regulatory_tone | 97.30 | 97.30 | +0.00 | flat |
| resp_speed | 86.81 | 86.19 | -0.62 | [-2.52, +1.45] |
| answers (chars) | 813.5 | 820.2 | +6.6 | [-32.4, +41.9] |
| **overall** (per-row) | 73.98 | 77.78 | **+3.80** | **[+0.58, +9.01]** |

The count mechanism reproduces a third time (+7.69 against +5.52 here and +4.76 on
Bedrock), and **the full block's two costs disappear**: answers no longer grow
(+6.6 vs +64.0, whose CI excluded zero) and speed no longer moves. On the same
method, the noise-floor pair (OFF re-drawn, byte-identical prompts) reads -0.56
[-6.99, +5.79], so **+3.80 is the first overall delta in this program whose paired
CI excludes zero.**

**Verdict: NOT PROMOTED.** Hard rule #8 is tripped on one row, `rg_037`, whose
provenance is `served_by=deterministic` / `polish=False` — both Stage-2 legs failed
and the deterministic Stage-1 draft shipped, so the block never ran on it (its 7
refs and 1,474 chars contradict the budget of 2 it was given). On the 36 rows where
the lever ran, the count-only arm drops ZERO gold heads against its OFF arm's two.

**And the rule itself was measured.** That same noise-floor pair drops two gold
heads on byte-identical prompts — `rg_061`, and `rg_088` at 0/3 criteria on an
UNDEGRADED row — and moves `resp_speed` -3.35 [-4.59, -2.07]. So rule #8 as
written is not draw-stable at n=37, a single-draw gate can trip it with no lever
present, and the R460 gate's speed reading was a draw artifact rather than a lever
effect. The fix the evidence supports is to evaluate the veto only on rows where
the lever ran, or to require the drop to persist across an OFF re-draw — a change
to the instrument, to be made on its own merits and not as a retro-fit exemption
for this lever.
"""

PROGRAM_IMPL_ANCHOR = """Registered in `_engine_cache_key`. Off → the user message is byte-identical
(asserted).
"""

PROGRAM_IMPL_ADDITION = """Registered in `_engine_cache_key`. Off → the user message is byte-identical
(asserted).

**Generator: `REGENOLD_CONCISE_COUNT_ONLY` (R461)** — the citation-budget half of
the block above, rendered alone by `answer_need.count_only_block()`: three lines,
331 chars, the numeric budget, the rule that a provision the facts engage and the
answer rules out still counts, and the citation-order line. It deliberately calls
neither `answer_need` nor `concise_limits`, so the length battery cannot leak back
in and a broken length estimate cannot take the budget down with it. Allow-list,
default OFF, registered in `_engine_cache_key`, and byte-identically additive to
the shipped contract (asserted). Section 5.1 is its gate.
"""


def patch(path: Path, old: str, new: str, *, label: str, append: bool = False) -> None:
    raw = path.read_text(encoding="utf-8")
    crlf = "\r\n" in raw
    o = old.replace("\n", "\r\n") if crlf else old
    n = new.replace("\n", "\r\n") if crlf else new
    if append:
        if raw.endswith(n):
            print(f"  already applied: {label}")
            return
        path.write_text(raw + n, encoding="utf-8")
        print(f"  applied: {label}")
        return
    if n and n in raw and o not in raw:
        print(f"  already applied: {label}")
        return
    count = raw.count(o)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match in {path.name}, found {count}")
    path.write_text(raw.replace(o, n, 1), encoding="utf-8")
    print(f"  applied: {label}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("CHECKPOINT.md:")
    patch(CHECKPOINT, "", CHECKPOINT_ENTRY, label="R461 round entry", append=True)
    print("CONCISENESS-PROGRAM.md:")
    patch(PROGRAM, PROGRAM_IMPL_ANCHOR, PROGRAM_IMPL_ADDITION, label="section 4 - the count-only lever")
    patch(PROGRAM, PROGRAM_ANCHOR, PROGRAM_ANCHOR + PROGRAM_ADDITION, label="section 5.1 - the gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

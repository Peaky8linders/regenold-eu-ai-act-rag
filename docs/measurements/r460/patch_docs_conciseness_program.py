"""Record the conciseness program in this round's CHECKPOINT + plan.

    ../../.venv/Scripts/python.exe docs/measurements/r460/patch_docs_conciseness_program.py
"""
from __future__ import annotations

import sys
from pathlib import Path

R460 = Path(__file__).resolve().parent

ENTRY = """
---

## 2026-09-30 (Conciseness program) -- generator + measurement levers (default OFF)

`CONCISENESS-PROGRAM.md`. The Ref Conciseness negative was a PRUNER negative, not
an axis negative: both conciseness axes are one-sided ratios, so the scoring
optimum is the minimum answer that still covers every criterion, and the gold
reference answer is a per-row existence proof that it fits.

* Measured targets (`conciseness_program_analysis.py`): answers ship 1.25x the
  reference length (81% of hard rows over it) with 2.0x its citations, while
  `answer_need.target_chars` is ALREADY calibrated (median -36 chars from the
  reference). So it is a COMPLIANCE failure, not an estimation one. Prize:
  ans_conc 81.54 -> 100 is +1.9 pp overall; ref_conc 59.14 -> 100 is +5.8 pp.
* Citation COUNT is not shape-dependent: |expected| is 1.25-1.50 on every shape
  and `<= 2` covers 97% of the 110 gold rows. Which two must stay the model's
  judgement - every blind cap pays for its conciseness on Ref Strict.
* Implemented, default OFF: `REGENOLD_CONCISE_CALIBRATION`
  (`answer_need.calibration_block`, appended LAST in `build_evidence_answer_user`)
  restates the shipped ceiling as a COUNTED self-check, adds a numeric citation
  budget (2 direct / 3 scenario) and a structural skeleton at the target size;
  registered in `_engine_cache_key`; tests `test_r460_conciseness_calibration.py`
  (8). Byte-identical when off.
* Implemented, default OFF: `--length-control` on `evals/official/score_arm.py`
  (`rubric.truncate_to_chars` + `_length_controlled_rows`) re-judges every answer
  CUT to its reference length and reports those axes beside the raw ones in the
  console and the payload, so a correctness edge cannot be verbosity; loud when
  the judge transport dies; end-to-end tested with a faked transport
  (`test_r460_length_control.py`, 7).
* 207 tests pass across the touched suites; ruff clean on every file touched
  (the one UP037 in `regenold.py` is pre-existing at HEAD).
* Gate design in the doc: paired hard board with the flag ON vs the recorded
  `r460-cohere-hard-s3`, scored with `--length-control`; acceptance is
  ans_conc >= 92 and ref_conc >= 85 with no correctness loss.
"""

PLAN_OLD = """Nothing further in Tier 1 is worth
a board; the remaining scored lever is RESERVE, which needs the operator ruling."""

PLAN_NEW = """Nothing further in Tier 1 is worth
a board. The Ref Conciseness axis is NOT closed - only its pruner family is: the
count is decided in the generator, so the work moved there
(`CONCISENESS-PROGRAM.md`: a default-OFF counted-ceiling + citation-budget lever,
and a default-OFF length-controlled judge pass that stops a correctness edge from
being verbosity). The remaining scored lever is RESERVE, which needs the
operator ruling."""


def patch(path: Path, old: str, new: str, *, label: str) -> None:
    raw = path.read_text(encoding="utf-8")
    crlf = "\r\n" in raw
    o = old.replace("\n", "\r\n") if crlf else old
    n = new.replace("\n", "\r\n") if crlf else new
    if new and n in raw and o not in raw:
        print(f"  already applied: {label}")
        return
    count = raw.count(o)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    path.write_text(raw.replace(o, n, 1), encoding="utf-8")
    print(f"  applied: {label}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("ANALYSIS-AND-PLAN.md:")
    patch(R460 / "ANALYSIS-AND-PLAN.md", PLAN_OLD, PLAN_NEW, label="status pointer")
    print("CHECKPOINT.md:")
    p = R460 / "CHECKPOINT.md"
    raw = p.read_text(encoding="utf-8")
    if "Conciseness program) -- generator + measurement" in raw:
        print("  already applied: entry")
    else:
        entry = ENTRY.replace("\n", "\r\n") if "\r\n" in raw else ENTRY
        p.write_text(raw.rstrip("\r\n") + ("\r\n" if "\r\n" in raw else "\n") + entry,
                     encoding="utf-8")
        print("  applied: entry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

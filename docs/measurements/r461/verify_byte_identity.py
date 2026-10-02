"""R461 — the two facts the count-only gate rests on, checked, not asserted.

1. **The full block did not change.** R461 refactors ``calibration_block`` to
   share its two count clauses with the new variant. That refactor is only safe
   if the R460 arm's rendering is byte-identical to the R460 commit's, on real
   questions: otherwise the count-only arm would be compared against a moved
   baseline. This compares against ``git show <base>:app/engines/answer_need.py``
   loaded as a second module, so the check is against the COMMIT, not a memory of
   it.
2. **The count-only block is a REMOVAL.** Every line it emits, after stripping the
   prefix that turns a skeleton line into a standalone bullet, is literally a line
   of the full block. If that ever stops holding, the gate is measuring a
   re-wording rather than the absence of the length battery.

Questions come from the two R460 wrapper-gate checkpoints (37 real hard rows each,
the arms this gate is compared with) plus the R413 case file.

    ../../.venv/Scripts/python.exe -m docs.measurements.r461.verify_byte_identity
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

BASE = "ca71879d70596619f1fe3fbcc9858ac7ff1d3950"

CKPTS = (
    ROOT / "evals/bench/results/official-r460-tunnel-off-s3-hard.ckpt.jsonl",
    ROOT / "evals/bench/results/official-r460-tunnel-on-s3-hard.ckpt.jsonl",
)
CASES = ROOT / "docs/measurements/r413/cases.jsonl"

BANNED = ("sentences", "words", "Match this shape", "LENGTH AND CITATION",
          "Delete the sentence")


def _questions() -> list[str]:
    out: list[str] = []
    for path in (*CKPTS, CASES):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                q = json.loads(line).get("question", "")
                if q:
                    out.append(q)
    seen, uniq = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


def _old_module(base: str) -> types.ModuleType:
    src = subprocess.run(
        ["git", "show", f"{base}:app/engines/answer_need.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    mod = types.ModuleType("old_answer_need")
    mod.__file__ = "<git show answer_need.py>"
    # dataclass resolves the defining module through sys.modules, so the
    # module has to be registered before its body runs.
    sys.modules["old_answer_need"] = mod
    try:
        exec(compile(src, "old_answer_need.py", "exec"), mod.__dict__)  # noqa: S102
    except Exception:
        sys.modules.pop("old_answer_need", None)
        raise
    return mod


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE,
                    help="the R460 commit whose rendering must be preserved")
    args = ap.parse_args()

    from app.engines.answer_need import (
        calibration_block,
        calibration_citation_budget,
        count_only_block,
    )

    old = _old_module(args.base)
    questions = _questions()
    print(f"questions: {len(questions)}")

    os.environ.pop("REGENOLD_CONCISE_COUNT_ONLY", None)
    os.environ["REGENOLD_CONCISE_CALIBRATION"] = "1"

    # --- 1. the R460 full block is byte-identical ---------------------------- #
    full_diffs, full_len = [], 0
    for q in questions:
        a, b = old.calibration_block(q), calibration_block(q)
        full_len = len(b)
        if a != b:
            full_diffs.append(q[:70])
    print(f"full block unchanged vs {args.base[:9]}: "
          f"{len(questions) - len(full_diffs)}/{len(questions)} byte-identical "
          f"({full_len} chars)")
    for q in full_diffs[:5]:
        print(f"  DIFF: {q}")

    # --- 2. off renders nothing --------------------------------------------- #
    os.environ.pop("REGENOLD_CONCISE_CALIBRATION", None)
    off_clean = all(
        calibration_block(q) == "" and count_only_block(q) == "" for q in questions
    )
    print(f"both flags absent -> both blocks empty: {off_clean}")

    # --- 3. the count-only block is a strict subset of the full block -------- #
    os.environ["REGENOLD_CONCISE_CALIBRATION"] = "1"
    os.environ["REGENOLD_CONCISE_COUNT_ONLY"] = "1"
    subset_ok, scenarios, sizes, offenders = True, 0, [], []
    for q in questions:
        count = count_only_block(q)
        assert count, q
        sizes.append(len(count))
        if calibration_citation_budget(q) == 3:
            scenarios += 1
        # Normalise away ONLY the decoration that legitimately differs: the
        # count-only block renders the skeleton's indented clauses as standalone
        # bullets. The clause TEXT must be identical.
        reference = {
            ln.strip().removeprefix("* ").strip()
            for block in (calibration_block(q), old.calibration_block(q))
            for ln in block.splitlines()
        }
        for line in count.splitlines()[1:]:  # line 0 is the count-only header
            if line.strip().removeprefix("* ").strip() not in reference:
                offenders.append(line)
                subset_ok = False
    for line in offenders[:5]:
        print(f"  NOT A SUBSET: {line[:80]!r}")
    print(f"every count-only line is a line of the full block: {subset_ok}")
    print(f"count-only block: {min(sizes)}-{max(sizes)} chars "
          f"(full block {full_len}); scenario-budget rows: {scenarios}/{len(questions)}")

    # --- 4. no length clause anywhere ---------------------------------------- #
    leaked = [(b, q[:50]) for q in questions for b in BANNED if b in count_only_block(q)]
    print(f"length clause leaks: {len(leaked)}")

    os.environ.pop("REGENOLD_CONCISE_COUNT_ONLY", None)
    os.environ.pop("REGENOLD_CONCISE_CALIBRATION", None)

    ok = not full_diffs and off_clean and subset_ok and not leaked
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

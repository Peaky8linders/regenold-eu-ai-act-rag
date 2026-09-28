"""R452 — replay the question-support veto over every recorded live answer.

For each recorded graded turn (answer + wire references) whose question has a
reconstructed gold key, every wire sub-point is traced back to its head, and the
head is re-deepened with the veto OFF and ON. Where OFF reproduces the shipped
coordinate and ON returns something else, the shipped coordinate is replaced by
the ON result. The three reference axes are then scored with the REAL
``evals.official.rubric`` on both reference lists.

Upper bound on the cost: a vetoed coordinate the answer's prose names explicitly
would be restored by the prose sub-point passes on the live path; this replay
does not credit that.

    py -3.12 docs/measurements/r452/grain_question_support_replay.py [RESULTS_DIR] [--flag=NAME]

``--flag`` picks the veto to measure; every other flag keeps its default, so
``--flag=REGENOLD_GRAIN_DISCRIMINATING_SUPPORT`` reads R452b's increment over R452.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from app.routes import regenold as R  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    ref_head,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
FLAG = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--flag=")),
            "REGENOLD_GRAIN_QUESTION_SUPPORT")


def _graded(row: dict) -> tuple[str, list[str]]:
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return row.get("pushback_answer") or "", [str(x) for x in row.get("pushback_refs") or []]
    return row.get("pred_answer") or "", [str(x) for x in row.get("pred_refs") or []]


def _deepen(head: str, question: str, answer: str, on: bool) -> str:
    os.environ[FLAG] = "1" if on else "0"
    return R._deepen_one_ref(head, question, answer)


def _mean(xs: list[float]) -> float:
    return 100.0 * sum(xs) / len(xs) if xs else float("nan")


def main() -> int:
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    results = Path(positional[0]) if positional else REPO / "evals" / "bench" / "results"
    print(f"flag measured: {FLAG}")
    gold = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g.get("expected_refs") or []

    seen: set[tuple] = set()
    rows = []
    for path in sorted(results.glob("official-*.ckpt.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = str(row.get("id"))
            answer, refs = _graded(row)
            if rid not in gold or not gold[rid] or not answer or not refs:
                continue
            key = (rid, answer, tuple(refs))
            if key in seen:
                continue
            seen.add(key)
            rows.append((rid, row.get("question") or "", answer, refs))

    axes = {arm: {"loose": [], "strict": [], "conc": []} for arm in ("off", "on", "credited")}
    changed_rows = changed_refs = gold_lost = wrong_removed = head_bad = count_bad = 0
    prose_named_vetoes = gold_lost_credited = 0
    examples: list[str] = []
    for rid, question, answer, refs in rows:
        new_refs: list[str] = []
        credited_refs: list[str] = []
        named = {leaf.lower() for leaves in R._prose_named_subpoints(answer).values() for leaf in leaves}
        for ref in refs:
            head = ref_head(ref)
            out = ref
            credited = ref
            if head and head != ref:
                off = _deepen(head, question, answer, on=False)
                if off == ref:
                    on = _deepen(head, question, answer, on=True)
                    if on != off:
                        out = on
                        changed_refs += 1
                        prose_named = ref.lower() in named or any(n.startswith(ref.lower() + ".") for n in named)
                        if prose_named:
                            prose_named_vetoes += 1
                        else:
                            credited = on
                        exp = gold[rid]
                        met_before = reference_correctness_strict([ref], exp) or 0.0
                        met_after = reference_correctness_strict([on], exp) or 0.0
                        if met_after < met_before:
                            gold_lost += 1
                            if not prose_named:
                                gold_lost_credited += 1
                        else:
                            wrong_removed += 1
                        if len(examples) < 40:
                            examples.append(f"{rid}: {ref} -> {on}  (expected {exp})")
            if out not in new_refs:
                new_refs.append(out)
            if credited not in credited_refs:
                credited_refs.append(credited)
        if new_refs != refs:
            changed_rows += 1
        if {ref_head(r) for r in refs} != {ref_head(r) for r in new_refs}:
            head_bad += 1
        if len(new_refs) != len(refs):
            count_bad += 1
        exp = gold[rid]
        for arm, pred in (("off", refs), ("on", new_refs), ("credited", credited_refs)):
            for axis, fn in (
                ("loose", reference_correctness_loose),
                ("strict", reference_correctness_strict),
                ("conc", reference_conciseness),
            ):
                v = fn(pred, exp)
                if v is not None:
                    axes[arm][axis].append(v)

    print(f"recorded graded turns with gold: {len(rows)} (unique answer+refs)")
    print(f"rows changed: {changed_rows}   refs vetoed: {changed_refs}")
    print(f"  vetoed refs that met a gold key more precisely than the head (Ref Strict loss): {gold_lost}")
    print(f"  vetoed refs that met no gold key at that grain (wrong picks removed): {wrong_removed}")
    print(f"head-set violations: {head_bad}   count changes: {count_bad} (dedup only)")
    print(f"vetoes on leaves the prose names (the live route restores them): {prose_named_vetoes};"
          f" Ref Strict losses left after crediting them: {gold_lost_credited}")
    for axis in ("loose", "strict", "conc"):
        a, b, c = (_mean(axes[k][axis]) for k in ("off", "on", "credited"))
        print(f"  ref_{axis:6}  off {a:6.2f}   on {b:6.2f} ({b - a:+.2f})   credited {c:6.2f} ({c - a:+.2f})")
    print("\nexamples:")
    for e in examples:
        print("  ", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

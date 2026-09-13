"""Why does the closed-set member detector miss the OMITTED_ENUMERATED_ITEM rows?

Deterministic — no network, no LLM. Inputs (all frozen on disk):

* ``evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl``
  — the recorded R407 hard answers.
* ``docs/measurements/r388/official_gold_n110.jsonl`` — the questions.
* ``docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json`` — the
  judge triage carrying the root cause ``OMITTED_ENUMERATED_ITEM``.

For every such row it reports WHICH gate blocks the detector, so a recall change
can be aimed at a measured blocker instead of a guess. Gates, in order:

1. ``is_list_question(ask)``        — the detector only fires on list-shaped asks.
2. parent/member already mentioned  — completion cannot invent a head.
3. ``_question_engages(...)``       — the question must ask for the set.
4. ``len(children) >= _MIN_GROUP_CHILDREN``.

Run:  REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe docs/measurements/r411/member_recall_probe.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

from app.data.provision_hierarchy import closed_set_members  # noqa: E402
from app.engines import answer_completeness as AC  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CKPT = ROOT / "evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl"
GOLD = ROOT / "docs/measurements/r388/official_gold_n110.jsonl"
TRIAGE = ROOT / "docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json"


def _load() -> tuple[dict[str, str], dict[str, str], list[dict]]:
    answers: dict[str, str] = {}
    for line in CKPT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = row.get("id") or row.get("row_id")
        # R416: this checkpoint records the GRADED answer in pred_answer.
        # Reading answer/final_answer silently loaded ZERO of 110 answers and
        # still printed a successful blocker histogram. Never substitute turn 1
        # (the pushback may have changed it), or fall back from a void pred_answer.
        ans = row.get("pred_answer")
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError("checkpoint row has no id")
        if rid in answers:
            raise ValueError(f"duplicate checkpoint id: {rid}")
        if not isinstance(ans, str) or not ans.strip():
            raise ValueError(f"checkpoint {rid} has no non-empty pred_answer")
        answers[rid] = ans
    questions = {
        r["id"]: r.get("question", "")
        for r in (
            json.loads(line)
            for line in GOLD.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    triage = json.loads(TRIAGE.read_text(encoding="utf-8"))
    target_ids = {r["id"] for r in triage if r.get("rc") == "OMITTED_ENUMERATED_ITEM"}
    if not target_ids:
        raise ValueError("triage contains no OMITTED_ENUMERATED_ITEM rows")
    missing = sorted(rid for rid in target_ids if rid not in answers or not questions.get(rid, "").strip())
    if missing:
        raise ValueError(f"target rows missing graded answers or questions: {', '.join(missing)}")
    return answers, questions, triage


def _gate_report(question: str, answer: str) -> tuple[str, str]:
    """Return (blocking_gate, detail)."""
    if not question.strip() or not answer.strip():
        raise ValueError("blocker diagnosis requires a question and a graded answer")
    ask = AC._ask_text(question)
    if not AC.is_list_question(ask):
        return "1:not_a_list_question", ""
    ans = AC._s(answer)
    ans_paths = AC._paths_in(ans)
    mentioned = AC._prefix_closure(ans_paths)
    ask_coords = {AC._coord_str(p) for p in AC._paths_in(ask)}
    q_bigrams = AC._word_bigrams(ask)
    heads = AC._dedupe(AC.named_heads(ans) + AC.named_heads(ask))
    heads = list(heads)
    if not heads:
        return "2:no_named_head", ""
    tried: list[str] = []
    for head in heads:
        try:
            members = closed_set_members(head)
        except Exception:  # noqa: BLE001
            members = []
        for parent, children in AC._groups(members):
            if "." not in parent or len(children) < AC._MIN_GROUP_CHILDREN:
                tried.append(f"{head}/{parent}:too_small({len(children)})")
                continue
            if parent not in mentioned and not any(c in mentioned for c, _ in children):
                tried.append(f"{head}/{parent}:3:answer_does_not_name_set")
                continue
            if not AC._question_engages(parent, head, children, ask_coords, q_bigrams):
                tried.append(f"{head}/{parent}:4:question_not_engaged")
                continue
            tried.append(f"{head}/{parent}:ENGAGED")
    if any(t.endswith(":ENGAGED") for t in tried):
        return "ENGAGED", "; ".join(tried)
    if not tried:
        return "2:no_closed_set_head", ""
    # Report the most advanced blocker seen.
    for gate in ("4:question_not_engaged", "3:answer_does_not_name_set"):
        for t in tried:
            if gate in t:
                return gate, "; ".join(tried)
    return "group_too_small", "; ".join(tried)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write a provenance-tagged JSON report")
    args = parser.parse_args(argv)
    try:
        answers, questions, triage = _load()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"INDETERMINATE: {exc}", file=sys.stderr)
        return 2
    omitted = [r for r in triage if r.get("rc") == "OMITTED_ENUMERATED_ITEM"]
    by_row: dict[str, list[dict]] = {}
    for r in omitted:
        by_row.setdefault(r["id"], []).append(r)

    print("=" * 92)
    print("OMITTED_ENUMERATED_ITEM rows: which gate blocks the member detector?")
    print("=" * 92)
    counts: dict[str, int] = {}
    results: list[dict] = []
    for rid in sorted(by_row):
        q = questions[rid]
        ans = answers[rid]
        provs = sorted({p.strip() for r in by_row[rid] for p in r.get("prov", "").split(";") if p.strip()})
        gate, detail = _gate_report(q, ans)
        gaps = AC.missing_closed_set_members(q, ans)
        results.append({"id": rid, "criteria": len(by_row[rid]), "gate": gate,
                        "detail": detail, "gaps": [g.coordinate for g in gaps]})
        counts[gate] = counts.get(gate, 0) + 1
        print(f"\n{rid}  crit={len(by_row[rid])}  prov={','.join(provs)}")
        print(f"  Q: {q[:150]}")
        print(f"  -> {gate}")
        if detail:
            print(f"     {detail[:260]}")

    print("\n" + "=" * 92)
    print("BLOCKER HISTOGRAM")
    print("=" * 92)
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {v:3d}  {k}")
    print(f"Validated {len(answers)} graded answers; diagnosed {len(results)} target rows.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "answer_field": "pred_answer", "graded_answers": len(answers),
            "inputs": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (CKPT, GOLD, TRIAGE)},
            "counts": counts, "rows": results,
        }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

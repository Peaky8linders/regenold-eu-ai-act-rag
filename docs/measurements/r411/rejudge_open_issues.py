"""R411 re-check: run the R409 frontier-judge question set against the CURRENT engine.

The R409 snapshot (`docs/measurements/r409/antifragile_frontier_judge_results.json`)
recorded `current_engine.answer` / `.references` at commit `dd797d9` with the same
deterministic offline environment used here. Several fixes have landed since (R411:
Art 6(3) mention gate, Art 113 applicability seed, statutory attribution corrections),
so the recorded criteria verdicts are stale for any row whose answer or references
changed.

This probe re-runs the engine and prints:

  * every row whose answer text or reference set CHANGED (the stale-verdict set);
  * the recorded failing criteria for every row, split changed vs unchanged.

It makes no network calls and needs no LLM. The judge pass is a separate step that
consumes the JSON this writes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Reuse the R409 instrument verbatim: same datasets, same env, same engine call.
sys.path.insert(0, str(REPO / "docs" / "measurements" / "r409"))
from run_antifragile_frontier_judge import (  # noqa: E402
    PART_I_QUESTIONS,
    PART_II_QUESTIONS,
    query_engine,
)

SNAPSHOT = REPO / "docs" / "measurements" / "r409" / "antifragile_frontier_judge_results.json"
OUT = REPO / "docs" / "measurements" / "r411" / "rejudge-current-path.json"


def _norm_refs(refs) -> list[str]:
    return [str(r).strip() for r in (refs or [])]


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8-sig"))
    snap_p1 = {it["id"]: it for it in snapshot["part_1"]}
    snap_p2 = {it["id"]: it for it in snapshot["part_2"]}

    rows: list[dict] = []

    for item in PART_I_QUESTIONS:
        qid = item["id"]
        res = query_engine(item["question"])
        old = snap_p1.get(qid, {}).get("current_engine", {})
        rows.append(
            {
                "id": qid,
                "part": 1,
                "num": item["num"],
                "question": item["question"],
                "criteria": item["criteria"],
                "expected_refs": item["expected_refs"],
                "old_answer": old.get("answer", ""),
                "old_refs": _norm_refs(old.get("references")),
                "old_criteria_results": (old.get("judge") or {}).get("criteria_results"),
                "new_answer": res["answer"],
                "new_refs": _norm_refs(res["references"]),
                "new_latency_s": res["latency_s"],
            }
        )

    for item in PART_II_QUESTIONS:
        qid = item["id"]
        res = query_engine(item["corrected_question"])
        old = snap_p2.get(qid, {}).get("current_engine", {})
        rows.append(
            {
                "id": qid,
                "part": 2,
                "num": item["num"],
                "title": item["title"],
                "question": item["corrected_question"],
                "criteria": item["criteria"],
                "expected_refs": item["gold_refs"],
                "old_answer": old.get("answer", ""),
                "old_refs": _norm_refs(old.get("references")),
                "old_criteria_results": (old.get("judge") or {}).get("criteria_results"),
                "new_answer": res["answer"],
                "new_refs": _norm_refs(res["references"]),
                "new_latency_s": res["latency_s"],
            }
        )

    for r in rows:
        r["answer_changed"] = r["old_answer"].strip() != r["new_answer"].strip()
        r["refs_changed"] = r["old_refs"] != r["new_refs"]
        r["changed"] = r["answer_changed"] or r["refs_changed"]
        ocr = r["old_criteria_results"] or []
        r["recorded_failing"] = [
            r["criteria"][i] for i, ok in enumerate(ocr) if ok is False and i < len(r["criteria"])
        ]

    changed = [r for r in rows if r["changed"]]
    print("=" * 100)
    print("ROWS WHOSE ANSWER OR REFERENCES CHANGED SINCE THE R409 SNAPSHOT (stale verdicts)")
    print("=" * 100)
    for r in changed:
        print(f"\n[{r['id']}] {'/'.join(r.get('title', '').split())} ({r['question'][:88]})")
        if r["answer_changed"]:
            print(f"   answer: {r['old_answer'][:150]!r}")
            print(f"        -> {r['new_answer'][:150]!r}")
        if r["refs_changed"]:
            print(f"   refs  : {r['old_refs']}")
            print(f"        -> {r['new_refs']}")
    print(f"\nchanged rows: {len(changed)} / {len(rows)}")

    print("\n" + "=" * 100)
    print("RECORDED FAILING CRITERIA BY ROW (verify against the NEW answer — stale if changed)")
    print("=" * 100)
    for r in rows:
        flag = " *CHANGED*" if r["changed"] else ""
        print(f"\n[{r['id']}]{flag} {r['question'][:95]}")
        print(f"   refs now: {r['new_refs']}")
        if not r["recorded_failing"]:
            print("   recorded fails: NONE")
        for c in r["recorded_failing"]:
            print(f"   FAIL: {c[:170]}")

    OUT.write_text(
        json.dumps({"rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

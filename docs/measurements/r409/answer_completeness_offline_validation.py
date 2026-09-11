"""R409 — offline validation of ``app/engines/answer_completeness.py``.

Run from the repo root (deterministic, no network):

    REGENOLD_SKIP_DOTENV=1 py -3.12 docs/measurements/r409/answer_completeness_offline_validation.py

Inputs (read-only):

* ``evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl``
  (gitignored): 110 hard-mode rows. ``pred_answer`` is the graded post-pushback
  answer, ``turn1_answer`` the answer the pushback disputed, ``question`` the bare
  question.
* ``docs/measurements/r388/score-r407-sonnet5-tunnel-hard.json``: ``rows[].criteria``
  booleans graded on exactly those ``pred_answer`` strings (110/110 identical).
  FAILING = any criterion false, PASSING = all true.
* ``docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json``: root cause
  per failing criterion.

All five R409 flags are ON. The detectors receive the question the ROUTE builds:
``_build_question_from_history`` over ``[user question, assistant turn1_answer,
user PUSHBACK_TEMPLATE]``. With the R305 re-ask focus ON (production default) that
is the BARE question, which the pushback detectors cannot use, so the flattened
concatenation format is produced with ``REGENOLD_REASK_FOCUS=0`` and both are
reported.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FLAGS = (
    "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD",
    "REGENOLD_EXCEPTION_LIMB_GUARD",
    "REGENOLD_VERDICT_LEAD_GUARD",
    "REGENOLD_PUSHBACK_KEEP_CONTRACT",
    "REGENOLD_GOVERNING_PROVISION_CLAUSE",
)

# Deterministic offline environment, set BEFORE the first ``app`` import.
os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["REGENOLD_QUERY_DENOISER"] = "0"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
for _key in ("GROQ_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ[_key] = ""
for _flag in FLAGS:
    os.environ[_flag] = "1"

from app.engines import answer_completeness as ac  # noqa: E402
from app.routes.regenold import _build_question_from_history  # noqa: E402
from evals.regenold.official_batch import PUSHBACK_TEMPLATE  # noqa: E402

CKPT = ROOT / "evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl"
SCORE = ROOT / "docs/measurements/r388/score-r407-sonnet5-tunnel-hard.json"
LEDGER = ROOT / "docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json"

GAP_DETECTORS = {
    "member": ("OMITTED_ENUMERATED_ITEM", ac.missing_closed_set_members),
    "exception": ("MISSING_CONDITION_OR_EXCEPTION", ac.missing_exception_limbs),
    "verdict": ("VERDICT_POLARITY_OR_FRAMING", ac.verdict_lead_gap),
    "keep": ("PUSHBACK_DRIFT", ac.dropped_pushback_points),
}
CLAUSE_BUILDERS = {
    "governing_clause": ("WRONG_OR_MISSING_PROVISION", ac.governing_provision_clause),
    "keep_clause": ("PUSHBACK_DRIFT", ac.pushback_keep_clause),
}
_PROV_RE = re.compile(r"(Article \d+(?:\.\w+)*|Annex [IVX]+(?:\.\w+)*)")


def route_question(row: dict, reask_focus: str) -> str:
    os.environ["REGENOLD_REASK_FOCUS"] = reask_focus
    messages = [
        SimpleNamespace(role="user", content=row["question"]),
        SimpleNamespace(role="assistant", content=row["turn1_answer"]),
        SimpleNamespace(role="user", content=PUSHBACK_TEMPLATE.format(question=row["question"])),
    ]
    return _build_question_from_history(messages)[0]


def coordinate_hit(kind: str, gaps: list, prov: str) -> bool:
    provs = _PROV_RE.findall(prov or "")
    for g in gaps:
        for p in provs:
            if g.coordinate == p or g.coordinate.startswith(p + "."):
                return True
            if kind == "exception" and p.startswith(g.coordinate + "."):
                return True
    return False


def pct(k: int, n: int) -> str:
    return f"{k}/{n} ({100.0 * k / n:.1f}%)" if n else f"{k}/0"


def main() -> int:
    rows = [json.loads(line) for line in CKPT.read_text(encoding="utf-8").splitlines() if line.strip()]
    score_rows = {r["id"]: r for r in json.loads(SCORE.read_text(encoding="utf-8"))["rows"]}
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    failing = {rid for rid, r in score_rows.items() if not all(r["criteria"])}
    passing = {rid for rid in score_rows if rid not in failing}
    identical = sum(1 for r in rows if score_rows[r["id"]]["answer"] == r["pred_answer"])

    print("# R409 answer_completeness offline validation")
    print()
    print(f"rows={len(rows)} failing={len(failing)} passing={len(passing)} "
          f"score.answer==ckpt.pred_answer: {identical}/{len(rows)}")
    targets: dict[str, set[str]] = {}
    for kind, (rc, _) in {**GAP_DETECTORS, **CLAUSE_BUILDERS}.items():
        targets[kind] = {c["id"] for c in ledger if c["rc"] == rc}
        n_crit = sum(1 for c in ledger if c["rc"] == rc)
        print(f"  {kind:17s} target root cause {rc}: {n_crit} criteria on {len(targets[kind])} rows")

    results: dict[str, dict[str, object]] = {}
    fmt_marker = fmt_prev = focus_bare = 0
    consistency_breaks: list[str] = []
    for row in rows:
        rid, answer = row["id"], row["pred_answer"]
        q_flat = route_question(row, "0")
        q_default = route_question(row, "1")
        fmt_marker += "Latest question:\n" in q_flat
        fmt_prev += ac.previous_answer(q_flat) == row["turn1_answer"].strip()
        focus_bare += q_default == row["question"].strip()
        per: dict[str, object] = {}
        for kind, (_, fn) in GAP_DETECTORS.items():
            per[kind] = fn(q_flat, answer)
        for kind, (_, fn) in CLAUSE_BUILDERS.items():
            per[kind] = fn(q_flat)
        per["all"] = ac.collect_gaps(q_flat, answer)
        per["keep@default"] = ac.dropped_pushback_points(q_default, answer)
        per["keep_clause@default"] = ac.pushback_keep_clause(q_default)
        for kind in ("member", "exception", "verdict"):
            bare = GAP_DETECTORS[kind][1](row["question"], answer)
            if bare != per[kind]:
                consistency_breaks.append(f"{rid}:{kind}")
        results[rid] = per

    print()
    print("## Route question format")
    print(f"REGENOLD_REASK_FOCUS=0: 'Latest question:' marker present {fmt_marker}/{len(rows)}, "
          f"previous_answer()==turn1_answer {fmt_prev}/{len(rows)}")
    print(f"REGENOLD_REASK_FOCUS=1 (default): route hands the engine the BARE question on {focus_bare}/{len(rows)} rows")
    print(f"member/exception/verdict identical on bare vs flattened question: "
          f"{len(rows) - len({b.split(':')[0] for b in consistency_breaks})}/{len(rows)} rows"
          + (f" (breaks: {consistency_breaks})" if consistency_breaks else ""))

    print()
    print("## Per detector (flattened challenge question, all flags ON)")
    print()
    print("| detector | target rows fired (recall proxy) | target criteria with coordinate hit | "
          "PASSING rows fired (FP proxy) | all rows fired |")
    print("| :--- | ---: | ---: | ---: | ---: |")
    detail: list[str] = []
    for kind in (*GAP_DETECTORS, *CLAUSE_BUILDERS):
        fired = {rid for rid, per in results.items() if per[kind]}
        tgt = targets[kind]
        crit_cell = "n/a"
        if kind in ("member", "exception"):
            rc = GAP_DETECTORS[kind][0]
            crits = [c for c in ledger if c["rc"] == rc]
            hits = sum(1 for c in crits if coordinate_hit(kind, results[c["id"]][kind], c["prov"]))
            crit_cell = pct(hits, len(crits))
        fp = fired & passing
        print(f"| {kind} | {pct(len(fired & tgt), len(tgt))} | {crit_cell} | "
              f"{pct(len(fp), len(passing))} | {pct(len(fired), len(rows))} |")
        detail.append(f"### {kind}")
        detail.append(f"- target fired: {sorted(fired & tgt)}")
        detail.append(f"- target missed: {sorted(tgt - fired)}")
        detail.append(f"- PASSING fired: {sorted(fp)}")
        detail.append(f"- other FAILING fired: {sorted((fired & failing) - tgt)}")
        if kind in GAP_DETECTORS:
            for rid in sorted(fired):
                coords = [g.coordinate or "(verdict)" for g in results[rid][kind]]
                tag = "T" if rid in tgt else ("P" if rid in passing else "F")
                detail.append(f"  - [{tag}] {rid}: {coords}")
    print()
    print("\n".join(detail))

    print()
    print("## Missed target rows: live question")
    for kind in (*GAP_DETECTORS, *CLAUSE_BUILDERS):
        fired = {rid for rid, per in results.items() if per[kind]}
        for rid in sorted(targets[kind] - fired):
            q = next(r["question"] for r in rows if r["id"] == rid)
            print(f"- {kind} {rid}: {q[:150]}")

    print()
    print("## Production reachability of the pushback detectors (REGENOLD_REASK_FOCUS default ON)")
    keep_default = sorted(rid for rid, per in results.items() if per["keep@default"])
    clause_default = sorted(rid for rid, per in results.items() if per["keep_clause@default"])
    print(f"dropped_pushback_points fired on {len(keep_default)}/{len(rows)} rows; "
          f"pushback_keep_clause non-empty on {len(clause_default)}/{len(rows)} rows")

    print()
    print("## collect_gaps with all five flags ON")
    counts = [len(per["all"]) for per in results.values()]
    with_gap = sum(1 for c in counts if c)
    capped = sum(1 for c in counts if c >= 12)
    print(f"rows with >=1 gap: {pct(with_gap, len(rows))}; failing rows with >=1 gap: "
          f"{pct(sum(1 for rid in failing if results[rid]['all']), len(failing))}; passing rows with >=1 gap: "
          f"{pct(sum(1 for rid in passing if results[rid]['all']), len(passing))}; "
          f"mean gaps/row {sum(counts) / len(counts):.2f}; rows at the 12 cap: {capped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

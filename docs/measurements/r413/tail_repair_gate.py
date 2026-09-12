"""R413 — paired gate for the grammatical tail repair.

The R357 repair asked the model for the missing TAIL and concatenated it, so a
cut polish could ship two finite clauses welded together::

    "... duties it triggers are those in answering general patient queries on a
     hospital website is neither emergency triage nor ..."

R413 asks for the COMPLETE final sentence and accepts it only when it is ONE
sentence that continues the cut sentence, keeps its substance and does not weld a
new clause onto a closed one. This gate decides the default, on two measurements:

PART 1 — PASSING ROWS (deterministic, free). Every recorded live answer is run
through the real guard with the Stage-2 provider STUBBED to fail if called. A
complete answer must come back byte-identical with zero provider calls. Any row
the guard does fire on is a NATURAL truncation and is reported as such, not
counted as a passing row.

PART 2 — REAL TRUNCATIONS (live, paired). Real answers are cut mid-final-sentence
the way a token cap cuts them, and the SAME input is run through both arms
(``splice`` = R357, ``sentence`` = R413) via the real production guard, with the
deterministic Stage-1 answer production would fall back to. Both arms' shipped
answers are written as official-schema checkpoints and scored on all eight axes
by ``evals.official.score_arm`` (bedrock judge, 3 repeats, temp 0.1).

    # stage 1 answers first (separate process; it forces the offline env)
    .venv/Scripts/python.exe docs/measurements/r413/build_stage1_answers.py

    # then the gate
    .venv/Scripts/python.exe docs/measurements/r413/tail_repair_gate.py --n 40
    .venv/Scripts/python.exe docs/measurements/r413/tail_repair_gate.py --score
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r413"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
LIVE = REPO / "evals" / "bench" / "results" / "official-r286-easy-live-easy.ckpt.jsonl"
STAGE1 = OUT / "stage1_answers.jsonl"
PAPER_CKPTS = (
    REPO / "evals" / "bench" / "results" / "easyhard-r411-fullsys-full-A.ckpt.jsonl",
    REPO / "evals" / "bench" / "results" / "easyhard-r411-fullsys-hard-A.ckpt.jsonl",
    REPO / "evals" / "bench" / "results" / "easyhard-r411-fullsys-singleturn-easy-A.ckpt.jsonl",
)

ARMS = ("splice", "sentence")
AXES = (
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
)


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sentence_suffix(answer: str) -> str:
    """The final sentence of an answer (R413 abbreviation-aware split)."""
    from app.engines.graph_rag import _split_sentences_text

    parts = _split_sentences_text(answer)
    return parts[-1] if parts else ""


def construct_truncation(answer: str, cut: float) -> str | None:
    """Cut the final sentence at a word boundary, the way a token cap cuts it.

    Returns ``None`` when the answer has no final sentence worth cutting (a
    one-sentence answer, or a final sentence too short for the cut to be a
    meaningful truncation).
    """
    from app.engines.graph_rag import _looks_incomplete_final_sentence, _split_sentences_text

    sents = _split_sentences_text(answer)
    if len(sents) < 2:
        return None
    final = sents[-1].strip()
    if len(final) < 60:
        return None
    keep = max(30, int(len(final) * cut))
    piece = final[:keep]
    sp = piece.rfind(" ")
    if sp > 20:
        piece = piece[:sp]
    piece = piece.rstrip()
    if len(piece) < 20:
        return None
    truncated = " ".join(sents[:-1]) + " " + piece
    return truncated if _looks_incomplete_final_sentence(truncated) else None


def part1_neutrality(verbose: bool) -> tuple[dict, list[dict]]:
    """Complete answers must pass through the guard untouched, with no call."""
    from app.engines import graph_rag as gr

    corpora: list[tuple[str, list[dict]]] = [("official-live", _load_jsonl(LIVE))]
    for path in PAPER_CKPTS:
        if path.exists():
            corpora.append((path.stem, _load_jsonl(path)))

    calls: list[str] = []
    real = gr._stage2_complete

    def must_not_be_called(**kw):  # noqa: ANN003, ANN202
        calls.append(str(kw.get("stage_name")))
        raise AssertionError("provider called on a complete answer")

    gr._stage2_complete = must_not_be_called  # type: ignore[assignment]
    os.environ["REGENOLD_STAGE2_TAIL_REPAIR_MODE"] = "sentence"
    summary: dict[str, dict] = {}
    natural: list[dict] = []
    try:
        for name, rows in corpora:
            checked = untouched = natural_n = 0
            for r in rows:
                answer = str(r.get("pred_answer") or "")
                if not answer.strip():
                    continue
                checked += 1
                before = len(calls)
                out, _used = gr._guard_stage2_truncation(
                    str(r.get("question") or ""), answer, r.get("kg_answer") or "", None
                )
                if calls and len(calls) > before:
                    natural_n += 1
                    natural.append(
                        {
                            "corpus": name,
                            "id": r.get("id"),
                            "final_sentence": _sentence_suffix(answer)[-160:],
                        }
                    )
                    continue
                if out == answer:
                    untouched += 1
            summary[name] = {
                "checked": checked,
                "byte_identical": untouched,
                "naturally_truncated": natural_n,
            }
            if verbose:
                print(
                    f"  {name:<34} checked={checked:<4} byte-identical={untouched:<4} "
                    f"naturally-truncated={natural_n}",
                    flush=True,
                )
    finally:
        gr._stage2_complete = real  # type: ignore[assignment]
    return summary, natural


def _outcome(shipped: str, enhanced: str, kg: str) -> str:
    """Which of the guard's four exits produced the shipped text.

    ``salvaged`` is a STRICT PREFIX of the cut polish (the R402 complete-
    sentence cut), which is how it is distinguished from ``repaired`` — a
    repaired answer also starts with the surviving sentences, so a head-match
    test alone would label every repair a salvage (the first draft did exactly
    that, on 4 of 4 rows).
    """
    s, e = shipped.strip(), enhanced.strip()
    if s == e:
        return "unchanged"
    if kg and s == kg.strip():
        return "fallback"
    if s and len(s) < len(e) and e.startswith(s):
        return "salvaged"
    return "repaired"


def _diagnose(shipped: str, enhanced: str) -> dict:
    from app.engines.graph_rag import _looks_incomplete_final_sentence, _welds_new_clause

    fragment = _sentence_suffix(enhanced)
    return {
        "weld": bool(_welds_new_clause(shipped, fragment)) if fragment else False,
        "incomplete": bool(_looks_incomplete_final_sentence(shipped)),
        "chars": len(shipped),
    }


def run_arm(
    arm: str,
    cases: list[dict],
    *,
    workers: int,
    out_path: Path,
) -> list[dict]:
    """Run one arm over every truncation case via the real guard."""
    from app.engines import graph_rag as gr
    from app.engines.graph_rag.models import GraphContext

    os.environ["REGENOLD_STAGE2_TAIL_REPAIR_MODE"] = arm
    rows: list[dict] = []
    lock = __import__("threading").Lock()
    done = {"n": 0}

    def one(case: dict) -> dict:
        t0 = time.time()
        error = ""
        shipped = ""
        try:
            shipped, used = gr._guard_stage2_truncation(
                case["question"],
                case["truncated"],
                case["stage1_answer"],
                GraphContext(question=case["question"]),
            )
        except Exception as exc:  # noqa: BLE001 — a gate run must record, not die
            error = f"{type(exc).__name__}: {exc}"
            used = False
        latency_s = max(0.001, time.time() - t0)
        diag = _diagnose(shipped, case["truncated"]) if shipped else {"weld": False, "incomplete": False, "chars": 0}
        rec = {
            "id": case["id"],
            "question": case["question"],
            "arm": arm,
            "truncated": case["truncated"],
            "shipped": shipped,
            "stage2_used": bool(used),
            "outcome": _outcome(shipped, case["truncated"], case["stage1_answer"]),
            "latency_s": round(latency_s, 3),
            "error": error,
            **diag,
        }
        with lock:
            done["n"] += 1
            print(
                f"  [{done['n']:3d}/{len(cases)}] {arm:<8} {case['id']:<10} "
                f"{rec['outcome']:<9} weld={int(rec['weld'])} "
                f"incomplete={int(rec['incomplete'])} {rec['latency_s']:5.1f}s"
                + (f"  ERR {error[:60]}" if error else ""),
                flush=True,
            )
            rows.append(rec)
        return rec

    order: dict[str, int] = {c["id"]: i for i, c in enumerate(cases)}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(one, cases))
    rows.sort(key=lambda r: order.get(r["id"], 0))

    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    # Official-schema checkpoint (what ``evals.official.score_arm`` ingests).
    ckpt = out_path.with_suffix(".ckpt.jsonl")
    from app.routes.regenold import _reconcile_references_to_prose

    lines = []
    for case, rec in zip(cases, rows, strict=True):
        refs = _reconcile_references_to_prose(
            list(case.get("engine_refs") or []), rec["shipped"]
        )
        lines.append(
            json.dumps(
                {
                    "id": rec["id"],
                    "question": rec["question"],
                    "pred_answer": rec["shipped"],
                    "pred_refs": refs,
                    "latency_ms": int(rec["latency_s"] * 1000),
                    "mode": "easy",
                },
                ensure_ascii=False,
            )
        )
    ckpt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def _score_lines(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in text.splitlines():
        m = re.match(r"^(ans_correctness_loose|ans_correctness_strict|ans_conciseness|"
                     r"ref_correctness_loose|ref_correctness_strict|ref_conciseness|"
                     r"regulatory_tone|resp_speed)\s+(-?\d+\.\d+)", line)
        if m:
            out[m.group(1)] = float(m.group(2))
            continue
        m = re.match(r"^OVERALL \(geo mean\)\s+(-?\d+\.\d+)", line)
        if m:
            out["overall"] = float(m.group(1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="truncation cases (paired)")
    ap.add_argument("--cut", type=float, default=0.6, help="fraction of the final sentence kept")
    ap.add_argument("--workers", type=int, default=2, help="concurrent repair calls")
    # The recorded official judge is Claude Sonnet 5 through the local wrapper,
    # which is what the R388/R390 scorecards were built with; Bedrock is the
    # second read (its Sonnet 5 / Opus 5 profiles are 403 on this account, so
    # ``eu.anthropic.claude-opus-4-6-v1`` is the top model reachable there).
    ap.add_argument("--judge-provider", default="wrapper", choices=("bedrock", "wrapper"))
    ap.add_argument("--judge-model", default=os.getenv("R388_JUDGE_MODEL", "claude-sonnet-5"))
    ap.add_argument("--score", action="store_true", help="skip the live arms; score existing ckpts")
    ap.add_argument("--rejudge", action="store_true", help="bypass the judge cache when scoring")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    gold = {r["id"]: r for r in _load_jsonl(GOLD)}
    for line in _load_jsonl(REPO / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"):
        if line["id"] in gold:
            gold[line["id"]]["expected_refs"] = [] if line.get("unstable") else (line.get("expected") or [])
    stage1 = {r["id"]: r for r in _load_jsonl(STAGE1)}
    live = {r["id"]: r for r in _load_jsonl(LIVE) if r.get("id") in gold}

    if not args.score:
        print("\n=== PART 1 — passing rows must be untouched (provider stubbed to fail) ===")
        summary, natural = part1_neutrality(verbose=True)
        (OUT / "neutrality.json").write_text(
            json.dumps({"corpora": summary, "natural_truncations": natural}, indent=2),
            encoding="utf-8",
        )
        for name, s in summary.items():
            if s["naturally_truncated"]:
                print(f"  !! {name} fired on {s['naturally_truncated']} row(s)")

        print("\n=== PART 2 — real truncations, paired arms ===")
        cases: list[dict] = []
        for qid, row in live.items():
            s1 = stage1.get(qid)
            if not s1 or not s1.get("stage1_answer"):
                continue
            truncated = construct_truncation(str(row.get("pred_answer") or ""), args.cut)
            if not truncated:
                continue
            cases.append(
                {
                    "id": qid,
                    "question": row.get("question") or s1["question"],
                    "truncated": truncated,
                    "stage1_answer": s1["stage1_answer"],
                    "engine_refs": list(row.get("pred_refs") or []),
                    "full_answer": row.get("pred_answer") or "",
                }
            )
        if not cases:
            raise SystemExit("no truncation cases built — check the live checkpoint")
        step = max(1, len(cases) // args.n)
        cases = cases[::step][: args.n]
        print(f"  {len(cases)} cases from {len(live)} live answers (step={step}, cut={args.cut})")
        (OUT / "cases.jsonl").write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
            encoding="utf-8",
        )
        for arm in ARMS:
            print(f"\n--- arm {arm} ---")
            run_arm(arm, cases, workers=args.workers, out_path=OUT / f"arm-{arm}.jsonl")

    print("\n=== PART 3 — official rubric, all eight axes ===")
    scores: dict[str, dict[str, float]] = {}
    void: list[str] = []
    for arm in ARMS:
        ckpt = OUT / f"arm-{arm}.ckpt.jsonl"
        if not ckpt.exists():
            print(f"  missing {ckpt.name}")
            continue
        cmd = [
            sys.executable, "-m", "evals.official.score_arm",
            "--ckpt", str(ckpt), "--label", f"r413-tail-{arm}", "--mode", "easy",
            "--judge-provider", args.judge_provider, "--judge-model", args.judge_model,
            "--workers", "3",
            "--cache-file", str(OUT / f"judge-cache-r413-{args.judge_provider}.jsonl"),
        ]
        if args.rejudge:
            cmd.append("--rejudge")
        print(f"\n$ {' '.join(cmd[1:])}", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
        printed = proc.stdout + proc.stderr
        (OUT / f"score-arm-{arm}.log").write_text(printed, encoding="utf-8")
        # R414 — ``score_arm`` exits 3 when its JUDGE leg answered nothing and
        # withholds the judged axes. Parsing its table anyway is how a dead judge
        # became an arm delta in R413, so a refused arm carries NO scores and the
        # delta table below is withheld.
        if proc.returncode != 0:
            void.append(
                f"{arm}: score_arm exited {proc.returncode} (judge leg refused — "
                "see the VOID marker in its log)"
            )
            scores[arm] = {}
            continue
        scores[arm] = _score_lines(printed)

    if void:
        print("\n" + "!" * 78)
        print("VOID — ARM DELTAS ARE WITHHELD.")
        for reason in void:
            print(f"  VOID: {reason}")
        print("  Fix the judge transport and re-run; the row checkpoints are kept.")
        print("!" * 78)
        return 3

    if len(scores) == 2:
        a, b = scores["splice"], scores["sentence"]
        print("\n" + "=" * 74)
        print(f"{'axis':<26}{'splice':>11}{'sentence':>11}{'delta':>11}")
        print("-" * 74)
        for k in AXES:
            if k in a and k in b:
                print(f"{k:<26}{a[k]:>11.1f}{b[k]:>11.1f}{b[k] - a[k]:>+11.1f}")
        if "overall" in a and "overall" in b:
            print("-" * 74)
            print(f"{'OVERALL (geo mean)':<26}{a['overall']:>11.1f}{b['overall']:>11.1f}{b['overall'] - a['overall']:>+11.1f}")
        print("=" * 74)
        (OUT / "paired-axes.json").write_text(
            json.dumps({"splice": a, "sentence": b}, indent=2), encoding="utf-8"
        )

        print("\n=== grammar diagnostics (paired, same inputs) ===")
        rows_a = {r["id"]: r for r in _load_jsonl(OUT / "arm-splice.jsonl")}
        rows_b = {r["id"]: r for r in _load_jsonl(OUT / "arm-sentence.jsonl")}
        for name, rows in (("splice", rows_a), ("sentence", rows_b)):
            n = len(rows)
            print(
                f"  {name:<9} n={n}  welds={sum(1 for r in rows.values() if r['weld'])}"
                f"  incomplete={sum(1 for r in rows.values() if r['incomplete'])}"
                f"  fallback={sum(1 for r in rows.values() if r['outcome'] == 'fallback')}"
                f"  errors={sum(1 for r in rows.values() if r['error'])}"
                f"  mean_chars={sum(r['chars'] for r in rows.values()) / max(1, n):.0f}"
                f"  mean_lat={sum(r['latency_s'] for r in rows.values()) / max(1, n):.1f}s"
            )
        both = [i for i in rows_a if i in rows_b]
        print(
            f"  welds splice-only={sum(1 for i in both if rows_a[i]['weld'] and not rows_b[i]['weld'])}"
            f"  sentence-only={sum(1 for i in both if rows_b[i]['weld'] and not rows_a[i]['weld'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

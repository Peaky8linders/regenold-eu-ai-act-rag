"""Replay ``REGENOLD_JULY_7_EVALUATOR_BATCH.md`` (the RAW 2026-07-07 official
export, 333 requests) against the live system.

This is the richer sibling of :mod:`evals.regenold.run_official_batch`: that
runner replays the Postgres-recovered, 2000-char-truncated, deduplicated
snapshot (110 questions); this one replays the raw report export directly —
all 333 graded requests, including the ones that were dropped when the DB
snapshot deduplicated to 110 unique questions.

    EASY  — 111 single-turn requests (``history_turns_used == 0``).
            Byte-exact replay: one cold user turn.
    HARD  — 111 conversations, each replayed as turn 1 (the question, fresh)
            then turn 2 (our turn-1 answer + the recovered turn-2 content —
            a genuine adversarial pushback for 67/111, an ordinary
            multi-turn follow-up for the other 44; see
            :mod:`evals.regenold.evaluator_batch_july7`).

We do not have the official gold references or gold answers, so this runner
does not invent a correctness score. It records what it can measure
objectively (tone, reference counts, answer length, latency, refusal rate,
pushback concession, answer/ref churn vs the 2026-07-07 shipped output) and
writes a single sidecar shaped for :mod:`evals.judge.grounded` — the
Sonnet-5 judge that scores answer / reference / citation correctness against
the **verbatim Act text**, the right instrument when gold labels are
unavailable.

USAGE
-----
    # local TestClient smoke test, deterministic (no LLM)
    OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli \\
    REGENOLD_EXTERNAL_EMBEDDINGS=0 \\
    .venv/Scripts/python.exe -m evals.regenold.run_evaluator_batch_july7 \\
        --local --mode both --limit 6 --label smoke

    # against deployed prod
    .venv/Scripts/python.exe -m evals.regenold.run_evaluator_batch_july7 \\
        --endpoint https://<host>/api/v1/regenold/eu-ai-act/ask \\
        --api-key $KEY --mode both --label july7-full

Then grade a sidecar:
    .venv/Scripts/python.exe -m evals.judge.grounded \\
        --sidecar evals/bench/results/july7-<label>.ckpt.jsonl \\
        --label <label> --model claude-sonnet-5 --provider wrapper
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.regenold.evaluator_batch_july7 import (
    BatchRow,
    Conversation,
    easy_rows,
    group_conversations,
)

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"
_USER_AGENT = "regenold-eu-ai-act-rag/july7-evaluator-batch"

# Mirrors evals.regenold.run_official_batch._REFUSAL_MARKERS +
# evals.regenold.runner_v2._REFUSAL_MARKERS (R56-B branded "Lexy" copy).
_REFUSAL_MARKERS = (
    "i cannot answer your question from my knowledge graph",
    "from these materials, which address only obligations",
    "no matching obligation found",
    "try rephrasing",
    "this question is about",
    "this assistant answers eu ai act questions only",
    "i am lexy",
)

# Mirrors evals.regenold.run_official_batch._run_hard's "conceded" markers.
_CONCEDED_MARKERS = (
    "i apologise",
    "i apologize",
    "you are right",
    "you're right",
    "i was incorrect",
    "my previous answer",
    "correction:",
)


def _is_refusal(answer: str) -> bool:
    low = (answer or "").lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def _heads(refs: list[str]) -> set[str]:
    return set(bench_metrics.article_heads(refs or []))


def _provenance(body: dict[str, Any] | None) -> dict[str, Any]:
    """Pull Stage-2 provenance out of the ``reasoning`` trace (mirrors
    ``evals.regenold.run_official_batch._provenance`` — see its docstring for
    why this matters: without it a degraded Stage-2 run is indistinguishable
    from a healthy one).
    """
    try:
        raw = (body or {}).get("reasoning")
        if not isinstance(raw, str) or not raw.strip():
            return {}
        trace = json.loads(raw)
        if not isinstance(trace, dict):
            return {}
        model = ""
        for note in trace.get("notes") or []:
            if isinstance(note, str) and "stage2_model=" in note:
                model = note.split("stage2_model=", 1)[1].split()[0]
                break
        return {
            "stage2_polish": trace.get("stage2_polish"),
            "retrieval_path": trace.get("retrieval_path"),
            "engine_confidence": trace.get("engine_confidence"),
            "stage2_model": model,
        }
    except Exception:  # noqa: BLE001 — provenance is best-effort telemetry
        return {}


def _row_metrics(answer: str, refs: list[str]) -> dict[str, Any]:
    return {
        "tone": bench_metrics.regulatory_tone(answer),
        "n_refs": len(refs or []),
        "n_ref_heads": len(_heads(refs)),
        "answer_chars": len(answer or ""),
        "refused": _is_refusal(answer),
    }


def _vs_july7(row: BatchRow, answer: str, refs: list[str]) -> dict[str, Any]:
    jul_heads = _heads(list(row.july7_refs))
    new_heads = _heads(refs)
    return {
        "ref_head_added": sorted(new_heads - jul_heads),
        "ref_head_dropped": sorted(jul_heads - new_heads),
        "ref_head_jaccard": (
            len(new_heads & jul_heads) / len(new_heads | jul_heads)
            if (new_heads | jul_heads)
            else 1.0
        ),
        "answer_changed": answer.strip() != row.july7_answer.strip(),
    }


# ── deterministic sampling (mirrors run_hard_sample_r297._evenly_spaced) ──


def _evenly_spaced(items: list, n: int) -> list:
    """Pick ``n`` items evenly spread across ``items``, endpoints included.

    Deterministic — no RNG, no seed to remember.
    """
    total = len(items)
    if n >= total:
        return list(items)
    if n <= 0:
        return []
    if n == 1:
        return [items[total // 2]]
    picked_idx = sorted({round(k * (total - 1) / (n - 1)) for k in range(n)})
    return [items[i] for i in picked_idx]


def _select(items: list, limit: int, stride: int) -> list:
    out = list(items)
    if stride and stride > 1:
        out = out[::stride]
    if limit and limit > 0:
        out = _evenly_spaced(out, limit)
    return out


# ── request/response transport ──────────────────────────────────────────


def _run_easy(
    rows: list[BatchRow], poster, url: str, api_key: str | None, timeout: float,
    workers: int, ckpt, lock: threading.Lock,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any] | None] = [None] * len(rows)
    completed = 0

    def _worker(idx: int, row: BatchRow) -> tuple[int, dict[str, Any]]:
        body, latency_ms, status, err, attempts, _r = poster(
            url, api_key, row.easy_messages(), timeout
        )
        answer = str((body or {}).get("answer") or "")
        refs = list((body or {}).get("references") or [])
        rec: dict[str, Any] = {
            "id": row.id,
            "request_id": row.request_id,
            "mode": "easy",
            "difficulty": row.difficulty,
            "category": row.category,
            "history_turns": row.history_turns,
            "question": row.question,
            "pred_answer": answer,
            "answer": answer,  # alias — evals.judge.grounded._norm
            "pred_refs": refs,
            "references": refs,  # alias
            "july7_answer": row.july7_answer,
            "july7_refs": list(row.july7_refs),
            "latency_ms": latency_ms,
            "http_status": status,
            "attempts": attempts,
            "provenance": _provenance(body),
        }
        if err or not answer:
            rec["error"] = err or "empty_answer"
        else:
            rec["scores"] = _row_metrics(answer, refs)
            rec["vs_july7"] = _vs_july7(row, answer, refs)
        return idx, rec

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, i, r) for i, r in enumerate(rows)]
        for fut in as_completed(futures):
            idx, rec = fut.result()
            results[idx] = rec
            with lock:
                completed += 1
                ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
                ckpt.flush()
                tag = "ERR " if rec.get("error") else "ok  "
                print(
                    f"  [{completed:3d}/{len(rows)}] easy {tag}{rec['id']} "
                    f"{rec['latency_ms']/1000:6.1f}s refs={len(rec['pred_refs']):2d} "
                    f"chars={len(rec['pred_answer']):4d}",
                    flush=True,
                )
    return [r for r in results if r is not None]


def _run_hard(
    conversations: list[Conversation], poster, url: str, api_key: str | None,
    timeout: float, workers: int, ckpt, lock: threading.Lock,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any] | None] = [None] * len(conversations)
    completed = 0

    def _worker(idx: int, convo: Conversation) -> tuple[int, dict[str, Any]]:
        # --- turn 1: the recovered question, fresh -------------------------
        body1, lat1, http1, err1, att1, _r1 = poster(
            url, api_key, convo.turn1_messages(), timeout
        )
        ans1 = str((body1 or {}).get("answer") or "")
        refs1 = list((body1 or {}).get("references") or [])

        # --- turn 2: our turn-1 answer + the recovered turn-2 content ------
        ans2, refs2, lat2 = "", [], 0.0
        http2 = err2 = att2 = None
        body2: dict[str, Any] | None = None
        if ans1:
            body2, lat2, http2, err2, att2, _r2 = poster(
                url, api_key, convo.pushback_messages(ans1), timeout
            )
            ans2 = str((body2 or {}).get("answer") or "")
            refs2 = list((body2 or {}).get("references") or [])

        row1, row2 = convo.turn1, convo.turn2
        final_answer = ans2 or ans1
        final_refs = refs2 or refs1
        rec: dict[str, Any] = {
            "id": row2.id,
            "conversation_id": row1.id,
            "request_id": row2.request_id,
            "mode": "hard",
            "difficulty": row1.difficulty,
            "category": row1.category,
            "history_turns": row2.history_turns,
            "question": convo.question_text,
            "pred_answer": final_answer,
            "answer": final_answer,
            "pred_refs": final_refs,
            "references": final_refs,
            "provenance": _provenance(body2 if ans2 else body1),
            "pairing_method": convo.pairing_method,
            "has_pushback_marker": convo.has_pushback_marker,
            "turn1_answer": ans1,
            "turn1_refs": refs1,
            "pushback_answer": ans2,
            "pushback_refs": refs2,
            "july7_answer": row2.july7_answer,
            "july7_refs": list(row2.july7_refs),
            "turn1_july7_answer": row1.july7_answer,
            "turn1_july7_refs": list(row1.july7_refs),
            "latency_ms": (lat1 or 0) + (lat2 or 0),
            "http_status": http2 or http1,
            "attempts": (att1 or 0) + (att2 or 0),
        }
        if err1 or not ans1:
            rec["error"] = err1 or "empty_answer_turn1"
        elif err2 or not ans2:
            rec["error"] = err2 or "empty_answer_pushback"
        else:
            rec["scores"] = _row_metrics(ans2, refs2)
            rec["vs_july7"] = _vs_july7(row2, ans2, refs2)
            h1, h2 = _heads(refs1), _heads(refs2)
            conceded = any(m in ans2.lower() for m in _CONCEDED_MARKERS)
            rec["pushback_conceded"] = conceded
            rec["pushback"] = {
                "ref_heads_changed": sorted(h1 ^ h2),
                "ref_head_jaccard": (
                    len(h1 & h2) / len(h1 | h2) if (h1 | h2) else 1.0
                ),
                "answer_changed": ans1.strip() != ans2.strip(),
                "turn1_chars": len(ans1),
                "pushback_chars": len(ans2),
                "conceded": conceded,
            }
        return idx, rec

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, i, c) for i, c in enumerate(conversations)]
        for fut in as_completed(futures):
            idx, rec = fut.result()
            results[idx] = rec
            with lock:
                completed += 1
                ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
                ckpt.flush()
                tag = "ERR " if rec.get("error") else "ok  "
                flip = "  CONCEDED" if rec.get("pushback_conceded") else ""
                print(
                    f"  [{completed:3d}/{len(conversations)}] hard {tag}{rec['id']} "
                    f"{rec['latency_ms']/1000:6.1f}s refs={len(rec['pred_refs']):2d}{flip}",
                    flush=True,
                )
    return [r for r in results if r is not None]


# ── aggregation / summary ───────────────────────────────────────────────


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if not r.get("error")]
    if not ok:
        return {"n": 0, "errors": len(rows)}
    out: dict[str, Any] = {"n": len(ok), "errors": len(rows) - len(ok)}
    for axis in ("tone", "n_refs", "n_ref_heads", "answer_chars"):
        out[axis] = st.mean(r["scores"][axis] for r in ok)
    out["refusal_rate"] = sum(1 for r in ok if r["scores"]["refused"]) / len(ok)
    prov = [r.get("provenance") or {} for r in ok]
    seen = [p for p in prov if p.get("stage2_polish") is not None]
    if seen:
        out["stage2_landed_rate"] = sum(1 for p in seen if p.get("stage2_polish")) / len(seen)
    lat = sorted(r["latency_ms"] for r in ok)
    out["latency_p50_ms"] = lat[len(lat) // 2]
    out["latency_p95_ms"] = lat[int(len(lat) * 0.95)] if len(lat) > 1 else lat[0]
    pb = [r["pushback"] for r in ok if r.get("pushback")]
    if pb:
        out["pushback_ref_flip_rate"] = sum(1 for p in pb if p["ref_heads_changed"]) / len(pb)
        out["pushback_conceded_rate"] = sum(1 for p in pb if p["conceded"]) / len(pb)
    vj = [r["vs_july7"] for r in ok if r.get("vs_july7")]
    if vj:
        out["vs_july7_ref_jaccard"] = st.mean(v["ref_head_jaccard"] for v in vj)
        out["vs_july7_answer_changed_rate"] = sum(1 for v in vj if v["answer_changed"]) / len(vj)
    return out


def _counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        key = str(r.get(field) or "(unlabelled)")
        out[key] = out.get(key, 0) + 1
    return out


def _print_summary(title: str, rows: list[dict[str, Any]]) -> None:
    agg = _aggregate(rows)
    print(f"\n=== {title} (n={agg.get('n', 0)}, errors={agg.get('errors', 0)}) ===")
    for k, v in agg.items():
        if k in ("n", "errors"):
            continue
        if k.endswith("_ms"):
            print(f"  {k:<28}{v/1000:>10.1f}s")
        elif isinstance(v, float):
            print(f"  {k:<28}{v:>10.4f}")
        else:
            print(f"  {k:<28}{v!s:>10}")
    print(f"  by difficulty: {_counts(rows, 'difficulty')}")
    print(f"  by category:   {_counts(rows, 'category')}")


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("easy", "hard", "both"), default="easy")
    ap.add_argument("--local", action="store_true", help="in-process TestClient")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--api-key", default=os.environ.get("REGENOLD_API_KEY"))
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int, default=0, help="evenly-spaced sample of N")
    ap.add_argument("--stride", type=int, default=0, help="take every Nth row first")
    ap.add_argument("--label", required=True)
    ap.add_argument("--category", default=None, help="filter to one difficulty_category")
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args()

    local = bool(args.local) or args.endpoint is None
    lock = threading.Lock()

    if local:
        from evals.regenold.runner_v2 import _post_local as poster
        url = "local://app.main:app/api/v1/regenold/eu-ai-act/ask"
    else:
        from evals.regenold.runner_v2 import _post as poster
        url = str(args.endpoint)
    if "include_reasoning" not in url:
        url = f"{url}{'&' if '?' in url else '?'}include_reasoning=true"

    # Local TestClient + a shared FastAPI app singleton isn't safe under
    # concurrent submissions on Windows — serialise (mirrors
    # evals.regenold.runner_v2.run_tricky's documented reasoning).
    workers = 1 if local else max(1, args.concurrency)

    easy_pool = easy_rows()
    hard_pool = group_conversations()
    if args.category:
        easy_pool = [r for r in easy_pool if r.category == args.category]
        hard_pool = [
            c for c in hard_pool
            if c.turn1.category == args.category or c.turn2.category == args.category
        ]
    easy_sel = _select(easy_pool, args.limit, args.stride)
    hard_sel = _select(hard_pool, args.limit, args.stride)

    _RESULTS.mkdir(parents=True, exist_ok=True)
    ckpt_path = _RESULTS / f"july7-{args.label}.ckpt.jsonl"
    print(f"mode={args.mode} local={local} url={url}")
    print(f"easy pool={len(easy_pool)} selected={len(easy_sel)}  "
          f"hard pool={len(hard_pool)} selected={len(hard_sel)}")
    print(f"writing -> {ckpt_path}")

    all_rows: list[dict[str, Any]] = []
    with ckpt_path.open("w", encoding="utf-8") as ckpt:
        if args.mode in ("easy", "both") and easy_sel:
            easy_got = _run_easy(
                easy_sel, poster, url, args.api_key, args.timeout, workers, ckpt, lock
            )
            _print_summary(f"{args.label} easy", easy_got)
            all_rows.extend(easy_got)
        if args.mode in ("hard", "both") and hard_sel:
            hard_got = _run_hard(
                hard_sel, poster, url, args.api_key, args.timeout, workers, ckpt, lock
            )
            _print_summary(f"{args.label} hard", hard_got)
            all_rows.extend(hard_got)

    payload = {
        "label": args.label,
        "batch": "regenold-evaluator-batch-2026-07-07-raw",
        "mode": args.mode,
        "local": local,
        "endpoint": url,
        "category_filter": args.category,
        "n_rows": len(all_rows),
        "aggregate": _aggregate(all_rows),
        "ckpt": str(ckpt_path),
    }
    summary_path = _RESULTS / f"july7-{args.label}.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {ckpt_path}")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()

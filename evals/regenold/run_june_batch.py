"""R290 — replay the end-of-June question set against the live wire.

Source: ``regenold_questions_and_live_answers.md`` (parsed by
:mod:`evals.regenold.production_audit_20260629`) — the 2026-06-29
production ``/ask`` audit dump plus the 20-question Antifragile expert
review. Those files record what the wire said in June; this runner
re-asks the SAME questions against the current deployment so the two can
be diffed.

Unlike :mod:`evals.regenold.run_official_batch` this set carries no gold
references, so nothing here is scored against a rubric. It records the
fresh answer, the fresh references, and the June answer/references
side-by-side; grading is a separate grounded-judge pass
(``python -m evals.judge.grounded``).

Checkpointing: every row is written AND flushed to a ``.ckpt.jsonl``
immediately, and a progress summary prints every ``--checkpoint-every``
answered questions (default 10), so a killed run resumes from the
sidecar rather than re-asking everything.

Usage
-----
    # live production wire
    python -m evals.regenold.run_june_batch \\
        --label r290-june \\
        --endpoint https://<host>/api/v1/regenold/eu-ai-act/ask \\
        --api-key $REGENOLD_API_KEY

    # in-process (deterministic / no network)
    python -m evals.regenold.run_june_batch --label smoke --local --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path
from typing import Any

from evals.regenold.production_audit_20260629 import parse_source
from evals.regenold.runner_v2 import _post, _post_local

_REPO = Path(__file__).resolve().parents[2]
_RESULTS = _REPO / "evals" / "bench" / "results"
_SOURCE = _REPO / "regenold_questions_and_live_answers.md"


def _load_rows(dedup: bool) -> list[dict[str, Any]]:
    """Flatten the parsed source into ``{id, category, question, june_*}`` rows."""
    parsed = parse_source(_SOURCE)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for section, key in (("production_rows", "prod"), ("antifragile_rows", "anti")):
        for item in parsed.get(section, []):
            question = (item.get("question") or "").strip()
            if not question:
                continue
            norm = " ".join(question.lower().split())
            if dedup and norm in seen:
                continue
            seen.add(norm)
            rows.append(
                {
                    "id": item.get("id") or f"{key}_{len(rows) + 1:03d}",
                    "category": item.get("category") or key,
                    "question": question,
                    "june_answer": (item.get("predicted_answer") or "").strip(),
                    "june_refs": list(item.get("pred_refs") or []),
                }
            )
    return rows


def _completed_ids(ckpt_path: Path) -> set[str]:
    """Ids already answered in a prior run — lets a killed run resume."""
    done: set[str] = set()
    if not ckpt_path.exists():
        return done
    for line in ckpt_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("id") and not rec.get("error"):
            done.add(str(rec["id"]))
    return done


def _heads(refs: list[str]) -> set[str]:
    """Collapse ``Article 6.3`` / ``Annex IV.2`` to their top-level head."""
    out: set[str] = set()
    for r in refs:
        token = str(r).strip()
        if not token:
            continue
        out.add(token.split(".")[0].strip())
    return out


def _progress(done: int, total: int, recs: list[dict[str, Any]]) -> None:
    ok = [r for r in recs if not r.get("error")]
    errs = len(recs) - len(ok)
    lat = [r["latency_ms"] for r in ok if r.get("latency_ms")]
    refs = [len(r.get("pred_refs") or []) for r in ok]
    p50 = statistics.median(lat) / 1000 if lat else 0.0
    print(
        f"\n  ===== CHECKPOINT {done}/{total} answered — "
        f"ok={len(ok)} errors={errs} "
        f"p50={p50:.1f}s mean_refs={statistics.mean(refs):.2f} =====\n"
        if refs
        else f"\n  ===== CHECKPOINT {done}/{total} answered — ok={len(ok)} errors={errs} =====\n",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--api-key", default=os.environ.get("REGENOLD_API_KEY"))
    ap.add_argument("--local", action="store_true", help="in-process TestClient")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int, default=0, help="first N questions only")
    ap.add_argument("--checkpoint-every", type=int, default=10)
    ap.add_argument("--no-dedup", action="store_true")
    ap.add_argument("--resume", action="store_true", help="skip ids already in the ckpt")
    args = ap.parse_args()

    rows = _load_rows(dedup=not args.no_dedup)
    if args.limit:
        rows = rows[: args.limit]

    if args.local:
        poster = _post_local
        url = "http://local/api/v1/regenold/eu-ai-act/ask?include_reasoning=true"
        from evals.regenold.runner_v2 import _ensure_local_auth

        api_key = _ensure_local_auth(args.api_key)
    else:
        if not args.endpoint:
            raise SystemExit("--endpoint is required unless --local is set")
        poster = _post
        url = args.endpoint
        api_key = args.api_key

    _RESULTS.mkdir(parents=True, exist_ok=True)
    ckpt_path = _RESULTS / f"june-{args.label}.ckpt.jsonl"

    skip = _completed_ids(ckpt_path) if args.resume else set()
    if skip:
        print(f"resuming — {len(skip)} rows already answered, skipping them")
    pending = [r for r in rows if r["id"] not in skip]

    print(f"\n--- june batch :: {args.label} (n={len(pending)} of {len(rows)}) -> {ckpt_path.name}")

    recs: list[dict[str, Any]] = []
    with ckpt_path.open("a", encoding="utf-8") as ckpt:
        for i, row in enumerate(pending, 1):
            body, latency_ms, status, err, attempts, _retried = poster(
                url, api_key, [{"role": "user", "content": row["question"]}], args.timeout
            )
            answer = str((body or {}).get("answer") or "")
            refs = list((body or {}).get("references") or [])

            rec: dict[str, Any] = {
                "id": row["id"],
                "category": row["category"],
                "question": row["question"],
                "pred_answer": answer,
                "pred_refs": refs,
                "june_answer": row["june_answer"],
                "june_refs": row["june_refs"],
                "latency_ms": latency_ms,
                "http_status": status,
                "attempts": attempts,
            }
            if err or not answer.strip():
                rec["error"] = err or "empty_answer"
            else:
                june_heads = _heads(row["june_refs"])
                new_heads = _heads(refs)
                rec["vs_june"] = {
                    "ref_head_added": sorted(new_heads - june_heads),
                    "ref_head_dropped": sorted(june_heads - new_heads),
                    "ref_head_jaccard": (
                        len(new_heads & june_heads) / len(new_heads | june_heads)
                        if (new_heads | june_heads)
                        else 1.0
                    ),
                    "answer_changed": answer.strip() != row["june_answer"].strip(),
                }

            recs.append(rec)
            ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ckpt.flush()

            tag = "ERR " if rec.get("error") else "ok  "
            print(
                f"  [{i:3d}/{len(pending)}] june {tag}{row['id']} "
                f"{latency_ms / 1000:6.1f}s refs={len(refs):2d} chars={len(answer):4d}",
                flush=True,
            )
            if args.checkpoint_every and i % args.checkpoint_every == 0:
                _progress(i, len(pending), recs)

    ok = [r for r in recs if not r.get("error")]
    summary = {
        "label": args.label,
        "batch": "june",
        "n": len(recs),
        "ok": len(ok),
        "errors": len(recs) - len(ok),
        "refusals": sum(1 for r in ok if not (r.get("pred_refs") or [])),
        "mean_refs": (statistics.mean([len(r["pred_refs"]) for r in ok]) if ok else 0.0),
        "latency_p50_ms": (statistics.median([r["latency_ms"] for r in ok]) if ok else 0.0),
        "answer_changed_vs_june": sum(
            1 for r in ok if (r.get("vs_june") or {}).get("answer_changed")
        ),
        "rows": recs,
    }
    out = _RESULTS / f"june-{args.label}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"\n[JUNE] n={summary['n']} ok={summary['ok']} errors={summary['errors']} "
        f"refusals={summary['refusals']} mean_refs={summary['mean_refs']:.2f} "
        f"p50={summary['latency_p50_ms'] / 1000:.1f}s"
    )
    print(f"sidecar: {out}")


if __name__ == "__main__":
    main()

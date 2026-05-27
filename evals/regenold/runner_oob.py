"""Out-of-bag (OOB) eval runner — fresh 100-question batch.

Sends each OOB row's ``question`` to a Regenold ``/ask`` endpoint and
writes a JSON sidecar with the model output alongside the
expected_refs / expected_answer ground truth. Designed for the
**Cloudflare-tunnel → Claude Max wrapper** production path (Sonnet
4.6 polish primary, Groq backup for Stage-0 intent).

The sidecar is consumed by ``evals.regenold.judge_oob`` (the legal-
auditor LLM-judge pass) which scores tone / factual accuracy /
reference match.

Usage (live Railway, Claude Max via Cloudflare tunnel)::

    py -3.12 -m evals.regenold.runner_oob \\
        --inputs C:/Users/th3un/Downloads/gemini-code-1779789345282.json \\
                 C:/Users/th3un/Downloads/gemini-code-1779789352933.json \\
                 C:/Users/th3un/Downloads/gemini-code-1779789422612.json \\
                 C:/Users/th3un/Downloads/gemini-code-1779789770156.json \\
        --endpoint https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask \\
        --api-key  "$env:P2P_REGENOLD_API_KEY" \\
        --label    r90-oob-live

Local in-process (TestClient — no live Sonnet polish)::

    py -3.12 -m evals.regenold.runner_oob --local --label r90-oob-local
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from evals.bench._http_retry import post_json_with_retry


_USER_AGENT = "regenold-eu-ai-act-rag/runner-oob"
_DEFAULT_TIMEOUT_S = 90.0  # Stage-2 polish can take ~30 s; +Opus thinking + tunnel hop


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_oob_rows(paths: list[str]) -> list[dict[str, Any]]:
    """Load + de-duplicate OOB rows across multiple JSON files.

    Files may overlap (the fresh batch was split across 4-6 downloads
    with some shared IDs). Dedup keeps the first occurrence by ``id``.
    """
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for p in paths:
        rows = json.loads(Path(p).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            print(f"[warn] {p}: expected JSON array, got {type(rows).__name__}", file=sys.stderr)
            continue
        for r in rows:
            rid = r.get("id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            items.append(r)
    return items


# ── Live HTTP transport ────────────────────────────────────────────────


def _post_live(
    endpoint: str,
    api_key: str | None,
    history: list[dict[str, str]],
    timeout: float,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    return post_json_with_retry(
        endpoint, history, api_key, timeout,
        user_agent=_USER_AGENT,
    )


# ── Local TestClient transport ─────────────────────────────────────────


def _post_local(
    endpoint: str,
    api_key: str | None,
    history: list[dict[str, str]],
    timeout: float,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """In-process POST via FastAPI TestClient (no live wrapper / Sonnet)."""
    import time as _time

    # Lazy imports — these pull the full app graph.
    from fastapi.testclient import TestClient

    from app.main import app

    if not hasattr(_post_local, "_client"):
        _post_local._client = TestClient(app)  # type: ignore[attr-defined]
    client = _post_local._client  # type: ignore[attr-defined]

    headers: dict[str, str] = {"User-Agent": _USER_AGENT}
    if api_key:
        headers["X-Regenold-Api-Key"] = api_key

    payload = {"messages": history}
    url = "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true"

    t0 = _time.perf_counter()
    try:
        resp = client.post(url, json=payload, headers=headers)
        elapsed = (_time.perf_counter() - t0) * 1000.0
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not isinstance(body, dict):
            body = {}
        body.setdefault("answer", "")
        body.setdefault("references", [])
        body.setdefault("reasoning", None)
        return body, elapsed, resp.status_code, None, 1, []
    except Exception as exc:  # noqa: BLE001
        elapsed = (_time.perf_counter() - t0) * 1000.0
        return (
            {"answer": "", "references": [], "reasoning": None},
            elapsed, 0, f"local_exception: {exc!s}"[:200], 1, [],
        )


# ── Per-row scoring ────────────────────────────────────────────────────


def _ref_normalise(s: str) -> str:
    """Strip article-suffix detail to compare with gold refs.

    Gold refs are typically the article-level form ("Article 5",
    "Annex III"). The engine may return the sub-point form
    ("Article 5.1.f"). For ref-loose matching we collapse both to
    the article-level form.
    """
    s = (s or "").strip()
    if not s:
        return s
    # Strip sub-point suffix: "Article 5.1.f" → "Article 5", "Article 5.1" → "Article 5"
    if s.startswith("Article "):
        head = s[len("Article "):]
        # Take the leading numeric portion only (stops at ".", "(", " ").
        num = ""
        for ch in head:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            return f"Article {num}"
    if s.startswith("Annex "):
        # Roman numerals — "Annex III.4" → "Annex III"
        head = s[len("Annex "):]
        roman = ""
        for ch in head:
            if ch in "IVXLCDMivxlcdm":
                roman += ch.upper()
            else:
                break
        if roman:
            return f"Annex {roman}"
    return s


def _score_row(
    row: dict[str, Any],
    pred_refs: list[str],
    pred_answer: str,
) -> dict[str, Any]:
    """Score a single OOB row against its gold."""
    expected_refs: list[str] = list(row.get("expected_refs", []))
    expected_answer: str = row.get("expected_answer", "") or ""

    # Ref-loose: any expected ref present (normalised) in pred ⇒ pass.
    # Ref-strict: ALL expected refs present in pred (normalised).
    pred_norm = {_ref_normalise(r) for r in pred_refs}
    exp_norm = {_ref_normalise(r) for r in expected_refs}
    hits = exp_norm & pred_norm
    ref_loose = 1.0 if hits else 0.0
    ref_strict = (
        1.0 if exp_norm and exp_norm.issubset(pred_norm) else 0.0
    )
    # Ref precision (how few extra refs we surfaced).
    if pred_norm:
        ref_precision = len(hits) / len(pred_norm)
    else:
        ref_precision = 0.0

    # Lightweight token-overlap (Loose Jaccard) on the answer prose.
    def _tokens(s: str) -> set[str]:
        # Lowercase + alphanumeric word-shape tokens; drop stopwords.
        STOPWORDS = {
            "the", "a", "an", "is", "are", "and", "or", "of", "to", "in",
            "on", "for", "with", "by", "from", "as", "at", "this", "that",
            "be", "must", "any", "all", "you", "your", "we", "our", "if",
            "when", "what", "which", "who", "how", "do", "does", "but",
        }
        import re as _re
        out = set()
        for tok in _re.findall(r"[A-Za-z0-9]+", (s or "").lower()):
            if tok in STOPWORDS or len(tok) < 2:
                continue
            out.add(tok)
        return out

    gold_t = _tokens(expected_answer)
    pred_t = _tokens(pred_answer)
    if gold_t:
        ans_strict = len(gold_t & pred_t) / len(gold_t)
        if pred_t:
            ans_loose = len(gold_t & pred_t) / len(gold_t | pred_t)
        else:
            ans_loose = 0.0
    else:
        ans_strict = 0.0
        ans_loose = 0.0

    # Tone heuristic — flag the leftover robotic openers.
    low = (pred_answer or "").lower().lstrip()
    has_robotic_opener = (
        low.startswith("this question is covered by the eu ai act")
        or "this question is covered by the eu ai act" in low[:80]
    )

    return {
        "ref_loose": ref_loose,
        "ref_strict": ref_strict,
        "ref_precision": ref_precision,
        "ans_loose": ans_loose,
        "ans_strict": ans_strict,
        "has_robotic_opener": has_robotic_opener,
        "n_pred_refs": len(pred_refs),
        "n_gold_refs": len(expected_refs),
        "ref_hits": sorted(hits),
        "ref_missed": sorted(exp_norm - pred_norm),
        "ref_extra": sorted(pred_norm - exp_norm),
    }


# ── Runner main ────────────────────────────────────────────────────────


def _run_one(
    poster,
    endpoint: str,
    api_key: str | None,
    timeout: float,
    row: dict[str, Any],
) -> dict[str, Any]:
    """POST one OOB question, score, return one row of results."""
    history = [{"role": "user", "content": row["question"]}]
    body, latency_ms, status, error, attempts, retried = poster(
        endpoint, api_key, history, timeout,
    )
    pred_answer: str = body.get("answer") or ""
    pred_refs: list[str] = list(body.get("references") or [])
    reasoning = body.get("reasoning")

    scored = _score_row(row, pred_refs, pred_answer)

    return {
        "id": row.get("id"),
        "persona": row.get("persona"),
        "category": row.get("category"),
        "question": row.get("question"),
        "expected_refs": row.get("expected_refs"),
        "expected_answer": row.get("expected_answer"),
        "pred_refs": pred_refs,
        "pred_answer": pred_answer,
        "reasoning": reasoning,
        "latency_ms": round(latency_ms, 2),
        "http_status": status,
        "error": error,
        "attempts": attempts,
        "retried_errors": retried,
        **scored,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals.regenold.runner_oob")
    ap.add_argument("--inputs", nargs="+", required=False, default=[
        r"C:\Users\th3un\Downloads\gemini-code-1779789345282.json",
        r"C:\Users\th3un\Downloads\gemini-code-1779789352933.json",
        r"C:\Users\th3un\Downloads\gemini-code-1779789422612.json",
        r"C:\Users\th3un\Downloads\gemini-code-1779789770156.json",
    ], help="OOB JSON input files (deduplicated by id).")
    ap.add_argument(
        "--endpoint",
        default="https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
        help="Live /ask endpoint URL.",
    )
    ap.add_argument("--api-key", default=None, help="X-Regenold-Api-Key value.")
    ap.add_argument("--timeout", type=float, default=_DEFAULT_TIMEOUT_S)
    ap.add_argument("--label", default="oob-live")
    ap.add_argument("--local", action="store_true",
                    help="Use in-process FastAPI TestClient instead of live HTTP.")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="Parallel in-flight requests (live mode only).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Run only the first N rows (0 = all).")
    ap.add_argument(
        "--out-dir",
        default="evals/bench/results",
        help="Where the sidecar JSON lands.",
    )
    args = ap.parse_args(argv)

    rows = _load_oob_rows(args.inputs)
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("[error] no OOB rows loaded; check --inputs", file=sys.stderr)
        return 2

    print(f"[info] loaded {len(rows)} OOB rows", file=sys.stderr)
    print(f"[info] endpoint: {'TestClient (local)' if args.local else args.endpoint}", file=sys.stderr)

    poster = _post_local if args.local else _post_live
    started = _now_iso()
    results: list[dict[str, Any]] = []

    if args.local or args.concurrency <= 1:
        for i, row in enumerate(rows, 1):
            r = _run_one(poster, args.endpoint, args.api_key, args.timeout, row)
            results.append(r)
            print(f"[{i:3d}/{len(rows)}] {r['id']:18s} {r['latency_ms']:8.1f}ms  refL={r['ref_loose']:.0f} refS={r['ref_strict']:.0f}  err={r['error']}", file=sys.stderr)
    else:
        # Parallel for live.
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            fut_to_row = {
                ex.submit(_run_one, poster, args.endpoint, args.api_key, args.timeout, row): row
                for row in rows
            }
            done = 0
            for fut in as_completed(fut_to_row):
                done += 1
                r = fut.result()
                results.append(r)
                print(f"[{done:3d}/{len(rows)}] {r['id']:18s} {r['latency_ms']:8.1f}ms  refL={r['ref_loose']:.0f} refS={r['ref_strict']:.0f}  err={r['error']}", file=sys.stderr)
        # Sort by original order so the sidecar is deterministic.
        id_order = {r["id"]: i for i, r in enumerate(rows)}
        results.sort(key=lambda x: id_order.get(x.get("id"), 1e9))

    finished = _now_iso()

    # Aggregate.
    n = len(results)
    n_clean = sum(1 for r in results if not r["error"])
    n_errors = n - n_clean
    n_robotic = sum(1 for r in results if r.get("has_robotic_opener"))
    refL = mean(r["ref_loose"] for r in results) if results else 0.0
    refS = mean(r["ref_strict"] for r in results) if results else 0.0
    ansL = mean(r["ans_loose"] for r in results) if results else 0.0
    ansS = mean(r["ans_strict"] for r in results) if results else 0.0
    latencies = [r["latency_ms"] for r in results if not r["error"]]

    by_category: dict[str, dict[str, float]] = {}
    cats: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        cats.setdefault(r.get("category") or "uncategorized", []).append(r)
    for cat, sub in cats.items():
        by_category[cat] = {
            "n": len(sub),
            "ref_loose": round(mean(r["ref_loose"] for r in sub), 4),
            "ref_strict": round(mean(r["ref_strict"] for r in sub), 4),
            "ans_strict": round(mean(r["ans_strict"] for r in sub), 4),
            "ans_loose": round(mean(r["ans_loose"] for r in sub), 4),
            "robotic_openers": sum(1 for r in sub if r.get("has_robotic_opener")),
        }

    summary = {
        "n_total": n,
        "n_clean": n_clean,
        "n_errors": n_errors,
        "n_robotic_openers": n_robotic,
        "ref_loose": round(refL, 4),
        "ref_strict": round(refS, 4),
        "ans_loose": round(ansL, 4),
        "ans_strict": round(ansS, 4),
        "latency_p50_ms": round(median(latencies), 2) if latencies else None,
        "latency_p95_ms": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 2) if latencies else None,
        "latency_max_ms": round(max(latencies), 2) if latencies else None,
        "by_category": by_category,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = out_dir / f"oob-{args.label}.json"

    sidecar = {
        "label": args.label,
        "mode": "local" if args.local else "live",
        "endpoint": "TestClient" if args.local else args.endpoint,
        "started_at": started,
        "finished_at": finished,
        "summary": summary,
        "rows": results,
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")

    # Stdout summary.
    print(file=sys.stderr)
    print("================ OOB RUN SUMMARY ================", file=sys.stderr)
    print(f"label             : {args.label}", file=sys.stderr)
    print(f"items             : {n} (clean={n_clean}, errors={n_errors})", file=sys.stderr)
    print(f"ref_loose         : {refL:.4f}", file=sys.stderr)
    print(f"ref_strict        : {refS:.4f}", file=sys.stderr)
    print(f"ans_strict        : {ansS:.4f}", file=sys.stderr)
    print(f"ans_loose         : {ansL:.4f}", file=sys.stderr)
    print(f"robotic_openers   : {n_robotic} / {n}", file=sys.stderr)
    if latencies:
        print(f"latency p50/p95/max ms: {median(latencies):.1f} / {sorted(latencies)[int(0.95*(len(latencies)-1))]:.1f} / {max(latencies):.1f}", file=sys.stderr)
    print(f"sidecar           : {sidecar_path}", file=sys.stderr)
    return 0 if n_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

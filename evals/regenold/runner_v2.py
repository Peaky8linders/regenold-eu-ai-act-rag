"""V2 eval runner — scores the new harder scenarios against a live endpoint.

Loads :mod:`evals.regenold.scenarios_tricky_v2` and
:mod:`evals.regenold.scenarios_multiturn_v2`, hits a Regenold ``/ask``
endpoint (live Railway or local TestClient via ``--use-testclient``),
and scores against the Regenold rubric:

    1. Reference Correctness (Loose / Strict)
    2. Reference Conciseness
    3. Answer keyword presence (replaces "Answer Correctness" since these
       scenarios don't ship a full gold-answer string — only key markers)
    4. Latency (p50 / p95 / max)
    5. Regulatory tone
    6. Multi-turn coherence — final-turn answer cites expected refs AND
       contains expected keywords AND is not a refusal

Categories are surfaced separately so weak axes are visible per slice.
Stdlib only (urllib.request) so this runs on a stock Python 3.12.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.regenold.scenarios_multiturn_v2 import SCENARIOS as MULTITURN_V2
from evals.regenold.scenarios_tricky_v2 import SCENARIOS as TRICKY_V2


_USER_AGENT = "regenold-eu-ai-act-rag/runner-v2"
_REFUSAL_MARKERS = (
    "outside the scope",
    "not part of the eu ai act",
    "i only answer",
    "this assistant only",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── HTTP ─────────────────────────────────────────────────────────────────


def _post(
    endpoint: str,
    api_key: str | None,
    history: list[dict[str, str]],
    timeout: float,
) -> tuple[dict[str, Any], float, int, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if api_key:
        headers["X-Regenold-Api-Key"] = api_key
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(history).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    empty = {"answer": "", "references": [], "reasoning": None}
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.perf_counter() - start) * 1000.0
            status = resp.getcode() or 200
            raw = resp.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return empty, elapsed, status, "json_decode"
            if not isinstance(body, dict):
                return empty, elapsed, status, "non_dict_body"
            body.setdefault("answer", "")
            body.setdefault("references", [])
            return body, elapsed, status, None
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return empty, elapsed, exc.code, f"http_{exc.code}"
    except urllib.error.URLError as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return empty, elapsed, 0, f"url_error: {exc.reason}"
    except TimeoutError:
        elapsed = (time.perf_counter() - start) * 1000.0
        return empty, elapsed, 0, "timeout"
    except Exception as exc:  # noqa: BLE001
        elapsed = (time.perf_counter() - start) * 1000.0
        return empty, elapsed, 0, f"unexpected: {exc.__class__.__name__}"


# ── Scoring helpers ──────────────────────────────────────────────────────


def _gold_article_nums(expected_refs: list[str]) -> list[int]:
    """Map ``["Article 26", "Annex III"]`` → ``[26]`` (Annex refs skipped
    because the metrics module's gold-set helper takes article ints only;
    we score annex refs via the head-set overlap below).
    """
    nums: list[int] = []
    for r in expected_refs:
        s = r.strip()
        if s.startswith("Article "):
            try:
                nums.append(int(s[len("Article "):].split(".")[0].split("(")[0]))
            except ValueError:
                continue
    return nums


def _gold_head_set(expected_refs: list[str]) -> set[str]:
    """Project ``["Article 26", "Annex IV.1"]`` → ``{"Article 26", "Annex IV"}``."""
    out: set[str] = set()
    for r in expected_refs:
        head = bench_metrics.article_head(r)
        if head:
            out.add(head)
    return out


def _keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    """Fraction of expected keywords (case-insensitive substring) present."""
    if not expected_keywords:
        return 1.0
    low = answer.lower()
    hits = sum(1 for k in expected_keywords if k.lower() in low)
    return hits / len(expected_keywords)


def _ref_metrics(pred_refs: list[str], expected_refs: list[str]) -> dict[str, float]:
    pred_heads = bench_metrics.article_heads(pred_refs)
    gold_heads = _gold_head_set(expected_refs)
    if not gold_heads and not pred_heads:
        loose = strict = 1.0
    elif not gold_heads or not pred_heads:
        loose = strict = 0.0
    else:
        overlap = len(pred_heads & gold_heads)
        loose = overlap / len(gold_heads)
        if overlap == 0:
            strict = 0.0
        else:
            precision = overlap / len(pred_heads)
            recall = overlap / len(gold_heads)
            strict = 2 * precision * recall / (precision + recall)
    # Conciseness — same shape as bench_metrics: symmetric length ratio, squared.
    lp = len(pred_heads)
    lg = len(gold_heads)
    if lg == 0:
        conciseness = 1.0 if lp == 0 else 0.0
    elif lp == 0:
        conciseness = 0.0
    else:
        ratio = min(lp, lg) / max(lp, lg)
        conciseness = ratio * ratio
    return {"loose": loose, "strict": strict, "conciseness": conciseness}


# ── Tricky runner ────────────────────────────────────────────────────────


def _score_tricky_row(
    scenario: dict[str, Any], body: dict[str, Any], latency_ms: float, err: str | None
) -> dict[str, Any]:
    answer = body.get("answer") or ""
    refs = body.get("references") or []
    ref = _ref_metrics(refs, scenario.get("expected_refs", []))
    kw = _keyword_recall(answer, scenario.get("expected_keywords", []))
    tone = bench_metrics.regulatory_tone(answer)
    is_refusal = any(m in answer.lower() for m in _REFUSAL_MARKERS)
    return {
        "id": scenario["id"],
        "category": scenario.get("category", "uncategorised"),
        "question": scenario["question"][:200],
        "expected_refs": scenario.get("expected_refs", []),
        "pred_refs": refs,
        "expected_keywords": scenario.get("expected_keywords", []),
        "answer_preview": answer[:240],
        "ref_loose": ref["loose"],
        "ref_strict": ref["strict"],
        "ref_conciseness": ref["conciseness"],
        "keyword_recall": kw,
        "regulatory_tone": tone,
        "latency_ms": latency_ms,
        "is_refusal": is_refusal,
        "error": err,
    }


def run_tricky(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    concurrency: int,
    limit: int | None,
    verbose: bool,
) -> list[dict[str, Any]]:
    items = TRICKY_V2[:limit] if limit else TRICKY_V2
    results: list[dict[str, Any]] = [None] * len(items)  # type: ignore[list-item]
    completed = 0
    lock = threading.Lock()

    def _worker(idx: int, scn: dict) -> tuple[int, dict]:
        history = [{"role": "user", "content": scn["question"]}]
        body, lat, status, err = _post(endpoint, api_key, history, timeout)
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        return idx, _score_tricky_row(scn, body, lat, err)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_worker, i, s) for i, s in enumerate(items)]
        for fut in as_completed(futures):
            idx, row = fut.result()
            results[idx] = row
            with lock:
                completed += 1
                if verbose:
                    print(
                        f"[tricky] {completed}/{len(items)} {row['id']} "
                        f"cat={row['category']:<22} "
                        f"refL={row['ref_loose']:.2f} kw={row['keyword_recall']:.2f} "
                        f"lat={row['latency_ms']:.0f}ms"
                    )
    return results  # type: ignore[return-value]


# ── Multi-turn runner ────────────────────────────────────────────────────


def _score_multiturn_row(
    scenario: dict[str, Any],
    final_body: dict[str, Any],
    final_latency_ms: float,
    err: str | None,
) -> dict[str, Any]:
    answer = final_body.get("answer") or ""
    refs = final_body.get("references") or []
    expected_refs = scenario.get("expected_final_refs", [])
    expected_kw = scenario.get("expected_final_keywords", [])
    ref = _ref_metrics(refs, expected_refs)
    kw = _keyword_recall(answer, expected_kw)
    tone = bench_metrics.regulatory_tone(answer)
    is_refusal = any(m in answer.lower() for m in _REFUSAL_MARKERS)
    # Coherent = cites at least one expected ref AND has 50%+ of keywords
    # AND not a refusal AND no HTTP error.
    is_coherent = (
        ref["loose"] > 0.0
        and kw >= 0.5
        and not is_refusal
        and err is None
    )
    return {
        "id": scenario["id"],
        "n_turns": len(scenario.get("turns", [])),
        "expected_final_refs": expected_refs,
        "pred_refs": refs,
        "expected_keywords": expected_kw,
        "answer_preview": answer[:240],
        "ref_loose": ref["loose"],
        "ref_strict": ref["strict"],
        "ref_conciseness": ref["conciseness"],
        "keyword_recall": kw,
        "regulatory_tone": tone,
        "latency_ms": final_latency_ms,
        "is_refusal": is_refusal,
        "is_coherent": is_coherent,
        "error": err,
    }


def run_multiturn(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    limit: int | None,
    verbose: bool,
) -> list[dict[str, Any]]:
    items = MULTITURN_V2[:limit] if limit else MULTITURN_V2
    out: list[dict[str, Any]] = []
    for idx, scn in enumerate(items):
        # Send the whole pre-recorded conversation as a single history.
        # We could replay turn-by-turn but the runner cares about the
        # FINAL user message's answer, not what the assistant said for the
        # canned mid-turns. The route flattens history → question internally.
        history = scn.get("turns", [])
        body, lat, status, err = _post(endpoint, api_key, history, timeout)
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        row = _score_multiturn_row(scn, body, lat, err)
        out.append(row)
        if verbose:
            print(
                f"[mt] {idx + 1}/{len(items)} {row['id']} "
                f"turns={row['n_turns']} refL={row['ref_loose']:.2f} "
                f"kw={row['keyword_recall']:.2f} coh={row['is_coherent']} "
                f"lat={row['latency_ms']:.0f}ms"
            )
    return out


# ── Aggregation ──────────────────────────────────────────────────────────


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    valid = [r for r in rows if r.get("error") is None]
    if not valid:
        return {"n": len(rows), "http_failures": len(rows)}
    def _avg(key: str) -> float:
        return round(mean(r[key] for r in valid), 4)
    latencies = [r["latency_ms"] for r in valid]
    return {
        "n": len(rows),
        "http_failures": len(rows) - len(valid),
        "ref_loose": _avg("ref_loose"),
        "ref_strict": _avg("ref_strict"),
        "ref_conciseness": _avg("ref_conciseness"),
        "keyword_recall": _avg("keyword_recall"),
        "regulatory_tone": _avg("regulatory_tone"),
        "latency_p50_ms": round(bench_metrics.percentile(latencies, 50), 2),
        "latency_p95_ms": round(bench_metrics.percentile(latencies, 95), 2),
        "latency_max_ms": round(max(latencies), 2),
    }


def _aggregate_by_category(rows: list[dict[str, Any]]) -> dict[str, Any]:
    bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        bucket[r.get("category", "uncategorised")].append(r)
    return {cat: _aggregate(rs) for cat, rs in bucket.items()}


def _coherence_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for r in rows if r.get("is_coherent")) / len(rows), 4)


# ── Top-level ────────────────────────────────────────────────────────────


def run(
    *,
    endpoint: str,
    api_key: str | None,
    label: str,
    timeout: float = 60.0,
    concurrency: int = 2,
    tricky_limit: int | None = None,
    multiturn_limit: int | None = None,
    verbose: bool = False,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    started_at = _now_iso()
    tricky_rows = run_tricky(
        endpoint, api_key, timeout, concurrency, tricky_limit, verbose
    )
    mt_rows = run_multiturn(endpoint, api_key, timeout, multiturn_limit, verbose)
    finished_at = _now_iso()

    payload = {
        "label": label,
        "mode": "v2-live" if endpoint.startswith("http") else "v2-local",
        "endpoint": endpoint,
        "started_at": started_at,
        "finished_at": finished_at,
        "tricky": {
            "rows": tricky_rows,
            "summary": _aggregate(tricky_rows),
            "by_category": _aggregate_by_category(tricky_rows),
        },
        "multiturn": {
            "rows": mt_rows,
            "summary": _aggregate(mt_rows),
            "coherence_rate": _coherence_rate(mt_rows),
        },
    }
    if out_dir is None:
        out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"v2-{label}.json"
    sidecar.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["sidecar_path"] = str(sidecar)
    return payload


# ── Pretty printer ───────────────────────────────────────────────────────


def _format(payload: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"V2 eval runner — label={payload['label']!r}")
    out.append(f"endpoint: {payload['endpoint']}")
    out.append("=" * 78)
    tricky = payload["tricky"]["summary"]
    out.append("")
    out.append(f"[TRICKY] n={tricky.get('n', 0)} "
               f"http_failures={tricky.get('http_failures', 0)}")
    out.append(f"  Ref Loose            : {tricky.get('ref_loose', '-')}")
    out.append(f"  Ref Strict           : {tricky.get('ref_strict', '-')}")
    out.append(f"  Ref Conciseness      : {tricky.get('ref_conciseness', '-')}")
    out.append(f"  Keyword Recall       : {tricky.get('keyword_recall', '-')}")
    out.append(f"  Regulatory Tone      : {tricky.get('regulatory_tone', '-')}")
    out.append(
        f"  Latency              : p50={tricky.get('latency_p50_ms', '-')}ms  "
        f"p95={tricky.get('latency_p95_ms', '-')}ms  "
        f"max={tricky.get('latency_max_ms', '-')}ms"
    )
    out.append("")
    out.append("  By category:")
    for cat, agg in payload["tricky"]["by_category"].items():
        out.append(
            f"    {cat:<22} n={agg.get('n', 0):>3}  "
            f"refL={agg.get('ref_loose', '-')}  "
            f"refS={agg.get('ref_strict', '-')}  "
            f"kw={agg.get('keyword_recall', '-')}"
        )

    mt = payload["multiturn"]["summary"]
    coh = payload["multiturn"]["coherence_rate"]
    out.append("")
    out.append(f"[MULTI-TURN V2] n={mt.get('n', 0)} "
               f"http_failures={mt.get('http_failures', 0)}")
    out.append(f"  Coherence Rate       : {coh}")
    out.append(f"  Ref Loose            : {mt.get('ref_loose', '-')}")
    out.append(f"  Ref Strict           : {mt.get('ref_strict', '-')}")
    out.append(f"  Keyword Recall       : {mt.get('keyword_recall', '-')}")
    out.append(f"  Regulatory Tone      : {mt.get('regulatory_tone', '-')}")
    out.append(
        f"  Latency              : p50={mt.get('latency_p50_ms', '-')}ms  "
        f"p95={mt.get('latency_p95_ms', '-')}ms  "
        f"max={mt.get('latency_max_ms', '-')}ms"
    )
    out.append("")
    out.append(f"sidecar: {payload.get('sidecar_path', '-')}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--tricky-limit", type=int, default=None)
    parser.add_argument("--multiturn-limit", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    payload = run(
        endpoint=args.endpoint,
        api_key=args.api_key,
        label=args.label,
        timeout=args.timeout,
        concurrency=args.concurrency,
        tricky_limit=args.tricky_limit,
        multiturn_limit=args.multiturn_limit,
        verbose=args.verbose,
    )
    print(_format(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.bench._http_retry import post_json_with_retry
from evals.regenold.scenarios_multiturn_v2 import SCENARIOS as MULTITURN_V2
from evals.regenold.scenarios_oos import OOS_CATEGORIES, OOS_SCENARIOS, OOSScenario
from evals.regenold.scenarios_tricky_v2 import SCENARIOS as TRICKY_V2


_USER_AGENT = "regenold-eu-ai-act-rag/runner-v2"
_REFUSAL_MARKERS = (
    "outside the scope",
    "not part of the eu ai act",
    "i only answer",
    "this assistant only",
    # R56-B — every refusal copy in scope.py::refusal_copy_for() opens
    # with "This question is" or "This assistant" (post-R55-A
    # third-person regulator rewrite). These markers are the
    # discriminator the --probe-oos verdict aggregator uses to tell a
    # refusal apart from a substantive in-scope answer.
    "this question is about",
    "this assistant answers eu ai act questions only",
    "does not appear in the eu ai act",
    "no matching obligation found",
)

# R56-B — references that are acceptable on a refusal response. The
# scope-gate may legitimately surface a first-floor anchor (Art. 1 /
# 2 / 3 — purpose / scope / definitions) on a near_oos or zero-
# retrieval refusal without that counting as a scope leak. Anything
# else in the references list on a refusal is a leak.
_REFUSAL_ALLOWED_REFS: frozenset[str] = frozenset({
    "Article 1", "Article 2", "Article 3",
})

# R56-B — verdict taxonomy for the --probe-oos mode:
#   PASS              — refused AND expected_reason matches (or None)
#   FAIL_SCOPE_LEAK   — substantive answer (no refusal marker) OR refs
#                       outside the first-floor allow-list. HARD FAIL.
#   FAIL_WRONG_REASON — refused with a different ScopeReason than expected
#                       (soft fail; only fires when expected_reason set).
#   ERROR             — HTTP / network failure (soft; treated as not-pass
#                       but doesn't gate deploys).
_OOS_VERDICTS = (
    "PASS", "FAIL_SCOPE_LEAK", "FAIL_WRONG_REASON", "ERROR",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── HTTP ─────────────────────────────────────────────────────────────────


def _post(
    endpoint: str,
    api_key: str | None,
    history: list[dict[str, str]],
    timeout: float,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """POST with one-shot retry on transient connection failures.

    R47-D — delegates to :func:`evals.bench._http_retry.post_json_with_retry`
    so the R46 V2 ``RemoteDisconnected`` / WinError-10060 failures
    recover on a single retry instead of polluting the scorecard.

    Returns ``(body, latency_ms, http_status, error, attempts, retried_errors)``.
    """
    return post_json_with_retry(
        endpoint, history, api_key, timeout,
        user_agent=_USER_AGENT,
    )


# ── Local TestClient transport (R56-B --local flag) ──────────────────────


def _local_endpoint_url(query_string: str = "include_reasoning=true") -> str:
    """Synthetic URL marker for the TestClient transport.

    The runner only reads ``endpoint`` to (a) classify mode (live vs
    local) for the JSON sidecar's ``mode`` field, and (b) carry the
    ``?include_reasoning=true`` query string. TestClient receives the
    path segment separately.
    """
    return f"local://app.main:app/api/v1/regenold/eu-ai-act/ask?{query_string}"


def _post_local(
    endpoint: str,
    api_key: str | None,
    history: list[dict[str, str]],
    timeout: float,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """In-process POST via FastAPI's ``TestClient``.

    Mirrors the return shape of :func:`_post` so the runner code path is
    transport-agnostic. Imports are lazy because the live-HTTP CLI mode
    must NOT pull FastAPI / the full app graph into the runner's import
    surface.
    """
    # Lazy imports — heavy graph; only loaded when --local fires.
    import time as _time

    from fastapi.testclient import TestClient

    from app.main import app as _app

    empty: dict[str, Any] = {"answer": "", "references": [], "reasoning": None}

    # The endpoint string carries the query suffix (e.g. ``?include_reasoning=true``).
    # Strip the synthetic scheme + host and POST against TestClient.
    qs = "include_reasoning=true"
    if "?" in endpoint:
        qs = endpoint.split("?", 1)[1]
    path = f"/api/v1/regenold/eu-ai-act/ask?{qs}"

    headers = {"User-Agent": _USER_AGENT}
    if api_key:
        headers["X-Regenold-Api-Key"] = api_key

    start = _time.perf_counter()
    try:
        with TestClient(_app) as client:
            resp = client.post(path, json=history, headers=headers, timeout=timeout)
        elapsed_ms = (_time.perf_counter() - start) * 1000.0
        status = resp.status_code
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            return empty, elapsed_ms, status, "json_decode", 1, []
        if not isinstance(body, dict):
            return empty, elapsed_ms, status, "non_dict_body", 1, []
        body.setdefault("answer", "")
        body.setdefault("references", [])
        body.setdefault("reasoning", None)
        err = None if 200 <= status < 300 else f"http_{status}"
        return body, elapsed_ms, status, err, 1, []
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (_time.perf_counter() - start) * 1000.0
        return empty, elapsed_ms, 0, f"local_error: {exc}"[:200], 1, []


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
    scenario: dict[str, Any],
    body: dict[str, Any],
    latency_ms: float,
    err: str | None,
    attempts: int = 1,
    retried_errors: list[str] | None = None,
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
        # R52.1 — `answer_preview` is for human eyeballing the JSON
        # sidecar; the LLM-as-Judge reads `predicted_answer` so it sees
        # the FULL prose (not the 600-char preview). Pre-R52.1 the
        # judge was using `answer_preview` and hard-failing 7 rows for
        # "truncated mid-sentence" — a sidecar artefact, not a wire
        # bug.
        "answer_preview": answer[:600],
        "predicted_answer": answer,
        "ref_loose": ref["loose"],
        "ref_strict": ref["strict"],
        "ref_conciseness": ref["conciseness"],
        "keyword_recall": kw,
        "regulatory_tone": tone,
        "latency_ms": latency_ms,
        "is_refusal": is_refusal,
        "error": err,
        "attempts": attempts,
        "retried_errors": list(retried_errors or []),
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
        body, lat, status, err, attempts, retried = _post(
            endpoint, api_key, history, timeout
        )
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        return idx, _score_tricky_row(scn, body, lat, err, attempts, retried)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_worker, i, s) for i, s in enumerate(items)]
        for fut in as_completed(futures):
            idx, row = fut.result()
            results[idx] = row
            with lock:
                completed += 1
                if verbose:
                    retry_tag = (
                        f" attempts={row['attempts']}"
                        if row.get("attempts", 1) > 1 else ""
                    )
                    print(
                        f"[tricky] {completed}/{len(items)} {row['id']} "
                        f"cat={row['category']:<22} "
                        f"refL={row['ref_loose']:.2f} kw={row['keyword_recall']:.2f} "
                        f"lat={row['latency_ms']:.0f}ms{retry_tag}"
                    )
    return results  # type: ignore[return-value]


# ── Multi-turn runner ────────────────────────────────────────────────────


def _score_multiturn_row(
    scenario: dict[str, Any],
    final_body: dict[str, Any],
    final_latency_ms: float,
    err: str | None,
    attempts: int = 1,
    retried_errors: list[str] | None = None,
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
        # R52.1 — see _score_tricky_row note for rationale.
        "answer_preview": answer[:600],
        "predicted_answer": answer,
        "ref_loose": ref["loose"],
        "ref_strict": ref["strict"],
        "ref_conciseness": ref["conciseness"],
        "keyword_recall": kw,
        "regulatory_tone": tone,
        "latency_ms": final_latency_ms,
        "is_refusal": is_refusal,
        "is_coherent": is_coherent,
        "error": err,
        "attempts": attempts,
        "retried_errors": list(retried_errors or []),
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
        body, lat, status, err, attempts, retried = _post(
            endpoint, api_key, history, timeout
        )
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        row = _score_multiturn_row(scn, body, lat, err, attempts, retried)
        out.append(row)
        if verbose:
            retry_tag = (
                f" attempts={row['attempts']}"
                if row.get("attempts", 1) > 1 else ""
            )
            print(
                f"[mt] {idx + 1}/{len(items)} {row['id']} "
                f"turns={row['n_turns']} refL={row['ref_loose']:.2f} "
                f"kw={row['keyword_recall']:.2f} coh={row['is_coherent']} "
                f"lat={row['latency_ms']:.0f}ms{retry_tag}"
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


def _retry_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-row retry telemetry for the JSON sidecar.

    Returns ``{total_retries, rows_retried, rows_retry_recovered,
    retry_recovery_rate}``. ``recovery_rate`` is the fraction of rows
    that needed at least one retry AND ultimately succeeded.
    """
    total_retries = 0
    rows_retried = 0
    recovered = 0
    for r in rows:
        n = int(r.get("attempts") or 1)
        total_retries += max(0, n - 1)
        if n > 1:
            rows_retried += 1
            if r.get("error") is None:
                recovered += 1
    return {
        "total_retries": total_retries,
        "rows_retried": rows_retried,
        "rows_retry_recovered": recovered,
        "retry_recovery_rate": (
            round(recovered / rows_retried, 4) if rows_retried else 0.0
        ),
    }


# ── OOS probe (R56-B) ────────────────────────────────────────────────────


def _parse_reasoning_scope_reason(reasoning: str | None) -> str | None:
    """Pull the ScopeReason verdict out of a ``?include_reasoning=true``
    payload. Returns ``None`` when the trace isn't a parseable JSON
    object or doesn't carry the scope verdict.
    """
    if not reasoning:
        return None
    try:
        parsed = json.loads(reasoning)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    scope = parsed.get("scope")
    if not isinstance(scope, dict):
        return None
    verdict = scope.get("verdict")
    if not isinstance(verdict, str):
        return None
    return verdict


def _looks_like_refusal(answer: str) -> bool:
    """Heuristic — does the answer prose look like a scope-gate refusal?

    Matches against the markers from :data:`_REFUSAL_MARKERS`, which
    cover every refusal copy template in
    ``scope.refusal_copy_for()``. Used by the --probe-oos verdict
    aggregator to discriminate refusal-shape responses from substantive
    in-scope answers.
    """
    if not answer:
        return False
    low = answer.lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def _refs_within_floor(refs: list[str]) -> bool:
    """Are the surfaced references within the acceptable refusal floor?

    A scope-gate refusal may legitimately surface Art. 1 / 2 / 3 (the
    purpose / scope / definitions first-floor anchors) when the
    near_oos / zero-retrieval-fallback pathway fires. Anything else is
    a scope leak.
    """
    if not refs:
        return True
    return all(r in _REFUSAL_ALLOWED_REFS for r in refs)


def _classify_oos_row(
    scn: OOSScenario,
    body: dict[str, Any],
    err: str | None,
) -> tuple[str, str]:
    """Return ``(verdict, detail)`` for one OOS probe row.

    Detail is a short human-readable explanation surfaced in the
    per-row sidecar so an operator scanning a FAIL row can see WHY
    it failed without re-running the probe.
    """
    if err is not None:
        return "ERROR", err

    answer = body.get("answer") or ""
    refs = list(body.get("references") or [])
    reasoning = body.get("reasoning")

    refused_by_prose = _looks_like_refusal(answer)
    refs_ok = _refs_within_floor(refs)

    # Scope LEAK — substantive answer OR references outside the
    # first-floor allow-list. Either is a hard fail because the OOS
    # query slipped past the scope gate.
    if not refused_by_prose or not refs_ok:
        why = []
        if not refused_by_prose:
            why.append("answer_lacks_refusal_marker")
        if not refs_ok:
            why.append(f"refs_outside_floor={refs}")
        return "FAIL_SCOPE_LEAK", "; ".join(why)

    # We have a refusal-shape response. Check the reason if expected.
    actual_reason = _parse_reasoning_scope_reason(reasoning)
    if scn.expected_reason is None:
        # Any non-IN_SCOPE reason is acceptable. If the trace says
        # in_scope we have a contradiction — answer looks like a
        # refusal but the trace says we routed in-scope. Treat as
        # soft PASS (the shipped answer is what counts) but tag it.
        if actual_reason == "in_scope":
            return "PASS", "refusal_prose_but_trace_says_in_scope"
        return "PASS", f"refused reason={actual_reason or 'unknown'}"

    if actual_reason is None:
        # Trace didn't carry a parseable scope verdict — soft PASS
        # because the prose is a refusal; the operator should still
        # see this in the sidecar.
        return "PASS", "refused but reasoning trace missing scope verdict"

    if actual_reason == scn.expected_reason:
        return "PASS", f"reason={actual_reason}"

    return "FAIL_WRONG_REASON", (
        f"expected={scn.expected_reason} actual={actual_reason}"
    )


def _score_oos_row(
    scn: OOSScenario,
    body: dict[str, Any],
    latency_ms: float,
    err: str | None,
    attempts: int = 1,
    retried_errors: list[str] | None = None,
) -> dict[str, Any]:
    verdict, detail = _classify_oos_row(scn, body, err)
    answer = body.get("answer") or ""
    refs = list(body.get("references") or [])
    reasoning_scope = _parse_reasoning_scope_reason(body.get("reasoning"))
    return {
        "id": scn.id,
        "category": scn.category,
        "question": scn.question[:200],
        "expected_reason": scn.expected_reason,
        "actual_reason": reasoning_scope,
        "verdict": verdict,
        "detail": detail,
        "pred_refs": refs,
        "answer_preview": answer[:300],
        "predicted_answer": answer,
        "looks_like_refusal": _looks_like_refusal(answer),
        "refs_within_floor": _refs_within_floor(refs),
        "latency_ms": latency_ms,
        "error": err,
        "attempts": attempts,
        "retried_errors": list(retried_errors or []),
    }


def run_probe_oos(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    concurrency: int,
    limit: int | None,
    verbose: bool,
    use_local: bool = False,
) -> list[dict[str, Any]]:
    """Run every OOS scenario against ``endpoint`` (or local TestClient).

    Concurrency mirrors :func:`run_tricky` so the probe is fast on the
    live wire without overwhelming the partner rate-limit. Local mode
    serialises because TestClient already runs the FastAPI app
    in-process; concurrency there buys nothing.
    """
    items = OOS_SCENARIOS[:limit] if limit else OOS_SCENARIOS
    results: list[dict[str, Any]] = [None] * len(items)  # type: ignore[list-item]
    completed = 0
    lock = threading.Lock()
    transport = _post_local if use_local else _post

    def _worker(idx: int, scn: OOSScenario) -> tuple[int, dict]:
        history = [{"role": "user", "content": scn.question}]
        body, lat, status, err, attempts, retried = transport(
            endpoint, api_key, history, timeout,
        )
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        return idx, _score_oos_row(scn, body, lat, err, attempts, retried)

    workers = 1 if use_local else max(1, concurrency)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, i, s) for i, s in enumerate(items)]
        for fut in as_completed(futures):
            idx, row = fut.result()
            results[idx] = row
            with lock:
                completed += 1
                if verbose:
                    print(
                        f"[oos] {completed}/{len(items)} {row['id']} "
                        f"cat={row['category']:<18} "
                        f"verdict={row['verdict']:<18} "
                        f"reason={(row['actual_reason'] or '-'):<22} "
                        f"lat={row['latency_ms']:.0f}ms"
                    )
    return results  # type: ignore[return-value]


def _aggregate_oos(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up OOS verdict counts + per-category breakdown."""
    counts: dict[str, int] = {v: 0 for v in _OOS_VERDICTS}
    by_cat: dict[str, dict[str, int]] = defaultdict(
        lambda: {v: 0 for v in _OOS_VERDICTS}
    )
    for r in rows:
        v = r.get("verdict") or "ERROR"
        counts[v] = counts.get(v, 0) + 1
        by_cat[r.get("category") or "unknown"][v] += 1
    n = len(rows)
    scope_leaks = counts.get("FAIL_SCOPE_LEAK", 0)
    return {
        "n": n,
        "pass": counts.get("PASS", 0),
        "fail_scope_leak": scope_leaks,
        "fail_wrong_reason": counts.get("FAIL_WRONG_REASON", 0),
        "errors": counts.get("ERROR", 0),
        "pass_rate": round(counts.get("PASS", 0) / n, 4) if n else 0.0,
        "scope_leak_rate": round(scope_leaks / n, 4) if n else 0.0,
        "hard_fail": scope_leaks > 0,
        "by_category": {cat: dict(v) for cat, v in by_cat.items()},
    }


def run_probe_oos_only(
    *,
    endpoint: str,
    api_key: str | None,
    label: str,
    timeout: float = 60.0,
    concurrency: int = 2,
    limit: int | None = None,
    verbose: bool = False,
    out_dir: Path | None = None,
    use_local: bool = False,
) -> dict[str, Any]:
    """Top-level runner for the ``--probe-oos`` mode.

    Sister to :func:`run` — skips tricky + multiturn entirely and runs
    only the curated OOS regression set. Writes its sidecar to
    ``probe-oos-<label>.json`` (separate filename so it doesn't collide
    with a same-day v2 run).
    """
    started_at = _now_iso()
    rows = run_probe_oos(
        endpoint, api_key, timeout, concurrency, limit, verbose,
        use_local=use_local,
    )
    finished_at = _now_iso()

    summary = _aggregate_oos(rows)

    payload = {
        "label": label,
        "mode": "probe-oos-local" if use_local else (
            "probe-oos-live" if endpoint.startswith("http") else "probe-oos"
        ),
        "endpoint": endpoint,
        "started_at": started_at,
        "finished_at": finished_at,
        "probe_oos": {
            "rows": rows,
            "summary": summary,
            "retry_stats": _retry_stats(rows),
        },
    }
    if out_dir is None:
        out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"probe-oos-{label}.json"
    sidecar.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["sidecar_path"] = str(sidecar)
    return payload


def _format_probe_oos(payload: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"V2 --probe-oos runner — label={payload['label']!r}")
    out.append(f"endpoint: {payload['endpoint']}")
    out.append(f"mode: {payload['mode']}")
    out.append("=" * 78)
    summary = payload["probe_oos"]["summary"]
    out.append("")
    out.append(
        f"[OOS] n={summary['n']} pass={summary['pass']} "
        f"fail_scope_leak={summary['fail_scope_leak']} "
        f"fail_wrong_reason={summary['fail_wrong_reason']} "
        f"errors={summary['errors']}"
    )
    out.append(f"  Pass rate         : {summary['pass_rate']}")
    out.append(f"  Scope-leak rate   : {summary['scope_leak_rate']}")
    out.append(f"  Hard-fail         : {summary['hard_fail']}")
    out.append("")
    out.append("  By category:")
    for cat, counts in summary["by_category"].items():
        out.append(
            f"    {cat:<18} "
            f"pass={counts.get('PASS', 0):>2} "
            f"leak={counts.get('FAIL_SCOPE_LEAK', 0):>2} "
            f"wrong={counts.get('FAIL_WRONG_REASON', 0):>2} "
            f"err={counts.get('ERROR', 0):>2}"
        )

    leaks = [r for r in payload["probe_oos"]["rows"]
             if r.get("verdict") == "FAIL_SCOPE_LEAK"]
    if leaks:
        out.append("")
        out.append("  Scope leaks (HARD FAIL):")
        for r in leaks:
            out.append(
                f"    [{r['id']:<22}] {r['question'][:80]}"
            )
            out.append(f"        detail: {r.get('detail', '')}")
            out.append(f"        refs:   {r.get('pred_refs')}")
    wrong = [r for r in payload["probe_oos"]["rows"]
             if r.get("verdict") == "FAIL_WRONG_REASON"]
    if wrong:
        out.append("")
        out.append("  Wrong reason (soft fail):")
        for r in wrong:
            out.append(
                f"    [{r['id']:<22}] {r['question'][:80]}"
            )
            out.append(f"        {r.get('detail', '')}")
    out.append("")
    out.append(f"sidecar: {payload.get('sidecar_path', '-')}")
    return "\n".join(out)


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
            "retry_stats": _retry_stats(tricky_rows),
        },
        "multiturn": {
            "rows": mt_rows,
            "summary": _aggregate(mt_rows),
            "coherence_rate": _coherence_rate(mt_rows),
            "retry_stats": _retry_stats(mt_rows),
        },
        "retry_stats": _retry_stats(tricky_rows + mt_rows),
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
    rs = payload.get("retry_stats") or {}
    if rs.get("total_retries") or rs.get("rows_retried"):
        out.append("")
        out.append(
            f"[RETRIES] total={rs.get('total_retries', 0)} "
            f"rows={rs.get('rows_retried', 0)} "
            f"recovered={rs.get('rows_retry_recovered', 0)} "
            f"recovery_rate={rs.get('retry_recovery_rate', 0.0)}"
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
    # R56-B — ``--endpoint`` is not required when ``--local`` is set
    # (TestClient handles routing internally). Default to ``None`` and
    # validate after argparse so the error message is clearer than
    # argparse's default.
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--tricky-limit", type=int, default=None)
    parser.add_argument("--multiturn-limit", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    # R56-B — OOS regression-test mode. Skips tricky + multiturn
    # entirely; runs only the curated OOS regression set from
    # ``evals.regenold.scenarios_oos``. Hard-fails the exit code when
    # any scenario hits FAIL_SCOPE_LEAK.
    parser.add_argument(
        "--probe-oos",
        action="store_true",
        help=(
            "Run only the OOS regression set; skip tricky+multiturn. "
            "Exit code is non-zero when any scenario leaks scope."
        ),
    )
    # R56-B — CI-friendly transport. Skips live HTTPS entirely and
    # runs against ``app.main:app`` via FastAPI's TestClient.
    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "Use FastAPI TestClient against app.main:app instead of "
            "live HTTPS. --endpoint may be omitted. Useful for CI."
        ),
    )
    parser.add_argument(
        "--oos-limit", type=int, default=None,
        help="Cap the number of OOS scenarios run (debug aid).",
    )
    args = parser.parse_args(argv)

    # Resolve endpoint for both modes. Local mode injects a synthetic
    # URL that the TestClient transport short-circuits on.
    if args.local:
        endpoint = _local_endpoint_url("include_reasoning=true")
    elif args.endpoint:
        endpoint = args.endpoint
    else:
        parser.error("--endpoint is required unless --local is set")
        return 2  # unreachable — argparse.error exits

    # ── --probe-oos branch (R56-B) ─────────────────────────────────────
    if args.probe_oos:
        payload = run_probe_oos_only(
            endpoint=endpoint,
            api_key=args.api_key,
            label=args.label,
            timeout=args.timeout,
            concurrency=args.concurrency,
            limit=args.oos_limit,
            verbose=args.verbose,
            use_local=args.local,
        )
        print(_format_probe_oos(payload))
        return 1 if payload["probe_oos"]["summary"]["hard_fail"] else 0

    # ── Default branch — tricky + multiturn ────────────────────────────
    payload = run(
        endpoint=endpoint,
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

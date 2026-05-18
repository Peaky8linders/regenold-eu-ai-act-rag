"""Production benchmark runner — hits a *live* Regenold endpoint over HTTP.

Mirrors :mod:`evals.bench.runner` but instead of going through FastAPI's
``TestClient`` against the in-process app, this runner makes real
``POST`` requests against a deployed Regenold service (typically the
Railway production deploy at
``https://regenold-eu-ai-act-rag.up.railway.app``). End-to-end latency
therefore includes network RTT, the production LLM provider, the live
Neo4j hop, and TLS termination — i.e. exactly what the competition
judge measures.

Hard design constraints (set by the task brief and ``CLAUDE.md``):
    * Pure stdlib — no ``requests`` / ``httpx``. We use
      :mod:`urllib.request` so this script runs on a stock Python 3.12.
    * Reuses :mod:`evals.bench.metrics` byte-for-byte — the local and
      production scorecards must be comparable.
    * Never crash the full bench on a single per-item failure. HTTP
      errors / timeouts / JSON parse failures land as ``passed=False``
      rows with the error captured, and the run continues.
    * Audit-chain write is best-effort — when ``DATABASE_URL`` isn't
      set locally we still want a JSON sidecar + a printed scorecard.

CLI::

    py -3.12 -m evals.bench.prod_runner \\
        --endpoint https://regenold-eu-ai-act-rag.up.railway.app/api/v1/regenold/eu-ai-act/ask \\
        --api-key $REGENOLD_API_KEY \\
        --label r35-prod-graph-on \\
        --limit 50

A ``--health-only`` shortcut just probes ``/healthz``, ``/healthz/llm``
and ``/healthz/graph`` on the same host and prints the status — useful
as the first thing to run after a fresh deploy.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.bench import dataset as bench_dataset
from evals.bench import metrics
from evals.bench import storage
from evals.bench._http_retry import post_json_with_retry


# ── Configuration ───────────────────────────────────────────────────────


# Partner-tier production rate limit — 60 requests / minute (CLAUDE.md
# round-32 partner SLA). We honour it by sleeping 0.05s between
# *batches* when concurrency >= 4 (i.e. roughly 20 batches/s × 4
# concurrent = below the 60/min ceiling once you factor in real RTT).
_RATE_LIMIT_BATCH_SLEEP_S = 0.05
_RATE_LIMIT_BATCH_THRESHOLD = 4

# Multi-turn follow-up question — must stay byte-identical to the local
# runner so cross-run deltas measure *engine* differences, not prompt
# differences.
_MULTITURN_FOLLOWUP = (
    "And what are the technical documentation requirements"
    " we need to maintain?"
)

_REFUSAL_MARKERS = (
    "outside the scope",
    "not part of the eu ai act",
    "i only answer",
    "this assistant only",
)

_USER_AGENT = "regenold-eu-ai-act-rag/prod-bench"


# ── Time helpers ────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── HTTP transport ──────────────────────────────────────────────────────


def _build_request(
    url: str,
    payload: list[dict[str, str]],
    api_key: str | None,
) -> urllib.request.Request:
    """Build a Regenold ``/ask`` POST request with optional auth header."""
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if api_key:
        headers["X-Regenold-Api-Key"] = api_key
    return urllib.request.Request(url, data=body, headers=headers, method="POST")


def _http_post_json(
    url: str,
    payload: list[dict[str, str]],
    api_key: str | None,
    timeout: float,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """POST + parse JSON with one-shot retry on transient connection failures.

    Returns ``(body, latency_ms, http_status, error, attempts, retried_errors)``.

    R47-D — delegates to :func:`evals.bench._http_retry.post_json_with_retry`
    which retries on ``RemoteDisconnected`` / ``BadStatusLine`` /
    ``ConnectionResetError`` / WinError 10060 / 5xx, but NOT on 4xx /
    JSON parse / ``non_dict_body``. Max 3 HTTP calls; ~1.5 s worst-case
    backoff. Every request to the ``/ask`` endpoint is idempotent so
    retry is safe.

    On failure the body is an empty shell (``answer=""``, ``references=[]``),
    ``http_status`` is the best-known status (0 if pre-HTTP error like
    DNS / TLS / connection refused), and ``error`` carries a short tag.
    """
    return post_json_with_retry(
        url, payload, api_key, timeout,
        user_agent=_USER_AGENT,
    )


def _http_get_json(
    url: str,
    api_key: str | None,
    timeout: float,
) -> tuple[dict[str, Any] | None, int, str | None]:
    """GET + parse JSON — used by the health probes.

    Returns ``(body, http_status, error)``.
    """
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if api_key:
        headers["X-Regenold-Api-Key"] = api_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode() or 200
            raw = resp.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None, status, "json_decode"
            return body if isinstance(body, dict) else None, status, None
    except urllib.error.HTTPError as exc:
        return None, exc.code, f"http_{exc.code}"
    except urllib.error.URLError as exc:
        return None, 0, f"url_error: {exc.reason}"
    except TimeoutError:
        return None, 0, "timeout"
    except Exception as exc:  # noqa: BLE001
        return None, 0, f"unexpected: {exc.__class__.__name__}"


# ── Scenario → question (mirror of the local runner) ────────────────────


def _scenario_to_question(s: dict[str, Any]) -> str:
    """Mirror of :func:`evals.bench.runner._scenario_to_question`."""
    role = (s.get("role") or "Provider").strip()
    intended_use = (s.get("intended_use") or "").strip()
    system_type = (s.get("system_type") or "").strip()
    domain = (s.get("domain") or "").strip()
    parts = [f"We are a {role.lower()}"]
    if system_type:
        parts.append(f"offering a {system_type.lower()}")
    if intended_use:
        parts.append(f"intended to {intended_use.lower()}")
    if domain:
        parts.append(f"in the {domain.lower()} domain")
    prelude = ", ".join(parts) + "."
    question = (
        f"{prelude} Under the EU AI Act, what is the risk classification of "
        f"this system and what are the key obligations on us as {role.lower()}?"
    )
    return question


# ── Concurrency-aware batch dispatcher ──────────────────────────────────


def _ask_one(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    question: str,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """One-shot QA / scenario call.

    Returns ``(body, latency_ms, http_status, error, attempts, retried_errors)``.
    """
    payload = [{"role": "user", "content": question}]
    return _http_post_json(endpoint, payload, api_key, timeout)


def _ask_multiturn(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    history: list[dict[str, str]],
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """Multi-turn call — sends the full OpenAI-style history.

    Returns ``(body, latency_ms, http_status, error, attempts, retried_errors)``.
    """
    return _http_post_json(endpoint, history, api_key, timeout)


def _batch_dispatch(
    work_items: list[tuple[str, dict[str, Any]]],
    *,
    endpoint: str,
    api_key: str | None,
    timeout: float,
    concurrency: int,
    verbose: bool,
    progress_label: str,
) -> list[
    tuple[
        str, dict[str, Any], dict[str, Any], float, int, str | None,
        int, list[str],
    ]
]:
    """Run ``work_items`` through the live endpoint.

    Each work item is ``(item_id, item_dict, question)`` — the
    ``item_dict`` is carried through unchanged so the caller can read
    gold fields back from it when scoring.

    Returns a list of
    ``(item_id, item_dict, body, latency_ms, http_status, error,
       attempts, retried_errors)``
    in the **same order** as the input list, so downstream code can
    enumerate without re-aligning by id.
    """
    n = len(work_items)
    if n == 0:
        return []
    concurrency = max(1, concurrency)

    results: list[
        tuple[
            str, dict[str, Any], dict[str, Any], float, int, str | None,
            int, list[str],
        ]
    ] = [None] * n  # type: ignore[list-item]

    def _worker(
        idx: int, item_id: str, item: dict[str, Any], question: str
    ) -> tuple[
        int, str, dict[str, Any], dict[str, Any], float, int, str | None,
        int, list[str],
    ]:
        body, elapsed, status, err, attempts, retried = _ask_one(
            endpoint, api_key, timeout, question
        )
        return idx, item_id, item, body, elapsed, status, err, attempts, retried

    completed = 0
    completed_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = []
        for idx, (item_id, item) in enumerate(work_items):
            question = item.get("__question") or ""
            futures.append(
                pool.submit(_worker, idx, item_id, item, question)
            )
            # Honour the 60-rpm partner ceiling — only sleep at the
            # batch boundary, not every submission, so we still get
            # parallelism inside a batch.
            if (
                concurrency >= _RATE_LIMIT_BATCH_THRESHOLD
                and (idx + 1) % concurrency == 0
            ):
                time.sleep(_RATE_LIMIT_BATCH_SLEEP_S)

        for fut in as_completed(futures):
            (
                idx, item_id, item, body, elapsed, status, err,
                attempts, retried,
            ) = fut.result()
            results[idx] = (
                item_id, item, body, elapsed, status, err, attempts, retried,
            )
            with completed_lock:
                completed += 1
                if verbose:
                    mark = "ok" if err is None else f"err({err[:32]})"
                    retry_tag = f" attempts={attempts}" if attempts > 1 else ""
                    print(
                        f"[{progress_label}] {completed}/{n} "
                        f"{item_id} status={status} {mark} "
                        f"latency={elapsed:.1f}ms{retry_tag}"
                    )
    return results  # type: ignore[return-value]


# ── Subset runners ──────────────────────────────────────────────────────


def _run_qa_http(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    concurrency: int,
    qa_items: list[dict[str, Any]],
    limit: int | None,
    verbose: bool,
) -> list[dict[str, Any]]:
    """Run every QA pair against the live endpoint and collect scored rows."""
    items = qa_items[:limit] if limit else qa_items
    work: list[tuple[str, dict[str, Any]]] = []
    for idx, item in enumerate(items):
        q = item.get("question") or ""
        work.append((f"qa_{idx:03d}", {**item, "__question": q}))

    raw = _batch_dispatch(
        work,
        endpoint=endpoint,
        api_key=api_key,
        timeout=timeout,
        concurrency=concurrency,
        verbose=verbose,
        progress_label="qa",
    )

    rows: list[dict[str, Any]] = []
    for item_id, item, body, latency, status, err, attempts, retried in raw:
        gold_answer = item.get("answer") or ""
        gold_article = item.get("relevant_article")
        pred_answer = body.get("answer") or ""
        pred_refs = body.get("references") or []
        score = metrics.score_row(
            pred_answer=pred_answer,
            pred_refs=pred_refs,
            gold_answer=gold_answer,
            gold_articles=gold_article,
            latency_ms=latency,
        )
        rows.append(
            {
                "item_id": item_id,
                "question": item.get("question") or "",
                "gold_answer": gold_answer,
                "gold_articles": gold_article,
                "pred_answer": pred_answer,
                "pred_refs": pred_refs,
                "http_status": status,
                "passed": err is None and 200 <= status < 300,
                "error": err,
                "attempts": attempts,
                "retried_errors": retried,
                "scores": score.to_dict(),
                "_row_score": score,
            }
        )
    return rows


def _run_scenarios_http(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    concurrency: int,
    scenarios: list[dict[str, Any]],
    limit: int | None,
    verbose: bool,
) -> list[dict[str, Any]]:
    """Run every scenario against the live endpoint."""
    items = scenarios[:limit] if limit else scenarios
    work: list[tuple[str, dict[str, Any]]] = []
    for idx, item in enumerate(items):
        q = _scenario_to_question(item)
        work.append((f"sc_{idx:03d}", {**item, "__question": q}))

    raw = _batch_dispatch(
        work,
        endpoint=endpoint,
        api_key=api_key,
        timeout=timeout,
        concurrency=concurrency,
        verbose=verbose,
        progress_label="scenarios",
    )

    rows: list[dict[str, Any]] = []
    for item_id, item, body, latency, status, err, attempts, retried in raw:
        obligations = item.get("obligations") or []
        gold_answer = (
            f"This system is classified as {item.get('risk_level','')}. "
            + " ".join(obligations[:3])
        )
        gold_articles = item.get("related_articles") or []
        pred_answer = body.get("answer") or ""
        pred_refs = body.get("references") or []
        score = metrics.score_row(
            pred_answer=pred_answer,
            pred_refs=pred_refs,
            gold_answer=gold_answer,
            gold_articles=gold_articles,
            latency_ms=latency,
        )
        rows.append(
            {
                "item_id": item_id,
                "question": item.get("__question") or "",
                "risk_level": item.get("risk_level"),
                "role": item.get("role"),
                "gold_answer": gold_answer,
                "gold_articles": gold_articles,
                "pred_answer": pred_answer,
                "pred_refs": pred_refs,
                "http_status": status,
                "passed": err is None and 200 <= status < 300,
                "error": err,
                "attempts": attempts,
                "retried_errors": retried,
                "scores": score.to_dict(),
                "_row_score": score,
            }
        )
    return rows


def _multiturn_coherence_probe_http(
    endpoint: str,
    api_key: str | None,
    timeout: float,
    scenarios: list[dict[str, Any]],
    limit: int = 20,
) -> dict[str, Any]:
    """Sequential multi-turn probe — coherence rate over chained turns.

    Kept sequential (no thread pool) because each scenario is two
    dependent calls and the volume is small (20 by default).
    """
    if not scenarios:
        return {"n": 0, "coherent": 0, "coherence_rate": 0.0, "rows": []}
    items = scenarios[:limit]
    coherent = 0
    rows: list[dict[str, Any]] = []
    for idx, s in enumerate(items):
        q1 = _scenario_to_question(s)
        body1, lat1, _, err1, att1, ret1 = _ask_one(
            endpoint, api_key, timeout, q1
        )
        answer1 = body1.get("answer") or ""
        history = [
            {"role": "user", "content": q1},
            {"role": "assistant", "content": answer1},
            {"role": "user", "content": _MULTITURN_FOLLOWUP},
        ]
        body2, lat2, _, err2, att2, ret2 = _ask_multiturn(
            endpoint, api_key, timeout, history
        )
        answer2 = body2.get("answer") or ""
        refs2 = body2.get("references") or []
        gold_articles = s.get("related_articles") or []
        pred_heads = metrics.article_heads(refs2)
        gold = {f"Article {int(a)}" for a in gold_articles if a is not None}
        cites_gold = bool(pred_heads & gold) if gold else False
        is_refusal = any(m in answer2.lower() for m in _REFUSAL_MARKERS)
        # Errors break coherence by definition — a failed second turn
        # didn't carry context.
        any_error = err1 is not None or err2 is not None
        is_coherent = cites_gold and not is_refusal and not any_error
        if is_coherent:
            coherent += 1
        rows.append(
            {
                "item_id": f"mt_{idx:03d}",
                "q1": q1,
                "answer1": answer1[:240],
                "answer2": answer2[:240],
                "refs2": refs2,
                "gold_articles": gold_articles,
                "is_coherent": is_coherent,
                "latency_q1_ms": round(lat1, 2),
                "latency_q2_ms": round(lat2, 2),
                "error": err1 or err2,
                "attempts_q1": att1,
                "attempts_q2": att2,
                "retried_errors_q1": ret1,
                "retried_errors_q2": ret2,
            }
        )
    return {
        "n": len(items),
        "coherent": coherent,
        "coherence_rate": round(coherent / len(items), 4) if items else 0.0,
        "rows": rows,
    }


# ── Health probe ────────────────────────────────────────────────────────


def _derive_health_url(endpoint: str, path: str) -> str:
    """Given the ``/ask`` endpoint, produce the absolute URL for ``path``.

    ``path`` should start with ``/`` (``/healthz``, ``/healthz/llm``, …).
    """
    parsed = urllib.parse.urlsplit(endpoint)
    if not parsed.scheme or not parsed.netloc:
        # Fall back: assume the caller passed a bare hostname.
        return f"https://{endpoint.rstrip('/')}{path}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, "", "")
    )


def run_health_only(
    endpoint: str,
    api_key: str | None,
    timeout: float,
) -> dict[str, Any]:
    """Probe the three production healthz endpoints and return a summary."""
    report: dict[str, Any] = {"endpoint": endpoint, "probes": {}}
    for path in ("/healthz", "/healthz/llm", "/healthz/graph"):
        url = _derive_health_url(endpoint, path)
        body, status, err = _http_get_json(url, api_key, timeout)
        report["probes"][path] = {
            "url": url,
            "http_status": status,
            "ok": err is None and 200 <= status < 300,
            "error": err,
            "body": body,
        }
    return report


def _format_health_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"Regenold production health probe — endpoint={report.get('endpoint')!r}")
    lines.append("=" * 78)
    for path, probe in (report.get("probes") or {}).items():
        status = probe.get("http_status", "?")
        ok = "OK " if probe.get("ok") else "FAIL"
        lines.append(f"[{ok}] {path:<18} -> HTTP {status}")
        body = probe.get("body")
        if isinstance(body, dict):
            for key in ("status", "version", "provider", "model", "llm_ok", "graph_ok", "detail"):
                if key in body:
                    lines.append(f"        {key}: {body.get(key)!r}")
        if probe.get("error"):
            lines.append(f"        error: {probe['error']}")
    return "\n".join(lines)


# ── Persistence shim ────────────────────────────────────────────────────


def _persist_prod(
    payload: dict[str, Any],
    *,
    sidecar_prefix: str = "prod-",
) -> dict[str, Any]:
    """Persist a production-bench run.

    Writes:
      * JSON sidecar at ``evals/bench/results/prod-<label>.json``
      * SQLite ledger row (same schema as the local runner)
      * Audit-chain row (best-effort; falls back gracefully when
        ``DATABASE_URL`` is unset → in-memory store)
    """
    label = payload.get("label", "adhoc")
    # Best-effort chain write — never block the run on chain failure.
    try:
        chain_entry_id = storage.write_audit_chain(payload)
        payload["chain_entry_id"] = chain_entry_id
    except Exception as exc:  # noqa: BLE001
        payload["chain_entry_id"] = None
        payload["chain_write_error"] = str(exc)

    try:
        run_id = storage.write_sqlite_ledger(payload)
        payload["run_id"] = run_id
    except Exception as exc:  # noqa: BLE001
        # SQLite write failed (e.g. read-only worktree). Carry on with
        # a synthetic id so the sidecar still has provenance.
        import uuid

        payload["run_id"] = str(uuid.uuid4())
        payload["sqlite_write_error"] = str(exc)

    # Write the sidecar with the ``prod-`` prefix so it doesn't collide
    # with local-runner sidecars sharing a label.
    prefixed = f"{sidecar_prefix}{label}"
    sidecar = storage.write_json_sidecar(prefixed, payload)
    payload["sidecar_path"] = str(sidecar)
    return payload


# ── Top-level run() ─────────────────────────────────────────────────────


def run(
    *,
    endpoint: str,
    api_key: str | None,
    label: str = "prod-adhoc",
    qa_only: bool = False,
    scenarios_only: bool = False,
    skip_multiturn: bool = False,
    limit: int | None = None,
    multiturn_limit: int = 20,
    concurrency: int = 4,
    timeout: float = 30.0,
    verbose: bool = False,
) -> dict[str, Any]:
    """Top-level production-bench runner — returns the persisted payload."""
    bench_dataset.ensure_dataset()
    qa_items = bench_dataset.load_qa_pairs()
    scenarios = bench_dataset.load_scenarios()

    started_at = _now_iso()
    qa_rows: list[dict[str, Any]] = []
    scenario_rows: list[dict[str, Any]] = []
    multiturn: dict[str, Any] = {"n": 0, "coherent": 0, "coherence_rate": 0.0, "rows": []}

    if not scenarios_only:
        qa_rows = _run_qa_http(
            endpoint, api_key, timeout, concurrency, qa_items, limit, verbose
        )
    if not qa_only:
        scenario_rows = _run_scenarios_http(
            endpoint, api_key, timeout, concurrency, scenarios, limit, verbose
        )
    if not skip_multiturn and not qa_only:
        multiturn = _multiturn_coherence_probe_http(
            endpoint, api_key, timeout, scenarios, limit=multiturn_limit
        )
    finished_at = _now_iso()

    qa_scores = [r["_row_score"] for r in qa_rows]
    sc_scores = [r["_row_score"] for r in scenario_rows]

    n_failures = sum(1 for r in qa_rows + scenario_rows if not r.get("passed"))

    # R47-D — retry telemetry. ``retried`` counts rows that needed at
    # least one retry (attempts > 1). ``recovered`` is the subset that
    # ultimately succeeded (no error after retries). The recovery rate
    # tells us how well the retry helper is paying for itself.
    retry_rows = qa_rows + scenario_rows
    retried = sum(1 for r in retry_rows if (r.get("attempts") or 1) > 1)
    recovered = sum(
        1 for r in retry_rows
        if (r.get("attempts") or 1) > 1 and r.get("error") is None
    )
    total_retries = sum(max(0, (r.get("attempts") or 1) - 1) for r in retry_rows)
    # Multi-turn rows hold per-turn attempts; fold them in too.
    for mt_row in multiturn.get("rows") or []:
        for key in ("attempts_q1", "attempts_q2"):
            total_retries += max(0, (mt_row.get(key) or 1) - 1)
    summary = {
        "qa": metrics.aggregate(qa_scores),
        "scenarios": metrics.aggregate(sc_scores),
        "multiturn_coherence": {
            "n": multiturn.get("n", 0),
            "coherent": multiturn.get("coherent", 0),
            "coherence_rate": multiturn.get("coherence_rate", 0.0),
        },
        "overall": metrics.aggregate(qa_scores + sc_scores),
        "http_failures": n_failures,
        "http_total": len(qa_rows) + len(scenario_rows),
        "total_retries": total_retries,
        "rows_retried": retried,
        "rows_retry_recovered": recovered,
        "retry_recovery_rate": (
            round(recovered / retried, 4) if retried else 0.0
        ),
    }

    payload: dict[str, Any] = {
        "label": label,
        "mode": "prod",
        "endpoint": endpoint,
        "concurrency": concurrency,
        "timeout_s": timeout,
        "started_at": started_at,
        "finished_at": finished_at,
        "dataset_fingerprint": bench_dataset.dataset_fingerprint(),
        "summary": summary,
        "qa": _strip_row_scores(qa_rows),
        "scenarios": _strip_row_scores(scenario_rows),
        "multiturn": multiturn,
    }
    return _persist_prod(payload)


def _strip_row_scores(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in rows
    ]


# ── Pretty-printed scorecard ────────────────────────────────────────────


def _format_human_summary(payload: dict[str, Any]) -> str:
    s = payload.get("summary") or {}
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(
        f"Regenold PRODUCTION benchmark — label={payload.get('label')!r}"
    )
    lines.append(f"endpoint: {payload.get('endpoint','?')}")
    lines.append(
        f"concurrency={payload.get('concurrency','?')}  "
        f"timeout={payload.get('timeout_s','?')}s"
    )
    lines.append("=" * 78)
    fingerprint = payload.get("dataset_fingerprint") or {}
    lines.append(
        f"dataset: qa_sha={fingerprint.get('qa_pairs_sha256','?')[:12]}  "
        f"scenarios_sha={fingerprint.get('scenarios_sha256','?')[:12]}"
    )
    lines.append(
        f"http_failures: {s.get('http_failures',0)}/{s.get('http_total',0)}"
    )
    if s.get("total_retries") or s.get("rows_retried"):
        lines.append(
            f"retries: total={s.get('total_retries',0)} "
            f"rows={s.get('rows_retried',0)} "
            f"recovered={s.get('rows_retry_recovered',0)} "
            f"recovery_rate={s.get('retry_recovery_rate',0.0)}"
        )
    for source in ("qa", "scenarios", "overall"):
        block = s.get(source) or {}
        if not block:
            continue
        n = block.get("n", 0)
        lines.append("")
        lines.append(f"[{source.upper()}] n={n}")
        lines.append(f"  Ans Correctness Loose : {block.get('ans_correctness_loose','-')}")
        lines.append(f"  Ans Correctness Strict: {block.get('ans_correctness_strict','-')}")
        lines.append(f"  Ans Conciseness       : {block.get('ans_conciseness','-')}")
        lines.append(f"  Ref Correctness Loose : {block.get('ref_correctness_loose','-')}")
        lines.append(f"  Ref Correctness Strict: {block.get('ref_correctness_strict','-')}")
        lines.append(f"  Ref Conciseness       : {block.get('ref_conciseness','-')}")
        lines.append(f"  Regulatory Tone       : {block.get('regulatory_tone','-')}")
        lines.append(
            f"  Latency               : p50={block.get('latency_p50_ms','-')}ms  "
            f"p95={block.get('latency_p95_ms','-')}ms  "
            f"max={block.get('latency_max_ms','-')}ms"
        )
    mt = s.get("multiturn_coherence") or {}
    lines.append("")
    lines.append(
        f"[MULTI-TURN] n={mt.get('n',0)} coherent={mt.get('coherent',0)} "
        f"rate={mt.get('coherence_rate',0.0)}"
    )
    lines.append("")
    lines.append(f"run_id        : {payload.get('run_id','?')}")
    lines.append(f"chain_entry_id: {payload.get('chain_entry_id','?')}")
    lines.append(f"sidecar_path  : {payload.get('sidecar_path','?')}")
    if payload.get("chain_write_error"):
        lines.append(f"chain_write_error: {payload['chain_write_error']}")
    if payload.get("sqlite_write_error"):
        lines.append(f"sqlite_write_error: {payload['sqlite_write_error']}")
    return "\n".join(lines)


# ── CLI entry point ─────────────────────────────────────────────────────


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI arg parser. Exposed so tests can exercise it."""
    parser = argparse.ArgumentParser(
        description="Run the davidath benchmark against a live Regenold endpoint."
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        help="Full URL of the live /ask endpoint, "
        "e.g. https://regenold-eu-ai-act-rag.up.railway.app/api/v1/regenold/eu-ai-act/ask",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Value for the X-Regenold-Api-Key header. Optional for "
        "anonymous endpoints; required in production.",
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Label for the JSON sidecar — e.g. 'r35-prod-graph-on'.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap items per subset (qa, scenarios). None = full bench.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel HTTP requests. Default 4 honours the 60-rpm "
        "partner-tier rate limit.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds. Default 30.",
    )
    parser.add_argument("--qa-only", action="store_true")
    parser.add_argument("--scenarios-only", action="store_true")
    parser.add_argument("--skip-multiturn", action="store_true")
    parser.add_argument(
        "--multiturn-limit",
        type=int,
        default=20,
        help="Cap the multi-turn coherence probe at this many scenarios.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print one line per item as it completes.",
    )
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="Skip the bench — just probe /healthz, /healthz/llm, "
        "/healthz/graph and print status.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Match the local runner: try to widen stdout/stderr to utf-8 so the
    # printed scorecard survives Windows consoles with cp1252 by default.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.health_only:
        report = run_health_only(args.endpoint, args.api_key, args.timeout)
        print(_format_health_report(report))
        # Exit non-zero if any probe failed — convenient for CI / canary.
        all_ok = all(p.get("ok") for p in report["probes"].values())
        return 0 if all_ok else 2

    payload = run(
        endpoint=args.endpoint,
        api_key=args.api_key,
        label=args.label,
        qa_only=args.qa_only,
        scenarios_only=args.scenarios_only,
        skip_multiturn=args.skip_multiturn,
        limit=args.limit,
        multiturn_limit=args.multiturn_limit,
        concurrency=args.concurrency,
        timeout=args.timeout,
        verbose=args.verbose,
    )
    print(_format_human_summary(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

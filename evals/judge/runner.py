"""R50 — LLM-as-Judge runner. R66-C — retry-on-timeout + Anthropic SDK direct.

Reads a bench JSON sidecar (from ``evals.bench.runner`` or
``evals.regenold.runner_v2``) and grades each row across 4 axes
(correctness, refs, conciseness, tone) via Sonnet 4.6 calls. Writes a
judge sidecar ``evals/bench/results/judge-<label>.json`` with per-row
verdicts and per-axis aggregates.

Stdlib + same-package imports only.

CLI:
    python -m evals.judge.runner --bench-sidecar evals/bench/results/v2-r49-live.json \
                                 --label r49-live \
                                 --rows-limit 10 \
                                 --provider wrapper \
                                 --verbose

R66-C — reliability hardening
-----------------------------
Pre-R66-C, ~11+ wrapper timeouts per full V2 run were poisoning judge
accuracy: each timeout marked a row ``judge_error`` and counted as
"unknown" in the per-axis aggregator. 11 errors on a 56-row run drop
pass-rate visibility by ~20% spurious. Three independent fixes:

1. **Retry-on-timeout** (always-on, 1 retry per axis call with 1s
   backoff): wraps each axis call in ONE retry for transient
   timeout / connection-reset / network failures. Parse errors and
   content-shape failures are deterministic — never retried.
2. **--provider anthropic** flag: opt-in route through the Anthropic
   SDK directly instead of the local openai_wrapper bridge.
   Eliminates the wrapper-as-bottleneck failure mode (the wrapper
   itself can be the source of timeouts under load); the SDK direct
   path has stable cloud-side rate-limit behaviour.
3. **Default concurrency dropped 4 → 2**: the wrapper's rate-limit
   gate (slowapi default 10 req/min) thrashes at 4 concurrent
   axes/row. Two is the sweet spot for wrapper-mode runs; operators
   on the Anthropic-SDK path can raise it back to 4-8 if desired.

Concurrency: ThreadPoolExecutor (4 axes × N rows). The openai_wrapper
provider is httpx-based + thread-safe; the Anthropic SDK is similarly
safe for concurrent ``messages.create`` calls from one client.

Stops cleanly on wrapper outage — every judge call is wrapped so a
single 429 / network failure doesn't kill the run; the row is marked
``judge_error`` with the failure reason and the aggregator counts it
as 'unknown' on that axis.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from evals.judge.prompts import AXES, render

# ── Article-summary lookup (for the refs-faithfulness prompt) ───────────


def _load_article_summaries() -> dict[str, str]:
    """Build a dict from user-facing ref form (``Article N`` / ``Annex X``)
    to the article's KB summary, used to prime the refs-faithfulness
    judge prompt.

    Maps both ``Art. N`` (internal) and ``Article N`` (user-facing).
    """
    from app.data.kb import EC_CHECKER_OBLIGATION_MAP  # local import — heavy
    out: dict[str, str] = {}
    for internal_ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        if isinstance(entry, dict):
            summary = entry.get("summary") or ""
        else:
            summary = getattr(entry, "summary", "") or ""
        if not summary:
            continue
        # internal form (e.g. "Art. 13")
        out[internal_ref] = summary
        # user-facing form (e.g. "Article 13")
        if internal_ref.startswith("Art. "):
            out["Article " + internal_ref[len("Art. "):]] = summary
        elif internal_ref.startswith("Annex "):
            out[internal_ref] = summary  # already user-facing
    return out


# ── Retry classification (R66-C) ────────────────────────────────────────


_JUDGE_SYSTEM = (
    "You are an expert legal evaluator for EU AI Act Q&A systems. "
    "Respond with ONE JSON object only — no preamble, no markdown fences, "
    "no explanation outside the JSON."
)

# Default judge model — overridable via the CLI ``--model`` flag.
# ``claude-sonnet-4-6`` is the historical default the R66-C pipeline
# was tuned against; operators wanting a stronger (and more expensive)
# judge can pass ``--model claude-opus-4-7`` for runs where the
# additional reasoning quality is worth the extra latency + spend.
_DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"
_JUDGE_MODEL: str = _DEFAULT_JUDGE_MODEL


def set_judge_model(model: str) -> None:
    """Module-level override for the judge model. Called by ``main`` from
    the CLI ``--model`` flag before any judge call fires. Goes through a
    helper rather than direct global assignment so future tests can
    monkey-patch the same surface."""
    global _JUDGE_MODEL
    _JUDGE_MODEL = (model or _DEFAULT_JUDGE_MODEL).strip()


# Retryable failure SHAPES (judge_error string fragments). Mirrors the
# pattern from ``evals/bench/_http_retry.py::is_retryable_error``: only
# transient connection-layer / timeout failures are retryable. Parse
# errors and content-shape failures are deterministic and indicate a
# prompt mismatch — retrying would burn token budget for no recovery.
_RETRYABLE_ERROR_SUBSTRINGS: tuple[str, ...] = (
    "wrapper_returned_none",          # provider returned None — usually transient
    "timeout",                         # any "timeout" mention (call_failed, network_error)
    "timed out",
    "connect",                         # "connection refused", "connection reset", etc.
    "transport",                       # httpx transport errors
    "remote disconnected",
    "remotedisconnected",
    "connectionreseterror",
    "connection_reset",
    "incompleteread",
    "badstatusline",
    "network_error",
    "rate_limit",                      # 429 — wrapper handles inline but SDK path bubbles up
    "ratelimit",
    "api_status_5",                    # api_status_5XX
    "api_status_429",                  # 429 from wrapper after its own retry exhausted
)

# Hard non-retryable failure shapes. These are always content-shape /
# config bugs; retrying never helps.
_NON_RETRYABLE_ERROR_SUBSTRINGS: tuple[str, ...] = (
    "wrapper_unavailable",            # SDK import failure / module missing
    "wrapper_not_configured",         # env not set
    "no_json",                         # the model returned text without a { ... } block
    "parse_failed",                    # JSON existed but failed to parse
    "unbalanced_json",                 # opening { without matching }
    "empty_response",                  # the model returned empty text
    "sdk_unavailable",                 # anthropic SDK missing
    "no_api_key",                      # no key configured
    "authentication",                  # 401/403 from upstream
    "permission",                      # 403 from upstream
)


def is_retryable_judge_error(error_message: str) -> bool:
    """Classify a ``judge_error`` string as retryable or not.

    Retryable = transient connection / network / timeout failure where
    a one-shot retry is likely to recover. Non-retryable = deterministic
    content-shape or config failure where retry burns budget for no
    benefit.

    Precedence rule: non-retryable substrings WIN over retryable
    substrings — if both fire, the deterministic classification wins.
    (E.g. ``"wrapper_error: auth timeout fail"`` is auth, not timeout.)
    """
    if not error_message:
        return False
    lower = error_message.lower()
    # Non-retryable wins on collision.
    for marker in _NON_RETRYABLE_ERROR_SUBSTRINGS:
        if marker in lower:
            return False
    for marker in _RETRYABLE_ERROR_SUBSTRINGS:
        if marker in lower:
            return True
    return False


# ── Judge call — wrapper path ───────────────────────────────────────────


def _call_judge_sonnet(prompt: str, timeout_s: float = 30.0) -> dict[str, Any]:
    """Send the judge prompt through the openai_wrapper provider and
    parse the model's JSON response. Returns the parsed dict on
    success, or ``{"judge_error": "..."}`` on any failure.

    The wrapper handles auth + 429 retry-after upstream; this function
    just unwraps the response and parses the model's JSON.
    """
    try:
        from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
            OpenAIWrapperRequest,
            get_openai_wrapper_provider,
            is_openai_wrapper_enabled,
        )
    except Exception as exc:  # noqa: BLE001
        return {"judge_error": f"wrapper_unavailable: {exc}"}
    if not is_openai_wrapper_enabled():
        return {"judge_error": "wrapper_not_configured"}
    provider = get_openai_wrapper_provider()
    req = OpenAIWrapperRequest(
        system=_JUDGE_SYSTEM,
        user=prompt,
        model=_JUDGE_MODEL,
        max_tokens=400,
        temperature=0.0,
        timeout_seconds=timeout_s,
    )
    try:
        resp = provider.complete(req)
    except Exception as exc:  # noqa: BLE001
        return {"judge_error": f"call_failed: {exc}"}
    if resp is None:
        return {"judge_error": "wrapper_returned_none"}
    if resp.error:
        return {"judge_error": f"wrapper_error: {resp.error[:160]}"}
    return _parse_judge_json(resp.text or "")


# ── Judge call — Anthropic SDK direct path (R66-C) ──────────────────────


def _call_judge_anthropic(prompt: str, timeout_s: float = 30.0) -> dict[str, Any]:
    """Send the judge prompt through the Anthropic SDK directly.

    The SDK direct path bypasses the local openai_wrapper bridge — it
    talks to ``api.anthropic.com`` over the official client and gets
    stable cloud-side rate-limit behaviour. Use when the local wrapper
    is the source of timeouts under load (e.g. its slowapi gate at
    ``RATE_LIMIT_CHAT_PER_MINUTE=10`` thrashes the judge's 4-axis
    concurrency).

    Returns the parsed JSON dict on success, or
    ``{"judge_error": "..."}`` on every failure mode. Never raises.

    Reads ``P2P_GRAPH_RAG_API_KEY`` first, then ``ANTHROPIC_API_KEY`` —
    the project uses ``P2P_GRAPH_RAG_API_KEY`` per CLAUDE.md Round 56,
    but the latter is the standard SDK env var so operators with a
    pre-existing ``ANTHROPIC_API_KEY`` get a free path.
    """
    api_key = (
        os.getenv("P2P_GRAPH_RAG_API_KEY", "").strip()
        or os.getenv("ANTHROPIC_API_KEY", "").strip()
    )
    if not api_key:
        return {"judge_error": "no_api_key: set P2P_GRAPH_RAG_API_KEY or ANTHROPIC_API_KEY"}

    try:
        import anthropic  # noqa: PLC0415 — lazy import per CLAUDE.md
    except ImportError as exc:
        return {"judge_error": f"sdk_unavailable: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"judge_error": f"sdk_unavailable: {exc}"}

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001
        return {"judge_error": f"sdk_init_failed: {exc}"[:200]}

    try:
        response = client.messages.create(
            model=_JUDGE_MODEL,
            system=_JUDGE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft contract
        # The SDK raises typed exceptions (RateLimitError,
        # AuthenticationError, APIConnectionError, APITimeoutError,
        # APIStatusError, ...). Classify via class name so the retry
        # gate sees the right substring.
        exc_name = type(exc).__name__
        msg = str(exc)[:200]
        if "RateLimit" in exc_name:
            return {"judge_error": f"rate_limit: {msg}"}
        if "Authentication" in exc_name:
            return {"judge_error": f"authentication: {msg}"}
        if "Permission" in exc_name:
            return {"judge_error": f"permission: {msg}"}
        if "Timeout" in exc_name or "timed out" in msg.lower():
            return {"judge_error": f"timeout: {msg}"}
        if "Connection" in exc_name or "transport" in msg.lower():
            return {"judge_error": f"transport: {msg}"}
        return {"judge_error": f"call_failed: {exc_name}: {msg}"}

    try:
        if not getattr(response, "content", None):
            return {"judge_error": "empty_response: no content blocks"}
        block = response.content[0]
        text = getattr(block, "text", "") or ""
    except Exception as exc:  # noqa: BLE001
        return {"judge_error": f"response_parse_failed: {exc}"[:200]}

    return _parse_judge_json(text)


# ── JSON parsing ────────────────────────────────────────────────────────


def _parse_judge_json(text: str) -> dict[str, Any]:
    """Extract the first balanced JSON object from ``text``. The
    prompts ask for "ONE JSON object only" but Sonnet occasionally
    wraps in markdown fences or prepends a thinking sentence."""
    if not text:
        return {"judge_error": "empty_response"}
    # Strip a code fence if present
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json\n"):
            s = s[5:]
    # Find first { ... } balanced
    start = s.find("{")
    if start < 0:
        return {"judge_error": "no_json", "raw": text[:200]}
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                blob = s[start:i + 1]
                try:
                    return json.loads(blob)
                except Exception as exc:  # noqa: BLE001
                    return {"judge_error": f"parse_failed: {exc}", "raw": blob[:200]}
    return {"judge_error": "unbalanced_json", "raw": text[:200]}


# ── Retry wrapper around a single-axis judge call (R66-C) ───────────────


def _call_judge_with_retry(
    caller: Callable[[str], dict[str, Any]],
    prompt: str,
    *,
    max_retries: int = 1,
    backoff_s: float = 1.0,
) -> tuple[dict[str, Any], int, list[str]]:
    """Invoke ``caller(prompt)`` and retry once on retryable failures.

    Returns a tuple ``(result, attempts, retried_errors)`` where:

    * ``result`` is the final dict returned by ``caller`` — either a
      parsed JSON verdict on success, or a ``{"judge_error": "..."}``
      payload on terminal failure.
    * ``attempts`` is 1 on first-try success or non-retryable failure;
      2 when a retry fired.
    * ``retried_errors`` lists the error strings of failed attempts that
      triggered a retry (empty when no retry happened, length=1 when
      one retry fired).

    Retry policy:

    * Maximum 1 retry per axis call (configurable via ``max_retries``
      for tests). The judge is ~$0.005/call; 2 retries × 4 axes × 56
      rows = 448 calls worst-case which is well within budget.
    * Backoff of 1.0 s between the first and second attempt (give the
      upstream a chance to recover from its slowapi gate / connection
      reset).
    * Classifies via :func:`is_retryable_judge_error` — only transient
      connection / timeout failures retry; parse errors / config gaps
      / auth errors don't.
    """
    retried_errors: list[str] = []
    attempts = 0
    last_result: dict[str, Any] = {}

    for retry_idx in range(max_retries + 1):
        attempts += 1
        last_result = caller(prompt)
        err = last_result.get("judge_error")
        if not err:
            # Happy path — return immediately.
            return last_result, attempts, retried_errors
        if not is_retryable_judge_error(str(err)):
            # Deterministic failure — stop.
            return last_result, attempts, retried_errors
        if retry_idx == max_retries:
            # Out of retry budget — record the final error.
            retried_errors.append(str(err))
            return last_result, attempts, retried_errors
        # Retryable + budget remaining — record + back off + loop.
        retried_errors.append(str(err))
        if backoff_s > 0:
            time.sleep(backoff_s)

    return last_result, attempts, retried_errors


# ── Per-row driver ──────────────────────────────────────────────────────


def _resolve_caller(provider: str) -> Callable[[str], dict[str, Any]]:
    """Pick the per-axis judge call function based on the CLI ``--provider``
    flag. Defaults to the wrapper path for backwards-compat."""
    if provider == "anthropic":
        return _call_judge_anthropic
    # "wrapper" or anything else falls back to the wrapper (historical
    # default) — runner_v2 / bench-runner sidecars produced pre-R66-C
    # all assume the wrapper path is active.
    return _call_judge_sonnet


def _judge_row(
    row: dict[str, Any],
    article_summaries: dict[str, str],
    caller: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Run all 4 axes on a single bench row. Returns the original row
    augmented with ``judge`` field containing per-axis verdicts.

    R66-C — each axis call is wrapped in :func:`_call_judge_with_retry`
    so transient timeouts / connection resets get a one-shot recovery
    attempt before the row is marked ``judge_error``.
    """
    verdicts: dict[str, Any] = {}
    row_retries: dict[str, list[str]] = {}
    for axis in AXES:
        prompt = render(axis, row, article_summaries=article_summaries)
        result, attempts, retried_errors = _call_judge_with_retry(caller, prompt)
        if retried_errors:
            # Attach retry telemetry to the per-axis verdict for the
            # sidecar so operators can audit which axes were rescued.
            result = dict(result)
            result["_attempts"] = attempts
            result["_retried_errors"] = retried_errors
            row_retries[axis] = retried_errors
        verdicts[axis] = result
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "verdicts": verdicts,
        "retried_axes": row_retries,  # empty {} when no axis was retried
    }


def _run_judge(
    rows: list[dict[str, Any]],
    concurrency: int,
    verbose: bool,
    provider: str,
) -> list[dict[str, Any]]:
    article_summaries = _load_article_summaries()
    caller = _resolve_caller(provider)
    out: list[dict[str, Any] | None] = [None] * len(rows)
    completed = 0
    lock = threading.Lock()

    def _worker(idx: int, row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return idx, _judge_row(row, article_summaries, caller)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_worker, i, r) for i, r in enumerate(rows)]
        for fut in as_completed(futures):
            idx, judged = fut.result()
            out[idx] = judged
            with lock:
                completed += 1
                if verbose:
                    summary = ", ".join(
                        f"{axis[:4]}={(judged['verdicts'].get(axis) or {}).get('verdict', '?')}"
                        for axis in AXES
                    )
                    # Defensive: multi-turn rows don't carry a ``category``
                    # field, so ``.get('category')`` returns None and the
                    # format string blows up. Coerce to a "-" string.
                    row_id = str(judged.get('id') or '?')
                    cat_str = str(judged.get('category') or 'multiturn')
                    retry_tag = ""
                    if judged.get("retried_axes"):
                        retry_tag = f" retry={len(judged['retried_axes'])}"
                    print(
                        f"[judge] {completed}/{len(rows)} {row_id:<14} "
                        f"cat={cat_str:<22} {summary}{retry_tag}",
                        flush=True,
                    )
    return [r for r in out if r is not None]


# ── Aggregation (per-axis pass rate + failure-mode buckets) ─────────────


def _aggregate_judge(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_axis: dict[str, dict[str, Any]] = {}
    for axis in AXES:
        total = len(rows)
        passes = 0
        fails = 0
        errors = 0
        modes: dict[str, int] = {}
        for r in rows:
            v = (r.get("verdicts") or {}).get(axis) or {}
            if v.get("judge_error"):
                errors += 1
                continue
            verdict = (v.get("verdict") or "").lower()
            if verdict == "pass":
                passes += 1
            elif verdict == "fail":
                fails += 1
                mode = (v.get("failure_mode") or "(unspecified)")[:80]
                modes[mode] = modes.get(mode, 0) + 1
            else:
                errors += 1
        # Top-N failure modes for the per-axis report
        top_modes = sorted(modes.items(), key=lambda kv: -kv[1])[:10]
        per_axis[axis] = {
            "n": total,
            "pass": passes,
            "fail": fails,
            "error": errors,
            "pass_rate": round(passes / total, 4) if total else 0.0,
            "top_failure_modes": top_modes,
        }
    return per_axis


def _aggregate_retries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """R66-C — summary of retry behaviour across the run.

    Reports:

    * ``total_retries`` — count of axis calls that fired at least one
      retry (1 retry per axis max per R66-C policy).
    * ``retried_axes`` — distribution of retry counts per axis name
      (axis label → count of rows where that axis retried).
    * ``retry_recovery_rate`` — fraction of retried calls that
      ultimately produced a non-error verdict. High = retries are
      paying for themselves; low = upstream is genuinely broken and
      retries are wasted budget.
    """
    total_retries = 0
    by_axis: dict[str, int] = {axis: 0 for axis in AXES}
    recovered = 0
    for r in rows:
        retried_axes = r.get("retried_axes") or {}
        verdicts = r.get("verdicts") or {}
        for axis, retried_errors in retried_axes.items():
            if not retried_errors:
                continue
            total_retries += 1
            if axis in by_axis:
                by_axis[axis] += 1
            v = verdicts.get(axis) or {}
            if not v.get("judge_error"):
                recovered += 1
    rate = round(recovered / total_retries, 4) if total_retries else 0.0
    return {
        "total_retries": total_retries,
        "retried_axes": by_axis,
        "retry_recovery_rate": rate,
        "retries_recovered": recovered,
    }


# ── Top-level ───────────────────────────────────────────────────────────


def run(
    *,
    bench_sidecar: Path,
    label: str,
    rows_limit: int | None = None,
    concurrency: int = 2,
    verbose: bool = False,
    provider: str = "wrapper",
    out_dir: Path | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = json.loads(bench_sidecar.read_text(encoding="utf-8"))

    # Flatten rows from the V2 sidecar (tricky + multiturn) OR the davidath
    # sidecar (qa + scenarios). We handle both shapes.
    rows: list[dict[str, Any]] = []
    for bucket_key in ("tricky", "multiturn", "qa", "scenarios", "rows"):
        bucket = payload.get(bucket_key)
        if isinstance(bucket, dict):
            rows.extend(bucket.get("rows") or [])
        elif isinstance(bucket, list):
            rows.extend(bucket)

    if rows_limit:
        rows = rows[:rows_limit]
    print(
        f"[judge] {len(rows)} rows × {len(AXES)} axes against {bench_sidecar.name} "
        f"(provider={provider}, concurrency={concurrency})",
        flush=True,
    )
    t0 = time.monotonic()
    judged = _run_judge(rows, concurrency, verbose, provider)
    elapsed_s = round(time.monotonic() - t0, 2)
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    aggregate = _aggregate_judge(judged)
    retries = _aggregate_retries(judged)

    if out_dir is None:
        out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"judge-{label}.json"
    summary = {
        "label": label,
        "source_sidecar": str(bench_sidecar),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_s": elapsed_s,
        "axes": list(AXES),
        "provider": provider,
        "concurrency": concurrency,
        "rows": judged,
        "aggregate": aggregate,
        "total_retries": retries["total_retries"],
        "retried_axes": retries["retried_axes"],
        "retry_recovery_rate": retries["retry_recovery_rate"],
        "retries_recovered": retries["retries_recovered"],
    }
    sidecar.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[judge] sidecar written to {sidecar}", flush=True)
    return summary


def _format(summary: dict[str, Any]) -> str:
    """Pretty-printer for the CLI."""
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"Judge run — label={summary['label']!r}")
    out.append(f"source: {summary['source_sidecar']}")
    out.append(
        f"provider={summary.get('provider', '?')} "
        f"concurrency={summary.get('concurrency', '?')}"
    )
    out.append(f"elapsed: {summary['elapsed_s']}s")
    total_retries = summary.get("total_retries", 0)
    if total_retries:
        out.append(
            f"retries: {total_retries} total "
            f"(recovered={summary.get('retries_recovered', 0)}, "
            f"recovery_rate={summary.get('retry_recovery_rate', 0.0)})"
        )
    out.append("=" * 78)
    agg = summary.get("aggregate") or {}
    for axis in summary.get("axes", []):
        a = agg.get(axis) or {}
        out.append(
            f"\n[{axis.upper()}] n={a.get('n', 0)} "
            f"pass={a.get('pass', 0)} fail={a.get('fail', 0)} "
            f"error={a.get('error', 0)} "
            f"pass_rate={a.get('pass_rate', 0.0)}"
        )
        top = a.get("top_failure_modes") or []
        if top:
            out.append("  top failure modes:")
            for mode, count in top:
                out.append(f"    {count:>3}× {mode}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-sidecar", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--rows-limit", type=int, default=None)
    # R66-C — default dropped 4 → 2. The wrapper's slowapi gate
    # defaults to 10 req/min; at concurrency=4 a 56-row × 4-axis run
    # bursts 8 simultaneous requests every few seconds and thrashes
    # the gate. Two is the empirical sweet spot. Operators on the
    # Anthropic-SDK-direct path can raise this back to 4-8 — Anthropic's
    # cloud rate limits are higher and more stable.
    parser.add_argument(
        "--concurrency", type=int, default=2,
        help="Number of worker threads (default 2 — tuned for the wrapper's slowapi gate).",
    )
    # R66-C — Anthropic SDK direct path. Routes each axis call through
    # ``anthropic.Anthropic().messages.create(...)`` instead of the
    # local openai_wrapper bridge. Requires ``P2P_GRAPH_RAG_API_KEY``
    # or ``ANTHROPIC_API_KEY`` to be set.
    parser.add_argument(
        "--provider", choices=("wrapper", "anthropic"), default="wrapper",
        help=(
            "Provider for the judge LLM. "
            "'wrapper' (default) routes through the local openai_wrapper bridge. "
            "'anthropic' uses the Anthropic SDK directly (requires "
            "P2P_GRAPH_RAG_API_KEY or ANTHROPIC_API_KEY)."
        ),
    )
    parser.add_argument(
        "--model", default=_DEFAULT_JUDGE_MODEL,
        help=(
            f"Judge model id (default {_DEFAULT_JUDGE_MODEL}). Pass "
            "'claude-opus-4-7' for higher-quality reasoning runs at extra "
            "latency / cost. The model id is forwarded verbatim to the "
            "selected provider — operators are responsible for matching "
            "what the provider accepts."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    set_judge_model(args.model)
    summary = run(
        bench_sidecar=args.bench_sidecar,
        label=args.label,
        rows_limit=args.rows_limit,
        concurrency=args.concurrency,
        verbose=args.verbose,
        provider=args.provider,
    )
    print(_format(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

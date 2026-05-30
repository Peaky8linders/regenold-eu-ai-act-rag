"""Paper-V4 eval runner — scores the three paper-grounded probe sets.

Mirrors runner_v2.py's scoring logic and CLI surface but loads the three
V4 modules instead of the V2 tricky + multiturn sets. Uses the same in-process
TestClient transport as article_coverage.py so it runs offline without a live
endpoint.

Usage
-----

    # Dry-collect (no HTTP — just verify imports + data load):
    .venv\\Scripts\\python.exe -m evals.regenold.run_paper_v4 --dry-run --label test

    # Local TestClient run (full app stack, no network):
    .venv\\Scripts\\python.exe -m evals.regenold.run_paper_v4 --local --label r98-paper-v4

    # Live endpoint run:
    .venv\\Scripts\\python.exe -m evals.regenold.run_paper_v4 \\
        --endpoint https://<railway>.up.railway.app/api/v1/regenold/eu-ai-act/ask \\
        --api-key $env:P2P_REGENOLD_API_KEY \\
        --label r98-paper-v4-live

Output
------
JSON sidecar written to ``evals/bench/results/paper-v4-<label>.json``.
Printed summary mirrors runner_v2's format, extended with per-category
breakdowns for single-turn and tricky sets and coherence rate for multi-turn.

Design notes
------------
* Single-turn scenarios use the runner_v2 *tricky* scoring path (same schema).
* Multi-turn scenarios use the runner_v2 *multiturn* scoring path (same schema).
* Both sets are run and reported together in one sidecar (no separate files).
* The runner is intentionally a thin wrapper — all scoring logic is delegated
  to runner_v2's helpers so metric semantics stay byte-identical.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

# ── V4 data imports ───────────────────────────────────────────────────────
from evals.regenold.scenarios_paper_singleturn_v4 import SCENARIOS as SINGLETURN_V4
from evals.regenold.scenarios_paper_tricky_v4 import SCENARIOS as TRICKY_V4
from evals.regenold.scenarios_paper_multiturn_v4 import SCENARIOS as MULTITURN_V4

# ── Delegate scoring helpers to runner_v2 ────────────────────────────────
from evals.regenold.runner_v2 import (
    _aggregate,
    _aggregate_by_category,
    _coherence_rate,
    _ensure_local_auth,
    _local_endpoint_url,
    _post,
    _post_local,
    _retry_stats,
    _score_multiturn_row,
    _score_tricky_row,
)

_USER_AGENT = "regenold-eu-ai-act-rag/paper-v4-runner"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Single-turn + tricky runner ───────────────────────────────────────────


def _run_singleturn_set(
    scenarios: list[dict],
    label_prefix: str,
    endpoint: str,
    api_key: str | None,
    timeout: float,
    concurrency: int,
    verbose: bool,
    use_local: bool,
) -> list[dict[str, Any]]:
    """Runs any list of single-turn tricky-schema scenarios."""
    results: list[dict[str, Any]] = [None] * len(scenarios)  # type: ignore[list-item]
    completed = 0
    lock = threading.Lock()
    transport = _post_local if use_local else _post

    def _worker(idx: int, scn: dict) -> tuple[int, dict]:
        history = [{"role": "user", "content": scn["question"]}]
        body, lat, status, err, attempts, retried = transport(
            endpoint, api_key, history, timeout
        )
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        return idx, _score_tricky_row(scn, body, lat, err, attempts, retried)

    workers = 1 if use_local else max(1, concurrency)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, i, s) for i, s in enumerate(scenarios)]
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
                        f"[{label_prefix}] {completed}/{len(scenarios)} {row['id']} "
                        f"cat={row['category']:<24} "
                        f"refL={row['ref_loose']:.2f} kw={row['keyword_recall']:.2f} "
                        f"lat={row['latency_ms']:.0f}ms{retry_tag}"
                    )
    return results  # type: ignore[return-value]


def _run_multiturn_set(
    scenarios: list[dict],
    endpoint: str,
    api_key: str | None,
    timeout: float,
    verbose: bool,
    use_local: bool,
) -> list[dict[str, Any]]:
    """Runs multi-turn scenarios sequentially (mirrors runner_v2.run_multiturn)."""
    out: list[dict[str, Any]] = []
    transport = _post_local if use_local else _post
    for idx, scn in enumerate(scenarios):
        history = scn.get("turns", [])
        body, lat, status, err, attempts, retried = transport(
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
                f"[mt_v4] {idx + 1}/{len(scenarios)} {row['id']} "
                f"turns={row['n_turns']} refL={row['ref_loose']:.2f} "
                f"kw={row['keyword_recall']:.2f} coh={row['is_coherent']} "
                f"lat={row['latency_ms']:.0f}ms{retry_tag}"
            )
    return out


# ── Top-level ────────────────────────────────────────────────────────────


def run(
    *,
    endpoint: str,
    api_key: str | None,
    label: str,
    timeout: float = 60.0,
    concurrency: int = 2,
    verbose: bool = False,
    out_dir: Path | None = None,
    use_local: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run all three V4 probe sets and write a JSON sidecar.

    ``dry_run=True`` skips all HTTP calls and returns the metadata payload
    with empty row lists — useful for import/schema verification.
    """
    started_at = _now_iso()

    if dry_run:
        singleturn_rows: list[dict[str, Any]] = []
        tricky_rows: list[dict[str, Any]] = []
        mt_rows: list[dict[str, Any]] = []
        print(
            f"[dry-run] singleturn_v4={len(SINGLETURN_V4)} items, "
            f"tricky_v4={len(TRICKY_V4)} items, "
            f"multiturn_v4={len(MULTITURN_V4)} items. "
            "No HTTP calls made."
        )
    else:
        if use_local:
            _ensure_local_auth(api_key)

        singleturn_rows = _run_singleturn_set(
            SINGLETURN_V4, "st_v4", endpoint, api_key,
            timeout, concurrency, verbose, use_local,
        )
        tricky_rows = _run_singleturn_set(
            TRICKY_V4, "tp_v4", endpoint, api_key,
            timeout, concurrency, verbose, use_local,
        )
        mt_rows = _run_multiturn_set(
            MULTITURN_V4, endpoint, api_key, timeout, verbose, use_local,
        )

    finished_at = _now_iso()

    payload: dict[str, Any] = {
        "label": label,
        "mode": (
            "paper-v4-dry-run" if dry_run
            else "paper-v4-local" if use_local
            else "paper-v4-live"
        ),
        "endpoint": endpoint,
        "started_at": started_at,
        "finished_at": finished_at,
        "data_counts": {
            "singleturn_v4": len(SINGLETURN_V4),
            "tricky_v4": len(TRICKY_V4),
            "multiturn_v4": len(MULTITURN_V4),
        },
        "singleturn": {
            "rows": singleturn_rows,
            "summary": _aggregate(singleturn_rows),
            "by_category": _aggregate_by_category(singleturn_rows),
            "retry_stats": _retry_stats(singleturn_rows),
        },
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
    }

    if out_dir is None:
        out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"paper-v4-{label}.json"
    sidecar.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    payload["sidecar_path"] = str(sidecar)
    return payload


def _format(payload: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"Paper-V4 eval runner — label={payload['label']!r}")
    out.append(f"endpoint: {payload['endpoint']}")
    out.append(f"mode: {payload['mode']}")
    counts = payload["data_counts"]
    out.append(
        f"items: singleturn={counts['singleturn_v4']} "
        f"tricky={counts['tricky_v4']} multiturn={counts['multiturn_v4']}"
    )
    out.append("=" * 78)

    for section_key, section_label in [
        ("singleturn", "SINGLE-TURN QA"),
        ("tricky", "TRICKY / NUANCED"),
    ]:
        sec = payload[section_key]["summary"]
        out.append("")
        out.append(
            f"[{section_label}] n={sec.get('n', 0)} "
            f"http_failures={sec.get('http_failures', 0)}"
        )
        out.append(f"  Ref Loose            : {sec.get('ref_loose', '-')}")
        out.append(f"  Ref Strict           : {sec.get('ref_strict', '-')}")
        out.append(f"  Keyword Recall       : {sec.get('keyword_recall', '-')}")
        out.append(f"  Regulatory Tone      : {sec.get('regulatory_tone', '-')}")
        out.append(
            f"  Latency              : p50={sec.get('latency_p50_ms', '-')}ms  "
            f"p95={sec.get('latency_p95_ms', '-')}ms"
        )
        out.append("  By category:")
        for cat, agg in payload[section_key]["by_category"].items():
            out.append(
                f"    {cat:<26} n={agg.get('n', 0):>3}  "
                f"refL={agg.get('ref_loose', '-')}  "
                f"kw={agg.get('keyword_recall', '-')}"
            )

    mt = payload["multiturn"]["summary"]
    coh = payload["multiturn"]["coherence_rate"]
    out.append("")
    out.append(
        f"[MULTI-TURN V4] n={mt.get('n', 0)} "
        f"http_failures={mt.get('http_failures', 0)}"
    )
    out.append(f"  Coherence Rate       : {coh}")
    out.append(f"  Ref Loose            : {mt.get('ref_loose', '-')}")
    out.append(f"  Ref Strict           : {mt.get('ref_strict', '-')}")
    out.append(f"  Keyword Recall       : {mt.get('keyword_recall', '-')}")
    out.append(f"  Regulatory Tone      : {mt.get('regulatory_tone', '-')}")
    out.append(
        f"  Latency              : p50={mt.get('latency_p50_ms', '-')}ms  "
        f"p95={mt.get('latency_p95_ms', '-')}ms"
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

    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use FastAPI TestClient (no network). --endpoint may be omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load data + write metadata only; skip all HTTP calls.",
    )
    args = parser.parse_args(argv)

    if args.local:
        endpoint = _local_endpoint_url("include_reasoning=true")
    elif args.endpoint:
        endpoint = args.endpoint
    elif args.dry_run:
        endpoint = "dry-run://local"
    else:
        parser.error("--endpoint is required unless --local or --dry-run is set")
        return 2

    payload = run(
        endpoint=endpoint,
        api_key=args.api_key,
        label=args.label,
        timeout=args.timeout,
        concurrency=args.concurrency,
        verbose=args.verbose,
        use_local=args.local,
        dry_run=args.dry_run,
    )
    print(_format(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

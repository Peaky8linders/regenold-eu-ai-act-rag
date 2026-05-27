"""Ad-hoc retry of HTTP-failed rows from a representative_100 sidecar.

R81-A1-live cascade-fail: 37/100 rows lost when the Cloudflare tunnel
or wrapper Max quota gave out mid-run. The 63 successful rows are
clean data. This script re-fires ONLY the failed rows against the live
endpoint and merges the new results into the existing sidecar, so the
final 100-row file is clean.

Usage:
    py -3.12 scripts/retry_failed_rep100.py \
        --sidecar evals/bench/results/representative-100-r81-a1-live.json \
        --endpoint "https://...up.railway.app/api/v1/regenold/eu-ai-act/ask" \
        --api-key dk5mhZqpDYhbhz-h5QNUrachCY2Eknz2nOKRwoRT-dE
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def _post(endpoint: str, api_key: str, messages: list[dict[str, str]], timeout: float = 90.0):
    req = urllib.request.Request(
        endpoint,
        data=json.dumps({"messages": messages}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Regenold-Api-Key": api_key,
        },
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body, (time.perf_counter() - start) * 1000.0, None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace"), (time.perf_counter() - start) * 1000.0, str(e)
    except Exception as e:  # noqa: BLE001
        return 0, "", (time.perf_counter() - start) * 1000.0, str(e)


def _messages_for_row(row: dict) -> list[dict[str, str]]:
    """Re-construct the messages list for a row. multi_turn rows have
    a list-shaped question; QA rows have a single string."""
    q = row.get("question")
    if isinstance(q, list):
        return q
    return [{"role": "user", "content": q}]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecar", required=True)
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--sleep-between", type=float, default=2.0,
                    help="Seconds to sleep between requests (avoid burst)")
    ap.add_argument("--max-rows", type=int, default=50,
                    help="Cap on how many failed rows to retry in one run")
    args = ap.parse_args()

    with open(args.sidecar, encoding="utf-8") as f:
        sidecar = json.load(f)

    rows = sidecar["rows"]
    failed = [(i, r) for i, r in enumerate(rows) if r.get("http_status") != 200]
    print(f"Sidecar has {len(rows)} rows; {len(failed)} HTTP-failed")
    if not failed:
        print("Nothing to retry.")
        return 0

    failed = failed[: args.max_rows]
    print(f"Retrying {len(failed)} failed rows (max={args.max_rows}, sleep={args.sleep_between}s)")
    print()

    new_success = 0
    new_fail = 0
    for k, (idx, row) in enumerate(failed):
        cat = row.get("category", "?")
        rid = row.get("id", f"row_{idx}")
        msgs = _messages_for_row(row)
        status, body, latency_ms, err = _post(args.endpoint, args.api_key, msgs)
        if status == 200:
            try:
                blob = json.loads(body)
            except Exception:
                blob = {}
            row["predicted_answer"] = blob.get("answer", "")
            row["pred_refs"] = blob.get("references", [])
            row["reasoning"] = blob.get("reasoning", "")
            row["answer_preview"] = (row["predicted_answer"] or "")[:140]
            row["http_status"] = 200
            row["latency_ms"] = round(latency_ms, 2)
            new_success += 1
            tag = "OK"
        else:
            row["http_status"] = status
            row["latency_ms"] = round(latency_ms, 2)
            new_fail += 1
            tag = f"FAIL({status})"
        print(f"  [{k+1}/{len(failed)}] {rid:<12s} {cat:<25s} {tag} {latency_ms:.0f}ms")

        sys.stdout.flush()
        if k < len(failed) - 1:
            time.sleep(args.sleep_between)

    # Recount
    rows = sidecar["rows"]
    still_failed = sum(1 for r in rows if r.get("http_status") != 200)
    sidecar["retry_note"] = (
        f"Retry pass applied: +{new_success} new OK, {new_fail} still failing; "
        f"total still-failing={still_failed}"
    )
    with open(args.sidecar, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)
    print()
    print(f"Retry done: +{new_success} OK, +{new_fail} fail. Still-failed total: {still_failed}/{len(rows)}")
    print(f"Sidecar updated: {args.sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

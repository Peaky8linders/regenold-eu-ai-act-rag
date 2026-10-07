"""R461 close — non-destructive POST-deploy wire verification.

Why this exists rather than `production_canary.py --phase post`: that script
writes `canary-post.jsonl` / `canary-post.json` **in place** under
`docs/measurements/r461/`, which are RECORDED artifacts of the R461.7/R461.8
read on an earlier commit. Re-running it would have replaced that record with
this deploy's numbers and silently re-attributed R461's own conciseness
promotion to a later code-only commit. So this probe reuses the canary's fixed
question set, its refusals list and its citation-budget definition read-only,
and writes nothing into the repository.

It gates exactly what a deploy verdict needs, and nothing it cannot support:

* ``deploy`` — the served commit is the expected one;
* ``health`` — ``/healthz`` ok and ``/healthz/llm`` ``llm_ok``, judged on a
  reading taken **after** this probe's own POSTs. On a freshly booted worker
  ``llm_ok`` reads ``True`` whenever Bedrock credentials are merely PRESENT and
  the leg has not been dialled yet — the R360.9/R361 false positive
  (``_degraded_to_bedrock`` in ``app/main.py``: *"Zero attempts is 'unknown',
  not 'broken'"*, measured live on ``1cab8f0`` reporting ``llm_ok:true`` beside
  ``fallback_ok:0``). Reading it BEFORE generating traffic therefore reports a
  down deploy as healthy, so a reading with no attempts on either leg is
  reported INCONCLUSIVE instead of PASS;
* ``transport`` — every question answered 200, non-empty, not a refusal;
* ``lint`` — every emitted reference resolves: the HEAD in the canonical table
  (AGENTS.md invariant #2 — ``ARTICLE_EXISTENCE`` holds bare heads, ``Art. N`` /
  ``Annex X``, so a wire reference is checked through ``_head_of``) and the full
  coordinate through the app's own ``provision_coordinates.coordinate_exists``.

Deliberately NOT gated: the budget/integrity DELTAS. The recorded ``pre`` arm is
pre-R461 (no conciseness block at all), so a delta against it prices R461's
promotion, not this deploy. The reference counts are reported for the record.

Also reported: which Stage-2 leg served each row (``/healthz/llm`` names it),
because production's primary wrapper leg read 401 before and after this deploy.

Usage::

    python docs/measurements/r461/post_deploy_wire_probe.py --expect-commit c09e5455b28a
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

ENDPOINT = "https://regenold-eu-ai-act-rag-production.up.railway.app"

#: The canary's own set and refusal vocabulary, imported read-only so the two
#: instruments cannot drift apart.
from docs.measurements.r461.production_canary import _REFUSALS, QUESTIONS  # noqa: E402


def _get(path: str, timeout: float = 30.0) -> dict:
    with urllib.request.urlopen(f"{ENDPOINT}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _ask(question: str, timeout: float) -> dict:
    body = json.dumps({"messages": [{"role": "user", "content": question}]}).encode()
    req = urllib.request.Request(
        f"{ENDPOINT}/api/v1/regenold/eu-ai-act/ask",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
            return {"status": r.status, "ms": (time.monotonic() - started) * 1000, "body": payload}
    except Exception as exc:  # noqa: BLE001 — a failed row is a failed row
        detail = getattr(exc, "read", lambda: b"")()
        return {
            "status": getattr(exc, "code", 0),
            "ms": (time.monotonic() - started) * 1000,
            "body": {},
            "error": f"{type(exc).__name__}: {str(exc)[:120]} {detail[:120]!r}",
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-commit", required=True)
    ap.add_argument("--timeout", type=float, default=180.0)
    a = ap.parse_args()

    health = _get("/healthz")
    served = str(health.get("commit") or "")
    gates: list[tuple[str, bool, str]] = []
    gates.append((
        "deploy",
        served.startswith(a.expect_commit[:12]),
        f"served {served or '?'} (expected {a.expect_commit[:12]})",
    ))

    from app.data.article_existence import ARTICLE_EXISTENCE
    from app.data.provision_coordinates import _head_of, coordinate_exists

    canonical = set(ARTICLE_EXISTENCE)
    rows: list[dict] = []
    for row_id, question in QUESTIONS:
        out = _ask(question, a.timeout)
        body = out["body"]
        answer = str(body.get("answer") or "")
        refs = [str(r) for r in (body.get("references") or [])]
        refusal = any(m in answer.lower() for m in _REFUSALS)
        bad_refs = [
            r for r in refs
            if _head_of(r) not in canonical or not coordinate_exists(r)
        ]
        rows.append({
            "id": row_id,
            "status": out["status"],
            "ms": round(out["ms"]),
            "chars": len(answer),
            "refs": refs,
            "bad_refs": bad_refs,
            "refusal": refusal,
            "empty": not answer.strip(),
            "error": out.get("error"),
        })
        print(f"  {row_id}: {out['status']} {round(out['ms'])}ms chars={len(answer)} refs={refs}",
              flush=True)

    # Judge the LLM path on a reading taken AFTER the traffic above: on a fresh
    # worker the pre-traffic reading is green by construction (see the module
    # docstring). Both legs at zero attempts is "unknown", never "healthy".
    llm = _get("/healthz/llm")
    stats = (llm.get("stage2_transport") or {}).get("stats") or {}
    dialled = int(stats.get("primary_attempts", 0) or 0) + int(
        stats.get("fallback_attempts", 0) or 0
    )
    if dialled == 0:
        gates.append((
            "health",
            False,
            f"INCONCLUSIVE — /healthz {health.get('status')} but neither Stage-2 leg recorded an "
            f"attempt after {len(rows)} rows, so llm_ok={llm.get('llm_ok')} proves nothing "
            f"(a freshly booted worker reads green while down, R361)",
        ))
    else:
        gates.append((
            "health",
            bool(health.get("status") == "ok") and bool(llm.get("llm_ok")),
            f"/healthz {health.get('status')} — llm_ok={llm.get('llm_ok')} on the post-traffic "
            f"read · primary {stats.get('primary_ok')}/{stats.get('primary_attempts')}, "
            f"fallback {stats.get('fallback_ok')}/{stats.get('fallback_attempts')} "
            f"(pid {llm.get('pid')}) · {str(llm.get('detail'))[:60]}",
        ))

    transport_ok = all(
        r["status"] == 200 and not r["empty"] and not r["refusal"] and not r["error"] for r in rows
    )
    gates.append((
        "transport",
        transport_ok,
        f"{sum(1 for r in rows if r['status'] == 200)}/{len(rows)} answered 200, non-empty, "
        f"not a refusal",
    ))
    all_bad = sorted({r for row in rows for r in row["bad_refs"]})
    gates.append((
        "lint",
        not all_bad,
        f"head in the canonical table ({len(canonical)} heads) AND coordinate resolvable"
        + (f" — UNRESOLVED: {all_bad}" if all_bad else ""),
    ))

    print(f"\n  references: mean {statistics.mean([len(r['refs']) for r in rows]):.2f}/row"
          f"  median chars {statistics.median([r['chars'] for r in rows]):.0f}"
          f"  median latency {statistics.median([r['ms'] for r in rows]):.0f}ms")
    print(f"  leg (post-traffic): {llm.get('provider')} · {llm.get('detail')}")
    print()
    ok = True
    for name, passed, detail in gates:
        ok &= passed
        print(f"  {'PASS' if passed else 'FAIL'}  {name:<10} {detail}")
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

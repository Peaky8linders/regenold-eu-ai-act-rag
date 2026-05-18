"""Round 52 — Stage-0 intent classifier A/B: Haiku (wrapper) vs Groq Llama.

Phase-1 of the Claude Max → Claude Pro migration. Validates that swapping
the Stage-0 intent classifier from Haiku 4.5 (via the local wrapper) to
Llama 3.3 70B (via Groq's serverless endpoint) doesn't materially
regress intent quality or the downstream rubric.

What it measures, per provider, against every V2 tricky + multi-turn
scenario's final user-question:

* Intent label (one of :data:`INTENT_LABELS`)
* Primary anchor (Art./Annex)
* Latency (per-call ms)
* Failure rate (wrapper-not-logged-in, network error, JSON parse fail)

Then computes:

* **Agreement rate** — fraction of questions where both providers
  return the same intent label.
* **Anchor agreement** — fraction where the primary_anchor matches.
* **Latency delta** — Groq p50/p95 vs Haiku p50/p95.
* **Top disagreements** — questions where the two providers picked
  different intents, surfaced with both labels for manual review.

Usage::

    # Set BOTH provider env vars before running (the script flips between
    # them per row; it does NOT require REGENOLD_INTENT_PROVIDER to be
    # toggled separately).
    $env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"   # wrapper for Haiku
    $env:OPENAI_API_KEY  = "dummy"
    $env:GROQ_API_KEY    = "gsk_..."

    .venv\\Scripts\\python.exe -m evals.regenold.intent_compare --label r50-pilot

Output: ``evals/bench/results/intent-compare-<label>.json``.

Stdlib + httpx only. Reuses the provider machinery in
:mod:`app.llm.openai_wrapper_provider` so the production wire shape is
exercised end-to-end.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from app.llm.intent_classifier import (
    INTENT_LABELS,
    _SYSTEM_PROMPT,
    _USER_TEMPLATE,
    _parse_intent_json,
)
from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    _OpenAIWrapperProvider,
)
from app.security.prompt_guard import sanitize_for_llm
from evals.bench import metrics as bench_metrics
from evals.regenold.scenarios_multiturn_v2 import SCENARIOS as MULTITURN_V2
from evals.regenold.scenarios_tricky_v2 import SCENARIOS as TRICKY_V2


# ── Provider construction ───────────────────────────────────────────────────


def _make_wrapper_provider() -> _OpenAIWrapperProvider:
    """Construct a wrapper provider explicitly (don't reuse the singleton —
    we don't want our intent-classifier production singleton to inherit the
    eval's timeouts or pollute its cache).
    """
    return _OpenAIWrapperProvider(
        base_url=os.getenv("OPENAI_API_BASE", "").strip() or "http://127.0.0.1:8000/v1",
        api_key=os.getenv("OPENAI_API_KEY", "dummy"),
        timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
    )


def _make_groq_provider() -> _OpenAIWrapperProvider:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY env var not set — provision a Groq API key at "
            "https://console.groq.com/keys before running this eval."
        )
    return _OpenAIWrapperProvider(
        base_url=(
            os.getenv("GROQ_API_BASE", "").strip()
            or "https://api.groq.com/openai/v1"
        ),
        api_key=api_key,
        timeout=float(os.getenv("GROQ_TIMEOUT_SECONDS", "10")),
    )


# ── Single-question classification ───────────────────────────────────────────


def _classify_one(
    provider: _OpenAIWrapperProvider,
    model: str,
    question: str,
    max_tokens: int = 160,
) -> dict[str, Any]:
    """Run one intent classification, returning a structured row.

    Failure paths: ``error`` is set, ``intent`` is ``None``. Caller is
    responsible for aggregating failures.
    """
    sanitised = sanitize_for_llm(question.strip(), context_type="query")
    if not sanitised:
        return {
            "model": model,
            "intent": None,
            "primary_anchor": "",
            "confidence": 0.0,
            "elapsed_ms": 0,
            "error": "empty_after_sanitise",
        }
    trimmed = sanitised if len(sanitised) <= 1500 else sanitised[-1500:]

    start = time.perf_counter()
    response = provider.complete(
        OpenAIWrapperRequest(
            system=_SYSTEM_PROMPT,
            user=_USER_TEMPLATE.format(q=trimmed),
            model=model,
            max_tokens=max_tokens,
            temperature=0.0,
            timeout_seconds=None,  # use provider default
        )
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if response.error:
        return {
            "model": model,
            "intent": None,
            "primary_anchor": "",
            "confidence": 0.0,
            "elapsed_ms": elapsed_ms,
            "error": response.error[:200],
        }

    parsed = _parse_intent_json(response.text or "")
    if parsed is None:
        return {
            "model": model,
            "intent": None,
            "primary_anchor": "",
            "confidence": 0.0,
            "elapsed_ms": elapsed_ms,
            "error": f"json_parse_fail: {(response.text or '')[:120]}",
        }
    return {
        "model": model,
        "intent": parsed.intent,
        "primary_anchor": parsed.primary_anchor,
        "alternate_anchors": list(parsed.alternate_anchors),
        "confidence": parsed.confidence,
        "elapsed_ms": elapsed_ms,
        "error": None,
    }


# ── Dataset assembly ─────────────────────────────────────────────────────────


def _collect_questions() -> list[dict[str, Any]]:
    """Flatten V2 tricky + final-turn multi-turn questions into one list.

    Each row carries ``id``, ``category`` (or ``"multiturn:<cat>"``),
    and ``question``. The same intent labels apply to both shapes —
    the multi-turn final-turn question is the one that needs to be
    classified correctly for the engine to surface the right anchor.
    """
    rows: list[dict[str, Any]] = []
    for scn in TRICKY_V2:
        rows.append({
            "id": scn["id"],
            "category": scn.get("category", "tricky"),
            "question": scn["question"],
            "source": "tricky",
        })
    for scn in MULTITURN_V2:
        turns = scn.get("turns") or []
        # Final user message — that's the one Stage-0 sees in production.
        user_turns = [t for t in turns if t.get("role") == "user"]
        if not user_turns:
            continue
        rows.append({
            "id": scn["id"],
            "category": f"multiturn:{scn.get('category', 'mt')}",
            "question": user_turns[-1]["content"],
            "source": "multiturn",
        })
    return rows


# ── Aggregation ──────────────────────────────────────────────────────────────


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    return round(bench_metrics.percentile(values, p), 2)


def _provider_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    failed = [r for r in rows if r.get("error")]
    succeeded = [r for r in rows if not r.get("error")]
    lats = [r["elapsed_ms"] for r in succeeded]
    intents = Counter(r["intent"] for r in succeeded)
    return {
        "n": len(rows),
        "success": len(succeeded),
        "failures": len(failed),
        "failure_rate": (
            round(len(failed) / len(rows), 4) if rows else 0.0
        ),
        "intent_distribution": dict(intents.most_common()),
        "avg_confidence": (
            round(mean(r["confidence"] for r in succeeded), 3)
            if succeeded else 0.0
        ),
        "latency_p50_ms": _percentile(lats, 50),
        "latency_p95_ms": _percentile(lats, 95),
        "latency_max_ms": round(max(lats), 2) if lats else 0.0,
    }


def _agreement(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute label + anchor agreement between two aligned row lists."""
    n = min(len(rows_a), len(rows_b))
    same_intent = 0
    same_anchor = 0
    both_succeeded = 0
    disagreements: list[dict[str, Any]] = []
    for i in range(n):
        a, b = rows_a[i], rows_b[i]
        if a.get("error") or b.get("error"):
            continue
        both_succeeded += 1
        if a["intent"] == b["intent"]:
            same_intent += 1
        else:
            disagreements.append({
                "id": a.get("id") or b.get("id"),
                "category": a.get("category") or b.get("category"),
                "question_preview": (a.get("question") or "")[:160],
                "a_intent": a["intent"],
                "a_anchor": a.get("primary_anchor", ""),
                "a_confidence": a.get("confidence", 0.0),
                "b_intent": b["intent"],
                "b_anchor": b.get("primary_anchor", ""),
                "b_confidence": b.get("confidence", 0.0),
            })
        if a.get("primary_anchor") == b.get("primary_anchor"):
            same_anchor += 1
    return {
        "compared": both_succeeded,
        "intent_agreement_rate": (
            round(same_intent / both_succeeded, 4) if both_succeeded else 0.0
        ),
        "anchor_agreement_rate": (
            round(same_anchor / both_succeeded, 4) if both_succeeded else 0.0
        ),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
    }


# ── Orchestration ───────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    *,
    label: str,
    haiku_model: str | None = None,
    groq_model: str | None = None,
    limit: int | None = None,
    verbose: bool = False,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    haiku_model = haiku_model or os.getenv(
        "REGENOLD_INTENT_MODEL", "claude-haiku-4-5-20251001"
    )
    groq_model = groq_model or os.getenv(
        "REGENOLD_INTENT_MODEL_GROQ", "llama-3.3-70b-versatile"
    )

    questions = _collect_questions()
    if limit:
        questions = questions[:limit]

    wrapper = _make_wrapper_provider()
    groq = _make_groq_provider()

    haiku_rows: list[dict[str, Any]] = []
    groq_rows: list[dict[str, Any]] = []

    started_at = _now_iso()
    for idx, q in enumerate(questions):
        # Run both providers per row so transient throttling on one
        # doesn't tilt the aggregate.
        row_a = _classify_one(wrapper, haiku_model, q["question"])
        row_a.update({"id": q["id"], "category": q["category"], "question": q["question"]})
        haiku_rows.append(row_a)

        row_b = _classify_one(groq, groq_model, q["question"])
        row_b.update({"id": q["id"], "category": q["category"], "question": q["question"]})
        groq_rows.append(row_b)

        if verbose:
            agree = "=" if row_a.get("intent") == row_b.get("intent") else "x"
            print(
                f"[{idx + 1}/{len(questions)}] {q['id']:<14} "
                f"haiku={row_a.get('intent') or 'ERR':<22} "
                f"groq={row_b.get('intent') or 'ERR':<22} {agree} "
                f"({row_a['elapsed_ms']}/{row_b['elapsed_ms']}ms)"
            )

    finished_at = _now_iso()

    agreement = _agreement(haiku_rows, groq_rows)
    payload = {
        "label": label,
        "started_at": started_at,
        "finished_at": finished_at,
        "n_questions": len(questions),
        "haiku": {
            "model": haiku_model,
            "summary": _provider_summary(haiku_rows),
            "rows": haiku_rows,
        },
        "groq": {
            "model": groq_model,
            "summary": _provider_summary(groq_rows),
            "rows": groq_rows,
        },
        "agreement": agreement,
    }

    if out_dir is None:
        out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"intent-compare-{label}.json"
    sidecar.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["sidecar_path"] = str(sidecar)
    return payload


# ── CLI ──────────────────────────────────────────────────────────────────────


def _format(payload: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"Intent A/B — label={payload['label']!r}")
    out.append(
        f"n_questions={payload['n_questions']}  "
        f"started={payload['started_at']}"
    )
    out.append("=" * 78)
    for name in ("haiku", "groq"):
        s = payload[name]["summary"]
        out.append("")
        out.append(f"[{name.upper()}] model={payload[name]['model']}")
        out.append(
            f"  success={s.get('success', 0)}/{s.get('n', 0)}  "
            f"failures={s.get('failures', 0)}  "
            f"avg_conf={s.get('avg_confidence', '-')}"
        )
        out.append(
            f"  latency p50={s.get('latency_p50_ms', '-')}ms  "
            f"p95={s.get('latency_p95_ms', '-')}ms  "
            f"max={s.get('latency_max_ms', '-')}ms"
        )
    ag = payload["agreement"]
    out.append("")
    out.append(
        f"[AGREEMENT] compared={ag['compared']}  "
        f"intent_match={ag['intent_agreement_rate']:.2%}  "
        f"anchor_match={ag['anchor_agreement_rate']:.2%}  "
        f"disagreements={ag['disagreement_count']}"
    )
    if ag["disagreements"]:
        out.append("")
        out.append("  Top disagreements (first 8):")
        for d in ag["disagreements"][:8]:
            out.append(
                f"    {d['id']:<14} cat={d['category']:<22} "
                f"a={d['a_intent']:<20} b={d['b_intent']:<20}"
            )
            out.append(f"      Q: {d['question_preview']}")
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
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--haiku-model",
        default=None,
        help="Override Haiku/wrapper model (default: env REGENOLD_INTENT_MODEL)",
    )
    parser.add_argument(
        "--groq-model",
        default=None,
        help="Override Groq model (default: env REGENOLD_INTENT_MODEL_GROQ)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit total questions (useful for quick smoke tests)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    payload = run(
        label=args.label,
        haiku_model=args.haiku_model,
        groq_model=args.groq_model,
        limit=args.limit,
        verbose=args.verbose,
    )
    print(_format(payload))
    return 0


_PUBLIC_API = {
    "INTENT_LABELS": INTENT_LABELS,
}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

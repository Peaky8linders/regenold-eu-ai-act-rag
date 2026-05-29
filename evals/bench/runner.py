"""Reproducible benchmark runner.

Loads the pinned ``davidath/ai-act-evaluation-benchmark`` dataset and
runs every row against the Regenold wire (``POST
/api/v1/regenold/eu-ai-act/ask``) via FastAPI's ``TestClient`` so no
real network or LLM API key is required. Scores each row across all 8
Regenold rubric axes, then persists the run to JSON + SQLite + the
audit chain.

CLI:
    py -3.12 -m evals.bench.runner
    py -3.12 -m evals.bench.runner --label baseline
    py -3.12 -m evals.bench.runner --qa-only       # skip 339 scenarios
    py -3.12 -m evals.bench.runner --limit 50      # smoke test
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.rate_limit import limiter

from evals.bench import dataset as bench_dataset
from evals.bench import metrics
from evals.bench import storage


_EVAL_KEY = "regenold-bench-eval-key"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ask(client: TestClient, question: str) -> tuple[dict, float, int]:
    """Single-turn request. Returns ``(body, latency_ms, http_status)``."""
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass
    payload = [{"role": "user", "content": question}]
    start = time.perf_counter()
    resp = client.post("/api/v1/regenold/eu-ai-act/ask", json=payload)
    elapsed = (time.perf_counter() - start) * 1000.0
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"answer": "", "references": [], "reasoning": None}
    if not isinstance(body, dict):
        body = {"answer": "", "references": [], "reasoning": None}
    return body, elapsed, resp.status_code


def _ask_multiturn(
    client: TestClient, history: list[dict[str, str]]
) -> tuple[dict, float, int]:
    """Multi-turn request — for the coherence axis."""
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass
    start = time.perf_counter()
    resp = client.post("/api/v1/regenold/eu-ai-act/ask", json=history)
    elapsed = (time.perf_counter() - start) * 1000.0
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"answer": "", "references": [], "reasoning": None}
    if not isinstance(body, dict):
        body = {"answer": "", "references": [], "reasoning": None}
    return body, elapsed, resp.status_code


# The scenario->question conversion is the canonical
# ``evals.bench.dataset.scenario_to_question`` — shared with
# ``evals.bench.representative_100`` so the synthesized question shape
# can never silently diverge between the two harnesses.
_scenario_to_question = bench_dataset.scenario_to_question


def _run_qa(
    client: TestClient, qa_items: list[dict[str, Any]], limit: int | None
) -> list[dict[str, Any]]:
    """Run every QA pair through the wire and collect scored rows."""
    items = qa_items[:limit] if limit else qa_items
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        time.sleep(1.0)  # [BYPASSED FOR BENCHMARK] rate limit to avoid 429s
        q = item.get("question") or ""
        gold_answer = item.get("answer") or ""
        gold_article = item.get("relevant_article")
        body, latency, http_status = _ask(client, q)
        pred_answer = body.get("answer") or ""
        pred_refs = body.get("references") or []
        score = metrics.score_row(
            pred_answer=pred_answer,
            pred_refs=pred_refs,
            gold_answer=gold_answer,
            gold_articles=gold_article,
            latency_ms=latency,
            expected_keywords=item.get("expected_keywords"),
        )
        rows.append(
            {
                "item_id": f"qa_{idx:03d}",
                "question": q,
                "gold_answer": gold_answer,
                "gold_articles": gold_article,
                "pred_answer": pred_answer,
                "pred_refs": pred_refs,
                "http_status": http_status,
                "scores": score.to_dict(),
                "_row_score": score,
            }
        )
    return rows


def _run_scenarios(
    client: TestClient,
    scenarios: list[dict[str, Any]],
    limit: int | None,
) -> list[dict[str, Any]]:
    """Run every scenario through the wire and collect scored rows.

    Gold answer is synthesized from the scenario's obligations list so
    correctness has something to score against. For pure
    risk-classification scoring see ``evals.regenold.runner``; this
    runner produces the unified 8-axis rubric scorecard the Regenold
    judge cares about.
    """
    items = scenarios[:limit] if limit else scenarios
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        time.sleep(1.0)  # [BYPASSED FOR BENCHMARK] rate limit to avoid 429s
        q = _scenario_to_question(item)
        risk_level = (item.get("risk_level") or "").replace("-", "_")
        obligations = item.get("obligations") or []
        gold_answer = f"This system is classified as {item.get('risk_level','')}. " + " ".join(
            obligations[:3]
        )
        gold_articles = item.get("related_articles") or []
        body, latency, http_status = _ask(client, q)
        pred_answer = body.get("answer") or ""
        pred_refs = body.get("references") or []
        score = metrics.score_row(
            pred_answer=pred_answer,
            pred_refs=pred_refs,
            gold_answer=gold_answer,
            gold_articles=gold_articles,
            latency_ms=latency,
            expected_keywords=item.get("expected_keywords"),
        )
        rows.append(
            {
                "item_id": f"sc_{idx:03d}",
                "question": q,
                "risk_level": item.get("risk_level"),
                "role": item.get("role"),
                "gold_answer": gold_answer,
                "gold_articles": gold_articles,
                "pred_answer": pred_answer,
                "pred_refs": pred_refs,
                "http_status": http_status,
                "scores": score.to_dict(),
                "_row_score": score,
            }
        )
    return rows


def _multiturn_coherence_probe(
    client: TestClient,
    scenarios: list[dict[str, Any]],
    limit: int = 20,
) -> dict[str, Any]:
    """Multi-turn coherence pass.

    Picks ``limit`` random scenarios, constructs a 2-turn conversation
    (initial classification question, then a follow-up "what about
    deployers?" / "and the technical documentation requirements?"),
    and measures whether the follow-up answer correctly resolves the
    referent. The score is the fraction of follow-up answers that
    (a) cite at least one of the gold articles, (b) don't introduce a
    fresh refusal phrase.
    """
    if not scenarios:
        return {"n": 0, "coherence_rate": 0.0}
    items = scenarios[:limit]
    coherent = 0
    rows: list[dict[str, Any]] = []
    for idx, s in enumerate(items):
        q1 = _scenario_to_question(s)
        body1, lat1, _ = _ask(client, q1)
        answer1 = body1.get("answer") or ""
        history = [
            {"role": "user", "content": q1},
            {"role": "assistant", "content": answer1},
            {
                "role": "user",
                "content": (
                    "And what are the technical documentation requirements"
                    " we need to maintain?"
                ),
            },
        ]
        body2, lat2, _ = _ask_multiturn(client, history)
        answer2 = body2.get("answer") or ""
        refs2 = body2.get("references") or []
        gold_articles = s.get("related_articles") or []
        pred_heads = metrics.article_heads(refs2)
        gold = {f"Article {int(a)}" for a in gold_articles if a is not None}
        cites_gold = bool(pred_heads & gold) if gold else False
        # Refusal sniff — if the follow-up dropped to "outside scope" it
        # broke coherence (the engine forgot the prior turn's context).
        refusal_markers = (
            "outside the scope",
            "not part of the eu ai act",
            "i only answer",
            "this assistant only",
        )
        is_refusal = any(m in answer2.lower() for m in refusal_markers)
        is_coherent = cites_gold and not is_refusal
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
            }
        )
    return {
        "n": len(items),
        "coherent": coherent,
        "coherence_rate": round(coherent / len(items), 4) if items else 0.0,
        "rows": rows,
    }


def _strip_row_scores(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the non-serialisable RowScore object before persistence."""
    return [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in rows
    ]


def run(
    *,
    label: str = "adhoc",
    qa_only: bool = False,
    scenarios_only: bool = False,
    skip_multiturn: bool = False,
    limit: int | None = None,
    multiturn_limit: int = 20,
    qa_dataset_path: Any = None,
) -> dict[str, Any]:
    """Run the full benchmark and return the persisted payload."""
    bench_dataset.ensure_dataset()
    qa_items = bench_dataset.load_qa_pairs(qa_dataset_path)
    scenarios = bench_dataset.load_scenarios()

    started_at = _now_iso()
    prev_key = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_EVAL_KEY)
    try:
        with TestClient(
            app, headers={"X-Regenold-Api-Key": _EVAL_KEY}
        ) as client:
            qa_rows: list[dict[str, Any]] = []
            scenario_rows: list[dict[str, Any]] = []
            multiturn: dict[str, Any] = {"n": 0, "coherence_rate": 0.0}
            if not scenarios_only:
                qa_rows = _run_qa(client, qa_items, limit)
            if not qa_only:
                scenario_rows = _run_scenarios(client, scenarios, limit)
            if not skip_multiturn and not qa_only:
                multiturn = _multiturn_coherence_probe(
                    client, scenarios, limit=multiturn_limit
                )
    finally:
        settings.regenold.api_key = prev_key

    finished_at = _now_iso()

    qa_scores = [r["_row_score"] for r in qa_rows]
    sc_scores = [r["_row_score"] for r in scenario_rows]
    summary = {
        "qa": metrics.aggregate(qa_scores),
        "scenarios": metrics.aggregate(sc_scores),
        "multiturn_coherence": {
            "n": multiturn.get("n", 0),
            "coherent": multiturn.get("coherent", 0),
            "coherence_rate": multiturn.get("coherence_rate", 0.0),
        },
        "overall": metrics.aggregate(qa_scores + sc_scores),
    }

    payload = {
        "label": label,
        "started_at": started_at,
        "finished_at": finished_at,
        "dataset_fingerprint": bench_dataset.dataset_fingerprint(),
        "summary": summary,
        "qa": _strip_row_scores(qa_rows),
        "scenarios": _strip_row_scores(scenario_rows),
        "multiturn": multiturn,
    }
    return storage.persist(payload)


def _format_human_summary(payload: dict[str, Any]) -> str:
    """Render a one-screen scorecard for the terminal."""
    s = payload.get("summary") or {}
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"Regenold competition benchmark — label={payload.get('label')!r}")
    lines.append("=" * 78)
    fingerprint = payload.get("dataset_fingerprint") or {}
    lines.append(
        f"dataset: qa_sha={fingerprint.get('qa_pairs_sha256','?')[:12]}  "
        f"scenarios_sha={fingerprint.get('scenarios_sha256','?')[:12]}"
    )
    for source in ("qa", "scenarios", "overall"):
        block = s.get(source) or {}
        if not block:
            continue
        n = block.get("n", 0)
        lines.append("")
        lines.append(f"[{source.upper()}] n={n}")
        lines.append(
            f"  Ans Correctness Loose : {block.get('ans_correctness_loose','-')}"
        )
        lines.append(
            f"  Ans Correctness Strict: {block.get('ans_correctness_strict','-')}"
        )
        lines.append(
            f"  Ans Conciseness       : {block.get('ans_conciseness','-')}"
        )
        lines.append(
            f"  Ref Correctness Loose : {block.get('ref_correctness_loose','-')}"
        )
        lines.append(
            f"  Ref Correctness Strict: {block.get('ref_correctness_strict','-')}"
        )
        lines.append(
            f"  Ref Conciseness       : {block.get('ref_conciseness','-')}"
        )
        lines.append(
            f"  Regulatory Tone       : {block.get('regulatory_tone','-')}"
        )
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
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="adhoc")
    parser.add_argument("--qa-only", action="store_true")
    parser.add_argument("--scenarios-only", action="store_true")
    parser.add_argument("--skip-multiturn", action="store_true")
    parser.add_argument("--qa-dataset", default=None, help="Path to custom qa pairs JSON dataset.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap each source (qa, scenarios) at this many rows. None = all.",
    )
    parser.add_argument(
        "--multiturn-limit",
        type=int,
        default=20,
        help="Cap the multi-turn coherence probe at this many scenarios.",
    )
    args = parser.parse_args(argv)

    from pathlib import Path
    qa_dataset_path = Path(args.qa_dataset) if args.qa_dataset else None

    payload = run(
        label=args.label,
        qa_only=args.qa_only,
        scenarios_only=args.scenarios_only,
        skip_multiturn=args.skip_multiturn,
        limit=args.limit,
        multiturn_limit=args.multiturn_limit,
        qa_dataset_path=qa_dataset_path
    )
    print(_format_human_summary(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

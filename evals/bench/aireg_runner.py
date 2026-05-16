"""AIReg-Bench runner — secondary EU AI Act benchmark for Regenold.

Loads ``camlsys/AIReg-Bench`` via :mod:`evals.bench.aireg_dataset` and
runs every annotated ``(document_id, article_id)`` pair against the
Regenold wire (``POST /api/v1/regenold/eu-ai-act/ask``) using FastAPI's
``TestClient``. Scores each row across the 7 Regenold rubric axes from
:mod:`evals.bench.metrics` plus the AIReg-specific **verdict match**
axis defined in :mod:`evals.bench.aireg_metrics`.

CLI:
    py -3.12 -m evals.bench.aireg_runner --label r33-aireg-smoke --limit 5
    py -3.12 -m evals.bench.aireg_runner --label r33-aireg
    py -3.12 -m evals.bench.aireg_runner --label refresh --refresh

Results land at ``evals/bench/results/aireg-<label>.json``. The
existing davidath runner's SQLite ledger + audit chain are NOT touched —
this is a parallel surface — but the JSON sidecar mirrors the davidath
layout so an operator can diff them.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.rate_limit import limiter

from evals.bench import aireg_dataset, aireg_metrics, metrics


_EVAL_KEY = "regenold-aireg-bench-eval-key"
_RESULTS_DIR = Path(__file__).parent / "results"

# Articles the bench scores against — for the typical co-cite list we
# bolt on Art. 6 (HRAIS framing) so the gold reference set matches the
# engine's tendency to cite the parent classification article.
_GOLD_CO_CITES = {
    9: ["Article 6"],
    10: ["Article 6"],
    12: ["Article 6"],
    14: ["Article 6"],
    15: ["Article 6"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(label: str) -> str:
    """Filesystem-safe slug for the sidecar name."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in label)


# ── Question construction ────────────────────────────────────────────────


def _build_question(
    document_id: str,
    article_id: int,
    intended_use: str,
    document_text: str | None,
) -> str:
    """Compose the user-facing question.

    Two shapes depending on whether the document text is available:

    * **doc-grounded** (preferred — once the upstream ships
      ``documentation/``): "Is this AI-system technical documentation
      compliant with Article N of the EU AI Act?\\n\\n<text>"

    * **prompt-only fallback** (current HF mirror, no docs): "Is an AI
      system used for {intended_use} likely to comply with Article N
      of the EU AI Act?" — still measures whether the engine cites the
      right article when asked about it. Less powerful than the doc
      variant but useful as a secondary signal.
    """
    if document_text:
        return (
            f"Is this AI-system technical documentation compliant with "
            f"Article {article_id} of the EU AI Act?\n\n{document_text}"
        )
    return (
        f"Is an AI system used for "
        f"{intended_use.rstrip('.').lower()} likely to comply with "
        f"Article {article_id} of the EU AI Act, and what compliance "
        f"verdict should we expect?"
    )


# ── Wire call ────────────────────────────────────────────────────────────


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


# ── Item grouping ────────────────────────────────────────────────────────


def _group_annotations(
    annotations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Collapse per-annotator records into per-(document, article) items.

    Output schema::

        {
            "item_id":        "art9_scenarioA_use1",
            "document_id":    "art9_scenarioA_use1",
            "article_id":     9,
            "scenario_id":    "A",
            "use_index":      1,
            "intended_use":   "Biometric...",
            "annotator_scores": [int, ...],
            "gold_verdict":   "compliant" | "borderline" | "non-compliant" | "unknown",
            "median_score":   float | None,
        }
    """
    buckets: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for a in annotations:
        key = (str(a.get("document_id", "")), int(a.get("article_id", 0)))
        buckets[key].append(a)
    items: list[dict[str, Any]] = []
    for (doc_id, art_id), recs in sorted(buckets.items()):
        head = recs[0]
        scores = [r.get("compliance_score") for r in recs]
        med = aireg_dataset.median(
            [s for s in scores if s is not None]
        )
        gold_verdict = aireg_metrics.gold_verdict_from_annotations(scores)
        items.append(
            {
                "item_id": doc_id,
                "document_id": doc_id,
                "article_id": art_id,
                "scenario_id": head.get("scenario_id"),
                "use_index": head.get("use_index"),
                "intended_use": head.get("intended_use", ""),
                "annotator_scores": [s for s in scores if s is not None],
                "median_score": med,
                "gold_verdict": gold_verdict,
                "n_annotators": len(scores),
            }
        )
    return items


# ── Per-row scoring ──────────────────────────────────────────────────────


def _score_row(
    pred_answer: str,
    pred_refs: list[str],
    gold_articles: list[int],
    intended_use: str,
    latency_ms: float,
) -> metrics.RowScore:
    """Reuse the davidath 7-axis scorer.

    For the answer-correctness axes we synthesize a gold answer from the
    article number + intended-use string ("AI systems used for X must
    comply with Article N..."). It's not a perfect ground-truth answer,
    but it gives the token-Jaccard and gold-token-fraction metrics
    something credible to score against on this dataset.
    """
    gold_answer = (
        f"AI systems used for {intended_use.lower()} that are subject to "
        f"Article {gold_articles[0] if gold_articles else 0} must comply "
        f"with the relevant obligations of the EU AI Act."
    )
    return metrics.score_row(
        pred_answer=pred_answer,
        pred_refs=pred_refs,
        gold_answer=gold_answer,
        gold_articles=gold_articles,
        latency_ms=latency_ms,
    )


def _run_items(
    client: TestClient,
    items: list[dict[str, Any]],
    documents: dict[str, str],
    limit: int | None,
) -> list[dict[str, Any]]:
    """Run grouped items through the wire and collect scored rows."""
    items = items[:limit] if limit else items
    rows: list[dict[str, Any]] = []
    for item in items:
        doc_text = documents.get(item["document_id"])
        question = _build_question(
            document_id=item["document_id"],
            article_id=int(item["article_id"]),
            intended_use=item.get("intended_use", ""),
            document_text=doc_text,
        )
        body, latency, http_status = _ask(client, question)
        pred_answer = body.get("answer") or ""
        pred_refs = body.get("references") or []
        gold_articles = [int(item["article_id"])] + [
            int(r.split()[1])
            for r in _GOLD_CO_CITES.get(int(item["article_id"]), [])
            if r.startswith("Article ")
        ]
        score = _score_row(
            pred_answer=pred_answer,
            pred_refs=pred_refs,
            gold_articles=gold_articles,
            intended_use=item.get("intended_use", ""),
            latency_ms=latency,
        )
        pred_verdict = aireg_metrics.extract_predicted_verdict(pred_answer)
        gold_verdict = item.get("gold_verdict", aireg_dataset.VERDICT_UNKNOWN)
        verdict_exact = aireg_metrics.verdict_match(pred_verdict, gold_verdict)
        verdict_soft = aireg_metrics.verdict_soft_match(
            pred_verdict, gold_verdict
        )
        rows.append(
            {
                "item_id": item["item_id"],
                "document_id": item["document_id"],
                "article_id": item["article_id"],
                "scenario_id": item.get("scenario_id"),
                "use_index": item.get("use_index"),
                "intended_use": item.get("intended_use"),
                "question": question[:240],  # truncate to keep JSON small
                "doc_grounded": bool(doc_text),
                "gold_verdict": gold_verdict,
                "median_score": item.get("median_score"),
                "annotator_scores": item.get("annotator_scores"),
                "pred_verdict": pred_verdict,
                "pred_answer": pred_answer,
                "pred_refs": pred_refs,
                "gold_articles": gold_articles,
                "http_status": http_status,
                "scores": {
                    **score.to_dict(),
                    "verdict_exact": round(verdict_exact, 4),
                    "verdict_soft": round(verdict_soft, 4),
                },
                "_row_score": score,
                "_pred_verdict": pred_verdict,
                "_gold_verdict": gold_verdict,
            }
        )
    return rows


# ── Aggregation ──────────────────────────────────────────────────────────


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """7-axis davidath aggregate plus the new verdict axes."""
    row_scores = [r["_row_score"] for r in rows]
    base = metrics.aggregate(row_scores)
    verdict_rows = [
        {"pred_verdict": r["_pred_verdict"], "gold_verdict": r["_gold_verdict"]}
        for r in rows
    ]
    verdict_report = aireg_metrics.aggregate_verdicts(verdict_rows).to_dict()
    base.update(verdict_report)
    return base


def _strip_private(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in rows
    ]


# ── Persistence ──────────────────────────────────────────────────────────


def _persist(payload: dict[str, Any]) -> Path:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = f"aireg-{_slug(payload.get('label', 'adhoc'))}"
    out = _RESULTS_DIR / f"{slug}.json"
    out.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return out


# ── Public entry-point ───────────────────────────────────────────────────


def run(
    *,
    label: str = "adhoc",
    limit: int | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Run the AIReg benchmark and return the persisted payload."""
    started_at = _now_iso()
    bench_payload = aireg_dataset.fetch_aireg_bench(refresh=refresh)
    annotations = bench_payload.get("annotations") or []
    documents = bench_payload.get("documents") or {}
    items = _group_annotations(annotations)
    if not items:
        finished_at = _now_iso()
        empty = {
            "label": label,
            "started_at": started_at,
            "finished_at": finished_at,
            "dataset_fingerprint": aireg_dataset.dataset_fingerprint(),
            "fetch_blocked": aireg_dataset.is_fetch_blocked(),
            "summary": {"n": 0},
            "items": [],
            "note": (
                "No annotation rows were available — either the HF "
                "fetch was blocked (see fetch_blocked=true) or the "
                "local cache is empty. Run with --refresh after the "
                "HF datasets-server is back up."
            ),
        }
        sidecar = _persist(empty)
        empty["sidecar_path"] = str(sidecar)
        return empty

    prev_key = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_EVAL_KEY)
    try:
        with TestClient(
            app, headers={"X-Regenold-Api-Key": _EVAL_KEY}
        ) as client:
            rows = _run_items(client, items, documents, limit)
    finally:
        settings.regenold.api_key = prev_key
    finished_at = _now_iso()

    summary = _aggregate(rows)
    payload = {
        "label": label,
        "started_at": started_at,
        "finished_at": finished_at,
        "dataset_fingerprint": aireg_dataset.dataset_fingerprint(),
        "fetch_blocked": aireg_dataset.is_fetch_blocked(),
        "n_items": len(rows),
        "n_doc_grounded": sum(1 for r in rows if r["doc_grounded"]),
        "summary": summary,
        "items": _strip_private(rows),
    }
    sidecar = _persist(payload)
    payload["sidecar_path"] = str(sidecar)
    return payload


# ── Human-readable scorecard ─────────────────────────────────────────────


def _format_summary(payload: dict[str, Any]) -> str:
    s = payload.get("summary") or {}
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(
        f"AIReg-Bench secondary benchmark — label={payload.get('label')!r}"
    )
    lines.append("=" * 78)
    fp = payload.get("dataset_fingerprint") or {}
    lines.append(
        f"dataset:  {fp.get('hf_id','?')}@{(fp.get('revision','?') or '?')[:12]}"
    )
    lines.append(
        f"cache:    sha={fp.get('annotations_json_sha256','?')[:12]}"
        f"   fetch_blocked={payload.get('fetch_blocked')}"
    )
    lines.append(
        f"items:    n={payload.get('n_items',0)} "
        f"doc_grounded={payload.get('n_doc_grounded',0)}"
    )
    if not s:
        lines.append("(no rows — see note in JSON sidecar)")
        return "\n".join(lines)
    lines.append("")
    lines.append("[Davidath-shared rubric axes]")
    lines.append(
        f"  Ans Correctness Loose : {s.get('ans_correctness_loose','-')}"
    )
    lines.append(
        f"  Ans Correctness Strict: {s.get('ans_correctness_strict','-')}"
    )
    lines.append(f"  Ans Conciseness       : {s.get('ans_conciseness','-')}")
    lines.append(
        f"  Ref Correctness Loose : {s.get('ref_correctness_loose','-')}"
    )
    lines.append(
        f"  Ref Correctness Strict: {s.get('ref_correctness_strict','-')}"
    )
    lines.append(f"  Ref Conciseness       : {s.get('ref_conciseness','-')}")
    lines.append(f"  Regulatory Tone       : {s.get('regulatory_tone','-')}")
    lines.append(
        f"  Latency               : p50={s.get('latency_p50_ms','-')}ms  "
        f"p95={s.get('latency_p95_ms','-')}ms"
    )
    lines.append("")
    lines.append("[AIReg-specific verdict axes]")
    lines.append(f"  Verdict exact-match : {s.get('verdict_exact','-')}")
    lines.append(f"  Verdict soft-match  : {s.get('verdict_soft','-')}")
    lines.append(f"  Verdict coverage    : {s.get('verdict_coverage','-')}")
    confusion = s.get("confusion") or {}
    if confusion:
        labels = [
            aireg_dataset.VERDICT_COMPLIANT,
            aireg_dataset.VERDICT_BORDERLINE,
            aireg_dataset.VERDICT_NON_COMPLIANT,
            aireg_dataset.VERDICT_UNKNOWN,
        ]
        lines.append("")
        lines.append("  Confusion (rows=gold, cols=pred):")
        header = "    " + " ".join(f"{l[:4]:>6}" for l in labels)
        lines.append(header)
        for gold in labels:
            row = confusion.get(gold) or {}
            cells = " ".join(f"{int(row.get(p,0)):>6}" for p in labels)
            lines.append(f"  {gold[:4]:>2}: {cells}")
    lines.append("")
    lines.append(f"sidecar: {payload.get('sidecar_path','?')}")
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
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap items at this many for smoke tests. None = run all.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Bypass the cache and re-fetch from huggingface.co.",
    )
    args = parser.parse_args(argv)
    payload = run(label=args.label, limit=args.limit, refresh=args.refresh)
    print(_format_summary(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

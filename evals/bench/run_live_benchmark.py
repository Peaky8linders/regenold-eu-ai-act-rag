"""Unified live benchmark runner for Regenold MedTech & Life-Sciences.

Polls the LIVE endpoint across a stratified cross-section of REAL datasets:

1. MedTech Nuances V4  (evals/regenold/scenarios_medtech_lifesci_v4.py)
2. Davidath RAG        (QA + Scenarios, via evals.bench.dataset)
3. AIReg-Bench         (camlsys/AIReg-Bench, via evals.bench.aireg_bench)
4. AIR-Bench 2024      (stanford-crfm, eu_mandatory; adversarial — opt-in via
                        REGENOLD_AIRBENCH=1)
5. appliedAI-style     (15 hand-authored risk-classification probes — clearly
                        labelled synthetic, NOT the appliedAI database)

All loaders are offline-safe: a dataset that cannot be fetched contributes
zero rows (with a printed note) rather than fabricated placeholder data, so
the scorecard never overstates coverage. Each subset feeds the generic
``_run_qa_http`` scorer (ref-correctness + keyword recall); the dedicated
AIReg/AIR-Bench scorers live in ``evals.bench.unbiased_runner`` for a richer
in-process measurement.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from evals.bench import aireg_bench, airbench_2024
from evals.bench import dataset as bench_dataset
from evals.bench import metrics
from evals.bench.prod_runner import (
    _run_qa_http,
    _strip_row_scores,
    _format_human_summary,
    _persist_prod,
)
from evals.regenold.scenarios_medtech_lifesci_v4 import MEDTECH_SCENARIOS_V4

# appliedAI-style risk-classification probes. HAND-AUTHORED synthetic cases
# (legally checked), NOT the appliedAI database — kept as a lightweight
# classification cross-section. Each gold ref resolves in the canonical
# 113-article + 13-annex catalog.
APPLIED_AI_CASES = [
    {"item_id": "aai_01", "question": "What is the risk level of an AI sorting resumes for job applicants?", "expected_refs": ["Annex III"], "expected_keywords": ["high-risk", "employment", "Annex III"]},
    {"item_id": "aai_02", "question": "Classify an AI system used to evaluate creditworthiness of individuals for bank loans.", "expected_refs": ["Annex III"], "expected_keywords": ["high-risk", "credit", "Annex III"]},
    {"item_id": "aai_03", "question": "What is the classification of an AI chatbot used for customer service on an e-commerce website?", "expected_refs": ["Article 50"], "expected_keywords": ["transparency", "interact", "Article 50"]},
    {"item_id": "aai_04", "question": "Classify an AI system used to control a safety valve in an industrial manufacturing plant.", "expected_refs": ["Annex I", "Article 6"], "expected_keywords": ["high-risk", "safety component", "Annex I"]},
    {"item_id": "aai_05", "question": "Risk level of an AI used by police to predict the occurrence of crimes based on profiling?", "expected_refs": ["Article 5"], "expected_keywords": ["prohibited", "predictive policing", "criminal offense", "Article 5"]},
    {"item_id": "aai_06", "question": "Classify an AI tool used by teachers to grade student essays and determine their final exams.", "expected_refs": ["Annex III"], "expected_keywords": ["high-risk", "education", "Annex III"]},
    {"item_id": "aai_07", "question": "Classification of an AI spam filter used in an enterprise email client?", "expected_refs": ["Article 6", "Annex III"], "expected_keywords": ["minimal", "not high-risk"]},
    {"item_id": "aai_08", "question": "Risk level of an AI system used to deepfake a politician's speech.", "expected_refs": ["Article 50"], "expected_keywords": ["transparency", "deepfake", "manipulation", "Article 50"]},
    {"item_id": "aai_09", "question": "Risk level of a biometric categorization system inferring sexual orientation from photos.", "expected_refs": ["Article 5"], "expected_keywords": ["prohibited", "biometric categorization", "sexual orientation"]},
    {"item_id": "aai_10", "question": "Classify an AI system managing critical infrastructure like water supply networks.", "expected_refs": ["Annex III"], "expected_keywords": ["high-risk", "critical infrastructure", "Annex III"]},
    {"item_id": "aai_11", "question": "Classification of an AI inventory management system for a retail store.", "expected_refs": ["Article 6", "Annex III"], "expected_keywords": ["minimal", "not high-risk"]},
    {"item_id": "aai_12", "question": "Risk level of a general-purpose AI model with 10^26 FLOPs computation.", "expected_refs": ["Article 51"], "expected_keywords": ["general-purpose", "systemic risk", "10^25"]},
    {"item_id": "aai_13", "question": "Classify an AI toy that encourages dangerous behavior in children through voice interaction.", "expected_refs": ["Article 5"], "expected_keywords": ["prohibited", "subliminal", "manipulative", "harm"]},
    {"item_id": "aai_14", "question": "Classify an AI software that triages emergency calls for ambulance dispatch.", "expected_refs": ["Annex III"], "expected_keywords": ["high-risk", "emergency", "dispatch"]},
    {"item_id": "aai_15", "question": "Risk classification of a real-time remote biometric identification system used by law enforcement in public spaces to find a kidnapped child.", "expected_refs": ["Article 5"], "expected_keywords": ["exception", "law enforcement", "kidnapping", "real-time"]},
]


def _norm_ref(ref: str) -> str:
    """Normalise an AIReg-style ``Art. 9`` ref to wire form ``Article 9``."""
    ref = (ref or "").strip()
    if ref.startswith("Art.") and not ref.startswith("Article"):
        return "Article" + ref[len("Art."):]
    return ref


def load_aireg_items(limit: int | None = None) -> list[dict]:
    """Real camlsys/AIReg-Bench rows mapped to the generic-scorer shape.

    Offline-safe: returns ``[]`` (no fabricated data) if the dataset cannot
    be loaded. AIReg rows describe an AI-system documentation excerpt plus the
    high-risk article it should be assessed against (Arts. 9/10/12/14/15).
    """
    try:
        rows = aireg_bench.load_aireg_bench() or []
    except Exception as exc:  # noqa: BLE001 — never break the run on a loader fault
        print(f"  [AIReg] loader unavailable ({type(exc).__name__}); contributing 0 rows.")
        return []
    if limit is not None:
        rows = rows[:limit]
    items: list[dict] = []
    for r in rows:
        gold = [_norm_ref(a) for a in (r.get("expected_articles") or [])]
        verdict = r.get("expected_verdict", "")
        items.append({
            "item_id": r.get("id"),
            "question": (
                f"{r.get('scenario', '')}\n\nWhich EU AI Act article governs "
                f"this AI system, and does it comply?"
            ),
            "relevant_article": gold,
            "expected_keywords": [verdict, *gold] if verdict else gold,
            "answer": verdict,
        })
    return items


def load_airbench_items(limit: int | None = None) -> list[dict]:
    """Real AIR-Bench 2024 ``eu_mandatory`` adversarial prompts.

    ADVERSARIAL — opt-in only via ``REGENOLD_AIRBENCH=1`` (mirrors the gate in
    ``unbiased_runner``). Offline-safe: returns ``[]`` when the gate is off OR
    the dataset cannot be loaded. Gold refs derive from the prompt's risk
    category (mostly Article 5); a compliant system should refuse / cite Art. 5.
    """
    gate = os.environ.get("REGENOLD_AIRBENCH", "").strip().lower()
    if gate not in ("1", "true", "yes", "on"):
        print("  [AIR-Bench] gated off (set REGENOLD_AIRBENCH=1 to include adversarial prompts).")
        return []
    try:
        rows = airbench_2024.load_eu_mandatory() or []
    except Exception as exc:  # noqa: BLE001
        print(f"  [AIR-Bench] loader unavailable ({type(exc).__name__}); contributing 0 rows.")
        return []
    if limit is not None:
        rows = rows[:limit]
    items: list[dict] = []
    for i, r in enumerate(rows):
        gold = airbench_2024.derive_gold_refs(r.get("cate_idx", ""))
        items.append({
            "item_id": f"airb_{i:03d}",
            "question": r.get("prompt", ""),
            "relevant_article": gold,
            "expected_keywords": ["prohibited", "refuse", "cannot"] if gold else ["out of scope", "not the eu ai act"],
            "answer": "",
        })
    return items


def load_davidath_subset(qa_items: list[dict], scenarios: list[dict]) -> tuple[list[dict], list[dict]]:
    """Take the first 10 QA + 10 Scenarios from the davidath bench."""
    return qa_items[:10], scenarios[:10]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    endpoint: str,
    api_key: str | None,
    label: str,
    limit: int | None,
    concurrency: int = 4,
    timeout: float = 30.0,
    verbose: bool = True,
    aireg_limit: int | None = 10,
    airbench_limit: int | None = 15,
):
    print("Loading datasets...")
    bench_dataset.ensure_dataset()
    full_qa = bench_dataset.load_qa_pairs()
    full_sc = bench_dataset.load_scenarios()
    davidath_qa, davidath_sc = load_davidath_subset(full_qa, full_sc)

    all_items: list[dict] = []
    counts: dict[str, int] = {}

    # 1. MedTech V4
    medtech = [
        {
            "item_id": s["id"],
            "question": s["question"],
            "relevant_article": s.get("expected_refs"),
            "expected_keywords": s.get("expected_keywords"),
            "answer": " ".join(s.get("expected_keywords", [])),
        }
        for s in MEDTECH_SCENARIOS_V4
    ]
    all_items.extend(medtech)
    counts["medtech_v4"] = len(medtech)

    # 2. Davidath QA
    dqa = [
        {
            "item_id": f"dqa_{i:03d}",
            "question": s["question"],
            "relevant_article": s["relevant_article"],
            "answer": s["answer"],
        }
        for i, s in enumerate(davidath_qa)
    ]
    all_items.extend(dqa)
    counts["davidath_qa"] = len(dqa)

    # 3. Davidath Scenarios (converted to QA shape)
    dsc = []
    for i, s in enumerate(davidath_sc):
        dsc.append({
            "item_id": f"dsc_{i:03d}",
            "question": bench_dataset.scenario_to_question(s),
            "relevant_article": s.get("related_articles"),
            "answer": f"This system is classified as {s.get('risk_level', '')}.",
        })
    all_items.extend(dsc)
    counts["davidath_scenarios"] = len(dsc)

    # 4. AIReg-Bench (real loader; offline-safe)
    aireg = load_aireg_items(aireg_limit)
    all_items.extend(aireg)
    counts["aireg_bench"] = len(aireg)

    # 5. AIR-Bench 2024 (real loader; adversarial, opt-in; offline-safe)
    airb = load_airbench_items(airbench_limit)
    all_items.extend(airb)
    counts["airbench_2024"] = len(airb)

    # 6. appliedAI-style hand-authored probes
    all_items.extend(
        {
            "item_id": s["item_id"],
            "question": s["question"],
            "relevant_article": s.get("expected_refs"),
            "expected_keywords": s.get("expected_keywords"),
            "answer": " ".join(s.get("expected_keywords", [])),
        }
        for s in APPLIED_AI_CASES
    )
    counts["applied_ai"] = len(APPLIED_AI_CASES)

    if limit:
        all_items = all_items[:limit]

    print("Subset coverage:")
    for name, n in counts.items():
        print(f"  - {name}: {n}")
    print(f"Loaded {len(all_items)} total items to evaluate"
          + (f" (capped at {limit})." if limit else "."))

    started_at = _now_iso()
    rows = _run_qa_http(endpoint, api_key, timeout, concurrency, all_items, None, verbose)
    finished_at = _now_iso()

    scores = [r["_row_score"] for r in rows]
    n_failures = sum(1 for r in rows if not r.get("passed"))

    retried = sum(1 for r in rows if (r.get("attempts") or 1) > 1)
    recovered = sum(1 for r in rows if (r.get("attempts") or 1) > 1 and r.get("error") is None)
    total_retries = sum(max(0, (r.get("attempts") or 1) - 1) for r in rows)

    agg = metrics.aggregate(scores)
    summary = {
        "qa": agg,
        "scenarios": {},  # everything flattened to QA; keep ledger-safe shape
        "overall": agg,
        "subset_counts": counts,
        "http_failures": n_failures,
        "http_total": len(rows),
        "total_retries": total_retries,
        "rows_retried": retried,
        "rows_retry_recovered": recovered,
        "retry_recovery_rate": round(recovered / retried, 4) if retried else 0.0,
    }

    payload = {
        "label": label,
        "mode": "prod",
        "endpoint": endpoint,
        "concurrency": concurrency,
        "timeout_s": timeout,
        "started_at": started_at,
        "finished_at": finished_at,
        "dataset_fingerprint": bench_dataset.dataset_fingerprint(),
        "summary": summary,
        "qa": _strip_row_scores(rows),
    }

    payload = _persist_prod(payload)
    print("\n" + _format_human_summary(payload))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified MedTech + multi-benchmark live runner")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--api-key")
    parser.add_argument("--label", default="unified-live")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--aireg-limit", type=int, default=10)
    parser.add_argument("--airbench-limit", type=int, default=15)
    args = parser.parse_args()

    run(
        endpoint=args.endpoint,
        api_key=args.api_key,
        label=args.label,
        limit=args.limit,
        concurrency=args.concurrency,
        aireg_limit=args.aireg_limit,
        airbench_limit=args.airbench_limit,
    )

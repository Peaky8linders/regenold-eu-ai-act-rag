"""Regenold eval harness.

Scoring follows the methodology of Davvetas et al. (arXiv:2603.09435v1),
"AI Act Evaluation Benchmark", with two extensions for the Regenold
competition rubric:

  * Per-scenario binary ``passed`` flag (the gate) — substring/regex
    predicates per scenario.
  * Per-class precision/recall/F1 for the two paper-grade tasks where
    gold values are available:
      - Risk-level classification (4 classes: prohibited / high_risk /
        limited / minimal, plus a "refusal" bucket for out-of-scope or
        non-existent article queries).
      - Article-retrieval (precision/recall against ``expected_references``
        gold sets on scenarios where the set is unambiguous).

Scenarios without a ``risk_label`` or ``expected_references`` gold set are
excluded from the F1 numerator/denominator (not counted as misses).

Implementation notes (CI-safe + stateless):

* Uses ``TestClient`` so no real Anthropic key is required.
* Resets the app's ``slowapi`` rate limiter between scenarios so we
  don't trip the per-IP 30/min cap inside a single eval batch.
* Reads the response, applies every scenario check, records
  pass/fail + the response excerpt for the report.
* Tracks Regenold-rubric quality metrics across the whole batch:
  citation format conformance, sentence-cap conformance, latency p50/p95,
  plus the paper-aligned per-class F1 + article-retrieval P/R/F1.

CLI:
    py -3.12 -m evals.regenold.runner
    py -3.12 -m evals.regenold.runner --json evals/regenold_results.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.integrations.regenold.models import (
    MAX_ANSWER_SENTENCES,
    MAX_REFERENCES,
    _split_sentences,
)
from app.main import app
from app.rate_limit import limiter
from evals.regenold.scenarios import (
    CATEGORIES,
    SCENARIOS,
    Scenario,
)

# ── Regenold-rubric quality metrics (batch-level) ─────────────────────────
#
# The Regenold competition scores 5 dimensions: Answer Correctness,
# Reference Accuracy, Conciseness, Tone, Latency. The per-scenario
# `passed` flag covers the binary correctness gate. These batch-level
# metrics surface the Conciseness / Reference-Accuracy / Latency
# dimensions so a regression that quietly breaks format-conformance
# (e.g. "Article 13(1)(a)" instead of "Article 13.1.a") is visible
# in the JSON report even when every binary check still passes.

# Strict per-spec output regexes (mirror app/integrations/regenold/models.py).
# TODO(R47): migrate to app.integrations.regenold.refs (centralised converter).
_REGENOLD_ANNEX_RE = re.compile(r"^Annex [IVXLC]+(?:\.[A-Za-z0-9]+)*$")
_REGENOLD_ARTICLE_RE = re.compile(r"^Article \d+(?:\.[A-Za-z0-9]+)*$")
# Internal-form sniffers — references should NEVER ship in these shapes.
_INTERNAL_ART_PAREN_RE = re.compile(r"^Art\.\s*\d+(?:\([^)]+\))*$")
_INTERNAL_ARTICLE_PAREN_RE = re.compile(r"^Article\s+\d+(?:\([^)]+\))*$")


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    description: str
    http_status: int
    response_excerpt: dict
    check_results: list[tuple[str, bool]]
    passed: bool
    duration_ms: float
    # ── Regenold-rubric per-scenario quality flags ──────────────────────
    # Each flag is True iff the response meets the spec dimension. They
    # are aggregated batch-wide to surface conciseness + format trends.
    refs_conformant: bool = True
    """Every reference in the response matches the strict spec regex."""
    answer_within_sentence_cap: bool = True
    """Answer is <= MAX_ANSWER_SENTENCES."""
    refs_within_max: bool = True
    """references list len is <= MAX_REFERENCES."""
    refs_count: int = 0
    """How many references shipped."""
    answer_sentence_count: int = 0
    """How many sentences the answer parses to."""
    # ── Paper-aligned per-scenario classification + retrieval state ─────
    # Populated for downstream aggregation in
    # ``_compute_classification_metrics`` / ``_compute_retrieval_metrics``.
    # ``None`` when the scenario has no gold value (skipped from F1).
    risk_label_gold: str | None = None
    """The scenario's ``risk_label`` gold (or ``None`` if unlabeled)."""
    risk_label_pred: str | None = None
    """The predicted risk class extracted from the response answer text."""
    expected_references: tuple[str, ...] = ()
    """The scenario's ``expected_references`` gold (or empty if unlabeled)."""
    predicted_references: tuple[str, ...] = ()
    """The article/annex heads we read off the response references list."""


def _compute_quality_flags(body: dict) -> dict[str, Any]:
    """Compute per-scenario quality flags off the wire body.

    Pure-functional, never raises. Returns a dict with the same keys as
    the ``ScenarioResult`` quality-metric fields so the caller can splat.
    """
    refs = body.get("references") or []
    refs_count = len(refs) if isinstance(refs, list) else 0

    refs_conformant = True
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, str):
                refs_conformant = False
                break
            if _REGENOLD_ANNEX_RE.match(ref) or _REGENOLD_ARTICLE_RE.match(ref):
                continue
            # Internal-form leakage is a hard fail (silently invalid wire).
            refs_conformant = False
            break

    refs_within_max = refs_count <= MAX_REFERENCES

    answer = body.get("answer") or ""
    sentence_count = 0
    if isinstance(answer, str) and answer.strip():
        try:
            sentences = _split_sentences(answer)
            sentence_count = len(sentences)
        except Exception:
            sentence_count = 0
    answer_within_cap = sentence_count <= MAX_ANSWER_SENTENCES

    return {
        "refs_conformant": refs_conformant,
        "answer_within_sentence_cap": answer_within_cap,
        "refs_within_max": refs_within_max,
        "refs_count": refs_count,
        "answer_sentence_count": sentence_count,
    }


# ── Paper-aligned metric helpers (Davvetas et al., Section 5) ────────────
#
# The paper reports per-class precision/recall/F1 for risk classification
# and article-retrieval. We keep the prediction heuristic deliberately
# simple (substring sniff on the answer text) so the metric is reproducible
# and doesn't depend on a separate classifier model.

# Class labels per the 4-tier risk pyramid + a "refusal" bucket for
# out-of-scope / non-existent-article queries (see Section 3.2 of the
# paper). The "out_of_scope" alias is normalised to "refusal" in metrics.
RISK_CLASSES: tuple[str, ...] = (
    "prohibited",
    "high_risk",
    "limited",
    "minimal",
    "refusal",
)


def _normalise_risk_label(label: str | None) -> str | None:
    """Collapse ``out_of_scope`` → ``refusal`` for confusion-matrix bucketing.

    The scenarios file uses both labels with the same intended meaning
    (the system declines to classify because the question is off-topic
    or refers to a non-existent article). The paper has no "out_of_scope"
    class; folding to "refusal" keeps the matrix square.
    """
    if label is None:
        return None
    if label == "out_of_scope":
        return "refusal"
    return label


_HIGH_RISK_POS_MARKERS = (
    "is high-risk",
    "are high-risk",
    "is high risk",
    "are high risk",
    "qualifies as high-risk",
    "falls under high-risk",
    "falls within high-risk",
)
_HIGH_RISK_NEG_MARKERS = (
    "not high-risk",
    "not high risk",
    "is not high",
    "are not high",
)
_PROHIBITED_POS_MARKERS = (
    "is prohibited",
    "are prohibited",
    "is banned",
    "are banned",
    "prohibited under article 5",
    "prohibited practice",
)
_PROHIBITED_NEG_MARKERS = (
    "not prohibited",
    "is not prohibited",
    "are not prohibited",
)


def _first_match(haystack: str, needles: tuple[str, ...]) -> int:
    """Return the lowest index where any needle appears, or -1."""
    best = -1
    for n in needles:
        i = haystack.find(n)
        if i != -1 and (best == -1 or i < best):
            best = i
    return best


def _predict_risk_class(body: dict) -> str | None:
    """Extract the predicted risk class from the response.

    Heuristic — sniffs the answer text for the four paper classes plus a
    refusal signal. Returns ``None`` when no class can be inferred (the
    response neither states a verdict nor refuses).

    Position-aware: a positive verdict that *leads* the prose counts
    even if a narrower negation appears later (matching the
    ``_verdict_high_risk`` regex pattern in scenarios.py).
    """
    answer = (body.get("answer") or "").lower()
    refs = body.get("references") or []

    # Refusal signal — empty references + a scope marker, OR a 4xx status.
    # Re-implemented here (rather than importing scenarios._refused) so
    # the runner stays decoupled from scenario predicates.
    refusal_markers = (
        "no matching obligation",
        "not part of the eu ai act",
        "outside the scope of this assistant",
        "i only answer questions about the eu ai act",
        "i can only answer eu ai act",
        "doesn't appear in the eu ai act",
        "does not appear in the eu ai act",
        "this assistant only covers the eu ai act",
        "this assistant only answers eu ai act",
        "this assistant answers eu ai act questions only",
        # R256 — branded "Lexy" decline / greeting / adversarial copy.
        "i cannot answer your question from my knowledge graph",
        "from these materials, which address only obligations",
        "i am lexy",
        "i do not act on instructions",
    )
    is_refusal = (not refs) and any(m in answer for m in refusal_markers)
    if is_refusal or body.get("__http_status", 200) in (400, 401, 403, 404, 422):
        return "refusal"

    if not answer:
        return None

    # Prohibited verdict — positive marker that leads, no leading
    # negation. Position-aware to handle nuanced answers that note a
    # carve-out later in the prose.
    pos_p = _first_match(answer, _PROHIBITED_POS_MARKERS)
    neg_p = _first_match(answer, _PROHIBITED_NEG_MARKERS)
    if pos_p != -1 and (neg_p == -1 or pos_p < neg_p):
        return "prohibited"

    # High-risk verdict — same position-aware logic. Mirrors the
    # ``_verdict_high_risk`` regex in scenarios.py so an answer that
    # leads with "are high-risk under Annex III" and later notes a
    # carve-out ("…are not high-risk on this basis") still counts as
    # the high-risk class.
    pos_h = _first_match(answer, _HIGH_RISK_POS_MARKERS)
    neg_h = _first_match(answer, _HIGH_RISK_NEG_MARKERS)
    if pos_h != -1 and (neg_h == -1 or pos_h < neg_h):
        return "high_risk"

    # Minimal — explicit "minimal" framing.
    if "minimal-risk" in answer or "minimal risk" in answer:
        return "minimal"

    # Limited — explicit Art. 50 transparency-only framing.
    if "limited-risk" in answer or "limited risk" in answer:
        return "limited"

    return None


def _ref_head(ref: str) -> str | None:
    """Strip a reference like ``Article 13.1.a`` down to ``Article 13``.

    Returns ``None`` for unparseable refs (defensive; the wire is
    spec-clean by the time we read it, but the runner shouldn't crash
    on a malformed payload).
    """
    if not isinstance(ref, str):
        return None
    if ref.startswith("Article "):
        body = ref[len("Article "):]
        return "Article " + body.split(".")[0]
    if ref.startswith("Annex "):
        body = ref[len("Annex "):]
        return "Annex " + body.split(".")[0]
    return None


def _predicted_ref_heads(body: dict) -> tuple[str, ...]:
    """Return the unique article/annex heads in the response references list."""
    refs = body.get("references") or []
    if not isinstance(refs, list):
        return ()
    heads: list[str] = []
    seen: set[str] = set()
    for r in refs:
        h = _ref_head(r)
        if h is None or h in seen:
            continue
        seen.add(h)
        heads.append(h)
    return tuple(heads)


def _compute_classification_metrics(
    results: list[ScenarioResult],
) -> dict[str, Any]:
    """Per-class precision/recall/F1 + macro-F1 on labeled scenarios.

    Returns ``{"labeled_scenarios": 0, ...}`` with empty per-class
    structure when no scenario carries a ``risk_label``. F1 for a class
    with zero true-positives + zero false-positives + zero false-negatives
    is reported as ``None`` (NaN-equivalent) — there's nothing to score.
    """
    labeled: list[ScenarioResult] = [
        r for r in results if r.risk_label_gold is not None
    ]
    if not labeled:
        return {
            "labeled_scenarios": 0,
            "per_class_f1": {c: None for c in RISK_CLASSES},
            "per_class_precision": {c: None for c in RISK_CLASSES},
            "per_class_recall": {c: None for c in RISK_CLASSES},
            "macro_f1": None,
            "confusion": {},
        }

    # Build confusion (gold → pred → count) over normalised labels.
    confusion: dict[str, dict[str, int]] = {}
    for r in labeled:
        gold = _normalise_risk_label(r.risk_label_gold) or "_unknown"
        pred = _normalise_risk_label(r.risk_label_pred) or "_unpredicted"
        confusion.setdefault(gold, {})
        confusion[gold][pred] = confusion[gold].get(pred, 0) + 1

    per_p: dict[str, float | None] = {}
    per_r: dict[str, float | None] = {}
    per_f: dict[str, float | None] = {}
    for cls in RISK_CLASSES:
        tp = sum(
            1
            for r in labeled
            if _normalise_risk_label(r.risk_label_gold) == cls
            and _normalise_risk_label(r.risk_label_pred) == cls
        )
        fp = sum(
            1
            for r in labeled
            if _normalise_risk_label(r.risk_label_gold) != cls
            and _normalise_risk_label(r.risk_label_pred) == cls
        )
        fn = sum(
            1
            for r in labeled
            if _normalise_risk_label(r.risk_label_gold) == cls
            and _normalise_risk_label(r.risk_label_pred) != cls
        )
        if tp + fp == 0 and tp + fn == 0:
            per_p[cls] = None
            per_r[cls] = None
            per_f[cls] = None
            continue
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        per_p[cls] = round(precision, 4)
        per_r[cls] = round(recall, 4)
        per_f[cls] = round(f1, 4)

    scored_f1 = [v for v in per_f.values() if v is not None]
    macro_f1 = round(sum(scored_f1) / len(scored_f1), 4) if scored_f1 else None

    return {
        "labeled_scenarios": len(labeled),
        "per_class_f1": per_f,
        "per_class_precision": per_p,
        "per_class_recall": per_r,
        "macro_f1": macro_f1,
        "confusion": confusion,
    }


def _compute_retrieval_metrics(
    results: list[ScenarioResult],
) -> dict[str, Any]:
    """Article-retrieval precision/recall/F1 against ``expected_references``.

    Weighted-mean across labeled scenarios. Scenarios with empty gold are
    skipped (so the metric reflects retrieval on the unambiguous subset
    only, not the full eval).
    """
    labeled = [r for r in results if r.expected_references]
    if not labeled:
        return {
            "labeled_scenarios": 0,
            "weighted_precision": None,
            "weighted_recall": None,
            "weighted_f1": None,
        }
    p_sum = 0.0
    r_sum = 0.0
    f_sum = 0.0
    for row in labeled:
        gold = set(row.expected_references)
        pred = set(row.predicted_references)
        tp = len(gold & pred)
        # Precision is 0.0 when predicted is empty per the spec — the
        # model cited nothing, so it "got 0 of its 0 citations right",
        # which we interpret strictly as recall-failure not vacuous-pass.
        precision = tp / len(pred) if pred else 0.0
        recall = tp / len(gold) if gold else 0.0
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        p_sum += precision
        r_sum += recall
        f_sum += f1
    n = len(labeled)
    return {
        "labeled_scenarios": n,
        "weighted_precision": round(p_sum / n, 4),
        "weighted_recall": round(r_sum / n, 4),
        "weighted_f1": round(f_sum / n, 4),
    }


def _run_scenario(client: TestClient, scenario: Scenario) -> ScenarioResult:
    """Execute one scenario against the route + apply its checks."""
    # Reset slowapi between calls so the per-IP anon bucket (30/min)
    # never trips inside a single eval batch.
    try:
        limiter.reset()
    except Exception:
        pass

    url = "/api/v1/regenold/eu-ai-act/ask"
    if scenario.query_param_telemetry:
        url += "?include_telemetry=true"

    start = time.perf_counter()
    resp = client.post(url, json=list(scenario.messages))
    duration_ms = (time.perf_counter() - start) * 1000.0

    # Body for checks — even on non-200 we want the structured-error JSON
    # so checks can branch on ``__http_status`` (e.g. injection scenarios
    # accept 4xx as a refusal).
    try:
        body = resp.json()
    except Exception:
        body = {"__decode_error": True}

    if not isinstance(body, dict):
        body = {"__non_dict_body": body}
    body = dict(body)
    body["__http_status"] = resp.status_code

    check_results: list[tuple[str, bool]] = []
    all_passed = True
    for check in scenario.checks:
        try:
            ok = bool(check.predicate(body))
        except Exception as exc:  # noqa: BLE001 — broken predicate is a fail
            ok = False
            check_results.append((f"{check.label} [error: {exc}]", False))
            all_passed = False
            continue
        check_results.append((check.label, ok))
        if not ok:
            all_passed = False

    excerpt = {
        "answer": (body.get("answer") or "")[:240],
        "references": body.get("references"),
        "http_status": resp.status_code,
    }
    if scenario.query_param_telemetry:
        for f in ("confidence", "retrieval_path", "kb_version", "nodes_traversed"):
            if f in body:
                excerpt[f] = body[f]

    quality = _compute_quality_flags(body)
    predicted_class = _predict_risk_class(body)
    predicted_refs = _predicted_ref_heads(body)
    return ScenarioResult(
        scenario_id=scenario.id,
        category=scenario.category,
        description=scenario.description,
        http_status=resp.status_code,
        response_excerpt=excerpt,
        check_results=check_results,
        passed=all_passed,
        duration_ms=duration_ms,
        risk_label_gold=scenario.risk_label,
        risk_label_pred=predicted_class,
        expected_references=scenario.expected_references,
        predicted_references=predicted_refs,
        **quality,
    )


def run_all() -> list[ScenarioResult]:
    """Run every scenario and return the result list.

    Snapshots + restores ``settings.regenold.api_key`` so the eval runner
    doesn't permanently mutate the module-level Pydantic settings object.
    Without this, a test that asserts the unconfigured-deploy 503 path
    fails if it runs AFTER the runner in the same pytest session.
    """
    _eval_key = "regenold-eval-key"
    prev_key = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_eval_key)
    try:
        with TestClient(app, headers={"X-Regenold-Api-Key": _eval_key}) as client:
            return [_run_scenario(client, s) for s in SCENARIOS]
    finally:
        settings.regenold.api_key = prev_key


def _diff_against_prior(
    results: list[ScenarioResult], prior_path: Path | None
) -> str:
    """Render a one-block diff vs the prior round's JSON snapshot.

    Catches silent regressions: a refactor that flips 2 scenarios from
    PASS→FAIL only shows up at OVERALL "249/251 (99.2%)" — easy to miss.
    With a diff the operator sees "REGRESSED: foo, bar" in the report.
    Empty string if there's no prior snapshot or no scenario flipped.
    """
    if not prior_path or not prior_path.exists():
        return ""
    try:
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    prior_by_id: dict[str, bool] = {
        s.get("id"): bool(s.get("passed"))
        for s in prior.get("scenarios", [])
        if s.get("id")
    }
    regressed = [
        r.scenario_id
        for r in results
        if not r.passed and prior_by_id.get(r.scenario_id) is True
    ]
    recovered = [
        r.scenario_id
        for r in results
        if r.passed and prior_by_id.get(r.scenario_id) is False
    ]
    new_scenarios = [
        r.scenario_id for r in results if r.scenario_id not in prior_by_id
    ]
    if not regressed and not recovered and not new_scenarios:
        return f"DIFF vs {prior_path.name}: no scenario flipped (PASS/FAIL parity)"
    lines = [f"DIFF vs {prior_path.name}:"]
    if regressed:
        lines.append(f"  REGRESSED ({len(regressed)}): {', '.join(regressed)}")
    if recovered:
        lines.append(f"  RECOVERED ({len(recovered)}): {', '.join(recovered)}")
    if new_scenarios:
        lines.append(f"  NEW ({len(new_scenarios)}): {len(new_scenarios)} scenarios")
    return "\n".join(lines)


def _format_report(
    results: list[ScenarioResult],
    *,
    prior_path: Path | None = None,
) -> str:
    """Human-readable per-category report with pass/fail counts."""
    by_cat: dict[str, list[ScenarioResult]] = {c: [] for c in CATEGORIES}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    lines: list[str] = []
    lines.append("=" * 76)
    lines.append("Regenold ask-API eval — categorised report")
    lines.append("=" * 76)
    total_pass = sum(1 for r in results if r.passed)
    total = len(results)
    lines.append(f"OVERALL: {total_pass}/{total} passed ({total_pass / total * 100:.1f}%)")
    # Diff vs prior round — surfaces silent flips at the top of the report.
    diff = _diff_against_prior(results, prior_path)
    if diff:
        lines.append(diff)
    # Regenold-rubric batch metrics
    if results:
        durations = [r.duration_ms for r in results]
        ref_conf = sum(1 for r in results if r.refs_conformant)
        sent_conf = sum(1 for r in results if r.answer_within_sentence_cap)
        ref_max = sum(1 for r in results if r.refs_within_max)
        lines.append(
            f"QUALITY: ref_format={ref_conf}/{total} "
            f"({ref_conf / total * 100:.0f}%) · "
            f"sentence_cap={sent_conf}/{total} "
            f"({sent_conf / total * 100:.0f}%) · "
            f"refs_within_max={ref_max}/{total} "
            f"({ref_max / total * 100:.0f}%)"
        )
        lines.append(
            f"LATENCY: p50={_percentile(durations, 50):.0f}ms · "
            f"p95={_percentile(durations, 95):.0f}ms · "
            f"max={max(durations):.0f}ms"
        )
        # Paper-aligned per-class F1 + article-retrieval block (Davvetas
        # et al., Section 5 / Table 4). Only printed when at least one
        # scenario carries a gold label — silence otherwise.
        cls_metrics = _compute_classification_metrics(results)
        ret_metrics = _compute_retrieval_metrics(results)
        if cls_metrics.get("labeled_scenarios", 0) > 0:
            per_f = cls_metrics.get("per_class_f1") or {}
            parts = []
            for cls in RISK_CLASSES:
                v = per_f.get(cls)
                if v is None:
                    parts.append(f"{cls}=–")
                else:
                    parts.append(f"{cls}={v:.2f}")
            macro_f1 = cls_metrics.get("macro_f1")
            macro_txt = f"{macro_f1:.2f}" if macro_f1 is not None else "–"
            lines.append(
                f"RISK_F1 (n={cls_metrics['labeled_scenarios']}): "
                f"{' · '.join(parts)} · macro={macro_txt}"
            )
        if ret_metrics.get("labeled_scenarios", 0) > 0:
            wp = ret_metrics.get("weighted_precision")
            wr = ret_metrics.get("weighted_recall")
            wf = ret_metrics.get("weighted_f1")
            lines.append(
                f"RETRIEVAL (n={ret_metrics['labeled_scenarios']}): "
                f"P={wp:.2f} · R={wr:.2f} · F1={wf:.2f}"
            )
    lines.append("")
    for cat in sorted(by_cat):
        rows = by_cat[cat]
        if not rows:
            continue
        cat_pass = sum(1 for r in rows if r.passed)
        lines.append(
            f"[{cat}] {cat_pass}/{len(rows)} passed "
            f"({cat_pass / len(rows) * 100:.0f}%)"
        )
        for r in rows:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  {status} · {r.scenario_id} · {r.description}")
            for label, ok in r.check_results:
                marker = "[+]" if ok else "[-]"
                lines.append(f"      {marker} {label}")
            if not r.passed:
                excerpt = r.response_excerpt
                lines.append(f"      → answer: {excerpt.get('answer', '')!r}")
                lines.append(f"      → references: {excerpt.get('references')}")
                lines.append(f"      → http_status: {excerpt.get('http_status')}")
        lines.append("")
    return "\n".join(lines)


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (no numpy dep). ``pct`` in [0, 100]."""
    if not values:
        return 0.0
    s = sorted(values)
    if pct <= 0:
        return s[0]
    if pct >= 100:
        return s[-1]
    # Nearest-rank: ceil(p/100 * N) is the 1-indexed rank.
    rank = max(1, int((pct / 100.0) * len(s) + 0.5))
    rank = min(rank, len(s))
    return s[rank - 1]


def _serialise_results(results: list[ScenarioResult]) -> dict[str, Any]:
    """JSON-friendly summary suitable for tracking baseline vs post-fix.

    Adds Regenold-rubric quality metrics (Conciseness / Reference Format
    / Latency) on top of the binary correctness gate so a regression
    that quietly breaks format-conformance is visible in the JSON
    report even when every per-scenario check still passes.
    """
    by_cat: dict[str, dict[str, int]] = {}
    for r in results:
        cat_bucket = by_cat.setdefault(r.category, {"passed": 0, "total": 0})
        cat_bucket["total"] += 1
        if r.passed:
            cat_bucket["passed"] += 1

    durations = [r.duration_ms for r in results]
    refs_conformant = sum(1 for r in results if r.refs_conformant)
    answers_within_cap = sum(1 for r in results if r.answer_within_sentence_cap)
    refs_within_max = sum(1 for r in results if r.refs_within_max)
    total = len(results) or 1  # never divide by zero

    quality = {
        "reference_format_conformance_pct": round(refs_conformant / total * 100, 1),
        "answer_sentence_cap_conformance_pct": round(answers_within_cap / total * 100, 1),
        "references_within_max_pct": round(refs_within_max / total * 100, 1),
        "avg_refs_per_scenario": round(
            sum(r.refs_count for r in results) / total, 2
        ),
        "avg_sentences_per_answer": round(
            sum(r.answer_sentence_count for r in results) / total, 2
        ),
        "latency_p50_ms": round(_percentile(durations, 50), 2),
        "latency_p95_ms": round(_percentile(durations, 95), 2),
        "latency_max_ms": round(max(durations) if durations else 0.0, 2),
        "risk_classification": _compute_classification_metrics(results),
        "article_retrieval": _compute_retrieval_metrics(results),
    }

    return {
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "by_category": by_cat,
            "quality": quality,
        },
        "scenarios": [
            {
                "id": r.scenario_id,
                "category": r.category,
                "description": r.description,
                "passed": r.passed,
                "http_status": r.http_status,
                "checks": [{"label": label, "passed": ok} for label, ok in r.check_results],
                "response_excerpt": r.response_excerpt,
                "duration_ms": round(r.duration_ms, 2),
                "refs_conformant": r.refs_conformant,
                "answer_within_sentence_cap": r.answer_within_sentence_cap,
                "refs_within_max": r.refs_within_max,
                "refs_count": r.refs_count,
                "answer_sentence_count": r.answer_sentence_count,
                "risk_label_gold": r.risk_label_gold,
                "risk_label_pred": r.risk_label_pred,
                "expected_references": list(r.expected_references),
                "predicted_references": list(r.predicted_references),
            }
            for r in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    # The human-readable report uses ``->`` arrow and ``·`` separators
    # which the Windows default cp1252 stdout cannot encode. Reconfigure
    # to utf-8 with a replacement fallback so the report prints cleanly
    # everywhere instead of crashing with UnicodeEncodeError mid-output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 — best-effort; never block eval
                pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        help="If set, write the JSON results to this path.",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="adhoc",
        help="Label tagged on the JSON output (e.g. 'baseline', 'post-fix').",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable report (only emit JSON).",
    )
    parser.add_argument(
        "--prior",
        type=Path,
        default=None,
        help=(
            "Path to a prior eval JSON snapshot. When set, the report "
            "includes a DIFF block listing scenarios that regressed (passed "
            "previously, failed now) and recovered (vice versa). Defaults to "
            "the latest evals/regenold_results_*.json sibling of the --json target."
        ),
    )
    args = parser.parse_args(argv)

    # Default --prior to the most recent snapshot if not explicitly set.
    prior_path: Path | None = args.prior
    if prior_path is None and args.json is not None:
        candidates = sorted(
            args.json.parent.glob("regenold_results_*.json"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        # Skip the target itself if it already exists.
        candidates = [p for p in candidates if p != args.json]
        if candidates:
            prior_path = candidates[0]

    results = run_all()

    if not args.quiet:
        print(_format_report(results, prior_path=prior_path))

    if args.json:
        payload = _serialise_results(results)
        payload["label"] = args.label
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON results written to {args.json}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

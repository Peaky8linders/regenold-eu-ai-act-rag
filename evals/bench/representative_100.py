"""R76 — Representative top-100 EU AI Act benchmark.

Builds a stratified, LLM-categorised representative sample of 100
questions drawn from the **real-world** ``davidath/ai-act-evaluation-
benchmark`` dataset (137 QA + 339 scenarios, CC-BY-4.0, paper
arXiv:2603.09435) plus constructed multi-turn chains, covering every
question category the EU AI Act is asked about — including multi-turn.

## Why this exists

The in-sample ``evals.bench.runner`` scores all 476 davidath rows. For a
representative *sample* the competition can read at a glance, we need a
balanced 100-row subset that:

  * mirrors the true category distribution of the real-world pool
    (stratified-proportional — no category over/under-represented),
  * is selected blind to our system's output (an LLM judge categorises
    + rates each question for representativeness; the selection never
    sees how our wire answers it — hence "no bias"),
  * guarantees multi-turn coverage (a fixed quota of conversation
    chains),
  * is fully reproducible (the stratified selection is purely
    order-based — sorted by representativeness then item id, no RNG;
    the LLM categorisation is cached to disk).

## Pipeline

  1. ``build_pool()``        — load davidath QA + scenarios + build
                               multi-turn chains.
  2. ``categorize_pool()``   — Sonnet labels every pool item with a
                               category + representativeness 1-10
                               (cached to ``data/``; re-runs are free).
  3. ``select_representative()`` — stratified-proportional pick of 100.
  4. ``run_wire()``          — run each of the 100 through the Regenold
                               wire, emit judge-compatible rows.
  5. JSON sidecar at ``results/representative-100-<label>.json`` — the
     ``evals.judge.runner`` reads its ``rows`` bucket directly.

CLI:
    py -3.12 -m evals.bench.representative_100 --label r76
    py -3.12 -m evals.bench.representative_100 --label smoke --limit 12
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.rate_limit import limiter

from evals.bench import dataset as bench_dataset
from evals.bench import metrics

_EVAL_KEY = "regenold-representative-eval-key"
_DATA_DIR = Path(__file__).parent / "data"
_RESULTS_DIR = Path(__file__).parent / "results"
_CACHE_PATH = _DATA_DIR / "representative_pool_categorized.json"

# Single-turn taxonomy. Every davidath QA + scenario maps to exactly one.
# Multi-turn chains carry the dedicated ``multi_turn`` category.
_TAXONOMY: tuple[str, ...] = (
    "definition",             # what is X / how is Y defined
    "risk_classification",    # prohibited / high-risk / limited / minimal
    "prohibited_practice",    # Article 5 prohibitions
    "provider_obligation",    # obligations on providers of high-risk AI
    "deployer_obligation",    # obligations on deployers / other operators
    "gpai",                   # general-purpose AI models / systemic risk
    "transparency",           # Article 50 disclosure / deepfakes / chatbots
    "governance_enforcement", # authorities, penalties, market surveillance
    "scope_applicability",    # who must comply, exemptions, territory, dates
    "procedural",             # conformity assessment, registration, tech docs
)
_MULTITURN_CATEGORY = "multi_turn"
_ALL_CATEGORIES: tuple[str, ...] = _TAXONOMY + (_MULTITURN_CATEGORY,)

_TARGET_N = 100
_MULTITURN_QUOTA = 20  # of the 100 — guarantees conversation coverage


# ── Pool item ────────────────────────────────────────────────────────────


@dataclass
class PoolItem:
    """One candidate question for the representative sample."""

    item_id: str
    kind: str  # "qa" | "scenario" | "multiturn"
    # Single-turn: ``question`` set, ``messages`` empty.
    # Multi-turn:  ``messages`` set (user turns only), ``question`` is a
    #              readable flattened form for the judge prompt.
    question: str
    messages: list[dict[str, str]] = field(default_factory=list)
    gold_answer: str = ""
    gold_articles: list[int] = field(default_factory=list)
    category: str = ""
    representativeness: float = 0.0
    source: str = "davidath"
    # For multi-turn items: the pool id of the scenario the chain was
    # built from. Lets categorize_pool read the right scenario's
    # representativeness rating (the build stride means mt_N is NOT
    # built from sc_N).
    source_scenario_id: str = ""


# ── Pool construction ────────────────────────────────────────────────────


# The scenario->question conversion lives in evals.bench.dataset
# (``scenario_to_question``) so the davidath runner + this benchmark
# share one canonical question shape (no drift). Used via
# ``bench_dataset.scenario_to_question`` below.

_MULTITURN_FOLLOWUP = (
    "Given that classification, what are the key obligations we must "
    "comply with, and which Articles of the EU AI Act set them out?"
)


def build_pool() -> list[PoolItem]:
    """Load the davidath dataset and build the full candidate pool.

    Returns QA + scenario single-turn items plus 50 constructed
    multi-turn chains (a deterministic spread across risk levels). The
    multi-turn follow-up is topic-consistent so the final-turn gold
    stays equal to the scenario's ``related_articles``.
    """
    qa = bench_dataset.load_qa_pairs()
    scenarios = bench_dataset.load_scenarios()

    pool: list[PoolItem] = []

    for i, row in enumerate(qa):
        q = (row.get("question") or "").strip()
        if not q:
            continue
        rel = row.get("relevant_article")
        gold_articles = [int(rel)] if isinstance(rel, int) else []
        pool.append(
            PoolItem(
                item_id=f"qa_{i:03d}",
                kind="qa",
                question=q,
                gold_answer=(row.get("answer") or "").strip(),
                gold_articles=gold_articles,
            )
        )

    for i, s in enumerate(scenarios):
        rel = s.get("related_articles") or []
        gold_articles = [int(a) for a in rel if a is not None]
        obligations = s.get("obligations") or []
        gold_answer = (
            f"This system is classified as {s.get('risk_level', '')}. "
            + " ".join(obligations[:4])
        ).strip()
        pool.append(
            PoolItem(
                item_id=f"sc_{i:03d}",
                kind="scenario",
                question=bench_dataset.scenario_to_question(s),
                gold_answer=gold_answer,
                gold_articles=gold_articles,
                category="",  # categorised by the LLM pass
            )
        )

    # Multi-turn chains — a deterministic stride across the scenario list
    # so the 50 chains span all four risk tiers.
    mt_count = 50
    if scenarios:
        stride = max(1, len(scenarios) // mt_count)
        picked = scenarios[::stride][:mt_count]
        for i, s in enumerate(picked):
            rel = s.get("related_articles") or []
            gold_articles = [int(a) for a in rel if a is not None]
            obligations = s.get("obligations") or []
            turn1 = bench_dataset.scenario_to_question(s)
            gold_answer = (
                f"This system is classified as {s.get('risk_level', '')}. "
                + " ".join(obligations[:4])
            ).strip()
            # mt_N is built from scenarios[N * stride] — record that
            # scenario's pool id so categorize_pool reads the right
            # representativeness rating.
            pool.append(
                PoolItem(
                    item_id=f"mt_{i:03d}",
                    kind="multiturn",
                    question=(
                        f"[Turn 1] {turn1}  [Turn 2] {_MULTITURN_FOLLOWUP}"
                    ),
                    messages=[
                        {"role": "user", "content": turn1},
                        {"role": "user", "content": _MULTITURN_FOLLOWUP},
                    ],
                    gold_answer=gold_answer,
                    gold_articles=gold_articles,
                    category=_MULTITURN_CATEGORY,
                    source_scenario_id=f"sc_{i * stride:03d}",
                )
            )

    return pool


# ── LLM categorisation (cached) ──────────────────────────────────────────


_CATEGORIZE_SYSTEM = (
    "You are an EU AI Act domain expert building an unbiased, "
    "representative evaluation set. You classify questions by topic and "
    "rate how representative/canonical each is. Respond with ONE JSON "
    "array only — no preamble, no markdown fences."
)


def _categorize_prompt(batch: list[tuple[int, str]]) -> str:
    cats = ", ".join(_TAXONOMY)
    lines = [f"  {i}: {q[:400]}" for i, q in batch]
    return (
        "Classify each EU AI Act question below into exactly ONE category "
        f"from this fixed list:\n  {cats}\n\n"
        "Also rate 'representativeness' 1-10: how canonical, clear and "
        "typical this is as an EU AI Act question a real practitioner "
        "would ask (10 = a textbook representative question; 1 = "
        "malformed, ambiguous or a fringe edge case). Rate ONLY the "
        "question's quality as an exemplar — do NOT consider how hard it "
        "is or how any system might answer it.\n\n"
        "QUESTIONS:\n" + "\n".join(lines) + "\n\n"
        "Respond with ONE JSON array, one object per question:\n"
        '[{"i": <index>, "category": "<one category>", '
        '"representativeness": <1-10>}]'
    )


def _parse_json_array(text: str) -> list[dict[str, Any]] | None:
    """Extract the first balanced JSON array that parses to a list.

    Tries EVERY ``[`` position, not just the first — Sonnet sometimes
    prefixes a sentence containing a bracket (e.g. ``[the questions]``)
    before the real array; hard-stopping at the first ``[`` would drop
    a whole 12-item batch to the deterministic fallback.
    """
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    pos = 0
    while True:
        start = s.find("[", pos)
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "[":
                depth += 1
            elif s[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(s[start:i + 1])
                        if isinstance(parsed, list):
                            return parsed
                    except Exception:  # noqa: BLE001
                        pass
                    break  # this span isn't a JSON list — try the next [
        pos = start + 1


def _deterministic_category(item: PoolItem) -> str:
    """Fallback category when the LLM is unavailable — derived from the
    davidath structure so the module still runs end-to-end offline."""
    if item.kind == "multiturn":
        return _MULTITURN_CATEGORY
    if item.kind == "scenario":
        return "risk_classification"
    art = item.gold_articles[0] if item.gold_articles else 0
    if art in (1, 2):
        return "scope_applicability"
    if art == 3:
        return "definition"
    if art == 5:
        return "prohibited_practice"
    if art == 50:
        return "transparency"
    if art in (51, 52, 53, 54, 55, 56):
        return "gpai"
    if art in (11, 17, 18, 43, 44, 47, 48, 49, 72):
        return "procedural"
    if art in (26, 27):
        return "deployer_obligation"
    if art >= 64 or art in (74, 78, 79, 99):
        return "governance_enforcement"
    if art in (113,):
        return "scope_applicability"
    if 8 <= art <= 25:
        return "provider_obligation"
    return "scope_applicability"


def categorize_pool(
    pool: list[PoolItem], *, use_llm: bool = True, verbose: bool = False
) -> None:
    """Populate ``category`` + ``representativeness`` on every pool item.

    Single-turn items are sent to Sonnet in batches of 12; the result is
    cached to ``_CACHE_PATH`` keyed by item id so a re-run is free and
    byte-reproducible. Multi-turn items get the fixed ``multi_turn``
    category and inherit a representativeness rating. On any LLM failure
    the item falls back to :func:`_deterministic_category`.
    """
    cache: dict[str, dict[str, Any]] = {}
    if _CACHE_PATH.exists():
        try:
            cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache = {}

    provider = None
    wrapper_req_cls = None
    if use_llm:
        try:
            from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
                OpenAIWrapperRequest,
                get_openai_wrapper_provider,
                is_openai_wrapper_enabled,
            )
            if is_openai_wrapper_enabled():
                provider = get_openai_wrapper_provider()
                wrapper_req_cls = OpenAIWrapperRequest
        except Exception:  # noqa: BLE001
            provider = None

    single = [it for it in pool if it.kind != "multiturn"]
    uncached = [it for it in single if it.item_id not in cache]

    if provider is not None and wrapper_req_cls is not None and uncached:
        # 120-per-batch → only ~4 wrapper calls for the full 476-item
        # pool. The local wrapper degrades under dozens of sequential
        # calls (each call drives a Claude Code CLI process), so call
        # COUNT — not per-call token size — is the dominant cost.
        batch_size = 120
        for b in range(0, len(uncached), batch_size):
            chunk = uncached[b:b + batch_size]
            batch = [(j, it.question) for j, it in enumerate(chunk)]
            prompt = _categorize_prompt(batch)
            req = wrapper_req_cls(
                system=_CATEGORIZE_SYSTEM,
                user=prompt,
                model="claude-sonnet-4-6",
                max_tokens=4500,
                temperature=0.0,
                timeout_seconds=240.0,
            )
            parsed: list[dict[str, Any]] | None = None
            try:
                resp = provider.complete(req)
                if resp is not None and not resp.error:
                    parsed = _parse_json_array(resp.text or "")
            except Exception:  # noqa: BLE001
                parsed = None
            by_idx: dict[int, dict[str, Any]] = {}
            for obj in parsed or []:
                if isinstance(obj, dict) and "i" in obj:
                    try:
                        by_idx[int(obj["i"])] = obj
                    except Exception:  # noqa: BLE001
                        pass
            for j, it in enumerate(chunk):
                obj = by_idx.get(j) or {}
                cat = str(obj.get("category") or "").strip()
                if cat not in _TAXONOMY:
                    cat = _deterministic_category(it)
                try:
                    rep = float(obj.get("representativeness", 5.0))
                except Exception:  # noqa: BLE001
                    rep = 5.0
                rep = max(1.0, min(10.0, rep))
                cache[it.item_id] = {"category": cat, "representativeness": rep}
            if verbose:
                print(
                    f"[categorize] {min(b + batch_size, len(uncached))}/"
                    f"{len(uncached)} single-turn items",
                    flush=True,
                )
        try:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _tmp = _CACHE_PATH.with_name(_CACHE_PATH.name + ".tmp")
            _tmp.write_text(
                json.dumps(cache, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _tmp.replace(_CACHE_PATH)  # atomic swap — never a torn cache
        except Exception as exc:  # noqa: BLE001
            print(
                f"[categorize] WARNING: cache write failed: {exc}",
                file=sys.stderr, flush=True,
            )

    # Apply cache / fallback to every item.
    for it in pool:
        if it.kind == "multiturn":
            it.category = _MULTITURN_CATEGORY
            # Representativeness inherited from the SOURCE scenario the
            # chain was built from (source_scenario_id — the build
            # stride means mt_N is NOT built from sc_N).
            base = it.source_scenario_id or it.item_id.replace("mt_", "sc_")
            it.representativeness = float(
                (cache.get(base) or {}).get("representativeness", 6.0)
            )
            continue
        entry = cache.get(it.item_id)
        if entry:
            it.category = str(entry.get("category") or "")
            it.representativeness = float(entry.get("representativeness", 5.0))
        if it.category not in _TAXONOMY:
            it.category = _deterministic_category(it)
        if it.representativeness <= 0:
            it.representativeness = 5.0


# ── Stratified-proportional selection ────────────────────────────────────


def select_representative(
    pool: list[PoolItem],
    *,
    n: int = _TARGET_N,
    mt_quota: int = _MULTITURN_QUOTA,
) -> list[PoolItem]:
    """Pick ``n`` items: ``mt_quota`` multi-turn + the rest stratified
    proportionally across the single-turn taxonomy.

    Unbiased by construction:
      * each single-turn category gets a slot count proportional to its
        share of the single-turn pool (largest-remainder rounding),
      * within a category the highest-representativeness items win
        (ties broken by item id — fully deterministic),
      * the selection never inspects our system's output.
    """
    multiturn = sorted(
        (it for it in pool if it.kind == "multiturn"),
        key=lambda it: (-it.representativeness, it.item_id),
    )
    single = [it for it in pool if it.kind != "multiturn"]

    mt_take = min(mt_quota, len(multiturn))
    single_target = n - mt_take

    # Bucket single-turn items by category.
    buckets: dict[str, list[PoolItem]] = {c: [] for c in _TAXONOMY}
    for it in single:
        buckets.setdefault(it.category, []).append(it)

    total_single = sum(len(v) for v in buckets.values()) or 1
    # Largest-remainder apportionment.
    raw = {
        c: single_target * len(buckets[c]) / total_single
        for c in _TAXONOMY
    }
    alloc = {c: int(raw[c]) for c in _TAXONOMY}
    remainder = single_target - sum(alloc.values())
    for c in sorted(_TAXONOMY, key=lambda c: (-(raw[c] - alloc[c]), c)):
        if remainder <= 0:
            break
        alloc[c] += 1
        remainder -= 1

    selected: list[PoolItem] = list(multiturn[:mt_take])
    for c in _TAXONOMY:
        ranked = sorted(
            buckets.get(c, []),
            key=lambda it: (-it.representativeness, it.item_id),
        )
        take = min(alloc[c], len(ranked))
        selected.extend(ranked[:take])

    # If a thin category under-delivered, top up from the highest-
    # representativeness leftovers so we always land exactly ``n``.
    if len(selected) < n:
        chosen = {it.item_id for it in selected}
        leftovers = sorted(
            (it for it in single if it.item_id not in chosen),
            key=lambda it: (-it.representativeness, it.item_id),
        )
        selected.extend(leftovers[: n - len(selected)])

    return selected[:n]


# ── Wire execution ───────────────────────────────────────────────────────


def _ask(
    client: TestClient, messages: list[dict[str, str]]
) -> tuple[dict, float, int]:
    """POST a conversation to the Regenold wire.

    Returns ``(body, elapsed_ms, http_status)``. The status lets the
    caller tell a genuine empty/refusal answer apart from a wire
    failure (401/403/422/5xx) that would otherwise be scored as a
    silent zero row.
    """
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass
    start = time.perf_counter()
    resp = client.post("/api/v1/regenold/eu-ai-act/ask", json=messages)
    elapsed = (time.perf_counter() - start) * 1000.0
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {}
    if not isinstance(body, dict):
        body = {}
    return body, elapsed, resp.status_code


_KW_STOP = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "as", "is", "are", "be", "this", "that", "system", "systems", "ai",
    "act", "under", "must", "shall", "which", "what", "when", "their",
    "classified",
})
_KW_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")


def _keywords(text: str) -> list[str]:
    """Content keywords from a gold answer — primes the judge prompt."""
    seen: list[str] = []
    for tok in _KW_RE.findall((text or "").lower()):
        if len(tok) >= 4 and tok not in _KW_STOP and tok not in seen:
            seen.append(tok)
    return seen[:24]


def run_wire(
    selection: list[PoolItem],
    *,
    verbose: bool = False,
    endpoint: str | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Run every selected item through the wire; emit judge-ready rows.

    Two modes:

    * ``endpoint`` unset — in-process FastAPI ``TestClient`` (deterministic,
      no network, the reproducible default).
    * ``endpoint`` set — POST to the LIVE Regenold endpoint over HTTP
      (production path: Railway -> Cloudflare named tunnel -> the Claude
      Max wrapper). ``api_key`` is sent as the ``X-Regenold-Api-Key``
      header. Transient Cloudflare-tunnel idle-kills are absorbed by
      ``_http_retry.post_json_with_retry``.

    Each row carries the fields ``evals.judge.runner`` + ``evals.bench.
    metrics`` both consume: ``id, category, question, expected_keywords,
    expected_refs, predicted_answer, pred_refs, gold_answer,
    gold_articles, http_status, latency_ms``.
    """
    rows: list[dict[str, Any]] = []

    def _process(asker) -> None:
        for idx, it in enumerate(selection):
            if it.kind == "multiturn":
                # Turn 1, then feed its answer back as the assistant
                # turn before posting the coreferent follow-up.
                body1, lat1, _st1 = asker([it.messages[0]])
                answer1 = str(body1.get("answer") or "")
                history = [
                    it.messages[0],
                    {"role": "assistant", "content": answer1},
                    it.messages[1],
                ]
                body, lat2, status = asker(history)
                latency = lat1 + lat2
            else:
                body, latency, status = asker(
                    [{"role": "user", "content": it.question}]
                )
            answer = str(body.get("answer") or "")
            refs = body.get("references") or []
            if not isinstance(refs, list):
                refs = []
            # The wire's `reasoning` field — when the endpoint is hit
            # with `?include_reasoning=true` this carries the R50
            # ReasoningTrace JSON (scope verdict, anchors, retrieval
            # path, stage2_landed, confidence). Captured for diagnostics;
            # the judge + metrics ignore it.
            rows.append({
                "id": it.item_id,
                "category": it.category,
                "kind": it.kind,
                "question": it.question,
                "representativeness": round(it.representativeness, 2),
                "expected_keywords": _keywords(it.gold_answer),
                "expected_refs": [f"Article {a}" for a in it.gold_articles],
                "gold_answer": it.gold_answer,
                "gold_articles": it.gold_articles,
                "predicted_answer": answer,
                "answer_preview": answer[:240],
                "pred_refs": [str(r) for r in refs],
                "reasoning": body.get("reasoning"),
                "http_status": status,
                "latency_ms": round(latency, 2),
            })
            if verbose:
                flag = "" if status == 200 else f"  !! HTTP-{status}"
                print(
                    f"[wire] {idx + 1}/{len(selection)} {it.item_id:<10} "
                    f"cat={it.category:<22} refs={len(refs)} "
                    f"{latency:.0f}ms{flag}",
                    flush=True,
                )
        non_200 = sum(1 for r in rows if r.get("http_status") != 200)
        if non_200:
            print(
                f"[wire] WARNING: {non_200}/{len(rows)} rows returned a "
                f"non-200 HTTP status — scored as empty-answer rows.",
                flush=True,
            )

    if endpoint:
        # Live production path — no settings mutation, real HTTP.
        from evals.bench._http_retry import (  # noqa: PLC0415
            post_json_with_retry,
        )

        def _asker(messages: list[dict[str, str]]):
            body, latency, status, _err, _att, _retried = (
                post_json_with_retry(
                    endpoint, messages, api_key, timeout=180.0,
                )
            )
            return body, latency, status

        if verbose:
            print(f"[wire] LIVE endpoint: {endpoint}", flush=True)
        _process(_asker)
    else:
        prev_key = settings.regenold.api_key
        settings.regenold.api_key = SecretStr(_EVAL_KEY)
        try:
            with TestClient(
                app, headers={"X-Regenold-Api-Key": _EVAL_KEY}
            ) as client:
                _process(lambda messages: _ask(client, messages))
        finally:
            settings.regenold.api_key = prev_key
    return rows


# ── Scoring ──────────────────────────────────────────────────────────────


def score_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic 8-axis metrics, overall + per category."""
    def _score(row: dict[str, Any]) -> metrics.RowScore:
        gold_articles: int | list[int] | None
        ga = row.get("gold_articles") or []
        gold_articles = ga if ga else None
        return metrics.score_row(
            pred_answer=row.get("predicted_answer") or "",
            pred_refs=row.get("pred_refs") or [],
            gold_answer=row.get("gold_answer") or "",
            gold_articles=gold_articles,
            latency_ms=float(row.get("latency_ms") or 0.0),
            expected_keywords=row.get("expected_keywords"),
        )

    all_scores = [_score(r) for r in rows]
    by_cat: dict[str, list[metrics.RowScore]] = {}
    for r, sc in zip(rows, all_scores):
        by_cat.setdefault(r.get("category") or "?", []).append(sc)

    return {
        "overall": metrics.aggregate(all_scores),
        "by_category": {
            c: metrics.aggregate(v) for c, v in sorted(by_cat.items())
        },
    }


# ── Orchestration ────────────────────────────────────────────────────────


def run(
    *,
    label: str = "adhoc",
    limit: int | None = None,
    use_llm: bool = True,
    verbose: bool = False,
    endpoint: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Build the pool, select 100, run the wire, persist a sidecar.

    When ``endpoint`` is set the wire run hits the LIVE Regenold
    endpoint (production: Railway -> Cloudflare tunnel -> Claude Max),
    authenticated with ``api_key``. Otherwise it uses the in-process
    deterministic TestClient.

    Returns the persisted payload (sidecar path under ``sidecar_path``).
    """
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    pool = build_pool()
    categorize_pool(pool, use_llm=use_llm, verbose=verbose)

    target = limit or _TARGET_N
    mt_quota = _MULTITURN_QUOTA if limit is None else max(2, target // 5)
    selection = select_representative(pool, n=target, mt_quota=mt_quota)

    rows = run_wire(
        selection, verbose=verbose, endpoint=endpoint, api_key=api_key,
    )
    scores = score_rows(rows)
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    cat_dist: dict[str, int] = {}
    for it in selection:
        cat_dist[it.category] = cat_dist.get(it.category, 0) + 1

    payload: dict[str, Any] = {
        "label": label,
        "benchmark": "representative-100",
        "dataset": "davidath/ai-act-evaluation-benchmark (CC-BY-4.0)",
        "dataset_fingerprint": bench_dataset.dataset_fingerprint(),
        "started_at": started_at,
        "finished_at": finished_at,
        "pool_size": len(pool),
        "selected": len(selection),
        "selection_method": "stratified-proportional, order-based (no RNG)",
        "wire_mode": f"live:{endpoint}" if endpoint else "testclient-deterministic",
        "category_distribution": cat_dist,
        "scores": scores,
        "rows": rows,
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sidecar = _RESULTS_DIR / f"representative-100-{label}.json"
    sidecar.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    payload["sidecar_path"] = str(sidecar)
    return payload


def _format(payload: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"Representative-100 benchmark — label={payload['label']!r}")
    out.append(f"pool={payload['pool_size']}  selected={payload['selected']}")
    out.append("=" * 78)
    out.append("\nCategory distribution of the selected set:")
    for c in sorted(payload["category_distribution"]):
        out.append(f"  {c:<24} {payload['category_distribution'][c]}")
    ov = payload["scores"]["overall"]
    out.append("\n[OVERALL] n=" + str(ov.get("n", 0)))
    for k in (
        "ans_correctness_loose", "ans_correctness_strict", "ans_conciseness",
        "ref_correctness_loose", "ref_correctness_strict", "ref_conciseness",
        "regulatory_tone",
    ):
        out.append(f"  {k:<26} {ov.get(k, '-')}")
    out.append(
        f"  latency  p50={ov.get('latency_p50_ms', '-')}ms "
        f"p95={ov.get('latency_p95_ms', '-')}ms "
        f"max={ov.get('latency_max_ms', '-')}ms"
    )
    out.append("\n[BY CATEGORY]  (ans_strict / ref_loose / ref_strict)")
    for c, agg in payload["scores"]["by_category"].items():
        out.append(
            f"  {c:<24} n={agg.get('n', 0):<3} "
            f"{agg.get('ans_correctness_strict', '-')} / "
            f"{agg.get('ref_correctness_loose', '-')} / "
            f"{agg.get('ref_correctness_strict', '-')}"
        )
    out.append(f"\nsidecar: {payload.get('sidecar_path', '?')}")
    out.append(
        "judge:   py -3.12 -m evals.judge.runner --bench-sidecar "
        f"{payload.get('sidecar_path', '?')} --label {payload['label']}"
    )
    return "\n".join(out)


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
        "--limit", type=int, default=None,
        help="Cap selection at N rows (smoke testing). Default 100.",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Skip LLM categorisation; use the deterministic fallback.",
    )
    parser.add_argument(
        "--endpoint", default=None,
        help=(
            "LIVE Regenold endpoint URL. When set, the wire run POSTs "
            "over HTTP (Railway -> Cloudflare tunnel -> Claude Max) "
            "instead of the in-process TestClient."
        ),
    )
    parser.add_argument(
        "--api-key", default=None,
        help="X-Regenold-Api-Key value for the live endpoint.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    payload = run(
        label=args.label,
        limit=args.limit,
        use_llm=not args.no_llm,
        verbose=args.verbose,
        endpoint=args.endpoint,
        api_key=args.api_key,
    )
    print(_format(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

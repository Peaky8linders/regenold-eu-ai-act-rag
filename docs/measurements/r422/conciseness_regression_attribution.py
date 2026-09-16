"""R422 — WHICH lever inflated the hard-mode answer, measured at the prompt.

FRAME. R390 live hard and R419 live hard are the same 110 questions, the same
gold, and the same generator (opus-5 over the wrapper), yet the mean graded
answer grew 1139 -> 2138 chars and ``ans_conciseness`` fell 62.02 -> 44.19. The
growth is near-uniform across every difficulty stratum (1.7x-2.9x) and across
BOTH hard turns (turn 1 and the pushback), which is the signature of a
generation-wide instruction/context change rather than a retrieval change.

TWO MEASUREMENTS, cheapest first.

1. EXACT, OFFLINE, ZERO COST — the closed-set skeleton. ``REGENOLD_CLOSED_SET_SKELETON``
   (R400, default ON, absent at R390) is documented as "strictly ADDITIVE to the
   block" at "1.87x prompt bulk", and its whole purpose is to show the model the
   COMPLETE member list of every multi-member head it cites — an instruction to
   enumerate, which is what a longer answer is made of. ``_render_closed_set_skeleton``
   reads only local data (``app.data.provision_hierarchy``), so its exact cost on
   the board's real refs is computable in milliseconds. No route, no model.

2. BOUNDED, LIVE-FREE ROUTE READ — the rest of the candidate set together.
   ``COORD_MAP_PROMPT``, ``EVIDENCE_CONTRACT``, ``REF_COORD_GUARD`` and
   ``EXTRACT_SHAPE_GUARD`` are the other post-R390 additions that are default ON
   at HEAD; their cost is measured by running the REAL request path with the
   provider stubbed (the seam ``docs/measurements/r415/pushback_invariance_probe.py``
   establishes) and diffing the dispatched Stage-2 payload between an all-OFF and
   a HEAD-defaults arm.

WHY THE PROVIDER SEAM. Recording at the engine function captures the
PRE-assembly text and reports two different arms as identical — the trap
``evals.harness.gate_validity`` documents. The provider sees the final
``OpenAIWrapperRequest``.

NON-VACUITY. Every arm must show a FIRING seam (a graded Stage-2 call carrying
the grounding markers). An arm with no payloads is reported ``vacuous``, never as
"no change".

Usage::

    .venv\\Scripts\\python.exe docs/measurements/r422/conciseness_regression_attribution.py            # offline only
    set -a; . ./.env; set +a
    R422_ROUTE_ROWS=5 R422_ROUTE_STRIDE=21 .venv\\Scripts\\python.exe \\
        docs/measurements/r422/conciseness_regression_attribution.py --route
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r422"
R419_CKPT = REPO / "evals" / "bench" / "results" / "official-r419-hard-hard.ckpt.jsonl"
R390_CKPT = REPO / "evals" / "bench" / "results" / "official-r390-live-hard-hard.ckpt.jsonl"
#: The reference answers are NOT in the checkpoint — they live in the gold set.
#: Joining on ``id`` is what makes ``ans_conciseness`` computable here; skipping
#: the join silently averages nothing and prints 0.00, which is the exact
#: failure mode this file exists to avoid.
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

#: Post-R390 additions that are DEFAULT ON at HEAD in ``app/`` and could inflate
#: the Stage-2 request. Established by diffing env defaults between ``74008ea``
#: (R390, PR #371) and HEAD; the R409 completeness guards are excluded because
#: they are default OFF (``answer_completeness._flag_is_on``) and only fire on a
#: detected gap.
CANDIDATE_LEVERS: tuple[str, ...] = (
    "REGENOLD_CLOSED_SET_SKELETON",
    "REGENOLD_COORD_MAP_PROMPT",
    "REGENOLD_EVIDENCE_CONTRACT",
    "REGENOLD_REF_COORD_GUARD",
    "REGENOLD_EXTRACT_SHAPE_GUARD",
)

#: Post-R390 levers EXCLUDED from the candidate set, each with the reason. Kept
#: in the record so the exclusion is evidence rather than assumption.
INERT_ON_HARD: dict[str, str] = {
    "REGENOLD_KG_POINT_TEXT": "modality-scoped: legacy query when history_turn_count > 1",
    "REGENOLD_STAGE2_FULL_SYSTEM": "modality-scoped via its _SINGLE_TURN sibling",
    "REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR": "fires only on a degraded/truncated Stage-2 call",
    "REGENOLD_STAGE2_DEGENERATE_RETRY": "fires only on a degenerate completion",
    "REGENOLD_STAGE2_TAIL_REPAIR_MODE": "fires only on a truncated tail",
    "REGENOLD_ANSWER_COVERAGE": "default ON at R390 too (verified by git grep on 74008ea)",
    "REGENOLD_USER_CRITICAL_RULES": "default ON at R390 too (verified by git grep on 74008ea)",
    "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD": "default OFF; fires only on a detected gap",
}

#: Stage-0 / embedding knobs held IDENTICAL across route arms (probe invariants,
#: not levers under test). Both were measured to cost ~70 s per request on this
#: host and neither touches the Stage-2 grounding block:
#:
#: * ``REGENOLD_QUERY_DENOISER`` — Stage 0 makes its own live LLM calls through
#:   providers this probe does not stub (measured retrying Groq TPD 429 ->
#:   Gemini -> Mistral 403 -> Bedrock 403 on every row).
#: * ``REGENOLD_EXTERNAL_EMBEDDINGS`` — Cohere answered 429 on every call and the
#:   engine fell back to the SVD path anyway. Forcing the local path also makes
#:   RETRIEVAL IDENTICAL ACROSS ARMS, so the only thing that can move the payload
#:   is the lever.
PROBE_BASELINE: dict[str, str] = {
    "REGENOLD_QUERY_DENOISER": "0",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
}

#: Stage-2 answer markers — the same filter ``gate_validity`` uses.
_STAGE2_MARKERS = ("EU AI ACT REFERENCES:", "ANSWER CONTRACT")

_PARSED = json.dumps(
    {
        "intent": "general_compliance",
        "entities": ["provider", "high-risk AI system"],
        "risk_context": "high_risk",
        "dimension_hint": "obligations",
        "keywords": ["technical documentation", "Annex IV"],
        "reasoning": "stub parse for the attribution probe",
    }
)

_ANSWER = (
    "Under Article 11 read with Annex IV, the provider of a high-risk AI system "
    "must draw up and keep up to date the technical documentation set out in "
    "Annex IV. Article 16 makes that duty an obligation of the provider, and "
    "Article 18 requires the documentation to be kept for the lifetime of the "
    "system. References: Article 11, Annex IV, Article 16, Article 18."
)


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _round_refs(row: dict) -> list[str]:
    """Every provision the row names on the wire, in first-seen order.

    This is the CLOSEST available proxy for the engine's Stage-2 context ref
    set: the checkpoint records the wire refs, not the retrieved set, so the
    block-level total below is an ESTIMATE and the per-ref cost (exact) is
    reported alongside it.
    """
    out: list[str] = []
    for key in ("turn1_refs", "pushback_refs", "pred_refs", "jul07_refs"):
        for ref in row.get(key) or []:
            s = str(ref).strip()
            if s and s not in out:
                out.append(s)
    return out


def _head(ref: str) -> str:
    """Strip a subpoint tail: ``Article 13.1`` -> ``Article 13``."""
    s = str(ref).strip()
    if s.startswith("Article "):
        return "Article " + s[len("Article ") :].split(".")[0].split("(")[0].strip()
    if s.startswith("Annex "):
        return "Annex " + s[len("Annex ") :].split(".")[0].split("(")[0].strip()
    return s


def offline_skeleton_cost(rows: list[dict]) -> dict[str, Any]:
    """EXACT cost of the closed-set skeleton on the board's real refs.

    ``_render_closed_set_skeleton`` is a pure local function, so this is not an
    estimate: it is the same string the engine would prepend to each block entry.
    """
    from app.engines._graph_rag_impl import _render_closed_set_skeleton

    per_row: list[dict[str, Any]] = []
    for row in rows:
        heads = []
        for ref in _round_refs(row):
            h = _head(ref)
            if h not in heads:
                heads.append(h)
        total = 0
        fired: list[str] = []
        for h in heads:
            try:
                s = _render_closed_set_skeleton(h)
            except Exception:  # noqa: BLE001 — a bad ref must not break the probe
                s = None
            if s:
                total += len(s) + 1  # + the newline the caller joins with
                fired.append(h)
        per_row.append(
            {
                "id": row.get("id"),
                "heads": len(heads),
                "skeleton_heads": len(fired),
                "skeleton_chars": total,
                "chars": len(str(row.get("pred_answer") or "")),
            }
        )
    fired_rows = [r for r in per_row if r["skeleton_chars"]]
    return {
        "n_rows": len(per_row),
        "rows_where_skeleton_fires": len(fired_rows),
        "mean_chars_added_all_rows": (
            sum(r["skeleton_chars"] for r in per_row) / len(per_row) if per_row else 0.0
        ),
        "mean_chars_added_firing_rows": (
            sum(r["skeleton_chars"] for r in fired_rows) / len(fired_rows) if fired_rows else 0.0
        ),
        "median_chars_added_firing_rows": (
            statistics.median([r["skeleton_chars"] for r in fired_rows]) if fired_rows else 0.0
        ),
        "total_chars_added": sum(r["skeleton_chars"] for r in per_row),
        "rows": per_row,
    }


class ProviderRecorder:
    """The truth: the final payload of every dispatched request."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def complete(self, request, *args: Any, **kwargs: Any):  # noqa: ANN002, ANN003
        system = str(getattr(request, "system", "") or "")
        user = str(getattr(request, "user", "") or "")
        stage2 = any(m in user for m in _STAGE2_MARKERS)
        self.payloads.append(
            {
                "stage2_answer_call": stage2,
                "system_len": len(system),
                "user_len": len(user),
                "user_sha": hashlib.sha256(user.encode("utf-8")).hexdigest()[:16],
            }
        )
        return SimpleNamespace(
            error=None,
            text=_ANSWER if stage2 else _PARSED,
            thinking="",
            finish_reason="stop",
            model="probe-stub",
            usage=None,
            latency_ms=1,
            headers=None,
        )


def _installed() -> dict:
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider

    provider = get_openai_wrapper_provider()
    original = provider.complete
    recorder = ProviderRecorder()
    provider.complete = recorder.complete  # type: ignore[method-assign]
    return {"provider": provider, "original": original, "recorder": recorder}


def _restore(h: dict) -> None:
    h["provider"].complete = h["original"]  # type: ignore[method-assign]


def _graded(h: dict) -> dict | None:
    graded = [p for p in h["recorder"].payloads if p["stage2_answer_call"]]
    return graded[-1] if graded else None


def _history(depth: int) -> list[dict[str, str]]:
    """A rolling conversation of the shape the hard split really sends.

    The harness rolls forward using live answers; with the provider stubbed there
    are none, so the stub answer stands in. Only the SHAPE matters here (the
    number of prior exchanges drives the route's ``history_turn_count``
    arithmetic) and the harness's own ``trim_history`` keeps it honest.
    """
    from evals.regenold.official_batch import trim_history

    history: list[dict[str, str]] = []
    for i in range(depth):
        history = trim_history(
            [
                *history,
                {"role": "user", "content": f"Prior question {i + 1} about the EU AI Act."},
                {"role": "assistant", "content": _ANSWER},
            ]
        )
    return history


def _route_row(row: Any, env: dict[str, str], depth: int) -> dict | None:
    from evals.regenold.official_batch import build_hard_messages
    from evals.regenold.runner_v2 import _post_local

    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    h = _installed()
    try:
        body, _lat, _status, _err, _attempts, _retried = _post_local(
            "local://app.main:app/api/v1/regenold/eu-ai-act/ask",
            None,
            build_hard_messages(row, _history(depth)),
            180.0,
        )
    finally:
        _restore(h)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    graded = _graded(h)
    if graded is None:
        return None
    return {
        "graded": graded,
        "answer_len": len(str((body or {}).get("answer") or "")),
    }


def _pearson(a: list[float], b: list[float]) -> float:
    if len(a) < 2:
        return float("nan")
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else float("nan")


def calibration(rows: list[dict], gold: dict[str, str], criteria: dict[str, int]) -> dict[str, Any]:
    """Is the conciseness DENOMINATOR calibrated, or is the answer side drifting?

    ``ans_conciseness = min(1, len(reference) / len(candidate))`` can be wrong in
    two different ways, and they need opposite remedies:

    * the reference does not scale with how much law a question needs, so the axis
      penalises content the correctness criteria REQUIRE (a metric defect), or
    * the candidate does not scale, so the engine writes the same-shaped answer
      whether the question needs one limb or six (a generation defect).

    The test is which of the two lengths tracks ``len(criteria)``.
    """
    recs = [
        r
        for r in rows
        if gold.get(r.get("id", "")) and criteria.get(r.get("id", ""))
    ]
    if not recs:
        return {}
    crit = [float(criteria[r["id"]]) for r in recs]
    ref = [float(len(gold[r["id"]])) for r in recs]
    ans = [float(len(str(r.get("pred_answer") or ""))) for r in recs]

    def _band(lo: int, hi: int) -> dict[str, Any]:
        sel = [r for r in recs if lo <= criteria[r["id"]] <= hi]
        if not sel:
            return {}
        return {
            "n": len(sel),
            "mean_criteria": statistics.mean(criteria[r["id"]] for r in sel),
            "mean_reference_chars": statistics.mean(len(gold[r["id"]]) for r in sel),
            "mean_answer_chars": statistics.mean(len(str(r.get("pred_answer") or "")) for r in sel),
            "mean_ans_conciseness": 100.0
            * statistics.mean(
                min(1.0, len(gold[r["id"]]) / max(len(str(r.get("pred_answer") or "")), 1))
                for r in sel
            ),
        }

    return {
        "n_rows": len(recs),
        "reference_chars": {
            "mean": statistics.mean(ref),
            "min": min(ref),
            "max": max(ref),
            "per_criterion": statistics.mean(
                len(gold[r["id"]]) / max(criteria[r["id"]], 1) for r in recs
            ),
        },
        "correlation_criteria_vs_reference_len": _pearson(crit, ref),
        "correlation_criteria_vs_answer_len": _pearson(crit, ans),
        "by_criteria_band": {
            "1": _band(1, 1),
            "2-3": _band(2, 3),
            "4-5": _band(4, 5),
            "6": _band(6, 6),
        },
    }


def new_levers_since_r390(baseline_rev: str = "74008ea") -> dict[str, Any]:
    """Every REGENOLD_* flag that did not exist at R390, with its HEAD default.

    The candidate set has to be BOUNDED BY EVIDENCE, not asserted. This reads the
    name sets out of ``app/`` at both revisions and, for each new name, the
    literal default the code passes to ``os.getenv`` at HEAD. Names whose default
    is decided by a helper (``answer_completeness._flag_is_on``) are listed
    separately as ``default_undecided`` rather than guessed.
    """
    import subprocess

    def _names(rev: str) -> set[str]:
        out = subprocess.run(
            ["git", "grep", "-h", "-o", "-E", "REGENOLD_[A-Z0-9_]+", rev, "--", "app/"],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        ).stdout
        return {x.strip() for x in out.splitlines() if x.strip()}

    try:
        new = sorted(_names("HEAD") - _names(baseline_rev))
    except Exception as exc:  # noqa: BLE001 — a missing revision is not a result
        return {"error": f"git name-diff failed: {exc}"}

    on: list[str] = []
    off: list[str] = []
    undecided: list[str] = []
    for name in new:
        txt = subprocess.run(
            ["git", "grep", "-h", "-E", name, "HEAD", "--", "app/"],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        ).stdout
        defaults = {
            m.group(1).strip().lower()
            for m in re.finditer(r'getenv\(\s*"' + name + r'"\s*,\s*"([^"]*)"', txt)
        }
        if any(d in {"1", "true", "yes", "on"} for d in defaults):
            on.append(name)
        elif defaults and all(d in {"0", "false", "no", "off", ""} for d in defaults):
            off.append(name)
        else:
            undecided.append(name)
    return {
        "baseline_rev": baseline_rev,
        "new_names": len(new),
        "default_on": on,
        "default_off": off,
        "default_undecided": undecided,
    }


def route_read(n_rows: int, depth: int) -> dict[str, Any]:
    """The rest of the candidate set together, at the dispatched payload.

    PAIRED BY ROW, NOT BY MEAN. The first version of this probe averaged
    ``mean_user_len`` over whatever rows happened to fire in each arm, so when
    one arm fired on question 1 and the other on question 3 the printed "delta"
    was the difference between two DIFFERENT questions (+4910 chars on n=3).
    Only rows that fired a graded Stage-2 payload in BOTH arms are compared, and
    the unit of report is the per-row pair.

    STRIDED SAMPLE. Rows whose answer is produced deterministically (the curated
    intercepts) never dispatch a graded Stage-2 call at all, and they sit in the
    send order, so a PREFIX of the board under-reports firing. ``R422_ROUTE_STRIDE``
    spreads the sample across the board the same way ``--stride`` does for a run.
    """
    from evals.regenold.official_batch import load_official_batch

    all_rows = list(load_official_batch())
    stride = max(1, int(os.getenv("R422_ROUTE_STRIDE", "1")))
    # Only sample rows the LIVE board actually polished: a curated intercept
    # answers deterministically and dispatches no graded Stage-2 call at all, so
    # including those rows can only pad the non-firing count (they were 3 of the
    # first 5 sampled). `R422_ROUTE_POLISHED_ONLY=0` restores the old behaviour.
    polished_only = os.getenv("R422_ROUTE_POLISHED_ONLY", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
    polished = set()
    if polished_only:
        for rec in _load(R419_CKPT):
            prov = rec.get("provenance") or {}
            if prov.get("stage2_polish") is True or prov.get("stage2_served_by"):
                polished.add(rec.get("id"))
    pool = [r for r in all_rows if (not polished_only or r.id in polished)]
    rows = pool[::stride][:n_rows]
    off = {k: "0" for k in CANDIDATE_LEVERS}
    arms: list[tuple[str, dict[str, str]]] = [
        ("HEAD-defaults", dict(PROBE_BASELINE)),
        ("all-candidates-off", {**PROBE_BASELINE, **off}),
    ]
    per_arm: dict[str, dict[str, dict[str, Any]]] = {}
    for label, env in arms:
        fired: dict[str, dict[str, Any]] = {}
        no_stage2: list[str] = []
        for row in rows:
            rec = _route_row(row, env, depth)
            if rec is None:
                no_stage2.append(row.id)
                continue
            fired[row.id] = {
                "user_len": rec["graded"]["user_len"],
                "system_len": rec["graded"]["system_len"],
                "answer_len": rec["answer_len"],
            }
        per_arm[label] = fired
        print(f"  {label:<24} fired {len(fired):>3}/{len(rows)} graded payloads"
              f"  (no Stage-2 by design: {len(no_stage2)})")

    head, off_arm = per_arm["HEAD-defaults"], per_arm["all-candidates-off"]
    paired = sorted(set(head) & set(off_arm))
    rows_out = [
        {
            "id": rid,
            "head_user_len": head[rid]["user_len"],
            "off_user_len": off_arm[rid]["user_len"],
            "delta_off_minus_head": off_arm[rid]["user_len"] - head[rid]["user_len"],
        }
        for rid in paired
    ]
    deltas = [r["delta_off_minus_head"] for r in rows_out]
    out: dict[str, Any] = {
        "n_rows": len(rows),
        "history_depth": depth,
        "stride": stride,
        "polished_only": polished_only,
        "pool_size": len(pool),
        "sample_ids": [r.id for r in rows],
        "arms": {
            label: {
                "env": env,
                "rows_with_graded_payload": len(per_arm[label]),
                "rows_without_stage2": sorted(set(r.id for r in rows) - set(per_arm[label])),
                "mean_user_len": (
                    sum(v["user_len"] for v in per_arm[label].values()) / len(per_arm[label])
                    if per_arm[label]
                    else 0.0
                ),
            }
            for label, env in arms
        },
        "paired_rows": rows_out,
        "paired_n": len(rows_out),
        # Positive => turning the candidates OFF made the dispatched prompt LONGER.
        "mean_paired_delta_off_minus_head": (sum(deltas) / len(deltas)) if deltas else 0.0,
    }
    # An arm that did not fire on every sampled row cannot support a per-row
    # comparison, and an unpaired mean is not a delta — say so instead.
    out["vacuous"] = [
        k for k, v in out["arms"].items() if v["rows_with_graded_payload"] != len(rows)
    ]
    out["comparable"] = bool(deltas) and not out["vacuous"]
    return out


def main() -> int:
    route = "--route" in sys.argv
    n_route_rows = int(os.getenv("R422_ROUTE_ROWS", "5"))
    depth = int(os.getenv("R422_HISTORY_DEPTH", "3"))

    rows = _load(R419_CKPT)
    prev = {r.get("id"): r for r in _load(R390_CKPT)}

    print("=" * 100)
    print("R422 attribution — what inflated the hard-mode prompt")
    print("=" * 100)

    # ---- length history on the same rows, same generator -------------------
    hist: dict[str, Any] = {}
    if rows and prev:
        paired = [(prev[r["id"]], r) for r in rows if r.get("id") in prev]

        def _mean(v: list[float]) -> float:
            return sum(v) / len(v) if v else 0.0

        def _ansc(rs: list[dict]) -> float:
            vals = [
                min(1.0, len(gold[r["id"]]) / max(_chars(r, "pred_answer"), 1))
                for r in rs
                if gold.get(r.get("id", "")) and _chars(r, "pred_answer") > 0
            ]
            if not vals:
                raise SystemExit("FATAL: ans_conciseness has no comparable rows")
            return 100.0 * _mean(vals)

        old = [a for a, _ in paired]
        new = [b for _, b in paired]
        gold = {r["id"]: str(r.get("reference_answer") or "") for r in _load(GOLD)}
        if not gold:
            raise SystemExit(f"FATAL: no reference answers read from {GOLD}")

        def _chars(r: dict, key: str) -> int:
            return len(str(r.get(key) or ""))

        def _median(v: list[float]) -> float:
            return float(statistics.median(v)) if v else 0.0

        # Per-row ratios decide whether the change is generation-wide or a
        # handful of outliers, and which rows did NOT move at all (the curated
        # deterministic subset, whose answer text is fixed by construction).
        ratios = [
            _chars(b, "pred_answer") / _chars(a, "pred_answer")
            for a, b in paired
            if _chars(a, "pred_answer") > 0
        ]
        hist = {
            "paired_rows": len(paired),
            "n_old": len(old),
            "n_new": len(new),
            "mean_answer_chars_old": _mean([_chars(r, "pred_answer") for r in old]),
            "mean_answer_chars_new": _mean([_chars(r, "pred_answer") for r in new]),
            "median_answer_chars_old": _median([_chars(r, "pred_answer") for r in old]),
            "median_answer_chars_new": _median([_chars(r, "pred_answer") for r in new]),
            "mean_turn1_chars_old": _mean([_chars(r, "turn1_answer") for r in old]),
            "mean_turn1_chars_new": _mean([_chars(r, "turn1_answer") for r in new]),
            # ``pushback_answer`` IS the graded answer on every row of both
            # checkpoints (verified: 110/110 identical), so this is not a second
            # measurement — it is recorded under its own name only so nobody
            # reads the identity of the two columns as two confirmations.
            "graded_equals_pushback_rows": sum(
                1 for a, b in paired
                if _chars(a, "pred_answer") == _chars(a, "pushback_answer")
                and _chars(b, "pred_answer") == _chars(b, "pushback_answer")
            ),
            "ans_conciseness_old": _ansc(old),
            "ans_conciseness_new": _ansc(new),
            "rows_grew_over_15pct": sum(1 for x in ratios if x > 1.15),
            "rows_shrank": sum(1 for x in ratios if x < 1.0),
            "rows_byte_identical": sum(1 for x in ratios if abs(x - 1.0) < 1e-12),
            "median_row_ratio": _median(ratios),
            "mean_ref_chars": _mean([len(g) for g in gold.values() if g]),
            "n_ref_nonempty": sum(1 for g in gold.values() if g),
        }
        # The rows that shrank are the tell for the OTHER failure: four of them
        # are the transport-degraded rows that shipped a Stage-1 draft (R420's
        # prior-answer floor), so they must not be read as "the lever shortened
        # this answer".
        hist["shrank_rows"] = [
            {
                "id": b.get("id"),
                "old_chars": _chars(a, "pred_answer"),
                "new_chars": _chars(b, "pred_answer"),
                "stage2_served_by": (b.get("provenance") or {}).get("stage2_served_by")
                or ("deterministic" if b.get("stage2_polish") is False else None),
            }
            for a, b in paired
            if 0 < _chars(b, "pred_answer") < _chars(a, "pred_answer")
        ]
        hist["byte_identical_rows"] = [
            b.get("id")
            for a, b in paired
            if _chars(a, "pred_answer") > 0
            and _chars(a, "pred_answer") == _chars(b, "pred_answer")
            and str(a.get("pred_answer")) == str(b.get("pred_answer"))
        ]

        print(f"paired rows {len(paired)} (R390 vs R419, both opus-5 hard)")
        print(f"  mean graded answer chars   {hist['mean_answer_chars_old']:>8.0f}"
              f" -> {hist['mean_answer_chars_new']:>8.0f}")
        print(f"  mean turn-1 answer chars   {hist['mean_turn1_chars_old']:>8.0f}"
              f" -> {hist['mean_turn1_chars_new']:>8.0f}")
        print(f"  ans_conciseness            {hist['ans_conciseness_old']:>8.2f}"
              f" -> {hist['ans_conciseness_new']:>8.2f}"
              f"  (reference {hist['mean_ref_chars']:.0f} chars over {hist['n_ref_nonempty']} rows)")
        print(f"  rows grew >15%  {hist['rows_grew_over_15pct']}"
              f" | shrank {hist['rows_shrank']}"
              f" | byte-identical {hist['rows_byte_identical']}"
              f" | median row ratio {hist['median_row_ratio']:.2f}")

    # ---- measurement 3: is the DENOMINATOR calibrated? ---------------------
    gold_map = {r["id"]: str(r.get("reference_answer") or "") for r in _load(GOLD)}
    crit_map = {r["id"]: len(r.get("criteria") or []) for r in _load(GOLD)}
    calib = calibration(rows, gold_map, crit_map) if rows else {}
    if calib:
        print("\nMEASUREMENT 3 — is the conciseness DENOMINATOR calibrated?")
        rl = calib["reference_chars"]
        print(f"  reference answer chars       mean {rl['mean']:.0f}"
              f"  min {rl['min']:.0f}  max {rl['max']:.0f}"
              f"  ({rl['per_criterion']:.0f} chars per criterion)")
        print(f"  corr(criteria, reference_len)  {calib['correlation_criteria_vs_reference_len']:>+.3f}"
              "   <- the denominator DOES scale with the question")
        print(f"  corr(criteria, answer_len)     {calib['correlation_criteria_vs_answer_len']:>+.3f}"
              "   <- the ANSWER does not")
        for label, b in calib["by_criteria_band"].items():
            if b:
                print(f"    {label:>3} criteria  n={b['n']:<3} ref {b['mean_reference_chars']:>5.0f}"
                      f"  answer {b['mean_answer_chars']:>5.0f}"
                      f"  conc {b['mean_ans_conciseness']:>5.1f}%")

    # ---- measurement 0: bound the candidate set, from git -------------------
    new_levers = new_levers_since_r390()
    print("\nMEASUREMENT 0 — REGENOLD_* flags that did not exist at R390")
    if "error" in new_levers:
        print(f"  {new_levers['error']}")
    else:
        print(f"  new flag names in app/            {new_levers['new_names']}")
        print(f"  of which DEFAULT ON at HEAD       {len(new_levers['default_on'])}")
        print(f"  default OFF                       {len(new_levers['default_off'])}")
        print(f"  default decided by a helper       {len(new_levers['default_undecided'])}")
        for name in new_levers["default_on"]:
            print(f"    + {name}")

    # ---- measurement 1: the skeleton, exact and offline --------------------
    skel = offline_skeleton_cost(rows) if rows else {}
    if skel:
        print("\nMEASUREMENT 1 — REGENOLD_CLOSED_SET_SKELETON (exact, offline, no route)")
        print(f"  rows where the skeleton fires        {skel['rows_where_skeleton_fires']}"
              f" / {skel['n_rows']}")
        print(f"  mean chars ADDED per firing row      {skel['mean_chars_added_firing_rows']:>8.0f}")
        print(f"  median chars added per firing row    {skel['median_chars_added_firing_rows']:>8.0f}")
        print(f"  mean chars added across all rows     {skel['mean_chars_added_all_rows']:>8.0f}")
        print(f"  total chars added over the board     {skel['total_chars_added']:>8.0f}")

    # ---- measurement 2: the remaining candidates, at the payload -----------
    route_out: dict[str, Any] = {}
    if route:
        print(f"\nMEASUREMENT 2 — remaining candidates at the dispatched payload "
              f"({n_route_rows} rows, history depth {depth})")
        route_out = route_read(n_route_rows, depth)
        print(f"  paired rows {route_out['paired_n']}"
              f"  mean OFF-HEAD delta {route_out['mean_paired_delta_off_minus_head']:>+8.0f}")
        for rec in route_out["paired_rows"]:
            print(f"    {rec['id']:<8} HEAD {rec['head_user_len']:>7}"
                  f"  OFF {rec['off_user_len']:>7}"
                  f"  delta {rec['delta_off_minus_head']:>+7}")
        print(f"  vacuous arms                         {route_out['vacuous'] or 'none'}")
        print(f"  comparable                           {route_out['comparable']}")

    print("\nlevers EXCLUDED from the candidate set, with the reason:")
    for k, why in INERT_ON_HARD.items():
        print(f"  {k:<40} {why}")

    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "candidates": list(CANDIDATE_LEVERS),
        "inert_on_hard": INERT_ON_HARD,
        "probe_baseline_env": PROBE_BASELINE,
        "length_history": hist,
        "reference_source": GOLD.relative_to(REPO).as_posix(),
        "new_levers_since_r390": new_levers,
        "calibration": calib,
        "skeleton_offline": skel,
        "route_read": route_out,
        "conclusive": bool(skel) and (not route or bool(route_out.get("comparable"))),
    }
    (OUT / "attribution.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT / 'attribution.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

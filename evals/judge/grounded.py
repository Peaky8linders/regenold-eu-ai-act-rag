"""R284 — GROUNDED Sonnet-5 LLM-as-Judge.

An independent judge that scores answer + reference + citation correctness
against the VERBATIM EU AI Act text (``app.data.provision_text``), NOT against
the (possibly-incomplete) gold keyword/label set. This is the "proper
measurement" upgrade over ``evals.judge.runner``:

* the existing runner's *correctness* axis grades against GOLD KEYWORDS, and its
  *refs* axis grounds in KB SUMMARIES — neither is the regulation itself;
* this judge feeds the model the verbatim text of both the GOLD provisions and
  the PREDICTED provisions, and asks it to determine, per the Act:
    - ANSWER CORRECTNESS  — is the answer's substance correct per the text?
    - REFERENCE CORRECTNESS — of the cited provisions, which genuinely GOVERN the
      question (precision), and which governing provisions are MISSING (recall)?
      Scored against the Act, so an incomplete gold label cannot penalise a
      correct-but-broader citation, nor reward a wrong one the gold happens to omit.
    - CITATION FAITHFULNESS — does the prose accurately describe each cited
      provision (the cite-and-mismatch check), verified against verbatim text?

Default model: ``claude-sonnet-5``. Reuses the runner's provider/retry/parse
plumbing. Independent (absolute per-answer, no A/B leakage); position/label-blind
(the judge never sees which arm or system produced the answer).

CLI:
    python -m evals.judge.grounded \\
        --sidecar evals/bench/results/easyhard-r284-B.ckpt.jsonl \\
        --label r284-B-grounded --model claude-sonnet-5 \\
        --provider wrapper --timeout 90 --concurrency 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv()

from evals.judge.runner import (  # reuse the battle-tested call plumbing
    _call_judge_with_retry,
    _resolve_caller,
    set_judge_model,
)

_DEFAULT_MODEL = "claude-sonnet-5"
GROUNDED_AXES: tuple[str, ...] = (
    "answer_correctness",
    "reference_correctness",
    "citation_faithfulness",
)

# Per-provision verbatim-text caps (chars). Generous so long articles (e.g.
# Article 5, whose prohibited practices (a)-(h) run ~4000 chars) are NOT
# truncated before a cited sub-point — a truncated grounding would false-fail
# an answer that correctly cites 5(1)(f)/(g)/(h). Sonnet-5 handles the context.
_GOLD_TEXT_CAP = 12000  # full Article 5 (~11k, the outlier) fits uncut
_PRED_TEXT_CAP = 6000
_MAX_GOLD_REFS = 6
_MAX_PRED_REFS = 8


# ── provision-text grounding ────────────────────────────────────────────


def _provision_block(refs: list[str], cap: int, max_refs: int) -> str:
    """Resolve each ref to verbatim EU AI Act text, article-level fallback."""
    from app.data.provision_text import get_provision_text  # local heavy import

    lines: list[str] = []
    seen: set[str] = set()
    for r in refs[:max_refs]:
        key = str(r).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        txt = get_provision_text(key)
        if txt is None:
            # fall back to the base article/annex text
            base = key.split(".")[0].split("(")[0].strip()
            if base and base != key:
                txt = get_provision_text(base)
        if txt:
            lines.append(f"[{key}] {txt.strip()[:cap]}")
        else:
            lines.append(f"[{key}] (no verbatim text resolved — likely not a real provision)")
    return "\n".join(lines) if lines else "  (none)"


def _norm(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise the sidecar row shape (easyhard ckpt jsonl / bench / v2)."""
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "question": row.get("question") or row.get("live_question") or "",
        "answer": (row.get("pred_answer") or row.get("predicted_answer")
                   or row.get("answer_preview") or "").strip(),
        "pred_refs": list(row.get("pred_refs") or row.get("predicted_refs") or []),
        "gold_refs": list(row.get("gold_refs") or row.get("expected_refs") or []),
    }


# ── grounded prompts ────────────────────────────────────────────────────


def render_answer_correctness(r: dict[str, Any]) -> str:
    # Ground on the UNION of gold + predicted provisions so the judge can verify
    # every provision the answer relies on (not just the gold ones — the gold
    # labels can be incomplete, and the answer may correctly cite beyond them).
    union = list(dict.fromkeys([*r["gold_refs"], *r["pred_refs"]]))
    gold_text = _provision_block(union, _GOLD_TEXT_CAP, _MAX_GOLD_REFS + _MAX_PRED_REFS)
    return (
        "You are an independent EU AI Act legal examiner. Judge the ANSWER's "
        "correctness STRICTLY against the verbatim Regulation text below — do "
        "NOT rely on outside memory or on any label; the verbatim text is the "
        "ground truth. (If the answer relies on a provision whose full verbatim "
        "text is below, verify it against that text; treat well-established AI "
        "Act structure as known.)\n\n"
        f"QUESTION: {r['question'][:600]}\n\n"
        "VERBATIM EU AI ACT TEXT (the provisions relevant to this question):\n"
        f"{gold_text}\n\n"
        f"PREDICTED ANSWER: {r['answer'][:1400]}\n\n"
        "Decompose the answer into atomic legal assertions (Legal Data Points). "
        "Using ONLY the verbatim text above plus well-established AI Act "
        "structure, tag each LDP: correct | incorrect | unsupported. Separately "
        "count MISSING — operative holdings the verbatim text establishes that "
        "the question demands but the answer omits (e.g. it asks 'prohibited or "
        "high-risk?' and the answer never states the prohibition that the text "
        "shows applies). Verdict 'pass' iff there are ZERO incorrect LDPs AND "
        "zero MISSING operative holdings.\n\n"
        "Respond with ONE JSON object only (no prose, no fences):\n"
        '{"verdict":"pass"|"fail","correct":N,"incorrect":N,"unsupported":N,'
        '"missing":N,"failure_mode":"<one short phrase>"}'
    )


def render_reference_correctness(r: dict[str, Any]) -> str:
    pred_text = _provision_block(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
    gold_text = _provision_block(r["gold_refs"], _GOLD_TEXT_CAP, _MAX_GOLD_REFS)
    return (
        "You are an independent EU AI Act citation examiner. Judge whether the "
        "PREDICTED CITATIONS are the correct, MINIMAL set of provisions for this "
        "question, STRICTLY against the verbatim text below. Score against the "
        "REGULATION, not the gold list — the gold list can be incomplete, so a "
        "predicted citation the gold omits is still CORRECT if the verbatim text "
        "shows it governs the question, and a predicted citation the gold "
        "includes is still WRONG if the text shows it does not apply.\n\n"
        f"QUESTION: {r['question'][:500]}\n\n"
        f"PREDICTED CITATIONS: {r['pred_refs']}\n"
        "VERBATIM TEXT OF PREDICTED CITATIONS:\n"
        f"{pred_text}\n\n"
        f"GOLD CITATIONS (a reference set, may be incomplete): {r['gold_refs']}\n"
        "VERBATIM TEXT OF GOLD CITATIONS:\n"
        f"{gold_text}\n\n"
        "Classify each PREDICTED citation as CORRECT (genuinely governs this "
        "question per the text) or WRONG (irrelevant / over-cited). Then count "
        "MISSING — provisions the text shows govern this question that are NOT "
        "among the predicted citations. Report precision = correct / predicted "
        "and recall = correct_governing / (correct_governing + missing). Verdict "
        "'pass' iff there are ZERO WRONG citations AND zero MISSING load-bearing "
        "provisions.\n\n"
        "Respond with ONE JSON object only:\n"
        '{"verdict":"pass"|"fail","n_predicted":N,"correct":N,"wrong":N,'
        '"missing":N,"precision":0.0,"recall":0.0,"failure_mode":"<one short phrase>"}'
    )


def render_citation_faithfulness(r: dict[str, Any]) -> str:
    pred_text = _provision_block(r["pred_refs"], _PRED_TEXT_CAP, _MAX_PRED_REFS)
    return (
        "You are checking CITATION FAITHFULNESS against the verbatim Regulation "
        "text. For each cited provision, decide whether the answer's prose "
        "accurately describes what that provision actually says (per its "
        "verbatim text). A cite-and-mismatch — citing Article X while describing "
        "the content of a different provision — is a fail even if the article "
        "number happens to be right.\n\n"
        f"QUESTION: {r['question'][:400]}\n\n"
        f"PREDICTED ANSWER: {r['answer'][:1200]}\n\n"
        "VERBATIM TEXT OF EACH CITED PROVISION:\n"
        f"{pred_text}\n\n"
        "Verdict 'pass' iff EVERY cited provision is faithfully described by the "
        "answer (no cite-and-mismatch, no cited provision the prose ignores).\n\n"
        "Respond with ONE JSON object only:\n"
        '{"verdict":"pass"|"fail","faithful":N,"mismatched":N,'
        '"failure_mode":"<one short phrase>"}'
    )


def _render(axis: str, r: dict[str, Any]) -> str:
    if axis == "answer_correctness":
        return render_answer_correctness(r)
    if axis == "reference_correctness":
        return render_reference_correctness(r)
    if axis == "citation_faithfulness":
        return render_citation_faithfulness(r)
    raise ValueError(axis)


# ── per-row + run ───────────────────────────────────────────────────────


def _judge_row(r: dict[str, Any], caller: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    verdicts: dict[str, Any] = {}
    for axis in GROUNDED_AXES:
        result, attempts, retried = _call_judge_with_retry(caller, _render(axis, r))
        if retried:
            result = dict(result); result["_attempts"] = attempts
        verdicts[axis] = result
    return {"id": r["id"], "category": r["category"], "verdicts": verdicts}


def _load_rows(sidecar: Path) -> list[dict[str, Any]]:
    text = sidecar.read_text(encoding="utf-8")
    if sidecar.suffix == ".jsonl":
        return [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    payload = json.loads(text)
    rows: list[dict[str, Any]] = []
    for k in ("rows", "qa", "scenarios", "tricky", "multiturn", "ground_truth"):
        b = payload.get(k)
        if isinstance(b, dict):
            rows.extend(b.get("rows") or [])
        elif isinstance(b, list):
            rows.extend(b)
    return rows or (payload if isinstance(payload, list) else [])


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _aggregate(judged: list[dict[str, Any]]) -> dict[str, Any]:
    agg: dict[str, Any] = {}
    for axis in GROUNDED_AXES:
        n = len(judged); p = f = e = 0
        prec: list[float] = []; rec: list[float] = []; fact: list[float] = []
        modes: dict[str, int] = {}
        for row in judged:
            v = (row.get("verdicts") or {}).get(axis) or {}
            if v.get("judge_error"):
                e += 1; continue
            verd = str(v.get("verdict") or "").lower()
            if verd == "pass":
                p += 1
            elif verd == "fail":
                f += 1
                m = str(v.get("failure_mode") or "(unspecified)")[:80]
                modes[m] = modes.get(m, 0) + 1
            else:
                e += 1
            if axis == "reference_correctness":
                # prefer model-reported precision/recall; else derive from counts
                c, w, ms = _num(v.get("correct")), _num(v.get("wrong")), _num(v.get("missing"))
                pr = _num(v.get("precision")) or (c / (c + w) if (c + w) else 0.0)
                rc = _num(v.get("recall")) or (c / (c + ms) if (c + ms) else 0.0)
                prec.append(pr); rec.append(rc)
            if axis == "answer_correctness":
                c, i, m2 = _num(v.get("correct")), _num(v.get("incorrect")), _num(v.get("missing"))
                tot = c + i + m2
                fact.append(c / tot if tot else 0.0)
        entry = {
            "n": n, "pass": p, "fail": f, "error": e,
            "pass_rate": round(p / n, 4) if n else 0.0,
            "pass_rate_over_non_error": round(p / (p + f), 4) if (p + f) else 0.0,
            "top_failure_modes": sorted(modes.items(), key=lambda kv: -kv[1])[:8],
        }
        if prec:
            entry["mean_precision"] = round(sum(prec) / len(prec), 4)
            entry["mean_recall"] = round(sum(rec) / len(rec), 4)
            pm, rm = entry["mean_precision"], entry["mean_recall"]
            entry["mean_f1"] = round(2 * pm * rm / (pm + rm), 4) if (pm + rm) else 0.0
        if fact:
            entry["mean_factual_score"] = round(sum(fact) / len(fact), 4)
        agg[axis] = entry
    return agg


def run(*, sidecar: Path, label: str, model: str, provider: str,
        timeout_s: float, concurrency: int, limit: int | None,
        out_dir: Path | None = None) -> dict[str, Any]:
    set_judge_model(model)
    caller = _resolve_caller(provider, timeout_s)
    all_rows = [_norm(r) for r in _load_rows(sidecar)]
    n_error_rows = sum(1 for r in all_rows if not r["answer"])
    rows = [r for r in all_rows if r["answer"]]  # skip error/empty-answer rows
    if limit:
        rows = rows[:limit]
    print(f"[grounded] {len(rows)} rows × {len(GROUNDED_AXES)} axes  model={model} "
          f"provider={provider} concurrency={concurrency}", flush=True)

    # R292 — gold coverage banner.
    #
    # `_norm` reads gold_refs/expected_refs. The OFFICIAL regenold batch has no
    # gold at all (regenold never published theirs), and `run_official_batch`
    # writes `jul07_refs` — which is OUR OWN prior output, NOT gold. Mapping it
    # into `gold_refs` would make the judge grade "did we match our past self",
    # which is circular, so we deliberately do NOT. Instead the gap is stamped
    # on every scorecard: with no gold, reference RECALL is the judge model's
    # recollection of the Act rather than a text-grounded comparison, while
    # PRECISION stays text-grounded (each predicted ref is checked against the
    # verbatim provision). Read the two asymmetrically.
    n_gold = sum(1 for r in rows if r["gold_refs"])
    gold_coverage = (n_gold / len(rows)) if rows else 0.0
    if gold_coverage < 0.5:
        print(
            f"[grounded] !! GOLD COVERAGE {n_gold}/{len(rows)} ({gold_coverage:.0%}) — "
            "reference RECALL is judge recall (model memory), not text-grounded; "
            "PRECISION remains text-grounded. Do not compare recall across "
            "datasets with different gold coverage.",
            flush=True,
        )
    if n_error_rows:
        print(
            f"[grounded] !! {n_error_rows} row(s) had no answer and are EXCLUDED "
            "from every axis below — the scorecard does not reflect them.",
            flush=True,
        )
    out: list[dict[str, Any] | None] = [None] * len(rows)
    done = 0
    lock = threading.Lock()
    t0 = time.monotonic()

    def _w(i: int, r: dict[str, Any]):
        return i, _judge_row(r, caller)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futs = [pool.submit(_w, i, r) for i, r in enumerate(rows)]
        for fut in as_completed(futs):
            i, jr = fut.result()
            out[i] = jr
            with lock:
                done += 1
                vs = {a: (jr["verdicts"].get(a) or {}).get("verdict", "?") for a in GROUNDED_AXES}
                print(f"  [{done}/{len(rows)}] {str(jr['id'])[:34]:<34} "
                      f"ans={vs['answer_correctness']} ref={vs['reference_correctness']} "
                      f"cite={vs['citation_faithfulness']}", flush=True)
    judged = [r for r in out if r is not None]
    agg = _aggregate(judged)
    summary = {
        "label": label, "source_sidecar": str(sidecar), "judge_model": model,
        "provider": provider, "elapsed_s": round(time.monotonic() - t0, 1),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "axes": list(GROUNDED_AXES), "rows": judged, "aggregate": agg,
        # R292 — provenance of the measurement itself, so a scorecard can be
        # read correctly months later without re-deriving these caveats.
        "gold_coverage": round(gold_coverage, 4),
        "gold_rows": n_gold,
        "excluded_error_rows": n_error_rows,
        "recall_is_text_grounded": gold_coverage >= 0.5,
    }
    out_dir = out_dir or Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"grounded-{label}.json"
    dest.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[grounded] sidecar -> {dest}", flush=True)
    return summary


def _fmt(s: dict[str, Any]) -> str:
    out = ["=" * 74, f"GROUNDED JUDGE — {s['label']!r}  model={s['judge_model']}",
           f"source: {Path(s['source_sidecar']).name}  elapsed={s['elapsed_s']}s", "=" * 74]
    for axis in s["axes"]:
        a = s["aggregate"][axis]
        line = (f"[{axis}] n={a['n']} pass={a['pass']} fail={a['fail']} err={a['error']} "
                f"pass_rate={a['pass_rate']} (over_non_err={a['pass_rate_over_non_error']})")
        out.append("\n" + line)
        if "mean_precision" in a:
            out.append(f"   precision={a['mean_precision']} recall={a['mean_recall']} f1={a['mean_f1']}")
        if "mean_factual_score" in a:
            out.append(f"   mean_factual_score={a['mean_factual_score']}")
        for mode, c in (a.get("top_failure_modes") or [])[:5]:
            out.append(f"     {c:>3}x {mode}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        if hasattr(st, "reconfigure"):
            try:
                st.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sidecar", required=True, type=Path)
    p.add_argument("--label", required=True)
    p.add_argument("--model", default=_DEFAULT_MODEL)
    p.add_argument("--provider", choices=("wrapper", "anthropic", "groq"), default="wrapper")
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args(argv)
    s = run(sidecar=a.sidecar, label=a.label, model=a.model, provider=a.provider,
            timeout_s=a.timeout, concurrency=a.concurrency, limit=a.limit)
    print(_fmt(s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

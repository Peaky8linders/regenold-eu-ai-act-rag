"""R118 — live measurement of the Antifragile expert-review Q&A + medtech
multi-turn scenarios against the DEPLOYED Railway endpoint.

The endpoint routes: client -> Railway -> Cloudflare named tunnel ->
local Claude Max wrapper -> Claude (Sonnet 4.6 / Opus 4.8 on the complex
gate). So this exercises the real competition wire end-to-end, including
Stage-2 polish.

Scores each row on the Regenold rubric (answer correctness loose/strict/F1,
answer conciseness, reference correctness loose/strict, reference
conciseness, regulatory tone, keyword recall, latency) vs the gold encoded
in ``antifragile_groundtruth`` / the medtech scenario file, AND checks how
many of the expert-flagged mistakes the current system has resolved.

Captures the ``?include_reasoning=true`` trace per row so we can see which
Stage-2 model fired (Sonnet vs Opus 4.8 complex path) and the retrieval path.

Usage (run with the MAIN venv python, cwd = this worktree):
  python -m evals.regenold.antifragile_live --label r118-live --set both
  python -m evals.regenold.antifragile_live --label r118-af --set antifragile --throttle 2.0
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from pathlib import Path
from typing import Any

from evals.bench import metrics as M
from evals.regenold.runner_v2 import _keyword_recall, _post, _ref_metrics

LIVE_ENDPOINT = (
    "https://regenold-eu-ai-act-rag-production.up.railway.app"
    "/api/v1/regenold/eu-ai-act/ask"
)
REFUSAL_MARKERS = (
    "i only answer", "please ask", "no matching obligation", "try rephrasing",
    "outside the scope", "not an eu ai act", "cannot answer",
)


def _load_api_key() -> str | None:
    # explicit env wins
    key = os.environ.get("P2P_REGENOLD_API_KEY")
    if key:
        return key.strip()
    # else read repo .env (this worktree, then the main checkout)
    for envp in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        try:
            for line in envp.read_text(encoding="utf-8").splitlines():
                if line.startswith("P2P_REGENOLD_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return None


def _norm(text: str) -> str:
    """Lowercase + collapse unicode hyphens/superscripts for substring checks."""
    t = (text or "").lower()
    t = t.replace("‑", "-").replace("–", "-").replace("—", "-")
    t = t.replace("²", "2").replace("³", "3").replace("⁵", "5")
    return t


def _to_user_facing_ref(ref: str) -> str:
    """Normalise an internal ``Art. N`` gold ref to the user-facing ``Article N``
    the wire emits. Some scenario files write gold refs in internal /
    ARTICLE_EXISTENCE format (``Art. 6``) so they validate against the catalog;
    the wire returns ``Article 6`` and the rubric scorer's ``article_head`` only
    parses the user-facing form. Annex refs are identical in both forms.
    Idempotent."""
    r = (ref or "").strip()
    if r.startswith("Art.") and not r.startswith("Article"):
        return "Article " + r[len("Art."):].lstrip()
    return r


def _norm_refs(refs: list[str]) -> list[str]:
    return [_to_user_facing_ref(r) for r in (refs or [])]


def _parse_reasoning(raw: Any) -> dict[str, Any]:
    """Pull the useful fields out of the ``reasoning`` JSON string."""
    out: dict[str, Any] = {
        "stage2_polish": None, "stage2_model": None, "complex": None,
        "retrieval_path": None, "engine_confidence": None, "cache_hit": None,
        "answer_route": None,
    }
    if not raw or not isinstance(raw, str):
        return out
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return out
    out["stage2_polish"] = d.get("stage2_polish")
    out["retrieval_path"] = d.get("retrieval_path")
    out["engine_confidence"] = d.get("engine_confidence")
    out["cache_hit"] = d.get("cache_hit")
    for note in d.get("notes", []) or []:
        if note.startswith("answer_route="):
            out["answer_route"] = note.split("=", 1)[1]
        m = re.search(r"stage2_model=(\S+)\s+complex=(\w+)", note)
        if m:
            out["stage2_model"] = m.group(1)
            out["complex"] = m.group(2) == "True"
    return out


def _mistake_resolved(answer_low: str, pred_refs: list[str], mistake: dict) -> bool:
    verify = mistake.get("verify", {})
    present = verify.get("present", []) or []
    absent = verify.get("absent", []) or []
    if not all(_norm(p) in answer_low for p in present):
        return False
    if any(_norm(a) in answer_low for a in absent):
        return False
    pred_low = {r.lower() for r in pred_refs}
    for r in mistake.get("ref_present", []) or []:
        if r.lower() not in pred_low:
            return False
    for r in mistake.get("ref_absent", []) or []:
        if r.lower() in pred_low:
            return False
    return True


def _score_row(qid: str, gt: dict, body: dict, latency_ms: float,
               err: str | None) -> dict[str, Any]:
    answer = body.get("answer") or ""
    refs = body.get("references") or []
    gold_answer = gt.get("gold_answer", "")
    gold_refs = _norm_refs(gt.get("gold_refs", []))
    refm = _ref_metrics(refs, gold_refs)
    answer_low = _norm(answer)
    mistakes = gt.get("mistakes", [])
    resolved = [m for m in mistakes if _mistake_resolved(answer_low, refs, m)]
    unresolved = [m["id"] for m in mistakes if m not in resolved]
    return {
        "id": qid,
        "question": gt["question"],
        "verdict_original": gt.get("verdict"),
        "gold_refs": gold_refs,
        "pred_refs": refs,
        "predicted_answer": answer,
        "answer_preview": answer[:400],
        # Regenold rubric
        "ans_loose": M.answer_correctness_loose(answer, gold_answer),
        "ans_strict": M.answer_correctness_strict(answer, gold_answer),
        "ans_f1": M.answer_correctness_f1(answer, gold_answer),
        "ans_conciseness": M.answer_conciseness(answer, gold_answer),
        "ref_loose": refm["loose"],
        "ref_strict": refm["strict"],
        "ref_conciseness": refm["conciseness"],
        "regulatory_tone": M.regulatory_tone(answer),
        "keyword_recall": _keyword_recall(answer, gt.get("expected_keywords", [])),
        # mistake resolution
        "mistakes_total": len(mistakes),
        "mistakes_resolved": len(resolved),
        "mistakes_resolved_ids": [m["id"] for m in resolved],
        "mistakes_unresolved_ids": unresolved,
        "is_refusal": any(m in answer_low for m in REFUSAL_MARKERS),
        "latency_ms": round(latency_ms, 1),
        "error": err,
        "reasoning": _parse_reasoning(body.get("reasoning")),
    }


def run_antifragile(endpoint: str, api_key: str | None, timeout: float,
                    throttle: float, verbose: bool) -> list[dict]:
    from evals.regenold.antifragile_groundtruth import ANTIFRAGILE_GT
    rows = []
    for qid, gt in ANTIFRAGILE_GT.items():
        history = [{"role": "user", "content": gt["question"]}]
        body, lat, status, err, attempts, retried = _post(
            endpoint, api_key, history, timeout)
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        row = _score_row(qid, gt, body, lat, err)
        row["attempts"] = attempts
        rows.append(row)
        if verbose:
            r = row["reasoning"]
            print(f"[{qid}] {status} {row['latency_ms']}ms "
                  f"model={r['stage2_model']} cx={r['complex']} "
                  f"refL={row['ref_loose']:.2f} ansS={row['ans_strict']:.2f} "
                  f"fixed={row['mistakes_resolved']}/{row['mistakes_total']} "
                  f"refs={row['pred_refs']}")
        time.sleep(throttle)
    return rows


def run_medtech(endpoint: str, api_key: str | None, timeout: float,
                throttle: float, verbose: bool) -> list[dict]:
    try:
        from evals.regenold.scenarios_medtech_multiturn_r118 import MEDTECH_MULTITURN
    except ImportError:
        print("  (medtech scenarios file not present yet — skipping)")
        return []
    rows = []
    for scn in MEDTECH_MULTITURN:
        history: list[dict[str, str]] = []
        turn_answers = []
        final_body: dict = {"answer": "", "references": [], "reasoning": None}
        final_lat = 0.0
        final_err = None
        for ti, user_turn in enumerate(scn["turns"]):
            history.append({"role": "user", "content": user_turn})
            body, lat, status, err, attempts, retried = _post(
                endpoint, api_key, history, timeout)
            if err is None and not (200 <= status < 300):
                err = f"http_{status}"
            ans = body.get("answer") or ""
            history.append({"role": "assistant", "content": ans})
            turn_answers.append({"turn": ti + 1, "user": user_turn,
                                 "answer": ans, "refs": body.get("references") or [],
                                 "latency_ms": round(lat, 1)})
            final_body, final_lat, final_err = body, lat, err
            time.sleep(throttle)
        answer = final_body.get("answer") or ""
        refs = final_body.get("references") or []
        expected_refs = _norm_refs(scn.get("expected_refs", []))
        refm = _ref_metrics(refs, expected_refs)
        kw = _keyword_recall(answer, scn.get("expected_keywords", []))
        answer_low = _norm(answer)
        row = {
            "id": scn["id"],
            "domain": scn.get("domain"),
            "turns_count": len(scn["turns"]),
            "final_question": scn["turns"][-1],
            "expected_refs": expected_refs,
            "pred_refs": refs,
            "predicted_answer": answer,
            "ref_loose": refm["loose"],
            "ref_strict": refm["strict"],
            "ref_conciseness": refm["conciseness"],
            "keyword_recall": kw,
            "regulatory_tone": M.regulatory_tone(answer),
            "coherent": (refm["loose"] >= 0.5 and kw >= 0.5
                         and not any(m in answer_low for m in REFUSAL_MARKERS)),
            "is_refusal": any(m in answer_low for m in REFUSAL_MARKERS),
            "latency_ms": round(final_lat, 1),
            "error": final_err,
            "reasoning": _parse_reasoning(final_body.get("reasoning")),
            "turn_answers": turn_answers,
        }
        rows.append(row)
        if verbose:
            r = row["reasoning"]
            print(f"[{scn['id']}] {row['turns_count']}turns model={r['stage2_model']} "
                  f"cx={r['complex']} refL={row['ref_loose']:.2f} kw={kw:.2f} "
                  f"coherent={row['coherent']} refs={refs}")
    return rows


def _mean(xs: list[float]) -> float:
    return round(statistics.mean(xs), 4) if xs else 0.0


def _aggregate_af(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["error"]]
    mt_total = sum(r["mistakes_total"] for r in ok)
    mt_fixed = sum(r["mistakes_resolved"] for r in ok)
    lats = sorted(r["latency_ms"] for r in ok)
    return {
        "n": len(rows), "n_ok": len(ok), "n_error": len(rows) - len(ok),
        "ans_loose": _mean([r["ans_loose"] for r in ok]),
        "ans_strict": _mean([r["ans_strict"] for r in ok]),
        "ans_f1": _mean([r["ans_f1"] for r in ok]),
        "ans_conciseness": _mean([r["ans_conciseness"] for r in ok]),
        "ref_loose": _mean([r["ref_loose"] for r in ok]),
        "ref_strict": _mean([r["ref_strict"] for r in ok]),
        "ref_conciseness": _mean([r["ref_conciseness"] for r in ok]),
        "regulatory_tone": _mean([r["regulatory_tone"] for r in ok]),
        "keyword_recall": _mean([r["keyword_recall"] for r in ok]),
        "mistakes_total": mt_total, "mistakes_resolved": mt_fixed,
        "mistakes_resolved_rate": round(mt_fixed / mt_total, 4) if mt_total else 0.0,
        "complex_fired": sum(1 for r in ok if r["reasoning"].get("complex")),
        "stage2_polish": sum(1 for r in ok if r["reasoning"].get("stage2_polish")),
        "latency_p50_ms": lats[len(lats) // 2] if lats else 0.0,
        "latency_p95_ms": lats[min(len(lats) - 1, int(len(lats) * 0.95))] if lats else 0.0,
    }


def _aggregate_mt(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["error"]]
    lats = sorted(r["latency_ms"] for r in ok)
    return {
        "n": len(rows), "n_ok": len(ok), "n_error": len(rows) - len(ok),
        "ref_loose": _mean([r["ref_loose"] for r in ok]),
        "ref_strict": _mean([r["ref_strict"] for r in ok]),
        "ref_conciseness": _mean([r["ref_conciseness"] for r in ok]),
        "keyword_recall": _mean([r["keyword_recall"] for r in ok]),
        "regulatory_tone": _mean([r["regulatory_tone"] for r in ok]),
        "coherence_rate": round(sum(1 for r in ok if r["coherent"]) / len(ok), 4) if ok else 0.0,
        "complex_fired": sum(1 for r in ok if r["reasoning"].get("complex")),
        "latency_p50_ms": lats[len(lats) // 2] if lats else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="r118-live")
    ap.add_argument("--set", choices=["antifragile", "medtech", "both"], default="both")
    ap.add_argument("--endpoint", default=LIVE_ENDPOINT)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--throttle", type=float, default=1.5)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    api_key = _load_api_key()
    if not api_key:
        raise SystemExit("No P2P_REGENOLD_API_KEY found (env or .env)")
    endpoint = args.endpoint
    if "include_reasoning" not in endpoint:
        endpoint += ("&" if "?" in endpoint else "?") + "include_reasoning=true"
    verbose = not args.quiet
    print(f"endpoint={endpoint}\nset={args.set} throttle={args.throttle}s timeout={args.timeout}s\n")

    out: dict[str, Any] = {"label": args.label, "endpoint": endpoint}
    if args.set in ("antifragile", "both"):
        print("=== Antifragile 20 (single-turn live) ===")
        af = run_antifragile(endpoint, api_key, args.timeout, args.throttle, verbose)
        out["antifragile_rows"] = af
        out["antifragile_summary"] = _aggregate_af(af)
        print("\nANTIFRAGILE SUMMARY:", json.dumps(out["antifragile_summary"], indent=2))
    if args.set in ("medtech", "both"):
        print("\n=== Medtech/life-sci multi-turn (live) ===")
        mt = run_medtech(endpoint, api_key, args.timeout, args.throttle, verbose)
        out["medtech_rows"] = mt
        out["medtech_summary"] = _aggregate_mt(mt)
        print("\nMEDTECH SUMMARY:", json.dumps(out["medtech_summary"], indent=2))

    outdir = Path(".evalout/r118")
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / f"live_{args.label}.json"
    outpath.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {outpath}")


if __name__ == "__main__":
    main()

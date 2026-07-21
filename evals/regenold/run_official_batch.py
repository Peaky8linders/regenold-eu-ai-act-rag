"""Replay the REAL regenold benchmark batch (2026-07-07) against the live system.

This is the highest-fidelity eval surface this repo has: the questions are the
ones the official report actually graded (see
:mod:`evals.regenold.official_batch` for provenance + the hard-mode recovery
caveat), not a proxy probe set.

    EASY  — 110 cold single-turn questions. Byte-exact replay.
    HARD  — the same 110 inside a rolling multi-turn conversation, each answer
            then challenged with the judge's verbatim pushback template. Two
            live requests per question; BOTH answers are recorded so the
            **pushback flip rate** (did we abandon a correct answer when told
            "I think you're hallucinating"?) is measurable.

We do NOT have the official gold references or gold answers, so this runner
deliberately does **not** invent a correctness score. It records what it can
measure objectively (tone, reference counts, answer length, latency, refusal
rate, pushback flips, answer/ref churn vs the 2026-07-07 shipped output) and
writes a sidecar shaped for :mod:`evals.judge.grounded` — the Sonnet-5 judge
that scores answer / reference / citation correctness against the **verbatim
Act text**, which is the right instrument when gold labels are unavailable.

USAGE
-----
    # single arm, live, both modes
    .venv/Scripts/python.exe -m evals.regenold.run_official_batch \\
        --label r285-head --mode both

    # A/B two env arms (sequential — never two wrapper-bound jobs at once)
    .venv/Scripts/python.exe -m evals.regenold.run_official_batch \\
        --label r285 --mode easy \\
        --baseline-env REGENOLD_VERIFY_VERDICT=1 \\
        --branch-env  REGENOLD_VERIFY_VERDICT=0

    # against deployed prod instead of the in-process route
    ... --endpoint https://<host>/api/v1/regenold/eu-ai-act/ask --api-key $KEY

Then grade a sidecar:
    .venv/Scripts/python.exe -m evals.judge.grounded \\
        --sidecar evals/bench/results/official-<label>-easy.ckpt.jsonl \\
        --label <label> --model claude-sonnet-5 --provider wrapper
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
from pathlib import Path
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.regenold.official_batch import (
    build_hard_messages,
    build_pushback_messages,
    load_official_batch,
    trim_history,
)

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"

_REFUSAL_MARKERS = (
    "i cannot answer your question from my knowledge graph",
    "from these materials, which address only obligations",
    "no matching obligation found",
    "try rephrasing",
)


def _is_refusal(answer: str) -> bool:
    low = (answer or "").lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def _heads(refs: list[str]) -> set[str]:
    return set(bench_metrics.article_heads(refs or []))


def _row_metrics(answer: str, refs: list[str]) -> dict[str, Any]:
    return {
        "tone": bench_metrics.regulatory_tone(answer),
        "n_refs": len(refs or []),
        "n_ref_heads": len(_heads(refs)),
        "answer_chars": len(answer or ""),
        "refused": _is_refusal(answer),
    }


def _apply_env(arm_env: dict[str, str]) -> dict[str, str | None]:
    saved: dict[str, str | None] = {}
    for k, v in arm_env.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v
    return saved


def _restore_env(saved: dict[str, str | None]) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _run_easy(rows, poster, url, api_key, timeout, ckpt) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        body, latency_ms, status, err, attempts, _r = poster(
            url, api_key, row.easy_messages(), timeout
        )
        answer = str((body or {}).get("answer") or "")
        refs = list((body or {}).get("references") or [])
        rec: dict[str, Any] = {
            "id": row.id,
            "mode": "easy",
            "question": row.question,
            "pred_answer": answer,
            "pred_refs": refs,
            "jul07_answer": row.jul07_answer,
            "jul07_refs": list(row.jul07_refs),
            "latency_ms": latency_ms,
            "http_status": status,
            "attempts": attempts,
        }
        if err or not answer:
            rec["error"] = err or "empty_answer"
        else:
            rec["scores"] = _row_metrics(answer, refs)
            jul_heads = _heads(list(row.jul07_refs))
            new_heads = _heads(refs)
            rec["vs_jul07"] = {
                "ref_head_added": sorted(new_heads - jul_heads),
                "ref_head_dropped": sorted(jul_heads - new_heads),
                "ref_head_jaccard": (
                    len(new_heads & jul_heads) / len(new_heads | jul_heads)
                    if (new_heads | jul_heads)
                    else 1.0
                ),
                "answer_changed": (answer.strip() != row.jul07_answer.strip()),
            }
        out.append(rec)
        ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ckpt.flush()
        tag = "ERR " if rec.get("error") else "ok  "
        print(
            f"  [{i:3d}/{len(rows)}] easy {tag}{row.id} "
            f"{latency_ms/1000:6.1f}s refs={len(refs):2d} chars={len(answer):4d}",
            flush=True,
        )
    return out


def _run_hard(rows, poster, url, api_key, timeout, ckpt) -> list[dict[str, Any]]:
    """Rolling multi-turn conversation + the judge's pushback, per question."""
    out: list[dict[str, Any]] = []
    history: list[dict[str, str]] = []
    for i, row in enumerate(rows, 1):
        # --- turn 1: the question inside the running conversation ----------
        msgs1 = build_hard_messages(row, history)
        body1, lat1, st1, err1, att1, _ = poster(url, api_key, msgs1, timeout)
        ans1 = str((body1 or {}).get("answer") or "")
        refs1 = list((body1 or {}).get("references") or [])

        # --- turn 2: pushback ----------------------------------------------
        ans2, refs2, lat2, st2, err2, att2 = "", [], 0.0, None, None, 0
        if ans1:
            msgs2 = build_pushback_messages(row, history, ans1)
            body2, lat2, st2, err2, att2, _ = poster(url, api_key, msgs2, timeout)
            ans2 = str((body2 or {}).get("answer") or "")
            refs2 = list((body2 or {}).get("references") or [])

        rec: dict[str, Any] = {
            "id": row.id,
            "mode": "hard",
            "question": row.question,
            # The graded answer for hard mode is the POST-pushback one; keep
            # turn 1 alongside so the flip is measurable.
            "pred_answer": ans2 or ans1,
            "pred_refs": refs2 or refs1,
            "turn1_answer": ans1,
            "turn1_refs": refs1,
            "pushback_answer": ans2,
            "pushback_refs": refs2,
            "jul07_answer": row.jul07_answer,
            "jul07_refs": list(row.jul07_refs),
            "latency_ms": (lat1 or 0) + (lat2 or 0),
            "http_status": st2 or st1,
            "attempts": (att1 or 0) + (att2 or 0),
        }
        if err1 or not ans1:
            rec["error"] = err1 or "empty_answer_turn1"
        elif err2 or not ans2:
            rec["error"] = err2 or "empty_answer_pushback"
        else:
            rec["scores"] = _row_metrics(ans2, refs2)
            h1, h2 = _heads(refs1), _heads(refs2)
            rec["pushback"] = {
                # Did the pushback change the citation set at all?
                "ref_heads_changed": sorted(h1 ^ h2),
                "ref_head_jaccard": (
                    len(h1 & h2) / len(h1 | h2) if (h1 | h2) else 1.0
                ),
                "answer_changed": ans1.strip() != ans2.strip(),
                "turn1_chars": len(ans1),
                "pushback_chars": len(ans2),
                # A capitulation marker: conceding under pressure without new law.
                "conceded": any(
                    p in ans2.lower()
                    for p in (
                        "i apologise",
                        "i apologize",
                        "you are right",
                        "you're right",
                        "i was incorrect",
                        "my previous answer",
                        "correction:",
                    )
                ),
            }
        out.append(rec)
        ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ckpt.flush()

        # Roll the conversation forward exactly as the judge did.
        if ans1:
            history = trim_history(
                [
                    *history,
                    {"role": "user", "content": row.question},
                    {"role": "assistant", "content": ans2 or ans1},
                ]
            )
        tag = "ERR " if rec.get("error") else "ok  "
        flip = ""
        if rec.get("pushback", {}).get("ref_heads_changed"):
            flip = "  REF-FLIP"
        if rec.get("pushback", {}).get("conceded"):
            flip += "  CONCEDED"
        print(
            f"  [{i:3d}/{len(rows)}] hard {tag}{row.id} "
            f"{(rec['latency_ms'])/1000:6.1f}s refs={len(refs2):2d}{flip}",
            flush=True,
        )
    return out


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if not r.get("error")]
    if not ok:
        return {"n": 0, "errors": len(rows)}
    out: dict[str, Any] = {"n": len(ok), "errors": len(rows) - len(ok)}
    for axis in ("tone", "n_refs", "n_ref_heads", "answer_chars"):
        out[axis] = st.mean(r["scores"][axis] for r in ok)
    out["refusal_rate"] = sum(1 for r in ok if r["scores"]["refused"]) / len(ok)
    lat = sorted(r["latency_ms"] for r in ok)
    out["latency_p50_ms"] = lat[len(lat) // 2]
    out["latency_p90_ms"] = lat[int(len(lat) * 0.9)] if len(lat) > 1 else lat[0]
    pb = [r["pushback"] for r in ok if r.get("pushback")]
    if pb:
        out["pushback_ref_flip_rate"] = sum(
            1 for p in pb if p["ref_heads_changed"]
        ) / len(pb)
        out["pushback_ref_jaccard"] = st.mean(p["ref_head_jaccard"] for p in pb)
        out["pushback_conceded_rate"] = sum(1 for p in pb if p["conceded"]) / len(pb)
    vj = [r["vs_jul07"] for r in ok if r.get("vs_jul07")]
    if vj:
        out["vs_jul07_ref_jaccard"] = st.mean(v["ref_head_jaccard"] for v in vj)
        out["vs_jul07_answer_changed_rate"] = sum(
            1 for v in vj if v["answer_changed"]
        ) / len(vj)
    return out


def _print_agg(title: str, agg: dict[str, Any]) -> None:
    print(f"\n=== {title} (n={agg.get('n', 0)}, errors={agg.get('errors', 0)}) ===")
    for k, v in agg.items():
        if k in ("n", "errors"):
            continue
        if k.endswith("_ms"):
            print(f"  {k:<32}{v/1000:>10.1f}s")
        elif isinstance(v, float):
            print(f"  {k:<32}{v:>10.4f}")
        else:
            print(f"  {k:<32}{v:>10}")


def _arm(
    label: str,
    mode: str,
    rows,
    *,
    poster,
    url: str,
    api_key: str | None,
    timeout: float,
    arm_env: dict[str, str],
    suffix: str,
) -> dict[str, Any]:
    saved = _apply_env(arm_env)
    try:
        result: dict[str, Any] = {}
        for m in ("easy", "hard"):
            if mode not in (m, "both"):
                continue
            ckpt_path = _RESULTS / f"official-{label}{suffix}-{m}.ckpt.jsonl"
            ckpt_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"\n--- {label}{suffix} :: {m} (n={len(rows)}) -> {ckpt_path.name}")
            with ckpt_path.open("a", encoding="utf-8") as ckpt:
                runner = _run_easy if m == "easy" else _run_hard
                got = runner(rows, poster, url, api_key, timeout, ckpt)
            result[m] = {"rows": got, "agg": _aggregate(got)}
            _print_agg(f"{label}{suffix} {m}", result[m]["agg"])
        return result
    finally:
        _restore_env(saved)


def _parse_env(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--*-env expects KEY=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    ap.add_argument("--mode", choices=("easy", "hard", "both"), default="easy")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--api-key", default=os.environ.get("REGENOLD_API_KEY"))
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int, default=0, help="first N questions only")
    ap.add_argument("--baseline-env", action="append", default=None)
    ap.add_argument("--branch-env", action="append", default=None)
    args = ap.parse_args()

    rows = list(load_official_batch())
    if args.limit:
        rows = rows[: args.limit]

    from evals.regenold.runner_v2 import _post, _post_local

    local = not args.endpoint
    poster = _post_local if local else _post
    url = (
        "local://app.main:app/api/v1/regenold/eu-ai-act/ask"
        if local
        else str(args.endpoint)
    )

    base_env = _parse_env(args.baseline_env)
    branch_env = _parse_env(args.branch_env)
    ab = bool(base_env or branch_env)

    payload: dict[str, Any] = {
        "label": args.label,
        "batch": "regenold-official-2026-07-07",
        "n_questions": len(rows),
        "mode": args.mode,
        "endpoint": url,
        "baseline_env": base_env,
        "branch_env": branch_env,
    }

    baseline = _arm(
        args.label, args.mode, rows,
        poster=poster, url=url, api_key=args.api_key, timeout=args.timeout,
        arm_env=base_env, suffix="-A" if ab else "",
    )
    payload["baseline"] = {m: v["agg"] for m, v in baseline.items()}

    if ab:
        # SEQUENTIAL — one local Claude Max backs every wrapper call.
        branch = _arm(
            args.label, args.mode, rows,
            poster=poster, url=url, api_key=args.api_key, timeout=args.timeout,
            arm_env=branch_env, suffix="-B",
        )
        payload["branch"] = {m: v["agg"] for m, v in branch.items()}
        for m in baseline:
            b, c = baseline[m]["agg"], branch.get(m, {}).get("agg", {})
            if not c:
                continue
            print(f"\n=== DELTA {m} (baseline -> branch) ===")
            for k in sorted(set(b) & set(c)):
                if k in ("n", "errors") or not isinstance(b[k], (int, float)):
                    continue
                print(f"  {k:<32}{b[k]:>10.4f}{c[k]:>10.4f}{c[k]-b[k]:>+10.4f}")

    out = _RESULTS / f"official-{args.label}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

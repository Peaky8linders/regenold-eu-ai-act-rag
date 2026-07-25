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


def _provenance(body: dict[str, Any] | None) -> dict[str, Any]:
    """Pull Stage-2 provenance out of the ``reasoning`` trace.

    R292: without this the sidecar records only ``answer`` + ``references``, so a
    run in which the Stage-2 provider silently degraded (wrapper down, credit
    exhausted, rate-limited) is INDISTINGUISHABLE from a healthy run — the
    deterministic fallback still returns a plausible answer. That makes the
    headline scorecard unfalsifiable. Recording ``stage2_polish`` / the resolved
    model / ``retrieval_path`` per row makes a degraded run detectable after the
    fact, and the aggregate ``stage2_landed_rate`` makes it obvious at a glance.

    Fail-soft: a missing / non-JSON ``reasoning`` field yields an empty dict, so
    this can never break a run.
    """
    try:
        raw = (body or {}).get("reasoning")
        if not isinstance(raw, str) or not raw.strip():
            return {}
        trace = json.loads(raw)
        if not isinstance(trace, dict):
            return {}
        model = ""
        for note in trace.get("notes") or []:
            if isinstance(note, str) and "stage2_model=" in note:
                model = note.split("stage2_model=", 1)[1].split()[0]
                break
        return {
            "stage2_polish": trace.get("stage2_polish"),
            "retrieval_path": trace.get("retrieval_path"),
            "engine_confidence": trace.get("engine_confidence"),
            "stage2_model": model,
        }
    except Exception:  # noqa: BLE001 — provenance is best-effort telemetry
        return {}


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
            # R293 — official difficulty label. Distinct from `mode`: `mode` is
            # HOW we replayed it, `difficulty` is the evaluator's own label. 59
            # of the 111 single-turn rows are HARD by content.
            "difficulty": row.difficulty,
            "difficulty_category": row.difficulty_category,
            "question": row.question,
            "pred_answer": answer,
            "pred_refs": refs,
            "jul07_answer": row.jul07_answer,
            "jul07_refs": list(row.jul07_refs),
            "latency_ms": latency_ms,
            "http_status": status,
            "attempts": attempts,
            "provenance": _provenance(body),
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
            # R293 — in hard mode every row is HARD / Multi-Turn Context &
            # Coreference by the official taxonomy, so the per-question label
            # from the single-turn export is not the operative one here; keep it
            # for cross-mode comparison of the SAME question.
            "difficulty": row.difficulty,
            "difficulty_category": row.difficulty_category,
            "question": row.question,
            # The graded answer for hard mode is the POST-pushback one; keep
            # turn 1 alongside so the flip is measurable.
            "pred_answer": ans2 or ans1,
            "pred_refs": refs2 or refs1,
            # Provenance of the GRADED turn (post-pushback when it landed).
            "provenance": _provenance(body2 if ans2 else body1),
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


#: Axes worth breaking out per difficulty stratum. Deliberately NOT every axis —
#: a 1-row stratum (Borderline Prohibition) makes most means meaningless, and a
#: wall of noisy numbers is how a real signal gets missed.
_STRATUM_AXES = ("n", "errors", "refusal_rate", "n_refs", "tone", "latency_p50_ms")


def _stratify(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """R293 — aggregate per official difficulty label and per category.

    The point: a single blended number hides which half of the batch is weak.
    52 of the single-turn requests are EASY (direct statutory lookup) and 59 are
    HARD by content, so a mediocre blended score can mean either "we are bad at
    lookups" or "we are fine at lookups and bad at decision boundaries" — very
    different problems with very different fixes.

    Strata with n < 3 still report, but carry ``low_n: True`` so nobody reads a
    mean over one row as a trend.
    """
    out: dict[str, Any] = {}
    for key, field in (("by_difficulty", "difficulty"), ("by_category", "difficulty_category")):
        buckets: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            label = str(r.get(field) or "")
            if not label:
                label = "(unlabelled)"
            buckets.setdefault(label, []).append(r)
        section: dict[str, Any] = {}
        for label, brows in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            agg = _aggregate(brows)
            slim = {k: agg[k] for k in _STRATUM_AXES if k in agg}
            if agg.get("n", 0) < 3:
                slim["low_n"] = True
            section[label] = slim
        out[key] = section
    return out


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if not r.get("error")]
    if not ok:
        return {"n": 0, "errors": len(rows)}
    out: dict[str, Any] = {"n": len(ok), "errors": len(rows) - len(ok)}
    for axis in ("tone", "n_refs", "n_ref_heads", "answer_chars"):
        out[axis] = st.mean(r["scores"][axis] for r in ok)
    out["refusal_rate"] = sum(1 for r in ok if r["scores"]["refused"]) / len(ok)
    # R292 — Stage-2 provenance. `stage2_landed_rate` well under 1.0 means the
    # LLM path degraded mid-run and the scorecard is measuring the deterministic
    # fallback, not the system under test. Check this BEFORE reading any axis.
    prov = [r.get("provenance") or {} for r in ok]
    seen = [p for p in prov if p.get("stage2_polish") is not None]
    if seen:
        out["stage2_landed_rate"] = sum(
            1 for p in seen if p.get("stage2_polish")
        ) / len(seen)
        models = sorted({p.get("stage2_model") or "?" for p in seen if p.get("stage2_polish")})
        out["stage2_models"] = models
        paths: dict[str, int] = {}
        for p in prov:
            key = str(p.get("retrieval_path") or "unknown")
            paths[key] = paths.get(key, 0) + 1
        out["retrieval_paths"] = dict(sorted(paths.items(), key=lambda kv: -kv[1]))
    else:
        out["stage2_landed_rate"] = None  # trace not requested / not available
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


def _print_strata(strata: dict[str, Any]) -> None:
    """R293 — print the per-difficulty / per-category breakdown."""
    for section, title in (
        ("by_difficulty", "by OFFICIAL difficulty"),
        ("by_category", "by difficulty category"),
    ):
        buckets = strata.get(section) or {}
        if len(buckets) < 2:
            continue  # nothing to compare against
        print(f"\n  --- {title} ---")
        for label, s in buckets.items():
            flag = "  [low n]" if s.get("low_n") else ""
            bits = [f"n={s.get('n', 0)}"]
            for k in ("refusal_rate", "n_refs", "tone"):
                if k in s:
                    bits.append(f"{k}={s[k]:.3f}")
            if "latency_p50_ms" in s:
                bits.append(f"p50={s['latency_p50_ms'] / 1000:.1f}s")
            print(f"    {label[:46]:<46} {'  '.join(bits)}{flag}")


def _print_agg(title: str, agg: dict[str, Any]) -> None:
    print(f"\n=== {title} (n={agg.get('n', 0)}, errors={agg.get('errors', 0)}) ===")
    for k, v in agg.items():
        if k in ("n", "errors"):
            continue
        if k.endswith("_ms"):
            print(f"  {k:<32}{v/1000:>10.1f}s")
        elif isinstance(v, float):
            print(f"  {k:<32}{v:>10.4f}")
        elif isinstance(v, (list, tuple)):
            # R292 — stage2_models etc. are lists; ">10" formatting raises.
            print(f"  {k:<32}{', '.join(str(x) for x in v) or '-':>10}")
        elif isinstance(v, dict):
            print(f"  {k:<32}{', '.join(f'{a}={b}' for a, b in v.items()):>10}")
        elif v is None:
            print(f"  {k:<32}{'n/a':>10}")
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
            # R292 — "w", not "a". In append mode, re-running the SAME label
            # silently merged the previous run's rows into the checkpoint file,
            # so anything reading the .ckpt.jsonl (a resumed run, or the judge)
            # graded a mix of stale and fresh answers with no way to tell them
            # apart. Each run now owns its checkpoint; use a distinct --label to
            # keep an earlier run.
            with ckpt_path.open("w", encoding="utf-8") as ckpt:
                runner = _run_easy if m == "easy" else _run_hard
                got = runner(rows, poster, url, api_key, timeout, ckpt)
            strata = _stratify(got)
            result[m] = {"rows": got, "agg": _aggregate(got), "strata": strata}
            _print_agg(f"{label}{suffix} {m}", result[m]["agg"])
            _print_strata(strata)
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
    # R292 — ask for the reasoning trace so `_provenance` can record whether
    # Stage-2 actually landed (see `_provenance`). The rubric ignores the
    # `reasoning` field, so this cannot affect a score; it only makes a
    # silently-degraded run detectable.
    if "include_reasoning" not in url:
        url = f"{url}{'&' if '?' in url else '?'}include_reasoning=true"

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

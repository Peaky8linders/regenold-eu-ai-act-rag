"""Checkpointed, sequential prompt A/B using the existing pairwise/gold gates.

Each pair is captured once and may be judged later with --judge-only. Identical
pairs need no judge calls. Transport failures abort instead of becoming ties.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--label", required=True)
    p.add_argument("--ids", nargs="*", default=[])
    p.add_argument("--probe-limit", type=int, default=0)
    p.add_argument("--provider", choices=["openai_wrapper", "bedrock"], default="openai_wrapper",
                   help="Stage-2 transport provider (default: openai_wrapper)")
    p.add_argument("--model", default=None,
                   help="Model override (for Bedrock, defaults to eu.anthropic.claude-sonnet-4-6)")
    p.add_argument("--judge-provider", choices=["wrapper", "bedrock"], default=None,
                   help="Judge caller provider (default: matches provider)")
    p.add_argument("--capture-only", action="store_true")
    p.add_argument("--judge-only", action="store_true")
    p.add_argument("--timeout", type=float, default=120)
    args = p.parse_args()
    if not args.label or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.label):
        p.error("label must contain only letters, digits, hyphens and underscores")

    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")

    is_bedrock = (args.provider == "bedrock")
    if is_bedrock:
        bedrock_model = args.model or "eu.anthropic.claude-sonnet-4-6"
        os.environ.update({
            "REGENOLD_SKIP_DOTENV": "1",
            "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
            "P2P_GRAPH_RAG_PROVIDER": "bedrock",
            "P2P_GRAPH_RAG_ENABLE_STAGE2": "1",
            "REGENOLD_STAGE2_STRICT_TRANSPORT": "0",
            "REGENOLD_BEDROCK_STAGE2_MODEL": bedrock_model,
            "REGENOLD_BEDROCK_COMPLEX_MODEL": bedrock_model,
            "REGENOLD_BEDROCK_MODEL": bedrock_model,
            "REGENOLD_BEDROCK_FALLBACK_CHAIN": bedrock_model,
            "REGENOLD_BEDROCK_WRAPPER_FALLBACK": "0",
        })
    else:
        os.environ.update({
            "REGENOLD_SKIP_DOTENV": "1",
            "P2P_GRAPH_RAG_PROVIDER": "openai_wrapper",
            "P2P_GRAPH_RAG_ENABLE_STAGE2": "1",
            "REGENOLD_BEDROCK_WRAPPER_FALLBACK": "0",
        })
    from evals.harness import ab_judge as ab, easyhard_ab as eh
    from evals.harness.probe_set import ProbeRow, load_probe_set
    from evals.regenold.runner_v2 import _ensure_local_auth, _post_local
    from evals.regenold.run_official_batch import _provenance
    from app.engines import _graph_rag_impl as engine
    from app.llm import stage2_policy

    outdir = root / "docs" / "measurements" / "prompt-compact"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{args.label}.jsonl"
    official = json.loads((root / "evals/regenold/_official_batch_20260707.json").read_text(encoding="utf-8"))
    keys = {r["id"]: r for r in map(json.loads, (root / "docs/measurements/r388/official_refkey_n110.jsonl").read_text(encoding="utf-8").splitlines())}
    selected = [r for r in official if r["id"] in args.ids]
    if set(args.ids) - {r["id"] for r in selected}:
        p.error("unknown official row id")
    rows = [ProbeRow(
        id=r["id"], source="official-proxy", category="official", is_multiturn=False,
        messages=({"role": "user", "content": r["question"]},),
        expected_refs=tuple(keys[r["id"]].get("expected") or []), expected_keywords=(),
    ) for r in selected]
    if args.probe_limit:
        rows += load_probe_set(limit=args.probe_limit)
    if not rows:
        p.error("select --ids or --probe-limit")

    saved = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    by_id = {r["id"]: r for r in saved}
    if not args.judge_only:
        if is_bedrock:
            from app.llm.bedrock_client import check_connectivity_and_permissions
            probe_status = check_connectivity_and_permissions(model_id=os.environ["REGENOLD_BEDROCK_STAGE2_MODEL"])
            if probe_status.get("status") != "ok":
                raise RuntimeError(f"Bedrock probe failed: {probe_status}")
        else:
            if not ab._wrapper_up(timeout=5):
                raise RuntimeError("live wrapper unavailable; no deterministic substitution")
        auth = _ensure_local_auth()
        original = engine._bedrock_complete_for_graph_rag if is_bedrock else engine._openai_wrapper_complete_for_graph_rag
        seen = []

        def record_prompt(*a, **kw):
            user = kw.get("user", "")
            if "EU AI ACT REFERENCES:" in user or "ANSWER CONTRACT" in user:
                seen.append({
                    "user_chars": len(user), "system_chars": len(kw.get("system", "")),
                    "compact_delivered": "ANSWER CONTRACT (compact)" in user,
                    "prompt_sha256": hashlib.sha256(user.encode()).hexdigest(),
                })
            return original(*a, **kw)

        if is_bedrock:
            engine._bedrock_complete_for_graph_rag = record_prompt
        else:
            engine._openai_wrapper_complete_for_graph_rag = record_prompt
        try:
            for i, row in enumerate(rows):
                if row.id in by_id:
                    continue
                rec = {"id": row.id, "row": row.to_dict()}
                # Alternate which arm runs first to balance cache/time effects.
                for value in (("0", "1") if i % 2 == 0 else ("1", "0")):
                    os.environ["REGENOLD_PROMPT_COMPACT"] = value
                    ab._clear_engine_cache()
                    stage2_policy.reset_transport_stats()
                    seen.clear()
                    body, latency, status, error, *_ = _post_local(
                        "x://local?include_reasoning=true", auth, list(row.messages), args.timeout,
                    )
                    stats = stage2_policy.transport_stats()
                    if error or status != 200 or not body.get("answer"):
                        raise RuntimeError(f"{row.id} arm {value}: route failed ({status})")
                    if is_bedrock:
                        prov = _provenance(body)
                        if seen and not prov.get("stage2_polish"):
                            raise RuntimeError(f"{row.id} arm {value}: Stage-2 Bedrock did not land")
                    else:
                        if stats.get("fallback_attempts") or stats.get("primary_failed"):
                            raise RuntimeError(f"{row.id} arm {value}: transport failure/fallback")
                        if seen and not stats.get("primary_ok"):
                            raise RuntimeError(f"{row.id} arm {value}: Stage-2 did not succeed")
                    rec[value] = {
                        "answer": body["answer"], "refs": body.get("references", []),
                        "latency_ms": latency, "http_status": status,
                        "provenance": _provenance(body), "transport": stats,
                        "prompts": list(seen),
                    }
                    print(f"capture {i+1}/{len(rows)} {row.id} arm={value} chars={len(body['answer'])} refs={body.get('references')} prompt_calls={len(seen)}", flush=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                by_id[row.id] = rec
        finally:
            if is_bedrock:
                engine._bedrock_complete_for_graph_rag = original
            else:
                engine._openai_wrapper_complete_for_graph_rag = original

    records = [by_id[r.id] for r in rows if r.id in by_id]
    if len(records) != len(rows):
        raise RuntimeError("incomplete paired capture")
    arms = {}
    for value in ("0", "1"):
        scored = [{
            "id": r.id, "is_multiturn": r.is_multiturn,
            "pred_refs": by_id[r.id][value]["refs"],
            "gold_refs": r.expected_refs,
            "scores": eh._score_row(r, by_id[r.id][value]["answer"], by_id[r.id][value]["refs"]),
            "latency_ms": by_id[r.id][value]["latency_ms"],
        } for r in rows]
        arms[value] = {s: eh._aggregate([r for r in scored if r["is_multiturn"] == (s == "hard")]) for s in ("easy", "hard")}
    gate = eh._gold_gate_verdict(arms["0"], arms["1"])
    result = {"n": len(rows), "arms": arms, "gold_gate": gate, "capture": str(path)}
    print("gold gate:", json.dumps(gate), flush=True)
    if not args.capture_only:
        from evals.judge import runner as judge
        judge_prov = args.judge_provider or ("bedrock" if is_bedrock else "wrapper")
        if judge_prov == "bedrock":
            judge_model = os.getenv("REGENOLD_BEDROCK_JUDGE_MODEL", "").strip() or "eu.anthropic.claude-sonnet-4-6"
            judge.set_judge_model(judge_model)
        else:
            judge.set_judge_model(os.getenv("REGENOLD_AB_JUDGE_MODEL", "claude-sonnet-5"))
        caller = judge._resolve_caller(judge_prov)
        summaries = judge._load_article_summaries()
        # ab_judge normally converts a judge error to a tie. Reject that outcome.
        def strict_caller(prompt):
            output = caller(prompt)
            if not output:
                raise RuntimeError("empty judge response")
            return output
        axes = {a: ab.AxisResult(axis=a) for a in ab.pairwise_prompts.AXES}
        verdict_path = outdir / f"{args.label}-verdicts.jsonl"
        done = {r["id"]: r for r in map(json.loads, verdict_path.read_text(encoding="utf-8").splitlines())} if verdict_path.exists() else {}
        for rec in records:
            verdicts = done.get(rec["id"], {}).get("verdicts")
            if verdicts is None:
                answers = [ab.ArmAnswer(**{k: rec[v][k] for k in ("answer", "refs", "latency_ms", "http_status")}) for v in ("0", "1")]
                rd = rec["row"]
                rd["question"] = next(r.live_question for r in rows if r.id == rec["id"])
                verdicts = {axis: ("tie" if answers[0].answer == answers[1].answer and answers[0].refs == answers[1].refs else ab._pairwise_verdict(rd, axis, *answers, strict_caller, summaries)) for axis in axes}
                with verdict_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": rec["id"], "verdicts": verdicts}) + "\n")
            for axis, verdict in verdicts.items():
                target = axes[axis]
                if verdict == "A": target.wins_a += 1
                elif verdict == "B": target.wins_b += 1
                else: target.ties += 1
            print("judge", rec["id"], verdicts, flush=True)
        result["pairwise"] = {a: {"baseline_wins": v.wins_a, "candidate_wins": v.wins_b, "ties": v.ties, "p_value": v.p_value()} for a, v in axes.items()}
    (outdir / f"{args.label}-summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return int(gate["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

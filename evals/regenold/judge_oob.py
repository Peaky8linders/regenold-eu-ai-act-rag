"""LLM-as-Judge runner for the OOB sidecar.

Implements the legal-auditor prompt the user supplied (the
``gemini-code-1779789350027.txt`` template). For each OOB row it
sends the question / gold refs / gold answer / pred answer / pred
refs to Sonnet 4.6 (via the Claude Max wrapper at 127.0.0.1:8000) and
expects a JSON verdict back:

    {
      "reference_strict_match": true/false,
      "reference_loose_match":  true/false,
      "tone_professionalism":   1..5,
      "factual_accuracy":       1..5,
      "critique":               "<one-sentence justification>"
    }

Per the project's MEMORY rule ``rule_eval_provider.md`` evals MUST go
through the Claude Max wrapper, not the Anthropic SDK direct.

Usage::

    py -3.12 -m evals.regenold.judge_oob \\
        --sidecar evals/bench/results/oob-r90-pre-deploy-baseline.json \\
        --label   judge-r90-baseline
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

import urllib.request


JUDGE_PROMPT = """You are an expert legal auditor specializing in the EU AI Act (Regulation (EU) 2024/1689). Your task is to evaluate the output of an AI Legal Assistant.

You will be provided with:
1. The User's Question (from a specific persona)
2. The Expected References (Ground Truth)
3. The Expected Answer Concept (Ground Truth)
4. The Model's Predicted Answer
5. The Model's Predicted References

Evaluate the Model's output on the following criteria. Output a JSON payload.

### Scoring Criteria:
- "reference_strict_match" (boolean): True if the Model's Predicted References EXACTLY match the Expected References.
- "reference_loose_match" (boolean): True if the Model successfully identified at least the core Article or Annex, even if sub-points differ.
- "tone_professionalism" (1-5): Rate the legal tone. 5 = Authoritative, clear, human-like legal counsel. 1 = Robotic, repetitive (e.g., heavily penalize starting sentences with "This question is covered by the EU AI Act under...").
- "factual_accuracy" (1-5): Does the predicted answer align with the legal facts of the expected answer?

### Output JSON Format:
{
  "reference_strict_match": true/false,
  "reference_loose_match": true/false,
  "tone_professionalism": <int>,
  "factual_accuracy": <int>,
  "critique": "<A brief one-sentence justification of the tone and accuracy>"
}"""


def _build_user_message(row: dict[str, Any]) -> str:
    return (
        f"Persona: {row.get('persona','(unspecified)')}\n"
        f"Category: {row.get('category','(unspecified)')}\n"
        f"\n"
        f"1. User's Question:\n{row.get('question','')}\n"
        f"\n"
        f"2. Expected References (Ground Truth):\n{json.dumps(row.get('expected_refs', []))}\n"
        f"\n"
        f"3. Expected Answer Concept (Ground Truth):\n{row.get('expected_answer','')}\n"
        f"\n"
        f"4. Model's Predicted Answer:\n{row.get('pred_answer','')}\n"
        f"\n"
        f"5. Model's Predicted References:\n{json.dumps(row.get('pred_refs', []))}\n"
        f"\n"
        f"Produce ONLY the JSON object with EXACTLY these five fields and "
        f"these spellings — no other fields, no prose, no markdown fences:\n"
        f"  reference_strict_match  (boolean)\n"
        f"  reference_loose_match   (boolean)\n"
        f"  tone_professionalism    (integer 1-5)\n"
        f"  factual_accuracy        (integer 1-5)\n"
        f"  critique                (string, one sentence)\n"
        f"\n"
        f"Example shape (DO NOT copy the values — use your own judgment):\n"
        f'{{"reference_strict_match": false, "reference_loose_match": true, '
        f'"tone_professionalism": 3, "factual_accuracy": 4, '
        f'"critique": "Identifies the core article but tone reads as templated."}}'
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Locate and parse the first balanced { ... } block in ``text``."""
    if not text:
        return None
    text = text.strip()
    # Strip a possible ```json ... ``` fence
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
        # Strip leading 'json' marker.
        if text.startswith("json"):
            text = text[4:].lstrip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _judge_one(
    row: dict[str, Any],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
) -> dict[str, Any]:
    """Send one row to the LLM judge and return the parsed verdict."""
    user_msg = _build_user_message(row)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.0,
        "max_tokens": 600,
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "regenold-eu-ai-act-rag/judge-oob",
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "id": row.get("id"),
            "judge_error": f"{exc.__class__.__name__}: {exc}"[:200],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        }
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not isinstance(body, dict):
        return {"id": row.get("id"), "judge_error": "non_dict_response", "elapsed_ms": round(elapsed, 1)}
    choices = body.get("choices") or []
    if not choices:
        return {"id": row.get("id"), "judge_error": "no_choices", "elapsed_ms": round(elapsed, 1)}
    content = (choices[0].get("message") or {}).get("content") or ""
    if isinstance(content, list):
        # Some wrappers return content as a list of blocks.
        parts = []
        for blk in content:
            if isinstance(blk, dict):
                parts.append(blk.get("text") or "")
        content = "".join(parts)
    if "Not logged in" in content:
        return {"id": row.get("id"), "judge_error": "wrapper_not_logged_in", "elapsed_ms": round(elapsed, 1)}
    verdict = _extract_json(content)
    if verdict is None:
        return {
            "id": row.get("id"),
            "judge_error": "json_parse_failed",
            "raw_content": content[:400],
            "elapsed_ms": round(elapsed, 1),
        }

    # Schema-drift normalization: Sonnet sometimes emits "verdict"/"reason"
    # /"reference_match"/"concept_match" instead of the requested 4 fields.
    # Translate when possible so the aggregator can still score.
    if "tone_professionalism" not in verdict or "factual_accuracy" not in verdict:
        critique = verdict.get("critique") or verdict.get("reason") or ""
        ref_match = verdict.get("reference_match")
        concept_match = verdict.get("concept_match")
        # Loose = at least core article matched. Strict = exact.
        if "reference_loose_match" not in verdict and ref_match is not None:
            verdict["reference_loose_match"] = bool(ref_match)
        if "reference_strict_match" not in verdict and ref_match is not None:
            verdict["reference_strict_match"] = bool(ref_match)
        if "factual_accuracy" not in verdict and concept_match is not None:
            # PASS / FAIL → 5 / 1; intermediate verdicts → 3.
            v = (verdict.get("verdict") or "").upper()
            if concept_match is True:
                verdict["factual_accuracy"] = 5 if v == "PASS" else 4
            else:
                verdict["factual_accuracy"] = 1 if v == "FAIL" else 2
        # Tone proxy when missing — judge didn't score it, default neutral.
        verdict.setdefault("tone_professionalism", 3)
        verdict.setdefault("critique", critique[:280])

    out = {
        "id": row.get("id"),
        "elapsed_ms": round(elapsed, 1),
        **verdict,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals.regenold.judge_oob")
    ap.add_argument("--sidecar", required=True, help="OOB runner sidecar path")
    ap.add_argument("--label", default=None)
    ap.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8000/v1"),
        help="OpenAI-compatible chat endpoint (Claude Max wrapper).",
    )
    ap.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY", "dummy"),
        help="Bearer token (wrapper accepts any string).",
    )
    ap.add_argument(
        "--model",
        default=os.environ.get("REGENOLD_JUDGE_MODEL", "claude-sonnet-4-6"),
        help="Judge model (defaults to Sonnet 4.6 via wrapper).",
    )
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    sidecar_path = Path(args.sidecar)
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    rows = sidecar.get("rows") or []
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print(f"[error] no rows in sidecar {args.sidecar}", file=sys.stderr)
        return 2

    print(f"[info] judging {len(rows)} rows from {sidecar_path.name}", file=sys.stderr)
    print(f"[info] judge model: {args.model} via {args.base_url}", file=sys.stderr)

    verdicts: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {
            ex.submit(
                _judge_one,
                row,
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                timeout=args.timeout,
            ): row for row in rows
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            v = fut.result()
            verdicts.append(v)
            tag = "ERR" if v.get("judge_error") else f"tone={v.get('tone_professionalism','?'):>1}  acc={v.get('factual_accuracy','?'):>1}"
            print(f"[{done:3d}/{len(rows)}] {v['id']:18s} {v.get('elapsed_ms',0):7.0f}ms  {tag}  {v.get('judge_error','')}", file=sys.stderr)

    # Sort by original sidecar order for determinism.
    id_order = {r["id"]: i for i, r in enumerate(rows)}
    verdicts.sort(key=lambda v: id_order.get(v.get("id"), 1e9))

    # Aggregate.
    n_total = len(verdicts)
    n_err = sum(1 for v in verdicts if v.get("judge_error"))
    clean = [v for v in verdicts if not v.get("judge_error")]
    n_clean = len(clean)

    def _avg(values: list[float]) -> float:
        return round(mean(values), 4) if values else 0.0

    tone_vals = [int(v["tone_professionalism"]) for v in clean if isinstance(v.get("tone_professionalism"), (int, float))]
    acc_vals = [int(v["factual_accuracy"]) for v in clean if isinstance(v.get("factual_accuracy"), (int, float))]
    ref_strict = sum(1 for v in clean if v.get("reference_strict_match") is True)
    ref_loose = sum(1 for v in clean if v.get("reference_loose_match") is True)

    summary = {
        "n_total": n_total,
        "n_clean": n_clean,
        "n_judge_errors": n_err,
        "tone_avg": _avg(tone_vals),
        "tone_distribution": {str(k): tone_vals.count(k) for k in (1, 2, 3, 4, 5)},
        "factual_accuracy_avg": _avg(acc_vals),
        "factual_accuracy_distribution": {str(k): acc_vals.count(k) for k in (1, 2, 3, 4, 5)},
        "ref_strict_match_rate": round(ref_strict / n_clean, 4) if n_clean else 0.0,
        "ref_loose_match_rate": round(ref_loose / n_clean, 4) if n_clean else 0.0,
    }

    out_label = args.label or sidecar_path.stem.replace("oob-", "judge-")
    out_path = sidecar_path.with_name(f"judge-{out_label}.json")
    out_path.write_text(
        json.dumps({
            "label": out_label,
            "source_sidecar": str(sidecar_path),
            "judge_model": args.model,
            "judge_base_url": args.base_url,
            "started_at": sidecar.get("started_at"),
            "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "summary": summary,
            "verdicts": verdicts,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(file=sys.stderr)
    print("================ OOB JUDGE SUMMARY ================", file=sys.stderr)
    print(f"label                 : {out_label}", file=sys.stderr)
    print(f"items                 : {n_total} (clean={n_clean}, err={n_err})", file=sys.stderr)
    print(f"tone_avg              : {summary['tone_avg']:.3f}  / 5  (distribution: {summary['tone_distribution']})", file=sys.stderr)
    print(f"factual_accuracy_avg  : {summary['factual_accuracy_avg']:.3f}  / 5  (distribution: {summary['factual_accuracy_distribution']})", file=sys.stderr)
    print(f"ref_strict_match_rate : {summary['ref_strict_match_rate']:.4f}", file=sys.stderr)
    print(f"ref_loose_match_rate  : {summary['ref_loose_match_rate']:.4f}", file=sys.stderr)
    print(f"output                : {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

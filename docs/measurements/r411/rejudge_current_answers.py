"""R411 re-judge: score the CURRENT engine answers with the RECORDED judge prompt.

Consumes `docs/measurements/r411/rejudge-current-path.json` (produced by
`rejudge_open_issues.py`) and re-applies the R409 frontier-judge prompt verbatim, so
the criteria verdicts are comparable with the R409 snapshot while reflecting today's
engine.

Judges are pluggable so the same answers can be read by the recorded judge
(OpenRouter `anthropic/claude-sonnet-5`, temp 0.1) and by a Bedrock top model
(`--model bedrock-opus5`) as a second, independent read.

Usage:
    python docs/measurements/r411/rejudge_current_answers.py --judge openrouter
    python docs/measurements/r411/rejudge_current_answers.py --judge bedrock --model anthropic.claude-opus-5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for p in (str(REPO), str(REPO / "docs" / "measurements" / "r409")):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import dotenv_values  # noqa: E402
from run_antifragile_frontier_judge import (  # noqa: E402
    JUDGE_PROMPT_TEMPLATE,
    TEMPERATURE,
    get_verbatim_provisions,
)

from evals.official.rubric import (  # noqa: E402
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

ENV = dotenv_values(REPO / ".env")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_JUDGE = "anthropic/claude-sonnet-5"


def _build_prompt(question: str, criteria: list[str], answer: str, expected_refs: list[str]) -> str:
    provisions = get_verbatim_provisions(expected_refs)
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1))
    ans = (answer or "").strip() or "(the system returned no answer)"
    return (
        JUDGE_PROMPT_TEMPLATE.replace("{provisions}", provisions)
        .replace("{question}", question)
        .replace("{criteria}", numbered)
        .replace("{answer}", f"<candidate_answer>\n{ans}\n</candidate_answer>")
    )


def _parse_verdict(raw_text: str, n_criteria: int) -> dict:
    clean = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    parsed = json.loads(clean)
    verdicts = parsed.get("verdicts", [])
    tone = parsed.get("tone", {}) or {}
    return {
        "criteria_results": [bool(v.get("satisfied")) for v in verdicts],
        "criteria_why": [v.get("why", "") for v in verdicts],
        "tone_pass": bool(tone.get("appropriate")) and bool(tone.get("clear")),
        "tone_why": tone.get("why", ""),
        "raw_response": raw_text,
    }


def _judge_openrouter(prompt: str, retries: int = 4) -> dict:
    key = ENV.get("OPENROUTER_API_KEY") or ""
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    body = json.dumps(
        {
            "model": OPENROUTER_JUDGE,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": TEMPERATURE,
        }
    ).encode()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "AntifragileEvaluator/1.0",
    }
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(OPENROUTER_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=120.0) as res:
                raw = json.loads(res.read().decode())["choices"][0]["message"]["content"] or ""
            return _parse_verdict(raw, 0)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"openrouter judge failed: {last}")


_BEDROCK_PROVIDER = None


def _judge_bedrock(prompt: str, model: str, retries: int = 3) -> dict:
    global _BEDROCK_PROVIDER
    import os

    for k in ("AWS_BEARER_TOKEN_BEDROCK", "BEDROCK_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        v = ENV.get(k)
        if v:
            os.environ.setdefault(k, v)

    from app.llm.bedrock_client import (
        BedrockProvider,
        BedrockRequest,
        resolve_bedrock_model,
    )

    if _BEDROCK_PROVIDER is None:
        _BEDROCK_PROVIDER = BedrockProvider()

    resolved = resolve_bedrock_model(model) or model
    last = None
    for attempt in range(retries):
        resp = _BEDROCK_PROVIDER.complete(
            BedrockRequest(
                user=prompt,
                model=resolved,
                max_tokens=2000,
                temperature=TEMPERATURE,
                timeout_seconds=180.0,
            )
        )
        if resp.error:
            last = resp.error
            time.sleep(1.5 * (attempt + 1))
            continue
        try:
            out = _parse_verdict(resp.text or "", 0)
            out["resolved_model"] = resolved
            return out
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"bedrock judge failed ({resolved}): {last}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["openrouter", "bedrock"], default="openrouter")
    ap.add_argument("--model", default="anthropic.claude-opus-5")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    src = REPO / "docs" / "measurements" / "r411" / "rejudge-current-path.json"
    rows = json.loads(src.read_text(encoding="utf-8"))["rows"]

    tag = "openrouter-sonnet5" if args.judge == "openrouter" else args.model.replace("/", "_")
    out_path = Path(args.out) if args.out else (
        REPO / "docs" / "measurements" / "r411" / f"rejudge-current-{tag}.json"
    )

    def run(row: dict) -> dict:
        prompt = _build_prompt(row["question"], row["criteria"], row["new_answer"], row["expected_refs"])
        if args.judge == "openrouter":
            judged = _judge_openrouter(prompt)
        else:
            judged = _judge_bedrock(prompt, args.model)
        crit = judged["criteria_results"]
        loose = sum(1 for c in crit if c) / len(crit) if crit else 0.0
        exp = row["expected_refs"]
        row = dict(row)
        row["rejudge"] = {
            **judged,
            "judge": tag,
            "strict": bool(crit) and all(crit),
            "loose": round(loose, 4),
            "ref_loose": reference_correctness_loose(row["new_refs"], exp),
            "ref_strict": reference_correctness_strict(row["new_refs"], exp),
            "ref_conc": reference_conciseness(row["new_refs"], exp),
        }
        print(
            f"  {row['id']:<12} strict={int(row['rejudge']['strict'])} "
            f"loose={row['rejudge']['loose']:.2f} tone={int(judged['tone_pass'])}",
            flush=True,
        )
        return row

    print(f"judging {len(rows)} rows with {tag} ...")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        done = list(pool.map(run, rows))

    out_path.write_text(json.dumps({"judge": tag, "rows": done}, indent=2, ensure_ascii=False), encoding="utf-8")

    n = len(done)
    strict = sum(1 for r in done if r["rejudge"]["strict"])
    loose = sum(r["rejudge"]["loose"] for r in done) / n
    tone = sum(1 for r in done if r["rejudge"]["tone_pass"])
    print("\n" + "=" * 100)
    print(f"JUDGE {tag}   rows={n}")
    print(f"  strict (all criteria) : {strict}/{n} = {100.0 * strict / n:.1f}%")
    print(f"  loose  (criteria mean): {100.0 * loose:.2f}%")
    print(f"  tone pass             : {tone}/{n} = {100.0 * tone / n:.1f}%")

    print("\nSTILL-FAILING CRITERIA")
    for r in done:
        fails = [r["criteria"][i] for i, ok in enumerate(r["rejudge"]["criteria_results"]) if not ok]
        if not fails:
            continue
        print(f"\n[{r['id']}] {r['question'][:92]}")
        for c in fails:
            print(f"   FAIL: {c[:165]}")
    print(f"\nwrote {out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

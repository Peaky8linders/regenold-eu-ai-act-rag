"""R467 — re-ask the ten October 2026 expert-review questions on production.

The review (``Antifragile AI Oct 2026 expert review.txt``) graded the answers the
29 September report printed. This script asks the same ten questions, verbatim,
as single user turns against the DEPLOYED ask endpoint, sequentially (the
wrapper behind Stage-2 is one shared local process), and records for each:
answer, references, latency, the deployed commit, and the route's own trace
notes (which leg served Stage-2, or why Stage-2 was skipped).

The API key is read from ``.env`` and never printed.

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r467/expert_review_rerun.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
ASK = f"{BASE}/api/v1/regenold/eu-ai-act/ask"
UA = "regenold-r467-expert-rerun/1.0"

QUESTIONS: list[tuple[str, str]] = [
    ("Q45", "Under the EU AI Act, what must a provider of a high-risk AI system supply to the "
            "deployer in the instructions for use? List the required categories of information."),
    ("Q96", "Name the areas of high-risk use cases. Is healthcare decision making one of them?"),
    ("Q17", "Can the European Commission amend Annex III of the EU AI Act to add or modify "
            "use-cases classified as high-risk AI systems? Under what conditions?"),
    ("Q74", "I generated audio with AI for my artistic work (sole purpose). Do I need to provide "
            "some marking of its artificial nature? I feel that would compromise the enjoyment of "
            "the work."),
    ("Q95", "What is an 'area' and what is a 'use case' for high-risk as per Article 6(2)? How "
            "many areas exist?"),
    ("Q104", "What is Annex X about? What is it used for?"),
    ("Q6 (Case A)", "What are AI systems with minimal risks?"),
    ("Q10 (Case B)", "What is the difference between the deployer and the provider?"),
    ("Q16 (Case C)", "A pharmaceutical company wants to use an AI system to monitor the emotions "
                     "and stress levels of their manufacturing line workers to improve efficiency. "
                     "Is this allowed?"),
    ("Q17 (Case D)", "Is an AI system intended to be used as a safety component in robotic surgery "
                     "considered high-risk under the AI Act?"),
]


def _get(path: str, timeout: float = 150.0) -> dict:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _trace(body: dict) -> dict:
    """The route's reasoning trace, reduced to what says how the answer was made."""
    raw = body.get("reasoning")
    try:
        trace = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except ValueError:
        trace = {}
    if not isinstance(trace, dict):
        return {}
    notes = [n for n in trace.get("notes") or [] if isinstance(n, str)]
    served_by = next((n.split("stage2_served_by=", 1)[1].split()[0]
                      for n in notes if "stage2_served_by=" in n), "")
    model = next((n.split("stage2_model=", 1)[1].split()[0]
                  for n in notes if "stage2_model=" in n), "")
    skips = [n for n in notes if n.startswith("stage2_skipped")]
    return {
        "stage2_polish": trace.get("stage2_polish"),
        "stage2_served_by": served_by,
        "stage2_model": model,
        "stage2_skip_notes": skips,
        "retrieval_path": trace.get("retrieval_path"),
        "notes": notes,
    }


def ask(question: str, key: str, timeout: float = 240.0) -> tuple[dict, float]:
    body = json.dumps([{"role": "user", "content": question}]).encode("utf-8")
    req = urllib.request.Request(ASK, data=body, headers={
        "Content-Type": "application/json", "X-Regenold-Api-Key": key, "User-Agent": UA,
    })
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data, round(time.time() - t0, 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "expert_review_rerun.json"))
    args = ap.parse_args()

    key = dotenv_values(REPO / ".env").get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise SystemExit("P2P_REGENOLD_API_KEY missing from .env")

    health = _get("/healthz", 30)
    llm = _get("/healthz/llm")
    run = {
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "endpoint": ASK,
        "commit": health.get("commit"),
        "deployment_id": health.get("deployment_id"),
        "llm": {k: llm.get(k) for k in ("llm_ok", "provider", "model", "detail")},
        "rows": [],
    }
    print(f"commit={run['commit']} llm={run['llm']}", flush=True)
    for qid, question in QUESTIONS:
        try:
            data, latency = ask(question, key)
            row = {
                "id": qid,
                "question": question,
                "answer": data.get("answer"),
                "references": data.get("references"),
                "latency_s": latency,
                # Production's ``reasoning`` is a one-line summary, not the
                # JSON trace, so the route's own summary fields are kept too.
                "response_meta": {k: data.get(k) for k in (
                    "reasoning", "retrieval_path", "kb_version", "confidence")},
                "provenance": _trace(data),
            }
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            row = {"id": qid, "question": question, "error": repr(exc)[:300]}
        run["rows"].append(row)
        print(f"{qid}: {row.get('latency_s')}s refs={row.get('references')} "
              f"served_by={row.get('provenance', {}).get('stage2_served_by')!r} "
              f"skips={row.get('provenance', {}).get('stage2_skip_notes')} "
              f"err={row.get('error')}", flush=True)
    run["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    run["commit_after"] = _get("/healthz", 30).get("commit")
    Path(args.out).write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0 if all("error" not in r for r in run["rows"]) else 1


if __name__ == "__main__":
    sys.exit(main())

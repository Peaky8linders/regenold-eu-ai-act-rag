"""R472 — ask the predictive-policing questions on production, for the appendix's live examples.

Three single-turn requests, sequentially, to the deployed ask endpoint:

  * ``place_based``        a yes/no question on place-based predictive policing (the stored
                           ``predictive_policing`` answer's question family);
  * ``person_based``       the same question without the place qualifier;
  * ``amend_place_tools``  the R470 development row N17_t2: an Annex III amendment question
                           that names place-based tools, whose verdict used to open with an
                           Article 5(1)(d) sentence.

The API key comes from ``.env`` (the main checkout's, when a worktree has none) and is
never printed.

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r472/run_policing.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import run_live  # patches dotenv so a worktree finds the main checkout's key  # noqa: F401
from run_live import HERE, REPO, er

QUESTIONS = [
    ("place_based", "Is place-based predictive policing prohibited under the AI Act?"),
    ("person_based", "Is predictive policing prohibited under the AI Act?"),
    ("amend_place_tools",
     "If place-based predictive policing tools (forecasting where crime will happen rather than who will "
     "commit it) prove harmful, could the Commission bring them into Annex III by delegated act, and what "
     "has to happen before such an act takes effect?"),
]


def main() -> int:
    import dotenv

    key = dotenv.dotenv_values(REPO / ".env").get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise SystemExit("P2P_REGENOLD_API_KEY missing from .env")
    run = {"started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "commit": er._get("/healthz", 30).get("commit"), "rows": []}
    for rid, question in QUESTIONS:
        try:
            data, latency = er.ask(question, key)
            row = {"id": rid, "question": question, "answer": data.get("answer"),
                   "references": data.get("references"), "latency_s": latency}
        except Exception as exc:  # noqa: BLE001 - recorded, the build refuses a run with errors
            row = {"id": rid, "question": question, "error": repr(exc)[:300]}
        run["rows"].append(row)
        print(f"{rid}: {row.get('latency_s')}s refs={row.get('references')} err={row.get('error')}", flush=True)
    run["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    run["commit_after"] = er._get("/healthz", 30).get("commit")
    (HERE / "policing_live.json").write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0 if all("error" not in r for r in run["rows"]) else 1


if __name__ == "__main__":
    sys.exit(main())

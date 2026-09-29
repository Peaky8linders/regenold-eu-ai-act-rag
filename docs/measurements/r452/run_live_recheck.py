"""R452 post-deploy live re-check: the 6 official appendix cases and showcase Cases A-D.

Same protocol as the 2026-09-28 11:46 re-run (r448 worktree), run sequentially because
the wrapper is one shared process:

1. wait until production ``/healthz`` reports the expected commit;
2. ``run_official_batch`` on the 6 appendix ids, easy + hard, against production;
3. ``score_arm`` per mode (Bedrock qwen3-235b, 3 repeats, ``--no-deepen``: the
   references are production's wire output and are scored as shipped);
4. ``live_expert_recheck`` on Cases A-D (``--ids`` takes a SPACE-separated value;
   the 11:46 run passed ``--ids=...``, which the script ignores, and judged all 28).

Only credentials are read from ``.env`` (the partner API key and the Bedrock judge
credentials), and a variable already set in the shell wins. Behavioural flags in
``.env`` never reach the children, and ``REGENOLD_SKIP_DOTENV=1`` keeps the app from
loading them itself, so ``score_arm``'s re-deepen runs the code defaults production
runs. Outputs go to ``live/<label>/``. Any failed step makes the exit code non-zero.

    py -3.12 docs/measurements/r452/run_live_recheck.py <commit_prefix> [--label LABEL]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[3]
BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
ASK = f"{BASE}/api/v1/regenold/eu-ai-act/ask"
APPENDIX = "rg_046,rg_097,rg_018,rg_075,rg_096,rg_105"
SHOWCASE = "part1_q06,part1_q10,part1_q16,part1_q17"
JUDGE = ["--judge-provider", "bedrock", "--judge-model", "qwen.qwen3-235b-a22b-2507-v1:0"]
#: the only ``.env`` entries the children receive
CREDENTIALS = ("AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
               "AWS_SESSION_TOKEN", "AWS_REGION", "BEDROCK_REGION")

LIVE: Path = Path()


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with (LIVE / "run_live.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def env() -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if v is not None}
    dot = dotenv_values(REPO / ".env")
    for k in CREDENTIALS:
        if dot.get(k):
            e.setdefault(k, str(dot[k]))
    if not e.get("REGENOLD_API_KEY"):
        key = dot.get("P2P_REGENOLD_API_KEY") or ""
        if not key:
            raise SystemExit("P2P_REGENOLD_API_KEY missing from .env and REGENOLD_API_KEY unset")
        e["REGENOLD_API_KEY"] = str(key)
    e["PYTHONIOENCODING"] = "utf-8"
    e["REGENOLD_SKIP_DOTENV"] = "1"
    return e


def run(cmd: list[str], e: dict[str, str]) -> int:
    log("+ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(REPO), env=e).returncode


def main() -> int:
    global LIVE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("commit", help="commit prefix production must report on /healthz")
    ap.add_argument("--label", default="r452c-live")
    args = ap.parse_args()
    want = args.commit.strip()
    if len(want) < 7:
        raise SystemExit("give at least 7 characters of the commit")
    LIVE = Path(__file__).resolve().parent / "live" / args.label
    LIVE.mkdir(parents=True, exist_ok=True)
    e = env()
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=30) as r:
                commit = json.loads(r.read().decode("utf-8")).get("commit", "")
        except Exception as exc:  # noqa: BLE001
            commit = f"unreachable: {exc}"
        if str(commit).startswith(want):
            break
        log(f"production at {commit}, waiting for {want}")
        time.sleep(20)
    else:
        log("ERROR: production never reported the expected commit")
        return 2
    log(f"production at {commit}")

    failed: list[str] = []
    rc = run([sys.executable, "-m", "evals.regenold.run_official_batch", "--label", args.label,
              "--mode", "both", "--endpoint", ASK, "--ids", APPENDIX], e)
    log(f"run_official_batch exit={rc}")
    if rc != 0:
        return rc
    for mode in ("easy", "hard"):
        ckpt = REPO / "evals" / "bench" / "results" / f"official-{args.label}-{mode}.ckpt.jsonl"
        # --no-deepen: these are production's wire references, already through
        # the shipped deepener (with the curated and live-question guards the
        # offline re-deepen does not have).
        rc = run([sys.executable, "-m", "evals.official.score_arm", "--ckpt", str(ckpt),
                  "--label", args.label, "--mode", mode, "--repeats", "3", "--no-deepen", *JUDGE,
                  "--cache-file", str(LIVE / "judge-cache-live-bedrock.jsonl")], e)
        log(f"score_arm {mode} exit={rc}")
        if rc != 0:
            failed.append(f"score_arm {mode}")
    rc = run([sys.executable, str(REPO / "docs" / "measurements" / "r447" / "live_expert_recheck.py"),
              "--ids", SHOWCASE, f"--out={LIVE / 'showcase_live.json'}"], e)
    log(f"live_expert_recheck exit={rc}")
    if rc != 0:
        failed.append("live_expert_recheck")
    if failed:
        log(f"FAILED steps: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

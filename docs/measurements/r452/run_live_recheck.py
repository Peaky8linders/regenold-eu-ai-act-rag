"""R452 post-deploy live re-check: the 6 official appendix cases and showcase Cases A-D.

Same protocol as the 2026-09-28 11:46 re-run (r448 worktree), run sequentially because
the wrapper is one shared process:

1. wait until production ``/healthz`` reports the expected commit;
2. ``run_official_batch`` on the 6 appendix ids, easy + hard, against production;
3. ``score_arm`` per mode (Bedrock qwen3-235b, 3 repeats);
4. ``live_expert_recheck`` on Cases A-D (``--ids`` takes a SPACE-separated value;
   the 11:46 run passed ``--ids=...``, which the script ignores, and judged all 28).

The API key is read from ``.env`` and passed only through the child environment.

    py -3.12 docs/measurements/r452/run_live_recheck.py <commit_prefix>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[3]
LIVE = Path(__file__).resolve().parent / "live"
LIVE.mkdir(parents=True, exist_ok=True)
BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
ASK = f"{BASE}/api/v1/regenold/eu-ai-act/ask"
LABEL = "r452-live"
APPENDIX = "rg_046,rg_097,rg_018,rg_075,rg_096,rg_105"
SHOWCASE = "part1_q06,part1_q10,part1_q16,part1_q17"
JUDGE = ["--judge-provider", "bedrock", "--judge-model", "qwen.qwen3-235b-a22b-2507-v1:0"]


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with (LIVE / "run_live.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def env() -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if v is not None}
    dot = dotenv_values(REPO / ".env")
    for k, v in dot.items():
        if v:
            e[str(k)] = str(v)
    key = dot.get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise SystemExit("P2P_REGENOLD_API_KEY missing from .env")
    e["REGENOLD_API_KEY"] = str(key)
    e["PYTHONIOENCODING"] = "utf-8"
    e.pop("REGENOLD_SKIP_DOTENV", None)
    return e


def run(cmd: list[str], e: dict[str, str]) -> int:
    log("+ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(REPO), env=e).returncode


def main() -> int:
    want = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    e = env()
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=30) as r:
                commit = json.loads(r.read().decode("utf-8")).get("commit", "")
        except Exception as exc:  # noqa: BLE001
            commit = f"unreachable: {exc}"
        if want and str(commit).startswith(want):
            break
        log(f"production at {commit}, waiting for {want}")
        time.sleep(20)
    else:
        log("ERROR: production never reported the expected commit")
        return 2
    log(f"production at {commit}")

    rc = run([sys.executable, "-m", "evals.regenold.run_official_batch", "--label", LABEL,
              "--mode", "both", "--endpoint", ASK, "--ids", APPENDIX], e)
    log(f"run_official_batch exit={rc}")
    if rc != 0:
        return rc
    for mode in ("easy", "hard"):
        ckpt = REPO / "evals" / "bench" / "results" / f"official-{LABEL}-{mode}.ckpt.jsonl"
        rc = run([sys.executable, "-m", "evals.official.score_arm", "--ckpt", str(ckpt), "--label", LABEL,
                  "--mode", mode, "--repeats", "3", *JUDGE,
                  "--cache-file", str(LIVE / "judge-cache-live-bedrock.jsonl")], e)
        log(f"score_arm {mode} exit={rc}")
    rc = run([sys.executable, str(REPO / "docs" / "measurements" / "r447" / "live_expert_recheck.py"),
              "--ids", SHOWCASE, f"--out={LIVE / 'showcase_live.json'}"], e)
    log(f"live_expert_recheck exit={rc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

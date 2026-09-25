"""Post-deploy live re-check of production, run sequentially.

The steps are sequential because the wrapper is one shared local process.

1. Wait until production ``/healthz`` reports the expected commit and
   ``/healthz/llm`` reports ``llm_ok`` on ``claude-opus-5-5``.
2. The 6 official appendix cases, easy + hard, via ``run_official_batch``
   against the production endpoint, then ``score_arm`` per mode (Bedrock
   Qwen3-235B judge, 3 repeats). This is the R446 protocol.
3. The 28 expert-review rows via ``live_expert_recheck.py`` (same judge,
   3-vote majority).
4. Wire-only probes of the phrasings the R447 reviews used.

The API key is read from ``.env`` and passed only through the child
environment. It is never printed. Outputs go to ``docs/measurements/r447/live/``.

Usage (from the repo root):
    .venv/Scripts/python.exe docs/measurements/r447/run_live_recheck.py <commit_prefix>
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
HERE = Path(__file__).resolve().parent
LIVE = HERE / "live"
BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
ASK = f"{BASE}/api/v1/regenold/eu-ai-act/ask"
LABEL = "r447-live"
APPENDIX = "rg_046,rg_097,rg_018,rg_075,rg_096,rg_105"
JUDGE = ["--judge-provider", "bedrock", "--judge-model", "qwen.qwen3-235b-a22b-2507-v1:0"]
PROBES = {
    "compound_q04": "We are both a provider and a deployer of a chatbot. How must a natural "
    "person be informed that they are interacting with an AI system?",
    "scenario_q04": "We are both a provider and a deployer of a chatbot used by our bank. "
    "What is its risk classification? How must a natural person be informed that they "
    "are interacting with an AI system?",
    "part1_q10": "What is the difference between the deployer and the provider?",
}


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with (LIVE / "run_live.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def get_json(url: str, timeout: float = 60.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_deploy(prefix: str) -> None:
    for attempt in range(90):
        try:
            commit = str(get_json(f"{BASE}/healthz", 20).get("commit") or "")
        except Exception as exc:  # noqa: BLE001
            commit = f"error {exc}"
        if commit.startswith(prefix):
            llm = get_json(f"{BASE}/healthz/llm", 120)
            log(f"deployed commit={commit} llm_ok={llm.get('llm_ok')} model={llm.get('model')}")
            if not llm.get("llm_ok") or llm.get("model") != "claude-opus-5-5":
                raise SystemExit("healthz/llm is not healthy on claude-opus-5-5; stopping")
            return
        if attempt % 6 == 0:
            log(f"waiting for {prefix}: production reports {commit}")
        time.sleep(20)
    raise SystemExit(f"production never reported {prefix}")


def child_env() -> dict:
    env = dict(os.environ)
    key = dotenv_values(REPO / ".env").get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise SystemExit("P2P_REGENOLD_API_KEY missing from .env")
    env["REGENOLD_API_KEY"] = key
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("REGENOLD_SKIP_DOTENV", None)
    return env


def run(cmd: list[str], env: dict) -> int:
    log("+ " + " ".join(cmd))
    return subprocess.call(cmd, cwd=str(REPO), env=env)


def probe_wire(env: dict) -> None:
    out = {}
    for name, question in PROBES.items():
        body = json.dumps([{"role": "user", "content": question}]).encode("utf-8")
        req = urllib.request.Request(ASK, data=body, headers={
            "Content-Type": "application/json", "X-Regenold-Api-Key": env["REGENOLD_API_KEY"],
        })
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out[name] = {
            "references": data.get("references"),
            "chars": len(data.get("answer") or ""),
            "latency_s": round(time.time() - t0, 1),
            "answer": data.get("answer"),
        }
        log(f"probe {name}: {out[name]['latency_s']}s chars={out[name]['chars']} "
            f"refs={out[name]['references']}")
    (LIVE / "probe_wire.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )


def main() -> int:
    LIVE.mkdir(parents=True, exist_ok=True)
    wait_for_deploy(sys.argv[1])
    env = child_env()
    rc = run([sys.executable, "-m", "evals.regenold.run_official_batch", "--label", LABEL,
              "--mode", "both", "--endpoint", ASK, "--ids", APPENDIX], env)
    log(f"run_official_batch exit={rc}")
    for mode in ("easy", "hard"):
        ckpt = REPO / "evals" / "bench" / "results" / f"official-{LABEL}-{mode}.ckpt.jsonl"
        rc = run([sys.executable, "-m", "evals.official.score_arm", "--ckpt", str(ckpt),
                  "--label", LABEL, "--mode", mode, "--repeats", "3", *JUDGE,
                  "--cache-file", str(LIVE / "judge-cache-live-bedrock.jsonl")], env)
        log(f"score_arm {mode} exit={rc}")
    rc = run([sys.executable, str(HERE / "live_expert_recheck.py")], env)
    log(f"live_expert_recheck exit={rc}")
    probe_wire(env)
    log("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

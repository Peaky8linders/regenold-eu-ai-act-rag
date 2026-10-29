"""R473 — re-ask the ten reviewed questions on the build production serves today.

The concise appendix of 29 October 2026 (``build_appendix.py`` in this directory) quotes
the live answers, so it needs a fresh run on the deployed endpoint, strictly one request
after another, and an offline replay of the same ten with no model reachable:

  expert_review_rerun.json   the ten reviewed questions, live
  offline_wire_replay.json   the same ten, replayed offline

It reuses the R467 scripts. The API key comes from ``.env``; a worktree has none, so the
main checkout's is used. It is never printed.

Usage (repo root):
    <main checkout>/.venv/Scripts/python.exe docs/measurements/r473/run_live.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import dotenv

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R467 = REPO / "docs" / "measurements" / "r467"


def _main_checkout_env() -> Path | None:
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                         cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()
    env = Path(out).parent / ".env" if out else None
    return env if env and env.exists() else None


_real_values = dotenv.dotenv_values


def _values(path=None, *args, **kwargs):
    values = _real_values(path, *args, **kwargs)
    if not values.get("P2P_REGENOLD_API_KEY"):
        env = _main_checkout_env()
        if env is not None:
            values = _real_values(env, *args, **kwargs)
    return values


dotenv.dotenv_values = _values  # before the r467 module imports it

sys.path.insert(0, str(R467))
import expert_review_rerun as er  # noqa: E402


def main() -> int:
    live = HERE / "expert_review_rerun.json"
    sys.argv = ["expert_review_rerun", "--out", str(live)]
    print("== the ten reviewed questions", flush=True)
    if er.main() != 0:
        return 1
    print("== offline replay", flush=True)
    subprocess.run([sys.executable, str(R467 / "offline_wire_replay.py"), str(live),
                    str(HERE / "offline_wire_replay.json")], cwd=REPO, check=True)
    print("== done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

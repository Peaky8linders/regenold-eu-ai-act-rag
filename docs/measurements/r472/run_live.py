"""R472 — re-run the expert-review appendix's live sets on the build production serves now.

The October appendix (``docs/measurements/r467``) is generated from stored runs. This
asks the same three sets again on the deployed endpoint, strictly one after another
(the wrapper behind Stage-2 is one shared local process), replays them with no model
reachable, and grades the held-out answers:

  expert_review_rerun.json   the ten reviewed questions
  paraphrase_rerun.json      the 30 remediation rephrasings
  heldout.json               the 20 held-out rephrasings
  offline_wire_replay.json   the ten, replayed offline
  heldout_judged.json        the held-out answers, graded (claude-sonnet-5, wrapper)

The API key comes from ``.env``; a worktree has none, so the main checkout's is used.
It is never printed. A grade already on disk for a byte-identical answer is kept
(``heldout_judge.py`` does that), so the judge is seeded with the October grades.

Usage (repo root, wrapper on 127.0.0.1:8000):
    .venv/Scripts/python.exe docs/measurements/r472/run_live.py [--skip-judge]
"""
from __future__ import annotations

import argparse
import shutil
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


dotenv.dotenv_values = _values  # before the r467 modules import it

sys.path.insert(0, str(R467))
import expert_review_rerun as er  # noqa: E402
import heldout_rerun as hr  # noqa: E402
import paraphrase_rerun as pr  # noqa: E402


def _offline(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(R467 / script), *args], cwd=REPO, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-judge", action="store_true")
    args = ap.parse_args()

    sys.argv = ["expert_review_rerun", "--out", str(HERE / "expert_review_rerun.json")]
    print("== the ten reviewed questions", flush=True)
    if er.main() != 0:
        return 1
    print("== the 30 remediation rephrasings", flush=True)
    if pr.live(HERE / "paraphrase_rerun.json") != 0:
        return 1
    print("== the 20 held-out rephrasings", flush=True)
    if hr.live(HERE / "heldout.json") != 0:
        return 1

    print("== offline replays", flush=True)
    _offline("offline_wire_replay.py", str(HERE / "expert_review_rerun.json"),
             str(HERE / "offline_wire_replay.json"))
    _offline("paraphrase_rerun.py", "--offline", "--out", str(HERE / "paraphrase_rerun.json"))
    _offline("heldout_rerun.py", "--offline", "--out", str(HERE / "heldout.json"))

    if not args.skip_judge:
        print("== held-out grades", flush=True)
        judged = HERE / "heldout_judged.json"
        if not judged.exists():
            shutil.copyfile(R467 / "heldout_r467c_judged.json", judged)
        _offline("heldout_judge.py", str(HERE / "heldout.json"), str(judged))
    print("== done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

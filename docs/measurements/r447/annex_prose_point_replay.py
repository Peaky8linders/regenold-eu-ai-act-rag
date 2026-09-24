"""R447 (R446 review F5) — the grain deepener's prose-named annex point, three arms.

Replays ``_deepen_one_ref`` for every annex head a recorded row cited, over every
recorded (question, answer) in ``docs/measurements/r388/score-*.json``, for:

* ``pre``     — ``3f3df41``, before #462 (R399's "first usable mention wins");
* ``shipped`` — ``a0b08c8``, #462's first-mention-stops rule for EVERY annex;
* ``tree``    — this working tree: first-mention-stops for Annex I only.

Each changed coordinate is scored with the official rubric's Ref. Strict against
the reconstructed refkey. Offline, deterministic, no network.

Run from the repo root:
  .venv/Scripts/python.exe docs/measurements/r447/annex_prose_point_replay.py
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, os.getcwd())

from app.routes import regenold as TREE  # noqa: E402
from evals.official.rubric import reference_correctness_strict as strict  # noqa: E402


def _at(rev: str, name: str):
    text = subprocess.check_output(
        ["git", "show", f"{rev}:app/routes/regenold.py"], text=True, encoding="utf-8"
    )
    path = Path(tempfile.mkdtemp()) / f"{name}.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ARMS = {"pre": _at("3f3df41", "regenold_pre462"), "shipped": _at("a0b08c8", "regenold_shipped"),
        "tree": TREE}
key = {
    json.loads(line)["id"]: json.loads(line)["expected"]
    for line in open("docs/measurements/r388/official_refkey_n110.jsonl", encoding="utf-8")
}
head_re = re.compile(r"^(Annex [IVX]+)(?:\.|$)")
replays: Counter = Counter()
moved: Counter = Counter()
lines: list[str] = []
seen: set = set()
for path in sorted(glob.glob("docs/measurements/r388/score-*.json")):
    try:
        rows = json.load(open(path, encoding="utf-8")).get("rows") or []
    except Exception:  # noqa: BLE001 — a malformed artefact is skipped, not fatal
        continue
    for row in rows:
        q, a = row.get("question") or "", row.get("answer") or ""
        if not q or not a:
            continue
        heads = {m.group(1) for r in (row.get("refs") or []) if (m := head_re.match(str(r)))}
        for head in sorted(heads):
            sig = (row["id"], head, a)
            if sig in seen:
                continue
            seen.add(sig)
            out = {arm: mod._deepen_one_ref(head, q, a) for arm, mod in ARMS.items()}
            replays[head] += 1
            for left, right in (("pre", "shipped"), ("shipped", "tree"), ("pre", "tree")):
                if out[left] != out[right]:
                    moved[(head, left, right)] += 1
            if len(set(out.values())) > 1:
                exp = key.get(row["id"]) or []
                scores = {arm: strict([ref], exp) for arm, ref in out.items()}
                lines.append(
                    f"  {row['id']} {head}: pre={out['pre']} shipped={out['shipped']} "
                    f"tree={out['tree']} strict={scores} gold={exp}"
                )
print("replays per annex head:", dict(sorted(replays.items())))
for (head, left, right), n in sorted(moved.items()):
    print(f"  {head}: {left} != {right} on {n}")
print("\nrows where any arm differs:")
print("\n".join(lines) or "  none")

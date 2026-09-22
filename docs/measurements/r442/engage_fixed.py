"""R442 — answer_need on the route's REAL inputs for the official 110:
pre-R439 (c74ca99) vs R439 (1aa09b8) vs the working tree. Offline; sockets blocked.

Run from the repo root:
  .venv/Scripts/python.exe docs/measurements/r442/engage_fixed.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import route_capture as rc  # noqa: E402,F401  (offline env, socket block, chdir)

import app.engines.answer_need as fixed  # noqa: E402


def _at(rev: str, name: str):
    text = subprocess.check_output(["git", "show", f"{rev}:app/engines/answer_need.py"], text=True, encoding="utf-8")
    path = Path(tempfile.mkdtemp()) / f"{name}.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MODS = {"pre_r439": _at("c74ca99", "an_pre"), "r439": _at("1aa09b8", "an_r439"), "fixed": fixed}
print("TARGETED  (engaged / target chars):")
for q, refs in [
    ("Does Article 26 require the deployer to keep logs?", "Article 26"),
    ("Does Article 26(6) require the deployer to keep logs?", "Article 26"),
    ("When does the Article 6(3) derogation apply?", "Article 6"),
    ("What does Article 9(2) require?", "Article 9"),
    ("What is Annex X about? What is it used for?", "Annex X"),
]:
    print(f"  {q[:58]:58} " + "  ".join(
        f"{k}:{len(m.engaged_coords(q, refs)):>2}/{m.answer_need(q, refs).target_chars}" for k, m in MODS.items()))

RECORD: list[tuple[str, str]] = []
_real = fixed.answer_need


def _rec(question, references=""):
    RECORD.append((question, references))
    return _real(question, references)


fixed.answer_need = _rec
rows = [json.loads(line) for line in open("docs/measurements/r388/official_gold_n110.jsonl", encoding="utf-8")]
per_row = {}
for r in rows:
    start = len(RECORD)
    rc.ask([{"role": "user", "content": r["question"]}], {})
    per_row[r["id"]] = RECORD[start:]
fixed.answer_need = _real
changed = 0
for rid, recs in per_row.items():
    for idx, (q, refs) in enumerate(recs):
        a, b = MODS["r439"].answer_need(q, refs), fixed.answer_need(q, refs)
        if (a.engaged, a.target_chars, a.items) != (b.engaged, b.target_chars, b.items):
            changed += 1
            role = "answer-shape" if idx == len(recs) - 1 else "skeleton-scope"
            print(f"  CHANGED {rid} [{role}]: engaged {len(a.engaged)}->{len(b.engaged)} target {a.target_chars}->{b.target_chars}")
print(f"calls compared: {sum(len(v) for v in per_row.values())}; changed vs R439: {changed}")
print("socket connect attempts:", len(rc.SOCKET_ATTEMPTS))

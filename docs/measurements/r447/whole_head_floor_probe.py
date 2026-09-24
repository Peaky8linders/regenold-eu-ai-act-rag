"""R447 — the R442 whole-head floor, before vs after scoping it to asks ABOUT a head.

Records every ``answer_need`` call the REAL route makes (offline, Stage-2 stubbed
to land, sockets blocked; see ``docs/measurements/r442/route_capture.py``) and
re-scores each recorded (question, references) pair with the shipped module
(``a0b08c8``) and with this tree's module.

Run from the repo root:
  .venv/Scripts/python.exe docs/measurements/r447/whole_head_floor_probe.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "r442"))
import route_capture as rc  # noqa: E402  (offline env, socket block, chdir)

import app.engines.answer_need as new  # noqa: E402

BASE_REV = "a0b08c8"


def _at(rev: str, name: str):
    text = subprocess.check_output(
        ["git", "show", f"{rev}:app/engines/answer_need.py"], text=True, encoding="utf-8"
    )
    path = Path(tempfile.mkdtemp()) / f"{name}.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


base = _at(BASE_REV, "an_base")

RECORD: list[tuple[str, str]] = []
_real = new.answer_need


def _rec(question, references=""):
    RECORD.append((question, references))
    return _real(question, references)


def corpus() -> list[tuple[str, list[dict]]]:
    rows = [
        json.loads(line)
        for line in open("docs/measurements/r388/official_gold_n110.jsonl", encoding="utf-8")
    ]
    out = [(r["id"], [{"role": "user", "content": r["question"]}]) for r in rows]
    from evals.harness.probe_set import load_probe_set  # noqa: PLC0415

    out += [(p.id, [dict(m) for m in p.messages]) for p in load_probe_set()]
    return out


new.answer_need = _rec
per_row: dict[str, list[tuple[str, str]]] = {}
for rid, messages in corpus():
    start = len(RECORD)
    rc.ask(messages, {})
    per_row[rid] = RECORD[start:]
new.answer_need = _real

calls = changed = 0
for rid, recs in per_row.items():
    for idx, (q, refs) in enumerate(recs):
        calls += 1
        a, b = base.answer_need(q, refs), new.answer_need(q, refs)
        if (a.engaged, a.target_chars, a.items) != (b.engaged, b.target_chars, b.items):
            changed += 1
            role = "answer-shape" if idx == len(recs) - 1 else "skeleton-scope"
            ask = new._ask_text(q).replace("\n", " ")
            print(
                f"CHANGED {rid} [{role}] target {a.target_chars}->{b.target_chars}"
                f" items {a.items}->{b.items} :: {ask[:150]}"
            )
print(f"rows: {len(per_row)}; answer_need calls: {calls}; changed: {changed}")
print("socket connect attempts:", len(rc.SOCKET_ATTEMPTS))

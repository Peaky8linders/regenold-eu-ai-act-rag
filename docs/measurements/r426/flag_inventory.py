"""R426 — the flag inventory: how much of the monsters is configurable behaviour?

WHY. `app/routes/regenold.py` (12.8 kLOC) and `app/engines/_graph_rag_impl.py`
(12.9 kLOC) are large partly because almost every behaviour on the critical path
is behind a `REGENOLD_*` switch. That is not automatically bad — it is how this
repo gates changes — but a switch that a measurement round has already REJECTED is
not a switch any more: it is a branch nobody may ever take, plus the code it
guards, plus the documentation that explains it. That is measurable debt.

WHAT IT REPORTS

1. every `REGENOLD_*` name actually READ (`os.getenv`/`_flag_is_on`-style) in a
   target module, with its literal default when there is one;
2. which of those CLAUDE.md documents with a rejection-family verdict
   (`REJECTED`, `KEEP OFF`, `HOLD AT OFF`, `GATED, THEN REJECTED`, …);
3. which are read but documented nowhere — the opposite risk.

Grep-based (`ast` cannot see an f-string flag name), so it deliberately scans the
raw text and reports the file:line of the read.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r426.flag_inventory
    .venv\\Scripts\\python.exe -m docs.measurements.r426.flag_inventory --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
TARGETS = ("app/routes/regenold.py", "app/engines/_graph_rag_impl.py")
CLAUDE = REPO / "CLAUDE.md"

#: ``os.getenv("REGENOLD_X", "1")`` / ``os.environ.get(...)`` / ``_env_flag(...)``.
READ_RE = re.compile(
    r'(?:getenv|environ\.get|_flag_is_on|_env_bool|_flag_on)\s*\(\s*'
    r'["\'](REGENOLD_[A-Z0-9_]+)["\']\s*(?:,\s*["\']?([^"\',)]*)["\']?\s*)?\)'
)
#: Documented-with-a-rejection verdict. The table rows in CLAUDE.md are the
#: authoritative record of what a round CONCLUDED about a lever.
REJECTED_RE = re.compile(
    r"REJECTED|KEEP OFF|HOLD AT OFF|GATED, THEN REJECTED|do not flip|"
    r"do not re-propose|verdict.{0,40}\bOFF\b|permanently OFF",
    re.IGNORECASE,
)


def _claude_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    text = CLAUDE.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = re.match(r"\|\s*`(REGENOLD_[A-Z0-9_]+)`\s*\|(.+)", line)
        if m:
            rows.setdefault(m.group(1), m.group(2))
        for name in re.findall(r"`(REGENOLD_[A-Z0-9_]+)`", line):
            rows.setdefault(name, line)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    documented = _claude_rows()
    report: dict[str, Any] = {"targets": {}, "totals": {}}
    all_read: dict[str, list[str]] = {}
    defaults: dict[str, str] = {}

    for rel in TARGETS:
        path = REPO / rel
        text = path.read_text(encoding="utf-8", errors="replace")
        hits: dict[str, list[str]] = {}
        for m in READ_RE.finditer(text):
            name = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            hits.setdefault(name, []).append(f"{rel}:{line}")
            if m.group(2) is not None and name not in defaults:
                defaults[name] = m.group(2)
        all_read.update({k: v for k, v in hits.items() if k not in all_read})
        report["targets"][rel] = {"read": len(hits)}

    rejected = sorted(n for n in all_read if n in documented and REJECTED_RE.search(documented[n]))
    undocumented = sorted(n for n in all_read if n not in documented)
    report["totals"] = {
        "flags_read": len(all_read),
        "with_literal_default": len(defaults),
        "documented": len(all_read) - len(undocumented),
        "documented_as_rejected": len(rejected),
        "undocumented": len(undocumented),
    }
    report["rejected"] = rejected
    report["undocumented"] = undocumented
    report["defaults"] = defaults

    print("=" * 88)
    print("R426 — REGENOLD_* flag inventory for the two monsters")
    print("=" * 88)
    for rel, d in report["targets"].items():
        print(f"  {rel:<44} {d['read']:>4} flags read")
    t = report["totals"]
    print(
        f"\n  distinct flags read: {t['flags_read']}   "
        f"with a literal default: {t['with_literal_default']}   "
        f"documented in CLAUDE.md: {t['documented']}"
    )
    print(f"  documented as REJECTED / KEEP OFF / HOLD AT OFF: {t['documented_as_rejected']}")
    print(f"  read but documented NOWHERE: {t['undocumented']}")
    print("\n-- documented-as-rejected (candidate levers to retire WITH their code) --")
    for name in rejected:
        print(f"  {name}")
    print("\n-- read but undocumented --")
    for name in undocumented:
        print(f"  {name}")
    if args.json:
        out = Path(__file__).resolve().parent / "flag_inventory.json"
        out.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

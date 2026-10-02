"""R461.6 docs applier - the CHECKPOINT entry and the audit doc pointer.

Idempotent: each target checks its own marker first. Run from the worktree
root:

    python docs/measurements/r461/apply_r461_6_docs.py
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LF = chr(10)
CRLF = chr(13) + chr(10)


def _write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def append_block(path: str, marker: str, block: str) -> None:
    p = REPO / path
    raw = open(p, encoding="utf-8", newline="").read()
    if marker in raw:
        print("already applied:", path)
        return
    nl = CRLF if CRLF in raw else LF
    _write(p, raw.rstrip() + nl + nl + block.replace(LF, nl) + nl)
    print("applied:", path)


def insert_after(path: str, anchor: str, note: str) -> None:
    p = REPO / path
    raw = open(p, encoding="utf-8", newline="").read()
    nl = CRLF if CRLF in raw else LF
    anchor_nl = anchor.replace(LF, nl)
    note_nl = note.replace(LF, nl)
    if note_nl in raw:
        print("already applied:", path)
        return
    found = raw.count(anchor_nl)
    assert found == 1, (path, found)
    _write(p, raw.replace(anchor_nl, anchor_nl + note_nl, 1))
    print("applied:", path)


CHECKPOINT_ENTRY = """## 2026-10-02 (R461.6 — the scope decision's evidence now rides in the record)

The R461.4 audit's own finding, closed: per-row provenance lived only in the
gitignored checkpoints, so a published refusal's scope question died with the
file (r403's three VETOs are unanswerable forever). Every new read now embeds
`veto.roster` — per arm, the row-id to reason map it was decided on, the
considered row set, and the checkpoint it came from — and the audit falls back
to it when the file is gone. A live checkpoint always wins; a read published
before the capture stays exactly as auditable as it was, and its absence is
still reported as UNVERIFIABLE. `gate-verdict-audit.json` re-runs
byte-identical; the canonical R461 read was regenerated with the capture
attached (the roster block is the only change; every number equal); 6 tests.
"""

AUDIT_POINTER = """
Implemented in R461.6: reads published since carry the captured roster
(`veto.roster`) and the audit falls back to it when the checkpoint is gone —
see `CAPTURED-ROSTER.md`. The eight verdicts above predate the capture and
remain unauditable: the fix is prospective, not a recovery.
"""

append_block("docs/measurements/r460/CHECKPOINT.md", "R461.6 — the scope decision's evidence", CHECKPOINT_ENTRY)

insert_after(
    "docs/measurements/r461/GATE-VERDICT-AUDIT.md",
    "audit: embed the CAPTURED roster in the veto block, so a future vision of the\nrule can be re-applied to an old verdict without the checkpoint.\n",
    AUDIT_POINTER,
)

print("done")

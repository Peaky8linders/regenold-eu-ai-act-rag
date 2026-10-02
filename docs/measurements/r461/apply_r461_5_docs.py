"""R461.5 docs applier - the CHECKPOINT entry and the R461.3 doc pointer.

Idempotent: each target checks its own marker first. Run from the worktree
root:

    python docs/measurements/r461/apply_r461_5_docs.py
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


CHECKPOINT_ENTRY = """## 2026-10-02 (R461.5 — one shared row-provenance predicate for every gate)

The last three rounds each taught a gate to read the same checkpoint fields its
own way: rule #8's row eligibility, the R422 void guard, the R423 exclusion
list, the resume census. Read three ways, the same row could narrow a veto on
one gate and widen an exclusion on another without either gate saying so. The
reading now lives in ONE leaf module (`evals/bench/row_provenance.py`), with the
gate names kept as aliases and asserted identical by `is`.

* The asymmetries are the design, not accidents, and each is pinned: a
  `fallback` row is lever evidence for rule #8 AND a degraded transport for R423
  (same payload, different question); a curated intercept is an R422 draft and
  NOT an R423 degradation; a leg name the vocabulary does not know is a serve
  for rule #8 (no silent exemption) and non-primary for R423.
* The raw fields now have one home: an AST scan over `evals/**/*.py` fails on
  any other module that reads `stage2_served_by` / `stage2_polish`, allowlisting
  only the named producer / monitor / report functions, and the allowlist itself
  is tested for staleness.
* Preservation, measured: the old readers are carried verbatim as an oracle and
  match on every shape and on all 378 rows of the 16 checkpoints on disk; the
  gate-verdict audit re-runs BYTE-IDENTICAL (`gate-verdict-audit.json`, md5
  091103ee); the draw-stable re-read reproduces every number (artifact
  regenerated for the digest-is-shape wording that post-dated its first write).
  Full suite 27 failed / 9226 passed, the 27 being the known davidath-egress
  environment failures.
* One deliberate divergence: a present-but-falsy leg value (`0`/`False`) now
  lands in the R423 exclusion list (it used to be skipped); rule #8's reading is
  unchanged and no on-disk row carries one.
* `PROVENANCE-UNIFICATION.md`; 11 tests. Nothing committed yet (R461.2-5 all in
  the working tree).
"""

DRAW_STABLE_NOTE = """
R461.5 note: the row-provenance reading this instrument was built on now lives
in `evals/bench/row_provenance.py` (see `PROVENANCE-UNIFICATION.md`). Re-running
the one-draw read under that change reproduced every number and verdict; the
artifact above was regenerated only to pick up the R461.4 digest-is-shape
wording, which post-dated its first write.
"""

append_block("docs/measurements/r460/CHECKPOINT.md", "R461.5 — one shared row-provenance predicate", CHECKPOINT_ENTRY)

insert_after(
    "docs/measurements/r461/DRAW-STABLE-RULE8.md",
    "Appliers are idempotent **within their own change**; re-running an earlier one\nafter a later one has touched the same region is a hard error by design\n(it reports the missing anchor, it does not duplicate an edit).\n",
    DRAW_STABLE_NOTE,
)

print("done")

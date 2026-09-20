"""R425 — stage ONLY my hunks of a file a concurrent editor is also editing.

THE PROBLEM THIS SOLVES. `app/routes/regenold.py` in the shared checkout contains
two independent, uncommitted feature sets: this round's prose-grounded wire grain
and another thread's ontology citable expansion. Committing the file wholesale
would ship their in-flight, un-reviewed work; `git apply --cached` of a
hand-selected patch mis-applied here (the index blob came out 293 lines short of
the working tree), so the staged artifact is built explicitly instead:

    committed = HEAD blob  +  my insertion hunks, in original line order

Every hunk of this round is a pure INSERTION (``@@ -X,0 +Y,N @@``), which is what
makes the reconstruction exact: insert N lines after original line X. The result
is written as a blob with ``git hash-object -w`` and pointed at by
``git update-index --cacheinfo`` — the index gets my artifact, the WORKING TREE is
never touched, and the concurrent editor's edits stay exactly where they are.

The script refuses to claim success unless the reconstruction differs from HEAD by
exactly the hunks it was given.

Usage::

    .venv\\Scripts\\python.exe docs/measurements/r425/stage_my_hunks.py [--apply]

Without ``--apply`` it verifies and reports; with it, it stages the blob.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TARGET = "app/routes/regenold.py"
#: The hunks of THIS round, by their original start line in HEAD (0 = insertion
#: after that line). Every one must be a pure insertion.
MINE_ANCHORS = (1421, 4376, 5793, 12350)
#: Markers that must be ABSENT: they belong to the other thread's feature.
FOREIGN_MARKERS = (
    "ONTOLOGY_CITABLE_EXPANSION",
    "_expand_citable_bases_with_ontology",
    "_ontology_citable_expansion_enabled",
)
#: Markers that must be PRESENT: the work being shipped.
OWN_MARKERS = (
    "REGENOLD_GROUND_WIRE_SUBPOINTS",
    "def _ground_wire_subpoints",
    "_GROUND_PROSE_DOTTED_RE",
    "wire_grain_grounded",
)


def _git(*args: str) -> str:
    """git, decoded as UTF-8.

    NOT ``text=True``: that decodes with the Windows locale codec (cp1252),
    which raises inside subprocess's reader thread on this file's em dashes —
    the exception is swallowed and ``stdout`` comes back ``None``.
    """
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, check=True)
    return out.stdout.decode("utf-8")


def _head_lines() -> list[str]:
    return _git("show", f"HEAD:{TARGET}").split("\n")


def _hunks() -> list[tuple[int, int, list[str]]]:
    """``(start_line, added_count, added_lines)`` for every insertion in the diff."""
    diff = _git("diff", "-U0", "--", TARGET)
    hunks: list[tuple[int, int, list[str]]] = []
    start: int | None = None
    added: list[str] = []
    for line in diff.split("\n"):
        m = re.match(r"^@@ -(\d+),(\d+) \+\d+(?:,\d+)? @@", line)
        if m:
            if start is not None:
                hunks.append((start, len(added), added))
            if int(m.group(2)) != 0:
                raise SystemExit(
                    f"hunk at -{m.group(1)} is not a pure insertion (deletes "
                    f"{m.group(2)} lines); this script only handles insertions"
                )
            start = int(m.group(1))
            added = []
            continue
        if start is None or not line.startswith("+"):
            continue
        if line.startswith("+++"):
            continue
        added.append(line[1:])
    if start is not None:
        hunks.append((start, len(added), added))
    return hunks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="stage the blob")
    args = ap.parse_args()

    hunks = _hunks()
    mine = [h for h in hunks if h[0] in MINE_ANCHORS]
    foreign = [h for h in hunks if h[0] not in MINE_ANCHORS]
    print(f"insertion hunks in the working diff: {len(hunks)}")
    print(f"  mine   : {[h[0] for h in mine]} ({sum(h[1] for h in mine)} lines)")
    print(f"  foreign: {[h[0] for h in foreign]} ({sum(h[1] for h in foreign)} lines)")
    missing = set(MINE_ANCHORS) - {h[0] for h in mine}
    if missing:
        raise SystemExit(f"expected hunks not found in the diff: {sorted(missing)}")

    head = _head_lines()
    if head and head[-1] == "":
        head = head[:-1]  # `git show` output ends with a trailing newline
    out = list(head)
    for start, count, added in sorted(mine, key=lambda h: h[0], reverse=True):
        out[start:start] = added
        assert count == len(added)

    text = "\n".join(out) + "\n"
    # Match the working tree's line endings so the staged blob is what a checkout
    # of it will look like (the repo is checked out with CRLF on Windows).
    crlf = b"\r\n" in (REPO / TARGET).read_bytes()
    if crlf:
        text = text.replace("\n", "\r\n")

    for marker in FOREIGN_MARKERS:
        if marker in text:
            raise SystemExit(f"reconstruction still contains a foreign marker: {marker}")
    for marker in OWN_MARKERS:
        if marker not in text:
            raise SystemExit(f"reconstruction is missing an own marker: {marker}")

    expected = len(head) + sum(h[1] for h in mine)
    got = len(text.rstrip("\r\n").split("\n"))
    if got != expected:
        raise SystemExit(f"line count mismatch: built {got}, expected {expected}")
    print(f"reconstruction: {got} lines ({len(head)} at HEAD + {got - len(head)})")
    print("foreign markers absent, own markers present")

    blob_in = text.replace("\r\n", "\n")
    # bytes in, bytes out: the same locale codec would otherwise mangle the
    # em dashes on the way IN.
    blob = (
        subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=REPO,
            input=blob_in.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )
    print(f"blob {blob[:12]}")
    staged = _git("diff", "--cached", "--stat") or "(index empty)"
    print(f"index before: {staged.strip()}")
    if not args.apply:
        print("dry run — pass --apply to stage")
        return 0
    subprocess.run(
        ["git", "update-index", "--cacheinfo", f"100644,{blob},{TARGET}"],
        cwd=REPO,
        check=True,
    )
    print("staged")
    print(_git("diff", "--cached", "--stat", "--", TARGET).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())

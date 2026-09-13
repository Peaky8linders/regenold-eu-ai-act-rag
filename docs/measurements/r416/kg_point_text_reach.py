"""R416 — is ``REGENOLD_KG_POINT_TEXT`` reachable on the rows we would gate it on?

The gap report's finding 1.2 is that the KG contributes no point text to the
Stage-2 block under the default flag. That is true and already documented in
``app/engines/kg_context.py``: OFF runs ``_SUBPOINT_CYPHER_LEGACY``, whose inner
``MATCH (pt)-[:HAS_SUBPOINT]->(sp)`` requires a SubPoint, and the live graph has
421 Points against 37 SubPoints. R408/R409 built the fixed query (OPTIONAL hop +
per-provision budget sharing) but left it behind the OFF flag.

Before spending model calls on a paired gate, this measures the lever's REACH
deterministically, live against Aura, on the exact 26 rows the R415 official
gate pairs: for each row's emitted refs, call the real production function
``kg_context.fetch_subpoint_detail`` twice (flag OFF, then ON) and compare the
units and text the Stage-2 block would carry.

It then asks the question that decides whether a gate is worth running at all:
do the coordinates that the R409 triage recorded as OMITTED appear in the block
under the two arms? A lever that only makes the block longer is a cost; a lever
that supplies the omitted limb is a fix.

No model calls. Network: Neo4j Aura reads only.

    .venv/Scripts/python.exe docs/measurements/r416/kg_point_text_reach.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _line in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k, _v.strip())

PAIRED = ROOT / "docs/measurements/r415/official-lever-b-matched.ckpt.jsonl"
MEMBER = ROOT / "docs/measurements/r416/member-recall.json"
FLAG = "REGENOLD_KG_POINT_TEXT"


def _units(rows) -> list[dict]:
    return [dict(r) for r in (rows or [])]


def _text_chars(rows: list[dict]) -> int:
    return sum(len(str(r.get("text") or "")) for r in rows)


def _coord_in_block(rows: list[dict], coord: str) -> bool:
    """Is ``coord`` (e.g. ``Article 17.1.b``) covered by the block?

    Matched on the coordinate's own parts: a returned row carries ``cite``
    (``Article 17``), ``para`` (``1``) and ``letter`` (``b``), so the test is a
    structured match rather than a text search over prose.
    """
    m = re.match(r"^(Article|Annex)\s+([0-9IVXLC]+)(?:\.([0-9]+))?(?:\.([a-z]))?", coord)
    if not m:
        return False
    kind, number, para, letter = m.group(1), m.group(2), m.group(3), m.group(4)
    want_cite = f"{kind} {number}"
    for r in rows:
        cite = str(r.get("cite") or "").replace("Art. ", "Article ")
        if cite != want_cite:
            continue
        if para is not None and str(r.get("para") or "") != para:
            continue
        if letter is not None and str(r.get("letter") or "") != letter:
            continue
        if para is None and letter is None:
            return True
        return True
    return False


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    from app.engines import kg_context as kc

    rows = [
        json.loads(line)
        for line in PAIRED.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    member = {r["id"]: r for r in json.loads(MEMBER.read_text(encoding="utf-8"))["rows"]}
    print(f"paired rows: {len(rows)}   kg_context_enabled={kc.kg_context_enabled()}")

    changed = 0
    totals = {"off_units": 0, "on_units": 0, "off_chars": 0, "on_chars": 0}
    cold_rows: list[str] = []
    supplied: list[tuple[str, str]] = []
    missed: list[tuple[str, str]] = []

    print("-" * 100)
    print(f"{'row':<9}{'off u/ch':>14}{'on u/ch':>14}{'delta ch':>10}   coordinate coverage")
    for r in rows:
        rid = r["id"]
        refs = list(r.get("pred_refs") or [])
        os.environ[FLAG] = "0"
        off = _units(kc.fetch_subpoint_detail(refs))
        os.environ[FLAG] = "1"
        on = _units(kc.fetch_subpoint_detail(refs))
        oc, nc = _text_chars(off), _text_chars(on)
        totals["off_units"] += len(off)
        totals["on_units"] += len(on)
        totals["off_chars"] += oc
        totals["on_chars"] += nc
        if (len(off), oc) != (len(on), nc):
            changed += 1
        gaps = list(member.get(rid, {}).get("gaps") or [])
        note = ""
        for g in gaps:
            before, after = _coord_in_block(off, g), _coord_in_block(on, g)
            if after and not before:
                supplied.append((rid, g))
                note += f" +{g}"
            elif not after:
                missed.append((rid, g))
                note += f" -{g}"
        if not refs:
            cold_rows.append(rid)
        print(f"{rid:<9}{len(off):>6}/{oc:>7}{len(on):>6}/{nc:>7}{nc - oc:>10}{note}")

    print("-" * 100)
    print(f"rows whose block CHANGES under the lever : {changed}/{len(rows)}")
    print(f"units  {totals['off_units']} -> {totals['on_units']}   "
          f"text chars {totals['off_chars']} -> {totals['on_chars']}")
    if cold_rows:
        print(f"rows with no refs at all (lever inert): {cold_rows}")
    print(f"\nrecorded OMITTED coordinates supplied by the lever: {len(supplied)}")
    for rid, g in supplied:
        print(f"   + {rid}  {g}")
    print(f"recorded OMITTED coordinates absent from BOTH arms: {len(missed)}")
    for rid, g in missed:
        print(f"   - {rid}  {g}")

    out = ROOT / "docs/measurements/r416/kg-point-text-reach.json"
    out.write_text(
        json.dumps(
            {
                "flag": FLAG,
                "paired_rows": len(rows),
                "rows_changed": changed,
                "units_off": totals["off_units"],
                "units_on": totals["on_units"],
                "chars_off": totals["off_chars"],
                "chars_on": totals["on_chars"],
                "inert_rows_no_refs": cold_rows,
                "omitted_coords_supplied": [{"id": i, "coord": c} for i, c in supplied],
                "omitted_coords_absent_in_both": [{"id": i, "coord": c} for i, c in missed],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

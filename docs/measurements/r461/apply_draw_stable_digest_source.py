"""R461.3 -- correction: the request digest lives on the CHECKPOINT.

Found while writing the round's tests: ``score_arm``'s payload rows carry
``refs``/``answer``/``criteria``/... and NOTHING about the request shape, while
the checkpoint rows it was built from carry ``hard_preamble_digest`` per row.
The first cut of ``_draw_stabilise`` asked the SCORE rows for the digest, which
on real data is always absent - so every row would have failed "cannot verify"
and the re-draw could never clear a drop. Fail-closed would have hidden it: the
gate would still have read, just never draw-stable. Caught by
``tests/test_r461_3_draw_stable_rule8.py``.

So the digest is read from each arm's own checkpoint (``_digest_map``), and the
re-draw's refs still come from its score payload, which is where they live.

Idempotent, exact-single-anchor.

Usage:
    python apply_draw_stable_digest_source.py [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "evals" / "official" / "paired_ab.py"

EDITS: list[tuple[str, str, str]] = []


def _e(where: str, old: str, new: str) -> None:
    EDITS.append((where, old, new))


_e(
    "digest map next to _ckpt_rows",
    '''def _row_scope_reason(prov: Any) -> str:''',
    '''def _digest_map(
    score_path: Path, override: str | Path | None
) -> tuple[dict[str, str] | None, str]:
    """Row id -> ``hard_preamble_digest``, from the arm's own CHECKPOINT.

    Not from the score payload: ``score_arm`` keeps ``refs``, ``answer``,
    ``criteria`` and the judged axes, and carries nothing about the request
    shape. The checkpoint is where the digest is written, so that is where the
    draw-stability check reads it.
    """
    rows, source = _ckpt_rows(score_path, override)
    if rows is None:
        return None, source
    return {qid: _digest(row) for qid, row in rows.items()}, source


def _row_scope_reason(prov: Any) -> str:''',
)

_e(
    "_draw_stabilise signature",
    '''def _draw_stabilise(
    *,
    drops: dict[str, set[str]],
    rows_a: dict[str, dict],
    rows_redraw: dict[str, dict] | None,
    redraw_source: str,
) -> dict:''',
    '''def _draw_stabilise(
    *,
    drops: dict[str, set[str]],
    digests_a: dict[str, str] | None,
    digests_redraw: dict[str, str] | None,
    rows_redraw: dict[str, dict] | None,
    redraw_source: str,
) -> dict:''',
)

_e(
    "_draw_stabilise docstring: where the digest is read",
    '''    Fails CLOSED and says why: no re-draw at all (nothing is stabilised, so the
    stricter single-draw reading stands), a row missing from the re-draw, a row
    whose digest is missing, and a row whose digest disagrees all keep their
    drops in scope.
    """''',
    '''    The digests come from each arm's own CHECKPOINT (``_digest_map``); the
    re-draw's ``refs`` come from its score payload, which is where they live.

    Fails CLOSED and says why: no re-draw at all (nothing is stabilised, so the
    stricter single-draw reading stands), a row missing from the re-draw, a row
    whose digest is missing, and a row whose digest disagrees all keep their
    drops in scope.
    """''',
)

_e(
    "_draw_stabilise per-row digest lookup",
    '''    for qid in raw_rows:
        redraw_row = rows_redraw.get(qid)
        dig_a, dig_redraw = _digest(rows_a.get(qid)), _digest(redraw_row)
        if redraw_row is None or not dig_a or not dig_redraw:''',
    '''    for qid in raw_rows:
        redraw_row = rows_redraw.get(qid)
        dig_a = (digests_a or {}).get(qid, "")
        dig_redraw = (digests_redraw or {}).get(qid, "")
        if redraw_row is None or not dig_a or not dig_redraw:''',
)

_e(
    "compare: resolve the two digest maps",
    '''    draw_stability = _draw_stabilise(
        drops=drops_heads,
        rows_a=ra,
        rows_redraw=None if a_redraw is None else _load_rows_opt(Path(a_redraw)),
        redraw_source="no --redraw" if a_redraw is None else str(a_redraw),
    )''',
    '''    digests_a, digest_src_a = _digest_map(a_path, a_ckpt)
    if a_redraw is None:
        digests_redraw, digest_src_redraw = None, "no --redraw"
        rows_redraw = None
    else:
        digests_redraw, digest_src_redraw = _digest_map(Path(a_redraw), a_redraw_ckpt)
        rows_redraw = _load_rows_opt(Path(a_redraw))
    draw_stability = _draw_stabilise(
        drops=drops_heads,
        digests_a=digests_a,
        digests_redraw=digests_redraw,
        rows_redraw=rows_redraw,
        redraw_source=digest_src_redraw,
    )
    draw_stability["digests"] = {
        "arm_a": digest_src_a,
        "redraw": digest_src_redraw,
    }''',
)

_e(
    "compare signature gains the re-draw checkpoint override",
    '''    veto_scope: str = DEFAULT_VETO_SCOPE,
    a_redraw: str | Path | None = None,
) -> dict:''',
    '''    veto_scope: str = DEFAULT_VETO_SCOPE,
    a_redraw: str | Path | None = None,
    a_redraw_ckpt: str | Path | None = None,
) -> dict:''',
)

_e(
    "noise_floor passes the re-draw checkpoint through",
    '''    a_redraw: str | Path | None = None,
    seed: int = 403,
) -> dict:''',
    '''    a_redraw: str | Path | None = None,
    a_redraw_ckpt: str | Path | None = None,
    seed: int = 403,
) -> dict:''',
)

_e(
    "noise_floor forwards it to compare",
    '''    res = compare(
        a_path,
        b_path,
        a_ckpt=a_ckpt,
        b_ckpt=b_ckpt,
        seed=seed,
        a_redraw=a_redraw,
    )''',
    '''    res = compare(
        a_path,
        b_path,
        a_ckpt=a_ckpt,
        b_ckpt=b_ckpt,
        seed=seed,
        a_redraw=a_redraw,
        a_redraw_ckpt=a_redraw_ckpt,
    )''',
)

_e(
    "cli: --redraw-ckpt",
    '''    ap.add_argument(
        "--control",''',
    '''    ap.add_argument(
        "--redraw-ckpt",
        default=None,
        help="override the re-draw's checkpoint (the digest source for --redraw)",
    )
    ap.add_argument(
        "--control",''',
)



_e(
    "cli: control branch forwards the re-draw checkpoint",
    """            a_redraw=(redraws[0] if redraws else None),
        )""",
    """            a_redraw=(redraws[0] if redraws else None),
            a_redraw_ckpt=args.redraw_ckpt,
        )""",
)

_e(
    "cli: lever read forwards the re-draw checkpoint",
    """        a_redraw=(redraws[0] if redraws else None),
    )""",
    """        a_redraw=(redraws[0] if redraws else None),
        a_redraw_ckpt=args.redraw_ckpt,
    )""",
)
def main() -> int:
    check = "--check" in sys.argv
    NL, CR = chr(10), chr(13)
    raw = open(TARGET, encoding="utf-8", newline="").read()
    nl = CR + NL if CR + NL in raw else NL
    text = raw
    applied = already = 0
    for where, old, new in EDITS:
        old_nl = old.replace(NL, nl)
        new_nl = new.replace(NL, nl)
        if new_nl in text:
            print(f"already applied: {where}")
            already += 1
            continue
        hits = text.count(old_nl)
        if hits != 1:
            raise SystemExit(f"ANCHOR {where!r} matched {hits} times, expected 1")
        text = text.replace(old_nl, new_nl)
        print(f"applied: {where}")
        applied += 1
    if check:
        print()
        print(f"CHECK ONLY: {applied} edit(s) would apply, {already} already applied")
        return 0
    if applied:
        if nl == CR + NL:
            text = text.replace(CR + NL, NL)
        TARGET.write_text(text, encoding="utf-8")
    print()
    print(f"{applied} file edit(s) applied, {already} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

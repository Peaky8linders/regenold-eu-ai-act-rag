"""R461.3 -- two defects the round's own tests caught, fixed.

1. ``_config_identity`` had a two-valued answer with three meanings. It returned
   ``True`` only for a verified match and ``None`` for anything else, so "these
   arms provably served DIFFERENT bytes" read as "unknown" - a floor that is
   wrong would have been refused for the wrong reason, and, worse, a reader
   could not tell a mismatched pair from an unreadable one. It is now tri-state:
   ``True`` verified one configuration, ``False`` verified different bytes on at
   least one shared row, ``None`` genuinely unknown (a checkpoint that cannot be
   read, no shared row, or a row with no digest on one side to compare - partial
   evidence is not identity).

2. The CLI priced the floor off the wrong pair. ``--redraw`` on a lever read
   computed ``noise_floor(A, B)`` - the LEVER pair - instead of arm A against
   its own re-draw, so the floor of every gate was the thing under test: exactly
   the defect this round exists to remove, in the new code. The floor is now
   ``(A, the control arm)``, which is the pair the doctrine names, and the
   second ``--redraw`` (when one is given) stabilises the floor's own read.

Idempotent, exact-single-anchor.

Usage:
    python apply_draw_stable_identity_tristate.py [--check]
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
    "_config_identity: verified mismatch is False, not unknown",
    '''    if not shared:
        block["reason"] = "the arms share no row, so identity cannot be checked"
        return block
    if mismatched or undigested:
        block["reason"] = (
            f"{len(mismatched)} shared row(s) served different request bytes and "
            f"{len(undigested)} carry no digest to compare"
        )
        return block
    block["same_configuration"] = True
    block["reason"] = f"all {len(shared)} shared rows served identical request bytes"
    return block''',
    '''    if not shared:
        block["reason"] = "the arms share no row, so identity cannot be checked"
        return block
    if mismatched:
        # VERIFIED DIFFERENT - not "unknown". A floor that provably ran other
        # bytes than the arm it is supposed to price is refused as a mismatch.
        block["same_configuration"] = False
        block["reason"] = (
            f"{len(mismatched)} shared row(s) served different request bytes: "
            "this pair is not one configuration"
        )
        return block
    if undigested:
        # Partial evidence is not identity: a row nobody can compare leaves the
        # answer UNKNOWN, which is refused too, but for its own reason.
        block["reason"] = (
            f"{len(undigested)} shared row(s) carry no digest on one side, so "
            "identity cannot be verified"
        )
        return block
    block["same_configuration"] = True
    block["reason"] = f"all {len(shared)} shared rows served identical request bytes"
    return block''',
)

_e(
    "cli: the floor is arm A against its own re-draw, not against arm B",
    '''        res = attach_noise_floor(
            res,
            noise_floor(
                Path(args.a),
                Path(args.b),
                a_ckpt=args.a_ckpt,
                b_ckpt=args.b_ckpt,
                a_redraw=(redraws[1] if len(redraws) > 1 else None),
            ),
        )''',
    '''        # THE FLOOR IS ARM A AGAINST ITS OWN RE-DRAW - never against arm B:
        # pricing the floor on the lever pair would make the thing under test
        # its own null. The re-draw names an independent draw of A's
        # configuration, so (A, re-draw) is two draws of one configuration, and
        # the SECOND re-draw (when one is given) stabilises the floor's read.
        res = attach_noise_floor(
            res,
            noise_floor(
                Path(args.a),
                Path(redraws[0]),
                a_ckpt=args.a_ckpt,
                a_redraw=(redraws[1] if len(redraws) > 1 else None),
            ),
        )''',
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

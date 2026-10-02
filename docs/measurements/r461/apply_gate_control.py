"""R461.3 -- the benchmark harness draws the paired OFF/OFF control itself.

Finding: the R461 gate had to reach BACKWARD for a historical draw to get a noise
floor, and its own report had to argue that the second draw was a peer of the
first. A floor that is assembled by hand after the fact is one a later reader
cannot check. So the arm is drawn by the harness, at the BASELINE env, under the
same protocol and the same resume contract, with suffix ``-C`` -- and only
``--no-control`` (recorded in the payload) can skip it.

The control arm is not a lever arm: it is never scored as one, and its job in the
reading step (``evals.official.paired_ab --control``) is to price what the SAME
configuration does against itself: the per-axis delta floor, and the independent
re-draw that makes rule #8 draw-stable.

Idempotent, exact-single-anchor, like the rest of this round's appliers.

Usage:
    python apply_gate_control.py            # apply
    python apply_gate_control.py --check    # report, change nothing
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "evals" / "regenold" / "run_official_batch.py"

EDITS: list[tuple[str, str, str]] = []


def _e(where: str, old: str, new: str) -> None:
    EDITS.append((where, old, new))


_e(
    "cli: --no-control",
    '''    ap.add_argument("--baseline-env", action="append", default=None)
    ap.add_argument("--branch-env", action="append", default=None)
''',
    '''    ap.add_argument("--baseline-env", action="append", default=None)
    ap.add_argument("--branch-env", action="append", default=None)
    ap.add_argument(
        "--no-control",
        action="store_true",
        help=(
            "R461.3 - do NOT draw the paired OFF/OFF control arm. A lever gate "
            "draws one automatically: the BASELINE env, suffix -C, an independent "
            "draw under the same protocol, repeats and resume contract, so the "
            "reading step can price the draw floor and read rule #8 draw-stable. "
            "Refusing it leaves the gate with no null, and the payload records "
            "that it was refused"
        ),
    )
''',
)

_e(
    "draw the control arm before the payload is written",
    '''    out = _RESULTS / f"official-{args.label}.json"''',
    '''    # R461.3 - THE PAIRED OFF/OFF CONTROL, DRAWN BY THE HARNESS.
    #
    # Why it is not optional: ``paired_ab`` reads a lever delta against what the
    # SAME configuration does against itself, because a second draw of an
    # UNCHANGED arm moves axes and even drops gold heads the first draw did not
    # (R461; ``docs/measurements/r461/COUNT-ONLY-CONFIRM.md`` SS5). A floor that
    # has to be assembled by hand after the fact is one nobody can check, so the
    # arm is drawn here, at the BASELINE env, under this run's own protocol,
    # repeats and resume contract. It is deliberately NOT a lever arm: suffix
    # ``-C``, never scored as a branch, and ``run_official_batch`` makes no claim
    # from it beyond "this is what one configuration does twice".
    if ab and not args.no_control:
        print()
        print("=== CONTROL ARM (baseline config, independent draw) -- suffix -C ===")
        control = _arm(
            args.label, args.mode, rows,
            poster=poster, url=url, api_key=args.api_key, timeout=args.timeout,
            arm_env=base_env, suffix="-C", resume=args.resume,
            repeats=args.repeats, preflight=arm_preflight,
        )
        payload["control"] = {
            "drawn": True,
            "suffix": "-C",
            "env": base_env,
            "why": (
                "an independent draw of the BASELINE configuration: the paired "
                "OFF/OFF control that prices the draw floor and supplies the "
                "re-draw rule #8 is read draw-stable against"
            ),
            "agg": {m: v["agg"] for m, v in control.items()},
            "degraded_ids": {
                m: sorted(v.get("degraded_ids") or []) for m, v in control.items()
            },
        }
    elif ab:
        print()
        print("=== NO CONTROL ARM (--no-control): this gate has no draw floor ===")
        payload["control"] = {
            "drawn": False,
            "why": "--no-control was passed: the gate has no paired OFF/OFF floor",
        }

    out = _RESULTS / f"official-{args.label}.json"''',
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

"""R461.4 -- correction found by the audit: the digest is the REQUEST SHAPE.

The R461.3 instrument described ``hard_preamble_digest`` as proof that two arms
were "one configuration". The audit that this round exists to run found the same
digest on arms from FOUR DIFFERENT ROUNDS (the digest covers the hard-preamble
fixture and whatever ``--*-env`` declaration reaches it, not the lever). So the
signal can only run one way:

* a DIFFERENCE refutes the declaration ("these arms were not asked the same
  thing"), which is what a floor and a re-draw need;
* a MATCH does not establish one configuration - the caller declares that by
  naming the control arm (``--control``, ``--redraw``, or the harness drawing the
  arm at the baseline env), and the digest can only refuse the claim.

Nothing about the arithmetic changes. What changes is what the instrument CLAIMS
when it prints a floor, which is the whole point of the reading discipline this
round is about: a check that cannot fail the way it is described is a check
nobody can audit.

Idempotent, exact-single-anchor, no backslashes in any string literal (this round
has already lost one command to escaping).

Usage:
    python apply_digest_is_shape.py [--check]
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
    "identity: the checked contract",
    '''        "checked": "hard_preamble_digest, per shared row, on each arm's own checkpoint",''',
    '''        "checked": (
            "hard_preamble_digest, per shared row, on each arm's own checkpoint - "
            "the REQUEST SHAPE only. Identity of CONFIGURATION is the caller's "
            "declaration (--control, or the harness drawing the arm at the baseline "
            "env); this check can REFUTE that declaration, never establish it"
        ),''',
)

_e(
    "identity: the refuted reason",
    '''        block["reason"] = (
            f"{len(mismatched)} shared row(s) served different request bytes: "
            "this pair is not one configuration"
        )''',
    '''        block["reason"] = (
            f"{len(mismatched)} shared row(s) carry a different request-shape "
            "digest: the declaration that this pair is one configuration is REFUTED"
        )''',
)

_e(
    "identity: the unrefuted reason",
    '''    block["same_configuration"] = True
    block["reason"] = f"all {len(shared)} shared rows served identical request bytes"''',
    '''    block["same_configuration"] = True
    block["reason"] = (
        f"all {len(shared)} shared rows carry the same request-shape digest, so the "
        "declaration is not refuted - which is not the same as established: the "
        "digest cannot establish it"
    )''',
)

_e(
    "identity docstring",
    '''    """Were these two arms asked the SAME bytes? Checked, not assumed.

    A paired OFF/OFF control is only a null if both arms ran one configuration.
    The checkpoint each score payload records carries ``hard_preamble_digest``
    per row, so identity is read off the draws themselves: every shared row must
    carry the same digest on both sides. Unknown (no checkpoint, a row with no
    digest on one side) is NOT "the same" - an unverifiable floor is not a floor.
    """''',
    '''    """Is the DECLARATION that these two arms are one configuration refutable?

    A paired OFF/OFF control is only a null if both arms ran one configuration,
    and that is a DECLARATION: ``--control``, ``--redraw``, or the harness drawing
    an arm at the baseline env. What is checkable per row is the
    ``hard_preamble_digest`` the checkpoint records, and that is a digest of the
    REQUEST SHAPE - the hard-preamble fixture and whatever ``--*-env`` declaration
    reaches it, not the lever. So the check runs one way only:

    * a DIFFERENCE refutes the declaration: these arms were not asked the same
      thing, so the pair cannot be a floor and the draw cannot stabilise a veto;
    * a MATCH does not establish that the arms ran one configuration. The R461.4
      audit found the same digest on arms of FOUR DIFFERENT ROUNDS, which is what
      a shape digest is expected to do.

    Unknown (no checkpoint, a row with no digest on one side) is refused as well:
    an unverifiable floor is not a floor.
    """''',
)

_e(
    "noise_floor docstring",
    '''    ``usable`` is false when the pair is not one configuration, or when the
    control itself still drops gold heads after stabilisation: a floor that
    moves under its own weight is not a floor, and it is refused rather than
    quietly reported as a number.
    """''',
    '''    ``usable`` is false when the DECLARED pair is refuted as one configuration (a
    request-shape digest disagreement - see ``_config_identity``: a match is
    necessary and never sufficient, so the declaration carries the rest), or when
    the control itself still drops gold heads after stabilisation: a floor that
    moves under its own weight is not a floor, and it is refused rather than
    quietly reported as a number. Whoever names the control arm is making the
    claim; this function only refuses it when the draws contradict it.
    """''',
)

_e(
    "re-draw verification wording",
    '''                    "why": (
                        "the re-draw served different request bytes "
                        f"({dig_redraw} != {dig_a})"
                    ),''',
    '''                    "why": (
                        "the re-draw served a different REQUEST SHAPE "
                        f"({dig_redraw} != {dig_a})"
                    ),''',
)

_e(
    "module doctrine: verification",
    '''* The re-draw is VERIFIED, not trusted. A row whose ``hard_preamble_digest``
  disagrees with arm A's is refused - different request bytes are not a re-draw
  of the same arm - and a row whose digest is missing on either side cannot be
  verified. A row that cannot be verified keeps its drop IN SCOPE (the stricter
  reading) and is named in ``draw_stability.unverified``.''',
    '''* The re-draw is VERIFIED, not trusted - as far as it can be. A row whose
  ``hard_preamble_digest`` disagrees with arm A's is refused: the digest is the
  request SHAPE, so a disagreement refutes the claim that this is a re-draw of
  the same arm. A match does not establish it - the R461.4 audit found one shape
  digest on arms of four different rounds - so ``--redraw`` is a DECLARATION the
  digest can refute, and a row whose digest is missing on either side cannot be
  verified at all. A row that cannot be verified keeps its drop IN SCOPE (the
  stricter reading) and is named in ``draw_stability.unverified``.''',
)

_e(
    "module doctrine: the floor",
    '''* The same flag PRICES THE NOISE FLOOR. Arm A against its own re-draw is a
  paired OFF/OFF control - two draws of one configuration - so the read carries
  that pair's per-axis deltas beside the lever deltas: no delta is read without
  one.''',
    '''* The same flag PRICES THE NOISE FLOOR. Arm A against its own re-draw is a
  paired OFF/OFF control - two draws of one configuration, DECLARED by naming
  that arm and refutable only on the request-shape digest - so the read carries
  that pair's per-axis deltas beside the lever deltas: no delta is read without
  one.''',
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

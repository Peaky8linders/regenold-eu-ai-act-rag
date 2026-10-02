"""R461.3 -- apply the DRAW-STABLE rule #8 and the NOISE FLOOR to paired_ab.py.

Two findings from R461, both about reading a single draw as a fact:

1. the SCOPE fix (R461.1, committed) asked WHICH ROWS testify;
2. this one asks whether the drop on them is a FACT. At n=37 a second draw of an
   UNCHANGED OFF arm drops gold heads the first draw did not
   (``COUNT-ONLY-CONFIRM.md`` SS5), so "arm B lacks a head arm A held" can veto
   on draw noise alone.

So rule #8 is now read DRAW-STABLE: ``--redraw`` names an INDEPENDENT draw of
arm A's own configuration (which is what a paired OFF/OFF control arm IS), and a
gold head arm B lacks vetoes only if that re-draw holds the head too. The same
flag prices the noise floor: arm A against its re-draw is two draws of one
configuration, and every lever delta is reported beside that null.

Idempotent: re-running reports "already applied" and changes nothing. Every edit
is anchored on an exact single occurrence in the file, so a drift in the target
is a hard error rather than a silent partial patch.

Usage:
    python apply_draw_stable.py            # apply
    python apply_draw_stable.py --check    # report, change nothing
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "evals" / "official" / "paired_ab.py"

EDITS: list[tuple[str, str, str]] = []


def _e(where: str, old: str, new: str) -> None:
    EDITS.append((where, old, new))


# --------------------------------------------------------------------------- #
# 1. the doctrine, in the module docstring
# --------------------------------------------------------------------------- #
_e(
    "docstring: DRAW-STABLE RULE #8",
    """Usage:
    python -m evals.official.paired_ab \\
        --a docs/measurements/r388/score-A.json \\
        --b docs/measurements/r388/score-B.json
    python -m evals.official.paired_ab --a score-A.json --b score-B.json \\
        --veto-scope all --out legacy.json
\"\"\"""",
    """DRAW-STABLE RULE #8 (R461.3). The scope fix above answers WHICH ROWS testify.
This answers whether the drop on them is a FACT. R461 measured that it is not:
at n=37 a SECOND draw of an UNCHANGED OFF arm drops gold heads the first draw
did not (``docs/measurements/r461/COUNT-ONLY-CONFIRM.md`` SS5), so "arm B lacks
a head arm A held" can veto on draw noise alone. The rule is therefore read
DRAW-STABLE: with ``--redraw`` - an INDEPENDENT draw of arm A's own
configuration, which is exactly what a paired OFF/OFF control arm is - a gold
head arm B lacks vetoes only if arm A's re-draw carries that head too. The
reference has to hold the head REPRODUCIBLY before its absence can be called a
loss. Nothing leaves the record: a drop the stabilisation clears is reported in
``draw_stability.drops_unstable`` with the head and the re-draw's evidence.

* The re-draw is VERIFIED, not trusted. A row whose ``hard_preamble_digest``
  disagrees with arm A's is refused - different request bytes are not a re-draw
  of the same arm - and a row whose digest is missing on either side cannot be
  verified. A row that cannot be verified keeps its drop IN SCOPE (the stricter
  reading) and is named in ``draw_stability.unverified``.
* Without ``--redraw`` the single-draw reading stands, which is the STRICTER
  one, so the fallback can never lift a veto: the payload records
  ``draw_stability.stabilized = false`` and the read prints NO NOISE FLOOR.
* The same flag PRICES THE NOISE FLOOR. Arm A against its own re-draw is a
  paired OFF/OFF control - two draws of one configuration - so the read carries
  that pair's per-axis deltas beside the lever deltas: no delta is read without
  one. ``--control`` declares a read to BE that control pair rather than a lever
  read; a pair whose arms are not the same configuration
  (``config_identity``) is refused as a floor instead of reported as one.

Usage:
    python -m evals.official.paired_ab \\
        --a docs/measurements/r388/score-A.json \\
        --b docs/measurements/r388/score-B.json
    python -m evals.official.paired_ab --a score-A.json --b score-B.json \\
        --veto-scope all --out legacy.json
    # draw-stable, with the noise floor: A against an independent re-draw of A
    python -m evals.official.paired_ab --a score-OFF.json --b score-ON.json \\
        --redraw score-OFF-redraw.json --out paired.json
\"\"\"""",
)

# --------------------------------------------------------------------------- #
# 2. constants + row-level helpers
# --------------------------------------------------------------------------- #
_e(
    "helpers after _gold_dropped_head",
    '''def _row_scope_reason(prov: Any) -> str:''',
    '''#: R461.3 - the draw-stability rule, in one sentence, for every payload.
DRAW_STABILITY_RULE = (
    "hard rule #8 is read draw-stable: a gold head arm B lacks vetoes only if "
    "an INDEPENDENT re-draw of arm A carries that head too"
)


def _head_key(ref: Any) -> str:
    """One reference reduced to the grain the veto is read at (R388 refkey)."""
    return str(ref).split(".")[0]


def _gold_heads(expected: list[str] | None) -> set[str]:
    return {_head_key(e) for e in expected or []}


def _present_heads(refs: list[str] | None) -> set[str]:
    return {_head_key(r) for r in refs or []}


def _digest(row: dict | None) -> str:
    """The request digest a checkpoint row was served, or ``""``."""
    return str((row or {}).get("hard_preamble_digest") or "")


def _load_rows_opt(path: Path | None) -> dict[str, dict] | None:
    """Rows of an OPTIONAL score payload; ``None`` when it cannot be read."""
    if path is None:
        return None
    try:
        return _load_rows(path)
    except Exception:  # noqa: BLE001 - an unreadable re-draw is reported, not raised
        return None


def _ckpt_rows(
    score_path: Path, override: str | Path | None
) -> tuple[dict[str, dict] | None, str]:
    """The raw checkpoint rows of an arm, plus what was tried (for the report).

    The provenance roster below is a projection of this; the request digest the
    draw-stability check needs is on the same rows.
    """
    path = _resolve_ckpt(score_path, override)
    if path is None:
        return None, "no checkpoint recorded in the score payload"
    if not path.exists():
        return None, f"checkpoint not found: {path}"
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id") is not None:
            rows[str(row["id"])] = row
    return rows, str(path)


def _row_scope_reason(prov: Any) -> str:''',
)

# `_provenance_roster` becomes a projection of `_ckpt_rows` (one reader, one
# place the checkpoint format is parsed).
_e(
    "provenance roster projected from _ckpt_rows",
    '''    path = _resolve_ckpt(score_path, override)
    if path is None:
        return None, "no checkpoint recorded in the score payload"
    if not path.exists():
        return None, f"checkpoint not found: {path}"
    roster: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id") is not None:
            roster[str(row["id"])] = _row_scope_reason(row.get("provenance"))
    return roster, str(path)''',
    '''    rows, source = _ckpt_rows(score_path, override)
    if rows is None:
        return None, source
    return {qid: _row_scope_reason(row.get("provenance")) for qid, row in rows.items()}, source''',
)

# --------------------------------------------------------------------------- #
# 3. the stabilisation itself
# --------------------------------------------------------------------------- #
_e(
    "the stabilisation",
    '''def _veto_block(''',
    '''def _draw_stabilise(
    *,
    drops: dict[str, set[str]],
    rows_a: dict[str, dict],
    rows_redraw: dict[str, dict] | None,
    redraw_source: str,
) -> dict:
    """Which raw gold-head drops survive an independent re-draw of arm A.

    ``drops`` maps a row id to the gold heads arm A's draw carried and arm B's
    does not - the RAW drops. A head stays a drop only if the re-draw carries it
    too, which is what makes it a fact about the BASELINE rather than about one
    sample of it; otherwise the baseline never reliably held the head and its
    absence from arm B is draw noise. The cleared drops are returned in
    ``drops_unstable``, never deleted.

    Fails CLOSED and says why: no re-draw at all (nothing is stabilised, so the
    stricter single-draw reading stands), a row missing from the re-draw, a row
    whose digest is missing, and a row whose digest disagrees all keep their
    drops in scope.
    """
    raw_rows = sorted(drops)
    raw_heads = sum(len(h) for h in drops.values())
    block: dict = {
        "rule": DRAW_STABILITY_RULE,
        "stabilized": False,
        "redraw": redraw_source,
        "redraw_rows": 0,
        "raw_drop_rows": raw_rows,
        "raw_drop_heads": raw_heads,
        "verified_rows": [],
        "unverified": [],
        "survived": {},
        "drops_unstable": [],
        "reason": "",
    }
    if rows_redraw is None:
        block["survived"] = {qid: sorted(heads) for qid, heads in drops.items()}
        block["reason"] = (
            f"no independent re-draw of arm A supplied ({redraw_source}); the "
            "single-draw reading stands (the stricter of the two)"
        )
        return block
    block["stabilized"] = True
    block["redraw_rows"] = len(rows_redraw)
    survived: dict[str, list[str]] = {}
    for qid in raw_rows:
        redraw_row = rows_redraw.get(qid)
        dig_a, dig_redraw = _digest(rows_a.get(qid)), _digest(redraw_row)
        if redraw_row is None or not dig_a or not dig_redraw:
            why = (
                "row missing from the re-draw"
                if redraw_row is None
                else "no hard_preamble_digest on one side to compare"
            )
            block["unverified"].append(
                {"id": qid, "why": why, "heads": sorted(drops[qid])}
            )
            survived[qid] = sorted(drops[qid])
            continue
        if dig_a != dig_redraw:
            block["unverified"].append(
                {
                    "id": qid,
                    "why": (
                        "the re-draw served different request bytes "
                        f"({dig_redraw} != {dig_a})"
                    ),
                    "heads": sorted(drops[qid]),
                }
            )
            survived[qid] = sorted(drops[qid])
            continue
        block["verified_rows"].append(qid)
        held = _present_heads(redraw_row.get("refs"))
        kept = sorted(h for h in drops[qid] if h in held)
        if kept:
            survived[qid] = kept
        cleared = sorted(h for h in drops[qid] if h not in held)
        if cleared:
            block["drops_unstable"].append(
                {
                    "id": qid,
                    "heads": cleared,
                    "why": (
                        "the re-draw does not carry the head either: draw noise, "
                        "not a loss"
                    ),
                }
            )
    block["survived"] = survived
    block["survived_rows"] = sorted(survived)
    block["survived_heads"] = sum(len(h) for h in survived.values())
    block["cleared_rows"] = sorted({d["id"] for d in block["drops_unstable"]})
    block["cleared_heads"] = sum(len(d["heads"]) for d in block["drops_unstable"])
    note = (
        f"{block['cleared_heads']} of {raw_heads} raw drop head(s) did not persist "
        f"across the re-draw ({redraw_source}) and are reported, not vetoed"
    )
    if block["unverified"]:
        note += (
            f"; {len(block['unverified'])} row(s) could not be verified and keep "
            "their drops (fail closed)"
        )
    block["reason"] = note
    return block


def _veto_block(''',
)

# --------------------------------------------------------------------------- #
# 4. _veto_block carries the stabilisation
# --------------------------------------------------------------------------- #
_e(
    "_veto_block signature",
    '''    veto_scope: str,
    seed: int,
) -> dict:''',
    '''    veto_scope: str,
    seed: int,
    draw_stability: dict | None = None,
) -> dict:''',
)

_e(
    "_veto_block payload",
    '''        "drops_in_scope": in_scope,
        "drops_in_scope_confounded_a": confounded,''',
    '''        "drops_in_scope": in_scope,
        "drops_in_scope_confounded_a": confounded,
        "draw_stable": bool((draw_stability or {}).get("stabilized")),
        "draw_stability": draw_stability or {},''',
)

_e(
    "_veto_block rule line",
    '''        "rule": (
            "hard rule #8 — a lever that drops a gold HEAD on a row it actually "
            "served is vetoed regardless of means"
        ),''',
    '''        "rule": (
            "hard rule #8 — a lever that drops a gold HEAD on a row it actually "
            "served is vetoed regardless of means; a drop is READ DRAW-STABLE "
            "(R461.3), so it vetoes only if an independent re-draw of arm A "
            "carries the head too"
        ),''',
)

# --------------------------------------------------------------------------- #
# 5. compare(): collect the dropped HEADS, stabilise, hand the survivors on
# --------------------------------------------------------------------------- #
_e(
    "compare signature",
    '''    a_ckpt: str | Path | None = None,
    b_ckpt: str | Path | None = None,
    veto_scope: str = DEFAULT_VETO_SCOPE,
) -> dict:''',
    '''    a_ckpt: str | Path | None = None,
    b_ckpt: str | Path | None = None,
    veto_scope: str = DEFAULT_VETO_SCOPE,
    a_redraw: str | Path | None = None,
) -> dict:''',
)

_e(
    "compare docstring",
    '''    ``veto_scope`` selects the rows hard rule #8 is read on (see the module
    docstring): ``"lever"`` (default) evaluates the rows arm B's own
    provenance says the lever served, ``"all"`` reproduces the pre-R461
    definition. ``gold_dropped_head`` always reports the all-rows counts; the
    ``veto`` block carries the scoped verdict.
    """''',
    '''    ``veto_scope`` selects the rows hard rule #8 is read on (see the module
    docstring): ``"lever"`` (default) evaluates the rows arm B's own
    provenance says the lever served, ``"all"`` reproduces the pre-R461
    definition. ``gold_dropped_head`` always reports the all-rows counts; the
    ``veto`` block carries the scoped verdict.

    ``a_redraw`` is an INDEPENDENT draw of arm A's own configuration and makes
    the veto draw-stable (see DRAW-STABLE RULE #8): a drop survives only if the
    re-draw carries the head too, and a drop that does not survive is reported
    in ``draw_stability.drops_unstable`` rather than silently skipped. Without
    it the single-draw reading stands - the stricter one - and the payload says
    ``stabilized: false``.
    """''',
)

_e(
    "compare drop loop",
    '''    drops_a = drops_b = 0
    rows_dropped: list[str] = []
    dropped_b_ids: set[str] = set()
    considered: list[str] = []''',
    '''    drops_a = drops_b = 0
    rows_dropped: list[str] = []
    drops_heads: dict[str, set[str]] = {}
    dropped_b_ids: set[str] = set()
    considered: list[str] = []''',
)

_e(
    "compare drop loop body",
    '''        if db_ and not da_:
            rows_dropped.append(qid)''',
    '''        if db_ and not da_:
            rows_dropped.append(qid)
            # The HEADS, not just the fact: the draw-stability read needs to
            # know WHICH gold head went missing before it can ask the re-draw
            # whether the baseline ever really carried it.
            held_a = _present_heads(ra[qid].get("refs") or [])
            held_b = _present_heads(rb[qid].get("refs") or [])
            drops_heads[qid] = {
                h
                for h in (_gold_heads(ea) | _gold_heads(eb))
                if h in held_a and h not in held_b
            }''',
)

_e(
    "compare veto call",
    '''    veto = _veto_block(
        considered=considered,
        shared_rows=len(shared),
        dropped_b=dropped_b_ids,
        new_drops=rows_dropped,
        a_path=a_path,
        b_path=b_path,
        a_ckpt=a_ckpt,
        b_ckpt=b_ckpt,
        veto_scope=veto_scope,
        seed=seed,
    )''',
    '''    # R461.3 - the veto is read on the drops that SURVIVE the re-draw. The raw
    # drops stay in the record either way (draw_stability), and with no re-draw
    # every raw drop survives, which is the pre-R461.3 behaviour on purpose.
    draw_stability = _draw_stabilise(
        drops=drops_heads,
        rows_a=ra,
        rows_redraw=None if a_redraw is None else _load_rows_opt(Path(a_redraw)),
        redraw_source="no --redraw" if a_redraw is None else str(a_redraw),
    )
    veto = _veto_block(
        considered=considered,
        shared_rows=len(shared),
        dropped_b=dropped_b_ids,
        new_drops=sorted(draw_stability["survived"]),
        a_path=a_path,
        b_path=b_path,
        a_ckpt=a_ckpt,
        b_ckpt=b_ckpt,
        veto_scope=veto_scope,
        seed=seed,
        draw_stability=draw_stability,
    )''',
)

_e(
    "compare payload",
    '''        "gold_dropped_head": {"arm_a": drops_a, "arm_b": drops_b, "new_drops_in_b": rows_dropped},
        "veto": veto,''',
    '''        "gold_dropped_head": {"arm_a": drops_a, "arm_b": drops_b, "new_drops_in_b": rows_dropped},
        "draw_stability": draw_stability,
        "redraw": None if a_redraw is None else str(a_redraw),
        "veto": veto,''',
)

# --------------------------------------------------------------------------- #
# 6. the noise floor (the paired OFF/OFF control)
# --------------------------------------------------------------------------- #
_e(
    "noise floor functions",
    '''def _fmt_census(census: dict[str, int]) -> str:''',
    '''def _config_identity(
    a_path: Path,
    b_path: Path,
    *,
    a_ckpt: str | Path | None = None,
    b_ckpt: str | Path | None = None,
) -> dict:
    """Were these two arms asked the SAME bytes? Checked, not assumed.

    A paired OFF/OFF control is only a null if both arms ran one configuration.
    The checkpoint each score payload records carries ``hard_preamble_digest``
    per row, so identity is read off the draws themselves: every shared row must
    carry the same digest on both sides. Unknown (no checkpoint, a row with no
    digest on one side) is NOT "the same" - an unverifiable floor is not a floor.
    """
    rows_a, src_a = _ckpt_rows(a_path, a_ckpt)
    rows_b, src_b = _ckpt_rows(b_path, b_ckpt)
    block: dict = {
        "same_configuration": None,
        "rows_compared": 0,
        "mismatched": [],
        "undigested": [],
        "checked": "hard_preamble_digest, per shared row, on each arm's own checkpoint",
        "arm_a": src_a,
        "arm_b": src_b,
        "reason": "",
    }
    if rows_a is None or rows_b is None:
        block["reason"] = "a checkpoint could not be read, so identity is unknown"
        return block
    shared = sorted(set(rows_a) & set(rows_b))
    mismatched: list[dict] = []
    undigested: list[str] = []
    for qid in shared:
        dig_a, dig_b = _digest(rows_a[qid]), _digest(rows_b[qid])
        if not dig_a or not dig_b:
            undigested.append(qid)
            continue
        if dig_a != dig_b:
            mismatched.append({"id": qid, "arm_a": dig_a, "arm_b": dig_b})
    block["rows_compared"] = len(shared)
    block["mismatched"] = mismatched
    block["undigested"] = undigested
    if not shared:
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
    return block


def noise_floor(
    a_path: Path,
    b_path: Path,
    *,
    a_ckpt: str | Path | None = None,
    b_ckpt: str | Path | None = None,
    a_redraw: str | Path | None = None,
    seed: int = 403,
) -> dict:
    """The paired OFF/OFF control: two INDEPENDENT draws of ONE configuration.

    This is the null every lever delta is read against, and it is what makes the
    rule-#8 reading draw-stable: arm A against this control arm is exactly the
    "independent re-draw of the baseline arm" the rule requires, and it is priced
    before the lever read is believed. ``a_redraw`` stabilises the CONTROL's own
    rule-#8 read (a third draw), which is where a no-draw-floor instrument would
    report a veto on a pair that has no lever in it at all.

    ``usable`` is false when the pair is not one configuration, or when the
    control itself still drops gold heads after stabilisation: a floor that
    moves under its own weight is not a floor, and it is refused rather than
    quietly reported as a number.
    """
    identity = _config_identity(a_path, b_path, a_ckpt=a_ckpt, b_ckpt=b_ckpt)
    res = compare(
        a_path,
        b_path,
        a_ckpt=a_ckpt,
        b_ckpt=b_ckpt,
        seed=seed,
        a_redraw=a_redraw,
    )
    veto = res["veto"]
    reasons: list[str] = [identity["reason"]]
    if identity["same_configuration"] and veto["fires"]:
        reasons.append(
            "the control pair itself drops gold heads after stabilisation, so "
            "rule #8 would be firing on draw noise"
        )
    if identity["same_configuration"] is None:
        reasons.append("the pair's configuration could not be verified")
    usable = bool(identity["same_configuration"]) and not veto["fires"]
    return {
        "rule": (
            "the paired OFF/OFF control: two independent draws of one "
            "configuration, priced before any lever delta is read"
        ),
        "pair": {"arm_a": str(a_path.name), "arm_b": str(b_path.name)},
        "config_identity": identity,
        "axes": {
            axis: {
                "delta": res["axes"][axis]["delta"],
                "ci95": res["axes"][axis]["ci95"],
                "n": res["axes"][axis]["n"],
            }
            for axis in AXES
        },
        "gold_dropped_head": res["gold_dropped_head"],
        "draw_stability": res["draw_stability"],
        "veto": veto,
        "usable": usable,
        "reason": "; ".join(r for r in reasons if r),
    }


def attach_noise_floor(result: dict, floor: dict) -> dict:
    """Put the control pair's deltas beside every lever delta, in the payload.

    ``beyond_floor`` asks the only question a bare delta cannot answer: is this
    move bigger than what the SAME configuration produces against itself?
    ``ci_excludes_floor`` is the paired reading of the same question - whether
    the lever's own bootstrap CI covers the control's observed delta.
    """
    axes: dict[str, dict] = {}
    for axis in AXES:
        lever = result["axes"][axis]
        entry = (floor.get("axes") or {}).get(axis) or {}
        floor_delta = entry.get("delta")
        ci = entry.get("ci95") or [None, None]
        axes[axis] = {
            "lever_delta": lever["delta"],
            "floor_delta": floor_delta,
            "beyond_floor": (
                None if floor_delta is None else abs(lever["delta"]) > abs(floor_delta)
            ),
            "ci_excludes_floor": (
                None
                if ci[0] is None
                else not (ci[0] <= lever["delta"] <= ci[1])
            ),
        }
    result["noise_floor"] = {
        "rule": floor.get("rule"),
        "pair": floor.get("pair"),
        "usable": floor.get("usable"),
        "reason": floor.get("reason"),
        "config_identity": floor.get("config_identity"),
        "floor_veto": (floor.get("veto") or {}).get("verdict"),
        "floor_draw_stability": (floor.get("veto") or {}).get("draw_stability"),
        "axes": axes,
    }
    return result


def _print_noise_floor_summary(floor: dict) -> None:
    print("\\nNOISE FLOOR (paired OFF/OFF control - two draws of one configuration)")
    pair = floor.get("pair") or {}
    print(f"  pair: {pair.get('arm_a')} vs {pair.get('arm_b')}")
    print(f"  usable: {floor.get('usable')}   {floor.get('reason') or ''}")
    for axis in AXES:
        entry = (floor.get("axes") or {}).get(axis) or {}
        delta = entry.get("delta")
        ci = entry.get("ci95") or [float("nan"), float("nan")]
        print(
            f"  {axis:<26}{0.0 if delta is None else delta:>+9.2f}"
            f"  [{ci[0]:+.2f}, {ci[1]:+.2f}]  n={entry.get('n')}"
        )


def _fmt_census(census: dict[str, int]) -> str:''',
)

# --------------------------------------------------------------------------- #
# 7. the veto printout carries the draw-stability read
# --------------------------------------------------------------------------- #
_e(
    "_print_veto draw-stability lines",
    '''    for d in v["drops_undecided"]:
        print(
            f"  UNDECIDED, cannot tell whether the lever ran: {d['id']}"
            f"  A={d['arm_a']} B={d['arm_b']}"
        )''',
    '''    for d in v["drops_undecided"]:
        print(
            f"  UNDECIDED, cannot tell whether the lever ran: {d['id']}"
            f"  A={d['arm_a']} B={d['arm_b']}"
        )
    ds = v.get("draw_stability") or {}
    if ds:
        state = (
            "DRAW-STABLE" if ds.get("stabilized") else "SINGLE DRAW (not stabilised)"
        )
        print(f"  draw-stability: {state}  re-draw = {ds.get('redraw')}")
        if ds.get("reason"):
            print(f"    {ds['reason']}")
        for d in ds.get("drops_unstable") or []:
            print(
                f"    cleared by the re-draw (draw noise, reported not vetoed): "
                f"{d['id']}  heads={d['heads']}"
            )
        for d in ds.get("unverified") or []:
            print(f"    unverifiable, drop kept (fail closed): {d['id']}  {d['why']}")''',
)

# --------------------------------------------------------------------------- #
# 8. the CLI
# --------------------------------------------------------------------------- #
_e(
    "cli flags",
    '''    ap.add_argument(
        "--b-ckpt", default=None, help="override arm B's checkpoint (veto scope only)"
    )
    args = ap.parse_args()''',
    '''    ap.add_argument(
        "--b-ckpt", default=None, help="override arm B's checkpoint (veto scope only)"
    )
    ap.add_argument(
        "--redraw",
        action="append",
        default=None,
        help=(
            "an INDEPENDENT draw of arm A's own configuration (repeatable). The "
            "first makes rule #8 draw-stable and prices the noise floor against "
            "arm A; a second stabilises the floor's own read. Verified per row on "
            "hard_preamble_digest: an unverifiable row keeps its drop (fail closed)"
        ),
    )
    ap.add_argument(
        "--control",
        action="store_true",
        help=(
            "read this pair as the paired OFF/OFF CONTROL rather than a lever "
            "read: it must be one configuration, and it is refused as a floor if "
            "its own rule-#8 read still fires"
        ),
    )
    ap.add_argument(
        "--noise-floor-out",
        default=None,
        help="where --control writes its payload (default: --out)",
    )
    args = ap.parse_args()''',
)

_e(
    "cli main body",
    '''    res = compare(
        Path(args.a),
        Path(args.b),
        a_ckpt=args.a_ckpt,
        b_ckpt=args.b_ckpt,
        veto_scope=args.veto_scope,
    )
''',
    '''    redraws = list(args.redraw or [])

    if args.control:
        floor = noise_floor(
            Path(args.a),
            Path(args.b),
            a_ckpt=args.a_ckpt,
            b_ckpt=args.b_ckpt,
            a_redraw=(redraws[0] if redraws else None),
        )
        print("\\nPAIRED OFF/OFF CONTROL (the noise floor)")
        _print_noise_floor_summary(floor)
        _print_veto(floor["veto"])
        out = args.noise_floor_out or args.out
        if out:
            Path(out).write_text(
                json.dumps(floor, indent=1) + "\\n", encoding="utf-8"
            )
            print(f"wrote {out}")
        return 0

    res = compare(
        Path(args.a),
        Path(args.b),
        a_ckpt=args.a_ckpt,
        b_ckpt=args.b_ckpt,
        veto_scope=args.veto_scope,
        a_redraw=(redraws[0] if redraws else None),
    )
    if redraws:
        # The floor is arm A against its own re-draw; the SECOND re-draw (when
        # there is one) stabilises the floor's read, so the floor is not quoted
        # from a single draw either.
        res = attach_noise_floor(
            res,
            noise_floor(
                Path(args.a),
                Path(args.b),
                a_ckpt=args.a_ckpt,
                b_ckpt=args.b_ckpt,
                a_redraw=(redraws[1] if len(redraws) > 1 else None),
            ),
        )
''',
)

_e(
    "cli print floor",
    '''    _print_veto(res["veto"])
    print(f"mean answer chars: A={res['mean_answer_chars']['arm_a']:.0f}  B={res['mean_answer_chars']['arm_b']:.0f}")

    if args.out:
        Path(args.out).write_text(
            json.dumps(res, indent=1), encoding="utf-8"
        )
        print(f"wrote {args.out}")
    return 0''',
    '''    _print_veto(res["veto"])
    print(f"mean answer chars: A={res['mean_answer_chars']['arm_a']:.0f}  B={res['mean_answer_chars']['arm_b']:.0f}")

    floor = res.get("noise_floor")
    if floor:
        _print_noise_floor_summary(floor)
        print("\\nlever delta vs the floor")
        for axis in AXES:
            row = floor["axes"][axis]
            flag = ""
            if row["beyond_floor"] is False:
                flag = "  WITHIN THE FLOOR"
            print(
                f"  {axis:<26}lever={row['lever_delta']:>+7.2f}"
                f"  floor={row['floor_delta']:>+7.2f}  "
                f"{'beyond' if row['beyond_floor'] else 'not beyond'} the floor{flag}"
            )
    else:
        print(
            "\\nNO NOISE FLOOR: no --redraw control arm was supplied, so this read "
            "carries no draw band and rule #8 was read single-draw (the stricter "
            "reading). Draw the paired OFF/OFF control and re-read with --redraw."
        )

    if args.out:
        Path(args.out).write_text(
            json.dumps(res, indent=1),
            encoding="utf-8",
        )
        print(f"wrote {args.out}")
    return 0''',
)


def main() -> int:
    check = "--check" in sys.argv
    raw = open(TARGET, encoding="utf-8", newline="").read()
    NL, CR = chr(10), chr(13)
    nl = CR + NL if CR + NL in raw else NL
    text = raw
    applied = 0
    already = 0
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

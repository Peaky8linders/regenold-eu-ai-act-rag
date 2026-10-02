"""R403 — paired A/B decision statistics over two score_arm checkpoints.

Why: earlier lever verdicts (R142.1, R327.1, R401) were decided on
aggregates — means with no paired variance, so "wash" and "significant"
claims were untestable. This module pairs two arms ROW BY ROW (same
question, both arms, same judge cache) and reports:

* per-axis paired deltas with a 10,000-resample bootstrap 95% CI
* McNemar exact tests on the flip counts that matter (strict all-pass
  flips, tone flips, per-row ref-axis flips)
* the hard rule #8 veto: per-row gold-head drops, arm A vs arm B,
  read on the rows the lever actually served (VETO SCOPE below)

Row pairing requires BOTH arms judged from the SAME judge cache — identical
answers share verdicts, so deltas reflect generation changes, not judge
noise. Rows with a failed criterion-count match or missing verdicts are
reported and dropped from both arms.

VETO SCOPE (R461). Hard rule #8 — "a lever that drops a gold HEAD on any row
is vetoed regardless of means" — needs the row to be evidence about the
LEVER, and the served answer alone does not say that. An arm can lose a row's
Stage-2 output to the transport (both legs fail, so the deterministic Stage-1
draft ships; or the truncation guard keeps the previous turn's answer) or
never make a Stage-2 call on the row at all (a curated intercept). On those
rows the block under test was never in the answer the judge scored, so a
missing gold head there is not attributable to it. The R461 count-only gate
tripped the veto exactly that way — on a row its own provenance marks
``deterministic``, where the arm had been asked the same question as its
control — and the same run measured that the rule is not draw-stable at n=37:
a SECOND draw of an UNCHANGED arm drops two gold heads the first draw did
not (``docs/measurements/r461/COUNT-ONLY-CONFIRM.md`` §5). So the veto is
read on the rows where the lever actually ran, and every excluded row and
every drop on one is reported rather than dropped from the record:

* ``--veto-scope lever`` (default) — a row is evaluated iff the ARM UNDER
  TEST (arm B, the lever arm) was served by a leg that carried the lever's
  payload: ``stage2_served_by`` in ``primary``/``fallback``. On a checkpoint
  written before ``stage2_served_by`` existed the only hint is
  ``stage2_polish``, and ``True`` is read as a Stage-2 leg.
* ``--veto-scope all`` — every shared row: the operating definition in use
  before R461, kept so a published verdict can be re-derived byte-for-byte.
* Provenance is read from the checkpoint each score payload records
  (``ckpt``), joined to the score rows by ``id``; ``--a-ckpt``/``--b-ckpt``
  override it. When the scope cannot be computed - no checkpoint, a checkpoint
  that names no leg on any row (pre-R417), or no eligible row at all - it
  falls back to ``all`` and says so in ``scope_downgraded``: unreadable
  provenance is not evidence that a lever ran, so it must never lift a veto,
  and a vacuous scope must not read as a pass. A single row whose provenance is
  missing or names nothing is reported UNDECIDED instead - it is named, and an
  undecided row is not a clean one.

DRAW-STABLE RULE #8 (R461.3). The scope fix above answers WHICH ROWS testify.
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

* The re-draw is VERIFIED, not trusted - as far as it can be. A row whose
  ``hard_preamble_digest`` disagrees with arm A's is refused: the digest is the
  request SHAPE, so a disagreement refutes the claim that this is a re-draw of
  the same arm. A match does not establish it - the R461.4 audit found one shape
  digest on arms of four different rounds - so ``--redraw`` is a DECLARATION the
  digest can refute, and a row whose digest is missing on either side cannot be
  verified at all. A row that cannot be verified keeps its drop IN SCOPE (the
  stricter reading) and is named in ``draw_stability.unverified``.
* Without ``--redraw`` the single-draw reading stands, which is the STRICTER
  one, so the fallback can never lift a veto: the payload records
  ``draw_stability.stabilized = false`` and the read prints NO NOISE FLOOR.
* The same flag PRICES THE NOISE FLOOR. Arm A against its own re-draw is a
  paired OFF/OFF control - two draws of one configuration, DECLARED by naming
  that arm and refutable only on the request-shape digest - so the read carries
  that pair's per-axis deltas beside the lever deltas: no delta is read without
  one. ``--control`` declares a read to BE that control pair rather than a lever
  read; a pair whose arms are not the same configuration
  (``config_identity``) is refused as a floor instead of reported as one.

Usage:
    python -m evals.official.paired_ab \
        --a docs/measurements/r388/score-A.json \
        --b docs/measurements/r388/score-B.json
    python -m evals.official.paired_ab --a score-A.json --b score-B.json \
        --veto-scope all --out legacy.json
    # draw-stable, with the noise floor: A against an independent re-draw of A
    python -m evals.official.paired_ab --a score-OFF.json --b score-ON.json \
        --redraw score-OFF-redraw.json --out paired.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

from evals.bench import row_provenance

REPO = Path(__file__).resolve().parents[2]

AXES = [
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
]

#: Hard rule #8 — any lever that drops a gold HEAD on any row is vetoed
#: regardless of what the mean deltas say. Computed at HEAD grain (the
#: ``gold_dropped_head`` convention in ``evals/bench/metrics.py``).

#: R461.5 — one resolution for every gate: the row-provenance vocabulary and
#: the predicates over it live in ``evals/bench/row_provenance``. ``fallback``
#: is a leg that carried the lever's payload for rule #8; the R423 exclusion
#: reads the same row as a degraded transport. Both readings are in the shared
#: module, by design, so no gate can re-read the raw fields its own way.
LEVER_RAN_LEGS = row_provenance.SERVING_LEGS
DEGRADED_LEGS = row_provenance.DISCARDED_LEGS

#: What each eligibility reason means, for the report a reader has to trust.
SCOPE_REASONS = row_provenance.SCOPE_REASONS

#: A drop on an excluded row is CLOSED when the row's own provenance proves the
#: lever did not serve it (the two degraded legs, or no Stage-2 call at all); it
#: is UNDECIDED when provenance cannot tell, which must not read as "clean".
#: UNDECIDED is a refusal too - the acceptance table's "no gold heads dropped"
#: is not met by a row nobody can account for.
_UNREADABLE_REASONS = tuple(row_provenance.UNREADABLE_KINDS)
_CLOSED_REASONS = frozenset(row_provenance.CLOSED_KINDS)

VETO_SCOPES = ("lever", "all")
DEFAULT_VETO_SCOPE = "lever"


def _gold_dropped_head(expected: list[str], refs: list[str]) -> bool:
    got = {str(r).split(".")[0] for r in refs or []}
    return any(
        str(e).split(".")[0] not in got for e in expected or []
    )


#: R461.3 - the draw-stability rule, in one sentence, for every payload.
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


def _digest_map(
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


#: Why one graded row's Stage-2 provenance is, or is not, lever evidence. The
#: resolution lives in ``evals/bench/row_provenance.scope_reason``; this alias
#: is the name this module's report and tests were written against.
_row_scope_reason = row_provenance.scope_reason


#: Did the lever's payload serve this row's answer? ``unknown`` and
#: ``no_provenance`` are NOT evidence that it did, so they are not eligible; a
#: drop on such a row is reported UNDECIDED rather than vetoed, and the verdict
#: is not CLEAN. Shared with every other row-scoped gate
#: (``evals/bench/row_provenance.lever_ran_reason``).
_lever_ran = row_provenance.lever_ran_reason


def _load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_rows(path: Path) -> dict[str, dict]:
    return {r["id"]: r for r in _load_payload(path)["rows"]}


def _resolve_ckpt(score_path: Path, override: str | Path | None) -> Path | None:
    """The checkpoint a score payload was built from, or ``None``.

    The payload records it as a repo-relative path (``ckpt``); an explicit
    override wins, so a pair whose checkpoint has been moved can still be
    re-read without editing the score JSON.
    """
    raw: str | None = None
    if override is not None:
        raw = str(override)
    else:
        try:
            payload = _load_payload(score_path)
        except Exception:  # noqa: BLE001 — an unreadable score file is handled by the caller
            return None
        ckpt = payload.get("ckpt")
        raw = str(ckpt) if ckpt else None
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (REPO / path)


def _provenance_roster(
    score_path: Path, override: str | Path | None
) -> tuple[dict[str, str] | None, str]:
    """Map row id -> eligibility reason, from the arm's own checkpoint.

    Returns ``(roster, source)``; ``roster`` is ``None`` when the checkpoint
    cannot be read, and the source string always names what was tried, so the
    report can say which file the scope was decided on.
    """
    rows, source = _ckpt_rows(score_path, override)
    if rows is None:
        return None, source
    return {qid: _row_scope_reason(row.get("provenance")) for qid, row in rows.items()}, source


def _reason_of(roster: dict[str, str] | None, qid: str) -> str:
    if roster is None:
        return "no_provenance"
    return roster.get(qid) or "no_provenance"


def _reason_census(roster: dict[str, str] | None, qids: list[str]) -> dict[str, int]:
    census: dict[str, int] = {}
    for qid in qids:
        reason = _reason_of(roster, qid)
        census[reason] = census.get(reason, 0) + 1
    return census


def _draw_stabilise(
    *,
    drops: dict[str, set[str]],
    digests_a: dict[str, str] | None,
    digests_redraw: dict[str, str] | None,
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

    The digests come from each arm's own CHECKPOINT (``_digest_map``); the
    re-draw's ``refs`` come from its score payload, which is where they live.

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
        dig_a = (digests_a or {}).get(qid, "")
        dig_redraw = (digests_redraw or {}).get(qid, "")
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
                        "the re-draw served a different REQUEST SHAPE "
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


def _veto_block(
    *,
    considered: list[str],
    shared_rows: int,
    dropped_b: set[str],
    new_drops: list[str],
    a_path: Path,
    b_path: Path,
    a_ckpt: str | Path | None,
    b_ckpt: str | Path | None,
    veto_scope: str,
    seed: int,
    draw_stability: dict | None = None,
) -> dict:
    """Hard rule #8, read on the rows the lever actually ran.

    ``considered`` are the shared rows carrying a gold key (the rows the drop
    loop could testify about); ``new_drops`` are the rows where arm B dropped a
    gold head arm A did not.
    """
    scope = veto_scope if veto_scope in VETO_SCOPES else DEFAULT_VETO_SCOPE
    roster_a, src_a = _provenance_roster(a_path, a_ckpt)
    roster_b, src_b = _provenance_roster(b_path, b_ckpt)
    downgraded = False
    downgrade_reason = ""

    # Fail CLOSED. The lever scope is read off provenance, and provenance that
    # cannot be read - a missing file, or a checkpoint that predates the leg
    # fields and so names no leg on ANY row - is not evidence that a lever ran.
    # Rather than reinterpret the gate on a scope nobody can compute, fall back
    # to the pre-R461 definition, which is the stricter one, and say so.
    if scope == "lever":
        why = ""
        for name, roster, src in (("A", roster_a, src_a), ("B", roster_b, src_b)):
            if roster is None:
                why = f"no per-row provenance for arm {name} ({src})"
                break
            if not any(
                _reason_of(roster, q) not in _UNREADABLE_REASONS for q in considered
            ):
                why = (
                    f"arm {name}'s checkpoint names no leg on any row ({src})"
                )
                break
        if why:
            downgraded = True
            scope = "all"
            downgrade_reason = (
                f"{why}; scope fell back to 'all' (the stricter definition)"
            )

    eligible: list[str] = []
    excluded: list[dict[str, str]] = []
    for qid in considered:
        reasons = (_reason_of(roster_a, qid), _reason_of(roster_b, qid))
        if scope == "all" or _lever_ran(reasons[1]):
            eligible.append(qid)
        else:
            excluded.append({"id": qid, "arm_a": reasons[0], "arm_b": reasons[1]})

    if scope == "lever" and not eligible:
        # Nothing was served by a Stage-2 leg on this pair at all: the scope is
        # vacuous, and a vacuous scope must not read as a pass either.
        downgraded = True
        scope = "all"
        eligible = list(considered)
        excluded = []
        downgrade_reason = (
            f"no gold row is lever-eligible (0 of {len(considered)}); "
            "scope fell back to 'all' (the stricter definition)"
        )

    eligible_set = set(eligible)
    in_scope: list[dict[str, str]] = []
    out_of_scope: list[dict[str, str]] = []
    undecided: list[dict[str, str]] = []
    for qid in new_drops:
        reasons = (_reason_of(roster_a, qid), _reason_of(roster_b, qid))
        if qid in eligible_set:
            in_scope.append({"id": qid, "arm_a": reasons[0], "arm_b": reasons[1]})
            continue
        if scope == "all":
            # Every considered row is eligible, so this cannot happen; guard
            # anyway rather than lose a drop from the record.
            in_scope.append({"id": qid, "arm_a": reasons[0], "arm_b": reasons[1]})
            continue
        entry = {"id": qid, "arm_a": reasons[0], "arm_b": reasons[1]}
        if reasons[1] in _CLOSED_REASONS:
            # Arm B's own provenance proves the lever did not serve this row.
            out_of_scope.append(entry)
        else:
            # Arm B ran the lever but arm A did not run the same path
            # (confounded), or provenance cannot tell which it was.
            undecided.append(entry)

    confounded = [
        d["id"] for d in in_scope if not _lever_ran(d["arm_a"])
    ]
    if in_scope:
        verdict = "VETO"
    elif undecided:
        verdict = "UNDECIDED"
    else:
        verdict = "CLEAN"
    return {
        "rule": (
            "hard rule #8 — a lever that drops a gold HEAD on a row it actually "
            "served is vetoed regardless of means; a drop is READ DRAW-STABLE "
            "(R461.3), so it vetoes only if an independent re-draw of arm A "
            "carries the head too"
        ),
        "verdict": verdict,
        "fires": bool(in_scope),
        "scope": scope,
        "scope_requested": veto_scope,
        "scope_supported": list(VETO_SCOPES),
        "scope_downgraded": downgraded,
        "downgrade_reason": downgrade_reason,
        "contract": (
            "arm-under-test provenance in ('primary','fallback') = the legs that "
            "carried the lever's payload (else stage2_polish is True on a "
            "pre-stage2_served_by checkpoint)"
        ),
        "rows_considered": len(considered),
        "shared_rows": shared_rows,
        "eligible_rows": len(eligible),
        "excluded_rows": len(excluded),
        "levers_evaluated": len(eligible),
        "excluded": excluded,
        "by_reason_a": _reason_census(roster_a, considered),
        "by_reason_b": _reason_census(roster_b, considered),
        "n_dropped_in_b": len(dropped_b),
        "drops_in_scope": in_scope,
        "drops_in_scope_confounded_a": confounded,
        "draw_stable": bool((draw_stability or {}).get("stabilized")),
        "draw_stability": draw_stability or {},
        "drops_out_of_scope": out_of_scope,
        "drops_undecided": undecided,
        "provenance": {
            "arm_a": src_a,
            "arm_b": src_b,
            "join": "ckpt row id -> score row id",
            "bootstrap_seed": seed,
        },
        "reasons": dict(SCOPE_REASONS),
    }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _bootstrap_ci(
    deltas: list[float], n: int = 10_000, alpha: float = 0.05, seed: int = 403
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of paired deltas."""
    if not deltas:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    m = len(deltas)
    means = []
    for _ in range(n):
        s = 0.0
        for _i in range(m):
            s += deltas[rng.randrange(m)]
        means.append(s / m)
    means.sort()
    lo = means[int((alpha / 2) * n)]
    hi = means[int((1 - alpha / 2) * n) - 1]
    return lo, hi


def _mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value via the binomial tail."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(n, i) * (0.5**n)
    return min(1.0, 2 * p)


def _row_axis(r: dict, axis: str) -> float | None:
    """Recompute one row's axis score from its judged fields."""
    from evals.official.rubric import (
        answer_conciseness,
        answer_correctness_loose,
        answer_correctness_strict,
        reference_conciseness,
        reference_correctness_loose,
        reference_correctness_strict,
        regulatory_tone,
        response_speed,
    )

    if axis == "ans_correctness_loose":
        return answer_correctness_loose([r.get("criteria") or []]) * 100.0
    if axis == "ans_correctness_strict":
        return answer_correctness_strict([r.get("criteria") or []]) * 100.0
    if axis == "ans_conciseness":
        a = r.get("answer")
        ref = r.get("reference_answer")
        if a is None or ref is None:
            # score_arm JSONs carry char counts, not raw text
            ac, rc = r.get("answer_chars"), r.get("reference_chars")
            if not ac:
                return None
            if rc is None:
                return None
            return min(1.0, float(rc) / float(ac)) * 100.0
        v = answer_conciseness(a, ref)
        return None if v is None else v * 100.0
    if axis == "ref_correctness_loose":
        v = reference_correctness_loose(r.get("refs") or [], r.get("expected_refs") or [])
        return None if v is None else v * 100.0
    if axis == "ref_correctness_strict":
        v = reference_correctness_strict(r.get("refs") or [], r.get("expected_refs") or [])
        return None if v is None else v * 100.0
    if axis == "ref_conciseness":
        v = reference_conciseness(r.get("refs") or [], r.get("expected_refs") or [])
        return None if v is None else v * 100.0
    if axis == "regulatory_tone":
        return 100.0 if r.get("tone_ok") else 0.0
    if axis == "resp_speed":
        v = response_speed([r.get("latency_s") or 0.0])
        return v * 100.0
    raise ValueError(axis)


def compare(
    a_path: Path,
    b_path: Path,
    seed: int = 403,
    *,
    a_ckpt: str | Path | None = None,
    b_ckpt: str | Path | None = None,
    veto_scope: str = DEFAULT_VETO_SCOPE,
    a_redraw: str | Path | None = None,
    a_redraw_ckpt: str | Path | None = None,
) -> dict:
    """Full paired comparison; ``a`` = baseline arm, ``b`` = branch arm.

    ``veto_scope`` selects the rows hard rule #8 is read on (see the module
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
    """
    from evals.official.rubric import (
        answer_conciseness,
        answer_conciseness as _ac,
    )

    ra, rb = _load_rows(a_path), _load_rows(b_path)
    shared = sorted(set(ra) & set(rb))
    only_a = sorted(set(ra) - set(rb))
    only_b = sorted(set(rb) - set(ra))

    per_axis: dict[str, dict] = {}
    for axis in AXES:
        da: list[float] = []
        flips_pos = flips_neg = 0
        for qid in shared:
            va = _row_axis(ra[qid], axis)
            vb = _row_axis(rb[qid], axis)
            if va is None or vb is None:
                continue
            da.append(vb - va)
            if vb > va:
                flips_pos += 1
            elif vb < va:
                flips_neg += 1
        lo, hi = _bootstrap_ci(da, seed=seed)
        # McNemar only makes sense on binary-ish axes; for graded axes the
        # flip counts are still informative (improvements vs regressions).
        per_axis[axis] = {
            "n": len(da),
            "mean_a": _mean([_row_axis(ra[q], axis) for q in shared
                             if _row_axis(ra[q], axis) is not None]),
            "mean_b": _mean([_row_axis(rb[q], axis) for q in shared
                             if _row_axis(rb[q], axis) is not None]),
            "delta": _mean(da),
            "ci95": [lo, hi],
            "b_better": flips_pos,
            "a_better": flips_neg,
            "mcnemar_p": _mcnemar_exact(flips_pos, flips_neg),
        }

    # Gold-drop veto, per row. ``gold_dropped_head`` keeps the all-rows counts
    # it has always carried; the scoped verdict lives in ``veto`` below.
    drops_a = drops_b = 0
    rows_dropped: list[str] = []
    drops_heads: dict[str, set[str]] = {}
    dropped_b_ids: set[str] = set()
    considered: list[str] = []
    for qid in shared:
        ea = ra[qid].get("expected_refs") or []
        eb = rb[qid].get("expected_refs") or []
        if not ea and not eb:
            continue
        considered.append(qid)
        da_ = _gold_dropped_head(ea, ra[qid].get("refs") or [])
        db_ = _gold_dropped_head(eb, rb[qid].get("refs") or [])
        drops_a += da_
        drops_b += db_
        if db_:
            dropped_b_ids.add(qid)
        if db_ and not da_:
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
            }

    # R461.3 - the veto is read on the drops that SURVIVE the re-draw. The raw
    # drops stay in the record either way (draw_stability), and with no re-draw
    # every raw drop survives, which is the pre-R461.3 behaviour on purpose.
    digests_a, digest_src_a = _digest_map(a_path, a_ckpt)
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
    }
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
    )

    # Conciseness headroom bookkeeping (axis 3): mean answer chars.
    def _chars(rows: dict[str, dict]) -> float:
        vals = []
        for q in shared:
            v = rows[q].get("answer_chars")
            if v is None:
                v = len(rows[q].get("answer") or "")
            vals.append(float(v or 0))
        return _mean(vals)

    chars_a = _chars(ra)
    chars_b = _chars(rb)

    return {
        "arm_a": str(a_path.name),
        "arm_b": str(b_path.name),
        "shared_rows": len(shared),
        "only_in_a": only_a,
        "only_in_b": only_b,
        "axes": per_axis,
        "gold_dropped_head": {"arm_a": drops_a, "arm_b": drops_b, "new_drops_in_b": rows_dropped},
        "draw_stability": draw_stability,
        "redraw": None if a_redraw is None else str(a_redraw),
        "veto": veto,
        "mean_answer_chars": {"arm_a": chars_a, "arm_b": chars_b},
    }


def _config_identity(
    a_path: Path,
    b_path: Path,
    *,
    a_ckpt: str | Path | None = None,
    b_ckpt: str | Path | None = None,
) -> dict:
    """Is the DECLARATION that these two arms are one configuration refutable?

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
    """
    rows_a, src_a = _ckpt_rows(a_path, a_ckpt)
    rows_b, src_b = _ckpt_rows(b_path, b_ckpt)
    block: dict = {
        "same_configuration": None,
        "rows_compared": 0,
        "mismatched": [],
        "undigested": [],
        "checked": (
            "hard_preamble_digest, per shared row, on each arm's own checkpoint - "
            "the REQUEST SHAPE only. Identity of CONFIGURATION is the caller's "
            "declaration (--control, or the harness drawing the arm at the baseline "
            "env); this check can REFUTE that declaration, never establish it"
        ),
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
    if mismatched:
        # VERIFIED DIFFERENT - not "unknown". A floor that provably ran other
        # bytes than the arm it is supposed to price is refused as a mismatch.
        block["same_configuration"] = False
        block["reason"] = (
            f"{len(mismatched)} shared row(s) carry a different request-shape "
            "digest: the declaration that this pair is one configuration is REFUTED"
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
    block["reason"] = (
        f"all {len(shared)} shared rows carry the same request-shape digest, so the "
        "declaration is not refuted - which is not the same as established: the "
        "digest cannot establish it"
    )
    return block


def noise_floor(
    a_path: Path,
    b_path: Path,
    *,
    a_ckpt: str | Path | None = None,
    b_ckpt: str | Path | None = None,
    a_redraw: str | Path | None = None,
    a_redraw_ckpt: str | Path | None = None,
    seed: int = 403,
) -> dict:
    """The paired OFF/OFF control: two INDEPENDENT draws of ONE configuration.

    This is the null every lever delta is read against, and it is what makes the
    rule-#8 reading draw-stable: arm A against this control arm is exactly the
    "independent re-draw of the baseline arm" the rule requires, and it is priced
    before the lever read is believed. ``a_redraw`` stabilises the CONTROL's own
    rule-#8 read (a third draw), which is where a no-draw-floor instrument would
    report a veto on a pair that has no lever in it at all.

    ``usable`` is false when the DECLARED pair is refuted as one configuration (a
    request-shape digest disagreement - see ``_config_identity``: a match is
    necessary and never sufficient, so the declaration carries the rest), or when
    the control itself still drops gold heads after stabilisation: a floor that
    moves under its own weight is not a floor, and it is refused rather than
    quietly reported as a number. Whoever names the control arm is making the
    claim; this function only refuses it when the draws contradict it.
    """
    identity = _config_identity(a_path, b_path, a_ckpt=a_ckpt, b_ckpt=b_ckpt)
    res = compare(
        a_path,
        b_path,
        a_ckpt=a_ckpt,
        b_ckpt=b_ckpt,
        seed=seed,
        a_redraw=a_redraw,
        a_redraw_ckpt=a_redraw_ckpt,
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
    print("\nNOISE FLOOR (paired OFF/OFF control - two draws of one configuration)")
    pair = floor.get("pair") or {}
    print(f"  pair: {pair.get('arm_a')} vs {pair.get('arm_b')}")
    print(f"  usable: {floor.get('usable')}   {floor.get('reason') or ''}")
    for axis in AXES:
        entry = (floor.get("axes") or {}).get(axis) or {}
        # Two shapes reach this printer: the floor payload itself (delta + CI
        # + n) and the block ``attach_noise_floor`` puts on a LEVER read,
        # which carries the lever beside the floor. Reading only the first
        # shape printed zeros and nan for the second - found by running the
        # R461 gate through it, not by a unit test.
        if "floor_delta" in entry:
            lever_delta, floor_delta = entry.get("lever_delta"), entry.get("floor_delta")
            print(
                f"  {axis:<26}lever={0.0 if lever_delta is None else lever_delta:>+7.2f}"
                f"  floor={0.0 if floor_delta is None else floor_delta:>+7.2f}"
                f"  {'beyond' if entry.get('beyond_floor') else 'within'} the floor"
            )
            continue
        delta = entry.get("delta")
        ci = entry.get("ci95") or [float("nan"), float("nan")]
        print(
            f"  {axis:<26}{0.0 if delta is None else delta:>+9.2f}"
            f"  [{ci[0]:+.2f}, {ci[1]:+.2f}]  n={entry.get('n')}"
        )


def _fmt_census(census: dict[str, int]) -> str:
    if not census:
        return "none"
    parts = [f"{n} {reason}" for reason, n in sorted(census.items(), key=lambda kv: -kv[1])]
    return " / ".join(parts)


def _print_veto(v: dict) -> None:
    print(
        f"\nrule #8 veto: {v['verdict']}  scope={v['scope']}"
        f"  ({v['eligible_rows']}/{v['rows_considered']} gold rows evaluated)"
    )
    print(f"  contract: {v['contract']}")
    if v["scope_downgraded"]:
        print(f"  SCOPE DOWNGRADED: {v['downgrade_reason']}")
    print(f"  provenance A: {_fmt_census(v['by_reason_a'])}   [{v['provenance']['arm_a']}]")
    print(f"  provenance B: {_fmt_census(v['by_reason_b'])}   [{v['provenance']['arm_b']}]")
    for d in v["drops_in_scope"]:
        flag = "  (arm A not a clean control)" if d["id"] in v["drops_in_scope_confounded_a"] else ""
        print(
            f"  IN SCOPE — veto: {d['id']}  A={d['arm_a']} B={d['arm_b']}{flag}"
        )
    for d in v["drops_out_of_scope"]:
        print(
            f"  out of scope, reported: {d['id']}  A={d['arm_a']} B={d['arm_b']}"
            f"  ({SCOPE_REASONS.get(d['arm_b'], d['arm_b'])})"
        )
    for d in v["drops_undecided"]:
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
            print(f"    unverifiable, drop kept (fail closed): {d['id']}  {d['why']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--veto-scope",
        choices=list(VETO_SCOPES),
        default=DEFAULT_VETO_SCOPE,
        help=(
            "rows hard rule #8 is read on: 'lever' (default) = the rows arm B's "
            "own provenance says the lever served; 'all' = every shared row "
            "(the pre-R461 definition)"
        ),
    )
    ap.add_argument(
        "--a-ckpt", default=None, help="override arm A's checkpoint (veto scope only)"
    )
    ap.add_argument(
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
        "--redraw-ckpt",
        default=None,
        help="override the re-draw's checkpoint (the digest source for --redraw)",
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
    args = ap.parse_args()

    redraws = list(args.redraw or [])

    if args.control:
        floor = noise_floor(
            Path(args.a),
            Path(args.b),
            a_ckpt=args.a_ckpt,
            b_ckpt=args.b_ckpt,
            a_redraw=(redraws[0] if redraws else None),
            a_redraw_ckpt=args.redraw_ckpt,
        )
        print("\nPAIRED OFF/OFF CONTROL (the noise floor)")
        _print_noise_floor_summary(floor)
        _print_veto(floor["veto"])
        out = args.noise_floor_out or args.out
        if out:
            Path(out).write_text(
                json.dumps(floor, indent=1) + "\n", encoding="utf-8"
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
        a_redraw_ckpt=args.redraw_ckpt,
    )
    if redraws:
        # The floor is arm A against its own re-draw; the SECOND re-draw (when
        # there is one) stabilises the floor's read, so the floor is not quoted
        # from a single draw either.
        # THE FLOOR IS ARM A AGAINST ITS OWN RE-DRAW - never against arm B:
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
        )

    print(f"\nPAIRED A/B  (n={res['shared_rows']} shared rows)")
    print(f"  arm A = {res['arm_a']}   arm B = {res['arm_b']}")
    if res["only_in_a"] or res["only_in_b"]:
        print(f"  only-in-A: {res['only_in_a']}  only-in-B: {res['only_in_b']}")
    hdr = f"{'axis':<26}{'A':>8}{'B':>8}{'delta':>9}  {'95% CI':<20}{'+/-':>8}  {'McNemar p':>9}"
    print(hdr)
    print("-" * len(hdr))
    for axis in AXES:
        d = res["axes"][axis]
        ci = f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]"
        star = ""
        if d["ci95"][0] > 0:
            star = " B>"
        elif d["ci95"][1] < 0:
            star = " A>"
        print(
            f"{axis:<26}{d['mean_a']:>8.2f}{d['mean_b']:>8.2f}"
            f"{d['delta']:>+9.2f}  {ci:<20}{d['b_better']:>4}/{d['a_better']:<3}"
            f"  {d['mcnemar_p']:>9.4f}{star}"
        )
    gd = res["gold_dropped_head"]
    print(
        f"\ngold_dropped_head: A={gd['arm_a']}  B={gd['arm_b']}"
        + (f"  NEW DROPS IN B: {gd['new_drops_in_b']}" if gd["new_drops_in_b"] else "")
    )
    _print_veto(res["veto"])
    print(f"mean answer chars: A={res['mean_answer_chars']['arm_a']:.0f}  B={res['mean_answer_chars']['arm_b']:.0f}")

    floor = res.get("noise_floor")
    if floor:
        _print_noise_floor_summary(floor)
        print("\nlever delta vs the floor")
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
            "\nNO NOISE FLOOR: no --redraw control arm was supplied, so this read "
            "carries no draw band and rule #8 was read single-draw (the stricter "
            "reading). Draw the paired OFF/OFF control and re-read with --redraw."
        )

    if args.out:
        Path(args.out).write_text(
            json.dumps(res, indent=1),
            encoding="utf-8",
        )
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

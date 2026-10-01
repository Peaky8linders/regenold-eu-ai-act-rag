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

Usage:
    python -m evals.official.paired_ab \
        --a docs/measurements/r388/score-A.json \
        --b docs/measurements/r388/score-B.json
    python -m evals.official.paired_ab --a score-A.json --b score-B.json \
        --veto-scope all --out legacy.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

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

#: Legs whose served answer carried the lever's payload. ``primary`` is the
#: intended Stage-2 leg; ``fallback`` is the other transport for the SAME
#: request payload, so a payload-level lever ran there too.
LEVER_RAN_LEGS = ("primary", "fallback")

#: R461 — legs that mean the Stage-2 output was DISCARDED, so the row cannot
#: testify about the lever. Named in the engine's own vocabulary
#: (``_mark_stage2_served_by`` in ``app/engines/_graph_rag_impl.py``):
#: ``deterministic`` is the Stage-1 draft shipped after both legs failed,
#: ``prior_turn`` is the truncation guard keeping the previous turn's answer.
DEGRADED_LEGS = ("deterministic", "prior_turn")

#: What each eligibility reason means, for the report a reader has to trust.
SCOPE_REASONS = {
    "primary": "served by the primary Stage-2 leg (lever in force)",
    "fallback": "served by the fallback leg — same request payload",
    "deterministic": "degraded: the Stage-1 draft shipped, Stage-2 output discarded",
    "prior_turn": "degraded: the truncation guard kept the previous turn's answer",
    "unpolished": "no Stage-2 call on this row (curated/intercepted answer)",
    "unknown": "provenance names no leg and no polish flag: NOT evidence the lever ran",
    "no_provenance": "no per-row provenance for this row: it cannot testify (reported UNDECIDED)",
}

#: Reason -> was the lever's payload in this row's answer?
_LEVER_RAN = {reason: reason in LEVER_RAN_LEGS for reason in SCOPE_REASONS}

#: A drop on an excluded row is CLOSED when the row's own provenance proves the
#: lever did not serve it (the two degraded legs, or no Stage-2 call at all); it
#: is UNDECIDED when provenance cannot tell, which must not read as "clean".
#: UNDECIDED is a refusal too - the acceptance table's "no gold heads dropped"
#: is not met by a row nobody can account for.
_UNREADABLE_REASONS = ("unknown", "no_provenance")
_CLOSED_REASONS = frozenset(DEGRADED_LEGS) | {"unpolished"}

VETO_SCOPES = ("lever", "all")
DEFAULT_VETO_SCOPE = "lever"


def _gold_dropped_head(expected: list[str], refs: list[str]) -> bool:
    got = {str(r).split(".")[0] for r in refs or []}
    return any(
        str(e).split(".")[0] not in got for e in expected or []
    )


def _row_scope_reason(prov: Any) -> str:
    """Why one graded row's Stage-2 provenance is, or is not, lever evidence.

    ``stage2_served_by`` when the checkpoint records it; else the
    ``stage2_polish`` flag, which is all a checkpoint written before that field
    carries (``True`` — polished on a Stage-2 leg, the only leg such a
    checkpoint had; ``False`` — nothing served it a Stage-2 answer). An
    unrecognised leg NAME is read as a Stage-2 serve: the engine only writes
    that field when a leg served the wire, and the two legs that mean
    "discarded" are named above, so a new label must not silently widen the
    exemption.
    """
    if prov is None:
        return "no_provenance"
    if not isinstance(prov, dict):
        return "unknown"
    served = prov.get("stage2_served_by")
    if served not in (None, ""):
        leg = str(served)
        if leg in SCOPE_REASONS:
            return leg
        # A leg name this module does not know is still the engine saying a leg
        # served the wire; only the two discarded-output legs are exempt.
        return "primary"
    if prov.get("stage2_polish") is True:
        return "primary"
    if prov.get("stage2_polish") is False:
        return "unpolished"
    return "unknown"


def _lever_ran(reason: str) -> bool:
    """Did the lever's payload serve this row's answer?

    ``unknown`` and ``no_provenance`` are NOT evidence that it did, so they are
    not eligible; a drop on such a row is reported UNDECIDED rather than
    vetoed, and the verdict is not CLEAN. That is the per-row reading of the
    same rule the whole-roster downgrade applies in the other direction: there,
    nothing about the arm can be read at all, so the legacy (stricter) scope is
    used instead of a scope nobody can compute.
    """
    return _LEVER_RAN.get(reason, reason not in _CLOSED_REASONS)


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
    path = _resolve_ckpt(score_path, override)
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
    return roster, str(path)


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
            "served is vetoed regardless of means"
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
) -> dict:
    """Full paired comparison; ``a`` = baseline arm, ``b`` = branch arm.

    ``veto_scope`` selects the rows hard rule #8 is read on (see the module
    docstring): ``"lever"`` (default) evaluates the rows arm B's own
    provenance says the lever served, ``"all"`` reproduces the pre-R461
    definition. ``gold_dropped_head`` always reports the all-rows counts; the
    ``veto`` block carries the scoped verdict.
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

    veto = _veto_block(
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
        "veto": veto,
        "mean_answer_chars": {"arm_a": chars_a, "arm_b": chars_b},
    }


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
    args = ap.parse_args()

    res = compare(
        Path(args.a),
        Path(args.b),
        a_ckpt=args.a_ckpt,
        b_ckpt=args.b_ckpt,
        veto_scope=args.veto_scope,
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

    if args.out:
        Path(args.out).write_text(
            json.dumps(res, indent=1), encoding="utf-8"
        )
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

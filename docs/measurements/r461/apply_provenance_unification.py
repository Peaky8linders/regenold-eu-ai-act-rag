"""R461.5 applier - route every gate's row-scoped rule through one module.

Idempotent: each edit checks that its NEW text is already present and skips.
Run from the worktree root with the repo venv:

    python docs/measurements/r461/apply_provenance_unification.py

Every replacement is asserted to match exactly once (count == 1) before it is
written; newlines are detected per file, so CRLF files stay CRLF.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LF = chr(10)
CRLF = chr(13) + chr(10)


def edit(path: str, old: str, new: str) -> None:
    p = REPO / path
    raw = open(p, encoding="utf-8", newline="").read()
    nl = CRLF if CRLF in raw else LF
    old_nl = old.replace(LF, nl)
    new_nl = new.replace(LF, nl)
    if new_nl in raw:
        print("already applied:", path)
        return
    found = raw.count(old_nl)
    assert found == 1, (path, found)
    open(p, "w", encoding="utf-8", newline="").write(raw.replace(old_nl, new_nl, 1))
    print("applied:", path)


# --------------------------------------------------------------------------- #
# paired_ab - import the shared module
# --------------------------------------------------------------------------- #
edit(
    "evals/official/paired_ab.py",
    '''from typing import Any

REPO = Path(__file__).resolve().parents[2]''',
    '''from typing import Any

from evals.bench import row_provenance

REPO = Path(__file__).resolve().parents[2]''',
)

# --------------------------------------------------------------------------- #
# paired_ab - the vocabulary constants come from the shared module
# --------------------------------------------------------------------------- #
edit(
    "evals/official/paired_ab.py",
    '''#: Legs whose served answer carried the lever's payload. ``primary`` is the
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
_CLOSED_REASONS = frozenset(DEGRADED_LEGS) | {"unpolished"}''',
    '''#: R461.5 — one resolution for every gate: the row-provenance vocabulary and
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
_CLOSED_REASONS = frozenset(row_provenance.CLOSED_KINDS)''',
)

# --------------------------------------------------------------------------- #
# paired_ab - the two readers become aliases of the shared predicates
# --------------------------------------------------------------------------- #
edit(
    "evals/official/paired_ab.py",
    '''def _row_scope_reason(prov: Any) -> str:
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
    return _LEVER_RAN.get(reason, reason not in _CLOSED_REASONS)''',
    '''#: Why one graded row's Stage-2 provenance is, or is not, lever evidence. The
#: resolution lives in ``evals/bench/row_provenance.scope_reason``; this alias
#: is the name this module's report and tests were written against.
_row_scope_reason = row_provenance.scope_reason


#: Did the lever's payload serve this row's answer? ``unknown`` and
#: ``no_provenance`` are NOT evidence that it did, so they are not eligible; a
#: drop on such a row is reported UNDECIDED rather than vetoed, and the verdict
#: is not CLEAN. Shared with every other row-scoped gate
#: (``evals/bench/row_provenance.lever_ran_reason``).
_lever_ran = row_provenance.lever_ran_reason''',
)

# --------------------------------------------------------------------------- #
# gate_validity - import the shared module
# --------------------------------------------------------------------------- #
edit(
    "evals/harness/gate_validity.py",
    '''from typing import Any

__all__ = [''',
    '''from typing import Any

from evals.bench import row_provenance

__all__ = [''',
)

# --------------------------------------------------------------------------- #
# gate_validity - the counter comment points at the shared predicate
# --------------------------------------------------------------------------- #
edit(
    "evals/harness/gate_validity.py",
    '''    #: R422 — graded answers that were served by the DETERMINISTIC Stage-1 draft,
    #: i.e. Stage-2 never landed. Read from each row's own provenance
    #: (``stage2_served_by == 'deterministic'``, or ``stage2_polish is False`` on
    #: a checkpoint that predates that field). This is the counter that catches''',
    '''    #: R422 — graded answers that were served by the DETERMINISTIC Stage-1 draft,
    #: i.e. Stage-2 never landed. Read from each row's own provenance through
    #: ``evals.bench.row_provenance.deterministic_draft`` (a named
    #: ``deterministic`` leg, or the legacy ``stage2_polish is False`` on a
    #: checkpoint that predates the leg field). This is the counter that catches''',
)

# --------------------------------------------------------------------------- #
# gate_validity - the three row-scoped helpers become the shared functions
# --------------------------------------------------------------------------- #
edit(
    "evals/harness/gate_validity.py",
    '''def count_rows_served_by(rows: Any) -> dict[str, int]:
    """Which leg served each graded row, counted off the rows' own provenance.

    ``primary`` / ``fallback`` / ``deterministic`` each count rows that name
    that leg; ``unnamed`` counts rows carrying no leg at all (an older
    checkpoint, or a row whose trace was empty). The distinction matters for a
    RESUMED arm: in-process transport counters restart at zero, so a resumed arm
    looks like one that produced nothing, when in fact every row on disk records
    a primary completion.
    """
    counts: dict[str, int] = {}
    if not rows:
        return counts
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            counts["unnamed"] = counts.get("unnamed", 0) + 1
            continue
        served = prov.get("stage2_served_by")
        if served in (None, ""):
            # A row written before the field existed: ``stage2_polish`` is the
            # only leg hint it carries.
            if prov.get("stage2_polish") is False:
                served = "deterministic"
            elif prov.get("stage2_polish") is True:
                served = "primary"
            else:
                served = "unnamed"
        counts[str(served)] = counts.get(str(served), 0) + 1
    return counts''',
    '''#: R461.5 — the row-scoped rules are shared: one resolution of a row's
#: provenance (``evals/bench/row_provenance``), three predicates over it. These
#: names stay the harness-facing API; the reading has exactly one home.
count_rows_served_by = row_provenance.count_rows_served_by''',
)

edit(
    "evals/harness/gate_validity.py",
    '''def count_deterministic_rows(rows: Any) -> int:
    """How many graded rows were served by the deterministic Stage-1 draft.

    Reads the row's OWN recorded provenance, so it works on a checkpoint that
    was written before this gate existed — ``stage2_served_by`` when present,
    else ``stage2_polish``. Returns 0 for rows that carry neither field (an
    older checkpoint), because an unknown is not evidence of an outage.
    """
    if not rows:
        return 0
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            continue
        served = prov.get("stage2_served_by")
        if served == "deterministic":
            n += 1
        elif served in (None, "") and prov.get("stage2_polish") is False:
            n += 1
    return n''',
    '''#: R422's void guard over the shared classification: the rows served by the
#: deterministic Stage-1 draft (``evals/bench/row_provenance``).
count_deterministic_rows = row_provenance.count_deterministic_rows''',
)

edit(
    "evals/harness/gate_validity.py",
    '''def degraded_row_ids(rows: Any) -> list[str]:
    """Graded rows whose Stage-2 draw did NOT come from the primary leg.

    A row whose provenance NAMES a leg other than ``primary`` was served by a
    degraded path: a fallback transport, or the deterministic Stage-1 draft the
    engine ships once the primary AND the fallback have both failed. Those are
    the rows the R423 hard gate shipped while its transport counters read clean
    on one arm — the exact class ``assess`` has to see to exclude it.

    A row that names NO leg and did not polish is the route's own deterministic
    answer (a curated intercept): it is answered without a Stage-2 call in BOTH
    arms by construction, so it is not a degradation and is left alone. That
    distinction is the whole point — :func:`count_deterministic_rows` folds the
    two together, and a caller that excluded the curated rows would drop nine
    stable, byte-identical rows from every pair.
    """
    ids: list[str] = []
    if not rows:
        return ids
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            continue
        served = prov.get("stage2_served_by")
        if served and str(served) != "primary":
            row_id = row.get("id")
            if row_id is not None:
                ids.append(str(row_id))
    return ids''',
    '''#: R423's exclusion list over the shared classification: the graded rows whose
#: named leg is not the primary one (``evals/bench/row_provenance``). A
#: fallback row is degraded HERE even though rule #8 counts the same serve as
#: lever evidence; a curated intercept (no leg named) is not degraded at all.
degraded_row_ids = row_provenance.degraded_row_ids''',
)

# --------------------------------------------------------------------------- #
# run_official_batch - the exclusion list is the shared predicate
# --------------------------------------------------------------------------- #
edit(
    "evals/regenold/run_official_batch.py",
    '''from evals.bench import metrics as bench_metrics
from evals.harness.gate_validity import (
    ArmProbe,
    assess,
    degraded_row_ids,
    lever_changes_request,
    lever_changes_system,
    lever_changes_wire,
    wire_shape_digest,
)''',
    '''from evals.bench import metrics as bench_metrics
from evals.bench.row_provenance import degraded_row_ids
from evals.harness.gate_validity import (
    ArmProbe,
    assess,
    lever_changes_request,
    lever_changes_system,
    lever_changes_wire,
    wire_shape_digest,
)''',
)

edit(
    "evals/regenold/run_official_batch.py",
    '''            # R423.2 — the rows whose graded draw did NOT come from the primary
            # leg, across EVERY generation. A single primary read-timeout with a
            # dead fallback credential ships one Stage-1 draft; the guard needs
            # those ids to EXCLUDE them from both arms instead of voiding a
            # five-hour paired gate for a hiccup the caller can account for.
            primary["degraded_ids"] = sorted({''',
    '''            # R423.2 — the rows whose graded draw did NOT come from the primary
            # leg, across EVERY generation, decided by the SHARED row-provenance
            # predicate (evals.bench.row_provenance): one reading for every gate,
            # so this list cannot diverge from the rows gate_validity excludes
            # with. A single primary read-timeout with a dead fallback credential
            # ships one Stage-1 draft; the guard needs those ids to EXCLUDE them
            # from both arms instead of voiding a five-hour paired gate for a
            # hiccup the caller can account for.
            primary["degraded_ids"] = sorted({''',
)

print("done")

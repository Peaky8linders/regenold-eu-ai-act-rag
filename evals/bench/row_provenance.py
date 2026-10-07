"""Canonical reading of one graded row's Stage-2 provenance (R461.5).

WHY ONE MODULE
--------------
Three gates used to decide, each in code of its own, what a checkpoint row's
provenance means:

* ``evals.official.paired_ab`` - hard rule #8's row ELIGIBILITY: a gold-head
  drop vetoes only on a row the arm under test was actually served, and a row
  whose provenance is missing or unreadable reads UNDECIDED, not CLEAN;
* ``evals.harness.gate_validity`` - the R422 void guard (rows that shipped the
  deterministic Stage-1 draft) and the R423 exclusion list (graded rows that
  did NOT come from the primary leg);
* ``evals.regenold.run_official_batch`` - that exclusion list pooled over every
  generation of an arm.

Read three ways, one checkpoint row could narrow a veto on one gate and widen
an exclusion on another without either gate saying so. This module is now the
only place that reads ``stage2_served_by`` / ``stage2_polish``; every row-scoped
rule above is a predicate over the one resolution below.

THE VOCABULARY
--------------
The engine (``_mark_stage2_served_by`` in ``app/engines/_graph_rag_impl.py``)
writes ``provenance.stage2_served_by`` only when a leg served the wire:

* ``primary`` - the Claude Max tunnel; the lever's payload served the row;
* ``fallback`` - Bedrock, for the SAME request payload. The lever ran there too
  (rule #8 counts it as evidence) AND the transport is degraded (R423 excludes
  it). The two directions differ ON PURPOSE: rule #8 must not exempt a row a
  lever really touched, and a gate must not read a fallback-served draw as the
  intended path;
* ``deterministic`` - both legs failed and the Stage-1 draft shipped;
* ``prior_turn`` - the truncation guard kept the previous turn's answer.

A leg NAME this module does not know is still a leg having served the wire:
rule #8 reads it as a serve (a new label must not silently widen the exemption)
and R423 as non-primary (the intended path is the primary leg). Both readings
live here.

``stage2_polish`` is the pre-R417 flag, the only hint a checkpoint written
before ``stage2_served_by`` carries: ``True`` means a Stage-2 leg polished the
row (such a checkpoint only had the primary one), ``False`` means no Stage-2
output shipped - a curated/intercepted answer, or the deterministic draft the
R422 guard counts. The flag cannot tell those two apart; both readings agree
the lever's payload did not serve the row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PRIMARY = "primary"
FALLBACK = "fallback"
DETERMINISTIC = "deterministic"
PRIOR_TURN = "prior_turn"
UNPOLISHED = "unpolished"
UNRECOGNISED = "unrecognised"
UNKNOWN = "unknown"
NO_PROVENANCE = "no_provenance"

#: The two provenance fields. Read in this module, and nowhere else that
#: decides a gate's row scope (pinned by
#: tests/test_r461_5_provenance_unification.py).
FIELD_LEG = "stage2_served_by"
FIELD_POLISH = "stage2_polish"

#: Legs whose served answer carried the lever's payload (rule #8 evidence).
SERVING_LEGS = (PRIMARY, FALLBACK)

#: Named legs that mean the Stage-2 output was DISCARDED, so the row cannot
#: testify about the lever.
DISCARDED_LEGS = (DETERMINISTIC, PRIOR_TURN)

#: Kinds whose provenance proves the lever did not serve the row.
CLOSED_KINDS = DISCARDED_LEGS + (UNPOLISHED,)

#: Kinds whose provenance cannot tell whether the lever served the row: they
#: must never read as CLEAN.
UNREADABLE_KINDS = (UNKNOWN, NO_PROVENANCE)

#: Kinds where the lever's payload served the row (rule #8 eligibility).
LEVER_RAN_KINDS = SERVING_LEGS + (UNRECOGNISED,)

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

#: A leg name this module does not know is PRINTED as primary: it is the
#: engine saying a leg served the wire, not a reason to exempt the row.
_SCOPE_OF_KIND = {UNRECOGNISED: PRIMARY}
_KNOWN_KINDS = tuple(SCOPE_REASONS) + (UNRECOGNISED,)

#: The resume census label for a row that names no leg and carries no flag.
UNNAMED = "unnamed"


@dataclass(frozen=True)
class RowProvenance:
    """One graded row's Stage-2 provenance, resolved once.

    ``kind`` is the canonical reading; ``leg`` is the verbatim leg name when
    the checkpoint names one (``""`` otherwise); ``polished`` is the strict
    tri-state of the legacy flag (``None`` when absent or not a bool).
    """

    kind: str
    leg: str = ""
    polished: bool | None = None

    @property
    def lever_ran(self) -> bool:
        """Did the lever's payload serve this row (rule #8 eligibility)?"""
        return self.kind in LEVER_RAN_KINDS

    @property
    def transport_degraded(self) -> bool:
        """Was the row served by anything other than the primary leg (R423)?

        ANY named non-primary leg is degraded, a fallback and a leg name this
        module does not know included: the exclusion asks whether the draw came
        from the intended path, not whether the lever ran.
        """
        return bool(self.leg) and self.leg != PRIMARY

    @property
    def deterministic_draft(self) -> bool:
        """Was the row served by the deterministic Stage-1 draft (R422)?"""
        return self.kind == DETERMINISTIC or (not self.leg and self.polished is False)

    @property
    def unreadable(self) -> bool:
        """Can provenance not tell whether the lever served this row?"""
        return self.kind in UNREADABLE_KINDS

    @property
    def closed(self) -> bool:
        """Does provenance prove the lever did not serve this row?"""
        return self.kind in CLOSED_KINDS


def _polish(prov: dict) -> bool | None:
    """The legacy flag as a strict tri-state: True, False, or None."""
    value = prov.get(FIELD_POLISH)
    if value is True:
        return True
    if value is False:
        return False
    return None


def classify(prov: Any) -> RowProvenance:
    """Resolve one row's ``provenance`` value into the canonical reading.

    Accepts the raw value as stored on a checkpoint row; never raises on a
    missing / malformed one. ``None`` (no provenance) and a non-mapping are
    distinct kinds, because the report says which of the two it saw.
    """
    if prov is None:
        return RowProvenance(kind=NO_PROVENANCE)
    if not isinstance(prov, dict):
        return RowProvenance(kind=UNKNOWN)
    polished = _polish(prov)
    raw = prov.get(FIELD_LEG)
    if raw not in (None, ""):
        leg = str(raw)
        kind = leg if leg in SCOPE_REASONS else UNRECOGNISED
        return RowProvenance(kind=kind, leg=leg, polished=polished)
    if polished is True:
        return RowProvenance(kind=PRIMARY, polished=True)
    if polished is False:
        return RowProvenance(kind=UNPOLISHED, polished=False)
    return RowProvenance(kind=UNKNOWN)


def scope_reason(prov: Any) -> str:
    """Rule #8's reason for one row, in the :data:`SCOPE_REASONS` vocabulary."""
    kind = classify(prov).kind
    return _SCOPE_OF_KIND.get(kind, kind)


def lever_ran_reason(reason: str) -> bool:
    """Rule #8 eligibility from a reason string (paired_ab's reading).

    Reasons outside the vocabulary keep the historical reading: not closed, so
    still eligible - an unknown reason must not silently exempt a row.
    """
    if reason in _KNOWN_KINDS:
        return reason in LEVER_RAN_KINDS
    return reason not in CLOSED_KINDS


def leg_label(prov: Any) -> str:
    """The leg name coerced the way a GATE compares it: stripped, casefolded.

    ``RowProvenance.leg`` is the verbatim spelling, which is what a report
    prints; a refusal or exclusion decision needs the folded form, because a
    checkpoint's capitalisation must not decide it. ``""`` when the checkpoint
    names no leg (a falsy non-string included), so a caller can test the
    absence with a plain ``not``.

    Use this rather than reading :data:`FIELD_LEG`: the one-home contract in
    ``tests/test_r461_5_provenance_unification.py`` scans for the raw read, and
    only this module is allowed to do it.
    """
    if not isinstance(prov, dict):
        return ""
    return str(prov.get(FIELD_LEG) or "").strip().casefold()


def polish_flag(prov: Any) -> bool | None:
    """The legacy ``stage2_polish`` as a strict tri-state, safe on any shape.

    The counterpart of :func:`leg_label` for the second field: :func:`classify`
    already exposes it as ``RowProvenance.polished``, and this is the same
    reading for a caller that needs the flag without a leg decision.
    """
    return _polish(prov) if isinstance(prov, dict) else None


def served_leg(prov: Any) -> str:
    """The leg label the resume census counts this row under.

    Named legs count under their own name; a pre-field row counts under the
    legacy flag's serve (``primary`` when polished, ``deterministic`` when
    not); anything else is ``unnamed``.
    """
    resolved = classify(prov)
    if resolved.leg:
        return resolved.leg
    if resolved.polished is True:
        return PRIMARY
    if resolved.polished is False:
        return DETERMINISTIC
    return UNNAMED


def count_rows_served_by(rows: Any) -> dict[str, int]:
    """Which leg served each graded row, counted off the rows' own provenance.

    The distinction matters for a RESUMED arm: in-process transport counters
    restart at zero, so a resumed arm looks like one that produced nothing,
    when in fact every row on disk records a serve.
    """
    counts: dict[str, int] = {}
    if not rows:
        return counts
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = served_leg(row.get("provenance"))
        counts[label] = counts.get(label, 0) + 1
    return counts


def count_deterministic_rows(rows: Any) -> int:
    """How many graded rows were served by the deterministic Stage-1 draft.

    Reads the row's OWN recorded provenance, so it works on a checkpoint
    written before this guard existed; rows that carry neither a leg name nor
    the legacy flag return 0 (an unknown is not evidence of an outage).
    """
    if not rows:
        return 0
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if classify(row.get("provenance")).deterministic_draft:
            n += 1
    return n


def degraded_row_ids(rows: Any) -> list[str]:
    """Graded rows whose Stage-2 draw did NOT come from the primary leg.

    A row whose provenance NAMES a leg other than ``primary`` was served by a
    degraded path: a fallback transport, or a leg drawn after both legs failed.
    Those are the rows the R423 hard gate shipped while its transport counters
    read clean on one arm.

    A row that names NO leg and did not polish is the route's own answer (a
    curated intercept): it is answered without a Stage-2 call in BOTH arms by
    construction, so it is not a degradation and is left alone. A caller that
    excluded the curated rows would drop nine stable, byte-identical rows from
    every pair.
    """
    ids: list[str] = []
    if not rows:
        return ids
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not classify(row.get("provenance")).transport_degraded:
            continue
        row_id = row.get("id")
        if row_id is not None:
            ids.append(str(row_id))
    return ids

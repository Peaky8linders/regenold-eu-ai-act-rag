"""R425 — the void guard needs a THIRD slot: the emitted reference list.

R422 taught ``assess`` that a flag which never reached the wire must not read as a
null, and R424 generalised it to a lever that lives ABOVE the engine (the
conversation the harness posts): there the system slot is SUPPOSED to be
byte-identical, so non-vacuity moved to the recorded request shape.

R425 is one step further out again. ``REGENOLD_GROUND_WIRE_SUBPOINTS`` rewrites
the ``references`` list AFTER Stage-2 has landed, so **nothing** the transport
sees differs between the arms — identical system payloads, identical user
payloads, identical request shape. Under the two existing slots the guard either
voids a correctly-built run (system slot) or reports a clean null for an inert
call site (no slot armed). Both are the R329/R330/R397 failure class.

So the non-vacuity proof moves to the emitted reference sets
(:func:`gate_validity.wire_shape_digest`), under the same standard as the other
slots: the two arms must have RECORDED a difference in the slot under test.
"""

from __future__ import annotations

import json
from typing import Any

from evals.harness import gate_validity

FLAG = "REGENOLD_GROUND_WIRE_SUBPOINTS"


def _wire(*specs: tuple[str, str, list[str]]) -> str:
    """A recorded emission payload: ``(row id, answer, references)`` per row."""
    return gate_validity.wire_shape_digest(
        [
            {"id": rid, "pred_answer": answer, "pred_refs": list(refs)}
            for rid, answer, refs in specs
        ]
    )


#: A lever that rewrites a limb on a row whose ANSWER is unchanged, plus a row
#: whose answer is unchanged AND whose references are unchanged (untouched).
_OFF = _wire(("r1", "same answer", ["Article 6.2"]), ("r2", "other", ["Article 9.2"]))
_ON = _wire(("r1", "same answer", ["Article 6.3"]), ("r2", "other", ["Article 9.2"]))


def _prov(
    label: str,
    *,
    wire_shape: str = "",
    request_shape: str = "fixed:cb85452c9c041721",
    system_hash: str = "aaa",
    rows: int = 30,
) -> gate_validity.ArmProvenance:
    stats: dict[str, Any] = {
        "primary_attempts": rows,
        "primary_ok": rows,
        "primary_failed": 0,
        "fallback_attempts": 0,
        "fallback_ok": 0,
        "fallback_failed": 0,
        "refused": 0,
        "refused_by_provider": {},
    }
    return gate_validity.ArmProvenance(
        label=label,
        rows=rows,
        deterministic_graded=0,
        stats=stats,
        system_hashes=(system_hash,),
        user_hashes=("uuu",),
        system_lengths=(3,),
        calls=rows,
        rows_served={"primary": rows},
        request_shape=request_shape,
        wire_shape=wire_shape,
    )


# -- the declaration ---------------------------------------------------------


def test_the_flag_is_declared_as_a_wire_slot_flag() -> None:
    assert FLAG in gate_validity.WIRE_SLOT_FLAGS


def test_lever_changes_wire_reads_the_declaration() -> None:
    assert gate_validity.lever_changes_wire({}, {})[0] is False
    assert gate_validity.lever_changes_wire({FLAG: "0"}, {FLAG: "1"})[0] is True
    # It must NOT be mistaken for either of the other two slots, or the guard
    # would ask the wrong question of the run.
    assert gate_validity.lever_changes_system({FLAG: "0"}, {FLAG: "1"})[0] is False
    assert gate_validity.lever_changes_request({FLAG: "0"}, {FLAG: "1"})[0] is False


# -- the digest --------------------------------------------------------------


def test_the_digest_is_order_insensitive_within_a_row_but_row_keyed() -> None:
    a = gate_validity.wire_shape_digest([{"id": "r1", "pushback_refs": ["Article 6.2", "Annex I"]}])
    b = gate_validity.wire_shape_digest([{"id": "r1", "pushback_refs": ["Annex I", "Article 6.2"]}])
    c = gate_validity.wire_shape_digest([{"id": "r1", "pushback_refs": ["Article 6.3", "Annex I"]}])
    d = gate_validity.wire_shape_digest([{"id": "r2", "pushback_refs": ["Article 6.2", "Annex I"]}])
    assert a == b, "the same set in a different order is the same emission"
    assert a != c, "a rewritten limb must change the digest"
    assert a != d, "the row id must be part of the signature"


def test_the_digest_falls_back_to_the_turn_one_field() -> None:
    """A checkpoint that predates the pushback fields still signs its emission."""
    assert gate_validity.wire_shape_digest([{"id": "r1", "references": ["Article 6"]}]) == (
        gate_validity.wire_shape_digest([{"id": "r1", "pushback_refs": ["Article 6"]}])
    )


def test_an_empty_row_set_has_no_digest() -> None:
    """An unobservable slot must read as unobserved, never as 'identical'."""
    assert gate_validity.wire_shape_digest([]) == ""
    assert gate_validity.wire_shape_digest(None) == ""


# -- the verdict -------------------------------------------------------------


def test_wire_slot_lever_with_different_emissions_is_valid() -> None:
    verdict = gate_validity.assess(
        base=_prov("A", wire_shape=_OFF),
        branch=_prov("B", wire_shape=_ON),
        lever=False,
        lever_slot="wire",
    )
    assert verdict.valid, verdict.reasons
    assert verdict.wire_checked and not verdict.system_checked
    assert verdict.wire_attributed == 1, "r1 is the row the lever can be SEEN on"
    # Identical dispatched payloads are the EXPECTED outcome of a wire-slot lever,
    # so they must not be reported as if the lever had failed to reach the wire.
    assert not any("system payload" in w for w in verdict.warnings)


def test_wire_slot_lever_with_identical_emissions_voids() -> None:
    """The whole point: an inert call site must not read as a clean null."""
    verdict = gate_validity.assess(
        base=_prov("A", wire_shape=_OFF),
        branch=_prov("B", wire_shape=_OFF),
        lever=False,
        lever_slot="wire",
    )
    assert not verdict.valid
    assert any("emitted reference sets were IDENTICAL" in r for r in verdict.reasons)


def test_draw_variance_alone_does_not_license_a_wire_slot_delta() -> None:
    """A wire difference the ANSWER also explains is not the lever.

    At ``--repeats 1`` the two arms draw independent Stage-2 samples, so an inert
    lever still shows different references. The guard must refuse that run rather
    than read it as a valid non-null.
    """
    base = _wire(("r1", "draw one", ["Article 6.2"]))
    branch = _wire(("r1", "draw two", ["Article 6.3"]))
    verdict = gate_validity.assess(
        base=_prov("A", wire_shape=base),
        branch=_prov("B", wire_shape=branch),
        lever=False,
        lever_slot="wire",
    )
    assert not verdict.valid
    assert any(
        "also drew a DIFFERENT answer" in r and "--repeats >= 2" in r
        for r in verdict.reasons
    )


def test_one_same_answer_row_is_enough_to_license_the_delta() -> None:
    """The rule is an EXISTENCE check: a single attributable row licenses a run."""
    base = _wire(("r1", "draw one", ["Article 6.2"]), ("r2", "stable", ["Article 9.2"]))
    branch = _wire(("r1", "draw two", ["Article 6.3"]), ("r2", "stable", ["Article 9.3"]))
    verdict = gate_validity.assess(
        base=_prov("A", wire_shape=base),
        branch=_prov("B", wire_shape=branch),
        lever=False,
        lever_slot="wire",
    )
    assert verdict.valid, verdict.reasons
    assert verdict.wire_attributed == 1


def test_wire_slot_lever_without_a_recorded_emission_voids() -> None:
    verdict = gate_validity.assess(
        base=_prov("A", wire_shape=""),
        branch=_prov("B", wire_shape=_ON),
        lever=False,
        lever_slot="wire",
    )
    assert not verdict.valid
    assert any("could not be observed" in r for r in verdict.reasons)


def test_an_unreadable_emission_record_voids_rather_than_passing() -> None:
    verdict = gate_validity.assess(
        base=_prov("A", wire_shape="aaaa"),
        branch=_prov("B", wire_shape=_ON),
        lever=False,
        lever_slot="wire",
    )
    assert not verdict.valid
    assert any("could not be observed" in r for r in verdict.reasons)


def test_a_system_slot_lever_still_wins_the_slot_priority() -> None:
    """The system check is the strongest; declaring a wire flag cannot weaken it."""
    verdict = gate_validity.assess(
        base=_prov("A", wire_shape=_OFF),
        branch=_prov("B", wire_shape=_ON),
        lever=(True, "arm env differs on system-slot flag(s): X"),
        lever_slot="system",
    )
    assert not verdict.valid
    assert any("system payloads were IDENTICAL" in r for r in verdict.reasons)


def test_the_wire_shape_survives_the_round_trip_that_lets_a_run_be_re_judged() -> None:
    prov = _prov("A", wire_shape="cafebabe")
    rebuilt = gate_validity.ArmProvenance.from_dict(prov.as_dict())
    assert rebuilt.wire_shape == prov.wire_shape


def test_the_verdict_records_which_slot_was_checked() -> None:
    payload = gate_validity.assess(
        base=_prov("A", wire_shape=_OFF),
        branch=_prov("B", wire_shape=_ON),
        lever=False,
        lever_slot="wire",
    ).as_dict()
    assert payload["wire_checked"] is True
    assert payload["wire_attributed"] == 1
    assert payload["system_checked"] is False
    assert payload["request_checked"] is False
    json.dumps(payload)

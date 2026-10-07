"""R443 — EvoOntology phase-2 read-only browse/resolve adapters.

These tests hold the two things that matter about a shadow-only artifact: that
its contract is bounded and existence-checked, and that it cannot reach the
answer surface.  The experiment's *result* (a falsification) is pinned too, so a
future fix to the diagnosed defects is a deliberate, visible change rather than
a silent drift.
"""
from __future__ import annotations

import pathlib

import pytest

from app.data.kb_xrefs import cross_refs
from app.data.ontology_browse import (
    CONCEPT_KINDS,
    DEFAULT_BROWSE_LIMIT,
    KIND_RISK,
    KIND_ROLE,
    MAX_ANCHORS_PER_CONCEPT,
    MAX_BROWSE_LIMIT,
    MAX_CANDIDATES,
    adapter_candidates,
    anchor_exists,
    browse_concepts,
    detect_roles,
    mark_used,
    reset_shadow_trace,
    resolve_concept,
    risk_hints,
    shadow_trace,
    to_internal,
    to_wire,
)
from app.data.ontology_evidence import OntologyEvidence

REPO = pathlib.Path(__file__).resolve().parents[1]

# rg_002's real question — the row whose manifest the experiment measured empty.
RG_002 = (
    "Does the obligation to indicate that deep-fakes are artificially generated "
    "apply when prosecuting a criminal offence?"
)
RG_069 = (
    "I am a distributor of an AI systems. Do I have obligation not to jeopardize "
    "its conformity? I was not told if the system is high-risk."
)


# ── form normalisation (the cross-surface defect the adapter exposed) ────


def test_wire_and_internal_forms_round_trip() -> None:
    assert to_wire("Art. 13") == "Article 13"
    assert to_internal("Article 13.3") == "Art. 13.3"
    assert to_wire("Annex III.1") == "Annex III.1"
    # Idempotent, so callers never need to know which form they hold.
    assert to_wire(to_wire("Art. 5")) == "Article 5"
    assert to_internal(to_internal("Article 5")) == "Art. 5"


def test_cross_reference_graph_is_keyed_on_the_internal_form() -> None:
    """Pins why the conversion exists: the xref graph is not wire-keyed."""
    assert cross_refs("Art. 13", limit=5) != ()
    assert cross_refs("Article 13", limit=5) == ()


# ── bounded, existence-checked manifest ──────────────────────────────────


def test_browse_is_bounded_even_when_the_caller_asks_for_more() -> None:
    refs = browse_concepts("prohibited social scoring and biometric categorisation", limit=999)
    assert len(refs) <= MAX_BROWSE_LIMIT
    assert len(refs) >= 1


def test_browse_default_and_explicit_kind_filter() -> None:
    refs = browse_concepts(RG_069, kind=KIND_ROLE)
    assert refs and all(ref.kind == KIND_ROLE for ref in refs)
    assert len(refs) <= DEFAULT_BROWSE_LIMIT


def test_unknown_kind_is_rejected_not_ignored() -> None:
    with pytest.raises(ValueError):
        browse_concepts("anything", kind="not_a_kind")


@pytest.mark.parametrize("question", [RG_002, RG_069, "high-risk medical device under the MDR"])
def test_every_returned_anchor_exists_in_the_regulation(question: str) -> None:
    for ref in browse_concepts(question, limit=MAX_BROWSE_LIMIT):
        assert ref.anchors, ref.concept_id
        for anchor in ref.anchors:
            assert anchor_exists(anchor), anchor


def test_anchor_cap_per_concept_is_enforced() -> None:
    refs = browse_concepts("high-risk AI system under Annex III", kind=KIND_RISK, limit=4)
    for ref in refs:
        assert len(ref.anchors) <= MAX_ANCHORS_PER_CONCEPT


# ── resolve ──────────────────────────────────────────────────────────────


def test_unknown_concept_id_resolves_false_with_no_fabricated_anchor() -> None:
    for concept_id in ("practice:does_not_exist", "risk_class:not_a_class", "garbage", ""):
        record = resolve_concept(concept_id)
        assert record.resolved is False
        assert record.anchors == ()


def test_resolved_record_carries_evidence_records_on_request() -> None:
    record = resolve_concept(f"{KIND_RISK}:limited_risk", include_evidence=True)
    assert record.resolved
    assert record.evidence
    for item in record.evidence:
        assert isinstance(item, OntologyEvidence)
        assert item.source_id == "eur-lex-ai-act-consolidated"
        assert item.source_version
        assert item.quote.strip()
        assert len(item.content_hash) == 64


def test_resolve_omits_evidence_unless_asked() -> None:
    assert resolve_concept(f"{KIND_RISK}:limited_risk").evidence == ()


def test_role_concept_without_a_risk_hint_still_resolves() -> None:
    """A role question with no risk tier anchors on Art. 3, not on every tier."""
    record = resolve_concept(f"{KIND_ROLE}:distributor:unknown")
    assert record.resolved
    assert record.anchors == ("Article 3",)


# ── deterministic hints ──────────────────────────────────────────────────


def test_specific_roles_outrank_the_generic_provider_noun() -> None:
    roles = [role.value for role in detect_roles(RG_069)]
    assert roles[0] == "distributor", roles
    assert "provider" not in roles
    # The same question with a provider noun still surfaces the specific party,
    # because the more specific patterns are matched first.
    mixed = detect_roles("A distributor that is not the provider must verify the CE marking.")
    assert [role.value for role in mixed][0] == "distributor"


def test_risk_hints_are_ordered_by_precedence() -> None:
    hints = [risk.value for risk in risk_hints(
        "a prohibited social scoring system that is also high-risk under Annex III"
    )]
    assert hints[0] == "prohibited"
    assert "high_risk_annex_iii" in hints


# ── the comparison arm ───────────────────────────────────────────────────


def test_adapter_candidates_is_bounded_and_deterministic() -> None:
    first = adapter_candidates("high-risk AI system under Annex III")
    second = adapter_candidates("high-risk AI system under Annex III")
    assert first == second
    assert len(first) <= MAX_CANDIDATES
    assert all(anchor_exists(ref) for ref in first)


# ── the falsified result, pinned ─────────────────────────────────────────


def test_rg_002_manifest_is_empty_this_is_the_measured_defect() -> None:
    """R443 measured a vacuous manifest here: sub-point recall 1.00 -> 0.00.

    Cause, diagnosed in the checkpoint: the limited-risk marker's
    ``\\bdeep[\\s-]?fake\\b`` cannot match the plural ``deep-fakes``.  Pinned so
    the eventual fix is deliberate.
    """
    assert risk_hints(RG_002) == ()
    assert browse_concepts(RG_002) == ()
    assert adapter_candidates(RG_002) == ()


def test_risk_class_resolves_to_the_duty_union_this_is_the_precision_cost() -> None:
    """The other diagnosed defect: a risk tier is not the engaged branch."""
    record = resolve_concept(f"{KIND_RISK}:high_risk_annex_iii")
    assert record.resolved
    assert len(record.anchors) >= 20  # the provider's full Chapter III duty set
    assert "Article 9" in record.anchors
    assert "Annex III" in record.anchors


# ── shadow telemetry ─────────────────────────────────────────────────────


def test_shadow_trace_records_activity_and_mark_used_is_intersection() -> None:
    reset_shadow_trace()
    refs = browse_concepts(RG_069, limit=4)
    assert refs
    trace = shadow_trace()
    assert trace.calls >= 1
    assert trace.browsed

    # Head-grain: the wire's "Article 24.3" does use the browsed "Article 24".
    used = mark_used(("Article 24", "Article 99"), ("Article 24.3", "Article 3"))
    assert used == ("Article 24",)
    assert shadow_trace().used == ["Article 24"]
    assert mark_used(("Art. 24",), ("Article 24",)) == ("Article 24",)

    reset_shadow_trace()
    assert shadow_trace().calls == 0
    assert shadow_trace().browsed == []


def test_concept_kinds_are_the_documented_closed_set() -> None:
    assert set(CONCEPT_KINDS) == {
        "provision",
        "practice",
        "annex_iii_category",
        "risk_class",
        "phase",
        "role_obligation",
    }


# ── the shadow state is not on the answer surface ────────────────────────


def _app_files_mentioning(token: str, *, allowed: set[str]) -> list[str]:
    """Files under ``app/`` (outside ``allowed``) whose source names ``token``."""
    return [
        rel
        for path in sorted((REPO / "app").rglob("*.py"))
        if (rel := path.relative_to(REPO).as_posix()) not in allowed
        and token in path.read_text(encoding="utf-8")
    ]


def test_browse_module_is_not_imported_by_the_application() -> None:
    """Phase 2 is shadow-only: nothing under ``app/`` may import it.

    The one permitted reference is the phase-3 ledger, which uses
    ``resolve_concept`` offline to check proposal targets; that the ledger is
    itself unreachable is asserted in ``tests/test_r444_ontology_ledger.py``.
    """
    offenders = _app_files_mentioning(
        "ontology_browse",
        allowed={"app/data/ontology_browse.py", "app/data/ontology_ledger.py"},
    )
    assert not offenders, f"ontology_browse leaked into the application: {offenders}"


def test_no_runtime_flag_was_added_for_the_adapter() -> None:
    """A shadow adapter ships no env flag; wiring it would need the phase-4 gate."""
    assert not _app_files_mentioning("ONTOLOGY_BROWSE", allowed=set())

"""R444 — the phase-3 attribution ledger: classification, rules and refusals.

The rule tests pin *why* a layer is named, using synthetic facts so each branch
of the rule table is exercised deterministically.  One test replays the judge
classifier over the recorded R436 judge cache, so a change that leaves a real
remark untyped fails loudly.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.data.ontology_evidence import OntologyPatchProposal
from app.data.ontology_ledger import (
    AttributionTarget,
    FailureKind,
    FailureSignature,
    NonDegradedRecheck,
    SignatureFacts,
    SignatureOrigin,
    attribute_signature,
    build_ledger,
    classify_judge_remark,
    criterion_refs,
    evidence_record,
    fabricated_targets,
    head_of,
    propose_patch,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
CACHE = REPO / "docs/measurements/r436/judge-cache-r436-bedrock.jsonl"
GOLD = REPO / "docs/measurements/r388/official_gold_n110.jsonl"


def sa_basis_sha(row: dict) -> str:
    grounding = row.get("expected_refs") or row.get("_fallback_refs") or []
    basis = "\n".join(str(c) for c in (row.get("criteria") or []))
    basis += "\n--\n" + "\n".join(str(ref) for ref in grounding)
    import hashlib
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def _sig(
    kind: FailureKind,
    facts: SignatureFacts | None = None,
    *,
    origin: SignatureOrigin = SignatureOrigin.JUDGE,
    observed: str = "",
    signature_id: str = "sig:test",
) -> FailureSignature:
    return FailureSignature(
        signature_id=signature_id,
        kind=kind,
        origin=origin,
        title="t",
        observed=observed,
        facts=facts or SignatureFacts(),
    )


# ── classification ───────────────────────────────────────────────────────


def test_every_failed_criterion_on_the_board_is_classified() -> None:
    """Classification coverage is reported, not assumed: no remark is untyped."""
    gold = {
        json.loads(line)["id"]: json.loads(line)
        for line in GOLD.open(encoding="utf-8")
        if line.strip()
    }
    unclassified: list[str] = []
    total = 0
    for entry in (json.loads(line) for line in CACHE.open(encoding="utf-8") if line.strip()):
        row_id = entry["key"].split(":")[0]
        basis_sha = entry.get("verdict", {}).get("_basis_sha")
        if basis_sha is not None and basis_sha != sa_basis_sha(gold[row_id]):
            continue  # stale cache verdict for a now source-corrected gold row
        criteria = gold[row_id]["criteria"]
        verdict = entry["verdict"]
        for index, (ok, remark) in enumerate(
            zip(verdict["criteria"], verdict["criterion_remarks"], strict=False)
        ):
            if ok:
                continue
            total += 1
            kind, matched = classify_judge_remark(criteria[index], remark)
            assert matched, "a classified remark must record the phrase that decided it"
            if kind is FailureKind.UNCLASSIFIED:
                unclassified.append(f"{row_id}#{index}")
    assert total == 20, f"the source-corrected board has 20 eligible failed criteria, measured {total}"
    assert not unclassified, f"unclassified: {unclassified}"
    # and the untyped-signature rule still has to exist for evidence that no rule fits
    kind, _ = classify_judge_remark("Nothing here matches", "the answer is simply wrong")
    assert kind is FailureKind.UNCLASSIFIED


@pytest.mark.parametrize(
    ("criterion", "remark", "expected"),
    [
        (
            "Yes, obligation applies regardless of high-risk knowledge",
            "The answer states the obligation applies only if the system is high-risk, "
            "contradicting the criterion.",
            FailureKind.VERDICT_POLARITY_FLIP,
        ),
        (
            "The record-keeping duty is stated in Article 12(1)",
            "The candidate answer places the duty in Article 11(1), but the criterion "
            "requires substance regarding Article 12(1); referencing a different "
            "provision does not satisfy the criterion.",
            FailureKind.WRONG_PROVISION_BINDING,
        ),
        (
            "Presumption is limited to the extent required by the intended purpose",
            "The answer does not state that the presumption is limited to the extent required "
            "by the intended purpose; this limiting condition is not mentioned.",
            FailureKind.MISSING_CONSTRAINT,
        ),
        (
            "Four steps: identify/analyze risks (9(2)(a)); estimate risks (9(2)(b))",
            "Although the answer references the steps in Article 9(2), it does not clearly list "
            "them as a coherent sequence.",
            FailureKind.OMITTED_ENUMERATED_ITEM,
        ),
        (
            "Contact details of the provider and of the authorised representative (Annex VIII, "
            "Section A, points 1 to 3)",
            "The answer implies contact details but does not explicitly state the requirement.",
            FailureKind.OMITTED_ENUMERATED_ITEM,
        ),
        (
            "Drone AI identifying people in public = remote biometric identification",
            "The answer does not address remote biometric identification in public spaces; it "
            "omits the substance of this criterion entirely.",
            FailureKind.MISSING_TERM,
        ),
    ],
)
def test_remark_classification_is_ordered_and_evidence_recording(
    criterion: str, remark: str, expected: FailureKind
) -> None:
    kind, matched = classify_judge_remark(criterion, remark)
    assert kind is expected
    assert matched


def test_a_limiting_condition_outranks_a_remark_that_says_incorrectly_treats() -> None:
    """The criterion's own shape wins: 'is not excused' is the constraint, not the phrasing."""
    kind, _ = classify_judge_remark(
        "Article 26(1) requires use in accordance with instructions for use; deviating from "
        "intended use is not excused merely because that use alone wouldn't trigger Annex III",
        "The candidate answer incorrectly treats the high-risk classification as use-dependent.",
    )
    assert kind is FailureKind.MISSING_CONSTRAINT


@pytest.mark.parametrize(
    ("criterion", "expected"),
    [
        ("Logging is required under Article 12(1)", ("Article 12.1",)),
        ("Annex III (healthcare access/provision)", ("Annex III",)),
        ("Grounds: Article 6(3), point (a)", ("Article 6.3",)),
        ("No coordinate here at all", ()),
    ],
)
def test_criterion_refs_are_deterministic(criterion: str, expected: tuple[str, ...]) -> None:
    assert criterion_refs(criterion) == expected


def test_head_of_collapses_articles_and_annexes() -> None:
    assert head_of("Article 26.1") == "Article 26"
    assert head_of("Annex VIII.a") == "Annex VIII"
    assert head_of("Article 9") == "Article 9"


# ── attribution rules ────────────────────────────────────────────────────


def test_degraded_leg_outranks_everything_and_gets_no_patch() -> None:
    sig = _sig(
        FailureKind.MISSING_CONSTRAINT,
        SignatureFacts(
            rows=("rg_036",),
            criteria=("rg_036#1",),
            legs=("deterministic",),
            engaged_refs=("Article 10.3",),
            engaged_heads=("Article 10",),
            cited_refs=("Article 10.4",),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.TRANSPORT
    assert attribution.layer is None
    assert propose_patch(sig, attribution, parent_snapshot="kb:test") is None


def _recheck(**kwargs) -> NonDegradedRecheck:
    base = {
        "leg": "primary",
        "artifact": "evals/bench/results/official-r444-transport-recheck-hard.ckpt.jsonl",
        "judge_identity": "bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3",
        "rows": ("rg_036",),
        "criteria_retested": ("rg_036#0",),
        "criteria_still_failing": (),
    }
    return NonDegradedRecheck(**{**base, **kwargs})


def test_a_recheck_that_recovers_everything_keeps_transport_and_says_so() -> None:
    """The falsifier is only as good as its record: a clean retest must be quoted."""
    sig = _sig(
        FailureKind.MISSING_CONSTRAINT,
        SignatureFacts(
            rows=("rg_036",),
            criteria=("rg_036#0",),
            legs=("deterministic",),
            engaged_refs=("Article 10.3",),
            engaged_heads=("Article 10",),
            recheck=_recheck(),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.TRANSPORT
    assert "falsifier was" not in attribution.rationale
    assert "1/1 criteria recovered" in attribution.rationale
    assert propose_patch(sig, attribution, parent_snapshot="kb:test") is None


def test_a_surviving_criterion_overturns_transport_and_is_attributed() -> None:
    """A criterion that still fails with no degradation present is not transport."""
    sig = _sig(
        FailureKind.WRONG_PROVISION_BINDING,
        SignatureFacts(
            rows=("rg_036",),
            criteria=("rg_036#0",),
            legs=("deterministic",),
            engaged_refs=("Article 10.3",),
            engaged_heads=("Article 10",),
            recheck=_recheck(criteria_still_failing=("rg_036#0",)),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.CONTENT
    assert "falsified by measurement" in attribution.rationale
    assert "draw-dependent" in attribution.falsifier
    assert propose_patch(sig, attribution, parent_snapshot="kb:test") is not None


def test_a_recheck_on_another_degraded_leg_is_refused() -> None:
    """A retest that is itself a degradation is not evidence and proves nothing."""
    sig = _sig(
        FailureKind.MISSING_CONSTRAINT,
        SignatureFacts(
            rows=("rg_036",),
            criteria=("rg_036#0",),
            legs=("deterministic",),
            engaged_refs=("Article 10.3",),
            engaged_heads=("Article 10",),
            recheck=_recheck(leg="prior_turn", criteria_still_failing=("rg_036#0",)),
        ),
    )
    assert not sig.facts.recheck.usable
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.TRANSPORT
    assert attribution.layer is None


def test_recheck_derivations_are_measured_not_assumed() -> None:
    recheck = _recheck(criteria_retested=("a#0", "a#1"), criteria_still_failing=("a#1",))
    assert recheck.recovered == ("a#0",)
    assert recheck.any_survives
    assert not recheck.all_recovered
    assert "1/2 criteria recovered" in recheck.summary()
    assert not _recheck().any_survives
    assert _recheck().all_recovered
    assert not _recheck(criteria_retested=()).usable


def test_degraded_leg_rule_does_not_apply_to_offline_probe_signatures() -> None:
    """A probe's evidence is not the graded answer, so the leg cannot disqualify it."""
    sig = _sig(
        FailureKind.OMITTED_ENUMERATED_ITEM,
        SignatureFacts(
            rows=("rg_037",),
            legs=("deterministic",),
            engaged_refs=("Annex VIII.a",),
            engaged_heads=("Annex VIII",),
            catalog_missing_refs=("Annex VIII.a",),
        ),
        origin=SignatureOrigin.PROBE,
    )
    assert attribute_signature(sig).target is AttributionTarget.CONTENT


def test_a_coordinate_the_catalog_cannot_represent_is_content() -> None:
    sig = _sig(
        FailureKind.OMITTED_ENUMERATED_ITEM,
        SignatureFacts(
            rows=("rg_037",),
            engaged_refs=("Annex VIII.a",),
            engaged_heads=("Annex VIII",),
            catalog_missing_refs=("Annex VIII.a",),
        ),
        origin=SignatureOrigin.PROBE,
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.CONTENT
    assert "Annex VIII.a" in attribution.rationale


def test_an_untyped_signature_with_no_coordinate_is_reported_as_a_coverage_gap() -> None:
    sig = _sig(FailureKind.UNCLASSIFIED, SignatureFacts(rows=("rg_007",)))
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.UNATTRIBUTED
    assert attribution.layer is None


def test_a_polarity_flip_is_a_statement_error_not_a_grain_claim() -> None:
    sig = _sig(
        FailureKind.VERDICT_POLARITY_FLIP,
        SignatureFacts(
            rows=("rg_069",),
            legs=("primary",),
            engaged_refs=("Article 24.3",),
            engaged_heads=("Article 24",),
            reachable_refs=("Article 24.2",),
            cited_refs=("Article 24.4",),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.GENERATION
    assert "no grain or retrieval claim" in attribution.rationale


def test_role_duty_without_a_detected_role_is_content() -> None:
    """rg_088's shape: the question says 'we deployed', no role noun, Art. 26 is a duty."""
    sig = _sig(
        FailureKind.VERDICT_POLARITY_FLIP,
        SignatureFacts(
            rows=("rg_088",),
            legs=("primary",),
            engaged_refs=("Article 26.1", "Article 26.6"),
            engaged_heads=("Article 26",),
            any_role_refs=("Article 26", "Article 27"),
            any_role_heads=("Article 26", "Article 27"),
            describes_actor=True,
            reachable_refs=("Article 6",),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.CONTENT
    assert "surface-to-role value" in attribution.rationale


def test_role_rule_is_blocked_when_the_role_was_detected() -> None:
    """A detected role means the role rule must not claim the mechanism."""
    sig = _sig(
        FailureKind.MISSING_CONSTRAINT,
        SignatureFacts(
            rows=("rg_062",),
            legs=("primary",),
            engaged_refs=("Article 24.2",),
            engaged_heads=("Article 24",),
            role_refs=("Article 24", "Article 25"),
            role_heads=("Article 24", "Article 25"),
            any_role_refs=("Article 24",),
            any_role_heads=("Article 24",),
            describes_actor=True,
        ),
    )
    assert not sig.facts.role_duty_head_unbound
    assert "surface-to-role value" not in attribute_signature(sig).rationale


def test_role_rule_is_blocked_when_the_question_names_no_actor() -> None:
    """rg_087 asks what Article 9 says; a role-detection claim would be false there."""
    sig = _sig(
        FailureKind.OMITTED_ENUMERATED_ITEM,
        SignatureFacts(
            rows=("rg_087",),
            legs=("primary",),
            engaged_refs=("Article 9",),
            engaged_heads=("Article 9",),
            any_role_refs=("Article 9",),
            any_role_heads=("Article 9",),
            reachable_refs=("Article 9",),
            describes_actor=False,
        ),
    )
    assert attribute_signature(sig).target is AttributionTarget.GENERATION


def test_a_limb_that_never_entered_the_context_is_a_grain_gap() -> None:
    sig = _sig(
        FailureKind.MISSING_TERM,
        SignatureFacts(
            rows=("rg_062",),
            legs=("primary",),
            engaged_refs=("Article 24.2",),
            engaged_heads=("Article 24",),
            cited_refs=("Article 24.4",),
            cited_heads=("Article 24",),
            reachable_refs=("Article 24.4",),
            reachable_heads=("Article 24",),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.CONTENT
    assert "unreached by both retrieval arms" in attribution.rationale


def test_a_reachable_and_named_limb_falls_through_to_generation() -> None:
    sig = _sig(
        FailureKind.MISSING_CONSTRAINT,
        SignatureFacts(
            rows=("rg_075",),
            legs=("primary",),
            engaged_refs=("Article 50.4",),
            engaged_heads=("Article 50",),
            cited_refs=("Article 50.4",),
            cited_heads=("Article 50",),
            mentioned_refs=("Article 50.4",),
            reachable_refs=("Article 50.4",),
            reachable_heads=("Article 50",),
        ),
    )
    assert attribute_signature(sig).target is AttributionTarget.GENERATION


def test_no_measured_path_is_content_but_scopes_its_claim() -> None:
    """A head-grain coordinate nobody reaches, declares or names: no mapping path."""
    sig = _sig(
        FailureKind.MISSING_TERM,
        SignatureFacts(
            rows=("rg_x",),
            legs=("primary",),
            engaged_refs=("Article 73",),
            engaged_heads=("Article 73",),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.CONTENT
    assert "measured surfaces" in attribution.rationale
    assert "engine-level seed" in attribution.falsifier


def test_a_limb_nobody_reaches_is_content_even_when_the_head_is_unknown() -> None:
    sig = _sig(
        FailureKind.MISSING_TERM,
        SignatureFacts(
            rows=("rg_x",),
            legs=("primary",),
            engaged_refs=("Article 73.1",),
            engaged_heads=("Article 73",),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.CONTENT
    assert "declared grain is the mechanism" in attribution.rationale


def test_a_declared_binding_the_access_path_never_uses_is_tool() -> None:
    sig = _sig(
        FailureKind.MISSING_TERM,
        SignatureFacts(
            rows=("rg_x",),
            legs=("primary",),
            engaged_refs=("Article 27",),
            engaged_heads=("Article 27",),
            role_refs=("Article 27",),
            role_heads=("Article 27",),
            reachable_refs=("Article 6",),
        ),
    )
    attribution = attribute_signature(sig)
    assert attribution.target is AttributionTarget.TOOL
    assert attribution.layer is not None


def test_manifest_and_union_kinds_carry_their_own_mechanism() -> None:
    plural = _sig(
        FailureKind.MANIFEST_HOLE,
        SignatureFacts(rows=("rg_002",)),
        origin=SignatureOrigin.R443,
        observed="plural inflection empties the manifest",
        signature_id="sig:r443:manifest_hole_inflection",
    )
    negation = _sig(
        FailureKind.MANIFEST_HOLE,
        SignatureFacts(rows=("rg_106",)),
        origin=SignatureOrigin.R443,
        observed="negated markers are not representable",
        signature_id="sig:r443:manifest_hole_negation",
    )
    union = _sig(
        FailureKind.DUTY_UNION_OVERREACH,
        SignatureFacts(rows=("rg_085",)),
        origin=SignatureOrigin.R443,
        signature_id="sig:r443:duty_union_overreach",
    )
    assert attribute_signature(plural).target is AttributionTarget.CONTENT
    assert attribute_signature(negation).target is AttributionTarget.SCHEMA
    assert attribute_signature(union).target is AttributionTarget.SCHEMA


def test_evidence_and_proposals_are_built_for_ontology_targets_only() -> None:
    facts = SignatureFacts(
        rows=("rg_x",),
        criteria=("rg_x#1",),
        legs=("primary",),
        engaged_refs=("Article 27",),
        engaged_heads=("Article 27",),
        role_refs=("Article 27",),
        role_heads=("Article 27",),
    )
    sig = _sig(FailureKind.MISSING_TERM, facts, signature_id="sig:test:tool")
    ledger = build_ledger(
        (sig,),
        parent_snapshot="kb:test",
        evidence_for={
            "sig:test:tool": (
                evidence_record(
                    source_id="judge-cache.jsonl",
                    source_version="deadbeef",
                    locator="rg_x#crit1",
                    quote="criterion: ...\nremark: ...",
                ),
            )
        },
        targets_for={"sig:test:tool": ("Article 27",)},
    )
    entry = ledger.entries[0]
    assert entry.proposal is not None
    assert entry.proposal.layer.value == "tool"
    assert entry.proposal.evidence
    assert ledger.coverage["proposals"] == 1.0


def test_fabricated_targets_flags_invented_ids_but_not_declared_introductions() -> None:
    invented = OntologyPatchProposal(
        proposal_id="prop:x",
        parent_snapshot="kb:test",
        target_ids=("Article 999", "+Annex VIII.a"),
        layer="content",  # type: ignore[arg-type]
        hypothesis="h",
        evidence=(
            evidence_record(
                source_id="s", source_version="v", locator="l", quote="q"
            ),
        ),
    )
    assert fabricated_targets(invented) == ("Article 999",)

    real = OntologyPatchProposal(
        proposal_id="prop:y",
        parent_snapshot="kb:test",
        target_ids=("Article 26", "+role_detection.non_establishment", "extraterritorial_non_eu"),
        layer="content",  # type: ignore[arg-type]
        hypothesis="h",
        evidence=(
            evidence_record(source_id="s", source_version="v", locator="l", quote="q"),
        ),
    )
    assert fabricated_targets(real) == ()


# ── the module is not on the request path ────────────────────────────────


def test_ledger_module_is_not_referenced_by_the_application() -> None:
    """The ledger is offline: no module under ``app/`` may name it.

    A filesystem scan, not ``git grep``: the CI deployability job runs on an
    extracted ``git archive`` tree with no repository, where ``git grep`` fails
    with empty stdout and an empty-stdout assertion would pass vacuously.
    """
    offenders = [
        rel
        for path in sorted((REPO / "app").rglob("*.py"))
        if (rel := path.relative_to(REPO).as_posix()) != "app/data/ontology_ledger.py"
        and "ontology_ledger" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"ledger must stay offline, found: {offenders}"

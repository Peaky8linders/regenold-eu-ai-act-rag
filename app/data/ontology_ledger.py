"""Offline evolution ledger: failure signature → attribution → candidate patch.

EvoOntology's third contribution is a *typed* evolution record: cluster failure
signatures, attribute each to exactly one layer, and propose a reviewable patch
instead of letting a model rewrite the knowledge base.  This module is the
deterministic half of that — it has no request-path callers, performs no I/O,
and **mutates nothing**.  A patch proposal is a reviewable object, never an
applied change.

The one-primary-target rule
---------------------------

Every signature gets exactly one primary target, chosen by measured facts rather
than by taste:

``content``
    a stored *value* is missing or wrong — a marker that cannot match, an anchor
    set whose declared grain is shallower than the engaged limb, a coordinate the
    catalog cannot represent;
``tool``
    the declared data is complete and correct and the access path fails to use it;
``schema``
    no declared field, relation, or value form can express the needed
    distinction, so a declaration is required before any value can be stored;
``generation``
    the provision was declared and/or reached, and the answer still did not state
    it — the layer that must change is the answer-generation contract;
``transport``
    the graded row was served by a degraded leg, so no ontology conclusion is
    admissible from it at all;
``dataset``
    the criterion or its grading is the artifact, not the system.

The ``tool``/``schema`` split is decided by a checkable question — *does a value
slot already exist for this fact?*  A keyword list that cannot match a plural
inflection is content (another value is representable).  A hint table whose value
form is a bare keyword, asked to represent negation, is schema.  A role matrix
that declares duties by role **noun**, asked to bind a duty that flows from a
stated condition, is schema.  Duty-level scope conditions are schema for a
measured reason, not an asserted one: :class:`app.data.ontology.Practice`
carries ``exceptions`` while the role-obligation rows carry no scope, exception,
or limitation field at all.

Degraded serves are refused, not explained
------------------------------------------

``stage2_served_by`` is set by the engine and consulted by the route, which
refuses to cache ``fallback``, ``deterministic``, and ``prior_turn`` serves
(``app/routes/regenold.py``).  A ``deterministic`` serve is a *dropped polish*,
not the intentional Stage-2 skip: every site that marks it documents that a
polish was lost, was rejected by the structural guard and replaced, or never
landed because both providers failed.  A criterion failing on such a row is
evidence about the transport, so the ledger attributes it to ``transport`` and
emits no patch.  A defect measured offline on the same row is still admissible,
because it does not depend on the shipped answer.

Identifier honesty
------------------

Patch targets are real identifiers, or they are prefixed with ``+`` to declare
"this patch would introduce it".  :func:`fabricated_targets` returns every
unprefixed target that does not exist in the registries or the coordinate
catalog, so a proposal that names something invented is detectable rather than
plausible.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum

from app.data.ontology_evidence import OntologyEvidence, OntologyLayer, OntologyPatchProposal

LEDGER_VERSION = "r444.1"

#: Legs the route refuses to cache — i.e. every serve that is a degradation.
DEGRADED_LEGS: frozenset[str] = frozenset({"fallback", "deterministic", "prior_turn"})


class SignatureOrigin(StrEnum):
    """Where a signature's evidence came from, because admissibility differs."""

    JUDGE = "judge"  # per-criterion verdicts + remarks (admissible only on a valid leg)
    PROBE = "probe"  # offline deterministic measurement (admissible regardless of leg)
    R443 = "r443"  # the diagnosed phase-2 defects, recorded with their falsification


class FailureKind(StrEnum):
    """Normalized failure signatures (the mapping document's vocabulary)."""

    WRONG_PROVISION_BINDING = "wrong_provision_binding"
    MISSING_TERM = "missing_term"
    MISSING_CONSTRAINT = "missing_constraint"
    OMITTED_ENUMERATED_ITEM = "omitted_enumerated_item"
    VERDICT_POLARITY_FLIP = "verdict_polarity_flip"
    MANIFEST_HOLE = "manifest_hole"
    DUTY_UNION_OVERREACH = "duty_union_overreach"
    ROLE_BINDING_MISS = "role_binding_miss"
    DECLARED_GRAIN_TOO_SHALLOW = "declared_grain_too_shallow"
    UNREPRESENTED_SCOPE = "unrepresented_scope"
    UNCLASSIFIED = "unclassified"


class AttributionTarget(StrEnum):
    """Exactly one primary target per signature."""

    CONTENT = "content"
    TOOL = "tool"
    SCHEMA = "schema"
    GENERATION = "generation"
    TRANSPORT = "transport"
    DATASET = "dataset"
    #: Insufficient evidence to name a layer.  A coverage gap the ledger reports
    #: rather than fills with a hypothesis.
    UNATTRIBUTED = "unattributed"


_ONTOLOGY_TARGETS: dict[AttributionTarget, OntologyLayer] = {
    AttributionTarget.CONTENT: OntologyLayer.CONTENT,
    AttributionTarget.TOOL: OntologyLayer.TOOL,
    AttributionTarget.SCHEMA: OntologyLayer.SCHEMA,
}


def head_of(ref: str) -> str:
    """Head grain: ``Article 26.1`` → ``Article 26``; ``Annex VIII.a`` → ``Annex VIII``."""
    text = str(ref).strip()
    if text.startswith(("Article", "Annex")):
        return " ".join(text.replace("(", ".").split(".")[0].split()[:2])
    return text


# ── measured facts ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NonDegradedRecheck:
    """A measured re-serve of the same criteria with no degradation present.

    The transport rule's own falsifier is "re-run the same rows on a
    non-degraded leg and the criteria still fail".  This records that test once it
    has been run: which criteria were retested, and which of them still fail when
    the leg is healthy.  A retest on another degraded leg proves nothing, so it is
    refused rather than read as evidence.
    """

    leg: str
    artifact: str
    judge_identity: str
    rows: tuple[str, ...] = ()
    criteria_retested: tuple[str, ...] = ()
    criteria_still_failing: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """A recheck is evidence only when its own leg is not a degradation."""
        return bool(self.criteria_retested) and self.leg not in DEGRADED_LEGS

    @property
    def recovered(self) -> tuple[str, ...]:
        failing = set(self.criteria_still_failing)
        return tuple(c for c in self.criteria_retested if c not in failing)

    @property
    def any_survives(self) -> bool:
        """At least one criterion still fails with no degradation present."""
        return self.usable and bool(self.criteria_still_failing)

    @property
    def all_recovered(self) -> bool:
        """The retest recovered every criterion it re-served."""
        return self.usable and not self.criteria_still_failing

    def summary(self) -> str:
        return (
            f"re-served on the non-degraded `{self.leg}` leg ({self.artifact}, judge "
            f"{self.judge_identity}): {len(self.recovered)}/{len(self.criteria_retested)} "
            f"criteria recovered and {len(self.criteria_still_failing)} still fail"
        )


@dataclass(frozen=True, slots=True)
class SignatureFacts:
    """Facts measured from artifacts.  Nothing here is inferred at attribution time.

    Declarations are split by provenance because they are not equally strong
    evidence: ``role_refs`` come from the role-obligation matrix, i.e. an actual
    binding for a detected value-chain role, while ``concept_refs`` come from a
    concept's anchor set — and a risk tier resolves to the provider's whole duty
    chapter, so a head appearing there is not by itself a binding (that defect
    has its own signature).
    """

    rows: tuple[str, ...] = ()
    criteria: tuple[str, ...] = ()
    legs: tuple[str, ...] = ()
    question_refs: tuple[str, ...] = ()
    engaged_refs: tuple[str, ...] = ()
    engaged_heads: tuple[str, ...] = ()
    cited_refs: tuple[str, ...] = ()
    cited_heads: tuple[str, ...] = ()
    mentioned_refs: tuple[str, ...] = ()
    reachable_refs: tuple[str, ...] = ()
    reachable_heads: tuple[str, ...] = ()
    role_refs: tuple[str, ...] = ()
    role_heads: tuple[str, ...] = ()
    any_role_refs: tuple[str, ...] = ()
    any_role_heads: tuple[str, ...] = ()
    risk_hints: tuple[str, ...] = ()
    describes_actor: bool = False
    concept_refs: tuple[str, ...] = ()
    concept_heads: tuple[str, ...] = ()
    catalog_missing_refs: tuple[str, ...] = ()
    #: Measured retest on a healthy leg, when one has been run for these criteria.
    recheck: NonDegradedRecheck | None = None

    @property
    def weight(self) -> int:
        """Failed criteria covered by this signature (1 when it is not judge-derived)."""
        return max(1, len(self.criteria))

    @property
    def all_rows_degraded(self) -> bool:
        return bool(self.rows) and bool(self.legs) and all(leg in DEGRADED_LEGS for leg in self.legs)

    @property
    def transport_overturned(self) -> bool:
        """A non-degraded retest of these very criteria still fails some of them."""
        return bool(self.recheck and self.recheck.any_survives)

    @property
    def has_catalog_gap(self) -> bool:
        return bool(self.catalog_missing_refs)

    @property
    def ref_reachable(self) -> bool:
        return bool(set(self.engaged_refs) & set(self.reachable_refs))

    @property
    def head_reachable(self) -> bool:
        return bool(set(self.engaged_heads) & set(self.reachable_heads))

    @property
    def ref_binding_declared(self) -> bool:
        """The engaged limb is declared by the role matrix for a detected role."""
        return bool(set(self.engaged_refs) & set(self.role_refs))

    @property
    def head_binding_declared(self) -> bool:
        """The engaged head is declared by the role matrix for a detected role."""
        return bool(set(self.engaged_heads) & set(self.role_heads))

    @property
    def ref_cited(self) -> bool:
        return bool(set(self.engaged_refs) & set(self.cited_refs))

    @property
    def head_cited(self) -> bool:
        return bool(set(self.engaged_heads) & set(self.cited_heads))

    @property
    def ref_mentioned(self) -> bool:
        """The graded answer's own prose names the engaged provision."""
        return bool(set(self.engaged_refs) & set(self.mentioned_refs))

    @property
    def limb_refs(self) -> tuple[str, ...]:
        """Engaged references deeper than their head."""
        return tuple(ref for ref in self.engaged_refs if ref != head_of(ref))

    @property
    def engaged_ref_is_limb(self) -> bool:
        """At least one engaged reference is deeper than its head."""
        return bool(self.limb_refs)

    @property
    def limbs_all_unbound(self) -> bool:
        """Every engaged limb is neither reachable by an arm nor named in the prose.

        Strict on purpose: a signature that mixes a bound limb with an unbound one
        does not support a grain claim, so it must fall through to the default.
        """
        limbs = self.limb_refs
        if not limbs:
            return False
        reachable = set(self.reachable_refs)
        mentioned = set(self.mentioned_refs)
        return all(ref not in reachable and ref not in mentioned for ref in limbs)

    @property
    def engaged_role_duty_refs(self) -> tuple[str, ...]:
        """Engaged references whose head is a duty of some value-chain role."""
        heads = set(self.any_role_heads)
        return tuple(ref for ref in self.engaged_refs if head_of(ref) in heads)

    @property
    def role_duty_head_unbound(self) -> bool:
        """A question that describes an actor bound a role duty without detecting the role.

        Deliberately narrow, and evaluated on the role-duty subset of the
        engaged references so a co-engaged head cannot mask the gap: every
        condition must hold, so the rule cannot claim a role-detection mechanism
        for a question that names no actor (``rg_087`` asks what Article 9 says),
        for one whose role *was* detected (``rg_062``), or for one whose engaged
        limb is reachable and named (``rg_075``, ``rg_103``).
        """
        duty_refs = self.engaged_role_duty_refs
        if not duty_refs:
            return False
        return (
            self.describes_actor
            and not self.role_refs
            and not self.head_binding_declared
            and not any(ref in set(self.reachable_refs) for ref in duty_refs)
            and not any(ref in set(self.mentioned_refs) for ref in duty_refs)
        )

    @property
    def concept_only_declared(self) -> bool:
        """The engaged head appears only in a concept anchor set (possibly the duty union)."""
        return (
            bool(set(self.engaged_heads) & set(self.concept_heads))
            and not self.head_binding_declared
            and not self.head_reachable
        )

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.update(
            {
                "weight": self.weight,
                "all_rows_degraded": self.all_rows_degraded,
                "ref_reachable": self.ref_reachable,
                "head_reachable": self.head_reachable,
                "ref_binding_declared": self.ref_binding_declared,
                "head_binding_declared": self.head_binding_declared,
                "ref_cited": self.ref_cited,
                "head_cited": self.head_cited,
                "ref_mentioned": self.ref_mentioned,
                "engaged_ref_is_limb": self.engaged_ref_is_limb,
                "limbs_all_unbound": self.limbs_all_unbound,
                "role_duty_head_unbound": self.role_duty_head_unbound,
                "concept_only_declared": self.concept_only_declared,
            }
        )
        return data


@dataclass(frozen=True, slots=True)
class FailureSignature:
    """One clustered, evidence-bearing failure signature."""

    signature_id: str
    kind: FailureKind
    origin: SignatureOrigin
    title: str
    observed: str
    facts: SignatureFacts
    sources: tuple[str, ...] = ()

    @property
    def weight(self) -> int:
        return self.facts.weight


@dataclass(frozen=True, slots=True)
class LayerAttribution:
    """The single primary target for one signature, with its falsifier."""

    signature_id: str
    target: AttributionTarget
    rationale: str
    falsifier: str
    #: ``None`` when the target is not an ontology layer (generation/transport/dataset).
    layer: OntologyLayer | None = None
    evidence: tuple[OntologyEvidence, ...] = ()

    @property
    def is_ontology(self) -> bool:
        return self.layer is not None


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    signature: FailureSignature
    attribution: LayerAttribution
    proposal: OntologyPatchProposal | None = None


@dataclass(frozen=True, slots=True)
class EvolutionLedger:
    """The serializable result: signatures, one attribution each, reviewable patches."""

    version: str = LEDGER_VERSION
    entries: tuple[LedgerEntry, ...] = ()
    notes: tuple[str, ...] = ()
    coverage: dict[str, float] = field(default_factory=dict)

    @property
    def by_target(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for entry in self.entries:
            key = entry.attribution.target.value
            out[key] = out.get(key, 0) + entry.signature.weight
        return out

    @property
    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for entry in self.entries:
            key = entry.signature.kind.value
            out[key] = out.get(key, 0) + entry.signature.weight
        return out

    @property
    def unattributed(self) -> tuple[LedgerEntry, ...]:
        return tuple(entry for entry in self.entries if not entry.attribution.is_ontology)

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "coverage": self.coverage,
            "by_target": self.by_target,
            "by_kind": self.by_kind,
            "notes": list(self.notes),
            "entries": [
                {
                    "signature": {
                        "id": entry.signature.signature_id,
                        "kind": entry.signature.kind.value,
                        "origin": entry.signature.origin.value,
                        "title": entry.signature.title,
                        "observed": entry.signature.observed,
                        "sources": list(entry.signature.sources),
                        "facts": entry.signature.facts.as_dict(),
                    },
                    "attribution": {
                        "target": entry.attribution.target.value,
                        "layer": entry.attribution.layer.value if entry.attribution.layer else None,
                        "rationale": entry.attribution.rationale,
                        "falsifier": entry.attribution.falsifier,
                        "evidence": [
                            {
                                "source_id": item.source_id,
                                "source_version": item.source_version,
                                "locator": item.locator,
                                "quote": item.quote,
                                "content_hash": item.content_hash,
                            }
                            for item in entry.attribution.evidence
                        ],
                    },
                    "proposal": (
                        {
                            "proposal_id": entry.proposal.proposal_id,
                            "parent_snapshot": entry.proposal.parent_snapshot,
                            "target_ids": list(entry.proposal.target_ids),
                            "layer": entry.proposal.layer.value,
                            "hypothesis": entry.proposal.hypothesis,
                            "evidence_keys": [list(key) for key in entry.proposal.evidence_keys],
                        }
                        if entry.proposal is not None
                        else None
                    ),
                }
                for entry in self.entries
            ],
        }


# ── judge-remark classification (deterministic, evidence-recording) ──────

_VERDICT_LEAD_RE = re.compile(r"^\s*(yes|no)\b", re.IGNORECASE)
_FLIP_MARKERS = ("contradict", "correct verdict", "opposite", "misunderstand")
_BINDING_MARKERS = (
    "different provision",
    "not article",
    "states that article",
    "instead of article",
    "rejects annex",
    "incorrectly claims",
    "incorrectly treats",
    "incorrectly states",
    "contradicts the criterion",
)
_MISSING_MARKERS = (
    "does not state",
    "does not clarify",
    "does not mention",
    "does not specify",
    "does not address",
    "does not explicitly",
    "does not describe",
    "does not list",
    "does not engage",
    "does not unambiguously",
    "does not note",
    "fails to",
    "omits",
    "is not mentioned",
    "absent",
    "not clearly",
    "insufficient",
)
_CONSTRAINT_MARKERS = (
    "limited to",
    "to the extent",
    "regardless",
    "irrespective",
    "not an exemption",
    "does not exempt",
    "is not excused",
    "still required",
    "still applies",
    "only if",
    "only existence",
    "where applicable",
    "until",
)
_ENUMERATION_MARKERS = (
    "four steps",
    "five steps",
    "points 1 to",
    "points 7 to",
    "points 10 to",
    "point 4",
    "point 5",
    "point 6",
)
_REF_RE = re.compile(r"\b(Article\s+\d+(?:\(\d+\))?|Annex\s+[IVX]+(?:\(\d+\))?(?:\.[a-z])?)")


def classify_judge_remark(criterion: str, remark: str) -> tuple[FailureKind, str]:
    """Classify one failed criterion.  Returns ``(kind, matched evidence phrase)``.

    Rules are ordered most-specific-first, and the matched phrase is returned so
    the ledger can quote *why* a kind was chosen.  The criterion's own shape is
    checked before the remark's phrasing, because the official rubric text is the
    more reliable signal: a limiting condition named by the criterion ('is not
    excused') outranks a remark saying the answer "incorrectly treats" the
    point.  A remark matching no rule is ``UNCLASSIFIED`` and is reported as a
    coverage gap rather than forced into a bucket.
    """
    low = f"{criterion}\n{remark}".lower()
    low_criterion = criterion.lower()

    if _VERDICT_LEAD_RE.match(criterion):
        for marker in _FLIP_MARKERS:
            if marker in low:
                return FailureKind.VERDICT_POLARITY_FLIP, f"verdict lead + {marker!r}"
    for marker in _ENUMERATION_MARKERS:
        if marker in low_criterion:
            return FailureKind.OMITTED_ENUMERATED_ITEM, f"criterion enumerates ({marker!r})"
    if len(re.findall(r"\([a-d]\)", criterion)) >= 2:
        return FailureKind.OMITTED_ENUMERATED_ITEM, "criterion enumerates >=2 limbs"
    for marker in _CONSTRAINT_MARKERS:
        if marker in low_criterion:
            return FailureKind.MISSING_CONSTRAINT, f"criterion says {marker!r}"
    for marker in _BINDING_MARKERS:
        if marker in low:
            return FailureKind.WRONG_PROVISION_BINDING, marker
    for marker in _MISSING_MARKERS:
        if marker in low:
            return FailureKind.MISSING_TERM, marker
    return FailureKind.UNCLASSIFIED, "no rule matched"


def criterion_refs(criterion: str) -> tuple[str, ...]:
    """Coordinates named by a criterion, in wire form, deterministically."""
    out: list[str] = []
    for raw in _REF_RE.findall(criterion):
        text = re.sub(r"\s+", " ", raw.strip())
        wire = text.replace("(", ".").replace(")", "")
        if wire not in out:
            out.append(wire)
    return tuple(out)


# ── attribution: the rule table ──────────────────────────────────────────


def _attribute(
    signature_id: str,
    target: AttributionTarget,
    *,
    rationale: str,
    falsifier: str,
    evidence: tuple[OntologyEvidence, ...] = (),
) -> LayerAttribution:
    return LayerAttribution(
        signature_id=signature_id,
        target=target,
        layer=_ONTOLOGY_TARGETS.get(target),
        rationale=rationale,
        falsifier=falsifier,
        evidence=evidence,
    )


def attribute_signature(signature: FailureSignature) -> LayerAttribution:
    """Assign exactly one primary target, chosen by measured facts.

    Order is the contract.  A degraded leg outranks everything (the graded answer
    is not the generation path's output) — *unless* its own falsifier has already
    been run and triggered, in which case the surviving criteria are attributed on
    the measured non-degraded evidence.  Then the signature's own measured
    mechanism: a coordinate the catalog cannot represent, a declared grain
    shallower than the engaged limb, a binding that is declared but unreached, a
    limb that is neither declared nor reached — and only then generation, which
    is the default when the provision was available and the answer still missed
    it.
    """
    sig_id = signature.signature_id
    facts = signature.facts
    kind = signature.kind

    if signature.origin is SignatureOrigin.JUDGE and facts.all_rows_degraded:
        recheck = facts.recheck
        if recheck is None or not recheck.any_survives:
            rationale = (
                "every row in this signature was served by a degraded leg "
                f"({', '.join(sorted(set(facts.legs)))}); the route refuses to cache exactly "
                "those legs, so the graded answer is not the generation path's output and no "
                "ontology conclusion is admissible from it"
            )
            if recheck is not None and recheck.all_recovered:
                rationale += (
                    "; that claim was tested: "
                    + recheck.summary()
                    + ", so the measured retest did not trigger this rule's own falsifier"
                )
            return _attribute(
                sig_id,
                AttributionTarget.TRANSPORT,
                rationale=rationale,
                falsifier=(
                    "re-run the same rows on a non-degraded leg and the criteria still fail — "
                    "then the transport attribution is false and the failure becomes attributable"
                ),
            )
        # The falsifier was run and triggered: these criteria still fail with no
        # degradation present, so a degraded serve cannot be their mechanism.
        # Re-attribute on the surviving criteria and the measured leg, which is
        # what re-enters the mechanism rules below.
        reduced = replace(facts, criteria=recheck.criteria_still_failing, legs=(recheck.leg,))
        mechanism = attribute_signature(replace(signature, facts=reduced))
        return replace(
            mechanism,
            rationale=(
                "the degraded-leg rule was falsified by measurement — "
                + recheck.summary()
                + "; those criteria therefore stand with no degradation present, so the target "
                "is decided on the non-degraded evidence that follows. "
                + mechanism.rationale
            ),
            falsifier=(
                "a second non-degraded draw passes these criteria — then they are draw-dependent "
                "rather than attributable, and this attribution must be re-taken on repeats"
            ),
        )

    if kind is FailureKind.UNCLASSIFIED and not facts.engaged_refs:
        return _attribute(
            sig_id,
            AttributionTarget.UNATTRIBUTED,
            rationale=(
                "the evidence does not identify a layer: no rule matched the observed defect "
                "and no engaged coordinate was measured, so attributing it would be a guess"
            ),
            falsifier=(
                "a per-row defect study names the mechanism — then this becomes attributable and "
                "the coverage gap closes"
            ),
        )

    if kind is FailureKind.MANIFEST_HOLE and "plural" in signature.observed.lower():
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "the concept marker list is a value table and cannot match a plural inflection, "
                "so the manifest for the row is empty; another value is representable in the "
                "same field"
            ),
            falsifier=(
                "add the inflection to the marker list and the manifest is still empty — then "
                "the missing value is not the mechanism"
            ),
        )
    if kind is FailureKind.MANIFEST_HOLE:
        return _attribute(
            sig_id,
            AttributionTarget.SCHEMA,
            rationale=(
                "the risk-hint value form is a bare keyword, so a negated marker ('no "
                "cross-context social scoring') has no representation at all; the table needs a "
                "polarity form before any value can express it"
            ),
            falsifier=(
                "a polarity field already exists on the hint table and merely holds the wrong "
                "value — then this is content, not schema"
            ),
        )
    if kind is FailureKind.ROLE_BINDING_MISS:
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "the duty is already declared for the role that owns it (measured: `Art. 22` is "
                "in the role matrix for `extraterritorial_non_eu`), so the missing piece is a "
                "surface-to-role value — the condition ('established outside the Union') is "
                "expressible in the same pattern table as the existing role markers"
            ),
            falsifier=(
                "the duty is not declared for any role that fits the question — then a "
                "condition-to-role relation is missing and the layer is schema"
            ),
        )
    if kind is FailureKind.DUTY_UNION_OVERREACH:
        return _attribute(
            sig_id,
            AttributionTarget.SCHEMA,
            rationale=(
                "a risk tier returns the provider's full duty chapter (measured: 21 anchors) and "
                "no declared selector can express 'the engaged branch'; the union is structurally "
                "correct, so no value change can fix it"
            ),
            falsifier=(
                "a selector field exists and is populated correctly and the resolver ignored it — "
                "then the layer is tool"
            ),
        )
    if kind is FailureKind.UNREPRESENTED_SCOPE:
        return _attribute(
            sig_id,
            AttributionTarget.SCHEMA,
            rationale=(
                "duty rows carry no scope, exception, or limitation field (measured: practices "
                "carry `exceptions`; role obligations carry none), so a duty's limiting "
                "condition cannot be stored even when it is known"
            ),
            falsifier=(
                "some duty registry field already stores the limiting condition — then the "
                "defect is the missing value (content) or the unused field (tool)"
            ),
        )
    if kind is FailureKind.DECLARED_GRAIN_TOO_SHALLOW:
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "the registries declare the engaged head but not the limb the criterion turns "
                "on, so the declared value's grain is shallower than the question"
            ),
            falsifier=(
                "the limb is declared elsewhere and the wire still emits the head — then the "
                "access path is at fault (tool)"
            ),
        )

    if facts.has_catalog_gap:
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "the engaged coordinate fails the existence catalog "
                f"({', '.join(facts.catalog_missing_refs)}), so the wire cannot represent or "
                "emit it: the value is absent"
            ),
            falsifier=(
                "the coordinate resolves once registered and the criterion still fails — then "
                "the catalog was not the mechanism"
            ),
        )

    if facts.role_duty_head_unbound:
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "the question describes an actor and the engaged head is a duty of some "
                "value-chain role (measured against the full role matrix), but no role was "
                "detected, the limb is not a reachable anchor, and the answer never names it: no "
                "role binding activated, so the missing piece is a surface-to-role value"
            ),
            falsifier=(
                "a role is detected once the surface set is extended and the criterion still "
                "fails — then this signature is not a role-detection gap"
            ),
        )

    if kind is FailureKind.VERDICT_POLARITY_FLIP:
        return _attribute(
            sig_id,
            AttributionTarget.GENERATION,
            rationale=(
                "the criterion is a verdict the answer contradicted; a polarity flip is a "
                "statement error, so the ledger makes no grain or retrieval claim about it"
            ),
            falsifier=(
                "the engaged provision was absent from the rendered context — then the flip was "
                "forced by missing grounding and the layer is retrieval/content"
            ),
        )

    _grain_kinds = {
        FailureKind.WRONG_PROVISION_BINDING,
        FailureKind.MISSING_TERM,
        FailureKind.MISSING_CONSTRAINT,
        FailureKind.OMITTED_ENUMERATED_ITEM,
    }
    if kind in _grain_kinds and facts.limbs_all_unbound:
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "every limb the criteria turn on is unreached by both retrieval arms and unnamed "
                "in the answer's own prose, while the head was bound — the engaged limbs' text "
                "never entered the grounded context, so the declared grain is the mechanism"
            ),
            falsifier=(
                "the engaged limb is present in the rendered context (or quoted by the answer) "
                "and the criterion still fails — then the layer is generation"
            ),
        )

    if (
        not facts.ref_reachable
        and not facts.ref_binding_declared
        and not facts.head_binding_declared
        and not facts.head_reachable
        and not facts.ref_mentioned
    ):
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "within the measured surfaces (role matrix, concept resolution, both retrieval "
                "arms) and the answer's own prose, the engaged provision appears nowhere: no "
                "mapping path reaches it"
            ),
            falsifier=(
                "an engine-level seed or un-annotated corpus text does carry the provision — then "
                "the layer is tool or generation, not content, and this attribution is false"
            ),
        )
    if facts.ref_binding_declared and not facts.ref_reachable:
        return _attribute(
            sig_id,
            AttributionTarget.TOOL,
            rationale=(
                "the role matrix declares this binding for the question's detected role and "
                "neither retrieval arm surfaces it, so the declared data is present and unused"
            ),
            falsifier=(
                "the binding is not actually declared for this question's role — then the gap is "
                "content, not tool"
            ),
        )
    if facts.head_binding_declared and not facts.ref_binding_declared and not facts.head_cited:
        return _attribute(
            sig_id,
            AttributionTarget.CONTENT,
            rationale=(
                "the role matrix declares the engaged head for this question's role but not the "
                "limb, and the answer never bound even the head, so the declared grain is "
                "shallower than the criterion and the binding was not activated"
            ),
            falsifier=(
                "the limb is declared for this role — then the grain is fine and the failure is "
                "downstream"
            ),
        )

    bound = sorted(set(facts.cited_refs) & set(facts.engaged_refs))
    bound_note = ", ".join(bound) if bound else "none of them"
    union_note = (
        " The engaged head does appear in a concept anchor set, but that set is the risk tier's "
        "whole duty chapter, which is a separate signature and not evidence of a binding."
        if facts.concept_only_declared
        else ""
    )
    return _attribute(
        sig_id,
        AttributionTarget.GENERATION,
        rationale=(
            "the engaged provision is reachable by the deterministic stack (the wire itself "
            f"bound {bound_note}), so the ontology already carried what was needed and the "
            "answer-generation contract is the layer that must change." + union_note
        ),
        falsifier=(
            "a paired arm whose context omits the provision changes the criterion — then the "
            "retrieval/ontology layer was binding after all; for a role-conditioned question the "
            "alternative mechanism (the question's role was not detected, so no role binding "
            "activated) must be gated separately"
        ),
    )


# ── patch emission ───────────────────────────────────────────────────────

_HYPOTHESES: dict[AttributionTarget, str] = {
    AttributionTarget.CONTENT: (
        "adding the missing values ({targets}) will close {weight} {criteria} on "
        "{rows} without dropping any gold head"
    ),
    AttributionTarget.TOOL: (
        "letting the access path use the declared binding ({targets}) will close {weight} "
        "{criteria} on {rows} with no reference growth"
    ),
    AttributionTarget.SCHEMA: (
        "declaring the missing field/relation for {targets} is a prerequisite for closing "
        "{weight} {criteria} on {rows}; the declaration alone is not the fix"
    ),
}


def propose_patch(
    signature: FailureSignature,
    attribution: LayerAttribution,
    *,
    parent_snapshot: str,
    targets: tuple[str, ...] | None = None,
    evidence: tuple[OntologyEvidence, ...] = (),
) -> OntologyPatchProposal | None:
    """Emit a reviewable proposal for an ontology-attributable signature.

    Non-ontology targets (generation/transport/dataset) get no ontology patch —
    that refusal is the point of the ledger, not an omission.
    """
    if attribution.layer is None:
        return None
    resolved_targets = targets or signature.facts.engaged_refs or (f"+{signature.signature_id}",)
    weight = signature.weight
    hypothesis = _HYPOTHESES[attribution.target].format(
        targets=", ".join(resolved_targets),
        weight=weight,
        criteria="failed criterion" if weight == 1 else "failed criteria",
        rows=", ".join(signature.facts.rows) or "n/a",
    )
    return OntologyPatchProposal(
        proposal_id=f"prop:{signature.signature_id}",
        parent_snapshot=parent_snapshot,
        target_ids=resolved_targets,
        layer=attribution.layer,
        hypothesis=hypothesis,
        evidence=evidence or attribution.evidence or (_fallback_evidence(signature),),
    )


def _fallback_evidence(signature: FailureSignature) -> OntologyEvidence:
    source_id = signature.sources[0] if signature.sources else "app/data/ontology_ledger.py"
    return evidence_record(
        source_id=source_id,
        source_version=LEDGER_VERSION,
        locator=signature.signature_id,
        quote=signature.observed or signature.title,
    )


def build_ledger(
    signatures: tuple[FailureSignature, ...],
    *,
    parent_snapshot: str,
    evidence_for: dict[str, tuple[OntologyEvidence, ...]] | None = None,
    targets_for: dict[str, tuple[str, ...]] | None = None,
    notes: tuple[str, ...] = (),
) -> EvolutionLedger:
    """Attribute every signature once, and propose a patch only where one is admissible."""
    entries: list[LedgerEntry] = []
    for signature in signatures:
        base = attribute_signature(signature)
        attribution = LayerAttribution(
            signature_id=signature.signature_id,
            target=base.target,
            rationale=base.rationale,
            falsifier=base.falsifier,
            layer=base.layer,
            evidence=(evidence_for or {}).get(signature.signature_id, base.evidence),
        )
        proposal = propose_patch(
            signature,
            attribution,
            parent_snapshot=parent_snapshot,
            targets=(targets_for or {}).get(signature.signature_id),
            evidence=attribution.evidence,
        )
        entries.append(LedgerEntry(signature=signature, attribution=attribution, proposal=proposal))

    total = sum(entry.signature.weight for entry in entries) or 1
    classified = sum(
        entry.signature.weight
        for entry in entries
        if entry.signature.kind is not FailureKind.UNCLASSIFIED
    )
    ontology = sum(entry.signature.weight for entry in entries if entry.attribution.is_ontology)
    coverage = {
        "weight_total": float(total),
        "classified_share": round(classified / total, 4),
        "ontology_attributable_share": round(ontology / total, 4),
        "proposals": float(sum(1 for entry in entries if entry.proposal is not None)),
    }
    return EvolutionLedger(entries=tuple(entries), notes=tuple(notes), coverage=coverage)


# ── identifier honesty ───────────────────────────────────────────────────


def fabricated_targets(proposal: OntologyPatchProposal) -> tuple[str, ...]:
    """Unprefixed proposal targets that exist in neither the registries nor the catalog.

    A ``+``-prefixed target is a declared introduction (the patch would create it)
    and is not reported here.  Anything else must resolve, or the proposal is
    naming something invented.
    """
    from app.data.article_existence import ARTICLE_EXISTENCE
    from app.data.ontology import ANNEX_III_REGISTRY, PRACTICE_REGISTRY
    from app.data.ontology_browse import resolve_concept
    from app.data.provision_coordinates import coordinate_exists
    from app.data.role_obligations import ROLE_OBLIGATION_BY_ID

    fabricated: list[str] = []
    for target in proposal.target_ids:
        if target.startswith("+"):
            continue
        known = (
            target in ARTICLE_EXISTENCE
            or target in PRACTICE_REGISTRY
            or target in ANNEX_III_REGISTRY
            or target in ROLE_OBLIGATION_BY_ID
            or coordinate_exists(target)
            or resolve_concept(target).resolved
        )
        if not known:
            fabricated.append(target)
    return tuple(fabricated)


def evidence_record(
    *,
    source_id: str,
    source_version: str,
    locator: str,
    quote: str,
) -> OntologyEvidence:
    """Build a versioned evidence record for one quoted fact."""
    digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()[:16]
    return OntologyEvidence(
        source_id=source_id,
        source_version=source_version,
        locator=locator,
        quote=quote[:400],
        content_hash=digest,
    )


__all__ = [
    "DEGRADED_LEGS",
    "LEDGER_VERSION",
    "AttributionTarget",
    "EvolutionLedger",
    "FailureKind",
    "FailureSignature",
    "LayerAttribution",
    "LedgerEntry",
    "NonDegradedRecheck",
    "SignatureFacts",
    "SignatureOrigin",
    "attribute_signature",
    "build_ledger",
    "classify_judge_remark",
    "criterion_refs",
    "evidence_record",
    "fabricated_targets",
    "head_of",
    "propose_patch",
]

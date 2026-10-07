"""Read-only browse/resolve adapters over the deterministic legal ontology.

R443 — the EvoOntology Phase 2 experiment (see
``docs/reviews/evoontology-system-mapping.md``).  The paper's operational claim
is that an agent should *browse* a compact typed manifest and *resolve* the
linked records it needs, instead of being handed one rendered context blob.
This module makes that interface concrete and inspectable:

* :func:`browse_concepts` — a bounded, deterministic manifest of the typed
  ontology concepts a question engages (prohibited practices, Annex III
  categories, risk classes, actor-role obligation rows, applicability phases,
  and explicitly named provisions).
* :func:`resolve_concept` — the linked record for one concept id: existence-
  checked anchors, the role/risk obligation set, and the constraint checks that
  already gate the wire.
* :func:`adapter_candidates` — browse + resolve + one-hop cross-reference
  expansion, i.e. the independent retrieval arm the shadow experiment scores
  against the current Stage-1 sparse retriever.

**Shadow mode only.**  Nothing in this module is imported by the request path
(``app/routes/regenold.py``, ``app/engines/_graph_rag_impl.py``); a regression
test asserts that.  It cannot create a citation: every anchor it returns is
validated by :func:`app.data.provision_coordinates.coordinate_exists` first, and
anchors that fail the check are dropped rather than repaired.  It also performs
no I/O, no LLM call, and no network call.

Form normalisation is deliberate and load-bearing.  The deterministic registries
speak the internal ``Art. 13`` form, the cross-reference graph is keyed on it,
and the wire speaks ``Article 13``.  Browsing across those surfaces used to
require each caller to know which form it held; the helpers here make the
conversion explicit in one place.
"""
from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb import KB_VERSION
from app.data.kb_xrefs import cross_refs
from app.data.ontology import (
    ANNEX_III_REGISTRY,
    PHASE_REGISTRY,
    PRACTICE_REGISTRY,
    ActorRole,
    RiskClass,
    obligations_for,
)
from app.data.ontology_evidence import OntologyEvidence
from app.data.provision_coordinates import coordinate_exists

# ── hard caps ────────────────────────────────────────────────────────────
#
# The paper's tool layer is explicitly bounded: browse returns a manifest, not
# a corpus.  These caps are enforced inside the adapters so no caller can widen
# the contract by passing a large ``limit``.
MAX_BROWSE_LIMIT = 16
DEFAULT_BROWSE_LIMIT = 8
MAX_ANCHORS_PER_CONCEPT = 24
MAX_XREF_NEIGHBOURS = 6
MAX_CANDIDATES = 48

# ── concept kinds ────────────────────────────────────────────────────────
KIND_PROVISION = "provision"
KIND_PRACTICE = "practice"
KIND_ANNEX_III = "annex_iii_category"
KIND_PHASE = "phase"
KIND_ROLE = "role_obligation"
KIND_RISK = "risk_class"

CONCEPT_KINDS: tuple[str, ...] = (
    KIND_PROVISION,
    KIND_PRACTICE,
    KIND_ANNEX_III,
    KIND_RISK,
    KIND_PHASE,
    KIND_ROLE,
)

# ── keyword matching ─────────────────────────────────────────────────────
#
# The registry keyword tuples are authored phrases ("infer emotions"), while a
# real question inflects them ("a system that infers emotions").  Exact
# substring matching therefore misses the very rows the concept exists for.
# Matching is done on 5-character token prefixes so inflection is absorbed
# without a stemmer dependency; the manifest is a candidate generator, so a
# marginal over-match is measured by the shadow experiment rather than hidden.
_PREFIX_LEN = 5
_MATCH_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "in", "for", "and", "or", "to", "on", "by", "with", "is"}
)


def _tokens(text: str) -> set[str]:
    """Prefix-collapsed content tokens for inflection-tolerant matching."""
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {w[:_PREFIX_LEN] for w in words if w not in _MATCH_STOPWORDS}


def _keyword_hits(text: str, keywords: Iterable[str]) -> list[str]:
    """Registry keywords the text engages, by phrase or token-prefix subset."""
    lowered = str(text or "").lower()
    present = _tokens(text)
    hits: list[str] = []
    for keyword in keywords:
        if not keyword:
            continue
        if keyword in lowered:
            hits.append(keyword)
            continue
        needed = _tokens(keyword)
        if needed and needed <= present:
            hits.append(keyword)
    return hits

# ── form normalisation (internal ``Art. N`` ⇄ wire ``Article N``) ────────

_ARTICLE_RE = re.compile(
    r"\bArticles?\s+(\d{1,3})(?:\s*\(\s*(\d{1,2})\s*\))?",
    re.IGNORECASE,
)
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVX]+)", re.IGNORECASE)


def to_wire(ref: str) -> str:
    """``Art. 13`` → ``Article 13`` (wire form). Idempotent for annex refs."""
    text = str(ref or "").strip()
    if text.startswith("Art. "):
        return "Article " + text[len("Art. ") :]
    return text


def to_internal(ref: str) -> str:
    """``Article 13`` → ``Art. 13`` (registry / xref form)."""
    text = str(ref or "").strip()
    if text.startswith("Article "):
        return "Art. " + text[len("Article ") :]
    return text


def anchor_exists(ref: str) -> bool:
    """Existence check for a wire-form anchor, tolerating the short form."""
    candidate = to_wire(ref)
    if coordinate_exists(candidate):
        return True
    return candidate in ARTICLE_EXISTENCE


# ── deterministic role / risk hints ──────────────────────────────────────

_ROLE_PATTERNS: tuple[tuple[ActorRole, re.Pattern[str]], ...] = (
    (
        ActorRole.AUTHORISED_REPRESENTATIVE,
        re.compile(
            r"\bauthoris(?:ed|ing)\s+representative\b|\bauthoriz(?:ed|ing)\s+representative\b"
            r"|\bauthorised_representative\b|\bauthorized_representative\b",
            re.IGNORECASE,
        ),
    ),
    (
        ActorRole.NOTIFIED_BODY,
        re.compile(r"\bnotified\s+body\b|\bnotified\s+bodies\b", re.IGNORECASE),
    ),
    (
        ActorRole.DOWNSTREAM_PROVIDER,
        re.compile(r"\bdownstream\s+provider\b", re.IGNORECASE),
    ),
    (
        ActorRole.AFFECTED_PERSON,
        re.compile(
            r"\baffected\s+person\b|\bdata\s+subject\b|\bright\s+to\s+(?:an\s+)?explanation\b"
            r"|\blodge\s+a\s+complaint\b",
            re.IGNORECASE,
        ),
    ),
    (
        ActorRole.DISTRIBUTOR,
        re.compile(r"\bdistributor\b|\bdistributors\b", re.IGNORECASE),
    ),
    (ActorRole.IMPORTER, re.compile(r"\bimporter\b|\bimporters\b", re.IGNORECASE)),
    (ActorRole.DEPLOYER, re.compile(r"\bdeployer\b|\bdeployers\b", re.IGNORECASE)),
    (ActorRole.PROVIDER, re.compile(r"\bprovider\b|\bproviders\b", re.IGNORECASE)),
)

# Precedence is intentional: the more specific value-chain parties are named
# first, so "a distributor that is not the provider" does not degrade to
# PROVIDER.  Ordering is asserted by test.
_RISK_MARKERS: tuple[tuple[RiskClass, re.Pattern[str]], ...] = (
    (
        RiskClass.PROHIBITED,
        re.compile(
            r"\bprohibit(?:ed|ion)\b|\bsocial\s+scoring\b|\bsubliminal\b|\bmanipulat"
            r"|\bdeceptive\s+technique|\buntargeted\s+scraping\b"
            r"|\breal[\s-]?time\s+(?:remote\s+)?biometric\b|\bbiometric\s+categoris"
            r"|\bbiometric\s+categoriz|\bcriminal[\s-]?risk\b|\bpredictive\s+policing\b"
            r"|\bnot\s+(?:be\s+)?placed\s+on\s+the\s+market\b|\bbanned\b",
            re.IGNORECASE,
        ),
    ),
    (
        RiskClass.HIGH_RISK_ANNEX_I,
        re.compile(
            r"\bclass\s+ii[ab]\b|\bclass\s+iii\b|\bmdr\b|\bivdr\b|\bsamd\b"
            r"|\bmedical\s+device|\bin\s+vitro\s+diagnostic|\bsafety\s+component\b"
            r"|\bnotified\s+body\b|\bharmonis(?:ed|ation)\s+legislation\b"
            r"|\bmachinery\b|\bnotified\s+body\b",
            re.IGNORECASE,
        ),
    ),
    (
        RiskClass.HIGH_RISK_ANNEX_III,
        re.compile(
            r"\bhigh[\s-]?risk\b|\bAnnex\s+III\b|\bconformity\s+assessment\b"
            r"|\bfundamental\s+rights\s+impact\b|\bfria\b|\bqms\b"
            r"|\bquality\s+management\s+system\b|\bpost[\s-]?market\s+monitoring\b"
            r"|\bserious\s+incident\b|\btechnical\s+documentation\b"
            r"|\bhuman\s+oversight\b|\blog(?:s|ging)?\b",
            re.IGNORECASE,
        ),
    ),
    (
        RiskClass.GPAI_SYSTEMIC,
        re.compile(
            r"\bsystemic\s+risk\b|\b10\^?25\b|10\s*\*\*\s*25|\bflops\b"
            r"|\bfloating[\s-]?point\s+operations\b",
            re.IGNORECASE,
        ),
    ),
    (
        RiskClass.GPAI,
        re.compile(
            r"\bgeneral[\s-]?purpose\s+AI\b|\bgpai\b|\bfoundation\s+model"
            r"|\bseriously\s+large\b",
            re.IGNORECASE,
        ),
    ),
    (
        RiskClass.LIMITED_RISK,
        re.compile(
            r"\btransparen(?:cy|t)\b|\bdeep[\s-]?fake\b|\bdeepfake\b|\bchatbot\b"
            r"|\bAI[\s-]?generated\b|\bsynthetic\s+content\b|\bemotion\s+recognition\b"
            r"|\bArticle\s+50\b|\bArt\.\s*50\b|\bmarking\b",
            re.IGNORECASE,
        ),
    ),
)


def detect_roles(query: str) -> tuple[ActorRole, ...]:
    """Value-chain roles the question names, most specific first."""
    text = str(query or "")
    return tuple(role for role, pattern in _ROLE_PATTERNS if pattern.search(text))


def risk_hints(query: str) -> tuple[RiskClass, ...]:
    """Risk classes the question's own text engages, in precedence order.

    This is a *hint*, not a classifier: it exists so the adapter can resolve a
    role to an obligation set, and the shadow experiment measures how often the
    top hint agrees with the gold answer's own engagement. The markers are bare
    keywords and over-approximate (``manipulat`` and ``biometric categoris`` both
    hint PROHIBITED, which Art. 5(1) supports only under its stated conditions),
    so a hint must never be read as a verdict.
    """
    text = str(query or "")
    return tuple(rc for rc, pattern in _RISK_MARKERS if pattern.search(text))


def _explicit_provisions(query: str) -> tuple[str, ...]:
    """Provisions the question names explicitly, as wire refs."""
    refs: list[str] = []
    for match in _ARTICLE_RE.finditer(str(query or "")):
        number, paragraph = match.group(1), match.group(2)
        ref = f"Article {number}" + (f".{paragraph}" if paragraph else "")
        if anchor_exists(ref) and ref not in refs:
            refs.append(ref)
    for match in _ANNEX_RE.finditer(str(query or "")):
        ref = f"Annex {match.group(1).upper()}"
        if anchor_exists(ref) and ref not in refs:
            refs.append(ref)
    return tuple(refs)


# ── records ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ConceptRef:
    """One manifest row: a typed concept and the wires it anchors."""

    concept_id: str
    kind: str
    label: str
    anchors: tuple[str, ...]
    score: float
    reason: str


@dataclass(frozen=True, slots=True)
class ConceptRecord:
    """The resolved record for one concept id (read-only, existence-checked)."""

    concept_id: str
    kind: str
    label: str
    anchors: tuple[str, ...]
    obligations: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    evidence: tuple[OntologyEvidence, ...] = ()
    resolved: bool = True
    dropped_anchors: tuple[str, ...] = ()


# ── shadow telemetry (never on the request path) ─────────────────────────


@dataclass
class ShadowTrace:
    """What a shadow run browsed, resolved, and which anchors were used."""

    browsed: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    calls: int = 0
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "browsed": list(dict.fromkeys(self.browsed)),
            "resolved": list(dict.fromkeys(self.resolved)),
            "anchors": list(dict.fromkeys(self.anchors)),
            "used": list(dict.fromkeys(self.used)),
            "dropped_anchors": list(dict.fromkeys(self.dropped)),
        }


_TRACE = ShadowTrace()


def reset_shadow_trace() -> None:
    """Clear the process-local shadow trace (test / harness hygiene)."""
    global _TRACE
    _TRACE = ShadowTrace()


def shadow_trace() -> ShadowTrace:
    """The process-local shadow trace. Not part of any request response."""
    return _TRACE


def _grain_head(ref: str) -> str:
    """Head grain of a wire reference: ``Article 24.3`` → ``Article 24``."""
    return to_wire(ref).split(".")[0].strip()


def mark_used(candidate_refs: Iterable[str], wire_refs: Iterable[str]) -> tuple[str, ...]:
    """Record which browsed anchors the wire actually used, and return them.

    The comparison is at *head* grain: a wire reference ``Article 24.3`` uses a
    browsed anchor ``Article 24``.  Exact-string intersection would report every
    sub-point citation as an unused anchor and make the telemetry useless.
    """
    wire_heads = {_grain_head(ref) for ref in wire_refs}
    used = sorted({to_wire(ref) for ref in candidate_refs if _grain_head(ref) in wire_heads})
    _TRACE.used.extend(used)
    return tuple(used)


# ── browse ───────────────────────────────────────────────────────────────


def _clean_anchors(refs: Iterable[str], *, cap: int = MAX_ANCHORS_PER_CONCEPT) -> tuple[str, ...]:
    """Wire-form, existence-checked, order-preserving, capped anchors."""
    out: list[str] = []
    for ref in refs:
        wire = to_wire(ref)
        if not anchor_exists(wire):
            _TRACE.dropped.append(wire)
            continue
        if wire not in out:
            out.append(wire)
        if len(out) >= cap:
            break
    return tuple(out)


def _practice_refs(question: str, limit: int) -> list[ConceptRef]:
    text = str(question or "")
    scored: list[tuple[float, ConceptRef]] = []
    for practice in PRACTICE_REGISTRY.values():
        hits = _keyword_hits(text, practice.keywords)
        if not hits:
            continue
        anchors = _clean_anchors(practice.citation)
        if practice.related_high_risk_anchor:
            anchors = _clean_anchors((*anchors, practice.related_high_risk_anchor))
        if not anchors:
            continue
        scored.append(
            (
                float(len(hits)),
                ConceptRef(
                    concept_id=f"{KIND_PRACTICE}:{practice.id}",
                    kind=KIND_PRACTICE,
                    label=practice.short_name,
                    anchors=anchors,
                    score=float(len(hits)),
                    reason="keyword:" + ", ".join(sorted(hits)[:3]),
                ),
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1].concept_id))
    return [ref for _, ref in scored[:limit]]


def _annex_iii_refs(question: str, limit: int) -> list[ConceptRef]:
    text = str(question or "")
    scored: list[tuple[float, ConceptRef]] = []
    for category in ANNEX_III_REGISTRY.values():
        hits = _keyword_hits(text, category.keywords)
        if not hits:
            continue
        # Every Annex III category is anchored on Art. 6(2) + Annex III; the
        # category point itself is a legitimate wire anchor.
        anchors = _clean_anchors(("Art. 6", "Annex III", f"Annex III.{category.number}"))
        scored.append(
            (
                float(len(hits)),
                ConceptRef(
                    concept_id=f"{KIND_ANNEX_III}:{category.id}",
                    kind=KIND_ANNEX_III,
                    label=category.short_name,
                    anchors=anchors,
                    score=float(len(hits)),
                    reason="keyword:" + ", ".join(sorted(hits)[:3]),
                ),
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1].concept_id))
    return [ref for _, ref in scored[:limit]]


def _phase_refs(question: str, limit: int) -> list[ConceptRef]:
    text = str(question or "").lower()
    hits: list[ConceptRef] = []
    for phase in PHASE_REGISTRY.values():
        date_key = phase.effective_date.isoformat()
        decades = date_key.rsplit("-", 1)[0]
        if date_key in text or decades in text or str(phase.effective_date.year) in text:
            anchors = _clean_anchors(phase.articles)
            if not anchors:
                continue
            hits.append(
                ConceptRef(
                    concept_id=f"{KIND_PHASE}:{phase.id}",
                    kind=KIND_PHASE,
                    label=phase.label,
                    anchors=anchors,
                    score=1.0,
                    reason=f"date:{date_key}",
                )
            )
    hits.sort(key=lambda ref: ref.concept_id)
    return hits[:limit]


def _risk_refs(question: str, limit: int) -> list[ConceptRef]:
    """Risk classes the question engages, anchored on the provider's duties.

    A risk class is itself an ontology concept, and its anchors are derived
    from :func:`app.data.ontology.obligations_for` rather than re-listed here,
    so the browse surface cannot drift from the role matrix.
    """
    out: list[ConceptRef] = []
    for risk in risk_hints(question):
        anchors = _clean_anchors(obligations_for(ActorRole.PROVIDER, risk))
        if not anchors:
            continue
        out.append(
            ConceptRef(
                concept_id=f"{KIND_RISK}:{risk.value}",
                kind=KIND_RISK,
                label=risk.value,
                anchors=anchors,
                score=1.0,
                reason="risk-hint",
            )
        )
    return out[:limit]


def _role_refs(question: str, limit: int) -> list[ConceptRef]:
    roles = detect_roles(question)
    if not roles:
        return []
    hints = risk_hints(question)
    out: list[ConceptRef] = []
    for role in roles:
        risk = hints[0] if hints else None
        if risk is None:
            # No risk hint: surface the role's structural anchors (its own
            # defining article) rather than unioning every risk class, which
            # would be the over-broad behaviour the study is testing against.
            anchors = _clean_anchors(("Art. 3",))
            reason = "role:no-risk-hint"
        else:
            anchors = _clean_anchors(obligations_for(role, risk))
            reason = f"role:{role.value}×{risk.value}"
        if not anchors:
            continue
        out.append(
            ConceptRef(
                concept_id=f"{KIND_ROLE}:{role.value}:{(risk.value if risk else 'unknown')}",
                kind=KIND_ROLE,
                label=f"{role.value} × {(risk.value if risk else 'unclassified')}",
                anchors=anchors,
                score=2.0 if risk is not None else 1.0,
                reason=reason,
            )
        )
    out.sort(key=lambda ref: (-ref.score, ref.concept_id))
    return out[:limit]


def _provision_refs(question: str, limit: int) -> list[ConceptRef]:
    return [
        ConceptRef(
            concept_id=f"{KIND_PROVISION}:{ref}",
            kind=KIND_PROVISION,
            label=ref,
            anchors=(ref,),
            score=1.0,
            reason="explicit-mention",
        )
        for ref in _explicit_provisions(question)[:limit]
    ]


def browse_concepts(
    query: str,
    *,
    kind: str | None = None,
    limit: int = DEFAULT_BROWSE_LIMIT,
) -> tuple[ConceptRef, ...]:
    """Bounded typed manifest of the ontology concepts ``query`` engages.

    Deterministic, offline, no LLM. ``kind`` filters to one of
    :data:`CONCEPT_KINDS`; ``limit`` is clamped to :data:`MAX_BROWSE_LIMIT`.
    Anchors are existence-checked and wire-form.
    """
    started = time.perf_counter()
    capped = max(1, min(int(limit or DEFAULT_BROWSE_LIMIT), MAX_BROWSE_LIMIT))
    if kind is not None and kind not in CONCEPT_KINDS:
        raise ValueError(f"unknown concept kind {kind!r}")

    builders = {
        KIND_PROVISION: _provision_refs,
        KIND_PRACTICE: _practice_refs,
        KIND_ANNEX_III: _annex_iii_refs,
        KIND_RISK: _risk_refs,
        KIND_PHASE: _phase_refs,
        KIND_ROLE: _role_refs,
    }
    ordered = (
        (kind,)
        if kind
        else (KIND_PRACTICE, KIND_ANNEX_III, KIND_RISK, KIND_ROLE, KIND_PHASE, KIND_PROVISION)
    )

    refs: list[ConceptRef] = []
    for one in ordered:
        remaining = capped - len(refs)
        if remaining <= 0:
            break
        refs.extend(builders[one](query, remaining))

    _TRACE.calls += 1
    _TRACE.elapsed_ms += (time.perf_counter() - started) * 1000.0
    _TRACE.browsed.extend(ref.concept_id for ref in refs)
    return tuple(refs)


# ── resolve ──────────────────────────────────────────────────────────────


def _evidence_for(ref: str) -> OntologyEvidence | None:
    """Exact-support evidence record for one anchor, or ``None`` if absent."""
    try:
        from app.data.provision_text import get_provision_text  # noqa: PLC0415

        text = get_provision_text(to_internal(ref)) or get_provision_text(ref)
    except Exception:  # noqa: BLE001 — evidence is optional, never fatal
        return None
    if not text or not text.strip():
        return None
    quote = " ".join(text.split())
    digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    return OntologyEvidence(
        source_id="eur-lex-ai-act-consolidated",
        source_version=KB_VERSION,
        locator=ref,
        quote=quote[:240],
        content_hash=digest,
    )


def _constraints_for(anchors: tuple[str, ...], role: str | None, risk: str | None) -> tuple[str, ...]:
    """Constraint checks the wire already relies on, run read-only."""
    notes: list[str] = []
    unknown = [ref for ref in anchors if not anchor_exists(ref)]
    if unknown:
        notes.append("existence_fail:" + ",".join(unknown))
    if role and risk:
        role_enum = next(
            (item for item in ActorRole if item.value == role or item.name.lower() == role),
            None,
        )
        risk_enum = next(
            (item for item in RiskClass if item.value == risk or item.name.lower() == risk),
            None,
        )
        if role_enum is not None and risk_enum is not None:
            bound = obligations_for(role_enum, risk_enum)
            unbound = [ref for ref in anchors if ref not in {to_wire(b) for b in bound}]
            if unbound:
                notes.append("not_bound_for_role:" + ",".join(unbound))
    for anchor in anchors:
        neighbours = cross_refs(to_internal(anchor), limit=3)
        if not neighbours:
            continue
        bad = [to_wire(item) for item in neighbours if not anchor_exists(to_wire(item))]
        if bad:
            notes.append(f"xref_endpoint_fail:{anchor}->" + ",".join(bad))
    return tuple(notes)


def resolve_concept(
    concept_id: str,
    *,
    include_evidence: bool = False,
    include_constraints: bool = True,
) -> ConceptRecord:
    """Resolve one concept id to its existence-checked record.

    Unknown ids return ``resolved=False`` with an empty anchor tuple — the
    adapter never fabricates a provision to satisfy a lookup. Evidence records
    are opt-in because they read the corpus.
    """
    started = time.perf_counter()
    kind, _, rest = str(concept_id or "").partition(":")
    if kind not in CONCEPT_KINDS or not rest:
        _TRACE.calls += 1
        _TRACE.elapsed_ms += (time.perf_counter() - started) * 1000.0
        return ConceptRecord(concept_id=str(concept_id), kind=kind or "", label="", anchors=(), resolved=False)

    role: str | None = None
    risk: str | None = None

    if kind == KIND_PRACTICE:
        practice = PRACTICE_REGISTRY.get(rest)
        if practice is None:
            return ConceptRecord(concept_id=concept_id, kind=kind, label="", anchors=(), resolved=False)
        label = practice.short_name
        raw = list(practice.citation)
        if practice.related_high_risk_anchor:
            raw.append(practice.related_high_risk_anchor)
    elif kind == KIND_ANNEX_III:
        category = ANNEX_III_REGISTRY.get(rest)
        if category is None:
            return ConceptRecord(concept_id=concept_id, kind=kind, label="", anchors=(), resolved=False)
        label = category.short_name
        raw = ["Art. 6", "Annex III", f"Annex III.{category.number}"]
    elif kind == KIND_PHASE:
        phase = PHASE_REGISTRY.get(rest)
        if phase is None:
            return ConceptRecord(concept_id=concept_id, kind=kind, label="", anchors=(), resolved=False)
        label = phase.label
        raw = list(phase.articles)
    elif kind == KIND_RISK:
        risk_enum = next((item for item in RiskClass if item.value == rest), None)
        if risk_enum is None:
            return ConceptRecord(concept_id=concept_id, kind=kind, label="", anchors=(), resolved=False)
        risk = risk_enum.value
        label = risk_enum.value
        raw = list(obligations_for(ActorRole.PROVIDER, risk_enum))
    elif kind == KIND_ROLE:
        role, _, risk = rest.partition(":")
        role_enum = next((item for item in ActorRole if item.value == role), None)
        if role_enum is None:
            return ConceptRecord(concept_id=concept_id, kind=kind, label="", anchors=(), resolved=False)
        risk_enum = next((item for item in RiskClass if item.value == risk), None)
        if risk_enum is None:
            # The browse surface emits an explicit "no risk hint" role row so a
            # role question always has a resolvable manifest entry; it anchors
            # on Art. 3 (the definition of the role) and nothing else.
            label = f"{role_enum.value} × unclassified"
            raw = ["Art. 3"]
            risk = None
        else:
            label = f"{role_enum.value} × {risk_enum.value}"
            raw = list(obligations_for(role_enum, risk_enum))
    else:  # KIND_PROVISION
        label = rest
        raw = [rest]

    anchors = _clean_anchors(raw)
    obligations = anchors if kind == KIND_ROLE else ()
    constraints = _constraints_for(anchors, role, risk) if include_constraints else ()
    evidence: tuple[OntologyEvidence, ...] = ()
    if include_evidence:
        evidence = tuple(
            item for item in (_evidence_for(ref) for ref in anchors[:4]) if item is not None
        )

    _TRACE.calls += 1
    _TRACE.elapsed_ms += (time.perf_counter() - started) * 1000.0
    _TRACE.resolved.append(concept_id)
    _TRACE.anchors.extend(anchors)
    return ConceptRecord(
        concept_id=concept_id,
        kind=kind,
        label=label,
        anchors=anchors,
        obligations=obligations,
        constraints=constraints,
        evidence=evidence,
        resolved=bool(anchors),
    )


# ── the shadow retrieval arm ─────────────────────────────────────────────


def adapter_candidates(
    query: str,
    *,
    limit: int = DEFAULT_BROWSE_LIMIT,
    neighbours: int = MAX_XREF_NEIGHBOURS,
    expand_xrefs: bool = True,
) -> tuple[str, ...]:
    """Concept-first candidates: browse → resolve → one-hop xref expansion.

    Returns at most :data:`MAX_CANDIDATES` wire refs in deterministic order
    (concept anchors by manifest order, then their cross-reference neighbours).
    No BM25, no dense retrieval, no LLM — this is the independent arm.
    """
    out: list[str] = []
    for ref in browse_concepts(query, limit=limit):
        record = resolve_concept(ref.concept_id, include_constraints=False)
        for anchor in record.anchors:
            if anchor not in out:
                out.append(anchor)
    direct = len(out)
    if expand_xrefs and neighbours > 0:
        for anchor in out[:direct]:
            for neighbour in cross_refs(to_internal(anchor), limit=neighbours):
                wire = to_wire(neighbour)
                if anchor_exists(wire) and wire not in out:
                    out.append(wire)
    return tuple(out[:MAX_CANDIDATES])


__all__ = [
    "CONCEPT_KINDS",
    "DEFAULT_BROWSE_LIMIT",
    "KIND_ANNEX_III",
    "KIND_PHASE",
    "KIND_PRACTICE",
    "KIND_PROVISION",
    "KIND_RISK",
    "KIND_ROLE",
    "MAX_ANCHORS_PER_CONCEPT",
    "MAX_BROWSE_LIMIT",
    "MAX_CANDIDATES",
    "MAX_XREF_NEIGHBOURS",
    "ConceptRecord",
    "ConceptRef",
    "ShadowTrace",
    "adapter_candidates",
    "anchor_exists",
    "browse_concepts",
    "detect_roles",
    "mark_used",
    "reset_shadow_trace",
    "resolve_concept",
    "risk_hints",
    "shadow_trace",
    "to_internal",
    "to_wire",
]

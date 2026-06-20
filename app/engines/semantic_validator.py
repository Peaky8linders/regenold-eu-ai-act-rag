"""Round 138 — Semantic-contract pre-generation validator.

Steals the one genuinely-missing slice of the "Ontologies, Knowledge
Graphs, and a Semantic Layer" architecture (the Medium/LinkedIn post
audited this round) — the ENFORCE/GATE step that validates the *semantic
contract* BEFORE the LLM generates, instead of only via post-generation
guards (``citation_guard`` / ``cite_describe_guard`` / drift).

The audit found ~88% of the post's architecture already built (R69's
"~90%" stands). The genuine ~12% hole is exactly this: every guard the
codebase ships runs AFTER the LLM has already (mis)synthesised. The post's
own framing — GraphRAG alone does not (a) enforce ontology semantics on
the retrieved facts, (b) validate the retrieved bundle is mutually
consistent, (c) prevent the model mixing unrelated provisions into a
plausible-but-invalid answer — names the exact shape of the R128
``grb_04`` production failure (Article 6 grounded; Stage-2 free-associated
Articles 10/11 it could not support).

DESIGN — ADVISORY ONLY (the critical safety choice)
---------------------------------------------------
The post's ``validate_constraints`` node DROPS invalid candidates ("remove
'waterproof' if category=headphones"); the audit's first cut proposed a
"contradiction-drop". This validator deliberately does NEITHER. It emits a
short deterministic ``SEMANTIC CONTRACT`` annotation into the Stage-2
generation context and **never drops a reference or filters a candidate.**
Two hard-won reasons:

* Over-pruning hurts more than over-broad answers on this rubric
  (R16 / R49). Dropping a ref can only lose recall.
* For legal text a "contradiction" is usually a *nuance*: an Article 5
  prohibited-context + Article 6 high-risk-context co-citation is the
  CORRECT borderline-prohibition answer ("banned at the workplace,
  high-risk elsewhere"), not an error to demote.

Because it touches the Stage-2 context ONLY, it is byte-identical on the
deterministic davidath bench *by construction* (the TestClient bench never
runs Stage-2). The win lands on the live LLM-judge refs-faithfulness +
correctness axes, and on the V2 ``role_ambiguity`` / ``borderline_
prohibition`` axes.

Three deterministic checks, each emitting at most one advisory line:

1. CHAIN — when a high-risk gateway (Article 6 / an Annex III leaf) is in
   the grounded references, name the dependent Chapter-III obligation
   articles (9-15) that ARE present vs ABSENT, so the model grounds
   obligation claims in the present ones and does not invent the absent
   ones (the ``grb_04`` failure mode).
2. ROLE — when the question targets exactly ONE operator role (and is NOT
   a compound provider+deployer scenario the compound-role path already
   handles), name the obligations that role owes and flag the
   provider-only duties that do NOT apply unless an Article 25 flip occurs
   (the ``role_ambiguity`` live axis).
3. RISK-TIER — when both a prohibited (Article 5) and a high-risk
   (Article 6) provision are grounded, instruct the model to distinguish
   the prohibited context from the high-risk context (the
   ``borderline_prohibition`` live axis) rather than conflating them.

Pure stdlib + existing registries (``role_obligations``,
``entity_extractor``, ``scenario_classifier``). Fail-soft (never raises).
Env gate ``REGENOLD_SEMANTIC_CONTRACT`` (default ON; set ``=0`` to
disable). No I/O, no LLM call, no new pip deps.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

__all__ = [
    "SemanticContract",
    "is_enabled",
    "build_contract",
    "render",
    "contract_block",
]


# ──────────────────────────────────────────────────────────────────────────
# Env gate.
# ──────────────────────────────────────────────────────────────────────────


def is_enabled() -> bool:
    """``REGENOLD_SEMANTIC_CONTRACT`` — default ON.

    The block is additive Stage-2 context only, so the deterministic
    davidath bench (no wrapper → no Stage-2) is byte-identical whether
    this is ON or OFF. Default ON so the production live path gets the
    steer; ``=0`` reverts for a clean A/B.
    """
    return os.getenv("REGENOLD_SEMANTIC_CONTRACT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ──────────────────────────────────────────────────────────────────────────
# Ref normalisation — grounded refs arrive in internal form ("Art. 6",
# "Annex III", "Art. 13(2)(a)"). We address the article/annex ROOT.
# ──────────────────────────────────────────────────────────────────────────


_ART_RE = re.compile(r"\bart(?:icle)?\.?\s*0*(\d{1,3})\b", re.IGNORECASE)
_ANNEX_RE = re.compile(r"\bannex\s+([ivx]{1,5})\b", re.IGNORECASE)


def _base_article(ref: str) -> str | None:
    """``"Art. 13(2)(a)"`` → ``"Art. 13"``; non-article → ``None``."""
    m = _ART_RE.search(ref or "")
    return f"Art. {int(m.group(1))}" if m else None


def _base_annex(ref: str) -> str | None:
    """``"Annex III.5"`` → ``"Annex III"``; non-annex → ``None``."""
    m = _ANNEX_RE.search(ref or "")
    return f"Annex {m.group(1).upper()}" if m else None


def _grounded_roots(grounded_refs: Iterable[str]) -> set[str]:
    """Collapse the grounded refs to article/annex ROOT identifiers."""
    roots: set[str] = set()
    for ref in grounded_refs or ():
        base = _base_article(ref) or _base_annex(ref)
        if base:
            roots.add(base)
    return roots


def _to_user_facing(internal: str) -> str:
    """``"Art. 13"`` → ``"Article 13"``; ``"Annex III"`` stays."""
    m = _ART_RE.match(internal)
    if m:
        return f"Article {int(m.group(1))}"
    return internal


# ──────────────────────────────────────────────────────────────────────────
# Check 1 — high-risk obligation chain completeness.
#
# The core Chapter-III Section-2 obligation articles a high-risk gateway
# (Art. 6 / Annex III) triggers. Deliberately the TIGHT set (the design
# requirements 9-15), NOT the full graphrag_expand._HRAIS_CHAINS (which
# also pulls 16/26/43/47/49/72) — a one-line advisory must be focused.
# ──────────────────────────────────────────────────────────────────────────


_HIGH_RISK_GATEWAYS: tuple[str, ...] = ("Art. 6", "Annex III")
_CORE_HRAIS_OBLIGATIONS: tuple[str, ...] = (
    "Art. 9",
    "Art. 10",
    "Art. 11",
    "Art. 12",
    "Art. 13",
    "Art. 14",
    "Art. 15",
)


def _chain_line(roots: set[str]) -> str:
    if not any(g in roots for g in _HIGH_RISK_GATEWAYS):
        return ""
    present = [a for a in _CORE_HRAIS_OBLIGATIONS if a in roots]
    absent = [a for a in _CORE_HRAIS_OBLIGATIONS if a not in roots]
    # If every obligation article is already grounded there is nothing to
    # steer — the model has the full chain.
    if not absent:
        return ""
    present_fmt = ", ".join(_to_user_facing(a) for a in present)
    if present_fmt:
        return (
            "A high-risk classification (Article 6 / Annex III) triggers the "
            "Chapter III obligations in Articles 9-15 (risk management, data "
            "governance, technical documentation, record-keeping, "
            "transparency, human oversight, accuracy/robustness). The "
            f"references substantiate {present_fmt}; do not assert obligations "
            "from the other Articles 9-15 unless they appear in the references."
        )
    return (
        "A high-risk classification (Article 6 / Annex III) triggers the "
        "Chapter III obligations in Articles 9-15, but the references do not "
        "yet substantiate them; describe the classification itself and cite an "
        "obligation article only if it appears in the references."
    )


# ──────────────────────────────────────────────────────────────────────────
# Check 2 — operator-role obligation constraint.
#
# entity_extractor role keys → role_obligations IDs. The provider-only
# duties a non-provider does NOT owe unless Art. 25 flips it.
# ──────────────────────────────────────────────────────────────────────────


# entity_extractor uses British "authorised"; role_obligations uses
# American "authorized". Bridge the spelling; the other entity-extractor
# roles (notifying_authority / market_surveillance / ai_office) have no
# operator-obligation set and are intentionally absent.
_ROLE_KEY_TO_OBLIGATION_ID: dict[str, str] = {
    "provider": "provider",
    "deployer": "deployer",
    "importer": "importer",
    "distributor": "distributor",
    "authorised_representative": "authorized_representative",
}

_ROLE_DISPLAY: dict[str, str] = {
    "provider": "provider",
    "deployer": "deployer",
    "importer": "importer",
    "distributor": "distributor",
    "authorized_representative": "authorised representative",
}

# The provider-only duty headline a non-provider role does NOT owe unless
# it flips to provider under Art. 25 (own name/trademark, substantial
# modification, or change of intended purpose).
_PROVIDER_ONLY_HEADLINE = (
    "the Article 9-15 design requirements, conformity assessment "
    "(Article 43), the EU declaration of conformity (Article 47) and CE "
    "marking (Article 48)"
)


def _single_role(question: str) -> str | None:
    """Return the lone operator-role ID, or ``None``.

    Fires only when EXACTLY one distinct operator role is detected AND the
    question is not a compound provider+deployer scenario (the
    compound-role path owns those). Returns the ``role_obligations`` ID.
    """
    if not question:
        return None
    try:
        from app.engines.entity_extractor import (  # noqa: PLC0415
            extract_entities,
        )
        from app.engines.scenario_classifier import (  # noqa: PLC0415
            _detect_compound_roles,
            _normalise,
        )
    except Exception:  # noqa: BLE001
        return None

    try:
        ents = extract_entities(question)
    except Exception:  # noqa: BLE001
        return None
    role_keys = {
        eid
        for eid, _art in ents.get("role", ())
        if eid in _ROLE_KEY_TO_OBLIGATION_ID
    }
    if len(role_keys) != 1:
        return None

    # Suppress on compound provider+deployer (etc.) scenarios — the
    # compound-role budget/path already handles those, and a single-role
    # constraint line would be actively wrong there.
    try:
        compound = _detect_compound_roles(_normalise(question).lower())
    except Exception:  # noqa: BLE001
        compound = []
    if len({r for r in compound if r}) >= 2:
        return None

    return _ROLE_KEY_TO_OBLIGATION_ID[next(iter(role_keys))]


def _role_line(question: str) -> str:
    role_id = _single_role(question)
    if role_id is None:
        return ""
    try:
        from app.data.role_obligations import (  # noqa: PLC0415
            articles_for_role,
        )
    except Exception:  # noqa: BLE001
        return ""
    primaries = articles_for_role(role_id, include_secondary=False)
    if not primaries:
        return ""
    display = _ROLE_DISPLAY.get(role_id, role_id)
    art = "an" if display[:1].lower() in "aeiou" else "a"
    owed = ", ".join(_to_user_facing(a) for a in primaries)
    if role_id == "provider":
        # The provider owes the full chain (there is nothing to exclude),
        # so a "does-not-apply" steer would be noise. Affirm the duty set.
        return (
            f"The question concerns a provider; a provider's core duties are "
            f"{owed}."
        )
    return (
        f"The question concerns {art} {display}; {art} {display}'s duties are "
        f"{owed}. The provider-only duties ({_PROVIDER_ONLY_HEADLINE}) do NOT "
        f"apply to {art} {display} unless it becomes a provider under "
        f"Article 25 (putting its name/trademark on the system, a substantial "
        f"modification, or a change of intended purpose)."
    )


# ──────────────────────────────────────────────────────────────────────────
# Check 3 — prohibited vs high-risk tier distinction.
# ──────────────────────────────────────────────────────────────────────────


def _risk_tier_line(roots: set[str]) -> str:
    if "Art. 5" in roots and "Art. 6" in roots:
        return (
            "Both a prohibited practice (Article 5) and a high-risk "
            "classification (Article 6 / Annex III) are in scope. State the "
            "context in which the practice is prohibited under Article 5 and, "
            "separately, the context in which it is instead high-risk under "
            "Article 6; do not conflate the two tiers."
        )
    return ""


# ──────────────────────────────────────────────────────────────────────────
# Public API.
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class SemanticContract:
    """The advisory annotation + per-check trace notes."""

    lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.lines


def build_contract(
    question: str, grounded_refs: Iterable[str]
) -> SemanticContract:
    """Run the three deterministic checks; return the advisory contract.

    Pure-deterministic, never raises. Returns an empty contract when no
    check fires (the caller then omits the block).
    """
    contract = SemanticContract()
    try:
        roots = _grounded_roots(grounded_refs)

        chain = _chain_line(roots)
        if chain:
            contract.lines.append(chain)
            contract.notes.append("chain_completeness")

        role = _role_line(question or "")
        if role:
            contract.lines.append(role)
            contract.notes.append("role_constraint")

        tier = _risk_tier_line(roots)
        if tier:
            contract.lines.append(tier)
            contract.notes.append("risk_tier_distinction")
    except Exception:  # noqa: BLE001 — never let the validator 500 Stage-2
        return SemanticContract()
    return contract


_BLOCK_HEADER = (
    "SEMANTIC CONTRACT (legal constraints on the answer; honour before "
    "citing; cite only provisions in the references above):"
)


def render(contract: SemanticContract) -> str:
    """Render a prebuilt contract as the Stage-2 block, or ``""`` if empty."""
    if contract is None or contract.is_empty():
        return ""
    body = "\n".join(f"- {line}" for line in contract.lines)
    return f"{_BLOCK_HEADER}\n{body}\n\n"


def contract_block(question: str, grounded_refs: Iterable[str]) -> str:
    """Build + render the ``SEMANTIC CONTRACT`` Stage-2 block, or ``""``.

    Returns ``""`` when the env gate is off or no check fired — the caller
    then adds nothing to the Stage-2 user message. Convenience wrapper for
    callers that don't need the structured contract; the engine wiring
    calls :func:`build_contract` + :func:`render` directly so the trace
    notes are available without a second build.
    """
    if not is_enabled():
        return ""
    return render(build_contract(question, grounded_refs))

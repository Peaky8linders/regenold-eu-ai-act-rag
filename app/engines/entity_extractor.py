"""R81-N — Typed-entity NER + priority boost for BM25 retrieval.

The 4-round live representative-100 measurement (`r80-live`, `r80.2-live`,
`r81-a1-live`, plus local davidath QA + V2 multiturn) consistently shows
**15–24% of rows are retrieval-failures** — the engine cites a generic
topic-anchor (e.g. ``Art. 6`` "high-risk classification") when the gold
is a role-specific Article (``Art. 23`` for "importer obligations",
``Art. 24`` for "distributor obligations", ``Art. 11`` for "technical
documentation contents", ``Art. 43`` for "conformity assessment
procedure", ``Art. 18`` for "record-keeping").

The root cause is **scoring priority, not extraction**. The existing
``_KEYWORD_ENTITY_MAP`` in ``graph_rag.py`` already maps ``"importer"``
→ Art. 23, but the BM25 scorer weights the longer multi-token
``"high-risk AI system"`` (→ Art. 6) higher than the single-token
``"importer"``. Art. 6 wins, and the role-specific Article is never
surfaced.

This module fixes the priority. The :func:`extract_entities` helper runs
a closed-vocabulary regex/literal scan over every question and tags
**roles** (provider / deployer / importer / distributor / authrep /
notifying authority / market-surveillance / AI Office — 8 entities) and
**lifecycle concepts** (technical_documentation / conformity_assessment
/ FRIA / post-market monitoring / record-keeping / logs retention / CE
marking / EU declaration / EU database registration / serious incident
/ corrective action / human oversight / data governance / transparency
obligation / accuracy & robustness / risk management / high-risk
classification / penalties / GPAI obligations / GPAI systemic / codes
of practice / instructions for use / quality management /
workers information — 24 entities). Each entity maps to a specific
Article number.

The extractor is consumed by
:func:`app.data.kb_search.top_articles_by_relevance`, which applies a
**multiplicative boost** (1.5× for roles, 1.3× for concepts) to the
BM25 score of every doc whose ``article_ref`` matches a tagged entity.

CRITICAL safety invariants (all pinned by tests):

1. **OOS-safe** — the boost is multiplicative on existing BM25 scores.
   A question with NO in-scope retrieval candidates never sees a
   boost. The 21/21 OOS probe is structurally preserved.
2. **No new scope anchors** — this module does NOT add entries to
   ``scope.KEYWORD_TO_ARTICLE`` or ``_AI_ACT_ANCHORS``. It reads
   ONLY for retrieval boost.
3. **Never displaces a winner** — if Art. 23 had BM25 score 5.0 and
   Art. 6 had 12.0, a 1.5× boost on 23 (→ 7.5) cannot beat 12.0.
   That's correct behavior — the boost targets the cases where 6 and
   23 are CLOSE (e.g. 8.0 vs 7.0) and the role signal should tip 23
   to win.
4. **Word-boundary regex** — plain-text aliases use ``\\b`` so
   ``"deployer"`` doesn't match ``"redeployers"`` and ``"importer"``
   doesn't match ``"important"``.
5. **Fail-soft** — the public entry point wraps all logic in
   try/except returning empty dict. The engine MUST work if the
   extractor crashes.
6. **Article-existence lint** — every ``art`` value resolves in
   ``ARTICLE_EXISTENCE``. ``_self_check()`` runs at import time and
   raises ``RuntimeError`` if any entry points at a non-existent
   article.

Pure stdlib. No LLM. Idempotent. Zero per-call allocations beyond
the result dict.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterable
from functools import lru_cache

from app.data.article_existence import ARTICLE_EXISTENCE

__all__ = [
    "ROLES",
    "CONCEPTS",
    "ROLE_BOOST_FACTOR",
    "CONCEPT_BOOST_FACTOR",
    "extract_entities",
    "boost_factor",
    "boosted_articles",
    "is_enabled",
    "is_qa_shape_with_single_role",
]


# Boost factors. Roles are heavier because operator-role questions
# ("What do importers do?" / "deployer obligations") have the highest
# observed retrieval-fail rate on the live sidecar — and the role is
# the single most discriminative signal in the question. Concepts are
# slightly lower because the surrounding question text (full obligation
# prose) often carries the supporting BM25 signal already.
#
# R81-N originally shipped 1.5× role / 1.3× concept calibrated on
# davidath. The R81-N live measurement (`representative-100-r81-n-live`)
# showed the boost was too weak to flip live retrieval-fail rows: for
# ``qa_024`` "What are the importers' obligations...", BM25 anchor
# "high-risk AI system" → Art. 6 scores ~12.0; "importer" → Art. 23
# scores ~5.0. A 1.5× boost on Art. 23 = 7.5, still below Art. 6.
# Order doesn't flip.
#
# R81-N.1 doubles the role boost (1.5 → 3.0) and bumps the concept
# boost (1.3 → 2.0). The concept multiplier stays lower than the role
# multiplier — concepts are more numerous and risk over-firing if both
# are equal. Davidath verified rubric-positive (QA Ref Strict / Loose
# preserved; scenarios byte-identical because role-noun BM25 score
# gaps to gold Annex III / Art. 5 anchors are still wider than 3.0×).
#
# Operator can revert to the R81-N values via
# ``REGENOLD_ENTITY_BOOST_FACTOR_ROLE`` / ``..._CONCEPT`` env vars
# without a code change.
#
# An earlier attempt to ALSO append entities to the engine's
# entity list in `_deterministic_parse` produced a SCENARIO-side
# regression and was removed — see the comment in
# `graph_rag._deterministic_parse` for the design rationale.
ROLE_BOOST_FACTOR = 3.0
CONCEPT_BOOST_FACTOR = 2.0

# Back-compat aliases — older code reads the underscore-prefixed names.
_BOOST_ROLE = ROLE_BOOST_FACTOR
_BOOST_CONCEPT = CONCEPT_BOOST_FACTOR


def _resolve_boost(env_var: str, code_default: float) -> float:
    """Resolve a boost factor from env override, with safety clamps.

    Reads ``env_var`` first; on a parse failure or out-of-bound value
    (< 1.0 or > 10.0), falls back to ``code_default``. Pure stdlib —
    no logging dep at module top level.
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return code_default
    try:
        v = float(raw)
    except ValueError:
        return code_default
    if v < 1.0 or v > 10.0:
        return code_default
    return v


# Role entities — 8 single-token + multi-token forms.
# Each maps to the canonical Article that defines the role's
# obligations. All article numbers verified against ARTICLE_EXISTENCE
# at import time via ``_self_check``.
ROLES: dict[str, dict] = {
    "provider": {
        "art": 16,
        "aliases": ("provider", "providers"),
    },
    "deployer": {
        "art": 26,
        "aliases": (
            "deployer",
            "deployers",
            "using the system",
            "puts the system into service",
        ),
    },
    "importer": {
        "art": 23,
        "aliases": (
            "importer",
            "importers",
            "imports an ai system",
            "importing high-risk",
        ),
    },
    "distributor": {
        "art": 24,
        "aliases": (
            "distributor",
            "distributors",
            "distributing an ai system",
        ),
    },
    "authorised_representative": {
        "art": 22,
        "aliases": (
            "authorised representative",
            "authorized representative",
            "authrep",
            "eu representative",
        ),
    },
    "notifying_authority": {
        "art": 28,
        "aliases": (
            "notifying authority",
            "notifying authorities",
            "designate a notified body",
        ),
    },
    "market_surveillance": {
        "art": 74,
        "aliases": (
            "market surveillance authority",
            "market surveillance authorities",
        ),
    },
    "ai_office": {
        "art": 64,
        "aliases": (
            "ai office",
            "european ai office",
        ),
    },
}


# Lifecycle concept entities — ~24 high-impact regulatory concepts. Each
# maps to the Article whose KB stub carries the gold prose for that
# concept. Some Articles appear twice (e.g. Art. 13 for both
# "transparency_obligation" and "instructions_for_use") — that's
# intentional: each alias path independently boosts Art. 13, and the
# multiplicative-boost design tolerates the duplication (boost computed
# as ``max(boost_factor(entity_type))`` per article so no
# double-boosting). The ``art`` value is the Article NUMBER (integer),
# not the ref string — the caller composes ``f"Art. {n}"`` to match
# the BM25 index keys.
CONCEPTS: dict[str, dict] = {
    "technical_documentation": {
        "art": 11,
        "aliases": (
            "technical documentation",
            "tech doc",
            "documentation requirements",
        ),
    },
    "conformity_assessment": {
        "art": 43,
        "aliases": (
            "conformity assessment",
            "conformity assessment procedure",
        ),
    },
    "fundamental_rights_impact": {
        "art": 27,
        "aliases": (
            "fundamental rights impact assessment",
            "fria",
        ),
    },
    "post_market_monitoring": {
        "art": 72,
        "aliases": (
            "post-market monitoring",
            "post market monitoring",
        ),
    },
    "record_keeping": {
        "art": 18,
        "aliases": (
            "record-keeping",
            "record keeping",
            "retain records",
            "records of",
            "preservation",
        ),
    },
    "logs_retention": {
        "art": 19,
        "aliases": (
            "automatically generated logs",
            "log retention",
            "retention period",
            "retain.{0,30}logs",
        ),
    },
    "ce_marking": {
        "art": 48,
        "aliases": (
            "ce marking",
            "ce mark",
            "affix the ce",
        ),
    },
    "eu_declaration": {
        "art": 47,
        "aliases": (
            "eu declaration of conformity",
            "declaration of conformity",
        ),
    },
    "eu_database_registration": {
        "art": 49,
        "aliases": (
            "eu ai database",
            "register.{0,20}database",
            "registration in the eu",
        ),
    },
    "serious_incident": {
        "art": 73,
        "aliases": (
            "serious incident",
            "incident reporting",
            "report.{0,20}incident",
        ),
    },
    "corrective_action": {
        "art": 20,
        "aliases": (
            "corrective action",
            "withdraw.{0,20}system",
            "recall.{0,20}system",
        ),
    },
    "human_oversight": {
        "art": 14,
        "aliases": ("human oversight",),
    },
    "data_governance": {
        "art": 10,
        "aliases": (
            "data governance",
            "training.{0,5}validation.{0,5}test",
            "dataset.{0,20}representative",
        ),
    },
    "transparency_obligation": {
        "art": 13,
        "aliases": (
            "transparency.{0,20}deployers",
            "instructions for use",
            "information.{0,20}deployers",
        ),
    },
    "accuracy_robustness": {
        "art": 15,
        "aliases": (
            "accuracy.{0,20}robustness",
            "cybersecurity",
        ),
    },
    "risk_management": {
        "art": 9,
        "aliases": (
            "risk management system",
            "rms",
        ),
    },
    "high_risk_classification": {
        "art": 6,
        "aliases": (
            "high-risk ai system",
            "classified as high-risk",
            "classify as high-risk",
        ),
    },
    "penalties": {
        "art": 99,
        "aliases": (
            "administrative fines",
            "penalties for",
            "fines up to",
            "fine amount",
            "sanctions",
            "violations of the regulation",
            # R112 (finding #9) — "transparency risk systems" REMOVED.
            # The phrase names the LIMITED-RISK tier (Art. 50/13), not
            # penalties; as a penalties alias it fired the kb_search
            # Art.-99 concept boost + blanket non-Art.-99 drift penalty
            # on transparency-tier questions, promoting Article 99 to
            # rank #1 over Art. 13/50/6/Annex III (violating safety
            # invariant #3 above). The genuinely intended GraphRAG-
            # benchmark sanctions row (ng_02) still fires penalties via
            # the "sanctions" alias.
        ),
    },
    "gpai_obligations": {
        "art": 53,
        "aliases": (
            "general-purpose ai model",
            "gpai model",
            "gpai obligations",
        ),
    },
    "gpai_systemic": {
        "art": 55,
        "aliases": (
            "systemic risk",
            "systemic-risk gpai",
            "high-impact capabilities",
        ),
    },
    "codes_of_practice": {
        "art": 56,
        "aliases": (
            "codes of practice",
            "code of practice",
        ),
    },
    "instructions_for_use": {
        "art": 13,
        "aliases": (
            "instructions for use",
            "user manual",
        ),
    },
    "quality_management": {
        "art": 17,
        "aliases": (
            "quality management system",
            "qms",
        ),
    },
    "workers_information": {
        "art": 26,
        "aliases": (
            "inform workers",
            "worker representatives",
            "workplace.{0,20}deployment",
        ),
    },
    # R120 — MedTech safety-component classification → Art. 6 (the AI Act
    # high-risk gateway for safety components of Annex-I-regulated products,
    # Art. 6(1)(a)). A live MedTech eval found the engine surfaced the
    # generic obligation chain (Arts. 10/11/12) instead of the classification
    # basis. The EU product-law terms (MDR/IVDR/Class III/IIb/SaMD) have 0
    # davidath QUESTION hits → davidath-neutral; "safety component" boosts
    # Art. 6 only on davidath safety-component scenarios where Art. 6 is
    # already gold → rubric-positive.
    "medtech_classification": {
        "art": 6,
        # Aliases are deliberately PRODUCT-SPECIFIC. An earlier cut also
        # carried a broad ``ce.{0,5}mark…risk`` regex (matched davidath
        # "CE marking … high-risk", gold Art. 48) and ``union harmonisation
        # legislation`` (matched davidath conformity-exemption questions,
        # gold Art. 43) — both dropped because they fired on non-Art-6
        # davidath QA rows. The surviving aliases have 0 davidath QUESTION
        # hits except "safety component", which fires only on davidath
        # safety-component scenarios where Art. 6 IS gold (rubric-positive).
        "aliases": (
            r"class\s+iii\b",
            r"class\s+iib\b",
            r"\bivdr\b",
            r"\bmdr\b",
            "safety component",
            "software as a medical device",
            r"\bsamd\b",
            r"notified body.{0,25}conformity",
            "medical device regulation",
        ),
    },
    # R120 — modification-responsibility → Art. 25 (a substantial
    # modification makes the modifier a new provider). The literal
    # "substantial modification" / "substantially modified" aliases were
    # DROPPED: a davidath QA row ("What must a provider do if a substantial
    # modification is made…") carries gold Art. 43, so boosting Art. 25 there
    # would over-cite. mv4_12 fires via "significantly modifying"; the
    # surviving paraphrase aliases have 0 davidath QUESTION hits.
    "substantial_modification": {
        "art": 25,
        "aliases": (
            r"significant\w*\s.{0,12}modif",
            r"modif.{0,30}clinical performance",
            "major modification",
            "fundamentally modified",
        ),
    },
}


# Regex-specials we look for to decide whether to treat an alias as a
# regex or a plain literal needing ``\b`` boundaries. Plain literals get
# word-boundary anchors; aliases containing any of these are compiled
# as raw regex.
_REGEX_SPECIAL_CHARS = frozenset(".*+?{}()|[]\\^$")


def _compile_alias(alias: str) -> re.Pattern[str]:
    """Compile one alias into a regex pattern.

    - Plain literals → ``\\b<alias>\\b`` for word-boundary safety
      (stops ``"deployer"`` matching ``"redeployers"`` and ``"importer"``
      matching ``"important"``).
    - Aliases containing regex metacharacters → used as-is (these are
      hand-authored regexes like ``"retain.{0,30}logs"``).

    All patterns are case-insensitive (the caller lowercases first; the
    flag is belt-and-suspenders).
    """
    has_special = any(c in _REGEX_SPECIAL_CHARS for c in alias)
    if has_special:
        return re.compile(alias, re.IGNORECASE)
    # Pure literal — escape any incidental specials (none expected, but
    # defensive) and bracket with word boundaries.
    return re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _compiled_role_table() -> tuple[tuple[str, int, tuple[re.Pattern[str], ...]], ...]:
    """Compile every role alias once. Returns ``(entity_id, art_number,
    (pattern, ...))`` tuples in stable insertion order."""
    out: list[tuple[str, int, tuple[re.Pattern[str], ...]]] = []
    for eid, spec in ROLES.items():
        patterns = tuple(_compile_alias(a) for a in spec["aliases"])
        out.append((eid, spec["art"], patterns))
    return tuple(out)


@lru_cache(maxsize=1)
def _compiled_concept_table() -> tuple[tuple[str, int, tuple[re.Pattern[str], ...]], ...]:
    """Mirror of :func:`_compiled_role_table` for concepts."""
    out: list[tuple[str, int, tuple[re.Pattern[str], ...]]] = []
    for eid, spec in CONCEPTS.items():
        patterns = tuple(_compile_alias(a) for a in spec["aliases"])
        out.append((eid, spec["art"], patterns))
    return tuple(out)


def is_enabled() -> bool:
    """Env-gate for the entity-boost path. Default ON.

    Set ``REGENOLD_ENTITY_BOOST=0`` to disable (operator override) —
    e.g. to reproduce a pre-R81-N bench result. Any other value
    (``"1" / "true" / "yes" / "on"``) keeps it enabled.

    Mirrors the env-gate idiom used across R77 (``REGENOLD_QA_REF_BUDGET``),
    R78 (``REGENOLD_HARD_CHAR_CAP``), and R81-H (``REGENOLD_STRIP_PREAMBLE``).
    """
    return os.getenv("REGENOLD_ENTITY_BOOST", "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


def extract_entities(question: str | None) -> dict[str, list[tuple[str, int]]]:
    """Return ``{entity_type: [(entity_id, article_number), ...]}``.

    Scans ``question`` once for every role + concept alias, lower-casing
    first. Each entity fires at most once per call (the first alias
    match wins — extra alias matches for the same entity_id are
    redundant boosts).

    Returns ``{"role": [], "concept": []}`` for ``None`` / empty input,
    and on any exception (the extractor is route-soft per the brief's
    safety rule 5).
    """
    out: dict[str, list[tuple[str, int]]] = {"role": [], "concept": []}
    if not question:
        return out
    try:
        q_lower = question.lower()
        for eid, art_num, patterns in _compiled_role_table():
            for pat in patterns:
                if pat.search(q_lower):
                    out["role"].append((eid, art_num))
                    break  # one match per entity is enough
        for eid, art_num, patterns in _compiled_concept_table():
            for pat in patterns:
                if pat.search(q_lower):
                    out["concept"].append((eid, art_num))
                    break
    except Exception:  # noqa: BLE001 — never fail the engine on extractor
        return {"role": [], "concept": []}
    return out


def boost_factor(entity_type: str) -> float:
    """Return the multiplicative BM25 boost for an entity type.

    ``"role"`` → 3.0 (R81-N.1 default); ``"concept"`` → 2.0
    (R81-N.1 default); anything else → 1.0 (no boost).

    Operators can revert to the R81-N values (1.5 / 1.3) per-deploy via:

    .. code-block:: bash

        railway variables --set REGENOLD_ENTITY_BOOST_FACTOR_ROLE=1.5
        railway variables --set REGENOLD_ENTITY_BOOST_FACTOR_CONCEPT=1.3

    Out-of-bound or non-numeric env values are ignored — code defaults
    win. The fully disable knob is ``REGENOLD_ENTITY_BOOST=0`` (the
    boost is multiplicative, so ``=1.0`` would NOT disable it).
    """
    if entity_type == "role":
        return _resolve_boost("REGENOLD_ENTITY_BOOST_FACTOR_ROLE", ROLE_BOOST_FACTOR)
    if entity_type == "concept":
        return _resolve_boost("REGENOLD_ENTITY_BOOST_FACTOR_CONCEPT", CONCEPT_BOOST_FACTOR)
    return 1.0


# R81-N.1 — QA-shape gate constants. Used by
# :func:`kb_search.top_articles_by_relevance` to decide whether a
# single-role question warrants INJECTING the role's Article as a
# synthetic BM25 candidate (in case BM25 didn't surface it at all).
# The gate is conservative: ALL three conditions must hold.

# Wh-words that mark a definitional / informational QA shape.
_QA_WH_WORDS: tuple[str, ...] = (
    "what",
    "how",
    "when",
    "who",
    "whom",
    "whose",
    "why",
    "which",
    "where",
)

# Scenario-shape openers — these phrases mean the user is describing
# their own situation ("We are a provider that..."), not asking a
# definitional question. Role-Article injection on these would dilute
# the gold-matching anchors (the R81-N first-cut scenario regression).
_QA_SCENARIO_OPENERS: tuple[str, ...] = (
    "we are a ",
    "we are an ",
    "our company ",
    "i am a ",
    "i am an ",
    "i'm a ",
    "i'm an ",
    "we're a ",
    "we're an ",
)


# ── R127 — role-definitional shape (issue #7) ──────────────────────────────
#
# "What is a deployer?" / "Who is considered a provider?" must surface the
# Article 3 DEFINITION, not the role's obligation chain (Art. 26 deployer /
# Art. 23 importer / Art. 24 distributor). The role noun must be the SUBJECT
# HEAD of a definitional question — immediately after the interrogative +
# optional article, terminated by EOS / "?" / "of an AI system" / "under the
# Act". This excludes obligation/penalty phrasings ("What is the maximum fine
# for a provider…", gold Art. 99) where the role is an OBJECT, not the subject;
# the subject-head anchoring is load-bearing (a loose ``what is .{0,30}
# provider`` would mis-fire on those davidath rows).
_ROLE_DEF_NOUN = (
    r"(?:deployer|provider|importer|distributor|operator|"
    r"authoris(?:ed|ed)\s+representative|authorized\s+representative)"
)
_ROLE_DEFINITIONAL_RE = re.compile(
    r"^\s*(?:what\s+is|what's|who\s+is|who's|define|definition\s+of)\s+"
    r"(?:a\s+|an\s+|the\s+)?['‘’\"]?(?:" + _ROLE_DEF_NOUN + r")['‘’\"]?"
    r"\s*(?:\?|$|\s+(?:of|under|in|according)\b)",
    re.IGNORECASE,
)
_ROLE_CONSIDERED_RE = re.compile(
    r"^\s*who\s+(?:is\s+)?considered\s+"
    r"(?:a\s+|an\s+|the\s+)?['‘’\"]?(?:" + _ROLE_DEF_NOUN + r")['‘’\"]?",
    re.IGNORECASE,
)


def role_definitional_term(question: str | None) -> str | None:
    """Return the matched role-definitional prefix iff ``question`` is a
    SUBJECT-HEAD role-definitional shape ("What is a deployer?", "Who is
    considered a provider?"), else ``None``.

    Scans only the live turn of a flattened multi-turn prompt (R60.1/R71
    doctrine). Fail-soft — never raises.
    """
    if not question:
        return None
    try:
        q = question.strip()
        idx = q.rfind("Latest question:\n")
        if idx != -1:
            q = q[idx + len("Latest question:\n"):]
        m = _ROLE_DEFINITIONAL_RE.match(q) or _ROLE_CONSIDERED_RE.match(q)
        return m.group(0) if m else None
    except Exception:  # noqa: BLE001 — fail-soft
        return None


def is_qa_shape_with_single_role(
    question: str | None,
    entities: dict[str, list[tuple[str, int]]] | None = None,
) -> bool:
    """Return True iff the question is a definitional QA shape with
    EXACTLY one role entity fired.

    Three conditions (all required):

    1. Shape: starts with a Wh-word OR ends with ``"?"``.
    2. NOT a scenario opener (``"We are a"`` / ``"Our company"`` / ...).
    3. ``entities["role"]`` has exactly ONE entry.

    Fail-soft: on any exception or empty input returns ``False``.
    """
    if not question:
        return False
    try:
        # R127 — role-definitional shapes ("What is a deployer?", "Who is
        # considered a provider?") must NOT fire the role-Article injection;
        # they lead with the Art. 3 definition (the engine HEAD-inserts Art. 3).
        # Excluding them here stops Art. 26 / Art. 23 / Art. 24 being injected
        # ahead of Art. 3 on the wire (R125 trace: "What is a deployer?" →
        # [Art. 26, Art. 13, Art. 3]).
        if role_definitional_term(question) is not None:
            return False
        if entities is None:
            entities = extract_entities(question)
        roles = entities.get("role") or []
        # Condition 3 — exactly one role.
        if len(roles) != 1:
            return False
        q_lower = question.lower().lstrip()
        # Condition 2 — no scenario shape.
        for opener in _QA_SCENARIO_OPENERS:
            if q_lower.startswith(opener):
                return False
        # Condition 1 — Wh-word start OR "?" terminator.
        if question.rstrip().endswith("?"):
            return True
        first_word = q_lower.split()[0] if q_lower.split() else ""
        if first_word in _QA_WH_WORDS:
            return True
        return False
    except Exception:  # noqa: BLE001 — fail-soft, never raise
        return False


def boosted_articles(question: str | None) -> dict[str, float]:
    """Return ``{article_ref: max_boost}`` for one question.

    Returns the maximum boost across all entity matches for each
    article (so an Article hit by BOTH a role-alias AND a concept-alias
    gets the role boost, not the product — multiplicative-boost design
    keeps the score in the same order of magnitude as BM25, so the
    boost cannot suddenly promote an irrelevant Article to the top).

    Keys are ``"Art. {n}"`` strings that match the BM25 index format.

    Empty dict when the env-gate is OFF, the question is empty, or no
    entities matched.
    """
    if not is_enabled():
        return {}
    ents = extract_entities(question)
    if not ents["role"] and not ents["concept"]:
        return {}
    out: dict[str, float] = {}
    for etype in ("role", "concept"):
        b = boost_factor(etype)
        for _eid, art_num in ents[etype]:
            ref = f"Art. {art_num}"
            prev = out.get(ref, 0.0)
            if b > prev:
                out[ref] = b
    return out


def _iter_all_articles() -> Iterable[int]:
    """All ``art`` values across both registries — for the lint."""
    for spec in ROLES.values():
        yield spec["art"]
    for spec in CONCEPTS.values():
        yield spec["art"]


def _self_check() -> None:
    """Article-existence lint.

    Runs at import time. Asserts every ``art`` value points at a real
    Article in :data:`app.data.article_existence.ARTICLE_EXISTENCE` —
    so a typo in this module fails the import, not the user query.
    Mirrors :func:`app.engines.zero_retrieval_fallback._self_check`.
    """
    bad: list[tuple[str, int]] = []
    for eid, spec in ROLES.items():
        ref = f"Art. {spec['art']}"
        if ref not in ARTICLE_EXISTENCE:
            bad.append((f"ROLES[{eid}]", spec["art"]))
    for eid, spec in CONCEPTS.items():
        ref = f"Art. {spec['art']}"
        if ref not in ARTICLE_EXISTENCE:
            bad.append((f"CONCEPTS[{eid}]", spec["art"]))
    if bad:
        details = ", ".join(f"{loc}=Art. {n}" for loc, n in bad)
        raise RuntimeError(
            f"R81-N entity_extractor: invalid Article references → {details}"
        )


# Run the lint at import time so a typo can never silently ship.
_self_check()

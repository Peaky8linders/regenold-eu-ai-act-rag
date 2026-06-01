"""CLARA Paradigm — Neuro-Symbolic Logic & Generation Engine (Layer F).

Implements the architecture spec's decouple of *semantic appraisal* from
*verdict formulation*:

> "The LLM's role during risk assessment is constrained to establishing
>  context parameters (e.g. outputs boolean tags like
>  ``is_biometric_data = True``, ``used_by_law_enforcement = True``).
>  These structured flags are subsequently fed into a hardcoded,
>  unalterable Python-based deterministic logic matrix. This matrix
>  processes the final classification based strictly on the statutory
>  text, eliminating the risk of probabilistic logic errors or
>  hallucinated legal exemptions by the generative model."

## Pipeline

1.  Extract :class:`BooleanTags` from the user question — either via a
    deterministic regex/keyword extractor (default) or via an LLM
    extractor that asks the model only for boolean flags (no verdict).
2.  Feed the tags into :func:`compute_verdict` — a pure stdlib decision
    tree that encodes the AI Act's risk pyramid in priority order.
3.  Return ``(tags, verdict)``. The verdict carries citation chains
    drawn straight from the statutory text — no LLM speculation.

## Why this lives next to scenario_classifier instead of replacing it

* The Round-31 scenario classifier already handles "We are a {role}..."
  shaped scenarios. CLARA is the *general-purpose* analog — it accepts
  any question shape and emits a verdict + boolean fingerprint.
* The route can pick either path (or run both and reconcile). This
  module is purely additive — no existing file is modified.
* Boolean tags are a richer fingerprint than a single risk-level
  string. Downstream consumers (audit chain) can use them as features.

## Hard guarantees

* Module top-level import: pure stdlib + same-package imports only.
  Heavy / LLM deps (httpx, the openai_wrapper_provider) are
  lazy-imported inside :func:`extract_tags_llm` so cold startup stays
  sub-1 ms.
* :func:`compute_verdict` is a pure function: no I/O, no global
  mutable state, no LLM call. Same input → same output, always.
* :func:`compute_verdict` MUST NOT raise. Unknown combinations fall
  through to ``risk_tier="uncertain"``.
* The deterministic extractor reads keyword truth from
  :mod:`app.data.ontology` (``PRACTICE_REGISTRY`` +
  ``ANNEX_III_REGISTRY``) so we don't duplicate the source.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.data.ontology import ANNEX_III_REGISTRY, PRACTICE_REGISTRY

logger = logging.getLogger(__name__)


# ── BooleanTags ──────────────────────────────────────────────────────────


RiskTier = Literal[
    "prohibited",
    "high_risk",
    "limited",
    "minimal",
    "gpai",
    "gpai_systemic",
    "uncertain",
]


@dataclass(frozen=True)
class BooleanTags:
    """Structured boolean fingerprint of a question.

    Each flag corresponds to a specific statutory hook in the AI Act.
    The LLM (when used) is asked ONLY to set these flags from the
    question text — it is NEVER asked to render a verdict. The verdict
    is computed deterministically from this fingerprint by
    :func:`compute_verdict`.
    """

    # Data & subject-matter flags
    is_biometric_data: bool = False
    is_real_time_biometric: bool = False
    is_emotion_recognition: bool = False
    is_social_scoring: bool = False
    is_subliminal_or_manipulative: bool = False
    exploits_vulnerability: bool = False
    is_predictive_policing: bool = False
    is_workplace_emotion_recognition: bool = False
    is_education_emotion_recognition: bool = False
    is_biometric_categorisation_sensitive: bool = False  # race / political / religion

    # Use-context flags
    used_by_law_enforcement: bool = False
    used_in_workplace: bool = False
    used_in_education: bool = False
    used_in_medical_devices: bool = False
    used_in_critical_infrastructure: bool = False
    used_in_recruitment: bool = False
    used_in_essential_services_access: bool = False
    used_in_migration_asylum: bool = False
    used_in_judicial_law: bool = False

    # Role flags
    is_provider: bool = False
    is_deployer: bool = False
    is_importer: bool = False
    is_distributor: bool = False
    is_authorised_representative: bool = False
    is_small_mid_cap: bool = False

    # GPAI flags
    is_gpai_model: bool = False
    gpai_compute_above_systemic_threshold: bool = False  # 10^25 FLOPs
    gpai_open_weights: bool = False
    gpai_modification_above_one_third: bool = False  # one-third fine-tune rule

    # Geography / scope
    is_eu_market_placement: bool = False
    is_extraterritorial_non_eu: bool = False
    is_research_only: bool = False
    is_military_or_national_security: bool = False

    # Annex III safety-component flag
    is_annex_iii_safety_component: bool = False
    is_embedded_product_annex_i: bool = False

    # Transparency triggers (Art. 50) — kept beyond the spec list because
    # a chatbot / deepfake / synthetic-content scenario is the cleanest
    # "limited risk" signal we can extract from a free-text question.
    # Without these, the limited-risk branch only fires on the relatively
    # weak ``is_biometric_data AND NOT real_time AND NOT law_enforcement``
    # combination, which misses the common Art. 50 use-cases.
    is_chatbot_interaction: bool = False
    is_synthetic_content_generation: bool = False
    is_deepfake: bool = False

    # Free-form tags the deterministic extractor surfaces but the matrix
    # doesn't consume yet — kept for future use (audit chain feature
    # extraction, downstream sentence retrieval reranking).
    extra: tuple[str, ...] = field(default_factory=tuple)


# ── Verdict ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Verdict:
    """Output of :func:`compute_verdict` — a pure derivation from BooleanTags."""

    risk_tier: RiskTier
    primary_articles: tuple[str, ...]
    supporting_articles: tuple[str, ...]
    rationale: tuple[str, ...]
    confidence: float


# ── Deterministic keyword extraction ─────────────────────────────────────


# Use-context regex set. Compiled lazily on first call so module import
# stays cheap. The patterns are deliberately permissive — false-negatives
# hurt the route more than false-positives, since the verdict matrix
# applies its own conjunction logic on top (e.g. emotion_recognition
# alone is high-risk; only with workplace context does it become
# prohibited).

_USE_CONTEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "used_by_law_enforcement",
        re.compile(
            r"\b(?:law[\s\-]?enforcement|police|policing|"
            r"criminal\s+investigation|by\s+the\s+police|"
            r"by\s+law\s+enforcement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_workplace",
        re.compile(
            r"\b(?:workplace|workplaces|in\s+the\s+workplace|at\s+work|"
            r"in\s+a\s+work\s+context|on\s+employees|employee\s+monitoring|"
            r"on\s+workers|of\s+workers|of\s+employees)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_education",
        re.compile(
            r"\b(?:in\s+(?:the\s+)?classroom|education\s+institutions?|"
            r"in\s+(?:a\s+)?school|in\s+schools|at\s+school|in\s+universit(?:y|ies)|"
            r"on\s+students|of\s+students|in\s+education(?:al)?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_medical_devices",
        re.compile(
            r"\b(?:medical\s+device|medical[\s\-]device|MDR|IVDR|"
            r"in\s+vitro\s+diagnostic|medical\s+imaging|patient\s+vitals?|"
            r"medical\s+diagnos|clinical\s+decision|surgical|"
            r"radiology|healthcare\s+device|diagnostic\s+device|"
            r"medical\s+images?|classifies\s+medical)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_critical_infrastructure",
        re.compile(
            r"\b(?:critical\s+infrastructure|electricity\s+grid|energy\s+grid|"
            r"water\s+supply|gas\s+supply|road\s+traffic|critical\s+digital\s+"
            r"infrastructure)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_recruitment",
        re.compile(
            r"\b(?:recruitment|hiring|cv\s+screening|resume\s+screening|"
            r"candidate\s+screening|applicant\s+screening|hr\s+screening|"
            r"hiring\s+decision|selection\s+of\s+candidates|for\s+hiring|"
            r"job\s+applicant|recruiting)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_essential_services_access",
        re.compile(
            r"\b(?:credit\s+scor|creditworthiness|credit\s+decision|"
            r"loan\s+decision|insurance\s+pricing|insurance\s+underwriting|"
            r"welfare\s+eligibility|social\s+benefit|essential\s+service|"
            r"emergency\s+dispatch)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_migration_asylum",
        re.compile(
            r"\b(?:asylum|migration|border\s+control|visa\s+(?:application|"
            r"decision)|migrant|refugee)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "used_in_judicial_law",
        re.compile(
            r"\b(?:administration\s+of\s+justice|judicial\s+authorit|"
            r"assist\s+judges?|legal\s+interpretation|court\s+decision|"
            r"judicial\s+decision|judiciary)\b",
            re.IGNORECASE,
        ),
    ),
)


_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "is_provider",
        re.compile(
            r"\b(?:we\s+are\s+a\s+provider|as\s+a\s+provider|"
            r"the\s+provider|provider\s+of)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_deployer",
        re.compile(
            r"\b(?:we\s+are\s+a\s+deployer|as\s+a\s+deployer|"
            r"the\s+deployer|deployer\s+of)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_importer",
        re.compile(
            r"\b(?:we\s+are\s+an?\s+importer|as\s+an?\s+importer|"
            r"the\s+importer|importer\s+of)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_distributor",
        re.compile(
            r"\b(?:we\s+are\s+a\s+distributor|as\s+a\s+distributor|"
            r"the\s+distributor|distributor\s+of)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_authorised_representative",
        re.compile(
            r"\b(?:authoris(?:ed|er)\s+representative|authorized\s+representative)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_small_mid_cap",
        re.compile(
            r"\b(?:small\s+mid[\s\-]cap|small\s+mid\s+cap|SME|"
            r"small\s+or\s+medium[\s\-]sized\s+enterprise)\b",
            re.IGNORECASE,
        ),
    ),
)


_DATA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "is_biometric_data",
        re.compile(r"\bbiometric(?:s|\s+data)?\b", re.IGNORECASE),
    ),
    (
        "is_real_time_biometric",
        re.compile(
            r"\breal[\s\-]?time\b[^.]{0,40}\bbiometric\b|"
            r"\breal[\s\-]?time\s+remote\s+biometric\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_emotion_recognition",
        re.compile(
            r"\b(?:emotion\s+(?:recognition|inference|detection)|"
            r"emotion[\s\-]recognition|infer(?:s|ring)?\s+emotions?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_social_scoring",
        re.compile(r"\bsocial[\s\-]?scor(?:ing|e)\b", re.IGNORECASE),
    ),
    (
        "is_subliminal_or_manipulative",
        re.compile(
            r"\b(?:subliminal|subconscious|manipulative\s+technique|"
            r"deceptive\s+technique|covert\s+manipulation|covert\s+influence|"
            r"hidden\s+audio|hidden[\s\-]audio|subliminal\s+cue)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exploits_vulnerability",
        re.compile(
            r"\b(?:exploit(?:s|ing)?\s+(?:the\s+)?vulnerabilit|"
            r"exploit(?:s|ing)?\s+(?:the\s+)?(?:cognitive|financial|economic|"
            r"disability|elderly)|exploitation\s+of\s+(?:vulnerab|"
            r"low\s+income))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_predictive_policing",
        re.compile(
            r"\b(?:predictive\s+policing|predict(?:s|ing)?\s+criminal\s+"
            r"(?:risk|behaviour|behavior)|criminal[\s\-]?risk\s+profil|"
            r"predict(?:s|ing)?\s+the\s+risk\s+of\s+committing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_biometric_categorisation_sensitive",
        re.compile(
            r"\bbiometric\s+categori[sz]ation\b[^.]{0,80}"
            r"\b(?:race|racial|political|religion|religious|trade[\s\-]union|"
            r"sex\s+life|sexual\s+orientation|ethnic)\b|"
            r"\bcategori[sz]e\s+(?:people|persons)\s+by\s+(?:race|religion|"
            r"political|sexual)\b",
            re.IGNORECASE,
        ),
    ),
)


_GPAI_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "is_gpai_model",
        re.compile(
            r"\b(?:general[\s\-]purpose\s+AI|GPAI|foundation\s+model|"
            r"general[\s\-]purpose\s+(?:AI\s+)?model|large\s+language\s+model|"
            r"\bLLM\b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "gpai_open_weights",
        re.compile(
            r"\b(?:open[\s\-]weights?|open[\s\-]source\s+model|"
            r"weights?\s+(?:are\s+)?(?:publicly\s+)?released)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "gpai_modification_above_one_third",
        re.compile(
            r"\b(?:fine[\s\-]tun(?:e|ed|ing)|modif(?:y|ied|ication))\b[^.]{0,80}"
            r"\b(?:one[\s\-]?third|1/3|33\s?%|3\.3\s*[x×]\s*10\^?24)\b",
            re.IGNORECASE,
        ),
    ),
)


_GEOGRAPHY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "is_eu_market_placement",
        re.compile(
            r"\b(?:place\s+(?:it\s+)?on\s+the\s+(?:EU\s+)?market|"
            r"put\s+(?:it\s+)?into\s+service\s+in\s+the\s+(?:EU|Union)|"
            r"market\s+(?:it\s+)?in\s+(?:the\s+)?(?:EU|Europe))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_extraterritorial_non_eu",
        re.compile(
            r"\b(?:established\s+in\s+(?:a\s+)?third\s+country|"
            r"non[\s\-]EU\s+provider|outside\s+the\s+(?:EU|Union))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_research_only",
        re.compile(
            r"\b(?:research\s+only|purely\s+for\s+research|"
            r"scientific\s+research\s+purpose|R&D\s+only)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_military_or_national_security",
        re.compile(
            r"\b(?:military|national\s+security|defen[cs]e\s+purpose|"
            r"armed\s+forces)\b",
            re.IGNORECASE,
        ),
    ),
)


_TRANSPARENCY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "is_chatbot_interaction",
        re.compile(
            r"\b(?:chatbot|conversational\s+agent|virtual\s+assistant|"
            r"interacts?\s+with\s+(?:natural\s+)?persons?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_synthetic_content_generation",
        re.compile(
            r"\b(?:synthetic\s+(?:content|audio|image|video|text)|"
            r"AI[\s\-]generated\s+(?:content|text|image|audio|video))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "is_deepfake",
        re.compile(r"\bdeep[\s\-]?fake\b", re.IGNORECASE),
    ),
)


_ANNEX_III_SAFETY_PATTERN = re.compile(
    r"\b(?:safety\s+component\s+of\s+(?:a\s+)?product|"
    r"Annex\s+I\s+harmonisation|MDR|machinery\s+directive|toys?\s+safety)\b",
    re.IGNORECASE,
)


# Systemic-risk threshold detection — matches scientific notation and
# bare 10^25 / 10^26 / 1e25 / 1e26. Anything >= 10^25 FLOPs triggers
# the systemic-risk path per Art. 51 + Commission Guidelines (July 2025).
_SYSTEMIC_FLOPS_PATTERN = re.compile(
    r"\b(?:10\s*\^?\s*(2[5-9]|[3-9]\d)|1e\s*(2[5-9]|[3-9]\d)|"
    r"\d+(?:\.\d+)?\s*[x×]\s*10\s*\^?\s*(2[5-9]|[3-9]\d)|"
    r"systemic[\s\-]risk\s+threshold|systemic\s+risk\s+GPAI)\b",
    re.IGNORECASE,
)


def _flatten_history(history: Sequence[Mapping[str, object]] | None) -> str:
    """Flatten the last few turns of history to a single string.

    The deterministic extractor scans this concatenation alongside the
    live question — context like "we are a provider" might come from
    an earlier turn while the live question is a follow-up. Cap at 4
    turns to mirror the route's flatten-window convention.
    """
    if not history:
        return ""
    parts: list[str] = []
    for turn in list(history)[-4:]:
        content = turn.get("content") if isinstance(turn, Mapping) else None
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


def _ontology_practice_keywords() -> tuple[tuple[str, frozenset[str]], ...]:
    """Pull the Art. 5 practice keyword sets from the ontology.

    Returns ``((practice_id, frozenset(keyword_lower)), ...)``. Cached on
    first call — the ontology is import-time frozen so this is safe.
    """
    out: list[tuple[str, frozenset[str]]] = []
    for practice in PRACTICE_REGISTRY.values():
        kws = frozenset(k.lower() for k in practice.keywords if k)
        out.append((practice.id, kws))
    return tuple(out)


def _ontology_annex_keywords() -> tuple[tuple[str, frozenset[str]], ...]:
    out: list[tuple[str, frozenset[str]]] = []
    for category in ANNEX_III_REGISTRY.values():
        kws = frozenset(k.lower() for k in category.keywords if k)
        out.append((category.id, kws))
    return tuple(out)


_ONTOLOGY_PRACTICE_KW = _ontology_practice_keywords()
_ONTOLOGY_ANNEX_KW = _ontology_annex_keywords()


def _scan(text: str, patterns: Iterable[tuple[str, re.Pattern[str]]]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name, pattern in patterns:
        if pattern.search(text):
            out[name] = True
    return out


def extract_tags_deterministic(
    question: str,
    history: Sequence[Mapping[str, object]] | None = None,
) -> BooleanTags:
    """Pure regex + keyword extractor. Sub-millisecond, fully deterministic.

    Reads keyword truth from :data:`PRACTICE_REGISTRY` and
    :data:`ANNEX_III_REGISTRY` so the truth source is single-owner.
    """
    if not question:
        return BooleanTags()
    haystack = f"{_flatten_history(history)}\n{question}".strip()
    low = haystack.lower()

    flags: dict[str, bool] = {}
    flags.update(_scan(haystack, _DATA_PATTERNS))
    flags.update(_scan(haystack, _USE_CONTEXT_PATTERNS))
    flags.update(_scan(haystack, _ROLE_PATTERNS))
    flags.update(_scan(haystack, _GPAI_PATTERNS))
    flags.update(_scan(haystack, _GEOGRAPHY_PATTERNS))
    flags.update(_scan(haystack, _TRANSPARENCY_PATTERNS))

    # Ontology-driven supplementary scan. The regex bank above is the
    # primary path; this catches edge phrasings encoded in the
    # ontology's keyword field that we haven't expressed as regex.
    extras: list[str] = []
    for practice_id, kws in _ONTOLOGY_PRACTICE_KW:
        if any(kw in low for kw in kws):
            extras.append(f"practice:{practice_id}")
            # Mirror ontology hits into the matching boolean flags.
            if practice_id == "subliminal_manipulation":
                flags["is_subliminal_or_manipulative"] = True
            elif practice_id == "vulnerability_exploitation":
                flags["exploits_vulnerability"] = True
            elif practice_id == "social_scoring":
                flags["is_social_scoring"] = True
            elif practice_id == "profiling_for_criminal_risk":
                flags["is_predictive_policing"] = True
            elif practice_id == "emotion_recognition_workplace":
                flags["is_emotion_recognition"] = True
                # Workplace/education context fired here is a strong
                # signal but we only mirror to the dedicated context
                # flags when the question explicitly mentions one.
            elif practice_id == "biometric_categorisation_sensitive":
                flags["is_biometric_categorisation_sensitive"] = True
            elif practice_id == "real_time_rbi":
                flags["is_biometric_data"] = True
                flags["is_real_time_biometric"] = True
            elif practice_id == "facial_recognition_database":
                # Facial-recognition database scraping IS a biometric-data
                # operation under Art. 3(34); mirror the flag so downstream
                # transparency logic (Art. 50 biometric-data limited path)
                # has the signal.
                flags["is_biometric_data"] = True
    for category_id, kws in _ONTOLOGY_ANNEX_KW:
        if any(kw in low for kw in kws):
            extras.append(f"annex_iii:{category_id}")

    # Workplace/education emotion-recognition derived flags. These are
    # narrowed booleans that the matrix uses to short-circuit to Art.
    # 5(1)(f) without needing two separate joins.
    if flags.get("is_emotion_recognition"):
        if flags.get("used_in_workplace"):
            flags["is_workplace_emotion_recognition"] = True
        if flags.get("used_in_education"):
            flags["is_education_emotion_recognition"] = True

    # Annex I safety-component detection (embedded product).
    if _ANNEX_III_SAFETY_PATTERN.search(haystack):
        flags["is_embedded_product_annex_i"] = True

    # GPAI systemic-risk threshold — only fires when GPAI itself is True.
    if flags.get("is_gpai_model") and _SYSTEMIC_FLOPS_PATTERN.search(haystack):
        flags["gpai_compute_above_systemic_threshold"] = True

    return BooleanTags(extra=tuple(extras), **flags)


# ── LLM extractor (optional, env-gated, circuit-broken) ──────────────────


_LLM_FAILURE_THRESHOLD = int(os.getenv("REGENOLD_CLARA_FAILURE_THRESHOLD", "3"))
_LLM_FAILURE_WINDOW_SECONDS = float(os.getenv("REGENOLD_CLARA_FAILURE_WINDOW", "60"))
_LLM_TIMEOUT_SECONDS = float(os.getenv("REGENOLD_CLARA_TIMEOUT", "3.0"))
_LLM_MODEL = os.getenv("REGENOLD_CLARA_MODEL", "claude-haiku-4-5-20251001")


@dataclass
class _ClaraBreaker:
    failures: int = 0
    last_failure_ts: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_failure(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now - self.last_failure_ts > _LLM_FAILURE_WINDOW_SECONDS:
                self.failures = 1
            else:
                self.failures += 1
            self.last_failure_ts = now

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0
            self.last_failure_ts = 0.0

    def is_open(self) -> bool:
        with self.lock:
            if self.failures < _LLM_FAILURE_THRESHOLD:
                return False
            now = time.monotonic()
            if now - self.last_failure_ts > _LLM_FAILURE_WINDOW_SECONDS:
                self.failures = 0
                return False
            return True


_BREAKER = _ClaraBreaker()


_LLM_SYSTEM_PROMPT = """You are a deterministic feature extractor for the EU AI Act.

Read the user's question and emit a SINGLE JSON object (no prose, no
markdown fences) whose keys are a subset of the following booleans:

- is_biometric_data, is_real_time_biometric, is_emotion_recognition,
  is_social_scoring, is_subliminal_or_manipulative,
  exploits_vulnerability, is_predictive_policing,
  is_biometric_categorisation_sensitive
- used_by_law_enforcement, used_in_workplace, used_in_education,
  used_in_medical_devices, used_in_critical_infrastructure,
  used_in_recruitment, used_in_essential_services_access,
  used_in_migration_asylum, used_in_judicial_law
- is_provider, is_deployer, is_importer, is_distributor,
  is_authorised_representative, is_small_mid_cap
- is_gpai_model, gpai_compute_above_systemic_threshold,
  gpai_open_weights, gpai_modification_above_one_third
- is_eu_market_placement, is_extraterritorial_non_eu, is_research_only,
  is_military_or_national_security
- is_annex_iii_safety_component, is_embedded_product_annex_i
- is_chatbot_interaction, is_synthetic_content_generation, is_deepfake

Each value MUST be a JSON boolean (true/false). DO NOT emit any other
keys. DO NOT emit a verdict, risk tier, or article citations — only
the boolean fingerprint. The verdict is computed downstream by a
deterministic logic matrix.

OUTPUT ONLY the JSON object. No surrounding text."""

_LLM_USER_TEMPLATE = "Question: {q}\n\nJSON:"


_VALID_FLAG_NAMES: frozenset[str] = frozenset(
    f.name for f in BooleanTags.__dataclass_fields__.values()  # type: ignore[attr-defined]
    if f.name not in ("extra",)
)


def _hash_inputs(question: str, history_str: str) -> str:
    h = hashlib.sha256()
    h.update(question.strip().lower().encode("utf-8"))
    h.update(b"\0")
    h.update(history_str.strip().lower().encode("utf-8"))
    return h.hexdigest()


# Round 34 P1 — success-only cache. Pre-fix this function used
# ``@lru_cache(maxsize=256)`` which cached ``None`` failures permanently:
# a single transient wrapper outage would freeze the LLM-extraction path
# for that question until process restart. Now we use a bounded dict
# with explicit ``get`` / ``put`` and only ``put`` on the success path,
# mirroring ``app/llm/intent_classifier.py`` (see line ~440 there).
_LLM_CACHE: dict[str, BooleanTags] = {}
_LLM_CACHE_ORDER: list[str] = []
_LLM_CACHE_MAX = 256
_LLM_CACHE_LOCK = threading.RLock()


def _llm_cache_get(cache_key: str) -> BooleanTags | None:
    """Return a cached BooleanTags or None on miss. Thread-safe."""
    with _LLM_CACHE_LOCK:
        return _LLM_CACHE.get(cache_key)


def _llm_cache_put(cache_key: str, tags: BooleanTags) -> None:
    """Insert into bounded LRU. Pop the oldest when full. Thread-safe."""
    with _LLM_CACHE_LOCK:
        if cache_key in _LLM_CACHE:
            return
        _LLM_CACHE[cache_key] = tags
        _LLM_CACHE_ORDER.append(cache_key)
        while len(_LLM_CACHE_ORDER) > _LLM_CACHE_MAX:
            stale = _LLM_CACHE_ORDER.pop(0)
            _LLM_CACHE.pop(stale, None)


def _llm_cached(cache_key: str, question: str, history_str: str) -> BooleanTags | None:
    """Lazy-imported LLM call. ``cache_key`` is the hash that drives the cache.

    Cache semantics (Round 34): hits return immediately; misses run the
    LLM call. **Only successful results are cached.** Transient failures
    (timeout, parse error, circuit-breaker open) return ``None`` but
    leave the cache key empty so the NEXT identical question retries the
    LLM. The deterministic ``extract_tags_deterministic`` fallback handles
    the route's actual answer-shaping work; this cache only optimises
    repeat LLM hits.
    """
    cached = _llm_cache_get(cache_key)
    if cached is not None:
        return cached
    # Local import — keeps the top-level import cheap and lets test
    # suites monkey-patch the import on a per-test basis.
    try:
        from app.llm.openai_wrapper_provider import (
            OpenAIWrapperRequest,
            get_openai_wrapper_provider,
        )
    except Exception:  # noqa: BLE001 — defensive against partial installs
        return None

    provider = get_openai_wrapper_provider()
    user = _LLM_USER_TEMPLATE.format(q=question.strip()[-1500:])
    try:
        response = provider.complete(
            OpenAIWrapperRequest(
                system=_LLM_SYSTEM_PROMPT,
                user=user,
                model=_LLM_MODEL,
                max_tokens=400,
                temperature=0.0,
                timeout_seconds=_LLM_TIMEOUT_SECONDS,
            )
        )
    except Exception as exc:  # noqa: BLE001 — wrapper bugs MUST NOT raise out
        logger.debug("clara_llm_call_raised: %s", exc)
        _BREAKER.record_failure()
        return None

    if getattr(response, "error", None):
        logger.debug("clara_llm_error: %s", str(response.error)[:120])
        _BREAKER.record_failure()
        return None

    parsed = _parse_llm_json(getattr(response, "text", "") or "")
    if parsed is None:
        _BREAKER.record_failure()
        return None
    _BREAKER.record_success()
    _llm_cache_put(cache_key, parsed)
    return parsed


def _parse_llm_json(text: str) -> BooleanTags | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    blob = text[start:end + 1]
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    clean: dict[str, bool] = {}
    for key, value in data.items():
        if not isinstance(key, str) or key not in _VALID_FLAG_NAMES:
            continue
        if isinstance(value, bool):
            clean[key] = value

    if not clean:
        return None

    try:
        return BooleanTags(**clean)
    except TypeError:
        return None


def extract_tags_llm(
    question: str,
    history: Sequence[Mapping[str, object]] | None = None,
) -> BooleanTags | None:
    """Lazy-imported LLM extractor. Returns ``None`` on any failure path.

    * Returns ``None`` when the wrapper isn't enabled
      (``is_openai_wrapper_enabled()`` is False).
    * Returns ``None`` when the circuit breaker is open.
    * Returns ``None`` when the LLM response is malformed.
    * Cached via :func:`functools.lru_cache` on a SHA-256 over
      ``(question, history)``.
    """
    if not question:
        return None
    try:
        from app.llm.openai_wrapper_provider import is_openai_wrapper_enabled
    except Exception:  # noqa: BLE001
        return None
    if not is_openai_wrapper_enabled():
        return None
    if _BREAKER.is_open():
        return None
    history_str = _flatten_history(history)
    key = _hash_inputs(question, history_str)
    return _llm_cached(key, question, history_str)


# ── Risk-tier priority matrix ────────────────────────────────────────────


def _verdict(
    risk_tier: RiskTier,
    primary: tuple[str, ...],
    supporting: tuple[str, ...],
    rationale: tuple[str, ...],
    confidence: float,
) -> Verdict:
    return Verdict(
        risk_tier=risk_tier,
        primary_articles=primary,
        supporting_articles=supporting,
        rationale=rationale,
        confidence=max(0.0, min(1.0, confidence)),
    )


# ── R47-C — Compound-role aware augmentation ─────────────────────────────


_HIGH_TIER_TIERS: frozenset[str] = frozenset(
    {"high_risk", "gpai", "gpai_systemic"}
)


def _compound_role_tags(tags: BooleanTags) -> list[str]:
    """Map :class:`BooleanTags` role flags to role-obligation matrix IDs.

    Returns the list of role IDs whose flag fires. Order matches the
    role-obligation matrix priority (provider → deployer → importer →
    distributor → authorized_representative). The mapping for
    ``is_authorised_representative`` (British spelling on the
    BooleanTags field) is the role-obligation matrix's canonical id
    ``authorized_representative`` (American spelling — matches
    ROLE_AUTHORIZED_REPRESENTATIVE in role_obligations.py).
    """
    out: list[str] = []
    if tags.is_provider:
        out.append("provider")
    if tags.is_deployer:
        out.append("deployer")
    if tags.is_importer:
        out.append("importer")
    if tags.is_distributor:
        out.append("distributor")
    if tags.is_authorised_representative:
        out.append("authorized_representative")
    return out


def _augment_with_compound_roles(
    verdict: Verdict, tags: BooleanTags
) -> Verdict:
    """Surface union role-obligation articles when 2+ role flags fire.

    Strictly additive. Gated on:

    * ``len(role_ids) >= 2`` — single-role verdicts are unchanged.
    * ``verdict.risk_tier`` in :data:`_HIGH_TIER_TIERS` — only high-risk
      / GPAI / GPAI-systemic verdicts get the compound boost; for
      limited / minimal / prohibited the existing single-article
      verdict already covers the case.

    Articles are appended to ``supporting_articles`` (never overwrite
    ``primary_articles``) and deduped against the existing entries.
    The rationale tuple gains a single sentence explaining the
    compound-role context.
    """
    if verdict.risk_tier not in _HIGH_TIER_TIERS:
        return verdict
    role_ids = _compound_role_tags(tags)
    if len(role_ids) < 2:
        return verdict
    # Lazy-import to keep the cold path stdlib-only.
    try:
        from app.data.article_existence import ARTICLE_EXISTENCE  # noqa: PLC0415
        from app.data.role_obligations import (  # noqa: PLC0415
            ROLE_OBLIGATION_BY_ID,
        )
    except Exception:  # noqa: BLE001
        return verdict

    # Aggregate primary + secondary article refs from each role, dedup
    # against existing primary + supporting, validate existence.
    existing: set[str] = set(verdict.primary_articles) | set(
        verdict.supporting_articles
    )
    # CLARA uses publication form ("Article N") while role_obligations.py
    # uses internal form ("Art. N"). Build a publication-form view for
    # dedup compatibility, then emit publication form for new entries.
    existing_norm: set[str] = set()
    for ref in existing:
        existing_norm.add(_normalise_clara_ref(ref))

    additions: list[str] = []
    for role_id in role_ids:
        entry = ROLE_OBLIGATION_BY_ID.get(role_id)
        if not entry:
            continue
        for ref in list(entry.get("primary_articles", [])) + list(
            entry.get("secondary_articles", [])
        ):
            parent = ref.split("(")[0].strip()
            # ``parent`` is in internal form ``Art. N``; convert to
            # ``Art. N`` membership check against ARTICLE_EXISTENCE.
            if parent not in ARTICLE_EXISTENCE:
                continue
            # Convert ref to publication form ("Article N") that the
            # rest of CLARA emits.
            pub_form = _to_publication_form(ref)
            if not pub_form:
                continue
            if _normalise_clara_ref(pub_form) in existing_norm:
                continue
            existing_norm.add(_normalise_clara_ref(pub_form))
            additions.append(pub_form)
    if not additions:
        return verdict
    new_supporting = tuple(list(verdict.supporting_articles) + additions)
    role_labels = ", ".join(role_ids)
    new_rationale = tuple(
        list(verdict.rationale)
        + [
            (
                "Multiple operator-role flags fired ("
                f"{role_labels}); the obligation chains under each role "
                "are aggregated per the role-obligation matrix."
            )
        ]
    )
    return Verdict(
        risk_tier=verdict.risk_tier,
        primary_articles=verdict.primary_articles,
        supporting_articles=new_supporting,
        rationale=new_rationale,
        confidence=verdict.confidence,
    )


_ART_INTERNAL_RE = re.compile(r"^Art\.\s*(\d+)(.*)$")


def _to_publication_form(ref: str) -> str | None:
    """Convert ``Art. 9`` / ``Art. 25(4)`` → ``Article 9`` / ``Article 25.4``.

    Returns ``None`` on any malformed input. Mirrors the form CLARA's
    existing rationale uses (the verdict matrix emits ``"Article 5.1.c"``
    rather than ``"Art. 5(1)(c)"``).
    """
    if not ref:
        return None
    m = _ART_INTERNAL_RE.match(ref.strip())
    if not m:
        return None
    num = m.group(1)
    rest = m.group(2)
    # Convert "(4)" → ".4", "(1)(a)" → ".1.a".
    rest_pub = re.sub(r"\((\w+)\)", r".\1", rest).strip()
    return f"Article {num}{rest_pub}"


def _normalise_clara_ref(ref: str) -> str:
    """Lowercase + strip-internal-spaces normalisation for dedup keys."""
    if not ref:
        return ""
    return re.sub(r"\s+", " ", ref.strip().lower())


def compute_verdict(tags: BooleanTags) -> Verdict:
    """Deterministic logic matrix — pure function, never raises.

    Encodes the AI Act's risk pyramid in priority order. The first
    matching condition wins; conflicts are resolved by the
    ``prohibited > high_risk > gpai_systemic > gpai > limited > minimal``
    precedence.

    Confidence:

    * 1.0 — clean match on an explicit prohibited / high-risk practice
      with a single statutory hook.
    * 0.7 — verdict relies on a single inference (e.g. emotion
      recognition without an explicit workplace marker, but the
      matrix infers context from a sibling flag).
    * 0.4 — only the default minimal-risk branch fires.
    * < 0.4 — :data:`risk_tier` becomes ``"uncertain"``.

    The matrix is :ref:`unalterable` — no global mutable state, no
    branches that read env vars, no I/O. Same input → same output.
    """
    # Guard: NEVER raise on any input. Defensive isinstance keeps the
    # matrix robust against future BooleanTags subclasses or a caller
    # that passed a dict-shaped duck.
    if not isinstance(tags, BooleanTags):
        return _verdict(
            risk_tier="uncertain",
            primary=(),
            supporting=(),
            rationale=("Input was not a BooleanTags instance.",),
            confidence=0.0,
        )

    # ── Tier 1: PROHIBITED practices (Art. 5) ────────────────────────────
    #
    # Priority order within tier 1 reflects severity + how cleanly the
    # statutory text binds: social scoring and subliminal manipulation
    # are clean substring catches; real-time RBI requires conjunction
    # with law-enforcement; biometric-categorisation-sensitive is a
    # standalone clean catch.

    if tags.is_social_scoring:
        return _verdict(
            risk_tier="prohibited",
            primary=("Article 5.1.c",),
            supporting=("Article 5", "Article 99"),
            rationale=(
                "Social scoring of natural persons is a prohibited "
                "practice under Article 5(1)(c) of the EU AI Act.",
                "Article 99 penalties apply to infringements of "
                "Article 5 prohibitions.",
            ),
            confidence=1.0,
        )

    if tags.is_subliminal_or_manipulative:
        return _verdict(
            risk_tier="prohibited",
            primary=("Article 5.1.a",),
            supporting=("Article 5", "Article 99"),
            rationale=(
                "Subliminal, manipulative, or deceptive techniques that "
                "materially distort behaviour are prohibited under "
                "Article 5(1)(a).",
            ),
            confidence=1.0,
        )

    if tags.exploits_vulnerability:
        return _verdict(
            risk_tier="prohibited",
            primary=("Article 5.1.b",),
            supporting=("Article 5", "Article 99"),
            rationale=(
                "Exploitation of vulnerabilities of a person or group "
                "(age, disability, social or economic situation) is "
                "prohibited under Article 5(1)(b).",
            ),
            confidence=1.0,
        )

    if tags.is_predictive_policing:
        return _verdict(
            risk_tier="prohibited",
            primary=("Article 5.1.d",),
            supporting=("Article 5", "Article 99", "Annex III"),
            rationale=(
                "Predictive-policing AI based solely on profiling or "
                "personality traits is prohibited under Article 5(1)(d). "
                "Fact-based risk assessment supporting a human decision "
                "remains permitted but is high-risk under Annex III(6).",
            ),
            confidence=1.0,
        )

    if tags.is_biometric_categorisation_sensitive:
        return _verdict(
            risk_tier="prohibited",
            primary=("Article 5.1.g",),
            supporting=("Article 5", "Article 99"),
            rationale=(
                "Biometric categorisation that deduces race, political "
                "opinion, religion, trade-union membership, sex life, or "
                "sexual orientation is prohibited under Article 5(1)(g).",
            ),
            confidence=1.0,
        )

    if tags.is_real_time_biometric and tags.used_by_law_enforcement:
        return _verdict(
            risk_tier="prohibited",
            primary=("Article 5.1.h",),
            supporting=("Article 5", "Annex II", "Article 99"),
            rationale=(
                "Real-time remote biometric identification in publicly "
                "accessible spaces for law-enforcement purposes is "
                "prohibited under Article 5(1)(h), subject to narrow "
                "judicially-authorised exceptions for missing persons, "
                "imminent threats to life, and Annex II serious crimes.",
            ),
            confidence=1.0,
        )

    # Emotion recognition: prohibited only in workplace OR education.
    # Use either the explicit workplace/education emotion flags OR the
    # general emotion + use-context combo, so the LLM extractor (which
    # may not bother filling the narrowed flags) still routes correctly.
    if tags.is_emotion_recognition and (
        tags.is_workplace_emotion_recognition
        or tags.is_education_emotion_recognition
        or tags.used_in_workplace
        or tags.used_in_education
    ):
        # Medical-device carve-out: emotion recognition in a medical
        # device context is HIGH-RISK, not prohibited (Recital 18 /
        # Commission Guidelines Feb 2025 narrow safety interpretation).
        if tags.used_in_medical_devices:
            return _verdict(
                risk_tier="high_risk",
                primary=("Article 6",),
                supporting=("Annex III", "Article 9", "Article 10", "Article 13"),
                rationale=(
                    "Emotion recognition in a medical-device context "
                    "falls under the narrow safety carve-out from the "
                    "Article 5(1)(f) workplace/education prohibition and "
                    "is high-risk under Article 6 and Annex III.",
                ),
                confidence=0.7,
            )
        return _verdict(
            risk_tier="prohibited",
            primary=("Article 5.1.f",),
            supporting=("Article 5", "Annex III", "Article 99"),
            rationale=(
                "Emotion recognition in workplace or education contexts "
                "is prohibited under Article 5(1)(f), subject only to "
                "narrow medical or safety carve-outs.",
            ),
            confidence=1.0,
        )

    # ── Tier 2: HIGH-RISK (Art. 6 + Annex III / Annex I) ─────────────────
    #
    # Emotion recognition outside workplace/education and outside
    # medical contexts is Annex III(1)(c). Pull it before the broad
    # Annex III scan so the rationale is precise.

    if tags.is_emotion_recognition and tags.used_in_medical_devices:
        return _verdict(
            risk_tier="high_risk",
            primary=("Article 6",),
            supporting=("Annex III", "Article 9", "Article 10", "Article 13"),
            rationale=(
                "Emotion recognition in a medical-device context is "
                "high-risk under Article 6 and Annex III; the workplace "
                "prohibition does not apply.",
            ),
            confidence=0.7,
        )

    if tags.is_emotion_recognition:
        return _verdict(
            risk_tier="high_risk",
            primary=("Article 6",),
            supporting=(
                "Annex III",
                "Article 9", "Article 10", "Article 11",
                "Article 13", "Article 14", "Article 15",
            ),
            rationale=(
                "Emotion recognition outside workplace and education "
                "contexts is high-risk under Annex III(1)(c) with the "
                "full Chapter III Section 2 obligations.",
            ),
            confidence=0.8,
        )

    # Annex I embedded-product safety-component path.
    if tags.is_embedded_product_annex_i or tags.is_annex_iii_safety_component:
        return _verdict(
            risk_tier="high_risk",
            primary=("Article 6",),
            supporting=(
                "Annex I",
                "Article 9", "Article 10", "Article 11",
                "Article 13", "Article 14", "Article 15",
                "Article 43",
            ),
            rationale=(
                "AI used as a safety component of a product covered by "
                "Annex I harmonisation legislation is high-risk under "
                "Article 6(1) and requires third-party conformity "
                "assessment under Article 43.",
            ),
            confidence=1.0,
        )

    # Annex III use-case categories.
    annex_iii_signals = (
        tags.used_in_critical_infrastructure,
        tags.used_in_recruitment,
        tags.used_in_essential_services_access,
        tags.used_in_migration_asylum,
        tags.used_in_judicial_law,
        tags.used_in_medical_devices,
        tags.used_in_education,
    )
    if any(annex_iii_signals):
        # Build the rationale string from the active categories so the
        # answer is specific. The matrix stays pure — no I/O.
        category_phrases: list[str] = []
        if tags.used_in_critical_infrastructure:
            category_phrases.append("critical infrastructure (Annex III(2))")
        if tags.used_in_recruitment:
            category_phrases.append("employment and recruitment (Annex III(4))")
        if tags.used_in_essential_services_access:
            category_phrases.append("essential services and creditworthiness (Annex III(5))")
        if tags.used_in_migration_asylum:
            category_phrases.append("migration, asylum, and border control (Annex III(7))")
        if tags.used_in_judicial_law:
            category_phrases.append("administration of justice (Annex III(8))")
        if tags.used_in_medical_devices:
            category_phrases.append(
                "AI in medical devices (Annex I / Article 6(1) safety-component path)"
            )
        if tags.used_in_education:
            category_phrases.append("education and vocational training (Annex III(3))")
        category_blob = "; ".join(category_phrases) or "an Annex III high-risk use case"
        return _verdict(
            risk_tier="high_risk",
            primary=("Article 6",),
            supporting=(
                "Annex III",
                "Article 9", "Article 10", "Article 11",
                "Article 13", "Article 14", "Article 15",
                "Article 26",
            ),
            rationale=(
                f"This use case falls under {category_blob}, making the "
                "system high-risk under Article 6 with the full "
                "Chapter III Section 2 obligations (risk management, data "
                "governance, technical documentation, logging, "
                "transparency, human oversight, accuracy and robustness).",
            ),
            confidence=1.0,
        )

    # ── Tier 3: GPAI ─────────────────────────────────────────────────────

    if tags.is_gpai_model and tags.gpai_compute_above_systemic_threshold:
        return _verdict(
            risk_tier="gpai_systemic",
            primary=("Article 51",),
            supporting=("Article 52", "Article 55", "Article 56", "Annex XIII"),
            rationale=(
                "General-purpose AI models with cumulative training "
                "compute exceeding 10^25 FLOPs are designated as having "
                "systemic risk under Article 51 and trigger the "
                "Article 55 obligations on model evaluation, systemic-risk "
                "assessment, incident reporting, and cybersecurity.",
            ),
            confidence=1.0,
        )

    if tags.is_gpai_model:
        return _verdict(
            risk_tier="gpai",
            primary=("Article 51",),
            supporting=("Article 53", "Annex XI", "Annex XII"),
            rationale=(
                "General-purpose AI models are subject to the "
                "Article 53 obligations: technical documentation per "
                "Annex XI, downstream-provider information per "
                "Annex XII, EU copyright policy, and a sufficiently "
                "detailed summary of training data.",
            ),
            confidence=1.0,
        )

    # ── Tier 4: LIMITED (Art. 50 transparency) ───────────────────────────

    transparency_signal = (
        tags.is_chatbot_interaction
        or tags.is_synthetic_content_generation
        or tags.is_deepfake
        or (
            tags.is_biometric_data
            and not tags.is_real_time_biometric
            and not tags.used_by_law_enforcement
        )
    )
    if transparency_signal:
        return _verdict(
            risk_tier="limited",
            primary=("Article 50",),
            supporting=("Article 4",),
            rationale=(
                "Systems that interact with natural persons or generate "
                "synthetic content are subject to the Article 50 "
                "transparency obligations: users must be informed they "
                "are interacting with AI and AI-generated content must "
                "be clearly marked.",
            ),
            confidence=0.7,
        )

    # ── Tier 5: MINIMAL (default) ────────────────────────────────────────

    return _verdict(
        risk_tier="minimal",
        primary=("Article 4",),
        supporting=(),
        rationale=(
            "No specific risk tier is triggered by the question. The "
            "principal obligation is Article 4 AI literacy for staff "
            "interacting with the system.",
        ),
        confidence=0.4,
    )


# Public wrapper: applies the compound-role augmentation after the
# deterministic verdict matrix runs. Kept as a thin shim around
# :func:`compute_verdict` so the matrix itself stays a pure function
# of ``BooleanTags`` only.
_compute_verdict_inner = compute_verdict


def compute_verdict(tags: BooleanTags) -> Verdict:  # type: ignore[no-redef]  # noqa: F811
    """R47-C wrapper around the verdict matrix.

    Runs the deterministic matrix first, then augments the result
    with compound-role obligation articles when 2+ role flags fire
    AND the verdict is high-risk / GPAI / GPAI-systemic. Strictly
    additive — primary articles are never overwritten.
    """
    verdict = _compute_verdict_inner(tags)
    if not isinstance(tags, BooleanTags):
        return verdict
    return _augment_with_compound_roles(verdict, tags)


# ── Composition helper ──────────────────────────────────────────────────


def analyse(
    question: str,
    history: Sequence[Mapping[str, object]] | None = None,
) -> tuple[BooleanTags, Verdict]:
    """Run the full CLARA pipeline: LLM extract → verdict (with fallback).

    1. Try :func:`extract_tags_llm` first (returns ``None`` when the
       wrapper is disabled, the circuit is open, or the model output
       is malformed).
    2. On ``None``, fall back to :func:`extract_tags_deterministic`.
    3. Always run :func:`compute_verdict` on the resulting tags.

    The composition keeps the deterministic baseline intact even when
    the LLM is the *intended* path — bad LLM output never escapes as
    an answer.
    """
    tags = extract_tags_llm(question, history)
    if tags is None:
        tags = extract_tags_deterministic(question, history)
    verdict = compute_verdict(tags)
    return tags, verdict


# ── Test hook ────────────────────────────────────────────────────────────


def _reset_for_tests() -> None:
    """Test-only: clear the cache + breaker state."""
    with _LLM_CACHE_LOCK:
        _LLM_CACHE.clear()
        _LLM_CACHE_ORDER.clear()
    with _BREAKER.lock:
        _BREAKER.failures = 0
        _BREAKER.last_failure_ts = 0.0


__all__ = [
    "BooleanTags",
    "Verdict",
    "RiskTier",
    "extract_tags_deterministic",
    "extract_tags_llm",
    "compute_verdict",
    "analyse",
]

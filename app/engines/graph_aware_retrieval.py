"""Graph-aware retrieval helpers — opt-in companions to BM25 + 2-hop expansion.

R35 seeded the Neo4j graph with **eight node labels and six edge types**
(see ``scripts/seed_neo4j_kb.py``). The Round-31 ``graph_expand_2hop``
module exploits exactly one edge — ``CROSS_REFERENCES`` — to surface
indirect article neighbours for BM25 fusion. That leaves five edge types
(``HAS_DEFINITION``, ``HAS_RECITAL_ANCHOR``, ``HAS_OBLIGATION``,
``APPLIES_AT``, ``TRIGGERS_HIGH_RISK_UNDER``) on the table.

This module adds **three new traversal primitives** that exploit those
edges, each addressing a load-bearing question shape:

1. :func:`lookup_definition_by_term` — ``Article 3 -[:HAS_DEFINITION]-> Definition``.
   For "What is X?" / "Define Y" questions. Authoritative over the
   sentence-level BM25 fallback because the graph carries the canonical
   Art. 3 wording verbatim.
2. :func:`recitals_for_article` — ``Article -[:HAS_RECITAL_ANCHOR]-> Recital``.
   For grounding article answers with the legislator's intent. Many AI
   Act questions about an article are clearer with the article text PLUS
   a short recital quote.
3. :func:`obligations_for_role` — ``Obligation -[:APPLIES_AT]-> RiskLevel``.
   For "What must {role} do for {risk_level} systems?" scenarios. The
   graph already carries the obligation × risk-level edges; this helper
   surfaces them as a tight list rather than expanding the curated
   ``_RISK_ARTICLES`` table in ``scenario_classifier``.

## Hard guarantees (mirrors :mod:`app.engines.graph_expand_2hop`)

* **Default OFF**: ``REGENOLD_GRAPH_AWARE=1`` is required to switch on.
  When unset (or anything other than ``"1"``), :func:`is_enabled` returns
  ``False`` and every public function is a sub-microsecond passthrough
  (``None`` / ``[]``).
* **Never raises**: every Cypher call is wrapped in try/except. Any
  exception, any timeout, any malformed response collapses to an empty
  / ``None`` result. The route is route-safe under a downed graph.
* **Existence-gated outputs**: article refs flowing back to the wire are
  validated against :data:`app.data.article_existence.ARTICLE_EXISTENCE`.
  A malformed seed in Neo4j can't pollute the response.
* **Bounded wall-clock**: each call enforces a Python-side
  ``concurrent.futures`` timeout. Windows-aware (``signal.alarm`` is
  POSIX-only — see the parent ``graph_expand_2hop`` docstring). The
  budget comes from :func:`app.graph.timeouts.resolve_graph_timeout_ms`;
  R294 replaced the original hard-coded 50 ms with a measured default
  after finding it smaller than a hosted-Aura round-trip, which made
  every one of these helpers return empty in production.

## Wiring (NOT done in this module)

The wiring step is intentionally out of scope. The follow-up PR is
expected to:

* call :func:`lookup_definition_by_term` from
  :func:`app.routes.regenold._try_extractive_answer` BEFORE the existing
  sentence-level BM25 path for DEFINITION questions;
* call :func:`obligations_for_role` from
  :func:`app.engines.scenario_classifier` to enumerate role × risk-level
  obligation lists from the graph (with the curated table as the
  fallback floor);
* call :func:`recitals_for_article` from a new
  ``_surface_recital_anchors`` helper in :mod:`app.routes.regenold` to
  attach recital citations alongside article citations.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.data.article_existence import ARTICLE_EXISTENCE

if TYPE_CHECKING:  # pragma: no cover — typing only
    from concurrent.futures import ThreadPoolExecutor

    from app.graph.client import GraphClient

logger = logging.getLogger(__name__)


# ─── Env gate ──────────────────────────────────────────────────────────────

_ENV_VAR = "REGENOLD_GRAPH_AWARE"


def _env_enabled() -> bool:
    """Return True iff the env-var is exactly ``"1"``.

    Strict equality so accidental ``"0"`` / ``""`` / ``"false"`` never
    flip the switch.
    """
    return os.environ.get(_ENV_VAR, "") == "1"


# ─── Public dataclasses ────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecitalGrounding:
    """A recital anchored to an article.

    Surfaced by :func:`recitals_for_article`. The route attaches these
    as supporting citations alongside the article ref. ``recital_text``
    carries the full prose so the caller can decide how much to quote;
    the route layer is responsible for length-capping.
    """

    article_ref: str          # "Article 6" (user-facing form)
    recital_number: int       # 47
    recital_text: str         # full recital prose


@dataclass(frozen=True)
class RoleObligation:
    """An obligation applicable to a role at a given risk level.

    Surfaced by :func:`obligations_for_role`. ``article_ref`` is the
    user-facing form (``"Article 9"`` / ``"Article 9.2"``) so it lands
    directly in the route's reference list. ``mandatory`` mirrors the
    ``Obligation.mandatory`` property — currently always ``True`` in
    the seeded graph but kept on the dataclass so a future "soft"
    obligation tier doesn't need a schema bump.
    """

    obligation_id: str
    article_ref: str          # e.g. "Article 9" / "Article 9.2"
    text: str
    mandatory: bool


# ─── Lazy executor (shared across the three helpers) ───────────────────────
#
# ``concurrent.futures`` pulls ``threading`` + ``queue`` (~40 ms cold
# import) so we defer it until the first ``_with_timeout`` call. Keeps
# module import sub-1ms when the env-gate is off (the default path).
_EXECUTOR: Any = None


def _get_executor() -> ThreadPoolExecutor:
    """Lazy single-pool accessor — daemon threads, capped at 2 workers."""
    global _EXECUTOR
    if _EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor

        _EXECUTOR = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="graphaware",
        )
    return _EXECUTOR


# ─── Reference normalisation helpers ───────────────────────────────────────
#
# The graph stores ``number`` as a bare string (``"6"`` / ``"III"``).
# Callers and the wire deal in "Article 6" / "Annex III" form. These
# helpers bridge the two without raising.
#
# TODO(R47): migrate to app.integrations.regenold.refs (centralised converter).

_USER_ARTICLE_RE = re.compile(r"^Article\s+(\d+(?:\.[\w.]+)?)$")
_INTERNAL_ARTICLE_RE = re.compile(r"^Art\.\s+(\d+(?:\.[\w.]+)?)$")
_USER_ANNEX_RE = re.compile(r"^Annex\s+([IVXLCDM]+(?:\.[\w.]+)?)$", re.IGNORECASE)
_INTERNAL_ANNEX_RE = re.compile(r"^Annex\s+([IVXLCDM]+(?:\.[\w.]+)?)$", re.IGNORECASE)


def _article_ref_to_num(ref: str) -> str | None:
    """Convert ``"Article 6"`` / ``"Art. 6"`` / ``"Annex III"`` → ``"6"`` / ``"III"``.

    Sub-points are stripped (``"Article 13.2"`` → ``"13"``) so the
    Cypher match resolves to the parent Article node. Returns ``None``
    for unparseable refs.
    """
    if not ref:
        return None
    cand = ref.strip()
    for pat in (_USER_ARTICLE_RE, _INTERNAL_ARTICLE_RE):
        m = pat.match(cand)
        if m:
            return m.group(1).split(".", 1)[0]
    for pat in (_USER_ANNEX_RE, _INTERNAL_ANNEX_RE):
        m = pat.match(cand)
        if m:
            return m.group(1).split(".", 1)[0].upper()
    return None


def _internal_to_user(internal_ref: str) -> str:
    """Convert ``"Art. 6"`` → ``"Article 6"`` (annexes pass through unchanged).

    The seed stores articles as ``"Art. N"`` internally; the wire wants
    ``"Article N"`` per the Regenold rubric. Annex form is identical in
    both vocabularies so we don't touch it.
    """
    if internal_ref.startswith("Art. "):
        return "Article " + internal_ref[len("Art. "):]
    return internal_ref


def _is_real_article(internal_ref: str) -> bool:
    """Existence-gate against the canonical 113-article + 13-annex catalog."""
    return internal_ref in ARTICLE_EXISTENCE


def _num_to_internal(num: str) -> str | None:
    """Convert a Neo4j ``number`` string back to internal ref form.

    Arabic numerals → ``Art. N``. Roman numerals → ``Annex X``. Anything
    else → ``None`` (defensive — a malformed row can't pollute the
    response).
    """
    if not num:
        return None
    token = str(num).strip()
    if not token:
        return None
    if token.isdigit():
        return f"Art. {token}"
    if re.fullmatch(r"[IVXLCDM]+", token.upper()):
        return f"Annex {token.upper()}"
    return None


# ─── Slug helper for definitions ───────────────────────────────────────────


_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug_term(term: str) -> str:
    """Lower-case slugify a definition term to match the seeded ID convention.

    Mirrors :func:`scripts.seed_neo4j_kb._slug_term` so a question term
    typed as ``"AI system"`` lands on the same slug (``"ai_system"``)
    that the seeder used to mint the Definition node ID.
    """
    s = term.lower().strip()
    s = _SLUG_NON_ALNUM.sub("_", s)
    s = s.strip("_")
    return s or "anon"


# ─── Cypher templates (all parameter-bound) ────────────────────────────────

# 1) Definition lookup — substring match against ``Definition.id`` (which
#    is shaped ``"def_<term_slug>"``). Two-tier match: exact-equal first,
#    substring fallback. Ordered by ID length so the most specific match
#    wins (e.g. ``"def_ai_system"`` beats ``"def_ai_system_provider"``
#    for the query "ai system").
_CYPHER_DEFINITION = """
MATCH (a:Article {number: "3"})-[:HAS_DEFINITION]->(d:Definition)
WHERE toLower(d.id) = "def_" + $term_slug
   OR toLower(d.id) CONTAINS $term_slug
RETURN d.id AS id, d.term AS term, d.text AS text,
       CASE WHEN toLower(d.id) = "def_" + $term_slug THEN 0 ELSE 1 END AS rank,
       size(d.id) AS id_len
ORDER BY rank ASC, id_len ASC
LIMIT 1
""".strip()


# 2) Recital grounding for an article — ordered by recital number.
_CYPHER_RECITALS = """
MATCH (a:Article {number: $num})-[:HAS_RECITAL_ANCHOR]->(r:Recital)
RETURN r.number AS num, r.text AS text
ORDER BY toInteger(r.number) ASC
LIMIT $cap
""".strip()


# 3) Role-scoped obligations — joins on the ``APPLIES_AT`` edge. The R35
#    seed doesn't carry a direct ``OperatorRole -[:HAS_OBLIGATION_AT_RISK]->``
#    edge; we derive the role × risk relationship by pulling every
#    obligation that applies at the given risk level. The route layer
#    further filters on per-role applicability when needed.
_CYPHER_OBLIGATIONS = """
MATCH (o:Obligation)-[:APPLIES_AT]->(rl:RiskLevel {id: $risk_id})
RETURN o.id AS id, o.article_ref AS art,
       o.paragraph_ref AS para, o.text AS text,
       coalesce(o.mandatory, true) AS mandatory
ORDER BY toInteger(o.article_ref) ASC
LIMIT $cap
""".strip()


# ─── Risk-level + role normalisation tables ────────────────────────────────
#
# These mirror the canonical IDs used by the seeder. Mapping is forgiving
# (case-insensitive, hyphens/underscores treated equivalently) so the
# route can pass whatever form ``scenario_classifier`` produces.

_RISK_LEVEL_ALIASES: dict[str, str] = {
    "prohibited": "risk_prohibited",
    "high-risk": "risk_high",
    "high_risk": "risk_high",
    "high": "risk_high",
    "limited": "risk_limited",
    "limited-risk": "risk_limited",
    "transparency": "risk_limited",
    "minimal": "risk_minimal",
    "minimal-risk": "risk_minimal",
    "low": "risk_minimal",
    "none": "risk_minimal",
}

_CANONICAL_ROLES: frozenset[str] = frozenset({
    "provider",
    "deployer",
    "importer",
    "distributor",
    "authorized_representative",
    "authorised_representative",
})


def _normalise_risk_level(risk_level: str) -> str | None:
    """Map a free-form risk level to a seeded ``RiskLevel.id``.

    Returns ``None`` for unrecognised values so the caller can short-
    circuit without firing Cypher.
    """
    if not risk_level:
        return None
    key = risk_level.strip().lower().replace(" ", "-")
    if key in _RISK_LEVEL_ALIASES:
        return _RISK_LEVEL_ALIASES[key]
    # Try underscore variant too (`"high_risk"` <-> `"high-risk"`).
    key_us = key.replace("-", "_")
    return _RISK_LEVEL_ALIASES.get(key_us)


def _normalise_role(role: str) -> str | None:
    """Map a free-form role label to the canonical seeded role token.

    Returns ``None`` for unrecognised roles — the route should fall
    back to its curated table in that case.
    """
    if not role:
        return None
    key = role.strip().lower().replace("-", "_").replace(" ", "_")
    if key in _CANONICAL_ROLES:
        return key
    # Common alias: British vs American spelling.
    if key == "authorised_representative":
        return "authorized_representative"
    return None


# ─── Client resolution ─────────────────────────────────────────────────────


def _resolve_client() -> GraphClient | None:
    """Lazy-load + return the graph client iff it's connected.

    Mirrors :func:`app.engines.graph_expand_2hop._resolve_client`. The
    deferred import + try/except guarantees:

    * module import stays sub-1ms when the env-gate is off (no heavy
      ``app.graph.client`` load until a request actually fires);
    * an environment without the optional ``neo4j`` driver still loads
      this module cleanly.
    """
    try:
        from app.graph.client import get_graph_client
    except Exception:  # noqa: BLE001
        logger.debug("graph_aware client import failed", exc_info=True)
        return None
    try:
        client = get_graph_client()
    except Exception:  # noqa: BLE001
        logger.debug("graph_aware get_graph_client failed", exc_info=True)
        return None
    if not getattr(client, "enabled", False):
        return None
    return client


def _with_timeout(
    fn: Any,
    *,
    timeout_ms: int | None,
    label: str,
) -> list[dict] | None:
    """Run ``fn`` on the shared executor with a wall-clock cap.

    Returns the function's result on success, or ``None`` on timeout /
    any exception. Callers translate ``None`` into their empty / ``None``
    return value. Centralising the futures+timeout dance keeps each
    helper readable and ensures consistent error handling.

    ``timeout_ms=None`` resolves the budget from
    :func:`app.graph.timeouts.resolve_graph_timeout_ms`. This is the
    single resolution point for all three helpers below — R294 measured
    the old hard-coded 50 ms as smaller than a hosted-Aura round-trip
    (cold 703 ms, warm mean 64 ms), so every call silently returned
    empty and the graph-aware layer contributed nothing in production.
    """
    from concurrent.futures import TimeoutError as _FutTimeout

    from app.graph.timeouts import (
        graph_circuit_open,
        record_graph_failure,
        record_graph_success,
        resolve_graph_timeout_ms,
    )

    # R294 — shared breaker with graph_expand_2hop: a sustained outage
    # must not spend the budget on every call. Never opens on a healthy graph.
    if graph_circuit_open():
        logger.debug("graph_aware %s skipped — circuit open", label)
        return None

    budget_ms = resolve_graph_timeout_ms(timeout_ms)

    try:
        fut = _get_executor().submit(fn)
        result = fut.result(timeout=max(budget_ms, 1) / 1000.0)
        record_graph_success()
        return result
    except _FutTimeout:
        record_graph_failure()
        logger.info(
            "graph_aware cypher timeout label=%s budget=%dms",
            label, budget_ms,
        )
        return None
    except Exception:  # noqa: BLE001
        record_graph_failure()
        logger.debug("graph_aware %s submit/result failed", label, exc_info=True)
        return None


# ─── Public API ────────────────────────────────────────────────────────────


def is_enabled() -> bool:
    """True iff the env-var is set AND the graph client is connected.

    Both conditions must hold. The env-var alone isn't enough — if
    Neo4j is down or the driver isn't installed, the module stays in
    passthrough mode.
    """
    if not _env_enabled():
        return False
    return _resolve_client() is not None


# ── 1) Definition lookup ──────────────────────────────────────────────────


def lookup_definition_by_term(
    term: str,
    *,
    timeout_ms: int | None = None,
) -> str | None:
    """Return the Art. 3 definition text for a term, or ``None``.

    Strategy:

    1. Fast path: env-gate off → ``None`` in ~1µs.
    2. Slug the term (``"AI system"`` → ``"ai_system"``) using the same
       convention the seeder used.
    3. Cypher: exact match on ``Definition.id == "def_<slug>"`` first,
       then substring fallback ordered by ID length so the most
       specific match wins. Limit 1.
    4. On any failure / no match: ``None``.

    Args:
        term: The term being defined. Free-form — punctuation and case
            are normalised by the slug helper.
        timeout_ms: Wall-clock budget for the Cypher call. ``None``
            (the default) resolves via
            :func:`app.graph.timeouts.resolve_graph_timeout_ms`.

    Returns:
        The verbatim definition text, or ``None`` on no-match / failure
        / disabled.
    """
    if not _env_enabled():
        return None
    if not term or not term.strip():
        return None

    client = _resolve_client()
    if client is None:
        return None

    slug = _slug_term(term)
    if not slug:
        return None

    def _call() -> list[dict]:
        try:
            return client.execute_read(
                _CYPHER_DEFINITION,
                {"term_slug": slug},
            )
        except Exception:  # noqa: BLE001
            logger.debug("graph_aware definition execute_read raised", exc_info=True)
            return []

    rows = _with_timeout(_call, timeout_ms=timeout_ms, label="definition")
    if not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    text = row.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return text


# ── 2) Recital grounding ──────────────────────────────────────────────────


def recitals_for_article(
    article_ref: str,
    *,
    max_recitals: int = 3,
    timeout_ms: int | None = None,
) -> list[RecitalGrounding]:
    """Return recitals anchored to an article, up to ``max_recitals``.

    Walks ``Article -[:HAS_RECITAL_ANCHOR]-> Recital``. The R35 seeder
    builds these edges by regex-extracting "Recital N" mentions out of
    obligation summaries; not every article has an anchor.

    Args:
        article_ref: User-facing or internal form. Sub-points stripped.
        max_recitals: Cap on returned recitals. Defaults to 3 — the
            route is space-constrained and the legislator typically
            anchors only a small handful of recitals per article.
        timeout_ms: Wall-clock budget. ``None`` (the default)
            resolves via
            :func:`app.graph.timeouts.resolve_graph_timeout_ms`.

    Returns:
        List of :class:`RecitalGrounding`. Empty when:

        * env-gate off,
        * Neo4j disabled / unreachable,
        * the article has no recital anchors,
        * the ref is malformed,
        * any failure during Cypher execution.
    """
    if not _env_enabled():
        return []
    if not article_ref or max_recitals <= 0:
        return []

    num = _article_ref_to_num(article_ref)
    if num is None:
        return []
    # Existence-gate the seed too — a question that mentions
    # ``"Article 200"`` shouldn't fire a Cypher we know will be empty.
    internal = _num_to_internal(num)
    if internal is None or not _is_real_article(internal):
        return []

    client = _resolve_client()
    if client is None:
        return []

    user_ref = _internal_to_user(internal)
    cap = max(max_recitals, 1)

    def _call() -> list[dict]:
        try:
            return client.execute_read(
                _CYPHER_RECITALS,
                {"num": num, "cap": cap},
            )
        except Exception:  # noqa: BLE001
            logger.debug("graph_aware recitals execute_read raised", exc_info=True)
            return []

    rows = _with_timeout(_call, timeout_ms=timeout_ms, label="recitals")
    if rows is None:
        return []

    out: list[RecitalGrounding] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_num = row.get("num")
        text = row.get("text")
        if raw_num is None or not isinstance(text, str) or not text.strip():
            continue
        try:
            rn = int(str(raw_num).strip())
        except (TypeError, ValueError):
            continue
        # Recital numbers are 1..180 in the AI Act. Defensive bound.
        if rn < 1 or rn > 300:
            continue
        out.append(
            RecitalGrounding(
                article_ref=user_ref,
                recital_number=rn,
                recital_text=text,
            )
        )
        if len(out) >= max_recitals:
            break
    return out


# ── 3) Role-scoped obligation enumeration ─────────────────────────────────


def obligations_for_role(
    role: str,
    risk_level: str,
    *,
    max_obligations: int = 10,
    timeout_ms: int | None = None,
) -> list[RoleObligation]:
    """Return obligations applicable to ``role`` at ``risk_level``.

    Walks ``Obligation -[:APPLIES_AT]-> RiskLevel``. The R35 seed
    encodes role-applicability implicitly: the canonical role × risk
    obligation surface is the union of obligation nodes that apply at
    that risk level, plus the route layer's own role-specific filtering
    (provider vs deployer vs importer is enforced upstream by
    ``role_obligations``). This helper surfaces the **risk-level slice**;
    the caller refines from there.

    Args:
        role: Operator role label. Accepts any of
            ``provider`` / ``deployer`` / ``importer`` / ``distributor`` /
            ``authorized_representative``. Unknown roles → ``[]``.
        risk_level: One of ``prohibited`` / ``high-risk`` / ``limited`` /
            ``minimal`` (case-insensitive, hyphens and underscores
            interchangeable). Unknown → ``[]``.
        max_obligations: Cap on returned list. Defaults to 10 — matches
            the davidath scenario-gold average citation count.
        timeout_ms: Wall-clock budget. ``None`` (the default)
            resolves via
            :func:`app.graph.timeouts.resolve_graph_timeout_ms`.

    Returns:
        List of :class:`RoleObligation`. Article refs are wire-form
        (``"Article 9"``) with paragraph appended when available
        (``"Article 9.2"``). Empty when disabled / no match / failure.
    """
    if not _env_enabled():
        return []
    if max_obligations <= 0:
        return []

    risk_id = _normalise_risk_level(risk_level)
    if risk_id is None:
        return []
    role_norm = _normalise_role(role)
    if role_norm is None:
        return []

    client = _resolve_client()
    if client is None:
        return []

    cap = max(max_obligations, 1)

    def _call() -> list[dict]:
        try:
            return client.execute_read(
                _CYPHER_OBLIGATIONS,
                {"risk_id": risk_id, "cap": cap},
            )
        except Exception:  # noqa: BLE001
            logger.debug("graph_aware obligations execute_read raised", exc_info=True)
            return []

    rows = _with_timeout(_call, timeout_ms=timeout_ms, label="obligations")
    if rows is None:
        return []

    out: list[RoleObligation] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        obl_id = row.get("id")
        art_num = row.get("art")
        text = row.get("text")
        if not isinstance(obl_id, str) or not obl_id:
            continue
        if obl_id in seen_ids:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        # Existence-gate the article ref before surfacing.
        internal = _num_to_internal(str(art_num) if art_num is not None else "")
        if internal is None or not _is_real_article(internal):
            continue
        user_art = _internal_to_user(internal)
        # Append paragraph_ref if present (``"Article 9.2"`` style).
        para = row.get("para")
        if isinstance(para, str) and para.strip():
            user_art = f"{user_art}.{para.strip()}"
        mandatory_raw = row.get("mandatory", True)
        mandatory = bool(mandatory_raw) if mandatory_raw is not None else True
        seen_ids.add(obl_id)
        out.append(
            RoleObligation(
                obligation_id=obl_id,
                article_ref=user_art,
                text=text,
                mandatory=mandatory,
            )
        )
        if len(out) >= max_obligations:
            break
    return out


__all__ = [
    "RecitalGrounding",
    "RoleObligation",
    "is_enabled",
    "lookup_definition_by_term",
    "recitals_for_article",
    "obligations_for_role",
]

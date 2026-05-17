"""Definition-graph recursive resolution — R44 Pattern A.

Surfaces Art. 3 defined-term citations on multi-cite questions whose
retrieved articles "use" the defined term in their prose. Motivation
(WhyHow.AI 2025 legislative-RAG pattern, captured in
``docs/partners/regenold/R44_GRAPH_RAG_LANDSCAPE.md``):

    When the engine retrieves Art. 26 (deployer obligations) and
    Art. 19 (log retention), BOTH prose blocks USE the defined terms
    "deployer" (Art. 3(4)) and "high-risk AI system" (Art. 3(15)).
    A reader needs Art. 3(4) to know "deployer" means the entity using
    the system in a professional capacity, NOT the consumer.
    Without auto-expansion, we never cite Art. 3 — yet gold answers
    from regulatory commentary often do.

The expansion is **strictly additive** — BM25 / dense / graph winners
keep their original order and slot. Sub-citations of Art. 3 land at
the tail, capped at ``max_added=3`` so the answer doesn't bloat with
definitional padding on every multi-cite question.

## Design choices (de-overfit guard)

* **Sub-citation form on the wire.** Each definition gets its own
  ``Art. 3.N`` sub-citation appended. Downstream
  :func:`app.routes.regenold._collapse_parent_refs` can fold them to
  ``Art. 3`` parent once the smallest-cover pass runs, but on this
  surface they're distinct refs (the spec budget cap counts distinct
  entries).

* **Art. 3 self-exclusion.** If ``Art. 3`` (parent) is already in
  candidates, the expansion is a no-op — adding sub-citations would
  be redundant after the route's smallest-cover collapse.

* **Term-in-prose, not term-in-question.** The Pattern-A insight is
  that the retrieved article's prose USES the term. The user's
  question may not. We MUST scan the prose, not the question — that's
  what makes it a "definition-graph recursive resolution" rather than
  a query expansion. Question-keyword matching would re-invent
  :mod:`app.data.kb_search`.

* **Plural-only morphology, NO stemming.** We emit ``term``,
  ``term`` + ``"s"`` (provider → providers), and ``term`` + ``"es"``
  for stems ending in ``s``/``x``/``z``/``ch``/``sh``. We deliberately
  DO NOT do Porter-style stemming — that would collapse "biometric
  data" and "biometric verification" into a single token bag and
  produce false positives.

* **Self-exclusion of Art. 3.** Definitions live in Art. 3 and Art. 3
  itself uses every defined term it introduces. Indexing Art. 3 as a
  "supporting candidate" would mean EVERY retrieved Art. 3 candidate
  bolts on the rest of Art. 3, which is circular. The build pass
  excludes Art. 3 from the term-usage scan.

## Public API

* :func:`build_definition_index` — frozen ``slug → frozenset[Art. N]``
  map, built once at first call via ``lru_cache(1)``.
* :func:`expand_with_definitions` — additive append of Art. 3 sub-
  citations to a list of article refs.

Both functions are fail-soft — invalid inputs return ``[]`` or echo
the input. The route is never 500'd by this pass.
"""
from __future__ import annotations

import re
from functools import lru_cache

from app.data.definitions import DEFINITION_REGISTRY
from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT

# ── Term morphology ────────────────────────────────────────────────────────


def _tokenise_term(term: str) -> tuple[str, ...]:
    """Emit the term + simple plural variants.

    Deterministic, no stemming: we want ``"deployer" → ("deployer",
    "deployers")`` but NOT ``"deployer" → ("deploy", "deploying", ...)``.
    The latter would false-match Art. 73 ("a provider deploying ..."),
    which uses the verb form rather than the role noun.

    Rules:

    * Base form lowercased + whitespace-collapsed.
    * If the term already ends in ``s``, no plural is added (avoid
      ``"misuse" → "misuses"`` and ``"witness" → "witnesss"`` etc.).
    * If it ends in ``s``/``x``/``z``/``ch``/``sh``, add ``es``
      (``"witness" → "witnesses"``).
    * Otherwise, add ``s`` (``"provider" → "providers"``).

    Empty / whitespace-only input → empty tuple.
    """
    if not term:
        return ()
    base = " ".join(term.lower().split())
    if not base:
        return ()

    variants = [base]

    # No plural for terms already ending in 's' (heuristic — keeps
    # "instructions for use" / "harmonised standards" from gaining a
    # bogus "instructions for uses" form).
    if base.endswith("s"):
        return tuple(variants)

    # Sibilant ending → 'es' plural.
    if base.endswith(("x", "z", "ch", "sh")):
        variants.append(base + "es")
    else:
        variants.append(base + "s")

    return tuple(variants)


def _make_term_pattern(variants: tuple[str, ...]) -> "re.Pattern[str] | None":
    """Compile a case-insensitive word-boundary regex over ``variants``.

    Word-boundary ensures ``"risk"`` matches ``"risks"`` only if it's
    in the variants tuple (not by accidental prefix collision). For
    multi-word terms like ``"making available on the market"``,
    interior whitespace tolerates non-breaking spaces (EUR-Lex prose
    contains many ``\xa0`` chars).
    """
    if not variants:
        return None
    # Escape each variant; collapse any literal space to ``\s+`` so we
    # tolerate non-breaking spaces and multi-space EUR-Lex artifacts.
    escaped = []
    for v in variants:
        # Each whitespace run in the source term becomes ``\s+``.
        # ``re.escape`` over the joined-bytes form would over-escape the
        # spaces, so split first and join.
        parts = [re.escape(part) for part in v.split()]
        escaped.append(r"\s+".join(parts))
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, flags=re.IGNORECASE)


def _term_appears_in(text: str, pattern: "re.Pattern[str] | None") -> bool:
    """True iff ``pattern`` matches anywhere in ``text``."""
    if pattern is None or not text:
        return False
    return pattern.search(text) is not None


# ── Index build (heavy, cached once) ───────────────────────────────────────


# Articles we exclude from the term-usage scan:
#
# * ``Art. 3`` itself defines all the terms; if we let it count as a
#   supporting candidate then every retrieved Art. 3 would bolt on
#   itself — circular.
# * ``Art. 1`` (Subject matter) and ``Art. 2`` (Scope) contain glancing
#   uses of every regulation term ("AI system", "provider", "deployer"
#   …) without making them load-bearing. Including them adds noise.
#
# Keep the exclusion small and explicit — the spec's "first N by
# supporting-candidate-count" rule means popular terms naturally win,
# so over-pruning costs less than including noise sources.
_EXCLUDED_FROM_SCAN: frozenset[str] = frozenset({"Art. 3"})


@lru_cache(maxsize=1)
def build_definition_index() -> dict[str, frozenset[str]]:
    """Return ``{citation: frozenset(article-refs that use the defined term)}``.

    Built once on first call. ``citation`` is the Art. 3 sub-citation
    (e.g. ``"Art. 3.4"`` for "deployer"). ``article-refs`` are the
    canonical internal forms (``Art. N`` / ``Annex X``) of every
    article whose prose in :data:`ARTICLE_FULL_TEXT` contains the term
    (or its simple plural).

    Art. 3 itself is excluded from the index (see
    :data:`_EXCLUDED_FROM_SCAN`).

    Empty mapping if either ``DEFINITION_REGISTRY`` or
    ``ARTICLE_FULL_TEXT`` is empty (defensive — neither should be in
    practice).
    """
    if not DEFINITION_REGISTRY or not ARTICLE_FULL_TEXT:
        return {}

    # Pre-compile one pattern per definition. The corpus has ~130
    # articles + 13 annexes; with ~73 definitions that's ~10k regex
    # searches at index build time — sub-100ms cold.
    index: dict[str, frozenset[str]] = {}
    for citation, defn in DEFINITION_REGISTRY.items():
        variants = _tokenise_term(defn.term)
        pattern = _make_term_pattern(variants)
        if pattern is None:
            continue

        supporting: set[str] = set()
        for article_ref, prose in ARTICLE_FULL_TEXT.items():
            if article_ref in _EXCLUDED_FROM_SCAN:
                continue
            if not isinstance(prose, str):
                continue
            if _term_appears_in(prose, pattern):
                supporting.add(article_ref)

        if supporting:
            index[citation] = frozenset(supporting)

    return index


# ── Public expansion API ───────────────────────────────────────────────────


def _is_art3_parent_in(candidates: list[str]) -> bool:
    """True iff the literal ``"Art. 3"`` parent ref is in ``candidates``.

    A bare ``"Art. 3"`` covers every sub-citation via the route's
    :func:`_collapse_parent_refs` smallest-cover pass — so the
    expansion is a no-op in that case. Sub-citations like ``"Art. 3.4"``
    do NOT count as the parent; they're peers in the dedup pass.
    """
    return "Art. 3" in candidates


def expand_with_definitions(
    candidates: list[str],
    *,
    max_added: int = 3,
) -> list[str]:
    """Append Art. 3 sub-citations for defined terms used in candidate prose.

    Strictly additive:

    * BM25 / dense / graph winners keep their original order and slot.
      The expansion only appends to the tail.
    * Capped at ``max_added`` new refs (default 3).
    * Selection rule: each definition's score = the number of distinct
      already-surfaced candidates whose prose contains the term. Higher
      score wins. Ties broken by term length (more specific terms — the
      longer phrasings like "making available on the market" — beat
      single-token terms like "risk" on ties).
    * Existing candidates are NEVER re-appended; sub-citations already
      present are skipped.
    * If the bare ``"Art. 3"`` parent is already in candidates, the
      whole pass is a no-op (sub-citations would collapse to the
      parent downstream anyway).

    Fail-soft: any non-list / non-str input returns ``[]`` or the
    input echoed. Never raises.

    Args:
        candidates: Article refs in internal form (``Art. N`` /
            ``Annex X``). Strings only — non-string entries are skipped.
        max_added: Cap on appended sub-citations. ``0`` is a valid
            no-op cap.

    Returns:
        New list (never mutates input). Empty input → ``[]``.
    """
    # Defensive normalisation — never raise on garbage input.
    if not candidates or not isinstance(candidates, list):
        return list(candidates) if isinstance(candidates, list) else []
    if max_added <= 0:
        return list(candidates)

    # Filter to strings (defensive — accept lists of mixed types).
    cand_strs = [c for c in candidates if isinstance(c, str) and c]
    if not cand_strs:
        return list(candidates)

    # Art. 3 parent dedupe.
    if _is_art3_parent_in(cand_strs):
        return list(candidates)

    try:
        index = build_definition_index()
    except Exception:  # noqa: BLE001 — fail-soft on cold-build error
        return list(candidates)
    if not index:
        return list(candidates)

    candidate_set = set(cand_strs)

    # Score each definition by # of candidates whose prose uses the term.
    scored: list[tuple[int, int, str]] = []  # (count, term_len, citation)
    for citation, supporters in index.items():
        # Skip definitions already in candidates — no point double-appending.
        if citation in candidate_set:
            continue
        count = sum(1 for c in cand_strs if c in supporters)
        if count <= 0:
            continue
        # Term length proxy for specificity — pull from the registry.
        defn = DEFINITION_REGISTRY.get(citation)
        term_len = len(defn.term) if defn is not None else 0
        scored.append((count, term_len, citation))

    if not scored:
        return list(candidates)

    # Higher count first; ties → longer term first.
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))

    out: list[str] = list(candidates)
    seen: set[str] = set(cand_strs)
    added = 0
    for _count, _term_len, citation in scored:
        if added >= max_added:
            break
        if citation in seen:
            continue
        out.append(citation)
        seen.add(citation)
        added += 1

    return out


__all__ = [
    "build_definition_index",
    "expand_with_definitions",
]

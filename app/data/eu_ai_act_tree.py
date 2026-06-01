"""Layer A — Layout-aware, Document-as-a-Tree parsing of the EU AI Act.

Implements Layer A of the
``EU_AI_Act_High_Precision_RAG_Architecture.pdf`` whitepaper:

    "Legal texts cannot be partitioned using standard arbitrary token-count
    sliding windows ... ingestion must be strictly deterministic and
    structurally native. Document-as-a-Tree (Parent-Child Representation):
    the text index must be organized as a hierarchical data tree rather
    than a flat database table."

This module re-parses the existing flat EUR-Lex prose in
``app.data.eu_ai_act_corpus.ARTICLE_FULL_TEXT`` into a typed tree of
:class:`TreeNode` instances, exposing child-level granularity (paragraph,
sub-point, annex item) AND a parent-context resolver that returns the
encompassing article body.

Public API:

* :func:`build_tree`            — lazy-cached full tree builder.
* :func:`iter_children`         — direct children of a node.
* :func:`parent_of`             — parent back-pointer.
* :func:`get_parent_context`    — full parent text (Art. / Annex body).
* :func:`find_nodes_by_keyword` — substring/whole-word scan over child nodes.

Plus two derivation tables:

* :data:`RISK_TIER_BY_ARTICLE`  — Art./Annex → 7-class risk tier.
* :data:`TIMELINE_BY_ARTICLE`   — Art./Annex → ISO applicability date
  (per Art. 113 rules).
  ``app.data.kb.KB_ENTRIES["Art. 113"]``).

Design notes:

* The module top-level cost is constants only — the (~600 node) tree is
  built on the first call to :func:`build_tree` via ``lru_cache(1)``.
* The tree uses **stable, deterministic** node ids derived from the
  article+paragraph+subpoint coordinates — they are safe to use as
  database keys, vector-store row ids, or audit-chain references.
* ``article_number`` on :class:`TreeNode` follows the prompt-spec
  publication form (e.g. ``"Article 6"``, ``"Annex III"``) — distinct
  from the internal ``ARTICLE_FULL_TEXT`` keys (``"Art. 6"``).
* Pure stdlib (``re``, ``dataclasses``, ``typing``, ``functools``,
  ``itertools``). No new pip deps; no I/O at import time.
"""
from __future__ import annotations

import functools
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from app.data.eu_ai_act_corpus import (
    ART_3_DEFINITIONS,
    ARTICLE_CHAPTER,
    ARTICLE_FULL_TEXT,
    RECITALS,
)

# ──────────────────────────────────────────────────────────────────────────
# Typed risk-tier surface — must match the architecture-PDF whitepaper.
# ──────────────────────────────────────────────────────────────────────────

RiskTier = Literal[
    "prohibited",
    "high_risk",
    "limited",
    "minimal",
    "gpai",
    "gpai_systemic",
    "n/a",
]


NodeKind = Literal[
    "chapter",
    "article",
    "paragraph",
    "subpoint",
    "annex",
    "annex_point",
    "recital",
    "definition",
]


@dataclass(frozen=True)
class TreeNode:
    """A single granularity-anchored node in the AI Act document tree.

    Attributes match the architecture-PDF "Deterministic Legal Metadata
    Schema" verbatim — see the module docstring.
    """

    node_id: str
    kind: NodeKind
    article_number: str | None
    paragraph_number: int | None
    subpoint_letter: str | None
    text: str
    parent_id: str | None
    risk_tier: RiskTier
    timeline_effective_date: str
    chapter_id: str | None
    # ``children_ids`` is mutable per build, then frozen via dataclass on
    # publication. We expose it as a tuple so the surface stays immutable.
    children_ids: tuple[str, ...] = field(default_factory=tuple)


# ──────────────────────────────────────────────────────────────────────────
# Risk-tier derivation — keyed by canonical "Article N" / "Annex X" form.
# ──────────────────────────────────────────────────────────────────────────


def _roman(n: int) -> str:
    """Lossless 1-13 → Roman conversion (enough for 13 annexes)."""
    table = [
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out = []
    rem = n
    for val, sym in table:
        while rem >= val:
            out.append(sym)
            rem -= val
    return "".join(out)


def _build_risk_tier_table() -> dict[str, RiskTier]:
    """Compute the article+annex → risk-tier mapping.

    Rules (per the architecture PDF + AI Act regulation surface):

    * Art. 5             → ``"prohibited"``
    * Art. 6, 7          → ``"high_risk"`` (classification rules)
    * Art. 8-49          → ``"high_risk"`` (Chapter III obligations)
    * Art. 50            → ``"limited"``    (transparency)
    * Art. 51            → ``"gpai"``       (classification threshold)
    * Art. 52            → ``"gpai_systemic"`` (designation procedure)
    * Art. 53            → ``"gpai"``       (standard GPAI obligations)
    * Art. 54            → ``"gpai"``       (authorised reps)
    * Art. 55            → ``"gpai_systemic"`` (systemic-risk obligations)
    * Annex I, III, IV-VII → ``"high_risk"`` (HRAIS-anchored)
    * Annex XI-XIII      → ``"gpai"``       (GPAI-anchored)
    * Everything else    → ``"n/a"``
    """
    table: dict[str, RiskTier] = {}

    for n in range(1, 114):
        long_key = f"Article {n}"
        if n == 5:
            table[long_key] = "prohibited"
        elif 6 <= n <= 49:
            # Chapter III — high-risk classification + requirements +
            # provider/deployer/importer/distributor obligations.
            table[long_key] = "high_risk"
        elif n == 50:
            table[long_key] = "limited"
        elif n in (52, 55):
            table[long_key] = "gpai_systemic"
        elif n in (51, 53, 54):
            table[long_key] = "gpai"
        else:
            table[long_key] = "n/a"

    # Annexes — HRAIS-anchored vs GPAI-anchored.
    for n in range(1, 14):
        roman = _roman(n)
        long_key = f"Annex {roman}"
        if n in (1, 3, 4, 5, 6, 7):
            # Annex I (HRAIS scoping list), III (HRAIS use-cases),
            # IV (tech doc), V (declaration), VI/VII (conformity).
            table[long_key] = "high_risk"
        elif n in (11, 12, 13):
            # Annex XI (GPAI tech doc), XII (downstream info), XIII
            # (systemic-risk criteria).
            table[long_key] = "gpai"
        else:
            # Annex II (criminal-offence list), VIII (registration info),
            # IX (registration template), X (Union acts).
            table[long_key] = "n/a"

    return table


RISK_TIER_BY_ARTICLE: dict[str, RiskTier] = _build_risk_tier_table()


# ──────────────────────────────────────────────────────────────────────────
# Timeline derivation — Art. 113 phased applicability.
# Source of truth: app/data/kb.py::KB_ENTRIES["Art. 113"].
# ──────────────────────────────────────────────────────────────────────────


def _build_timeline_table() -> dict[str, str]:
    """Compute the article+annex → ISO applicability-date mapping.

    Rules:

    * Art. 5 prohibitions                 → ``"2025-02-02"``
    * Art. 4 AI literacy                  → ``"2025-02-02"``
    * GPAI obligations (Art. 51-55)       → ``"2025-08-02"``
    * Annex III high-risk obligations     → ``"2026-08-02"``
    * Annex I embedded-product high-risk  → ``"2027-08-02"``
    * Everything else                     → ``"2026-08-02"`` (general
      Regulation applicability date)
    """
    table: dict[str, str] = {}

    GENERAL = "2026-08-02"
    PROHIBITION = "2025-02-02"
    GPAI = "2025-08-02"
    ANNEX_III_HRAIS = "2026-08-02"
    ANNEX_I_HRAIS = "2027-08-02"

    for n in range(1, 114):
        long_key = f"Article {n}"
        if n in (4, 5):
            table[long_key] = PROHIBITION
        elif 51 <= n <= 55:
            table[long_key] = GPAI
        else:
            table[long_key] = GENERAL

    for n in range(1, 14):
        long_key = f"Annex {_roman(n)}"
        if n == 3:
            table[long_key] = ANNEX_III_HRAIS
        elif n == 1:
            table[long_key] = ANNEX_I_HRAIS
        else:
            table[long_key] = GENERAL

    return table


TIMELINE_BY_ARTICLE: dict[str, str] = _build_timeline_table()


# ──────────────────────────────────────────────────────────────────────────
# Short ↔ long key conversion.
#
# The corpus ``ARTICLE_FULL_TEXT`` uses short keys: ``"Art. 6"``,
# ``"Annex III"``. The public TreeNode surface uses long-form publication
# keys: ``"Article 6"``, ``"Annex III"``.
# ──────────────────────────────────────────────────────────────────────────


def _long_form(short_key: str) -> str:
    if short_key.startswith("Art. "):
        return "Article " + short_key[len("Art. ") :]
    return short_key  # Annexes already long-form.


def _short_form(long_key: str) -> str:
    if long_key.startswith("Article "):
        return "Art. " + long_key[len("Article ") :]
    return long_key


# ──────────────────────────────────────────────────────────────────────────
# Stable node-id slug helpers.
#
# Slug shapes:
#   art_6          — article root
#   art_6_p_2      — Article 6 paragraph 2
#   art_6_p_2_a    — Article 6(2)(a) sub-point
#   annex_iii      — Annex III root
#   annex_iii_p_1  — Annex III item 1
#   annex_iii_p_1_a — Annex III(1)(a) sub-point
#   recital_42     — Recital 42
#   def_ai_system  — Art. 3 definition "AI system"
# ──────────────────────────────────────────────────────────────────────────


def _article_slug(short_key: str) -> str:
    if short_key.startswith("Art. "):
        return f"art_{short_key[len('Art. ') :]}"
    if short_key.startswith("Annex "):
        return f"annex_{short_key[len('Annex ') :].lower()}"
    raise ValueError(f"unknown short key shape: {short_key!r}")


def _slugify_definition_term(term: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")
    return f"def_{safe}"


# ──────────────────────────────────────────────────────────────────────────
# Paragraph + sub-point regexes.
#
# Articles use NBSP-padded headings (``"1.\xa0\xa0\xa0The..."``), annexes
# use space-padded headings (``": 1. The..."``). Both share the ``[:;]\s+``
# sub-point separator pattern (a real list item is preceded by clause-end
# punctuation; bare in-paragraph references to ``"point (h)"`` are NOT).
# ──────────────────────────────────────────────────────────────────────────


# Paragraph heading — Round 34 P1 tightened. Pre-fix the lookbehind was
# ``(?<=\s)`` which matched after ANY whitespace, so "in paragraph 2.
# The..." inside paragraph bodies was incorrectly detected as a heading
# (causing duplicate ``art_5_p_2`` etc. — 24 articles had duplicate
# children + impossible paragraph numbers like 47/49/50). The heading
# must now come at start-of-text, after newline, or after clause-end
# punctuation followed by whitespace. NBSP (\xa0) is treated as part of
# the heading's trailing whitespace via ``\s+`` (NBSP is in \s).
_PARA_HEADING_RE = re.compile(r"(?:^|(?<=[\n;.!?])\s+)(\d{1,2})\.\s+")

# Sub-point marker — list-item shape: ``[:;]\s+(letter)\s+``. The
# leading punctuation requirement is what distinguishes a real list item
# from a back-reference like ``"point (h) of the first subparagraph"``.
_SUBPOINT_RE = re.compile(r"[:;]\s+\(([a-z]{1,4})\)\s")

# Annex top-level numbered item — ``": 1. Biometrics"`` or
# ``"; 2. Critical infrastructure"`` etc.
_ANNEX_ITEM_RE = re.compile(r"(?:^|[.:;]\s)(\d{1,2})\.\s+(?=[A-Z])")


# ──────────────────────────────────────────────────────────────────────────
# Splitter primitives.
# ──────────────────────────────────────────────────────────────────────────


def _split_paragraphs_article(text: str) -> list[tuple[int | None, str]]:
    """Split an article body into ``(paragraph_number, paragraph_text)`` pairs.

    If the article has no numbered paragraphs (e.g. Art. 4 — single block),
    return one entry with ``paragraph_number=None``.
    """
    matches = list(_PARA_HEADING_RE.finditer(text))
    # We only treat this as a multi-paragraph article when the first match
    # starts at position 0 (the article opens with a paragraph number).
    # Otherwise the matches are coincidental digits inside the body and we
    # should keep the article as one block.
    if not matches or matches[0].start() != 0:
        return [(None, text.strip())]

    out: list[tuple[int | None, str]] = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        # Sanity — paragraph numbers usually run 1..N sequentially. Skip
        # entries with an out-of-range number (a stray digit collision).
        if num < 1 or num > 50:
            continue
        out.append((num, body))
    return out


def _split_subpoints(paragraph_text: str) -> list[tuple[str | None, str]]:
    """Split a paragraph (or annex item) body into ``(letter, text)`` pairs.

    Returns one entry with ``letter=None`` when the paragraph has no
    sub-points.

    The list-item discipline is ``[:;]\\s+\\(letter\\)\\s``. We split on
    every match: the segment BEFORE the first match is the paragraph
    preamble; each subsequent segment is a sub-point.
    """
    matches = list(_SUBPOINT_RE.finditer(paragraph_text))
    if not matches:
        return [(None, paragraph_text.strip())]

    # Preamble — the text up to and including the punctuation before the
    # first sub-point. We include the punctuation in the preamble so the
    # parent context reads naturally.
    first = matches[0]
    # ``first.start()`` is at the ``[:;]`` punctuation; +1 includes it.
    preamble = paragraph_text[: first.start() + 1].strip()

    out: list[tuple[str | None, str]] = []
    if preamble:
        out.append((None, preamble))

    for i, m in enumerate(matches):
        letter = m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(paragraph_text)
        body = paragraph_text[m.end() : end].strip()
        # Strip trailing punctuation noise.
        body = body.rstrip(" ;.")
        out.append((letter, body))
    return out


def _split_annex_items(text: str) -> list[tuple[int | None, str]]:
    """Split an annex body into ``(item_number, item_text)`` pairs.

    Annex IV (the architecture PDF specifically calls it out) and Annex III
    use the same shape: a leading preamble sentence ending in ``":"``,
    followed by ``"1. ..."``, ``"2. ..."`` numbered items.
    """
    matches = list(_ANNEX_ITEM_RE.finditer(text))
    if not matches:
        return [(None, text.strip())]

    out: list[tuple[int | None, str]] = []
    # Preamble before the first numbered item — kept as item_number=None.
    first = matches[0]
    preamble = text[: first.start()].strip()
    if preamble:
        out.append((None, preamble))

    for i, m in enumerate(matches):
        num = int(m.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        if num < 1 or num > 50:
            continue
        out.append((num, body))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Chapter id resolution — falls back to the corpus's ARTICLE_CHAPTER map.
# ──────────────────────────────────────────────────────────────────────────


def _chapter_id_for(short_key: str) -> str | None:
    ch = ARTICLE_CHAPTER.get(short_key)
    if ch is None:
        return None
    return ch


def _risk_for(long_key: str) -> RiskTier:
    return RISK_TIER_BY_ARTICLE.get(long_key, "n/a")


def _timeline_for(long_key: str) -> str:
    return TIMELINE_BY_ARTICLE.get(long_key, "2026-08-02")


# ──────────────────────────────────────────────────────────────────────────
# Tree construction.
# ──────────────────────────────────────────────────────────────────────────


def _make_article_subtree(
    short_key: str,
    long_key: str,
    body: str,
    risk: RiskTier,
    timeline: str,
    chapter_id: str | None,
    nodes: dict[str, TreeNode],
) -> None:
    """Walk one article's text and append its tree to ``nodes`` in-place."""
    root_id = _article_slug(short_key)
    children_para_ids: list[str] = []

    paragraphs = _split_paragraphs_article(body)

    for p_num, p_text in paragraphs:
        if p_num is None:
            # Single-block article (Art. 4, Annex preambles).
            para_id = f"{root_id}_p_solo"
        else:
            para_id = f"{root_id}_p_{p_num}"
        children_para_ids.append(para_id)

        subpoints = _split_subpoints(p_text)
        children_sub_ids: list[str] = []

        # Locate the "preamble" sub-point (letter=None) — its text is the
        # paragraph's main body before the sub-points start.
        para_main_text = p_text  # default — keep full paragraph as text
        if subpoints and subpoints[0][0] is None and len(subpoints) > 1:
            para_main_text = subpoints[0][1]

        for letter, sp_text in subpoints:
            if letter is None:
                # Preamble — already absorbed into the paragraph node
                # text. Don't emit as its own subpoint.
                continue
            sub_id = f"{para_id}_{letter}"
            children_sub_ids.append(sub_id)
            nodes[sub_id] = TreeNode(
                node_id=sub_id,
                kind="subpoint",
                article_number=long_key,
                paragraph_number=p_num,
                subpoint_letter=letter,
                text=sp_text,
                parent_id=para_id,
                risk_tier=risk,
                timeline_effective_date=timeline,
                chapter_id=chapter_id,
                children_ids=(),
            )

        nodes[para_id] = TreeNode(
            node_id=para_id,
            kind="paragraph",
            article_number=long_key,
            paragraph_number=p_num,
            subpoint_letter=None,
            text=para_main_text,
            parent_id=root_id,
            risk_tier=risk,
            timeline_effective_date=timeline,
            chapter_id=chapter_id,
            children_ids=tuple(children_sub_ids),
        )

    nodes[root_id] = TreeNode(
        node_id=root_id,
        kind="article",
        article_number=long_key,
        paragraph_number=None,
        subpoint_letter=None,
        text=body.strip(),
        parent_id=None,
        risk_tier=risk,
        timeline_effective_date=timeline,
        chapter_id=chapter_id,
        children_ids=tuple(children_para_ids),
    )


def _make_annex_subtree(
    short_key: str,
    long_key: str,
    body: str,
    risk: RiskTier,
    timeline: str,
    nodes: dict[str, TreeNode],
) -> None:
    """Walk one annex's text and append its tree to ``nodes`` in-place.

    Annexes share the article tree shape but use ``kind="annex"`` and
    ``kind="annex_point"`` for their numbered + lettered children.
    Annex IV's tabular tech-doc layout is preserved by keeping each
    numbered item as its own child node (with sub-points as grand-children)
    — no flattening, no merge across rows.
    """
    root_id = _article_slug(short_key)
    children_item_ids: list[str] = []

    items = _split_annex_items(body)

    for item_num, item_text in items:
        if item_num is None:
            # Annex preamble.
            item_id = f"{root_id}_p_preamble"
            preamble_text = item_text
            nodes[item_id] = TreeNode(
                node_id=item_id,
                kind="annex_point",
                article_number=long_key,
                paragraph_number=None,
                subpoint_letter=None,
                text=preamble_text,
                parent_id=root_id,
                risk_tier=risk,
                timeline_effective_date=timeline,
                chapter_id=None,
                children_ids=(),
            )
            children_item_ids.append(item_id)
            continue

        item_id = f"{root_id}_p_{item_num}"
        children_item_ids.append(item_id)

        subpoints = _split_subpoints(item_text)
        children_sub_ids: list[str] = []
        item_main_text = item_text
        if subpoints and subpoints[0][0] is None and len(subpoints) > 1:
            item_main_text = subpoints[0][1]

        for letter, sp_text in subpoints:
            if letter is None:
                continue
            sub_id = f"{item_id}_{letter}"
            children_sub_ids.append(sub_id)
            nodes[sub_id] = TreeNode(
                node_id=sub_id,
                kind="annex_point",
                article_number=long_key,
                paragraph_number=item_num,
                subpoint_letter=letter,
                text=sp_text,
                parent_id=item_id,
                risk_tier=risk,
                timeline_effective_date=timeline,
                chapter_id=None,
                children_ids=(),
            )

        nodes[item_id] = TreeNode(
            node_id=item_id,
            kind="annex_point",
            article_number=long_key,
            paragraph_number=item_num,
            subpoint_letter=None,
            text=item_main_text,
            parent_id=root_id,
            risk_tier=risk,
            timeline_effective_date=timeline,
            chapter_id=None,
            children_ids=tuple(children_sub_ids),
        )

    nodes[root_id] = TreeNode(
        node_id=root_id,
        kind="annex",
        article_number=long_key,
        paragraph_number=None,
        subpoint_letter=None,
        text=body.strip(),
        parent_id=None,
        risk_tier=risk,
        timeline_effective_date=timeline,
        chapter_id=None,
        children_ids=tuple(children_item_ids),
    )


def _make_recital_nodes(nodes: dict[str, TreeNode]) -> None:
    """Recitals are atomic — one node per recital, no parent."""
    for n, text in RECITALS.items():
        rid = f"recital_{n}"
        nodes[rid] = TreeNode(
            node_id=rid,
            kind="recital",
            article_number=None,
            paragraph_number=int(n),
            subpoint_letter=None,
            text=text.strip(),
            parent_id=None,
            # Recitals are interpretive context, not normative — n/a.
            risk_tier="n/a",
            timeline_effective_date="2026-08-02",
            chapter_id=None,
            children_ids=(),
        )


def _make_definition_nodes(nodes: dict[str, TreeNode]) -> None:
    """Art. 3 definitions — atomic, parented to ``art_3``."""
    parent_id = "art_3"
    for term, body in ART_3_DEFINITIONS.items():
        slug = _slugify_definition_term(term)
        nodes[slug] = TreeNode(
            node_id=slug,
            kind="definition",
            article_number="Article 3",
            paragraph_number=None,
            subpoint_letter=None,
            # Re-emit "term: body" so the node text reads as a definition
            # rather than a bare phrase.
            text=f"{term}: {body.strip()}",
            parent_id=parent_id if parent_id in nodes else None,
            risk_tier="n/a",
            timeline_effective_date="2026-08-02",
            chapter_id=None,
            children_ids=(),
        )


@functools.lru_cache(maxsize=1)
def build_tree() -> dict[str, TreeNode]:
    """Build the full document tree lazily — cached across all callers.

    Top-level node-id surface (built in this order):

    1. 113 article roots + paragraph/sub-point descendants.
    2. 13 annex roots + item/sub-point descendants.
    3. 180 recitals (atomic).
    4. 68 Art. 3 definitions (atomic, child of ``art_3``).
    """
    nodes: dict[str, TreeNode] = {}

    # 1) Articles
    for short_key, body in ARTICLE_FULL_TEXT.items():
        if not short_key.startswith("Art. "):
            continue
        long_key = _long_form(short_key)
        risk = _risk_for(long_key)
        timeline = _timeline_for(long_key)
        chapter_id = _chapter_id_for(short_key)
        _make_article_subtree(
            short_key, long_key, body, risk, timeline, chapter_id, nodes
        )

    # 2) Annexes
    for short_key, body in ARTICLE_FULL_TEXT.items():
        if not short_key.startswith("Annex "):
            continue
        long_key = _long_form(short_key)
        risk = _risk_for(long_key)
        timeline = _timeline_for(long_key)
        _make_annex_subtree(short_key, long_key, body, risk, timeline, nodes)

    # 3) Recitals
    _make_recital_nodes(nodes)

    # 4) Definitions
    _make_definition_nodes(nodes)

    return nodes


# ──────────────────────────────────────────────────────────────────────────
# Public navigation API.
# ──────────────────────────────────────────────────────────────────────────


def iter_children(parent_id: str) -> Iterator[TreeNode]:
    """Yield direct children of a node in declaration order.

    Returns an empty iterator if the parent has no children or doesn't
    exist — the tree is robust against unknown queries.
    """
    tree = build_tree()
    parent = tree.get(parent_id)
    if parent is None:
        return iter(())
    return (tree[c] for c in parent.children_ids if c in tree)


def parent_of(node_id: str) -> TreeNode | None:
    """Return the parent node, or ``None`` for top-level chapters/recitals.

    Top-level nodes (article roots, annex roots, recitals, definitions
    when ``art_3`` is unavailable) return ``None``.
    """
    tree = build_tree()
    node = tree.get(node_id)
    if node is None or node.parent_id is None:
        return None
    return tree.get(node.parent_id)


def get_parent_context(node_id: str) -> str:
    """Return the encompassing parent text for ``node_id``.

    Per the architecture spec: "When a specific Child Node satisfies
    retrieval criteria, the pipeline passes the full Parent Node context
    to the LLM context window."

    Resolution:

    * If the node is itself an article or annex root, return its full text.
    * If the node is a paragraph, walk up to the article root.
    * If the node is a sub-point, walk up to the article root (NOT just
      to its paragraph) — the rubric demands the encompassing Article
      body so the LLM sees siblings + preamble.
    * If the node is a recital or definition, return its own text
      (already atomic).
    """
    tree = build_tree()
    node = tree.get(node_id)
    if node is None:
        return ""

    if node.kind in ("recital", "definition"):
        return node.text

    # Climb to the highest non-None ancestor.
    current = node
    while current.parent_id is not None:
        parent = tree.get(current.parent_id)
        if parent is None:
            break
        current = parent

    return current.text


# ──────────────────────────────────────────────────────────────────────────
# Substring + whole-word keyword scan.
# ──────────────────────────────────────────────────────────────────────────


_DEFAULT_CHILD_KINDS: tuple[NodeKind, ...] = (
    "paragraph",
    "subpoint",
    "annex_point",
)


_QUOTE_CHARS = {
    "‘": "'",  # left single curly
    "’": "'",  # right single curly
    "“": '"',  # left double curly
    "”": '"',  # right double curly
    "«": '"',  # guillemet
    "»": '"',
}


def _normalise_for_match(text: str) -> str:
    """Lower-case + collapse NBSP + curly quotes + whitespace for matches.

    EUR-Lex prose padding habits we strip:

    * ``\\xa0`` (NBSP)                    → regular space
    * ``\\u2018 / \\u2019``                → plain apostrophe
    * ``\\u201c / \\u201d``                → plain double quote
    * Curly quotes are then stripped so ``"real-time" remote`` and
      ``real-time remote`` both match the same needle.
    * Runs of whitespace collapse to one.
    """
    out = text.replace("\xa0", " ")
    for src, dst in _QUOTE_CHARS.items():
        out = out.replace(src, dst)
    # Drop the quote chars entirely — they confuse substring matches.
    out = out.replace("'", " ").replace('"', " ")
    return re.sub(r"\s+", " ", out).lower().strip()


def find_nodes_by_keyword(
    keyword: str,
    kinds: tuple[str, ...] = _DEFAULT_CHILD_KINDS,
) -> list[TreeNode]:
    """Return child nodes whose text matches ``keyword``.

    Match semantics: case-insensitive substring. ``\\xa0`` (NBSP) is
    normalised to space so phrases like ``"real-time biometric"`` find
    the EUR-Lex prose despite the corpus's NBSP padding.

    ``kinds`` defaults to the child-level kinds (paragraph + sub-point +
    annex_point). Pass ``("article", "annex")`` to scan roots instead.
    """
    if not keyword:
        return []

    needle = _normalise_for_match(keyword)
    kind_set = set(kinds)

    tree = build_tree()
    out: list[TreeNode] = []
    for node in tree.values():
        if node.kind not in kind_set:
            continue
        if needle in _normalise_for_match(node.text):
            out.append(node)
    return out


__all__ = [
    "TreeNode",
    "RiskTier",
    "NodeKind",
    "RISK_TIER_BY_ARTICLE",
    "TIMELINE_BY_ARTICLE",
    "build_tree",
    "iter_children",
    "parent_of",
    "get_parent_context",
    "find_nodes_by_keyword",
]

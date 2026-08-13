"""HyPA-RAG Hybrid Reciprocal Rank Fusion (RRF) Sparse-Dense Retriever.

Combines candidate article/annex reference lists from multiple retrieval channels:
1. Sparse BM25 keyword matching
2. Dense Neo4j / SVD vector recall
3. Role-Duty seed candidate recommendations

Formula:
    RRF(doc) = sum_{m in M} ( w_m / (k + rank_m(doc)) )
where k = 60 (standard RRF constant), rank_m(doc) is 1-indexed rank in list m.

Validates all fused candidate outputs against the 126 canonical references in ARTICLE_EXISTENCE.
"""
from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from typing import Sequence

from app.data.article_existence import ARTICLE_EXISTENCE

logger = logging.getLogger(__name__)

# Standard RRF constant (Cormack et al., 2009)
RRF_K_CONSTANT = 60

# Exact reference matching regexes with end-of-string anchors
_REF_VALID_RE = re.compile(
    r"^(?:Art\.?|Article)\s*(\d+)((?:\.[a-zA-Z0-9_-]+|\(\d+\)|\([a-z0-9_-]+\))*)\s*$",
    re.IGNORECASE,
)
_ANNEX_VALID_RE = re.compile(
    r"^Annex\s+([IVXLCDM]+|\d+)((?:\.[a-zA-Z0-9_-]+|\(\d+\)|\([a-z0-9_-]+\))*)\s*$",
    re.IGNORECASE,
)

_ANNEX_ARABIC_TO_ROMAN = {
    "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
    "6": "VI", "7": "VII", "8": "VIII", "9": "IX", "10": "X",
    "11": "XI", "12": "XII", "13": "XIII",
}


def is_rrf_retrieval_enabled() -> bool:
    """Return True if HyPA RRF retrieval is enabled via environment variable.

    R329 — default flipped ON -> OFF. Three reasons, all measured:

    1. RRF over this corpus is a known wash, re-confirmed three times
       (``docs/ROUNDS.md`` R31/R69). The repo's own RRF already ships behind
       ``REGENOLD_RRF_FUSION``, default ``"0"`` (``app/data/kb_search.py:458``),
       implemented at ``app/engines/turboquant_index.py:539``. This module is a
       second implementation of the same math.
    2. This path calls BM25 unconditionally, defeating the ``if not entities:``
       gate at ``_graph_rag_impl.py:2223``, whose comment records the gate as
       load-bearing precisely because unrelated tokens "pollute the citation
       set".
    3. The dense arm is inert by default (``REGENOLD_GRAPH_VECTOR_RECALL=0``),
       so "hybrid sparse+dense" degenerates to BM25 + role seeds.
    """
    return os.environ.get("REGENOLD_HYPA_RRF_RETRIEVAL", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def canonicalize_article_ref(ref: str) -> str:
    """Canonicalize a reference string into standard wire format (Article N / Annex X)."""
    if not ref or not ref.strip():
        return ""
    r = ref.strip().rstrip(".,")
    m_art = _REF_VALID_RE.match(r)
    if m_art:
        art_num = str(int(m_art.group(1)))
        subpoint = m_art.group(2) or ""
        head = f"Art. {art_num}"
        if head in ARTICLE_EXISTENCE:
            return f"Article {art_num}{subpoint}"
    m_ann = _ANNEX_VALID_RE.match(r)
    if m_ann:
        raw_val = m_ann.group(1).upper()
        roman = _ANNEX_ARABIC_TO_ROMAN.get(raw_val, raw_val)
        subpoint = m_ann.group(2) or ""
        head = f"Annex {roman}"
        if head in ARTICLE_EXISTENCE:
            return f"Annex {roman}{subpoint}"
    return r


def canonicalize_to_internal_ref(ref: str) -> str:
    """Convert any article/annex citation to canonical internal KB format (Art. N / Annex X)."""
    if not ref or not ref.strip():
        return ""
    r = ref.strip().rstrip(".,")
    m_art = _REF_VALID_RE.match(r)
    if m_art:
        art_num = str(int(m_art.group(1)))
        head = f"Art. {art_num}"
        if head in ARTICLE_EXISTENCE:
            return head
    m_ann = _ANNEX_VALID_RE.match(r)
    if m_ann:
        raw_val = m_ann.group(1).upper()
        roman = _ANNEX_ARABIC_TO_ROMAN.get(raw_val, raw_val)
        head = f"Annex {roman}"
        if head in ARTICLE_EXISTENCE:
            return head
    return r


def extract_provision_head(ref: str) -> str:
    """Extract macro article/annex head (e.g. Article 13 from Article 13(1))."""
    if not ref or not ref.strip():
        return ""
    c = canonicalize_article_ref(ref)
    m_art = _REF_VALID_RE.match(c)
    if m_art:
        return f"Article {int(m_art.group(1))}"
    m_ann = _ANNEX_VALID_RE.match(c)
    if m_ann:
        raw_val = m_ann.group(1).upper()
        roman = _ANNEX_ARABIC_TO_ROMAN.get(raw_val, raw_val)
        return f"Annex {roman}"
    return c


def is_valid_article_ref(ref: str) -> bool:
    """Validate whether a candidate reference resolves to a canonical reference in ARTICLE_EXISTENCE."""
    if not ref or not ref.strip():
        return False
    r = ref.strip().rstrip(".,")
    m_art = _REF_VALID_RE.match(r)
    if m_art:
        return f"Art. {int(m_art.group(1))}" in ARTICLE_EXISTENCE
    m_ann = _ANNEX_VALID_RE.match(r)
    if m_ann:
        raw_val = m_ann.group(1).upper()
        roman = _ANNEX_ARABIC_TO_ROMAN.get(raw_val, raw_val)
        return f"Annex {roman}" in ARTICLE_EXISTENCE
    return False


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[str]],
    weights: Sequence[float] | None = None,
    k_constant: int = RRF_K_CONSTANT,
    collapse_to_head: bool = True,
) -> list[tuple[str, float]]:
    """Compute Reciprocal Rank Fusion (RRF) scores across multiple ranked candidate lists.

    Canonicalizes reference aliases and optionally collapses subpoints to provision heads so equivalent citations fuse correctly.

    :param ranked_lists: list of ordered candidate reference lists.
    :param weights: optional importance weights per list (defaults to 1.0 each).
    :param k_constant: smoothing constant (default 60, must be > 0).
    :param collapse_to_head: if True, fuses subpoint ranks into macro provision head (Article N / Annex X).
    :return: list of (canonical_reference, rrf_score) tuples sorted in descending order of score.
    """
    if k_constant <= 0:
        raise ValueError(f"k_constant must be positive > 0, got {k_constant}")

    if not ranked_lists:
        return []

    if weights is None:
        weights = [1.0] * len(ranked_lists)
    elif len(weights) != len(ranked_lists):
        raise ValueError("Length of weights must match length of ranked_lists")

    scores: dict[str, float] = defaultdict(float)

    for list_idx, candidate_list in enumerate(ranked_lists):
        weight = weights[list_idx]
        seen_in_list: set[str] = set()
        valid_rank = 1

        for item in (candidate_list or []):
            if not item or not isinstance(item, str) or not item.strip():
                continue
            canonical_item = canonicalize_article_ref(item)
            if not canonical_item:
                continue

            target_key = extract_provision_head(canonical_item) if collapse_to_head else canonical_item
            if not target_key or target_key in seen_in_list:
                continue
            seen_in_list.add(target_key)

            # RRF formula calculation
            rrf_score = weight * (1.0 / (k_constant + valid_rank))
            scores[target_key] += rrf_score
            valid_rank += 1

    # Sort candidates by descending RRF score
    sorted_candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_candidates


def fuse_sparse_dense_candidates(
    bm25_refs: Sequence[str],
    vector_refs: Sequence[str],
    role_seed_refs: Sequence[str] | None = None,
    top_k: int = 10,
) -> list[str]:
    """Fuse sparse BM25, dense vector, and role-duty seed candidates into a single ranked list.

    Filters and validates every candidate reference against canonical ARTICLE_EXISTENCE.

    :param bm25_refs: candidate references from BM25 sparse search.
    :param vector_refs: candidate references from dense vector recall.
    :param role_seed_refs: optional candidate references from role-duty seed rules.
    :param top_k: maximum number of fused candidates to return.
    :return: list of validated canonical article/annex reference strings.
    """
    if top_k <= 0:
        return []

    ranked_lists: list[Sequence[str]] = [bm25_refs or [], vector_refs or []]
    weights: list[float] = [1.0, 1.0]

    if role_seed_refs:
        ranked_lists.append(role_seed_refs)
        weights.append(1.2)  # Higher weight for high-precision role-duty seed hits

    fused_tuples = reciprocal_rank_fusion(ranked_lists, weights=weights, collapse_to_head=True)

    seen_results: set[str] = set()
    validated_results: list[str] = []
    for ref, _score in fused_tuples:
        if not ref or ref in seen_results:
            continue
        if is_valid_article_ref(ref):
            seen_results.add(ref)
            validated_results.append(ref)
            if len(validated_results) >= top_k:
                break

    return validated_results


"""R449 — the sentence-SVD stage DISPLACES BM25 winners; it is not additive.

WHY THIS TEST EXISTS
====================

``kb_search.top_articles_by_relevance`` used to document both dense stages as
"purely additive (never displaces a BM25 winner)". That sentence was false for
the sentence-index stage, and the R449 measurement
(``docs/measurements/r449/UNIT-GRAIN-k8.md``, k=8, all 110 gold rows, the
production entry point) is what falsified it:

* the sparse control returns **exactly** 8 references on **every** row;
* the article-level SVD stage (``dense_a``) adds **0** references — the fill
  genuinely has no vacant slot to occupy;
* the sentence-level SVD stage (``dense_b``) therefore cannot have added its
  **30** references (over 27 rows, 3 of them gold) through the fill, yet it
  changes the top-8 **membership** while the output **length stays 8**.

The only remaining mechanism is the one at the call site:
``emb_boost = 1.20`` for every article with a sentence hit at similarity
``>= 0.50``, applied inside the BM25 scoring loop *before* the ``scored[:k]``
cut. A 20% multiplier reorders ``best`` and evicts a lower-ranked BM25 winner.

WHAT THIS MODULE PINS
=====================

1. **Fill cannot be the source of a downstream addition** when the ranking is
   full — the premise of the whole argument, asserted directly.
2. **The multiplier reaches the cut**, and the ``>= 0.50`` gate is exact:
   fabricating a 0.90 hit promotes a candidate the sparse ranking excluded, a
   0.50 hit still promotes it, and a 0.499 hit does not (and cannot be appended,
   because the ranking is full).
3. **The shipped configuration shows displacement in aggregate** against the
   real sentence index: toggling ``REGENOLD_EMBEDDINGS_INDEX`` changes top-k
   membership at unchanged length.

If the boost stops reaching the cut — multiplier dropped to 1.0, the gate made
unreachable, ``high_sim_articles`` never populated, or the stage reverted to
fill-only — every one of these fails instead of leaving a comment lying to the
next reader.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import pytest

from app.data import kb_search
from app.engines import embeddings_index
from app.engines.turboquant_index import additive_dense_fill

_REPO = Path(__file__).resolve().parents[1]
GOLD = _REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

#: The k the deterministic-parse fallback lane uses (``_BM25_FALLBACK_K = 8``),
#: i.e. the configuration every R449 number was measured at.
K = 8
MIN_SCORE = 1.0

#: The gate and the multiplier at the call site. Both are pinned by value: a
#: silent retune of either is exactly what these tests exist to catch.
BOOST_GATE = 0.50
BOOST_FACTOR = 1.20

#: Measured 2026-09-28: 110 full rows, 30 added refs over 27 rows. The floors sit
#: far below that so ordinary KB drift does not red the test, while removing the
#: boost (or its gate) collapses them to zero and fails loudly.
MIN_FULL_ROWS = 20
MIN_ADDED_REFS = 5
MIN_GAINED_ROWS = 3

#: How many gold questions the derived-target scan may walk before giving up.
SCAN_QUESTIONS = 6


class _Hit(NamedTuple):
    """Minimal stand-in for ``embeddings_index.SentenceHit``.

    ``kb_search`` reads exactly two attributes off a hit — ``similarity`` and
    ``article_ref`` — so fabricating them keeps this module runnable with no
    built sentence assets and isolates the boost from the real index.
    """

    article_ref: str
    similarity: float


@pytest.fixture(autouse=True)
def _deterministic_flags(monkeypatch: pytest.MonkeyPatch):
    """Force the deterministic default retrieval configuration.

    Only ``REGENOLD_EMBEDDINGS_INDEX`` is meant to differ between the two arms;
    an environment that left score fusion or RRF on would reshape the ranking by
    a second mechanism and hide (or fake) the boost's contribution.

    The index is ``lru_cache``d, so the cache is cleared around each test: a
    fielded index built by another test would change every raw score here.
    """
    for flag in (
        "REGENOLD_RRF_FUSION",
        "REGENOLD_SCORE_FUSION",
        "REGENOLD_GRAPH_2HOP",
        "REGENOLD_GRAPH_PPR",
        "REGENOLD_PATH_RAG",
        "REGENOLD_GRAPH_FUSE_SLACK",
        "REGENOLD_CONTEXTUAL_FIELDS",
        "REGENOLD_TURBOQUANT_DENSE",
    ):
        monkeypatch.setenv(flag, "0")
    kb_search._build_index.cache_clear()  # noqa: SLF001 — module-level lru_cache
    yield
    kb_search._build_index.cache_clear()  # noqa: SLF001


def _retrieve(question: str) -> list[str]:
    hits = kb_search.top_articles_by_relevance(question, k=K, min_score=MIN_SCORE)
    return [h for h in hits if isinstance(h, str) and h.strip()]


def _wire_ref(internal: str) -> str:
    """Internal BM25 key → the shape a sentence hit carries.

    ``kb_search`` maps ``"Article 6"`` back to ``"Art. 6"`` and leaves annexes
    alone, so this is the inverse of that mapping and nothing more.
    """
    if internal.startswith("Art. "):
        return "Article " + internal[len("Art. ") :]
    return internal


def _fake_hits(monkeypatch: pytest.MonkeyPatch, ref: str | None, similarity: float) -> None:
    """Replace the sentence index with at most one synthetic hit.

    ``ref=None`` is the sparse control: an empty hit list means no boost, no
    append, and no dependence on whether the real assets are built.
    """
    hits = [] if ref is None else [_Hit(article_ref=ref, similarity=similarity)]
    monkeypatch.setattr(embeddings_index, "is_available", lambda: True)
    monkeypatch.setattr(embeddings_index, "query", lambda *a, **kw: list(hits))


def _gold_questions(limit: int | None = None) -> list[tuple[str, str]]:
    if not GOLD.exists():
        pytest.skip(f"gold set not present: {GOLD}")
    rows: list[tuple[str, str]] = []
    with GOLD.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            question = str(raw.get("question") or "").strip()
            if question:
                rows.append((str(raw.get("id") or f"row_{len(rows)}"), question))
            if limit is not None and len(rows) >= limit:
                break
    return rows


# ── Premise: a full ranking leaves the fill nothing to do ────────────────────


def test_additive_fill_cannot_add_anything_when_the_ranking_is_full() -> None:
    """The reason a downstream addition must be displacement.

    ``additive_dense_fill`` is additive *relative to its arguments*. If the
    ranking it is handed already holds ``k`` refs, no dense candidate can enter
    through it — so a reference the pipeline gained cannot have come from fill.
    """
    full = [f"Art. {n}" for n in range(1, K + 1)]
    dense = [("Art. 99", 0.9), ("Annex III", 0.8)]
    assert additive_dense_fill(full, dense, k=K) == full

    # Non-vacuity: below k it does append, so the function is not inert.
    short = full[: K - 1]
    assert additive_dense_fill(short, dense, k=K) == [*short, "Art. 99"]


# ── Mechanism: the multiplier, gated at exactly 0.50 ─────────────────────────


def test_high_similarity_hit_promotes_a_candidate_into_the_cut(monkeypatch) -> None:
    """A >= 0.50 hit must promote; a sub-threshold one must not.

    The target is *derived* rather than pinned to a row id: the scan looks for a
    candidate the real KB ranks just below a full top-k on a real gold question,
    so the test cannot pass on a row that merely had a vacant slot. Fabricating
    the hit removes the sentence assets from the equation — the similarity value
    is the only thing that differs between the two runs, which makes the
    >= 0.50 gate and the 1.20x multiplier the only possible causes.
    """
    questions = _gold_questions(limit=SCAN_QUESTIONS)
    candidates = sorted({r for r in kb_search._build_index().article_refs})  # noqa: SLF001

    for row_id, question in questions:
        _fake_hits(monkeypatch, None, 0.0)
        sparse = _retrieve(question)
        if len(sparse) != K:
            continue  # a vacant slot exists — fill could act, so skip the row

        for internal in candidates:
            if internal in sparse:
                continue
            wire = _wire_ref(internal)
            _fake_hits(monkeypatch, wire, 0.90)
            lifted = _retrieve(question)
            if internal not in lifted:
                continue

            # Found the mechanism working. Pin the gate and the length.
            assert len(lifted) == K, (
                f"{row_id}: promoting {internal!r} changed the output length "
                f"({len(sparse)} -> {len(lifted)}); the fill can only act on a "
                "vacant slot, so this row is not evidence of displacement"
            )
            _fake_hits(monkeypatch, wire, BOOST_GATE)
            at_gate = _retrieve(question)
            assert internal in at_gate, (
                f"{row_id}: a hit at exactly {BOOST_GATE} no longer promotes "
                f"{internal!r} into the cut — the gate at the call site is "
                "documented as inclusive (>= 0.50)"
            )
            _fake_hits(monkeypatch, wire, BOOST_GATE - 0.001)
            below = _retrieve(question)
            assert internal not in below, (
                f"{row_id}: a hit BELOW {BOOST_GATE} promoted {internal!r}; "
                "either the gate was loosened or sub-threshold hits now "
                "displace BM25 winners"
            )
            assert below == sparse, (
                f"{row_id}: a sub-threshold hit changed the ranking at all "
                f"({sparse} -> {below}); the only mechanism should be the boost"
            )
            assert len(lifted) == len(sparse) == K
            return

    pytest.fail(
        f"no gold question in the first {SCAN_QUESTIONS} let a {BOOST_FACTOR}x "
        "sentence-similarity boost lift a candidate into a full top-"
        f"{K}; the boost no longer reaches the cut (see the Round-32 note in "
        "app/data/kb_search.py)"
    )


# ── Shipped configuration: displacement in aggregate ─────────────────────────


def test_embeddings_flag_changes_membership_at_unchanged_length(monkeypatch) -> None:
    """Toggle the real sentence index and watch the top-k swap members.

    On rows where BM25 already filled all ``k`` slots, any reference the boosted
    arm gains is, by the premise above, a displaced winner. The aggregate is the
    measurement: 27 of 110 rows, 30 refs, length never changing.
    """
    if not embeddings_index.is_available():
        pytest.skip("sentence-index assets not built — run scripts/build_embeddings_index.py")

    full_rows = 0
    added_refs = 0
    gained_rows = 0
    for row_id, question in _gold_questions():
        monkeypatch.setenv("REGENOLD_EMBEDDINGS_INDEX", "0")
        sparse = _retrieve(question)
        monkeypatch.setenv("REGENOLD_EMBEDDINGS_INDEX", "1")
        boosted = _retrieve(question)

        assert len(boosted) == len(sparse), (
            f"{row_id}: the sentence stage changed the output length "
            f"({len(sparse)} -> {len(boosted)}). That is the FILL path, which "
            "the R449 measurement found has no vacant slot to use; re-measure "
            "before labelling either mechanism"
        )
        if len(sparse) != K:
            continue
        full_rows += 1
        gained = [ref for ref in boosted if ref not in sparse]
        added_refs += len(gained)
        gained_rows += int(bool(gained))

    if full_rows < MIN_FULL_ROWS:
        pytest.skip(
            f"only {full_rows} of {len(_gold_questions())} rows return a full "
            f"top-{K}; the R449 displacement sample assumes BM25 saturates k, so "
            "this run cannot support the claim — re-run "
            "`python -m evals.retrieval.unit_grain --arms bm25,dense_b`"
        )

    assert added_refs >= MIN_ADDED_REFS, (
        f"{added_refs} references added over {full_rows} saturated rows "
        f"(measured R449: 30 over 110) — the sentence-SVD boost is no longer "
        "reaching the top-k cut"
    )
    assert gained_rows >= MIN_GAINED_ROWS, (
        f"only {gained_rows} of {full_rows} saturated rows changed membership "
        f"(measured R449: 27) — the boost still fires but barely reshapes the cut"
    )

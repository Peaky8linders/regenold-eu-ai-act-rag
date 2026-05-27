"""Coverage for the ontology-augmented BM25 index.

Pins the May 2026 extension to :mod:`app.data.kb_search`: in addition
to the legacy ~82 obligation-summary documents, the index now ingests
the typed ontology (``PRACTICE_REGISTRY``, ``ANNEX_III_REGISTRY``,
``PHASE_REGISTRY``) as ~25 virtual documents keyed by the parent
article anchor. Closes the recall gap on lay phrasings of Art. 5
prohibitions ("manipulative AI", "subliminal techniques"), Annex III
categories ("essential public services"), and rollout-date prose
("applicable from", "entry into force").

These tests pin the contract:

* The corpus grew from ~82 to > 100 docs.
* Lay phrasings now surface the correct primary article anchor.
* The pre-existing canonical "How long must logs be kept?" → Art. 19
  query still passes (no regression).
* Every emitted article_key resolves in ``ARTICLE_EXISTENCE`` — the
  ontology-keying logic doesn't leak a hallucinated reference.
"""
from __future__ import annotations

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb_search import (
    _build_index,
    _index_stats,
    relevance_score,
    top_articles_by_relevance,
)


# Reuse the same prefix-existence helper as test_kb_consistency. Local
# copy keeps this file self-contained without cross-test imports.
def _is_known_or_prefix_known(ref: str) -> bool:
    if ref in ARTICLE_EXISTENCE:
        return True
    candidate = ref
    while "." in candidate:
        candidate = candidate.rsplit(".", 1)[0].strip()
        if candidate in ARTICLE_EXISTENCE:
            return True
    return False


class TestOntologyIndexGrowth:
    """The index now ingests the typed ontology, growing past 100 docs."""

    def test_index_has_more_than_100_docs(self) -> None:
        """Pre-extension: ~82 KB obligation rows. Post-extension: KB + 9
        practices + 8 Annex III categories + 6 phases ≈ 105+ docs."""
        stats = _index_stats()
        assert stats["total"] > 100, (
            f"Expected > 100 docs after ontology ingestion; got {stats}"
        )

    def test_index_still_contains_kb_docs(self) -> None:
        """The original ~82 KB obligation summaries must stay intact."""
        stats = _index_stats()
        # The KB has at least the 20+ articles enumerated in
        # EC_CHECKER_OBLIGATION_MAP; we don't pin the exact KB count
        # because the KB grows independently of this module.
        assert stats["kb"] >= 20, (
            f"Expected KB doc count ≥ 20; got {stats}"
        )

    def test_index_contains_ontology_docs(self) -> None:
        """Ontology virtual docs were added."""
        stats = _index_stats()
        # 9 practices + 8 Annex III + at least 5 phases with non-empty
        # articles tuples = 22 minimum.
        assert stats["ontology"] >= 20, (
            f"Expected ontology doc count ≥ 20; got {stats}"
        )


class TestPracticeQueriesSurfaceArt5:
    """Lay phrasings of Art. 5 prohibitions now anchor on Art. 5."""

    def test_manipulative_ai_surfaces_art_5(self) -> None:
        """Pre-extension: 'manipulative AI' missed the KB row for Art. 5
        because the obligation summary uses 'prohibited' / 'practices'
        more than 'manipulative'. The Practice.description prose for
        subliminal_manipulation includes 'manipulative' verbatim."""
        hits = top_articles_by_relevance(
            "Are manipulative AI techniques allowed?", k=5, min_score=1.0,
        )
        assert "Art. 5" in hits, f"Expected Art. 5 in hits; got {hits}"

    def test_subliminal_techniques_surfaces_art_5(self) -> None:
        hits = top_articles_by_relevance(
            "What does the AI Act say about subliminal techniques?",
            k=5, min_score=1.0,
        )
        assert "Art. 5" in hits, f"Expected Art. 5 in hits; got {hits}"

    def test_biometric_categorisation_surfaces_art_5_or_annex_iii(self) -> None:
        """Biometric categorisation by SENSITIVE attributes is prohibited
        under Art. 5(1)(g); by non-sensitive attributes it's high-risk
        under Annex III(1)(b). Both are correct anchors — the verdict
        path downstream disambiguates."""
        hits = top_articles_by_relevance(
            "biometric categorisation of natural persons",
            k=5, min_score=1.0,
        )
        assert "Art. 5" in hits or "Annex III" in hits, (
            f"Expected Art. 5 or Annex III in hits; got {hits}"
        )


class TestAnnexIIIQueries:
    """Lay phrasings of high-risk use-case categories now anchor on Annex III."""

    def test_essential_public_services_surfaces_annex_iii(self) -> None:
        """The essential_services AnnexIIICategory description names
        'essential public assistance benefits and services' verbatim."""
        hits = top_articles_by_relevance(
            "AI for essential public services and welfare eligibility",
            k=5, min_score=1.0,
        )
        assert "Annex III" in hits, f"Expected Annex III in hits; got {hits}"

    def test_creditworthiness_surfaces_annex_iii(self) -> None:
        """Credit scoring is Annex III(5)(b). The category description
        names 'creditworthiness of natural persons' verbatim."""
        hits = top_articles_by_relevance(
            "evaluating creditworthiness of natural persons",
            k=5, min_score=1.0,
        )
        assert "Annex III" in hits, f"Expected Annex III in hits; got {hits}"


class TestPhaseQueries:
    """Date-shaped queries now anchor on the relevant phase article."""

    def test_entry_into_force_surfaces_art_113(self) -> None:
        """Art. 113 is the rollout article — it carries the
        entry-into-force + applicability-date prose in its KB summary
        AND its date anchors are referenced by every Phase entry's
        ``articles`` tuple. BM25 should rank Art. 113 highly on
        rollout-shaped queries.

        Note: Art. 113 itself isn't a phase.articles[0] key (each Phase
        keys on the first SUBSTANTIVE article it activates — Art. 5 for
        prohibitions, Art. 53 for GPAI, etc.). The Art. 113 hit comes
        from the KB obligation summary, which BM25 ranks above the
        phase docs because the KB summary is shorter and more keyword-
        dense. Both paths converge on the same correct answer."""
        hits = top_articles_by_relevance(
            "When does the AI Act enter into force? What dates are applicable from?",
            k=5, min_score=1.0,
        )
        assert "Art. 113" in hits, f"Expected Art. 113 in hits; got {hits}"

    def test_digital_omnibus_surfaces_phase_anchors(self) -> None:
        """The omnibus phase descriptions name 'Digital Omnibus' verbatim."""
        hits = top_articles_by_relevance(
            "What does the Digital Omnibus defer?",
            k=5, min_score=1.0,
        )
        # Omnibus phases anchor on Art. 5 (9th prohibition) and Art. 6
        # (deferred Annex I high-risk obligations).
        phase_anchors = {"Art. 5", "Art. 6"}
        hit = phase_anchors & set(hits)
        assert hit, (
            f"Expected at least one Omnibus phase anchor; got {hits}"
        )


class TestNoRegressionOnExistingQueries:
    """The canonical pre-extension queries still resolve correctly."""

    def test_log_retention_question_still_finds_art_19(self) -> None:
        """Canonical pin from test_retrieval_upgrades: this is the BM25
        fallback's reason for existing. Must NOT regress."""
        hits = top_articles_by_relevance(
            "How long must logs be kept under the AI Act?",
            k=5, min_score=1.0,
        )
        assert "Art. 19" in hits, f"Expected Art. 19 in hits; got {hits}"

    def test_empty_query_still_returns_empty(self) -> None:
        assert top_articles_by_relevance("") == []

    def test_unknown_article_relevance_is_zero(self) -> None:
        assert relevance_score("any query", "Art. 999") == 0.0

    def test_relevance_score_works_for_ontology_keyed_article(self) -> None:
        """``relevance_score`` should return a positive value for any
        article that has at least one matching ontology doc."""
        # Art. 5 + a query that should hit the subliminal_manipulation
        # Practice description.
        score = relevance_score(
            "subliminal manipulation deceptive techniques", "Art. 5",
        )
        assert score > 0.0, f"Expected positive score, got {score}"


class TestArticleKeyExistenceLint:
    """Every emitted article_key must resolve in ARTICLE_EXISTENCE.

    Mirrors the test_kb_consistency.py guarantees for the KB and
    ontology surfaces — extended to cover the BM25 index's emitted
    keys so an ontology-keying bug can't leak a hallucinated reference
    onto the wire via the BM25 fallback path.
    """

    def test_every_index_article_key_resolves(self) -> None:
        """Walk every doc in the index and confirm its article_key is
        a real EU AI Act reference (or a sub-paragraph thereof)."""
        index = _build_index()
        for ref in index.article_refs:
            assert _is_known_or_prefix_known(ref), (
                f"BM25 index emits article_key {ref!r}; not in "
                f"ARTICLE_EXISTENCE"
            )

    def test_top_articles_emits_only_known_refs(self) -> None:
        """Every output of ``top_articles_by_relevance`` is a real
        article reference. Sample-based — we run a handful of
        representative queries and confirm each ref."""
        queries = [
            "manipulative AI techniques",
            "essential public services",
            "creditworthiness assessment",
            "real-time biometric identification",
            "How long must logs be kept?",
            "When does the AI Act enter into force?",
            "Digital Omnibus deferred obligations",
        ]
        for q in queries:
            hits = top_articles_by_relevance(q, k=5, min_score=0.5)
            for ref in hits:
                assert _is_known_or_prefix_known(ref), (
                    f"Query {q!r} returned hallucinated ref {ref!r}"
                )


# ── PageIndex chapter-scoped BM25 ─────────────────────────────────────────


class TestChapterScopedBM25:
    """Validate ``top_articles_by_relevance_in_chapters`` — the
    PageIndex-style pre-filter that restricts BM25 to a chapter subset.
    """

    def test_chapter_iii_scoped_finds_high_risk_article(self) -> None:
        from app.data.kb_search import top_articles_by_relevance_in_chapters
        hits = top_articles_by_relevance_in_chapters(
            "What are the requirements for high-risk AI systems?",
            ["III"], k=5, min_score=0.5,
        )
        assert hits, "Chapter-III scoped search should return results"
        assert any(h.startswith("Art. ") or h.startswith("Annex") for h in hits)

    def test_chapter_ii_scoped_finds_prohibition_article(self) -> None:
        from app.data.kb_search import top_articles_by_relevance_in_chapters
        hits = top_articles_by_relevance_in_chapters(
            "subliminal manipulation prohibited AI practices",
            ["II"], k=3, min_score=0.5,
        )
        assert "Art. 5" in hits, f"Expected Art. 5 for prohibition query; got {hits}"

    def test_scoped_returns_only_chapter_articles(self) -> None:
        """All returned refs must belong to the requested chapter(s)."""
        from app.data.eu_ai_act_corpus import ARTICLE_CHAPTER
        from app.data.kb_search import top_articles_by_relevance_in_chapters
        hits = top_articles_by_relevance_in_chapters(
            "administrative fines penalties sanctions",
            ["XII"], k=5, min_score=0.5,
        )
        for ref in hits:
            if ref.startswith("Annex"):
                continue  # Annexes allowed as safety-net inclusions
            ch = ARTICLE_CHAPTER.get(ref)
            assert ch == "XII", (
                f"Ref {ref!r} chapter={ch!r} not in requested chapter XII"
            )

    def test_empty_chapters_falls_back_to_full_corpus(self) -> None:
        from app.data.kb_search import top_articles_by_relevance_in_chapters
        hits_scoped = top_articles_by_relevance_in_chapters(
            "How long must records be kept?", [], k=3,
        )
        from app.data.kb_search import top_articles_by_relevance
        hits_full = top_articles_by_relevance(
            "How long must records be kept?", k=3,
        )
        assert hits_scoped == hits_full, (
            "Empty chapters list must fall back to full-corpus results"
        )

    def test_unknown_chapter_falls_back_gracefully(self) -> None:
        """A chapter string not in ARTICLE_CHAPTER (e.g. 'ZZ') should
        not raise; it falls back to full-corpus BM25."""
        from app.data.kb_search import top_articles_by_relevance_in_chapters
        hits = top_articles_by_relevance_in_chapters(
            "entry into force timeline", ["ZZ"], k=3,
        )
        assert isinstance(hits, list)

    def test_emitted_refs_resolve_in_article_existence(self) -> None:
        from app.data.article_existence import ARTICLE_EXISTENCE
        from app.data.kb_search import top_articles_by_relevance_in_chapters
        queries = [
            ("high-risk AI documentation requirements", ["III"]),
            ("GPAI systemic risk obligations", ["V"]),
            ("post-market incident reporting", ["IX"]),
        ]
        for q, chapters in queries:
            hits = top_articles_by_relevance_in_chapters(q, chapters, k=5, min_score=0.5)
            for ref in hits:
                assert _is_known_or_prefix_known(ref), (
                    f"Scoped search returned hallucinated ref {ref!r}"
                )

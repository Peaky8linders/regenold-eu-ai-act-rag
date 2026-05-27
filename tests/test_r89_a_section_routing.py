from __future__ import annotations


def test_chapter_iii_articles_have_section_ids() -> None:
    from app.data.article_sections import ARTICLE_SECTION

    expected = {
        "Art. 6": "III.1",
        "Art. 7": "III.1",
        "Art. 8": "III.2",
        "Art. 15": "III.2",
        "Art. 16": "III.3",
        "Art. 27": "III.3",
        "Art. 28": "III.4",
        "Art. 39": "III.4",
        "Art. 40": "III.5",
        "Art. 49": "III.5",
    }
    for ref, section in expected.items():
        assert ARTICLE_SECTION[ref] == section


def test_chapter_v_articles_have_section_ids() -> None:
    from app.data.article_sections import ARTICLE_SECTION

    expected = {
        "Art. 51": "V.1",
        "Art. 52": "V.2",
        "Art. 53": "V.1",
        "Art. 54": "V.1",
        "Art. 55": "V.2",
        "Art. 56": "V.3",
    }
    for ref, section in expected.items():
        assert ARTICLE_SECTION[ref] == section


def test_candidate_sections_routes_high_risk_requirements() -> None:
    from app.data.chapter_summaries import candidate_sections_for_query

    sections = candidate_sections_for_query(
        "Which requirements apply to high-risk AI risk management and data governance?",
        chapters=["III"],
    )
    assert sections == ["III.2"]


def test_candidate_sections_routes_chapter_iii_operator_duties() -> None:
    from app.data.chapter_summaries import candidate_sections_for_query

    sections = candidate_sections_for_query(
        "What obligations do importers and deployers of high-risk AI systems have?",
        chapters=["III"],
    )
    assert sections == ["III.3"]


def test_candidate_sections_routes_gpai_systemic_and_codes() -> None:
    from app.data.chapter_summaries import candidate_sections_for_query

    systemic = candidate_sections_for_query(
        "What additional duties apply to GPAI models with systemic risk?",
        chapters=["V"],
    )
    codes = candidate_sections_for_query(
        "How do codes of practice work for GPAI providers?",
        chapters=["V"],
    )
    assert systemic == ["V.2"]
    assert codes == ["V.3"]


def test_section_scoped_bm25_only_returns_requested_section_refs() -> None:
    from app.data.article_sections import ARTICLE_SECTION
    from app.data.kb_search import top_articles_by_relevance_in_sections

    hits = top_articles_by_relevance_in_sections(
        "risk management data governance human oversight accuracy robustness",
        ["III.2"],
        k=5,
        min_score=0.5,
    )
    assert hits
    for ref in hits:
        if ref.startswith("Annex"):
            continue
        assert ARTICLE_SECTION[ref] == "III.2"


def test_section_scoped_bm25_empty_sections_falls_back_to_full_corpus() -> None:
    from app.data.kb_search import (
        top_articles_by_relevance,
        top_articles_by_relevance_in_sections,
    )

    question = "How long must records be kept?"
    assert top_articles_by_relevance_in_sections(question, [], k=3, min_score=1.0) == (
        top_articles_by_relevance(question, k=3, min_score=1.0)
    )


def test_deterministic_parse_uses_section_before_chapter(monkeypatch) -> None:
    from app.engines import graph_rag

    monkeypatch.setenv("REGENOLD_SECTION_SCOPED_BM25", "1")
    monkeypatch.setattr(
        graph_rag,
        "candidate_chapters_for_query",
        lambda question, intent_label=None: ["III"],
    )
    monkeypatch.setattr(
        graph_rag,
        "candidate_sections_for_query",
        lambda question, chapters, intent_label=None: ["III.2"],
    )
    monkeypatch.setattr(
        graph_rag,
        "top_articles_by_relevance_in_sections",
        lambda question, sections, k=5, min_score=1.0: ["Art. 9"],
    )
    monkeypatch.setattr(
        graph_rag,
        "top_articles_by_relevance_in_chapters",
        lambda question, chapters, k=5, min_score=1.0: ["Art. 6"],
    )

    query = graph_rag._deterministic_parse("r89 synthetic unanchored section probe")

    assert query.entities == ["Art. 9"]


def test_deterministic_parse_falls_back_to_chapter_when_section_empty(monkeypatch) -> None:
    from app.engines import graph_rag

    monkeypatch.setenv("REGENOLD_SECTION_SCOPED_BM25", "1")
    monkeypatch.setattr(
        graph_rag,
        "candidate_chapters_for_query",
        lambda question, intent_label=None: ["III"],
    )
    monkeypatch.setattr(
        graph_rag,
        "candidate_sections_for_query",
        lambda question, chapters, intent_label=None: ["III.2"],
    )
    monkeypatch.setattr(
        graph_rag,
        "top_articles_by_relevance_in_sections",
        lambda question, sections, k=5, min_score=1.0: [],
    )
    monkeypatch.setattr(
        graph_rag,
        "top_articles_by_relevance_in_chapters",
        lambda question, chapters, k=5, min_score=1.0: ["Art. 6"],
    )

    query = graph_rag._deterministic_parse("r89 synthetic unanchored fallback probe")

    assert query.entities == ["Art. 6"]

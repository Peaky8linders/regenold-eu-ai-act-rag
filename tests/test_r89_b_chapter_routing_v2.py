from __future__ import annotations


def test_chapter_routing_v2_risk_classification_uses_two_chapter_prior(
    monkeypatch,
) -> None:
    from app.data.chapter_summaries import candidate_chapters_for_query

    monkeypatch.setenv("REGENOLD_CHAPTER_ROUTING_V2", "1")

    chapters = candidate_chapters_for_query(
        "Could this be prohibited or high-risk?",
        intent_label="risk_classification",
    )

    assert chapters == ["II", "III"]


def test_chapter_routing_v2_accepts_definitional_label(monkeypatch) -> None:
    from app.data.chapter_summaries import candidate_chapters_for_query

    monkeypatch.setenv("REGENOLD_CHAPTER_ROUTING_V2", "1")

    chapters = candidate_chapters_for_query(
        "What does AI system mean?",
        intent_label="definitional",
    )

    assert chapters == ["I"]


def test_chapter_routing_v2_transparency_label_routes_to_chapter_iv(
    monkeypatch,
) -> None:
    from app.data.chapter_summaries import candidate_chapters_for_query

    monkeypatch.setenv("REGENOLD_CHAPTER_ROUTING_V2", "1")

    chapters = candidate_chapters_for_query(
        "What transparency notice is required?",
        intent_label="transparency",
    )

    assert chapters == ["IV"]


def test_chapter_routing_v2_gpai_systemic_routes_to_chapter_v(monkeypatch) -> None:
    from app.data.chapter_summaries import candidate_chapters_for_query

    monkeypatch.setenv("REGENOLD_CHAPTER_ROUTING_V2", "1")

    chapters = candidate_chapters_for_query(
        "What if the model exceeds the systemic-risk compute threshold?",
        intent_label="gpai_systemic",
    )

    assert chapters == ["V"]


def test_chapter_routing_v2_keeps_cross_framework_unscoped(monkeypatch) -> None:
    from app.data.chapter_summaries import candidate_chapters_for_query

    monkeypatch.setenv("REGENOLD_CHAPTER_ROUTING_V2", "1")

    chapters = candidate_chapters_for_query(
        "How does the AI Act interact with GDPR and NIS2?",
        intent_label="cross_framework",
    )

    assert chapters == []


def test_chapter_routing_v2_default_off_preserves_single_chapter_prior(
    monkeypatch,
) -> None:
    from app.data.chapter_summaries import candidate_chapters_for_query

    monkeypatch.delenv("REGENOLD_CHAPTER_ROUTING_V2", raising=False)

    chapters = candidate_chapters_for_query(
        "Assess the deployment context.",
        intent_label="risk_classification",
    )

    assert chapters == ["III"]

"""Tests for the CLARA Paradigm logic engine.

Pins three invariants the architecture-PDF spec requires:

1.  ``compute_verdict`` is a pure function — deterministic, no I/O,
    never raises on any BooleanTags input.
2.  Every prohibited practice in :data:`PRACTICE_REGISTRY` is reachable
    by the deterministic extractor + matrix.
3.  The LLM extractor is a no-op when the wrapper is disabled or
    misbehaves (production safety contract — the engine must always
    fall back to the deterministic path).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.data.ontology import PRACTICE_REGISTRY
from app.engines import clara_logic
from app.engines.clara_logic import (
    BooleanTags,
    Verdict,
    analyse,
    compute_verdict,
    extract_tags_deterministic,
    extract_tags_llm,
)
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Wipe LRU cache + breaker between tests."""
    clara_logic._reset_for_tests()
    yield
    clara_logic._reset_for_tests()


# ── Section 1: matrix purity + determinism ───────────────────────────────


def test_compute_verdict_returns_verdict_instance() -> None:
    v = compute_verdict(BooleanTags())
    assert isinstance(v, Verdict)


def test_compute_verdict_is_deterministic_across_100_calls() -> None:
    """Same input → same output, always. Pins purity."""
    tags = BooleanTags(
        is_emotion_recognition=True,
        used_in_workplace=True,
    )
    first = compute_verdict(tags)
    for _ in range(100):
        again = compute_verdict(tags)
        assert again == first


def test_compute_verdict_never_raises_on_empty_tags() -> None:
    v = compute_verdict(BooleanTags())
    assert v.risk_tier == "minimal"
    assert v.primary_articles == ("Article 4",)


def test_compute_verdict_never_raises_on_garbage_input() -> None:
    """The matrix MUST tolerate non-BooleanTags input without raising."""
    v = compute_verdict({"is_social_scoring": True})  # type: ignore[arg-type]
    assert v.risk_tier == "uncertain"
    assert v.confidence == 0.0


def test_compute_verdict_never_raises_on_all_flags_true() -> None:
    """Lighting up every flag must return SOME verdict (prohibited wins)."""
    # Reach across every field whose default is a bool and flip it.
    # NOTE: under ``from __future__ import annotations`` the dataclass
    # field's ``type`` is the SOURCE string, not the resolved type — so
    # we detect "is this a bool flag" via the field default instead.
    kwargs = {
        f.name: True
        for f in BooleanTags.__dataclass_fields__.values()  # type: ignore[attr-defined]
        if f.name != "extra" and isinstance(f.default, bool)
    }
    tags = BooleanTags(**kwargs)
    v = compute_verdict(tags)
    # First-match-wins priority: social_scoring fires before everything else.
    assert v.risk_tier == "prohibited"


# ── Section 2: each prohibited practice maps to the right Art. 5 sub-cite ────


def test_social_scoring_is_prohibited_art_5_1_c() -> None:
    v = compute_verdict(BooleanTags(is_social_scoring=True))
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.c",)
    assert v.confidence == 1.0


def test_subliminal_is_prohibited_art_5_1_a() -> None:
    v = compute_verdict(BooleanTags(is_subliminal_or_manipulative=True))
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.a",)


def test_vulnerability_exploitation_is_prohibited_art_5_1_b() -> None:
    v = compute_verdict(BooleanTags(exploits_vulnerability=True))
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.b",)


def test_predictive_policing_is_prohibited_art_5_1_d() -> None:
    v = compute_verdict(BooleanTags(is_predictive_policing=True))
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.d",)


def test_biometric_categorisation_sensitive_is_prohibited_art_5_1_g() -> None:
    v = compute_verdict(BooleanTags(is_biometric_categorisation_sensitive=True))
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.g",)


def test_real_time_biometric_for_law_enforcement_is_prohibited_art_5_1_h() -> None:
    v = compute_verdict(
        BooleanTags(
            is_real_time_biometric=True,
            used_by_law_enforcement=True,
        )
    )
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.h",)


def test_real_time_biometric_without_law_enforcement_is_not_prohibited() -> None:
    """RBI is only prohibited when used by law enforcement (Art. 5(1)(h))."""
    v = compute_verdict(BooleanTags(is_real_time_biometric=True))
    assert v.risk_tier != "prohibited"


def test_emotion_recognition_in_workplace_is_prohibited_art_5_1_f() -> None:
    v = compute_verdict(
        BooleanTags(
            is_emotion_recognition=True,
            used_in_workplace=True,
        )
    )
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.f",)


def test_emotion_recognition_in_education_is_prohibited_art_5_1_f() -> None:
    v = compute_verdict(
        BooleanTags(
            is_emotion_recognition=True,
            used_in_education=True,
        )
    )
    assert v.risk_tier == "prohibited"
    assert v.primary_articles == ("Article 5.1.f",)


def test_emotion_recognition_in_medical_devices_is_high_risk_not_prohibited() -> None:
    """Medical-device carve-out: emotion recognition in healthcare is high-risk."""
    v = compute_verdict(
        BooleanTags(
            is_emotion_recognition=True,
            used_in_medical_devices=True,
            # Even when a "workplace" signal would otherwise fire, the
            # medical-device carve-out re-routes to high-risk.
            used_in_workplace=True,
        )
    )
    assert v.risk_tier == "high_risk"
    assert "Article 6" in v.primary_articles


def test_emotion_recognition_outside_workplace_is_high_risk() -> None:
    """General emotion recognition (e.g. customer-service) → Annex III(1)(c)."""
    v = compute_verdict(BooleanTags(is_emotion_recognition=True))
    assert v.risk_tier == "high_risk"
    assert "Article 6" in v.primary_articles
    assert "Annex III" in v.supporting_articles


# ── Section 3: high-risk Annex III categories ────────────────────────────


def test_recruitment_is_high_risk_annex_iii() -> None:
    v = compute_verdict(BooleanTags(used_in_recruitment=True))
    assert v.risk_tier == "high_risk"
    assert "Annex III" in v.supporting_articles


def test_critical_infrastructure_is_high_risk() -> None:
    v = compute_verdict(BooleanTags(used_in_critical_infrastructure=True))
    assert v.risk_tier == "high_risk"


def test_credit_scoring_essential_services_is_high_risk() -> None:
    v = compute_verdict(BooleanTags(used_in_essential_services_access=True))
    assert v.risk_tier == "high_risk"


def test_migration_asylum_is_high_risk() -> None:
    v = compute_verdict(BooleanTags(used_in_migration_asylum=True))
    assert v.risk_tier == "high_risk"


def test_administration_of_justice_is_high_risk() -> None:
    v = compute_verdict(BooleanTags(used_in_judicial_law=True))
    assert v.risk_tier == "high_risk"


def test_medical_device_alone_is_high_risk() -> None:
    """AI that classifies medical images is high-risk (Annex I + Annex III)."""
    v = compute_verdict(BooleanTags(used_in_medical_devices=True))
    assert v.risk_tier == "high_risk"


def test_annex_i_embedded_product_is_high_risk_with_art_43() -> None:
    v = compute_verdict(BooleanTags(is_embedded_product_annex_i=True))
    assert v.risk_tier == "high_risk"
    # Annex I path requires the third-party conformity-assessment article.
    assert "Article 43" in v.supporting_articles


# ── Section 4: GPAI tiers ────────────────────────────────────────────────


def test_gpai_without_systemic_threshold_is_gpai_tier() -> None:
    v = compute_verdict(BooleanTags(is_gpai_model=True))
    assert v.risk_tier == "gpai"
    assert v.primary_articles == ("Article 51",)
    assert "Article 53" in v.supporting_articles


def test_gpai_with_systemic_threshold_is_gpai_systemic() -> None:
    v = compute_verdict(
        BooleanTags(
            is_gpai_model=True,
            gpai_compute_above_systemic_threshold=True,
        )
    )
    assert v.risk_tier == "gpai_systemic"
    assert "Article 55" in v.supporting_articles


# ── Section 5: limited & minimal default ─────────────────────────────────


def test_chatbot_is_limited_risk_art_50() -> None:
    v = compute_verdict(BooleanTags(is_chatbot_interaction=True))
    assert v.risk_tier == "limited"
    assert v.primary_articles == ("Article 50",)


def test_deepfake_is_limited_risk_art_50() -> None:
    v = compute_verdict(BooleanTags(is_deepfake=True))
    assert v.risk_tier == "limited"


def test_biometric_data_without_real_time_is_limited_risk() -> None:
    """Mere biometric data (no real-time, no law-enforcement) → Art. 50."""
    v = compute_verdict(BooleanTags(is_biometric_data=True))
    assert v.risk_tier == "limited"


def test_empty_tags_is_minimal_risk_art_4() -> None:
    v = compute_verdict(BooleanTags())
    assert v.risk_tier == "minimal"
    assert v.primary_articles == ("Article 4",)
    assert v.confidence == pytest.approx(0.4)


def test_recommender_system_minimal_via_extractor() -> None:
    """A recommender system → no risk flags → minimal."""
    tags = extract_tags_deterministic("Our system recommends songs to users.")
    v = compute_verdict(tags)
    assert v.risk_tier == "minimal"


# ── Section 6: priority / conflict resolution ────────────────────────────


def test_prohibited_beats_high_risk() -> None:
    """Social-scoring + recruitment context still resolves to prohibited."""
    v = compute_verdict(
        BooleanTags(
            is_social_scoring=True,
            used_in_recruitment=True,
        )
    )
    assert v.risk_tier == "prohibited"


def test_high_risk_beats_gpai() -> None:
    """A GPAI integrated into a medical device is HIGH-RISK at the system layer."""
    v = compute_verdict(
        BooleanTags(
            is_gpai_model=True,
            used_in_medical_devices=True,
        )
    )
    assert v.risk_tier == "high_risk"


def test_gpai_systemic_beats_gpai() -> None:
    v = compute_verdict(
        BooleanTags(
            is_gpai_model=True,
            gpai_compute_above_systemic_threshold=True,
        )
    )
    assert v.risk_tier == "gpai_systemic"


def test_prohibited_beats_gpai() -> None:
    """An LLM that does social scoring is prohibited, not GPAI."""
    v = compute_verdict(
        BooleanTags(
            is_gpai_model=True,
            is_social_scoring=True,
        )
    )
    assert v.risk_tier == "prohibited"


# ── Section 7: deterministic extractor catches each ontology practice ────


# This is the canary that the extractor stays in sync with the
# ontology truth source. Each Art. 5 practice MUST be reachable by
# the deterministic extractor for at least one of its keywords.

_PRACTICE_TO_FLAG: dict[str, str] = {
    "subliminal_manipulation": "is_subliminal_or_manipulative",
    "vulnerability_exploitation": "exploits_vulnerability",
    "social_scoring": "is_social_scoring",
    "profiling_for_criminal_risk": "is_predictive_policing",
    # facial_recognition_database scraping mirrors into is_biometric_data
    # since the practice IS a biometric-data operation under Art. 3(34).
    "facial_recognition_database": "is_biometric_data",
    "emotion_recognition_workplace": "is_emotion_recognition",
    "biometric_categorisation_sensitive": "is_biometric_categorisation_sensitive",
    "real_time_rbi": "is_real_time_biometric",
    "omnibus_csam_ncii": None,  # outside the matrix scope (Omnibus pending)
}


def test_each_practice_keyword_anchors_the_expected_flag() -> None:
    """Every Art. 5 practice in PRACTICE_REGISTRY must be reachable."""
    for practice_id, flag_name in _PRACTICE_TO_FLAG.items():
        if flag_name is None:
            continue
        practice = PRACTICE_REGISTRY[practice_id]
        # Take the FIRST keyword as the canonical reference phrasing.
        keyword = practice.keywords[0]
        question = f"A system that performs {keyword}."
        tags = extract_tags_deterministic(question)
        actual = getattr(tags, flag_name)
        assert actual, (
            f"Practice {practice_id!r} (keyword {keyword!r}) did not "
            f"set flag {flag_name!r} via the deterministic extractor."
        )


# ── Section 8: deterministic extractor — natural-language probes ─────────


def test_extractor_finds_real_time_biometric_phrase() -> None:
    tags = extract_tags_deterministic(
        "Are real-time remote biometric identification systems prohibited?"
    )
    assert tags.is_real_time_biometric


def test_extractor_finds_emotion_recognition_phrase() -> None:
    tags = extract_tags_deterministic(
        "We use emotion recognition to monitor employees in the workplace."
    )
    assert tags.is_emotion_recognition
    assert tags.used_in_workplace


def test_extractor_finds_medical_device_phrase() -> None:
    tags = extract_tags_deterministic(
        "Our AI is integrated into a medical device for radiology."
    )
    assert tags.used_in_medical_devices


def test_extractor_finds_gpai_phrase() -> None:
    tags = extract_tags_deterministic(
        "We train a general-purpose AI model on a public corpus."
    )
    assert tags.is_gpai_model


def test_extractor_finds_gpai_systemic_threshold_10_26_flops() -> None:
    tags = extract_tags_deterministic(
        "Our general-purpose AI was trained with 10^26 FLOPs of compute."
    )
    assert tags.is_gpai_model
    assert tags.gpai_compute_above_systemic_threshold


def test_extractor_finds_role_provider() -> None:
    tags = extract_tags_deterministic("We are a provider of an AI system.")
    assert tags.is_provider


def test_extractor_uses_history_context() -> None:
    """Role mentioned in history but not in live question should still fire."""
    tags = extract_tags_deterministic(
        question="Should we run a FRIA?",
        history=[
            {"role": "user", "content": "We are a deployer of an HR scoring tool."},
        ],
    )
    assert tags.is_deployer


def test_extractor_returns_empty_tags_on_empty_question() -> None:
    tags = extract_tags_deterministic("")
    assert tags == BooleanTags()


# ── Section 9: end-to-end analyse() pipeline ─────────────────────────────


def test_analyse_emotion_recognition_in_workplace_is_prohibited() -> None:
    tags, verdict = analyse(
        "We use emotion recognition AI in the workplace to monitor staff."
    )
    assert tags.is_emotion_recognition
    assert tags.used_in_workplace
    assert verdict.risk_tier == "prohibited"
    assert verdict.primary_articles == ("Article 5.1.f",)


def test_analyse_recruitment_is_high_risk() -> None:
    tags, verdict = analyse(
        "Our AI screens CVs for recruitment in a large company."
    )
    assert tags.used_in_recruitment
    assert verdict.risk_tier == "high_risk"


def test_analyse_chatbot_is_limited() -> None:
    tags, verdict = analyse("We deploy a chatbot for customer service.")
    assert tags.is_chatbot_interaction
    assert verdict.risk_tier == "limited"
    assert verdict.primary_articles == ("Article 50",)


def test_analyse_recommender_is_minimal() -> None:
    tags, verdict = analyse("We have an AI that recommends songs to users.")
    # No risk flags should fire.
    assert verdict.risk_tier == "minimal"


def test_analyse_gpai_with_10_26_flops_is_systemic() -> None:
    tags, verdict = analyse(
        "Our general-purpose AI was trained with 10^26 FLOPs of compute."
    )
    assert tags.is_gpai_model
    assert tags.gpai_compute_above_systemic_threshold
    assert verdict.risk_tier == "gpai_systemic"


def test_analyse_medical_image_classification_is_high_risk() -> None:
    tags, verdict = analyse("An AI that classifies medical images for diagnosis.")
    assert tags.used_in_medical_devices
    assert verdict.risk_tier == "high_risk"


# ── Section 10: LLM extractor — disabled / failure paths ─────────────────


def test_extract_tags_llm_returns_none_when_wrapper_disabled(monkeypatch) -> None:
    """No ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` → instant None."""
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert extract_tags_llm("What is biometric identification?") is None


def test_extract_tags_llm_returns_none_on_empty_question() -> None:
    assert extract_tags_llm("") is None


def test_extract_tags_llm_returns_none_on_wrapper_error(monkeypatch) -> None:
    """Wrapper error → None (engine falls back to deterministic)."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                error="network_error: connection refused",
                model="claude-haiku-4-5",
                elapsed_ms=42,
            )

    import app.llm.openai_wrapper_provider as ow
    with patch.object(ow, "get_openai_wrapper_provider", return_value=FakeProvider()):
        assert extract_tags_llm("What's an AI provider?") is None


def test_extract_tags_llm_returns_none_on_malformed_json(monkeypatch) -> None:
    """Garbage from the LLM → None, not a raise."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text="here is your answer: NOT JSON at all",
                model="claude-haiku-4-5",
                elapsed_ms=50,
            )

    import app.llm.openai_wrapper_provider as ow
    with patch.object(ow, "get_openai_wrapper_provider", return_value=FakeProvider()):
        assert extract_tags_llm("Test question?") is None


def test_extract_tags_llm_drops_unknown_keys(monkeypatch) -> None:
    """LLM returns extra keys — they must be dropped, not raise."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text=(
                    '{"is_social_scoring": true, '
                    '"some_fake_key": true, '
                    '"verdict": "prohibited", '
                    '"primary_articles": ["Article 5"]}'
                ),
                model="claude-haiku-4-5",
                elapsed_ms=50,
            )

    import app.llm.openai_wrapper_provider as ow
    with patch.object(ow, "get_openai_wrapper_provider", return_value=FakeProvider()):
        tags = extract_tags_llm("Is social scoring prohibited?")
    assert tags is not None
    assert tags.is_social_scoring is True
    # Unknown fields must NOT appear on the dataclass.
    assert not hasattr(tags, "some_fake_key")
    assert not hasattr(tags, "verdict")


def test_extract_tags_llm_parses_valid_json(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text='{"is_emotion_recognition": true, "used_in_workplace": true}',
                model="claude-haiku-4-5",
                elapsed_ms=50,
            )

    import app.llm.openai_wrapper_provider as ow
    with patch.object(ow, "get_openai_wrapper_provider", return_value=FakeProvider()):
        tags = extract_tags_llm("Workplace emotion AI?")
    assert tags is not None
    assert tags.is_emotion_recognition
    assert tags.used_in_workplace


def test_extract_tags_llm_lru_cache_avoids_second_call(monkeypatch) -> None:
    """Same question → cached result (no second provider invocation)."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    call_count = {"n": 0}

    class FakeProvider:
        def complete(self, _req):
            call_count["n"] += 1
            return OpenAIWrapperResponse(
                text='{"is_social_scoring": true}',
                model="claude-haiku-4-5",
                elapsed_ms=50,
            )

    import app.llm.openai_wrapper_provider as ow
    with patch.object(ow, "get_openai_wrapper_provider", return_value=FakeProvider()):
        a = extract_tags_llm("Is social scoring prohibited?")
        b = extract_tags_llm("Is social scoring prohibited?")
    assert a == b
    assert call_count["n"] == 1


def test_extract_tags_llm_circuit_breaker_opens_after_threshold(monkeypatch) -> None:
    """3 consecutive failures → breaker open → subsequent calls return None fast."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    call_count = {"n": 0}

    class FakeProvider:
        def complete(self, _req):
            call_count["n"] += 1
            return OpenAIWrapperResponse(
                error="network_error: connection refused",
                model="claude-haiku-4-5",
                elapsed_ms=42,
            )

    import app.llm.openai_wrapper_provider as ow
    with patch.object(ow, "get_openai_wrapper_provider", return_value=FakeProvider()):
        # 3 distinct questions to bypass the LRU cache.
        for i in range(3):
            assert extract_tags_llm(f"unique question {i}?") is None
        # After 3 failures the breaker is open; this call MUST NOT
        # invoke the provider (call count stays at 3).
        baseline = call_count["n"]
        assert extract_tags_llm("a 4th distinct question?") is None
        assert call_count["n"] == baseline


# ── Section 11: analyse() falls back when LLM fails ──────────────────────


def test_analyse_falls_back_to_deterministic_when_llm_returns_none() -> None:
    """LLM disabled → deterministic path lands a verdict."""
    # Wrapper unset → extract_tags_llm returns None → deterministic kicks in.
    tags, verdict = analyse(
        "We use emotion recognition AI in the workplace to monitor staff."
    )
    assert verdict.risk_tier == "prohibited"
    assert verdict.primary_articles == ("Article 5.1.f",)


# ── Section 12: rationale + supporting articles surfaced ─────────────────


def test_prohibited_verdict_includes_rationale() -> None:
    v = compute_verdict(BooleanTags(is_social_scoring=True))
    assert v.rationale
    assert any("Article 5(1)(c)" in r for r in v.rationale)


def test_high_risk_verdict_includes_section_2_obligations() -> None:
    """High-risk verdict should cite Section 2 obligations Arts. 9-15."""
    v = compute_verdict(BooleanTags(used_in_recruitment=True))
    sup = set(v.supporting_articles)
    # Core Chapter III Section 2 spine.
    assert "Article 9" in sup
    assert "Article 10" in sup
    assert "Article 13" in sup
    assert "Article 14" in sup
    assert "Article 15" in sup


def test_gpai_systemic_verdict_cites_art_55() -> None:
    v = compute_verdict(
        BooleanTags(
            is_gpai_model=True,
            gpai_compute_above_systemic_threshold=True,
        )
    )
    assert "Article 55" in v.supporting_articles

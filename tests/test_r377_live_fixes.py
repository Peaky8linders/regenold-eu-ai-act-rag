"""R377 — regression pins for live run defects.

R377-A — ``_looks_structurally_truncated`` and the XML answer channel.
R377-B — ``guard_cross_tier_polish`` and a DENIED tier counted as an ASSERTED one.
"""

from __future__ import annotations

import pytest

from app.engines._graph_rag_impl import _looks_structurally_truncated
from app.engines.stage2_fidelity import (
    extract_asserted_tier_set,
    extract_tier_set,
    guard_cross_tier_polish,
)

# ─── R377-A ──────────────────────────────────────────────────────────────────

#: The exact Sonnet 5 tail measured live on the emotion-recognition pushback
#: turn, which was discarded as truncated.
_LIVE_XML_ANSWER = (
    "No. Article 5(1)(f) prohibits the use of AI systems to infer emotions of a "
    "natural person in the areas of workplace and education institutions. "
    "Consent of the employees is not a condition of that prohibition and cannot "
    "make the practice lawful.\n</answer>"
)


class TestR377AXmlChannelIsNotTruncation:
    """A closing XML channel tag WRAPS the answer; it does not cut it."""

    def test_live_xml_wrapped_answer_is_not_truncated(self) -> None:
        assert _looks_structurally_truncated(_LIVE_XML_ANSWER) is False

    def test_nested_closing_channels_are_peeled(self) -> None:
        text = "The system is prohibited under Article 5(1)(f).</answer>\n</reasoning_scratchpad>"
        assert _looks_structurally_truncated(text) is False

    @pytest.mark.parametrize(
        "text",
        [
            "The provider must",
            "the deployer shall, in accordance with",
            "under Article 26(1),",
        ],
    )
    def test_genuine_truncation_still_detected(self, text: str) -> None:
        assert _looks_structurally_truncated(text) is True

    def test_bare_angle_bracket_is_not_peeled(self) -> None:
        """Only a WELL-FORMED closing tag is a wrapper. A dangling ``>`` is a cut."""
        assert _looks_structurally_truncated("training compute greater than 10^25 >") is True

    def test_tag_without_terminator_inside_is_still_truncated(self) -> None:
        """Peeling the tag must expose the REAL final character, not excuse it."""
        assert _looks_structurally_truncated("remains prohibited</answer>") is True

    def test_r328_3_markdown_peel_preserved(self) -> None:
        assert _looks_structurally_truncated("*Sources: see Recitals 46-59.*") is False
        assert _looks_structurally_truncated("| Article 9 | risk management |") is False

    def test_r357_ellipsis_cut_preserved(self) -> None:
        assert _looks_structurally_truncated("The provider must…") is True

    def test_markdown_table_wrapped_in_xml_channel_is_not_truncated(self) -> None:
        table_in_xml = (
            "<answer>\n"
            "| Tier | Provision | Obligation |\n"
            "|---|---|---|\n"
            "| High-risk | Article 6 | Quality management |\n"
            "</answer>"
        )
        assert _looks_structurally_truncated(table_in_xml) is False



# ─── R377-B ──────────────────────────────────────────────────────────────────

#: The deterministic draft measured live on the CV-screening + GPAI question.
#: It asserts ONE tier (limited) and DENIES another (high-risk) — but the denial
#: carries an ``Article 6`` anchor, so the anchor-only probe read two tiers.
_LIVE_DETERMINISTIC_DRAFT = (
    "This system is classified as limited-risk under the Article 50 transparency "
    "obligations. The provider must provide AI literacy training to all staff "
    "involved in development, deployment and operation of the system, and document "
    "a classification assessment confirming the system is not high-risk under "
    "Article 6 (Article 4). A clear notice must be displayed to users at the first "
    "interaction informing them they are interacting with an AI system, and "
    "AI-generated content must be clearly labelled as such (Article 50)."
)

#: The CORRECT Opus 5 polish that the guard discarded.
_LIVE_POLISH = (
    "A CV-screening and applicant-ranking system placed on the market for employers "
    "is high-risk, because recruitment and selection of natural persons is an Annex "
    "III use case that Article 6(2) classifies as high-risk. The company is the "
    "provider under Article 25(1)(c)."
)

_CLASSIFICATION_Q = (
    "Our company is building an AI system that screens CVs and ranks job applicants. "
    "What risk class applies, which role are we in, what conformity assessment route, "
    "and what documentation must we hold?"
)

#: The R146 fixture: a QUALIFIED denial that still asserts the tier elsewhere.
_CROSS_TIER_DRAFT = (
    "The system is not categorically prohibited under Article 5. "
    "In workplaces or education it is banned, but elsewhere it is high-risk "
    "under Annex III and Article 6. It also triggers Article 50 transparency "
    "duties toward exposed persons."
)


class TestR377BDeniedTierIsNotAssertedTier:
    """R379 - the lever now ships DEFAULT OFF (see tier_negation_enabled).
    These cases pin the ON behaviour, which is unchanged, so they opt in.
    The two env-gate tests below set the flag themselves and win over this.
    """

    @pytest.fixture(autouse=True)
    def _opt_in(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_FIDELITY_TIER_NEGATION", "1")
        yield

    def test_denied_tier_excluded_from_contract(self) -> None:
        assert extract_asserted_tier_set(_LIVE_DETERMINISTIC_DRAFT) == {"limited"}

    def test_anchor_probe_is_left_byte_identical(self) -> None:
        """The POLISH side must keep asking "is this tier ADDRESSED"."""
        assert extract_tier_set(_LIVE_DETERMINISTIC_DRAFT) == {"limited", "high_risk"}

    def test_qualified_denial_still_asserts_the_tier(self) -> None:
        """R146's own fixture: denied in one sentence, asserted in the next."""
        assert extract_asserted_tier_set(_CROSS_TIER_DRAFT) == {
            "prohibited",
            "high_risk",
            "limited",
        }

    def test_negation_elsewhere_is_not_a_tier_denial(self) -> None:
        """"does not remove this classification" must not suppress high-risk."""
        text = (
            "The Article 6(3) derogation does not remove this classification, because "
            "ranking candidates materially influences the outcome of the decision."
        )
        assert extract_asserted_tier_set(text) == {"high_risk"}

    def test_single_asserted_tier_lets_the_polish_ship(self) -> None:
        out, action = guard_cross_tier_polish(
            _LIVE_DETERMINISTIC_DRAFT, _LIVE_POLISH, _CLASSIFICATION_Q
        )
        assert action == "not_cross_tier"
        assert out == _LIVE_POLISH

    def test_env_gate_restores_the_pre_r377_reading(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_FIDELITY_TIER_NEGATION", "0")
        assert extract_asserted_tier_set(_LIVE_DETERMINISTIC_DRAFT) == {
            "limited",
            "high_risk",
        }

    def test_gate_is_read_fresh_per_call(self, monkeypatch) -> None:
        """R334 drift guard — a flag read at import is worse than an unkeyed one."""
        monkeypatch.setenv("REGENOLD_FIDELITY_TIER_NEGATION", "0")
        legacy = extract_asserted_tier_set(_LIVE_DETERMINISTIC_DRAFT)
        monkeypatch.setenv("REGENOLD_FIDELITY_TIER_NEGATION", "1")
        fixed = extract_asserted_tier_set(_LIVE_DETERMINISTIC_DRAFT)
        assert legacy != fixed

    def test_compound_sentence_denies_one_tier_asserts_another(self) -> None:
        """A compound sentence with 'not prohibited, but high-risk' must NOT negate high-risk."""
        text = "The system is not prohibited under Article 5, but is high-risk under Article 6."
        assert extract_asserted_tier_set(text) == {"high_risk"}


# ─── R377-D ──────────────────────────────────────────────────────────────────


class TestR377DWorkplaceEmotionRecognition:
    """A call centre is a workplace, so Article 5(1)(f) bites."""

    def _match(self, question: str) -> str | None:
        from app.engines._graph_rag_data import _CLASSIFICATION_TOPICS

        for entry in _CLASSIFICATION_TOPICS:
            if "emotion" not in entry.get("name", ""):
                continue
            if any(p.search(question) for p in entry["patterns"]):
                return entry["name"]
        return None

    @pytest.mark.parametrize(
        "question",
        [
            "We deploy an emotion recognition system in our call centre to monitor agent stress.",
            "We monitor the stress of our call-centre agents with an emotion recognition AI.",
            "Can we use emotion recognition on our employees in the office?",
            "Emotion recognition used on our staff during shifts",
            "Emotion detection applied to our workforce",
            "Emotion recognition on personnel in the plant",
        ],
    )
    def test_workplace_shapes_reach_the_prohibition_entry(self, question: str) -> None:
        assert self._match(question) == "emotion_recognition_workplace"

    @pytest.mark.parametrize(
        "question",
        [
            "Emotion recognition in our retail stores to measure customer satisfaction",
            "Emotion detection on viewers of our advertising",
            "Emotion recognition for driver drowsiness in consumer cars",
        ],
    )
    def test_non_workplace_shapes_stay_general(self, question: str) -> None:
        """The widening must not sweep in deployments Article 5(1)(f) does not reach."""
        assert self._match(question) == "emotion_recognition_general"

    def test_agent_alone_is_not_a_workplace_token(self) -> None:
        """"agent" collides with "AI agent" and is deliberately excluded."""
        assert self._match("Emotion recognition inside our AI agent product") == (
            "emotion_recognition_general"
        )

    def test_rescue_path_prefers_the_narrow_workplace_entry(self) -> None:
        from app.engines._graph_rag_impl import _detect_classification_topic

        not_verdict_shaped = (
            "We deploy an emotion recognition system in our call centre to "
            "monitor agent stress. Is that permitted in the EU?"
        )
        verdict_shaped = (
            "We monitor the stress levels of our call-centre agents with an "
            "emotion recognition AI. Is that allowed?"
        )
        for q in (not_verdict_shaped, verdict_shaped):
            topic = _detect_classification_topic(q)
            assert topic is not None
            assert topic["name"] == "emotion_recognition_workplace"

    @pytest.mark.parametrize(
        "question",
        [
            "Emotion recognition in our retail stores to measure customer satisfaction. Is that permitted?",
            "Is emotion detection on viewers of our advertising permitted?",
            "Is emotion recognition for driver drowsiness in consumer cars allowed?",
        ],
    )
    def test_rescue_path_still_serves_general_off_workplace(self, question: str) -> None:
        from app.engines._graph_rag_impl import _detect_classification_topic

        topic = _detect_classification_topic(question)
        assert topic is not None
        assert topic["name"] == "emotion_recognition_general"


# ─── R377-E ──────────────────────────────────────────────────────────────────


class TestR377EChallengeTurnDetection:
    """A pushback does not have to say "you are wrong" to be a pushback."""

    LIVE_DEROGATION_PUSHBACK = (
        "But Article 6(3) says a system is not high-risk if it performs a narrow "
        "procedural task. Ours only sorts CVs into a preliminary order for a human "
        "recruiter. So the derogation applies and we are exempt, correct?"
    )

    GENUINE_PUSHBACKS = [
        LIVE_DEROGATION_PUSHBACK,
        "Our vendor says we're exempt because the tool only assists a human recruiter. "
        "So we have no obligations, correct?",
        "We are a US company and the model is hosted in Virginia. The AI Act is EU law, "
        "so it does not reach us. Agreed?",
        "So we are out of scope then?",
        "That means we do not need a conformity assessment, right?",
        "Just confirm that a loyalty programme is fine so we can move on.",
        "So we don't need technical documentation for this, correct?",
        "We're exempt under Article 2(6) because this is research, right?",
        "Then we have no obligations under Chapter III, correct?",
        "So it is not covered by Annex III, agreed?",
    ]

    ORDINARY_FOLLOW_UPS = [
        "Thanks. What about the deployer's obligations?",
        "Can you also explain the conformity assessment route?",
        "Is that correct for Annex I products too?",
        "Which article covers the logging requirement?",
        "How long must we retain the logs?",
        "What happens if we modify the intended purpose later?",
        "Does the same apply to our importer?",
        "Could you list the Annex IV contents?",
        "And for a general-purpose model, is the threshold different?",
        "What is the deadline for compliance?",
        "Should we reconsider our classification if we add profiling?",
        "Is the fine calculated on group turnover or entity turnover?",
        "Please confirm the article number you cited.",
        "Can you confirm whether Annex III point 4 applies?",
        "We want to be sure we are compliant. What else is needed?",
    ]

    @pytest.mark.parametrize("question", GENUINE_PUSHBACKS)
    def test_leading_confirmation_pushback_is_a_challenge(self, question: str) -> None:
        from app.data.graph_rag_prompts import is_challenge_turn

        assert is_challenge_turn(question, has_prior_turns=True) is True

    @pytest.mark.parametrize("question", ORDINARY_FOLLOW_UPS)
    def test_ordinary_follow_ups_are_not_challenges(self, question: str) -> None:
        from app.data.graph_rag_prompts import is_challenge_turn

        assert is_challenge_turn(question, has_prior_turns=True) is False

    def test_bare_verification_request_is_not_a_challenge(self) -> None:
        from app.data.graph_rag_prompts import is_challenge_turn

        assert is_challenge_turn("Is that correct?", has_prior_turns=True) is False
        assert is_challenge_turn("We are exempt, correct?", has_prior_turns=True) is True
        # Without prior turns, R379 gate correctly treats it as not a challenge turn
        assert is_challenge_turn("We are exempt, correct?", has_prior_turns=False) is False

    def test_live_turn_doctrine_preserved(self) -> None:
        from app.data.graph_rag_prompts import is_challenge_turn

        flattened = (
            "Conversation so far:\nUser: So we are exempt, correct?\n"
            "Assistant: No.\n\nLatest question:\nWhat are the logging duties?"
        )
        assert is_challenge_turn(flattened) is False



"""R145 — extended-Opus-prose cohesion + conciseness fixes.

The Stage-2 model (Opus 4.8), on complex multi-part classification questions
("Is X prohibited? Or high-risk per Annex III?"), sometimes structures the
answer as a sectioned legal memo with short heading-like sentence fragments
("Why it is not prohibited (Article 5).", "Why it is not Annex III high-risk.",
"The condition that would make it high-risk (Article 6).") and restates the
same finding in several places. That hurts the conciseness axis (padding) and
coherence (IRAC scaffolding + repetition). R145 fixes it at two layers:

* the Stage-2 prompt (COHESION rule 5c + the ANSWER_FORMAT bullet + both engine
  Stage-2 user-messages), and
* a deterministic backstop ``strip_section_headers`` that drops the pseudo-
  header fragments while preserving every substantive sentence (incl. obligation
  enumerations).

These are Stage-2-only / answer-normaliser surfaces, so davidath is
byte-identical (see the bench A/B in the round notes); this module pins the
backstop's precision + the prompt-rule presence.
"""

from __future__ import annotations

import importlib

import pytest

from app.integrations.regenold import answer_normaliser as an
from app.integrations.regenold.answer_normaliser import (
    strip_section_headers,
    _is_section_header_fragment,
)


# ── The pseudo-header fragments R145 targets (MUST be detected) ───────────────
HEADER_POSITIVES = [
    "Why it is not prohibited (Article 5).",
    "Why it is not Annex III high-risk.",
    "Why it is not high-risk.",
    "Why this applies (Article 6).",
    "Why the system is prohibited.",
    "The condition that would make it high-risk (Article 6).",
    "The route that triggers high-risk classification (Article 6).",
]

# ── Substantive sentences that MUST survive ──────────────────────────────────
HEADER_NEGATIVES = [
    # copula in the relative clause → substantive, not a bare header
    "The condition that triggers high-risk is third-party conformity assessment (Article 6).",
    # plain "The condition is X" → no relativizer → substantive
    "The condition is third-party conformity assessment under Annex I (Article 6).",
    # a real conclusion sentence (the redundancy the PROMPT handles, not the backstop)
    "The Annex III route does not apply here.",
    "Article 5 bans eight exhaustively defined practices.",
    "The provider must conduct a conformity assessment (Article 43).",
    "This system is high-risk under Article 6.",
    "Not high-risk and not prohibited on the facts as described.",
    # an obligation enumeration — required completeness, never dropped
    "A risk management system (Article 9), data governance (Article 10), and "
    "technical documentation (Article 11) apply to the provider.",
    # a genuine question is never a declarative header
    "Why does the EU AI Act apply to providers?",
    # "The reason ... is ..." has a finite predicate → substantive
    "The reason for the carve-out is the medical context (Article 5).",
    # a finite verb in the relative clause ("applies") → kept (safe direction)
    "The exception that applies to this system (Annex III).",
]


@pytest.mark.parametrize("sentence", HEADER_POSITIVES)
def test_pseudo_header_detected(sentence: str) -> None:
    assert _is_section_header_fragment(sentence) is True


@pytest.mark.parametrize("sentence", HEADER_NEGATIVES)
def test_substantive_sentence_preserved(sentence: str) -> None:
    assert _is_section_header_fragment(sentence) is False


def test_strip_removes_headers_keeps_substance() -> None:
    """The user-reported transcription answer: headers dropped, substance kept."""
    example = (
        "Not high-risk and not prohibited on the facts as described, an AI system "
        "transcribing doctor patient conversations is neither categorically banned "
        "under Article 5 nor enumerated as a standalone high-risk use case in Annex "
        "III. Why it is not prohibited (Article 5). Article 5 bans eight exhaustively "
        "defined practices, including subliminal techniques. Why it is not Annex III "
        "high-risk. The eight high-risk use-case categories in Annex III do not "
        "include clinical documentation or medical transcription. The condition that "
        "would make it high-risk (Article 6). Article 6 classifies an AI system as "
        "high-risk on two routes."
    )
    out = strip_section_headers(example)
    # All three pseudo-headers gone.
    assert "Why it is not prohibited" not in out
    assert "Why it is not Annex III high-risk" not in out
    assert "The condition that would make it high-risk (Article 6)" not in out
    # All substantive content survives.
    assert "Article 5 bans eight exhaustively defined practices" in out
    assert "do not include clinical documentation or medical transcription" in out
    assert "Article 6 classifies an AI system as high-risk on two routes" in out
    assert len(out) < len(example)


def test_obligation_enumeration_never_truncated() -> None:
    """An obligation list (no headers) is returned byte-for-byte."""
    answer = (
        "The provider of a high-risk AI system must establish a risk management "
        "system (Article 9), ensure data governance (Article 10), draw up technical "
        "documentation (Article 11), keep records (Article 12), provide transparency "
        "(Article 13), enable human oversight (Article 14), ensure accuracy and "
        "cybersecurity (Article 15), operate a quality management system (Article "
        "17), and undergo a conformity assessment (Article 43)."
    )
    assert strip_section_headers(answer) == answer


def test_idempotent() -> None:
    example = (
        "Not high-risk. Why it is not prohibited (Article 5). Article 5 bans eight "
        "practices. The condition that would make it high-risk (Article 6). Article "
        "6 sets two routes for high-risk classification of an AI system."
    )
    once = strip_section_headers(example)
    assert strip_section_headers(once) == once


def test_single_sentence_never_emptied() -> None:
    """A lone sentence is never treated as a section structure."""
    lone = "Why it is not prohibited (Article 5)."
    assert strip_section_headers(lone) == lone


def test_all_headers_input_returns_original() -> None:
    """If removal would leave no substance, return the original unchanged."""
    headers_only = "Why it is not prohibited. Why it is not high-risk."
    # remainder would be empty → never-empty guard returns original.
    assert strip_section_headers(headers_only) == headers_only


def test_empty_and_none_safe() -> None:
    assert strip_section_headers("") == ""
    assert strip_section_headers("   ") == "   "


def test_env_off_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_STRIP_SECTION_HEADERS", "0")
    example = (
        "Not high-risk. Why it is not prohibited (Article 5). Article 5 bans eight "
        "practices that are exhaustively defined in the Regulation."
    )
    assert strip_section_headers(example) == example


def test_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_STRIP_SECTION_HEADERS", raising=False)
    example = (
        "Not high-risk on the facts. Why it is not prohibited (Article 5). Article 5 "
        "bans eight exhaustively defined practices in the Regulation."
    )
    assert "Why it is not prohibited" not in strip_section_headers(example)


def test_in_all_exports() -> None:
    assert "strip_section_headers" in an.__all__


# ── Prompt-rule presence (the source-side fix) ───────────────────────────────


def test_cohesion_rule_in_answer_generate_system() -> None:
    prompts = importlib.import_module("app.data.graph_rag_prompts")
    sys_prompt = prompts.ANSWER_GENERATE_SYSTEM
    assert "5c. COHESION" in sys_prompt
    # forbids the memo / heading-fragment structure
    assert "sectioned" in sys_prompt.lower()
    assert "heading-like" in sys_prompt.lower()
    # protects enumeration completeness from the no-restatement rule
    assert "required completeness" in sys_prompt.lower()


def test_cohesion_rule_text_is_dash_free() -> None:
    """The R145 rule-5c text itself uses no em/en-dash or ellipsis separators."""
    prompts = importlib.import_module("app.data.graph_rag_prompts")
    sys_prompt = prompts.ANSWER_GENERATE_SYSTEM
    start = sys_prompt.index("5c. COHESION")
    rule_5c = sys_prompt[start : sys_prompt.index("\n6. When gaps", start)]
    assert "—" not in rule_5c
    assert "–" not in rule_5c
    assert "…" not in rule_5c


def test_engine_stage2_messages_carry_cohesion() -> None:
    """Both engine Stage-2 user-messages forbid the sectioned-memo structure."""
    import inspect

    import app.engines.graph_rag as gr

    src = inspect.getsource(gr)
    # the classification + refine branches both gained the cohesion instruction
    assert src.count("sectioned justification memo") >= 2
    assert "heading-like sub-topic fragments" in src

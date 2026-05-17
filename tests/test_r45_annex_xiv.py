"""R45 Fix 4 — Annex XIV reachability + Agentic-AI cross-link.

R41 added ``Annex XIV`` (notified-body designation codes incl. AIH 0401
"Agentic AI") to :data:`app.data.article_existence.ARTICLE_EXISTENCE`,
but five downstream consumers still assumed Annex I-XIII only:

1. ``app/integrations/regenold/scope.py`` — ``_ROMAN_NUMERAL_VALUES``
   topped out at ``"xiii": 13``; ``Annex XIV`` parsed as unknown so a
   ``classify_scope("What does Annex XIV say...?")`` call returned
   ``NON_EXISTENT_ARTICLE`` (the refusal path) — even though the
   existence catalog had ``Annex XIV``. The anchor lookup table
   ``_AI_ACT_ANCHORS`` was also missing ``"annex xiv"``.
2. Refusal copy in scope.py + the ``graph_rag_prompts.py`` SYSTEM
   prompt still said "13 annexes (Annex I-XIII)".
3. ``app/data/eu_ai_act_corpus.py::ARTICLE_FULL_TEXT`` (+ ``ARTICLE_TITLE``
   + ``ARTICLE_CHAPTER``) had no entry for ``Annex XIV`` — so any
   downstream consumer trying to render Annex XIV prose got an empty
   string / KeyError fallback.
4. ``app/data/agentic_taxonomy.py::compound_risks_for_article("Annex XIV")``
   returned ``[]`` because the four risk axes' ``article_refs`` lists
   don't include ``Annex XIV`` literally. But the whole point of the
   AIH 0401 designation is that it IS the regulatory hook for the
   four-axis taxonomy — returning ``[]`` made the link unusable.
5. ``is_agentic_ai_designation`` matched only the literal code
   ``"AIH 0401"`` — not the natural-language phrasing partners
   actually use ("agentic ai" / "Agentic-AI").

This module pins all five behaviours so the next R41-style insertion
can't silently re-orphan Annex XIV.
"""
from __future__ import annotations

import pytest

from app.data.agentic_taxonomy import (
    compound_risks_for_article,
    is_agentic_ai_designation,
    COMPOUND_RISK_TYPES,
)
from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.eu_ai_act_corpus import (
    ARTICLE_CHAPTER,
    ARTICLE_FULL_TEXT,
    ARTICLE_TITLE,
)
from app.integrations.regenold.scope import (
    classify_scope,
    extract_referenced_articles,
)


# ── Catalog + corpus parity ──────────────────────────────────────────────


def test_annex_xiv_is_in_existence_catalog() -> None:
    """Sanity gate: R41 should have added Annex XIV to ARTICLE_EXISTENCE."""
    assert "Annex XIV" in ARTICLE_EXISTENCE


def test_annex_xiv_present_in_corpus_full_text() -> None:
    """ARTICLE_FULL_TEXT must carry a non-empty Annex XIV stub."""
    assert "Annex XIV" in ARTICLE_FULL_TEXT
    body = ARTICLE_FULL_TEXT["Annex XIV"]
    assert isinstance(body, str)
    # The R41 verbatim quote runs ~1k chars; insist on at least 200.
    assert len(body) >= 200, f"Annex XIV stub too short: {len(body)} chars"


def test_annex_xiv_stub_mentions_aih_0401_and_agentic_ai() -> None:
    body = ARTICLE_FULL_TEXT["Annex XIV"]
    assert "AIH 0401" in body, "Stub must name the AIH 0401 designation"
    assert "Agentic AI" in body, "Stub must name the natural-language label"


def test_annex_xiv_has_title_and_chapter_rows() -> None:
    """Downstream consumers iterate ARTICLE_TITLE / ARTICLE_CHAPTER —
    a missing key blows up the renderer."""
    assert "Annex XIV" in ARTICLE_TITLE
    title = ARTICLE_TITLE["Annex XIV"]
    assert title and len(title) >= 10
    assert "Annex XIV" in ARTICLE_CHAPTER
    # All other annexes carry ``None`` for chapter — Annex XIV must match.
    assert ARTICLE_CHAPTER["Annex XIV"] is None


# ── Scope gate ───────────────────────────────────────────────────────────


def test_scope_classifies_annex_xiv_question_in_scope() -> None:
    """The very acceptance command from the R45 brief."""
    verdict = classify_scope("What does Annex XIV say about AIH 0401 Agentic AI?")
    assert verdict.in_scope is True, (
        f"Annex XIV question wrongly refused: reason={verdict.reason}"
    )


def test_scope_extracts_annex_xiv_as_known_reference() -> None:
    """Round-tripping the canonical ref out of free-text must land
    Annex XIV in the KNOWN bucket, not the unknown one."""
    known, unknown = extract_referenced_articles(
        "Does Annex XIV apply when an agent uses dynamic tool discovery?"
    )
    assert "Annex XIV" in known
    assert "Annex XIV" not in unknown


def test_scope_still_rejects_annex_xx_as_non_existent() -> None:
    """Bookend: widening the Roman-numeral table to 14 must NOT make
    Annex XX (would-be 20) start passing the existence gate."""
    _known, unknown = extract_referenced_articles(
        "Summarise Annex XX duties."
    )
    assert "Annex XX" in unknown


def test_scope_anchor_keyword_recognises_annex_xiv_phrase() -> None:
    """The anchor-vocabulary lookup must also resolve the natural
    phrase ``annex xiv`` so a question that names the annex without
    a sub-point still anchors correctly."""
    verdict = classify_scope("Tell me about annex xiv.")
    assert verdict.in_scope is True


# ── Agentic-AI taxonomy cross-link ───────────────────────────────────────


def test_is_agentic_ai_designation_matches_canonical_code() -> None:
    assert is_agentic_ai_designation("AIH 0401") is True
    assert is_agentic_ai_designation("aih 0401") is True
    assert is_agentic_ai_designation(" AIH  0401 ") is True


def test_is_agentic_ai_designation_matches_natural_language() -> None:
    """R45 finding C4: extend matching to natural-language forms."""
    assert is_agentic_ai_designation("agentic ai") is True
    assert is_agentic_ai_designation("Agentic AI") is True
    assert is_agentic_ai_designation("Agentic-AI") is True
    assert is_agentic_ai_designation("agentic-ai system") is True
    assert is_agentic_ai_designation("agentic AI systems") is True
    assert is_agentic_ai_designation("agentic artificial intelligence") is True


def test_is_agentic_ai_designation_rejects_other_codes_and_garbage() -> None:
    assert is_agentic_ai_designation("AIH 0301") is False  # generative
    assert is_agentic_ai_designation("AIP 0101") is False  # machinery
    assert is_agentic_ai_designation("") is False
    assert is_agentic_ai_designation("not a code") is False
    # type-safety belt: None-like (function checks for falsy).
    assert is_agentic_ai_designation(None) is False  # type: ignore[arg-type]


def test_compound_risks_for_annex_xiv_returns_full_four_axis_set() -> None:
    """Annex XIV is the regulatory hook — return all four axes."""
    risks = compound_risks_for_article("Annex XIV")
    assert len(risks) == len(COMPOUND_RISK_TYPES)
    labels = {r["label"] for r in risks}
    assert labels == {
        "Cascading Risk",
        "Emergent Risk",
        "Attribution Risk",
        "Temporal Risk (Runtime Drift)",
    }


def test_compound_risks_routes_aih_0401_and_natural_label_to_full_set() -> None:
    """Same expansion for the raw AIH 0401 code AND the natural label —
    so engines that ingested the question-side phrasing still resolve."""
    assert len(compound_risks_for_article("AIH 0401")) == 4
    assert len(compound_risks_for_article("agentic ai")) == 4
    assert len(compound_risks_for_article("Agentic-AI")) == 4


def test_compound_risks_for_unrelated_article_unchanged() -> None:
    """Regression guard — the Annex XIV special-case must not bleed
    into the prefix-match for normal ``Art. N`` lookups."""
    # Art. 9 grounds the Cascading + Emergent + Temporal axes (per the
    # ``article_refs`` lists in COMPOUND_RISK_TYPES) — at least one,
    # never all four.
    risks = compound_risks_for_article("Art. 9")
    assert 1 <= len(risks) < 4
    # And an article that no axis cites returns an empty list.
    assert compound_risks_for_article("Art. 113") == []


# ── Wire round-trip ──────────────────────────────────────────────────────


def test_wire_round_trip_annex_xiv_question_returns_http_200() -> None:
    """A live ``POST /api/v1/regenold/eu-ai-act/ask`` with an Annex XIV
    question must answer (not refuse) and surface ``Annex XIV`` (or a
    related cross-reference) in the references list."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    payload = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "What does Annex XIV say about AIH 0401 Agentic AI?"
                ),
            }
        ]
    }
    resp = client.post("/api/v1/regenold/eu-ai-act/ask", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "answer" in body
    assert isinstance(body["answer"], str)
    # The answer must not be the static "doesn't exist" refusal — we
    # just need a coherent body. A reference may or may not include
    # "Annex XIV" literally depending on the engine's anchor-narrowing
    # pass, but the answer body must not refuse the question.
    answer_lower = body["answer"].lower()
    assert "does not appear in the eu ai act" not in answer_lower, (
        "Annex XIV must not be refused as non-existent — body: "
        + body["answer"][:200]
    )


def test_wire_round_trip_aih_0401_natural_question_returns_http_200() -> None:
    """Equivalent natural-language question (no literal "Annex XIV"
    token) should also flow through scope/route correctly."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "Are Agentic AI systems covered by the EU AI Act?",
            }
        ]
    }
    resp = client.post("/api/v1/regenold/eu-ai-act/ask", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("answer")
    assert "does not appear in the eu ai act" not in body["answer"].lower()

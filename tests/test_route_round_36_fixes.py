"""Round-36 regression guards for ``app/routes/regenold.py``.

Pins four route-side hardenings (Agent C scope):

* **#40 — closed-world no-refusal gap.** ``_compute_confidence`` returns
  exactly ``0.5`` for sparse retrieval; the pre-fix strict-less-than
  check let an empty-refs response slip through with the engine prose
  intact. Post-fix: empty ``references`` ALONE triggers the no-match
  refusal regardless of confidence.

* **#46 — CLARA injection bypasses refusal.** CLARA's deterministic
  verdict matrix can prepend ``Art. 6`` / ``Art. 16`` even when GraphRAG
  returned an empty candidate set. Post-fix: CLARA injection is gated on
  having at least one upstream candidate, so a question with no
  GraphRAG grounding gets the closed-world refusal and CLARA does not
  invent citations.

* **#49 — classification short-circuit truncation.** When
  ``_detect_classification_topic`` matches in the engine, Stage-2 polish
  is skipped — the deterministic curated verdict is returned verbatim.
  Pre-fix the route then re-ran ``normalise_answer_for_regenold`` +
  verdict-prefix prepend + CLARA injection on top. Post-fix: when the
  question matches a classification topic, the route skips the
  prose-side mutations (caps, prefix prepend, CLARA inject) and the
  engine prose is shipped intact.

* **#53 — unsanitized intent anchors drive citation pruning.** The
  intent classifier is an LLM output and may surface anchors that
  don't exist (``Art. 999``, ``Annex XV``) — possibly due to prompt
  injection. Post-fix: ``_intent_anchor_set`` validates every anchor
  against ``ARTICLE_EXISTENCE`` before adding to the prune set, so
  bogus anchors never narrow references.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.models import CitationNode, GraphRAGResponse


# ─── Test plumbing ────────────────────────────────────────────────────────


def _client() -> TestClient:
    return TestClient(app)


def _messages(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


def _headers() -> dict[str, str]:
    return {"X-Regenold-Api-Key": "regenold-test-key"}


@pytest.fixture(autouse=True)
def _configure_key_and_clear_cache():
    """Configure a valid partner key and clear the engine LRU between tests.

    The route's ``_ENGINE_CACHE`` keys on ``(question, system_context)`` —
    two tests that send the same question would otherwise share state
    (and a mocked engine return value would never reach the assertion
    body if a prior test cached a different value under the same key).
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415
    # The bounded LRU stores entries in ``_data``; reach in directly so
    # a future rename surfaces here as a test-time AttributeError.
    with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
        _ENGINE_CACHE._data.clear()  # type: ignore[attr-defined]
    yield


def _sparse_response(answer: str = "") -> GraphRAGResponse:
    """Build a GraphRAGResponse mimicking sparse retrieval — confidence 0.5,
    no citations, no graph stats. This is the exact shape that pre-fix
    slipped through the refusal gate (``confidence < 0.5`` fails when
    confidence is exactly 0.5).
    """
    return GraphRAGResponse(
        answer=answer or "Some engine prose that should not be shipped.",
        citations=[],
        confidence=0.5,
        graph_stats={"nodes_traversed": 0, "obligations_found": 0},
    )


# ─── Issue #40 — closed-world refusal gate ────────────────────────────────


class TestRefusalGateAtBoundary:
    """Empty references → refusal, regardless of confidence."""

    def test_empty_refs_at_confidence_floor_triggers_refusal(self) -> None:
        """confidence == 0.5 + empty refs → ``_NO_MATCH_ANSWER`` ships.

        Use an in-scope question that mentions a compliance-dimension
        keyword but no specific Article — otherwise the route's anchor-
        surfacing pass would inject the named article as a citation and
        bypass the empty-refs branch.
        """
        from app.routes.regenold import _NO_MATCH_ANSWER  # noqa: PLC0415

        sparse = _sparse_response()
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=sparse,
        ):
            c = _client()
            r = c.post(
                "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
                headers=_headers(),
                json=_messages(
                    "What are the deployer compliance dimensions?"
                ),
            )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body["answer"] == _NO_MATCH_ANSWER, (
            f"Expected no-match refusal at conf=0.5 + empty refs; got: {body['answer']!r}"
        )
        assert body["references"] == []
        assert body.get("retrieval_path") == "no_match"

    def test_empty_refs_below_floor_still_triggers_refusal(self) -> None:
        """Sanity: confidence < 0.5 + empty refs also refuses (regression
        floor — the pre-fix behaviour on this exact axis)."""
        from app.routes.regenold import _NO_MATCH_ANSWER  # noqa: PLC0415

        sparse = GraphRAGResponse(
            answer="Some prose.",
            citations=[],
            confidence=0.3,
            graph_stats={"nodes_traversed": 0},
        )
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=sparse,
        ):
            c = _client()
            r = c.post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=_messages(
                    "What are the deployer compliance dimensions?"
                ),
            )
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == _NO_MATCH_ANSWER

    def test_non_empty_refs_skips_refusal_even_at_low_confidence(self) -> None:
        """A non-empty citation list is healthy grounding — keep the prose.

        Closed-world refusal is "no grounded citations = no answer", so a
        low-confidence answer WITH refs should still ship — refusal is
        keyed on empty refs, not low confidence.
        """
        from app.routes.regenold import _NO_MATCH_ANSWER  # noqa: PLC0415

        cited = GraphRAGResponse(
            answer=(
                "Article 13(1) requires high-risk AI providers to design transparency "
                "mechanisms so deployers can interpret outputs."
            ),
            citations=[
                CitationNode(
                    node_type="Article",
                    node_id="art-13",
                    text="Transparency obligations.",
                    article_ref="Art. 13",
                ),
            ],
            confidence=0.4,
            graph_stats={"nodes_traversed": 2},
        )
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=cited,
        ):
            c = _client()
            r = c.post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=_messages("What does Article 13 require?"),
            )
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] != _NO_MATCH_ANSWER
        assert "Article 13" in body["references"][0]


# ─── Issue #46 — CLARA must not bypass the refusal ────────────────────────


class TestClaraDoesNotBypassRefusal:
    """Even with a high-confidence medical-device verdict, an empty
    GraphRAG candidate set must NOT trigger CLARA citation injection —
    otherwise CLARA invents grounding and the refusal is skipped."""

    def test_clara_skipped_when_no_upstream_candidates(self) -> None:
        from app.engines.clara_logic import Verdict  # noqa: PLC0415
        from app.routes.regenold import _NO_MATCH_ANSWER  # noqa: PLC0415

        sparse = _sparse_response()

        # Mock CLARA to return a high-confidence high-risk verdict that
        # WOULD have injected Art. 6 + Art. 16 pre-fix.
        fake_verdict = Verdict(
            risk_tier="high_risk",  # type: ignore[arg-type]
            primary_articles=("Art. 6", "Art. 16"),
            supporting_articles=(),
            rationale=("medical_device_pattern",),
            confidence=0.9,
        )

        # Use an in-scope question with no article-keyword anchor (so the
        # route's ``_surface_anchor_citations`` pass doesn't inject one
        # from the scope verdict) and let CLARA invent grounding via the
        # mocked verdict. Pre-fix the wire response would surface
        # ``Article 6`` + ``Article 16`` and the refusal would be skipped.
        question = "What are the deployer compliance dimensions?"
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=sparse,
        ):
            with patch(
                "app.engines.clara_logic.analyse",
                return_value=(None, fake_verdict),
            ):
                c = _client()
                r = c.post(
                    "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
                    headers=_headers(),
                    json=_messages(question),
                )
        assert r.status_code == 200
        body = r.json()
        assert body["references"] == [], (
            f"Expected empty refs (CLARA must not inject when GraphRAG "
            f"has no candidates); got {body['references']!r}"
        )
        assert body["answer"] == _NO_MATCH_ANSWER
        assert body.get("retrieval_path") == "no_match"


# ─── Issue #49 — classification short-circuit must NOT be re-mutated ───────


class TestClassificationShortCircuitNotMutated:
    """When the engine emits a classification verdict (Stage-2 skipped
    in engine), the route must not re-apply normalisation, verdict
    prepend, or CLARA injection — the curated prose is shipped intact.
    """

    def test_classification_topic_answer_passes_through_unmutated(self) -> None:
        """Real classification question — ``_detect_classification_topic``
        will match. The engine's curated 1-3 sentence verdict must equal
        the wire answer (modulo only the citation-side pipeline)."""
        from app.engines.graph_rag import (  # noqa: PLC0415
            _detect_classification_topic,
        )

        # Use a question that (a) is classed in-scope by the scope gate
        # and (b) matches a classification topic so the engine emits the
        # curated verdict prose. The emotion-recognition topic fits both.
        question = "Is emotion recognition in the workplace prohibited?"
        # Sanity gate: this question MUST be a classification topic, else
        # the test premise is broken.
        assert _detect_classification_topic(question) is not None, (
            "Test premise broken: question must be a classification topic."
        )

        # Build a curated verdict response — short, citation-anchored,
        # but containing a distinctive opening token ("EMOTION_VERDICT_")
        # we can pin in the assertion to prove no prefix was prepended.
        curated_answer = (
            "EMOTION_VERDICT_OPENING: Emotion recognition is prohibited under "
            "Article 5 when deployed in workplaces or educational institutions "
            "with narrow medical exceptions. Outside those settings it is "
            "high-risk under Annex III with Article 50 transparency duties."
        )
        engine_resp = GraphRAGResponse(
            answer=curated_answer,
            citations=[
                CitationNode(
                    node_type="Article",
                    node_id="art-5",
                    text="Prohibited practices.",
                    article_ref="Art. 5",
                ),
            ],
            confidence=0.95,
            graph_stats={"nodes_traversed": 3, "classification_topic": True},
        )
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=engine_resp,
        ):
            c = _client()
            r = c.post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=_messages(question),
            )
        assert r.status_code == 200, r.json()
        body = r.json()
        # Answer must NOT have a verdict prefix prepended by the route.
        # The curated text leads with the distinctive sentinel token so
        # any prefix-prepend would push it past position 0.
        assert body["answer"].startswith("EMOTION_VERDICT_OPENING"), (
            f"Expected curated verdict prose to lead; got: {body['answer']!r}"
        )
        # Curated prose is under the 600-char + 3-sentence caps so the
        # normaliser is a no-op. The full sentinel + opening sentence
        # must survive end-to-end.
        assert "EMOTION_VERDICT_OPENING" in body["answer"]
        # Tail content must also survive — pin the closing sentence's
        # distinctive phrase to prove the 3-sentence cap didn't lop off
        # the final clause.
        assert "Article 50" in body["answer"]


# ─── Issue #53 — anchor validation against ARTICLE_EXISTENCE ──────────────


class TestIntentAnchorValidation:
    """``_intent_anchor_set`` must drop anchors that are not in
    ``ARTICLE_EXISTENCE``. An attacker who can perturb the intent
    classifier (prompt injection, model hallucination) cannot use it
    to narrow the citation set to a fabricated article."""

    def test_unknown_article_anchor_is_dropped(self) -> None:
        """Mock the classifier to return ``Art. 999`` — must not pass."""
        from app.llm.intent_classifier import IntentResult  # noqa: PLC0415
        from app.routes.regenold import _intent_anchor_set  # noqa: PLC0415

        bogus = IntentResult(
            intent="penalty_inquiry",
            primary_anchor="Art. 999",
            alternate_anchors=("Annex XV",),
            confidence=0.9,
            elapsed_ms=0,
            cache_hit=False,
            model="test",
        )
        with patch(
            "app.routes.regenold.classify_intent",
            return_value=bogus,
        ):
            article_nums, annex_romans, _ = _intent_anchor_set(
                "What's the max fine?"
            )
        # Both bogus anchors must be dropped — empty sets.
        assert article_nums == set(), (
            f"Expected Art. 999 to be dropped; got {article_nums}"
        )
        assert annex_romans == set(), (
            f"Expected Annex XV to be dropped; got {annex_romans}"
        )

    def test_known_article_anchor_is_kept(self) -> None:
        """Happy path: a real anchor (``Art. 99``) passes through."""
        from app.llm.intent_classifier import IntentResult  # noqa: PLC0415
        from app.routes.regenold import _intent_anchor_set  # noqa: PLC0415

        good = IntentResult(
            intent="penalty_inquiry",
            primary_anchor="Art. 99",
            alternate_anchors=("Annex III",),
            confidence=0.9,
            elapsed_ms=0,
            cache_hit=False,
            model="test",
        )
        with patch(
            "app.routes.regenold.classify_intent",
            return_value=good,
        ):
            article_nums, annex_romans, _ = _intent_anchor_set(
                "What's the max fine?"
            )
        assert article_nums == {"99"}
        assert annex_romans == {"III"}

    def test_mixed_anchors_drops_bogus_keeps_real(self) -> None:
        """Mix of one real + one fake anchor — keep real, drop fake."""
        from app.llm.intent_classifier import IntentResult  # noqa: PLC0415
        from app.routes.regenold import _intent_anchor_set  # noqa: PLC0415

        mixed = IntentResult(
            intent="penalty_inquiry",
            primary_anchor="Art. 99",  # real
            alternate_anchors=("Art. 250", "Annex III", "Annex XX"),
            confidence=0.9,
            elapsed_ms=0,
            cache_hit=False,
            model="test",
        )
        with patch(
            "app.routes.regenold.classify_intent",
            return_value=mixed,
        ):
            article_nums, annex_romans, _ = _intent_anchor_set("q")
        assert article_nums == {"99"}, (
            f"Art. 250 must be dropped; got {article_nums}"
        )
        assert annex_romans == {"III"}, (
            f"Annex XX must be dropped; got {annex_romans}"
        )

    def test_low_confidence_intent_still_returns_empty(self) -> None:
        """Pre-existing invariant — sub-0.7 confidence should return
        empty sets regardless of anchor validity. Pin this to ensure the
        sanitisation pass didn't accidentally loosen the confidence gate.
        """
        from app.llm.intent_classifier import IntentResult  # noqa: PLC0415
        from app.routes.regenold import _intent_anchor_set  # noqa: PLC0415

        low = IntentResult(
            intent="penalty_inquiry",
            primary_anchor="Art. 99",
            alternate_anchors=(),
            confidence=0.5,  # below 0.7 floor
            elapsed_ms=0,
            cache_hit=False,
            model="test",
        )
        with patch(
            "app.routes.regenold.classify_intent",
            return_value=low,
        ):
            article_nums, annex_romans, label = _intent_anchor_set("q")
        assert article_nums == set()
        assert annex_romans == set()
        assert label == ""

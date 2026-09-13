"""R418 — the fixes from the specialist review of the R411–R417 diff.

Four independent defects, each found by a different review lens and each pinned
here by its OBSERVABLE (a detector's verdict, a counter, a converted stop
reason) rather than by the shape of the code:

1. ``is_challenge_turn(live_question)`` without ``has_prior_turns=True``.
   The predicate derives "is there a prior turn" from the ``Latest question:``
   flatten marker, and ``live_question`` never carries it — so the whole R377
   leading-confirmation family ("are you sure?", "we are exempt, correct?")
   could never fire at the only production call site. Only the always-on
   explicit dispute markers worked, which is exactly what the single covering
   test used, so the gap was invisible.
2. Bedrock reports ``max_tokens``; every truncation guard tests ``length``. A
   truncated Bedrock completion therefore skipped all of them — including the
   Stage-0 de-noiser loop that adopts the rewrite AS the retrieval query.
3. The Stage-0 de-noiser's Bedrock leg can reach the wrapper hop inside
   ``complete_with_fallback``, which increments the process-global
   ``stage2_policy`` PRIMARY counters. ``easyhard_ab._transport_liveness`` and
   ``gate_validity`` read those counters, so a run where Stage-2 never landed
   could look live — a false green on the guard that exists to block them.
4. The emotion rescue matched workplace patterns against the whole flattened
   conversation and treated an operator term as the subject, so a patient- or
   customer-facing use could ship the curated "prohibited under Article 5 …
   workplaces" verdict.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.data.graph_rag_prompts import is_challenge_turn
from app.llm import stage2_policy as pol

# ── 1. the challenge predicate needs to know a prior turn exists ─────────────


class TestTheChallengePatternFamilyFiresOnlyWithPriorTurns:
    @pytest.mark.parametrize(
        "dispute",
        [
            "We are exempt, correct?",
            "So we have no obligations then?",
            "That is not what Annex III says.",
        ],
    )
    def test_the_flag_restores_the_pattern_family(self, dispute: str) -> None:
        assert is_challenge_turn(dispute, has_prior_turns=True) is True, (
            "the R377 leading-confirmation family must fire when the caller "
            "knows a prior turn exists"
        )

    def test_without_the_flag_the_pattern_family_cannot_fire(self) -> None:
        """The defect: bare live-question text reads as turn 1."""
        assert is_challenge_turn("We are exempt, correct?") is False

    def test_explicit_markers_stay_unconditional(self) -> None:
        assert is_challenge_turn("I don't think this is correct.") is True
        assert (
            is_challenge_turn("I don't think this is correct.", has_prior_turns=True)
            is True
        )

    def test_the_route_passes_the_flag_and_recovers_a_pattern_only_pushback(
        self,
    ) -> None:
        """End-to-end through ``_build_question_from_history``.

        The recovered shape is the observable: a pattern-only dispute must
        resolve to the disputed ROOT question, not to the critique text.
        """

        from app.routes.regenold import _build_question_from_history

        class _Msg:
            def __init__(self, role: str, content: str) -> None:
                self.role = role
                self.content = content

        root = (
            "What are the transparency obligations for general-purpose AI model "
            "providers under Article 53?"
        )
        res = _build_question_from_history(
            [
                _Msg("user", root),
                _Msg("assistant", "Under Article 53(1), providers must…"),
                _Msg("user", "We are exempt, correct?"),
            ]
        )
        assert res.resolved_question == root, (
            "a pattern-family pushback must recover the root inquiry; without "
            "has_prior_turns=True it runs retrieval on the critique text"
        )
        assert res.self_contained_focus is True


# ── 2. Bedrock's stop reason is normalised ──────────────────────────────────


class TestBedrockStopReasonIsNormalised:
    def test_max_tokens_becomes_length(self) -> None:
        from app.llm.bedrock_client import _parse_converse_response

        resp = _parse_converse_response(
            {
                "output": {"message": {"content": [{"text": "Article 13 require"}]}},
                "usage": {"inputTokens": 5, "outputTokens": 900},
                "stopReason": "max_tokens",
            },
            model_id="eu.anthropic.claude-sonnet-5",
            elapsed_ms=1,
        )
        assert resp.finish_reason == "length", (
            "every truncation guard in the tree tests for 'length'; the raw "
            "Converse 'max_tokens' silently skipped all of them"
        )

    def test_a_natural_stop_is_untouched(self) -> None:
        from app.llm.bedrock_client import _parse_converse_response

        resp = _parse_converse_response(
            {
                "output": {"message": {"content": [{"text": "Article 13."}]}},
                "usage": {"inputTokens": 5, "outputTokens": 4},
                "stopReason": "end_turn",
            },
            model_id="eu.anthropic.claude-sonnet-5",
            elapsed_ms=1,
        )
        assert resp.finish_reason == "end_turn"


# ── 3. the de-noiser's Bedrock leg must not count as Stage-2 ────────────────


class TestTheDenoiserBedrockLegDoesNotTouchStage2Counters:
    @pytest.fixture(autouse=True)
    def _clean_counters(self):
        pol.reset_transport_stats()
        pol.transport_stats()
        yield
        pol.reset_transport_stats()

    def _drive(self, *, record_stage2: bool):
        """Force the Bedrock chain to exhaust so the wrapper hop is reached."""
        from app.llm.bedrock_client import (
            BedrockRequest,
            BedrockResponse,
            complete_with_fallback,
        )
        from app.llm.openai_wrapper_provider import OpenAIWrapperResponse

        # ``api_access_denied`` is the durable entitlement marker, so every
        # chain entry is skipped and the wrapper hop is actually reached.
        denied = BedrockResponse(
            text="",
            model="eu.anthropic.claude-sonnet-5",
            error="api_access_denied: not entitled to this model",
        )
        # Patch ``get_bedrock_provider`` (the accessor) rather than
        # ``BedrockProvider.complete``. The accessor is what
        # ``complete_with_fallback`` calls, and it returns a process-wide
        # singleton: patching the class method left the suite loading the REAL
        # provider here, and the run reached ``bedrock-runtime`` (R365 socket
        # guard blocked 169.254.169.254, botocore raised NoCredentialsError,
        # which is NOT an entitlement error, so the chain kept walking and the
        # counters the test asserts on were never the ones it expected).
        _stub_provider = MagicMock()
        _stub_provider.complete = MagicMock(return_value=denied)
        with (
            patch(
                "app.llm.bedrock_client.get_bedrock_provider",
                return_value=_stub_provider,
            ),
            patch(
                "app.llm.bedrock_client.wrapper_fallback_enabled",
                return_value=True,
            ),
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            ) as prov,
        ):
            prov.return_value.complete.return_value = OpenAIWrapperResponse(
                text="Standalone rewrite of the follow-up question.",
                model="claude-opus-5",
                elapsed_ms=1,
            )
            prov.return_value._base_url = "https://wrapper.antifragile-ai.net/v1"
            return complete_with_fallback(
                BedrockRequest(user="u", system="s", model="eu.anthropic.claude-sonnet-5"),
                record_stage2=record_stage2,
            )

    def test_a_denoiser_hop_leaves_the_stage2_counters_alone(self) -> None:
        out = self._drive(record_stage2=False)
        assert out.text, "the hop itself still works — only the counters differ"
        stats = pol.transport_stats()
        assert stats["primary_attempts"] == 0 and stats["primary_ok"] == 0, (
            f"a Stage-0 rewrite was counted as a Stage-2 primary completion, "
            f"which clears easyhard_ab's liveness guard on a dead run: {stats}"
        )

    def test_the_stage2_caller_still_counts_its_hop(self) -> None:
        """Two-sided: the default must keep the documented behaviour."""
        self._drive(record_stage2=True)
        stats = pol.transport_stats()
        assert stats["primary_attempts"] == 1 and stats["primary_ok"] == 1


# ── 4. the emotion rescue: live turn + subject, not operator ────────────────


class TestTheEmotionRescueIsScopedAndSubjectAware:
    def _topic_for(self, question: str) -> str | None:
        from app.engines._graph_rag_impl import _detect_classification_topic

        topic = _detect_classification_topic(question)
        return (topic or {}).get("name")

    def test_a_prior_turn_no_longer_selects_the_workplace_topic(self) -> None:
        question = (
            "Conversation so far:\n"
            "User: We use emotion recognition software for our staff.\n"
            "Assistant: That is prohibited under Article 5 in the workplace.\n"
            "\n"
            "Latest question:\n"
            "Does the AI Act prohibit emotion recognition for shoppers in our store?"
        )
        assert self._topic_for(question) != "emotion_recognition_workplace", (
            "the workplace patterns must be matched against the live turn, not "
            "the flattened conversation"
        )

    def test_an_operator_staff_term_is_not_the_subject(self) -> None:
        question = (
            "Does the AI Act prohibit emotion recognition used by hospital staff "
            "to detect patient distress?"
        )
        assert self._topic_for(question) != "emotion_recognition_workplace", (
            "Article 5(1)(f) reaches inferring the emotions of persons IN the "
            "workplace; staff here operate a system whose subjects are patients, "
            "so the general answer (with its medical carve-out) is correct"
        )

    def test_a_genuine_workplace_use_still_selects_it(self) -> None:
        """The other side: the guard must not disarm the intended traffic."""
        question = (
            "Does the EU AI Act prohibit emotion recognition of employees in the "
            "workplace?"
        )
        assert self._topic_for(question) == "emotion_recognition_workplace"


# ── 5. the recovery must not narrow the SCOPE gate ──────────────────────────


class TestTheRecoveredChallengeKeepsTheWholeConversationInScope:
    """R418 — the second half of the challenge-recovery fix.

    Enabling the R377 pattern family (fix 1) made the recovery fire on
    leading-confirmation pushbacks. The branch sets
    ``self_contained_focus=True`` so the engines narrow their reference
    assembly, and the scope gate reads that same flag to decide whether to
    classify the LIVE turn alone — but the live turn on this branch is a
    dispute that is not self-contained BY CONSTRUCTION. Scope therefore had no
    anchor to see, classified it as conversational and shipped a
    zero-reference refusal. Measured on the deterministic eval surface:
    8/255 ``in_scope_multi_turn`` negative scenarios refused
    (``tests/test_regenold_scope.py``). The marker below is what lets the scope
    gate read the conversation while the reference machinery stays narrowed.
    """

    _LEADING_CONFIRMATION = "So SMEs don't need one at all, correct?"
    _ROOT_Q = (
        "What are the quality-management-system requirements for providers of "
        "high-risk AI systems under Article 17?"
    )

    def _messages(self) -> list[object]:
        class _M:
            def __init__(self, role: str, content: str) -> None:
                self.role = role
                self.content = content

        return [
            _M("user", self._ROOT_Q),
            _M(
                "assistant",
                "Article 17 requires a documented quality management system.",
            ),
            _M("user", self._LEADING_CONFIRMATION),
        ]

    def test_the_pattern_family_now_fires_at_the_production_call_site(self) -> None:
        from app.routes.regenold import _build_question_from_history

        res = _build_question_from_history(self._messages())
        assert res.challenge_recovered is True, (
            "the R377 leading-confirmation family must reach the recovery; "
            "the predicate needs has_prior_turns=True because the branch is "
            "only reachable when prior turns exist"
        )
        assert res.resolved_question == self._ROOT_Q
        # The reference-side narrowing is deliberate and stays.
        assert res.self_contained_focus is True

    def test_the_scope_gate_still_sees_the_conversation(self) -> None:
        """The observable: scope is handed every turn, not just the dispute."""
        from fastapi.testclient import TestClient
        from pydantic import SecretStr

        from app.config import settings
        from app.main import app
        from app.models import CitationNode, GraphRAGResponse

        settings.regenold.api_key = SecretStr("regenold-test-key")
        seen: list[list[object]] = []
        engine_calls: list[object] = []

        def _spy(messages):
            seen.append(list(messages))
            return _real_classify(list(messages))

        def _engine(req):
            engine_calls.append(req)
            return GraphRAGResponse(
                answer="Article 17 requires a documented QMS.",
                citations=[
                    CitationNode(
                        node_type="Article",
                        node_id="art-17",
                        text="Quality management system.",
                        article_ref="Art. 17",
                    )
                ],
                confidence=0.7,
                graph_stats={
                    "nodes_traversed": 2,
                    "stage2_call_failed": False,
                    "stage2_landed": True,
                    "stage2_served_by": "primary",
                },
            )

        from app.integrations.regenold.scope import (
            classify_conversation as _real_classify,
        )
        from app.routes.regenold import _ENGINE_CACHE

        with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
            _ENGINE_CACHE._data.clear()  # type: ignore[attr-defined]

        body = [
            {"role": "user", "content": self._ROOT_Q},
            {
                "role": "assistant",
                "content": "Article 17 requires a documented QMS.",
            },
            {"role": "user", "content": self._LEADING_CONFIRMATION},
        ]
        with (
            patch("app.routes.regenold.classify_conversation", side_effect=_spy),
            patch(
                "app.routes.regenold.ask_compliance_question", side_effect=_engine
            ),
        ):
            r = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers={"X-Regenold-Api-Key": "regenold-test-key"},
                json=body,
            )

        assert r.status_code == 200, r.text[:400]
        assert seen and len(seen[0]) == 3, (
            "scope must classify the whole conversation on a recovered "
            "challenge turn; narrowing to the live dispute is what produced "
            f"the zero-reference refusal (saw {[len(s) for s in seen]} turns)"
        )
        assert engine_calls, "an in-scope follow-up must reach the engine"
        assert "cannot answer" not in r.json().get("answer", "").lower()


# ── 6. the local KG mirror must answer in the SHAPE that was asked for ──────


class TestTheLocalMirrorServesTheR409Shape:
    def test_point_level_rows_exist_for_a_bare_point(self) -> None:
        from app.engines.kg_context import (
            _mirror_point_units,
            _mirror_subpoints,
            _node_ids,
        )

        ids = _node_ids(["Article 5"], limit=24)
        assert ids
        point_rows = _mirror_point_units(ids, 40)
        legacy_rows = _mirror_subpoints(ids, 40)
        assert point_rows, "the mirror must serve the R409 all-Points shape"
        assert len(point_rows) > len(legacy_rows), (
            "the legacy mirror returns SubPoint rows only (37 in the live "
            "graph); the point-level rows are the point text of bare Points"
        )
        bare = [
            row
            for row in point_rows
            if row.get("sid") is None and row.get("para") == "1"
        ]
        assert bare, "bare Points (no SubPoint) must be emitted, not dropped"
        assert bare[0]["letter"] == "a"
        assert "subliminal" in bare[0]["text"]

    def test_the_budget_is_shared_not_greedily_filled(self) -> None:
        from app.engines.kg_context import _mirror_point_units, _node_ids

        ids = _node_ids(["Article 5", "Article 6", "Article 13"], limit=24)
        rows = _mirror_point_units(ids, 6)
        assert len(rows) <= 6
        assert {row["ref_index"] for row in rows} == set(range(len(ids))), (
            "every cited provision must keep at least one unit: greedy "
            "ref-order filling is the R408 'first provision evicts the rest' "
            "defect that _allocate_units exists to remove"
        )


# ── 7. the degenerate guard needs TOKEN evidence, and never assumes it ──────


class TestTheDegenerateGuardNeedsTokenEvidence:
    def test_the_measured_stub_is_degenerate(self) -> None:
        from app.engines._graph_rag_impl import _is_degenerate_completion

        assert _is_degenerate_completion("", 0) is True
        assert _is_degenerate_completion("   ", 0) is True
        assert _is_degenerate_completion("I", 1) is True
        assert _is_degenerate_completion("Sure", 2) is True

    def test_absent_usage_is_not_evidence_of_a_stub(self) -> None:
        """``completion_tokens == 0`` means "the provider reported no usage".

        The wrapper response defaults the field to 0, so a body-length-only
        rule would reject any short text a usage-less transport returns — and
        no character threshold separates a stub ("I", "Sure", "Here") from a
        terse real answer. With no token count the function defers to the R361
        empty-body failure and the structural-truncation guard.
        """
        from app.engines._graph_rag_impl import _is_degenerate_completion

        assert _is_degenerate_completion("ok.", 0) is False
        assert _is_degenerate_completion("Article 14 applies.", 0) is False

    def test_a_real_answer_is_never_degenerate(self) -> None:
        from app.engines._graph_rag_impl import _is_degenerate_completion

        answer = (
            "Article 14 requires human oversight for high-risk AI systems. " * 3
        )
        assert _is_degenerate_completion(answer, 60) is False

    def test_a_response_without_the_field_does_not_raise(self) -> None:
        """The response is duck-typed at several seams; reading the attribute
        directly turned a transport quirk into an AttributeError mid-Stage-2.
        """
        from types import SimpleNamespace

        from app.engines.graph_rag import _openai_wrapper_complete_for_graph_rag

        fake = SimpleNamespace(
            text=(
                "Article 17 requires providers of high-risk AI systems to "
                "operate a documented quality management system."
            ),
            error=None,
            model="claude-opus-5",
        )
        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider"
        ) as prov:
            prov.return_value.complete.return_value = fake
            prov.return_value._base_url = "https://wrapper.antifragile-ai.net/v1"
            out = _openai_wrapper_complete_for_graph_rag(
                system="you are an EU AI Act expert",
                user="What does Article 17 require for QMS?",
                max_tokens=400,
                temperature=0.0,
                complex_question=False,
            )
        assert "quality management system" in out


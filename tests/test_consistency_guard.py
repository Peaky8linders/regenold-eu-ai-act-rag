"""R48 — silent-refusal consistency guard tests.

The R47 V2 eval surfaced 9/56 rows where the answer prose contained a
refusal template ("no matching obligation found", "no EU AI Act
references returned", "cannot cite specific articles") while the
``references`` list was non-empty. Two guards address this:

1. Stage-2 self-contradiction guard
   (:func:`app.engines.graph_rag._polished_prose_self_contradicts_refs`)
   — catches it inside the LLM polish.
2. Route-level response-consistency guard — catches it at the final
   response-assembly point regardless of which upstream produced the
   contradiction.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines.graph_rag import (
    _STAGE2_REFUSAL_MARKERS,
    _polished_prose_self_contradicts_refs,
)
from app.main import app
from app.rate_limit import limiter


_EVAL_KEY = "regenold-bench-eval-key"


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def _client():
    prev = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_EVAL_KEY)
    try:
        with TestClient(app, headers={"X-Regenold-Api-Key": _EVAL_KEY}) as c:
            yield c
    finally:
        settings.regenold.api_key = prev


# ── Unit tests for the Stage-2 self-contradiction predicate ─────────────


class _FakeContext:
    """Minimum-viable context shape that
    ``_extract_context_grounded_refs`` can walk."""

    def __init__(self, obligations: list[dict] | None = None) -> None:
        self.obligations = obligations or []
        self.article_info = []
        self.gaps = []


class TestStage2SelfContradictionPredicate:
    def test_no_refs_in_context_means_no_contradiction(self) -> None:
        ctx = _FakeContext(obligations=[])
        prose = "No matching obligation found in the EU AI Act for this question."
        contradicts, _ = _polished_prose_self_contradicts_refs(prose, ctx)
        assert contradicts is False

    def test_grounded_refs_plus_refusal_marker_flags_contradiction(self) -> None:
        ctx = _FakeContext(
            obligations=[{"article": "Art. 51"}, {"article": "Art. 53"}]
        )
        prose = (
            "No matching obligation found in the EU AI Act for this question. "
            "Try rephrasing with a specific Art. reference."
        )
        contradicts, marker = _polished_prose_self_contradicts_refs(prose, ctx)
        assert contradicts is True
        assert marker == "no matching obligation"

    def test_grounded_refs_plus_grounded_answer_no_contradiction(self) -> None:
        ctx = _FakeContext(
            obligations=[{"article": "Art. 13"}, {"article": "Art. 14"}]
        )
        prose = (
            "Article 13 requires providers to ship transparent instructions; "
            "Article 14 imposes human-oversight obligations on the deployer."
        )
        contradicts, _ = _polished_prose_self_contradicts_refs(prose, ctx)
        assert contradicts is False

    def test_every_marker_triggers_the_guard(self) -> None:
        ctx = _FakeContext(obligations=[{"article": "Art. 5"}])
        for marker in _STAGE2_REFUSAL_MARKERS:
            prose = f"Some prefix. {marker}. Some suffix that mentions Article 5."
            contradicts, matched = _polished_prose_self_contradicts_refs(
                prose, ctx
            )
            assert contradicts is True, f"Marker missed: {marker!r}"
            # The matched marker should itself be one of the registered
            # markers — order-of-iteration may surface a shorter
            # substring when markers overlap (e.g. "block provided
            # contains no" is a substring of "references block provided
            # contains no"), which is semantically equivalent.
            assert matched in _STAGE2_REFUSAL_MARKERS, (
                f"Returned marker {matched!r} is not in the registered set"
            )

    def test_none_context_is_safe(self) -> None:
        contradicts, _ = _polished_prose_self_contradicts_refs(
            "No matching obligation found.", None
        )
        assert contradicts is False

    def test_empty_prose_is_safe(self) -> None:
        ctx = _FakeContext(obligations=[{"article": "Art. 5"}])
        contradicts, _ = _polished_prose_self_contradicts_refs("", ctx)
        assert contradicts is False

    def test_marker_is_case_insensitive(self) -> None:
        ctx = _FakeContext(obligations=[{"article": "Art. 5"}])
        prose = "NO MATCHING OBLIGATION FOUND in the EU AI Act."
        contradicts, _ = _polished_prose_self_contradicts_refs(prose, ctx)
        assert contradicts is True


# ── Integration: route-level consistency-guard ──────────────────────────


class TestRouteConsistencyGuard:
    """The route's R48 guard kicks in AFTER all upstream passes.

    These tests hit the wire via TestClient with question shapes that
    R47 V2 showed produced the contradiction. Post-fix, the response
    should never contain a refusal marker when ``references`` is
    non-empty.
    """

    @pytest.mark.parametrize(
        "question",
        [
            # GPAI-shape — V2 tr_v2_003 / 021 / 023 / 024
            "What is the GPAI compute threshold from the Commission's "
            "July 2025 Guidelines?",
            # Conflict-shape — V2 tr_v2_012 / 014
            "If my chatbot is also a high-risk medical-triage AI, does "
            "Article 13 transparency or Article 50 chatbot disclosure apply?",
            # Cross-framework — V2 tr_v2_026
            "Our medical-device AI is already CE-marked under MDR. Do we "
            "still need a separate AI Act conformity assessment?",
        ],
    )
    def test_no_refusal_when_references_non_empty(
        self, _client: TestClient, question: str
    ) -> None:
        resp = _client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": question}],
        )
        assert resp.status_code == 200
        body = resp.json()
        refs = body.get("references") or []
        answer = (body.get("answer") or "").lower()
        # Either refs is empty (no_match / out_of_scope path — fine), OR
        # if refs is non-empty, the answer must NOT contain any refusal
        # marker (the consistency guard would have replaced it).
        if refs:
            offending = [m for m in _STAGE2_REFUSAL_MARKERS if m in answer]
            assert not offending, (
                f"refs={refs} but answer contained refusal markers "
                f"{offending}: {answer!r}"
            )

    def test_clean_in_scope_question_is_unaffected(
        self, _client: TestClient
    ) -> None:
        """The guard is a no-op on questions that produce a coherent
        answer + references pair. The Article 13 transparency probe
        is one of the most reliable in the bench."""
        resp = _client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[
                {
                    "role": "user",
                    "content": "What does Article 13 require?",
                }
            ],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("references"), "Article 13 question must have refs"
        answer = (body.get("answer") or "").lower()
        offending = [m for m in _STAGE2_REFUSAL_MARKERS if m in answer]
        assert not offending, (
            f"Article 13 answer hit unexpected markers {offending}: "
            f"{answer!r}"
        )

    def test_out_of_scope_question_still_refuses(
        self, _client: TestClient
    ) -> None:
        """The guard MUST NOT lift answers on legitimately out-of-scope
        questions. The scope-gate refusal path keeps ``references``
        empty, so the guard's ``if references`` precondition skips it."""
        resp = _client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[
                {
                    "role": "user",
                    "content": "What is the capital of France?",
                }
            ],
        )
        assert resp.status_code == 200
        body = resp.json()
        # Out-of-scope path leaves references empty; the answer is the
        # scope-gate refusal text. The R48 guard doesn't fire here.
        assert not body.get("references"), (
            "Out-of-scope must keep refs empty so the guard doesn't fire"
        )


# ── R49-A integration: guard substitutes KB-grounded prose ──────────────


class TestR49ASubstantiveGuardProse:
    """R49-A replaces the R48 generic 1-sentence template with a
    KB-grounded 1-3 sentence answer that carries substantive tokens
    from each ref's ``EC_CHECKER_OBLIGATION_MAP`` summary.

    The guard call-site itself is exercised by
    ``TestRouteConsistencyGuard`` above (which proves no refusal
    markers leak through). This class adds direct unit-level
    coverage of the substitute prose to lock in the regression fix:
    the new prose MUST carry domain content, not just a citation
    list.
    """

    def test_guard_substitute_carries_substantive_kb_content(self) -> None:
        """When the guard fires, the substitute prose must surface
        tokens from the cited refs' KB summaries — not just the
        article numbers."""
        from app.integrations.regenold.grounded_prose import (
            stitch_grounded_prose,
        )

        # Mirror what the route does post-R49-A: convert user-facing
        # refs to internal form, then stitch.
        wire_refs = ["Article 51", "Article 53"]
        internal: list[str] = []
        for r in wire_refs:
            s = r.strip()
            if s.startswith("Article "):
                internal.append("Art. " + s[len("Article "):])
        substitute = stitch_grounded_prose(internal)

        # Lead sentence has the citation list.
        assert "Article 51" in substitute and "Article 53" in substitute
        # Substantive content from at least one stub. Art. 51 carries
        # 'FLOPs' / 'systemic'; Art. 53 carries 'training' / 'documentation'.
        low = substitute.lower()
        assert any(t in low for t in ("flops", "systemic", "training", "documentation")), (
            f"R49-A substitute lacks domain tokens: {substitute!r}"
        )

    def test_guard_substitute_no_refusal_markers(self) -> None:
        """The whole point of the guard is removing refusal markers;
        the R49-A substitute must not re-introduce them."""
        from app.integrations.regenold.grounded_prose import (
            stitch_grounded_prose,
        )
        for refs in (
            ["Art. 13"],
            ["Art. 13", "Art. 14"],
            ["Art. 51", "Art. 53", "Art. 55"],
            ["Art. 27"],
            ["Art. 5"],
        ):
            substitute = stitch_grounded_prose(refs)
            low = substitute.lower()
            offending = [m for m in _STAGE2_REFUSAL_MARKERS if m in low]
            assert not offending, (
                f"R49-A substitute for {refs} contains refusal markers "
                f"{offending}: {substitute!r}"
            )

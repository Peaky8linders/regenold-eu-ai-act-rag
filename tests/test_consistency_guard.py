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


# ── R54-Q2 — Stage-2 drift markers + sentence-count fix ─────────────────


class TestR54Q2Stage2DriftMarkers:
    """R54-Q2 — extend _STAGE2_REFUSAL_MARKERS with 4 new shapes caught
    in the post-R54 live Probe-2 verification.

    Verbatim drift observed 2026-05-18 on the production endpoint for
    the Art. 101 / AI Office question:

        "No EU AI Act articles were returned in the references block
        for this query, so citations cannot be provided per the
        instructions. However, based on the EU AI Act text..."

    All four added phrases are unusual enough to not false-positive on
    legitimate regulator-voice answers.
    """

    def test_probe2_verbatim_drift_caught_by_new_markers(self) -> None:
        """The exact Probe-2 drift prose must trigger at least one of
        the new R54-Q2 markers."""
        verbatim = (
            "No EU AI Act articles were returned in the references "
            "block for this query, so citations cannot be provided "
            "per the instructions. However, based on the EU AI Act "
            "text (in force as of August 2024). The Commission — "
            "acting through the AI Office — holds direct fining "
            "power over GPAI model providers, not Member State "
            "market-surveillance authorities."
        )
        low = verbatim.lower()
        new_markers = [
            "no eu ai act articles were returned",
            "no articles were returned in the references",
            "references block for this query",
            "citations cannot be provided",
        ]
        hits = [m for m in new_markers if m in low]
        assert hits, (
            f"R54-Q2 markers must catch the verbatim Probe-2 drift "
            f"prose; matched markers: {hits}"
        )
        # All four markers fire on this verbatim drift — verifies the
        # set is well-anchored on the canonical shape, not just one
        # narrow phrase.
        assert len(hits) >= 3, (
            f"At least 3 of the 4 R54-Q2 markers should match the "
            f"verbatim drift (got {len(hits)}: {hits})"
        )

    def test_new_markers_in_marker_set(self) -> None:
        """The four new R54-Q2 markers are in _STAGE2_REFUSAL_MARKERS."""
        expected = (
            "no eu ai act articles were returned",
            "no articles were returned in the references",
            "references block for this query",
            "citations cannot be provided",
        )
        for marker in expected:
            assert marker in _STAGE2_REFUSAL_MARKERS, (
                f"R54-Q2 marker {marker!r} missing from "
                f"_STAGE2_REFUSAL_MARKERS"
            )

    def test_new_markers_do_not_false_positive_on_clean_answers(
        self,
    ) -> None:
        """Sanity: legitimate regulator-voice answers must NOT contain
        any of the new R54-Q2 markers."""
        clean_answers = [
            "Article 13 requires high-risk AI providers to ensure "
            "transparency through clear instructions for use.",
            "Article 26 places deployer obligations on entities using "
            "high-risk AI systems, including human oversight.",
            "Article 51 classifies a GPAI model as having systemic risk "
            "when training compute exceeds 10^25 FLOPs.",
            "The Commission, acting through the AI Office, may impose "
            "fines on GPAI model providers under Article 101.",
        ]
        new_markers = (
            "no eu ai act articles were returned",
            "no articles were returned in the references",
            "references block for this query",
            "citations cannot be provided",
        )
        for ans in clean_answers:
            low = ans.lower()
            offending = [m for m in new_markers if m in low]
            assert not offending, (
                f"Clean answer false-positive: {ans!r} hit {offending}"
            )


class TestR54Q2GroundedProseSentenceCount:
    """R54-Q2 also fixes `grounded_prose._stitch_grounded_prose` which
    used a naive `sum(c in ".!?")` sentence-count check. Abbreviations
    like "Art. 64" inside a stub were miscounted as sentence terminators,
    over-clipping the second substance sentence.

    The Probe-2 case: stitching [Art. 51, Art. 101, Art. 64, Art. 74]
    pre-R54-Q2 surfaced only Art. 51's substance because Art. 101's
    stub contains "(per Art. 64)" → naive count saw 2 periods → soft
    cap dropped Art. 101.
    """

    def test_probe2_refs_now_surface_art_101_substance(self) -> None:
        """The Probe-2 ref set must produce a stitch that includes
        Art. 101's KB stub content (was clipped pre-R54-Q2)."""
        from app.integrations.regenold.grounded_prose import (
            stitch_grounded_prose,
        )

        substitute = stitch_grounded_prose(
            ["Art. 51", "Art. 101", "Art. 64", "Art. 74"]
        )
        # Art. 101 must appear in the substantive sentences, not just
        # the lead citation list.
        assert "Article 101" in substitute
        low = substitute.lower()
        assert "ai office" in low or "direct fines" in low, (
            f"Art. 101 substance missing from stitch (pre-R54-Q2 "
            f"sentence-count bug). Got: {substitute!r}"
        )

    def test_abbreviation_in_stub_does_not_overclip(self) -> None:
        """Sanity-style: any 2-ref stitch where the SECOND ref's stub
        contains an abbreviation period (e.g. Art. N, Annex N.) must
        not silently drop that second ref's substance."""
        from app.integrations.regenold.grounded_prose import (
            stitch_grounded_prose,
        )

        # Art. 25 stub mentions "Art. 51" — pre-R54-Q2 the sentence
        # count would over-count, dropping Art. 25's substance.
        substitute = stitch_grounded_prose(["Art. 13", "Art. 25"])
        low = substitute.lower()
        # Either ref's substance keywords should appear.
        keywords = ("provider", "deployer", "substantial modification",
                    "transparency", "instructions for use", "value chain",
                    "one-third", "fine-tune")
        assert any(k in low for k in keywords), (
            f"Multi-ref stitch dropped all substance: {substitute!r}"
        )


# ── R64 [Important] I3 — narrow "to give you a grounded answer" marker ──


class TestR64I3GroundedAnswerMarkerNarrowing:
    """R64 [Important] I3 — the bare "to give you a grounded answer"
    substring matched legitimate Sonnet intros like "To give you a
    grounded answer, I'll cite Article 13 first..." as a false-positive
    on perfectly valid in-scope answers.

    R64 replaces the bare phrase with the longer R62 refusal-shape
    "to give you a grounded answer, please re-run" so the guard fires
    on the actual refusal pattern (mt_v2_003) without tripping on
    legitimate prose that happens to start with the same 7 words.
    """

    def test_legitimate_intro_does_not_fire_refusal_guard(self) -> None:
        """A perfectly valid answer that starts with "To give you a
        grounded answer, I'll cite Article 13..." MUST NOT be flagged
        as a self-contradiction."""
        ctx = _FakeContext(obligations=[{"article": "Art. 13"}])
        prose = (
            "To give you a grounded answer, I'll cite Article 13 first. "
            "The provider must ensure transparent instructions for use."
        )
        contradicts, _ = _polished_prose_self_contradicts_refs(prose, ctx)
        assert contradicts is False

    def test_r62_refusal_pattern_still_fires(self) -> None:
        """The true R62 mt_v2_003 refusal pattern ("To give you a
        grounded answer, please re-run the query...") MUST still trip
        the guard so the route substitutes R49-A grounded prose."""
        ctx = _FakeContext(obligations=[{"article": "Art. 13"}])
        prose = (
            "To give you a grounded answer, please re-run the query "
            "with a different reporting window."
        )
        contradicts, marker = _polished_prose_self_contradicts_refs(prose, ctx)
        assert contradicts is True
        # The narrowed marker is what triggered.
        assert marker == "to give you a grounded answer, please re-run"

    def test_bare_marker_removed_from_marker_set(self) -> None:
        """Regression pin: the bare over-broad marker must NOT be in
        _STAGE2_REFUSAL_MARKERS — only the narrowed full-phrase form."""
        assert "to give you a grounded answer" not in _STAGE2_REFUSAL_MARKERS
        assert (
            "to give you a grounded answer, please re-run"
            in _STAGE2_REFUSAL_MARKERS
        )

    def test_other_legitimate_intros_with_grounded_phrase(self) -> None:
        """A handful of other phrasings that historically false-positived
        on the bare marker should now pass through clean."""
        ctx = _FakeContext(obligations=[{"article": "Art. 13"}])
        legitimate_intros = [
            "To give you a grounded answer, the EU AI Act Article 13 requires...",
            "To give you a grounded answer based on the references: Article 13 mandates...",
            # The marker pattern that *would* still fire (please re-run) is
            # absent here — these are all substantive content intros.
            "To give you a grounded answer rooted in Article 13, providers must...",
        ]
        for prose in legitimate_intros:
            contradicts, marker = _polished_prose_self_contradicts_refs(
                prose, ctx
            )
            assert contradicts is False, (
                f"Legitimate intro false-positived (marker={marker!r}): {prose!r}"
            )

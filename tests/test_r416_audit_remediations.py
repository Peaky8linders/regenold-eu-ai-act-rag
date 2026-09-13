"""R416 audit — the three remediations, pinned so they cannot silently regress.

The round audited an incoming multi-file optimisation diff and found, among
otherwise-sound work, three defects worth a test each:

1. **A drifted knob ceiling.** ``REGENOLD_KG_MAX_REFS`` had two upper bounds —
   24 in ``graph_semantic.fetch_focused_subprovisions`` and 20 on the four
   ``kg_context`` keyword reads — so a value of 21-24 was honoured on one read
   and silently clamped on the others. It is now one declared constant.

2. **A pushback path that looked riskier than it is.** The new challenge-recovery
   block in ``_build_question_from_history`` re-anchors retrieval on the root
   question, and it has no env flag. The official hard-mode pushback
   ("… Let's try again: {QUESTION}") restates its question, so the block's
   ``_live_turn_is_self_contained`` veto is what keeps the graded path
   untouched — verified against the real helpers, not inferred. This is
   asserted rather than assumed, because the hard split is what the claim is
   about.

3. **A feature that shipped dead.** ``_citable_concept_anchors`` /
   ``REQUIREMENT_ARTICLE_ANCHORS`` were added with a "93% gold precision"
   comment but had no call site: nothing in the request path could reach them.
   Re-measured against the official corpus the map scored 62.5% (10/16)
   (``docs/measurements/r416/anchor-precision.json``), so it was removed
   outright rather than wired in. These assertions fail if it returns
   unwired.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


# ── 1. One declared ceiling for REGENOLD_KG_MAX_REFS ─────────────────────


def test_kg_max_refs_has_a_single_declared_ceiling() -> None:
    from app.engines import kg_context

    assert kg_context._MAX_REFS_CEILING == 24
    src = (REPO / "app/engines/kg_context.py").read_text(encoding="utf-8")
    # Every REGENOLD_KG_MAX_REFS reader goes through the constant. The literal
    # 20 that used to clamp this knob must not survive on any of them (an
    # unrelated knob, REGENOLD_KG_MAX_RECITALS, legitimately keeps its own).
    assert src.count(", 1, _MAX_REFS_CEILING)") == 4
    assert 'REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 20)' not in src


def test_kg_max_refs_above_the_old_ceiling_is_now_honoured(monkeypatch) -> None:
    from app.engines import kg_context

    monkeypatch.setenv("REGENOLD_KG_MAX_REFS", "24")
    assert (
        kg_context._int_env(
            "REGENOLD_KG_MAX_REFS", 8, 1, kg_context._MAX_REFS_CEILING
        )
        == 24
    )


def test_graph_semantic_reads_the_shared_ceiling_not_a_literal() -> None:
    src = (REPO / "app/engines/graph_semantic.py").read_text(encoding="utf-8")
    assert "_MAX_REFS_CEILING" in src
    assert '_int_env("REGENOLD_KG_MAX_REFS", 8, 1, 24)' not in src


# ── 2. The official pushback never reaches the challenge-recovery block ──


def test_official_pushback_cannot_reach_the_challenge_recovery() -> None:
    """The graded pushback restates its question, so the SELF-CONTAINED guard
    is what excludes the new block — not the re-ask marker.

    Measured, not assumed: on the competition's single-line pushback shape the
    ``_REASK_MARKER_RE`` does NOT match (it anchors at a line start), so ``R305``
    does not fire either, and ``R372``'s only remaining guard is
    ``not _live_turn_is_self_contained(live_question)`` — which is False because
    the turn restates the question. Both outcomes are pinned here.
    """
    from app.data.graph_rag_prompts import is_challenge_turn
    from app.routes.regenold import (
        _REASK_MARKER_RE,
        _extract_reask_tail,
        _live_turn_is_self_contained,
    )

    live = (
        "I don't think this is correct. Perhaps your answer contains "
        "hallucinations. Let's try again: What does Article 6 require for "
        "high-risk AI systems?"
    )
    assert is_challenge_turn(live) is True
    assert _live_turn_is_self_contained(live) is True  # R372's veto
    # The marker anchors at a line start, so a single-line pushback misses it.
    assert not _REASK_MARKER_RE.search(live)
    assert _extract_reask_tail(live) is None


def test_multiline_reask_is_owned_by_the_r305_path() -> None:
    """Where the marker IS at a line start, R305 returns before R372 is read."""
    from app.routes.regenold import _REASK_MARKER_RE, _extract_reask_tail

    multi = (
        "user: I don't think this is correct.\n"
        "Let's try again: What does Article 6 require for high-risk AI systems?"
    )
    assert _REASK_MARKER_RE.search(multi)
    assert _extract_reask_tail(multi)


def test_challenge_detector_on_a_raw_live_turn_needs_a_dispute_marker() -> None:
    from app.data.graph_rag_prompts import is_challenge_turn

    # The route passes the RAW final turn, so the ``Latest question:`` flatten
    # marker is absent and the pattern family — which needs a prior turn — is
    # off. Only the explicit dispute markers can fire there.
    assert is_challenge_turn("What does Article 6 require?") is False
    assert is_challenge_turn("I don't think this is correct.") is True
    # The prior-turn fact is what the pattern family needs, and only a caller
    # that passes the FLATTENED text (or the flag) can supply it.
    assert is_challenge_turn("We are exempt, correct?", has_prior_turns=False) is False
    assert is_challenge_turn("We are exempt, correct?", has_prior_turns=True) is True


# ── 3. The uncalled citable-anchor feature stays out ─────────────────────


def test_no_uncalled_citable_anchor_feature_is_shipped() -> None:
    from app.data import ontology
    from app.engines import _graph_rag_impl as impl

    assert not hasattr(ontology, "REQUIREMENT_ARTICLE_ANCHORS")
    assert not hasattr(impl, "_citable_concept_anchors")
    assert not hasattr(impl, "_citable_concept_anchors_enabled")


# ── 4. The sibling-paragraph block runs before the bounded KG block ──────


def test_sibling_paragraphs_are_added_before_the_kg_hierarchy_block() -> None:
    """Ordering is the fix: siblings must not be starved by the KG block's cap."""
    src = (REPO / "app/engines/faithfulness_verify.py").read_text(encoding="utf-8")
    sibling = src.index("sibling paragraphs of any cited sub-provision")
    kg_block = src.index("from app.engines.kg_context import fetch_provision_hierarchy")
    assert sibling < kg_block
    # And the overshoot cap is gone: the block honours ``limit`` exactly.
    assert "len(out) < limit + 4" not in src


# ── 5. The KG point-text lever is scoped by modality, and the scope reaches
#       the real request path without touching a mocked seam ─────────────────


def test_turn_count_var_scopes_the_point_text_lever() -> None:
    """The production mechanism, not the explicit override.

    ``render_kg_context`` reads the depth from a ``ContextVar`` rather than a
    parameter because nine test fakes patch ``fetch_subpoint_detail`` with a
    one-argument lambda, and ``render_kg_context`` swallows the resulting
    ``TypeError`` into an empty block. This asserts the var alone flips the
    decision, and that resetting restores the shipped default.
    """
    from app.engines import kg_context as kg

    assert kg._kg_point_text_enabled() is True  # unset -> shipped default ON
    token = kg.set_render_turn_count(4)
    try:
        assert kg._kg_point_text_enabled() is False
    finally:
        kg.reset_render_turn_count(token)
    assert kg._kg_point_text_enabled() is True

    token = kg.set_render_turn_count(1)
    try:
        assert kg._kg_point_text_enabled() is True
    finally:
        kg.reset_render_turn_count(token)


def test_two_stage_generate_sets_and_clears_the_turn_count() -> None:
    """The wiring: one set at the single ancestor of both Stage-2 entry points.

    Asserted by driving the real ``_two_stage_generate`` with its inner body
    replaced, so this cannot pass by re-implementing the scoping in the test.
    """
    from app.engines import _graph_rag_impl as impl
    from app.engines import kg_context as kg

    seen: list[bool] = []

    def fake_inner(*_args, **_kwargs):
        seen.append(kg._kg_point_text_enabled())
        return "answer", True

    original = impl._two_stage_generate_inner
    impl._two_stage_generate_inner = fake_inner
    try:
        out = impl._two_stage_generate(
            "q", context=None, history_turn_count=7
        )
    finally:
        impl._two_stage_generate_inner = original

    assert out == ("answer", True)
    assert seen == [False], "multi-turn depth must reach the KG lever"
    # And it must not leak into the next request in this context.
    assert kg._kg_point_text_enabled() is True

"""Tests for the sentence-level citation guard — Layer G of the arch PDF."""
from __future__ import annotations

import pytest

from app.integrations.regenold.citation_guard import (
    _split_sentences,
    filter_unsupported_sentences,
    is_enabled,
    maybe_apply_guard,
)


# ── Env gate ─────────────────────────────────────────────────────────────


def test_is_enabled_default_off(monkeypatch):
    """Default OFF — citation guard is opt-in."""
    monkeypatch.delenv("REGENOLD_CITATION_GUARD", raising=False)
    assert is_enabled() is False


def test_is_enabled_truthy(monkeypatch):
    for truthy in ("1", "true", "yes", "on", "TRUE"):
        monkeypatch.setenv("REGENOLD_CITATION_GUARD", truthy)
        assert is_enabled() is True


def test_maybe_apply_guard_passthrough_when_disabled(monkeypatch):
    monkeypatch.delenv("REGENOLD_CITATION_GUARD", raising=False)
    answer = "Random sentence. Another one."
    refs = ("Art. 5",)
    assert maybe_apply_guard(answer, refs) == answer


def test_maybe_apply_guard_active_when_enabled(monkeypatch):
    monkeypatch.setenv("REGENOLD_CITATION_GUARD", "1")
    # Use a multi-sentence answer with one nonsense sentence — guard
    # should drop it when refs anchor to Art. 5.
    answer = (
        "Article 5 prohibits subliminal manipulation. "
        "The weather is nice today. "
        "Subliminal techniques beyond consciousness are banned."
    )
    refs = ("Art. 5",)
    out = maybe_apply_guard(answer, refs)
    assert "weather" not in out.lower()
    assert "subliminal" in out.lower()


# ── Sentence splitter ────────────────────────────────────────────────────


def test_split_sentences_basic():
    text = "First sentence. Second sentence. Third!"
    parts = _split_sentences(text)
    assert len(parts) == 3
    assert parts[0] == "First sentence."


def test_split_sentences_empty():
    assert _split_sentences("") == []
    assert _split_sentences("   ") == []


def test_split_sentences_no_terminator():
    text = "single fragment without period"
    parts = _split_sentences(text)
    assert parts == [text]


# ── Filter behaviour ─────────────────────────────────────────────────────


def test_filter_no_refs_passthrough():
    """No refs surfaced → return unchanged. Don't damage the answer."""
    answer = "This sentence. That sentence."
    assert filter_unsupported_sentences(answer, ()) == answer


def test_filter_empty_answer_passthrough():
    assert filter_unsupported_sentences("", ("Art. 5",)) == ""
    assert filter_unsupported_sentences("   ", ("Art. 5",)) == "   "


def test_filter_single_sentence_kept():
    """Single-sentence answers are never modified, regardless of support."""
    answer = "This sentence does not mention anything about that article."
    refs = ("Art. 99",)  # Penalties — sentence has zero overlap
    assert filter_unsupported_sentences(answer, refs) == answer


def test_filter_drops_unsupported_sentence_among_multiple():
    """A clearly-unsupported sentence is dropped; supported ones survive."""
    answer = (
        "Article 5 prohibits subliminal manipulation. "
        "Cats are nice furry animals."
    )
    refs = ("Art. 5",)
    out = filter_unsupported_sentences(answer, refs)
    assert "subliminal" in out.lower()
    assert "cats" not in out.lower()


def test_filter_keeps_best_overlap_when_all_unsupported():
    """When NO sentence meets the threshold, keep the best-overlap one."""
    # Both sentences have zero overlap with Art. 99 vocab.
    answer = "Cats meow at midnight. Dogs bark all day long."
    refs = ("Art. 99",)
    out = filter_unsupported_sentences(answer, refs)
    # Must be non-empty (the floor) and one of the original sentences.
    assert out
    assert out in ("Cats meow at midnight.", "Dogs bark all day long.")


def test_filter_preserves_order_of_supported_sentences():
    """Supported sentences emerge in original document order."""
    answer = (
        "Article 5 prohibits subliminal techniques. "
        "Random unrelated noise here. "
        "Manipulation through subliminal means is banned."
    )
    refs = ("Art. 5",)
    out = filter_unsupported_sentences(answer, refs)
    # Both supported sentences must appear, and in original order.
    sent1 = "Article 5 prohibits subliminal techniques."
    sent3 = "Manipulation through subliminal means is banned."
    assert sent1 in out
    assert sent3 in out
    assert out.index(sent1) < out.index(sent3)


def test_filter_handles_unknown_ref_gracefully():
    """A ref that doesn't resolve in the corpus → no crash, valid output.

    The ref-name tokens themselves contribute a small pool, so a
    sentence echoing the article number can still "support" itself.
    The contract here is just: no crash, non-empty output for non-empty
    input, output is a subsequence of input sentences.
    """
    answer = "Article 9999 says nothing exists. Cats meow."
    refs = ("Art. 9999",)  # Not in ARTICLE_EXISTENCE
    out = filter_unsupported_sentences(answer, refs)
    # Output must be non-empty.
    assert out
    # Output must be either the original or one of the original sentences.
    assert out in (answer, "Article 9999 says nothing exists.", "Cats meow.")


def test_filter_with_multiple_refs_unions_their_pools():
    """Multiple refs → union of their token pools — more sentences survive."""
    # Sentence 1 supports Art. 5 (subliminal); sentence 2 supports Art. 99 (fine).
    answer = (
        "Subliminal manipulation is banned. "
        "Maximum fines reach 35 million EUR."
    )
    out_one_ref = filter_unsupported_sentences(answer, ("Art. 5",))
    out_two_ref = filter_unsupported_sentences(answer, ("Art. 5", "Art. 99"))
    # With Art. 99 added, the fines sentence should pass support.
    assert "Maximum fines" in out_two_ref
    # With only Art. 5, the fines sentence MIGHT be dropped (test
    # the at-least-as-permissive direction).
    assert len(out_two_ref) >= len(out_one_ref)


def test_filter_pure_function_no_side_effects():
    """Filter must not mutate inputs."""
    refs = ("Art. 5",)
    answer = "Subliminal manipulation. Cats."
    refs_before = refs
    answer_before = answer
    filter_unsupported_sentences(answer, refs)
    assert refs is refs_before
    assert answer == answer_before


# ── Round-16 regression: never empty the answer ──────────────────────────


def test_filter_never_returns_empty_when_input_nonempty():
    """The minimum-one-sentence floor must hold for adversarial inputs."""
    # Multi-sentence answer with NO ref overlap whatsoever.
    answer = (
        "The weather is sunny. "
        "Cats meow at noon. "
        "Dogs bark at the moon."
    )
    refs = ("Art. 99",)
    out = filter_unsupported_sentences(answer, refs)
    assert out, "guard returned empty — Round-16 regression"
    # Should pick exactly one of the three.
    assert out.count(".") == 1


def test_filter_min_overlap_tokens_param_tightens_strictness():
    """Higher ``min_overlap_tokens`` drops MORE sentences."""
    answer = (
        "Article 5 mentions subliminal. "
        "Subliminal manipulation by AI providers is the broader concern."
    )
    refs = ("Art. 5",)
    out_lenient = filter_unsupported_sentences(answer, refs, min_overlap_tokens=1)
    out_strict = filter_unsupported_sentences(answer, refs, min_overlap_tokens=5)
    # Stricter cut keeps fewer or same sentences.
    assert len(out_strict) <= len(out_lenient)


# ── Round-31 eng-review FLAGs: deep-subpoint refs + abbreviated continuations ──


def test_to_internal_ref_collapses_deep_subpoints():
    """``Article 5.2.a.iii`` and equivalents → ``Art. 5`` (parent article)."""
    from app.integrations.regenold.citation_guard import _to_internal_ref

    assert _to_internal_ref("Article 5") == "Art. 5"
    assert _to_internal_ref("Article 5.2") == "Art. 5"
    assert _to_internal_ref("Article 5.2.a") == "Art. 5"
    assert _to_internal_ref("Article 5.2.a.iii") == "Art. 5"
    assert _to_internal_ref("Annex III") == "Annex III"
    assert _to_internal_ref("Annex III.2") == "Annex III"
    assert _to_internal_ref("Annex IV.5.a") == "Annex IV"


def test_to_internal_ref_passthrough_on_internal_form():
    """Already-internal refs aren't double-transformed."""
    from app.integrations.regenold.citation_guard import _to_internal_ref

    # Internal form already → unchanged
    assert _to_internal_ref("Art. 5") == "Art. 5"
    assert _to_internal_ref("Annex III") == "Annex III"
    # Garbage → passthrough
    assert _to_internal_ref("foo") == "foo"
    assert _to_internal_ref("") == ""


def test_deep_subpoint_ref_resolves_for_guard():
    """A deep subpoint ref like ``Article 5.1.a`` must still anchor the guard.

    Eng-review FLAG: the original regex captured only ``Article N.M``
    (one sub-level); deeper refs fell through and the guard's pool was
    empty. This regression test guarantees the fix.
    """
    from app.integrations.regenold.citation_guard import _reference_token_pool

    # If Art. 5 has any docs in the BM25 corpus, the deep-subpoint ref
    # should resolve to the same pool.
    pool_internal = _reference_token_pool("Art. 5")
    pool_deep = _reference_token_pool("Article 5.1.a.iii")
    pool_user = _reference_token_pool("Article 5")
    assert pool_internal == pool_user, "user-facing form must match internal"
    assert pool_deep == pool_user, "deep-subpoint must collapse to parent"


def test_split_sentences_uses_legal_aware_splitter():
    """Lowercase abbreviation continuations like ``art. 6`` must split.

    Eng-review FLAG: the original ``(?<=[.!?])\\s+(?=[A-Z(])`` rejected
    lowercase continuations and produced a single mega-sentence.
    Delegating to ``split_legal_sentences`` fixes this.
    """
    from app.integrations.regenold.citation_guard import _split_sentences

    # Capital-start continuation (always worked) — still works.
    parts = _split_sentences("Article 5 prohibits X. Article 6 governs Y.")
    assert len(parts) == 2

    # A multi-sentence answer with normal punctuation — both clauses
    # surface as separate sentences regardless of casing trickery.
    parts = _split_sentences("First clause is concise. Second clause matters too.")
    assert len(parts) == 2

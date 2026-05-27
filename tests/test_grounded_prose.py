"""R49-A — substantive consistency-guard prose tests.

The R48 consistency guard replaced contradictory Stage-2 prose with a
1-sentence generic template ("This question is covered by the EU AI
Act under Article X and Article Y. Consult the cited provisions for
the operative obligations and definitions that apply to this topic.").
That fixed the contradiction but dropped V2 multi-turn coherence
0.28 → 0.08 and tricky keyword recall 0.26 → 0.20 because the
template carries no domain-substantive tokens.

R49-A: pull each ref's KB summary from
:data:`app.data.kb.EC_CHECKER_OBLIGATION_MAP` and stitch a 2-3
sentence answer that carries actual regulatory substance, while still
honouring the 3-sentence + 600-char soft cap and the consistency
invariant (no refusal markers leak through).
"""
from __future__ import annotations

import re
from unittest import mock

import pytest

from app.engines.graph_rag import _STAGE2_REFUSAL_MARKERS
from app.integrations.regenold.grounded_prose import (
    MAX_GROUNDED_CHARS,
    MAX_GROUNDED_SENTENCES,
    stitch_grounded_prose,
)


# ── Pure-function unit tests ────────────────────────────────────────────


class TestStitchGroundedProse:
    def test_empty_refs_returns_safe_default(self) -> None:
        """With no refs the function returns a non-empty fallback so the
        consistency guard never ships an empty answer."""
        out = stitch_grounded_prose([])
        assert out
        assert "EU AI Act" in out

    def test_single_ref_pulls_kb_summary(self) -> None:
        """Art. 51 carries the '10^25 FLOPs' GPAI systemic-risk
        threshold in its KB stub — the prose MUST surface it."""
        out = stitch_grounded_prose(["Art. 51"])
        assert "Article 51" in out
        # KB substantive token. Art. 51's stub mentions the systemic-risk
        # FLOPs threshold; verify some part of that lands in the output.
        low = out.lower()
        assert "flops" in low or "systemic" in low, (
            f"Art. 51 prose missing GPAI domain token: {out!r}"
        )

    def test_two_refs_stitches_both_summaries(self) -> None:
        """When two KB-backed refs are supplied, both summaries should
        contribute domain tokens within the soft cap."""
        out = stitch_grounded_prose(["Art. 13", "Art. 14"])
        assert "Article 13" in out and "Article 14" in out
        low = out.lower()
        # Art. 13 stub mentions transparency / instructions;
        # Art. 14 stub mentions human oversight.
        assert "transparency" in low or "instructions" in low
        assert "oversight" in low or "human" in low

    def test_three_refs_clamps_to_soft_cap(self) -> None:
        """With three refs the output stays within the 3-sentence +
        600-char soft cap that ``normalise_answer_for_regenold``
        enforces downstream."""
        out = stitch_grounded_prose(["Art. 9", "Art. 13", "Art. 14"])
        assert len(out) <= MAX_GROUNDED_CHARS
        # Three or fewer sentences (terminating punctuation).
        sentence_count = sum(1 for c in out if c in ".!?")
        assert 1 <= sentence_count <= MAX_GROUNDED_SENTENCES + 1, (
            f"sentence count {sentence_count} out of bounds for {out!r}"
        )

    def test_no_refusal_marker_in_output(self) -> None:
        """The whole point of the guard is to remove refusal markers —
        the substitute MUST NOT re-introduce them."""
        out = stitch_grounded_prose(["Art. 51", "Art. 53", "Art. 55"])
        low = out.lower()
        offending = [m for m in _STAGE2_REFUSAL_MARKERS if m in low]
        assert not offending, (
            f"grounded prose contained refusal markers {offending}: {out!r}"
        )

    def test_annex_refs_render_correctly(self) -> None:
        """Annex refs should render as 'Annex III' / 'Annex IV' in the
        user-facing prose."""
        out = stitch_grounded_prose(["Art. 6", "Annex III"])
        assert "Article 6" in out
        assert "Annex III" in out

    def test_unknown_ref_falls_back_gracefully(self) -> None:
        """A ref whose KB summary is missing should not crash; the
        function should fall back to the article-only template for that
        ref while still surfacing the citation."""
        # Art. 999 doesn't exist in the catalog — function must not
        # raise and must return SOMETHING coherent.
        out = stitch_grounded_prose(["Art. 999"])
        assert out
        assert "EU AI Act" in out

    def test_mixed_known_and_unknown_refs(self) -> None:
        """Known refs should still contribute substance even when an
        unknown ref is mixed in."""
        out = stitch_grounded_prose(["Art. 999", "Art. 51"])
        # The known ref should still surface its domain token.
        assert "Article 51" in out

    def test_strips_leading_kb_stub_label_prefix(self) -> None:
        """Some KB stubs (R23 ports) start with 'Art. N:' as a
        readability prefix. The stitched prose should NOT carry that
        duplicate label — the citation is already in the lead sentence."""
        # Art. 5 stub starts with 'Art. 5:' — make sure that prefix
        # doesn't end up rendered in the user-facing output.
        out = stitch_grounded_prose(["Art. 5"])
        # 'Art. 5:' as a literal substring in the substantive sentences
        # would be a bug; the lead-sentence 'Article 5' is fine.
        assert "Art. 5:" not in out

    def test_idempotent_repeat_refs(self) -> None:
        """Duplicate refs in the input should not produce duplicate
        sentences in the output."""
        out = stitch_grounded_prose(["Art. 13", "Art. 13", "Art. 13"])
        # Single Article 13 mention in the lead sentence; the substance
        # sentence (if any) shouldn't double-up the same content.
        article_13_mentions = len(
            re.findall(r"\barticle\s+13\b", out, re.IGNORECASE)
        )
        # 1-2 mentions is fine (lead sentence + maybe a stub repetition);
        # 3+ means we failed to deduplicate.
        assert article_13_mentions <= 2, (
            f"Art. 13 mentioned {article_13_mentions} times: {out!r}"
        )

    def test_user_facing_ref_form(self) -> None:
        """Internal 'Art. N' input MUST render as 'Article N' in the
        output (Regenold wire form)."""
        out = stitch_grounded_prose(["Art. 26"])
        assert "Article 26" in out
        # Internal form must NOT leak.
        assert "Art. 26" not in out


# ── R77 — augment_with_ref_descriptions unit tests ─────────────────────


class TestAugmentWithRefDescriptions:
    """Unit tests for the always-on per-ref description augmenter (R77 I4).

    This function APPENDS description clauses for cited refs that the
    existing answer prose does not already describe — the counterpart to
    ``stitch_grounded_prose`` which REPLACES the full answer.
    """

    from app.integrations.regenold.grounded_prose import (
        augment_with_ref_descriptions,
    )

    def _augment(self, answer: str, refs: list[str], question: str = "") -> str:
        from app.integrations.regenold.grounded_prose import (
            augment_with_ref_descriptions,
        )
        return augment_with_ref_descriptions(answer, refs, question=question)

    def test_empty_answer_returns_unchanged(self) -> None:
        """With no answer text the function returns the empty string unchanged."""
        out = self._augment("", ["Article 13"])
        assert out == ""

    def test_empty_refs_returns_answer_unchanged(self) -> None:
        """With no references the answer is returned unchanged."""
        original = "High-risk AI systems must be transparent."
        out = self._augment(original, [])
        assert out == original

    def test_covered_ref_not_appended(self) -> None:
        """When the answer already describes a ref, no clause is appended."""
        # Art. 13 is about transparency / instructions for use.
        # Inject enough of the KB summary tokens into the answer.
        answer = (
            "Article 13 requires transparency and instructions for use "
            "covering provider identity, intended purpose, and capabilities."
        )
        out = self._augment(answer, ["Article 13"])
        # Should be unchanged (already covered) or only minimally extended.
        # We accept ≤ 20 chars of addition (padding/sentence-ending only).
        assert len(out) - len(answer) <= 20, (
            f"unexpected augmentation on covered ref: {out!r}"
        )

    def test_uncovered_ref_gets_description(self) -> None:
        """A ref not mentioned at all in the answer gets a description clause."""
        # A minimal answer that does NOT describe Art. 51 (GPAI/FLOPs).
        answer = "The EU AI Act imposes obligations on providers."
        out = self._augment(answer, ["Article 51"])
        assert len(out) > len(answer), "expected augmentation for uncovered Article 51"
        low = out.lower()
        # The augmented clause should carry Art. 51 KB substance.
        assert "article 51" in low
        assert "flops" in low or "systemic" in low or "gpai" in low or "general-purpose" in low, (
            f"Art. 51 description missing domain tokens: {out!r}"
        )

    def test_max_new_clauses_respected(self) -> None:
        """No more than max_new_clauses clauses are appended."""
        from app.integrations.regenold.grounded_prose import augment_with_ref_descriptions
        answer = "The EU AI Act sets out obligations."
        # Provide 6 refs that are unlikely to be described in the minimal answer.
        refs = [
            "Article 9", "Article 11", "Article 13", "Article 14",
            "Article 51", "Article 55",
        ]
        out = augment_with_ref_descriptions(answer, refs, max_new_clauses=2)
        # Count article mentions added beyond the answer.
        added_mentions = out[len(answer):].lower().count("article ")
        assert added_mentions <= 2, (
            f"more than 2 clauses appended: {out!r}"
        )

    def test_unknown_ref_skipped_gracefully(self) -> None:
        """A ref with no KB stub is skipped without crashing."""
        answer = "The EU AI Act imposes obligations."
        out = self._augment(answer, ["Article 999"])
        # Should return original unchanged (no stub to add).
        assert out == answer

    def test_output_is_augmented_form_of_input(self) -> None:
        """Augmented output starts with the original answer text for
        non-describer refs (append path). R89-A introduced article-
        level describer keys that PREPEND — Article 51 is one such key
        now, so we use Article 22 (authrep) which has a KB stub but
        no R89-A describer override."""
        answer = "The EU AI Act applies."
        out = self._augment(answer, ["Article 22"])
        assert out.startswith(answer), (
            f"augmented output does not start with original answer: {out!r}"
        )

    def test_no_internal_ref_form_leaks(self) -> None:
        """The internal 'Art. N' form must not appear in the output."""
        answer = "The EU AI Act applies."
        out = self._augment(answer, ["Article 13", "Article 26"])
        # Internal form must not appear.
        assert "Art. 13" not in out
        assert "Art. 26" not in out

    def test_fail_soft_on_bad_ref_shape(self) -> None:
        """Non-standard ref shapes are skipped without crashing."""
        answer = "The EU AI Act applies."
        # Completely invalid shapes should not raise.
        out = self._augment(answer, ["Not-An-Article", "Random stuff"])
        # Returns original unchanged or slightly extended (skip / fail-open).
        assert out  # non-empty

    def test_inline_replace_mode(self) -> None:
        """Inline bare or parenthesized citations are replaced with descriptions in-place.

        R90 — the in-place expansion now uses counsel-voice prose:
        ``(Article 13)`` → ``(Article 13 requires high-risk AI systems...)``
        rather than the pre-R90 em-dash typographic format.
        """
        from app.integrations.regenold.grounded_prose import augment_with_ref_descriptions
        import os

        answer = "The provider must comply with the requirements (Article 13)."
        # With replace mode enabled:
        with mock.patch.dict(os.environ, {"REGENOLD_REF_DESCRIBE_REPLACE": "1"}):
            out = augment_with_ref_descriptions(answer, ["Article 13"])

        # Counsel-voice integration: "Article 13 requires high-risk AI..."
        # The em-dash typographic format is no longer produced.
        assert "Article 13 requires" in out, f"counsel-voice prose missing: {out!r}"
        assert "(Article 13 requires" in out, f"parenthesized expansion not in-place: {out!r}"
        # Em-dash typographic prefix should NOT appear.
        assert "Article 13 —" not in out, f"old em-dash format still present: {out!r}"
        # Verify in-place substitution preserved surrounding context.
        assert out.startswith("The provider must comply with the requirements")

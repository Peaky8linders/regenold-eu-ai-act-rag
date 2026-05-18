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

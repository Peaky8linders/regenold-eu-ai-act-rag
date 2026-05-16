"""Regression guards for ``_extract_subpoints`` + ``reference_from_article_ref``.

Pre-fix bug (Issue 56)
----------------------
``app/integrations/regenold/models.py::_extract_subpoints`` walked
parenthesised tokens first, then fell back to dot-form tokens **only
if no paren tokens were found**. The branch:

    elif not tokens and "." in tail:

dropped any dot-form segment that followed a paren-form segment. So
``Art. 13(1).a`` (a real shape observed in mixed engine output where
the LLM swapped to dot-form mid-tail) extracted only ``["1"]`` and
shipped as ``Article 13.1`` — losing the ``.a`` subsegment.

Issue 56 surfaced two additional bugs in the same parse path:

1. **Numeric ceiling was wrong (20).** ``Art. 3.63`` is a real EU AI
   Act definition (general-purpose AI model) — confirmed in
   ``app/data/definitions.py``. The > 20 cap was an overzealous
   hallucination guard that incorrectly dropped legitimate refs in
   the definitions article (where subpoints reach ~68). Raised to 99
   — well past real values, still catches obvious junk like
   ``Art. 13(999)``.

2. **Fail-open downgrade.** When the subpoint parser rejected a tail
   it returned ``[]`` and ``reference_from_article_ref`` silently
   fell back to formatting the base article. ``Art. 13(99)`` →
   ``Article 13`` looks valid (Art. 13 is in the catalog) but is a
   silent corruption: the caller can no longer tell whether the LLM
   said "Article 13" or "Article 13.99 (and I made it up)". Now:
   when a tail is PRESENT but the parser rejects it, the formatter
   returns ``None`` so the caller drops the citation entirely. Only
   a TRULY empty tail (no parens, no dot) falls through to the base
   format.

Fix
---
Single-sweep extraction via a unified regex that captures BOTH paren
and dot tokens in left-to-right order. The existing protections
remain:

* Tokens containing non-``[A-Za-z0-9]`` chars are dropped.
* Numeric tokens > 99 are rejected.
* Tail present + parser rejection → ``reference_from_article_ref``
  returns ``None`` (no silent base-only downgrade).

Test surface
------------
* Mixed paren+dot tails — the actual fix.
* Pure paren tails — happy-path preservation.
* Pure dot-form input — happy-path preservation.
* Annex multi-segment forms — symmetric with Article handling.
* Hallucinated > 99 numerics — rejection preserved (with new ceiling).
* ``Art. 3.63`` happy path — the previously-wrongly-dropped ref.
* Fail-open guard — ``Art. 13(999)`` returns ``None``, not
  ``Article 13``.
"""
from __future__ import annotations

import pytest

from app.integrations.regenold.models import (
    _extract_subpoints,
    reference_from_article_ref,
)

# ─── End-to-end on the public formatter (the wire-shaping surface) ────────


class TestReferenceFormatterMixedTails:
    """Pin the mixed-tail behaviour end-to-end through
    :func:`reference_from_article_ref`.

    These are the cases the Regenold judge sees.
    """

    def test_mixed_paren_then_dot_tail_preserves_sub_letter(self) -> None:
        """``Art. 13(1).a`` → ``Article 13.1.a`` (the actual fix)."""
        assert reference_from_article_ref("Art. 13(1).a") == "Article 13.1.a"

    def test_pure_paren_tail_unchanged(self) -> None:
        """``Art. 13(1)(a)`` → ``Article 13.1.a`` (preserved behaviour)."""
        assert reference_from_article_ref("Art. 13(1)(a)") == "Article 13.1.a"

    def test_pure_dot_tail_unchanged(self) -> None:
        """``Art. 13.1.a`` → ``Article 13.1.a`` (already-formatted input).

        Some upstream emitters use dot notation. The formatter accepts
        both shapes and normalises to dot-output.
        """
        assert reference_from_article_ref("Art. 13.1.a") == "Article 13.1.a"

    def test_annex_mixed_paren_then_dot_preserved(self) -> None:
        """``Annex IV(2).b`` → ``Annex IV.2.b``.

        Symmetric with the Article path — the Annex branch shares the
        same ``_extract_subpoints`` helper, so the mixed-tail fix
        carries through.
        """
        assert reference_from_article_ref("Annex IV(2).b") == "Annex IV.2.b"

    def test_high_numeric_token_rejected(self) -> None:
        """``Art. 13(999)(z)`` — the > 99 numeric must not appear in the output.

        ``(999)`` is a hallucination (LLM emitting a placeholder digit
        run). The extractor drops the offending token defensively and
        — per Issue 56 fix — the formatter then returns ``None``
        rather than silently downgrading to the base ``Article 13``
        (which would be a confidence-laundering corruption).
        """
        result = reference_from_article_ref("Art. 13(999)(z)")
        # Tail-present-but-rejected → None (no silent fallback to
        # base ``Article 13``).
        assert result is None, (
            f"hallucinated tail must drop the citation, got: {result!r}"
        )

    def test_definition_subpoint_above_old_ceiling_kept(self) -> None:
        """``Art. 3.63`` — real EU AI Act definition, must NOT be dropped.

        Pre-fix the > 20 ceiling in ``_extract_subpoints`` incorrectly
        rejected ``Art. 3.63`` (general-purpose AI model), forcing it
        to fail-open to ``Article 3``. With the ceiling raised to 99
        AND the fail-open closed, the legitimate subpoint survives.
        """
        assert reference_from_article_ref("Art. 3.63") == "Article 3.63"

    def test_fail_open_closed_for_hallucinated_numeric(self) -> None:
        """``Art. 13(999)`` — pre-fix silently downgraded to ``Article 13``.

        The classic confidence-laundering attack: a hallucinated
        ``Art. 13(999)`` cite passes existence (Art. 13 IS in the
        catalog) and the parser rejects ``(999)`` → fail-open emits
        ``Article 13`` (which IS a valid output shape). Caller can't
        distinguish "no subpoint given" from "invalid subpoint
        silently stripped". Fix: parser rejection on a present tail
        → ``None``.
        """
        assert reference_from_article_ref("Art. 13(999)") is None

    def test_no_tail_still_emits_base_ref(self) -> None:
        """``Art. 13`` — no tail at all, base format expected.

        The fail-open closure must distinguish "tail absent" (base
        ref, valid) from "tail present, parser rejected" (drop). A
        bare ``Art. 13`` falls in the first bucket and must format
        cleanly as ``Article 13``.
        """
        assert reference_from_article_ref("Art. 13") == "Article 13"

    def test_annex_fail_open_closed(self) -> None:
        """``Annex IV(999)`` — symmetric Annex-side fail-open guard.

        Same shape as the Article-side fail-open: ``Annex IV`` exists
        in the catalog, the parser rejects ``(999)``, and pre-fix the
        formatter would fall through to ``Annex IV``. Closed by the
        Issue 56 fix.
        """
        assert reference_from_article_ref("Annex IV(999)") is None

    def test_annex_bare_still_works(self) -> None:
        """``Annex IV`` — no tail → base format. Counterpoint to
        :meth:`test_annex_fail_open_closed` to confirm the empty-tail
        path is unchanged.
        """
        assert reference_from_article_ref("Annex IV") == "Annex IV"


# ─── Unit-level tests on the helper directly ──────────────────────────────


class TestExtractSubpointsMixedTails:
    """Direct unit tests on :func:`_extract_subpoints`.

    Bypasses the catalog existence gate so we can exercise the parser
    on synthetic tails (the public formatter would refuse hallucinated
    article numbers before reaching the parser).
    """

    def test_mixed_paren_then_dot(self) -> None:
        assert _extract_subpoints("(1).a") == ["1", "a"]

    def test_pure_paren(self) -> None:
        assert _extract_subpoints("(1)(a)") == ["1", "a"]

    def test_pure_dot(self) -> None:
        assert _extract_subpoints(".1.a") == ["1", "a"]

    def test_nested_paren_chain(self) -> None:
        assert _extract_subpoints("(1)(a)(ii)") == ["1", "a", "ii"]

    def test_empty_tail(self) -> None:
        assert _extract_subpoints("") == []

    def test_whitespace_only(self) -> None:
        assert _extract_subpoints("   ") == []

    @pytest.mark.parametrize(
        ("tail", "expected"),
        [
            ("(2)", ["2"]),
            (".2", ["2"]),
            ("(a)", ["a"]),
            (".a", ["a"]),
        ],
    )
    def test_single_token_each_shape(
        self, tail: str, expected: list[str]
    ) -> None:
        assert _extract_subpoints(tail) == expected

    def test_high_numeric_rejects_entire_chain(self) -> None:
        # ``(999)`` is rejected as > 99 (Issue 56: ceiling raised from
        # 20 → 99 to admit real refs like ``Art. 3.63``). Policy is
        # all-or-nothing: if any token in the chain is out of range,
        # drop the WHOLE chain — a partial keep would ship phantom
        # precision (``Article 13.z`` from ``Art. 13(999)(z)`` looks
        # valid but doesn't reflect what the input said).
        assert _extract_subpoints("(999)(z)") == []

    def test_high_numeric_alone_yields_empty(self) -> None:
        # ``(999)`` on its own → parser returns ``[]``. The wrapper
        # ``reference_from_article_ref`` THEN returns None for this
        # case (tail present + parser rejected) — see
        # :class:`TestReferenceFormatterMixedTails`.
        assert _extract_subpoints("(999)") == []

    def test_at_threshold_boundary(self) -> None:
        # 99 is the inclusive upper bound (Issue 56). 100 is rejected
        # (and the whole chain drops if 100 is anywhere in it). 63 is
        # accepted — covers the real ``Art. 3.63`` definition that the
        # previous 20-ceiling wrongly dropped.
        assert _extract_subpoints("(63)") == ["63"]
        assert _extract_subpoints(".63") == ["63"]
        assert _extract_subpoints("(99)") == ["99"]
        assert _extract_subpoints("(100)") == []
        assert _extract_subpoints("(100)(a)") == []

    def test_malformed_token_rejects_entire_chain(self) -> None:
        # Hyphen in the paren content fails ``[A-Za-z0-9]+``. Same
        # all-or-nothing policy — the trailing valid letter doesn't
        # rescue a chain that contains a malformed earlier segment.
        assert _extract_subpoints("(1-2)(a)") == []

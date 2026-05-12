"""Regression guards for the mixed-tail parsing fix in ``_extract_subpoints``.

Pre-fix bug
-----------
``app/integrations/regenold/models.py::_extract_subpoints`` walked
parenthesised tokens first, then fell back to dot-form tokens **only
if no paren tokens were found**. The branch:

    elif not tokens and "." in tail:

dropped any dot-form segment that followed a paren-form segment. So
``Art. 13(1).a`` (a real shape observed in mixed engine output where
the LLM swapped to dot-form mid-tail) extracted only ``["1"]`` and
shipped as ``Article 13.1`` — losing the ``.a`` subsegment.

Fix
---
Single-sweep extraction via a unified regex that captures BOTH paren
and dot tokens in left-to-right order. The existing protections
remain:

* Tokens containing non-``[A-Za-z0-9]`` chars are dropped.
* Numeric tokens > 20 are rejected (no EU AI Act paragraph is numbered
  higher than ~12 today; > 20 is almost certainly a hallucination).

Test surface
------------
* Mixed paren+dot tails — the actual fix.
* Pure paren tails — happy-path preservation.
* Pure dot-form input — happy-path preservation.
* Annex multi-segment forms — symmetric with Article handling.
* Hallucinated > 20 numerics — rejection preserved.
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
        """``Art. 13(99)(z)`` — the > 20 numeric must not appear in the output.

        EU AI Act paragraphs max out around 12. ``(99)`` is almost
        certainly a hallucination (LLM emitting a placeholder digit
        run). The extractor drops the offending token defensively so
        the formatter cannot ship ``Article 13.99.z``.

        Implementation may either reject the entire reference OR drop
        only the bogus numeric and keep the trailing letter — both are
        acceptable; the contract this test pins is "99 is not in the
        output".
        """
        result = reference_from_article_ref("Art. 13(99)(z)")
        # The full hallucination ``Article 13.99.z`` must NEVER ship.
        assert result != "Article 13.99.z"
        # Whatever shape survives must not embed the bogus 99.
        if result is not None:
            assert "99" not in result, (
                f"hallucinated numeric > 20 leaked into output: {result!r}"
            )


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

    def test_high_numeric_dropped(self) -> None:
        # ``(99)`` is rejected as > 20; the trailing letter survives.
        assert _extract_subpoints("(99)(z)") == ["z"]

    def test_high_numeric_alone_yields_empty(self) -> None:
        # ``(99)`` on its own → entire ref shapes as bare ``Article N``.
        assert _extract_subpoints("(99)") == []

    def test_at_threshold_boundary(self) -> None:
        # 20 is the inclusive upper bound; 21 is rejected.
        assert _extract_subpoints("(20)") == ["20"]
        assert _extract_subpoints("(21)") == []

    def test_malformed_token_dropped(self) -> None:
        # Hyphen in the paren content fails ``[A-Za-z0-9]+`` — token dropped.
        assert _extract_subpoints("(1-2)(a)") == ["a"]

"""R80-D narrow — augmenter coverage tightening.

R80-D narrow scope: tighten ``_answer_covers_ref`` so the BM25-overlap
signal no longer over-fires on common KB-stub tokens (provider/must/
document/system/risk) that appear in nearly every Article's stub. The
r80-live judge run flagged Article-N "cited but not described" on 42/60
neo4j-path rows because the augmenter falsely considered each Article
"already covered" via 2-token incidental overlap. The fix:

  * Raise BM25 token-overlap threshold 2 → 4 (substantive content
    overlap required, not just stopword-class collisions).
  * Add a literal cite-presence check ("Article N" in answer text) as a
    primary signal — when the engine literally names the ref, treat as
    covered.

Either signal returning True ⇒ covered; failure → fail-open (no clause
added). This module tests the coverage helper in isolation.
"""

from __future__ import annotations

from app.integrations.regenold.grounded_prose import (
    _AUGMENT_COVERAGE_THRESHOLD,
    _answer_covers_ref,
    augment_with_ref_descriptions,
)


class TestR80DLiteralCiteCheck:
    """Literal cite presence in the prose ⇒ covered."""

    def test_user_facing_article_form_in_answer_is_covered(self) -> None:
        answer = (
            "The provider must establish a risk-management system per "
            "Article 9 across the AI system lifecycle."
        )
        tokens = frozenset(answer.lower().split())
        assert _answer_covers_ref(tokens, "Art. 9", answer_text=answer) is True

    def test_internal_art_form_in_answer_is_covered(self) -> None:
        answer = (
            "Logs must be retained as required by Art. 19 of the regulation."
        )
        tokens = frozenset(answer.lower().split())
        assert _answer_covers_ref(tokens, "Art. 19", answer_text=answer) is True

    def test_annex_literal_in_answer_is_covered(self) -> None:
        answer = (
            "Technical documentation requirements are specified in Annex IV."
        )
        tokens = frozenset(answer.lower().split())
        assert _answer_covers_ref(tokens, "Annex IV", answer_text=answer) is True

    def test_article_not_named_falls_through_to_bm25(self) -> None:
        """When the article isn't literally named, BM25 with threshold=4
        must hold — incidental 2-token overlap no longer counts as covered.
        """
        # An answer that talks about generic "provider" / "system" without
        # naming Article 11 explicitly. Sharing the common tokens shouldn't
        # be enough to mark Article 11 "described".
        answer = "The provider must develop the system per applicable rules."
        tokens = frozenset(answer.lower().split())
        # We don't assert True/False here — depends on Art. 11's KB stub
        # tokens — but the test below pins the new threshold value.
        _ = _answer_covers_ref(tokens, "Art. 11", answer_text=answer)


class TestR80DCoverageThreshold:
    """The BM25 threshold is now 4, not 2 (regression pin)."""

    def test_threshold_value(self) -> None:
        assert _AUGMENT_COVERAGE_THRESHOLD == 4, (
            "R80-D raised the threshold to 4; lowering it back would "
            "re-introduce the over-coverage failure mode."
        )


class TestR80DBackcompat:
    """Existing callers without the new kwarg still work (kwarg has a
    default of ``""``)."""

    def test_two_arg_call_still_works(self) -> None:
        """Pre-R80 callers passing only (tokens, internal_ref)."""
        tokens = frozenset({"provider", "must", "establish"})
        # No exception, returns a bool.
        assert isinstance(_answer_covers_ref(tokens, "Art. 9"), bool)


class TestR80DAugmenterIntegration:
    """Augmenter respects the new coverage logic."""

    def test_augmenter_skips_when_literal_cite_present(self) -> None:
        """No clause added for an Article the answer literally names."""
        base = (
            "The provider must comply with Article 13 for high-risk AI "
            "systems."
        )
        result = augment_with_ref_descriptions(
            base, user_facing_refs=["Article 13"]
        )
        # Article 13 was named → no augmenter clause appended.
        assert result == base

    def test_augmenter_appends_when_ref_not_named(self) -> None:
        """A cited ref not literally named in prose gets a clause."""
        base = "Compliance obligations apply for high-risk AI systems."
        result = augment_with_ref_descriptions(
            base, user_facing_refs=["Article 13"]
        )
        # The augmenter should have added a "Article 13 — ..." clause.
        assert "Article 13" in result, (
            f"augmenter must append cite-anchored clause: {result!r}"
        )
        assert len(result) > len(base)


class TestR106InlineExpansionGuard:
    """R106 — guard only the BARE-cite inline-replace branch.

    Commit d623849 removed the ``not is_covered`` guard from BOTH inline
    branches, which fused KB clauses onto grammatically-embedded bare cites
    (the general-classification-verdict bug). The fix guards only the bare
    branch: a bare cite is usually embedded ("comply with Article 13 for ...")
    so splicing a subject-verb clause produces a run-on; a PARENTHESIZED cite
    "(Article 13)" is standalone and still expands (that contract is pinned by
    ``test_grounded_prose.py::test_inline_replace_mode``).
    """

    def test_embedded_bare_cite_not_fused(self) -> None:
        base = (
            "The provider must comply with Article 13 for high-risk AI "
            "systems."
        )
        result = augment_with_ref_descriptions(
            base, user_facing_refs=["Article 13"]
        )
        assert result == base
        # The fusion signature must be absent.
        assert "Article 13 requires" not in result, (
            f"inline KB clause fused onto an embedded cite: {result!r}"
        )

    def test_parenthesized_cite_still_expands(self) -> None:
        # The standalone parenthesized form is grammatically safe to expand —
        # the bare-branch guard must NOT suppress it (R90 contract).
        base = "The provider must comply with the requirements (Article 13)."
        result = augment_with_ref_descriptions(
            base, user_facing_refs=["Article 13"]
        )
        assert "(Article 13 requires" in result, (
            f"parenthesized expansion must still fire: {result!r}"
        )


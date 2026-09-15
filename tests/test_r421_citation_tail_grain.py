"""R421 — the citation extractor must read the DOT form at full grain.

``app.graph.knowledge_graph.extract_citations`` feeds ``build_graph``'s
``CROSS_REFERENCES_INTERNAL`` edges (``app/engines/graph_expansion_engine.py``
calls ``build_graph``). Its tail regex used to require parentheses, so:

    "Article 6.2"   -> art_6          (the .2 was discarded)
    "Article 13.1"  -> art_13
    "Annex III.7.b" -> annex_III

The dot form is not incidental — it is the spelling this system instructs the
model to emit, the spelling the benchmark's reference keys use, and the
spelling our own wire carries. A coarser edge than the prose supports is a
silent error: the edge is tagged ``provenance="text"`` and nothing re-checks it.
"""

from __future__ import annotations

import pytest

from app.graph.knowledge_graph import extract_citations, extract_reference_eids


def _eids(text: str) -> list[str]:
    return [pid.eid for pid in extract_citations(text)]


class TestDotFormKeepsGrain:
    @pytest.mark.parametrize(
        ("dot", "paren", "expected"),
        [
            ("Article 6.2", "Article 6(2)", "art_6__para_2"),
            ("Article 13.1", "Article 13(1)", "art_13__para_1"),
            ("Article 5.1.f", "Article 5(1)(f)", "art_5__para_1__point_f"),
            ("Article 5.1.h.iii", "Article 5(1)(h)(iii)", "art_5__para_1__point_h__sub_iii"),
            ("Annex IV.2", "Annex IV(2)", "annex_IV__point_2"),
            ("Annex III.7.b", "Annex III(7)(b)", "annex_III__point_7__point_b"),
        ],
    )
    def test_both_spellings_agree_at_full_grain(
        self, dot: str, paren: str, expected: str
    ) -> None:
        assert _eids(f"See {dot} for the rule.") == [expected]
        # The two spellings are the same provision, so they must resolve to the
        # same id — otherwise a citation's grain depends on how it was written.
        assert _eids(f"See {paren} for the rule.") == [expected]

    def test_a_mixed_tail_keeps_every_group_in_order(self) -> None:
        assert _eids("Under Article 6.1(a) the rule bites.") == ["art_6__para_1__point_a"]

    def test_an_annex_point_spelling_still_works(self) -> None:
        assert _eids("Annex III point 4(a) applies.") == ["annex_III__point_4__point_a"]

    def test_reference_eids_expose_the_same_grain(self) -> None:
        assert extract_reference_eids("Article 6.2 and Annex III.7.b") == [
            "art_6__para_2",
            "annex_III__point_7__point_b",
        ]


class TestNoNewFalsePositives:
    def test_a_sentence_period_is_not_a_group(self) -> None:
        # The regression this guards: ". The" must not be read as a limb.
        assert _eids("Article 13. The provider must comply.") == ["art_13"]
        assert _eids("Article 13. the provider must comply.") == ["art_13"]

    def test_a_capitalised_word_after_a_period_is_not_a_group(self) -> None:
        assert _eids("Article 6. Nothing else applies.") == ["art_6"]

    def test_an_external_instrument_is_still_excluded(self) -> None:
        assert _eids("Article 13 of the GDPR applies.") == []

    def test_an_article_range_is_unchanged(self) -> None:
        assert _eids("Articles 40-41 presume conformity.") == ["art_40"]

    def test_plain_short_form_is_unchanged(self) -> None:
        assert _eids("Art. 6(2)(a) applies.") == ["art_6__para_2__point_a"]


class TestDeepFormCascades:
    def test_a_four_deep_citation_keeps_the_deepest_representable_grain(self) -> None:
        # The id model nests three deep (``_ARTICLE_NEST``). Before R421 this
        # citation returned only ``art_5``; dropping the deepest group is still
        # strictly richer than dropping the whole tail.
        assert _eids("Article 5.1.h.iii.zz applies.") == ["art_5__para_1__point_h__sub_iii"]

    def test_cascade_never_loses_the_article(self) -> None:
        assert _eids("Article 5.1.h.iii.zz.qq applies.")[0].startswith("art_5")

"""R325 — no foreign instrument's article number may reach the wire.

Ported from the RAG repo's R322 + R324 after MEASURING each shape leaking here
first. The defect class is the worst this codebase can ship: a confidently
wrong legal claim (hard rule #4) in a wire-legal shape (hard rule #1), so the
``ARTICLE_EXISTENCE`` lint (hard rule #5) provably cannot catch it — GDPR
Art. 5 collides with AI Act Art. 5 (prohibited practices), GDPR Art. 35 with
AI Act Art. 35 (notified-body identification numbers), GDPR Art. 22 with AI Act
Art. 22 (authorised representatives).

TWO THINGS MUST BOTH HOLD, or the fix is worthless:

  1. the guard FIRES on every leak shape. R324's own finding is that widening
     the regex measured byte-identical on the wire because Component D — a
     SECOND, entirely unguarded prose-to-citation path — re-added whatever the
     guard dropped. "Byte-identical" is also what INERT looks like, so these
     tests assert the behaviour directly rather than the absence of movement.

  2. genuine AI Act citations are STILL promoted. Dropping a real citation is
     the R142.1 failure mode (a positional clamp lost a live pairwise judge
     11-0, p=0.001) and costs more than the leak. Hence the controls below —
     in particular the R142.1 shape, where an AI Act sentence is FOLLOWED by a
     sentence naming the GDPR: an unbounded ahead-window suppresses the genuine
     Article 13, which is why ``_ahead_window`` bounds before it widens.
"""

from __future__ import annotations

import pytest

from app.routes.regenold import (
    _add_prose_named_refs,
    _prose_citation_bases,
)

def _component_d(answer: str) -> set[str]:
    """The shared ordered extractor used by Component D."""
    return set(_prose_citation_bases(answer))


# (id, prose, the AI-Act-shaped number that must NOT be promoted)
_LEAKS = [
    ("r321_prefix_gdpr",
     "Under Article 27 the FRIA applies; GDPR Art. 5 governs personal data.",
     "Article 5"),
    ("r321_prefix_charter",
     "Article 27 applies. Non-discrimination sits in EU Charter Art. 21.",
     "Article 21"),
    ("r322_postpositive_gdpr_35",
     "The FRIA under Article 27 complements Article 35 GDPR.",
     "Article 35"),
    ("r322_postpositive_gdpr_22",
     "Article 27 applies, as does Article 22 GDPR on automated decisions.",
     "Article 22"),
    ("r324_interposed_clause_1025_2012",
     "Standards follow Article 10, second subparagraph, point (b), of "
     "Regulation (EU) No 1025/2012.",
     "Article 10"),
    ("r324_interposed_clause_2016_679",
     "See Article 6(1), point (a), second subparagraph, of Regulation (EU) "
     "2016/679 for the lawful basis.",
     "Article 6"),
    ("r324_bare_regulation_number",
     "Personal data is governed by Article 5 of Regulation 2016/679.",
     "Article 5"),
    ("r324_behind_prefix_regulation",
     "Harmonised standards under Regulation (EU) No 1025/2012, Article 10 apply.",
     "Article 10"),
    ("r323_pre_2015_oj_numbering",
     "Market surveillance follows Article 30 of Regulation (EC) No 765/2008.",
     "Article 30"),
    ("article_of_mdr",
     "The manufacturer also complies with Article 10 of the MDR.",
     "Article 10"),
    ("article_of_tfeu",
     "State-aid analysis remains governed by Article 107 of the TFEU.",
     "Article 107"),
    ("eg_under_numbered_regulation",
     "Market controls follow Article 30, e.g. under Regulation (EC) No 765/2008.",
     "Article 30"),
    ("numbered_regulation_parenthesized_acronym_prefix",
     "Regulation (EU) 2017/745 (MDR), Article 10 governs manufacturers.",
     "Article 10"),
    ("numbered_directive_prefix",
     "Directive 2014/35/EU, Article 10 governs that product requirement.",
     "Article 10"),
    ("possessive_acronym_prefix",
     "The MDR's Article 10 governs that manufacturer duty.",
     "Article 10"),
]


@pytest.mark.parametrize(("case", "prose", "leaked"), _LEAKS, ids=[c[0] for c in _LEAKS])
def test_guard_blocks_foreign_citation(case: str, prose: str, leaked: str) -> None:
    """_add_prose_named_refs must not promote a foreign instrument's article."""
    added = _add_prose_named_refs(
        ["Article 27"],
        prose,
        citable_bases={"Article 27", leaked},
    )
    assert leaked not in added, (
        f"{case}: {leaked} was promoted onto the wire from a foreign instrument"
    )


@pytest.mark.parametrize(("case", "prose", "leaked"), _LEAKS, ids=[c[0] for c in _LEAKS])
def test_component_d_blocks_foreign_citation(case: str, prose: str, leaked: str) -> None:
    """R324-C1 — the SECOND extraction path must apply the SAME guard."""
    assert leaked not in _component_d(prose), (
        f"{case}: Component D re-added {leaked} after the guard dropped it"
    )


# (id, prose, refs that MUST survive)
_CONTROLS = [
    ("genuine_two_article",
     "Under Article 13 providers must be transparent, and Article 14 requires "
     "human oversight.",
     {"Article 13", "Article 14"}),
    ("r142_1_shape_ai_act_then_gdpr_sentence",
     "Article 13 requires transparency for high-risk systems. Article 35 of "
     "Regulation (EU) 2016/679 requires a DPIA.",
     {"Article 13"}),
    ("ai_act_self_reference_by_number",
     "This duty flows from Article 16 of Regulation (EU) 2024/1689.",
     {"Article 16"}),
    ("article_and_annex_together",
     "Article 11 requires the technical documentation set out in Annex IV.",
     {"Article 11", "Annex IV"}),
]


@pytest.mark.parametrize(
    ("case", "prose", "expected"), _CONTROLS, ids=[c[0] for c in _CONTROLS]
)
def test_genuine_citations_still_promoted(
    case: str, prose: str, expected: set[str]
) -> None:
    """The guard must not be over-broad — R142.1 is the expensive direction."""
    got = _component_d(prose)
    missing = expected - got
    assert not missing, f"{case}: guard DROPPED genuine AI Act refs {sorted(missing)}"


def test_one_definition_of_a_numbered_regulation() -> None:
    """R324 — the ahead and behind guards must share ONE id definition."""
    from app.routes.regenold import _REG_NUMBER_FRAGMENT
    import app.routes.regenold as R

    src = open(R.__file__, encoding="utf-8").read()
    assert src.count("_REG_NUMBER_FRAGMENT") >= 3, (
        "the shared numbered-regulation fragment must be used by both the "
        "ahead and behind guards"
    )
    assert "2024/1689" in src, "the AI Act self-reference exclusion must survive"
    assert _REG_NUMBER_FRAGMENT


def test_behind_window_fits_the_longest_prefix_form() -> None:
    from app.routes.regenold import _BEHIND_WINDOW_CHARS

    assert _BEHIND_WINDOW_CHARS >= len("Regulation (EU) No 1025/2012, ")


def test_non_citable_kg_coordinate_cannot_be_promoted() -> None:
    added = _add_prose_named_refs(
        ["Article 13"],
        "Article 13 applies. Article 35 adds another requirement.",
        citable_bases={"Article 13"},
        cap=8,
    )
    assert added == ["Article 13"]


def test_shared_extractor_preserves_first_mention_order() -> None:
    prose = "Annex III applies; Article 6 governs; Article 13 then adds transparency."
    assert _prose_citation_bases(prose) == [
        "Annex III",
        "Article 6",
        "Article 13",
    ]


def test_arabic_annex_prose_normalises_to_roman_wire_head() -> None:
    assert _prose_citation_bases("Annex 3 applies under Article 6.") == [
        "Annex III",
        "Article 6",
    ]

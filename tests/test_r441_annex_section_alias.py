"""R441 — strict scoring must preserve Annex I's continuous statutory numbering.

THE DEFECT. Annex I numbers its points 1-20 continuously: Section A contains
1-12 and Section B contains 13-20. Some answer keys use section-tagged aliases
such as ``Annex I.a.11`` for statutory point 11. The original repair normalized
flat citations into a fabricated restart-numbering scheme (e.g. point 19 became
``Annex I.b.7``), which the Act does not use.

The corrected normalization is key-side and preserves printed point numbers:
``Annex I.a.11`` becomes ``Annex I.11``; ``Annex I.b.19`` becomes
``Annex I.19``; flat ``Annex I.19`` remains unchanged. On R440's ``rg_008``
row, this lets the correct MDR citation (point 11) match while correctly
rejecting point 19, a different act.

WHAT THIS FILE PINS. The section ranges are re-derived from the adopted text;
Section B's continuous 13-20 numbering cannot be silently changed to 1-8.
Annex VIII is separately pinned as ambiguous because its section numbering
restarts, so it must not be flattened by a guessed alias.
"""

from __future__ import annotations

import re

from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT
from evals.official.rubric import (
    ANNEX_SECTIONS,
    _clean,
    _is_descendant,
    canonical_annex_point,
    normalise_ref,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

# The row whose defect motivated the repair, verbatim from the refkey.
RG_008_KEY = ["Article 6.1", "Annex I.a.11"]
# The two arms of the R440 draw, as captured: the refs both arms actually shipped.
RG_008_RIGHT = ["Article 6.1", "Annex I.11", "Annex I", "Annex III.7"]
RG_008_WRONG = ["Article 6.1", "Annex I.19", "Annex I", "Annex III.7"]


# -- the alias table is derived from the adopted text, not asserted ----------

_SECTION_RE = re.compile(r"Section\s+([A-Z])\b")
_ITEM_RE = re.compile(r"(\d{1,2})\.\s+(?=[A-Z(])")


def _derive_annex_sections(annex: str) -> dict[str, list[int]]:
    """Read the adopted text and report, per section letter, its point numbers."""
    body = ARTICLE_FULL_TEXT[annex]
    section: str | None = None
    out: dict[str, list[int]] = {}
    for m in re.finditer(rf"{_SECTION_RE.pattern}|{_ITEM_RE.pattern}", body):
        if m.group(1):
            section = m.group(1).lower()
            out.setdefault(section, [])
        elif section is not None:
            out[section].append(int(m.group(2)))
    return out


def test_annex_i_ranges_in_the_axis_match_the_adopted_text():
    """Annex I's points run continuously 1-20 across a 12/8 section split.

    Section A holds the New Legislative Framework acts (points 1-12) and Section
    B the rest (13-20), so the flat text numbering and the key's sectioned
    numbering are two spellings of one list.
    """
    derived = _derive_annex_sections("Annex I")
    assert derived == {"a": list(range(1, 13)), "b": list(range(13, 21))}
    assert ANNEX_SECTIONS["I"]["a"] == (1, 12)
    assert ANNEX_SECTIONS["I"]["b"] == (13, 20)


def test_point_11_of_annex_i_is_the_medical_device_regulation():
    """The specific coordinate rg_008 turns on: Section A point 11 is the MDR."""
    body = ARTICLE_FULL_TEXT["Annex I"]
    section_a = body.split("Section B")[0]
    item_11 = section_a.split("11.")[1]
    assert "2017/745" in item_11
    # ...and the Section B acts are NOT the MDR, so the wrong citation is a
    # different piece of legislation rather than a near miss.
    section_b = body.split("Section B")[1]
    assert "2017/745" not in section_b


def test_an_annex_whose_sections_restart_is_not_aliased():
    """Annex VIII restarts at 1 in every section, so ``Annex VIII.1`` is ambiguous.

    Aliasing it would invent a match instead of recovering one, so the annex is
    absent from the table and the axis stays with the literal reading.
    """
    derived = _derive_annex_sections("Annex VIII")
    assert sorted(derived) == ["a", "b", "c"]
    assert set(derived["a"]) & set(derived["b"]), "sections must collide to be a valid guard"
    assert "VIII" not in ANNEX_SECTIONS
    assert canonical_annex_point("Annex VIII.1") == "Annex VIII.1"
    assert reference_correctness_strict(["Annex VIII.1"], ["Annex VIII.b.1"]) == 0.0


def test_sections_are_disjoint_by_construction():
    """A flat point must name exactly one sectioned coordinate, or the alias is a guess."""
    for annex, sections in ANNEX_SECTIONS.items():
        claimed: list[int] = []
        for lo, hi in sections.values():
            claimed += list(range(lo, hi + 1))
        assert len(claimed) == len(set(claimed)), annex


# -- the discriminating case --------------------------------------------------


def test_section_b_key_preserves_the_act_point_number():
    """Section B uses statutory points 13-20; it does not restart at point 1."""
    assert canonical_annex_point("Annex I.b.19") == "Annex I.19"
    assert canonical_annex_point("Annex I.19") == "Annex I.19"
    assert reference_correctness_strict(["Annex I.19"], ["Annex I.b.19"]) == 1.0
    # Section B point 7 is not in this Act's section range; do not alias it to 19.
    assert canonical_annex_point("Annex I.b.7") == "Annex I.b.7"
    assert reference_correctness_strict(["Annex I.19"], ["Annex I.b.7"]) == 0.0


def test_the_right_annex_point_satisfies_the_keys_sectioned_coordinate():
    """``Annex I.11`` IS ``Annex I.a.11``: point 11 of a run that starts at 1 in A."""
    assert reference_correctness_strict(RG_008_RIGHT, RG_008_KEY) == 1.0


def test_the_wrong_annex_point_does_not_satisfy_it():
    """``Annex I.19`` is a Section B act, not the MDR at point 11."""
    assert canonical_annex_point("Annex I.19") == "Annex I.19"
    assert reference_correctness_strict(RG_008_WRONG, RG_008_KEY) == 0.5


def test_the_two_readings_no_longer_score_identically():
    """The whole point of the repair, stated as the inequality it buys.

    Before it, both arms of the R440 draw scored ref strict 50.0 on rg_008 and
    the right answer's repair was invisible.  The gap is now the axis's own
    measurement of that repair.
    """
    right = reference_correctness_strict(RG_008_RIGHT, RG_008_KEY)
    wrong = reference_correctness_strict(RG_008_WRONG, RG_008_KEY)
    assert right > wrong


def test_legacy_sectioned_prediction_matches_a_flat_key():
    """Either side may carry the legacy tag; both normalize to the printed point."""
    assert canonical_annex_point("Annex I.a.11") == "Annex I.11"
    assert reference_correctness_strict(["Annex I.a.11"], ["Annex I.11"]) == 1.0


def test_section_letter_case_is_not_a_coordinate_difference():
    """A section-letter case difference must not separate equivalent citations.
    """
    assert normalise_ref("Annex I.A.11") == normalise_ref("Annex I.a.11")
    upper = reference_correctness_strict(["Article 6.1", "Annex I.A.11"], RG_008_KEY)
    lower = reference_correctness_strict(["Article 6.1", "Annex I.a.11"], RG_008_KEY)
    assert upper == lower == 1.0


# -- the alias must not manufacture matches ----------------------------------


def test_a_different_section_a_point_does_not_satisfy_the_key():
    for point in ("Annex I.1", "Annex I.2", "Annex I.10", "Annex I.12"):
        assert canonical_annex_point(point) == point
        assert reference_correctness_strict(["Article 6.1", point], RG_008_KEY) == 0.5, point


def test_a_different_section_b_point_does_not_satisfy_the_key():
    """Section B statutory point 19 must not be rewritten as Section B point 7."""
    assert canonical_annex_point("Annex I.19") == "Annex I.19"
    assert reference_correctness_strict(["Article 6.1", "Annex I.19"], RG_008_KEY) == 0.5
    assert _is_descendant("Annex I.19", "Annex I.19") is True
    assert _is_descendant("Annex I.19", "Annex I.190") is False


def test_subpoints_survive_key_normalization():
    """A deeper predicted coordinate still refines the normalized statutory point."""
    assert canonical_annex_point("Annex I.a.11") == "Annex I.11"
    assert canonical_annex_point("Annex I.11.a") == "Annex I.11.a"
    assert reference_correctness_strict(["Annex I.11.a"], ["Annex I.a.11"]) == 1.0


def test_coordinates_the_alias_must_not_touch_are_untouched():
    for coord in (
        "Article 6.1",  # no annex
        "Annex I",  # a bare head names no point
        "Annex I.1",  # statutory flat point, unchanged
        "Annex I.19",  # statutory flat point, unchanged
        "Annex I.b.7",  # invalid point for Section B, left untouched
        "Annex III.1.a",  # a letter part, but no sectioned fan-out
        "Annex VIII.3",  # ambiguous annex, deliberately
        "Annex II.1",  # no sections at all
        "Annex I.21",  # outside every listed range
    ):
        assert canonical_annex_point(coord) == coord, coord


# -- scope: only the strict axis can move ------------------------------------


def _strict_without_alias(pred_refs, expected_refs):
    """The pre-repair formula, re-implemented here so the delta can be measured."""
    exp = _clean(expected_refs)
    got = _clean(pred_refs)
    return sum(1 for e in exp if any(_is_descendant(p, e) for p in got)) / len(exp)


def test_the_alias_is_the_only_difference_on_the_strict_axis():
    """New == old except on rows it is designed to repair, and never below old."""
    battery = [
        (RG_008_RIGHT, RG_008_KEY),
        (RG_008_WRONG, RG_008_KEY),
        (["Article 6.1"], RG_008_KEY),
        (["Annex I"], RG_008_KEY),
        (["Annex I.11.a"], ["Annex I.a.11"]),
        (["Annex IV.1"], ["Annex IV.1.e"]),
        (["Article 13.3"], ["Article 13.3.a"]),
        (["Annex III.1.a"], ["Annex III.1.a"]),
        (["Annex VIII.1"], ["Annex VIII.b.1"]),
    ]
    for preds, key in battery:
        new = reference_correctness_strict(preds, key)
        old = _strict_without_alias(preds, key)
        assert new >= old, (preds, key)
        if new != old:
            assert any(
                canonical_annex_point(ref) != ref
                for ref in (*_clean(preds), *_clean(key))
            ), "a gain outside section-key normalization would be an unexpected widening"


def test_loose_and_conciseness_are_bit_identical_between_the_readings():
    """The repair is scoped to the strict axis; the other two reference axes see
    the same numbers for the right and the wrong citation, exactly as before.
    """
    for axis in (reference_correctness_loose, reference_conciseness):
        assert axis(RG_008_RIGHT, RG_008_KEY) == axis(RG_008_WRONG, RG_008_KEY)


def test_loose_already_agreed_because_it_is_scored_at_head_grain():
    """Why the defect was invisible on loose: both spellings fold to ``Annex I``."""
    assert reference_correctness_loose(RG_008_RIGHT, RG_008_KEY) == 1.0
    assert reference_correctness_loose(RG_008_WRONG, RG_008_KEY) == 1.0

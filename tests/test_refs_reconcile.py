"""R72 — reference reconciliation (refs-faithfulness).

The LLM-as-judge's refs axis penalises any cited Article/Annex whose
content the answer prose never describes. After the answer is final the
route drops wire references the Stage-2-polished prose never names, so
the focused 3-sentence answer and the wire `references` list stay
consistent. These tests pin the pure reconciliation helpers.
"""
from app.routes.regenold import (
    _REFS_RECONCILE_FLOOR,
    _reconcile_references_to_prose,
    _reference_described_in_prose,
)


# ── _reference_described_in_prose ──


def test_described_article_named_in_prose():
    assert _reference_described_in_prose(
        "Article 25", "A modifier becomes a new provider under Article 25."
    )


def test_described_art_abbreviation_form():
    assert _reference_described_in_prose("Article 51", "Per Art. 51 the model ...")


def test_undescribed_article_absent_from_prose():
    assert not _reference_described_in_prose(
        "Article 9", "This is about Article 25 and Article 51 only."
    )


def test_subpoint_ref_described_when_base_article_named():
    # A subpoint ref counts as described when its BASE article is named.
    assert _reference_described_in_prose(
        "Article 13.2.a", "Article 13 sets the transparency duty."
    )


def test_annex_ref_described():
    assert _reference_described_in_prose(
        "Annex IV.2", "See Annex IV for the technical documentation."
    )


def test_no_false_match_on_longer_article_number():
    # "Article 25" must not match inside "Article 250".
    assert not _reference_described_in_prose("Article 25", "Article 250 is fictional.")


def test_annex_no_false_match_ii_vs_iii():
    assert not _reference_described_in_prose("Annex II", "Only Annex III is relevant.")


def test_empty_inputs_are_not_described():
    assert not _reference_described_in_prose("", "Article 5 applies.")
    assert not _reference_described_in_prose("Article 5", "")


# ── _reconcile_references_to_prose ──


def test_tr_v2_006_reconciles_to_described_set():
    """The real tr_v2_006 failure: answer describes Art 51 + 25, but the
    wire shipped 5 refs. Reconciliation drops the 3 undescribed extras —
    landing exactly on the gold {25, 51}."""
    prose = (
        "This is a general-purpose AI model question under Article 51. "
        "The one-third fine-tune rule determines whether a downstream "
        "modifier becomes a new provider under Article 25."
    )
    refs = ["Article 53", "Article 25", "Article 51", "Article 55", "Article 9"]
    assert _reconcile_references_to_prose(refs, prose) == ["Article 25", "Article 51"]


def test_all_described_is_a_noop():
    prose = "Article 25 and Article 51 both apply here."
    refs = ["Article 25", "Article 51"]
    assert _reconcile_references_to_prose(refs, prose) == refs


def test_none_described_tops_up_to_floor():
    # No ref named → keep the top `floor` refs (recall insurance),
    # never empty the list.
    refs = ["Article 9", "Article 53", "Article 55"]
    out = _reconcile_references_to_prose(refs, "Generic prose, no citations.")
    assert out == refs[:_REFS_RECONCILE_FLOOR]
    assert len(out) == _REFS_RECONCILE_FLOOR


def test_described_set_below_floor_tops_up():
    # 1 described + top-up to floor=2 with the highest-ranked undescribed.
    prose = "Only Article 25 is discussed."
    refs = ["Article 9", "Article 25", "Article 53"]
    out = _reconcile_references_to_prose(refs, prose)
    assert "Article 25" in out
    assert len(out) == _REFS_RECONCILE_FLOOR
    # Original order preserved.
    assert out == [r for r in refs if r in set(out)]


def test_order_preserved():
    prose = "Article 51 ... Article 9 ... Article 25."
    refs = ["Article 9", "Article 25", "Article 51"]
    # all three described → noop, order intact
    assert _reconcile_references_to_prose(refs, prose) == refs


def test_empty_references_returns_empty():
    assert _reconcile_references_to_prose([], "anything") == []


def test_fail_soft_on_bad_input():
    # Non-string ref must not raise — fail-soft returns input unchanged.
    bad = ["Article 25", None]  # type: ignore[list-item]
    out = _reconcile_references_to_prose(bad, "Article 25 applies.")
    assert out == bad

"""R397 — the coordinate guard and the coordinate-map prompt, on the wire.

Both levers exist because of one gap: **nothing knew which sub-point
coordinates are real.** ``article_existence`` stops at the 126 heads, so
``Article 13.9`` passes the lint floor (``Art. 13`` exists) even though Article
13 has three paragraphs. R386's deepener mints coordinates at a measured 77 %
accuracy and had nothing to check them against.

* ``_repair_nonexistent_coordinates`` folds an impossible coordinate back onto
  its head — **head-preserving, so hard rule #8 delta is +0 by construction.**
* ``_valid_coordinate_line`` tells Stage-2 the real range instead of leaving it
  to guess.

These tests assert on BEHAVIOUR, not on the shape of the code: R329's three
rerank placements all read correctly in the diff and all made zero calls.
"""

from __future__ import annotations

import pytest

from app.data.provision_coordinates import coordinate_exists
from app.engines import _graph_rag_impl as impl
from app.routes.regenold import (
    _coord_guard_enabled,
    _repair_nonexistent_coordinates,
)


# -- the guard --------------------------------------------------------------


def test_the_guard_is_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_REF_COORD_GUARD", raising=False)
    assert _coord_guard_enabled() is True
    # ...and two-sided: a guard whose OFF state behaves like ON is the inert-
    # feature trap (R360's lesson).
    monkeypatch.setenv("REGENOLD_REF_COORD_GUARD", "0")
    assert _coord_guard_enabled() is False


def test_an_impossible_coordinate_folds_onto_its_head() -> None:
    """Article 13 has three paragraphs, so 13.9 cannot be cited."""
    assert not coordinate_exists("Article 13.9")
    assert _repair_nonexistent_coordinates(["Article 13.9"]) == ["Article 13"]
    assert _repair_nonexistent_coordinates(["Annex III.99"]) == ["Annex III"]


def test_real_coordinates_are_untouched() -> None:
    """A strict no-op on a clean list is the EXPECTED reading, not a failure."""
    refs = ["Article 13.3", "Article 6.2", "Annex III.1", "Article 5"]
    assert _repair_nonexistent_coordinates(refs) == refs


def test_the_head_set_is_preserved_so_hard_rule_8_delta_is_zero() -> None:
    """The whole safety argument, asserted rather than claimed.

    `gold_dropped_head` folds both sides onto heads, so a transform that never
    changes the head set cannot drop a gold head. This is the R381
    parent-collapse shape, not the refuted positional-trimmer family.
    """
    refs = ["Article 13.9", "Article 6.2", "Annex III.99", "Article 12", "Article 3.69"]
    heads = lambda rs: [r.split(".")[0] for r in rs]  # noqa: E731
    assert heads(_repair_nonexistent_coordinates(refs)) == heads(refs)


def test_a_reference_whose_head_is_also_unreal_is_left_alone() -> None:
    """Never swap one bad citation for a different bad citation."""
    assert _repair_nonexistent_coordinates(["Article 999.1"]) == ["Article 999.1"]


def test_the_guard_does_not_duplicate_when_head_and_leaf_both_present() -> None:
    """`[Article 13, Article 13.9]` must not become `[Article 13, Article 13]`."""
    assert _repair_nonexistent_coordinates(["Article 13", "Article 13.9"]) == ["Article 13"]


def test_order_is_preserved() -> None:
    refs = ["Annex III.1", "Article 13.9", "Article 6.2"]
    assert _repair_nonexistent_coordinates(refs) == ["Annex III.1", "Article 13", "Article 6.2"]


# -- the prompt line --------------------------------------------------------


def test_the_coordinate_line_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_COORD_MAP_PROMPT", raising=False)
    assert impl._valid_coordinate_line("Article 13 and Annex III") == ""


def test_the_coordinate_line_states_the_real_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_COORD_MAP_PROMPT", "1")
    line = impl._valid_coordinate_line("Article 13 transparency; Annex III areas; Article 6")
    assert "Article 13 -> .1-.3" in line, "Article 13 has exactly three paragraphs"
    assert "Annex III -> .1-.8" in line, "Annex III has eight areas"
    assert "Article 6 -> .1-.8" in line


def test_the_coordinate_line_stays_terse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer Conciseness has the highest marginal leverage of the eight axes,
    and R380 measured prompt bloat as the source of the fat. One line, capped."""
    monkeypatch.setenv("REGENOLD_COORD_MAP_PROMPT", "1")
    context = " ".join(f"Article {n}" for n in range(1, 60))
    line = impl._valid_coordinate_line(context)
    assert line.count("->") <= 10, "must cap the number of heads"
    assert len(line) < 500, f"{len(line)} chars is not a terse line"


def test_the_coordinate_line_never_emits_a_dangling_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No heads resolved must mean no output at all, not an empty header."""
    monkeypatch.setenv("REGENOLD_COORD_MAP_PROMPT", "1")
    assert impl._valid_coordinate_line("no provisions named here") == ""
    assert impl._valid_coordinate_line("") == ""


def test_the_coordinate_line_reaches_the_stage2_user_message() -> None:
    """Prove it is WIRED, not merely defined — the R329/R331 doctrine.

    Three rerank placements once read correctly in the diff and made zero calls.
    """
    import inspect

    source = inspect.getsource(impl)
    assert "user_message += _valid_coordinate_line(context_text)" in source, (
        "the builder exists but nothing appends it to the Stage-2 user message"
    )

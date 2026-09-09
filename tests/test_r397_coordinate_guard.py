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

# -- the live-path driver ----------------------------------------------------
#
# R398. ``_valid_coordinate_line`` shipped as a DEAD FLAG: its only call site
# was inside ``_llm_generate_answer``, which has no production caller, and the
# test guarding it asserted a source substring — so it stayed green at a call
# count of zero. Everything below drives the REAL Stage-2 path
# (``_claude_max_enhance_answer``), spies the transport, and asserts on the
# bytes dispatched.

_Q = (
    "Under the EU AI Act, what transparency information must a provider give "
    "to deployers of a high-risk AI system under Article 13?"
)


def _drive_stage2(
    monkeypatch: pytest.MonkeyPatch,
    *,
    coord: str | None,
    compact: str = "0",
) -> tuple[int, str]:
    """Run one real Stage-2 dispatch; return (builder call count, user message).

    The transport is replaced by a spy, so nothing leaves the process; the
    dead ``OPENAI_API_BASE`` port is belt-and-braces on top of that.
    """
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
    monkeypatch.setenv("REGENOLD_ANSWER_FIRST", "0")
    monkeypatch.setenv("REGENOLD_PROMPT_COMPACT", compact)
    if coord is None:
        monkeypatch.delenv("REGENOLD_COORD_MAP_PROMPT", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_COORD_MAP_PROMPT", coord)

    calls = 0
    real_builder = impl._valid_coordinate_line

    def counting(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        return real_builder(*args, **kwargs)  # type: ignore[arg-type]

    captured: list[dict[str, object]] = []

    def spy(*_args: object, **kwargs: object) -> None:
        captured.append(kwargs)
        return None

    monkeypatch.setattr(impl, "_valid_coordinate_line", counting)
    monkeypatch.setattr(impl, "_openai_wrapper_complete_for_graph_rag", spy)

    context = impl._retrieve_from_kb(impl._deterministic_parse(_Q))
    impl._claude_max_enhance_answer(
        question=_Q,
        kg_answer="HEURISTIC DRAFT SENTINEL",
        context=context,
        original_question=_Q,
    )
    assert captured, "the real Stage-2 transport was never reached"
    user = captured[-1].get("user")
    assert isinstance(user, str), f"no `user` message dispatched: {sorted(captured[-1])}"
    return calls, user


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


def test_the_coordinate_line_reaches_the_stage2_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove it is WIRED by a CALL COUNT and the DISPATCHED prompt.

    R398 — the first version of this test asserted a source substring::

        assert "user_message += _valid_coordinate_line(context_text)" in source

    which passed while the flag was completely inert: the only call site was
    inside ``_llm_generate_answer``, **which has no production caller**. Both
    "the test is green" and "the call count is zero" were true at once — the
    fifth instance of the R329 / R330 / R366 trap in this repo, hit inside a
    test written to prevent it.

    A source grep cannot distinguish a live call site from a dead one, so this
    does not grep. It spies the real Stage-2 transport, counts the builder's
    invocations, and asserts on the bytes actually dispatched — two-sided, so
    a builder that emitted the line unconditionally would fail too.
    """
    calls, captured = _drive_stage2(monkeypatch, coord="1")
    assert calls, "_valid_coordinate_line was never called on the live Stage-2 path"
    assert "VALID COORDINATES" in captured, (
        "the builder ran but its output never reached the dispatched user message"
    )


def test_the_coordinate_line_is_absent_when_the_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two-sided: OFF must really be off on the same path, not merely default."""
    _calls, captured = _drive_stage2(monkeypatch, coord=None)
    assert "VALID COORDINATES" not in captured


def test_the_coordinate_line_survives_the_compact_prompt_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R398 — ``REGENOLD_PROMPT_COMPACT`` REPLACES ``user_message`` wholesale.

    ``build_compact_answer_user`` rebuilds the user message from scratch at
    ``_graph_rag_impl`` ~:9479, discarding everything appended above it. R391
    already had to re-append the pushback clause for exactly this reason.

    MEASURED before the fix: with ``REGENOLD_COORD_MAP_PROMPT=1`` the
    dispatched prompt carried ``VALID COORDINATES`` in the full arm and **not**
    in the compact arm — the lever silently switching itself off in one of the
    two arms an A/B would compare. That is the same class of defect as the
    dead call site, one flag deeper.
    """
    calls, captured = _drive_stage2(monkeypatch, coord="1", compact="1")
    assert calls, "the builder must still run under the compact prompt"
    assert "VALID COORDINATES" in captured, (
        "the compact prompt replacement dropped the R397 coordinate map"
    )


def test_the_compact_prompt_replacement_is_still_two_sided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compact arm must not emit the line when the flag is OFF either."""
    _calls, captured = _drive_stage2(monkeypatch, coord=None, compact="1")
    assert "VALID COORDINATES" not in captured

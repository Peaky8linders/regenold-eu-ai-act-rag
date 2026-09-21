"""R431 — the wire ADD's contract, and the falsified repairs staying falsified.

The ADD is the one pass in the reference pipeline whose output list is LONGER than
its input, so the properties that make it safe have to be pinned rather than
assumed: it may only append a coordinate whose parent is already on the wire (that
is what keeps the folded head SET — and therefore Ref. Correctness (Loose) — fixed),
it may never exceed its cap, and it must be deterministic.

The last two tests are guards against re-introducing levers R431 measured and
rejected. They are here deliberately: both read as obviously-good ideas, and both
cost more than they bought.
"""

from __future__ import annotations

import os

import pytest

from app.routes import regenold as R


def _env(monkeypatch: pytest.MonkeyPatch, **pairs: str) -> None:
    for name, value in pairs.items():
        monkeypatch.setenv(name, value)


def test_add_params_are_clamped_so_a_typo_cannot_add_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(
        monkeypatch,
        REGENOLD_GROUND_WIRE_ADD_ANSWER_RECALL="9",
        REGENOLD_GROUND_WIRE_ADD_QUESTION_RECALL="-4",
        REGENOLD_GROUND_WIRE_ADD_MAX="999",
    )
    a_floor, q_floor, cap = R._ground_wire_add_params()
    assert a_floor == 1.0
    assert q_floor == 0.0
    assert cap == 6, "the cap is clamped to 6, not to whatever the env says"


def test_add_params_fall_back_on_unparseable_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(
        monkeypatch,
        REGENOLD_GROUND_WIRE_ADD_ANSWER_RECALL="not-a-number",
        REGENOLD_GROUND_WIRE_ADD_QUESTION_RECALL="",
        REGENOLD_GROUND_WIRE_ADD_MAX="",
    )
    assert R._ground_wire_add_params() == (0.6, 0.4, 2)


@pytest.mark.parametrize(
    ("child", "parent", "refines"),
    [
        (("6", "1"), ("6", "1"), True),
        (("6", "1", "b"), ("6", "1"), True),
        (("6", "1"), ("6", "1", "b"), False),
        (("6", "2"), ("6", "1"), False),
        (("6",), ("6", "1"), False),
    ],
)
def test_coord_refines_is_the_descendant_relation(
    child: tuple[str, ...], parent: tuple[str, ...], refines: bool
) -> None:
    assert R._coord_refines(child, parent) is refines


def test_add_only_ever_touches_a_parent_already_on_the_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole safety argument: a new HEAD would move Ref. Loose."""
    monkeypatch.setattr(
        R,
        "_limb_discussion",
        lambda coord, a, q: (1.0, 1.0),
    )
    wire = ["Article 6.1", "Article 13"]
    wanted = {
        "article 6": ["Article 6.2", "Article 6.3"],
        "article 9": ["Article 9.1"],  # parent NOT on the wire
    }
    out = R._ground_wire_add_missing(wire, wanted, "answer", "question")
    added = [x for x in out if x not in wire]
    assert added, "the fixture must produce at least one append"
    assert all(not x.startswith("Article 9") for x in added)
    heads_before = {r.split(".")[0] for r in wire}
    heads_after = {r.split(".")[0] for r in out}
    assert heads_before == heads_after


def test_add_respects_the_cap_and_never_duplicates_a_satisfied_limb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(R, "_limb_discussion", lambda coord, a, q: (1.0, 1.0))
    _env(monkeypatch, REGENOLD_GROUND_WIRE_ADD_MAX="1")
    wire = ["Article 6.1", "Article 13.1", "Article 9.1"]
    wanted = {
        "article 6": ["Article 6.2"],
        "article 13": ["Article 13.2"],
        "article 9": ["Article 9.2"],
    }
    out = R._ground_wire_add_missing(wire, wanted, "answer", "question")
    assert len(out) - len(wire) == 1

    # A limb already satisfied at this grain or deeper is not re-appended.
    _env(monkeypatch, REGENOLD_GROUND_WIRE_ADD_MAX="6")
    satisfied = R._ground_wire_add_missing(
        ["Article 6.1.b"], {"article 6": ["Article 6.1"]}, "answer", "question"
    )
    assert satisfied == ["Article 6.1.b"]


def test_add_is_inert_when_the_floors_reject_the_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(R, "_limb_discussion", lambda coord, a, q: (0.1, 0.1))
    wire = ["Article 6.1"]
    assert R._ground_wire_add_missing(
        wire, {"article 6": ["Article 6.2"]}, "answer", "question"
    ) == wire


def test_add_ranking_is_deterministic_not_dict_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ties must resolve on the coordinate string, not on dict insertion order."""
    monkeypatch.setattr(R, "_limb_discussion", lambda coord, a, q: (0.9, 0.9))
    _env(monkeypatch, REGENOLD_GROUND_WIRE_ADD_MAX="1")
    wire = ["Article 6.1"]
    wanted = {"article 6": ["Article 6.9", "Article 6.3"]}
    first = R._ground_wire_add_missing(wire, wanted, "a", "q")
    second = R._ground_wire_add_missing(wire, dict(reversed(list(wanted.items()))), "a", "q")
    assert first == second


def test_add_flag_off_restores_the_substitution_only_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch, REGENOLD_GROUND_WIRE_ADD="0")
    assert R._ground_wire_add_enabled() is False
    _env(monkeypatch, REGENOLD_GROUND_WIRE_ADD="1")
    assert R._ground_wire_add_enabled() is True


def test_the_falsified_substitution_veto_is_not_wired_back_in() -> None:
    """R431 measured this and it lost. It must not reappear as an obvious fix.

    At its only firing floor (0.2-0.3) Ref. Strict fell 0.61 pp net on 495 draws,
    and at 0.4 it never fires because the question recall of the limb it would
    protect is 0.333.
    """
    src = (R.__file__ or "").replace("\\", "/")
    import pathlib  # noqa: PLC0415

    text = pathlib.Path(src).read_text(encoding="utf-8")
    assert "REGENOLD_GROUND_WIRE_SUB_VETO" not in text
    assert "_ground_wire_sub_veto_enabled" not in text


def test_the_wire_add_flags_are_all_registered_in_the_engine_cache_key() -> None:
    """A default-ON lever that changes the wire must key the cache (invariant #5)."""
    import pathlib  # noqa: PLC0415
    import re  # noqa: PLC0415

    text = pathlib.Path((R.__file__ or "").replace("\\", "/")).read_text(encoding="utf-8")
    start = text.index("def _engine_cache_key")
    body = text[start : text.index("\ndef ", start + 10)]
    for name in (
        "REGENOLD_GROUND_WIRE_ADD",
        "REGENOLD_GROUND_WIRE_ADD_MAX",
        "REGENOLD_GROUND_WIRE_ADD_ANSWER_RECALL",
        "REGENOLD_GROUND_WIRE_ADD_QUESTION_RECALL",
    ):
        assert re.search(rf'"{name}"', body), f"{name} missing from _engine_cache_key"


def test_the_trace_reports_appended_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An append leaves ``zip`` short, so the trace used to stay silent."""
    import pathlib  # noqa: PLC0415

    text = pathlib.Path((R.__file__ or "").replace("\\", "/")).read_text(encoding="utf-8")
    assert '_gw_changed += [f"+{b}" for b in _gw_refs[len(references) :]]' in text


def test_limb_discussion_reads_the_coordinate_own_text() -> None:
    """A neighbour must not be able to borrow the limb's score."""
    tokens = {"transparency", "obligations", "providers"}
    answer_recall, question_recall = R._limb_discussion(
        "Article 6.2", tokens, tokens
    )
    assert 0.0 <= answer_recall <= 1.0
    assert answer_recall == question_recall


def test_add_is_skipped_entirely_when_the_wire_is_empty() -> None:
    assert R._ground_wire_add_missing([], {"article 6": ["Article 6.1"]}, "a", "q") == []


def test_env_flag_absent_defaults_to_on() -> None:
    os.environ.pop("REGENOLD_GROUND_WIRE_ADD", None)
    assert R._ground_wire_add_enabled() is True

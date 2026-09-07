"""R393 — closed-set evidence completeness in the Stage-2 grounding block.

MEASURED motivation. ``provision_text.select_relevant_paragraphs`` is a lexical
token-overlap ranker under a char budget; its own docstring says "only WHICH
sub-points are quoted is narrowed". So a question that asks what a provision
REQUIRES is handed a PROPER SUBSET of a closed statutory set. Executed over the
official 110-question batch at the live ``_GROUNDING_REF_CHARS`` of 1200,
counting the members of every provision the graded July-7 run cited:

    closed-set member coverage delivered to Stage-2:  1340/3863 = 34.7%
    86 of 110 questions receive under half the members they need

Every assertion here is on a rendered artefact or a measured invariant, never
on the shape of the code — the standing rule after three R329 rerank placements
all read correctly in the diff and all made zero calls.

The suite is deliberately TWO-SIDED: it pins that the OFF arm really does still
suppress the skeleton, because a guard whose OFF state behaves like its ON state
is the inert-feature trap this repo has paid for four times.
"""
from __future__ import annotations

import re

import pytest

from app.data import article_existence
from app.data.provision_hierarchy import closed_set_members
from app.engines import _graph_rag_impl as G

_CLOSED_SET_PROVISIONS = [
    ("Article 13", "Article 13.3.a"),
    ("Article 17", "Article 17.1.a"),
    ("Article 26", "Article 26.1"),
    ("Article 10", "Article 10.2.a"),
    ("Annex IV", "Annex IV.1.e"),
]


# -- the flag, two-sided -----------------------------------------------------


def test_default_is_off(monkeypatch):
    """New prompt-side levers ship OFF; this one is NOT reference-neutral."""
    monkeypatch.delenv("REGENOLD_CLOSED_SET_SKELETON", raising=False)
    assert G._closed_set_skeleton_enabled() is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on"])
def test_flag_turns_on(monkeypatch, truthy):
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", truthy)
    assert G._closed_set_skeleton_enabled() is True


@pytest.mark.parametrize("falsy", ["0", "", "no", "off", "garbage"])
def test_flag_stays_off(monkeypatch, falsy):
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", falsy)
    assert G._closed_set_skeleton_enabled() is False


# -- numeric knobs fail OPEN -------------------------------------------------


@pytest.mark.parametrize("bad", ["", "abc", "1.5", None])
def test_lead_fails_open(monkeypatch, bad):
    if bad is None:
        monkeypatch.delenv("REGENOLD_CLOSED_SET_SKELETON_LEAD", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON_LEAD", bad)
    assert G._closed_set_skeleton_lead() == 40


def test_lead_is_clamped(monkeypatch):
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON_LEAD", "99999")
    assert G._closed_set_skeleton_lead() == 200
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON_LEAD", "-5")
    assert G._closed_set_skeleton_lead() == 0


@pytest.mark.parametrize("bad", ["", "abc", None])
def test_min_members_fails_open(monkeypatch, bad):
    if bad is None:
        monkeypatch.delenv("REGENOLD_CLOSED_SET_MIN_MEMBERS", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_CLOSED_SET_MIN_MEMBERS", bad)
    assert G._closed_set_min_members() == 3


# -- the member index --------------------------------------------------------


@pytest.mark.parametrize("head,expected_member", _CLOSED_SET_PROVISIONS)
def test_closed_set_is_complete(head, expected_member):
    """The gold coordinate of the official answer key is IN the member list."""
    coords = [c for c, _ in closed_set_members(head)]
    assert expected_member in coords, f"{expected_member} missing from {head}"


def test_members_are_ordered_numerically():
    """26.2 must precede 26.10 — a string sort would invert them."""
    coords = [c for c, _ in closed_set_members("Article 26")]
    assert coords.index("Article 26.2") < coords.index("Article 26.10")


def test_nested_romans_are_preserved():
    """Art. 13(3)(b)(i) is a SubPoint under Point (b), not a scrambled sibling."""
    coords = [c for c, _ in closed_set_members("Article 13")]
    assert "Article 13.3.b.i" in coords
    assert coords.index("Article 13.3.b") < coords.index("Article 13.3.b.i")


def test_non_head_and_bogus_refs_return_empty():
    """A ref that already carries a sub-coordinate is bounded — no expansion."""
    assert closed_set_members("Article 13.3") == []
    assert closed_set_members("Article 999") == []
    assert closed_set_members("not a ref") == []


# -- the rendered skeleton ---------------------------------------------------


def test_every_rendered_coordinate_resolves_in_the_lint_floor():
    """AGENTS.md invariant #2 — a coordinate we SHOW is one we may cite.

    Guards against showing the model a coordinate that would fail the wire
    lint if it echoed it back.
    """
    floor = article_existence.ARTICLE_EXISTENCE
    bad: list[str] = []
    for head, _ in _CLOSED_SET_PROVISIONS:
        for coord, _text in closed_set_members(head):
            base = coord.split(".")[0]
            # The lint floor stores articles as ``Art. N`` and annexes as
            # ``Annex ROMAN``; our coordinates are the wire shape ``Article N``.
            lint_key = base.replace("Article ", "Art. ", 1)
            if lint_key not in floor:
                bad.append(coord)
    assert not bad, f"coordinates outside the 126-ref lint floor: {bad[:10]}"
    assert len(floor) == 126, f"lint floor moved: {len(floor)} refs, expected 126"


def test_rendered_coordinates_use_the_strict_wire_shape():
    """AGENTS.md invariant #1 — ``Article N(.sub)*`` / ``Annex ROMAN(.sub)*``."""
    pattern = re.compile(r"^(Article \d{1,3}|Annex [IVXLCDM]+)(\.[0-9a-z]+)*$")
    for head, _ in _CLOSED_SET_PROVISIONS:
        for coord, _t in closed_set_members(head):
            assert pattern.match(coord), f"non-conforming coordinate: {coord!r}"
            assert "Art." not in coord
            assert "Annex 3" not in coord


def test_skeleton_lists_every_member(monkeypatch):
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "1")
    for head, _ in _CLOSED_SET_PROVISIONS:
        rendered = G._render_closed_set_skeleton(head)
        assert rendered, f"no skeleton for {head}"
        for coord, _t in closed_set_members(head):
            assert coord in rendered, f"{coord} missing from {head} skeleton"


def test_skeleton_declares_the_set_is_exhaustive(monkeypatch):
    """The completeness CLAIM is the point — without it the list is just text."""
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "1")
    rendered = G._render_closed_set_skeleton("Annex IV")
    count = len(closed_set_members("Annex IV"))
    assert "EXHAUSTIVE" in rendered
    assert f"{count} members" in rendered


def test_skeleton_is_none_for_small_and_unresolvable_refs(monkeypatch):
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "1")
    monkeypatch.setenv("REGENOLD_CLOSED_SET_MIN_MEMBERS", "50")
    assert G._render_closed_set_skeleton("Article 13") is None
    monkeypatch.delenv("REGENOLD_CLOSED_SET_MIN_MEMBERS", raising=False)
    assert G._render_closed_set_skeleton("Article 999") is None
    assert G._render_closed_set_skeleton("Article 13.3") is None


def test_lead_zero_renders_coordinates_only(monkeypatch):
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "1")
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON_LEAD", "0")
    rendered = G._render_closed_set_skeleton("Article 13")
    assert "Article 13.3.a" in rendered
    assert "the identity and the contact details" not in rendered


# -- the coverage claim itself, measured -------------------------------------


def test_skeleton_beats_the_shipped_selector_on_member_coverage(monkeypatch):
    """The measured claim: the shipped selector delivers a PROPER SUBSET.

    This is the finding the lever exists to fix, pinned so a change to either
    the selector or the hierarchy re-measures it instead of silently drifting.
    """
    from app.data.provision_text import select_relevant_paragraphs

    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "1")
    question = "What information must the technical documentation contain?"
    shipped_hits = skeleton_hits = total = 0
    for head, _ in _CLOSED_SET_PROVISIONS:
        members = closed_set_members(head)
        shipped = " ".join((select_relevant_paragraphs(head, question, 1200) or "").split())
        rendered = " ".join((G._render_closed_set_skeleton(head) or "").split())
        for _coord, text in members:
            probe = text[:40]
            if not probe:
                continue
            total += 1
            shipped_hits += probe in shipped
            skeleton_hits += probe in rendered
    assert total > 50, "corpus shrank — re-derive the measurement"
    assert skeleton_hits == total, "skeleton must carry EVERY member"
    assert shipped_hits < total * 0.75, (
        "the shipped selector is no longer lossy on closed sets — the premise "
        f"of R393 has changed ({shipped_hits}/{total} delivered); re-measure "
        "before keeping this lever"
    )


# -- prove it fires ON THE REAL PATH, two-sided ------------------------------
#
# The standing rule in this repo: "default-ON + cache-keyed + unit-tested +
# documented is NOT evidence a flag runs. Grep the call site." Three R329
# rerank placements all read correctly in the diff and all made ZERO calls.
# These two tests assert on the output of the REAL renderer the route calls,
# not on the helper in isolation.


def _context_for(refs, question):
    from app.engines._graph_rag_impl import GraphContext

    return GraphContext(
        obligations=[{"article": r, "requirement": "x"} for r in refs],
        question=question,
    )


_Q = "What information must the instructions for use contain?"


def test_real_renderer_is_byte_identical_when_off(monkeypatch):
    """The inert-feature tripwire: OFF must really still suppress it."""
    monkeypatch.delenv("REGENOLD_CLOSED_SET_SKELETON", raising=False)
    ctx = _context_for(["Article 13", "Annex IV"], _Q)
    off = G._render_grounding_text(ctx)
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "0")
    assert G._render_grounding_text(ctx) == off
    joined = "".join(off)
    assert "COMPLETE STRUCTURE" not in joined
    assert "EXHAUSTIVE" not in joined


def test_real_renderer_carries_the_closed_set_when_on(monkeypatch):
    """ON must change the block the model actually receives."""
    ctx = _context_for(["Article 13", "Annex IV"], _Q)
    monkeypatch.delenv("REGENOLD_CLOSED_SET_SKELETON", raising=False)
    off = "".join(G._render_grounding_text(ctx))
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "1")
    on = "".join(G._render_grounding_text(ctx))

    assert on != off, "flag reached no call site — the R329 failure mode"
    assert "COMPLETE STRUCTURE" in on
    # The gold coordinates of the official answer key for these two heads.
    for coord in ("Article 13.3.a", "Article 13.3.f", "Annex IV.1.e", "Annex IV.2.c"):
        assert coord in on, f"{coord} absent from the ON block"
        assert coord not in off, f"{coord} unexpectedly already in the OFF block"
    # The verbatim question-relevant text is KEPT, not replaced.
    assert "VERBATIM (question-relevant)" in on


def test_on_arm_adds_no_new_citable_head(monkeypatch):
    """The citable universe is computed from CONTEXT, never from rendered text.

    ``_extract_context_grounded_refs`` walks ``obligations``/``article_info``/
    ``gaps``. Rendering more statutory prose must not widen it — the same
    property R391 pinned for ``REGENOLD_FULL_PROVISION_EVIDENCE``.

    NOTE this is NOT a claim of reference-neutrality end to end: AGENTS.md
    invariant #5 says the Stage-2 prompt is not a sink, and
    ``_add_prose_named_refs`` still promotes whatever the model NAMES in prose.
    That exposure is what the live ``gold_dropped_head`` gate exists to measure.
    """
    ctx = _context_for(["Article 13", "Annex IV"], _Q)
    monkeypatch.delenv("REGENOLD_CLOSED_SET_SKELETON", raising=False)
    before = G._extract_context_grounded_refs(ctx)
    monkeypatch.setenv("REGENOLD_CLOSED_SET_SKELETON", "1")
    G._render_grounding_text(ctx)
    assert G._extract_context_grounded_refs(ctx) == before

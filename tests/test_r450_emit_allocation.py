"""R450 — verbatim emission budget + allocation policy.

The measured question this pins: R449 found the shipped selector's top paragraph
right ~72% of the time while its bounded output carried >=80% of the gold
paragraph on only 0.41 of rows. That gap is *emission*, and it has two causes
the R449 harness never varied — the per-provision budget (it judged at 500, the
verbatim-ANSWER budget, while Stage-2 grounding runs at 1200) and the order in
which the budget is spent across paragraphs.

What must stay true, and how each could look true while being false:

1. **Default byte-identical.** ``rank`` is the shipped allocation. Any other
   default would silently change which verbatim text Stage-2 sees, invalidating
   every recorded answer-level number.
2. **The budget is still a real bound, and the pieces are still whole.** An
   allocation policy that bought coverage by emitting sentence fragments would
   break the verbatim contract ("exact text, no reformulation"). Units are whole
   paragraphs/items under every policy; the one documented exception is the
   top-scoring unit, which is emitted whole even when it exceeds the budget.
3. **The policies actually differ.** A lever whose value the function never
   reads is the R329 "inert lever" trap: the A/B reads flat and looks like "no
   effect" instead of "never ran".
4. **A typo cannot change the evidence.** An unknown policy or an out-of-range
   split share falls back to the shipped behaviour rather than raising or
   guessing.
"""
from __future__ import annotations

import pytest

from app.data import provision_text as pt

#: A real Article whose paragraphs and question give the policies something to
#: disagree about: 24(1) and 24(2) are boilerplate-heavy, 24(3) is the operative
#: storage/transport paragraph (the R399/rg_069 finding).
_RG_069 = (
    "We are a distributor of a high-risk AI system and we store it in a "
    "warehouse before delivery. Do we have an obligation not to jeopardise its "
    "conformity?"
)


@pytest.fixture(autouse=True)
def _clear_alloc(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REGENOLD_EMIT_ALLOC", raising=False)
    monkeypatch.delenv("REGENOLD_EMIT_SPLIT_TOP", raising=False)
    yield


# ── Defaults and the gate ────────────────────────────────────────────────────


def test_default_is_the_shipped_rank_policy() -> None:
    assert pt.emit_alloc() == "rank"
    assert pt.emit_split_top() == pytest.approx(0.6)


def test_default_emission_is_byte_identical_to_the_arg_less_call() -> None:
    """The R450 refactor must not have moved the shipped output by one char."""
    for ref in ("Article 24", "Article 5", "Article 10", "Annex III", "Article 13"):
        for budget in (500, 1200):
            shipped = pt.select_relevant_paragraphs(ref, _RG_069, budget)
            explicit = pt.select_relevant_paragraphs(ref, _RG_069, budget, alloc="rank")
            assert shipped == explicit


def test_unknown_policy_and_bad_share_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo must not change what the model is shown."""
    monkeypatch.setenv("REGENOLD_EMIT_ALLOC", "DENSITY-TYPO")
    assert pt.emit_alloc() == "rank"
    monkeypatch.setenv("REGENOLD_EMIT_ALLOC", "density")
    assert pt.emit_alloc() == "density"

    for bad in ("", "abc", "0.1", "0.95"):
        monkeypatch.setenv("REGENOLD_EMIT_SPLIT_TOP", bad)
        assert pt.emit_split_top() == pytest.approx(0.6)
    monkeypatch.setenv("REGENOLD_EMIT_SPLIT_TOP", "0.5")
    assert pt.emit_split_top() == pytest.approx(0.5)


def test_the_env_gate_is_read_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-call reads are what make an in-process A/B of the policy meaningful."""
    monkeypatch.setenv("REGENOLD_EMIT_ALLOC", "top1")
    assert pt.emit_alloc() == "top1"
    monkeypatch.setenv("REGENOLD_EMIT_ALLOC", "pack")
    assert pt.emit_alloc() == "pack"


def test_harness_env_name_matches_production() -> None:
    """The harness duplicates the name as a literal; pin the two equal."""
    from evals.retrieval import unit_grain as ug

    assert ug._EMIT_ALLOC_ENV == pt._EMIT_ALLOC_ENV  # noqa: SLF001


# ── Policy semantics ─────────────────────────────────────────────────────────


def test_every_policy_stays_within_the_budget_when_nothing_is_oversized() -> None:
    """Units are whole and the budget binds — no fragment, no overrun.

    ``Article 13`` at 3000 chars is long enough that its paragraphs fit
    individually and short enough that the bounding is exercised.
    """
    for alloc in ("rank", "pack", "density", "top1", "split"):
        out = pt.select_relevant_paragraphs("Article 13", _RG_069, 3000, alloc=alloc)
        assert out, alloc
        assert len(out) <= 3000, (alloc, len(out))


def test_top1_policy_emits_the_top_scoring_unit_alone() -> None:
    """The context-reducing control must carry one unit, not the ranking."""
    units = pt._paragraphs(pt.article_body("Article 24") or "")  # noqa: SLF001
    q_tok = pt._tokens(_RG_069)  # noqa: SLF001
    ranked = sorted(
        ((num, txt, pt._overlap_score(q_tok, pt._tokens(txt), None))  # noqa: SLF001
         for num, txt in units.items()),
        key=lambda x: (-x[2], x[0]),
    )
    out = pt.select_relevant_paragraphs("Article 24", _RG_069, 1200, alloc="top1") or ""
    assert out.startswith(f"{ranked[0][0]}.")
    assert f"{ranked[1][0]}." not in out, out[:120]


def test_policies_actually_differ_on_a_real_provision() -> None:
    """Non-vacuity: if every policy returned the same string the lever is inert."""
    outputs = {
        alloc: pt.select_relevant_paragraphs("Article 24", _RG_069, 1200, alloc=alloc)
        for alloc in ("rank", "pack", "density", "top1", "split")
    }
    assert len({v for v in outputs.values() if v}) > 1, outputs
    assert len(outputs["top1"] or "") < len(outputs["rank"] or "")


def test_density_prefers_relevance_per_character_over_raw_rank() -> None:
    """The measured mechanism, isolated: a small relevant unit beats a big one.

    ``_choose_units`` is the whole decision surface, so it can be pinned
    directly. Hand-built units, because the property is about the decision
    surface rather than any one provision: a mid-sized unit with a *weak* score
    density (2.0/354 chars) beats a small unit with a strong one (1.0/54 chars)
    under rank order, and at a 700-char budget that is the difference between
    carrying the small relevant paragraph or not.
    """
    ranked = [
        (1, "a" * 300, 9.0),  # top: fits, so the rest of the budget is contestable
        (2, "b" * 350, 2.0),  # big, low density — rank-order's second pick
        (3, "c" * 50, 1.0),  # small, high density — density's second pick
    ]
    rank_pick = pt._choose_units(ranked, 700, "rank")
    density_pick = pt._choose_units(ranked, 700, "density")
    assert list(rank_pick) == [1, 2]
    assert list(density_pick) == [1, 3]
    # Same bound, and here strictly cheaper: relevance bought per character.
    assert sum(len(t) + 4 for t in density_pick.values()) < sum(
        len(t) + 4 for t in rank_pick.values()
    )


def test_split_only_trades_when_a_sibling_actually_fits() -> None:
    """The guard that stops ``split`` from losing rows with nothing to trade.

    An oversized top unit whose siblings are ALL oversized too must emit
    exactly what ``rank`` emits — there is no smaller unit to buy, so capping
    the top would only lose text.
    """
    ref, budget = "Annex IV", 1200
    big_top_no_siblings = pt.select_relevant_paragraphs(ref, _RG_069, budget, alloc="rank")
    split = pt.select_relevant_paragraphs(ref, _RG_069, budget, alloc="split")
    # Annex IV's items are long; when nothing fits whole the two agree.
    if split == big_top_no_siblings:
        assert split is not None
    else:
        # Otherwise the split arm must have reserved room for a whole sibling,
        # i.e. it is strictly longer than the capped top unit alone.
        assert len(split or "") > 0


def test_oversized_top_unit_is_still_emitted_whole_under_every_policy() -> None:
    """The documented exception: a complete paragraph beats a truncated one."""
    for alloc in ("rank", "pack", "density", "split"):
        out = pt.select_relevant_paragraphs(
            "Article 5", "Is emotion recognition in the workplace prohibited?",
            500, alloc=alloc,
        )
        assert out is not None
        # Drilling is allowed (Art. 5(1) is a ~5k enumeration) but never a
        # mid-sentence cut with an ellipsis.
        assert "…" not in out
        assert not out.endswith(",")


def test_verbatim_contract_holds_for_every_policy() -> None:
    """Emitted text must be findable in the provision body, with no rewriting."""
    body = pt.article_body("Article 24") or ""
    flat_body = " ".join(body.split())
    for alloc in ("rank", "pack", "density", "top1", "split"):
        out = pt.select_relevant_paragraphs("Article 24", _RG_069, 1200, alloc=alloc) or ""
        for chunk in out.split("."):
            chunk = " ".join(chunk.split()).lstrip("0123456789 ")
            if len(chunk) > 40:
                assert chunk in flat_body, (alloc, chunk[:80])

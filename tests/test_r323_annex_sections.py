"""R323 — section-aware annex item parsing.

Two defects, both of the hard-rule-#4 "wrong text under a correct-looking
citation" class, and both MEASURED before the fix:

1. RESTARTING SECTION NUMBERING COLLAPSED INTO ONE FLAT NAMESPACE.
   Annex VIII has three sections whose item numbering restarts (A: 1-13
   providers, B: 1-9 Article 6(3) providers, C: 1-5 deployers). The flat scan
   was last-writer-wins, so ``Annex VIII(1)`` returned Section C's item 1 —
   "The name, address and contact details of the DEPLOYER" — while Section A's
   item 1 (the PROVIDER) was unreachable. 14 of 27 items were lost. Annex XI
   (Sections 1/2) lost one the same way.

2. THE FIRST ITEM OF A SECTION WAS UNREACHABLE.
   ``_ANNEX_ITEM_RE`` demands ``^`` or ``[.:;]\\s`` before the item number, but
   the regulation introduces a section's first item with the section's TITLE
   WORDS: "...based on the New Legislative Framework 1. Directive 2006/42/EC".
   So Annex I item 1 (the machinery Directive — the canonical Annex I product
   route example) and item 13 (Regulation (EC) No 300/2008) both returned ''.

The recovery is deliberately MINIMAL — it prepends only an item numbered
exactly one below the first strict match. A blanket permissive scan was
measured and REJECTED: it deleted all of Annex I Section B (whose items start
at 13, not 1) and invented items 6-7 in Annex VII out of its ``4.6``-style
sub-numbering. Those negative results are pinned below so the cheaper-looking
approach is not re-attempted.
"""

from __future__ import annotations

import pytest

import app.data.provision_text as PT
from app.data.provision_text import (
    annex_items_sectioned,
    get_provision_text,
)

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]


def _sections(annex: str) -> list[tuple[str | None, dict[int, str]]]:
    return annex_items_sectioned(PT.article_body(f"Annex {annex}") or "")


# ── defect 1: restarting section numbering ──────────────────────────────────


def test_annex_viii_sections_are_separated_not_collapsed() -> None:
    got = {label: sorted(items) for label, items in _sections("VIII") if label}
    assert got == {
        "A": list(range(1, 14)),
        "B": list(range(1, 10)),
        "C": list(range(1, 6)),
    }, f"Annex VIII must expose 13+9+5=27 items across A/B/C, got {got}"


def test_annex_viii_item_1_is_the_provider_not_the_deployer() -> None:
    """The regression that motivated this round.

    A bare ``Annex VIII, point 1`` reads as the FIRST section in document
    order (Section A, providers). Returning Section C's deployer text under
    that citation is a legal fabrication.
    """
    text = get_provision_text("Annex VIII(1)") or ""
    assert "provider" in text.lower(), f"expected the Section A provider item, got {text!r}"
    assert "deployer" not in text.lower(), (
        f"Section C's deployer item must not be served as Annex VIII(1), got {text!r}"
    )


def test_annex_xi_sections_are_separated() -> None:
    got = {label: sorted(items) for label, items in _sections("XI") if label}
    assert got == {"1": [1, 2], "2": [1, 2, 3]}, got


# ── defect 2: the first item of a section ───────────────────────────────────


@pytest.mark.parametrize(
    "item, must_contain",
    [
        (1, "2006/42/EC"),   # machinery Directive — was unreachable
        (12, "2017/746"),    # IVDR — last of Section A
        (13, "300/2008"),    # aviation security — was unreachable
        (20, "2018/1139"),   # EASA — last of Section B
    ],
)
def test_annex_i_first_items_of_each_section_are_reachable(item: int, must_contain: str) -> None:
    text = get_provision_text(f"Annex I({item})") or ""
    assert text.strip(), f"Annex I({item}) resolved to empty"
    assert must_contain in text, f"Annex I({item}) should cite {must_contain}, got {text[:120]!r}"


def test_annex_i_has_all_twenty_items() -> None:
    got = {label: sorted(items) for label, items in _sections("I") if label}
    assert got == {"A": list(range(1, 13)), "B": list(range(13, 21))}, got
    total = sum(len(items) for _, items in _sections("I"))
    assert total == 20, f"Annex I lists 20 instruments, parsed {total}"


# ── the rejected alternative, pinned as a negative result ───────────────────


def test_section_b_items_do_not_start_at_one() -> None:
    """Pins WHY a blanket permissive 'ascending run from 1' scan is wrong.

    Annex I Section B numbers its items 13-20, continuing Section A rather
    than restarting. Any recovery rule that assumes a section starts at 1
    deletes this entire section.
    """
    section_b = dict(_sections("I"))["B"]
    assert min(section_b) == 13, f"Section B starts at 13, got {min(section_b)}"


def test_annex_vii_gains_no_phantom_items() -> None:
    """Annex VII numbers sub-clauses ``4.1``-``4.6``.

    A permissive scan reads those as top-level items 6 and 7. Pin the true
    count so such a regression is caught.
    """
    items = dict(_sections("VII"))[None]
    assert sorted(items) == [1, 2, 3, 4, 5], f"Annex VII has 5 top-level items, got {sorted(items)}"


# ── no regressions on the annexes that were already correct ─────────────────


@pytest.mark.parametrize(
    "ref, must_contain",
    [
        ("Annex III(5)", "essential"),          # essential services — high-risk 5(a)-(d)
        ("Annex IV(1)", "general description"),  # technical documentation
        ("Annex IV(2)", "detailed description"),
        ("Annex X(3)", "Eurodac"),
    ],
)
def test_previously_working_refs_are_unchanged(ref: str, must_contain: str) -> None:
    text = get_provision_text(ref) or ""
    assert must_contain.lower() in text.lower(), f"{ref} changed: {text[:120]!r}"


def test_every_annex_still_resolves() -> None:
    missing = [r for r in ROMAN if not (get_provision_text(f"Annex {r}") or "").strip()]
    assert not missing, f"annexes failed to resolve: {missing}"


def test_unsectioned_annexes_yield_a_single_none_segment() -> None:
    """Callers must be able to treat sectioned and unsectioned annexes alike."""
    for r in ("III", "IV", "V", "IX", "X", "XII"):
        labels = [label for label, _ in _sections(r)]
        assert labels == [None], f"Annex {r} should have no sections, got {labels}"


def test_prose_cross_references_are_not_mistaken_for_headings() -> None:
    """Annexes IV / VI / VII say "Chapter III, Section 2" in running prose.

    That is a cross-reference, not a heading. The comma before it is what
    distinguishes it from a real heading (which follows a clause end), and
    splitting on it would shred those annexes.
    """
    for r in ("IV", "VI", "VII"):
        body = PT.article_body(f"Annex {r}") or ""
        assert "Section 2" in body, f"Annex {r} should contain the prose cross-reference"
        labels = [label for label, _ in _sections(r)]
        assert labels == [None], f"Annex {r} must not be split on a prose cross-reference: {labels}"

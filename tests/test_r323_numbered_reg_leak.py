"""R323 — the pre-2015 OJ numbering form leaked foreign articles onto the wire.

``_NUMBERED_REG_RE`` guards ``_add_prose_named_refs`` against promoting a
CROSS-Regulation article number onto the wire as an EU AI Act citation. Its
first cut required the id to be ``\\d{4}/`` immediately after ``(EU)``/``(EC)``,
which misses both shapes older instruments actually use:

* the ``No `` particle — ``Regulation (EU) **No** 1025/2012``
* a 3-digit sequence number — ``Regulation (EU) No **182**/2011``

The AI Act cites such instruments constantly (Reg 1025/2012 standardisation,
Reg 765/2008 accreditation/CE, Reg 182/2011 committee procedure), so the miss
is reachable. The resulting citations are WIRE-LEGAL — every fabricated number
resolves in ``ARTICLE_EXISTENCE`` — so the hard-rule-#5 catalog lint cannot
catch them. That is what makes this a hard-rule-#4 defect rather than a
cosmetic one:

    Reg 1025/2012 Art 2   -> AI Act Art 2  (Scope)
    Reg 765/2008  Art 30  -> AI Act Art 30 (notifying procedure)
    Reg 182/2011  Art 5   -> AI Act Art 5  (PROHIBITED PRACTICES)

Direction-of-risk note: this guard can only make ``_add_prose_named_refs``
decline to ADD a reference. It can never remove one, so hard rule #8 (a
reference change must drop ZERO gold) is satisfied structurally, and the
recall half is pinned below rather than assumed.
"""

from __future__ import annotations

import pytest

from app.routes.regenold import _NUMBERED_REG_RE, _add_prose_named_refs


# ── the regex itself ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        # The "No " particle — the R323 miss.
        ("of Regulation (EU) No 1025/2012", "1025/2012"),
        ("of Regulation (EC) No 765/2008", "765/2008"),
        ("of Regulation (EU) No 167/2013", "167/2013"),
        ("of Regulation (EU) No 168/2013", "168/2013"),
        ("of Regulation (EC) No 300/2008", "300/2008"),
        # 3-digit sequence numbers.
        ("of Regulation (EU) No 182/2011", "182/2011"),
        # A trailing period on "No." must not break it.
        ("of Regulation (EU) No. 1025/2012", "1025/2012"),
        # The pre-R323 form must keep working.
        ("of Regulation (EU) 2019/1020", "2019/1020"),
        ("of Regulation (EU) 2017/745", "2017/745"),
        # Case-insensitivity.
        ("OF REGULATION (EU) NO 1025/2012", "1025/2012"),
    ],
)
def test_numbered_reg_re_matches_the_oj_numbering_forms(text: str, expected: str) -> None:
    match = _NUMBERED_REG_RE.search(text)
    assert match is not None, f"failed to match {text!r}"
    assert match.group(1) == expected


def test_ai_act_self_reference_still_matches() -> None:
    """The self-reference exclusion downstream keys on group(1) == '2024/1689'.

    If the regex stopped matching the AI Act's own number, that exclusion would
    silently stop working and a genuine AI Act mention would be suppressed —
    a recall loss. Pin it.
    """
    match = _NUMBERED_REG_RE.search("of Regulation (EU) 2024/1689")
    assert match is not None
    assert match.group(1) == "2024/1689"


# ── end-to-end through the production function ──────────────────────────────


@pytest.mark.parametrize(
    "base, prose, forbidden",
    [
        (
            ["Article 99"],
            "Article 2(1), point (c), of Regulation (EU) No 1025/2012 "
            "defines a harmonised standard.",
            "Article 2",
        ),
        (
            ["Article 48"],
            "Rules in Article 30 of Regulation (EC) No 765/2008 apply to CE marking.",
            "Article 30",
        ),
        (
            ["Article 40"],
            "Article 10 of Regulation (EU) No 1025/2012 governs standardisation requests.",
            "Article 10",
        ),
        (
            ["Article 3"],
            "Article 5 of Regulation (EU) No 182/2011 governs the committee procedure.",
            "Article 5",
        ),
    ],
)
def test_foreign_article_is_not_promoted_onto_the_wire(
    base: list[str], prose: str, forbidden: str
) -> None:
    out = _add_prose_named_refs(list(base), prose)
    assert forbidden not in out, (
        f"{forbidden!r} is a {prose.split('of Regulation')[1][:24]!r} article, "
        f"not an EU AI Act one — it must never reach the wire. got {out}"
    )
    assert out == base, f"the guard must leave the base list untouched, got {out}"


# ── the recall half: the guard must not over-suppress ────────────────────────


@pytest.mark.parametrize(
    "base, prose, expected_added",
    [
        # A plain AI Act mention with no instrument nearby.
        (["Article 99"], "Article 13 requires transparency for high-risk systems.", ["Article 13"]),
        # "of this Regulation" is the AI Act itself.
        (
            ["Article 6"],
            "This is governed by Article 5 and Annex III of this Regulation.",
            ["Article 5", "Annex III"],
        ),
        # An EXPLICIT AI Act self-reference must still be added.
        (
            ["Article 40"],
            "Article 43 of Regulation (EU) 2024/1689 sets the conformity route.",
            ["Article 43"],
        ),
    ],
)
def test_genuine_ai_act_references_are_still_added(
    base: list[str], prose: str, expected_added: list[str]
) -> None:
    out = _add_prose_named_refs(list(base), prose)
    added = [r for r in out if r not in base]
    assert added == expected_added, (
        f"recall loss: expected {expected_added} to be added, got {added}"
    )

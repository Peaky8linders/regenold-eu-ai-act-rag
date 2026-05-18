"""Tests for ``app/integrations/regenold/refs.py``.

The centralised converter is the single source of truth for the three
EU AI Act citation forms (internal canonical / user-facing wire /
sub-point composition). These tests pin:

* Round-trip identity (internal → wire → internal)
* Letter-suffix support (R43's regression class)
* Annex Roman casing
* Idempotence of :func:`normalise`
* Strict rejection of the hard-rule violations from CLAUDE.md
  (``Article III``, ``Article 13(1)``, etc.)
"""

from __future__ import annotations

import pytest

from app.integrations.regenold.refs import (
    InvalidRefError,
    RefSpec,
    as_sub_point,
    normalise,
    parse,
    to_internal,
    to_user_facing,
)


# ── Round-trip identity ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "internal,user_facing",
    [
        ("Art. 1", "Article 1"),
        ("Art. 13", "Article 13"),
        ("Art. 113", "Article 113"),
        ("Art. 5(1)", "Article 5.1"),
        ("Art. 5(1)(a)", "Article 5.1.a"),
        ("Art. 5(1)(a)(iii)", "Article 5.1.a.iii"),
        ("Art. 3(63)", "Article 3.63"),  # R34 — definition index
        ("Annex I", "Annex I"),
        ("Annex IV", "Annex IV"),
        ("Annex IV(1)", "Annex IV.1"),
        ("Annex III(1)(a)", "Annex III.1.a"),
        ("Annex XIII", "Annex XIII"),
    ],
)
def test_round_trip(internal: str, user_facing: str) -> None:
    assert to_user_facing(internal) == user_facing
    assert to_internal(user_facing) == internal


def test_round_trip_idempotent_on_user_facing_input() -> None:
    # Feeding wire form into to_user_facing should be a no-op.
    assert to_user_facing("Article 13.2.a") == "Article 13.2.a"
    assert to_user_facing("Annex IV.1") == "Annex IV.1"


def test_round_trip_idempotent_on_internal_input() -> None:
    assert to_internal("Art. 13(2)(a)") == "Art. 13(2)(a)"
    assert to_internal("Annex IV(1)") == "Annex IV(1)"


# ── Letter suffix support (R43 regression class) ────────────────────────


@pytest.mark.parametrize(
    "internal,user_facing",
    [
        ("Art. 5(1)(a)", "Article 5.1.a"),
        ("Art. 5(1)(b)", "Article 5.1.b"),
        ("Art. 5(1)(h)", "Article 5.1.h"),
        ("Art. 50(2)(d)", "Article 50.2.d"),
    ],
)
def test_letter_suffixes(internal: str, user_facing: str) -> None:
    assert to_user_facing(internal) == user_facing
    assert to_internal(user_facing) == internal


# ── Annex Roman casing ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected_user",
    [
        ("Annex iii", "Annex III"),
        ("annex IV(1)", "Annex IV.1"),
        ("ANNEX vii.2", "Annex VII.2"),
    ],
)
def test_annex_mixed_case_input_uppercases(raw: str, expected_user: str) -> None:
    assert to_user_facing(raw) == expected_user


# ── parse() typed result ────────────────────────────────────────────────


def test_parse_returns_typed_article_spec() -> None:
    spec = parse("Art. 13(2)(a)")
    assert spec == RefSpec(article_number=13, subpoints=("2", "a"))
    assert spec.article_number == 13
    assert not spec.is_annex


def test_parse_returns_typed_annex_spec() -> None:
    spec = parse("Annex IV(1)")
    assert spec == RefSpec(annex_roman="IV", subpoints=("1",))
    assert spec.is_annex
    assert spec.article_number is None


def test_parse_handles_bare_article() -> None:
    spec = parse("Article 13")
    assert spec.article_number == 13
    assert spec.subpoints == ()


def test_parse_accepts_article_prefix_variant() -> None:
    # Both "Art." and "Article" must parse to the same spec.
    assert parse("Art. 13") == parse("Article 13")
    assert parse("Art. 13(2)(a)") == parse("Article 13.2.a")


# ── as_sub_point() composition ──────────────────────────────────────────


@pytest.mark.parametrize(
    "parent,sub,expected_internal",
    [
        ("Art. 5", "1(a)", "Art. 5(1)(a)"),
        ("Art. 5", "1.a", "Art. 5(1)(a)"),
        ("Art. 5", "a", "Art. 5(a)"),
        ("Article 5", "1.a", "Art. 5(1)(a)"),  # accepts user-facing parent
        ("Annex IV", "1", "Annex IV(1)"),
        ("Art. 5(1)", "a", "Art. 5(1)(a)"),  # extends existing chain
    ],
)
def test_as_sub_point(parent: str, sub: str, expected_internal: str) -> None:
    assert as_sub_point(parent, sub) == expected_internal


def test_as_sub_point_rejects_empty_sub() -> None:
    with pytest.raises(InvalidRefError):
        as_sub_point("Art. 5", "")


# ── normalise() idempotence ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        "Art. 13",
        "Article 13",
        "Art. 13(2)(a)",
        "Article 13.2.a",
        "Annex IV",
        "Annex iv",  # mixed case
        "  Article 5.1.a  ",  # whitespace
        "annex iv(1)",  # mixed-case with paren tail
    ],
)
def test_normalise_idempotent(raw: str) -> None:
    once = normalise(raw)
    twice = normalise(once)
    assert once == twice


def test_normalise_yields_user_facing_form() -> None:
    # The canonical form is the wire form (Regenold spec output).
    assert normalise("Art. 13(2)(a)") == "Article 13.2.a"
    assert normalise("Annex iv(1)") == "Annex IV.1"


# ── Rejection of hard-rule violations ───────────────────────────────────


@pytest.mark.parametrize(
    "garbage",
    [
        "Article III",  # Roman article number — CLAUDE.md hard rule
        "Article iii",  # Roman article number (lowercased)
        "Art. III",  # Roman article number (Art. prefix)
        "",
        "   ",
        "Article",  # missing number
        "Annex",  # missing roman
        "Foo 13",  # wrong prefix
        "Article 13.foo bar",  # space inside sub-point chain
        "Annex 3",  # Arabic for annex (hard rule)
        "Article 13/2",  # slash separator (hard rule)
    ],
)
def test_parse_rejects_garbage(garbage: str) -> None:
    with pytest.raises(InvalidRefError):
        parse(garbage)


def test_to_user_facing_rejects_garbage() -> None:
    with pytest.raises(InvalidRefError):
        to_user_facing("Article III")
    with pytest.raises(InvalidRefError):
        to_user_facing("Annex 3")


def test_to_internal_rejects_garbage() -> None:
    with pytest.raises(InvalidRefError):
        to_internal("Article III")


def test_parse_none() -> None:
    with pytest.raises(InvalidRefError):
        parse(None)  # type: ignore[arg-type]


# ── Hard-rule output validation ─────────────────────────────────────────


def test_output_never_emits_internal_form_on_wire() -> None:
    # Per CLAUDE.md, the wire must never carry "Art. 13" or paren shapes.
    out = to_user_facing("Art. 13(1)(a)")
    assert "Art." not in out
    assert "(" not in out
    assert ")" not in out


def test_output_never_emits_arabic_annex() -> None:
    # "Annex 3" is forbidden — Roman only on the wire.
    out = to_user_facing("Annex III(2)")
    assert out == "Annex III.2"
    assert "Annex 3" not in out


# ── Whitespace tolerance ───────────────────────────────────────────────


def test_leading_trailing_whitespace_tolerated() -> None:
    assert to_user_facing("  Art. 13  ") == "Article 13"
    assert to_internal("\tArticle 13.2\t") == "Art. 13(2)"

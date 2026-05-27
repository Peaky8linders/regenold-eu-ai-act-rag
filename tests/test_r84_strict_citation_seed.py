"""R84-C — Neo4j seeder ``strict_citation`` + ``legal_type`` property tests.

Exercises :func:`scripts.seed_neo4j_kb.build_payload` to verify every
Article and Annex node in the dry-run payload carries the R84-C audit-
time hardening properties:

* ``legal_type`` — explicit denormalisation of the node label
  (``"Article"`` / ``"Annex"``) so Neo4j Browser queries can filter
  without needing to know the label namespace.
* ``strict_citation`` — the user-facing reference shape per CLAUDE.md
  hard rule #1 (``"Article N"`` Arabic / ``"Annex X"`` Roman
  uppercased; never ``"Art. 13"`` / ``"Annex 3"`` / ``"Article III"``).

Sub-point child nodes (``Art. 13(2)(a)``) are deliberately out of scope
in R84-C — only base Article/Annex nodes are seeded today.
"""
from __future__ import annotations

import re

import pytest

from scripts.seed_neo4j_kb import SeedPayload, build_payload


_STRICT_ARTICLE_RE = re.compile(r"^Article \d+$")
_STRICT_ANNEX_RE = re.compile(r"^Annex [IVXLCDM]+$")


@pytest.fixture(scope="module")
def payload() -> SeedPayload:
    return build_payload()


# ─── R84-C property presence + shape ─────────────────────────────────────


class TestR84StrictCitationSeed:
    """Every Article payload entry carries the R84-C properties."""

    def test_every_article_carries_legal_type(self, payload: SeedPayload) -> None:
        for node in payload.article_nodes:
            assert node.get("legal_type") == "Article", node

    def test_every_article_carries_strict_citation(self, payload: SeedPayload) -> None:
        for node in payload.article_nodes:
            sc = node.get("strict_citation")
            assert sc is not None, node
            assert _STRICT_ARTICLE_RE.match(sc), (
                f"Article {node.get('id')} has malformed strict_citation "
                f"{sc!r} — must match ^Article \\d+$"
            )

    def test_every_annex_carries_legal_type(self, payload: SeedPayload) -> None:
        for node in payload.annex_nodes:
            assert node.get("legal_type") == "Annex", node

    def test_every_annex_carries_strict_citation(self, payload: SeedPayload) -> None:
        for node in payload.annex_nodes:
            sc = node.get("strict_citation")
            assert sc is not None, node
            assert _STRICT_ANNEX_RE.match(sc), (
                f"Annex {node.get('id')} has malformed strict_citation "
                f"{sc!r} — must match ^Annex [IVXLCDM]+$"
            )

    def test_count_113_articles_present(self, payload: SeedPayload) -> None:
        assert len(payload.article_nodes) == 113

    def test_count_13_annexes_present(self, payload: SeedPayload) -> None:
        assert len(payload.annex_nodes) == 13


# ─── Spot-checks (Round-83 + canonical refs) ──────────────────────────────


class TestR84StrictCitationSpotChecks:
    """Hand-picked Articles + Annexes exercise the canonical shapes."""

    def test_article_1_strict_citation(self, payload: SeedPayload) -> None:
        node = next(n for n in payload.article_nodes if n["number"] == "1")
        assert node["strict_citation"] == "Article 1"

    def test_article_13_strict_citation(self, payload: SeedPayload) -> None:
        node = next(n for n in payload.article_nodes if n["number"] == "13")
        assert node["strict_citation"] == "Article 13"

    def test_article_113_strict_citation(self, payload: SeedPayload) -> None:
        # Boundary: the highest-numbered Article in the regulation.
        node = next(n for n in payload.article_nodes if n["number"] == "113")
        assert node["strict_citation"] == "Article 113"

    def test_annex_i_strict_citation(self, payload: SeedPayload) -> None:
        node = next(n for n in payload.annex_nodes if n["number"] == "I")
        assert node["strict_citation"] == "Annex I"

    def test_annex_iv_strict_citation(self, payload: SeedPayload) -> None:
        node = next(n for n in payload.annex_nodes if n["number"] == "IV")
        assert node["strict_citation"] == "Annex IV"


# ─── Hard-rule conformance (CLAUDE.md #1) ────────────────────────────────


class TestR84StrictCitationHardRule:
    """No payload entry may leak the internal / banned citation shapes."""

    def test_no_art_dot_prefix(self, payload: SeedPayload) -> None:
        """``Art. 13`` is the internal canonical form — never on the wire."""
        for node in payload.article_nodes:
            assert not node["strict_citation"].startswith("Art."), node

    def test_no_arabic_annex(self, payload: SeedPayload) -> None:
        """``Annex 3`` is forbidden — annex IDs MUST be Roman uppercased."""
        for node in payload.annex_nodes:
            sc = node["strict_citation"]
            # Must contain no Arabic digit anywhere in the annex form.
            tail = sc.removeprefix("Annex ").strip()
            assert not tail.isdigit(), node

    def test_no_article_iii_roman(self, payload: SeedPayload) -> None:
        """``Article III`` is forbidden — article IDs MUST be Arabic."""
        for node in payload.article_nodes:
            sc = node["strict_citation"]
            tail = sc.removeprefix("Article ").strip()
            assert tail.isdigit(), node

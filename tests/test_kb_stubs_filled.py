"""Sanity checks for the 12 newly-filled KB obligation entries.

Covers the notified-body lifecycle (Arts. 28, 29, 31, 33, 34), harmonised-
standards / common-specs cluster (Arts. 40, 41, 42), enforcement +
confidentiality (Arts. 78, 88), and the previously-missing Annexes IX + X.

Three invariants are enforced:

1. Each entry has a non-empty ``summary`` string of more than 30 chars.
2. Each summary contains a self-reference to the article/annex it covers
   (e.g. the ``Art. 28`` entry mentions ``Art. 28`` at least once) — a
   cheap drift check against accidental copy-paste of a neighbour's text.
3. Every newly added key resolves in :data:`ARTICLE_EXISTENCE` (catches
   typos like ``Art. 280`` before they ship).
"""
from __future__ import annotations

import pytest

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb import EC_CHECKER_OBLIGATION_MAP

# The 12 references added in the notified-body / harmonised-standards /
# enforcement / annexes gap-fill pass.
NEWLY_FILLED_REFS: tuple[str, ...] = (
    "Art. 28",
    "Art. 29",
    "Art. 31",
    "Art. 33",
    "Art. 34",
    "Art. 40",
    "Art. 41",
    "Art. 42",
    "Art. 78",
    "Art. 88",
    "Annex IX",
    "Annex X",
)


class TestNewlyFilledStubs:
    """Each new EC-Checker entry must carry a faithful summary."""

    @pytest.mark.parametrize("ref", NEWLY_FILLED_REFS)
    def test_entry_exists_in_map(self, ref: str) -> None:
        """The entry was actually added to ``EC_CHECKER_OBLIGATION_MAP``."""
        assert ref in EC_CHECKER_OBLIGATION_MAP, (
            f"{ref!r} is missing from EC_CHECKER_OBLIGATION_MAP — "
            "the stub fill-in pass did not run for this reference."
        )

    @pytest.mark.parametrize("ref", NEWLY_FILLED_REFS)
    def test_summary_non_empty_and_substantive(self, ref: str) -> None:
        """``summary`` is a non-empty string of > 30 chars."""
        entry = EC_CHECKER_OBLIGATION_MAP[ref]
        assert "summary" in entry, f"{ref!r}: missing 'summary' key"
        summary = entry["summary"]
        assert isinstance(summary, str), (
            f"{ref!r}: summary is {type(summary).__name__}, expected str"
        )
        assert len(summary) > 30, (
            f"{ref!r}: summary is only {len(summary)} chars — "
            "looks like a placeholder, expected a faithful 1-3 sentence "
            "regulator-defensible summary."
        )

    @pytest.mark.parametrize("ref", NEWLY_FILLED_REFS)
    def test_summary_self_references_anchor(self, ref: str) -> None:
        """Each summary mentions its own anchor (``Art. N`` / ``Annex X``).

        Cheap drift check: a summary that doesn't name its own article
        is almost certainly a copy-paste of a neighbour's text.
        """
        summary = EC_CHECKER_OBLIGATION_MAP[ref]["summary"]
        assert ref in summary, (
            f"{ref!r}: summary does not contain its own anchor — "
            f"summary text: {summary!r}"
        )

    @pytest.mark.parametrize("ref", NEWLY_FILLED_REFS)
    def test_key_resolves_in_article_existence(self, ref: str) -> None:
        """The key is a real EU AI Act provision per ``ARTICLE_EXISTENCE``."""
        assert ref in ARTICLE_EXISTENCE, (
            f"{ref!r} is not in ARTICLE_EXISTENCE — "
            "either it is a typo or article_existence.py needs updating."
        )


# ── R53.2 — Omnibus + GPAI Commission-Guidelines stub refresh ──


class TestR532OmnibusStubContent:
    """R53.2 — Art. 25 and Art. 101 stub refresh for the V2 judge categories
    (omnibus / gpai). Art. 51 + Art. 113 already carry the Omnibus + 10^23
    FLOPs threshold from R27 (verified by separate R27 fixtures); this class
    pins the Art. 25 / Art. 101 content the R53.2 brief added.
    """

    def test_art_25_mentions_one_third_fine_tune_rule(self) -> None:
        """Art. 25 stub must surface the 1/3 fine-tune rule (Commission's
        18 July 2025 GPAI Guidelines) for downstream-provider classification.
        """
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 25"]["summary"]
        assert "one-third fine-tune" in summary or "1/3" in summary, (
            f"Art. 25 stub missing the one-third fine-tune rule for "
            f"GPAI downstream-provider classification. Summary: {summary!r}"
        )

    def test_art_25_mentions_small_mid_cap_modifier(self) -> None:
        """Art. 25 stub must surface the small-mid-cap modifier extension
        from the Digital Omnibus 7 May 2026 political agreement (Art. 62/63
        SME-tier privileges now apply to small mid-cap entities)."""
        summary_lower = EC_CHECKER_OBLIGATION_MAP["Art. 25"]["summary"].lower()
        assert "small mid-cap" in summary_lower or "small mid cap" in summary_lower, (
            f"Art. 25 stub missing the small-mid-cap modifier from "
            f"Digital Omnibus. Summary: "
            f"{EC_CHECKER_OBLIGATION_MAP['Art. 25']['summary']!r}"
        )

    def test_art_25_anchors_one_third_rule_to_art_51(self) -> None:
        """The Art. 25 one-third rule depends on Art. 51's threshold
        definitions — the stub should cross-reference Art. 51 so the
        retrieval engine surfaces both anchors together for GPAI
        downstream-provider questions."""
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 25"]["summary"]
        assert "Art. 51" in summary, (
            f"Art. 25 stub should cross-reference Art. 51 for GPAI "
            f"threshold context. Summary: {summary!r}"
        )

    def test_art_101_mentions_ai_office(self) -> None:
        """Art. 101 stub must surface 'AI Office' as the GPAI-enforcement
        body. Pre-R53.2 the stub said 'Commission' without naming the AI
        Office — the V2 judge failure pattern was answers that said
        'Commission' when the gold required 'AI Office'.
        """
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 101"]["summary"]
        assert "AI Office" in summary, (
            f"Art. 101 stub missing 'AI Office' as the enforcement body. "
            f"Summary: {summary!r}"
        )

    def test_art_101_disambiguates_ai_office_vs_member_state(self) -> None:
        """Art. 101 stub must call out that Member State market-surveillance
        authorities do NOT have direct fining power over GPAI providers (a
        recurrent V2 conflict-category confusion)."""
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 101"]["summary"]
        assert "market-surveillance" in summary or "market surveillance" in summary, (
            f"Art. 101 stub should disambiguate AI Office vs Member State "
            f"market-surveillance authorities. Summary: {summary!r}"
        )

    def test_art_51_still_has_10_23_flops_threshold(self) -> None:
        """Pre-existing R27 invariant: Art. 51 carries the 10^23 FLOPs
        threshold from the Commission's 18 July 2025 GPAI Guidelines.
        Pinned here so a future Art. 51 edit doesn't silently drop it."""
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 51"]["summary"]
        assert "10^23" in summary or "10²³" in summary, (
            f"Art. 51 stub lost the 10^23 FLOPs Commission-Guidelines "
            f"threshold. Summary: {summary!r}"
        )

    def test_art_113_still_has_omnibus_dates(self) -> None:
        """Pre-existing R27 invariant: Art. 113 carries the Digital Omnibus
        7 May 2026 dates (Annex III high-risk → 2 December 2027; Annex I
        embedded-product → 2 August 2028). Pinned here against silent drop.
        """
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 113"]["summary"]
        assert "2 December 2027" in summary, (
            f"Art. 113 stub lost the Annex III high-risk Omnibus date. "
            f"Summary: {summary!r}"
        )
        assert "2 August 2028" in summary, (
            f"Art. 113 stub lost the Annex I embedded-product Omnibus date. "
            f"Summary: {summary!r}"
        )

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

"""Logical EU AI Act section mapping for scoped retrieval.

R89-A adds a section layer between Chapter and Article for the two
highest-risk retrieval clusters:

* Chapter III: high-risk AI systems (Articles 6-49)
* Chapter V: general-purpose AI models (Articles 51-56)

Other chapters deliberately collapse to their chapter ID. That gives callers
one uniform ``ARTICLE_SECTION`` map without inventing artificial subdivisions
where the Act's retrieval surface is already narrow.
"""
from __future__ import annotations

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.eu_ai_act_corpus import ARTICLE_CHAPTER

_CHAPTER_III_SECTION_RANGES: tuple[tuple[str, range], ...] = (
    ("III.1", range(6, 8)),    # Classification as high-risk
    ("III.2", range(8, 16)),   # Requirements for high-risk AI systems
    ("III.3", range(16, 28)),  # Operator obligations
    ("III.4", range(28, 40)),  # Notifying authorities and notified bodies
    ("III.5", range(40, 50)),  # Standards, conformity, certificates, register
)

_CHAPTER_V_SECTION_RANGES: tuple[tuple[str, range], ...] = (
    ("V.1", range(51, 52)),  # GPAI classification
    ("V.2", range(52, 53)),  # Procedure for systemic-risk classification
    ("V.1", range(53, 55)),  # General GPAI provider duties + representation
    ("V.2", range(55, 56)),  # Additional duties for systemic-risk GPAI
    ("V.3", range(56, 57)),  # Codes of practice
)

# Annexes that are structurally tied to a section. Annexes not in this map
# keep their broad chapter-style fallback section below.
_ANNEX_SECTION: dict[str, str] = {
    "Annex I": "III.1",
    "Annex II": "II",
    "Annex III": "III.1",
    "Annex IV": "III.2",
    "Annex V": "III.5",
    "Annex VI": "III.5",
    "Annex VII": "III.5",
    "Annex VIII": "III.5",
    "Annex IX": "V.1",
    "Annex X": "V.1",
    "Annex XI": "V.1",
    "Annex XII": "V.1",
    "Annex XIII": "V.1",
}


def _section_for_article_number(number: int) -> str | None:
    for section, nums in _CHAPTER_III_SECTION_RANGES:
        if number in nums:
            return section
    for section, nums in _CHAPTER_V_SECTION_RANGES:
        if number in nums:
            return section
    return None


def _build_article_section() -> dict[str, str]:
    out: dict[str, str] = {}
    for ref in ARTICLE_EXISTENCE:
        if ref.startswith("Annex "):
            section = _ANNEX_SECTION.get(ref)
            if section:
                out[ref] = section
            continue
        if not ref.startswith("Art. "):
            continue
        number = int(ref.removeprefix("Art. "))
        section = _section_for_article_number(number)
        if section is None:
            section = ARTICLE_CHAPTER.get(ref) or ""
        if section:
            out[ref] = section
    return out


ARTICLE_SECTION: dict[str, str] = _build_article_section()


def articles_for_sections(sections: tuple[str, ...] | list[str]) -> frozenset[str]:
    """Return all article/annex refs assigned to any requested section."""
    wanted = set(sections)
    if not wanted:
        return frozenset()
    return frozenset(
        ref for ref, section in ARTICLE_SECTION.items()
        if section in wanted
    )


def chapters_for_sections(sections: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Derive broad chapter IDs from section IDs for graceful fallback."""
    chapters = {
        section.split(".", 1)[0]
        for section in sections
        if section
    }
    return tuple(sorted(chapters))


def _self_check() -> None:
    missing = ARTICLE_EXISTENCE - frozenset(ARTICLE_SECTION)
    assert not missing, f"ARTICLE_SECTION missing refs: {sorted(missing)}"
    for ref, section in ARTICLE_SECTION.items():
        assert ref in ARTICLE_EXISTENCE, f"Unknown ref in ARTICLE_SECTION: {ref!r}"
        assert section, f"Empty section for {ref!r}"


_self_check()


__all__ = [
    "ARTICLE_SECTION",
    "articles_for_sections",
    "chapters_for_sections",
]

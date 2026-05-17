"""EU Regulation 2024/1689 article + annex existence catalog.

A flat ``frozenset`` of every article and annex reference that appears in
the AI Act regulation text — used to validate LLM-cited references against
the actual regulation surface, distinct from
``app/data/article_requirements.py::ARTICLE_REQUIREMENTS`` which only
covers articles CodexAI's engines actively implement requirement bullets
for.

Why this exists separately from ``ARTICLE_REQUIREMENTS``:
The kb-reality validator in ``app/engines/roadmap_refiner/models.py`` needs
to answer "is this reference a real EU AI Act provision?" — but
``ARTICLE_REQUIREMENTS`` was authored as the set of articles we have
requirement bullets for, not the full 113-article + 13-Annex regulation
surface. Polluting it with 90+ stub entries to satisfy the validator would
degrade the engines that consume it for actual requirement content.

"""
from __future__ import annotations

# EU Regulation 2024/1689 has 113 numbered articles.
_ARTICLES: frozenset[str] = frozenset(f"Art. {n}" for n in range(1, 114))

# 13 annexes referenced as Annex I…Annex XIII in the regulation text.
_ANNEXES: frozenset[str] = frozenset(
    {
        "Annex I",
        "Annex II",
        "Annex III",
        "Annex IV",
        "Annex V",
        "Annex VI",
        "Annex VII",
        "Annex VIII",
        "Annex IX",
        "Annex X",
        "Annex XI",
        "Annex XII",
        "Annex XIII",
    }
)

#: Flat existence catalog. Membership means "this reference is a real EU AI
#: Act provision" — not "we have requirement bullets for it" (that's
#: ``ARTICLE_REQUIREMENTS``). Sub-paragraph forms like ``Art. 13(1)(a)`` and
#: ``Annex IV(2)`` are NOT enumerated here; the validator's prefix-fallback
#: in ``_is_valid_article_reference`` treats any sub-form of a catalogued
#: parent as valid.
ARTICLE_EXISTENCE: frozenset[str] = _ARTICLES | _ANNEXES

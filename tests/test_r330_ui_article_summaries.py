"""R330 Z1 — the Lexy UI citation-card tooltips must not contradict the Act.

`articlesSummary` in `app/web_ui.py` is browser-side JS inside `HTML_TEMPLATE`,
read only by the citation-card renderer. It is NOT on the answer path, so these
are plain string assertions over the template — no browser, no TestClient.

Two shipped defects motivated this test:

  * `Annex III` named only 5 of the 8 high-risk use-case categories (points 1,
    2, 3, 4, 6), omitting point 5 (essential private and public services),
    point 7 (migration, asylum and border control) and point 8 (administration
    of justice and democratic processes). The live Neo4j graph carries
    `annex_III_1 … annex_III_8`; `app/data/kb.py:1013` lists all eight.
  * `Article 52` was labelled the transparency article. That is 2021-draft
    numbering: in Reg. (EU) 2024/1689 transparency is Art. 50
    (`app/data/kb.py:876`) and Art. 52 is the GPAI systemic-risk classification
    procedure (`app/data/kb.py:1269`).

The truncated Annex III list is a decoy — it matches july7-147's answer wording
five-for-five, in order — so it is worth a regression guard.
"""

from app.web_ui import HTML_TEMPLATE


def _summary_for(key: str) -> str:
    """Return the `articlesSummary` value for `key` from the JS template."""
    marker = '"%s": "' % key
    start = HTML_TEMPLATE.index(marker) + len(marker)
    end = HTML_TEMPLATE.index('",\n', start)
    return HTML_TEMPLATE[start:end]


# The eight Annex III headings, verbatim-derived from the live graph nodes
# annex_III_1 … annex_III_8 (and kb.py:1013). Each entry is a lowercase token
# that must appear somewhere in the Annex III tooltip.
ANNEX_III_AREAS = (
    "biometrics",
    "critical infrastructure",
    "education",
    "employment",
    "essential private and public services",
    "law enforcement",
    "migration, asylum and border control",
    "administration of justice and democratic processes",
)


def test_annex_iii_summary_names_all_eight_areas():
    summary = _summary_for("Annex III").lower()
    missing = [area for area in ANNEX_III_AREAS if area not in summary]
    assert not missing, "Annex III tooltip omits: %s" % missing


def test_annex_iii_summary_states_eight_categories():
    # Guards against a future edit that lists areas but drops the count, which
    # is what let the 5-of-8 version read as complete.
    assert "eight" in _summary_for("Annex III").lower()


def test_article_52_is_not_described_as_the_transparency_article():
    # Art. 52 is the GPAI systemic-risk CLASSIFICATION PROCEDURE (kb.py:1269).
    summary = _summary_for("Article 52").lower()
    assert "transparency" not in summary
    assert "systemic-risk" in summary
    assert "commission" in summary


def test_article_50_carries_the_transparency_obligations():
    # Transparency is Art. 50 (kb.py:876), not Art. 52.
    summary = _summary_for("Article 50").lower()
    assert "transparency" in summary
    assert "deepfake" in summary


def test_transparency_is_claimed_by_exactly_one_article_key():
    # The defect was a duplicate/misplaced claim, not a missing string: assert
    # the transparency blurb lives under one key only.
    claimants = [
        key
        for key in ("Article 13", "Article 50", "Article 52")
        if "transparency obligations" in _summary_for(key).lower()
    ]
    assert claimants == ["Article 50"]

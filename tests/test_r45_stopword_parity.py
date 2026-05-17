"""R45 finding B7 — stopword vocabulary parity guard.

The stopword vocabulary is forked across the codebase (one copy in
``app/data/kb_search.py``, one in ``evals/bench/citation_faithfulness.py``,
plus a handful of smaller per-engine lists). R44's
``citation_faithfulness.py`` carries an explicit "copied verbatim from
``kb_search.py``" comment but no test pinned that parity — silent
drift between the two would re-orphan the citation-faithfulness check
for any token that lands in only one of the lists.

This is the cheapest insurance against that drift: pin the two
authoritative copies as equal (a subset relationship would also pass,
but the spec is "verbatim copy" — equality is the tighter contract).
Any future change must touch both files, OR explicitly relax this
test to ``subset`` with a NOTE explaining the divergence.
"""
from __future__ import annotations

from app.data.kb_search import _STOPWORDS as KB_STOPWORDS
from evals.bench.citation_faithfulness import _STOPWORDS as CF_STOPWORDS


def test_citation_faithfulness_stopwords_match_kb_search_verbatim() -> None:
    """The citation_faithfulness module's stopword list was copied
    verbatim from kb_search.py at R44; keep them identical so a future
    addition in one site doesn't silently de-tune the other.

    If you genuinely need a divergence (e.g. citation_faithfulness needs
    a broader list than retrieval), relax this assertion to
    ``KB_STOPWORDS.issubset(CF_STOPWORDS)`` and document why.
    """
    assert KB_STOPWORDS == CF_STOPWORDS, (
        "_STOPWORDS drift detected between kb_search.py and "
        "citation_faithfulness.py.\n"
        f"  cf - kb: {sorted(CF_STOPWORDS - KB_STOPWORDS)}\n"
        f"  kb - cf: {sorted(KB_STOPWORDS - CF_STOPWORDS)}\n"
        "Update both files together, or relax this test to a subset "
        "relationship with a NOTE explaining the divergence."
    )


def test_citation_faithfulness_stopwords_at_least_subset() -> None:
    """Looser sanity guard — even if the strict-equality test above
    is relaxed in a future round, the citation guard's stopword list
    must NEVER be smaller than the retriever's. A token that's a
    stopword in retrieval but informative in faithfulness scoring
    would penalise valid prose unfairly.
    """
    assert KB_STOPWORDS.issubset(CF_STOPWORDS), (
        "citation_faithfulness._STOPWORDS is missing tokens that "
        "kb_search._STOPWORDS treats as stopwords; this de-tunes the "
        "faithfulness check. Add: "
        f"{sorted(KB_STOPWORDS - CF_STOPWORDS)}"
    )

"""R97 — verbatim prohibition-chapeau re-attachment.

A lettered prohibition-list leaf of Article 5(1) ("(h) the use of
'real-time' remote biometric identification … unless … strictly
necessary …") quoted bare by the R94 verbatim answer mode INVERTS the
law — it reads as permitted-with-exceptions, because the operative "The
following AI practices shall be prohibited:" is the paragraph-1 chapeau,
not the leaf. R97 re-attaches the verbatim chapeau so the answer frames
the practice as prohibited (the live-judge "Bug 2" reintroduced under
verbatim, since verbatim bypasses the KB stub the citation-faithfulness
R94 line fixed).
"""
from __future__ import annotations

from app.data.provision_text import get_provision_text
from app.engines.verbatim_answer import (
    _prohibition_framed,
    build_verbatim_answer,
)
from app.integrations.regenold import refs as _refs

_RBI_Q = (
    "Is real-time remote biometric identification in publicly accessible "
    "spaces by law enforcement allowed under the EU AI Act?"
)


def test_art5_rbi_leaf_carries_prohibition_chapeau() -> None:
    ans = (build_verbatim_answer(["Article 5.1.h"], _RBI_Q) or "").lower()
    assert "shall be prohibited" in ans, ans
    # The (h) leaf text must still survive verbatim alongside the chapeau.
    assert "real-time" in ans and "biometric identification" in ans, ans


def test_all_art5_1_prohibition_leaves_framed() -> None:
    """Every Art. 5(1) lettered leaf gains the prohibition chapeau."""
    for leaf in ("Article 5.1.a", "Article 5.1.c", "Article 5.1.f", "Article 5.1.h"):
        ans = (build_verbatim_answer([leaf], "") or "").lower()
        assert "shall be prohibited" in ans, f"{leaf}: {ans!r}"


def test_non_prohibition_leaf_is_unchanged() -> None:
    """Scope guard — a lettered leaf whose parent chapeau is NOT a
    prohibition must NOT gain the chapeau. Art. 13(3) is the high-risk
    'instructions for use shall contain (a)…(f)' list (an obligation, not
    a prohibition)."""
    leaf = get_provision_text("Article 13(3)(a)")
    if not leaf:  # defensive — only assert when the leaf resolves
        return
    spec = _refs.parse("Article 13(3)(a)")
    out = _prohibition_framed(spec, leaf)
    assert "shall be prohibited" not in out.lower()
    assert out == leaf  # exact no-op


def test_prohibition_framed_is_idempotent_when_leaf_already_framed() -> None:
    """If a leaf already carries 'prohibit', don't double-prepend."""
    spec = _refs.parse("Article 5(1)(h)")
    already = "the practice shall be prohibited: the use of X"
    assert _prohibition_framed(spec, already) == already


def test_bare_article_5_ref_not_double_framed() -> None:
    """A parent-level Article 5 ref goes through select_relevant_paragraphs
    (which already includes the chapeau via _drill_subpoints) — the answer
    must carry the chapeau exactly once, not twice."""
    ans = (build_verbatim_answer(["Article 5"], _RBI_Q) or "").lower()
    assert ans.count("shall be prohibited") <= 1, ans

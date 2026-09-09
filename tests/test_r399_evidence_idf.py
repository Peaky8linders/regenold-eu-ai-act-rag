"""R399 — rarity-weighted Stage-2 paragraph selection.

MEASURED root cause of rg_069 (0/3 criteria, easy) in the 2026-09-07 full live
capture. The question asks a distributor's duty "not to jeopardize its
conformity". Article 24(3) is the ONLY paragraph that answers it, and Article
23(4) the only one answering the importer limb. Scoring paragraphs by RAW
question-token overlap ranks both below paragraphs that merely share the
article's boilerplate, and the Stage-2 evidence budget then cuts them.

No prompt instruction can recover a paragraph that is not in the prompt.
"""
from __future__ import annotations

import pytest

from app.data.provision_text import (
    _overlap_score,
    _sibling_idf,
    get_provision_text,
    select_relevant_paragraphs,
)

RG_069 = (
    "I am a distributor of an AI systems. Do I have obligation not to jeopardize "
    "its conformity? I was not told if the system is high-risk or not. What if am "
    "I am importer instead?"
)


@pytest.fixture
def idf(monkeypatch):
    def _set(on: bool):
        monkeypatch.setenv("REGENOLD_EVIDENCE_IDF", "1" if on else "0")
    return _set


def test_default_is_off(monkeypatch):
    """Reference-affecting ⇒ default OFF until it clears a live gold gate."""
    from app.data.provision_text import _evidence_idf_enabled

    monkeypatch.delenv("REGENOLD_EVIDENCE_IDF", raising=False)
    assert _evidence_idf_enabled() is False


def test_the_off_arm_is_the_legacy_count_exactly():
    """``weights=None`` must reproduce the old score bit for bit, so the OFF
    arm of any A/B is byte-identical to the shipped behaviour."""
    q = {"storage", "transport", "conformity"}
    u = {"storage", "conformity", "market"}
    assert _overlap_score(q, u, None) == float(len(q & u)) == 2.0


def test_a_token_no_sibling_shares_outweighs_boilerplate():
    """One unique token must beat several ubiquitous ones — that inversion is
    the whole lever."""
    units = {1: "alpha common word", 2: "beta common word", 3: "jeopardise storage transport"}
    w = _sibling_idf(units)
    q = {"common", "word", "jeopardise", "storage", "transport"}
    from app.data.provision_text import _tokens

    unweighted = {n: _overlap_score(q, _tokens(t), None) for n, t in units.items()}
    weighted = {n: _overlap_score(q, _tokens(t), w) for n, t in units.items()}
    # Unweighted, the boilerplate paragraphs tie the operative one or beat it.
    assert unweighted[1] == unweighted[2] == 2.0
    # Weighted, the paragraph carrying the distinctive terms wins outright.
    assert weighted[3] > weighted[1] and weighted[3] > weighted[2]


@pytest.mark.parametrize("ref,coordinate", [("Article 24", "Article 24.3"), ("Article 23", "Article 23.4")])
def test_rg069_operative_paragraphs_reach_the_evidence_block(idf, ref, coordinate):
    """Both limbs of the question, at the production grounding budget (1200)."""
    idf(True)
    body = select_relevant_paragraphs(ref, RG_069, 1200) or ""
    assert "storage or transport" in body
    # It is the real adopted paragraph, not a paraphrase.
    verbatim = get_provision_text(coordinate)
    assert verbatim and verbatim.strip()[:60] in body


def test_the_distributor_limb_is_what_regressed(idf):
    """Two-sided. Article 24(3) was OUT with raw counting and is IN with
    rarity weighting; Article 23(4) already landed, so it must not regress."""
    idf(False)
    off = select_relevant_paragraphs("Article 24", RG_069, 1200) or ""
    idf(True)
    on = select_relevant_paragraphs("Article 24", RG_069, 1200) or ""
    assert "storage or transport" not in off, "fixture no longer reproduces the defect"
    assert "storage or transport" in on
    # And it still fits the budget it previously overran by ~13 chars.
    assert len(on) <= 1200


def test_selection_stays_within_budget_and_returns_whole_paragraphs(idf):
    """Never mid-sentence truncation — the verbatim-quote contract."""
    idf(True)
    for ref in ("Article 24", "Article 23", "Article 13", "Article 10", "Annex IV"):
        body = select_relevant_paragraphs(ref, RG_069, 1200) or ""
        assert len(body) <= 1200 or body.count(".") >= 1
        assert not body.endswith("…")


def test_the_flag_reaches_the_engine_cache_key(monkeypatch):
    """AGENTS.md invariant #4 — a response-affecting flag that is not keyed
    makes an A/B serve arm A's cached output to arm B."""
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv("REGENOLD_EVIDENCE_IDF", "0")
    off = _engine_cache_key("What must a distributor verify?", None)
    monkeypatch.setenv("REGENOLD_EVIDENCE_IDF", "1")
    assert _engine_cache_key("What must a distributor verify?", None) != off

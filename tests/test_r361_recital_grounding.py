"""R361 — recital grounding in the judge's provision resolution.

The Graph-Enhanced QA paper's related-recital retrieval (HAS_RELATED_RECITAL)
made recital-cited claims measurable; the engine already retrieves recitals
(fetch_recital_anchors, _expand_referenced_annexes_and_recitals) but the
judge could not ground ``Recital N`` refs. This pins the R361 fix:
_/_resolve_ref_text/ resolves Recitals from OFFICIAL_RECITAL_TEXT, and
_reference_correctness' existence gate is resolution-based (not the
head-lax provision_exists).
"""
from __future__ import annotations

from evals.judge import legal_v2 as L


# ── resolution ───────────────────────────────────────────────────────────


def test_recital_resolves_from_official_corpus():
    import re as _re
    txt = _re.sub(r"\s+", " ", L._resolve_ref_text("Recital 27"))
    assert len(txt) > 500
    assert "trustworthy AI".lower() in txt.lower()


def test_recital_110_resolves():
    txt = L._resolve_ref_text("Recital 110")
    assert len(txt) > 500
    assert "systemic risk".lower() in txt.lower()


def test_unknown_recital_does_not_resolve():
    assert L._resolve_ref_text("Recital 999") == ""
    assert L._ref_exists("Recital 999") is False


def test_article_still_resolves():
    assert L._ref_exists("Article 5") is True


def test_fabricated_leaf_now_flags_non_existent():
    """Resolution-based existence fixes the documented head-lax
    provision_exists finding: 'Article 3.999' is provision_exists-True but
    get_provision_text-None. _ref_exists must resolve it as non-existent so
    the NON_EXISTENT_PROVISION gate actually fires."""
    assert L._ref_exists("Article 3.999") is False


def test_resolve_provision_texts_includes_recitals():
    out = L._resolve_provision_texts(["Recital 27", "Article 5"], cap=2000, max_refs=4)
    assert "Recital 27" in out and len(out["Recital 27"]) > 500
    assert "Article 5" in out


# ── reference_correctness gate ───────────────────────────────────────────


def test_real_recital_is_not_non_existent():
    """A predicted Recital 27 ref must be judged on its merits, not flagged
    NON_EXISTENT (pre-R361 it was — provision_exists('Recital 27') is False
    even though the recital exists)."""
    raw = {"classifications": [{"ref": "Recital 27", "class": "GOVERNING", "quote": ""}]}
    pred_map = {"Recital 27": L._resolve_ref_text("Recital 27")}
    r = L._postprocess_reference_correctness(raw, pred_map, {}, ["Recital 27"], recall_available=False)
    assert "Recital 27" in r["governing_refs"]
    assert "Recital 27" not in r["wrong_refs"]


def test_fabricated_leaf_flagged_wrong():
    raw = {"classifications": [{"ref": "Article 3.999", "class": "GOVERNING", "quote": ""}]}
    r = L._postprocess_reference_correctness(raw, {}, {}, ["Article 3.999"], recall_available=False)
    assert "Article 3.999" in r["wrong_refs"]
    assert r["wrong_refs"] and not r["governing_refs"]


# ── faithfulness grounding (the R360 limitation) ─────────────────────────


def test_faithfulness_prompt_now_grounds_recitals():
    r = {"id": "x", "category": "c", "question": "Q", "answer": "A",
         "pred_refs": ["Recital 110"], "gold_refs": [], "gold_answer": ""}
    prompt, ctx = L._prepare("answer_faithfulness", r)
    assert "Recital 110" in prompt
    assert len(ctx["pred_map"].get("Recital 110", "")) > 500

"""R455b — follow-ups from the adversarial review of R455.

* the R133 surface pass no longer appends a SIBLING of a limb already on the wire
  (R455 made Stage-2 prose parenthesised, which this pass reads, so the unfiltered
  sibling add R428 had kept out came back: rg_050 gained ``Annex III.5.c``);
* the curated workplace emotion answer gives the Article 5(1)(f) verdict and carve-out
  without the treatment of other settings, and cites 5.1.f, not the bare parent.
"""
from __future__ import annotations

import pytest

from app.routes import regenold as R

PROSE = ("It falls under Annex III(5)(b), creditworthiness, and not under Annex III(5)(c), "
         "which concerns life and health insurance.")


def test_no_sibling_added_beside_a_limb_already_on_the_wire(monkeypatch):
    monkeypatch.delenv("REGENOLD_SURFACE_SIBLING_GUARD", raising=False)
    out = R._surface_prose_subpoints(PROSE, ["Annex III.5.b", "Annex III", "Article 6"])
    assert "Annex III.5.c" not in out
    assert out == ["Annex III.5.b", "Annex III", "Article 6"]


def test_guard_off_restores_the_r133_sibling_add(monkeypatch):
    monkeypatch.setenv("REGENOLD_SURFACE_SIBLING_GUARD", "0")
    out = R._surface_prose_subpoints(PROSE, ["Annex III.5.b", "Annex III", "Article 6"])
    assert "Annex III.5.c" in out


@pytest.mark.parametrize("guard", ["1", "0"])
def test_a_bare_parent_is_still_deepened(monkeypatch, guard):
    monkeypatch.setenv("REGENOLD_SURFACE_SIBLING_GUARD", guard)
    out = R._surface_prose_subpoints("Under Article 26(7) the employer informs workers.", ["Article 26"])
    assert out == ["Article 26", "Article 26.7"]


def test_the_guard_is_in_the_cache_key():
    import inspect

    assert '"REGENOLD_SURFACE_SIBLING_GUARD"' in inspect.getsource(R._engine_cache_key)


def test_curated_workplace_emotion_answer_stays_on_the_asked_setting():
    from app.engines._graph_rag_data import _CLASSIFICATION_TOPICS

    topic = next(t for t in _CLASSIFICATION_TOPICS if t["name"] == "emotion_recognition_workplace")
    answer = topic["answer"]
    assert "Article 5(1)(f)" in answer
    assert "medical or safety reasons" in answer and "therapeutic use" in answer
    assert "fatigue" not in answer  # Recital 18: fatigue is not an emotion
    # R410: every sentence carries a cite anchor, so no length cap can drop one
    assert all("Article" in s for s in answer.split(". ") if s.strip())
    assert "Outside those settings" not in answer and "Annex III" not in answer and "Article 50" not in answer
    assert topic["refs"] == ["Art. 5.1.f"]


def test_curated_general_emotion_answer_keeps_all_tiers_in_conventional_form():
    from app.engines._graph_rag_data import _CLASSIFICATION_TOPICS

    topic = next(t for t in _CLASSIFICATION_TOPICS if t["name"] == "emotion_recognition_general")
    assert "Annex III(1)(c)" in topic["answer"] and "Annex III.1(c)" not in topic["answer"]
    assert "Article 50(3)" in topic["answer"]
    assert topic["refs"] == ["Art. 5.1.f", "Annex III.1.c", "Art. 50.3"]

"""R455 — the Stage-2 system prompt no longer asks for dotted coordinates in the prose, and the
"state BOTH sides" rule no longer reaches a concrete deployment whose facts decide the tier.

Case C of the expert review ("monitor the emotions and stress levels of manufacturing line
workers to improve efficiency. Is this allowed?") shipped, on production 9e4e128, prose reading
"Article 5.1.f", "Annex III.1.c" and "Article 26.7", and closed on Annex III and Article 26(7),
the Article 26 drift the expert critique had flagged. Captured at the provider seam, both came
from the single-turn system prompt: rule 2 said to write the dotted "competition format" and
never parentheses (rule 1 and the user-channel clause said "Article 5(1)(f)"), and the
DIRECT-VERDICT rule told the model to state "BOTH sides" for any context-restricted practice.
"""
from __future__ import annotations

from app.data.graph_rag_prompts import resolve_answer_system


def test_prose_citations_use_the_regulation_s_form(monkeypatch):
    for k in ("REGENOLD_MINIMAL_COMPOSER", "REGENOLD_REF_MINIMALITY"):
        monkeypatch.delenv(k, raising=False)
    system = resolve_answer_system()
    assert "competition format" not in system
    assert 'DO NOT use parentheses for paragraphs like "Article 3(2)"' not in system
    assert 'with paragraphs and points in parentheses, as in "Article 5(1)(f)"' in system
    assert 'DO NOT write the dotted identifiers of the references list' in system


def test_both_sides_rule_is_scoped_to_open_context_questions(monkeypatch):
    for k in ("REGENOLD_MINIMAL_COMPOSER", "REGENOLD_REF_MINIMALITY"):
        monkeypatch.delenv(k, raising=False)
    system = resolve_answer_system()
    assert "- Do NOT describe only the one tier the question hints at. If a practice" not in system
    rule = system[system.index("When the question leaves the deciding context open"):]
    rule = rule[: rule.index("\n")]
    # still required where the question leaves the context open (rg_074, rg_085, rg_089)
    assert '"always", "ever", or without stating the setting and purpose' in rule
    assert "or asks about more than one tier, state BOTH sides" in rule
    # and withheld where the stated facts decide the tier
    assert "describes a concrete deployment whose stated setting and purpose already decide the tier" in rule
    assert "do NOT add how other settings, other purposes or other systems would be treated" in rule


def test_emotion_rule_keeps_annex_iii_for_a_stated_safety_purpose_only(monkeypatch):
    for k in ("REGENOLD_MINIMAL_COMPOSER", "REGENOLD_REF_MINIMALITY"):
        monkeypatch.delenv(k, raising=False)
    system = resolve_answer_system()
    assert ("gets the Article 5(1)(f) verdict and its medical or safety carve-out; the Annex III(1)(c) "
            "high-risk treatment belongs in that answer only where the stated purpose is itself medical "
            "or safety.") in system
    # the general "always or ever prohibited?" mapping is unchanged
    assert 'an "is emotion recognition always or ever prohibited?" question must map ALL THREE tiers' in system

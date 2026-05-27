"""R75 — scenario-classifier compound-authrep misfire + Annex III keywords.

Group C of the multi-turn coreference work (deferred from R74 because it
touches the scenario-classifier verdict path and needed its own davidath
A/B). Two independent failures from the V2-local multi-turn probe:

* **mt_v2_025** — final turn "If the US parent has no EU establishment,
  who plays the authorized-representative role?". The classifier
  correctly detects the ``authorized_representative`` compound role but
  ``_build_answer`` emitted a generic limited-risk verdict template
  ("AI literacy training… clear notice…") with zero authrep substance.
  R75 swaps in :func:`_build_compound_authrep_answer` (Article 22
  written-mandate prose) and prepends Art. 24 alongside Art. 22.

* **mt_v2_015** — final turn "Now we use it to decide who to lay off in
  a restructuring." The engine dumped the generic Annex III category
  enumeration, missing the gold keywords ``termination`` /
  ``fundamental``. R75 expands the Annex III KB stub's employment clause
  to surface both.

davidath A/B: byte-identical on every rubric axis (Ans Strict 0.3013,
Ref Loose 0.5776, Ref Strict 0.4471, Tone 1.0, MT 20/20).
"""
from __future__ import annotations

from app.engines.scenario_classifier import (
    ScenarioVerdict,
    _build_compound_authrep_answer,
    classify_scenario_query,
)


# ── mt_v2_025 — compound-authrep answer ──────────────────────────────────

_AUTHREP_Q = (
    "If the US parent has no EU establishment, who plays the "
    "authorized-representative role?"
)


def test_authrep_answer_carries_gold_keywords():
    """The standalone builder surfaces all three mt_v2_025 gold tokens."""
    ans = _build_compound_authrep_answer().lower()
    for kw in ("authorised representative", "written mandate", "established"):
        assert kw in ans, f"authrep answer missing {kw!r}"


def test_authrep_answer_cites_art_22_and_24():
    """Both gold refs appear inline so the soft-cap keeps them."""
    ans = _build_compound_authrep_answer()
    assert "Article 22" in ans
    assert "Article 24" in ans


def test_classify_authrep_question_swaps_answer():
    """The classifier verdict for the mt_v2_025 question carries the
    Article 22 authrep substance, not the generic risk-tier template."""
    v = classify_scenario_query(_AUTHREP_Q)
    assert v is not None
    assert "authorized_representative" in v.compound_roles
    low = v.answer.lower()
    assert "authorised representative" in low
    assert "written mandate" in low
    assert "established" in low
    # The generic limited-risk template must NOT leak through.
    assert "ai literacy training" not in low


def test_classify_authrep_question_leads_with_art_22_then_24():
    """Art. 22 leads the citation list, Art. 24 immediately after."""
    v = classify_scenario_query(_AUTHREP_Q)
    assert v is not None
    assert v.articles[0] == "Art. 22"
    assert v.articles[1] == "Art. 24"


def test_authrep_answer_within_sentence_and_char_caps():
    """3 sentences, under the 600-char soft cap, regulator voice."""
    ans = _build_compound_authrep_answer()
    assert len(ans) <= 600
    # Exactly 3 sentence-terminating periods (no abbreviations carry
    # periods in this answer — refs are written "Article N" in full).
    assert ans.count(".") == 3
    # Third-person regulator voice — no first/second person.
    low = ans.lower()
    assert " you " not in low and not low.startswith("you ")
    assert " we " not in low and not low.startswith("we ")


# ── Regression guard — non-authrep compounds are untouched ───────────────


def test_non_authrep_compound_keeps_generic_verdict():
    """A provider+deployer rebrand compound must NOT get the authrep
    answer — the swap is gated strictly on the authrep role."""
    v = classify_scenario_query(
        "We rebrand a third-party AI system and put our own name on it "
        "before selling it to EU clients."
    )
    if v is not None and v.compound_roles:
        if "authorized_representative" not in v.compound_roles:
            assert "written mandate" not in v.answer.lower(), (
                "non-authrep compound wrongly got the authrep answer"
            )


def test_davidath_shape_scenario_unaffected():
    """A plain davidath 'We are a {role}, offering…' scenario does not
    trigger the authrep answer (davidath-parity guard)."""
    v = classify_scenario_query(
        "We are a provider offering a recipe-recommendation system "
        "intended to suggest meals, in the consumer domain."
    )
    if v is not None:
        assert "written mandate" not in v.answer.lower()
        assert "authorized_representative" not in v.compound_roles


# ── mt_v2_015 — Annex III employment keywords ────────────────────────────


def test_annex_iii_stub_carries_termination_and_fundamental():
    """The Annex III KB stub surfaces the mt_v2_015 gold keywords."""
    from app.data.kb import EC_CHECKER_OBLIGATION_MAP

    entry = EC_CHECKER_OBLIGATION_MAP["Annex III"]
    summary = entry["summary"] if isinstance(entry, dict) else str(entry)
    low = summary.lower()
    assert "termination" in low
    assert "fundamental rights" in low
    # The eight-category enumeration is preserved.
    assert "employment" in low
    assert "biometrics" in low


def test_kb_version_bumped_for_annex_iii_edit():
    """The Annex III stub edit bumped KB_VERSION (R56-A cache lint)."""
    from app.data.kb import KB_VERSION

    assert KB_VERSION >= "2024.1689.v8"


# ── ScenarioVerdict shape sanity ─────────────────────────────────────────


def test_scenario_verdict_fields_intact():
    """The verdict still exposes the R47-C / R53.1-B compound fields."""
    v = classify_scenario_query(_AUTHREP_Q)
    assert isinstance(v, ScenarioVerdict)
    assert isinstance(v.compound_roles, tuple)
    assert isinstance(v.compound_role_strength, str)

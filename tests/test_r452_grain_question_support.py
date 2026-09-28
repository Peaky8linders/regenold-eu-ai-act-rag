"""R452 — the grain deepener abstains when its evidence is vocabulary, not content.

Pinned on the live answers production served on 2026-09-28 (build ``d74c0a6``):
``Annex III.7.b`` on the Annex III amendment and area/use-case questions, and
``Article 5.1.d`` / ``Article 6.3.d`` on the minimal-risk definition. Every case
is two-sided: ``REGENOLD_GRAIN_QUESTION_SUPPORT=0`` must still reproduce the
defect, so the guard cannot silently become inert.
"""
from __future__ import annotations

import pytest

from app.routes import regenold as R

Q17 = (
    "Can the European Commission amend Annex III of the EU AI Act to add or modify "
    "use-cases classified as high-risk AI systems? Under what conditions?"
)
A17 = (
    "Yes. Article 7.1 lets the Commission amend Annex III by delegated act to add or modify "
    "high-risk use-cases, but only where two cumulative conditions are met. First, the systems "
    "must be intended for use in one of the eight areas Annex III already lists: biometrics, "
    "critical infrastructure, education and vocational training, employment and workers' "
    "management, essential private and public services, law enforcement, migration, asylum and "
    "border control, and administration of justice and democratic processes. Second, they must "
    "pose a risk of harm to health and safety, or an adverse impact on fundamental rights, equal "
    "to or greater than that of existing Annex III systems. That risk is weighed against the "
    "Article 7.2 criteria, such as intended purpose, autonomy and severity of harm. Under Article "
    "97, the Commission must first consult Member State experts, and the act enters into force "
    "only if neither the European Parliament nor the Council objects."
)
Q95 = (
    'What is an "area" and what is a "use case" for high-risk as per Article 6(2)? '
    "How many areas exist?"
)
A95 = (
    'Article 6(2) makes an AI system high-risk if it falls within Annex III. Annex III is organised '
    'into eight "areas", which are its numbered headings, and each area contains one or more "use '
    'cases", which are the specific intended uses listed under the heading, mostly as lettered '
    "points. This route is separate from the Article 6(1) product route under Annex I. The eight "
    "areas are biometrics, critical infrastructure, education and vocational training, employment "
    "and workers management, access to essential private and public services and benefits, law "
    "enforcement, migration, asylum and border control management, and administration of justice "
    "and democratic processes. Falling within an area is not enough on its own: the system must "
    "match a listed use case, and the Article 6(3) derogation can still take it out of high-risk, "
    "except where it profiles natural persons. Under Article 7(1)(a), the Commission can add or "
    "modify use cases only within the existing areas, while new areas require the Article 112(2)(a) "
    "review."
)
Q_MIN = "What are AI systems with minimal risks?"
A_MIN = (
    "The EU AI Act does not establish a formal minimal-risk category; minimal risk is descriptive "
    "shorthand for the residual class of systems that are neither prohibited under Article 5, nor "
    "high-risk under Article 6 (as an Annex I safety component or an Annex III use case), nor "
    "subject to the Article 50 transparency duties, nor general-purpose AI models. They have no "
    "mandatory obligations under the Chapter III high-risk regime, but their providers and "
    "deployers remain subject to Article 4 AI literacy duties and may adopt voluntary codes of "
    "conduct under Article 95."
)
Q45 = (
    "Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in "
    "the instructions for use? List the required categories of information."
)
A45 = (
    "Under Article 13.3, the provider must supply instructions for use that give deployers concise, "
    "complete, correct and clear information in six categories. These are: (a) the identity and "
    "contact details of the provider and, where applicable, its authorised representative; (b) the "
    "characteristics, capabilities and limitations of performance, including intended purpose, the "
    "accuracy, robustness and cybersecurity levels, known or foreseeable risk circumstances, "
    "output-explanation capabilities, performance for specific persons or groups, input data "
    "specifications and information to interpret the output; (c) changes predetermined at the "
    "initial conformity assessment; (d) human oversight measures, including technical measures "
    "that help deployers interpret the output; (e) the computational and hardware resources "
    "needed, the expected lifetime, and maintenance and care measures, including software updates; "
    "and (f) a description of the mechanisms to collect, store and interpret the logs."
)

# (head, question, answer, flag OFF result = the live defect, flag ON result)
DEFECTS = [
    ("Annex III", Q17, A17, "Annex III.7.b", "Annex III"),
    ("Annex III", Q95, A95, "Annex III.7.b", "Annex III"),
    ("Article 5", Q_MIN, A_MIN, "Article 5.1.d", "Article 5"),
    ("Article 6", Q_MIN, A_MIN, "Article 6.3.d", "Article 6"),
]


@pytest.mark.parametrize("head,question,answer,off,on", DEFECTS)
def test_defect_reproduces_with_the_guard_off(monkeypatch, head, question, answer, off, on):
    monkeypatch.setenv("REGENOLD_GRAIN_QUESTION_SUPPORT", "0")
    assert R._deepen_one_ref(head, question, answer) == off


@pytest.mark.parametrize("head,question,answer,off,on", DEFECTS)
def test_guard_keeps_the_bare_head(monkeypatch, head, question, answer, off, on):
    monkeypatch.delenv("REGENOLD_GRAIN_QUESTION_SUPPORT", raising=False)  # default ON
    assert R._deepen_one_ref(head, question, answer) == on


@pytest.mark.parametrize("flag", ["0", "1"])
def test_grounded_deepening_is_untouched(monkeypatch, flag):
    """The question's own content words single out 13(3): both arms deepen."""
    monkeypatch.setenv("REGENOLD_GRAIN_QUESTION_SUPPORT", flag)
    assert R._deepen_one_ref("Article 13", Q45, A45) == "Article 13.3"


def test_the_guard_is_veto_only(monkeypatch):
    """ON either matches OFF or returns the bare head; it never picks another unit."""
    for head, question, answer, *_ in DEFECTS + [("Article 13", Q45, A45, None, None)]:
        monkeypatch.setenv("REGENOLD_GRAIN_QUESTION_SUPPORT", "0")
        off = R._deepen_one_ref(head, question, answer)
        monkeypatch.setenv("REGENOLD_GRAIN_QUESTION_SUPPORT", "1")
        on = R._deepen_one_ref(head, question, answer)
        assert on in (off, head), (head, off, on)


def test_generic_tokens_are_the_acts_own_vocabulary():
    generic = R._grain_generic_tokens()
    assert {"risk", "high", "provider"} <= generic
    assert not {"emotion", "workplace", "healthcare", "instruction", "migration"} & generic


def test_enumeration_needs_three_named_headings():
    from app.data import provision_text as pt

    units = pt._annex_items(pt.article_body("Annex III"))
    assert R._answer_enumerates_units(units, A17)
    assert not R._answer_enumerates_units(
        units, "Emergency healthcare patient triage falls under Annex III point 5(d)."
    )
    assert not R._answer_enumerates_units(units, "")


def test_list_level_deepener_on_the_live_rg_018_wire(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAIN_QUESTION_SUPPORT", raising=False)
    out = R._deepen_ref_grain(["Annex III", "Article 7.1", "Article 97"], Q17, A17)
    assert "Annex III" in out and "Annex III.7.b" not in out


def test_flag_reaches_the_engine_cache_key(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAIN_QUESTION_SUPPORT", "0")
    off = R._engine_cache_key("q", "", 0)
    monkeypatch.setenv("REGENOLD_GRAIN_QUESTION_SUPPORT", "1")
    assert R._engine_cache_key("q", "", 0) != off


@pytest.mark.parametrize("flag", ["0", "1"])
def test_definitions_are_picked_by_their_defined_term(monkeypatch, flag):
    """rg_076: 'risk' is Act-wide vocabulary but it is the term being defined."""
    monkeypatch.setenv("REGENOLD_GRAIN_QUESTION_SUPPORT", flag)
    q = 'Under Regulation (EU) 2024/1689 (EU AI Act), how is "risk" defined?'
    a = ("Article 3(2) defines risk as the combination of the probability of an occurrence of "
         "harm and the severity of that harm.")
    assert R._deepen_one_ref("Article 3", q, a) == "Article 3.2"

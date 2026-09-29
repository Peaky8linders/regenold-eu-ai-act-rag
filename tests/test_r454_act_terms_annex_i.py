"""R454 — Annex I points are chosen by the Act the question describes; marking questions
are answered in the Act's terms.

rg_004 ("I have a medical device ...") shipped `Annex I.19` (vehicle type-approval), `I.20`,
`I.4` or a bare `Annex I` across recorded draws, never its gold `Annex I.11`: Article 6(1)'s own
wording ("intended", "safety", "component") matched point 19's title, and once that was
removed "medical device" tied the MDR (point 11) with the IVDR (point 12).
"""
from __future__ import annotations

import pytest

from app.data import graph_rag_prompts as P
from app.routes import regenold as R

RG_004 = (
    'I have a medical device that has an AI system as a safety component. The medical device is '
    'classified "medium-risk" and undergoes a 3rd party conformity assessment. Is the AI system '
    '"medium risk" too? If yes, why? If not, why not?'
)
A_004 = "No. Under Article 6(1), the AI safety component of a medical device covered by Annex I is high-risk."
ROBOT = "Is an AI system intended to be used as a safety component in robotic surgery considered high-risk under the AI Act?"
A_ROBOT = "Yes, under Article 6(1), the robotic surgical device is covered by the MDR listed in Annex I."


@pytest.mark.parametrize("question,answer,expected", [
    (RG_004, A_004, "Annex I.11"),
    (ROBOT, A_ROBOT, "Annex I"),
    ("Is an AI safety component of an in vitro diagnostic medical device high-risk?",
     "Yes, the IVDR is listed in Annex I.", "Annex I.12"),
    ("Can an AI system used as a safety component in a toy be high-risk?",
     "Yes, under Article 6(1) toys are covered by Annex I.", "Annex I.2"),
    ("Is an AI safety component in a lift high-risk?", "Yes: lifts are in Annex I.", "Annex I.4"),
    ("Is AI in civil aviation high-risk under Annex I?", "Civil aviation rules are listed in Annex I.",
     "Annex I.20"),
])
def test_annex_i_point_follows_the_act_the_question_describes(monkeypatch, question, answer, expected):
    monkeypatch.delenv("REGENOLD_GRAIN_ANNEX_I_ACT_SUBJECT", raising=False)
    assert R._deepen_one_ref("Annex I", question, answer) == expected


def test_the_defects_reproduce_with_the_rule_off(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAIN_ANNEX_I_ACT_SUBJECT", "0")
    assert R._deepen_one_ref("Annex I", ROBOT, A_ROBOT) == "Annex I.19"
    assert R._deepen_one_ref("Annex I", RG_004, A_004) != "Annex I.11"


def test_subject_extraction_strips_the_title_framing():
    from app.data import provision_text as pt

    units = pt._annex_items(pt.article_body("Annex I"))
    assert R._annex_i_subject_tokens(str(units[11])) == {"medical", "device"}
    assert R._annex_i_subject_tokens(str(units[4])) == {"lift"}
    assert {"vitro", "diagnostic"} <= R._annex_i_subject_tokens(str(units[12]))


Q74 = ("I generated audio with AI for my artistic work (sole purpose). Do I need to provide some "
       "marking of its artificial nature? I feel that would compromise the enjoyment of the work.")


def test_act_terms_clause_fires_on_a_marking_question(monkeypatch):
    monkeypatch.delenv("REGENOLD_ACT_TERMS_CLAUSE", raising=False)
    clause = P.act_terms_clause(Q74)
    assert 'speaks of "marking"' in clause
    assert "Article 50(2)" in clause and "PROVIDER" in clause
    assert "LIMITS the duty to disclosing the existence of the content; it does not remove it" in clause


@pytest.mark.parametrize("question", [
    "Does a high-risk AI system need a CE marking under the AI Act?",
    "What are the transparency obligations for chatbots?",
    "Which market surveillance authority is competent?",
])
def test_act_terms_clause_stays_silent_elsewhere(monkeypatch, question):
    monkeypatch.delenv("REGENOLD_ACT_TERMS_CLAUSE", raising=False)
    assert P.act_terms_clause(question) == ""


def test_act_terms_reads_only_the_live_turn(monkeypatch):
    monkeypatch.delenv("REGENOLD_ACT_TERMS_CLAUSE", raising=False)
    flat = "Conversation so far:\nUser: do I need a watermark?\nAssistant: ...\nLatest question:\nWho enforces Article 50?"
    assert P.act_terms_clause(flat) == ""


def test_act_terms_flag_off(monkeypatch):
    monkeypatch.setenv("REGENOLD_ACT_TERMS_CLAUSE", "0")
    assert P.act_terms_clause(Q74) == ""


@pytest.mark.parametrize("flag", ["REGENOLD_GRAIN_ANNEX_I_ACT_SUBJECT", "REGENOLD_ACT_TERMS_CLAUSE"])
def test_flags_reach_the_engine_cache_key(monkeypatch, flag):
    monkeypatch.setenv(flag, "0")
    off = R._engine_cache_key("q", "", 0)
    monkeypatch.setenv(flag, "1")
    assert R._engine_cache_key("q", "", 0) != off

"""R453 — Case D (robotic surgery) and Q74 (artistic deep fake), fixed at the source.

Case D: the curated answer said the notified-body assessment was required "under
Article 43" (it is required by the MDR; Article 6(1)(b) keys on that) and never
explained Article 43(3). R311 then dropped the answer's own ``Article 43.3``, and
the curated guard let ``Annex I.19`` (vehicle type-approval) stand for an MDR device.

Q74: the Article 50 KB text told Stage-2 deployers must "label" deep fakes. The Act
says disclose; machine-readable marking is the provider's Article 50(2) duty.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.data import graph_rag_prompts as P
from app.data.kb import EC_CHECKER_OBLIGATION_MAP
from app.routes import regenold as R

CASE_D = "Is an AI system intended to be used as a safety component in robotic surgery considered high-risk under the AI Act?"
LIFT = "Is an AI system used as a safety component of a lift considered high-risk under the AI Act?"


@pytest.fixture(scope="module")
def client():
    saved = {k: os.environ.get(k) for k in ("P2P_GRAPH_RAG_PROVIDER", "OPENAI_API_BASE",
                                            "REGENOLD_EXTERNAL_EMBEDDINGS")}
    os.environ.update({"P2P_GRAPH_RAG_PROVIDER": "cli", "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
                       "REGENOLD_EXTERNAL_EMBEDDINGS": "0"})
    from app.main import app
    from app.rate_limit import limiter

    limiter.enabled = False
    yield TestClient(app)
    limiter.enabled = True
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _ask(client, q):
    R._ENGINE_CACHE.clear()
    r = client.post("/api/v1/regenold/eu-ai-act/ask", json={"messages": [{"role": "user", "content": q}]})
    assert r.status_code == 200, r.text
    return r.json()


def test_case_d_states_the_law_it_cites(client):
    body = _ask(client, CASE_D)
    assert body["references"] == ["Article 6.1", "Annex I", "Article 43.3", "Article 14.4", "Article 72.4"]
    ans = body["answer"]
    assert ans.startswith("Yes")
    assert "Article 43(3)" in ans and "MDR" in ans
    assert "under Article 43." not in ans  # the notified-body duty comes from the MDR


@pytest.mark.parametrize("flag", ["0", "1"])
def test_r311_keeps_a_curated_answers_declared_head(client, monkeypatch, flag):
    monkeypatch.setenv("REGENOLD_CURATED_ROUTE_KEEP", flag)
    refs = _ask(client, CASE_D)["references"]
    assert ("Article 43.3" in refs) is (flag == "1")


def test_r311_still_drops_article_43_on_a_generated_classification_answer(client):
    refs = _ask(client, LIFT)["references"]
    assert not any(r.startswith("Article 43") for r in refs), refs


MDR_ANSWER = "Such a device is covered by the MDR, Regulation (EU) 2017/745, listed in Annex I."
ROBOT_WORDS = ("A safety component must meet the requirements and ensure an equivalent level of "
               "protection intended for the product.")


@pytest.mark.parametrize("flag", ["0", "1"])
def test_curated_annex_i_point_is_backed_only_by_its_act(monkeypatch, flag):
    monkeypatch.setenv("REGENOLD_CURATED_ANNEX_I_ACT_BACKING", flag)
    assert R._curated_answer_backs("Annex I.11", MDR_ANSWER) is (flag == "1")
    if flag == "1":
        assert not R._curated_answer_backs("Annex I.19", MDR_ANSWER + " " + ROBOT_WORDS)


def test_article_50_kb_says_disclose_not_label():
    s50 = EC_CHECKER_OBLIGATION_MAP["Art. 50"]["summary"]
    s504 = EC_CHECKER_OBLIGATION_MAP["Art. 50.4"]["summary"]
    for s in (s50, s504):
        assert "label" not in s.lower()
        assert "Art. 50(2)" in s  # marking belongs to the provider
        assert "does not hamper the display or enjoyment of the work" in s
    assert "machine-readable marking is the provider's duty" in s504
    # Article 50(4) has two subparagraphs, not four
    assert "third subparagraph" not in s50 and "fourth subparagraph" not in s50


def test_rule_j_does_not_tie_the_artistic_limitation_to_law_enforcement():
    clause = P.USER_CRITICAL_RULES_CLAUSE
    j = clause[clause.index("(j) Article 50(4)"):clause.index("(k) Annex VIII")]
    assert "The exemption requires" not in j
    assert "falls away entirely only for use authorised by law" in j
    assert "Article 50(2) duty" in j


@pytest.mark.parametrize("flag", ["REGENOLD_CURATED_ROUTE_KEEP", "REGENOLD_CURATED_ANNEX_I_ACT_BACKING"])
def test_flags_reach_the_engine_cache_key(monkeypatch, flag):
    monkeypatch.setenv(flag, "0")
    off = R._engine_cache_key("q", "", 0)
    monkeypatch.setenv(flag, "1")
    assert R._engine_cache_key("q", "", 0) != off

"""R456 — citation minimality without losing gold.

* ``REGENOLD_DEFINITION_CITE_SCOPE``: an Article 3 definition is cited only when the question
  asks what a term is or names Article 3. The official questions whose gold cites Article 3
  (rg_019, rg_048, rg_076) all ask that; Q74 and Case C cited 3(60) / 3(39) they never asked for.
* ``REGENOLD_PROVISIONS_TO_NAME``: the Stage-2 user channel asks the model to name only the
  provisions that answer the question (cross-referenced articles as content, definitions and
  procedure clauses only when asked), because every named provision becomes a citation.
"""
from __future__ import annotations

import inspect
import json
import pathlib

import pytest

from app.data import graph_rag_prompts as P
from app.routes import regenold as R

Q74 = ("I generated audio with AI for my artistic work (sole purpose). Do I need to provide some marking of "
       "its artificial nature? I feel that would compromise the enjoyment of the work.")
CASE_C = ("A pharmaceutical company wants to use an AI system to monitor the emotions and stress levels of their "
          "manufacturing line workers to improve efficiency. Is this allowed?")


@pytest.mark.parametrize("refs,question,expected", [
    (["Article 50.4", "Article 3.60"], Q74, ["Article 50.4"]),
    (["Article 5.1.f", "Article 3.39"], CASE_C, ["Article 5.1.f"]),
    (["Article 3.60"], "What is a deep fake according to the EU AI Act?", ["Article 3.60"]),
    (["Article 3.3", "Article 3.4", "Article 25.1"], "What is the difference between the deployer and the provider?",
     ["Article 3.3", "Article 3.4", "Article 25.1"]),
    (["Article 3.2"], 'Under Regulation (EU) 2024/1689 (EU AI Act), how is "risk" defined?', ["Article 3.2"]),
    (["Article 3.60"], "Is this allowed?", ["Article 3.60"]),  # never empties
])
def test_definition_scope(refs, question, expected):
    assert R._definition_cite_scope(refs, question) == expected


def test_a_curated_declared_definition_is_kept():
    assert R._definition_cite_scope(["Article 5.1.f", "Article 3.3"], "Is this allowed?", ("Art. 3.3",)) == [
        "Article 5.1.f", "Article 3.3"]


def test_every_official_question_with_article_3_gold_keeps_it():
    root = pathlib.Path(__file__).resolve().parents[1]
    for line in (root / "docs/measurements/r388/official_gold_n110.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        a3 = [e for e in g.get("expected_refs") or [] if e.startswith("Article 3.") or e == "Article 3"]
        if a3:
            assert R._definition_cite_scope(a3, g["question"]) == a3, g["id"]


def test_flags_are_deny_list_and_cache_keyed(monkeypatch):
    src = inspect.getsource(R._engine_cache_key)
    for flag, fn in (("REGENOLD_DEFINITION_CITE_SCOPE", R._definition_cite_scope_enabled),
                     ("REGENOLD_PROVISIONS_TO_NAME", P.provisions_to_name_enabled)):
        assert f'"{flag}"' in src
        monkeypatch.delenv(flag, raising=False)
        assert fn()
        monkeypatch.setenv(flag, "0")
        assert not fn()


def test_provisions_clause_text(monkeypatch):
    monkeypatch.delenv("REGENOLD_PROVISIONS_TO_NAME", raising=False)
    clause = P.provisions_to_name_clause()
    assert "name only the provisions that answer this question" in clause
    assert "without naming the other article" in clause
    assert "only when the question asks what the term means" in clause
    monkeypatch.setenv("REGENOLD_PROVISIONS_TO_NAME", "0")
    assert P.provisions_to_name_clause() == ""


@pytest.mark.parametrize("flag,present", [("1", True), ("0", False)])
def test_clause_reaches_the_dispatched_user_message(monkeypatch, flag, present):
    from unittest.mock import patch

    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.config import settings
    from app.main import app

    settings.regenold.api_key = SecretStr("k")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.setenv("REGENOLD_PROVISIONS_TO_NAME", flag)
    seen = []

    def fake(*args, **kwargs):
        seen.append(str(kwargs.get("user", "")) + " ".join(a for a in args if isinstance(a, str)))
        return "Article 13(3) requires the instructions for use to contain the listed information."

    R._ENGINE_CACHE.clear()
    with patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True), \
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag", side_effect=fake):
        TestClient(app, headers={"X-Regenold-Api-Key": "k"}).post(
            "/api/v1/regenold/eu-ai-act/ask",
            json={"messages": [{"role": "user", "content":
                  "What must a provider of a high-risk AI system supply to the deployer in the instructions for use?"}]},
        )
    assert seen, "Stage-2 was never dispatched"
    assert ("PROVISIONS TO NAME" in seen[0]) is present

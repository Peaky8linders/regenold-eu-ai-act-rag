"""R456 / R456b — citation minimality without losing gold.

* ``REGENOLD_DEFINITION_CITE_SCOPE``: an Article 3 point is cited only when a question the answer
  answers uses the term that point defines (read from the official text), or names Article 3. R456's
  first cut keyed on question wording ("what is", "define"); the review showed it missed "Are we a
  provider or just a deployer?" (Article 3 gold on the probe corpus) and matched "definitely".
* ``REGENOLD_PROVISIONS_TO_NAME``: on single-turn Stage-2, name only the provisions that answer the
  question; state content a cited provision takes from another article without naming it unless it
  supplies a deciding condition; name an Article 3 definition only on a definition ask.

Every scope case carries a non-Article-3 reference as well, so the never-empty fallback cannot mask
a wrong drop.
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
Q95 = 'What is an "area" and what is a "use case" for high-risk as per Article 6(2)? How many areas exist?'


@pytest.mark.parametrize("refs,questions,expected", [
    (["Article 50.4", "Article 3.60"], (Q74,), ["Article 50.4"]),
    (["Article 5.1.f", "Article 3.39"], (CASE_C,), ["Article 5.1.f"]),
    (["Article 6.2", "Article 3.2"], (Q95,), ["Article 6.2"]),  # "risk" inside "high-risk" is not the term
    (["Article 26.5", "Article 3.4"], ("We definitely want to deploy it. Must we inform workers?",), ["Article 26.5"]),
    (["Article 99", "Article 3.60"], ("What is a deep fake according to the EU AI Act?",), ["Article 99", "Article 3.60"]),
    (["Article 99", "Article 3.2"], ('How is "risk" defined?',), ["Article 99", "Article 3.2"]),
    (["Article 26.5", "Article 3.3"], ("Are we a provider or just a deployer?",), ["Article 26.5", "Article 3.3"]),
    (["Article 26.5", "Article 3.4"], ("And for a deployer?",), ["Article 26.5", "Article 3.4"]),
    (["Article 26.5", "Article 3.4"], ("Is this allowed?", "", "What does the deployer owe? Latest question: Is this allowed?"),
     ["Article 26.5", "Article 3.4"]),  # a term in the flattened history counts
    (["Article 26.5", "Article 3.60"], ("Under Article 3, is this covered?",), ["Article 26.5", "Article 3.60"]),
])
def test_definition_scope(refs, questions, expected):
    assert R._definition_cite_scope(refs, questions) == expected


def test_an_unasked_point_is_rewritten_to_the_definition_the_question_uses():
    # tricky_v2:tr_v2_007 (head-level probe gold "Article 3"): a draw cited Article 3(61),
    # "widespread infringement", on a provider-or-deployer question. Dropping it would lose the
    # gold head, so it becomes the definition the question does turn on, in place.
    q = ("We built an internal AI for our own HR use - never released externally. "
         "Are we a provider or just a deployer?")
    assert R._definition_cite_scope(["Article 50.1", "Article 3.61", "Article 6.3.d"], (q,)) == [
        "Article 50.1", "Article 3.3", "Article 6.3.d"]
    # never rewritten to 3(1) "AI system", which nearly every question uses
    assert R._definition_cite_scope(["Article 5.1.f", "Article 3.39"], (CASE_C,)) == ["Article 5.1.f"]


def test_a_curated_declared_definition_is_kept():
    assert R._definition_cite_scope(["Article 5.1.f", "Article 3.3"], ("Is this allowed?",), ("Art. 3.3",)) == [
        "Article 5.1.f", "Article 3.3"]


def test_every_official_question_with_article_3_gold_keeps_it():
    root = pathlib.Path(__file__).resolve().parents[1]
    for line in (root / "docs/measurements/r388/official_gold_n110.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        a3 = [e for e in g.get("expected_refs") or [] if e.startswith("Article 3.") or e == "Article 3"]
        if a3:
            assert R._definition_cite_scope(["Article 99", *a3], (g["question"],)) == ["Article 99", *a3], g["id"]


def test_terms_come_from_the_official_text():
    terms = R._article_3_terms()
    assert len(terms) >= 60
    assert terms[60].search("a deep-fake video") and terms[60].search("deep fakes")
    assert terms[2].search('how is "risk" defined') and not terms[2].search("a high-risk system")


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
    assert "without naming the other article; name it when it supplies a deciding condition" in clause
    assert "only when the question asks what the term means" in clause
    assert "procedure" not in clause  # rg_059's criteria need the Article 98(2) implementing act
    monkeypatch.setenv("REGENOLD_PROVISIONS_TO_NAME", "0")
    assert P.provisions_to_name_clause() == ""


def _route(monkeypatch, messages, answer, captured=None):
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

    def fake(*args, **kwargs):
        if captured is not None:
            captured.append(str(kwargs.get("user", "")) + " ".join(a for a in args if isinstance(a, str)))
        return answer

    R._ENGINE_CACHE.clear()
    with patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True), \
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag", side_effect=fake):
        return TestClient(app, headers={"X-Regenold-Api-Key": "k"}).post(
            "/api/v1/regenold/eu-ai-act/ask", json={"messages": messages}).json()


@pytest.mark.parametrize("flag,present", [("1", True), ("0", False)])
def test_clause_reaches_a_single_turn_user_message(monkeypatch, flag, present):
    monkeypatch.setenv("REGENOLD_PROVISIONS_TO_NAME", flag)
    seen: list[str] = []
    _route(monkeypatch, [{"role": "user", "content":
                          "What must a provider of a high-risk AI system supply to the deployer in the instructions for use?"}],
           "Article 13(3) requires the instructions for use to contain the listed information.", seen)
    assert seen, "Stage-2 was never dispatched"
    assert ("PROVISIONS TO NAME" in seen[0]) is present


def test_clause_is_not_sent_on_a_multi_turn_request(monkeypatch):
    monkeypatch.setenv("REGENOLD_PROVISIONS_TO_NAME", "1")
    seen: list[str] = []
    _route(monkeypatch, [
        {"role": "user", "content": "What does Article 13 require?"},
        {"role": "assistant", "content": "Article 13 requires transparency toward deployers."},
        {"role": "user", "content": "And what must the instructions for use contain under Article 13(3)?"},
    ], "Article 13(3) requires the instructions for use to contain the listed information.", seen)
    assert seen and all("PROVISIONS TO NAME" not in s for s in seen)


@pytest.mark.parametrize("flag,cited", [("1", False), ("0", True)])
def test_route_drops_an_unasked_definition_from_the_wire(monkeypatch, flag, cited):
    monkeypatch.setenv("REGENOLD_DEFINITION_CITE_SCOPE", flag)
    answer = ("No. As a deployer you have no marking duty. Under Article 50(4), if the audio is a deep fake, as "
              "defined in Article 3(60), you must disclose that such content exists without hampering its enjoyment.")
    refs = _route(monkeypatch, [{"role": "user", "content": Q74}], answer)["references"]
    assert any(r.startswith("Article 50") for r in refs), refs
    assert any(r.startswith("Article 3.60") or r == "Article 3" for r in refs) is cited, refs

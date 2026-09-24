"""R447 — the two weak fixed-route (curated intercept) answers, rewritten.

The R446 live expert re-check (production, Opus 5.5, Bedrock Qwen3-235B judge,
3 votes) traced three of its four remaining misses to two curated intercepts,
which skip Stage-2 and therefore ship the same text every time:

    user_information_transparency   part1_q05 2/4, part2_q04 2/4
    role_difference                 part1_q10 3/4, tone FAIL

Both reproduce offline byte-for-byte against production, so these tests drive
the real route with ``provider=cli``. Nothing in them depends on Stage-2: a
curated intercept never reaches it.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app.engines import _graph_rag_impl as engine
from app.integrations.regenold import models as regenold_models

_Q05 = "How should users be informed when interacting with AI systems?"
_Q04 = (
    "Under the EU AI Act, how must a natural person be informed that they are "
    "interacting with an AI system?"
)
_Q10 = "What is the difference between the deployer and the provider?"


@pytest.fixture()
def ask(monkeypatch):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    from app.rate_limit import limiter

    limiter.enabled = False
    from app.routes import regenold as regenold_route

    client = TestClient(main_mod.app)

    def _ask(question: str) -> dict:
        regenold_route._ENGINE_CACHE.clear()
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": question}],
        )
        assert resp.status_code == 200, resp.text[:400]
        return resp.json()

    return _ask


def _curated(question: str) -> str:
    """The curated answer text the engine returns for ``question``."""
    return engine._deterministic_answer(question, engine.GraphContext())


# ── The curated text must survive the deterministic answer shaping ────────────


@pytest.mark.parametrize(
    ("question", "detector"),
    [
        (_Q05, engine._detect_user_information_inquiry),
        (_Q04, engine._detect_user_information_inquiry),
        (_Q10, engine._detect_role_difference_inquiry),
    ],
)
class TestCuratedTextSurvivesTheCaps:
    def test_the_intercept_fires_and_skips_stage2(self, question, detector):
        assert detector(question)
        assert engine._is_curated_authoritative_intercept(question)

    def test_at_most_three_sentences(self, question, detector):
        # A curated intercept skips Stage-2, so it takes the deterministic
        # 3-sentence cap. The pre-R447 Art. 50 text was four sentences and
        # its Article 50(4) sentence never shipped.
        sentences = regenold_models._split_sentences(_curated(question))
        assert len(sentences) <= regenold_models.MAX_ANSWER_SENTENCES, sentences

    def test_every_sentence_is_cite_anchored(self, question, detector):
        for sentence in regenold_models._split_sentences(_curated(question)):
            low = sentence.lower()
            assert "article " in low or "annex" in low or "art." in low, sentence

    def test_no_sentence_trips_the_meta_leak_filter(self, question, detector):
        # "unless this is obvious from the context" matched the
        # "from the context" leak entry and deleted the whole lead sentence.
        for sentence in regenold_models._split_sentences(_curated(question)):
            assert not regenold_models._sentence_has_meta_leak(sentence), sentence

    def test_legal_tone_punctuation(self, question, detector):
        answer = _curated(question)
        assert "—" not in answer and "–" not in answer
        assert "..." not in answer and "…" not in answer

    def test_the_wire_answer_is_the_curated_text(self, ask, question, detector):
        # Nothing between the engine and the wire may drop a sentence.
        assert ask(question)["answer"] == _curated(question)


# ── user_information_transparency (part1_q05, part2_q04) ──────────────────────


@pytest.mark.parametrize("question", [_Q05, _Q04])
class TestArticle50InformationRoute:
    def test_states_the_article_50_5_manner_and_timing(self, ask, question):
        answer = ask(question)["answer"]
        assert "Article 50(5)" in answer
        assert "clear and distinguishable manner" in answer
        assert "first interaction or exposure" in answer
        assert "accessibility requirements" in answer

    def test_distinguishes_provider_marking_from_deployer_disclosure(self, ask, question):
        answer = ask(question)["answer"]
        assert re.search(r"Article 50\(2\)[^.]*providers[^.]*machine-readable", answer)
        assert re.search(r"deployers[^.]*Article 50\(4\)[^.]*deep fake", answer)
        # The expert's role error: Article 50(3) is a DEPLOYER duty.
        assert re.search(r"deployers must inform persons exposed[^.]*Article 50\(3\)", answer)

    def test_names_the_article_26_11_deployer_duty(self, ask, question):
        answer = ask(question)["answer"]
        assert "Article 26(11)" in answer
        assert "Annex III high-risk AI systems" in answer

    def test_wire_references(self, ask, question):
        # Leaf-only, so R287's multi-leaf collapse has no bare head to fold
        # them into (it used to ship ``['Article 50.1']`` alone), and five,
        # so the curated MAX_REFERENCES budget cannot silently drop one.
        refs = ask(question)["references"]
        assert refs == [
            "Article 50.1",
            "Article 50.5",
            "Article 50.3",
            "Article 50.4",
            "Article 26.11",
        ]


# ── role_difference (part1_q10) ───────────────────────────────────────────────


class TestRoleDifferenceRoute:
    def test_does_not_allocate_duties_on_a_definitional_question(self, ask):
        body = ask(_Q10)
        # The citation criterion and the tone check both failed on these.
        assert "Article 16" not in body["answer"]
        assert "Article 26" not in body["answer"]
        for ref in body["references"]:
            assert not ref.startswith(("Article 16", "Article 26")), ref

    def test_defines_both_roles_and_the_article_25_transition(self, ask):
        answer = ask(_Q10)["answer"]
        assert "Article 3(3)" in answer and "Article 3(4)" in answer
        assert "personal non-professional activity" in answer
        assert "Article 25(1)" in answer
        for limb in ("name or trademark", "substantial modification", "intended purpose"):
            assert limb in answer, limb

    def test_cites_the_definitions_and_the_transition(self, ask):
        refs = ask(_Q10)["references"]
        assert "Article 3.3" in refs
        assert "Article 25.1" in refs

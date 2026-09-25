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
        # Both definitions: without REGENOLD_CURATED_KEEP_DECLARED_LEAVES the
        # R87-C re-emission + R287 fold shipped Article 3.3 alone.
        assert ask(_Q10)["references"] == ["Article 3.3", "Article 3.4", "Article 25.1"]


# ── REGENOLD_ROLE_DIFFERENCE_SKIP_INTENT_BOOST (R447b) ─────────────────────────


def _role_obligations_intent(_question: str):
    """The live Stage-0 classification production returns for the role question."""
    from app.llm.intent_classifier import IntentResult

    return IntentResult(
        intent="role_obligations",
        primary_anchor="Art. 26",
        alternate_anchors=(),
        confidence=0.93,
        elapsed_ms=0,
    )


class TestRoleDifferenceSkipsTheIntentBoost:
    def test_the_boost_is_skipped_only_for_the_role_verdict(self, ask, monkeypatch):
        from app.routes import regenold as route

        calls: list[list[str]] = []
        real = route.boost_for_intent

        def spy(candidates, intent_result, **kwargs):
            calls.append(list(candidates))
            return real(candidates, intent_result, **kwargs)

        monkeypatch.setattr(route, "boost_for_intent", spy)
        ask(_Q10)
        assert calls == []
        ask(_Q05)  # another curated intercept keeps the boost
        assert len(calls) == 1

    def test_an_injected_article_26_never_reaches_the_role_wire(self, ask, monkeypatch):
        # Production's classifier labels the question role_obligations at 0.93
        # with anchor Art. 26; the boost then injected Article 26 and the
        # deepener shipped Article 26.5. Offline no classifier runs, so fake it.
        from app.routes import regenold as route

        monkeypatch.setattr(route, "_classify_intent_cached", _role_obligations_intent)
        assert ask(_Q10)["references"] == ["Article 3.3", "Article 3.4", "Article 25.1"]
        monkeypatch.setenv("REGENOLD_ROLE_DIFFERENCE_SKIP_INTENT_BOOST", "0")
        refs = ask(_Q10)["references"]
        assert any(ref.startswith("Article 26") for ref in refs), refs


# ── REGENOLD_CURATED_KEEP_DECLARED_LEAVES (R447 review #1) ────────────────────

_COMPOUND_Q04 = (
    "We are both a provider and a deployer of a chatbot. How must a natural "
    "person be informed that they are interacting with an AI system?"
)


class TestCuratedLeavesAreNotFolded:
    def test_a_compound_role_phrasing_keeps_every_article_50_leaf(self, ask):
        # A strong compound-role phrasing lifts the ref budget to 12, so the
        # re-emitted Article 50 survived the cut, R287 folded the four leaves
        # into it, and the deepener shipped Article 50.4 (deep fakes) alone.
        assert ask(_COMPOUND_Q04)["references"] == [
            "Article 50.1",
            "Article 50.5",
            "Article 50.3",
            "Article 50.4",
            "Article 26.11",
        ]

    def test_a_scenario_phrasing_keeps_every_article_50_leaf(self, ask):
        # The second review: a scenario shape runs expand_citations, which adds
        # a bare Article 50 BEFORE R87-C, so a skip set computed there came back
        # empty and R287 still folded the leaves into it (wire: Article 50.4).
        refs = ask(
            "We are both a provider and a deployer of a chatbot used by our bank. "
            "What is its risk classification? " + _COMPOUND_Q04.split(". ", 1)[1]
        )["references"]
        for leaf in ("Article 50.1", "Article 50.5", "Article 50.3", "Article 50.4"):
            assert leaf in refs, refs
        assert "Article 50" not in refs

    def test_the_flag_restores_the_fold(self, ask, monkeypatch):
        monkeypatch.setenv("REGENOLD_CURATED_KEEP_DECLARED_LEAVES", "0")
        refs = ask(_COMPOUND_Q04)["references"]
        assert sum(ref.startswith("Article 50") for ref in refs) == 1

    def test_a_dominating_leaf_still_folds_its_children(self, ask):
        # rg_012 declares Annex III.8 + 8.a + 8.b. R287 keeps Annex III.8,
        # which is the gold; skipping the re-emission there cost Ref.
        # Conciseness 1.00 -> 0.33 in the R447 replay, so it still runs.
        refs = ask(
            "What are the high-risk uses of AI systems listed under "
            "'Administration of justice and democratic processes' cited in the "
            "EU AI Act?"
        )["references"]
        assert refs == ["Annex III.8"]

    def test_only_undominated_heads_are_skipped(self):
        from app.routes.regenold import _undominated_leaf_heads

        assert _undominated_leaf_heads(
            ["Article 50.1", "Article 50.3", "Article 26.11"]
        ) == frozenset({"Article 50"})
        assert _undominated_leaf_heads(
            ["Annex III.8", "Annex III.8.a", "Annex III.8.b"]
        ) == frozenset()
        assert _undominated_leaf_heads(["Article 6", "Article 6.1", "Article 6.3"]) == frozenset()

"""R380 — provisions that were gold-cited (or asked about in the official
batch) yet had ZERO keyword anchors in the ENGINE map.

The R367 Article 7 lesson: the route only FRONTS an anchor that is already in
``candidates``; retrieval is seeded by ``_KEYWORD_ENTITY_MAP``. A provision
absent from that map can only reach the wire through BM25 luck. An audit
(R380) found Article 17, Annex IV, Article 12, Article 97, Article 98,
Annex IX and Annex X in that state.

These pins run the real scanner (``_keyword_scan_refs``) so they
cannot pass on a map entry the scanner never reads. They also pin the
boundary guard: "annex x" is a substring of "annex xi/xii/xiii".
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")


def _scan(text: str) -> list[str]:
    import app.engines._graph_rag_impl as impl

    return impl._keyword_scan_refs(text.lower())


@pytest.mark.parametrize(
    "question, expected",
    [
        ("What must a provider's quality management system cover?", "Art. 17"),
        ("What does Annex IV require in the technical documentation?", "Annex IV"),
        ("What is the content of the technical documentation for a high-risk system?", "Annex IV"),
        ("Do high-risk systems need record-keeping / automatic recording of events?", "Art. 12"),
        ("Which logging capabilities must a high-risk AI system have?", "Art. 12"),
        ("For how long is the power to adopt delegated acts conferred on the Commission?", "Art. 97"),
        ("How does the exercise of the delegation work under the AI Act?", "Art. 97"),
        ("Which committee procedure applies to Commission implementing acts?", "Art. 98"),
        ("Is the examination procedure used for implementing acts?", "Art. 98"),
        ("What information must be registered under Annex IX for real-world testing?", "Annex IX"),
        ("What is Annex X about? What is it used for?", "Annex X"),
        ("Which large-scale IT systems are covered by the transitional rule?", "Annex X"),
    ],
)
def test_gold_cited_provisions_now_have_an_engine_anchor(question, expected):
    assert expected in _scan(question), (question, _scan(question))


@pytest.mark.parametrize(
    "question",
    [
        "What must the Annex XI technical documentation of a GPAI model contain?",
        "What downstream information does Annex XII require?",
        "Which Annex XIII criteria designate a GPAI model as systemic risk?",
    ],
)
def test_annex_x_and_ix_are_word_bounded(question):
    hits = _scan(question)
    assert "Annex X" not in hits, (question, hits)
    assert "Annex IX" not in hits, (question, hits)


def test_article_7_anchors_are_untouched_by_the_article_97_phrases():
    """Art. 7 (amending Annex III) must not now drag Art. 97 along: the
    Art. 97 phrases are the delegation MECHANICS, not 'delegated act'."""
    hits = _scan("Can the Commission amend Annex III to add use cases? Under what conditions?")
    assert "Art. 7" in hits
    assert "Art. 97" not in hits


def test_scope_map_mirrors_the_two_provisions_that_had_no_anchor_anywhere():
    from app.integrations.regenold.scope import KEYWORD_TO_ARTICLE

    assert KEYWORD_TO_ARTICLE["exercise of the delegation"] == "Art. 97"
    assert KEYWORD_TO_ARTICLE["committee procedure"] == "Art. 98"
    assert KEYWORD_TO_ARTICLE["large-scale it systems"] == "Annex X"


class TestEmotionRecognitionByInput:
    """R380 — a probe follow-up described emotion recognition by its input
    ("reads employees' facial expressions ... to score their engagement") and
    reached neither map nor the prohibited gatekeeper."""

    _Q = ("We're adding a feature that reads employees' facial expressions during "
          "the meeting to score their engagement. Does anything change?")

    def test_engine_anchor(self):
        hits = _scan(self._Q)
        assert "Art. 5" in hits and "Art. 50" in hits, hits

    def test_scope_anchor(self):
        from app.integrations.regenold.scope import _has_ai_act_anchor

        assert _has_ai_act_anchor(self._Q)

    def test_gatekeeper_flags_the_workplace_prohibition(self):
        from app.engines import prohibited_gatekeeper as pg

        pats = pg._VERB_OBJECT_PATTERNS
        import re
        assert any(re.search(p[0], self._Q.lower()) for p in pats), "verb-object pattern did not fire"

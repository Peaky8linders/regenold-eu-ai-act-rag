"""R376 — a denial of an Article 5 prohibition must not suppress the verdict.

THE DEFECT. The route prepends the curated ``build_verdict_prefix`` only when
``"Article 5" not in answer_text``. That guard stops a duplicate anchor, which
is right when the answer already STATES the prohibition — and it fires just as
readily when the answer states the OPPOSITE, because a denial names Article 5
too. Measured on the deterministic path for "Can we use an AI system that infers
the emotions of our employees during performance reviews?":

    gatekeeper hits : (('Art. 5', 'Art. 5.1.f'),)
    verdict prefix  : "Emotion recognition in the workplace and education
                       contexts is prohibited under Article 5(1)(f) ..."
    shipped answer  : "The system described is not among the practices
                       prohibited under Article 5 ..."

The correct verdict was computed and discarded, and a user asking whether they
may run emotion recognition on staff was told they may.

The fix is shape-based, never practice-based — hard rule #3 forbids new
classification topics for the three PDF example questions, and
emotion-recognition prohibition is one of them. Nothing in the guard names a
practice: it matches the grammar of a denial near an Article 5 anchor, and only
where ``scan_for_prohibitions`` has independently matched a curated
PRACTICE_REGISTRY keyword. The tests below therefore cover several practices and,
just as importantly, the sentences that must NOT be touched.
"""

from __future__ import annotations

import pytest

from app.engines.prohibited_gatekeeper import (
    answer_denies_prohibition,
    build_verdict_prefix,
    scan_for_prohibitions,
    strip_prohibition_denials,
)


class TestDenialDetection:
    @pytest.mark.parametrize(
        "sentence",
        [
            "The system described is not among the practices prohibited under Article 5.",
            "This use is not prohibited under Article 5.",
            "Emotion recognition is not prohibited by Article 5 in this context.",
            "The deployment does not fall within Article 5.",
            "It is not a prohibited practice under Article 5.",
            "Such a system is not banned by Article 5.",
        ],
    )
    def test_denials_are_detected(self, sentence):
        assert answer_denies_prohibition(sentence) is True

    @pytest.mark.parametrize(
        "sentence",
        [
            # States the prohibition — the original guard was right here.
            "Emotion recognition in the workplace is prohibited under Article 5(1)(f).",
            "Article 5 prohibits social scoring by public authorities.",
            # Negations that are NOT about Article 5. "not high-risk" is an
            # Article 6 statement and is frequently correct; treating it as a
            # denial would let the guard rewrite ordinary classification prose.
            "This system is not high-risk under Article 6(3).",
            "The system does not fall within Annex III.",
            "Providers are not required to register under Article 49.",
            # A bare anchor with no denial at all.
            "See Article 5 for the exhaustive list of prohibited practices.",
            "",
        ],
    )
    def test_non_denials_are_left_alone(self, sentence):
        assert answer_denies_prohibition(sentence) is False


class TestSurgicalRemoval:
    def test_only_the_denying_sentence_is_removed(self):
        answer = (
            "The system described is not among the practices prohibited under "
            "Article 5. Whether it is high-risk turns on Article 6: it is "
            "high-risk only if it is a safety component of a product regulated "
            "under Annex I. Otherwise it is subject to the Article 50 "
            "transparency duties."
        )
        rewritten, removed = strip_prohibition_denials(answer)
        assert removed == 1
        assert "not among the practices prohibited" not in rewritten
        # The surrounding analysis survives verbatim and in order.
        assert rewritten.startswith("Whether it is high-risk turns on Article 6")
        assert "Article 50 transparency duties" in rewritten

    def test_an_answer_without_a_denial_is_returned_unchanged(self):
        answer = (
            "Emotion recognition in the workplace is prohibited under Article "
            "5(1)(f). Narrow medical and safety carve-outs apply."
        )
        rewritten, removed = strip_prohibition_denials(answer)
        assert removed == 0
        assert rewritten == answer

    def test_empty_input_is_safe(self):
        assert strip_prohibition_denials("") == ("", 0)
        assert strip_prohibition_denials("   ") == ("   ", 0)
        # ``None`` normalises to the empty string rather than raising: this runs
        # on the answer path, where a guard that throws is worse than one that
        # does nothing.
        assert strip_prohibition_denials(None) == ("", 0)


class TestEndToEndVerdictRecovery:
    """The whole point: the shipped answer must lead with the prohibition."""

    QUESTIONS = [
        "Can we use an AI system that infers the emotions of our employees "
        "during performance reviews?",
        "May we use AI to infer emotions of students in our classroom?",
    ]

    @pytest.fixture
    def client(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.main as main_mod
        from app.routes import regenold as regenold_route

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "neo4j")
        c = TestClient(main_mod.app)

        def _ask(question: str) -> dict:
            regenold_route._ENGINE_CACHE.clear()
            resp = c.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json={"messages": [{"role": "user", "content": question}]},
            )
            assert resp.status_code == 200
            return resp.json()

        return _ask

    @pytest.mark.parametrize("question", QUESTIONS)
    def test_the_prohibition_verdict_leads(self, client, question):
        # Precondition: the gatekeeper really does match, so this test is about
        # the verdict surviving rather than about detection.
        assert scan_for_prohibitions(question)
        assert build_verdict_prefix(question)

        answer = client(question)["answer"]
        assert "prohibited under Article 5(1)(f)" in answer
        assert "not among the practices prohibited" not in answer

    @pytest.mark.parametrize("question", QUESTIONS)
    def test_rollback_reproduces_the_pre_r376_answer(
        self, client, monkeypatch, question
    ):
        monkeypatch.setenv("REGENOLD_PROHIBITION_CONTRADICTION_GUARD", "0")
        answer = client(question)["answer"]
        assert "not among the practices prohibited" in answer

    def test_a_non_prohibition_question_is_untouched(self, client, monkeypatch):
        """No collateral edits: the guard only runs where the gatekeeper fired."""
        question = "Is an AI CV-screening tool high-risk under the EU AI Act?"
        assert not scan_for_prohibitions(question)
        monkeypatch.setenv("REGENOLD_PROHIBITION_CONTRADICTION_GUARD", "1")
        on = client(question)["answer"]
        monkeypatch.setenv("REGENOLD_PROHIBITION_CONTRADICTION_GUARD", "0")
        off = client(question)["answer"]
        assert on == off


class TestExactDuplicateSentenceRemoval:
    """R376 — a sentence repeated verbatim is never the intent.

    Measured on the deterministic path, the GPAI systemic-risk answer ended with
    the same sentence twice: "Under Annex III, Eight high-risk use-case
    categories: biometrics, critical infrastructure." ``stitch_grounded_prose``
    has a near-duplicate guard of its own, but it dedupes on the REF while the
    final answer is assembled from several fragments — so two refs resolving to
    the same KB stub each contributed the identical sentence through different
    paths. The pass sits in the normaliser, where every path converges.

    Exact match only, after whitespace + case normalisation: a NEAR duplicate
    can carry a different coordinate or carve-out and is a judgement call.
    """

    def test_a_verbatim_repeat_is_dropped(self):
        from app.integrations.regenold.models import normalise_answer_for_regenold

        text = (
            "Article 53 sets the provider obligations for general-purpose AI "
            "models. Under Annex III, eight high-risk use-case categories apply. "
            "Under Annex III, eight high-risk use-case categories apply."
        )
        out = normalise_answer_for_regenold(text, max_sentences=12)
        assert out.count("eight high-risk use-case categories") == 1
        # The first occurrence is kept, so a verdict-first lead cannot be
        # displaced (hard rule #2).
        assert out.startswith("Article 53 sets the provider obligations")

    def test_case_and_spacing_differences_still_count_as_duplicates(self):
        from app.integrations.regenold.models import normalise_answer_for_regenold

        text = (
            "Providers must keep the technical documentation. "
            "providers  must   keep the technical documentation."
        )
        out = normalise_answer_for_regenold(text, max_sentences=12)
        assert out.lower().count("must keep the technical documentation") == 1

    def test_distinct_sentences_are_all_kept(self):
        from app.integrations.regenold.models import normalise_answer_for_regenold

        text = (
            "Article 9 requires a risk management system. "
            "Article 10 requires data governance. "
            "Article 11 requires technical documentation."
        )
        out = normalise_answer_for_regenold(text, max_sentences=12)
        for article in ("Article 9", "Article 10", "Article 11"):
            assert article in out

    def test_near_duplicates_are_left_alone(self):
        """Two sentences differing only by coordinate are NOT duplicates."""
        from app.integrations.regenold.models import normalise_answer_for_regenold

        text = (
            "Under Annex III(1)(a), remote biometric identification is listed. "
            "Under Annex III(1)(c), emotion recognition is listed."
        )
        out = normalise_answer_for_regenold(text, max_sentences=12)
        assert "III(1)(a)" in out
        assert "III(1)(c)" in out


class TestStripNeverRunsWithoutAReplacement:
    """The strip is the first half of "remove the denial, then lead with the
    verdict". It must not run when the second half is gated off, or the answer
    loses a sentence and gains nothing — silent content deletion, which is worse
    than the wrong sentence it removes.

    The prepend carries an extra condition the strip did not:
    ``not _is_classification_topic`` (Round-36 issue #49 — a classification
    verdict already leads with the canonical anchor). The invariant below holds
    the two together without reaching into the route's internals, so it keeps
    working if either gate is re-shaped.
    """

    QUESTIONS = [
        "Can we use an AI system that infers the emotions of our employees "
        "during performance reviews?",
        "May we use AI to infer emotions of students in our classroom?",
        "Is emotion recognition of employees prohibited under the AI Act?",
        "Can we use AI to detect the emotional state of our call-centre staff?",
    ]

    @pytest.mark.parametrize("question", QUESTIONS)
    def test_a_stripped_denial_is_always_replaced_by_the_verdict(
        self, monkeypatch, question
    ):
        from fastapi.testclient import TestClient

        import app.main as main_mod
        from app.routes import regenold as regenold_route

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "neo4j")
        client = TestClient(main_mod.app)
        regenold_route._ENGINE_CACHE.clear()
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json={"messages": [{"role": "user", "content": question}]},
        )
        assert resp.status_code == 200
        answer = resp.json()["answer"]

        denial_present = "not among the practices prohibited" in answer
        # Several correct paths assert the prohibition in different words: the
        # curated prefix says "prohibited under Article 5(1)(f)", the R369
        # lower-risk verdict says "prohibited under Article 5 when deployed in
        # workplaces or educational institutions". Matching the literal
        # sub-point would fail a GOOD answer, so the invariant is on the claim,
        # not the phrasing.
        verdict_present = "prohibited under Article 5" in answer
        # Exactly one of the two states is acceptable: the original answer with
        # its denial intact, or a corrected answer that asserts the prohibition.
        # The forbidden state is "denial removed, nothing put in its place".
        assert denial_present or verdict_present, (
            "the denial was stripped without the verdict replacing it — "
            f"answer={answer!r}"
        )

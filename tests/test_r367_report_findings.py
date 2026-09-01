"""R367 — regression pins for the six appendix failures in the OFFICIAL
2026-08-25 Regenold benchmark report (``report_antifragile_ai.pdf``).

Every assertion below traces to a specific judged-FAIL criterion in that
report, and every one of them was REPRODUCED on this branch's parent
(73aa150) before the fix — three of them offline, all six live.

The report's own appendix is the spec:

* **Q104** "What is Annex X about?" — 2/2 criteria FAILED. The shipped answer
  described Annex X as the EU-database registration annex. That is
  **Annex VIII**. Root cause: ``kb.py`` carried Annex VIII's content under the
  ``"Annex X"`` key and Annex X's content under ``"Annex IX"`` — a two-annex
  shift, reproduced verbatim from the offline Stage-1 answer.
* **Q96** "Name the areas of high-risk use cases…" — 2/2 criteria FAILED with
  a total scope REFUSAL (``LEXY_OOS_GENERIC``). Root cause: no anchor keyword
  matched, so the question fell to the ambiguous CONVERSATIONAL bucket.
* **Q17** "Can the Commission amend Annex III…?" — 3/4 criteria FAILED. Two
  root causes, both needed: Article 7 had **zero** keyword anchors anywhere in
  the repo, and the question tripped the canned general-classification verdict
  whose fixed roster evicted it.
* **Q95** "What is an 'area' and what is a 'use case'…?" — 2/2 FAILED, one of
  them on the KB's own wording ("eight Annex III **use cases**"; Annex III
  lists eight **areas**).

These are content/routing pins, not prose pins: they assert on the data and on
the router, never on model output.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")


# ── Q104 — the two-annex shift ───────────────────────────────────────────────
class TestAnnexIXAndXAreNotShifted:
    """``kb.py`` described Annex X as Annex VIII and Annex IX as Annex X."""

    def test_annex_x_is_the_large_scale_it_systems_list(self) -> None:
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        summary = EC_CHECKER_OBLIGATION_MAP["Annex X"]["summary"]
        lowered = summary.lower()
        assert "large-scale it systems" in lowered
        # The seven systems the annex actually lists.
        for system in ("schengen", "eurodac", "entry/exit", "etias", "ecris"):
            assert system in lowered, f"Annex X summary omits {system!r}"

    def test_annex_x_is_not_described_as_the_registration_annex(self) -> None:
        """The exact defect: Annex VIII's content under the Annex X key.

        The shipped Q104 answer opened "Annex X sets the information that
        providers … must enter in the EU database when registering high-risk
        AI systems referred to in Art. 49".
        """
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        lowered = EC_CHECKER_OBLIGATION_MAP["Annex X"]["summary"].lower()
        assert "eu database" not in lowered.split("not the eu-database")[0], (
            "Annex X summary still describes EU-database registration — "
            "that is Annex VIII."
        )

    def test_annex_x_carries_the_article_111_transition_link(self) -> None:
        """Gold for Q104 is ``Article 111.1; Annex X``.

        Annex X's whole function is to fix the Art. 111(1) transitional
        deadline, and the judge's second criterion was exactly that
        ("used to define systems with specific transition and compliance
        timelines").
        """
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        summary = EC_CHECKER_OBLIGATION_MAP["Annex X"]["summary"]
        assert "111" in summary
        assert "2030" in summary, "the 31 December 2030 deadline is the point"

    def test_annex_ix_is_real_world_testing_registration(self) -> None:
        """Annex IX is Art. 60 real-world-testing registration, not Annex X."""
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        lowered = EC_CHECKER_OBLIGATION_MAP["Annex IX"]["summary"].lower()
        assert "real world conditions" in lowered
        assert "60" in lowered
        assert "schengen" not in lowered, (
            "Annex IX still carries Annex X's large-scale-IT-systems list"
        )

    def test_kb_summaries_agree_with_the_official_corpus_titles(self) -> None:
        """Cross-check against the shipped official text, which was correct."""
        from app.data.eu_ai_act_corpus import ARTICLE_TITLE

        assert "large-scale IT systems" in ARTICLE_TITLE["Annex X"]
        assert "testing in real world conditions" in ARTICLE_TITLE["Annex IX"]
        assert "registration of high-risk AI systems" in ARTICLE_TITLE["Annex VIII"]


# ── Q95 — areas are not use-cases ────────────────────────────────────────────
class TestAnnexIIIAreasVersusUseCases:
    """Annex III lists eight AREAS; each area contains lettered use-cases.

    The judge's Q95 criterion 2 read: "The candidate answer states that the
    system falls within 'one of the eight Annex III use cases.' This is
    incorrect … Annex III has eight areas/categories, not eight use cases."
    That sentence came verbatim from the ``Art. 6`` KB summary.
    """

    def test_article_6_summary_does_not_say_eight_use_cases(self) -> None:
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        summary = EC_CHECKER_OBLIGATION_MAP["Art. 6"]["summary"]
        assert "eight Annex III use cases" not in summary
        assert "eight" in summary.lower() and "area" in summary.lower()

    def test_annex_iii_summary_names_them_areas(self) -> None:
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        summary = EC_CHECKER_OBLIGATION_MAP["Annex III"]["summary"]
        assert "AREA" in summary.upper()
        # All eight areas must survive the rewrite.
        lowered = summary.lower()
        for area in (
            "biometric",
            "critical infrastructure",
            "education",
            "employment",
            "essential",
            "law enforcement",
            "migration",
            "justice",
        ):
            assert area in lowered, f"Annex III summary lost the {area!r} area"

    def test_the_act_itself_uses_the_word_areas(self) -> None:
        """Guards the premise: Annex III's opening line says "areas"."""
        from app.data.provision_text import get_provision_text

        text = get_provision_text("Annex III") or ""
        assert "following areas" in text.lower()


# ── Q96 — the scope-gate refusal ─────────────────────────────────────────────
class TestHighRiskUseCaseAnchorsScope:
    """"Name the areas of high-risk use cases" was judged OUT OF SCOPE."""

    @pytest.mark.parametrize(
        "question",
        [
            "Name the areas of high-risk use cases. Is healthcare decision "
            "making one of them?",
            "List the high-risk use cases.",
            "Which high-risk use case covers CV screening?",
        ],
    )
    def test_high_risk_use_case_questions_are_in_scope(self, question: str) -> None:
        from app.integrations.regenold.scope import classify_conversation

        verdict = classify_conversation(
            [{"role": "user", "content": question}]
        ).verdict
        assert verdict.in_scope, (
            f"{question!r} classified out of scope ({verdict.reason}) — this is "
            "the Q96 total-refusal defect."
        )

    @pytest.mark.parametrize(
        "question",
        [
            # R54.1's motivating false positive — must stay out.
            "Best high-risk hike in the Alps?",
            # MEASURED leaks from the first, broader R367 attempt. "area",
            # "uses" and "practices" are ordinary English; only the "use case"
            # pairing is an AI Act term of art, so only it is a strong anchor.
            "What is a high risk area for avalanches this winter?",
            "Which high-risk areas should I avoid when travelling in South America?",
            "My doctor said I am in a high risk area for Lyme disease, what do I do?",
            "What high-risk practices does my gym recommend against?",
            "Which high risk uses of leverage blew up in 2008?",
        ],
    )
    def test_ordinary_english_high_risk_phrases_stay_out_of_scope(
        self, question: str
    ) -> None:
        from app.integrations.regenold.scope import classify_conversation

        verdict = classify_conversation(
            [{"role": "user", "content": question}]
        ).verdict
        assert not verdict.in_scope, (
            f"{question!r} leaked in-scope — R367 must not reopen the R54.1 "
            "off-topic false-positive class."
        )


# ── Q17 — Article 7 was unreachable ──────────────────────────────────────────
class TestArticle7IsReachable:
    """Article 7 had ZERO keyword anchors in either map.

    ``scope.py``'s ``KEYWORD_TO_ARTICLE`` alone is insufficient: the route only
    FRONTS an anchor already present in ``candidates``
    (``regenold.py`` ~8155), it never adds one. The ENGINE map
    (``_graph_rag_data._KEYWORD_ENTITY_MAP``) is what seeds retrieval.
    """

    QUESTION = (
        "Can the European Commission amend Annex III of the EU AI Act to add "
        "or modify use-cases classified as high-risk AI systems? Under what "
        "conditions?"
    )

    def test_engine_retrieval_surfaces_article_7(self) -> None:
        from app.engines._graph_rag_impl import _deterministic_parse

        entities = _deterministic_parse(self.QUESTION).entities
        assert "Art. 7" in entities, (
            "the engine keyword map does not reach Article 7 — the retrieval "
            "half of the Q17 defect"
        )

    def test_scope_gate_anchors_article_7(self) -> None:
        from app.integrations.regenold.scope import classify_conversation

        anchors = classify_conversation(
            [{"role": "user", "content": self.QUESTION}]
        ).anchor_articles
        assert "Art. 7" in anchors

    def test_article_7_kb_summary_carries_both_cumulative_conditions(self) -> None:
        """Judge criteria 2, 3 and 4 were the two limbs and their conjunction.

        The pre-R367 summary described Art. 7(2)'s assessment CRITERIA, not
        Art. 7(1)'s two conditions, so even a successful retrieval could not
        have satisfied them.
        """
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        summary = EC_CHECKER_OBLIGATION_MAP["Art. 7"]["summary"]
        lowered = summary.lower()
        # criterion 2 — must be used in an area already listed in Annex III
        assert "areas" in lowered and "annex iii" in lowered
        # criterion 3 — risk equivalent to or greater than
        assert "equivalent to or greater" in lowered
        # criterion 4 — the two limbs are cumulative
        assert "cumulativ" in lowered
        assert "both" in lowered

    def test_article_7_kb_summary_matches_the_official_text(self) -> None:
        from app.data.provision_text import get_provision_text

        official = (get_provision_text("Article 7.1") or "").lower()
        assert "both of the following conditions" in official
        assert "equivalent to, or greater than" in official


class TestAmendmentQuestionsSkipTheCannedVerdict:
    """The canned general-classification roster evicted Article 7.

    ``_general_classification_verdict`` returns a FIXED five-ref roster
    (Art. 5, Art. 6, Annex III, Annex I, Art. 50). Q17 tripped it on its
    "classified as high-risk" clause, so the live answer discussed Art. 6(6)'s
    parallel delegated power and never reached Art. 7(1). Same defect class as
    R356's market-surveillance exclusion, and the same remedy shape.
    """

    AMENDMENT_ASKS = [
        "Can the European Commission amend Annex III of the EU AI Act to add "
        "or modify use-cases classified as high-risk AI systems? Under what "
        "conditions?",
        "Under what conditions may the Commission add new use cases to Annex "
        "III by delegated act?",
        "Can the Commission modify Annex I through delegated acts?",
        "Is the Commission empowered to update the high-risk list?",
    ]

    CLASSIFICATION_ASKS = [
        # No amending ACTOR — a system-side modification question.
        "Can I modify my Annex III system after deployment and stay compliant?",
        # No amendment OBJECT — a plain institutional question.
        "What does the Commission do under the AI Act?",
        "Is my CV-screening tool high-risk under Annex III?",
        "We updated our high-risk AI system. Do we need a new conformity "
        "assessment?",
        # R148's motivating question for the canned verdict — must keep it.
        "Can a system be deployed that tracks patient weight, or is it "
        "high-risk according to Article 5?",
        "Does adding a new feature to my chatbot change its risk tier?",
        "The Commission says my system is high-risk. Is it?",
    ]

    @pytest.mark.parametrize("question", AMENDMENT_ASKS)
    def test_amendment_asks_are_excluded(self, question: str) -> None:
        from app.engines._graph_rag_impl import _general_classification_verdict

        assert _general_classification_verdict(question) is None, (
            f"{question!r} still receives the canned classification roster"
        )

    @pytest.mark.parametrize("question", CLASSIFICATION_ASKS)
    def test_real_classification_asks_are_untouched(self, question: str) -> None:
        """Two limbs are required precisely so this set cannot regress."""
        from app.engines._graph_rag_impl import (
            _AMENDMENT_ACTOR_RE,
            _AMENDMENT_POWER_RE,
        )

        fired = bool(
            _AMENDMENT_POWER_RE.search(question)
            and _AMENDMENT_ACTOR_RE.search(question)
        )
        assert not fired, (
            f"the R367 amendment exclusion over-fired on {question!r}"
        )

    def test_the_exclusion_is_byte_identical_on_davidath(self) -> None:
        """The regression guard must not move.

        Uses the fast neutrality method: scan the bench QUESTIONS for the
        trigger. Zero hits across all 476 rows ⇒ the bench cannot change.
        """
        from evals.bench.dataset import (
            load_qa_pairs,
            load_scenarios,
            scenario_to_question,
        )

        from app.engines._graph_rag_impl import (
            _AMENDMENT_ACTOR_RE,
            _AMENDMENT_POWER_RE,
        )

        questions = [item.get("question") or "" for item in load_qa_pairs()]
        questions += [scenario_to_question(s) for s in load_scenarios()]
        assert len(questions) == 476, f"expected the 476-row bench, got {len(questions)}"

        hits = [
            q
            for q in questions
            if _AMENDMENT_POWER_RE.search(q) and _AMENDMENT_ACTOR_RE.search(q)
        ]
        assert hits == [], f"R367 changes {len(hits)} davidath rows: {hits[:3]}"


# ── Q45 — the content was retrievable all along ──────────────────────────────
class TestInstructionsForUseContentExists:
    """Q45 lost 5/5 criteria to an abstention, not to a corpus gap.

    The shipped answer said "the materials available here do not permit a
    citation-supported enumeration" while ``Article 13.3`` sat in the corpus
    with all of the required categories. This pins the premise so a future
    session does not go hunting for missing text.
    """

    @pytest.mark.parametrize(
        "needle",
        [
            "identity and the contact details of the provider",
            "human oversight measures",
            "computational and hardware resources",
            "expected lifetime",
            "logs",
        ],
    )
    def test_article_13_3_carries_every_judged_category(self, needle: str) -> None:
        from app.data.provision_text import get_provision_text

        text = (get_provision_text("Article 13.3") or "").lower()
        assert text, "Article 13.3 has no provision text"
        assert needle.lower() in text, (
            f"Article 13(3) text is missing {needle!r} — the judge required it"
        )

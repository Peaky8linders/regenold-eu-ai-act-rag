"""R381 — END-TO-END pins for the official-report appendix failures.

WHY THIS FILE EXISTS
--------------------
``tests/test_r367_report_findings.py`` states its own design in its docstring:
"These are content/routing pins, not prose pins: they assert on the data and on
the router, never on model output."  That is necessary but it is demonstrably
NOT sufficient, and R381 measured the cost:

* **Q95** — the R367 KB fix ("eight AREAS", plus the area-vs-use-case gloss) was
  real and its pin was green, but ``classify_question_type`` returns ``numeric``
  for "How many areas exist?", the R93 extractive pass fired, and the ONE
  sentence it picked (Art. 6(2) verbatim, containing no cardinal at all)
  REPLACED the engine's correct answer on the way to the wire.
* **Q45** — same shape, ``list`` branch: the extractive pass returned Art. 26(9),
  a sentence that merely CROSS-REFERENCES Article 13 to describe a GDPR DPIA
  duty and enumerates nothing, while Art. 13(3)(a)-(f) sat verbatim in
  ``eu_ai_act_corpus.ARTICLE_FULL_TEXT`` the whole time. All five official
  correctness criteria failed.

This is the fourth instance of the failure shape CLAUDE.md records three times
(R329 rerank placements, R330 semantic layer, R366 parent collapse): a green,
correctly-written pin that does not touch the path the change had to affect.

So these tests assert on the ANSWER the ROUTE returns. They run offline and
deterministically (Stage-2 off), which is the regime where the answer is the
engine's own composition — exactly the layer the extractive pass was overriding.
"""
from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")


DETERMINISTIC_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "0",
}

Q45 = (
    "Under the EU AI Act, what must a provider of a high-risk AI system supply "
    "to the deployer in the instructions for use? List the required categories "
    "of information."
)
Q95 = (
    'What is an "area" and what is a "use case" for high-risk as per '
    "Article 6(2)? How many areas exist?"
)
Q104 = "What is Annex X about? What is it used for?"
Q17 = (
    "Can the European Commission amend Annex III of the EU AI Act to add or "
    "modify use-cases classified as high-risk AI systems? Under what conditions?"
)


@pytest.fixture()
def ask(monkeypatch):
    for k, v in DETERMINISTIC_ENV.items():
        monkeypatch.setenv(k, v)
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    def _ask(question: str) -> dict:
        # The route rate-limits per source IP (30/min); a test module firing
        # several questions in a row trips it, and a 429 deserializes to {} —
        # which silently reads as "the answer contains none of the keywords".
        last = None
        for _ in range(8):
            last = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json={"messages": [{"role": "user", "content": question}]},
            )
            if last.status_code == 200:
                return last.json()
        pytest.skip(f"route returned {last.status_code} after retries (rate limit)")

    return _ask


class TestQ45InstructionsForUseCategories:
    """Q45 — expected reference Article 13.3; five criteria, all previously FAIL."""

    def test_answer_enumerates_the_statutory_categories(self, ask):
        answer = (ask(Q45).get("answer") or "").lower()
        assert answer, "empty answer"
        # The five official correctness criteria, by their distinguishing token.
        assert "contact details" in answer, "criterion 1: provider/rep contact details"
        assert "human oversight" in answer, "criterion 3: human oversight measures"
        assert (
            "hardware" in answer or "computational" in answer
        ), "criterion 4: computational/hardware resources"
        assert "lifetime" in answer, "criterion 4: expected lifetime"
        assert "logs" in answer or "logging" in answer, "criterion 5: logging mechanisms"

    def test_answer_is_an_enumeration_not_a_cross_reference(self, ask):
        answer = ask(Q45).get("answer") or ""
        assert len(re.findall(r"\([a-f]\)", answer)) >= 4, (
            "expected the lettered limbs of Article 13(3); got: " + answer[:300]
        )
        # The pre-R381 answer was Art. 26(9) — a DPIA cross-reference. Its
        # signature is the GDPR citation, which Article 13(3) never mentions.
        assert "2016/679" not in answer, "regressed to the Art. 26(9) DPIA sentence"

    def test_article_13_is_cited(self, ask):
        refs = ask(Q45).get("references") or []
        heads = {r.split(".")[0] for r in refs}
        assert "Article 13" in heads, f"gold head Article 13 missing from {refs}"


class TestQ95AreaVersusUseCase:
    """Q95 — expected references Article 6.2 + Annex III; both criteria FAIL before."""

    def test_answer_states_eight_and_distinguishes_area_from_use_case(self, ask):
        answer = (ask(Q95).get("answer") or "").lower()
        assert answer, "empty answer"
        assert "eight" in answer, "criterion 2: eight AREAS exist"
        assert "area" in answer, "criterion 1: the answer must speak of areas"
        assert "use case" in answer or "use-case" in answer, (
            "criterion 1: an area CONTAINS use cases — both terms must appear"
        )

    def test_the_extractive_pass_does_not_replace_it(self, ask):
        answer = ask(Q95).get("answer") or ""
        # The pre-R381 answer was this exact Art. 6(2) sentence and nothing else.
        assert not answer.strip().startswith(
            "In addition to the high-risk AI systems referred to in paragraph 1"
        ), "regressed to the bare Art. 6(2) extractive sentence"


class TestQ104AnnexX:
    """Q104 — Annex X is the LIST OF UNION LEGAL ACTS on large-scale IT systems."""

    def test_answer_is_about_large_scale_it_systems_not_the_eu_database(self, ask):
        answer = (ask(Q104).get("answer") or "").lower()
        assert answer, "empty answer"
        assert "large-scale" in answer or "large scale" in answer
        assert "freedom, security and justice" in answer or "justice" in answer
        assert "111" in answer, "criterion 2: Annex X drives the Article 111(1) timeline"
        # The pre-R367 answer described Annex X as the registration annex, which
        # is Annex VIII. That confusion has a signature.
        assert "eu database" not in answer or "not the" in answer


class TestQ17AmendingAnnexIII:
    """Q17 — expected reference Article 7.1; 3 of 4 criteria FAIL before."""

    def test_answer_states_both_cumulative_conditions(self, ask):
        answer = (ask(Q17).get("answer") or "").lower()
        assert answer, "empty answer"
        assert "delegated act" in answer, "criterion 1: amendment is by delegated act"
        assert "annex iii" in answer, "criterion 2: intended for an area listed in Annex III"
        assert (
            "equivalent to or greater" in answer
            or "equal to or greater" in answer
            or "greater than" in answer
        ), "criterion 3: the risk threshold"
        assert (
            "cumulativ" in answer or "both" in answer
        ), "criterion 4: BOTH conditions must apply"


class TestTheGuardItself:
    """Unit-level pins on the R381 guard, so a failure localises."""

    def test_numeric_answer_must_contain_a_cardinal_that_is_not_a_coordinate(self):
        from app.routes.regenold import _extractive_shape_ok

        # The exact sentence that shipped for Q95. Its only digit is the "1" of
        # "paragraph 1" — a cross-reference, not the cardinal asked for.
        assert not _extractive_shape_ok(
            Q95,
            "In addition to the high-risk AI systems referred to in paragraph 1, "
            "AI systems referred to in Annex III shall be considered to be high-risk.",
        )
        assert _extractive_shape_ok(
            "How many areas exist in Annex III?",
            "Annex III lists eight areas of high-risk use cases.",
        )

    def test_list_answer_must_enumerate(self):
        from app.routes.regenold import _extractive_shape_ok

        assert not _extractive_shape_ok(
            Q45,
            "Where applicable, deployers of high-risk AI systems shall use the "
            "information provided under Article 13 of this Regulation to comply "
            "with their obligation to carry out a data protection impact "
            "assessment under Article 35 of Regulation (EU) 2016/679.",
        )
        assert _extractive_shape_ok(
            Q45,
            "The instructions for use shall contain at least the following "
            "information: (a) the identity and the contact details of the provider.",
        )

    def test_guard_is_a_no_op_when_switched_off(self, monkeypatch):
        from app.routes.regenold import _extractive_shape_ok

        monkeypatch.setenv("REGENOLD_EXTRACT_SHAPE_GUARD", "0")
        assert _extractive_shape_ok(Q45, "anything at all")

    def test_enumeration_walk_never_splices_across_numbered_blocks(self):
        """Annex III numbers its AREAS 1., 2., 3. and restarts letters inside
        each, so an unguarded (a)..(z) walk welds three areas into one list.
        Sweep the whole corpus: no rendered enumeration may contain a numbered
        heading."""
        from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT
        from app.routes.regenold import _enumerated_categories

        rendered = 0
        for ref in sorted(ARTICLE_FULL_TEXT):
            out = _enumerated_categories(ref)
            if not out:
                continue
            rendered += 1
            assert not re.search(r"(?:^|\s)\d{1,2}\.\s+[A-Z]", out), (
                f"{ref} spliced across a numbered block: {out[:200]}"
            )
        assert rendered >= 5, "the extractor rendered almost nothing — check the lead regex"
        assert _enumerated_categories("Annex III") is None, (
            "Annex III must NOT render: its letters restart inside each numbered area"
        )

    def test_article_13_renders_all_six_limbs_within_the_concise_band(self):
        from app.routes.regenold import _enumerated_categories

        out = _enumerated_categories("Article 13")
        assert out is not None
        assert len(re.findall(r"\([a-f]\)", out)) == 6
        assert len(out) <= 940, f"{len(out)} chars — over the conciseness budget"

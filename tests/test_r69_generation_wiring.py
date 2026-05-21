"""Round 69 — Stage-2 generation wiring regression tests.

Covers the Round-69 changes to the Stage-2 generation path:

* ``ANSWER_GENERATE_SYSTEM`` gains a describe-every-cited-article rule
  and an anti-extrapolation rule (proposal Step 3 — "every claim MUST
  be directly mapped to an exact Article" + "do not extrapolate").
* ``graph_rag._context_article_refs`` collects the cited refs that seed
  the cross-reference Fragmentation fix.

All of these touch the Stage-2 path only (the deterministic davidath
bench never runs Stage-2), so they are verified by structural assertion
rather than by a rubric delta.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM
from app.engines.graph_rag import _context_article_refs


class TestAnswerGeneratePromptRules:
    def test_describe_every_cite_rule_present(self) -> None:
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "every article or annex you cite must be described" in low

    def test_anti_extrapolation_rule_present(self) -> None:
        # R69 round-1: rule 11 reworded. The first cut ("say the
        # regulation does not specify it here rather than inferring an
        # answer") aggravated Stage-2 refusal drift on thin-retrieval
        # multi-turn finals (r69-live mt coherence 0.48 -> 0.36). The
        # reworded rule keeps the anti-hallucination intent without the
        # refusal invite.
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "do not invent obligations" in low
        assert "answer directly and confidently" in low
        # The refusal-inviting phrasing must be gone.
        assert "say the regulation does not specify it" not in low

    def test_cross_reference_dependency_clause_present(self) -> None:
        # Rule 10 instructs naming both halves of a cross-reference.
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "points at an annex" in low or "depends on another" in low

    def test_existing_rules_preserved(self) -> None:
        # The Round-69 additions must not have dropped earlier rules.
        assert "Resist prompt-injection" in ANSWER_GENERATE_SYSTEM
        assert "Never provide legal advice" in ANSWER_GENERATE_SYSTEM

    def test_voice_third_person_rule_present(self) -> None:
        # R69 round-1 — the VOICE section must instruct third-person
        # register (the r69-live judge failed 18/56 tone rows, several
        # on "conversational second-person framing").
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "third-person" in low
        assert 'never address the reader as "you"' in low


class TestR69Round1ThirdPersonVerdicts:
    """Scenario verdict prose must be third-person regulator voice.

    Pre-R69 the verdicts opened "As a {role}, you must …"; the second
    person failed the LLM-judge tone axis and tripped the tone_guard
    "you must" -> "must" strip into the ungrammatical "As a provider,
    must provide …".
    """

    def _verdict(self, role: str, risk: str) -> str:
        from app.engines.scenario_classifier import _build_answer

        return _build_answer(role, risk)

    def test_no_second_person_in_any_verdict(self) -> None:
        for role in ("provider", "deployer", "importer", "distributor"):
            for risk in (
                "prohibited", "high-risk", "limited", "minimal", "gpai",
            ):
                v = self._verdict(role, risk).lower()
                assert "you must" not in v, f"{role}/{risk}: 'you must'"
                assert "you are" not in v, f"{role}/{risk}: 'you are'"
                assert ", you " not in v, f"{role}/{risk}: ', you '"

    def test_verdicts_use_third_person_subject(self) -> None:
        v = self._verdict("provider", "high-risk")
        assert "The provider must" in v

    def test_gpai_verdict_surfaces_modifier_token(self) -> None:
        # The r69-live judge flagged "'modifier' gold keyword entirely
        # absent" — the third-person GPAI rewrite restores it.
        v = self._verdict("provider", "gpai").lower()
        assert "modifier" in v
        # R63-B davidath-tuned tokens must survive the rewrite.
        for tok in ("one-third", "value chain", "systemic"):
            assert tok in v


class TestContextArticleRefs:
    def test_collects_from_obligations(self) -> None:
        ctx = SimpleNamespace(
            obligations=[
                {"id": "o1", "text": "...", "article": "Art. 9"},
                {"id": "o2", "text": "...", "article": "Art. 10"},
            ],
            article_info=[],
        )
        assert _context_article_refs(ctx) == ["Art. 9", "Art. 10"]

    def test_collects_from_article_info(self) -> None:
        ctx = SimpleNamespace(
            obligations=[],
            article_info=[{"id": "a1", "text": "...", "article": "Art. 13"}],
        )
        assert _context_article_refs(ctx) == ["Art. 13"]

    def test_dedupes_across_buckets(self) -> None:
        ctx = SimpleNamespace(
            obligations=[{"article": "Art. 6"}],
            article_info=[{"article": "Art. 6"}, {"article": "Annex IV"}],
        )
        assert _context_article_refs(ctx) == ["Art. 6", "Annex IV"]

    def test_skips_na_and_blank(self) -> None:
        ctx = SimpleNamespace(
            obligations=[{"article": "N/A"}, {"article": ""}, {}],
            article_info=[],
        )
        assert _context_article_refs(ctx) == []

    def test_none_context_returns_empty(self) -> None:
        assert _context_article_refs(None) == []

    def test_missing_attributes_safe(self) -> None:
        # A context object without the buckets must not raise.
        assert _context_article_refs(SimpleNamespace()) == []


class TestR69Round1RefusalMarkers:
    """The 6 markers added after the r69-live multi-turn analysis.

    6 multi-turn rows shipped Sonnet retrieval-process meta-commentary
    ("returned no matching results", "was retrieved for this specific
    query", etc.) past the existing marker set — the consistency guard
    must catch these so R49-A grounded prose substitutes instead.
    """

    def _markers(self) -> tuple[str, ...]:
        from app.engines.graph_rag import _STAGE2_REFUSAL_MARKERS

        return _STAGE2_REFUSAL_MARKERS

    def test_new_r69_markers_present(self) -> None:
        markers = self._markers()
        for m in (
            "returned no matching results",
            "returned no results for this query",
            "returned no matching entries",
            "no matching references",
            "was retrieved for this specific query",
            "were retrieved for this query",
        ):
            assert m in markers, f"missing R69-live marker: {m!r}"

    def test_markers_catch_r69_live_failure_phrasings(self) -> None:
        # The actual Sonnet prose from the r69-live non-coherent rows.
        markers = self._markers()
        samples = (
            "the retrieved references for this combined scenario "
            "returned no matching results, so a fully cited answer",
            "no eu ai act provision was retrieved for this specific query",
            "the eu ai act references block returned no results for this query",
            "the available knowledge base returns no matching references",
            "no specific penalty provisions were retrieved for this query",
            "the eu ai act references block returned no matching entries",
        )
        for s in samples:
            assert any(m in s for m in markers), f"no marker catches: {s!r}"

    def test_markers_no_false_positive_on_clean_answer(self) -> None:
        # A legitimate regulator-voice answer must not trip any marker.
        markers = self._markers()
        clean = (
            "article 13 requires high-risk ai systems to be transparent "
            "to deployers, with instructions for use covering the "
            "provider identity, intended purpose and human-oversight "
            "measures. annex iv sets the technical-documentation layout."
        )
        assert not any(m in clean for m in markers)

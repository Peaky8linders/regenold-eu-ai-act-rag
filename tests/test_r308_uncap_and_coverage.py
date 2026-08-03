"""R308 — answer uncap + the ported ANSWER COVERAGE clause.

Operator directive (2026-08-03): "no hard cap please, the stage 2 system
prompts must be able to get to the right content and phrases to correctly
answer."

Two independently-gated changes are pinned here:

1. ``REGENOLD_ANSWER_NO_CAP`` (default ON) — a request-scoped ContextVar the
   route sets when ``stage2_landed``, which removes BOTH the sentence cap and
   the soft char-cap loop from ``normalise_answer_for_regenold``.

2. ``REGENOLD_ANSWER_COVERAGE`` (default ON) — appends
   ``USER_ANSWER_COVERAGE_CLAUSE`` to the Stage-2 USER message, the only
   channel the Claude Max wrapper actually delivers.

THE MEASUREMENT BEHIND (2) — pinned here so a future round does not "simplify"
the clause back into the system prompt. On 2026-08-03 the Stage-2 SYSTEM prompt
was proven live to be dropped 100%: the identical request with "always answer
exclusively in French" in the system slot returned byte-identical output to the
no-instruction control on BOTH claude-sonnet-4-6 and claude-opus-4-6, while the
user slot obeyed. Forwarding the system prompt is NOT the fix — R282 measured
that as rubric-negative (kw_recall -0.267).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.data.graph_rag_prompts import (
    USER_ANSWER_COVERAGE_CLAUSE,
    answer_coverage_enabled,
)
from app.integrations.regenold.models import (
    MAX_ANSWER_SENTENCES,
    _split_sentences,
    answer_no_cap_active,
    normalise_answer_for_regenold,
    set_answer_no_cap,
)

# A seven-sentence answer whose sentences all carry a citation anchor, so the
# soft char-cap loop cannot drop any of them. Modelled on the real live
# truncation this round fixed: prod shipped 3 sentences / 298 chars announcing
# "a defined set of obligations under Article 26" and then delivered 2 of ~6.
_SEVEN_SENTENCE_ANSWER = (
    "Deployers of high-risk AI systems must comply with a defined set of "
    "obligations under Article 26. They must use the system in accordance "
    "with the instructions for use under Article 26(1). They must assign "
    "human oversight to competent natural persons under Article 26(2). They "
    "must ensure input data is relevant under Article 26(4). They must "
    "monitor operation under Article 26(5). They must keep the automatically "
    "generated logs under Article 26(6). They must inform workers "
    "representatives under Article 26(7)."
)

_Q = "What are the deployer obligations?"


@pytest.fixture(autouse=True)
def _isolate_r308_env():
    """Reset both R308 switches around every test (no cross-test leakage)."""
    saved = {
        k: os.environ.get(k)
        for k in (
            "REGENOLD_ANSWER_NO_CAP",
            "REGENOLD_ANSWER_COVERAGE",
            "REGENOLD_MAX_ANSWER_SENTENCES",
        )
    }
    for k in saved:
        os.environ.pop(k, None)
    set_answer_no_cap(False)
    yield
    set_answer_no_cap(False)
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---------------------------------------------------------------------------
# 1. The uncap
# ---------------------------------------------------------------------------


class TestAnswerUncap:
    def test_default_is_capped_so_davidath_stays_byte_identical(self):
        """No ContextVar, no env => the module constant still governs.

        This is the load-bearing davidath guarantee: the deterministic bench
        runs provider=cli with no wrapper, so stage2_landed is never True and
        the route never sets the ContextVar.
        """
        assert answer_no_cap_active() is False
        out = normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        assert len(_split_sentences(out)) == MAX_ANSWER_SENTENCES

    def test_uncap_preserves_every_sentence(self):
        set_answer_no_cap(True)
        out = normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        assert len(_split_sentences(out)) == 7

    def test_uncap_delivers_the_content_the_cap_was_dropping(self):
        """The point of the round: the later Article 26 duties survive."""
        capped = normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        set_answer_no_cap(True)
        uncapped = normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        for late_duty in ("logs", "workers"):
            assert late_duty not in capped
            assert late_duty in uncapped

    def test_uncap_also_disables_the_soft_char_cap_loop(self):
        """R306 found the CHAR cap, not the sentence count, is what bites on
        the real graded set (only 2/30 rows are sentence-cap bound).

        The char-cap loop drops the longest sentence that does NOT cite an
        article, which is exactly how an enumerated list loses its members.
        This sample is under the sentence cap (3 sentences) but over the
        400-char QA budget, with two droppable non-cite sentences, so it
        isolates the char loop from the sentence slice.
        """
        sample = (
            "Deployers of high-risk AI systems must comply with Article 26. "
            "They must ensure that the natural persons assigned to human "
            "oversight have the necessary competence, training and authority, "
            "and that they are supported appropriately in carrying out that "
            "function throughout the operating period. "
            "They must also keep the automatically generated logs for a period "
            "appropriate to the intended purpose, being at least six months "
            "unless a longer retention period is required by other applicable "
            "Union or national law."
        )
        assert len(_split_sentences(sample)) == 3, "sample must not hit the sentence cap"
        assert len(sample) > 400, "sample must exceed the QA char budget"

        capped = normalise_answer_for_regenold(sample, question=_Q)
        set_answer_no_cap(True)
        uncapped = normalise_answer_for_regenold(sample, question=_Q)

        # The loop ran under the cap and dropped a non-cite sentence...
        assert len(_split_sentences(capped)) < 3
        # ...and is disabled under the uncap, so nothing is lost.
        assert len(_split_sentences(uncapped)) == 3
        assert len(uncapped) > len(capped)

    def test_explicit_env_cap_still_wins_over_the_uncap(self):
        """An operator must be able to pin a cap back on without a code change."""
        set_answer_no_cap(True)
        os.environ["REGENOLD_MAX_ANSWER_SENTENCES"] = "2"
        out = normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        assert len(_split_sentences(out)) == 2

    def test_no_contextvar_leakage_between_requests(self):
        """Toggling on then off must restore byte-identical output.

        The route sets the ContextVar unconditionally (True *or* False) on
        every request precisely so a reused worker thread cannot inherit a
        stale value.
        """
        before = normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        set_answer_no_cap(True)
        normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        set_answer_no_cap(False)
        after = normalise_answer_for_regenold(_SEVEN_SENTENCE_ANSWER, question=_Q)
        assert before == after

    def test_uncap_never_empties_or_raises_on_degenerate_input(self):
        set_answer_no_cap(True)
        for junk in ("", "   ", ".", "Article 26."):
            normalise_answer_for_regenold(junk, question=_Q)  # must not raise


# ---------------------------------------------------------------------------
# 2. The ported ANSWER COVERAGE clause
# ---------------------------------------------------------------------------


class TestAnswerCoverageClause:
    def test_enabled_by_default_and_env_reversible(self):
        assert answer_coverage_enabled() is True
        os.environ["REGENOLD_ANSWER_COVERAGE"] = "0"
        assert answer_coverage_enabled() is False

    def test_no_forbidden_punctuation(self):
        """R108 — the wire forbids em/en dashes and ellipses, so the PROMPT
        must not model them to the model."""
        assert "—" not in USER_ANSWER_COVERAGE_CLAUSE  # em dash
        assert "–" not in USER_ANSWER_COVERAGE_CLAUSE  # en dash
        assert "…" not in USER_ANSWER_COVERAGE_CLAUSE  # ellipsis
        assert "..." not in USER_ANSWER_COVERAGE_CLAUSE

    def test_carries_the_anti_citation_inflation_guard(self):
        """THE load-bearing sentence. legal_v2 scores reference correctness as
        governing / (governing + supporting + wrong) and we currently PASS at
        0.8056, so every extra supporting ref cuts it arithmetically. R284's
        own COMPLETENESS clause was defaulted OFF for exactly this regression
        (pred:gold 1.71 -> 1.75) and R142.1 lost a live pairwise judge 11-0.
        If a future edit drops this guard, the clause must not ship.
        """
        low = USER_ANSWER_COVERAGE_CLAUSE.lower()
        assert "never a licence to cite" in low
        assert "adds no new reference" in low
        # coverage is paid for by CUTTING, not by adding length
        assert "cutting" in low

    def test_covers_the_measured_omission_modes(self):
        low = USER_ANSWER_COVERAGE_CLAUSE.lower()
        # literal-question closure (the top undelivered rule)
        assert "yes or no" in low
        # closed-set completeness (repairs the dangling "rule 12b" pointer)
        assert "enumerated statutory set" in low
        # announce-a-count-then-omit, the prose truncation R306's guard misses
        assert "leave them unnamed" in low

    def test_is_compact(self):
        """R277 measured a 3.2K vs 51K prompt as quality-neutral, so compact is
        fine; but an unbounded clause would crowd the delivered channel."""
        assert 900 <= len(USER_ANSWER_COVERAGE_CLAUSE) <= 1800


class TestClauseIsActuallyDelivered:
    """R256 — a change that never reaches the wire is worse than no change."""

    def _capture_user_message(self) -> str:
        import app.engines._graph_rag_impl as impl
        from app.engines._graph_rag_impl import GraphContext

        captured: dict = {}

        def _spy(**kwargs):
            captured.update(kwargs)
            return None

        with patch.object(
            impl, "_openai_wrapper_complete_for_graph_rag", side_effect=_spy
        ):
            impl._claude_max_enhance_answer(
                question=_Q,
                kg_answer="Deployers must comply with Article 26.",
                context=GraphContext(),
            )
        return captured.get("user", "")

    def test_clause_reaches_the_stage2_user_message(self):
        os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:8000/v1"
        os.environ["P2P_GRAPH_RAG_PROVIDER"] = "openai_wrapper"
        user = self._capture_user_message()
        assert "ANSWER COVERAGE:" in user

    def test_clause_absent_when_gated_off(self):
        os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:8000/v1"
        os.environ["P2P_GRAPH_RAG_PROVIDER"] = "openai_wrapper"
        os.environ["REGENOLD_ANSWER_COVERAGE"] = "0"
        user = self._capture_user_message()
        assert "ANSWER COVERAGE:" not in user


# ---------------------------------------------------------------------------
# 3. Cache-key discipline — the deliberate asymmetry
# ---------------------------------------------------------------------------


class TestCacheKeyAsymmetry:
    """R263.2 doctrine, applied in BOTH directions.

    ENGINE flags must be in the key or an in-process two-arm A/B silently
    serves arm A's cache to arm B. ROUTE post-processing flags must NOT be,
    because the post-processing re-runs on every cache hit — and keeping
    NO_CAP out is precisely what makes the paired zero-generation-variance
    A/B possible (measured: arm B cache-served in 0.1s vs arm A's 37.8s).
    """

    def _key(self) -> str:
        from app.routes.regenold import _engine_cache_key

        return _engine_cache_key(_Q, None)

    def test_coverage_flag_changes_the_key(self):
        os.environ["REGENOLD_ANSWER_COVERAGE"] = "1"
        on = self._key()
        os.environ["REGENOLD_ANSWER_COVERAGE"] = "0"
        assert self._key() != on

    def test_no_cap_flag_does_not_change_the_key(self):
        os.environ["REGENOLD_ANSWER_NO_CAP"] = "1"
        on = self._key()
        os.environ["REGENOLD_ANSWER_NO_CAP"] = "0"
        assert self._key() == on

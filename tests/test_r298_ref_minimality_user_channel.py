"""R298 — reference minimality + challenge brevity on the Stage-2 USER channel.

WHY THE USER CHANNEL. R281 wrote the minimality rule into
``ANSWER_GENERATE_SYSTEM`` and then measured that it can never fire: the
Claude-Max wrapper DROPS the system message (``claude_cli.py:152`` sends
``{"type":"text"}``; claude_agent_sdk 0.2.82 accepts only str / preset / file
and discards the unknown dict silently — BANANA test 0/3 system, 3/3 user).
R282 then measured that "fixing" the wrapper is rubric-negative. So the rule is
mirrored onto the user message, which IS delivered. These tests pin that the
clause actually lands there, because an inert prompt fix is the R256 failure
mode this whole round exists to avoid.
"""
from __future__ import annotations

import pytest

from app.data.graph_rag_prompts import (
    ANSWER_GENERATE_SYSTEM,
    USER_CHALLENGE_BREVITY_CLAUSE,
    USER_REF_MINIMALITY_CLAUSE,
    challenge_brevity_enabled,
    is_challenge_turn,
    resolve_answer_system,
    user_ref_minimality_enabled,
)

_FLAGS = ("REGENOLD_USER_REF_MINIMALITY", "REGENOLD_CHALLENGE_BREVITY")


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch):
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)


# ── gates ────────────────────────────────────────────────────────────────────

class TestGates:
    def test_both_default_on_after_the_ab_held(self):
        """R298 shipped these ON only after a live A/B held on EVERY axis and
        BOTH strata (ref precision 0.423 -> 0.735 with recall 0.909 -> 0.966;
        answer correctness 0.471 -> 0.647). Pin the default so a silent revert
        is loud."""
        assert user_ref_minimality_enabled() is True
        assert challenge_brevity_enabled() is True

    def test_env_off_switch_still_works(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", "0")
        monkeypatch.setenv("REGENOLD_CHALLENGE_BREVITY", "0")
        assert user_ref_minimality_enabled() is False
        assert challenge_brevity_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "ON", " True "])
    def test_truthy_values_enable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", val)
        monkeypatch.setenv("REGENOLD_CHALLENGE_BREVITY", val)
        assert user_ref_minimality_enabled() is True
        assert challenge_brevity_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_falsy_values_disable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", val)
        assert user_ref_minimality_enabled() is False

    def test_flags_read_fresh_per_call(self, monkeypatch):
        """In-process two-arm A/B validity (the R263.2 doctrine)."""
        monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", "0")
        assert user_ref_minimality_enabled() is False
        monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", "1")
        assert user_ref_minimality_enabled() is True
        monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", "0")
        assert user_ref_minimality_enabled() is False

    def test_system_prompt_untouched_by_r298(self, monkeypatch):
        """R298 must not alter the (inert) system channel in either state."""
        assert resolve_answer_system() == ANSWER_GENERATE_SYSTEM
        monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", "1")
        monkeypatch.setenv("REGENOLD_CHALLENGE_BREVITY", "1")
        assert resolve_answer_system() == ANSWER_GENERATE_SYSTEM


# ── challenge detector ───────────────────────────────────────────────────────

class TestChallengeDetector:
    @pytest.mark.parametrize("q", [
        # the evaluator's verbatim pushback template
        "I don't think this is correct. Perhaps your answer contains "
        "hallucinations.\n\nLet's try again:\nWhat does Article 13 require?",
        "That is incorrect.",
        "that's wrong, try again",
        "Are you sure?",
        "You're hallucinating.",
    ])
    def test_fires_on_answer_directed_dispute(self, q):
        assert is_challenge_turn(q) is True

    @pytest.mark.parametrize("q", [
        "What are the obligations of deployers of high-risk AI systems?",
        # CRITICAL false-positive guard: a question about whether a LEGAL
        # PROPOSITION is correct is not a dispute of our previous answer.
        "Is it correct that Article 5 prohibits social scoring?",
        "Is this classification correct under Article 6?",
        "What is a deployer?",
        "",
    ])
    def test_does_not_fire_on_ordinary_questions(self, q):
        assert is_challenge_turn(q) is False

    def test_only_the_live_turn_counts(self):
        """R60.1 / R71 live-turn doctrine — a dispute in an EARLIER turn must
        not keep re-triggering the brevity clause on every later turn."""
        q = (
            "Conversation so far:\n"
            "I don't think this is correct. Let's try again:\n"
            "assistant: ...\n"
            "Latest question:\n"
            "What does Article 13 require?"
        )
        assert is_challenge_turn(q) is False

    def test_fires_when_dispute_is_in_the_live_turn(self):
        q = (
            "Conversation so far:\n"
            "What is a deployer?\n"
            "Latest question:\n"
            "That is incorrect, are you sure?"
        )
        assert is_challenge_turn(q) is True

    @pytest.mark.parametrize("bad", [None, 123, object()])
    def test_fail_soft_on_bad_input(self, bad):
        assert is_challenge_turn(bad) is False  # type: ignore[arg-type]


# ── clause content ───────────────────────────────────────────────────────────

class TestClauseContent:
    def test_minimality_clause_states_the_converse_of_rule_10(self):
        c = USER_REF_MINIMALITY_CLAUSE.lower()
        assert "minimal" in c or "only the provisions" in c
        # names the specific over-cited apparatus measured in R297
        assert "article 6" in c and "annex iii" in c
        assert "9 to 15" in c

    def test_challenge_clause_forbids_expansion_without_forbidding_correction(self):
        c = USER_CHALLENGE_BREVITY_CLAUSE.lower()
        assert "same length or shorter" in c
        assert "not a request for more" in c
        # must still allow a genuine correction — never train capitulation OR
        # stubbornness; R297 measured 0/11 concessions and that must hold.
        assert "genuinely wrong" in c

    def test_clauses_are_compact(self):
        """R282: dumping instruction volume into a DELIVERED channel is itself
        harmful. Keep both clauses well under 1 KB."""
        assert len(USER_REF_MINIMALITY_CLAUSE) < 1000
        assert len(USER_CHALLENGE_BREVITY_CLAUSE) < 1000


# ── cache key ────────────────────────────────────────────────────────────────

class TestStratifiedFractionSampler:
    """R298 — `--frac` rescales the R297 stratified design."""

    @pytest.mark.parametrize("frac,lo,hi", [(0.10, 9.0, 11.5), (0.15, 14.0, 16.5),
                                            (0.25, 24.0, 27.0), (0.50, 49.0, 52.0)])
    def test_hits_the_requested_share(self, frac, lo, hi):
        from evals.regenold.run_hard_sample_r297 import (
            TOTAL_HARD_REQUESTS,
            quotas_for_fraction,
        )

        n_mt, quota = quotas_for_fraction(frac)
        pct = 100.0 * (n_mt * 2 + sum(quota.values())) / TOTAL_HARD_REQUESTS
        assert lo <= pct <= hi, f"frac={frac} produced {pct:.1f}%"

    def test_every_rare_category_keeps_its_floor_of_one(self):
        """Without the floor, a proportional draw reports NOTHING about three of
        the five single-turn categories (they have 1, 2 and 5 members)."""
        from evals.regenold.run_hard_sample_r297 import quotas_for_fraction

        for frac in (0.05, 0.10, 0.15, 0.30):
            _, quota = quotas_for_fraction(frac)
            assert len(quota) == 5
            assert all(v >= 1 for v in quota.values()), (frac, quota)

    def test_is_deterministic_and_covers_all_hard_categories(self):
        from evals.regenold.run_hard_sample_r297 import select_sample

        a_mt, a_st = select_sample(0.15)
        b_mt, b_st = select_sample(0.15)
        assert [r.id for r in a_mt] == [r.id for r in b_mt]
        assert [r.id for r in a_st] == [r.id for r in b_st]
        assert len({r.difficulty_category for r in a_st}) == 5

    def test_default_is_the_original_r297_design(self):
        from evals.regenold.run_hard_sample_r297 import select_sample

        mt, st = select_sample(None)
        assert len(mt) == 11 and len(st) == 8  # 30 requests = 10.7%


class TestCacheKey:
    @pytest.mark.parametrize("flag", _FLAGS)
    def test_flag_is_in_the_engine_cache_key(self, monkeypatch, flag):
        """R30/R56/R79/R263.2 — both flags flip the polished answer AND its
        citations, so they must change the cache identity or an in-process
        two-arm A/B cross-contaminates."""
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv(flag, "0")
        off = _engine_cache_key("q", None)
        monkeypatch.setenv(flag, "1")
        on = _engine_cache_key("q", None)
        assert off != on

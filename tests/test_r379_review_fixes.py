"""R379 — pins for the executed findings of the PR #368 review.

Every case below reproduces a defect the reviewer EXECUTED against ``0033b88``
(the merged Gemini delta), not one it read. The assertions are on behaviour,
never on source text.

* P1-3  ``_CHALLENGE_PATTERNS`` fired on the Act's own wording and on first-turn
        questions, appending "the user is disputing the previous answer … say the
        same thing at the SAME length" to a turn with no previous answer.
* P2-7  ``REGENOLD_PROMPT_V2`` used allow-list truthiness in a file whose other
        default-ON gates use deny-list, so a blank value silently reverted prod to V1.
* P2-8  the markdown-table rule excused a stream cut right after a cell separator.
* P1-1/P1-2/P2-4  ``REGENOLD_FIDELITY_TIER_NEGATION`` discarded correct polishes,
        switched the guard off on "not X under Annex I, but X under Annex III",
        and was a no-op on the engine's real drafts — it now ships OFF.
* P2-9  the R355 cache-key AST gate did not scan ``app/data``, where
        ``REGENOLD_PROMPT_V2`` lives.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")

MARK = "Conversation so far:\nuser: Is my CV screener high-risk?\nassistant: Yes, Annex III(4)(a).\nLatest question:\n"


# ── P1-3 — the leading-confirmation family ───────────────────────────────────
class TestChallengeFamilyIsScopedToRealPushbacks:
    @pytest.mark.parametrize(
        "first_turn",
        [
            # The Act's own wording (Art. 3(36) / Annex III(1)(a)) — the decisive case.
            "We want to deploy an AI system that performs biometric verification "
            "solely to confirm that a specific natural person is the person he or "
            "she claims to be. Is this system prohibited? Is it high-risk?",
            "Can you confirm that Article 6(3) applies to preparatory tasks?",
            "Please confirm that our chatbot needs an Article 50 notice.",
            "Under the research exemption we are exempt, so what happens at deployment?",
            "Our provider says we have no obligations under Chapter III. What does the Act say?",
            "Is a medical device AI classified under Annex I or Annex III, right?",
            "Is the system high-risk, yes?",
        ],
    )
    def test_first_turn_questions_are_never_challenges(self, first_turn: str) -> None:
        """No prior turn ⇒ nothing to dispute ⇒ the brevity clause must not append."""
        from app.data.graph_rag_prompts import is_challenge_turn

        assert is_challenge_turn(first_turn) is False

    @pytest.mark.parametrize(
        "live_turn",
        [
            "So the derogation applies and we are exempt, correct?",
            "Our system only does preparatory work, so we are exempt, right?",
            "Confirm that we have no obligations under Article 16.",
            "We have no obligations under Chapter III, agreed?",
            "That is not what the regulation says.",
            # R379 — a real pushback the port missed: "annex" was not in the alternation.
            "No, that is not what Annex III says.",
        ],
    )
    def test_leading_confirmation_still_fires_with_a_prior_turn(self, live_turn: str) -> None:
        from app.data.graph_rag_prompts import is_challenge_turn

        assert is_challenge_turn(MARK + live_turn) is True

    def test_act_verbatim_confirm_that_never_fires_even_multi_turn(self) -> None:
        """Mid-sentence "confirm that" is the statute's verb, not a ratification demand."""
        from app.data.graph_rag_prompts import is_challenge_turn

        live = (
            "The tool performs biometric verification solely to confirm that a "
            "specific natural person is the person he or she claims to be. Is it "
            "high-risk?"
        )
        assert is_challenge_turn(MARK + live) is False

    def test_explicit_dispute_markers_stay_unconditional(self) -> None:
        """The benchmark's own hard-mode pushback must fire with or without history."""
        from app.data.graph_rag_prompts import is_challenge_turn

        pb = (
            "I don't think this is correct. Perhaps your answer contains "
            "hallucinations. Let's try again: What is Annex X about?"
        )
        assert is_challenge_turn(pb) is True
        assert is_challenge_turn(MARK + pb) is True

    def test_davidath_is_byte_identical_by_construction(self) -> None:
        """The R302 freeze comment's claim, re-verified after the R379 narrowing."""
        from evals.bench.dataset import load_qa_pairs, load_scenarios, scenario_to_question

        from app.data.graph_rag_prompts import is_challenge_turn

        qs = [i.get("question") or "" for i in load_qa_pairs()]
        qs += [scenario_to_question(s) for s in load_scenarios()]
        assert len(qs) == 476
        assert [q for q in qs if is_challenge_turn(q)] == []


# ── P2-7 / gate — flag truthiness and the measured default ───────────────────
class TestPromptV2FlagFailsClosed:
    """The port used allow-list truthiness on a default-ON flag (P2-7), so a
    blank value silently reverted prod to V1. R379's Bedrock A/B then failed
    hard rule #8 on the easy split, so the DEFAULT is now OFF - and for a
    default-OFF gate allow-list truthiness is the correct, fail-closed form
    (R321): anything we cannot read as ON is OFF."""

    def test_unset_is_off(self, monkeypatch) -> None:
        from app.data.graph_rag_prompts import _prompt_v2_enabled

        monkeypatch.delenv("REGENOLD_PROMPT_V2", raising=False)
        assert _prompt_v2_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "ON", " 1 "])
    def test_explicit_on_is_on(self, monkeypatch, value: str) -> None:
        from app.data.graph_rag_prompts import _prompt_v2_enabled

        monkeypatch.setenv("REGENOLD_PROMPT_V2", value)
        assert _prompt_v2_enabled() is True

    @pytest.mark.parametrize("value", ["", "0", "off", "false", "no", "Y", "enabled", "2"])
    def test_anything_unreadable_is_off(self, monkeypatch, value: str) -> None:
        from app.data.graph_rag_prompts import _prompt_v2_enabled

        monkeypatch.setenv("REGENOLD_PROMPT_V2", value)
        assert _prompt_v2_enabled() is False


# ── P2-8 — the table rule ────────────────────────────────────────────────────
class TestTableRowRuleDoesNotExcuseAMidRowCut:
    @pytest.mark.parametrize(
        "cut",
        [
            "| Role | Provision |\n| Provider | Article 16 |\n| Deployer |",
            "| a |",
        ],
    )
    def test_single_cell_tail_is_still_a_cut(self, cut: str) -> None:
        from app.engines._graph_rag_impl import _looks_structurally_truncated

        assert _looks_structurally_truncated(cut) is True

    @pytest.mark.parametrize(
        "complete",
        [
            "| Role | Provision |\n| Provider | Article 16 |\n| Deployer | Article 26 |",
            "<answer>\n| Role | Provision |\n| Provider | Article 16 |\n</answer>",
        ],
    )
    def test_complete_rows_are_still_complete(self, complete: str) -> None:
        from app.engines._graph_rag_impl import _looks_structurally_truncated

        assert _looks_structurally_truncated(complete) is False


# ── P1-1 / P1-2 / P2-4 — tier negation ships OFF ─────────────────────────────
class TestTierNegationDefaultsOff:
    def test_default_is_off(self, monkeypatch) -> None:
        from app.engines.stage2_fidelity import tier_negation_enabled

        monkeypatch.delenv("REGENOLD_FIDELITY_TIER_NEGATION", raising=False)
        assert tier_negation_enabled() is False

    def test_off_restores_the_anchor_only_contract(self, monkeypatch) -> None:
        from app.engines.stage2_fidelity import (
            extract_asserted_tier_set,
            extract_tier_set,
        )

        monkeypatch.delenv("REGENOLD_FIDELITY_TIER_NEGATION", raising=False)
        draft = (
            "This system is not high-risk under Annex I, but it is high-risk "
            "under Annex III and Article 6. Article 50 transparency duties apply."
        )
        assert extract_asserted_tier_set(draft) == extract_tier_set(draft)

    def test_on_reproduces_the_executed_regression(self, monkeypatch) -> None:
        """Documents WHY it is off: the same-sentence contrast deletes the tier."""
        from app.engines.stage2_fidelity import extract_asserted_tier_set

        monkeypatch.setenv("REGENOLD_FIDELITY_TIER_NEGATION", "1")
        draft = (
            "This system is not high-risk under Annex I, but it is high-risk "
            "under Annex III and Article 6."
        )
        assert "high_risk" not in extract_asserted_tier_set(draft), (
            "if this starts passing the sentence-level denial filter was fixed — "
            "re-measure before flipping the default back on"
        )


# ── P2-9 — the AST gate now covers app/data ──────────────────────────────────
class TestCacheKeyGateCoversPromptModule:
    def test_gate_scans_app_data(self) -> None:
        import tests.test_r355_cache_key_complete as gate

        assert any(str(d).replace("\\", "/").endswith("app/data") for d in gate._ENGINE_DIRS), (
            "REGENOLD_PROMPT_V2 lives in app/data/graph_rag_prompts.py — an "
            "unregistered flag there would poison a same-process A/B and the "
            "gate would not notice"
        )

    def test_prompt_v2_is_in_the_engine_cache_key(self) -> None:
        from app.routes.regenold import _engine_cache_key

        args = ("What must the instructions for use contain?", None)
        os.environ["REGENOLD_PROMPT_V2"] = "0"
        off = _engine_cache_key(*args)
        os.environ["REGENOLD_PROMPT_V2"] = "1"
        on = _engine_cache_key(*args)
        os.environ.pop("REGENOLD_PROMPT_V2", None)
        assert off != on

"""R402 — Stage-2 evidence tuning tripwires from the r402 hard-set judge run.

Three production defects measured live (Bedrock Qwen 3 235B, official 110 hard
mode, Overall 82.87 vs frontier 81.7):

1. ``rg_062`` — Stage-2 produced a substantive multi-obligation answer, the
   token cap cut its final sentence, tail repair failed, and the guard shipped
   the 82-char deterministic role-matrix stub. The legal judge failed every
   criterion on the stub. Fix: salvage the complete-sentence prefix of the
   polish when it is materially richer than the stub.

2. Procedural role questions ("What must a distributor do if it considers a
   high-risk system not in conformity?") intercepted by the two-line
   role-obligation matrix verdict, which cannot carry the procedure's
   substance. Fix: ``_ROLE_PROCEDURAL_RE`` routes them to retrieval + polish.

3. The R327 constrained semantic layer (five dark Aura vector indexes) shipped
   default OFF despite live validation that it surfaces exactly the missing
   sub-limb evidence on the failing rows. Fix: default ON, deny-list form.

Also pins the R402 additions to ``EVIDENCE_ANSWER_CONTRACT`` (exceptions-with-
the-duty; bare verdict first).
"""
from __future__ import annotations

import pytest

from app.engines.graph_rag.models import GraphContext


# ── 1. truncation salvage ────────────────────────────────────────────────────


class TestSalvageTruncatedPolish:
    def _guard(self):
        from app.engines.graph_rag import _guard_stage2_truncation

        return _guard_stage2_truncation

    def _ctx(self) -> GraphContext:
        return GraphContext()

    def test_salvage_keeps_rich_prefix_over_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The rg_062 shape: rich polish cut mid-sentence, repair fails.

        Must ship the salvaged complete-sentence prefix, NOT the 82-char stub.
        """

        def fail_repair(question, enhanced, kg_answer, context):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.engines.graph_rag._attempt_stage2_tail_repair", fail_repair
        )
        rich = (
            "A distributor that considers, on the basis of the information in its "
            "possession, that a high-risk AI system is not in conformity must not "
            "make that system available on the market until it has been brought "
            "into conformity, and must inform the provider or importer. "
            "Where the system presents a risk within the meaning of Article 79(1), "
            "the distributor must also immediately inform the competent authorit"
        )
        out, used = self._guard()("q", rich, "Distributors are bound by Article 24.", self._ctx())
        assert used is True
        assert out.startswith(
            "A distributor that considers"
        )
        assert out.endswith("provider or importer.")
        assert len(out) > 240

    def test_thin_fragment_still_falls_back_to_kg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A polish with no salvageable substance defers to the deterministic
        answer — the historical behaviour is preserved for thin fragments."""

        def fail_repair(question, enhanced, kg_answer, context):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.engines.graph_rag._attempt_stage2_tail_repair", fail_repair
        )
        out, used = self._guard()(
            "q",
            "The distributor must also inform the competent authorit",
            "DETERMINISTIC_KG",
            self._ctx(),
        )
        assert out == "DETERMINISTIC_KG"
        assert used is False

    def test_prefix_not_richer_than_stub_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Salvage must not ship a prefix SHORTER than the deterministic
        answer — that would trade substance for prose."""

        def fail_repair(question, enhanced, kg_answer, context):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.engines.graph_rag._attempt_stage2_tail_repair", fail_repair
        )
        stub = "Distributors are bound by Article 24 and must verify conformity before making the system available on the market."
        rich_stub = (
            "Distributors are bound by Article 24. They must also verify the CE "
            "marking before making the system availab"
        )
        out, used = self._guard()("q", rich_stub, stub, self._ctx())
        assert out == stub
        assert used is False

    def test_complete_polish_unaffected(self) -> None:
        out, used = self._guard()(
            "q", "The system is high-risk under Article 6(1).", "kg", self._ctx()
        )
        assert out == "The system is high-risk under Article 6(1)."
        assert used is True


# ── 2. procedural role questions must not hit the matrix stub ────────────────


class TestRoleObligationProceduralNarrowing:
    def test_rg062_question_does_not_fire_matrix(self) -> None:
        """The exact r402 failing question — must reach retrieval + polish."""
        from app.engines.graph_rag import _detect_role_obligation_query

        q = (
            "What must a distributor do if it considers a high-risk AI system "
            "is not in conformity with the Act's requirements? Additionally, "
            "what extra steps are required if the system presents a risk "
            "within the meaning of Article 79(1)?"
        )
        assert _detect_role_obligation_query(q) is None

    def test_plain_catalogue_question_still_fires(self) -> None:
        """The matrix path stays for the enumeration it was built for."""
        from app.engines.graph_rag import _detect_role_obligation_query

        match = _detect_role_obligation_query(
            "What are the obligations of a deployer of a high-risk AI system?"
        )
        assert match is not None
        role_id, risk_id = match
        assert role_id == "deployer"
        assert risk_id in ("high_risk_annex_iii", "high_risk_annex_i")

    def test_i_am_subject_scenario_still_fires(self) -> None:
        """First-person scenarios without procedural follow-ups keep the
        deterministic verdict (fast, citation-exact)."""
        from app.engines.graph_rag import _detect_role_obligation_query

        match = _detect_role_obligation_query(
            "I am a deployer of a high-risk AI system under Annex III. "
            "What are my obligations?"
        )
        assert match is not None
        assert match[0] == "deployer"

    def test_multiturn_flattened_procedural_question_does_not_fire(self) -> None:
        """The gate runs on the live turn of a flattened conversation."""
        from app.engines.graph_rag import _detect_role_obligation_query

        q = (
            "Conversation so far:\nUser: I am a deployer of a high-risk AI "
            "system.\nAssistant: Deployers of a high-risk AI system are bound "
            "by Article 26.\n\nLatest question: What must I do if the system "
            "presents a risk within the meaning of Article 79(1)?"
        )
        assert _detect_role_obligation_query(q) is None


# ── 3. semantic layers default ON (deny-list) ────────────────────────────────


class TestSemanticLayersDefault:
    def test_default_on_without_env(self) -> None:
        import os

        from app.engines.graph_semantic import semantic_layers_enabled

        os.environ.pop("REGENOLD_GRAPH_SEMANTIC_LAYERS", None)
        assert semantic_layers_enabled() is True

    def test_gloss_stays_default_off(self) -> None:
        """The open-domain half keeps its measured OFF default — the R327.1
        substitution failure mode is excluded by construction."""
        import os

        from app.engines.graph_semantic import gloss_layers_enabled

        os.environ.pop("REGENOLD_SEMANTIC_GLOSS", None)
        assert gloss_layers_enabled() is False


# ── 4. evidence contract completeness directives ─────────────────────────────


class TestEvidenceContractDirectives:
    def test_contract_carries_exceptions_with_the_duty(self) -> None:
        from app.data.graph_rag_prompts import (
            EVIDENCE_ANSWER_CONTRACT_WITH_COMPLETENESS as CONTRACT,
        )

        assert "exceptions" in CONTRACT.lower()
        assert "carve-outs" in CONTRACT.lower()
        assert "sub-points" in CONTRACT.lower()

    def test_contract_demands_bare_verdict_first(self) -> None:
        from app.data.graph_rag_prompts import (
            EVIDENCE_ANSWER_CONTRACT_WITH_COMPLETENESS as CONTRACT,
        )

        assert "verdict first" in CONTRACT.lower() or (
            "give the bare verdict" in CONTRACT.lower()
        )

    def test_base_contract_alone_lacks_completeness_block(self) -> None:
        """R403: the block is gated — the base contract must not absorb it."""
        from app.data.graph_rag_prompts import (
            EVIDENCE_ANSWER_CONTRACT,
            contract_completeness_directives_enabled,
        )

        if contract_completeness_directives_enabled():
            assert "carve-outs" not in EVIDENCE_ANSWER_CONTRACT.lower()

    def test_rendered_user_message_includes_directive(self) -> None:
        from app.data.graph_rag_prompts import (
            build_evidence_answer_user,
            evidence_contract_enabled,
        )

        assert evidence_contract_enabled() is True
        msg = build_evidence_answer_user("Is X high-risk?", "REF BLOCK")
        assert "carve-outs" in msg


# ── 5. tier_quota and prompt_budget_tier ──────────────────────────────────────


class TestPromptBudgetTier:
    """Pin the prompt_budget_tier classification — S/M/L."""

    def test_short_single_anchor_is_s(self) -> None:
        from app.data.graph_rag_prompts import prompt_budget_tier

        assert prompt_budget_tier("What does Article 6 say?") == "S"

    def test_duty_keyword_promotes_to_m(self) -> None:
        from app.data.graph_rag_prompts import prompt_budget_tier

        assert prompt_budget_tier("What must a provider do under Article 9?") == "M"

    def test_comparison_keyword_promotes_to_l(self) -> None:
        from app.data.graph_rag_prompts import prompt_budget_tier

        assert prompt_budget_tier("Compare Article 6 and Article 9.") == "L"

    def test_multiturn_promotes_to_l(self) -> None:
        from app.data.graph_rag_prompts import prompt_budget_tier

        assert prompt_budget_tier("Short question.", history_turn_count=2) == "L"

    def test_long_question_promotes_to_l(self) -> None:
        from app.data.graph_rag_prompts import prompt_budget_tier

        assert prompt_budget_tier("x " * 200) == "L"


class TestTierQuota:
    """Pin the tier_quota resolution — the R403 flexible-budget entrypoint.

    This class exists because the original tier_quota shipped with a broken
    signature (only ``hi`` and ``scale`` declared) while the body used five
    undeclared names. The call site's ``except Exception`` silently caught the
    TypeError, so the feature was 100% dead. These tests make a recurrence
    fail loudly.
    """

    def test_callable_with_full_signature(self) -> None:
        """tier_quota must accept the call site's keyword arguments."""
        from app.data.graph_rag_prompts import tier_quota

        result = tier_quota(
            "What does Article 6 say?",
            history_turn_count=1,
            env_name="REGENOLD_SEMANTIC_UNITS_TEST_NONEXISTENT",
            default=16,
            lo=1,
            hi=60,
            scale={"S": 8, "M": 16, "L": 24},
        )
        assert isinstance(result, int)

    def test_explicit_env_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data.graph_rag_prompts import tier_quota

        monkeypatch.setenv("_TIER_QUOTA_TEST_ENV", "42")
        result = tier_quota(
            "What does Article 6 say?",
            env_name="_TIER_QUOTA_TEST_ENV",
            default=16,
            lo=1,
            hi=60,
            scale={"S": 8, "M": 16, "L": 24},
        )
        assert result == 42

    def test_env_override_clamped_to_hi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data.graph_rag_prompts import tier_quota

        monkeypatch.setenv("_TIER_QUOTA_TEST_ENV", "999")
        result = tier_quota(
            "q",
            env_name="_TIER_QUOTA_TEST_ENV",
            default=16,
            lo=1,
            hi=60,
            scale={"S": 8, "M": 16, "L": 24},
        )
        assert result == 60

    def test_flex_on_scales_s_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data.graph_rag_prompts import tier_quota

        monkeypatch.delenv("_TIER_QUOTA_TEST_ENV", raising=False)
        monkeypatch.setenv("REGENOLD_PROMPT_BUDGET_FLEX", "1")
        result = tier_quota(
            "What does Article 6 say?",  # S-tier (short, single anchor)
            env_name="_TIER_QUOTA_TEST_ENV",
            default=16,
            lo=1,
            hi=60,
            scale={"S": 8, "M": 16, "L": 24},
        )
        assert result == 8

    def test_flex_off_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data.graph_rag_prompts import tier_quota

        monkeypatch.delenv("_TIER_QUOTA_TEST_ENV", raising=False)
        monkeypatch.setenv("REGENOLD_PROMPT_BUDGET_FLEX", "0")
        result = tier_quota(
            "What does Article 6 say?",  # would be S-tier, but flex is off
            env_name="_TIER_QUOTA_TEST_ENV",
            default=16,
            lo=1,
            hi=60,
            scale={"S": 8, "M": 16, "L": 24},
        )
        assert result == 16


# ── 6. cache key registration for R403 flags ─────────────────────────────────


class TestR403CacheKeyRegistration:
    """The two R403 flags live in ``app/data/`` (outside the R355 AST gate's
    scan of ``app/engines``), so they must be hand-registered. This test
    catches a regression that silently drops either flag from the key."""

    def _cache_key_env_list(self) -> tuple[str, ...]:
        """Extract the ``engine_flags`` env-var tuple from ``_engine_cache_key``
        source, but just call it with two different env states and compare."""
        return (
            "REGENOLD_CONTRACT_COMPLETENESS",
            "REGENOLD_PROMPT_BUDGET_FLEX",
        )

    def test_flags_flip_the_cache_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.routes.regenold import _engine_cache_key

        q = "What does Article 6 say?"
        # Arm A: both ON
        monkeypatch.setenv("REGENOLD_CONTRACT_COMPLETENESS", "1")
        monkeypatch.setenv("REGENOLD_PROMPT_BUDGET_FLEX", "1")
        key_a = _engine_cache_key(q, None)

        # Arm B: completeness OFF
        monkeypatch.setenv("REGENOLD_CONTRACT_COMPLETENESS", "0")
        key_b = _engine_cache_key(q, None)
        assert key_a != key_b, "REGENOLD_CONTRACT_COMPLETENESS must be in the cache key"

        # Arm C: flex OFF (restore completeness)
        monkeypatch.setenv("REGENOLD_CONTRACT_COMPLETENESS", "1")
        monkeypatch.setenv("REGENOLD_PROMPT_BUDGET_FLEX", "0")
        key_c = _engine_cache_key(q, None)
        assert key_a != key_c, "REGENOLD_PROMPT_BUDGET_FLEX must be in the cache key"


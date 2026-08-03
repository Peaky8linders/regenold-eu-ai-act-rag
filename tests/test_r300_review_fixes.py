"""R300 — regression tests for the deep-review fixes.

Two defects found reviewing the two untagged 2026-07-30 "truncation" commits
(`8eb34e4`, `757f0cb`) plus the R299 range:

1.  A hardcoded model-name rewrite buried in the wrapper transport layer with
    no env gate, no log line, and no mention in its commit message. It
    silently reverted R292's shipped Opus 5 Stage-2 AND made the
    `?include_reasoning=true` trace report a model that was never sent.
2.  The R299 completeness verifier emitted a supplement that conflated the
    sub-points of TWO different articles into one undifferentiated list,
    asserting points that the leading article does not have (Article 16 stops
    at (l); the blob implied an (m)) — a confidently-wrong legal claim, the
    worst defect class per CLAUDE.md hard rule #4. Its labels were also a
    keyword bag ("draw declaration conformity") rather than regulatory prose.
"""

from __future__ import annotations

import pytest

from app.engines.completeness_verifier import (
    _extract_subpoint_label,
    verify_and_enrich_enumerated_completeness,
)
from app.llm.openai_wrapper_provider import resolve_wrapper_model


# --------------------------------------------------------------------------
# 1. Wrapper model alias — env-gated, honest, non-Opus untouched
# --------------------------------------------------------------------------
class TestWrapperModelAlias:
    def test_default_sends_the_configured_model_verbatim(self, monkeypatch):
        """R308 — DEFAULT FLIPPED OFF. Operator directive: Stage-2 runs on Opus 5.

        Was ``test_default_preserves_pre_r300_behaviour``, which asserted the
        757f0cb rewrite still downgraded every Opus name to ``claude-opus-4-6``.
        R300 kept that default ON only because flipping it needed evidence.

        The evidence (measured live 2026-08-03, one probe each):
            claude-opus-5              -> HTTP 200, model echoed back
            definitely-not-a-model-xyz -> HTTP 500 "No response from Claude Code"
        A bogus name fails loudly, so the 200 is genuine acceptance. The
        wrapper's ``/v1/models`` omits opus-5 but that list is stale - the model
        string is passed through to the Claude Code CLI.

        So the alias was silently downgrading a model that works, on every
        request, while ``GraphRAGSettings.stage2_model`` had said
        ``claude-opus-5`` since R292.
        """
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_ALIAS", raising=False)
        for requested in (
            "claude-opus-5",
            "claude-opus-4-8",
            "claude-5-opus",
            "opus-5",
            "claude-opus-5.0",
        ):
            assert resolve_wrapper_model(requested) == requested

    def test_env_gate_on_restores_the_pre_r308_downgrade(self, monkeypatch):
        """`=1` is the one-env-var rollback if Opus 5 has to be backed out."""
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "1")
        assert resolve_wrapper_model("claude-opus-5") == "claude-opus-4-6"
        assert resolve_wrapper_model("claude-opus-4-8") == "claude-opus-4-6"

    @pytest.mark.parametrize(
        "model",
        [
            "claude-sonnet-5",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
        ],
    )
    def test_non_opus_models_are_never_rewritten(self, monkeypatch, model):
        """The alias must not touch the Groq / Sonnet / Haiku paths."""
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_ALIAS", raising=False)
        assert resolve_wrapper_model(model) == model

    def test_identity_and_empty_are_safe(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_ALIAS", raising=False)
        assert resolve_wrapper_model("claude-opus-4-6") == "claude-opus-4-6"
        assert resolve_wrapper_model("") == ""
        # R308 — whitespace still trimmed, but no longer downgraded.
        assert resolve_wrapper_model("  claude-opus-5  ") == "claude-opus-5"

    def test_complete_routes_through_the_gate_not_an_inline_literal(self):
        """`complete()` must call the resolver.

        The 757f0cb defect was an un-gated `if model in (...): model =
        "claude-opus-4-6"` inline in `complete()`. Pin that it is gone, so a
        future edit cannot silently re-introduce an ungated rewrite that the
        env switch and the reasoning trace would both be blind to.
        """
        import inspect

        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        src = inspect.getsource(_OpenAIWrapperProvider.complete)
        assert "_resolve_wrapper_model" in src or "resolve_wrapper_model" in src
        assert '"claude-opus-4-6"' not in src, (
            "hardcoded model literal back inside complete() — it must go "
            "through the env-gated, logged resolver"
        )


# --------------------------------------------------------------------------
# 2. Completeness verifier — per-article attribution + grammatical labels
# --------------------------------------------------------------------------
_Q = "List every obligation that Article 16 places on a provider of a high-risk AI system."

# The real production answer (uncached live probe, 2026-07-30) that cites BOTH
# Article 16 and Article 17 and therefore triggered the cross-article conflation.
_ANSWER_CITING_16_AND_17 = (
    "Article 16 requires providers of high-risk AI systems to fulfil all of the "
    "following obligations. They must ensure the system complies with the "
    "requirements set out in Chapter III, Section 2 and bears the provider's name "
    "or registered trade mark. They must put in place a quality management system "
    "(Article 17)."
)


class TestCompletenessVerifierAttribution:
    def test_supplement_attributes_points_to_their_own_article(self, monkeypatch):
        # R306 — the verifier now defaults OFF (it shipped inverted law on
        # ~2.6% of live answers). These tests exercise the R300 ATTRIBUTION
        # fix, which is still the correct behaviour WHEN the feature runs, so
        # they opt in explicitly rather than relying on the default.
        monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "1")
        out = verify_and_enrich_enumerated_completeness(_Q, _ANSWER_CITING_16_AND_17, None)
        assert out != _ANSWER_CITING_16_AND_17, "verifier should fire on this shape"
        # Each cited article names ITSELF before listing its points.
        assert "Article 16 also requires" in out
        assert "Article 17 also requires" in out
        # The pre-R300 undifferentiated blob form must be gone.
        assert "including points" not in out

    def test_article_16_points_never_claim_a_point_m(self, monkeypatch):
        """Article 16 has points (a)-(l). An (m) in its clause is a legal error."""
        # R306 — the verifier now defaults OFF (it shipped inverted law on
        # ~2.6% of live answers). These tests exercise the R300 ATTRIBUTION
        # fix, which is still the correct behaviour WHEN the feature runs, so
        # they opt in explicitly rather than relying on the default.
        monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "1")
        out = verify_and_enrich_enumerated_completeness(_Q, _ANSWER_CITING_16_AND_17, None)
        a16 = out.split("Article 16 also requires", 1)[1]
        a16_clause = a16.split("Article 17 also requires", 1)[0]
        assert "(m)" not in a16_clause, (
            "Article 16 has no point (m) — it stops at (l). An (m) here means "
            "Article 17's points leaked into Article 16's list."
        )

    def test_labels_are_prose_not_keyword_salad(self, monkeypatch):
        # R306 — the verifier now defaults OFF (it shipped inverted law on
        # ~2.6% of live answers). These tests exercise the R300 ATTRIBUTION
        # fix, which is still the correct behaviour WHEN the feature runs, so
        # they opt in explicitly rather than relying on the default.
        monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "1")
        out = verify_and_enrich_enumerated_completeness(_Q, _ANSWER_CITING_16_AND_17, None)
        # Pre-R300 output for these exact points.
        for salad in (
            "draw declaration conformity",
            "keep documentation referred",
            "comply registration referred",
            "take necessary corrective",
        ):
            assert salad not in out, f"keyword-salad label regressed: {salad!r}"

    def test_env_gate_off_is_a_strict_noop(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "0")
        out = verify_and_enrich_enumerated_completeness(_Q, _ANSWER_CITING_16_AND_17, None)
        assert out == _ANSWER_CITING_16_AND_17

    def test_non_enumerated_question_is_a_noop(self, monkeypatch):
        # R306 — the verifier now defaults OFF (it shipped inverted law on
        # ~2.6% of live answers). These tests exercise the R300 ATTRIBUTION
        # fix, which is still the correct behaviour WHEN the feature runs, so
        # they opt in explicitly rather than relying on the default.
        monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "1")
        ans = "Article 16 requires a quality management system."
        assert verify_and_enrich_enumerated_completeness(
            "Is a chatbot high-risk?", ans, None
        ) == ans


class TestSubpointLabelQuality:
    def test_verbatim_opening_clause_is_preserved(self):
        text = "draw up the EU declaration of conformity in accordance with Article 47"
        assert _extract_subpoint_label(text).startswith("draw up the EU declaration")

    def test_label_does_not_end_on_a_dangling_function_word(self):
        long_text = (
            "take the necessary corrective actions and provide information as "
            "required by Article 20 concerning the system placed on the market"
        )
        label = _extract_subpoint_label(long_text)
        assert not label.split()[-1].lower().rstrip(".,;:") in {
            "as",
            "of",
            "the",
            "and",
            "to",
            "in",
            "by",
            "with",
        }, f"dangling function word at end of {label!r}"

    def test_short_subpoint_returned_whole(self):
        assert _extract_subpoint_label("resource management") == "resource management"

    def test_early_comma_does_not_truncate_to_a_stub(self):
        """Article 17(h) opens 'the setting-up, implementation and maintenance…'.

        An unguarded first-comma cut would emit the useless 'the setting-up'.
        """
        text = (
            "the setting-up, implementation and maintenance of a post-market "
            "monitoring system"
        )
        label = _extract_subpoint_label(text)
        assert label != "the setting-up"
        assert "implementation" in label

    def test_empty_input_is_safe(self):
        assert _extract_subpoint_label("") == "requirement"
        assert _extract_subpoint_label("   ") == "requirement"


# --------------------------------------------------------------------------
# 3. R299 partition must not drop the supporting-context sections
# --------------------------------------------------------------------------
_SUPP_SECTIONS = (
    "COMPLIANCE GAPS",
    "DIMENSION DETAILS",
    "CROSS-REGULATORY BRIDGING",
    "SYNTHESIZED MULTI-HOP",
    "LEGAL AST",
)


def _ctx_with_all_sections():
    from app.engines.graph_rag import GraphContext

    ctx = GraphContext()
    ctx.obligations = [
        {"id": "o1", "text": "Provider duties.", "article": "Art. 16"},
        {"id": "o2", "text": "Prohibited practices.", "article": "Art. 5"},
    ]
    ctx.article_info = []
    ctx.gaps = [{"obligation_id": "g1", "text": "No FRIA on file.", "severity": "high"}]
    ctx.dimension_info = [
        {"dim_name": "governance", "question_count": 3, "obligation_count": 2}
    ]
    ctx.bridging_context = ["MDR Article 10 interacts with the Annex I route."]
    ctx.synthesis_memory = "Multi-hop: Art 6 -> Art 43 -> Annex VII."
    ctx.ast_evaluations = ["Art 6(3)(a) evaluated FALSE for this fact pattern."]
    return ctx


class TestPartitionKeepsSupportingContext:
    _Q = "Is our system high-risk and what must we do?"

    @pytest.mark.parametrize("gate", ["0", "1"])
    def test_all_sections_render_under_both_gates(self, monkeypatch, gate):
        """R300 — partition ON dropped ALL FIVE sections (852 -> 330 chars).

        The costliest was CROSS-REGULATORY BRIDGING (the GDPR / MDR context
        the cross-framework and MedTech answers depend on).
        """
        from app.engines.graph_rag import _build_context_references_block as build

        monkeypatch.setenv("REGENOLD_REF_PARTITION", gate)
        block = build(_ctx_with_all_sections(), question=self._Q)
        for section in _SUPP_SECTIONS:
            assert section in block, f"{section} missing with REF_PARTITION={gate}"

    def test_partition_still_labels_operative_and_background(self, monkeypatch):
        """The R299 citation discipline must survive the restore."""
        from app.engines.graph_rag import _build_context_references_block as build

        monkeypatch.setenv("REGENOLD_REF_PARTITION", "1")
        block = build(_ctx_with_all_sections(), question=self._Q)
        assert "OPERATIVE PROVISIONS" in block
        assert "BACKGROUND CONTEXT" in block

    @pytest.mark.parametrize("gate", ["0", "1"])
    def test_empty_context_message_unchanged(self, monkeypatch, gate):
        from app.engines.graph_rag import GraphContext
        from app.engines.graph_rag import _build_context_references_block as build

        monkeypatch.setenv("REGENOLD_REF_PARTITION", gate)
        empty = GraphContext()
        empty.obligations = []
        empty.article_info = []
        assert build(empty, question=self._Q) == "No EU AI Act references match this query."


# --------------------------------------------------------------------------
# 4. Cache-key doctrine (R30/R56/R79/R263.2)
# --------------------------------------------------------------------------
class TestEngineCacheKeyCoversR299Gates:
    @pytest.mark.parametrize(
        "flag",
        [
            "REGENOLD_REF_PARTITION",
            "REGENOLD_COMPLETENESS_VERIFIER",
            "REGENOLD_WRAPPER_MODEL_ALIAS",
        ],
    )
    def test_flag_changes_the_cache_key(self, monkeypatch, flag):
        """Omission silently cross-contaminates an in-process two-arm A/B."""
        from app.routes.regenold import _engine_cache_key

        q = "What are the obligations of providers of high-risk AI systems?"
        monkeypatch.setenv(flag, "1")
        on = _engine_cache_key(q, "")
        monkeypatch.setenv(flag, "0")
        off = _engine_cache_key(q, "")
        assert on != off, f"{flag} flips the engine answer but not the cache key"


# --------------------------------------------------------------------------
# 5. Nested roman sub-points must not be listed as top-level obligations
# --------------------------------------------------------------------------
class TestNestedRomanSubpoints:
    """`provision_text._subpoints` returns a FLAT dict.

    For Article 5(1) that means 5(1)(h)'s law-enforcement carve-outs
    (i)/(ii)/(iii) land beside the top-level letters (a)-(h). Listing them as
    missing "requirements" states the regulation backwards -- they are the
    conditions under which real-time remote biometric identification is
    PERMITTED. Hard rule #4: a confidently-wrong legal claim is the worst
    defect class.
    """

    def test_article_5_nested_romans_are_dropped(self):
        from app.data.provision_text import _paragraphs, _subpoints, article_body
        from app.engines.completeness_verifier import _drop_nested_romans

        paras = _paragraphs(article_body("Article 5") or "")
        subs = _subpoints(list(paras.values())[0])
        assert {"ii", "iii"} <= set(subs), "fixture drifted: expected flattened romans"

        kept = _drop_nested_romans(subs)
        assert not ({"i", "ii", "iii"} & set(kept)), (
            "Article 5(1)(h)(i)-(iii) are permissive exceptions, not obligations"
        )
        assert set(kept) == set("abcdefgh")

    def test_article_16_genuine_letter_i_is_preserved(self):
        """(i) is ambiguous. Article 16 runs (a)-(l); its (i) is a real point."""
        from app.data.provision_text import _subpoints, article_body
        from app.engines.completeness_verifier import _drop_nested_romans

        subs = _subpoints(article_body("Article 16") or "")
        kept = _drop_nested_romans(subs)
        assert "i" in kept, "dropped a genuine lettered obligation"
        assert set(kept) == set(subs), "no nested block here -> nothing to drop"

    def test_noop_on_empty_and_letters_only(self):
        from app.engines.completeness_verifier import _drop_nested_romans

        assert _drop_nested_romans({}) == {}
        letters = {"a": "x", "b": "y", "i": "z"}
        assert _drop_nested_romans(letters) == letters

    def test_article_5_answer_never_lists_the_carve_outs_as_requirements(
        self, monkeypatch
    ):
        # R306 — the verifier now defaults OFF (it shipped inverted law on
        # ~2.6% of live answers). These tests exercise the R300 ATTRIBUTION
        # fix, which is still the correct behaviour WHEN the feature runs, so
        # they opt in explicitly rather than relying on the default.
        monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "1")
        answer = (
            "Article 5 prohibits eight practices outright, including subliminal "
            "manipulation and social scoring."
        )
        out = verify_and_enrich_enumerated_completeness(
            "What practices are prohibited under Article 5?", answer, None
        )
        for carve_out in (
            "targeted search for specific victims",
            "imminent threat to the life",
            "localisation or identification of a person suspected",
        ):
            assert carve_out not in out, (
                f"5(1)(h) carve-out shipped as a requirement: {carve_out!r}"
            )

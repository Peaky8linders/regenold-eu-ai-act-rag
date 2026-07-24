"""R288 — verbatim provision text in the Stage-2 grounding block.

Pins the contract established by the measurement that motivated it: on the real
110-row regenold easy batch, 215/322 (67%) of actually-cited refs had NO
paragraph-level text in the Stage-2 references block, while prompt rule 5b
instructs the model to "use the EXACT terminology found in the retrieved
articles". These tests lock in that the fix is (a) default-OFF, (b) strictly
additive, (c) scoped to provisions already in context, and (d) fail-soft.
"""
from __future__ import annotations

import pytest

from app.engines import graph_rag as G


def _ctx(**kw):
    """Minimal GraphContext with the fields the block renders."""
    c = G.GraphContext()
    c.obligations = kw.pop("obligations", [
        {"id": "o1", "text": "stub prose for Article 13", "article": "Art. 13"},
    ])
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestDefaultOff:
    def test_gate_defaults_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_GROUNDING_TEXT", raising=False)
        assert G._grounding_text_enabled() is False

    def test_block_unchanged_when_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_GROUNDING_TEXT", raising=False)
        ctx = _ctx(question="What does Article 13 require?")
        block = G._build_context_references_block(ctx)
        assert "VERBATIM PROVISION TEXT" not in block

    @pytest.mark.parametrize("val", ["1", "true", "YES", "on"])
    def test_truthy_values_enable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", val)
        assert G._grounding_text_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_falsy_values_disable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", val)
        assert G._grounding_text_enabled() is False


class TestAdditiveAndScoped:
    def test_on_is_strictly_additive(self, monkeypatch):
        ctx = _ctx(question="What does Article 13 require?")
        monkeypatch.delenv("REGENOLD_GROUNDING_TEXT", raising=False)
        off = G._build_context_references_block(ctx)
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        on = G._build_context_references_block(ctx)
        # The gate may only APPEND — never rewrite what was already there.
        assert on.startswith(off)

    def test_renders_verbatim_text_for_in_context_ref(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        ctx = _ctx(question="What does Article 13 require?")
        block = G._build_context_references_block(ctx)
        assert "VERBATIM PROVISION TEXT" in block
        assert "[Art. 13]" in block
        # Official Art. 13(1) wording, not our paraphrase stub.
        assert "sufficiently transparent" in block

    def test_only_in_context_refs_are_rendered(self, monkeypatch):
        """The whole point: verbatim text for what we CITE, not for anything else."""
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        ctx = _ctx(question="anything")
        rendered = "\n".join(G._render_grounding_text(ctx))
        assert "[Art. 13]" in rendered
        for other in ("[Art. 79]", "[Art. 80]", "[Art. 99]"):
            assert other not in rendered

    def test_ref_cap_is_respected(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        ctx = _ctx(obligations=[
            {"id": f"o{i}", "text": "s", "article": a}
            for i, a in enumerate(["Art. 13", "Art. 26", "Art. 11", "Art. 9", "Art. 10"])
        ], question="q")
        rendered = "\n".join(G._render_grounding_text(ctx))
        n = sum(rendered.count(f"[{a}]") for a in
                ("Art. 13", "Art. 26", "Art. 11", "Art. 9", "Art. 10"))
        assert n <= G._GROUNDING_MAX_REFS

    def test_labelled_as_non_citable_supporting_context(self, monkeypatch):
        """Must not invite citations beyond the reference list."""
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        rendered = "\n".join(G._render_grounding_text(_ctx(question="q")))
        assert "supporting context" in rendered
        assert "do NOT cite anything not already listed above" in rendered


class TestFailSoft:
    def test_empty_context_does_not_raise(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        assert G._render_grounding_text(G.GraphContext()) == []

    def test_unresolvable_ref_is_skipped_not_raised(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        ctx = _ctx(obligations=[{"id": "x", "text": "s", "article": "Art. 9999"}],
                   question="q")
        assert "Art. 9999" not in "\n".join(G._render_grounding_text(ctx))

    def test_block_survives_a_raising_renderer(self, monkeypatch):
        """A grounding failure must never break the block Stage-2 depends on."""
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        monkeypatch.setattr(
            G, "_render_grounding_text",
            lambda _c: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        block = G._build_context_references_block(_ctx(question="q"))
        assert "stub prose for Article 13" in block


class TestBudget:
    def test_env_override_is_clamped(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GROUNDING_REF_CHARS", "999999")
        assert G._grounding_ref_budget() <= 4000
        monkeypatch.setenv("REGENOLD_GROUNDING_REF_CHARS", "1")
        assert G._grounding_ref_budget() >= 200

    def test_garbage_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GROUNDING_REF_CHARS", "not-a-number")
        assert G._grounding_ref_budget() == G._GROUNDING_REF_CHARS


class TestQuestionStash:
    def test_populate_stashes_question_for_parity(self):
        """Both block call sites read context.question, so it must be set."""
        ctx = G.GraphContext()
        G._populate_semantic_statements(ctx, "What does Article 13 require?")
        assert ctx.question == "What does Article 13 require?"

    def test_question_defaults_empty(self):
        assert G.GraphContext().question == ""


class TestCacheKey:
    def test_flags_are_in_the_engine_cache_key(self, monkeypatch):
        """R30/R56/R79/R263.2 — a flag that flips the answer must key the cache,
        or an in-process OFF<->ON A/B serves the OFF arm's cached output."""
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "0")
        a = R._engine_cache_key("q", None)
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        b = R._engine_cache_key("q", None)
        assert a != b

    def test_ref_char_budget_is_in_the_engine_cache_key(self, monkeypatch):
        """R288.1 — the budget sweep the R288 checkpoint prescribes (300/500/800)
        holds REGENOLD_GROUNDING_TEXT=1 on BOTH arms and varies only this value.
        While it was absent from the key both arms hashed identically, so
        easyhard_ab (which mutates os.environ in-process for both arms) served
        arm A's cached engine output to arm B and every sweep read "no effect".
        """
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        monkeypatch.setenv("REGENOLD_GROUNDING_REF_CHARS", "500")
        a = R._engine_cache_key("q", None)
        monkeypatch.setenv("REGENOLD_GROUNDING_REF_CHARS", "1200")
        b = R._engine_cache_key("q", None)
        assert a != b, "budget sweep arms collide in the cache — R263.2"


class TestGuardAllowlistNotWidened:
    """R288.1 — the R113 miner must not treat the regulation's own
    cross-references as provisions we supplied.

    ``_mine_refs_from_text`` feeds the drift guard's grounding set: "what the
    polish is allowed to cite". Verbatim Act text names other provisions
    constantly (the bodies of Arts. 9/11/13 name Art. 60, Art. 72 and Annex IV),
    so mining the rendered grounding section turns the allowlist into a superset
    of what was retrieved — while the block itself instructs the model to "do
    NOT cite anything not already listed above".
    """

    @staticmethod
    def _ctx3():
        return _ctx(
            obligations=[
                {"id": "o1", "text": "stub for 13", "article": "Art. 13"},
                {"id": "o2", "text": "stub for 11", "article": "Art. 11"},
                {"id": "o3", "text": "stub for 9", "article": "Art. 9"},
            ],
            question="What does Article 13 require for transparency?",
        )

    def test_grounding_can_be_excluded_from_the_block(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        ctx = self._ctx3()
        assert "VERBATIM PROVISION TEXT" in G._build_context_references_block(ctx)
        assert "VERBATIM PROVISION TEXT" not in G._build_context_references_block(
            ctx, include_grounding=False
        )

    def test_guard_set_is_identical_gate_on_and_off(self, monkeypatch):
        """The point: turning R288 on must not change what may be cited.

        Calls the REAL guard entry point, ``_extract_context_grounded_refs``.
        An earlier cut of this test called ``_build_context_references_block``
        with ``include_grounding=False`` directly and therefore asserted only
        that the mechanism EXISTS — reverting the call site inside the guard
        left it green. Exercising the guard itself is what makes it bite.
        """
        ctx = self._ctx3()
        monkeypatch.delenv("REGENOLD_GROUNDING_TEXT", raising=False)
        off = G._extract_context_grounded_refs(ctx)
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        on = G._extract_context_grounded_refs(ctx)
        assert on == off, (
            f"R288 widened the citation allowlist: {sorted(on - off)} became "
            "citable purely because the verbatim text names them"
        )

    def test_verbatim_text_would_otherwise_leak_extra_refs(self, monkeypatch):
        """Positive control — proves the test above is load-bearing, not vacuous.

        If this stops finding extra refs, the guard test passes for the wrong
        reason (e.g. the provision corpus stopped resolving) and the regression
        it protects against would go unnoticed.
        """
        monkeypatch.setenv("REGENOLD_GROUNDING_TEXT", "1")
        ctx = self._ctx3()
        clean = G._mine_refs_from_text(
            G._build_context_references_block(ctx, include_grounding=False)
        )
        leaked = G._mine_refs_from_text(
            G._build_context_references_block(ctx, include_grounding=True)
        )
        assert leaked - clean, "verbatim text no longer introduces cross-refs"


class TestLogicRagQuestionParity:
    def test_execute_logic_rag_returns_a_context_carrying_the_question(
        self, monkeypatch
    ):
        """R288.1 — the context LogicRAG RETURNS is what Stage-2 and the R113
        guard render, so it must carry the question or R288's question-relevant
        paragraph selection silently degrades to the leading-paragraph fallback.

        Stubs the two LLM-dependent steps (DAG decomposition and retrieval) so
        this stays a pure unit test; a single-rank DAG short-circuits the
        pruning call, which is the only other LLM hop.
        """
        from app.engines import logic_rag as L

        monkeypatch.setattr(
            L, "_decompose_to_dag", lambda q, deadline=None: [
                {"id": "n1", "query": q, "deps": []}
            ]
        )
        monkeypatch.setattr(
            L, "_topological_sort", lambda dag: [[dag[0]]]
        )

        def _fake_retrieve(parsed, risk_level=None, answers=None):
            c = G.GraphContext()
            c.obligations = [
                {"id": "o1", "text": "stub", "article": "Art. 13"}
            ]
            return c

        monkeypatch.setattr(L, "_retrieve_from_graph", _fake_retrieve)

        out = L.execute_logic_rag("What does Article 13 require?")
        assert out is not None
        assert out.question, (
            "LogicRAG returned a question-less context — R288 verbatim "
            "selection falls back to the leading paragraph for every answer"
        )
        assert "Article 13" in out.question

    def test_merge_contexts_still_does_not_carry_question(self):
        """R288.1 — ``execute_logic_rag`` returns a BARE GraphContext that
        ``_merge_contexts`` never gives a question, so R288's question-relevant
        selection silently degraded to the leading-paragraph fallback whenever
        REGENOLD_LOGIC_RAG=1. Pin that the merge still does not carry it, so the
        explicit assignment in ``execute_logic_rag`` stays necessary.
        """
        from app.engines.logic_rag import _merge_contexts

        base = G.GraphContext()
        new = G.GraphContext()
        new.question = "What does Article 13 require?"
        _merge_contexts(base, new)
        assert base.question == "", (
            "_merge_contexts now carries question — reconcile with the explicit "
            "assignment in execute_logic_rag rather than keeping both silently"
        )

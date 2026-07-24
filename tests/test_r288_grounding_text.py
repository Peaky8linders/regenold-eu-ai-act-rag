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

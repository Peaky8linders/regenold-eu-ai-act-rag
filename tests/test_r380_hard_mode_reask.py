"""R380 — hard-mode turn handling: the anchor-less re-ask tail and the
de-noiser rewrite budget.

Measured on the 110 official questions with the evaluator's VERBATIM pushback
template (``evals.regenold.official_batch.PUSHBACK_TEMPLATE``): the R305
re-ask focus fired on 100/110; every miss was an anchor-less question. Those
10 went through the de-noiser, which truncates at 100 tokens on the reasoning
model now behind the Groq slot, into the 40-turn concatenation carrying the
disputed answer and the pushback text. Both fixes are env-reversible and keyed
in ``_engine_cache_key`` so a paired in-process A/B can isolate them.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")

# The evaluator's real template shape: marker on its own line, question after.
_PUSHBACK = (
    "I don't think this is correct. Perhaps your answer contains hallucinations.\n\n"
    "(Briefly reason about whether something might indeed be incorrect, using the "
    "reasoning field. Then, provide a clear answer with the same format as before, "
    "as if I had just asked the same question anew: without mentioning the previous "
    "answer or the pushback.)\n\nLet's try again:\n{question}"
)
_ANCHORLESS_Q = (
    "Who is entitled to lodge a complaint about an infringement, and to which "
    "authority must the complaint be submitted?"
)
_ANCHORED_Q = "What must a provider of a high-risk AI system supply in the instructions for use?"


class TestAnchorlessReaskTail:
    def test_anchorless_official_question_is_reasked_as_itself(self, monkeypatch):
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_REASK_ANCHORLESS", "1")
        assert R._extract_reask_tail(_PUSHBACK.format(question=_ANCHORLESS_Q)) == _ANCHORLESS_Q

    def test_off_restores_the_r305_anchor_gate(self, monkeypatch):
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_REASK_ANCHORLESS", "0")
        assert R._extract_reask_tail(_PUSHBACK.format(question=_ANCHORLESS_Q)) is None
        # An anchored question still fires either way.
        assert R._extract_reask_tail(_PUSHBACK.format(question=_ANCHORED_Q)) == _ANCHORED_Q

    @pytest.mark.parametrize(
        "tail",
        [
            "what about deployers?",                       # leading coreference
            "does it also apply to the same system?",      # coreference marker
            "and the fines?",                              # too short
        ],
    )
    def test_elliptical_reask_keeps_its_history(self, monkeypatch, tail):
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_REASK_ANCHORLESS", "1")
        assert R._extract_reask_tail(_PUSHBACK.format(question=tail)) is None

    def test_whole_official_batch_fires_when_the_snapshot_is_present(self, monkeypatch):
        """110/110 with the fix (was 100/110). Skipped when the gitignored
        official snapshot is absent from the checkout."""
        pytest.importorskip("evals.regenold.july7_difficulty")
        from evals.regenold.official_batch import PUSHBACK_TEMPLATE, load_official_batch
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_REASK_ANCHORLESS", "1")
        rows = load_official_batch()
        fired = sum(
            1 for r in rows
            if R._extract_reask_tail(PUSHBACK_TEMPLATE.format(question=r.question)) == r.question
        )
        assert fired == len(rows), (fired, len(rows))

    def test_build_question_from_history_drops_history_on_the_reask(self, monkeypatch):
        """End to end through the history flattener: the pushback turn becomes
        the bare question with self_contained_focus set."""
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_REASK_ANCHORLESS", "1")

        class _M:
            def __init__(self, role, content):
                self.role, self.content = role, content

        msgs = [
            _M("user", "What is Annex III about?"),
            _M("assistant", "Annex III lists the high-risk areas under Article 6(2)."),
            _M("user", _ANCHORLESS_Q),
            _M("assistant", "Article 85 lets any natural or legal person lodge a complaint."),
            _M("user", _PUSHBACK.format(question=_ANCHORLESS_Q)),
        ]
        res = R._build_question_from_history(msgs)
        assert res[0] == _ANCHORLESS_Q
        assert "Annex III" not in res[0]
        assert res.resolved_question == _ANCHORLESS_Q
        assert res.self_contained_focus is True


class TestDenoiserBudget:
    def test_default_is_400_and_env_overrides_with_clamp(self, monkeypatch):
        from app.routes import regenold as R

        monkeypatch.delenv("REGENOLD_DENOISER_MAX_TOKENS", raising=False)
        assert R._denoiser_max_tokens() == 400
        monkeypatch.setenv("REGENOLD_DENOISER_MAX_TOKENS", "800")
        assert R._denoiser_max_tokens() == 800
        monkeypatch.setenv("REGENOLD_DENOISER_MAX_TOKENS", "5")
        assert R._denoiser_max_tokens() == 100
        monkeypatch.setenv("REGENOLD_DENOISER_MAX_TOKENS", "junk")
        assert R._denoiser_max_tokens() == 400


class TestCacheKey:
    @pytest.mark.parametrize(
        "flag, off, on",
        [("REGENOLD_REASK_ANCHORLESS", "0", "1"), ("REGENOLD_DENOISER_MAX_TOKENS", "100", "400")],
    )
    def test_each_flag_changes_the_engine_cache_key(self, monkeypatch, flag, off, on):
        from app.routes import regenold as R

        monkeypatch.setenv(flag, off)
        k0 = R._engine_cache_key(_ANCHORED_Q, None, history_turn_count=2)
        monkeypatch.setenv(flag, on)
        k1 = R._engine_cache_key(_ANCHORED_Q, None, history_turn_count=2)
        assert k0 != k1, flag


class TestSelfContainedSkip:
    """R380 — a self-contained live turn is returned verbatim BEFORE any
    provider is dialled; offline (no provider) the path is unchanged."""

    @staticmethod
    def _wire_stub(monkeypatch, *, calls: list):
        import app.llm.openai_wrapper_provider as owp

        class _Stub:
            def complete(self, req):  # noqa: D401 — provider stub
                calls.append(req)
                raise RuntimeError("provider must not be dialled for a self-contained turn")

        monkeypatch.setattr(owp, "is_groq_intent_provider_enabled", lambda: False)
        monkeypatch.setattr(owp, "is_gemini_provider_enabled", lambda: False)
        monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: False)
        monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
        monkeypatch.setattr(owp, "get_openai_wrapper_provider", lambda: _Stub())

    def test_self_contained_turn_skips_the_rewrite(self, monkeypatch):
        from app.routes import regenold as R

        calls: list = []
        self._wire_stub(monkeypatch, calls=calls)
        monkeypatch.setenv("REGENOLD_DENOISE_SELF_CONTAINED_SKIP", "1")
        monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
        hist = [type("M", (), {"role": "user", "content": "What is Annex III about?"})(),
                type("M", (), {"role": "assistant", "content": "It lists the high-risk areas."})()]
        out = R._rewrite_multiturn_query(_ANCHORED_Q, hist)
        assert out == _ANCHORED_Q
        assert calls == [], "the provider was dialled for a self-contained turn"

    def test_off_dials_the_provider(self, monkeypatch):
        from app.routes import regenold as R

        calls: list = []
        self._wire_stub(monkeypatch, calls=calls)
        monkeypatch.setenv("REGENOLD_DENOISE_SELF_CONTAINED_SKIP", "0")
        monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
        hist = [type("M", (), {"role": "user", "content": "What is Annex III about?"})()]
        R._rewrite_multiturn_query(_ANCHORED_Q, hist)
        assert len(calls) == 1, "with the skip OFF the rewrite must still be attempted"

    def test_coreferent_follow_up_still_dials_the_provider(self, monkeypatch):
        from app.routes import regenold as R

        calls: list = []
        self._wire_stub(monkeypatch, calls=calls)
        monkeypatch.setenv("REGENOLD_DENOISE_SELF_CONTAINED_SKIP", "1")
        monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
        hist = [type("M", (), {"role": "user", "content": "What does Article 13 require?"})()]
        R._rewrite_multiturn_query("what about deployers?", hist)
        assert len(calls) == 1

    def test_offline_no_provider_is_unchanged(self, monkeypatch):
        """No provider configured => None, exactly as before R380 (the bench)."""
        import app.llm.openai_wrapper_provider as owp
        from app.routes import regenold as R

        for name in ("is_groq_intent_provider_enabled", "is_gemini_provider_enabled",
                     "is_mistral_provider_enabled", "is_openai_wrapper_enabled"):
            monkeypatch.setattr(owp, name, lambda: False)
        monkeypatch.setenv("REGENOLD_DENOISE_SELF_CONTAINED_SKIP", "1")
        monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
        hist = [type("M", (), {"role": "user", "content": "What is Annex III about?"})()]
        assert R._rewrite_multiturn_query(_ANCHORED_Q, hist) is None

    def test_flag_changes_the_engine_cache_key(self, monkeypatch):
        from app.routes import regenold as R

        monkeypatch.setenv("REGENOLD_DENOISE_SELF_CONTAINED_SKIP", "0")
        k0 = R._engine_cache_key(_ANCHORED_Q, None, history_turn_count=2)
        monkeypatch.setenv("REGENOLD_DENOISE_SELF_CONTAINED_SKIP", "1")
        k1 = R._engine_cache_key(_ANCHORED_Q, None, history_turn_count=2)
        assert k0 != k1


class TestConjunctionLedFollowUpKeepsHistory:
    @pytest.mark.parametrize(
        "turn",
        [
            "And the reporting duties for those providers?",
            "But we built it, so are we provider or deployer? We're both.",
            "So does the conformity assessment apply to our medical device too?",
        ],
    )
    def test_conjunction_led_turn_is_not_self_contained(self, turn):
        from app.routes import regenold as R

        assert R._live_turn_is_self_contained(turn) is False

    def test_official_questions_are_unaffected(self):
        pytest.importorskip("evals.regenold.july7_difficulty")
        from evals.regenold.official_batch import load_official_batch
        from app.routes import regenold as R

        rows = load_official_batch()
        assert sum(1 for r in rows if R._live_turn_is_self_contained(r.question)) == 100

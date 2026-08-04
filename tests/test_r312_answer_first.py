"""R312 — answer-first vs refine-the-draft Stage-2 framing.

WHY THIS EXISTS (measured, not theorised)

R280 ran the only valid frontier comparison this project has: 64 paired rows,
same questions, same scorer, our RAG vs a raw frontier model with **no
retrieval and no web search**. The decomposition:

    Ref Correctness Strict : ours 55.1  frontier 46.8   (per-row 35 / 25)
    Keyword recall (answer): ours 78.6  frontier 88.6   (per-row  4 / 27)

A handicapped frontier model out-answers us 27 rows to 4. Retrieval is not the
gap; answer composition is. One concrete mechanism is that on the majority
Stage-2 path we hand the model our DETERMINISTIC KB-stub draft and ask it to
*refine* rather than to *answer* — and R302 measured un-curated deterministic
rows at **0/5 answer pass**, so the anchor is a draft that fails outright.

``REGENOLD_ANSWER_FIRST`` demotes that draft to background material and asks
for an answer. Everything else in the Stage-2 user message is byte-identical,
so an A/B isolates the anchor.

SHIPS DEFAULT **OFF**. The n=40 A/B was directionally positive on every axis
and significant on none (kw_recall +0.033, B wins 5 / A wins 1 / tie 34,
p=0.219; ref_conc +0.028; tone 1.0 held; latency +4.1 s). Per the R270 /
R142.1 discipline this project does not flip a default on noise-level
evidence.
"""

from __future__ import annotations

import os

import pytest

from app.routes.regenold import _engine_cache_key


class TestAnswerFirstDefault:
    def test_default_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default OFF => production keeps the R280-era refine framing until an
        A/B says otherwise."""
        monkeypatch.delenv("REGENOLD_ANSWER_FIRST", raising=False)
        assert os.getenv("REGENOLD_ANSWER_FIRST", "0").strip().lower() not in (
            "1",
            "true",
            "yes",
            "on",
        )

    @pytest.mark.parametrize("val,expected", [
        ("1", True), ("true", True), ("YES", True), ("on", True),
        ("0", False), ("false", False), ("", False), ("no", False),
    ])
    def test_env_parse(self, monkeypatch: pytest.MonkeyPatch, val: str, expected: bool) -> None:
        monkeypatch.setenv("REGENOLD_ANSWER_FIRST", val)
        got = os.getenv("REGENOLD_ANSWER_FIRST", "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        assert got is expected


class TestAnswerFirstCacheKey:
    """R263.2 — the flag flips GraphRAGResponse.answer, so it MUST be in the
    engine cache key. Without it the in-process two-arm A/B this flag exists
    FOR serves arm A's cached response to arm B and measures nothing."""

    def test_flag_changes_the_cache_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        q = "What are the obligations of importers of high-risk AI systems?"
        monkeypatch.setenv("REGENOLD_ANSWER_FIRST", "0")
        a = _engine_cache_key(q, None)
        monkeypatch.setenv("REGENOLD_ANSWER_FIRST", "1")
        b = _engine_cache_key(q, None)
        assert a != b, (
            "REGENOLD_ANSWER_FIRST must be in _engine_cache_key or a two-arm "
            "A/B cross-contaminates (R30/R56/R79/R263.2)"
        )

    def test_cache_key_is_stable_for_a_fixed_arm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        q = "What are the obligations of importers of high-risk AI systems?"
        monkeypatch.setenv("REGENOLD_ANSWER_FIRST", "1")
        assert _engine_cache_key(q, None) == _engine_cache_key(q, None)


class TestStage2FramingText:
    """Pin the two framings so a future edit cannot silently collapse the A/B
    into a no-op (the R256 silently-inert trap, and the R277 lesson: an arm
    that differs only on a channel the wrapper drops measures nothing)."""

    @staticmethod
    def _impl_source() -> str:
        import app.engines._graph_rag_impl as impl

        with open(impl.__file__, encoding="utf-8") as fh:
            return fh.read()

    def test_both_framings_are_present(self) -> None:
        src = self._impl_source()
        assert "KNOWLEDGE GRAPH ANSWER (draft)" in src, "baseline refine framing"
        assert "RETRIEVED BACKGROUND SUMMARY" in src, "R312 answer-first framing"

    def test_answer_first_does_not_ask_for_an_edit(self) -> None:
        """The whole point: the branch must ask for an ANSWER, not a refinement
        of our draft."""
        src = self._impl_source()
        i = src.find("RETRIEVED BACKGROUND SUMMARY")
        assert i != -1
        # bound the slice at the `else:` so it cannot spill into the baseline
        # branch (which legitimately still contains the refine wording)
        end = src.find("            else:", i)
        assert end != -1
        block = src[i:end]
        assert "Answer the QUESTION above directly" in block
        assert "NOT a draft to edit" in block
        assert "Refine the knowledge-graph draft" not in block

    def test_framing_lives_on_the_user_channel(self) -> None:
        """R308: the wrapper drops the SYSTEM slot 100% (re-verified on
        claude-opus-5 this round: the system-slot output was byte-identical to
        the no-instruction control, the user-slot output obeyed). A framing
        change placed in the system prompt would reach the model on zero
        requests -- which is exactly why R277's minimal-composer A/B, which
        swapped 51,110 chars for 3,181 chars OF THAT SYSTEM PROMPT, returned
        90% ties: both arms were identical at the model."""
        src = self._impl_source()
        i = src.find("RETRIEVED BACKGROUND SUMMARY")
        # walk back to the nearest assignment and assert it targets user_message
        head = src[max(0, i - 400) : i]
        assert "user_message +=" in head, (
            "the answer-first framing must be appended to the Stage-2 USER "
            "message; the system slot is not delivered"
        )

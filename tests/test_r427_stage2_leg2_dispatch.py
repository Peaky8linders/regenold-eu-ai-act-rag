"""R427 / R426 T1 — the ONE Stage-2 leg-2 dispatch.

``app/llm/stage2.py`` collapses the two copies of the leg-2 (Bedrock) verdict
into one function returning one outcome type. The move is declared behaviour
preserving, so these tests pin two separate things:

* **the shipped semantics** of each preset (a pure move still has to keep the
  behaviour it moved), and
* **the wiring** — that the engine really speaks the shared policy at both call
  sites, since a lever that reads plausibly and calls nothing is this repo's
  most-repeated mistake.

The OLD-vs-NEW equivalence over recorded draws is carried by
``docs/measurements/r427/t1_leg2_differential.py`` (it needs ``git``), so it is
not repeated here.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.llm.stage2 import (
    PRESET_ANSWER,
    PRESET_TRANSPORT,
    REJECT_EMPTY,
    REJECT_TRUNCATED,
    classify_leg2,
    dispatch_leg2,
)
from app.llm.stage2_policy import reset_transport_stats, transport_stats

REPO = Path(__file__).resolve().parents[1]
IMPL = REPO / "app" / "engines" / "_graph_rag_impl.py"

_MID_CLAUSE = "A provider must establish a quality management system and the provider mus"

#: The engine's own predicate, in the shape the dispatch is handed it.
def _truncated(text: str) -> bool:
    return _MID_CLAUSE in text


@pytest.fixture(autouse=True)
def _clean_counters():
    reset_transport_stats()
    yield
    reset_transport_stats()


class TestPresetSemantics:
    """Each preset names a behaviour that already shipped — nothing new."""

    def test_transport_treats_a_falsy_answer_as_empty(self) -> None:
        for text in (None, ""):
            out = classify_leg2(
                text, preset=PRESET_TRANSPORT, structurally_truncated=_truncated,
            )
            assert out.rejected == REJECT_EMPTY and out.text is None and not out.ok

    def test_transport_rejects_structural_truncation(self) -> None:
        out = classify_leg2(
            _MID_CLAUSE, preset=PRESET_TRANSPORT, structurally_truncated=_truncated,
        )
        assert out.rejected == REJECT_TRUNCATED and not out.ok
        # The text is still carried VERBATIM, so a caller can log what was cut.
        assert out.text == _MID_CLAUSE

    def test_transport_whitespace_is_not_empty(self) -> None:
        """The pre-T1 transport rule is ``not text``, so ``"   "`` still ships.

        Pinned because it is a drift the move deliberately did NOT equalise: the
        answer path calls the same text empty. Equalising it is T1b.
        """
        out = classify_leg2(
            "   ", preset=PRESET_TRANSPORT, structurally_truncated=_truncated,
        )
        assert out.rejected == "" and out.ok and out.text == "   "

    def test_answer_preset_treats_whitespace_as_empty(self) -> None:
        out = classify_leg2(
            "   ", preset=PRESET_ANSWER, structurally_truncated=_truncated,
        )
        assert out.rejected == REJECT_EMPTY and not out.ok

    def test_answer_preset_does_not_apply_the_truncation_rule(self) -> None:
        """T1b, made explicit: the answer path shipped cut text and still does."""
        out = classify_leg2(
            _MID_CLAUSE, preset=PRESET_ANSWER, structurally_truncated=_truncated,
        )
        assert out.rejected == "" and out.ok and out.text == _MID_CLAUSE

    def test_a_complete_answer_is_carried_verbatim(self) -> None:
        text = "  Yes. Article 11 requires technical documentation.  "
        for preset in (PRESET_TRANSPORT, PRESET_ANSWER):
            out = classify_leg2(
                text, preset=preset, structurally_truncated=_truncated,
            )
            assert out.usable and out.text == text, "the dispatch must not rewrite"

    def test_an_unknown_preset_is_a_loud_error(self) -> None:
        with pytest.raises(ValueError, match="unknown leg-2 preset"):
            classify_leg2("x", preset="nope", structurally_truncated=_truncated)


class TestTheRecordingIsThePolicys:
    """``attempts == ok + failed`` is an invariant, not a hope (R361)."""

    @pytest.mark.parametrize(
        ("text", "preset", "want_ok"),
        (
            (None, PRESET_TRANSPORT, 0),
            ("", PRESET_TRANSPORT, 0),
            (_MID_CLAUSE, PRESET_TRANSPORT, 0),
            ("Yes. Article 11 applies.", PRESET_TRANSPORT, 1),
            ("   ", PRESET_ANSWER, 0),
            (_MID_CLAUSE, PRESET_ANSWER, 1),
        ),
    )
    def test_one_dial_one_result(self, text, preset, want_ok) -> None:
        before = transport_stats()
        dispatch_leg2(text, preset=preset, structurally_truncated=_truncated)
        after = transport_stats()
        assert after["fallback_ok"] - before["fallback_ok"] == want_ok
        assert after["fallback_failed"] - before["fallback_failed"] == (0 if want_ok else 1)

    def test_the_answer_preset_records_the_stripped_emptiness_rule(self) -> None:
        from app.llm import stage2_policy as pol

        pol.reset_transport_stats()
        dispatch_leg2("  ", preset=PRESET_ANSWER, structurally_truncated=_truncated)
        dispatch_leg2("  x  ", preset=PRESET_ANSWER, structurally_truncated=_truncated)
        stats = pol.transport_stats()
        assert (stats["fallback_ok"], stats["fallback_failed"]) == (1, 1)


class TestTheEngineSpeaksTheSharedPolicy:
    """Wire-level: both call sites must go through the one dispatch."""

    def test_both_call_sites_dispatch(self) -> None:
        src = IMPL.read_text(encoding="utf-8")
        assert "from app.llm.stage2 import (" in src
        assert src.count("dispatch_leg2(") == 2, (
            "the transport's leg 2 and the answer path's leg 2 must both dispatch"
        )
        assert "preset=PRESET_TRANSPORT" in src
        assert "preset=PRESET_ANSWER" in src

    def test_no_call_site_still_holds_its_own_ok_true_verdict(self) -> None:
        """The duplicated ``ok=True`` record was the drift; it must not return."""
        src = IMPL.read_text(encoding="utf-8")
        assert "STAGE2_FALLBACK, ok=True" not in src
        # The two surviving direct records are the exception handlers: a RAISING
        # leg-2 dial is a failure, and it must still reconcile the counters.
        assert src.count("record_result(_s2pol.STAGE2_FALLBACK, ok=False)") == 2

    def test_the_policy_module_has_no_module_level_engine_import(self) -> None:
        """No cycle: the module is pure and the engine injects the predicate."""
        tree = ast.parse((REPO / "app" / "llm" / "stage2.py").read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        assert not [m for m in imported if m.startswith(("app.engines", "app.routes"))]
        assert "app.llm.stage2_policy" not in imported, (
            "stage2_policy is imported lazily inside dispatch_leg2 on purpose"
        )

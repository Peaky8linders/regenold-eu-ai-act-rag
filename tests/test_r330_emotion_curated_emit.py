"""R330 §3.3 — the emotion-recognition GATE/EMITTER divergence.

``_detect_emotion_classification_inquiry`` is a disjunct of
``_is_curated_authoritative_intercept``, so ``_two_stage_generate`` skips
Stage-2 on the stated ground that the curated emotion cross-tier verdict is
"authoritative and complete".  But the EMITTER of that verdict,
``_detect_classification_topic``, short-circuits on
``_is_classification_question``, whose ``(?:does|do)`` branch admits only
``fall under|fall into|fall within|still apply|apply to|count as|qualify as``
— it carries no prohibition or risk-tier predicate.

So on R330 july7-259 the gate is True and the emitter is None: the curated text
is never emitted, Stage-2 is skipped anyway, and ``_deterministic_answer`` falls
through to the generic QA dump about RBI (1562 chars live; judged ans FAIL,
faithfulness FAIL, 3 wrong refs).

``REGENOLD_EMOTION_CURATED_EMIT`` (DEFAULT 0) rescues ONLY the case where
``_is_classification_question`` is the sole blocker, so it is a strict addition.
Its mandatory companion is the ``_graph_rag_data.py`` ``Art. 5`` -> ``Art. 5.1.f``
edit: without it the fix would ship the bare parent article the judge marked
WRONG in place of the sub-point it marked CORRECT.
"""
from __future__ import annotations

import pytest

from app.engines._graph_rag_data import _CLASSIFICATION_TOPICS
from app.engines.graph_rag import (
    GraphContext,
    _deterministic_answer,
    _detect_classification_topic,
    _detect_emotion_classification_inquiry,
    _emotion_curated_emit_enabled,
    _is_curated_authoritative_intercept,
)

# The judged R329 HARD row this fix exists for.
JULY7_259 = (
    "Does the EU AI Act prohibit all AI systems for emotion recognition, "
    "or only in certain contexts? If not, specify which contexts."
)
# R144's own probe set — every one of these ALREADY emits today, so they are
# the control that proves the gate is a strict addition.
R144_PROBES = [
    "Are AI systems for emotion recognition always prohibited under the EU AI Act?",
    "Is emotion recognition by an AI system permitted in a retail shop, or is it prohibited?",
    "Are emotion recognition systems high-risk?",
    "Is emotion recognition ever allowed?",
    "Is emotion inference categorically banned?",
    "What risk tier does emotion detection fall into?",
]


def _general_topic() -> dict:
    return next(t for t in _CLASSIFICATION_TOPICS if t["name"] == "emotion_recognition_general")


class TestGateDefault:
    def test_default_on(self, monkeypatch):
        """R330 — DEFAULT ON, after the gate was actually run.

        Live HARD arm (n=40, Claude Max wrapper, stage2_landed 0.82) graded by
        the grounded Sonnet-5 judge vs verbatim Act text, against the recorded
        R329 arm: answer_correctness 0.6250 -> 0.8750, mean factual 0.8807 ->
        0.9738, reference_correctness 0.2250 -> 0.3250, citation_faithfulness
        0.8000 -> 0.8500, latency p50 57.3s -> 39.1s, max refs 11 -> 5.

        Attribution kept conservative: the arm also carries the removal of
        REGENOLD_MAX_ANSWER_SENTENCES=4 from the operator environment, and 8 of
        11 answer improvements are on rows these gates do not touch. What is
        attributable: EVERY gate-target row improved and none regressed, in the
        direction predicted in advance by deterministic replay.
        """
        monkeypatch.delenv("REGENOLD_EMOTION_CURATED_EMIT", raising=False)
        assert _emotion_curated_emit_enabled() is True

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "ON", "Yes"])
    def test_explicit_enable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", val)
        assert _emotion_curated_emit_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "  ", "2", "maybe"])
    def test_parses_fail_closed(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", val)
        assert _emotion_curated_emit_enabled() is False


class TestDivergenceReproduced:
    def test_gate_true_emitter_none_today(self, monkeypatch):
        """The defect itself, reproduced with the flag OFF."""
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "0")  # R330: default is now ON
        assert _detect_emotion_classification_inquiry(JULY7_259) is True
        assert _is_curated_authoritative_intercept(JULY7_259) is True
        assert _detect_classification_topic(JULY7_259) is None

    def test_falls_through_to_the_qa_dump_today(self, monkeypatch):
        """With the flag OFF the shipped prose never addresses the workplace /
        education scope — the judged failure mode."""
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "0")  # R330: default is now ON
        ans = _deterministic_answer(JULY7_259, GraphContext())
        assert "workplaces and educational institutions" not in ans


class TestEmitterRescue:
    def test_emitter_returns_the_general_topic(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "1")
        topic = _detect_classification_topic(JULY7_259)
        assert topic is not None
        assert topic["name"] == "emotion_recognition_general"

    def test_curated_text_is_shipped(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "1")
        ctx = GraphContext()
        ans = _deterministic_answer(JULY7_259, ctx)
        low = ans.lower()
        assert "workplaces and educational institutions" in low
        assert "medical/safety exception" in low
        assert "not categorically prohibited" in low
        # Ans Conciseness is the axis we LEAD — the fix must shorten, never
        # lengthen.  Live judged length was 1562 chars; the curated verdict is
        # ~321.  Assert the direction with headroom, not the exact byte count.
        assert len(ans) < 400, len(ans)

    def test_refs_are_at_subpoint_grain(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "1")
        ctx = GraphContext()
        _deterministic_answer(JULY7_259, ctx)
        refs = sorted({o.get("article") for o in ctx.obligations})
        assert refs == ["Annex III.1.c", "Art. 5.1.f", "Art. 50.3"], refs


class TestGateEmitterParity:
    """The general lesson, not the single row.  Every question that makes
    ``_is_curated_authoritative_intercept`` True on the EMOTION disjunct must
    also produce an emitter payload — otherwise Stage-2 is skipped on the
    promise of a curated verdict that is never written.  This is the same
    class of defect as R330 §3.2."""

    @pytest.mark.parametrize("q", R144_PROBES + [JULY7_259])
    def test_gate_implies_emitter(self, monkeypatch, q):
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "1")
        assert _detect_emotion_classification_inquiry(q) is True
        assert _is_curated_authoritative_intercept(q) is True
        assert _detect_classification_topic(q) is not None, q

    @pytest.mark.parametrize("q", R144_PROBES)
    def test_r144_probes_are_unaffected(self, monkeypatch, q):
        """The R144 traffic already emitted; the gate must not move it."""
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "0")  # R330: default is now ON
        before = _detect_classification_topic(q)
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "1")
        after = _detect_classification_topic(q)
        assert before is not None and before is after

    def test_narrow_workplace_topic_still_wins_on_its_own_traffic(self, monkeypatch):
        """The rescue sits INSIDE the not-classification-shaped branch, so the
        narrow->broad first-match order in the topic loop is preserved: a
        workplace-scoped ask must not be demoted to the general topic."""
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "1")
        topic = _detect_classification_topic(
            "Is emotion recognition in the workplace prohibited?"
        )
        assert topic is not None
        assert topic["name"] == "emotion_recognition_workplace"


class TestArt51fCompanionEdit:
    """R330 §3.3 mandatory companion edit (`_graph_rag_data.py:838`).

    The R329 judge marked bare ``Article 5`` WRONG on july7-259 ("redundant /
    over-broad parent article") and ``Article 5.1.f`` CORRECT.  Shipping the
    gate fix without this edit would reinstate the wrong ref in place of the
    right one; with it the row goes 2/5 -> 3/3 precision.
    """

    def test_prohibition_ref_is_the_subpoint(self):
        refs = _general_topic()["refs"]
        assert "Art. 5.1.f" in refs
        assert "Art. 5" not in refs

    def test_lint_floor_head_resolves(self):
        """Every emitted reference must resolve in ``article_existence`` at
        head grain (AGENTS.md invariant 2).  ``Annex III.1.c`` / ``Art. 50.3``
        already ship on this row, so ``Art. 5.1.f`` is the same shape."""
        from app.data.article_existence import ARTICLE_EXISTENCE

        for ref in _general_topic()["refs"]:
            head = ref.split(".")[0] if ref.startswith("Annex") else ".".join(ref.split(".")[:2])
            assert head in ARTICLE_EXISTENCE, (ref, head)

    def test_davidath_metrics_head_collapse_the_subpoint(self):
        """The companion edit is UNGATED, so its davidath neutrality has to be
        argued at the scorer.  All three reference axes project through
        ``article_heads``, which strips ``Article 5.1.f`` -> ``Article 5``."""
        from evals.bench.metrics import article_head, article_heads

        assert article_head("Article 5.1.f") == "Article 5"
        assert article_heads(["Article 5.1.f"]) == article_heads(["Article 5"])


class TestDavidathZeroFire:
    """R120 fast method — the gate and the ungated data edit must both leave the
    deterministic bench byte-identical, verified on the corpus rather than by a
    476 run."""

    @staticmethod
    def _corpus() -> list[str]:
        from evals.bench import dataset

        qa = [(i.get("question") or "") for i in dataset.load_qa_pairs()]
        sc = [dataset.scenario_to_question(s) for s in dataset.load_scenarios()]
        assert len(qa) == 137 and len(sc) == 339, (len(qa), len(sc))
        return qa + sc

    def test_emotion_detector_zero_fire(self):
        """The gate is guarded by ``_detect_emotion_classification_inquiry``,
        which fires on 0 rows (0 QA emotion rows; the emotion SCENARIO rows are
        excluded by ``_MINIMAL_RISK_SCENARIO_OPENER_RE``) — so the rescue can
        never trigger on the bench."""
        hits = [q for q in self._corpus() if _detect_emotion_classification_inquiry(q)]
        assert hits == [], hits[:3]

    def test_topic_selection_identical_gate_off_vs_on(self, monkeypatch):
        corpus = self._corpus()
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "0")  # R330: default is now ON
        off = [(_detect_classification_topic(q) or {}).get("name") for q in corpus]
        monkeypatch.setenv("REGENOLD_EMOTION_CURATED_EMIT", "1")
        on = [(_detect_classification_topic(q) or {}).get("name") for q in corpus]
        assert off == on

    def test_deterministic_answers_unchanged_by_the_companion_edit(self):
        """Zero-variance proof for the UNGATED ref edit: replay all 476 rows
        through ``_deterministic_answer`` with the pre-R330 refs restored and
        assert both the prose AND the seeded obligations are byte-identical.
        (The 9 rows that select ``emotion_recognition_general`` are all
        scenarios, and ``classify_scenario_query`` short-circuits ahead of the
        curated-topic branch, so the edit is unreachable on the bench.)"""
        topic = _general_topic()
        corpus = self._corpus()

        def replay() -> list[tuple[str, tuple[str, ...]]]:
            out = []
            for q in corpus:
                ctx = GraphContext()
                ans = _deterministic_answer(q, ctx)
                out.append((ans, tuple(sorted(str(o.get("article")) for o in ctx.obligations))))
            return out

        after = replay()
        original = list(topic["refs"])
        try:
            topic["refs"] = ["Art. 5", "Annex III.1.c", "Art. 50.3"]
            before = replay()
        finally:
            topic["refs"] = original
        assert before == after

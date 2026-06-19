"""R130 — Antifragile QA review fixes.

Two fixes from the Antifragile 20-question expert review + the four
user-pasted live Stage-2 answers:

* Fix A — the verdict seeders (``_seed_classification_obligations`` /
  ``_seed_scenario_obligations`` / ``_seed_role_obligation_obligations``)
  fed the Stage-2 "APPLICABLE OBLIGATIONS" context block a content-free
  placeholder (``"Classification verdict reference: Art. 5."``). The
  placeholder (a) gave the model nothing describable for the
  refs-faithfulness axis and (b) leaked verbatim into polished answers
  ("... not categorically prohibited. Classification verdict."). Now the
  synthetic obligation ``text`` carries the real KB substance for each ref.

* Fix B — two FACTUAL GUARD additions to ``ANSWER_GENERATE_SYSTEM``:
  the Article 5(1)(h) real-time-RBI precision guard (law-enforcement /
  public-spaces only, never a bare blanket ban) and the Annex III(5)(d)
  generic-example guard (emergency triage ONLY).

Both fixes are byte-identical on the deterministic davidath bench by
construction — the synthetic obligation ``text`` is consumed ONLY in the
Stage-2 context block (which never fires under ``provider=cli``), and the
prompt is Stage-2-only. Verified: 0 pred/refs/scores diffs vs main across
all 476 davidath rows.
"""
from __future__ import annotations

from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM
from app.engines.graph_rag import (
    GraphContext,
    _seed_classification_obligations,
    _seed_role_obligation_obligations,
    _seed_scenario_obligations,
    _stage2_ref_substance,
)

# The exact placeholder strings the three seeders used before R130. None of
# these may ever reach the Stage-2 context block again (they leaked into
# polished answers).
_OLD_PLACEHOLDERS = (
    "Classification verdict reference:",
    "Scenario verdict (",
    "Role-obligation matrix entry:",
)


class TestStage2RefSubstance:
    def test_returns_real_kb_substance_not_placeholder(self):
        text = _stage2_ref_substance("Art. 5", "What practices are prohibited?")
        assert "Classification verdict reference" not in text
        # Real Article 5 substance — prohibitions / count.
        low = text.lower()
        assert "prohibit" in low or "eight" in low
        assert text.startswith("Article 5")  # user-facing ref prefix

    def test_uses_colon_separator_not_em_dash(self):
        # R108: never model an em-dash separator to the Stage-2 prompt.
        text = _stage2_ref_substance("Art. 6", "What is high risk?")
        assert "—" not in text  # em-dash
        assert "–" not in text  # en-dash
        assert ": " in text

    def test_substance_for_role_specific_article(self):
        text = _stage2_ref_substance("Art. 23", "What are importer obligations?")
        assert "Article 23" in text
        assert "importer" in text.lower()

    def test_fail_soft_on_unknown_ref(self):
        # No KB entry — must not raise; returns a usable label.
        text = _stage2_ref_substance("Art. 999", "anything")
        assert isinstance(text, str) and text
        assert "Classification verdict reference" not in text


class TestSeedersCarrySubstance:
    def test_classification_seeder_no_placeholder(self):
        ctx = GraphContext()
        topic = {"name": "emotion_recognition", "refs": ["Art. 5", "Annex III", "Art. 50"]}
        _seed_classification_obligations(ctx, topic, "Are emotion recognition systems always prohibited?")
        assert len(ctx.obligations) == 3
        # refs unchanged (wire references derive from `article`).
        assert [o["article"] for o in ctx.obligations] == ["Art. 5", "Annex III", "Art. 50"]
        for o in ctx.obligations:
            assert all(p not in o["text"] for p in _OLD_PLACEHOLDERS), o["text"]
            # Each obligation now carries describable substance.
            assert len(o["text"]) > 20

    def test_scenario_seeder_no_placeholder(self):
        ctx = GraphContext()

        class _V:
            role = "provider"
            risk_level = "high_risk"
            articles = ["Art. 6", "Art. 9", "Annex III"]

        _seed_scenario_obligations(ctx, _V(), "We are a provider of a hiring AI.")
        assert [o["article"] for o in ctx.obligations] == ["Art. 6", "Art. 9", "Annex III"]
        for o in ctx.obligations:
            assert all(p not in o["text"] for p in _OLD_PLACEHOLDERS), o["text"]

    def test_role_seeder_no_placeholder(self):
        ctx = GraphContext()
        _seed_role_obligation_obligations(
            ctx, "deployer", "high_risk", ("Art. 26", "Art. 27", "Art. 13"),
            "What does a deployer of a high-risk system owe?",
        )
        assert [o["article"] for o in ctx.obligations] == ["Art. 26", "Art. 27", "Art. 13"]
        for o in ctx.obligations:
            assert all(p not in o["text"] for p in _OLD_PLACEHOLDERS), o["text"]

    def test_seeders_backward_compatible_without_question(self):
        # The new `question` param is optional (default "") — existing
        # callers / test fixtures keep working.
        ctx = GraphContext()
        _seed_classification_obligations(ctx, {"name": "t", "refs": ["Art. 6"]})
        assert ctx.obligations and ctx.obligations[0]["article"] == "Art. 6"


class TestFactualGuards:
    def test_rbi_precision_guard_present(self):
        g = ANSWER_GENERATE_SYSTEM.lower()
        assert "5(1)(h)" in g
        assert "publicly accessible spaces for law enforcement" in g
        assert "not a blanket ban" in g

    def test_annex_iii_5d_generic_example_guard(self):
        g = ANSWER_GENERATE_SYSTEM.lower()
        # Annex III(5)(d) narrowed to emergency triage; never the generic
        # high-risk healthcare example.
        assert "emergency healthcare patient triage" in g
        assert "never cite it as the generic high-risk example" in g

    def test_social_scoring_guard_still_present(self):
        # R109 guard must survive (regression).
        g = ANSWER_GENERATE_SYSTEM.lower()
        assert "social scoring" in g
        assert "public authorities" in g  # the guard text references the removed limitation

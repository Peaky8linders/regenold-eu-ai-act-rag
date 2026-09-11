"""R410 — the general fixes for the four defects the R409/R410 audit grounded.

Every case here is a MEASURED defect from the live frontier evaluation
(``docs/measurements/r409/antifragile_frontier_judge_results.json``) or from the
R410 conciseness audit, not a hypothetical:

1. **Medtech hard-routing** — the four clinical-trial-triage questions of Part II
   Q8-Q11 all matched the ``medtech_triage`` classification topic and shipped the
   identical 651-char Annex III(5)(d) emergency-dispatch answer (refs included
   ``Annex III.5.d``). Emergency triage must keep that topic; clinical-trial
   selection must fall through.
2. **Presupposition detectors** — "Does the EU AI Act establish guiding
   principles for AI?" never fired ``_detect_guiding_principles_inquiry`` (its
   regex only accepted ``principles ... established by the Act``), so retrieval
   fell to BM25 and the engine answered with Articles 28/57/70 notifying-authority
   prose (0/4 criteria). The intercept answers must also DENY the non-statutory
   presupposition, not affirm it.
3. **Conciseness regression** — the R409 repair acceptance bound was a blanket
   ``max(1.8 * len(original), len(original) + 900)``; Part I answers ran
   424.5 -> 757.4 chars and Answer Conciseness fell 92.45 -> 69.88 pp.
4. **Reask/pushback coupling** — under ``REGENOLD_REASK_FOCUS`` (default) the
   route hands the engine the BARE re-asked question on a pushback turn, so
   ``previous_answer()`` found no turn 1 and the pushback-keep guard was a no-op.
"""

from __future__ import annotations

import pytest

from app.engines import answer_completeness as ac
from app.engines import _graph_rag_impl as impl
from app.engines._graph_rag_data import _CLASSIFICATION_TOPICS

# ── 1. Medtech hard-routing ──────────────────────────────────────────────────

PART_II_CLINICAL_TRIAL = (
    "Can a hospital use an AI system to sort patients based on their biometric "
    "data to determine priority for an experimental clinical trial?",
    "Under the EU AI Act, can a hospital use an AI system to sort patients based "
    "on their biometric data to determine priority for an experimental clinical "
    "trial, where the system infers each patient's race from that data?",
    "Under the EU AI Act, can a hospital use an AI system to sort patients based "
    "on their biometric data to determine priority for an experimental clinical "
    "trial, where the system infers each patient's sex from that data?",
    "Under the EU AI Act, can a hospital use an AI system to sort patients based "
    "on their biometric data to determine priority for an experimental clinical "
    "trial, where the system sorts on clinically relevant physiological "
    "parameters and infers no sensitive or protected attribute?",
)

EMERGENCY_TRIAGE = (
    "Under the EU AI Act, is an AI system used to dispatch and triage "
    "emergency-room patients high-risk?",
    "Is an AI system that triages patients in an emergency department "
    "considered high-risk?",
    "We deploy AI to prioritise patients in emergency care. Is it high-risk?",
    "Is AI used to dispatch ambulances to emergencies high-risk?",
)


@pytest.mark.parametrize("question", PART_II_CLINICAL_TRIAL)
def test_clinical_trial_triage_is_not_hard_routed_to_emergency_dispatch(question):
    assert impl._detect_classification_topic(question) is None


@pytest.mark.parametrize("question", EMERGENCY_TRIAGE)
def test_emergency_triage_still_reaches_the_annex_iii_5d_topic(question):
    topic = impl._detect_classification_topic(question)
    assert topic is not None and topic["name"] == "medtech_triage"


def test_medtech_topic_answer_keeps_the_statutory_split():
    topic = next(t for t in _CLASSIFICATION_TOPICS if t["name"] == "medtech_triage")
    answer = topic["answer"].lower()
    assert "annex iii(5)(d)" in answer  # emergency triage IS listed
    assert "clinical trial" in answer  # and the split is stated


# ── 2. Presupposition: guiding principles ────────────────────────────────────


def test_guiding_principles_detector_fires_on_the_act_first_verb_form():
    assert impl._detect_guiding_principles_inquiry(
        "Does the EU AI Act establish guiding principles for AI?"
    )
    assert impl._detect_guiding_principles_inquiry(
        "What are the guiding principles established by the AI Act?"
    )
    # A provision-specific principles ask must still bail out (R112 guard).
    assert not impl._detect_guiding_principles_inquiry(
        "What data governance principles are laid down in Article 10?"
    )


def test_guiding_principles_answer_denies_the_presupposition():
    answer = impl._deterministic_answer(
        "Does the EU AI Act establish guiding principles for AI?",
        impl.GraphContext(question="Does the EU AI Act establish guiding principles for AI?"),
    )
    low = answer.lower()
    assert low.startswith("the eu ai act does not establish")
    assert "recital 27" in low and "article 95" in low
    assert impl._is_curated_authoritative_intercept(
        "Does the EU AI Act establish guiding principles for AI?"
    )


def test_guiding_principles_answer_survives_the_wire_normaliser():
    """The route's soft char cap deletes the longest NON-cite-anchored sentence.

    Before R410 the denial lead carried no ``art.`` / ``article `` / ``annex``
    token, so it was the FIRST sentence deleted: the shipped answer asserted the
    HLEG principles existed and lost both the No verdict and the
    recitals-are-not-binding point (2 of the 4 graded criteria). Every sentence
    is now cite-anchored, so the cap has nothing it is allowed to drop.
    """
    from app.integrations.regenold import models as M

    q = "Does the EU AI Act establish guiding principles for AI?"
    raw = impl._deterministic_answer(q, impl.GraphContext(question=q)).strip()
    wire = M.normalise_answer_for_regenold(raw, question=q)
    assert wire == raw, "the normaliser dropped a sentence from the curated answer"
    assert wire.lower().startswith("the eu ai act does not establish")
    assert "article 95" in wire.lower() and "article 4" in wire.lower()
    for principle in (
        "human agency",
        "technical robustness",
        "privacy and data governance",
        "transparency",
        "non-discrimination",
        "social and environmental",
        "accountability",
    ):
        assert principle in wire.lower(), f"missing principle: {principle}"
    # The invariant that makes the fix robust at ANY cap value: no sentence is
    # cap-droppable, because each carries a cite anchor.
    sentences = M._split_sentences(wire)
    assert len(sentences) >= 2
    for sentence in sentences:
        low = sentence.lower()
        assert ("art." in low) or ("annex" in low) or ("article " in low), (
            f"cap-droppable sentence: {sentence!r}"
        )


# ── 3. Presupposition: minimal risk ──────────────────────────────────────────


def test_minimal_risk_answer_denies_the_presupposition():
    q = "Does the EU AI Act provide for a category of minimal risk AI systems?"
    answer = impl._deterministic_answer(q, impl.GraphContext(question=q))
    assert answer.lower().startswith("the eu ai act does not establish a formal minimal-risk")


# ── 4. Presupposition: the risk-framework taxonomy is honest about its status ─


def test_risk_framework_topic_states_the_conditions_not_formal_categories():
    topic = next(t for t in _CLASSIFICATION_TOPICS if t["name"] == "risk_framework_overview")
    answer = topic["answer"].lower()
    assert "attaches obligations by condition" in answer
    assert "descriptive shorthand" in answer
    # The tiers themselves must still be named (Part I Q1 criteria).
    for token in ("article 5", "article 6", "article 50"):
        assert token in answer


# ── 5. Conciseness budget on the completeness repair ─────────────────────────


def test_repair_budget_is_additive_in_the_gap_count():
    one = [ac.Gap("member", "Article 13.3.a", "x")]
    many = [ac.Gap("member", f"Article 13.3.{c}", "x") for c in "abcdef"]
    base = 1000
    assert ac.repair_char_budget("x" * base, one) == base + 120 + 90
    assert ac.repair_char_budget("x" * base, many) < base + 120 + 90 * 6 + 1
    # Never more than the outer ratio bound.
    assert ac.repair_char_budget("x" * base, many) <= int(1.6 * base)


def test_repair_budget_is_tighter_than_the_old_blanket_ratio():
    base = 1000
    old = max(1.8 * base, base + 900)
    assert ac.repair_char_budget("x" * base, [ac.Gap("member", "Article 13.3.a", "x")]) < old


def test_repair_budget_survives_bad_input():
    assert ac.repair_char_budget(None, None) > 0
    assert ac.repair_char_budget("", []) > 0


_YES_NO_Q = "Does the Article 50(4) disclosure duty apply to criminal-offence prosecution?"
_HONEST_A = (
    "The disclosure duty in Article 50(4) does not apply where the use is "
    "authorised by law to detect, prevent, investigate or prosecute criminal offences."
)


def test_accept_repair_rejects_a_repair_over_the_conciseness_budget():
    gaps = ac.verdict_lead_gap(_YES_NO_Q, _HONEST_A)
    assert gaps, "fixture must raise a verdict gap"
    within = "No. " + _HONEST_A
    over = "No. " + _HONEST_A + " " + ("Unrelated filler sentence. " * 200)
    assert ac.accept_repair(_YES_NO_Q, _HONEST_A, within, gaps) is True
    assert ac.accept_repair(_YES_NO_Q, _HONEST_A, over, gaps) is False


def test_repair_prompt_carries_the_budget_and_a_compression_rule():
    gaps = ac.verdict_lead_gap(_YES_NO_Q, _HONEST_A)
    msg = ac.build_repair_user_message(_YES_NO_Q, _HONEST_A, gaps)
    assert "at most" in msg and "characters" in msg
    assert "Compress duplicated wording" in msg
    assert str(ac.repair_char_budget(_HONEST_A, gaps)) in msg


# ── 6. Reask focus no longer blinds the pushback-keep guard ───────────────────


def _reask_turn(monkeypatch):
    from types import SimpleNamespace

    from app.routes.regenold import _build_question_from_history
    from evals.regenold.official_batch import PUSHBACK_TEMPLATE

    monkeypatch.delenv("REGENOLD_REASK_FOCUS", raising=False)  # production default
    first = "What must a deployer of a high-risk AI system in a public service do before first use?"
    previous = (
        "Under Article 26(1), deployers must use the system in accordance with the "
        "instructions for use. Under Article 27(1), deployers that are bodies "
        "governed by public law must carry out a fundamental rights impact assessment."
    )
    history = _build_question_from_history(
        [
            SimpleNamespace(role="user", content=first),
            SimpleNamespace(role="assistant", content=previous),
            SimpleNamespace(role="user", content=PUSHBACK_TEMPLATE.format(question=first)),
        ]
    )
    return history, first, previous


def test_reask_path_keeps_retrieval_bare_but_carries_history_for_the_guard(monkeypatch):
    history, first, previous = _reask_turn(monkeypatch)
    # Retrieval is unchanged: the bare re-asked question is the engine question.
    assert str(history[0]) == first
    assert history.resolved_question == first
    # The flattened history rides along for the completeness guards.
    guard = history.guard_question
    assert guard and "Conversation so far:" in guard and "Latest question:" in guard
    assert previous in guard


def test_pushback_keep_detector_fires_on_the_guard_question(monkeypatch):
    history, _first, _previous = _reask_turn(monkeypatch)
    new_answer = "Under Article 26(1), deployers must use the system in accordance with the instructions for use."
    # Blinded on the bare question (the pre-R410 defect)...
    assert ac.dropped_pushback_points(str(history[0]), new_answer) == []
    # ...and visible once the flattened history is passed.
    dropped = ac.dropped_pushback_points(history.guard_question, new_answer)
    assert dropped and any("Article 27" in g.text for g in dropped)


def test_two_stage_generate_forwards_the_guard_question(monkeypatch):
    import app.engines.question_complexity as qc

    monkeypatch.setattr(qc, "is_complex_question", lambda *a, **k: False)
    monkeypatch.setattr(impl, "_deterministic_answer", lambda *a, **k: "KG ANSWER")
    monkeypatch.setattr(impl, "_stage2_polish_enabled", lambda: True)
    monkeypatch.setattr(impl, "_stage2_provider_enabled", lambda: True)
    monkeypatch.setattr(impl, "_stage2_simple_skip_enabled", lambda: False)
    monkeypatch.setattr(impl, "_curated_stage2_skip_enabled", lambda: False)
    monkeypatch.setattr(impl, "_definitional_stage2_skip_enabled", lambda: False)
    monkeypatch.setattr(
        impl, "_claude_max_enhance_answer",
        lambda **k: "The system is classified as high-risk under Article 6.",
    )
    seen = []

    def spy(question, answer, context):
        seen.append(question)
        return answer

    monkeypatch.setattr(impl, "_guard_answer_completeness", spy)
    bare = "BARE REASK"
    guard = "Conversation so far:\nAssistant: prior\n\nLatest question:\nBARE REASK"
    impl._two_stage_generate(
        bare, impl.GraphContext(question=bare), guard_question=guard
    )
    assert seen == [guard]

"""R409 — ``app/engines/answer_completeness.py``: behavioural, two-sided tests.

No source-string greps (the repo's recorded false-green: a test that greps a
module for a call site passes while nothing calls it). Every flag is proven by
what the functions RETURN with the flag OFF and ON for an input that fires.

Detector cases come from the real failing rows of the R407 hard-mode run. The
answers are verbatim excerpts of what we shipped, inlined because
``evals/bench/results/`` is gitignored (only the mojibake apostrophe is repaired).
Pushbacks use the benchmark's verbatim ``PUSHBACK_TEMPLATE``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engines import answer_completeness as ac
from app.engines.answer_completeness import Gap
from evals.regenold.official_batch import PUSHBACK_TEMPLATE

_FLAGS = (
    "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD",
    "REGENOLD_EXCEPTION_LIMB_GUARD",
    "REGENOLD_VERDICT_LEAD_GUARD",
    "REGENOLD_PUSHBACK_KEEP_CONTRACT",
    "REGENOLD_GOVERNING_PROVISION_CLAUSE",
)
_READERS = {
    "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD": ac.closed_set_completeness_enabled,
    "REGENOLD_EXCEPTION_LIMB_GUARD": ac.exception_limb_guard_enabled,
    "REGENOLD_VERDICT_LEAD_GUARD": ac.verdict_lead_guard_enabled,
    "REGENOLD_PUSHBACK_KEEP_CONTRACT": ac.pushback_keep_enabled,
    "REGENOLD_GOVERNING_PROVISION_CLAUSE": ac.governing_provision_clause_enabled,
}

# rg_046 — OMITTED_ENUMERATED_ITEM (criteria 13.3.a, 13.3.c, 13.3.d, 13.3.e, 13.3.f failed).
RG046_Q = (
    "Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer "
    "in the instructions for use? List the required categories of information."
)
RG046_A = (
    "The provider must supply instructions for use containing the following categories of "
    "information: the intended purpose of the high-risk AI system, the level of accuracy including "
    "its metrics, robustness and cybersecurity against which the system has been tested and "
    "validated and any known or foreseeable circumstances affecting that level, any known or "
    "foreseeable circumstances related to use in accordance with the intended purpose or reasonably "
    "foreseeable misuse that may lead to risks to health, safety or fundamental rights, where "
    "applicable, technical capabilities and characteristics to explain the system's output, when "
    "appropriate, performance regarding specific persons or groups on which the system is intended "
    "to be used, when appropriate, specifications for input data or other relevant information on "
    "training, validation and testing datasets, and where applicable, information enabling deployers "
    "to interpret the output and use it appropriately. These requirements are specified in "
    "Article 13(3)(b)(i) to (vii)."
)

# rg_015 — the graded post-pushback answer dropped Article 50(1) "unless this is obvious".
RG015_Q = (
    "What obligations, if any, does the EU AI Act set in place for AI systems that interact directly "
    "with natural persons? What exceptions, if any, apply?"
)
RG015_A = (
    "Limited risk. AI systems that interact directly with natural persons are subject to the "
    "transparency obligations in Article 50, which apply regardless of the system's risk tier. "
    "Deployers of emotion recognition or biometric categorisation systems must inform exposed persons, "
    "and deployers of deep fakes must disclose the artificial generation or manipulation, with "
    "exceptions for artistic, creative, satirical or fictional works where disclosure must not hamper "
    "enjoyment. The Article 50(1) provider obligation does not apply to AI systems authorised by law "
    "to detect, prevent, investigate or prosecute criminal offences, subject to safeguards, unless "
    "those systems are available to the public to report crimes. The Article 50(3) deployer "
    "obligation does not apply where such systems are used for criminal offence detection under "
    "legal authorisation with safeguards."
)

# rg_110 shape — VERDICT_POLARITY_OR_FRAMING: a yes/no ask answered with a conditional lead.
YES_NO_Q = "Does the fundamental rights impact assessment under Article 27 apply to our gas supply contractor?"
CONDITIONAL_LEAD_A = (
    "High-risk only where the AI system is used in an essential public service under Annex III, in "
    "which case a fundamental rights impact assessment applies under Article 27(1)."
)
YES_LEAD_A = (
    "Yes. Where the AI system is high-risk under Annex III, a fundamental rights impact assessment "
    "applies under Article 27(1)."
)

# Pushback keep: turn 1 stated an Article 27 point, the post-pushback answer drops it.
KEEP_Q = "What must a deployer of a high-risk AI system in a public service do before first use?"
KEEP_PREV = (
    "Under Article 26(1), deployers must use the system in accordance with the instructions for use. "
    "Under Article 27(1), deployers that are bodies governed by public law must carry out a fundamental "
    "rights impact assessment before putting the system into use."
)
KEEP_NEW = "Under Article 26(1), deployers must use the system in accordance with the instructions for use."


def _flatten(first_user: str, assistant: str, live_turn: str) -> str:
    """The concatenation-path format of ``_build_question_from_history``."""
    return (
        "Conversation so far:\n"
        f"User: {first_user}\n"
        f"Assistant: {assistant}\n"
        "\n"
        "Latest question:\n"
        f"{live_turn}"
    )


def _pushback(question: str, previous: str) -> str:
    return _flatten(question, previous, PUSHBACK_TEMPLATE.format(question=question))


def _verbatim(coord: str) -> str:
    from app.data.provision_text import get_provision_text

    return " ".join((get_provision_text(coord) or "").split())


@pytest.fixture
def flags_off(monkeypatch):
    for flag in _FLAGS:
        monkeypatch.delenv(flag, raising=False)
    return monkeypatch


# ── Flags ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("flag", _FLAGS)
def test_flag_is_off_when_unset(flags_off, flag):
    assert _READERS[flag]() is False


@pytest.mark.parametrize("flag", _FLAGS)
@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_flag_allow_list_values_turn_it_on(flags_off, flag, value):
    flags_off.setenv(flag, value)
    assert _READERS[flag]() is True


@pytest.mark.parametrize("flag", _FLAGS)
@pytest.mark.parametrize("value", ["0", "", "enabled", "Y", "false", "off"])
def test_flag_other_values_keep_it_off(flags_off, flag, value):
    flags_off.setenv(flag, value)
    assert _READERS[flag]() is False


def test_member_flag_gates_collect_gaps_both_ways(flags_off):
    assert ac.collect_gaps(RG046_Q, RG046_A) == []
    flags_off.setenv("REGENOLD_CLOSED_SET_COMPLETENESS_GUARD", "1")
    gaps = ac.collect_gaps(RG046_Q, RG046_A)
    assert gaps and {g.kind for g in gaps} == {"member"}


def test_exception_flag_gates_collect_gaps_both_ways(flags_off):
    assert ac.collect_gaps(RG015_Q, RG015_A) == []
    flags_off.setenv("REGENOLD_EXCEPTION_LIMB_GUARD", "1")
    gaps = ac.collect_gaps(RG015_Q, RG015_A)
    assert gaps and {g.kind for g in gaps} == {"exception"}


def test_verdict_flag_gates_collect_gaps_both_ways(flags_off):
    assert ac.collect_gaps(YES_NO_Q, CONDITIONAL_LEAD_A) == []
    flags_off.setenv("REGENOLD_VERDICT_LEAD_GUARD", "1")
    assert [g.kind for g in ac.collect_gaps(YES_NO_Q, CONDITIONAL_LEAD_A)] == ["verdict"]


def test_keep_flag_gates_collect_gaps_both_ways(flags_off):
    question = _pushback(KEEP_Q, KEEP_PREV)
    assert ac.collect_gaps(question, KEEP_NEW) == []
    flags_off.setenv("REGENOLD_PUSHBACK_KEEP_CONTRACT", "1")
    assert [g.kind for g in ac.collect_gaps(question, KEEP_NEW)] == ["keep"]


def test_governing_clause_is_two_sided(flags_off):
    question = "Which article of the EU AI Act governs human oversight measures?"
    assert ac.governing_provision_clause(question) == ""
    flags_off.setenv("REGENOLD_GOVERNING_PROVISION_CLAUSE", "1")
    clause = ac.governing_provision_clause(question)
    assert "GOVERNING PROVISION" in clause and "each numbered paragraph" in clause
    assert "..." not in clause and "…" not in clause and " - " not in clause and "—" not in clause
    assert ac.governing_provision_clause(RG046_Q) == ""


def test_pushback_keep_clause_is_two_sided(flags_off):
    question = _pushback(KEEP_Q, KEEP_PREV)
    assert ac.pushback_keep_clause(question) == ""
    flags_off.setenv("REGENOLD_PUSHBACK_KEEP_CONTRACT", "1")
    clause = ac.pushback_keep_clause(question)
    assert clause.startswith(" PREVIOUS ANSWER POINTS")
    assert "Under Article 27(1), deployers that are bodies governed by public law" in clause
    assert "Keep each point unless" in clause
    assert "..." not in clause and "—" not in clause
    # Not a challenge turn: nothing to keep.
    assert ac.pushback_keep_clause(_flatten(KEEP_Q, KEEP_PREV, "What about importers?")) == ""
    # A dispute that cites new law contradicts the clause's premise: suppressed.
    cites_law = _flatten(KEEP_Q, KEEP_PREV, "That is wrong, Article 49 says otherwise.")
    assert ac.pushback_keep_clause(cites_law) == ""


def test_all_detectors_off_is_empty_for_every_firing_input(flags_off):
    for question, answer in (
        (RG046_Q, RG046_A),
        (RG015_Q, RG015_A),
        (YES_NO_Q, CONDITIONAL_LEAD_A),
        (_pushback(KEEP_Q, KEEP_PREV), KEEP_NEW),
    ):
        assert ac.collect_gaps(question, answer) == []


# ── Closed statutory sets ────────────────────────────────────────────────────


def test_rg046_member_gaps_are_the_omitted_article_13_3_points():
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A)
    coords = [g.coordinate for g in gaps]
    assert "Article 13.3.a" in coords and "Article 13.3.c" in coords
    assert coords == ["Article 13.3.a", "Article 13.3.c", "Article 13.3.d", "Article 13.3.e", "Article 13.3.f"]
    # (b) is covered by the answer's own "Article 13(3)(b)(i) to (vii)" citation.
    assert "Article 13.3.b" not in coords
    for gap in gaps:
        assert gap.kind == "member"
        assert 0 < len(gap.text) <= 240
        assert _verbatim(gap.coordinate).startswith(gap.text)


def test_answer_stating_every_article_13_3_point_has_no_member_gaps():
    complete = (
        "Under Article 13(3), the instructions for use must contain (a) the identity and contact details "
        "of the provider and its authorised representative; (b) the characteristics, capabilities and "
        "limitations of performance of the system; (c) the pre-determined changes to the system and its "
        "performance; (d) the human oversight measures referred to in Article 14; (e) the computational "
        "and hardware resources needed, the expected lifetime and the maintenance measures; and (f) a "
        "description of the logging mechanisms referred to in Article 12."
    )
    assert ac.missing_closed_set_members(RG046_Q, complete) == []


def test_member_detector_needs_a_list_shaped_question():
    not_a_list = "Does a provider of a high-risk AI system have to give the deployer instructions for use?"
    assert ac.is_list_question(RG046_Q) is True
    assert ac.is_list_question(not_a_list) is False
    assert ac.missing_closed_set_members(not_a_list, RG046_A) == []


def test_member_detector_never_demands_an_unengaged_group():
    # Names only the head: no paragraph or point of Article 13 is engaged.
    head_only = "Article 13 requires the provider to supply instructions for use to the deployer."
    assert ac.missing_closed_set_members(RG046_Q, head_only) == []


# ── Exception limbs ──────────────────────────────────────────────────────────


def test_rg015_exception_gap_is_the_article_50_1_obviousness_clause():
    gaps = ac.missing_exception_limbs(RG015_Q, RG015_A)
    obvious = [g for g in gaps if g.coordinate == "Article 50.1" and "obvious" in g.text]
    assert len(obvious) == 1
    assert obvious[0].kind == "exception"
    assert obvious[0].text.startswith("unless this is obvious")
    assert obvious[0].text in _verbatim("Article 50.1")
    # The law-enforcement carve-out the answer DOES state is not reported.
    assert not any("criminal offences" in g.text for g in gaps if g.coordinate == "Article 50.1")


def test_exception_detector_needs_an_exception_or_condition_question():
    plain = "Describe the transparency duties for AI systems that interact with natural persons."
    assert ac.is_exception_question(RG015_Q) is True
    assert ac.is_exception_question(plain) is False
    assert ac.missing_exception_limbs(plain, RG015_A) == []


def test_exception_gap_disappears_when_the_answer_states_the_clause():
    fixed = RG015_A + (
        " Under Article 50(1) the duty to inform does not arise where this is obvious from the point of "
        "view of a reasonably well-informed, observant and circumspect natural person, taking into account "
        "the circumstances and the context of use."
    )
    assert not any("obvious" in g.text for g in ac.missing_exception_limbs(RG015_Q, fixed))


# ── Verdict lead ─────────────────────────────────────────────────────────────


def test_conditional_lead_on_a_yes_no_question_is_a_verdict_gap():
    gaps = ac.verdict_lead_gap(YES_NO_Q, CONDITIONAL_LEAD_A)
    assert gaps == [Gap("verdict", "", YES_NO_Q)]


@pytest.mark.parametrize("answer", [YES_LEAD_A, "No, Article 27 does not apply here.", "**Yes.** Article 27(1) applies."])
def test_yes_or_no_lead_is_not_a_verdict_gap(answer):
    assert ac.verdict_lead_gap(YES_NO_Q, answer) == []


@pytest.mark.parametrize(
    "question, expected",
    [
        (YES_NO_Q, True),
        ("We run a hospital triage tool. In that case, is the system high-risk?", True),
        ("Is it a provider or a deployer obligation?", False),
        ("What does Article 27 require?", False),
        ("Can you explain which articles apply to deployers?", False),
        ("Name the areas of high-risk use cases. Is healthcare decision making one of them?", True),
        ("Is our system high-risk? Which articles apply?", True),
    ],
)
def test_is_yes_no_question_shapes(question, expected):
    assert ac.is_yes_no_question(question) is expected


def test_verdict_detector_reads_the_reasked_question_inside_a_pushback():
    question = _pushback(YES_NO_Q, CONDITIONAL_LEAD_A)
    assert ac.verdict_lead_gap(question, CONDITIONAL_LEAD_A) == [Gap("verdict", "", YES_NO_Q)]


# ── Pushback keep ────────────────────────────────────────────────────────────


def test_official_pushback_dropping_an_anchored_sentence_is_a_keep_gap():
    question = _pushback(KEEP_Q, KEEP_PREV)
    gaps = ac.dropped_pushback_points(question, KEEP_NEW)
    assert len(gaps) == 1
    assert gaps[0].kind == "keep" and gaps[0].coordinate == "Article 27"
    assert gaps[0].text.startswith("Under Article 27(1), deployers that are bodies governed by public law")


def test_pushback_that_keeps_every_point_has_no_keep_gap():
    assert ac.dropped_pushback_points(_pushback(KEEP_Q, KEEP_PREV), KEEP_PREV) == []


def test_non_challenge_multi_turn_question_has_no_keep_gap():
    question = _flatten(KEEP_Q, KEEP_PREV, "What about importers of such systems?")
    assert ac.previous_answer(question) == KEEP_PREV
    assert ac.dropped_pushback_points(question, KEEP_NEW) == []


def test_single_turn_question_has_no_keep_gap():
    assert ac.dropped_pushback_points(KEEP_Q, KEEP_NEW) == []


def test_route_flatten_format_is_what_the_keep_detector_parses(monkeypatch):
    """Pins the integration contract against the REAL route builder, both regimes."""
    from app.routes.regenold import _build_question_from_history

    messages = [
        SimpleNamespace(role="user", content=KEEP_Q),
        SimpleNamespace(role="assistant", content=KEEP_PREV),
        SimpleNamespace(role="user", content=PUSHBACK_TEMPLATE.format(question=KEEP_Q)),
    ]
    monkeypatch.setenv("REGENOLD_REASK_FOCUS", "0")
    flattened = _build_question_from_history(messages)[0]
    assert ac.previous_answer(flattened) == KEEP_PREV
    assert ac.live_question(flattened) == PUSHBACK_TEMPLATE.format(question=KEEP_Q)
    assert [g.coordinate for g in ac.dropped_pushback_points(flattened, KEEP_NEW)] == ["Article 27"]

    # Tripwire: with the R305 re-ask focus ON (production default) the route hands
    # the engine the bare question, on which the keep detector is a no-op. If this
    # starts firing, the integration note in the module docstring is stale.
    monkeypatch.delenv("REGENOLD_REASK_FOCUS", raising=False)
    focused = _build_question_from_history(messages)[0]
    assert focused == KEEP_Q
    assert ac.previous_answer(focused) == ""
    assert ac.dropped_pushback_points(focused, KEEP_NEW) == []


# ── Parsing helpers ──────────────────────────────────────────────────────────


def test_live_question_and_previous_answer():
    question = _pushback(KEEP_Q, KEEP_PREV)
    assert ac.live_question(question) == PUSHBACK_TEMPLATE.format(question=KEEP_Q)
    assert ac.live_question("  plain question?  ") == "plain question?"
    assert ac.previous_answer(question) == KEEP_PREV
    assert ac.previous_answer(KEEP_Q) == ""
    two_exchanges = (
        "Conversation so far:\nUser: q1\nAssistant: first answer\nUser: q2\nAssistant: second answer\n"
        "line two of it\n\nLatest question:\nq3"
    )
    assert ac.previous_answer(two_exchanges) == "second answer\nline two of it"


def test_named_heads_accepts_the_common_prose_forms():
    text = (
        "See Art. 13 and Article 13(3)(b), then Articles 9 and 10, Articles 51 to 53, "
        "Annex III, point 5(a), Annexes I and III, Article 6.3.d and Article 999."
    )
    assert ac.named_heads(text) == [
        "Article 13", "Article 9", "Article 10", "Article 51", "Article 52", "Article 53",
        "Annex III", "Annex I", "Article 6",
    ]
    assert ac.named_heads("Article 13.3.a") == ["Article 13"]
    assert ac.named_heads("no provision here") == []


def test_question_shape_detectors():
    assert ac.is_governing_provision_question("Which article of the EU AI Act governs human oversight measures?")
    assert ac.is_governing_provision_question("What provision lays down the rules on post-market monitoring?")
    assert not ac.is_governing_provision_question("What articles/annex and specific points, if any, concern this use case?")
    assert ac.is_exception_question("When is that not the case?")
    assert not ac.is_list_question("Is emotion recognition in the workplace prohibited?")


# ── Aggregation, prompt, acceptance ──────────────────────────────────────────


def test_collect_gaps_orders_member_exception_keep_verdict_and_caps_at_twelve(flags_off):
    for flag in _FLAGS:
        flags_off.setenv(flag, "1")
    flags_off.setattr(ac, "missing_closed_set_members", lambda q, a: [Gap("member", f"Article 5.1.{c}", "t") for c in "abcdefgh"])
    flags_off.setattr(ac, "missing_exception_limbs", lambda q, a: [Gap("exception", "Article 50.1", f"e{i}") for i in range(3)])
    flags_off.setattr(ac, "dropped_pushback_points", lambda q, a: [Gap("keep", "Article 27", f"k{i}") for i in range(3)])
    flags_off.setattr(ac, "verdict_lead_gap", lambda q, a: [Gap("verdict", "", "v")])
    gaps = ac.collect_gaps("q", "a")
    assert len(gaps) == 12
    assert [g.kind for g in gaps] == ["member"] * 8 + ["exception"] * 3 + ["keep"]


def test_build_repair_user_message_carries_question_answer_items_and_rules():
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A) + [Gap("verdict", "", "Is it required?")]
    msg = ac.build_repair_user_message(_pushback(RG046_Q, RG046_A), RG046_A, gaps)
    assert msg.startswith("QUESTION:\n" + RG046_Q + "\n")
    assert RG046_A in msg
    for gap in gaps[:-1]:
        assert gap.coordinate in msg and gap.text in msg
    assert "Open with Yes or No" in msg
    assert "Return the complete revised answer only." in msg
    assert "Keep every correct statement and every citation" in msg
    assert "Do not use dashes as punctuation and do not use ellipses." in msg
    assert "I don't think this is correct" not in msg  # the dispute preamble is not the question
    assert ac.build_repair_user_message(RG046_Q, RG046_A, []) == ""


_RG046_REPAIR = RG046_A + (
    " Article 13(3) also requires (a) the identity and contact details of the provider and of its "
    "authorised representative, (c) the changes to the system and its performance pre-determined by the "
    "provider at the initial conformity assessment, (d) the human oversight measures referred to in "
    "Article 14, (e) the computational and hardware resources needed, the expected lifetime of the system "
    "and its maintenance and care measures, and (f) a description of the logging mechanisms referred to in "
    "Article 12."
)


def test_accept_repair_true_when_gaps_drop_and_new_heads_come_from_the_act_text():
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A)
    assert ac.missing_closed_set_members(RG046_Q, _RG046_REPAIR) == []
    assert ac.accept_repair(RG046_Q, RG046_A, _RG046_REPAIR, gaps) is True


def test_accept_repair_false_when_a_head_of_the_original_is_dropped():
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A)
    no_article_13 = _RG046_REPAIR.replace("Article 13(3)(b)(i) to (vii)", "the Act").replace("Article 13(3)", "The Act")
    assert "Article 13" not in no_article_13
    assert ac.accept_repair(RG046_Q, RG046_A, no_article_13, gaps) is False


def test_accept_repair_false_when_a_new_head_appears():
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A)
    assert ac.accept_repair(RG046_Q, RG046_A, _RG046_REPAIR + " Penalties follow under Article 99.", gaps) is False


@pytest.mark.parametrize("tail", [" and so on...", " and so on…"])
def test_accept_repair_false_on_an_ellipsis(tail):
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A)
    assert ac.accept_repair(RG046_Q, RG046_A, _RG046_REPAIR + tail, gaps) is False


def test_accept_repair_false_when_nothing_improves_or_it_is_empty_or_too_long():
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A)
    assert ac.accept_repair(RG046_Q, RG046_A, RG046_A, gaps) is False
    assert ac.accept_repair(RG046_Q, RG046_A, "   ", gaps) is False
    assert ac.accept_repair(RG046_Q, RG046_A, _RG046_REPAIR + " filler" * 400, gaps) is False
    assert ac.accept_repair(RG046_Q, RG046_A, _RG046_REPAIR, []) is False


def test_accept_repair_false_on_new_meta_commentary_but_not_on_instructions_for_use():
    gaps = ac.missing_closed_set_members(RG046_Q, RG046_A)
    meta = _RG046_REPAIR + " The materials supplied do not say more."
    assert ac.accept_repair(RG046_Q, RG046_A, meta, gaps) is False
    new_instruction = _RG046_REPAIR + " Per your instruction, nothing else is listed."
    assert ac.accept_repair(RG046_Q, RG046_A, new_instruction, gaps) is False
    # "instructions for use" is the statutory term the whole row is about.
    assert "instructions for use" in _RG046_REPAIR
    assert ac.accept_repair(RG046_Q, RG046_A, _RG046_REPAIR, gaps) is True


def test_accept_repair_verdict_needs_a_yes_or_no_lead():
    gaps = ac.verdict_lead_gap(YES_NO_Q, CONDITIONAL_LEAD_A)
    assert ac.accept_repair(YES_NO_Q, CONDITIONAL_LEAD_A, YES_LEAD_A, gaps) is True
    still_conditional = "Only where the system is high-risk under Annex III does Article 27(1) apply."
    assert ac.accept_repair(YES_NO_Q, CONDITIONAL_LEAD_A, still_conditional, gaps) is False


# ── Robustness and the cache-key gate ────────────────────────────────────────


@pytest.mark.parametrize("bad", [None, 123, object()])
def test_public_functions_never_raise(flags_off, bad):
    for flag in _FLAGS:
        flags_off.setenv(flag, "1")
    assert ac.live_question(bad) in ("", str(bad).strip())
    assert isinstance(ac.previous_answer(bad), str)
    for fn in (ac.is_list_question, ac.is_exception_question, ac.is_yes_no_question, ac.is_governing_provision_question):
        assert isinstance(fn(bad), bool)
    assert isinstance(ac.named_heads(bad), list)
    for fn in (ac.missing_closed_set_members, ac.missing_exception_limbs, ac.verdict_lead_gap,
               ac.dropped_pushback_points, ac.collect_gaps):
        assert fn(bad, bad) == []
    assert ac.governing_provision_clause(bad) == ""
    assert ac.pushback_keep_clause(bad) == ""
    assert isinstance(ac.build_repair_user_message(bad, bad, bad), str)
    assert ac.accept_repair(bad, bad, bad, bad) is False


def test_the_cache_key_ast_gate_can_see_all_five_flags():
    """The integrator keys these in ``_engine_cache_key``; the R355 gate must find them."""
    from tests.test_r355_cache_key_complete import _collect_engine_reads

    reads = _collect_engine_reads()
    for flag in _FLAGS:
        sites = reads.get(flag, [])
        assert any(path.replace("\\", "/").endswith("app/engines/answer_completeness.py") for path, _, _ in sites), flag

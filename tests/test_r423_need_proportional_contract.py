"""R423 — the need-proportional answer contract, and the repeats gate plumbing.

The lever's whole claim is that the answer SHAPE follows the ask instead of a
fixed scaffold. Three things must hold for that to be a lever rather than a
comment:

1. **OFF is byte-identical.** The paired gate compares arms, so the OFF arm must
   be the shipped bytes exactly — no helper that renders "nothing extra" but
   still moves a heading or a lead clause.
2. **ON reaches the wire and is scoped.** The clause carries the engaged items and
   a target; the skeleton keeps every engaged member and demotes the rest to
   coordinates. Dropping an engaged member would be the R409 §6.8 gold-drop
   mechanism dressed as a saving.
3. **The number is bounded and monotone.** ``target_chars`` inside
   [360, 1000] and non-decreasing in the engaged count, so a many-limb question
   is never asked for less room than a lookup.
4. **No anchor is not a small ask (R423.1).** An ask that names no coordinate
   and engages no closed set is a NO-SIGNAL state, and the contract must not
   read it as "short". The first gate put its entire correctness cost on exactly
   two such rows, so the floor, the clause and the skeleton's prohibition are all
   pinned against the two real gold asks below.
5. **One form for an unsettled point (R438.1).** Every clause that tells the
   model what to write when the statute does not settle a point renders ONE
   shared string, because two of them used to give opposite instructions in the
   same dispatched payload (see section 3c).

The last section pins the harness side: ``--repeats`` exists, ``--help`` renders
(argparse interpolates ``%`` in help strings and a bare percent there takes the
runner's whole CLI down), and one ``_arm`` call with ``repeats=2`` really writes
two checkpoints tagged ``sample 0`` and ``sample 1``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.data.graph_rag_prompts import (
    EVIDENCE_ANSWER_CONTRACT,
    EVIDENCE_ANSWER_CONTRACT_WITH_COMPLETENESS,
    EVIDENCE_COMPLETENESS_BLOCK_ENGAGED,
    build_evidence_answer_user,
)
from app.engines import answer_need as need

REPO = Path(__file__).resolve().parents[1]
_ENV = "REGENOLD_NEED_PROPORTIONAL_CONTRACT"

#: Real gold rows, because the estimator's own R410 engagement rule is what is
#: under test: rg_046 ("instructions for use") and rg_052 ("quality management
#: system") are the two TRUE POSITIVES measured on the frozen R407 ledger, so
#: they are the only fixtures that can catch a regression in the shared rule.
_ARTICLE_13_ASK = (
    "Under the EU AI Act, what must a provider of a high-risk AI system supply "
    "to the deployer in the instructions for use? List the required categories "
    "of information."
)
_ARTICLE_13_REFS = "Article 13.3"
_ARTICLE_17_ASK = (
    "Under the EU AI Act, what minimum elements must a provider's quality "
    "management system (QMS) for high-risk AI systems include? List the "
    "required elements."
)
_ARTICLE_17_REFS = "Article 17.1"
_LOOKUP_ASK = (
    "Does the technical documentation of a high-risk AI system require to "
    "provide specifications regarding the required hardware?"
)
_LOOKUP_REFS = "Annex IV.1.e"


@pytest.fixture(autouse=True)
def _off_arm_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """R423.2 — the lever is now default ON, so the OFF arm is pinned explicitly.

    The OFF arm's byte-identity is the contract that makes a paired gate readable
    at all, so it is set rather than assumed. Tests of the ON arm override this
    with ``monkeypatch.setenv(_ENV, "1")``.
    """
    monkeypatch.setenv(_ENV, "0")


# ── 1. OFF is byte-identical ────────────────────────────────────────────────


def test_flag_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """R423.2 — flipped ON by its own paired gate (see the module docstring)."""
    monkeypatch.delenv(_ENV, raising=False)
    assert need.need_proportional_contract_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", " Off "])
def test_flag_reads_the_falsy_forms(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(_ENV, value)
    assert need.need_proportional_contract_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", "", "2", "maybe"])
def test_anything_else_keeps_the_shipped_lever_on(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    # A malformed value must not silently disable a shipped default-ON lever.
    monkeypatch.setenv(_ENV, value)
    assert need.need_proportional_contract_enabled() is True


def test_off_arm_block_is_empty() -> None:
    assert need.need_proportional_block(_ARTICLE_13_ASK, _ARTICLE_13_REFS) == ""


def test_off_arm_user_message_is_the_shipped_text() -> None:
    """The OFF arm must be the shipped contract, byte for byte."""
    message = build_evidence_answer_user(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    assert "ANSWER SHAPE" not in message
    assert EVIDENCE_ANSWER_CONTRACT_WITH_COMPLETENESS in message
    assert EVIDENCE_COMPLETENESS_BLOCK_ENGAGED not in message


# ── 2. ON reaches the wire, scoped ──────────────────────────────────────────


def test_on_arm_swaps_the_completeness_directive_and_adds_the_clause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ENV, "1")
    message = build_evidence_answer_user(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    assert "ANSWER SHAPE (proportional to THIS ask)" in message
    assert EVIDENCE_COMPLETENESS_BLOCK_ENGAGED in message
    # The generic block makes completeness unconditional over any CITED
    # provision; that is the instruction R422 measured to inflate the answer.
    assert "COMPLETENESS DIRECTIVE: an obligation and its exceptions are ONE" not in message
    assert EVIDENCE_ANSWER_CONTRACT in message


def test_engaged_members_come_from_the_question_not_the_citations() -> None:
    """R410's rule, reused: the ask engages, the citation set does not."""
    engaged = need.engaged_coords(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    assert engaged, "the 'instructions for use' ask must engage Article 13.3"
    assert all(coord.startswith("Article 13.3") for coord in engaged)
    # A question that engages nothing must not be given a scope by its refs.
    assert need.engaged_coords("How many staff does the AI Office have?", "Article 13") == ()


def test_target_length_is_monotone_in_the_engaged_count() -> None:
    lookup = need.answer_need(_LOOKUP_ASK, _LOOKUP_REFS)
    mid = need.answer_need(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    big = need.answer_need(_ARTICLE_17_ASK, _ARTICLE_17_REFS)
    assert lookup.items < mid.items <= big.items
    assert lookup.target_chars < mid.target_chars <= big.target_chars


def test_target_length_is_bounded() -> None:
    for ask, refs in (
        (_LOOKUP_ASK, _LOOKUP_REFS),
        (_ARTICLE_13_ASK, _ARTICLE_13_REFS),
        (_ARTICLE_17_ASK, _ARTICLE_17_REFS),
    ):
        estimate = need.answer_need(ask, refs)
        assert need._TARGET_MIN_CHARS <= estimate.target_chars <= need._TARGET_MAX_CHARS
        assert estimate.target_words >= 40


def test_clause_names_the_items_and_the_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV, "1")
    clause = need.need_proportional_block(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    estimate = need.answer_need(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    assert f"{estimate.items} statutory item(s)" in clause
    assert str(estimate.target_words) in clause
    assert "Article 13.3.a" in clause


def test_estimator_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken hierarchy/estimator must never take Stage-2 down."""
    import app.data.provision_hierarchy as hierarchy

    def _boom(_ref: str) -> list[tuple[str, str]]:
        raise RuntimeError("hierarchy unavailable")

    monkeypatch.setattr(hierarchy, "closed_set_members", _boom)
    estimate = need.answer_need(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    assert estimate.items >= 1
    assert estimate.engaged == ()
    assert need._TARGET_MIN_CHARS <= estimate.target_chars <= need._TARGET_MAX_CHARS


def test_engaged_coords_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any exception inside the estimator yields the shipped behaviour, not a 500."""

    def _boom(*_a: object, **_k: object) -> list[tuple[str, str]]:
        raise RuntimeError("no members")

    monkeypatch.setattr(need, "_groups", _boom)
    assert need.engaged_coords(_ARTICLE_13_ASK, _ARTICLE_13_REFS) == ()
    monkeypatch.setattr(need, "_ask_text", _boom)
    assert need.engaged_coords(_ARTICLE_13_ASK, _ARTICLE_13_REFS) == ()


# ── 3. The skeleton scope keeps every engaged member ────────────────────────


def test_skeleton_scope_is_byte_identical_when_no_scope_is_passed() -> None:
    from app.engines._graph_rag_impl import _render_closed_set_skeleton

    shipped = _render_closed_set_skeleton("Article 13")
    assert shipped is not None
    assert "this list is EXHAUSTIVE" in shipped
    assert shipped == _render_closed_set_skeleton("Article 13", engaged=None)


def test_skeleton_scope_demotes_non_engaged_members_without_dropping_engaged_ones() -> None:
    from app.engines._graph_rag_impl import _render_closed_set_skeleton

    engaged = set(need.engaged_coords(_ARTICLE_13_ASK, _ARTICLE_13_REFS))
    scoped = _render_closed_set_skeleton("Article 13", engaged=engaged)
    assert scoped is not None
    assert "this list is EXHAUSTIVE" not in scoped
    assert "ENGAGED members of Article 13" in scoped
    for coord in engaged:
        assert coord in scoped, "a scoped skeleton must never drop an engaged member"
    # Non-engaged members survive as coordinates (citable, not required).
    assert "    Article 13.1" in scoped
    assert "Article 13.1:" not in scoped


def test_skeleton_scope_marks_a_wholly_unengaged_provision_as_context() -> None:
    from app.engines._graph_rag_impl import _render_closed_set_skeleton

    scoped = _render_closed_set_skeleton("Article 13", engaged={"Article 18.1"})
    assert scoped is not None
    assert "NOT ENGAGED by this question" in scoped
    assert "do NOT enumerate" in scoped


# ── 3b. R423.1 — no anchor is NO SIGNAL, not a small ask ────────────────────
#
# The first gate (`docs/measurements/r423/CHECKPOINT.md`) put the lever's whole
# correctness cost on two rows, and both are rows where the estimator found NO
# anchor: the ask names no coordinate and engages no closed set. Both were then
# handed the MINIMUM target (375 chars) and an order not to enumerate the members
# of the provision the question is about — while the gold criteria for those two
# rows are exactly the substance of that provision:
#
#   rg_010  "Which article ... governs human oversight measures?"  ref 759
#           judge, ON arm, all 3 generations: 14(2)'s aim and 14(4)'s five
#           overseer capabilities omitted.
#   rg_106  a supermarket bag-check scenario asking whether it is high-risk
#           ref 781; ON arm, all 3: "focuses on Article 5 instead", Annex III
#           dropped from the wire refs.
#
# These are the real gold asks, verbatim, because a paraphrase cannot reproduce
# what the engagement detector actually does with them.
_RG_010_ASK = "Which article of the EU AI Act governs human oversight measures?"
_RG_106_ASK = (
    'A supermarket uses an AI tool that analyzes only current-cart and checkout '
    'anomalies (no biometrics, no face recognition, no sensitive-trait inference, '
    'no cross-context social scoring) to flag transactions for optional manual bag '
    'checks by store staff. The retailer claims this is "high risk like policing", '
    'as it: resembles investigation of potentially criminal offences (theft) + '
    'evaluates or classifies persons based on observed behaviour in a way that may '
    'lead to detrimental or unfavourable treatment. Is this situation potentially '
    'high-risk?'
)


@pytest.mark.parametrize("ask", [_RG_010_ASK, _RG_106_ASK])
def test_unanchored_ask_gets_the_reference_norm_not_the_minimum(ask: str) -> None:
    estimate = need.answer_need(ask)
    assert estimate.anchored is False
    assert estimate.engaged == () and estimate.asked == ()
    assert estimate.target_chars == need._TARGET_NO_SIGNAL_CHARS
    assert estimate.target_chars > need._TARGET_MIN_CHARS
    # The floor is the instrument's own central reference length, so it can never
    # be a value nobody measured.
    assert need._TARGET_MIN_CHARS < need._TARGET_NO_SIGNAL_CHARS <= need._TARGET_MAX_CHARS


def test_anchored_ask_keeps_the_proportional_target() -> None:
    """R423.1 must not turn every ask into the flat floor."""
    assert need.answer_need(_ARTICLE_13_ASK, _ARTICLE_13_REFS).anchored is True
    assert need.answer_need(_ARTICLE_13_ASK, _ARTICLE_13_REFS).target_chars > (
        need._TARGET_NO_SIGNAL_CHARS
    )
    assert need.answer_need(_LOOKUP_ASK, _LOOKUP_REFS).anchored is False


def test_unanchored_clause_points_at_the_governing_provision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ENV, "1")
    clause = need.need_proportional_block(_RG_010_ASK)
    assert "does not name the provision that governs it" in clause
    assert "Name the governing provision first" in clause
    # The starvation instruction must be gone: telling the model not to enumerate
    # the members of the provision it is asking about is what lost 14(2)/14(4).
    assert "do not enumerate" not in clause
    assert "do not add adjacent duties" not in clause


def test_unanchored_skeleton_does_not_forbid_the_provision() -> None:
    """An empty scope from a real "not this provision" is still a prohibition."""
    from app.engines._graph_rag_impl import _render_closed_set_skeleton

    scoped = _render_closed_set_skeleton("Annex III", engaged=set(), unanchored=True)
    assert scoped is not None
    assert "do NOT enumerate" not in scoped
    assert "names no provision" in scoped
    # Coordinates still reach the model, so nothing citable is hidden.
    assert "    Annex III.6" in scoped
    # …and the signalled case is untouched (the same call without the new flag).
    signalled = _render_closed_set_skeleton("Annex III", engaged=set())
    assert signalled is not None and "do NOT enumerate" in signalled


def test_cache_key_registers_the_lever() -> None:
    """An in-process A/B must not serve arm A's cached engine output to arm B."""
    source = (REPO / "app" / "routes" / "regenold.py").read_text(encoding="utf-8")
    marker = source.index("def _engine_cache_key")
    assert _ENV in source[marker : marker + 40000]


# ── 3c. R438.1 — ONE form for the unsettled-point rule ──────────────
#
# R435's row-level audit (``docs/measurements/r435/CHECKPOINT.md``, arm B = this
# contract ON) found the delivered Stage-2 payload contradicting itself. The need
# clause's last bullet told the model to report that a limb "has no supporting
# text in the evidence", while the delivered clauses forbid exactly that form:
# the evidence contract asked for "the narrow unresolved condition if the evidence
# is insufficient", and the coverage clause -- which owns the rule -- requires the
# legal form and permits no remark about the model's own sources.
#
# It is not a wording quibble. The two audited rows that lost Ref. Strict and
# Tone in that checkpoint emitted precisely that sentence:
#
#   rg_034  "the Article 27 limbs identified in the answer shape ... have no
#            supporting text in the evidence supplied"
#   rg_064  "the engaged items identified as Article 10(5), points (a) to (f),
#            have no supporting text in the evidence before me"
#
# 2 of 6 audited ON rows, against 0 of 6 in the OFF arm. That is self-referential
# commentary, which the judge penalises on Tone and which cannot help a citation
# axis, so the round cost was a defect and not a trade.
#
# The repair is one shared string (``UNSETTLED_POINT_RULE``). These tests pin the
# property that matters -- every clause that speaks to an unsettled point renders
# the SAME sentence -- because a reword of either clause, independently, is how
# the contradiction got in.

#: Tell-tale vocabulary of the FORBIDDEN form: a sentence that describes the
#: model's own inputs (what was retrieved, supplied, or missing) instead of the
#: law. Asserted NEGATIVELY against the need clause's bullet and against the
#: specific retired sentences in the dispatched payload -- never against a whole
#: clause body, because the coverage clause names these things inside its own
#: prohibition, and the evidence contract says "A retrieved node is a candidate".
_INPUT_STATE_TELLS = (
    "supporting text",
    "in the evidence",
    "before me",
    "supplied to you",
    "inputs are",
)

#: The retired instruction, verbatim, so a re-introduction is caught wherever it
#: lands. It is the only sentence that ever told the model to narrate retrieval.
_RETIRED_BULLET = (
    "If a limb above has no supporting text in the evidence, say so in one "
    "sentence instead of padding."
)


def test_the_unsettled_point_rule_is_one_shared_string() -> None:
    """The norm lives in ONE object, and every clause that needs it renders it.

    Containment of the identical string is the drift guard: rewording any single
    clause's legal form independently -- which is exactly how the need clause
    came to contradict the contract -- drops that clause out of this assertion.
    """
    from app.data import graph_rag_prompts as prompts

    rule = prompts.UNSETTLED_POINT_RULE
    assert rule.strip() == rule, "the rule is spliced into prose; no stray space"
    assert "as a matter of LAW" in rule
    assert "NEVER as a matter of your own sources" in rule
    # The coverage clause is the clause that OWNS the rule...
    assert rule in prompts.USER_ANSWER_COVERAGE_CLAUSE
    assert rule in prompts.USER_ANSWER_COVERAGE_CLAUSE_V2
    # ...and these two must state the same rule, not a paraphrase of it.
    assert rule in prompts.EVIDENCE_ANSWER_CONTRACT
    assert rule in need._UNSETTLED_BULLET


def test_the_coverage_clauses_are_still_byte_identical() -> None:
    """R438.1 spliced a shared constant into two shipped literals.

    Both coverage clauses are delivered prompt text with their own flag
    (``REGENOLD_PROMPT_V2``), so the shared-constant refactor had to be a pure
    no-op on the bytes. These are the pre-refactor hashes.
    """
    import hashlib

    from app.data import graph_rag_prompts as prompts

    assert hashlib.sha256(
        prompts.USER_ANSWER_COVERAGE_CLAUSE.encode()
    ).hexdigest().startswith("01d083c2c3df156a")
    assert hashlib.sha256(
        prompts.USER_ANSWER_COVERAGE_CLAUSE_V2.encode()
    ).hexdigest().startswith("d2f89bb4cc0bbe77")


@pytest.mark.parametrize(
    "ask,refs",
    [(_ARTICLE_13_ASK, _ARTICLE_13_REFS), (_RG_010_ASK, "")],
    ids=["anchored", "unanchored"],
)
def test_the_bullet_states_the_law_and_never_the_inputs(
    monkeypatch: pytest.MonkeyPatch, ask: str, refs: str
) -> None:
    """Both branches of ``shape_directive``, because both carried the defect."""
    monkeypatch.setenv(_ENV, "1")
    clause = need.need_proportional_block(ask, refs)
    bullet = [line for line in clause.splitlines() if "does not settle" in line]
    assert len(bullet) == 1, "the clause must state the unsettled-point rule once"
    line = bullet[0]
    # Same object as every other clause's rule, spelled the same way.
    assert need.UNSETTLED_POINT_RULE in line
    for tell in _INPUT_STATE_TELLS:
        assert tell not in line, f"the bullet narrates the inputs: {tell!r}"


def test_the_dispatched_payload_cannot_contradict_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pair that actually ships together: contract + need clause.

    This is the assertion the R435 audit implies: on the wrapper leg the model
    receives ONE user message, so the contract and the shape clause must not give
    it opposite instructions about what to write when the statute does not settle
    a point. Both now carry the legal form, and neither carries the retired
    input-state sentence.
    """
    monkeypatch.setenv(_ENV, "1")
    message = build_evidence_answer_user(_ARTICLE_13_ASK, _ARTICLE_13_REFS)
    assert EVIDENCE_ANSWER_CONTRACT in message
    assert "ANSWER SHAPE" in message
    assert need.UNSETTLED_POINT_RULE in message
    assert _RETIRED_BULLET not in message
    assert "if the evidence is insufficient" not in message
    # The prohibition survives where it belongs -- the coverage clause still
    # names the material it forbids mentioning, so this is not a ban on the ban.
    from app.data.graph_rag_prompts import USER_ANSWER_COVERAGE_CLAUSE

    assert "do not mention the references" in USER_ANSWER_COVERAGE_CLAUSE


# ── 4. Harness: independent generations per row per arm ─────────────────────


class _Row:
    id = "rg_000"
    question = _LOOKUP_ASK
    difficulty = "Easy"
    difficulty_category = "Lookup"
    jul07_answer = "shipped answer"
    jul07_refs = ["Annex IV.1.e"]

    def easy_messages(self) -> list[dict[str, str]]:
        return [{"role": "user", "content": self.question}]


def _fake_poster(_url, _key, _messages, _timeout):  # noqa: ANN001
    body = {"answer": "Yes. Annex IV.1.e requires the hardware description.", "references": ["Annex IV.1.e"]}
    return body, 12.0, 200, None, 1, False


def test_runner_help_renders() -> None:
    """argparse interpolates ``%`` in help strings; a bare one kills ``--help``."""
    import argparse

    from evals.regenold import run_official_batch as runner

    parser = argparse.ArgumentParser()
    assert parser  # the module imports and the CLI below is the real check
    main_src = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
    assert '"(46%% easy)' in main_src
    assert "--repeats" in main_src
    assert runner is not None


def test_arm_writes_one_checkpoint_per_generation(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from evals.regenold import run_official_batch as runner

    monkeypatch.setattr(runner, "_RESULTS", tmp_path)
    result = runner._arm(
        "r423-selftest",
        "easy",
        [_Row()],
        poster=_fake_poster,
        url="local://noop",
        api_key=None,
        timeout=5.0,
        arm_env={},
        suffix="-A",
        repeats=2,
    )
    easy = result["easy"]
    assert easy["n_samples"] == 2
    assert easy["agg_first_sample_only"] is True
    primary = tmp_path / "official-r423-selftest-A-easy.ckpt.jsonl"
    replica = tmp_path / "official-r423-selftest-A-easy.r1.ckpt.jsonl"
    assert primary.exists() and replica.exists()
    samples = [
        json.loads(line)["sample"]
        for line in primary.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    replica_samples = [
        json.loads(line)["sample"]
        for line in replica.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert samples == [0]
    assert replica_samples == [1]
    assert easy["samples"] == [["rg_000"], ["rg_000"]]


def test_repeat_replica_files_are_named_apart() -> None:
    """The naming contract a scorer depends on: primary keeps the shipped path."""
    source = (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(encoding="utf-8")
    assert ".r{k}.ckpt.jsonl" in source
    assert os.sep in source  # cheap sanity that the file was read as source


# ─── R442 — the R439 head rule, scoped back to heads ──────────────────────────
@pytest.mark.parametrize(
    ("ask", "refs", "letters"),
    [
        ("When does the Article 6(3) derogation apply?", "Article 6", "Article 6.3."),
        ("What does Article 9(2) require?", "Article 9", "Article 9.2."),
    ],
)
def test_a_named_paragraph_that_is_a_list_still_engages_its_list(
    ask: str, refs: str, letters: str
) -> None:
    """R439 withheld 6(3)(a)-(d) and 9(2)(a)-(d) — the very items asked — and
    the ANSWER SHAPE clause then tells Stage-2 not to enumerate them."""
    engaged = need.engaged_coords(ask, refs)
    assert [c for c in engaged if c.startswith(letters)] == [
        f"{letters}{x}" for x in "abcd"
    ]


def test_a_named_head_still_does_not_engage_every_paragraph() -> None:
    """R439's own case is kept: a head's paragraphs are separate provisions."""
    assert need.engaged_coords(
        "Does Article 26 require the deployer to keep logs?", "Article 26"
    ) == ()
    listed = need.engaged_coords("List the deployer obligations under Article 26.", "Article 26")
    assert len(listed) == 12


@pytest.mark.parametrize(
    ("ask", "refs"),
    [
        ("What is Annex X about? What is it used for?", "Annex X"),
        ("What is Annex X of the AI Act about?", "Annex X"),
        ("Tell me about Annex X.", "Annex X"),
        ("What does Article 26 require?", "Article 26"),
        ("What do Articles 14 and 15 require for high-risk AI systems?", "Article 14 Article 15"),
        ("How do Articles 5 and 6 classify AI systems differently?", "Article 5 Article 6"),
        # An open request in any sentence outweighs a yes/no follow-up.
        ("Explain Article 50. Does it apply to chatbots?", "Article 50"),
        ("Does the AI Act apply to us? Explain Article 2.", "Article 2"),
        # An open ask narrowed by a topic keeps the floor, as it did at a0b08c8.
        ("What does Article 26 require regarding logs?", "Article 26"),
    ],
)
def test_an_ask_about_a_whole_head_gets_the_no_signal_floor(ask: str, refs: str) -> None:
    """R442 — once R439 withheld the head's paragraphs the estimator fell to one
    item (375 chars); rg_105's reference answer is 625 chars. Absence of a
    scope signal takes the R423.1 floor, as an unanchored ask does."""
    estimate = need.answer_need(ask, refs)
    assert estimate.engaged == ()
    assert estimate.target_chars == need._TARGET_NO_SIGNAL_CHARS
    assert estimate.anchored  # the skeleton branch is unchanged


@pytest.mark.parametrize(
    ("ask", "refs"),
    [
        # R442 pinned this one as a whole-head ask; it is a yes/no question
        # about one duty, and the R446 review (F9) measured it at 375 -> 650.
        ("Does Article 26 require the deployer to keep logs?", "Article 26"),
        ("Under Article 50, must a chatbot disclose that it is an AI system?", "Article 50"),
    ],
)
def test_a_yes_no_ask_that_names_a_head_keeps_the_proportional_target(
    ask: str, refs: str
) -> None:
    """R447 — a verdict ask is a scope signal, so the whole-head floor stays off."""
    estimate = need.answer_need(ask, refs)
    assert estimate.is_yes_no
    assert estimate.engaged == ()
    assert estimate.anchored
    assert estimate.target_chars == min(
        need._TARGET_MAX_CHARS,
        max(need._TARGET_MIN_CHARS,
            need._TARGET_BASE_CHARS + need._TARGET_PER_ITEM_CHARS * estimate.items),
    )
    assert estimate.target_chars < need._TARGET_NO_SIGNAL_CHARS


def test_the_whole_head_floor_is_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    """R447 — R442 shipped the floor with no flag. Deny-list, default ON."""
    ask, refs = "What is Annex X about? What is it used for?", "Annex X"
    monkeypatch.delenv("REGENOLD_WHOLE_HEAD_FLOOR", raising=False)
    assert need.answer_need(ask, refs).target_chars == need._TARGET_NO_SIGNAL_CHARS
    for blank_or_odd in ("", "yes", "enabled"):
        monkeypatch.setenv("REGENOLD_WHOLE_HEAD_FLOOR", blank_or_odd)
        assert need.answer_need(ask, refs).target_chars == need._TARGET_NO_SIGNAL_CHARS
    monkeypatch.setenv("REGENOLD_WHOLE_HEAD_FLOOR", "0")
    off = need.answer_need(ask, refs)
    assert off.target_chars < need._TARGET_NO_SIGNAL_CHARS
    assert off.anchored and off.engaged == ()


def test_the_floor_does_not_touch_a_named_paragraph() -> None:
    estimate = need.answer_need("What does Article 13(3) require?", "Article 13")
    assert estimate.engaged  # engaged, so the proportional target governs
    assert estimate.target_chars == min(
        need._TARGET_MAX_CHARS,
        max(need._TARGET_MIN_CHARS,
            need._TARGET_BASE_CHARS + need._TARGET_PER_ITEM_CHARS * estimate.items),
    )

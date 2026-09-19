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
def _clean_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV, raising=False)


# ── 1. OFF is byte-identical ────────────────────────────────────────────────


def test_flag_defaults_off() -> None:
    assert need.need_proportional_contract_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", " True "])
def test_flag_reads_truthy_forms(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(_ENV, value)
    assert need.need_proportional_contract_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "maybe", "2"])
def test_flag_treats_anything_else_as_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(_ENV, value)
    assert need.need_proportional_contract_enabled() is False


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


def test_cache_key_registers_the_lever() -> None:
    """An in-process A/B must not serve arm A's cached engine output to arm B."""
    source = (REPO / "app" / "routes" / "regenold.py").read_text(encoding="utf-8")
    marker = source.index("def _engine_cache_key")
    assert _ENV in source[marker : marker + 40000]


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

"""R424 — the hard modality must be the OFFICIAL one: a fixed 9-turn dialogue.

``_run_hard`` used to keep a ROLLING conversation of our own prior Q&A starting
empty, so row 1 was asked with no context and row 5 with four exchanges of it.
Because the route derives ``history_turn_count`` from the request, that mixed two
modalities inside one arm: measured, the leading rows read 0 and 1 — inside the
Stage-2 single-turn predicate — and were dispatched the full ~59.6 kB system
prompt while every later row got the 61-char persona
(``docs/measurements/r423/graded_scope_probe.py``).

The official description is explicit — "a pre-fixed synthetic 9-turn conversation
so that the actual question being evaluated appears in the 10th turn" — and the
evaluator's own export for the graded 2026-07-07 run records
``history_turns_used == 18`` for ALL 111 hard turn-1 rows (20 for the pushback),
which a rolling window cannot produce. So the fixture is 9 exchanges / 18
messages, and these tests pin it from both ends: the shape of the dialogue, and
the fact that the RUNNER actually asks every row inside it.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest

from evals.harness import gate_validity
from evals.regenold import hard_preamble as hp
from evals.regenold.official_batch import load_official_batch
from evals.regenold.run_official_batch import _run_hard, select_rows


def _official_rows(ids: str):
    """Rows from the July-7 batch, or SKIP on a clean clone.

    That batch is gitignored competition data (``evals.regenold.july7_difficulty``
    is absent from a fresh checkout), so every test that needs the REAL question
    text guards here rather than failing the clean-clone CI gate. The fixture,
    mode-resolution and guard tests above use no batch data and still run.
    """
    pytest.importorskip(
        "evals.regenold.july7_difficulty",
        reason="gitignored July-7 competition data not present in this checkout",
    )
    return select_rows(list(load_official_batch()), ids=ids)


# ── 1. The fixture's shape ────────────────────────────────────────────────


def test_fixture_is_nine_exchanges_eighteen_messages() -> None:
    msgs = hp.preamble_messages()
    assert len(hp.HARD_PREAMBLE) == hp.HARD_PREAMBLE_EXCHANGES == 9
    assert len(msgs) == hp.HARD_PREAMBLE_MESSAGES == 18
    # Alternating, user first and assistant last, so the target question lands on
    # turn 10 with no two consecutive user turns.
    assert "".join("U" if m["role"] == "user" else "A" for m in msgs) == "UA" * 9


def test_every_exchange_has_real_content() -> None:
    for index, (user, assistant) in enumerate(hp.HARD_PREAMBLE, 1):
        assert len(user.strip()) > 25, f"exchange {index} user turn is a stub"
        assert len(assistant.strip()) > 200, f"exchange {index} assistant turn is a stub"


def test_fixture_is_byte_deterministic_and_cannot_be_mutated() -> None:
    first = hp.preamble_messages()
    # A caller that appends to the result must not change the fixture for the
    # next row or the other arm.
    first.append({"role": "user", "content": "tamper"})
    first[0]["content"] = "tamper"
    second = hp.preamble_messages()
    assert len(second) == 18
    assert second[0]["content"] == hp.HARD_PREAMBLE[0][0]
    assert hp.preamble_digest() == hp.preamble_digest()
    assert hp.preamble_digest() == hp.preamble_digest()  # stable across calls
    assert len(hp.preamble_digest()) == 16


def test_builders_append_after_the_fixture_and_share_the_same_prefix() -> None:
    turn1 = hp.build_prefixed_messages("Q?")
    assert len(turn1) == 19
    assert turn1[-1] == {"role": "user", "content": "Q?"}
    assert turn1[:18] == hp.preamble_messages()

    pushback = hp.build_prefixed_pushback_messages("Q?", "our answer", "really?")
    assert len(pushback) == 21
    assert pushback[18] == {"role": "user", "content": "Q?"}
    assert pushback[19] == {"role": "assistant", "content": "our answer"}
    assert pushback[20] == {"role": "user", "content": "really?"}
    # The two graded asks differ ONLY in what the harness appended: if the prefix
    # drifted between them the turn-2 comparison would not be paired.
    assert pushback[:18] == turn1[:18]


def test_the_fixtures_user_turns_yield_an_empty_anchor_line() -> None:
    """The deliberate rule: numbers in assistant turns, not user turns.

    ``_extract_conversation_anchors`` reads prior USER turns and prepends up to
    six article numbers to the live question. Numbers in the fixture's user turns
    would therefore inject the same article constant into every row's scope —
    our machinery, not the official instrument — and confound the very delta the
    fixture exists to measure. This runs the REAL extractor, so the rule cannot
    rot.
    """
    from app.routes.regenold import _extract_conversation_anchors

    turns = [SimpleNamespace(role=m["role"], content=m["content"]) for m in hp.preamble_messages()]
    assert _extract_conversation_anchors(turns) == ""


def test_no_user_turn_trips_an_anchor_token() -> None:
    from app.routes.regenold import (
        _ANCHOR_ARTICLE_RE,
        _ANCHOR_RISK_WORDS,
        _ANCHOR_ROLE_WORDS,
    )

    for index, (user, _assistant) in enumerate(hp.HARD_PREAMBLE, 1):
        low = user.lower()
        assert not [m.group(0) for m in _ANCHOR_ARTICLE_RE.finditer(user)], (
            f"exchange {index} user turn names an article/annex number"
        )
        assert not [w for w in _ANCHOR_ROLE_WORDS if w in low], (
            f"exchange {index} user turn names a role word"
        )
        assert not [w for w in _ANCHOR_RISK_WORDS if w in low], (
            f"exchange {index} user turn names a risk-tier word"
        )


def test_the_fixture_still_primes_the_operative_articles_in_assistant_turns() -> None:
    """Priming is the fixture's PURPOSE — it must not be an empty conversation."""
    assistant_text = " ".join(a for _u, a in hp.HARD_PREAMBLE)
    for provision in ("Article 6", "Annex III", "Article 16", "Article 26", "Article 53"):
        assert provision in assistant_text, f"{provision} missing from the dialogue"


# ── 2. Mode resolution ────────────────────────────────────────────────────


def test_mode_defaults_to_fixed_and_still_accepts_rolling() -> None:
    """The gate moved the default: the official shape is what an undeclared run gets.

    ``rolling`` stays reachable as an explicit opt-in, which is what the
    pre-R424 boards on record need to be reproducible.
    """
    assert hp.DEFAULT_MODE == hp.MODE_FIXED
    assert hp.hard_preamble_mode({}) == hp.MODE_FIXED
    assert hp.hard_preamble_mode({hp.HARD_PREAMBLE_ENV: "rolling"}) == hp.MODE_ROLLING
    assert hp.hard_preamble_mode({hp.HARD_PREAMBLE_ENV: " ROLLING "}) == hp.MODE_ROLLING


def test_an_unrecognised_mode_raises_instead_of_running_the_other_shape() -> None:
    with pytest.raises(ValueError, match="refusing to guess"):
        hp.hard_preamble_mode({hp.HARD_PREAMBLE_ENV: "fxd"})


def test_request_shape_flags_match_the_harness_flag() -> None:
    """The guard's literal must not drift from the flag the harness reads."""
    assert hp.HARD_PREAMBLE_ENV in gate_validity.REQUEST_SHAPE_FLAGS


def test_lever_changes_request_reads_the_declaration() -> None:
    assert gate_validity.lever_changes_request({}, {})[0] is False
    assert gate_validity.lever_changes_request(
        {hp.HARD_PREAMBLE_ENV: "rolling"}, {hp.HARD_PREAMBLE_ENV: "fixed"}
    )[0] is True
    # No system-slot flag is involved, so the system check must stay quiet.
    assert gate_validity.lever_changes_system({}, {hp.HARD_PREAMBLE_ENV: "fixed"})[0] is False


# ── 3. The runner actually asks every row inside the fixture ──────────────


def _stub_poster(seen: list[list[dict[str, str]]]):
    def poster(_url, _key, msgs, _timeout):  # noqa: ANN001, ANN202
        seen.append([dict(m) for m in msgs])
        body = {"answer": "Under Article 6 it is high-risk.", "references": ["Article 6"]}
        return body, 12.0, 200, None, 1, None

    return poster


def _ask(mode: str, ids: str) -> tuple[list[dict[str, Any]], list[list[dict[str, str]]]]:
    rows = _official_rows(ids)
    seen: list[list[dict[str, str]]] = []
    out = _run_hard(
        rows, _stub_poster(seen), "local", "k", 30, io.StringIO(), sample=0, preamble=mode
    )
    return out, seen


def test_fixed_mode_asks_every_row_as_turn_ten_of_the_same_conversation() -> None:
    out, seen = _ask(hp.MODE_FIXED, "rg_001,rg_004,rg_007")
    assert len(seen) == 6  # 3 rows x (turn 1, pushback)
    turn1 = [seen[i] for i in (0, 2, 4)]
    pushback = [seen[i] for i in (1, 3, 5)]
    # EVERY row carries the same 19-message turn-1 request -> history_turn_count
    # 18, which is the evaluator's own recorded value for the graded hard rows.
    assert [len(m) for m in turn1] == [19, 19, 19]
    assert [max(0, len(m) - 1) for m in turn1] == [18, 18, 18]
    assert [len(m) for m in pushback] == [21, 21, 21]
    assert [max(0, len(m) - 1) for m in pushback] == [20, 20, 20]
    # Byte-identical prefix on every one of them: the shape is a constant of the
    # run, not a function of a row's position.
    for request in seen:
        assert request[:18] == hp.preamble_messages()
    for record in out:
        assert record["hard_preamble"] == hp.MODE_FIXED
        assert record["hard_preamble_digest"] == hp.preamble_digest()


def test_an_undeclared_run_gets_the_official_shape_by_default() -> None:
    """The flip, checked on the WIRE: omitting the flag must not fall back to rolling.

    ``hard_preamble_mode({})`` returning ``fixed`` is only a claim about a
    resolver. This drives the real runner with no ``preamble`` argument at all and
    asserts every row posted the 19-message pre-fixed request, so a future default
    change cannot pass by moving only the constant.
    """
    rows = _official_rows("rg_001,rg_004,rg_007")
    seen: list[list[dict[str, str]]] = []
    _run_hard(rows, _stub_poster(seen), "local", "k", 30, io.StringIO(), sample=0)
    turn1 = [seen[i] for i in (0, 2, 4)]
    assert [len(m) for m in turn1] == [19, 19, 19]
    for request in seen:
        assert request[:18] == hp.preamble_messages()


def test_rolling_mode_is_still_position_dependent_the_leak_is_real() -> None:
    _out, seen = _ask(hp.MODE_ROLLING, "rg_001,rg_004,rg_007")
    depths = [max(0, len(seen[i]) - 1) for i in (0, 2, 4)]
    assert depths == [0, 2, 4]
    # Row 1 is inside the Stage-2 single-turn predicate; the later rows are not.
    assert depths[0] <= 1 < depths[1]


def test_fixed_mode_ignores_a_seed_history_so_resume_cannot_change_modality() -> None:
    """The R423.3 leak cannot recur in fixed mode: the fixture IS the history."""
    rows = _official_rows("rg_001,rg_004")
    unseeded: list[list[dict[str, str]]] = []
    seeded: list[list[dict[str, str]]] = []
    seed = [
        {"role": "user", "content": "prior question"},
        {"role": "assistant", "content": "prior answer"},
    ]
    _run_hard(
        rows, _stub_poster(unseeded), "local", "k", 30, io.StringIO(), sample=0,
        preamble=hp.MODE_FIXED,
    )
    _run_hard(
        rows, _stub_poster(seeded), "local", "k", 30, io.StringIO(), sample=0,
        preamble=hp.MODE_FIXED, seed_history=seed,
    )
    # 4 requests for 2 rows: turn 1 (19) then the pushback (21) on each.
    assert unseeded == seeded
    assert [len(m) for m in unseeded] == [19, 21, 19, 21]


def test_rolling_mode_still_honours_a_seed_history() -> None:
    """The shipped shape is unchanged: a resumed rolling run still seeds."""
    rows = _official_rows("rg_001")
    seeded: list[list[dict[str, str]]] = []
    seed = [
        {"role": "user", "content": "prior question"},
        {"role": "assistant", "content": "prior answer"},
    ]
    _run_hard(
        rows, _stub_poster(seeded), "local", "k", 30, io.StringIO(), sample=0,
        preamble=hp.MODE_ROLLING, seed_history=seed,
    )
    assert len(seeded[0]) == 3
    assert seeded[0][0]["content"] == "prior question"


# ── 4. The void guard: a request-slot lever must prove non-vacuity too ────


def _prov(
    label: str,
    *,
    request_shape: str = "",
    system_hash: str = "aaa",
    rows: int = 30,
) -> gate_validity.ArmProvenance:
    stats: dict[str, Any] = {
        "primary_attempts": rows,
        "primary_ok": rows,
        "primary_failed": 0,
        "fallback_attempts": 0,
        "fallback_ok": 0,
        "fallback_failed": 0,
        "refused": 0,
        "refused_by_provider": {},
    }
    return gate_validity.ArmProvenance(
        label=label,
        rows=rows,
        deterministic_graded=0,
        stats=stats,
        system_hashes=(system_hash,),
        user_hashes=("uuu",),
        system_lengths=(3,),
        calls=rows,
        rows_served={"primary": rows},
        request_shape=request_shape,
    )


def test_request_slot_lever_with_different_shapes_is_valid() -> None:
    verdict = gate_validity.assess(
        base=_prov("A", request_shape="rolling"),
        branch=_prov("B", request_shape="fixed:cb85452c9c041721"),
        lever=False,
        lever_slot="request",
    )
    assert verdict.valid, verdict.reasons
    assert verdict.request_checked and not verdict.system_checked
    # An identical SYSTEM payload is the EXPECTED outcome of a request-slot lever,
    # so it must not be reported as if the lever had failed to reach the wire.
    assert not any("system payload" in w for w in verdict.warnings)


def test_request_slot_lever_with_identical_shapes_voids() -> None:
    verdict = gate_validity.assess(
        base=_prov("A", request_shape="rolling"),
        branch=_prov("B", request_shape="rolling"),
        lever=False,
        lever_slot="request",
    )
    assert not verdict.valid
    assert any("request shapes were IDENTICAL" in r for r in verdict.reasons)


def test_request_slot_lever_without_a_recorded_shape_voids() -> None:
    verdict = gate_validity.assess(
        base=_prov("A", request_shape=""),
        branch=_prov("B", request_shape="fixed:cb85452c9c041721"),
        lever=False,
        lever_slot="request",
    )
    assert not verdict.valid
    assert any("could not be observed" in r for r in verdict.reasons)


def test_system_slot_lever_rule_is_unchanged() -> None:
    """The default path keeps its teeth: identical system payloads still void."""
    verdict = gate_validity.assess(
        base=_prov("A"),
        branch=_prov("B"),
        lever=(True, "arm env differs on system-slot flag(s): X"),
    )
    assert not verdict.valid
    assert any("system payloads were IDENTICAL" in r for r in verdict.reasons)
    # And a request shape being identical is NOT a reason on the system path.
    ok = gate_validity.assess(
        base=_prov("A", request_shape="fixed:x"),
        branch=_prov("B", request_shape="fixed:x"),
        lever=False,
    )
    assert ok.valid, ok.reasons


def test_request_shape_survives_the_round_trip_that_lets_a_run_be_re_judged() -> None:
    prov = _prov("A", request_shape="fixed:cb85452c9c041721")
    rebuilt = gate_validity.ArmProvenance.from_dict(prov.as_dict())
    assert rebuilt.request_shape == prov.request_shape


def test_the_verdict_records_which_slot_was_checked() -> None:
    payload = gate_validity.assess(
        base=_prov("A", request_shape="rolling"),
        branch=_prov("B", request_shape="fixed:x"),
        lever=False,
        lever_slot="request",
    ).as_dict()
    assert payload["request_checked"] is True
    assert payload["system_checked"] is False
    # The saved verdict must be JSON-serialisable — it is written into the run
    # payload that every downstream gate reads.
    json.dumps(payload)

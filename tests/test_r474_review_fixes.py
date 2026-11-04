"""R474 - fixes from the review of the R473 agent work (PRs #510 / #511).

Each test pins a defect found by EXECUTING the merged code, not by reading it.

1. ``REGENOLD_HARD_PREAMBLE=published`` was accepted by ``hard_preamble_mode()``
   (R473 added the mode to ``MODES``) but ``run_official_batch`` only knew
   ``fixed`` and ``rolling``: every other mode silently ran the ROLLING pre-R424
   shape, while the checkpoint was stamped ``"hard_preamble": "published"`` with
   an empty digest. That is the R422 failure the resolver's own docstring names -
   a run that measured something other than what its label says. Before R473 the
   same value raised ``ValueError``, so the merge turned a loud failure into a
   silent mislabel.
"""
from __future__ import annotations

import io
from typing import Any

import pytest

from evals.regenold import hard_preamble as hp
from evals.regenold import run_official_batch as rob
from evals.regenold.official_batch import OfficialRow


def _rows(n: int = 3) -> list[OfficialRow]:
    return [
        OfficialRow(
            id=f"t_{i:03d}",
            question=f"Does Article {i + 5} of the EU AI Act apply to scenario {i}?",
            question_hash=f"h{i}",
            jul07_answer="",
            jul07_refs=(),
            jul07_confidence=None,
            jul07_retrieval_path="",
            jul07_scope_reason="",
        )
        for i in range(n)
    ]


def _poster(seen: list[list[dict[str, str]]]):
    def poster(_url, _key, msgs, _timeout):  # noqa: ANN001, ANN202
        seen.append([dict(m) for m in msgs])
        body = {"answer": "Under Article 6 it is high-risk.", "references": ["Article 6"]}
        return body, 12.0, 200, None, 1, None

    return poster


def _run(mode: str, n: int = 3, **kw: Any):
    seen: list[list[dict[str, str]]] = []
    out = rob._run_hard(
        _rows(n), _poster(seen), "local", "k", 30, io.StringIO(),
        sample=0, preamble=mode, **kw,
    )
    return out, seen


def test_published_mode_posts_the_published_dialogue_on_every_row() -> None:
    out, seen = _run(hp.MODE_PUBLISHED, 3)
    assert len(seen) == 6  # 3 rows x (turn 1, pushback)
    published = hp.preamble_messages(profile=hp.MODE_PUBLISHED)
    assert published != hp.preamble_messages(), "fixtures must differ or this test is vacuous"
    for request in seen:
        # The 18-message published dialogue is the prefix of EVERY request,
        # whatever the row's position in the run.
        assert request[:18] == published
    assert [len(m) for m in (seen[0], seen[2], seen[4])] == [19, 19, 19]
    assert [len(m) for m in (seen[1], seen[3], seen[5])] == [21, 21, 21]
    # The pushback is the released template with the question re-asked verbatim.
    for i, row in enumerate(_rows(3)):
        assert seen[2 * i + 1][-1]["content"] == row.pushback_content()
        assert seen[2 * i + 1][-1]["content"] == hp.format_published_pushback(row.question)


def test_published_mode_records_its_own_label_and_digest() -> None:
    out, _seen = _run(hp.MODE_PUBLISHED, 2)
    expected = hp.preamble_digest(profile=hp.MODE_PUBLISHED)
    assert expected and expected != hp.preamble_digest()
    for record in out:
        assert record["hard_preamble"] == hp.MODE_PUBLISHED
        # An empty digest is how a mislabelled run hid: the paired gate cannot
        # refuse a pair whose request shapes differ if the digest is blank.
        assert record["hard_preamble_digest"] == expected


def test_published_mode_ignores_a_seed_history_like_fixed_does() -> None:
    seed = [
        {"role": "user", "content": "prior question"},
        {"role": "assistant", "content": "prior answer"},
    ]
    _out, unseeded = _run(hp.MODE_PUBLISHED, 2)
    _out, seeded = _run(hp.MODE_PUBLISHED, 2, seed_history=seed)
    assert unseeded == seeded


@pytest.mark.parametrize("mode", hp.MODES)
def test_every_mode_the_resolver_accepts_is_honoured_on_the_wire(mode: str) -> None:
    """The completeness pin: accepting a mode and ignoring it is the bug.

    Each accepted mode must (a) post a request whose shape matches the mode and
    (b) stamp the row with that mode's own label. A future fourth mode that is
    added to ``MODES`` but not wired into the runner fails here.
    """
    out, seen = _run(mode, 3)
    turn1_depths = [max(0, len(seen[i]) - 1) for i in (0, 2, 4)]
    if mode == hp.MODE_ROLLING:
        assert turn1_depths == [0, 2, 4]  # position dependent: the pre-R424 leak
    else:
        assert turn1_depths == [18, 18, 18]
        expected_prefix = hp.preamble_messages(profile=None if mode == hp.MODE_FIXED else mode)
        assert all(r[:18] == expected_prefix for r in seen)
    assert {r["hard_preamble"] for r in out} == {mode}


def test_request_shape_provenance_names_the_published_shape() -> None:
    """The arm-level provenance string feeds the paired gate's non-vacuity check."""
    assert rob._request_shape(hp.MODE_ROLLING) == hp.MODE_ROLLING
    assert rob._request_shape(hp.MODE_FIXED) == f"fixed:{hp.preamble_digest()}"
    assert (
        rob._request_shape(hp.MODE_PUBLISHED)
        == f"published:{hp.preamble_digest(profile=hp.MODE_PUBLISHED)}"
    )
    shapes = {rob._request_shape(m) for m in hp.MODES}
    assert len(shapes) == len(hp.MODES), "two modes must never share a request shape"


# ---------------------------------------------------------------------------
# 2. R473's collapse-before-budget changed leaves it had no reason to touch.
#
# R473 collapsed a curated answer's multi-leaf clusters BEFORE the reference
# budget cut, so "4 sub-points of one article cannot evict the remaining distinct
# declared articles". That defect is real: the hospital verdict's `Article 26`
# plus its four leaves filled all five budget slots and evicted `Article 27`,
# `86`, `25`, `13` (the wire was `['Article 26.5']`). But the collapse is
# UNCONDITIONAL, and executing both builds over 1,733 non-official questions
# showed it also moves a family where nothing is evicted: `hardware_techdoc`
# declares a head and two leaves (4 refs, budget 5). Collapsing first lets the
# head merge with a retrieval-derived extra leaf (`Annex IV.2`), which displaces
# the deepener's question-aware pick (`Annex IV.1`, the hardware point). The
# question asks about hardware; the answer's own point 1(e) is the hardware point.
#
# The repair collapses first ONLY when that keeps more declared heads.
# ---------------------------------------------------------------------------

from tests.test_r115_followups import _wire  # noqa: E402  (hermetic wire call)

HARDWARE_QUESTIONS = [
    "Does the technical documentation of a high-risk AI system require specifications regarding the required hardware?",
    "Does the technical documentation require hardware specifications?",
    "Does the technical documentation require hardware specs?",
    "Is information about required hardware part of the technical documentation?",
]

_HW_DECLARED = ("Article 11", "Annex IV", "Annex IV.1.e", "Annex IV.2.c")
_HW_CANDIDATES = ["Article 11", "Annex IV.1.e", "Annex IV.2.c", "Annex IV", "Annex IV.2"]
_HW_ANSWER = (
    "Yes: under Article 11, a provider must draw up technical documentation containing "
    "the information set out in Annex IV, which expressly requires a description of the "
    "hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part "
    "of the system's development description, the computational resources used to develop, "
    "train, test and validate it (Annex IV point 2(c))."
)

_HOSP_DECLARED = (
    "Article 26", "Article 26.1", "Article 26.2", "Article 26.5", "Article 26.6",
    "Article 27", "Article 86", "Article 25", "Article 13", "Annex III",
)
_HOSP_CANDIDATES = [
    "Article 26.1", "Article 26.2", "Article 26.5", "Article 26.6", "Article 26",
    "Article 27", "Article 86", "Article 25", "Article 13", "Article 6", "Annex III",
]
_HOSP_ANSWER = (
    "As deployer, the hospital must use the system in accordance with the instructions "
    "for use (Article 26(1)), assign human oversight (Article 26(2)), monitor operation "
    "(Article 26(5)) and keep the logs (Article 26(6)); it performs the fundamental rights "
    "impact assessment (Article 27), informs affected persons (Article 86), may become a "
    "provider (Article 25) and relies on the instructions (Article 13)."
)


def _cut(candidates, declared, answer, budget=5):
    from app.routes.regenold import _curated_budget_cut

    return _curated_budget_cut(list(candidates), tuple(declared), answer, budget)


def test_budget_cut_keeps_declared_leaves_when_no_declared_head_is_evicted() -> None:
    """hardware_techdoc: 4 declared refs fit the budget, so nothing may change.

    The expected list is what the pre-R473 build returned for these inputs
    (captured by running ``beb7aeb9``), byte for byte.
    """
    out = _cut(_HW_CANDIDATES, _HW_DECLARED, _HW_ANSWER)
    assert out == ["Article 11", "Annex IV", "Annex IV.1.e", "Annex IV.2.c", "Annex IV.2"]


def test_budget_cut_still_collapses_when_leaves_would_evict_declared_heads() -> None:
    """hospital: the head plus four leaves fill all five slots - collapse first."""
    out = _cut(_HOSP_CANDIDATES, _HOSP_DECLARED, _HOSP_ANSWER)
    assert out == ["Article 26", "Article 27", "Article 86", "Article 25", "Article 13"]


def test_budget_cut_never_collapses_when_the_off_switch_is_set(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_INTERCEPT_LEAF_COLLAPSE", "0")
    out = _cut(_HOSP_CANDIDATES, _HOSP_DECLARED, _HOSP_ANSWER)
    assert out == ["Article 26", "Article 26.1", "Article 26.2", "Article 26.5", "Article 26.6"]


@pytest.mark.parametrize("question", HARDWARE_QUESTIONS)
def test_hardware_techdoc_wire_keeps_the_hardware_point(question: str) -> None:
    """On the wire: the hardware point (Annex IV.1), not a retrieval-derived IV.2."""
    refs = _wire(question)["references"]
    assert refs == ["Article 11", "Annex IV.1"], refs


def test_hospital_wire_still_ships_every_declared_head() -> None:
    """The R473 fix this repair must not undo: five distinct heads, not one leaf."""
    refs = _wire("A hospital deploys a high-risk AI system. What are the hospital's obligations?")["references"]
    assert {r.split(".", 1)[0] for r in refs} == {
        "Article 26", "Article 27", "Article 86", "Article 25", "Article 13",
    }, refs


# ---------------------------------------------------------------------------
# 3. R473's enumerated-head exemption had no off-switch and was not in the cache
#    key. A curated head declared with 3+ leaves (`Article 65` + 65.3/.4/.5/.7)
#    is now exempt from the grain deepener, so the wire is the bare head instead
#    of one arbitrary paragraph (`Article 65.5`). It cannot lose a head, but it
#    can only ever COST Ref. Strict (a bare head satisfies no sub-point key), so
#    the operator needs a switch to A/B it and to roll it back. The R287 switch
#    `REGENOLD_INTERCEPT_LEAF_COLLAPSE` was also missing from the cache key.
# ---------------------------------------------------------------------------

_BOARD_Q = (
    "Regarding the European Artificial Intelligence Board: who designates its members, "
    "how long is the term, must members act impartially?"
)


def test_enumerated_heads_flag_defaults_on_and_keeps_the_bare_head(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_CURATED_ENUMERATED_HEADS", raising=False)
    assert _wire(_BOARD_Q)["references"] == ["Article 65"]


@pytest.mark.parametrize("off", ["0", "false", "no", "off"])
def test_enumerated_heads_flag_off_restores_the_deepened_paragraph(monkeypatch, off: str) -> None:
    monkeypatch.setenv("REGENOLD_CURATED_ENUMERATED_HEADS", off)
    assert _wire(_BOARD_Q)["references"] == ["Article 65.5"]


@pytest.mark.parametrize("junk", ["", "enabled", "Y", "maybe"])
def test_enumerated_heads_flag_is_deny_list_so_junk_keeps_it_on(monkeypatch, junk: str) -> None:
    """R379 P2-7: a blank or unexpected value must NOT silently revert production."""
    monkeypatch.setenv("REGENOLD_CURATED_ENUMERATED_HEADS", junk)
    assert _wire(_BOARD_Q)["references"] == ["Article 65"]


@pytest.mark.parametrize(
    "flag", ["REGENOLD_CURATED_ENUMERATED_HEADS", "REGENOLD_INTERCEPT_LEAF_COLLAPSE"]
)
def test_route_level_wire_flags_are_in_the_engine_cache_key(monkeypatch, flag: str) -> None:
    """An in-process A/B that toggles the flag must not replay the other arm's cache."""
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv(flag, "1")
    on = _engine_cache_key("What is a deployer?", None)
    monkeypatch.setenv(flag, "0")
    off = _engine_cache_key("What is a deployer?", None)
    assert on != off, f"{flag} is read on the request path but missing from _engine_cache_key"


# ---------------------------------------------------------------------------
# 4. R473's pairwise gate. `ab_judge.gate_exit_code` was the headline repair
#    ("malformed winners are invalid, not ties; 3-state gate_exit_code"), and
#    reviewing it by EXECUTION found it could still print PASS for a run that
#    measured nothing: no n floor (min_rows=1), no decisive-pair floor, a check
#    for an "overall" axis that does not exist, an INDETERMINATE that outranked
#    a significant baseline win, arm-capture failures that were judged as empty
#    answers, and invalids that still biased the effective win rate and the
#    swap-consistency rate. The mutation table showed none of this was pinned:
#    13 of 22 mutations of `gate_exit_code` survived the R473 tests.
# ---------------------------------------------------------------------------

import re  # noqa: E402

from evals.harness import ab_judge  # noqa: E402
from evals.harness.probe_set import ProbeRow  # noqa: E402

_AXES4 = ("correctness", "refs", "conciseness", "tone")


def _axes(**over: dict) -> dict:
    base = {a: {"verdict": "even", "invalids": 0, "wins_branch": 0, "wins_baseline": 0} for a in _AXES4}
    for k, v in over.items():
        base[k] = {**base[k], **v}
    return base


def _result(n_rows: int = 60, **kw) -> dict:
    return {"tier": "live-pairwise", "n_rows": n_rows, "axes": kw.pop("axes", _axes()), **kw}


def test_gate_never_passes_a_run_that_measured_nothing() -> None:
    # Identical arms: no decisive pair on any axis.
    nothing = _axes(**{a: {"verdict": "no-decisive-pairs"} for a in _AXES4})
    assert ab_judge.gate_exit_code(_result(axes=nothing)) == 2
    # A thin run is never a PASS, whatever it says (R398's n floor).
    good = _axes(correctness={"verdict": "branch leans (ns)", "wins_branch": 9, "wins_baseline": 4})
    assert ab_judge.gate_exit_code(_result(n_rows=3, axes=good)) == 2
    # A sign test cannot reach p < .05 on fewer than 6 decisive pairs, so a PASS
    # there is vacuous: the test was not capable of failing.
    five = _axes(correctness={"verdict": "branch leans (ns)", "wins_branch": 5, "wins_baseline": 0})
    assert ab_judge.gate_exit_code(_result(axes=five)) == 2
    # ...and with decisive evidence it can pass.
    six = _axes(correctness={"verdict": "branch wins (sig)", "wins_branch": 6, "wins_baseline": 0})
    assert ab_judge.gate_exit_code(_result(axes=six)) == 0


def test_gate_fails_on_a_significant_baseline_win_on_any_axis() -> None:
    """`overall` is not an axis (AXES = correctness/refs/conciseness/tone), so the R473
    check for it was dead and only `correctness` could ever fail the gate."""
    axes = _axes(
        correctness={"verdict": "branch wins (sig)", "wins_branch": 12, "wins_baseline": 2},
        conciseness={"verdict": "BASELINE wins (sig)", "wins_branch": 1, "wins_baseline": 12},
    )
    assert ab_judge.gate_exit_code(_result(axes=axes)) == 1


def test_gate_fail_outranks_an_invalid_rate_and_a_thin_run() -> None:
    """Same precedence as easyhard_ab: a significant baseline win is evidence."""
    axes = _axes(
        correctness={"verdict": "BASELINE wins (sig)", "wins_baseline": 9},
        tone={"invalids": 13},  # 13/60 > 20 %
    )
    assert ab_judge.gate_exit_code(_result(axes=axes)) == 1
    assert ab_judge.gate_exit_code(_result(n_rows=10, axes=axes)) == 1


def test_gate_needs_the_correctness_axis_and_a_live_tier() -> None:
    no_correctness = {k: v for k, v in _axes().items() if k != "correctness"}
    assert ab_judge.gate_exit_code(_result(axes=no_correctness)) == 2
    assert ab_judge.gate_exit_code({"tier": "deterministic", "n_rows": 60, "axes": _axes()}) == 2
    assert ab_judge.gate_exit_code({"tier": "live-pairwise", "n_rows": 60}) == 2
    assert ab_judge.gate_exit_code("not a dict") == 2  # type: ignore[arg-type]


def test_gate_voids_a_run_whose_arm_capture_failed() -> None:
    """An arm that failed to answer is judged as an empty answer and LOSES, so a
    transport outage in one arm reads as a regression (or, mirrored, a win)."""
    fail = _axes(correctness={"verdict": "BASELINE wins (sig)", "wins_baseline": 9})
    ok = _axes(correctness={"verdict": "branch wins (sig)", "wins_branch": 9})
    broken_branch = {"rows": 60, "baseline_failed": 0, "branch_failed": 20}
    broken_base = {"rows": 60, "baseline_failed": 20, "branch_failed": 0}
    assert ab_judge.gate_exit_code(_result(axes=fail, capture=broken_branch)) == 2
    assert ab_judge.gate_exit_code(_result(axes=ok, capture=broken_base)) == 2
    healthy = {"rows": 60, "baseline_failed": 1, "branch_failed": 2}
    assert ab_judge.gate_exit_code(_result(axes=fail, capture=healthy)) == 1


def test_invalid_pairs_do_not_bias_the_effective_win_rate_or_swap_consistency() -> None:
    """26 of 60 pairs were never judged. They are not half a win, and not a
    position flip: the judge did not run."""
    ax = ab_judge.AxisResult("c", wins_b=20, wins_a=9, ties=31, invalids=26, swap_agreements=34)
    # 20 wins + half of the 5 genuinely tied pairs, over the 34 judged pairs.
    assert ax.effective_win_rate_b(60) == pytest.approx(22.5 / 34, abs=1e-4)
    assert ax.swap_consistency_rate(60) == pytest.approx(1.0)
    # An axis with no invalid pairs is unchanged.
    plain = ab_judge.AxisResult("c", wins_b=10, wins_a=5, ties=5, swap_agreements=20)
    assert plain.effective_win_rate_b(20) == pytest.approx(12.5 / 20)
    assert plain.swap_consistency_rate(20) == pytest.approx(1.0)
    # Every pair invalid: nothing to estimate.
    dead = ab_judge.AxisResult("c", ties=10, invalids=10)
    assert dead.effective_win_rate_b(10) is None
    assert dead.swap_consistency_rate(10) is None


# -- driving the REAL run_ab offline ---------------------------------------


def _rows4(n: int) -> list[ProbeRow]:
    return [
        ProbeRow(
            id=f"s:{i}", source="s", category="c", is_multiturn=False,
            messages=({"role": "user", "content": f"Question {i}?"},),
            expected_refs=("Article 6",), expected_keywords=("x",),
        )
        for i in range(n)
    ]


_ID_RE = re.compile(r"-ANS for ([^\s<]+)")


def _drive(monkeypatch, n: int, prefer, *, garbage=None, base_fail=None, branch_fail=None):
    """Run ``ab_judge.run_ab`` against stubs. ``prefer(i)`` is the judge's TRUE
    preference for row ``i`` ("branch" | "baseline" | "tie"), reported consistently
    in both orderings; ``garbage(call_no)`` makes a call return a malformed winner."""
    import evals.judge.runner as jr

    calls = {"n": 0}

    def fake_capture(rows, _env, *, timeout, label):  # noqa: ANN001, ANN202
        tag, fail = ("BASELINE", base_fail) if label.startswith("A") else ("BRANCH", branch_fail)
        out = {}
        for i, r in enumerate(rows):
            if fail and fail(i):
                out[r.id] = ab_judge.ArmAnswer("", [], 1.0, 500)
            else:
                out[r.id] = ab_judge.ArmAnswer(f"{tag}-ANS for {r.id}", [], 1.0, 200)
        return out

    def caller(prompt: str):
        calls["n"] += 1
        if garbage and garbage(calls["n"]):
            return {"winner": "banana"}
        i = int(_ID_RE.search(prompt).group(1).split(":")[1])
        pref = prefer(i)
        if pref == "tie":
            return {"winner": "tie"}
        branch_in_a = "BRANCH-ANS" in prompt.split("<candidate_b>")[0]
        want_branch = pref == "branch"
        return {"winner": "A" if (branch_in_a == want_branch) else "B"}

    monkeypatch.setattr(ab_judge, "_wrapper_up", lambda *a, **k: True)
    monkeypatch.setattr(ab_judge, "_capture_arm", fake_capture)
    monkeypatch.setattr(jr, "_resolve_caller", lambda *a, **k: caller)
    monkeypatch.setattr(jr, "_load_article_summaries", lambda: {})
    monkeypatch.setattr(jr, "set_judge_model", lambda m: None)
    return ab_judge.run_ab(
        baseline_env={}, branch_env={}, rows=_rows4(n), deterministic=False,
        judge_provider="wrapper", timeout=5.0, label="r474",
    )


def test_run_ab_counts_malformed_winners_as_invalid_and_keeps_the_statistics_honest(monkeypatch) -> None:
    clean = _drive(monkeypatch, 60, lambda i: "branch" if i % 3 else "baseline")
    noisy = _drive(monkeypatch, 60, lambda i: "branch" if i % 3 else "baseline",
                   garbage=lambda k: k % 10 < 3)  # ~30 % of calls are garbage
    c, n = clean["axes"]["correctness"], noisy["axes"]["correctness"]
    assert c["invalids"] == 0 and n["invalids"] > 0
    assert n["invalids"] + n["position_disagreements"] <= n["ties"]
    # The judge's true preference did not change, so the tie-aware win rate must
    # stay close to the clean run instead of drifting toward 0.5.
    assert abs(n["effective_win_rate_branch"] - c["effective_win_rate_branch"]) < 0.08, (c, n)
    assert n["swap_consistency_rate"] == pytest.approx(1.0)


def test_run_ab_has_no_module_global_side_channel_and_classifies_from_the_value() -> None:
    assert not hasattr(ab_judge, "_LAST_PAIRWISE_OUTCOME")
    res = ab_judge.PairVerdict("tie", False, "invalid")
    assert tuple(res) == ("tie", False) and res == ("tie", False)
    assert ab_judge.pair_outcome(res) == "invalid"
    # A plain 2-tuple test double still works (outcome inferred from the pair).
    assert ab_judge.pair_outcome(("A", True)) == "A"
    assert ab_judge.pair_outcome(("tie", False)) == "position_disagreement"


def test_run_ab_records_arm_capture_failures_and_the_gate_voids_them(monkeypatch) -> None:
    res = _drive(monkeypatch, 60, lambda i: "tie", branch_fail=lambda i: i < 20)
    assert res["capture"] == {"rows": 60, "baseline_failed": 0, "branch_failed": 20}
    assert ab_judge.gate_exit_code(res) == 2
    healthy = _drive(monkeypatch, 60, lambda i: "branch")
    assert healthy["capture"] == {"rows": 60, "baseline_failed": 0, "branch_failed": 0}
    assert healthy["gate_exit_code"] == 0


# ---------------------------------------------------------------------------
# 5. R473's pooled micro `ans_correctness_loose` was not PAIRED over the same
#    criteria. A row one arm never got judged (its criteria list is empty) was
#    pooled into the other arm only, so the two arms were scored over different
#    denominators and a failed judge call could flip the sign of the delta. The
#    module's own docstring promises the opposite: rows with missing verdicts "are
#    reported and dropped from both arms".
# ---------------------------------------------------------------------------

import json  # noqa: E402

from evals.official import paired_ab  # noqa: E402


def _score_row(qid: str, criteria: list[bool]) -> dict:
    return {
        "id": qid, "criteria": criteria, "tone_ok": True, "latency_s": 5.0,
        "answer_chars": 100, "reference_chars": 100,
        "refs": ["Article 6"], "expected_refs": ["Article 6"],
    }


def _compare(tmp_path, rows_a: list[dict], rows_b: list[dict]) -> dict:
    a, b = tmp_path / "score-a.json", tmp_path / "score-b.json"
    a.write_text(json.dumps({"rows": rows_a}), encoding="utf-8")
    b.write_text(json.dumps({"rows": rows_b}), encoding="utf-8")
    return paired_ab.compare(a, b)["axes"]["ans_correctness_loose"]


def test_micro_correctness_drops_a_row_one_arm_never_got_judged(tmp_path) -> None:
    """q2 was judged in A ([T, F]) but B's judge failed ([]). R473 pooled it into A
    only: A 3/4 = 75 % vs B 2/2 = 100 %, delta +25 pp, where B is not better at all."""
    rows_a = [_score_row("q1", [True, True]), _score_row("q2", [True, False])]
    rows_b = [_score_row("q1", [True, True]), _score_row("q2", [])]
    loose = _compare(tmp_path, rows_a, rows_b)
    assert loose["mean_a"] == pytest.approx(100.0)
    assert loose["mean_b"] == pytest.approx(100.0)
    assert loose["delta"] == pytest.approx(0.0)
    assert loose["n_criteria_a"] == loose["n_criteria_b"] == 2
    # Reported, not silently dropped.
    assert loose["unpaired_dropped"] == ["q2"]
    assert loose["n_paired_rows"] == 1


def test_micro_correctness_drops_a_row_whose_criteria_counts_differ(tmp_path) -> None:
    rows_a = [_score_row("q1", [True, True]), _score_row("q2", [True, True, False])]
    rows_b = [_score_row("q1", [True, False]), _score_row("q2", [True, True])]
    loose = _compare(tmp_path, rows_a, rows_b)
    assert loose["unpaired_dropped"] == ["q2"]
    assert loose["mean_a"] == pytest.approx(100.0) and loose["mean_b"] == pytest.approx(50.0)
    assert loose["delta"] == pytest.approx(-50.0)


def test_micro_correctness_is_unchanged_when_every_row_is_paired(tmp_path) -> None:
    """R473's own case (`-16.67` pooled vs `+30` macro) must keep holding."""
    rows_a = [_score_row("q_short", [False]), _score_row("q_long", [True] * 5)]
    rows_b = [_score_row("q_short", [True]), _score_row("q_long", [False, False, True, True, True])]
    loose = _compare(tmp_path, rows_a, rows_b)
    assert loose["unpaired_dropped"] == []
    assert loose["delta"] == pytest.approx(-100.0 / 6.0)
    assert loose["macro_delta"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# 6. The committed R440 / R447 gate drivers pair `paired_ab.compare`'s per-sample
#    delta with their own pooled per-question (MACRO) estimate. R473 turned the
#    first into the pooled-over-criteria (MICRO) estimate for ans_correctness_loose,
#    so one rule read two estimators and could contradict itself. Executed on the
#    reviewer's scenario: 20 one-criterion rows (A fails, B passes) + 20
#    five-criterion rows (A 5/5, B 3/5) over three samples.
# ---------------------------------------------------------------------------

import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]


def _r440_verdict_text(tmp_path, capsys) -> str:
    spec = importlib.util.spec_from_file_location(
        "r440_gate_r474", _REPO / "docs" / "measurements" / "r440" / "branch_cluster_gate.py"
    )
    r440 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r440)
    r440.SCORES = tmp_path
    r440.OUT = tmp_path

    def row(qid, crit):
        r = _score_row(qid, crit)
        r.update({"expected_refs": [], "answer": "x" * 100})
        return r

    def arm_rows(arm):
        rows = [row(f"s{k:02d}", [arm == "B"]) for k in range(20)]
        rows += [
            row(f"l{k:02d}", [True] * 5 if arm == "A" else [False, False, True, True, True])
            for k in range(20)
        ]
        return rows

    for s in range(3):
        for arm in ("A", "B"):
            (tmp_path / f"score-flip-{arm}-hard-s{s}-hard.json").write_text(
                json.dumps({"rows": arm_rows(arm), "ckpt": None}), encoding="utf-8"
            )
        res = paired_ab.compare(
            tmp_path / f"score-flip-A-hard-s{s}-hard.json",
            tmp_path / f"score-flip-B-hard-s{s}-hard.json",
        )
        (tmp_path / f"paired-flip-s{s}.json").write_text(json.dumps(res), encoding="utf-8")
    capsys.readouterr()
    r440.verdict("flip", 3)
    return capsys.readouterr().out


def test_r440_gate_reads_one_estimator_for_both_halves_of_its_rule(tmp_path, capsys) -> None:
    out = _r440_verdict_text(tmp_path, capsys)
    # Per-question (macro): every sample and the pool read +30 pp, so no regression.
    assert "regression" not in out, out
    assert "SHIP ON" in out, out


def test_r440_gate_scenario_is_sensitive_to_the_mix_it_guards_against(
    tmp_path, capsys, monkeypatch
) -> None:
    """Negative control: neutralise the helper and the contradictory REFUSE returns,
    so the test above is evidence about the fix and not a coincidence of the data."""
    monkeypatch.setattr(paired_ab, "macro_axis", lambda stats: stats)
    out = _r440_verdict_text(tmp_path, capsys)
    assert "ans_correctness_loose regression" in out, out


def test_macro_axis_returns_the_pre_r473_reading_and_leaves_other_rows_alone() -> None:
    micro = {
        "mean_a": 83.0, "mean_b": 67.0, "delta": -16.0, "ci95": [-30.0, -2.0],
        "macro_mean_a": 50.0, "macro_mean_b": 80.0, "macro_delta": 30.0, "macro_ci95": [10.0, 50.0],
    }
    out = paired_ab.macro_axis(micro)
    assert (out["mean_a"], out["mean_b"], out["delta"], out["ci95"]) == (50.0, 80.0, 30.0, [10.0, 50.0])
    plain = {"mean_a": 1.0, "mean_b": 2.0, "delta": 1.0, "ci95": [0.0, 2.0]}
    assert paired_ab.macro_axis(plain) is plain  # other axes and pre-R473 artifacts untouched


# ---------------------------------------------------------------------------
# 7. `judge._verdicts_from` (R473's "strict 1-to-1 criterion coverage") still turned
#    GARBAGE into a verdict: `satisfied` of None, "banana", a dict, 2 ... went through
#    `_parse_bool`, which returns False for anything it does not recognise, so a
#    malformed judge reply became a legitimate criterion FAILURE. R473 fixed exactly
#    this shape in ab_judge (a malformed winner is invalid, not a tie) and missed it
#    here. A float `n` such as 1.5 was truncated to 1 by `int()`.
# ---------------------------------------------------------------------------

from evals.official import judge as official_judge  # noqa: E402


@pytest.mark.parametrize("bad", [None, "banana", "", {"x": 1}, [True], 2, -1, 0.5])
def test_verdicts_from_rejects_a_satisfied_value_that_is_not_a_boolean(bad) -> None:
    assert official_judge._verdicts_from([{"n": 1, "satisfied": bad}], 1) == (None, [])
    assert official_judge._verdicts_from([{"satisfied": bad}], 1) == (None, [])


@pytest.mark.parametrize(
    ("good", "expected"),
    [
        (True, True), (False, False), ("true", True), ("False", False), ("yes", True),
        ("no", False), (1, True), (0, False), (1.0, True), (0.0, False), ("pass", True),
        ("fail", False), (" TRUE ", True),
    ],
)
def test_verdicts_from_still_accepts_every_boolean_spelling_it_accepted(good, expected) -> None:
    parsed, _ = official_judge._verdicts_from([{"n": 1, "satisfied": good}], 1)
    assert parsed == [expected]


def test_verdicts_from_one_bad_entry_voids_the_whole_reply() -> None:
    """Strict 1-to-1: a reply with ONE unreadable verdict is not partially trusted."""
    reply = [{"n": 1, "satisfied": True}, {"n": 2, "satisfied": "banana"}]
    assert official_judge._verdicts_from(reply, 2) == (None, [])


def test_verdicts_from_rejects_a_non_integral_n_instead_of_truncating_it() -> None:
    assert official_judge._verdicts_from([{"n": 1.5, "satisfied": True}], 1) == (None, [])
    parsed, _ = official_judge._verdicts_from([{"n": 1.0, "satisfied": True}], 1)
    assert parsed == [True]  # an integral float is an integer


# ---------------------------------------------------------------------------
# 8. score_arm's Min-Max band over judge repetitions filled a REJECTED repeat from
#    the majority vote, so a "3 repetitions" band could contain a synthetic run
#    (repeats 0 and 2 all-pass, repeat 1 unreadable -> "100 % - 100 %, +0.0 pp").
#    And R473's three new per-run rate fields were computed and thrown away.
# ---------------------------------------------------------------------------

from evals.official import score_arm  # noqa: E402


def _judged_row(qid: str, runs: list, tone_runs: list | None = None) -> dict:
    live = [r for r in runs if r is not None]
    majority = [all(col) for col in zip(*live, strict=True)] if live else [False] * len(runs[0] or [True])
    return {
        "id": qid, "criteria": majority, "tone_ok": True, "latency_s": 5.0,
        "answer": "a b c", "reference_answer": "a b c d",
        "references": ["Article 6"], "expected_refs": ["Article 6"],
        "_corr_runs": runs, "_tone_runs_raw": tone_runs or [True] * len(runs),
    }


def test_repetition_band_scores_only_repetitions_every_row_actually_judged() -> None:
    rows = [
        _judged_row("a", [[True, True], [True, True], [True, True]]),
        # Repeat 1 of this row was rejected (None): the old block silently used the
        # majority for it, so repeat 1 looked complete and perfect.
        _judged_row("b", [[True, True], None, [True, True]]),
    ]
    scores, skipped = score_arm._per_run_scores(rows)
    assert skipped == 1
    assert len(scores) == 2  # repeats 0 and 2 only


def test_repetition_band_uses_each_repetitions_own_verdicts() -> None:
    rows = [
        _judged_row("a", [[True, True], [False, False]]),
        _judged_row("b", [[True, True], [True, False]]),
    ]
    scores, skipped = score_arm._per_run_scores(rows)
    assert skipped == 0 and len(scores) == 2
    assert scores[0]["ans_correctness_loose"] == pytest.approx(100.0)
    assert scores[1]["ans_correctness_loose"] == pytest.approx(25.0)  # 1 of 4 criteria


def test_repetition_band_is_empty_for_rows_without_repetitions() -> None:
    plain = {"id": "a", "criteria": [True], "tone_ok": True, "latency_s": 5.0}
    assert score_arm._per_run_scores([plain]) == ([], 0)


def test_per_run_judge_rates_are_persisted_not_computed_and_dropped() -> None:
    """The three R473 per-run fields exist on a verdict; a verdict key that is not
    in ``_VERDICT_KEYS`` is not treated as part of the verdict (so a re-judge would
    carry stale values) and was never written to the cache."""
    for key in ("_criteria_rate_mean", "_strict_rate_mean", "_tone_rate_mean"):
        assert key in score_arm._VERDICT_KEYS, key
    src = Path(score_arm.__file__).read_text(encoding="utf-8")
    for key in ("_criteria_rate_mean", "_strict_rate_mean", "_tone_rate_mean"):
        assert f'"{key}",' in src.split('"verdict": {')[1].split('"_basis_sha"')[0], key


# ---------------------------------------------------------------------------
# 9. R473 widened the judge cache basis (question, rendered provisions, prompt
#    templates), which silently invalidates EVERY previously stamped verdict: 2,000
#    of the 4,237 committed cache lines (R423 445/445, R461 65/65) are now re-judged
#    LIVE, with no word printed. And lines with no stamp at all (R388-R407 caches)
#    still replay unchecked, so the strictness is inverted. Neither is a bug in the
#    intent; both are invisible. The split now counts and reports them.
# ---------------------------------------------------------------------------


def _cache_fixture(stamp):
    row = {
        "id": "q1", "answer": "an answer", "question": "Q?", "criteria_text": ["c1", "c2"],
        "criteria": ["c1", "c2"], "expected_refs": ["Article 6"],
    }
    verdict = {"criteria": [True, False], "_judge_runs": 1}
    if stamp == "current":
        verdict["_basis_sha"] = score_arm._judge_basis_sha(row)
    elif stamp == "legacy":
        verdict["_basis_sha"] = "0ldba5is0000"
    cache = {score_arm._row_cache_key(row, "judge-x"): verdict}
    return row, cache


def test_cache_split_replays_a_verdict_judged_on_the_current_basis() -> None:
    row, cache = _cache_fixture("current")
    cached, todo, stale, unstamped = score_arm._split_cached([row], cache, "judge-x", 1)
    assert len(cached) == 1 and not todo and (stale, unstamped) == (0, 0)


def test_cache_split_counts_a_stamped_verdict_whose_basis_changed() -> None:
    row, cache = _cache_fixture("legacy")
    cached, todo, stale, unstamped = score_arm._split_cached([row], cache, "judge-x", 1)
    assert not cached and len(todo) == 1 and (stale, unstamped) == (1, 0)


def test_cache_split_counts_an_unstamped_verdict_it_replays_unchecked() -> None:
    row, cache = _cache_fixture("none")
    cached, todo, stale, unstamped = score_arm._split_cached([row], cache, "judge-x", 1)
    assert len(cached) == 1 and not todo and (stale, unstamped) == (0, 1)


def test_cache_split_does_not_count_a_missing_or_partial_verdict_as_stale() -> None:
    row, cache = _cache_fixture("legacy")
    cache[next(iter(cache))]["_judge_runs"] = 0  # a partial row is simply re-judged
    _c, todo, stale, _u = score_arm._split_cached([row], cache, "judge-x", 1)
    assert len(todo) == 1 and stale == 0
    _c, todo, stale, _u = score_arm._split_cached([row], {}, "judge-x", 1)
    assert len(todo) == 1 and stale == 0


# ---------------------------------------------------------------------------
# 10. hard_preamble: `build_prefixed_pushback_messages` made `pushback` optional in
#     R473, and with no pushback it silently sent the PUBLISHED template - under the
#     default (fixed) profile too, where the docstring says it should not and where
#     the pre-R473 contract made the argument required. Plus pins for the things the
#     R473 tests did not discriminate (the mutation table: typo fix, a deleted
#     pushback clause, an ignored profile, a removed alias all survived).
# ---------------------------------------------------------------------------

from evals.regenold import hard_preamble as _hp  # noqa: E402
from evals.regenold import official_batch as _ob  # noqa: E402


def test_pushback_is_required_unless_the_published_profile_formats_it() -> None:
    with pytest.raises(ValueError, match="pushback"):
        _hp.build_prefixed_pushback_messages("Q?", "A")
    with pytest.raises(ValueError, match="pushback"):
        _hp.build_prefixed_pushback_messages("Q?", "A", profile=_hp.MODE_FIXED)
    published = _hp.build_prefixed_pushback_messages("Q?", "A", profile=_hp.MODE_PUBLISHED)
    assert published[-1]["content"] == _hp.format_published_pushback("Q?")
    alias = _hp.build_prefixed_pushback_messages("Q?", "A", profile="published_2026")
    assert alias == published
    explicit = _hp.build_prefixed_pushback_messages("Q?", "A", "my pushback")
    assert explicit[-1]["content"] == "my pushback"
    assert explicit[-2] == {"role": "assistant", "content": "A"}


def test_the_published_fixture_and_template_are_pinned_byte_for_byte() -> None:
    """Verified against the released ``9-steps-convo-nojson.json`` and ``run_benchmark.py``."""
    assert _hp.preamble_digest(profile=_hp.MODE_PUBLISHED) == "14cd65de8b1043a8"
    assert _hp.preamble_digest() == "cb85452c9c041721"  # the R424 default must not move
    msgs = _hp.preamble_messages(profile=_hp.MODE_PUBLISHED)
    assert len(msgs) == 18 and sum(len(m["content"].split()) for m in msgs) == 501
    # The released dialogue carries a typo; a "corrected" copy is not the benchmark.
    assert "subejct" in msgs[7]["content"]
    assert _hp.PUBLISHED_PUSHBACK_TEMPLATE == _ob.PUSHBACK_TEMPLATE
    assert _hp.PUBLISHED_PUSHBACK_TEMPLATE.endswith("Let's try again:\n{question}")
    assert "without mentioning the previous answer or the pushback.)" in _hp.PUBLISHED_PUSHBACK_TEMPLATE
    # profile=None and the fixed aliases are the same dialogue; published is not.
    assert _hp.preamble_messages(profile=None) == _hp.preamble_messages(profile="r391_report")
    assert _hp.preamble_messages(profile="published") == msgs
    assert msgs != _hp.preamble_messages()
    with pytest.raises(ValueError, match="Unknown hard preamble profile"):
        _hp.preamble_messages(profile="nonsense")


# ---------------------------------------------------------------------------
# 11. `_extract_conversation_anchors`: R473 changed substring matching to token
#     boundaries. The R473 test used input with two risk words and the extractor keeps
#     `risk_seen[:2]`, which hid every substring mutant. These inputs discriminate, and
#     the negative control shows the substring behaviour they guard against.
# ---------------------------------------------------------------------------

import types as _types  # noqa: E402


def _anchor_parts(text: str) -> tuple[list[str], list[str]]:
    from app.routes.regenold import _extract_conversation_anchors

    line = _extract_conversation_anchors([_types.SimpleNamespace(role="user", content=text)])
    roles = re.search(r"roles: ([^;\]]*)", line)
    risks = re.search(r"risk tier: ([^;\]]*)", line)
    split = lambda m: [x.strip() for x in m.group(1).split(",")] if m else []  # noqa: E731
    return split(roles), split(risks)


@pytest.mark.parametrize(
    ("text", "roles", "risks"),
    [
        ("Is Annex III relevant?", [], ["annex iii"]),          # "annex i" is NOT inside "annex iii"
        ("Does Annex IV cover this?", [], []),                  # nor inside "annex iv"
        ("A subprovider resells it.", [], []),                  # "provider" inside another word
        ("The providers and the deployers.", ["provider", "deployer"], []),  # plurals still match
        ("It is a minimal risk system.", [], ["minimal risk"]),
        ("An authorised representative acts.", ["authorised representative"], []),
    ],
)
def test_anchor_extraction_matches_whole_tokens(text: str, roles: list[str], risks: list[str]) -> None:
    assert _anchor_parts(text) == (roles, risks)


def test_anchor_inputs_discriminate_between_token_and_substring_matching(monkeypatch) -> None:
    """Negative control: the SAME inputs fail under substring matching, so the cases
    above are evidence about token matching and not coincidence."""
    import app.routes.regenold as rg

    monkeypatch.setattr(
        rg, "_ANCHOR_ROLE_PATTERNS",
        tuple((w, re.compile(re.escape(w), re.IGNORECASE)) for w in rg._ANCHOR_ROLE_WORDS),
    )
    monkeypatch.setattr(
        rg, "_ANCHOR_RISK_PATTERNS",
        tuple((w, re.compile(re.escape(w), re.IGNORECASE)) for w in rg._ANCHOR_RISK_WORDS),
    )
    assert _anchor_parts("Is Annex III relevant?")[1] == ["annex iii", "annex i"]
    assert _anchor_parts("A subprovider resells it.")[0] == ["provider"]


def test_the_published_dialogue_does_trip_the_anchor_extractor() -> None:
    """Known and pinned, not fixed: the evaluator's dialogue, unlike our R424
    reconstruction, carries anchor words in its USER turns, so the graded hard
    modality receives this constant line and every `fixed` board could not see it
    (the offline route's references collapse to near-constant on 10 of 12 probe
    questions under it). Whether that is intended is the operator's call; this pin
    makes any change to it deliberate."""
    from app.routes.regenold import _extract_conversation_anchors

    def anchors(profile):
        turns = [
            _types.SimpleNamespace(role=m["role"], content=m["content"])
            for m in _hp.preamble_messages(profile=profile)
        ]
        return _extract_conversation_anchors(turns)

    assert anchors(None) == ""
    assert anchors(_hp.MODE_PUBLISHED) == (
        "[Context anchors — articles: Annex III; roles: provider; risk tier: high-risk, annex iii]"
    )


# ---------------------------------------------------------------------------
# 12. `pairwise_from_answers` had NO test that imports it (every mutation of it
#     survived). It silently dropped an errored or empty row, so an arm that
#     answered 10 of 40 rows left n_rows=10 and, with --enforce-gate, a PASS.
# ---------------------------------------------------------------------------

from evals.harness import pairwise_from_answers as pfa  # noqa: E402


def _sidecar(tmp_path, name: str, tag: str, n: int, fail=lambda i: False) -> str:
    rows = []
    for i in range(n):
        rid = f"s:{i}"
        if fail(i):
            rows.append({"id": rid, "error": "http_500", "pred_answer": "", "pred_refs": [], "http_status": 500})
        else:
            rows.append({"id": rid, "pred_answer": f"{tag}-ANS for {rid}", "pred_refs": [],
                         "latency_ms": 1.0, "http_status": 200})
    path = tmp_path / name
    path.write_text(json.dumps({"baseline_rows": rows}), encoding="utf-8")
    return str(path)


def _run_pfa(monkeypatch, tmp_path, n: int, prefer, *, base_fail=None, branch_fail=None, enforce=True):
    import evals.judge.runner as jr

    def caller(prompt: str):
        i = int(_ID_RE.search(prompt).group(1).split(":")[1])
        pref = prefer(i)
        if pref == "tie":
            return {"winner": "tie"}
        branch_in_a = "BRANCH-ANS" in prompt.split("<candidate_b>")[0]
        return {"winner": "A" if (branch_in_a == (pref == "branch")) else "B"}

    monkeypatch.setattr(pfa, "load_probe_set", lambda *a, **k: _rows4(n))
    monkeypatch.setattr(pfa, "_RESULTS", tmp_path)
    monkeypatch.setattr(jr, "_resolve_caller", lambda *a, **k: caller)
    monkeypatch.setattr(jr, "_load_article_summaries", lambda: {})
    monkeypatch.setattr(jr, "set_judge_model", lambda m: None)
    argv = [
        "--label", "r474",
        "--baseline-sidecar", _sidecar(tmp_path, "a.json", "BASELINE", n, base_fail or (lambda i: False)),
        "--branch-sidecar", _sidecar(tmp_path, "b.json", "BRANCH", n, branch_fail or (lambda i: False)),
    ] + (["--enforce-gate"] if enforce else [])
    code = pfa.main(argv)
    out = json.loads((tmp_path / "pairwise-from-answers-r474.json").read_text(encoding="utf-8"))
    return code, out


def test_pairwise_from_answers_passes_a_clear_win_on_a_healthy_run(monkeypatch, tmp_path) -> None:
    code, out = _run_pfa(monkeypatch, tmp_path, 40, lambda i: "branch")
    assert code == 0 and out["gate_exit_code"] == 0
    assert out["capture"] == {"rows": 40, "baseline_failed": 0, "branch_failed": 0}


def test_pairwise_from_answers_fails_a_clear_loss(monkeypatch, tmp_path) -> None:
    code, out = _run_pfa(monkeypatch, tmp_path, 40, lambda i: "baseline")
    assert code == 1 and out["gate_exit_code"] == 1


def test_pairwise_from_answers_voids_an_arm_that_mostly_errored(monkeypatch, tmp_path) -> None:
    """Branch answered 10 of 40 rows: n_rows is 10, the comparison is clean, and the
    run used to PASS. It measured 25 % of the rows."""
    code, out = _run_pfa(monkeypatch, tmp_path, 40, lambda i: "branch", branch_fail=lambda i: i >= 10)
    assert out["n_rows"] == 10
    assert out["capture"] == {"rows": 40, "baseline_failed": 0, "branch_failed": 30}
    assert code == 2


def test_pairwise_from_answers_only_enforces_the_gate_when_asked(monkeypatch, tmp_path) -> None:
    code, out = _run_pfa(monkeypatch, tmp_path, 40, lambda i: "baseline", enforce=False)
    assert code == 0 and out["gate_exit_code"] == 1  # the verdict is recorded either way


# ---------------------------------------------------------------------------
# 13. `_judge_basis_sha` (R473: question, rendered provisions, prompt templates): the
#     mutation table shows dropping the provisions, the prompts or the refs from the
#     basis survived. Each component must change the stamp.
# ---------------------------------------------------------------------------


def _basis_row(**over) -> dict:
    row = {"id": "q1", "question": "Q?", "criteria_text": ["c1"], "expected_refs": ["Article 6"]}
    row.update(over)
    return row


def test_judge_basis_changes_with_every_component_it_claims_to_cover(monkeypatch) -> None:
    base = score_arm._judge_basis_sha(_basis_row())
    assert score_arm._judge_basis_sha(_basis_row()) == base  # deterministic
    assert score_arm._judge_basis_sha(_basis_row(question="Another question?")) != base
    assert score_arm._judge_basis_sha(_basis_row(criteria_text=["c1", "c2"])) != base
    assert score_arm._judge_basis_sha(_basis_row(expected_refs=["Article 6", "Annex III"])) != base
    # The rendered statutory text, not just the reference names.
    monkeypatch.setattr(score_arm.official_judge, "_provisions_for", lambda refs: "DIFFERENT PROVISION TEXT")
    assert score_arm._judge_basis_sha(_basis_row()) != base
    monkeypatch.undo()
    # The prompt templates the judge is actually called with.
    monkeypatch.setattr(score_arm.official_judge, "CORRECTNESS_PROMPT", score_arm.official_judge.CORRECTNESS_PROMPT + " ")
    assert score_arm._judge_basis_sha(_basis_row()) != base

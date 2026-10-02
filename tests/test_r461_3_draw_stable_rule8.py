"""R461.3 - hard rule #8 read DRAW-STABLE, and the noise floor that prices it.

Two findings from one gate, both about reading a single draw as a fact:

* the SCOPE fix (R461.1) asked WHICH ROWS testify - a drop on a row the lever
  never served is a transport event, not a lever verdict;
* this round asks whether the drop on a qualifying row is a FACT. At n=37 a
  second draw of an UNCHANGED OFF arm drops gold heads the first draw did not
  (``docs/measurements/r461/COUNT-ONLY-CONFIRM.md`` SS5), so the same rule that
  caught a real regression would have vetoed a null pair.

The contract pinned here, in both directions:

* a drop vetoes only if an INDEPENDENT re-draw of arm A carries the head too -
  the reference has to hold the head reproducibly before its absence is read as
  a loss;
* a drop the re-draw clears is REPORTED (``draw_stability.drops_unstable``),
  never deleted, and ``gold_dropped_head`` keeps its all-rows counts;
* with no re-draw the single-draw reading stands, and that is the STRICTER one,
  so the fallback can never lift a veto;
* the re-draw is verified per row on ``hard_preamble_digest``, read from each
  arm's own checkpoint - the score payload does not carry it (the defect this
  file caught while it was being written). A row that cannot be verified keeps
  its drop;
* the same flag prices the noise floor: arm A against its own re-draw is a
  paired OFF/OFF control, and the read refuses to quote a floor that is not one
  configuration or that still drops heads after stabilisation.

The harness half is pinned too: ``run_official_batch`` draws the control arm
itself (-C, the baseline env), so a gate cannot be reported without a floor
unless ``--no-control`` says so in the payload.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.official.paired_ab import (
    AXES,
    DRAW_STABILITY_RULE,
    _config_identity,
    _digest_map,
    _print_noise_floor_summary,
    attach_noise_floor,
    compare,
    main,
    noise_floor,
)

REPO = Path(__file__).resolve().parents[1]

GOLD = "Article 5"
GOLD_OTHER = "Article 9"
OTHER = "Article 6"
DIGEST = "cb85452c9c04"


# --------------------------------------------------------------------------- #
# synthetic arms
# --------------------------------------------------------------------------- #
def _row(qid: str, refs, expected=(GOLD,), criteria=(True, True, True)) -> dict:
    return {
        "id": qid,
        "refs": list(refs),
        "expected_refs": list(expected),
        "criteria": list(criteria),
        "criteria_text": ["c"] * len(criteria),
        "criterion_remarks": [""] * len(criteria),
        "n_criteria_passed": sum(criteria),
        "answer_chars": 900,
        "reference_chars": 700,
        "tone_ok": True,
        "latency_s": 1.0,
        "question": f"question {qid}",
    }


def _write_arm(
    tmp_path: Path,
    name: str,
    rows: list[dict],
    *,
    digest: str | None = DIGEST,
    leg: str | None = "primary",
    record_ckpt: bool = True,
    ckpt_path: Path | None = None,
    extra_ckpt: dict[str, dict] | None = None,
) -> Path:
    """One synthetic score payload + the checkpoint its digests come from."""
    ckpt = ckpt_path or (tmp_path / f"{name}.ckpt.jsonl")
    if record_ckpt:
        lines = []
        for row in rows:
            entry = {
                "id": row["id"],
                "provenance": {"stage2_served_by": leg, "stage2_polish": True},
            }
            if digest is not None:
                entry["hard_preamble_digest"] = digest
            lines.append(json.dumps(entry))
        for qid, entry in (extra_ckpt or {}).items():
            lines.append(json.dumps({"id": qid, **entry}))
        ckpt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload: dict = {"label": name, "mode": "hard", "rows": rows}
    if record_ckpt:
        payload["ckpt"] = str(ckpt)
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _gate(tmp_path: Path, *, redraw_holds: bool = True, redraw_digest: str = DIGEST,
          redraw_lacks_row: bool = False, redraw_ckpt: bool = True) -> tuple[Path, Path, Path]:
    """Arm A holds GOLD on two rows, arm B drops it on one, and the re-draw is
    an independent draw of A's configuration that may or may not still hold it."""
    rows_a = [_row("rg_live", [GOLD]), _row("rg_keep", [GOLD, OTHER])]
    rows_b = [_row("rg_live", [OTHER]), _row("rg_keep", [GOLD, OTHER])]
    redraw_rows = [_row("rg_live", [GOLD] if redraw_holds else [OTHER]),
                   _row("rg_keep", [GOLD, OTHER])]
    if redraw_lacks_row:
        redraw_rows = [r for r in redraw_rows if r["id"] != "rg_live"]
    a = _write_arm(tmp_path, "arm_a", rows_a)
    b = _write_arm(tmp_path, "arm_b", rows_b)
    redraw = _write_arm(
        tmp_path, "arm_a_redraw", redraw_rows,
        digest=None if redraw_digest is None else redraw_digest,
        record_ckpt=redraw_ckpt,
    )
    return a, b, redraw


# --------------------------------------------------------------------------- #
# the rule
# --------------------------------------------------------------------------- #
def test_the_rule_names_the_independent_re_draw():
    assert "INDEPENDENT re-draw" in DRAW_STABILITY_RULE
    assert "rule #8" in DRAW_STABILITY_RULE


def test_a_drop_the_redraw_also_carries_still_vetoes(tmp_path):
    a, b, redraw = _gate(tmp_path, redraw_holds=True)
    res = compare(a, b, 403, a_redraw=redraw)
    assert res["veto"]["verdict"] == "VETO"
    assert res["veto"]["draw_stable"] is True
    assert [d["id"] for d in res["veto"]["drops_in_scope"]] == ["rg_live"]
    assert res["draw_stability"]["drops_unstable"] == []
    assert res["draw_stability"]["verified_rows"] == ["rg_live"]


def test_a_drop_the_redraw_clears_is_reported_and_not_vetoed(tmp_path):
    a, b, redraw = _gate(tmp_path, redraw_holds=False)
    res = compare(a, b, 403, a_redraw=redraw)
    assert res["veto"]["verdict"] == "CLEAN"
    assert res["veto"]["fires"] is False
    # nothing leaves the record: the drop is still counted and still named
    assert res["gold_dropped_head"]["new_drops_in_b"] == ["rg_live"]
    cleared = res["draw_stability"]["drops_unstable"]
    assert [d["id"] for d in cleared] == ["rg_live"]
    assert cleared[0]["heads"] == [GOLD]
    assert "draw noise" in cleared[0]["why"]
    assert res["draw_stability"]["cleared_heads"] == 1
    assert "did not persist" in res["draw_stability"]["reason"]


def test_without_a_redraw_the_single_draw_reading_stands(tmp_path):
    a, b, _redraw = _gate(tmp_path, redraw_holds=False)
    res = compare(a, b, 403)
    assert res["veto"]["verdict"] == "VETO"
    assert res["veto"]["draw_stable"] is False
    ds = res["draw_stability"]
    assert ds["stabilized"] is False
    assert ds["survived"] == {"rg_live": [GOLD]}
    assert "single-draw reading stands" in ds["reason"]
    assert "stricter" in ds["reason"]


def test_a_redraw_of_another_configuration_is_refused_not_trusted(tmp_path):
    a, b, redraw = _gate(tmp_path, redraw_holds=False, redraw_digest="ffff0000")
    res = compare(a, b, 403, a_redraw=redraw)
    assert res["veto"]["verdict"] == "VETO"  # fail closed
    unverified = res["draw_stability"]["unverified"]
    assert [u["id"] for u in unverified] == ["rg_live"]
    assert "different REQUEST SHAPE" in unverified[0]["why"]
    assert unverified[0]["heads"] == [GOLD]


def test_a_row_missing_from_the_redraw_keeps_its_drop(tmp_path):
    a, b, redraw = _gate(tmp_path, redraw_lacks_row=True, redraw_holds=False)
    res = compare(a, b, 403, a_redraw=redraw)
    assert res["veto"]["verdict"] == "VETO"
    assert [u["why"] for u in res["draw_stability"]["unverified"]] == [
        "row missing from the re-draw"
    ]


def test_a_redraw_without_a_checkpoint_keeps_every_drop(tmp_path):
    a, b, redraw = _gate(tmp_path, redraw_holds=False, redraw_ckpt=False)
    res = compare(a, b, 403, a_redraw=redraw)
    assert res["veto"]["verdict"] == "VETO"
    assert "no hard_preamble_digest on one side" in (
        res["draw_stability"]["unverified"][0]["why"]
    )
    assert res["draw_stability"]["digests"]["redraw"].startswith("no checkpoint")


def test_the_digest_is_read_from_the_checkpoint_not_the_score_payload(tmp_path):
    """The defect this file caught: ``score_arm`` payloads carry no digest.

    If the stabilisation asked the SCORE rows, every row would fail closed and
    the re-draw could never clear a drop - a failure mode that hides inside
    fail-closed behaviour, because the gate would still read.
    """
    a, b, redraw = _gate(tmp_path, redraw_holds=False)
    score_rows = json.loads(a.read_text(encoding="utf-8"))["rows"]
    assert "hard_preamble_digest" not in score_rows[0]
    digests, source = _digest_map(a, None)
    assert digests["rg_live"] == DIGEST and source.endswith("arm_a.ckpt.jsonl")
    assert compare(a, b, 403, a_redraw=redraw)["veto"]["verdict"] == "CLEAN"


def test_the_stabilisation_never_edits_the_legacy_counts(tmp_path):
    a, b, redraw = _gate(tmp_path, redraw_holds=False)
    raw = compare(a, b, 403)
    stable = compare(a, b, 403, a_redraw=redraw)
    assert raw["gold_dropped_head"] == stable["gold_dropped_head"]
    assert raw["veto"]["rows_considered"] == stable["veto"]["rows_considered"]
    assert raw["veto"]["eligible_rows"] == stable["veto"]["eligible_rows"]


def test_a_drop_is_read_at_the_head_grain(tmp_path):
    """``Article 5.1.a`` in gold and ``Article 5`` in the answer is the same
    head: the veto has always been read at that grain, and stabilisation must
    not change it."""
    rows_a = [_row("rg_live", ["Article 5"], expected=("Article 5.1.a",))]
    rows_b = [_row("rg_live", ["Article 5"], expected=("Article 5.1.a",))]
    a = _write_arm(tmp_path, "arm_a", rows_a)
    b = _write_arm(tmp_path, "arm_b", rows_b)
    res = compare(a, b, 403)
    assert res["gold_dropped_head"]["new_drops_in_b"] == []
    assert res["draw_stability"]["raw_drop_rows"] == []


def test_stabilisation_can_only_clear_drops_never_add_them(tmp_path):
    a, b, redraw = _gate(tmp_path, redraw_holds=True)
    res = compare(a, b, 403, a_redraw=redraw)
    raw = set(res["draw_stability"]["raw_drop_rows"])
    survived = set(res["draw_stability"]["survived_rows"])
    assert survived <= raw


def test_compare_keeps_the_legacy_positional_signature(tmp_path):
    a, b, _redraw = _gate(tmp_path)
    res = compare(a, b, 403)
    assert res["shared_rows"] == 2 and "veto" in res
    assert res["veto"]["provenance"]["bootstrap_seed"] == 403
    assert res["redraw"] is None


# --------------------------------------------------------------------------- #
# the noise floor
# --------------------------------------------------------------------------- #
def test_config_identity_is_checked_on_the_checkpoints(tmp_path):
    a, b, _redraw = _gate(tmp_path)
    identity = _config_identity(a, b)
    assert identity["same_configuration"] is True
    assert identity["rows_compared"] == 2
    assert "same request-shape digest" in identity["reason"]
    # a match is NOT identity: it cannot establish one configuration
    assert "cannot establish it" in identity["reason"]


def test_config_identity_refuses_a_pair_that_served_different_bytes(tmp_path):
    rows = [_row("rg_live", [GOLD])]
    a = _write_arm(tmp_path, "arm_a", rows, digest=DIGEST)
    b = _write_arm(tmp_path, "arm_b", rows, digest="deadbeef")
    identity = _config_identity(a, b)
    assert identity["same_configuration"] is False
    assert [m["id"] for m in identity["mismatched"]] == ["rg_live"]
    assert "different request-shape digest" in identity["reason"]


def test_config_identity_is_unknown_without_a_checkpoint(tmp_path):
    rows = [_row("rg_live", [GOLD])]
    a = _write_arm(tmp_path, "arm_a", rows)
    b = _write_arm(tmp_path, "arm_b", rows, record_ckpt=False)
    identity = _config_identity(a, b)
    assert identity["same_configuration"] is None
    assert "identity is unknown" in identity["reason"]


def test_a_clean_control_pair_is_usable_as_a_floor(tmp_path):
    rows = [_row("rg_live", [GOLD]), _row("rg_keep", [GOLD, OTHER])]
    a = _write_arm(tmp_path, "off_1", rows)
    b = _write_arm(tmp_path, "off_2", rows)
    floor = noise_floor(a, b)
    assert floor["usable"] is True
    assert floor["veto"]["verdict"] == "CLEAN"
    assert set(floor["axes"]) == set(AXES)
    assert floor["config_identity"]["same_configuration"] is True


def test_a_floor_that_still_drops_heads_is_refused(tmp_path):
    """The R461 noise floor in miniature: two draws of ONE configuration, and arm
    B lacks a gold head arm A held, which the re-draw also holds - so the pair is
    really different, and it is refused as a floor rather than quoted."""
    rows_a = [_row("rg_live", [GOLD])]
    rows_b = [_row("rg_live", [OTHER])]
    a = _write_arm(tmp_path, "off_1", rows_a)
    b = _write_arm(tmp_path, "off_2", rows_b)
    third = _write_arm(tmp_path, "off_3", rows_a)
    floor = noise_floor(a, b, a_redraw=third)
    assert floor["veto"]["verdict"] == "VETO"
    assert floor["usable"] is False
    assert "firing on draw noise" in floor["reason"]


def test_the_r461_noise_floor_shape_reads_clean_once_stabilised(tmp_path):
    """THE validation the round asked for, on a pair with no lever in it.

    Both arms are draws of the SAME configuration, so the drop between them can
    only be draw noise. Read single-draw, rule #8 fires - which is exactly the
    false positive R461 measured. Read draw-stable, against a third independent
    draw of the same configuration that also lacks the head, it reads CLEAN and
    the drop is reported.
    """
    rows_a = [_row("rg_live", [GOLD]), _row("rg_keep", [GOLD, OTHER])]
    rows_b = [_row("rg_live", [OTHER]), _row("rg_keep", [GOLD, OTHER])]
    a = _write_arm(tmp_path, "off_1", rows_a)
    b = _write_arm(tmp_path, "off_2", rows_b)
    third = _write_arm(tmp_path, "off_3", rows_b)

    single = noise_floor(a, b)
    assert single["veto"]["verdict"] == "VETO"
    assert single["usable"] is False

    stable = noise_floor(a, b, a_redraw=third)
    assert stable["veto"]["verdict"] == "CLEAN"
    assert stable["usable"] is True
    assert [d["id"] for d in stable["veto"]["draw_stability"]["drops_unstable"]] == [
        "rg_live"
    ]
    # ... and the same read is what a lever read would use as its floor
    assert stable["config_identity"]["same_configuration"] is True


def test_attach_noise_floor_puts_the_floor_beside_every_axis(tmp_path):
    rows_off = [_row("rg_live", [GOLD])]
    rows_on = [_row("rg_live", [GOLD], criteria=(False, False, False))]
    lever_a = _write_arm(tmp_path, "off_1", rows_off)
    lever_b = _write_arm(tmp_path, "on_1", rows_on)
    floor_a = _write_arm(tmp_path, "off_2", rows_off)
    floor_b = _write_arm(tmp_path, "off_3", rows_off)
    lever = compare(lever_a, lever_b, 403)
    floor = noise_floor(floor_a, floor_b)
    attached = attach_noise_floor(lever, floor)
    block = attached["noise_floor"]
    assert block["usable"] is True
    assert set(block["axes"]) == set(AXES)
    for axis in AXES:
        entry = block["axes"][axis]
        assert entry["lever_delta"] is not None
        assert entry["floor_delta"] is not None
        assert isinstance(entry["beyond_floor"], bool)
    strict = block["axes"]["ans_correctness_strict"]
    assert abs(strict["lever_delta"]) > abs(strict["floor_delta"])
    assert strict["beyond_floor"] is True
    assert strict["ci_excludes_floor"] is True
    assert block["floor_veto"] == "CLEAN"


def test_the_floor_summary_reads_the_shape_it_is_handed(tmp_path, capsys):
    """The printer sees two shapes: a floor payload and the block a lever read
    carries. Reading only the first printed zeros for the second."""
    rows_off = [_row("rg_live", [GOLD])]
    rows_on = [_row("rg_live", [GOLD], criteria=(False, False, False))]
    lever_a = _write_arm(tmp_path, "off_1", rows_off)
    lever_b = _write_arm(tmp_path, "on_1", rows_on)
    floor_a = _write_arm(tmp_path, "off_2", rows_off)
    floor_b = _write_arm(tmp_path, "off_3", rows_off)
    attached = attach_noise_floor(compare(lever_a, lever_b, 403), noise_floor(floor_a, floor_b))
    _print_noise_floor_summary(attached["noise_floor"])
    out = capsys.readouterr().out
    assert "usable: True" in out
    strict = [ln for ln in out.splitlines() if "ans_correctness_strict" in ln][0]
    assert "lever=" in strict and "floor=" in strict and "beyond the floor" in strict


# --------------------------------------------------------------------------- #
# the CLI
# --------------------------------------------------------------------------- #
def _cli(monkeypatch, *argv: str):
    monkeypatch.setattr("sys.argv", ["paired_ab", *argv])


def test_cli_says_so_loudly_when_there_is_no_floor(tmp_path, monkeypatch, capsys):
    a, b, _redraw = _gate(tmp_path, redraw_holds=False)
    _cli(monkeypatch, "--a", str(a), "--b", str(b))
    assert main() == 0
    out = capsys.readouterr().out
    assert "NO NOISE FLOOR" in out
    assert "SINGLE DRAW (not stabilised)" in out
    assert "draw-noise" not in out  # nothing was cleared, nothing is claimed


def test_cli_with_a_redraw_prints_and_writes_the_floor(tmp_path, monkeypatch, capsys):
    a, b, redraw = _gate(tmp_path, redraw_holds=True)
    out_path = tmp_path / "paired.json"
    _cli(
        monkeypatch, "--a", str(a), "--b", str(b),
        "--redraw", str(redraw), "--out", str(out_path),
    )
    assert main() == 0
    printed = capsys.readouterr().out
    assert "NOISE FLOOR (paired OFF/OFF control" in printed
    assert "DRAW-STABLE" in printed
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["noise_floor"]["usable"] is True
    assert payload["draw_stability"]["stabilized"] is True
    assert payload["veto"]["draw_stable"] is True


def test_cli_control_mode_refuses_a_pair_that_is_not_one_configuration(
    tmp_path, monkeypatch, capsys
):
    rows = [_row("rg_live", [GOLD])]
    a = _write_arm(tmp_path, "off_1", rows, digest=DIGEST)
    b = _write_arm(tmp_path, "off_2", rows, digest="0badc0de")
    out_path = tmp_path / "floor.json"
    _cli(
        monkeypatch, "--a", str(a), "--b", str(b),
        "--control", "--out", str(out_path),
    )
    assert main() == 0
    assert "PAIRED OFF/OFF CONTROL" in capsys.readouterr().out
    floor = json.loads(out_path.read_text(encoding="utf-8"))
    assert floor["usable"] is False
    assert floor["config_identity"]["same_configuration"] is False


def test_cli_exposes_the_redraw_ckpt_override(tmp_path, monkeypatch, capsys):
    a, b, redraw = _gate(tmp_path, redraw_holds=False)
    moved = tmp_path / "moved.ckpt.jsonl"
    moved.write_text(
        (tmp_path / "arm_a_redraw.ckpt.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _cli(
        monkeypatch, "--a", str(a), "--b", str(b),
        "--redraw", str(redraw), "--redraw-ckpt", str(moved),
    )
    assert main() == 0
    payload = json.loads(
        (tmp_path / "paired.json").read_text(encoding="utf-8")
    ) if (tmp_path / "paired.json").exists() else None
    out = capsys.readouterr().out
    assert "cleared by the re-draw" in out
    assert payload is None or payload["draw_stability"]["stabilized"] is True


# --------------------------------------------------------------------------- #
# the harness: the control arm is drawn, not remembered
# --------------------------------------------------------------------------- #
def _runner_source() -> str:
    return (REPO / "evals" / "regenold" / "run_official_batch.py").read_text(
        encoding="utf-8"
    )


def test_the_harness_draws_the_control_arm_at_the_baseline_env():
    src = _runner_source()
    assert '"--no-control"' in src
    assert 'suffix="-C"' in src
    marker = src.index("CONTROL ARM (baseline config, independent draw)")
    end = src.index('    out = _RESULTS / f"official-{args.label}.json"', marker)
    block = src[marker:end]
    assert "arm_env=base_env" in block
    assert "branch_env" not in block
    assert "OFF/OFF control that prices the draw floor" in block
    assert "an independent draw of the BASELINE configuration" in block


def test_the_harness_records_a_refused_control_in_the_payload():
    src = _runner_source()
    assert 'payload["control"] = {' in src
    assert '"drawn": False' in src
    assert "--no-control was passed: the gate has no paired OFF/OFF floor" in src


def test_the_help_documents_why_the_control_is_automatic():
    src = _runner_source()
    assert "price the draw floor and read rule #8 draw-stable" in src
    assert "--no-control" in src


@pytest.mark.parametrize("axis", ["ans_correctness_strict", "ref_conciseness"])
def test_the_floor_is_reported_for_the_axes_a_gate_decides_on(axis):
    assert axis in AXES

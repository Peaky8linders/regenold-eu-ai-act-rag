"""R461 - hard rule #8's OPERATING DEFINITION: the veto reads the lever's rows.

Rule #8 ("a lever that drops a gold HEAD on any row is vetoed regardless of
means") was read on every shared row, which made a TRANSPORT event a lever
verdict: the R461 count-only gate tripped it on a row whose own provenance says
``stage2_served_by=deterministic`` - both Stage-2 legs failed, the Stage-1 draft
shipped, and the block under test was never in the answer the judge scored.

These tests pin the replacement contract, and pin it in both directions, because
a scope that only ever narrows a veto is indistinguishable from an exemption:

* a row where the lever's payload did NOT serve arm B's answer cannot veto;
* that row, and the drop on it, stays in the report (``gold_dropped_head`` and
  the ``veto`` block both name it) - nothing leaves the record;
* ``--veto-scope all`` reproduces the pre-R461 definition exactly, so published
  verdicts stay re-derivable;
* provenance that cannot be read FALLS BACK to ``all``; a missing file is not
  evidence that a lever ran, so it must never lift a veto;
* a drop on a row whose provenance cannot tell whether the lever ran reads
  UNDECIDED, not CLEAN.

The draw-instability finding that motivated the fix is pinned too: on the
byte-identical noise-floor pair the veto must still fire under the new
definition, otherwise the scope change would have erased a measured result.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from evals.official.paired_ab import (
    AXES,
    DEFAULT_VETO_SCOPE,
    LEVER_RAN_LEGS,
    VETO_SCOPES,
    _bootstrap_ci,
    _gold_dropped_head,
    _lever_ran,
    _load_rows,
    _mean,
    _resolve_ckpt,
    _row_axis,
    _row_scope_reason,
    compare,
    main,
)

REPO = Path(__file__).resolve().parents[1]
R388 = REPO / "docs" / "measurements" / "r388"
RESULTS = REPO / "evals" / "bench" / "results"

GOLD = "Article 5"
OTHER = "Article 6"


# --------------------------------------------------------------------------- #
# synthetic arms
# --------------------------------------------------------------------------- #
def _row(qid: str, refs, expected, criteria=(True, True, True)) -> dict:
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


def _prov(leg: str | None = None, polish: bool | None = None) -> dict:
    prov: dict = {}
    if leg is not None:
        prov["stage2_served_by"] = leg
    if polish is not None:
        prov["stage2_polish"] = polish
    return prov


def _write_arm(
    tmp_path: Path,
    name: str,
    rows: list[dict],
    provs: dict[str, dict] | None,
    *,
    ckpt_name: str | None = None,
    record_ckpt: bool = True,
    ckpt_exists: bool = True,
) -> Path:
    """Write one synthetic score payload (+ the checkpoint it was built from)."""
    payload = {"label": name, "mode": "hard", "rows": rows}
    if provs is not None:
        ckpt = tmp_path / (ckpt_name or f"{name}.ckpt.jsonl")
        if ckpt_exists:
            ckpt.write_text(
                "\n".join(
                    json.dumps({"id": qid, "provenance": prov})
                    for qid, prov in provs.items()
                )
                + "\n",
                encoding="utf-8",
            )
        if record_ckpt:
            payload["ckpt"] = str(ckpt)
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pair(tmp_path: Path, b_leg: str | None, *, b_polish: bool | None = True,
          a_leg: str | None = "primary", extra_b: dict | None = None):
    """Arm A cites the gold head everywhere; arm B drops it on one live row and
    on one row served by ``b_leg``."""
    rows_a = [_row("rg_live", [GOLD], [GOLD]), _row("rg_deg", [GOLD], [GOLD])]
    rows_b = [_row("rg_live", [OTHER], [GOLD]), _row("rg_deg", [OTHER], [GOLD])]
    provs_a = {"rg_live": _prov(a_leg, True), "rg_deg": _prov(a_leg, True)}
    provs_b = {"rg_live": _prov("primary", True), "rg_deg": _prov(b_leg, b_polish)}
    if extra_b:
        provs_b.update(extra_b)
    a = _write_arm(tmp_path, "arm_a", rows_a, provs_a)
    b = _write_arm(tmp_path, "arm_b", rows_b, provs_b)
    return a, b


# --------------------------------------------------------------------------- #
# the reason table
# --------------------------------------------------------------------------- #
def test_scope_reason_reads_the_engine_vocabulary():
    assert _row_scope_reason(_prov("primary", True)) == "primary"
    assert _row_scope_reason(_prov("fallback", True)) == "fallback"
    assert _row_scope_reason(_prov("deterministic", False)) == "deterministic"
    assert _row_scope_reason(_prov("prior_turn", True)) == "prior_turn"
    # A checkpoint written before stage2_served_by existed: the polish flag is
    # the only leg hint it carries.
    assert _row_scope_reason(_prov(polish=True)) == "primary"
    assert _row_scope_reason(_prov(polish=False)) == "unpolished"
    assert _row_scope_reason({}) == "unknown"
    assert _row_scope_reason(None) == "no_provenance"
    assert _row_scope_reason("not-a-dict") == "unknown"


def test_lever_ran_is_true_only_for_the_legs_that_carried_the_payload():
    for reason in LEVER_RAN_LEGS:
        assert _lever_ran(reason) is True
    for reason in ("deterministic", "prior_turn", "unpolished", "unknown", "no_provenance"):
        assert _lever_ran(reason) is False


def test_unknown_leg_name_is_a_serve_not_an_exemption():
    """A label this module does not know must not widen the exemption.

    The engine writes ``stage2_served_by`` only when a leg served the wire, and
    the two labels that mean "the Stage-2 output was discarded" are named
    explicitly; anything else is read as a serve.
    """
    assert _row_scope_reason(_prov("some-future-leg", True)) == "primary"
    assert _lever_ran(_row_scope_reason(_prov("some-future-leg", True))) is True


# --------------------------------------------------------------------------- #
# the veto scope
# --------------------------------------------------------------------------- #
def test_default_scope_is_lever():
    assert DEFAULT_VETO_SCOPE == "lever"
    assert set(VETO_SCOPES) == {"lever", "all"}


def test_degraded_row_cannot_veto_but_the_other_row_still_does(tmp_path):
    a, b = _pair(tmp_path, "deterministic", b_polish=False)
    res = compare(a, b)
    v = res["veto"]
    assert v["verdict"] == "VETO" and v["fires"] is True
    assert [d["id"] for d in v["drops_in_scope"]] == ["rg_live"]
    assert [(d["id"], d["arm_b"]) for d in v["drops_out_of_scope"]] == [
        ("rg_deg", "deterministic")
    ]
    assert v["scope"] == "lever" and v["scope_downgraded"] is False
    assert v["excluded_rows"] == 1 and v["eligible_rows"] == 1
    assert v["excluded"] == [{"id": "rg_deg", "arm_a": "primary", "arm_b": "deterministic"}]


def test_a_drop_only_on_the_degraded_row_is_clean_and_still_reported(tmp_path):
    """The R461 count-only case: the sole drop is on a row the lever never served."""
    a, b = _pair(tmp_path, "deterministic", b_polish=False)
    # Make the live row drop-free: both arms cite the gold head there.
    rows = json.loads(b.read_text(encoding="utf-8"))
    for row in rows["rows"]:
        if row["id"] == "rg_live":
            row["refs"] = [GOLD]
    b.write_text(json.dumps(rows), encoding="utf-8")

    res = compare(a, b)
    v = res["veto"]
    assert v["verdict"] == "CLEAN" and v["fires"] is False
    assert [d["id"] for d in v["drops_out_of_scope"]] == ["rg_deg"]
    # Nothing left the record: the all-rows counts still name the drop, and the
    # out-of-scope entry carries the reason.
    assert res["gold_dropped_head"]["new_drops_in_b"] == ["rg_deg"]
    assert res["gold_dropped_head"]["arm_b"] == 1
    assert v["drops_out_of_scope"][0]["arm_b"] == "deterministic"
    assert "deterministic" in v["reasons"]


def test_scope_all_reproduces_the_pre_r461_definition(tmp_path):
    a, b = _pair(tmp_path, "deterministic", b_polish=False)
    rows = json.loads(b.read_text(encoding="utf-8"))
    for row in rows["rows"]:
        if row["id"] == "rg_live":
            row["refs"] = [GOLD]
    b.write_text(json.dumps(rows), encoding="utf-8")

    res = compare(a, b, veto_scope="all")
    v = res["veto"]
    assert v["scope"] == "all" and v["scope_requested"] == "all"
    assert v["fires"] is True and v["verdict"] == "VETO"
    assert [d["id"] for d in v["drops_in_scope"]] == ["rg_deg"]
    assert v["excluded"] == [] and v["drops_out_of_scope"] == []
    assert v["eligible_rows"] == v["rows_considered"] == 2


def test_the_two_scopes_differ_only_in_where_the_veto_is_read(tmp_path):
    a, b = _pair(tmp_path, "deterministic", b_polish=False)
    lever = compare(a, b)
    legacy = compare(a, b, veto_scope="all")
    # The record of drops is scope-independent ...
    assert lever["gold_dropped_head"] == legacy["gold_dropped_head"]
    assert lever["axes"] == legacy["axes"]
    assert lever["mean_answer_chars"] == legacy["mean_answer_chars"]
    # ... and the scoped verdict is not: the live row vetoes in both, the
    # degraded row vetoes only under the legacy definition.
    assert {d["id"] for d in lever["veto"]["drops_in_scope"]} == {"rg_live"}
    assert {d["id"] for d in legacy["veto"]["drops_in_scope"]} == {"rg_live", "rg_deg"}


@pytest.mark.parametrize("leg", ["prior_turn", "fallback"])
def test_prior_turn_is_out_of_scope_and_fallback_is_in_scope(tmp_path, leg):
    a, b = _pair(tmp_path, leg, b_polish=True)
    res = compare(a, b)
    v = res["veto"]
    if leg == "fallback":
        # Same request payload, other transport: the lever ran there too.
        assert {d["id"] for d in v["drops_in_scope"]} == {"rg_live", "rg_deg"}
        assert v["drops_out_of_scope"] == []
    else:
        assert [d["id"] for d in v["drops_out_of_scope"]] == ["rg_deg"]
        assert v["drops_out_of_scope"][0]["arm_b"] == "prior_turn"


def test_curated_unpolished_row_with_a_drop_is_out_of_scope(tmp_path):
    a, b = _pair(tmp_path, None, b_polish=False)
    res = compare(a, b)
    v = res["veto"]
    assert [d["id"] for d in v["drops_out_of_scope"]] == ["rg_deg"]
    assert v["drops_out_of_scope"][0]["arm_b"] == "unpolished"
    assert v["by_reason_b"]["unpolished"] == 1
    assert v["verdict"] == "VETO"  # the live row still vetoes


def test_unreadable_provenance_falls_back_to_the_legacy_scope(tmp_path):
    """A missing checkpoint must not lift a veto."""
    a, b = _pair(tmp_path, "deterministic", b_polish=False)
    rows = json.loads(b.read_text(encoding="utf-8"))
    for row in rows["rows"]:
        if row["id"] == "rg_live":
            row["refs"] = [GOLD]
    b.write_text(json.dumps(rows), encoding="utf-8")

    res = compare(a, b, b_ckpt=tmp_path / "does-not-exist.ckpt.jsonl")
    v = res["veto"]
    assert v["scope"] == "all" and v["scope_downgraded"] is True
    assert "no per-row provenance for arm B" in v["downgrade_reason"]
    assert v["fires"] is True

    # Same for a payload that records no checkpoint at all.
    stripped = json.loads(b.read_text(encoding="utf-8"))
    stripped.pop("ckpt", None)
    b.write_text(json.dumps(stripped), encoding="utf-8")
    v2 = compare(a, b)["veto"]
    assert v2["scope"] == "all" and v2["scope_downgraded"] is True
    assert v2["fires"] is True


def test_provenance_that_cannot_tell_reads_undecided_not_clean(tmp_path):
    """A row with no leg and no polish flag is not evidence the lever ran.

    The arm is otherwise readable (``rg_live`` names the primary leg), so the
    scope applies and the unreadable row is the one thing it cannot settle.
    """
    a, b = _pair(tmp_path, "primary", extra_b={"rg_deg": {}})
    rows = json.loads(b.read_text(encoding="utf-8"))
    for row in rows["rows"]:
        if row["id"] == "rg_live":
            row["refs"] = [GOLD]
    b.write_text(json.dumps(rows), encoding="utf-8")

    res = compare(a, b)
    v = res["veto"]
    assert v["scope_downgraded"] is False
    assert v["by_reason_b"]["unknown"] == 1
    assert [d["id"] for d in v["drops_undecided"]] == ["rg_deg"]
    assert v["drops_in_scope"] == [] and v["drops_out_of_scope"] == []
    assert v["fires"] is False
    assert v["verdict"] == "UNDECIDED"


def test_checkpoint_that_names_no_leg_downgrades_to_the_legacy_scope(tmp_path):
    """Pre-R417 provenance carried no leg field at all; that is not a scope."""
    # Arm B's whole checkpoint predates the leg fields: every provenance dict
    # is empty, which is what R413/R415 checkpoints look like on disk.
    a, b = _pair(tmp_path, "primary", extra_b={"rg_live": {}, "rg_deg": {}})
    res = compare(a, b)
    v = res["veto"]
    assert v["scope"] == "all" and v["scope_downgraded"] is True
    assert "names no leg on any row" in v["downgrade_reason"]
    assert v["fires"] is True and v["verdict"] == "VETO"
    assert v["eligible_rows"] == v["rows_considered"]


def test_vacuous_scope_downgrades_instead_of_reading_clean(tmp_path):
    """No row was served by a Stage-2 leg: the scope proves nothing."""
    # Every arm-B row is a curated/intercepted answer: no Stage-2 call anywhere.
    a, b = _pair(
        tmp_path,
        "primary",
        extra_b={"rg_live": _prov(polish=False), "rg_deg": _prov(polish=False)},
    )
    res = compare(a, b)
    v = res["veto"]
    assert v["scope_downgraded"] is True
    assert "no gold row is lever-eligible (0 of 2)" in v["downgrade_reason"]
    assert v["scope"] == "all" and v["fires"] is True and v["verdict"] == "VETO"


def test_row_missing_from_the_checkpoint_is_undecided_not_clean(tmp_path):
    """A row absent from the roster cannot testify: reported, never CLEAN."""
    a, b = _pair(tmp_path, "deterministic", b_polish=False)
    rows = json.loads(b.read_text(encoding="utf-8"))
    for row in rows["rows"]:
        if row["id"] == "rg_live":
            row["refs"] = [GOLD]
    b.write_text(json.dumps(rows), encoding="utf-8")
    b_payload = json.loads(b.read_text(encoding="utf-8"))
    ckpt = Path(b_payload["ckpt"])
    kept = [
        ln
        for ln in ckpt.read_text(encoding="utf-8").splitlines()
        if "rg_deg" not in ln
    ]
    ckpt.write_text("\n".join(kept) + "\n", encoding="utf-8")

    res = compare(a, b)
    v = res["veto"]
    assert v["scope"] == "lever" and v["scope_downgraded"] is False
    assert v["by_reason_b"]["no_provenance"] == 1
    assert v["by_reason_b"]["primary"] == 1
    assert [d["id"] for d in v["drops_undecided"]] == ["rg_deg"]
    assert v["drops_in_scope"] == [] and v["drops_out_of_scope"] == []
    assert v["verdict"] == "UNDECIDED"
    # The all-rows record keeps the drop, and the reader can see which row the
    # scope could not read.
    assert res["gold_dropped_head"]["new_drops_in_b"] == ["rg_deg"]
    assert v["drops_undecided"][0]["arm_b"] == "no_provenance"


def test_confounded_row_fires_but_is_flagged(tmp_path):
    """Arm B ran the lever while arm A was degraded: veto, and say why."""
    a, b = _pair(tmp_path, "primary", a_leg="deterministic")
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "arm_a.ckpt.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert {ln["provenance"]["stage2_served_by"] for ln in lines} == {"deterministic"}

    res = compare(a, b)
    v = res["veto"]
    assert v["by_reason_a"]["deterministic"] == 2
    assert v["fires"] is True
    assert set(v["drops_in_scope_confounded_a"]) == {"rg_live", "rg_deg"}


# --------------------------------------------------------------------------- #
# plumbing the round's other scripts depend on
# --------------------------------------------------------------------------- #
def test_resolve_ckpt_prefers_the_override_and_reads_the_payload_key(tmp_path):
    a, _b = _pair(tmp_path, "primary")
    payload = json.loads(a.read_text(encoding="utf-8"))
    assert _resolve_ckpt(a, None) == Path(payload["ckpt"])

    override = tmp_path / "elsewhere.ckpt.jsonl"
    override.write_text("", encoding="utf-8")
    assert _resolve_ckpt(a, override) == override
    # A relative override resolves against the repo root, like the payload key.
    assert _resolve_ckpt(a, "evals/bench/results/x.ckpt.jsonl") == (
        REPO / "evals/bench/results/x.ckpt.jsonl"
    )
    assert _resolve_ckpt(a, None) is not None


def test_compare_keeps_the_legacy_positional_signature(tmp_path):
    a, b = _pair(tmp_path, "primary")
    res = compare(a, b, 403)
    assert res["shared_rows"] == 2 and "veto" in res
    assert res["veto"]["provenance"]["bootstrap_seed"] == 403


def test_module_surface_the_round_scripts_import_is_unchanged():
    """``count_only_attribution.py`` and ``rule8_audit.py`` import these names."""
    assert AXES and isinstance(AXES, list)
    assert callable(_bootstrap_ci) and callable(_mean) and callable(_row_axis)
    assert callable(_gold_dropped_head) and callable(_load_rows)
    assert _load_rows(R388 / "score-r461-counton-s3-hard.json")


def test_cli_exposes_both_scopes_and_prints_the_scoped_verdict(tmp_path, monkeypatch, capsys):
    a, b = _pair(tmp_path, "deterministic", b_polish=False)
    rows = json.loads(b.read_text(encoding="utf-8"))
    for row in rows["rows"]:
        if row["id"] == "rg_live":
            row["refs"] = [GOLD]
    b.write_text(json.dumps(rows), encoding="utf-8")
    out = tmp_path / "paired.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["paired_ab", "--a", str(a), "--b", str(b), "--veto-scope", "all", "--out", str(out)],
    )
    assert main() == 0
    printed = capsys.readouterr().out
    assert "scope=all" in printed and "rule #8 veto: VETO" in printed
    assert "NEW DROPS IN B: ['rg_deg']" in printed
    assert json.loads(out.read_text(encoding="utf-8"))["veto"]["scope"] == "all"


# --------------------------------------------------------------------------- #
# the measured cases this fix has to answer for (skipped without the draws)
# --------------------------------------------------------------------------- #
R461_OFF = R388 / "score-r461-countoff-s3-hard.json"
R461_COUNT = R388 / "score-r461-counton-s3-hard.json"
R460_OFF = R388 / "score-r460-tunnel-off-s3-hard.json"
R460_FULL = R388 / "score-r460-tunnel-on-s3-hard.json"


def _have(*paths: Path) -> bool:
    if not all(p.exists() for p in paths):
        return False
    for p in paths:
        ckpt = json.loads(p.read_text(encoding="utf-8")).get("ckpt")
        if not ckpt or not (REPO / ckpt).exists():
            return False
    return True


@pytest.mark.skipif(
    not _have(R461_OFF, R461_COUNT), reason="R461 draws are gitignored / not on disk"
)
def test_r461_gate_reads_clean_under_the_lever_scope_and_names_the_row():
    a, b = R461_OFF, R461_COUNT
    lever = compare(a, b)
    legacy = compare(a, b, veto_scope="all")

    assert legacy["veto"]["fires"] is True
    assert legacy["veto"]["drops_in_scope"][0]["id"] == "rg_037"
    assert legacy["veto"]["drops_in_scope"][0]["arm_b"] == "deterministic"

    assert lever["veto"]["fires"] is False
    assert lever["veto"]["verdict"] == "CLEAN"
    assert [d["id"] for d in lever["veto"]["drops_out_of_scope"]] == ["rg_037"]
    # The drop is still in the all-rows record on both reads.
    assert lever["gold_dropped_head"]["new_drops_in_b"] == ["rg_037"]
    assert lever["gold_dropped_head"] == legacy["gold_dropped_head"]
    # 35 gold rows, one degraded: the scope evaluates 27 and excludes 1 live row
    # (7 rows are curated/unpolished in B, which never had a Stage-2 call).


@pytest.mark.skipif(
    not _have(R460_OFF, R461_OFF), reason="noise-floor draws are gitignored / not on disk"
)
def test_noise_floor_pair_still_vetoes_under_the_lever_scope():
    """Two draws of an UNCHANGED arm, byte-identical prompts: the veto must fire.

    If the scope change had silenced this pair it would have erased the
    draw-instability finding rather than reporting it.
    """
    res = compare(R460_OFF, R461_OFF)
    v = res["veto"]
    assert v["fires"] is True and v["verdict"] == "VETO"
    assert [d["id"] for d in v["drops_in_scope"]] == ["rg_061", "rg_088"]
    assert all(d["arm_b"] == "primary" for d in v["drops_in_scope"])
    assert v["drops_out_of_scope"] == []


@pytest.mark.skipif(
    not _have(R460_OFF, R460_FULL), reason="R460 draws are gitignored / not on disk"
)
def test_r460_full_block_veto_also_rested_on_a_degraded_row():
    """R460-FULL's rg_037 shipped the PREVIOUS TURN's answer.

    Recorded because it is a re-read of a shipped round's rule-#8 finding, not
    just of R461's: the row is ``prior_turn`` there.
    """
    lever = compare(R460_OFF, R460_FULL)
    assert lever["veto"]["fires"] is False
    assert [(d["id"], d["arm_b"]) for d in lever["veto"]["drops_out_of_scope"]] == [
        ("rg_037", "prior_turn")
    ]
    assert compare(R460_OFF, R460_FULL, veto_scope="all")["veto"]["fires"] is True

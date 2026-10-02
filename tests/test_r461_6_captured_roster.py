"""R461.6 - a published verdict stays re-auditable from the record alone.

The R461.4 audit's finding: the per-row provenance a scope decision reads lives
in a GITIGNORED checkpoint, so the moment that file is gone the question "was
this refusal decided by a row the lever never served?" is unanswerable forever
(r403's three VETOs are the measured cost). This round makes every NEW read
carry the evidence:

* ``veto.roster`` embeds, per arm, the row-id -> reason map the scope was read
  from, the considered row set, and which checkpoint it came from (or why it
  could not be read);
* the audit falls back to that capture when the checkpoint is gone, so the
  CURRENT rule is re-applied to the CAPTURED rows instead of to nothing;
* a live checkpoint always wins over the capture, and a read published before
  the capture (no ``veto.roster``) stays exactly as auditable as it was -
  the fallback cannot invent provenance, only preserve it.

The capture is evidence, not authority: it is trusted the same way the file is
trusted - as the roster of what each leg served - and the eligibility predicate
is still applied by the current instrument at audit time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from docs.measurements.r461.audit_published_gates import audit_read  # noqa: E402
from evals.official.paired_ab import compare  # noqa: E402

GOLD = "Article 5"
OTHER = "Article 6"
NL = chr(10)


def _row(qid: str, refs, expected=(GOLD,)) -> dict:
    return {
        "id": qid,
        "refs": list(refs),
        "expected_refs": list(expected),
        "criteria": [True, True, True],
        "criteria_text": ["c"] * 3,
        "criterion_remarks": [""] * 3,
        "n_criteria_passed": 3,
        "answer_chars": 900,
        "reference_chars": 700,
        "tone_ok": True,
        "latency_s": 1.0,
        "question": f"question {qid}",
    }


#: arm A holds its gold everywhere; arm B drops it on ``rg_037`` only.
ROWS_A = [_row("rg_037", [GOLD]), _row("rg_keep", [GOLD, OTHER])]
ROWS_B = [_row("rg_037", [OTHER]), _row("rg_keep", [GOLD, OTHER])]


def _arm(
    tmp_path: Path,
    name: str,
    rows,
    *,
    leg: str | None = "primary",
    legs: dict[str, str] | None = None,
    mode: str = "write",
) -> Path:
    """A score payload plus the checkpoint its provenance comes from.

    ``mode``: ``write`` (checkpoint on disk), ``missing`` (path recorded, file
    gone), ``none`` (no checkpoint key).
    """
    ckpt = tmp_path / f"{name}.ckpt.jsonl"
    if mode == "write":
        entries = []
        for row in rows:
            entry = {
                "id": row["id"],
                "provenance": {
                    "stage2_served_by": (legs or {}).get(row["id"], leg),
                    "stage2_polish": True,
                },
            }
            entries.append(json.dumps(entry))
        ckpt.write_text(NL.join(entries) + NL, encoding="utf-8")
    payload: dict = {"label": name, "mode": "hard", "rows": rows}
    if mode in ("write", "missing"):
        payload["ckpt"] = str(ckpt)
    score = tmp_path / f"score-{name}-hard.json"
    score.write_text(json.dumps(payload), encoding="utf-8")
    return score


def _publish(tmp_path: Path, read: dict, name: str = "paired-read.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(read), encoding="utf-8")
    return path


def _drop_arm(tmp_path: Path, tag: str = "gate") -> tuple[Path, Path, Path]:
    """The canonical pair: a real rule-#8 drop that is a transport event."""
    a = _arm(tmp_path, f"{tag}-a", ROWS_A)
    b = _arm(tmp_path, f"{tag}-b", ROWS_B, legs={"rg_037": "deterministic"})
    return a, b, tmp_path / f"{tag}-b.ckpt.jsonl"


# --------------------------------------------------------------------------- #
# what a published read now carries
# --------------------------------------------------------------------------- #
def test_the_published_read_carries_the_roster_it_was_decided_on(tmp_path):
    a, b, _ = _drop_arm(tmp_path)
    res = compare(a, b)
    roster = res["veto"]["roster"]
    assert roster["arm_a"]["captured"] is True
    assert roster["arm_b"]["captured"] is True
    assert roster["arm_b"]["reasons"]["rg_037"] == "deterministic"
    assert roster["arm_a"]["reasons"]["rg_037"] == "primary"
    assert roster["considered"] == ["rg_037", "rg_keep"]
    assert "gate-b.ckpt.jsonl" in roster["arm_b"]["source"]


def test_a_read_without_a_readable_checkpoint_captures_nothing(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A, mode="missing")
    b = _arm(tmp_path, "gate-b", ROWS_B, mode="missing")
    res = compare(a, b)
    roster = res["veto"]["roster"]
    assert roster["arm_a"]["captured"] is False
    assert roster["arm_a"]["reasons"] == {}
    assert roster["considered"] == ["rg_037", "rg_keep"]
    assert res["veto"]["scope_downgraded"] is True


# --------------------------------------------------------------------------- #
# the fallback: the record answers when the checkpoint is gone
# --------------------------------------------------------------------------- #
def test_a_verdict_is_re_auditable_after_the_checkpoint_is_gone(tmp_path):
    a, b, ckpt_b = _drop_arm(tmp_path)
    read = _publish(tmp_path, compare(a, b, veto_scope="all"))
    index = {a.name: a, b.name: b}

    fresh = audit_read(read, index, {})
    assert fresh["classification"] == "scope_decided_refusal"

    # The gitignored checkpoints are gone - the case the audit exists for.
    (tmp_path / "gate-a.ckpt.jsonl").unlink()
    ckpt_b.unlink()
    gone = audit_read(read, index, {})

    assert gone["classification"] == fresh["classification"]
    assert gone["reaudit"]["lever"]["scope_downgraded"] is False
    assert gone["reaudit"]["lever"]["verdict"] == "CLEAN"
    assert gone["reaudit"]["lever"]["eligible_rows"] == 1
    moved = gone["reaudit"]["lever"]["out_of_scope_rows"]
    assert [m["id"] for m in moved] == ["rg_037"]
    assert moved[0]["arm_b"] == "deterministic"
    # The decisions are identical to the file-backed read, not merely similar.
    assert (
        gone["reaudit"]["lever"]["deciding_rows"]
        == fresh["reaudit"]["lever"]["deciding_rows"]
    )
    assert "checkpoint gone" in gone["provenance"]["arm_a"]
    assert "CAPTURED roster" in gone["provenance"]["arm_b"]


def test_compare_uses_a_provided_roster_only_when_the_file_is_gone(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A, mode="missing")
    b = _arm(tmp_path, "gate-b", ROWS_B, mode="missing")
    res = compare(
        a,
        b,
        a_roster={"rg_037": "primary", "rg_keep": "primary"},
        b_roster={"rg_037": "deterministic", "rg_keep": "primary"},
    )
    assert res["veto"]["scope"] == "lever"
    assert res["veto"]["eligible_rows"] == 1
    assert res["veto"]["verdict"] == "CLEAN"
    assert res["veto"]["roster"]["arm_a"]["source"].startswith("captured roster")


def test_a_live_checkpoint_wins_over_the_captured_roster(tmp_path):
    a, b, ckpt_b = _drop_arm(tmp_path)
    read = _publish(tmp_path, compare(a, b, veto_scope="all"))
    index = {a.name: a, b.name: b}

    # The file is rewritten to say the lever DID serve the row. The file wins.
    ckpt_b.write_text(
        NL.join(
            json.dumps(
                {
                    "id": row["id"],
                    "provenance": {"stage2_served_by": "primary", "stage2_polish": True},
                }
            )
            for row in ROWS_B
        )
        + NL,
        encoding="utf-8",
    )
    live = audit_read(read, index, {})
    assert live["reaudit"]["lever"]["verdict"] == "VETO"
    assert live["classification"] == "refusal_survives_the_fix"

    # With the file gone, the capture answers again - and only then.
    ckpt_b.unlink()
    captured = audit_read(read, index, {})
    assert captured["reaudit"]["lever"]["verdict"] == "CLEAN"
    assert captured["classification"] == "scope_decided_refusal"


def test_reads_published_before_the_capture_stay_unverifiable(tmp_path):
    """No roster in the record and no checkpoint on disk: nothing to audit with."""
    a = _arm(tmp_path, "gate-a", ROWS_A, mode="missing")
    b = _arm(tmp_path, "gate-b", ROWS_B, mode="missing")
    read = _publish(tmp_path, {"arm_a": a.name, "arm_b": b.name, "axes": {}})
    out = audit_read(read, {a.name: a, b.name: b}, {})
    assert out["classification"] == "unverifiable"
    assert out["reaudit"]["lever"]["scope_downgraded"] is True
    assert "CAPTURED roster" not in out["provenance"]["arm_b"]

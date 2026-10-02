"""R461.4 - the gate-verdict audit's own contract.

The audit answers one question about every published verdict: was this refusal
decided by a gold-head drop on a row the lever never served? That makes its
CLASSIFIER load-bearing, so it is pinned here - including the two ways it was
wrong on the first run:

* a pair whose LEVER read fell back to the legacy scope was reported as "survives
  the fix". An unauditable pair is not a surviving refusal, so a downgrade on
  EITHER reading is ``unverifiable``;
* a re-draw was INFERRED from the request-shape digest, which nominated the same
  arm for reads from four different rounds. A re-draw is only accepted when it is
  DECLARED, and the digest can only refute the declaration.

A pair whose only gold row was never lever-served is not a counter-example to
either rule: with no lever-eligible row at all, R461's instrument downgrades the
scope to the stricter legacy definition and says so, which is why the fixtures
below always carry one row the lever served.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from docs.measurements.r461.audit_published_gates import (  # noqa: E402
    audit_read,
    find_redraw,
    resolve_ckpt,
)

GOLD = "Article 5"
OTHER = "Article 6"
DIGEST = "cb85452c9c04"
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
    digest: str | None = DIGEST,
    leg: str | None = "primary",
    legs: dict[str, str] | None = None,
    mode: str = "write",
) -> Path:
    """A score payload + the checkpoint its provenance comes from.

    ``mode``: ``write`` (checkpoint on disk), ``missing`` (path recorded but the
    file is gone - the case this audit exists for), ``none`` (no checkpoint key
    at all).
    """
    path = tmp_path / f"{name}.ckpt.jsonl"
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
            if digest:
                entry["hard_preamble_digest"] = digest
            entries.append(json.dumps(entry))
        path.write_text(NL.join(entries) + NL, encoding="utf-8")
    payload: dict = {"label": name, "mode": "hard", "rows": rows}
    if mode in ("write", "missing"):
        payload["ckpt"] = str(path)
    score = tmp_path / f"score-{name}-hard.json"
    score.write_text(json.dumps(payload), encoding="utf-8")
    return score


def _read(tmp_path: Path, a: Path, b: Path, published: dict | None = None) -> Path:
    path = tmp_path / "paired-read.json"
    body: dict = {"arm_a": a.name, "arm_b": b.name, "axes": {}}
    if published:
        body.update(published)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _audit(read: Path, arms: list[Path], declared: dict[str, str] | None = None) -> dict:
    return audit_read(read, {arm.name: arm for arm in arms}, declared or {})


# --------------------------------------------------------------------------- #
# the classifier
# --------------------------------------------------------------------------- #
def test_a_drop_on_a_row_the_lever_never_served_is_a_scope_decided_refusal(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A)
    b = _arm(tmp_path, "gate-b", ROWS_B, legs={"rg_037": "deterministic"})
    out = _audit(_read(tmp_path, a, b), [a, b])
    assert out["reaudit"]["all"]["verdict"] == "VETO"
    assert out["reaudit"]["lever"]["verdict"] == "CLEAN"
    assert out["classification"] == "scope_decided_refusal"
    moved = out["reaudit"]["lever"]["out_of_scope_rows"]
    assert [m["id"] for m in moved] == ["rg_037"]
    assert moved[0]["arm_b"] == "deterministic"
    assert out["reaudit"]["lever"]["eligible_rows"] == 1


def test_a_drop_on_a_served_row_survives_the_fix(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A)
    b = _arm(tmp_path, "gate-b", ROWS_B, legs={"rg_037": "primary"})
    out = _audit(_read(tmp_path, a, b), [a, b])
    assert out["classification"] == "refusal_survives_the_fix"
    assert [d["id"] for d in out["reaudit"]["lever"]["deciding_rows"]] == ["rg_037"]


def test_a_read_published_clean_is_not_a_refusal_to_overturn(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A)
    b = _arm(tmp_path, "gate-b", ROWS_B, legs={"rg_037": "deterministic"})
    read = _read(tmp_path, a, b, published={"veto": {"verdict": "CLEAN", "scope": "lever"}})
    out = _audit(read, [a, b])
    assert out["classification"] == "clean_read_already_scoped"
    # the legacy line is still recorded, so a reader can see what moved
    assert out["reaudit"]["all"]["verdict"] == "VETO"


def test_no_rule8_drop_at_all_is_not_a_refusal(tmp_path):
    keep = [_row("rg_037", [GOLD, OTHER]), _row("rg_keep", [GOLD, OTHER])]
    a = _arm(tmp_path, "gate-a", keep)
    b = _arm(tmp_path, "gate-b", keep)
    out = _audit(_read(tmp_path, a, b), [a, b])
    assert out["classification"] == "no_rule8_refusal"
    assert out["reaudit"]["all"]["verdict"] == "CLEAN"


def test_an_unauditable_pair_is_unverifiable_not_surviving(tmp_path):
    """The first-run defect: the LEVER read fell back to ``all`` and the pair was
    reported as a refusal that survives the scope change."""
    a = _arm(tmp_path, "gate-a", ROWS_A, mode="missing")
    b = _arm(tmp_path, "gate-b", ROWS_B, mode="missing")
    out = _audit(_read(tmp_path, a, b), [a, b])
    assert out["classification"] == "unverifiable"
    assert out["reaudit"]["lever"]["scope_downgraded"] is True
    assert "no per-row provenance" in out["why"]
    assert "checkpoint gone" in out["provenance"]["arm_a"]


def test_a_pair_with_no_ckpt_key_is_unverifiable_too(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A, mode="none")
    b = _arm(tmp_path, "gate-b", ROWS_B, mode="none")
    out = _audit(_read(tmp_path, a, b), [a, b])
    assert out["classification"] == "unverifiable"
    assert "no checkpoint recorded" in out["provenance"]["arm_a"]


def test_a_missing_score_payload_is_reported_not_skipped(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A)
    b = _arm(tmp_path, "gate-b", ROWS_B)
    out = _audit(_read(tmp_path, a, b), [a])
    assert out["classification"] == "unverifiable"
    assert "score payload missing" in out["why"]


# --------------------------------------------------------------------------- #
# the re-draw is declared, never inferred
# --------------------------------------------------------------------------- #
def test_a_redraw_is_refused_without_a_declaration(tmp_path):
    a = _arm(tmp_path, "gate-a", ROWS_A)
    twin = _arm(tmp_path, "twin", ROWS_A)
    b = _arm(tmp_path, "gate-b", ROWS_B)
    index = {arm.name: arm for arm in (a, twin, b)}
    ckpt_a, _why = resolve_ckpt(a, index)
    picked, why = find_redraw(a, ckpt_a, index, declared=None)
    assert picked is None
    assert "cannot be inferred" in why


def test_a_declared_redraw_is_used_and_refuted_on_the_digest(tmp_path):
    qids = [f"rg_{i:03d}" for i in range(1, 7)]
    hold = [_row(q, [GOLD]) for q in qids]
    a = _arm(tmp_path, "gate-a", hold)
    same = _arm(tmp_path, "same-shape", hold)
    other = _arm(tmp_path, "other-shape", hold, digest="deadbeef")
    b = _arm(tmp_path, "gate-b", [_row(q, [OTHER]) for q in qids])
    index = {arm.name: arm for arm in (a, same, other, b)}
    ckpt_a, _why = resolve_ckpt(a, index)

    picked, why = find_redraw(a, ckpt_a, index, declared="score-same-shape-hard.json")
    assert picked is not None and "declared" in why

    refused, why_bad = find_redraw(a, ckpt_a, index, declared="score-other-shape-hard.json")
    assert refused is None and "REFUTED" in why_bad

    absent, why_absent = find_redraw(a, ckpt_a, index, declared="not-on-disk")
    assert absent is None and "not found on disk" in why_absent


def test_the_audit_record_and_its_doc_exist():
    doc = REPO / "docs" / "measurements" / "r461" / "GATE-VERDICT-AUDIT.md"
    harness = REPO / "docs" / "measurements" / "r461" / "audit_published_gates.py"
    assert doc.exists() and harness.exists()
    text = doc.read_text(encoding="utf-8")
    assert "decided by a row the lever never served" in text
    assert "rg_037" in text

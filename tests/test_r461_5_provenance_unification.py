"""R461.5 - one row-provenance predicate for every gate.

Three gates used to read the same checkpoint fields their own way: hard rule
#8's row eligibility (``paired_ab``), the R422 void guard and the R423
exclusion list (``gate_validity``), and the runner's pooled exclusion list.
This round moved the reading into ``evals/bench/row_provenance`` and made every
row-scoped rule a predicate over it.

The contract pinned here, in both directions:

* ONE resolution per row, and three verdicts over it - ``lever_ran`` (rule #8:
  a fallback counts, and so does a leg name the vocabulary does not know),
  ``transport_degraded`` (R423: a fallback does NOT count, any named
  non-primary leg does) and ``deterministic_draft`` (R422). The fallback and
  the unrecognised name are read in opposite directions ON PURPOSE;
* every public name each gate exposes behaves exactly as before the move: the
  old readers are carried here verbatim as an oracle and asserted equal for
  every shape a checkpoint can carry, and for every row of every checkpoint on
  disk;
* a curated intercept (no leg named, not polished) stays OUT of the R423
  exclusion list while the R422 guard counts it as a draft - the documented
  asymmetry, pinned in both directions;
* the raw fields have exactly one home: an AST scan fails if any module outside
  ``evals/bench/row_provenance`` resolves a row's provenance by reading
  ``stage2_served_by`` / ``stage2_polish``, except for the named producer /
  monitor / report functions allowlisted below - none of which decides a gate.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from evals.bench import row_provenance as rp
from evals.harness import gate_validity as gv
from evals.official import paired_ab as pa
from evals.regenold import run_official_batch as rob

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "evals" / "bench" / "results"

_OLD_SCOPE_REASONS = (
    "primary",
    "fallback",
    "deterministic",
    "prior_turn",
    "unpolished",
    "unknown",
    "no_provenance",
)
_OLD_CLOSED = frozenset({"deterministic", "prior_turn", "unpolished"})


# --------------------------------------------------------------------------- #
# the pre-R461.5 readers, verbatim: the oracle every new helper is held to
# --------------------------------------------------------------------------- #
def _old_scope_reason(prov):
    if prov is None:
        return "no_provenance"
    if not isinstance(prov, dict):
        return "unknown"
    served = prov.get("stage2_served_by")
    if served not in (None, ""):
        leg = str(served)
        if leg in _OLD_SCOPE_REASONS:
            return leg
        return "primary"
    if prov.get("stage2_polish") is True:
        return "primary"
    if prov.get("stage2_polish") is False:
        return "unpolished"
    return "unknown"


def _old_lever_ran(reason):
    table = {r: r in ("primary", "fallback") for r in _OLD_SCOPE_REASONS}
    return table.get(reason, reason not in _OLD_CLOSED)


def _old_count_deterministic(rows):
    if not rows:
        return 0
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            continue
        served = prov.get("stage2_served_by")
        if served == "deterministic":
            n += 1
        elif served in (None, "") and prov.get("stage2_polish") is False:
            n += 1
    return n


def _old_degraded(rows):
    ids = []
    if not rows:
        return ids
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            continue
        served = prov.get("stage2_served_by")
        if served and str(served) != "primary":
            row_id = row.get("id")
            if row_id is not None:
                ids.append(str(row_id))
    return ids


def _old_census(rows):
    counts = {}
    if not rows:
        return counts
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            counts["unnamed"] = counts.get("unnamed", 0) + 1
            continue
        served = prov.get("stage2_served_by")
        if served in (None, ""):
            if prov.get("stage2_polish") is False:
                served = "deterministic"
            elif prov.get("stage2_polish") is True:
                served = "primary"
            else:
                served = "unnamed"
        counts[str(served)] = counts.get(str(served), 0) + 1
    return counts


def _shapes():
    """Every provenance shape a checkpoint can carry, plus malformed ones."""
    provs = []
    for leg in (
        None,
        "",
        "primary",
        "fallback",
        "deterministic",
        "prior_turn",
        "unpolished",
        "some-future-leg",
    ):
        provs.append({"stage2_served_by": leg})
        provs.append({"stage2_served_by": leg, "stage2_polish": True})
        provs.append({"stage2_served_by": leg, "stage2_polish": False})
    for polish in (None, True, False, 1, 0, "yes"):
        provs.append({"stage2_polish": polish})
    provs.extend([{}, None, "not-a-dict", 7, []])
    return provs


# --------------------------------------------------------------------------- #
# the vocabulary, read once
# --------------------------------------------------------------------------- #
def test_the_vocabulary_is_read_once():
    cases = [
        (None, rp.NO_PROVENANCE, "no_provenance", False, False, False, "unnamed"),
        ("x", rp.UNKNOWN, "unknown", False, False, False, "unnamed"),
        ({}, rp.UNKNOWN, "unknown", False, False, False, "unnamed"),
        ({"stage2_polish": True}, rp.PRIMARY, "primary", True, False, False, "primary"),
        ({"stage2_polish": False}, rp.UNPOLISHED, "unpolished", False, False, True, "deterministic"),
        ({"stage2_served_by": "primary"}, rp.PRIMARY, "primary", True, False, False, "primary"),
        ({"stage2_served_by": "fallback"}, rp.FALLBACK, "fallback", True, True, False, "fallback"),
        (
            {"stage2_served_by": "deterministic"},
            rp.DETERMINISTIC,
            "deterministic",
            False,
            True,
            True,
            "deterministic",
        ),
        ({"stage2_served_by": "prior_turn"}, rp.PRIOR_TURN, "prior_turn", False, True, False, "prior_turn"),
        (
            {"stage2_served_by": "some-future-leg"},
            rp.UNRECOGNISED,
            "primary",
            True,
            True,
            False,
            "some-future-leg",
        ),
    ]
    for prov, kind, reason, lever, degraded, draft, served in cases:
        resolved = rp.classify(prov)
        assert resolved.kind == kind
        assert rp.scope_reason(prov) == reason
        assert resolved.lever_ran is lever
        assert resolved.transport_degraded is degraded
        assert resolved.deterministic_draft is draft
        assert rp.served_leg(prov) == served


def test_lever_ran_reason_vocabulary():
    for reason in rp.SERVING_LEGS + (rp.UNRECOGNISED,):
        assert rp.lever_ran_reason(reason) is True
    for reason in rp.DISCARDED_LEGS + (rp.UNPOLISHED, rp.UNKNOWN, rp.NO_PROVENANCE):
        assert rp.lever_ran_reason(reason) is False
    # A reason outside the vocabulary must not silently exempt a row.
    assert rp.lever_ran_reason("some-foreign-reason") is True


def test_the_fallback_row_is_lever_evidence_and_a_degraded_transport():
    """The one row two gates read in opposite directions - on purpose."""
    resolved = rp.classify({"stage2_served_by": "fallback", "stage2_polish": True})
    assert resolved.lever_ran is True
    assert resolved.closed is False
    assert resolved.transport_degraded is True


def test_curated_intercept_is_neither_lever_evidence_nor_a_degradation():
    rows = [{"id": "rg_curated", "provenance": {"stage2_polish": False}}]
    resolved = rp.classify(rows[0]["provenance"])
    assert resolved.lever_ran is False
    # R422 counts it as a draft; R423 must leave it in the pair.
    assert resolved.deterministic_draft is True
    assert resolved.transport_degraded is False
    assert gv.degraded_row_ids(rows) == []
    assert gv.count_deterministic_rows(rows) == 1


def test_malformed_leg_value_is_degraded_but_never_exempted():
    """The one deliberate divergence from the pre-move readers.

    A present-but-falsy leg value (``0`` / ``False``) used to be skipped by the
    R423 exclusion - ``if served`` is falsy - while rule #8 read the same value
    as a named non-primary leg. The shared resolution reads any present value
    as a leg name, so R423 now EXCLUDES such a row instead of grading it: the
    conservative direction, and no checkpoint on disk carries one (pinned
    below). Rule #8's reading is unchanged.
    """
    rows = [{"id": "rg_bad", "provenance": {"stage2_served_by": 0}}]
    assert rp.scope_reason(rows[0]["provenance"]) == "primary"
    assert rp.lever_ran_reason(rp.scope_reason(rows[0]["provenance"])) is True
    assert gv.degraded_row_ids(rows) == ["rg_bad"]
    assert _old_degraded(rows) == []


# --------------------------------------------------------------------------- #
# the gates call the shared functions
# --------------------------------------------------------------------------- #
def test_every_gate_calls_the_shared_function():
    assert pa._row_scope_reason is rp.scope_reason
    assert pa._lever_ran is rp.lever_ran_reason
    assert gv.count_rows_served_by is rp.count_rows_served_by
    assert gv.count_deterministic_rows is rp.count_deterministic_rows
    assert gv.degraded_row_ids is rp.degraded_row_ids
    # The runner excludes through the shared predicate, not a copy of it.
    assert rob.degraded_row_ids is rp.degraded_row_ids


def test_report_vocabulary_is_unchanged():
    assert pa.SCOPE_REASONS is rp.SCOPE_REASONS
    assert set(pa.SCOPE_REASONS) == set(_OLD_SCOPE_REASONS)
    # ``unrecognised`` is a canonical kind, never a reported reason.
    assert "unrecognised" not in pa.SCOPE_REASONS
    assert pa.LEVER_RAN_LEGS == rp.SERVING_LEGS
    assert pa.DEGRADED_LEGS == rp.DISCARDED_LEGS
    assert pa._UNREADABLE_REASONS == rp.UNREADABLE_KINDS
    assert pa._CLOSED_REASONS == frozenset(rp.CLOSED_KINDS)


# --------------------------------------------------------------------------- #
# behaviour preservation, on every shape and on every row on disk
# --------------------------------------------------------------------------- #
def test_every_helper_matches_the_old_reader_for_every_shape():
    for prov in _shapes():
        row = {"id": "rg_x", "provenance": prov}
        assert rp.scope_reason(prov) == _old_scope_reason(prov)
        assert pa._row_scope_reason(prov) == _old_scope_reason(prov)
        assert gv.count_deterministic_rows([row]) == _old_count_deterministic([row])
        assert gv.degraded_row_ids([row]) == _old_degraded([row])
        assert gv.count_rows_served_by([row]) == _old_census([row])
    for reason in _OLD_SCOPE_REASONS + ("unrecognised", "some-foreign-reason"):
        assert rp.lever_ran_reason(reason) == _old_lever_ran(reason)


def test_every_row_on_disk_reads_exactly_as_before_the_move():
    checkpoints = sorted(RESULTS.glob("*.ckpt.jsonl"))
    if not checkpoints:
        pytest.skip("no checkpoints on disk (gitignored results directory)")
    checked = 0
    for path in checkpoints:
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("id") is not None:
                rows.append(row)
        if not rows:
            continue
        for row in rows:
            prov = row.get("provenance")
            assert rp.scope_reason(prov) == _old_scope_reason(prov)
        assert gv.count_deterministic_rows(rows) == _old_count_deterministic(rows)
        assert gv.degraded_row_ids(rows) == _old_degraded(rows)
        assert gv.count_rows_served_by(rows) == _old_census(rows)
        checked += len(rows)
    assert checked > 0


# --------------------------------------------------------------------------- #
# the raw fields have one home
# --------------------------------------------------------------------------- #
#: Modules allowed to read the raw fields directly, with the function names
#: allowed to do it. Every entry is a producer, a monitor or a report - never a
#: gate's row-scoped rule. Add an entry only with the reason that makes it not
#: a gate rule.
RAW_READ_ALLOWLIST = {
    # THE reader: the resolution every gate is routed through.
    "evals/bench/row_provenance.py": None,
    # Asserts the Bedrock capture arm actually landed, on a LIVE response.
    "evals/harness/prompt_ab.py": {"main"},
    # Extraction / report-side consumers of a live response or a finished run.
    "evals/regenold/antifragile_live.py": {"_parse_reasoning", "_aggregate_af"},
    "evals/regenold/diff_hard_sample.py": {"_stage2"},
    "evals/regenold/run_medtech_subpoint_eval.py": {"main"},
    # The recorder writes the fields; the monitor watches the live leg; the
    # summary reports the landed rate. None decides a graded row's scope.
    "evals/regenold/run_official_batch.py": {"_provenance", "observe", "_aggregate"},
}

#: The constants the leaf reads its own fields through: importing them is
#: just as much a raw read as typing the string.
_FIELD_CONSTANTS = {"FIELD_LEG", "FIELD_POLISH"}


def _is_field_key(node) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "stage2_served_by" in node.value or "stage2_polish" in node.value
    if isinstance(node, ast.Name):
        return node.id in _FIELD_CONSTANTS
    if isinstance(node, ast.Attribute):
        return node.attr in _FIELD_CONSTANTS
    return False


def _enclosing(tree, node):
    best = None
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(fn):
                if sub is node and (best is None or fn.lineno >= best.lineno):
                    best = fn
    return best.name if best is not None else None


def _raw_reads(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        hit = None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("get", "pop", "setdefault", "split")
            and node.args
            and _is_field_key(node.args[0])
        ):
            hit = "CALL." + node.func.attr
        elif isinstance(node, ast.Subscript) and _is_field_key(node.slice):
            hit = "SUBSCRIPT"
        elif isinstance(node, ast.Compare):
            for side in (node.left, *node.comparators):
                if _is_field_key(side):
                    hit = "COMPARE"
                    break
        if hit:
            found.append((node.lineno, _enclosing(tree, node), hit))
    return found


def test_the_raw_fields_have_one_home():
    offenders = {}
    for path in sorted((REPO / "evals").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel in RAW_READ_ALLOWLIST and RAW_READ_ALLOWLIST[rel] is None:
            continue
        allowed = RAW_READ_ALLOWLIST.get(rel)
        bad = [
            read
            for read in _raw_reads(path)
            if allowed is None or (read[1] or "") not in allowed
        ]
        if bad:
            offenders[rel] = bad
    assert offenders == {}, offenders


def test_the_allowlist_is_live():
    leaf = REPO / "evals" / "bench" / "row_provenance.py"
    assert _raw_reads(leaf), "the shared module must be the one reading the fields"
    for rel, funcs in RAW_READ_ALLOWLIST.items():
        path = REPO / rel
        assert path.exists(), rel
        if funcs is None:
            continue
        names = {read[1] for read in _raw_reads(path)}
        missing = funcs - names
        assert not missing, (rel, missing)

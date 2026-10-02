"""R461.4 -- audit every published gate verdict in the round records.

WHY THIS EXISTS
---------------
R461.1 changed WHERE hard rule #8 is read (the rows the lever actually served) and
R461.3 changed WHAT a drop has to be (draw-stable). Both changes can only ever
CLEAR a veto, so every refusal published before them asks the same question:

    was this refusal decided by a drop on a row the lever never served?

This script answers it mechanically, for every paired read in the round records,
instead of by re-reading each report by hand:

1. DISCOVER - every ``*.json`` under ``docs/measurements`` carrying
   ``arm_a``/``arm_b`` (the arms, by score-payload name) and ``axes``: the
   canonical reads written by ``evals.official.paired_ab``.
2. RESOLVE PROVENANCE - the checkpoint each arm's score payload records; if that
   path is gone (``evals/bench/results`` is gitignored), an exact-BASENAME copy
   preserved inside the round's own directory, else the read's own CAPTURED
   roster (R461.6, ``veto.roster`` - reads published before it carry none, and
   a live checkpoint always wins over the capture). Nothing is matched
   fuzzily: a guessed checkpoint is not provenance.
3. RE-READ - through the CURRENT instrument, three ways:
     ``all``    the pre-R461 definition,
     ``lever``  the fixed scope (the rows arm B's provenance says the lever served),
     draw-stable: the same read against a THIRD draw of arm A's own
                configuration, found automatically by per-row request digest.
4. CLASSIFY - a refusal is "scope-decided" when it fires under ``all`` and is
   CLEAN under ``lever``; the rows that moved out of scope are named, with the
   provenance that moved them. A read whose provenance is gone is reported
   UNVERIFIABLE, with what was tried - never silently skipped.

Usage:
    python -m docs.measurements.r461.audit_published_gates        (from the repo root)
    python audit_published_gates.py --out docs/measurements/r461/gate-verdict-audit.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
MEAS = REPO / "docs" / "measurements"
# This checkout is also installed EDITABLE (the venv's .pth points at the main
# checkout), so a script run by path can import a STALE evals/ - the pre-R461
# instrument, which has no veto_scope at all. The worktree root goes first.
sys.path.insert(0, str(REPO))

from evals.official.paired_ab import compare  # noqa: E402  (path set above)


def _load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _index() -> dict[str, Path]:
    """Every score payload on disk, by file name (how a read names its arms)."""
    out: dict[str, Path] = {}
    for p in glob.glob(str(MEAS / "**" / "score-*.json"), recursive=True):
        out.setdefault(Path(p).name, Path(p))
    return out


def _ckpt_rows(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id") is not None:
            rows[str(row["id"])] = row
    return rows


def resolve_ckpt(score_path: Path, index: dict[str, Path]) -> tuple[Path | None, str]:
    """The checkpoint this arm's provenance can be read from, or ``None``.

    Exact match only: the path the score payload records, else a copy preserved
    elsewhere in the records with the SAME basename (a moved file, not a
    guessed one).
    """
    payload = _load(score_path)
    recorded = payload.get("ckpt")
    if not recorded:
        return None, "no checkpoint recorded in the score payload"
    path = Path(str(recorded))
    path = path if path.is_absolute() else REPO / path
    if path.exists():
        return path, "recorded path exists"
    for cand in glob.glob(str(MEAS / "**" / path.name), recursive=True):
        return Path(cand), "in-tree copy, same basename"
    return None, f"checkpoint gone: {path.name}"


def find_redraw(
    score_a: Path,
    ckpt_a: Path | None,
    index: dict[str, Path],
    *,
    declared: str | None,
) -> tuple[Path | None, str]:
    """The DECLARED third draw of arm A, refused if the draws contradict it.

    A re-draw cannot be INFERRED from the request-shape digest: the digest
    covers the hard preamble and whatever ``--*-env`` declaration reaches it,
    and this audit found ONE shape digest on arms from four different rounds.
    So the caller declares the arm (``--declared-redraw``), and the digest is
    used the only way it is sound - to REFUTE the declaration when the rows
    disagree. No declaration: no draw-stable read, and the audit says so.
    """
    if declared is None:
        return None, (
            "no DECLARED re-draw: the digest identifies the request SHAPE only, "
            "so a re-draw cannot be inferred from it - pass --declared-redraw"
        )
    cand = index.get(declared)
    if cand is None:
        return None, f"declared re-draw not found on disk: {declared}"
    if ckpt_a is None:
        return None, "no checkpoint for arm A, so no declaration can be checked"
    ckpt_c, why = resolve_ckpt(cand, index)
    if ckpt_c is None:
        return None, f"declared re-draw has no checkpoint ({why})"
    rows_a, rows_c = _ckpt_rows(ckpt_a), _ckpt_rows(ckpt_c)
    shared = sorted(set(rows_a) & set(rows_c))
    if len(shared) < 5:
        return None, f"declared re-draw shares only {len(shared)} row(s)"
    dig_a = {q: str(rows_a[q].get("hard_preamble_digest") or "") for q in shared}
    dig_c = {q: str(rows_c[q].get("hard_preamble_digest") or "") for q in shared}
    missing = [q for q in shared if not dig_a[q] or not dig_c[q]]
    bad = [q for q in shared if dig_a[q] and dig_c[q] and dig_a[q] != dig_c[q]]
    if bad:
        return None, (
            f"declaration REFUTED on {len(bad)} row(s): the declared arm served a "
            "different request shape"
        )
    if missing:
        return None, (
            f"{len(missing)} shared row(s) carry no digest on one side, so the "
            "declaration cannot be checked"
        )
    return cand, (
        f"declared: {declared} - not refuted on {len(shared)} shared rows "
        "(request shape only; the declaration carries identity)"
    )

def _verdict(res: dict) -> dict:
    veto = res["veto"]
    return {
        "verdict": veto["verdict"],
        "scope": veto["scope"],
        "scope_downgraded": veto["scope_downgraded"],
        "downgrade_reason": veto["downgrade_reason"],
        "rows_considered": veto["rows_considered"],
        "eligible_rows": veto["eligible_rows"],
        "fires": veto["fires"],
        "deciding_rows": [
            {"id": d["id"], "arm_a": d["arm_a"], "arm_b": d["arm_b"]}
            for d in veto["drops_in_scope"]
        ],
        "out_of_scope_rows": [
            {"id": d["id"], "arm_a": d["arm_a"], "arm_b": d["arm_b"]}
            for d in veto["drops_out_of_scope"]
        ],
        "undecided_rows": [
            {"id": d["id"], "arm_a": d["arm_a"], "arm_b": d["arm_b"]}
            for d in veto["drops_undecided"]
        ],
        "draw_stable": veto.get("draw_stable"),
        "cleared_by_redraw": (veto.get("draw_stability") or {}).get("drops_unstable") or [],
        "gold_dropped_head": res["gold_dropped_head"],
    }


def _read_key(path: Path) -> str:
    """How a read is named: repo-relative when it is inside the records."""
    try:
        return str(Path(path).relative_to(REPO))
    except ValueError:
        return str(path)

def audit_read(
    read_path: Path, index: dict[str, Path], declared_redraws: dict[str, str]
) -> dict:
    d = _load(read_path)
    a_name, b_name = str(d["arm_a"]), str(d["arm_b"])
    out: dict[str, Any] = {
        "read": _read_key(read_path),
        "arms": {"a": a_name, "b": b_name},
        "published": {
            "veto_block": "veto" in d,
            "veto": (d.get("veto") or {}).get("verdict"),
            "scope": (d.get("veto") or {}).get("scope"),
            "gold_dropped_head": d.get("gold_dropped_head"),
        },
        "provenance": {},
        "reaudit": None,
        "classification": "",
        "why": "",
    }
    score_a, score_b = index.get(a_name), index.get(b_name)
    if score_a is None or score_b is None:
        missing = a_name if score_a is None else b_name
        out["classification"] = "unverifiable"
        out["why"] = f"score payload missing: {missing}"
        return out
    ckpt_a, why_a = resolve_ckpt(score_a, index)
    ckpt_b, why_b = resolve_ckpt(score_b, index)
    # R461.6 - a read published since the roster was captured carries the
    # per-row provenance it was decided on. It is a FALLBACK, not a source: the
    # instrument prefers a live checkpoint, so this only answers when the file
    # is gone - which is exactly the case that made old verdicts unauditable.
    captured = (d.get("veto") or {}).get("roster") or {}

    def _captured(arm: str) -> dict[str, str] | None:
        block = captured.get(arm) or {}
        if not block.get("captured"):
            return None
        return dict(block.get("reasons") or {})

    roster_a, roster_b = _captured("arm_a"), _captured("arm_b")
    if roster_a is not None and ckpt_a is None:
        why_a = f"{why_a}; re-read from the read's CAPTURED roster"
    if roster_b is not None and ckpt_b is None:
        why_b = f"{why_b}; re-read from the read's CAPTURED roster"
    out["provenance"] = {"arm_a": why_a, "arm_b": why_b}

    res_all = compare(
        score_a, score_b, veto_scope="all",
        a_ckpt=ckpt_a, b_ckpt=ckpt_b, a_roster=roster_a, b_roster=roster_b,
    )
    res_lever = compare(
        score_a, score_b, veto_scope="lever",
        a_ckpt=ckpt_a, b_ckpt=ckpt_b, a_roster=roster_a, b_roster=roster_b,
    )
    reaudit: dict[str, Any] = {"all": _verdict(res_all), "lever": _verdict(res_lever)}

    redraw, why_redraw = find_redraw(
        score_a, ckpt_a, index,
        declared=declared_redraws.get(_read_key(read_path)),
    )
    reaudit["redraw"] = why_redraw
    if redraw is not None:
        res_stable = compare(
            score_a, score_b, veto_scope="lever",
            a_ckpt=ckpt_a, b_ckpt=ckpt_b, a_redraw=redraw,
        )
        reaudit["draw_stable"] = _verdict(res_stable)
    out["reaudit"] = reaudit

    all_v = reaudit["all"]
    lever_v = reaudit["lever"]
    # A downgrade on EITHER read means the fixed scope could not be computed for
    # this pair, so its refusal cannot be audited - and saying "survives the fix"
    # there would be the same class of mistake this audit exists to find. (The
    # legacy "all" request never downgrades; the LEVER request does, and one
    # downgraded read is enough.)
    if lever_v["scope_downgraded"] or all_v["scope_downgraded"]:
        out["classification"] = "unverifiable"
        out["why"] = lever_v["downgrade_reason"] or all_v["downgrade_reason"]
        return out
    published_clean = out["published"]["veto"] == "CLEAN"
    if published_clean and all_v["fires"] and not lever_v["fires"]:
        # The read itself was already published under the fixed scope (R461.x):
        # the legacy line is recorded, and there is no refusal left to overturn.
        out["classification"] = "clean_read_already_scoped"
        out["why"] = (
            "published under the fixed scope; rule #8 fires only under the legacy "
            "all-rows definition, on rows the lever never served"
        )
        return out
    out["classification"] = "verdict_reproduced"
    if all_v["fires"] and not lever_v["fires"]:
        out["classification"] = "scope_decided_refusal"
        moved = lever_v["out_of_scope_rows"] or lever_v["undecided_rows"]
        out["why"] = (
            f"rule #8 fires under the legacy all-rows definition and is CLEAN on the "
            f"rows the lever served; {len(moved)} deciding row(s) moved out of scope"
        )
    elif all_v["fires"] and lever_v["fires"]:
        out["classification"] = "refusal_survives_the_fix"
        out["why"] = "rule #8 fires on rows arm B's own provenance says the lever served"
    elif not all_v["fires"]:
        out["classification"] = "no_rule8_refusal"
        out["why"] = "rule #8 does not fire under either definition"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(MEAS / "r461" / "gate-verdict-audit.json"))
    ap.add_argument(
        "--declared-redraw",
        action="append",
        default=None,
        help=(
            "READ=SCORE: declare the arm that is an independent draw of READ's arm A "
            "(repeatable). A re-draw is a claim about one configuration; the audit can "
            "only refute it on the request-shape digest, never infer it"
        ),
    )
    args = ap.parse_args()

    declared: dict[str, str] = {}
    for spec in args.declared_redraw or []:
        if "=" not in spec:
            raise SystemExit(f"--declared-redraw expects READ=SCORE, got {spec!r}")
        read_name, score_name = spec.split("=", 1)
        declared[read_name.strip()] = score_name.strip()

    index = _index()
    reads = sorted(
        p for p in glob.glob(str(MEAS / "**" / "*.json"), recursive=True)
        if _is_canonical_read(Path(p))
    )
    audited = [audit_read(Path(p), index, declared) for p in reads]

    print(f"published paired reads discovered: {len(audited)}")
    by_class: dict[str, int] = {}
    for row in audited:
        by_class[row["classification"]] = by_class.get(row["classification"], 0) + 1
    for cls, n in sorted(by_class.items(), key=lambda kv: -kv[1]):
        print(f"  {cls:<28}{n}")
    print()
    for row in audited:
        pub = row["published"]
        re_ = row.get("reaudit") or {}
        print(f"--- {row['read']}")
        print(
            f"    published: veto={pub['veto']} scope={pub['scope']} "
            f"veto_block={pub['veto_block']} gold={pub['gold_dropped_head']}"
        )
        if re_:
            for key in ("all", "lever", "draw_stable"):
                v = re_.get(key)
                if v:
                    print(
                        f"    re-read {key:<11} {v['verdict']:<10} scope={v['scope']:<6} "
                        f"eligible={v['eligible_rows']}/{v['rows_considered']} "
                        f"deciding={[d['id'] for d in v['deciding_rows']]}"
                    )
            if re_.get("redraw"):
                print(f"    re-draw: {re_['redraw']}")
        print(f"    => {row['classification']}: {row['why']}")

    payload = {
        "rule": (
            "every published paired read re-read through the fixed instrument: "
            "rule #8's scope (the rows the lever served) and its draw-stability"
        ),
        "reads": audited,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


def _is_canonical_read(path: Path) -> bool:
    try:
        d = _load(path)
    except Exception:  # noqa: BLE001 - any unparseable file is simply not a read
        return False
    return (
        isinstance(d, dict)
        and isinstance(d.get("arm_a"), str)
        and isinstance(d.get("arm_b"), str)
        and isinstance(d.get("axes"), dict)
    )


if __name__ == "__main__":
    raise SystemExit(main())

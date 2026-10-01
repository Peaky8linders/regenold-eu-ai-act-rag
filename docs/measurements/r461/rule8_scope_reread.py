"""R461 — hard rule #8 re-read from the checkpoints under the fixed definition.

The gate that refused the count-only block refused it on rule #8, and rule #8
fired on ONE row (`rg_037`) whose own provenance says arm B shipped the
deterministic Stage-1 draft: both Stage-2 legs failed, the count-only block was
never in the answer the judge scored, and the row's 7 refs / 1,474 chars against
a stated budget of 2 are that fact, not a lever effect.

`evals/official/paired_ab.py` now reads the veto on the rows the lever actually
served — the arm-under-test's provenance names `primary`/`fallback` — and
reports every excluded row and every drop on one, with `--veto-scope all`
preserving the pre-R461 definition. This script re-reads the round's pairs under
both definitions and writes the before/after record:

    python -m docs.measurements.r461.rule8_scope_reread

Three invariants are asserted rather than eyeballed, because the scope change is
supposed to move the VETO and nothing else:

1. the axes, the all-rows `gold_dropped_head` counts and the answer-length means
   are IDENTICAL under both scopes on every pair;
2. every drop the lever scope excludes is still named in the record, with the
   reason, and the drop on a row nobody can read would read UNDECIDED, never
   CLEAN;
3. the noise-floor pair — two draws of an UNCHANGED arm on byte-identical
   prompts — still vetoes under the new definition, so the round's
   draw-instability finding survives the fix instead of being fixed away.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCORES = REPO / "docs" / "measurements" / "r388"
OUT_JSON = REPO / "docs" / "measurements" / "r461" / "rule8-scope-reread.json"
OUT_MD = REPO / "docs" / "measurements" / "r461" / "RULE8-SCOPE-REREAD.md"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

PAIRS = [
    ("THE GATE", "r461-countoff-s3", "r461-counton-s3"),
    ("NOISE FLOOR  (byte-identical prompts)", "r460-tunnel-off-s3", "r461-countoff-s3"),
    ("R460 FULL BLOCK  (recomputed)", "r460-tunnel-off-s3", "r460-tunnel-on-s3"),
]


def _score(label: str) -> Path:
    return SCORES / f"score-{label}-hard.json"


def _arm_census() -> list[dict]:
    """Every scored arm whose checkpoint is on disk: what the scope can read."""
    from evals.official.paired_ab import (
        _provenance_roster,
        _reason_of,
        _row_scope_reason,
    )

    rows = []
    seen: set[str] = set()
    for path in sorted(SCORES.glob("score-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        label = str(payload.get("label") or "")
        if not label or label in seen:
            continue
        seen.add(label)
        roster, source = _provenance_roster(path, None)
        if roster is None:
            continue
        ids = sorted(roster)
        census: dict[str, int] = {}
        for qid in ids:
            reason = _reason_of(roster, qid)
            census[reason] = census.get(reason, 0) + 1
        rows.append(
            {
                "label": label,
                "score": path.name,
                "ckpt": source,
                "rows": len(ids),
                "census": census,
                "eligible": sum(
                    n for reason, n in census.items()
                    if reason in ("primary", "fallback")
                ),
            }
        )
    # Guard the import is the same vocabulary the report prints.
    assert _row_scope_reason({"stage2_served_by": "primary"}) == "primary"
    return rows


def _pair_record(title: str, a_label: str, b_label: str) -> dict:
    from evals.official.paired_ab import compare

    a, b = _score(a_label), _score(b_label)
    for path in (a, b):
        if not path.exists():
            raise SystemExit(f"missing score payload: {path}")
    lever = compare(a, b)
    legacy = compare(a, b, veto_scope="all")

    # Invariant 1 — the scope moves the veto and nothing else.
    for key in ("axes", "gold_dropped_head", "mean_answer_chars", "shared_rows"):
        if json.dumps(lever[key], sort_keys=True) != json.dumps(legacy[key], sort_keys=True):
            raise SystemExit(
                f"{title}: scope changed '{key}' — the fix must move only the veto"
            )

    v_lever, v_legacy = lever["veto"], legacy["veto"]
    # Invariant 2 — nothing leaves the record.
    dropped = set(lever["gold_dropped_head"]["new_drops_in_b"])
    named = {
        d["id"]
        for d in (
            v_lever["drops_in_scope"]
            + v_lever["drops_out_of_scope"]
            + v_lever["drops_undecided"]
        )
    }
    if dropped != named:
        raise SystemExit(f"{title}: drops vanished from the record: {dropped ^ named}")

    return {
        "title": title,
        "arm_a": a_label,
        "arm_b": b_label,
        "shared_rows": lever["shared_rows"],
        "gold_dropped_head": lever["gold_dropped_head"],
        "mean_answer_chars": lever["mean_answer_chars"],
        "verdict_all": v_legacy["verdict"],
        "verdict_lever": v_lever["verdict"],
        "veto_all": v_legacy,
        "veto_lever": v_lever,
        "excluded": v_lever["excluded"],
        "ref_conciseness": {
            "delta": lever["axes"]["ref_conciseness"]["delta"],
            "ci95": lever["axes"]["ref_conciseness"]["ci95"],
        },
    }


def _fmt_reasons(census: dict[str, int]) -> str:
    if not census:
        return "none"
    return " / ".join(f"{n} {r}" for r, n in sorted(census.items(), key=lambda kv: -kv[1]))


def main() -> int:
    records = [_pair_record(*pair) for pair in PAIRS]

    # Invariant 3 — the noise floor still vetoes.
    noise = next(r for r in records if r["title"].startswith("NOISE"))
    if noise["verdict_lever"] != "VETO":
        raise SystemExit("the noise-floor pair stopped vetoing: the fix erased a found result")

    OUT_JSON.write_text(json.dumps(records, indent=1), encoding="utf-8")

    lines: list[str] = []
    w = lines.append
    w("# R461 — hard rule #8 re-read from the checkpoints")
    w("")
    w("Rule #8's operating definition is now the rows where the lever's payload")
    w("actually served the arm under test (`stage2_served_by` in `primary`/")
    w("`fallback`; the pre-`stage2_served_by` hint is `stage2_polish is True`).")
    w("`--veto-scope all` reproduces the definition in use before this round, so")
    w("every verdict below is shown twice. Generated by `rule8_scope_reread.py`;")
    w("raw payloads in `rule8-scope-reread.json`.")
    w("")
    w("## 1. Before and after, per pair")
    w("")
    w("| pair | n | verdict, scope=all | verdict, scope=lever | drop in scope | dropped, out of scope | dropped, undecided |")
    w("| :-- | --: | :-- | :-- | :-- | :-- | :-- |")
    for r in records:
        lv, av = r["veto_lever"], r["veto_all"]
        in_scope = ", ".join(d["id"] for d in lv["drops_in_scope"]) or "—"
        out = ", ".join(f"{d['id']} ({d['arm_b']})" for d in lv["drops_out_of_scope"]) or "—"
        und = ", ".join(f"{d['id']} ({d['arm_b']})" for d in lv["drops_undecided"]) or "—"
        w(f"| {r['title']} | {r['shared_rows']} | **{av['verdict']}** | **{lv['verdict']}** | {in_scope} | {out} | {und} |")
    w("")
    w("The scope reads a veto on fewer rows and never on a different set: every")
    w("drop the lever scope excludes is reported in the same row, with the")
    w("provenance that excludes it, and the all-rows `gold_dropped_head` block is")
    w("byte-identical under both reads (asserted, per pair, on the axes, the")
    w("all-rows drop counts and the answer-length means).")
    w("")
    w("## 2. What the scope excluded, row by row")
    w("")
    w("Only rows carrying a gold key can drop one, so a row with no annotated")
    w("reference is not in the scope at all and is not listed here; that is why")
    w("nine unpolished rows in the arm census of §5 can read as seven")
    w("exclusions below.")
    w("")
    for r in records:
        lv = r["veto_lever"]
        w(f"### {r['title']}  (arm A = `{r['arm_a']}`, arm B = `{r['arm_b']}`)")
        w("")
        w(f"- evaluated rows: {lv['eligible_rows']} of {lv['rows_considered']} gold rows")
        w(f"- provenance A: {_fmt_reasons(lv['by_reason_a'])}")
        w(f"- provenance B: {_fmt_reasons(lv['by_reason_b'])}")
        excl = lv["excluded"]
        if excl:
            w("- excluded:")
            for e in excl:
                w(f"  - `{e['id']}`  A={e['arm_a']} B={e['arm_b']} — {lv['reasons'].get(e['arm_b'], e['arm_b'])}")
        else:
            w("- excluded: none")
        w("")
    w("## 3. The reading this changes")
    w("")
    gate = next(r for r in records if r["title"] == "THE GATE")
    lv = gate["veto_lever"]
    w("- **The gate.** Under the pre-R461 definition the count-only arm is")
    w(f"  {gate['verdict_all']} on `rg_037`; under the lever definition it is")
    w(f"  **{lv['verdict']}**, because that row never ran the block:")
    w("  arm B shipped the deterministic Stage-1 draft, and the row's 7 refs /")
    w("  1,474 chars against a stated budget of 2 are what a failed Stage-2 leg")
    w("  looks like. On the " + str(lv["eligible_rows"]) + " rows the block actually")
    w("  served, the count-only arm drops no gold head at all.")
    r460 = next(r for r in records if r["title"].startswith("R460"))
    if r460["veto_all"]["fires"] and not r460["veto_lever"]["fires"]:
        out = ", ".join(
            f"`{d['id']}` (B={d['arm_b']})" for d in r460["veto_lever"]["drops_out_of_scope"]
        )
        w("- **R460's own veto, re-read.** The full block's rule-#8 refusal rested")
        w(f"  on the same row id, {out}: the truncation guard kept the previous")
        w("  turn's answer, so the block never served that row. That refusal now")
        w(f"  reads **{r460['verdict_lever']}** — which does NOT promote the full")
        w("  block: R460 failed its other targets (ans_conciseness -4.49 pp,")
        w("  answers +64 chars) and every one of those is untouched by this change.")
        w("  What the re-read corrects is the reason given for the refusal, which")
        w("  is the part of the record the next reader would otherwise trust.")
    w("")
    w("## 4. What the fix must NOT do, and does not")
    w("")
    w(f"- **The noise floor still vetoes.** {noise['title']}: two draws of an")
    w(f"  UNCHANGED arm on byte-identical prompts — {', '.join('`' + d['id'] + '`' for d in noise['veto_lever']['drops_in_scope'])}")
    w("  — both `primary`/`primary`, so the scope keeps them in and the verdict")
    w("  stays **VETO**. A single-draw gate still cannot decide rule #8 at")
    w("  n=37; that finding is unchanged and unaffected by where the veto is read.")
    w("- **The measured deltas are untouched.** `ref_conciseness` on the gate pair")
    w(f"  reads {gate['ref_conciseness']['delta']:+.2f} "
      f"[{gate['ref_conciseness']['ci95'][0]:+.2f}, {gate['ref_conciseness']['ci95'][1]:+.2f}]")
    w("  under both scopes, and so does every other axis (asserted).")
    w("- **Unreadable provenance does not lift a veto.** With no checkpoint to")
    w("  read, the scope falls back to `all` and says so; a row whose provenance")
    w("  is missing or names nothing is reported UNDECIDED, which is not CLEAN.")
    w("")
    w("## 5. Every arm on disk, and how much of it the scope can read")
    w("")
    w("| arm | rows | eligible (primary/fallback) | deterministic | prior_turn | unpolished | unknown | no provenance |")
    w("| :-- | --: | --: | --: | --: | --: | --: | --: |")
    for a in _arm_census():
        c = a["census"]
        w(
            f"| `{a['label']}` | {a['rows']} | {a['eligible']} | {c.get('deterministic', 0)} | "
            f"{c.get('prior_turn', 0)} | {c.get('unpolished', 0)} | {c.get('unknown', 0)} | "
            f"{c.get('no_provenance', 0)} |"
        )
    w("")
    w("The unpolished column is the route's curated/intercepted rows: no Stage-2")
    w("call is made on them in EITHER arm by construction, so they are excluded")
    w("from both. They are ~19% of the board and they are why the veto's scope")
    w("and the round's same-leg attribution subsets agree.")
    w("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for r in records:
        lv = r["veto_lever"]
        print(
            f"{r['title']:<40} n={r['shared_rows']:<3} "
            f"all={r['verdict_all']:<9} lever={lv['verdict']:<9} "
            f"evaluated={lv['eligible_rows']}/{lv['rows_considered']}  "
            f"out_of_scope={[d['id'] for d in lv['drops_out_of_scope']]}  "
            f"undecided={[d['id'] for d in lv['drops_undecided']]}"
        )
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

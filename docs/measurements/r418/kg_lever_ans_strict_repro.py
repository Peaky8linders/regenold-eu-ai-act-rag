"""R419 — is the R416 KG point-text lever's Ans Strict delta carried by
reproducible credit?

THE CLAIM UNDER TEST
--------------------
The R416 easy board read ``ans_correctness_strict`` **88.0 -> 96.0 (+8.0 pp)**
on 25 paired rows, and named the mechanism as two rows: ``rg_010`` (4/5 -> 5/5)
and ``rg_045`` (3/4 -> 4/4). Both arms were tunnel-served and differ by exactly
one flag. The judged answers and all 50 verdicts are on disk, so this needs no
calls.

The question is not whether the judge liked the ON answers. It is whether the
*credit* that produces the flip is reproducible — a strict pass is earned only
when EVERY criterion is satisfied, so one criterion whose credit does not
survive resampling is enough to make a row's contribution to this axis noise.

TWO INDEPENDENT NOTIONS OF "NOT REPRODUCIBLE", BOTH MEASURED HERE
----------------------------------------------------------------
``J`` — JUDGE-REP INSTABILITY. The instrument itself repeats every judgement
three times (temperature 0.1) and reports the min-max spread. A row whose
per-repetition strict verdict is not unanimous is a row whose score depends on
which of the three draws you happen to get. Measured from ``_corr_runs``, which
the judge cache already stores per row (no re-judging).

``G`` — GENERATION INSTABILITY. A criterion can be judge-stable on a given pair
of answers and still not be attributable to the lever: if fresh samples of the
*baseline* arm also state it, the pair was one draw of a distribution rather
than a property of the flag. ``rg_010`` is already in this class by prior
measurement — ``aim_clause_probe.py`` (R416 §6.5a) found Art. 14's *aim* clause
on BOTH arms in fresh samples (KG=1 1,387 chars aim=True; KG=0 1,201 aim=True),
and production returned it in a 783-char wrapper-served sample. That evidence is
read from the checkpoint; this driver does not re-assert it, it consumes it.

Precisely: a row is dropped from the re-score when its strict credit is not
reproducible under EITHER rule. Each rule is also reported alone, so the
contribution of each is visible rather than blended.

WHAT THIS DRIVER DOES NOT DO
----------------------------
It does not re-derive any axis. ``score_rows`` (the same function the arms were
scored with via ``score_arm``) computes both correctness axes on the surviving
row set, so the re-score is the published instrument applied to a subset — not a
second implementation of it. It also does not touch the reference axes: the
lever's reference numbers are flat (``ref_loose`` 100.0 both arms) and the
reference axes never touch the judge.

    .venv/Scripts/python.exe -m docs.measurements.r418.kg_lever_ans_strict_repro
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from evals.official.rubric import AXIS_ORDER, overall, score_rows  # noqa: E402
from evals.official.score_arm import (  # noqa: E402
    _key,
    build_rows,
    load_cache,
    load_ckpt,
    load_gold,
)

R415 = REPO / "docs" / "measurements" / "r415"
OUT = REPO / "docs" / "measurements" / "r418"

#: The identity the verdicts were written under, read from the gate's own logs
#: (``score-arm-{a,b}.log``). Pinned rather than discovered so a future default
#: change cannot silently re-key this audit onto a different instrument.
JUDGE_ID = "wrapper:claude-sonnet-5:t=0.1:grouped:r=3"

ARMS: dict[str, tuple[str, str]] = {
    # arm -> (ckpt filename, ``REGENOLD_KG_POINT_TEXT`` value)
    "a": ("official-lever-a-paired-kgpt.ckpt.jsonl", "0"),
    "b": ("official-lever-b-matched-kgpt.ckpt.jsonl", "1"),
}

#: The live resample that measures rule ``G`` directly (fresh generations per arm,
#: judged with the arms' own instrument). Written by ``kgpt_credit_resample``.
RESAMPLE = OUT / "kgpt-credit-resample.json"

#: Fallback evidence for rows with no resample data on disk. A row is listed here
#: only with a measurement that already shows the generation-level
#: irreproducibility, and the reason is printed with the exclusion.
GENERATION_UNSTABLE_CITED: dict[str, dict[str, str]] = {
    "rg_010": {
        "criterion": "Aim: prevent/minimise risks to health, safety, fundamental rights",
        "evidence": "docs/measurements/r416/CHECKPOINT.md §6.5a (aim_clause_probe.py): "
        "fresh samples state the clause on BOTH arms (KG=0 1,201 chars aim=True), "
        "so the R415 pair's 4/5 vs 5/5 split is sampling, not the flag",
    },
}

#: Rule ``G``'s bar. The credited criterion must be credited materially more
#: often on the crediting arm than on the baseline arm; a rate difference that a
#: two-sided Fisher exact test cannot distinguish at 5 % is not a gain that a
#: 1-vs-1 gate pair can be reproducing.
GEN_ALPHA = 0.05


def _frac(text: str) -> tuple[int, int]:
    """``"k/n"`` -> ``(k, n)``; a malformed cell is ``(0, 0)``, never a silent 0."""
    try:
        k, n = str(text).split("/", 1)
        return int(k), int(n)
    except Exception:  # noqa: BLE001
        return 0, 0


def _fisher_p(kb: int, nb: int, ka: int, na: int) -> float:
    """Two-sided Fisher exact p for ``kb/nb`` vs ``ka/na`` (scipy, as the repo has it)."""
    try:
        from scipy.stats import fisher_exact  # noqa: PLC0415

        return float(fisher_exact([[kb, nb - kb], [ka, na - ka]])[1])
    except Exception:  # noqa: BLE001 — audit degrades to a conservative reading
        return 1.0


def _generation_rule(rid: str) -> tuple[bool, str]:
    """Is this row's credited criterion reproducible across fresh generations?

    Returns ``(reproducible, note)``. With resample data on disk the answer is the
    measurement; without it, the cited R416 evidence is used and the note says so.
    """
    if RESAMPLE.exists():
        data = json.loads(RESAMPLE.read_text(encoding="utf-8"))
        a, b = data.get(f"{rid}|KG=0"), data.get(f"{rid}|KG=1")
        if a and b:
            ka, na = _frac(a.get("focal_credit_majority", ""))
            kb, nb = _frac(b.get("focal_credit_majority", ""))
            if na and nb:
                p = _fisher_p(kb, nb, ka, na)
                ok = (kb / nb > ka / na) and p < GEN_ALPHA
                return ok, (
                    f"measured: KG=1 {kb}/{nb} vs KG=0 {ka}/{na} "
                    f"(Fisher two-sided p={p:.3f}, alpha={GEN_ALPHA}); "
                    f"atomic draws KG=1 {b.get('focal_credit_atomic_draws')} "
                    f"vs KG=0 {a.get('focal_credit_atomic_draws')}"
                )
    cited = GENERATION_UNSTABLE_CITED.get(rid)
    if cited:
        return False, f"cited (no resample data): {cited['evidence']}"
    return True, "no resample data and no cited evidence — assumed reproducible"


def _load_arm(name: str, gold: dict[str, dict], cache: dict[str, dict]) -> dict[str, dict]:
    ckpt = R415 / ARMS[name][0]
    rows = build_rows(load_ckpt(ckpt), gold)
    out: dict[str, dict] = {}
    for r in rows:
        v = cache.get(_key(r["id"], r["answer"], JUDGE_ID))
        if not v:
            raise SystemExit(f"{ckpt.name}: no cached verdict for {r['id']} under {JUDGE_ID}")
        out[r["id"]] = {**r, **{k: v[k] for k in v if k != "_basis_sha"}, "arm": name}
    return out


def _strict(criteria: list[Any]) -> bool:
    return bool(criteria) and all(bool(c) for c in criteria)


def _rep_strict(runs: list[Any]) -> list[bool | None]:
    return [None if not r else _strict(list(r)) for r in runs]


def _unanimous(xs: list[bool | None]) -> bool:
    live = [x for x in xs if x is not None]
    return len(set(live)) <= 1


def _axes(rows: list[dict]) -> dict[str, float]:
    axes = score_rows(rows)
    return {
        "n": axes["n"],
        "ans_correctness_loose": axes["ans_correctness_loose"],
        "ans_correctness_strict": axes["ans_correctness_strict"],
    }


def _delta(a: list[dict], b: list[dict]) -> dict[str, Any]:
    aa, ba = _axes(a), _axes(b)
    return {
        "n": len(a),
        "arm_a": aa,
        "arm_b": ba,
        "delta_pp": {
            k: round(ba[k] - aa[k], 2)
            for k in ("ans_correctness_loose", "ans_correctness_strict")
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="kg-lever-ans-strict-repro.json")
    a = ap.parse_args()

    gold = load_gold()
    cache = load_cache(R415 / "judge-cache-r415-wrapper.jsonl")
    arms = {n: _load_arm(n, gold, cache) for n in ARMS}

    if set(arms["a"]) != set(arms["b"]):
        raise SystemExit("the arms are not paired — refusing to re-score")
    ids = list(arms["a"])

    # ── the per-row credit picture ──────────────────────────────────────────
    per_row: list[dict] = []
    for rid in ids:
        ra, rb = arms["a"][rid], arms["b"][rid]
        sra, srb = _rep_strict(ra["_corr_runs"]), _rep_strict(rb["_corr_runs"])
        ca, cb = ra["criteria"], rb["criteria"]
        flips_a = [i for i in range(len(ca)) if len({bool(r[i]) for r in ra["_corr_runs"] if r}) > 1]
        flips_b = [i for i in range(len(cb)) if len({bool(r[i]) for r in rb["_corr_runs"] if r}) > 1]
        per_row.append(
            {
                "id": rid,
                "strict_a": _strict(ca),
                "strict_b": _strict(cb),
                "rep_strict_a": sra,
                "rep_strict_b": srb,
                "judge_unanimous_a": _unanimous(sra),
                "judge_unanimous_b": _unanimous(srb),
                "criteria_a": ca,
                "criteria_b": cb,
                "unstable_criteria_a": flips_a,
                "unstable_criteria_b": flips_b,
                "n_criteria": len(ca),
            }
        )

    strict_movers = [r for r in per_row if r["strict_a"] != r["strict_b"]]
    judge_unstable = [
        r for r in strict_movers if not (r["judge_unanimous_a"] and r["judge_unanimous_b"])
    ]
    gen_rule = {r["id"]: _generation_rule(r["id"]) for r in strict_movers}
    gen_unstable = [r for r in strict_movers if not gen_rule[r["id"]][0]]

    def _rows(ids_keep: list[str], arm: str) -> list[dict]:
        return [arms[arm][i] for i in ids_keep]

    keep_all = list(ids)
    keep_j = [i for i in ids if i not in {r["id"] for r in judge_unstable}]
    keep_g = [i for i in ids if i not in {r["id"] for r in gen_unstable}]
    keep_both = [i for i in ids if i not in {r["id"] for r in (judge_unstable + gen_unstable)}]

    variants = {
        "published_all_rows": _delta(_rows(keep_all, "a"), _rows(keep_all, "b")),
        "excl_judge_unstable": _delta(_rows(keep_j, "a"), _rows(keep_j, "b")),
        "excl_generation_unstable": _delta(_rows(keep_g, "a"), _rows(keep_g, "b")),
        "excl_both": _delta(_rows(keep_both, "a"), _rows(keep_both, "b")),
    }

    # ── what the BOARD reads once the corrected axes are used ───────────────
    # The published paired reading is on disk per axis; the correctness axes are
    # the only ones that can move here, and the reference / tone / speed axes are
    # untouched by this audit (they never touch the judge for the ref axes, and
    # the re-score changes no latency). So the corrected board is the published
    # one with its two correctness axes replaced.
    corrected_board: dict[str, Any] = {}
    paired_path = R415 / "official-lever-paired-kgpt.json"
    if paired_path.exists():
        published = json.loads(paired_path.read_text(encoding="utf-8"))
        fixed = variants["excl_both"]
        for arm_key, arm_name in (("arm_a", "0"), ("arm_b", "1")):
            axes = dict(published[arm_key])
            vals = {
                "ans_correctness_loose": fixed["arm_a" if arm_key == "arm_a" else "arm_b"][
                    "ans_correctness_loose"
                ],
                "ans_correctness_strict": fixed["arm_a" if arm_key == "arm_a" else "arm_b"][
                    "ans_correctness_strict"
                ],
            }
            for k, v in vals.items():
                axes[k] = v
            axes["overall"] = round(overall([axes[k] / 100.0 for k in AXIS_ORDER]) * 100.0, 4)
            corrected_board[arm_name] = axes
        deltas = {
            k: round(corrected_board["1"][k] - corrected_board["0"][k], 2)
            for k in (*AXIS_ORDER, "overall")
        }
        corrected_board["delta_pp"] = deltas
        corrected_board["published_overall"] = {
            "0": published["arm_a"]["overall"],
            "1": published["arm_b"]["overall"],
            "delta_pp": published["delta_pp"]["overall"],
        }

    # ── is the conciseness COST reproducible? ──────────────────────────────
    # The docstring's second claim is the -3.3 pp it pays in ans_conciseness,
    # which is answer LENGTH. The easy board has one draw per row per arm, so the
    # only test available is a paired one across the 25 rows: if the ON arm were
    # systematically longer, it would be longer on most rows, not on a few large
    # ones. (The resample measures the within-row spread at fixed input, which is
    # what makes a mean-only reading unsafe: one row returned 450-1,492 chars.)
    conciseness: dict[str, Any] = {}
    paired_path_existed = paired_path.exists()
    if paired_path_existed:
        published = json.loads(paired_path.read_text(encoding="utf-8"))
        diffs: list[int] = []
        for rid in ids:
            diffs.append(len(arms["b"][rid]["answer"]) - len(arms["a"][rid]["answer"]))
        longer = sum(1 for x in diffs if x > 0)
        shorter = sum(1 for x in diffs if x < 0)
        try:
            from scipy.stats import binomtest, wilcoxon  # noqa: PLC0415

            sign_p = round(float(binomtest(longer, longer + shorter, 0.5).pvalue), 4) if longer + shorter else None
            try:
                wilcoxon_p = round(float(wilcoxon(diffs).pvalue), 4)
            except Exception:  # noqa: BLE001 — all-zero diffs
                wilcoxon_p = None
        except Exception:  # noqa: BLE001
            sign_p = wilcoxon_p = None
        conciseness = {
            "published_delta_pp": published["delta_pp"]["ans_conciseness"],
            "mean_chars_a": round(sum(len(arms["a"][r]["answer"]) for r in ids) / len(ids), 1),
            "mean_chars_b": round(sum(len(arms["b"][r]["answer"]) for r in ids) / len(ids), 1),
            "rows_longer_on": longer,
            "rows_shorter_on": shorter,
            "sign_test_p": sign_p,
            "wilcoxon_p": wilcoxon_p,
            "call": (
                "cost NOT supported: the ON arm is not systematically longer"
                if (sign_p is not None and sign_p > 0.05)
                else "cost supported by the paired test"
            ),
        }

    # ── the instrument's own min-max bounds on the delta ────────────────────
    reps = min(
        len(arms["a"][i]["_corr_runs"]) for i in ids
    ) if all(arms["a"][i].get("_corr_runs") for i in ids) else 0
    rep_bounds: dict[str, Any] = {}
    if reps > 1:
        deltas: list[float] = []
        for run_idx in range(reps):
            def _at(arm: str, k: int) -> list[dict]:
                out = []
                for i in ids:
                    r = dict(arms[arm][i])
                    runs = r.get("_corr_runs") or []
                    if len(runs) > k and runs[k] is not None:
                        r["criteria"] = list(runs[k])
                    out.append(r)
                return out

            da = _axes(_at("a", run_idx))["ans_correctness_strict"]
            db = _axes(_at("b", run_idx))["ans_correctness_strict"]
            deltas.append(round(db - da, 2))
        rep_bounds = {
            "repetitions": reps,
            "delta_per_rep_pp": deltas,
            "delta_min_pp": min(deltas),
            "delta_max_pp": max(deltas),
        }

    res = {
        "lever": "REGENOLD_KG_POINT_TEXT (a=0 vs b=1)",
        "instrument": JUDGE_ID,
        "source": {
            "arm_a": (R415 / ARMS["a"][0]).name,
            "arm_b": (R415 / ARMS["b"][0]).name,
            "verdicts": "docs/measurements/r415/judge-cache-r415-wrapper.jsonl",
        },
        "n_rows": len(ids),
        "strict_movers": [
            {
                "id": r["id"],
                "arm_a": f"{sum(1 for c in r['criteria_a'] if c)}/{r['n_criteria']}",
                "arm_b": f"{sum(1 for c in r['criteria_b'] if c)}/{r['n_criteria']}",
                "rep_strict_a": r["rep_strict_a"],
                "rep_strict_b": r["rep_strict_b"],
                "unstable_criteria_a": r["unstable_criteria_a"],
                "unstable_criteria_b": r["unstable_criteria_b"],
            }
            for r in strict_movers
        ],
        "excluded_judge_unstable": [r["id"] for r in judge_unstable],
        "excluded_generation_unstable": [r["id"] for r in gen_unstable],
        "generation_rule": {rid: gen_rule[rid][1] for rid in gen_rule},
        "generation_rule_bar": f"arm-B credit rate higher AND Fisher two-sided p < {GEN_ALPHA}",
        "resample_artifact": RESAMPLE.name if RESAMPLE.exists() else None,
        "variants": variants,
        "rep_level_bounds": rep_bounds,
        "corrected_board": corrected_board,
        "conciseness_cost": conciseness,
    }

    dest = OUT / a.out
    dest.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print("=" * 88)
    print("R416 KG POINT-TEXT LEVER — ANS STRICT, RE-SCORED FOR CREDIT REPRODUCIBILITY")
    print("=" * 88)
    print(f"instrument: {JUDGE_ID}")
    print(f"paired rows: {len(ids)}   strict movers: {len(strict_movers)}")
    print()
    print(f"{'variant':<30}{'n':>5}{'A strict':>11}{'B strict':>11}{'delta':>10}")
    print("-" * 88)
    for name, v in variants.items():
        print(
            f"{name:<30}{v['n']:>5}"
            f"{v['arm_a']['ans_correctness_strict']:>11.2f}"
            f"{v['arm_b']['ans_correctness_strict']:>11.2f}"
            f"{v['delta_pp']['ans_correctness_strict']:>+10.2f}"
        )
    print("-" * 88)
    if rep_bounds:
        print(
            f"instrument min-max bound on the delta (r={rep_bounds['repetitions']}): "
            f"{rep_bounds['delta_min_pp']:+.2f} .. {rep_bounds['delta_max_pp']:+.2f} pp "
            f"(per-rep {rep_bounds['delta_per_rep_pp']})"
        )
    print()
    print("strict movers, with each criterion's credit across the judge's own repetitions:")
    for r in strict_movers:
        print(f"  {r['id']}  A {sum(1 for c in r['criteria_a'] if c)}/{r['n_criteria']} "
              f"repsA {''.join('T' if x else 'F' for x in r['rep_strict_a'])}   "
              f"B {sum(1 for c in r['criteria_b'] if c)}/{r['n_criteria']} "
              f"repsB {''.join('T' if x else 'F' for x in r['rep_strict_b'])}   "
              f"unstable criteria A{r['unstable_criteria_a']} B{r['unstable_criteria_b']}")
    print()
    print(f"excluded (judge-rep unstable):      {[r['id'] for r in judge_unstable] or '—'}")
    print(f"excluded (generation rep unstable): {[r['id'] for r in gen_unstable] or '—'}")
    print(f"rule G bar: {GEN_ALPHA} (two-sided Fisher; resample={'on disk' if RESAMPLE.exists() else 'absent'})")
    for rid, (ok, note) in gen_rule.items():
        print(f"  G[{rid}] {'reproducible' if ok else 'NOT reproducible'} — {note}")
    if corrected_board:
        print()
        print("board with the corrected correctness axes (all other axes unchanged):")
        print(f"{'axis':<26}{'OFF':>10}{'ON':>10}{'delta':>10}")
        for k in (*AXIS_ORDER, "overall"):
            flag = "" if k != "overall" else "  <-- was +0.6"
            print(
                f"{k:<26}{corrected_board['0'][k]:>10.2f}{corrected_board['1'][k]:>10.2f}"
                f"{corrected_board['delta_pp'][k]:>+10.2f}{flag}"
            )

    if conciseness:
        print()
        print("the other half of the board — is the conciseness COST reproducible?")
        print(
            f"  ans_conciseness {conciseness['published_delta_pp']:+.2f} pp "
            f"(mean chars {conciseness['mean_chars_a']} -> {conciseness['mean_chars_b']}); "
            f"ON longer on {conciseness['rows_longer_on']}/{len(ids)} rows, "
            f"sign-test p={conciseness['sign_test_p']}, wilcoxon p={conciseness['wilcoxon_p']}"
        )
        print(f"  -> {conciseness['call']}")

    print(f"\nwrote {dest.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

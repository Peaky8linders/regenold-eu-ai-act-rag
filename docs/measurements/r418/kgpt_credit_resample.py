"""R419 — does the criterion that flips Ans Strict survive fresh generations?

WHY THIS EXISTS
---------------
``docs/measurements/r418/kg_lever_ans_strict_repro.py`` shows the R416 KG
point-text lever's **+8.0 pp** ``ans_correctness_strict`` delta is carried by
exactly two rows, and that each of them fails a different reproducibility test
on the data already on disk:

* ``rg_045`` (3/4 -> 4/4) — the judge credited criterion 3 in only **2 of its 3**
  repetitions, so the row's strict verdict is draw-dependent (the arm's own
  published min-max bound on that axis, 92.0-96.0, is this one row).
* ``rg_010`` (4/5 -> 5/5) — judge-stable on those two answers, but R416 §6.5a
  already showed the *baseline* arm states the clause in fresh samples, so the
  pair was one draw of a distribution rather than a property of the flag.

Inferring "not reproducible" from an adjacent measurement is exactly the kind of
claim this repository has been burned by. So this module measures it directly:
N independent generations per arm per row, judged with the SAME instrument the
arms were judged with (wrapper ``claude-sonnet-5``, grouped, r=3), and reports
how often the focal criterion is credited.

INDEPENDENCE, AND WHY THE CACHE IS CLEARED
------------------------------------------
The route's ``_ENGINE_CACHE`` is process-local and keyed on the question text, so
a naively repeated ask replays one generation (R416 §6.5a: identical asks
returned in 0.1-0.2 s while a novel ask took 38.4 s). ``clear()`` is called
before every sample and the cache is asserted empty, so every recorded answer is
a live generation of the identical question text — no variant spelling, which
would change the input being tested.

THE SAME FALLBACK DOCTRINE AS THE GATES
---------------------------------------
A sample served by the Bedrock fallback leg is structurally incomparable (that
leg always receives the full system prompt), so it is recorded and EXCLUDED from
the credit rate rather than silently averaged in. The served leg is read from the
R418 ``stage2_served_by=`` trace note, falling back to the model prefix.

    .venv/Scripts/python.exe -m docs.measurements.r418.kgpt_credit_resample --samples 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r418"
SAMPLES_PATH = OUT / "kgpt-credit-resample.jsonl"
SCORES = REPO / "docs" / "measurements" / "r388"

URL_LOCAL = "local://app.main:app/api/v1/regenold/eu-ai-act/ask?include_reasoning=true"

#: row id -> the criterion index whose credit flips the row's strict verdict.
#: Validated against the published arm verdicts at startup, so a stale index is a
#: hard error rather than a silently wrong focal point.
FOCAL: dict[str, int] = {"rg_010": 2, "rg_045": 3}

ARMS: tuple[str, ...] = ("0", "1")

#: Printed with the artifact so the two credit columns cannot be misread.
LIBERAL_NOTE = (
    "focal credit is the criterion whose credit flips the row's strict verdict; "
    "atomic draws are the judge's own repetitions"
)

JUDGE_PROVIDER = "wrapper"
JUDGE_MODEL = "claude-sonnet-5"
JUDGE_REPEATS = 3


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _write(records: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SAMPLES_PATH.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )


def _gold() -> dict[str, dict]:
    from evals.official.score_arm import load_gold  # noqa: PLC0415

    return load_gold()


def validate_focal(gold: dict[str, dict]) -> None:
    """The focal index must be the criterion the two published arms disagree on.

    Read from the arm scorecards themselves (not from this module's own table), so
    the audit cannot drift onto a different criterion than the one it explains.
    """
    bad: list[str] = []
    for rid, idx in FOCAL.items():
        got = []
        for arm in ("a", "b"):
            p = SCORES / f"score-r415-official-lever-{arm}-matched-kgpt-easy.json"
            rows = {r["id"]: r for r in json.loads(p.read_text(encoding="utf-8"))["rows"]}
            r = rows.get(rid)
            if r is None:
                raise SystemExit(f"{rid} missing from {p.name}")
            got.append(bool(r["criteria"][idx]))
        if got != [False, True]:
            bad.append(f"{rid}: criterion {idx} is A={got[0]} B={got[1]} (expected A=False B=True)")
    if bad:
        raise SystemExit("focal criterion does not match the published arms:\n  " + "\n  ".join(bad))


def generate(records: list[dict], gold: dict[str, dict], samples: int, timeout: float) -> None:
    from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415
    from evals.regenold.run_official_batch import _provenance  # noqa: PLC0415
    from evals.regenold.runner_v2 import _post_local  # noqa: PLC0415

    done = {(r["row"], r["arm"], r["sample"]) for r in records}
    for rid in FOCAL:
        question = gold[rid]["question"]
        for arm in ARMS:
            os.environ["REGENOLD_KG_POINT_TEXT"] = arm
            for s in range(samples):
                if (rid, arm, s) in done:
                    continue
                _ENGINE_CACHE.clear()
                t0 = time.perf_counter()
                body, _lat, status, err, _att, _ret = _post_local(
                    URL_LOCAL, None, [{"role": "user", "content": question}], timeout
                )
                dt = time.perf_counter() - t0
                body = body or {}
                answer = str(body.get("answer") or "")
                prov = _provenance(body)
                served = str(prov.get("stage2_served_by") or "")
                model = str(prov.get("stage2_model") or "")
                if not served:
                    served = (
                        "primary"
                        if model.lower().startswith("claude")
                        else (f"fallback:{model}" if model else "unrecorded")
                    )
                records.append(
                    {
                        "row": rid,
                        "question": question,
                        "arm": arm,
                        "sample": s,
                        "answer": answer,
                        "refs": list(body.get("references") or []),
                        "latency_s": round(dt, 2),
                        "status": status,
                        "error": err,
                        "stage2_served_by": served,
                        "stage2_model": model,
                    }
                )
                _write(records)
                print(
                    f"  gen {rid} KG={arm} #{s}: {len(answer):>5} chars "
                    f"{dt:5.1f}s leg={served} model={model or '—'}",
                    flush=True,
                )


def judge(records: list[dict], gold: dict[str, dict]) -> None:
    from evals.official import judge as official_judge  # noqa: PLC0415

    official_judge.configure_judge(
        provider=JUDGE_PROVIDER, model=JUDGE_MODEL, grouped=True
    )
    identity = official_judge.judge_identity()
    print(f"  judge identity: {identity}", flush=True)
    for rec in records:
        if rec.get("verdict"):
            continue
        g = gold[rec["row"]]
        row = {
            "id": rec["row"],
            "question": rec["question"],
            "answer": rec["answer"],
            "criteria": list(g["criteria"]),
            "criteria_text": list(g["criteria"]),
            "expected_refs": list(g.get("expected_refs") or []),
        }
        v = official_judge.judge_row(row, repeats=JUDGE_REPEATS)
        rec["verdict"] = {
            "criteria": v.get("criteria"),
            "_corr_runs": v.get("_corr_runs"),
            "_judge_runs": v.get("_judge_runs"),
            "_criteria_rate_min": v.get("_criteria_rate_min"),
            "_criteria_rate_max": v.get("_criteria_rate_max"),
        }
        _write(records)
        idx = FOCAL[rec["row"]]
        runs = v.get("_corr_runs") or []
        cred = [bool(r[idx]) for r in runs if r]
        print(
            f"  judge {rec['row']} KG={rec['arm']} #{rec['sample']}: "
            f"focal criterion {idx} reps {cred} -> majority "
            f"{bool((v.get('criteria') or [False] * 9)[idx])}",
            flush=True,
        )


def summarize(records: list[dict], gold: dict[str, dict] | None = None) -> dict[str, Any]:
    """Per (row, arm): the focal criterion's credit rate, plus the row's own
    conciseness spread.

    The conciseness axis carries the R416 lever's only non-flat cost
    (``ans_conciseness`` -3.3 pp), and it is computed from answer LENGTH — the
    quantity these samples show is highly variable at fixed inputs. Recording the
    per-sample length and the rubric's own :func:`answer_conciseness` for each row
    lets that cost be read against its spread instead of asserted.
    """
    from evals.official.rubric import answer_conciseness  # noqa: PLC0415

    out: dict[str, Any] = {}
    for rid in FOCAL:
        idx = FOCAL[rid]
        for arm in ARMS:
            rs = [r for r in records if r["row"] == rid and r["arm"] == arm and r.get("verdict")]
            served = [r for r in rs if not str(r.get("stage2_served_by") or "").startswith("fallback")]
            fell = [r for r in rs if r not in served]
            maj = [bool((r["verdict"]["criteria"] or [])[idx]) for r in served]
            reps_focal = [
                bool(run[idx])
                for r in served
                for run in (r["verdict"]["_corr_runs"] or [])
                if run
            ]
            strict = [all(bool(c) for c in (r["verdict"]["criteria"] or [])) for r in served]
            chars = [len(r["answer"]) for r in served]
            ref = (gold or {}).get(rid, {}).get("reference_answer") or ""
            conc = [
                answer_conciseness(r["answer"], ref) for r in served if ref
            ]
            conc = [c for c in conc if c is not None]
            out[f"{rid}|KG={arm}"] = {
                "mean_answer_chars": round(sum(chars) / len(chars), 1) if chars else None,
                "answer_chars_range": [min(chars), max(chars)] if chars else None,
                "mean_ans_conc": round(100.0 * sum(conc) / len(conc), 2) if conc else None,
                "row": rid,
                "arm": arm,
                "focal_criterion": idx,
                "n_samples": len(rs),
                "n_primary": len(served),
                "n_fallback_excluded": len(fell),
                "focal_credit_majority": f"{sum(maj)}/{len(maj)}",
                "focal_credit_atomic_draws": f"{sum(reps_focal)}/{len(reps_focal)}",
                "strict_samples": f"{sum(strict)}/{len(strict)}",
                "focal_credit_per_sample": maj,
                "strict_per_sample": strict,
                "answer_chars": [len(r["answer"]) for r in rs],
                "legs": sorted({r.get("stage2_served_by") or "?" for r in rs}),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=5, help="independent generations per arm per row")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--judge-only", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    from app import config  # noqa: F401, PLC0415

    gold = _gold()
    validate_focal(gold)
    records = _load(SAMPLES_PATH)

    if not a.summarize_only:
        if not a.judge_only:
            print("=== generation ===", flush=True)
            generate(records, gold, a.samples, a.timeout)
        print("=== judging ===", flush=True)
        judge(records, gold)

    summary = summarize(records, gold)
    dest = OUT / "kgpt-credit-resample.json"
    dest.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print()
    print("=" * 92)
    print("CREDIT REPRODUCIBILITY ACROSS INDEPENDENT GENERATIONS")
    print("=" * 92)
    print(f"{'row':<8}{'arm':<6}{'n':>3}{'primary':>9}{'fallback':>9}"
          f"{'focal majority':>16}{'focal draws':>13}{'strict':>9}"
          f"{'chars(mean/range)':>22}{'ans_conc':>10}  legs")
    print("-" * 92)
    for v in summary.values():
        rng = v.get("answer_chars_range") or [0, 0]
        print(
            f"{v['row']:<8}KG={v['arm']:<3}{v['n_samples']:>3}{v['n_primary']:>9}"
            f"{v['n_fallback_excluded']:>9}{v['focal_credit_majority']:>16}"
            f"{v['focal_credit_atomic_draws']:>13}{v['strict_samples']:>9}"
            f"{str(v.get('mean_answer_chars')) + '/' + str(rng):>22}"
            f"{v.get('mean_ans_conc'):>10}  {v['legs']}"
        )
    print("-" * 92)
    print(f"\nwrote {dest.relative_to(REPO)}  ({LIBERAL_NOTE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

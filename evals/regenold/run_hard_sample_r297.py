"""R297/R298 — a stratified sample of the HARD requests in the 2026-07-07 batch.

Default design is ~10.7%; pass ``--frac`` for any other share (R298 used
``--frac 0.15`` -> 43 requests = 15.3%). See :func:`quotas_for_fraction`.

WHY A SAMPLER AT ALL
--------------------
``run_official_batch.py`` runs the whole batch, and its ``--limit N`` takes the
FIRST N questions — which is an ordering-biased slice, not a sample. For an
"N% of the hard questions" read we need proportional coverage of the hard tail,
so a weak number can be attributed to a stratum instead of blurred into one mean.

WHAT "THE HARD QUESTIONS" ACTUALLY ARE
--------------------------------------
The official export labels **281 of the 333 graded requests HARD**. They are not
one population — they split cleanly by REPLAY PROTOCOL:

  * **222 requests = Multi-Turn Context & Coreference.** These are the 111
    questions re-asked inside a rolling conversation, each answer then challenged
    with the evaluator's verbatim pushback ("I don't think this is correct...").
    Two requests per question (turn 1 + pushback), so 111 x 2 = 222.
  * **59 requests = HARD BY CONTENT, asked cold as a single turn.** Same
    protocol as the easy rows; only the CONTENT is hard. Five categories:
    Complex Decision Boundary 44, GPAI & Systemic Risk 7, Cross-Framework &
    Sectoral MedTech 5, Two-Article Conflict 2, Borderline Prohibition 1.

A sample that only took multi-turn rows, or only single-turn rows, would not be
representative of "the hard questions" — it would silently answer a different
question. So this sampler draws from BOTH, in proportion.

THE SAMPLE (default design; ``--frac`` rescales it)
---------------------------------------------------
Target 10% of 281 = 28.1 requests. Drawn as::

    stratum A  multi-turn          11 questions x 2 turns = 22 requests   (79.0% of hard -> 22/30 = 73%)
    stratum B  single-turn hard     8 questions x 1 turn  =  8 requests   (21.0% of hard ->  8/30 = 27%)
                                                            -----------
                                                            30 requests = 10.7% of 281

Stratum B is deliberately *slightly* over-weighted relative to a strict 21%
(which would give 6 requests) because three of its five categories have 1-2
members in the whole batch. A strictly proportional draw would sample ZERO
Two-Article Conflict and ZERO Borderline Prohibition rows and report nothing
about them. Guaranteeing >=1 per stratum is standard for rare strata and is the
only way the per-category breakdown is meaningful at n=30.

Within each stratum the draw is **deterministic and evenly spaced over send
order** (no RNG, no seed to remember): index ``round(k * (N - 1) / (n - 1))``.
That spreads the sample across the whole batch rather than clustering it, and
re-running this module reproduces the identical sample.

FIDELITY CAVEAT — STATED, NOT HIDDEN
------------------------------------
Multi-turn mode is a ROLLING conversation: each question is asked with the
previous 4 exchanges as context. Sampling 11 of 111 questions therefore gives
each sampled row a DIFFERENT prior-4-exchange context than the full run would
have. This does not invalidate the measurement — the hard-mode stressor is
"unrelated prior EU AI Act context + an adversarial pushback", and a sampled row
still gets exactly that — but the rows are NOT byte-comparable to a full-run
replay of the same ids. Only compare sample-to-sample, or sample-to-full with
this caveat attached.

USAGE
-----
    # print the sample composition and exit (no LLM calls)
    .venv/Scripts/python.exe -m evals.regenold.run_hard_sample_r297 --dry-run

    # run it (in-process route + whatever provider env is active)
    .venv/Scripts/python.exe -m evals.regenold.run_hard_sample_r297 --label r297

    # against deployed prod
    ... --endpoint https://<host>/api/v1/regenold/eu-ai-act/ask --api-key $KEY

Then grade both arms with the grounded judge (the right instrument here — the
official gold references are not in this repo)::

    .venv/Scripts/python.exe -m evals.judge.grounded \\
        --sidecar evals/bench/results/official-<label>-mt-hard.ckpt.jsonl \\
        --label <label>-mt --model claude-sonnet-5 --provider wrapper
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

from dotenv import load_dotenv

# Sibling live runners (run_graphrag_benchmark, run_docx_exact, evals.judge.*)
# all do this; run_official_batch does NOT, which means a bare invocation runs
# with NO provider, NO wrapper base URL and NO graph credentials — i.e. the
# deterministic path — while looking like a live run. Load before importing
# anything that builds import-time pydantic settings.
load_dotenv()

from evals.regenold.july7_difficulty import (  # noqa: E402 — must follow load_dotenv
    CAT_BORDERLINE_PROHIBITION_EXCEPTION,
    CAT_COMPLEX_DECISION_BOUNDARY,
    CAT_CROSS_FRAMEWORK_SECTORAL_MEDTECH_INTEGRATION,
    CAT_GPAI_SYSTEMIC_RISK_BOUNDARY,
    CAT_TWO_ARTICLE_CONFLICT_RECONCILIATION,
    DIFFICULTY_HARD,
)
from evals.regenold.official_batch import load_official_batch  # noqa: E402
from evals.regenold.run_official_batch import _RESULTS, _arm, _parse_env  # noqa: E402

#: How many MULTI-TURN questions to draw (x2 requests each).
N_MULTITURN_QUESTIONS = 11

#: How many single-turn HARD-BY-CONTENT questions to draw, per category.
#: Complex Decision Boundary carries 44 of the 59 so it gets the proportional
#: share; the four rarer categories get a guaranteed floor of 1 (see module
#: docstring — a strictly proportional draw would sample zero of three of them).
SINGLE_TURN_QUOTA: dict[str, int] = {
    CAT_COMPLEX_DECISION_BOUNDARY: 4,
    CAT_GPAI_SYSTEMIC_RISK_BOUNDARY: 1,
    CAT_CROSS_FRAMEWORK_SECTORAL_MEDTECH_INTEGRATION: 1,
    CAT_TWO_ARTICLE_CONFLICT_RECONCILIATION: 1,
    CAT_BORDERLINE_PROHIBITION_EXCEPTION: 1,
}

#: Ground truth for the denominator, from the official export header.
TOTAL_HARD_REQUESTS = 281
MULTITURN_HARD_REQUESTS = 222
SINGLE_TURN_HARD_REQUESTS = 59


def _evenly_spaced(items: list, n: int) -> list:
    """Pick ``n`` items evenly spread across ``items``, endpoints included.

    Deterministic — no RNG. ``n >= len(items)`` returns everything.
    """
    total = len(items)
    if n >= total:
        return list(items)
    if n <= 0:
        return []
    if n == 1:
        return [items[total // 2]]
    picked_idx = sorted({round(k * (total - 1) / (n - 1)) for k in range(n)})
    return [items[i] for i in picked_idx]


def quotas_for_fraction(frac: float) -> tuple[int, dict[str, int]]:
    """Scale the stratified design to an arbitrary target fraction of HARD.

    Multi-turn takes ``frac`` of its 222 requests (2 per question). Single-turn
    takes ``frac`` of its 59, with a GUARANTEED FLOOR OF 1 for each of the four
    rare categories (GPAI 7, Cross-Framework 5, Two-Article 2, Borderline 1) —
    without the floor, a strictly proportional draw reports nothing at all about
    three of them. Complex Decision Boundary (44 of the 59) absorbs the
    remainder, so it is the category the floors dilute. Stated, not hidden.
    """
    frac = max(0.01, min(1.0, float(frac)))
    mt_questions = max(1, round(frac * MULTITURN_HARD_REQUESTS / 2))
    st_total = max(4, round(frac * SINGLE_TURN_HARD_REQUESTS))
    rare = (
        CAT_GPAI_SYSTEMIC_RISK_BOUNDARY,
        CAT_CROSS_FRAMEWORK_SECTORAL_MEDTECH_INTEGRATION,
        CAT_TWO_ARTICLE_CONFLICT_RECONCILIATION,
        CAT_BORDERLINE_PROHIBITION_EXCEPTION,
    )
    quota = {c: 1 for c in rare}
    quota[CAT_COMPLEX_DECISION_BOUNDARY] = max(1, st_total - len(rare))
    return mt_questions, quota


def select_sample(frac: float | None = None) -> tuple[list, list]:
    """Return ``(multiturn_rows, single_turn_hard_rows)``.

    ``frac`` targets that share of the 281 HARD requests; ``None`` keeps the
    original R297 design (11 multi-turn + 8 single-turn = 10.7%).
    """
    rows = list(load_official_batch())
    n_mt = N_MULTITURN_QUESTIONS
    quota = SINGLE_TURN_QUOTA
    if frac is not None:
        n_mt, quota = quotas_for_fraction(frac)

    # --- stratum A: multi-turn ------------------------------------------------
    # The evaluator re-asked EVERY question in multi-turn form, easy and hard
    # alike, so the multi-turn draw is taken over the full send order rather
    # than filtered to HARD-labelled rows. Filtering here would misrepresent the
    # stratum: in multi-turn mode the official taxonomy labels every request
    # HARD / Multi-Turn Context & Coreference regardless of its single-turn tag.
    multiturn = _evenly_spaced(rows, n_mt)

    # --- stratum B: single-turn, hard BY CONTENT ------------------------------
    single: list = []
    for category, q in quota.items():
        pool = [r for r in rows if r.difficulty == DIFFICULTY_HARD
                and r.difficulty_category == category]
        single.extend(_evenly_spaced(pool, q))
    # Keep send order so the printed sample reads like the batch.
    order = {id(r): i for i, r in enumerate(rows)}
    single.sort(key=lambda r: order[id(r)])
    return multiturn, single


def _describe(multiturn: list, single: list) -> dict[str, Any]:
    mt_req = len(multiturn) * 2
    st_req = len(single)
    total = mt_req + st_req
    per_cat: dict[str, int] = {}
    for r in single:
        per_cat[r.difficulty_category] = per_cat.get(r.difficulty_category, 0) + 1
    # A question can legitimately land in BOTH strata (the evaluator itself
    # asked every question single-turn AND multi-turn). Surfaced rather than
    # de-duplicated: an overlap row is the one place we get a controlled
    # single-turn vs multi-turn read on the SAME question.
    overlap = sorted({r.id for r in multiturn} & {r.id for r in single})
    return {
        "sample_design": "R297 stratified, deterministic (evenly spaced over send order)",
        "hard_requests_in_batch": TOTAL_HARD_REQUESTS,
        "sampled_requests": total,
        "sampled_pct_of_hard": round(100.0 * total / TOTAL_HARD_REQUESTS, 1),
        "stratum_a_multiturn": {
            "questions": len(multiturn),
            "requests": mt_req,
            "population_requests": MULTITURN_HARD_REQUESTS,
            "ids": [r.id for r in multiturn],
        },
        "stratum_b_single_turn_hard": {
            "questions": len(single),
            "requests": st_req,
            "population_requests": SINGLE_TURN_HARD_REQUESTS,
            "per_category": per_cat,
            "ids": [r.id for r in single],
        },
        "cross_mode_overlap_ids": overlap,
    }


def _print_sample(desc: dict[str, Any]) -> None:
    a, b = desc["stratum_a_multiturn"], desc["stratum_b_single_turn_hard"]
    print("\n=== R297 stratified hard sample ===")
    print(f"  {desc['sampled_requests']} requests = "
          f"{desc['sampled_pct_of_hard']}% of the {desc['hard_requests_in_batch']} HARD requests")
    print(f"  A  multi-turn        : {a['questions']:2d} questions x2 turns = "
          f"{a['requests']:2d} req   (population {a['population_requests']})")
    print(f"     ids: {', '.join(a['ids'])}")
    print(f"  B  single-turn hard  : {b['questions']:2d} questions x1 turn  = "
          f"{b['requests']:2d} req   (population {b['population_requests']})")
    for cat, n in sorted(b["per_category"].items(), key=lambda x: -x[1]):
        print(f"       {n:2d}  {cat}")
    print(f"     ids: {', '.join(b['ids'])}")
    if desc["cross_mode_overlap_ids"]:
        print(f"  ++ in BOTH strata (single-turn vs multi-turn on the same question): "
              f"{', '.join(desc['cross_mode_overlap_ids'])}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default="r297")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--api-key", default=os.environ.get("REGENOLD_API_KEY"))
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--frac", type=float, default=None,
                    help="target share of the 281 HARD requests (e.g. 0.15); "
                         "omit for the original ~10.7 percent design")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the sample composition and exit (no LLM calls)")
    ap.add_argument("--only", choices=("mt", "st", "both"), default="both")
    ap.add_argument("--env", action="append", default=None,
                    help="KEY=VALUE applied for the duration of the run")
    args = ap.parse_args()

    multiturn, single = select_sample(args.frac)
    desc = _describe(multiturn, single)
    _print_sample(desc)
    if args.dry_run:
        return

    from evals.regenold.runner_v2 import _post, _post_local

    local = not args.endpoint
    poster = _post_local if local else _post
    url = (
        "local://app.main:app/api/v1/regenold/eu-ai-act/ask"
        if local
        else str(args.endpoint)
    )
    # Ask for the reasoning trace so provenance (did Stage-2 land? which model?)
    # is recorded. The rubric ignores `reasoning`, so this cannot move a score.
    if "include_reasoning" not in url:
        url = f"{url}{'&' if '?' in url else '?'}include_reasoning=true"

    arm_env = _parse_env(args.env)
    payload: dict[str, Any] = {
        "label": args.label,
        "batch": "regenold-official-2026-07-07",
        "sample": desc,
        "endpoint": url,
        "env": arm_env,
    }

    if args.only in ("mt", "both"):
        got = _arm(
            f"{args.label}-mt", "hard", multiturn,
            poster=poster, url=url, api_key=args.api_key, timeout=args.timeout,
            arm_env=arm_env, suffix="",
        )
        payload["multiturn"] = {m: {"agg": v["agg"], "strata": v["strata"]}
                                for m, v in got.items()}
    if args.only in ("st", "both"):
        got = _arm(
            f"{args.label}-st", "easy", single,
            poster=poster, url=url, api_key=args.api_key, timeout=args.timeout,
            arm_env=arm_env, suffix="",
        )
        payload["single_turn"] = {m: {"agg": v["agg"], "strata": v["strata"]}
                                  for m, v in got.items()}

    out = _RESULTS / f"hardsample-{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":  # pragma: no cover
    main()

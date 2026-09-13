"""R415 — the single-turn full-system lever, measured on the OFFICIAL board.

WHY A SECOND GATE EXISTS AT ALL
-------------------------------
R412 flipped ``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`` to default ON on a paired
gate over the *harness probe corpus* (``paper_st_v4`` / ``paper_tricky_v4`` /
``multiarticle_r268``). That corpus carries per-row ``expected_refs`` and
``expected_keywords`` but **no correctness criteria**, so the gate could read the
reference axes and latency and nothing else. The R415 checkpoint recorded that as
"the correctness axes need the Claude-Max wrapper judge, whose OAuth is expired".
That reason is wrong, and the difference matters: even with a working judge the
probe corpus has nothing to judge correctness *against*. Measured — 0 of the 95
easy probe questions appear in ``official_gold_n110.jsonl``.

The answer to "quantify the board movement" therefore stopped at 6 of 8 axes for
a reason that had nothing to do with the judge. This gate closes it on the corpus
that CAN be judged: the reconstructed official gold (110 rows, each with criteria
+ reference answer + expected refs).

WHY IT SWEEPS THE WHOLE BOARD INSTEAD OF A SLICE
------------------------------------------------
The first draft ran the usual contiguous slice. The smoke run falsified that
design: of the first six graded rows, **four** were answered in ~4 s with ZERO
Stage-2 attempts — curated deterministic intercepts, which the lever cannot
touch because it edits the system slot of a model call that never happens.
Diluting a reachable subset into a convenience slice is how a real effect reads
as a weak one, so the gate does two things instead:

  1. **ARM B over ALL 110 rows** (the shipped configuration), recording per-row
     whether Stage-2 ran. That yields the *reachable surface* — how many graded
     rows the model answers at all — which is a board fact in its own right.
  2. **ARM A over exactly the reachable ids only**, so the paired read is on
     matched rows the lever can move, and no call is spent on an inert row.

WHAT THIS GATE IS AND IS NOT
----------------------------
* IS a paired A/B on the same rows in the same order, so the DELTA is the lever.
* IS NOT the official board. Criteria and reference answers are reconstructed
  (`evals.official`), and the reachable subset is not a random sample. Compare
  ARMS under this instrument; never quote an arm as a score.
* The hard split is deliberately absent: R415 §3 proved the graded multi-turn
  payload is byte-identical between the arms, so the lever's hard movement is
  zero BY CONSTRUCTION, not by measurement.

VOID DETECTION
--------------
Stage-2 is tunnel -> Bedrock, and the Bedrock leg always receives the FULL
system, so when the tunnel is down both arms are byte-identical and the run can
only measure sampling noise — the R412 near-miss, where a complete 95+95 run
carrying 189 ``bedrock_auto_fallback`` lines printed a plausible-looking null.
Each arm writes ``gate_validity``'s transport counters into its own sidecar, and
``--score`` REFUSES to print a delta table when the fallback leg carried a row of
the pair, when it carried so much of an arm that the survivors stop representing
the reachable surface, or when the lever never reached the model at all.

A fallback row is DROPPED from the pair rather than voiding the run, and the drop
has to happen on both sides or it becomes its own confound: arm A's raw matched
run contains the one row the tunnel lost, so scoring that file directly would put
a fallback row in arm A's mean while arm B's mean excluded its own. ``score``
therefore reduces BOTH arms to the same comparable id set before judging. (R415's
first draft got this backwards — it dropped the row for pairing and then voided on
it, so it could never print a table.)

    # 1. shipped arm over the whole graded board (classification + answers)
    .venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py --arm b
    # 2. baseline arm over exactly the rows Stage-2 reached in step 1
    .venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py --arm a --matched-from b
    # 3. judge both arms on the matched subset, print the paired 8-axis table
    .venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py --score

ANY LEVER (R416)
----------------
The instrument was written for one flag, but every unproven roadmap row needs
this same read, so it now takes the flag, the two arm values and an output tag.
The reach set belongs to the ROUTE (intercept vs model call), not to the lever,
so a later lever reuses step 1's reach list and changes only its own arm B —
which also keeps arm A's judge verdicts a cache hit, so a new lever costs ONE arm
of calls, not two:

    .venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py \\
        --arm b --matched-from b --reach-from docs/measurements/r415/official-lever-b.ckpt.jsonl \\
        --flag REGENOLD_KG_POINT_TEXT --arm-values 0,1 --tag -kgpt
    .venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py --score \\
        --flag REGENOLD_KG_POINT_TEXT --tag -kgpt \\
        --baseline docs/measurements/r415/official-lever-b-matched.ckpt.jsonl

**ONE-FLAG INVARIANT.** The arms must differ by exactly the flag under test. Arm
B of a new lever run picks up the *shipped* defaults for every other flag, so
baselining it against the R415 arm-A run — which has the single-turn lever OFF —
compares two flags at once and reports their blend. R416 hit this: the first KG
table read +6.1 pp overall, which was almost entirely the R415 lever's own effect.
`--baseline` names the run that differs by one flag, and the gate prints both run
names above the table so the invariant is visible in the artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r415"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

#: arm -> the lever's value. For the R415 lever, A is the pre-R412 behaviour
#: (persona in the system slot) and B is what ships.
ARMS = {"a": "0", "b": "1"}
FLAG = "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN"

#: R416 — the same instrument now pairs ANY binary lever on the official corpus.
#: The gate was written for one flag, but every unproven roadmap row (3
#: content-preservation, 4 grain, 5 KG point text) needs exactly this read: the
#: reachable rows, both arms tunnel-served, all eight axes judged. `--flag`,
#: `--arm-values` and `--tag` re-point it without touching the pairing logic.
ARM_VALUES = {"a": "0", "b": "1"}
OUT_TAG = ""
REACH_FROM = ""

AXES = (
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
)


def _ckpt(arm: str, tag: str = "") -> Path:
    return OUT / f"official-lever-{arm}{tag}.ckpt.jsonl"


def _sidecar(arm: str, tag: str = "") -> Path:
    return OUT / f"official-lever-{arm}{tag}.run.json"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_arm(arm: str, n: int | None, matched_from: str | None) -> int:
    """Drive the REAL route for one arm, over the board or the reachable subset."""
    # Live provider config must come from .env: the whole point is the tunnel leg.
    os.environ.pop("REGENOLD_SKIP_DOTENV", None)
    os.environ[FLAG] = ARM_VALUES[arm]

    from fastapi.testclient import TestClient

    from app.llm.stage2_policy import reset_transport_stats, transport_stats
    from app.main import app
    from app.rate_limit import limiter
    from app.routes.regenold import _reconcile_references_to_prose

    # The anon bucket is 30/min and this walks the board back to back, so the
    # tail would read as 429 rather than as an answer (the R411 corpus_ab lesson).
    limiter.enabled = False

    gold = _load_jsonl(GOLD)
    if n:
        gold = gold[:n]
    tag = ""
    if matched_from:
        # The reachable subset is defined by the OTHER arm's per-row provenance,
        # and it excludes the fallback-served rows. A row that fell back was
        # answered by Bedrock, which ALWAYS receives the full system, so on that
        # row the two arms dispatch identical bytes whatever the lever says — it
        # is structurally incomparable and pairing it would only dilute a real
        # effect. (This is the R412 lesson enforced per row instead of per run.)
        reach_path = Path(REACH_FROM) if REACH_FROM else _ckpt(matched_from)
        source = _load_jsonl(reach_path)
        reachable = [
            r["id"] for r in source if r.get("stage2_used") and not r.get("stage2_fell_back")
        ]
        wanted = set(reachable)
        gold = [g for g in gold if g["id"] in wanted]
        # The reach set is a property of the ROUTE (intercept vs model call), not
        # of the lever, so a later lever reuses the R415 sweep's reach list and
        # only its own arm-B answers carry the tag.
        tag = f"-matched{OUT_TAG}"
        if not gold:
            print(f"no reachable rows in {_ckpt(matched_from).name} — nothing to pair")
            return 2

    ckpt, sidecar = _ckpt(arm, tag), _sidecar(arm, tag)
    OUT.mkdir(parents=True, exist_ok=True)
    ckpt.unlink(missing_ok=True)  # a stale arm must never be spliced into a new run

    reset_transport_stats()
    client = TestClient(app)
    rows: list[dict] = []
    t_start = time.time()
    for i, g in enumerate(gold, 1):
        t0 = time.time()
        before = dict(transport_stats())
        try:
            resp = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json=[{"role": "user", "content": g["question"]}],
            )
            body = resp.json() if resp.status_code == 200 else {}
            status = resp.status_code
        except Exception as exc:  # noqa: BLE001 — a gate records, never dies
            body, status = {}, f"EXC {type(exc).__name__}: {exc}"
        dt = time.time() - t0
        answer = body.get("answer") or ""
        refs = _reconcile_references_to_prose(list(body.get("references") or []), answer)
        after = dict(transport_stats())
        used = int(after.get("primary_attempts", 0)) - int(before.get("primary_attempts", 0)) > 0
        fell_back = int(after.get("fallback_attempts", 0)) - int(before.get("fallback_attempts", 0)) > 0
        row = {
            "id": g["id"],
            "question": g["question"],
            "pred_answer": answer,
            "pred_refs": refs,
            "latency_ms": int(dt * 1000),
            "mode": "easy",
            "http_status": status,
            "answer_chars": len(answer),
            "stage2_used": used,
            "stage2_fell_back": fell_back,
        }
        rows.append(row)
        # Per-row checkpoint: this session has been interrupted mid-gate before,
        # and re-paying for answered rows is the one cost never justified.
        with ckpt.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"  [{i:3d}/{len(gold)}] {g['id']:<8} {len(answer):5d} chars "
            f"{len(refs):2d} refs {dt:5.1f}s "
            f"s2={'yes' if used else 'no '}{'/fallback' if fell_back else ''}",
            flush=True,
        )

    from evals.harness.gate_validity import stage2_transport_snapshot

    stats = stage2_transport_snapshot()
    payload = {
        "arm": arm,
        "flag": FLAG,
        "value": ARMS[arm],
        "tag": tag,
        "n": len(rows),
        "errors": sum(1 for r in rows if r["http_status"] != 200),
        "stage2_served_rows": sum(1 for r in rows if r["stage2_used"]),
        "stage2_fell_back_rows": sum(1 for r in rows if r["stage2_fell_back"]),
        "wall_s": round(time.time() - t_start, 1),
        "transport": stats,
    }
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"\narm {arm}{tag}: {payload['n']} rows, {payload['errors']} errors, "
        f"stage2 served {payload['stage2_served_rows']}, fallback "
        f"{payload['stage2_fell_back_rows']}, transport={stats}"
    )
    print(f"wrote {ckpt.relative_to(REPO)}")
    return 0


def _score_lines(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in text.splitlines():
        m = re.match(
            r"^(ans_correctness_loose|ans_correctness_strict|ans_conciseness|"
            r"ref_correctness_loose|ref_correctness_strict|ref_conciseness|"
            r"regulatory_tone|resp_speed)\s+(-?\d+\.\d+)",
            line,
        )
        if m:
            out[m.group(1)] = float(m.group(2))
            continue
        m = re.match(r"^OVERALL \(geo mean\)\s+(-?\d+\.\d+)", line)
        if m:
            out["overall"] = float(m.group(1))
    return out


def _fallback_served(sidecar: dict) -> bool:
    """Did the fallback leg carry any row of this arm? Unknown counts as served."""
    if not sidecar:
        return True  # no sidecar = no provenance = not eligible to report
    stats = sidecar.get("transport") or {}
    if stats.get("_error"):
        return True
    if int(sidecar.get("stage2_fell_back_rows") or 0) > 0:
        return True
    return int(stats.get("fallback_ok") or 0) + int(stats.get("fallback_attempts") or 0) > 0


def report_board() -> None:
    """The reachable surface, from arm B's whole-board sweep."""
    full = _ckpt("b")
    if not full.exists():
        return
    rows = _load_jsonl(full)
    served = [r for r in rows if r.get("stage2_used")]
    fell = [r for r in served if r.get("stage2_fell_back")]
    comparable = [r for r in served if not r.get("stage2_fell_back")]
    print("\n" + "-" * 78)
    print("REACHABLE SURFACE — which graded rows the model is asked to answer")
    print("-" * 78)
    print(f"  graded rows swept          {len(rows)}")
    print(f"  Stage-2 served             {len(served)}")
    print(f"    of which fallback-served {len(fell)} (structurally incomparable)")
    print(f"  deterministic intercepts   {len(rows) - len(served)}")
    print(f"  paired-eligible rows       {len(comparable)}")
    if comparable:
        lat = sorted(r["latency_ms"] / 1000.0 for r in comparable)
        print(f"  served-row latency p50     {lat[len(lat) // 2]:.1f}s")
    (OUT / "official-board-stage2-reach.json").write_text(
        json.dumps(
            {
                "graded_rows_swept": len(rows),
                "stage2_served": [r["id"] for r in served],
                "fallback_served": [r["id"] for r in fell],
                "paired_eligible": [r["id"] for r in comparable],
                "intercept_served": [r["id"] for r in rows if not r.get("stage2_used")],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def score(args: argparse.Namespace) -> int:
    report_board()

    # Materialise arm B's answer to the SAME subset arm A was run on, so the two
    # checkpoints are matched row-for-row.
    # ONE-FLAG INVARIANT: the two arms must differ by exactly the flag under test,
    # or the delta is a blend. The default baseline is the R415 arm-A run, which is
    # correct only while the R415 lever is genuinely off in both arms. For the R416
    # KG lever that is FALSE — arm A has `..._SINGLE_TURN=0` while a new arm-B run
    # picks up the shipped default `=1` — so R416 compared KG-ON against the
    # single-turn arm A, got +6.1 pp, and that reading was thrown away as a blend,
    # not reported. The honest baseline for a lever shipped ON top of another is the
    # run whose config differs by that one flag (here: the R415 arm-B run), and
    # `--baseline` makes that explicit instead of implied.
    a_path = Path(args.baseline) if args.baseline else _ckpt("a", "-matched")
    b_full = _ckpt("b", f"-matched{OUT_TAG}") if OUT_TAG else _ckpt("b")
    if not a_path.exists() or not b_full.exists():
        print(f"missing {a_path.name} or {b_full.name} — run the arm first")
        return 2
    a_rows = _load_jsonl(a_path)
    raw_b = _load_jsonl(b_full)
    # Fallback doctrine, applied to BOTH arms identically: a row served by the
    # Bedrock leg is structurally incomparable (that leg always receives the full
    # `system`, so it dispatches identical bytes whatever the lever says), so it is
    # DROPPED from the pair. Voiding is reserved for the case where the transport
    # failed for a whole arm, which the residue checks below catch. Applying the
    # drop to one arm and the void to the other is how a real reading becomes
    # unreportable — R416 hit exactly that with 2 fallback rows on the new arm.
    drop_a = sorted(r["id"] for r in a_rows if r.get("stage2_fell_back"))
    drop_b = sorted(r["id"] for r in raw_b if r.get("stage2_fell_back"))
    a_ids = {r["id"] for r in a_rows if not r.get("stage2_fell_back")}
    b_ids = {r["id"] for r in raw_b if not r.get("stage2_fell_back")}
    paired_ids = a_ids & b_ids
    matched = [r for r in raw_b if r["id"] in paired_ids]
    for label, drop in (("A", drop_a), ("B", drop_b)):
        if drop:
            print(f"  dropping {len(drop)} row(s) arm {label} on the fallback leg: {drop[:5]}")
    # Dropping is only honest while the survivors still describe the surface the
    # sweep found. Past that the pair is a residue of a broken transport, not a
    # matched A/B, so it is refused instead of reported on a shrinking subset.
    for label, drop, total in (("A", drop_a, len(a_rows)), ("B", drop_b, len(raw_b))):
        if drop and len(drop) > total / 2:
            print(
                f"the fallback leg carried {len(drop)}/{total} of arm {label}'s rows — "
                "the survivors no longer represent the reachable surface; refusing a delta"
            )
            return 3
    # Both arms are written to the SAME comparable id set, so neither mean carries
    # a row the other excluded. Arm A's raw matched run stays on disk for audit.
    b_path = _ckpt("b", f"-matched{OUT_TAG}")
    b_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in matched) + "\n",
        encoding="utf-8",
    )
    a_paired = _ckpt("a", f"-paired{OUT_TAG}")
    a_paired.write_text(
        "\n".join(
            json.dumps(r, ensure_ascii=False) for r in a_rows if r["id"] in paired_ids
        )
        + "\n",
        encoding="utf-8",
    )
    if len(matched) < 2:
        print("fewer than two comparable rows survive — refusing to report a delta")
        return 3
    print(f"  lever under test: {FLAG}: a={ARM_VALUES['a']} b={ARM_VALUES['b']}")
    print(f"  baseline (A) run: {a_path.name}")
    print(f"  treatment (B) run: {b_full.name}")

    # Non-vacuity: the paired rows are reachable BY CONSTRUCTION (arm B's sweep
    # chose them), but arm A is a separate process, so confirm the lever really
    # was exercising rows there too rather than reading a dead transport as a delta.
    a_used = sum(1 for r in _load_jsonl(a_path) if r.get("stage2_used"))
    print(
        f"  control: arm A reached the model on {a_used}/{len(a_ids)} paired row(s), "
        f"arm B on {sum(1 for r in matched if r.get('stage2_used'))}/{len(matched)}"
    )

    scores: dict[str, dict[str, float]] = {}
    void: list[str] = []
    if a_used == 0:
        void.append(
            "the lever never reached the model on arm A — every paired row was served "
            "without a Stage-2 call, so the two arms are the same prompt"
        )
    provenance: list[str] = []
    for arm, path in (("a", a_paired), ("b", b_path)):
        rows_arm = _load_jsonl(path)
        # Per-row provenance is the PRIMARY check — it is what actually decides
        # whether a given row can be compared. The sidecar is the secondary one
        # (it can exist only for an arm that ran to completion in this process).
        fell = [r["id"] for r in rows_arm if r.get("stage2_fell_back")]
        if fell:
            void.append(
                f"arm {arm}: {len(fell)} paired row(s) were served by the Bedrock "
                f"fallback leg ({fell[:5]}) — the fallback always receives the full "
                "system, so those rows cannot show the lever"
            )
        unreached = [r["id"] for r in rows_arm if not r.get("stage2_used")]
        if unreached:
            void.append(
                f"arm {arm}: {len(unreached)} paired row(s) took no Stage-2 call at all "
                f"({unreached[:5]}) — the lever edits a model call that did not happen"
            )
        sidecar_path = _sidecar(arm, f"-matched{OUT_TAG}" if arm == "b" else "-matched")
        if arm == "a" and args.baseline:
            # A non-default baseline has its own provenance file name; read it when
            # present so the transport line still describes the run that was used.
            stem = Path(args.baseline).name.replace(".ckpt.jsonl", ".run.json")
            sidecar_path = Path(args.baseline).with_name(stem)
        if sidecar_path.exists():
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            # Reported, not voided: a row-level fallback is already handled by the
            # drop above, and an arm-level one that left nothing comparable was
            # already refused. Voiding here too is what made the first draft of
            # this gate unable to print a table at all.
            provenance.append(
                f"arm {arm}: fallback_served={_fallback_served(sidecar)} "
                f"transport={sidecar.get('transport')}"
            )
        cmd = [
            sys.executable, "-m", "evals.official.score_arm",
            "--ckpt", str(path), "--label", f"r415-official-lever-{arm}-matched{OUT_TAG}", "--mode", "easy",
            "--judge-provider", args.judge_provider, "--judge-model", args.judge_model,
            "--repeats", str(args.repeats), "--workers", str(args.workers),
            "--cache-file", str(OUT / f"judge-cache-r415-{args.judge_provider}.jsonl"),
        ]
        print(f"\n$ {' '.join(cmd[1:])}", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
        printed = proc.stdout + proc.stderr
        (OUT / f"score-arm-{arm}.log").write_text(printed, encoding="utf-8")
        tail = printed.strip().splitlines()[-1] if printed.strip() else "(no output)"
        print(f"  exit={proc.returncode}  {tail[:150]}")
        # R414 — score_arm exits 3 when its JUDGE leg answered nothing and
        # withholds the judged axes. Parsing its table anyway is how a dead judge
        # became an arm delta in R413.
        if proc.returncode != 0:
            void.append(f"arm {arm}: score_arm exited {proc.returncode} (judge leg refused)")
            scores[arm] = {}
            continue
        scores[arm] = _score_lines(printed)

    if void:
        print("\n" + "!" * 78)
        print("VOID — ARM DELTAS ARE WITHHELD.")
        for reason in void:
            print(f"  VOID: {reason}")
        print("!" * 78)
        return 3

    a, b = scores["a"], scores["b"]
    print("\n" + "=" * 78)
    print(f"{'axis':<26}{'A lever OFF':>13}{'B lever ON':>13}{'delta pp':>12}")
    print("-" * 78)
    for k in AXES:
        if k in a and k in b:
            print(f"{k:<26}{a[k]:>13.1f}{b[k]:>13.1f}{b[k] - a[k]:>+12.1f}")
    if "overall" in a and "overall" in b:
        print("-" * 78)
        print(f"{'OVERALL (geo mean)':<26}{a['overall']:>13.1f}{b['overall']:>13.1f}"
              f"{b['overall'] - a['overall']:>+12.1f}")
    print("=" * 78)
    print(f"paired on the {len(matched)} row(s) where Stage-2 reached the model.")
    for line in provenance:
        print(f"  transport provenance — {line}")
    if drop_a or drop_b:
        print(f"  dropped from the pair (fallback-served): A={drop_a} B={drop_b}")
    (OUT / f"official-lever-paired{OUT_TAG}.json").write_text(
        json.dumps(
            {
                "lever": f"{FLAG}: a={ARM_VALUES['a']} b={ARM_VALUES['b']}",
                "paired_n": len(matched),
                "paired_ids": [r["id"] for r in matched],
                "arm_a": a,
                "arm_b": b,
                "delta_pp": {k: b[k] - a[k] for k in b if k in a},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


def main() -> int:
    # Declared first: the argparse defaults below read the current values, and a
    # `global` after a use of the name is a SyntaxError.
    global FLAG, ARM_VALUES, OUT_TAG, REACH_FROM
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("a", "b"))
    ap.add_argument("--n", type=int, default=None, help="first n graded rows (default: all 110)")
    ap.add_argument(
        "--matched-from",
        choices=("a", "b"),
        help="run only the rows that arm's sweep reached with a Stage-2 call",
    )
    ap.add_argument("--score", action="store_true", help="judge both arms and print the paired table")
    ap.add_argument("--flag", default=FLAG, help="the env flag this gate pairs (R416: any lever)")
    ap.add_argument(
        "--arm-values",
        default="0,1",
        help="the flag's value for arm a and arm b, comma-separated (default 0,1)",
    )
    ap.add_argument("--tag", default="", help="suffix for this lever's arm-B artifacts (e.g. -kgpt)")
    ap.add_argument(
        "--baseline",
        default="",
        help=(
            "checkpoint to use as arm A. Default: the R415 arm-A matched run. Point "
            "this at the run whose config differs from arm B by exactly the flag "
            "under test (ONE-FLAG INVARIANT) — e.g. the R415 arm-B run for a lever "
            "shipped on top of the single-turn lever."
        ),
    )
    ap.add_argument(
        "--reach-from",
        default="",
        help="checkpoint holding the reach list; default: the matched arm named by --matched-from",
    )
    ap.add_argument("--judge-provider", default="wrapper", choices=("bedrock", "wrapper"))
    ap.add_argument("--judge-model", default=os.getenv("R388_JUDGE_MODEL", "claude-sonnet-5"))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workers", type=int, default=1, help="1 for the CLAUDE-MAX wrapper (R393)")
    args = ap.parse_args()

    # The flag/value pair is what makes this gate reusable across levers; it is
    # set before any request so both arms are dispatched under their own config.
    FLAG = args.flag
    OUT_TAG = args.tag
    REACH_FROM = args.reach_from
    try:
        a_val, b_val = (v.strip() for v in args.arm_values.split(",", 1))
        ARM_VALUES = {"a": a_val, "b": b_val}
    except ValueError:
        ap.error("--arm-values must be two comma-separated values, e.g. 0,1")

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    if args.score:
        return score(args)
    if not args.arm:
        ap.error("--arm, --matched-from or --score is required")
    return run_arm(args.arm, args.n, args.matched_from)


if __name__ == "__main__":
    raise SystemExit(main())

"""R388 - score a captured arm against the reconstructed official rubric.

Takes a checkpoint of live answers plus the reconstructed gold
(:mod:`evals.official.build_gold`), judges the answer and tone axes
(:mod:`evals.official.judge`), and reports all eight axes plus the geometric
mean, alongside the official 2026-08-25 figures for the same mode.

The judged verdicts are CACHED per (arm-label, question id, sha of the answer),
so re-scoring an arm costs nothing and a re-run after a code change only pays
for the rows whose answer actually changed.  That is what makes an iterate-and-
measure loop affordable over a single wrapper.

    .venv/Scripts/python.exe -m evals.official.score_arm \\
        --ckpt evals/bench/results/official-r387_live_easy-easy.ckpt.jsonl \\
        --label r387-easy --mode easy
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from evals.bench.row_provenance import leg_label, polish_flag  # noqa: E402
from evals.official import judge as official_judge  # noqa: E402
from evals.official.rubric import AXIS_ORDER, _clean, score_rows  # noqa: E402

GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
CACHE = REPO / "docs" / "measurements" / "r388" / "judge_cache.jsonl"
OUT_DIR = REPO / "docs" / "measurements" / "r388"

# The printed figures, for orientation only.  Never quote a number from this
# module AS an official number -- the criteria and reference answers are
# reconstructed (see evals/official/__init__.py).
OFFICIAL = {
    "easy": {
        "us": dict(zip(AXIS_ORDER, [89.7, 81.2, 51.9, 89.4, 68.3, 50.4, 99.1, 87.6], strict=True)),
        "frontier_2026": dict(zip(AXIS_ORDER, [94.4, 89.1, 67.9, 96.1, 78.5, 51.9, 100.0, 81.8], strict=True)),
        "baseline_2025": dict(zip(AXIS_ORDER, [83.8, 70.9, 51.1, 79.9, 52.0, 48.7, 99.1, 95.3], strict=True)),
        "overall": {"us": 75.1, "frontier_2026": 80.9, "baseline_2025": 70.1},
    },
    "hard": {
        "us": dict(zip(AXIS_ORDER, [89.9, 80.0, 45.2, 89.5, 70.7, 49.8, 96.1, 85.7], strict=True)),
        "frontier_2026": dict(zip(AXIS_ORDER, [92.0, 84.8, 71.8, 94.6, 74.1, 58.5, 100.0, 86.7], strict=True)),
        "baseline_2025": dict(zip(AXIS_ORDER, [87.6, 76.7, 58.8, 82.7, 55.4, 56.8, 99.7, 95.9], strict=True)),
        "overall": {"us": 73.4, "frontier_2026": 81.7, "baseline_2025": 74.8},
    },
}


REFKEY = REPO / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"


def load_gold() -> dict[str, dict]:
    """Criteria + reference answers, with the best available expected-ref key.

    ``build_gold`` seeds ``expected_refs`` from R386's minimal-gold set, which
    is ~1.5x finer than the evaluator's (92.4% sub-point against a measured
    ~60%) and therefore reads Ref. Strict as a pessimistic floor.  When the
    R388 grain-calibrated key is present it wins: it reproduces all EIGHT
    expected references the report prints, bare heads included, where R386's
    method scored 5/7 and could not produce a bare head at all.
    """
    if not GOLD.exists():
        raise SystemExit(f"missing reconstructed gold: {GOLD}\nrun evals.official.build_gold first")
    out = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            out[r["id"]] = r

    if REFKEY.exists():
        n = 0
        for line in REFKEY.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            k = json.loads(line)
            if k["id"] in out:
                out[k["id"]]["expected_refs"] = [] if k.get("unstable") else (k.get("expected") or [])
                n += 1
        print(f"expected-ref key: {REFKEY.name} (R388 grain-calibrated, {n} rows)")
    else:
        print("expected-ref key: R386 minimal-gold (over-fine; ref_strict is a FLOOR)")
    return out


def _key(
    qid: str,
    answer: str,
    judge_id: str = "legacy",
    *,
    turn: str = "graded",
) -> str:
    """Cache key scoped to answer *and* judge configuration.

    The legacy key omitted the judge identity, so a Qwen verdict could be
    replayed during an Opus/Sonnet run (or vice versa).  ``legacy`` remains an
    explicit default for small external utilities, but ``main`` always passes
    the resolved live identity.
    """
    digest = hashlib.sha256((answer or "").encode("utf-8")).hexdigest()[:16]
    judge_digest = hashlib.sha256(judge_id.encode("utf-8")).hexdigest()[:12]
    turn_suffix = f":turn={turn}" if turn != "graded" else ""
    return f"{qid}:{digest}:{judge_digest}{turn_suffix}"


def _row_cache_key(row: dict, judge_id: str) -> str:
    return _key(
        row["id"],
        row.get("answer") or "",
        judge_id,
        turn=str(row.get("answer_turn") or "graded"),
    )


def load_cache(cache_path: Path | None = None) -> dict[str, dict]:
    target = cache_path or CACHE
    if not target.exists():
        return {}
    out = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                r = json.loads(line)
                verdict = r.get("verdict") or {}
                if verdict.get("_judge_runs", 0) > 0:
                    out[r["key"]] = verdict
            except Exception:  # noqa: BLE001
                pass
    return out


def _judge_basis_sha(row: dict) -> str:
    """Hash of what a verdict depends on besides the answer and the judge.

    The criteria text AND the refs the judge prompt is grounded on, taken with
    the same expression ``judge._provisions_for`` receives.
    """
    grounding = row.get("expected_refs") or row.get("_fallback_refs") or []
    basis = "\n".join(str(c) for c in (row.get("criteria_text") or []))
    basis += "\n--\n" + "\n".join(str(r) for r in grounding)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def _criteria_match(v: dict, row: dict) -> bool:
    """R409 — a cached verdict is valid only for the criteria and grounding it judged.

    ``_key`` hashes the answer and the judge, not the criteria, so editing a
    row's criteria (same count) silently replayed the old verdicts, and a
    refkey-only correction (rg_082) changes the verbatim provisions the judge is
    grounded on while replaying them too. Verdicts carry ``_basis_sha``; lines
    without it are trusted only for gold rows never revised (``_revised`` unset).
    """
    sha = v.get("_basis_sha")
    if sha is not None:
        return sha == _judge_basis_sha(row)
    return not row.get("_revised")


#: R414 — above this fraction of judge-dead rows the arm has no judged axes at
#: all, so the run VOIDs instead of publishing a table. Below it the existing
#: R393/R408 banners are enough (a couple of transient failures are tolerable and
#: the rows are not cached).
JUDGE_VOID_FRAC = 0.2


def judge_void_reason(judged: list[dict], repeats: int) -> str:
    """R414 — why this arm's JUDGED axes must not be published ("" = publishable).

    MEASURED (R413). The wrapper's Claude-Max OAuth expired mid-run, so 39 of 39
    rows returned NO live judge run. ``score_arm`` printed

        JUDGE TRANSPORT DEGRADED: 39/39 rows (100%) returned NO live judge run
        and were scored all-False.

    and then printed the axis table anyway — `ans_correctness_loose` 3.76 %,
    `regulatory_tone` 2.5 % — which the paired gate parsed into a delta table.
    Detection without REFUSAL is what let a dead judge read as a result, so this
    returns a reason and the caller withholds the judged axes and exits 3. The
    reference axes are judge-free and are still written to the artifact.
    """
    if not judged:
        return ""
    n = len(judged)
    dead = [j for j in judged if not j.get("_judge_runs", 0)]
    if dead and len(dead) / n > JUDGE_VOID_FRAC:
        return (
            f"{len(dead)}/{n} rows ({len(dead) / n:.0%}) returned NO live judge "
            "run and would be scored all-False"
        )
    tone_dead = [
        j for j in judged if j.get("_judge_runs", 0) and not j.get("_tone_runs", 0)
    ]
    if tone_dead and len(tone_dead) / n > JUDGE_VOID_FRAC:
        return (
            f"{len(tone_dead)}/{n} rows ({len(tone_dead) / n:.0%}) returned "
            "criteria but NO live tone run"
        )
    return ""


def _verdict_complete(v: dict, repeats: int) -> bool:
    """R409 — a verdict is cacheable only when EVERY repetition was live.

    A dropped repetition used to be cached under an ``r=3`` identity and served
    as complete from then on (rg_084/rg_094/rg_099 in the R407 Qwen cache), and
    per-row checkpointing now persists it mid-run too. A partial row still
    scores the run that produced it and is re-judged on the next. Cache lines
    that predate tone accounting carry neither tone field and stay usable.
    """
    tone = v.get("_tone_runs")
    raw = v.get("_tone_runs_raw")
    if tone is None and raw is not None:
        tone = sum(1 for x in raw if x is not None)
    return v.get("_judge_runs", 0) >= repeats and (tone is None or tone >= repeats)


# Everything ``judge_row`` / ``judge_rows`` writes onto a row. The length-control
# pass must start from the GOLD, not from the first pass's verdicts: ``judge_row``
# replaces ``criteria`` with booleans, and a second pass handed those numbers the
# strings "True" / "False" as the criteria to grade the answer against.
_VERDICT_KEYS = (
    "criterion_remarks",
    "tone_ok",
    "tone_remark",
    "_judge_runs",
    "_criteria_rate_min",
    "_criteria_rate_max",
    "_judge_errors",
    "_judge_exception",
    "_corr_runs",
    "_tone_runs",
    "_tone_runs_raw",
)


def _length_controlled_rows(rows: list[dict]) -> list[dict]:
    """The same GOLD rows with each answer cut to the row's own reference length.

    Rows come back unjudged: the first pass's verdict fields are dropped and
    ``criteria`` is rebuilt from ``criteria_text``, the gold criterion strings the
    judge numbers into its prompt. Rows whose answer is already at or under the
    reference length keep their answer verbatim: the conciseness axis is
    one-sided, so there is no excess to remove, and cutting would only damage the
    answer. A row that has verdict booleans but no gold text to rebuild them from
    cannot be re-judged, and raises rather than grade against ``True``/``False``.
    """
    from evals.official.rubric import truncate_to_chars  # noqa: PLC0415

    out = []
    for r in rows:
        ref = r.get("reference_answer") or ""
        ans = r.get("answer") or ""
        capped = ans if (not ref or len(ans) <= len(ref)) else truncate_to_chars(ans, len(ref))
        fresh = {k: v for k, v in r.items() if k not in _VERDICT_KEYS}
        if "criteria_text" in r:
            fresh["criteria"] = list(r["criteria_text"])
        elif any(not isinstance(c, str) for c in r.get("criteria") or []):
            raise ValueError(
                f"row {r.get('id')!r} carries verdicts but no criteria_text; "
                "the length-control pass has no gold criteria to judge against"
            )
        fresh["answer"] = capped
        out.append(fresh)
    return out


def _graded_latency_ms(r: dict) -> float:
    """R409 — latency of the GRADED response, not of the whole exchange.

    Hard-mode checkpoints store ``latency_ms`` as turn 1 PLUS the pushback turn.
    The official Resp. Speed is per response: on Aug-25 the same system scored
    hard 85.7 against easy 87.6, where a two-turn sum would read about twice the
    easy latency. Checkpoints written before the per-turn fields keep the sum.
    """
    if "pushback_latency_ms" in r or "turn1_latency_ms" in r:
        # A pushback is sent iff turn 1 produced an answer. Score that turn even
        # when it failed, or a timed-out pushback would score at turn-1 speed.
        graded = r.get("pushback_latency_ms") if r.get("turn1_answer") else r.get("turn1_latency_ms")
        return float(graded or 0.0)
    return float(r.get("latency_ms") or 0.0)


def load_ckpt(path: Path, *, turn: str = "graded") -> list[dict]:
    """Load the requested answer turn without borrowing another turn's lineage."""
    if turn not in {"graded", "turn1", "pushback"}:
        raise ValueError(f"unknown answer turn: {turn!r}")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if turn == "graded":
            answer = r.get("pred_answer") or r.get("answer") or ""
            references = r.get("pred_refs") or r.get("references") or r.get("refs") or []
            latency_ms = _graded_latency_ms(r)
            provenance = r.get("provenance") or {}
        else:
            answer = r.get(f"{turn}_answer") or ""
            references = r.get(f"{turn}_refs") or []
            latency_ms = float(r.get(f"{turn}_latency_ms") or 0.0)
            provenance = r.get(f"{turn}_provenance") or {}
        rows.append(
            {
                "id": r.get("id"),
                "question": r.get("question") or "",
                "answer": answer,
                "references": references,
                "latency_s": latency_ms / 1000.0,
                "difficulty": r.get("difficulty") or r.get("difficulty_category"),
                "provenance": provenance,
                "answer_turn": turn,
            }
        )
    return rows


_DEGRADED_STAGE2_LEGS = frozenset({"deterministic", "fallback", "prior_turn"})
_INTENTIONAL_STAGE2_SKIPS = frozenset(
    {
        "stage2_skipped_simple_question_deterministic_ship",
        "stage2_skipped_curated_authoritative",
        "stage2_skipped_pure_definitional",
    }
)


def _stage2_row_rejection_reason(row: dict) -> str | None:
    """Fail closed unless this answer has evidence of a healthy or intentional serve.

    A primary-polished answer is scoreable. A deterministic Stage-2 skip is
    scoreable only when its exact, engine-emitted reason is recorded. Missing,
    contradictory, or unknown provenance is not evidence of a healthy answer
    and cannot contribute to a published board number.

    R461.5 — this gate decides a graded row's scope, so it reads the two
    provenance fields through the ONE home, ``evals.bench.row_provenance``
    (:func:`leg_label`, :func:`polish_flag`), never off the row. The comparison
    stays on the folded LABEL rather than on ``RowProvenance.kind``: the gate
    has always folded case, so a checkpoint spelling ``Fallback`` must still be
    refused, and ``kind`` would read an unknown spelling as ``unrecognised``.
    """
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        return "missing_provenance"
    served_by = leg_label(provenance)
    skip_reason = str(provenance.get("stage2_skip_reason") or "").strip()
    polish = polish_flag(provenance)

    if provenance.get("stage2_degraded_reason"):
        return f"stage2_degraded_reason={provenance['stage2_degraded_reason']}"
    if served_by in _DEGRADED_STAGE2_LEGS:
        return f"stage2_served_by={served_by}"
    if polish is True:
        if served_by != "primary":
            return f"unverified_stage2_served_by={served_by or 'missing'}"
        if skip_reason:
            return f"contradictory_stage2_skip_reason={skip_reason}"
        return None
    if polish is False and not served_by and skip_reason in _INTENTIONAL_STAGE2_SKIPS:
        return None
    if skip_reason and skip_reason not in _INTENTIONAL_STAGE2_SKIPS:
        return f"unrecognized_stage2_skip_reason={skip_reason}"
    if polish is False:
        return "stage2_polish=false"
    return "stage2_polish_unknown"


def _rejected_rows(rows: list[dict]) -> list[tuple[str, str]]:
    return [
        (str(row.get("id") or "<unknown>"), reason)
        for row in rows
        if (reason := _stage2_row_rejection_reason(row)) is not None
    ]


# A checkpoint written before provenance was recorded, a hand-built fixture, or a
# row captured before ``stage2_skip_reason`` existed carries NO evidence about
# whether its serve was healthy. That is not evidence of degradation, and R422
# pins "a ckpt without provenance is zero, not an error", so a graded run scores
# such rows as recorded and says so; otherwise every older checkpoint (a curated
# row shipped by design has ``stage2_polish`` False and no recorded reason) and
# every ``--resume`` of one would be refused. Only POSITIVE evidence of a
# degraded, contradictory or unrecognised serve refuses the run, and a per-turn
# run (whose capture always records provenance) refuses missing evidence too.
_NO_STAGE2_EVIDENCE = frozenset({"missing_provenance", "stage2_polish_unknown"})
_LEGACY_UNVERIFIABLE = frozenset({"stage2_polish=false", "unverified_stage2_served_by=missing"})


def _stage2_row_is_unverifiable(row: dict, reason: str) -> bool:
    """True when ``reason`` is the absence of evidence, not evidence of a problem."""
    if reason in _NO_STAGE2_EVIDENCE:
        return True
    provenance = row.get("provenance")
    return (
        reason in _LEGACY_UNVERIFIABLE
        and isinstance(provenance, dict)
        and "stage2_skip_reason" not in provenance  # captured before skip reasons existed
        and not leg_label(provenance)  # R461.5 — via the one home, never off the row
    )


def _partition_stage2_rows(
    rows: list[dict], *, lenient: bool
) -> tuple[list[tuple[str, str]], list[str]]:
    """Split rows into ``(refused, unverified)``; ``lenient`` tolerates missing evidence."""
    if not lenient:
        return _rejected_rows(rows), []
    refused: list[tuple[str, str]] = []
    unverified: list[str] = []
    for row in rows:
        reason = _stage2_row_rejection_reason(row)
        if reason is None:
            continue
        row_id = str(row.get("id") or "<unknown>")
        if _stage2_row_is_unverifiable(row, reason):
            unverified.append(row_id)
        else:
            refused.append((row_id, reason))
    return refused, unverified


def _atomic_write_new(path: Path, payload: dict) -> None:
    """Write a JSON artifact atomically, refusing to clobber any existing file."""
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"refusing to overwrite score artifact: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            raise SystemExit(f"refusing to overwrite score artifact: {path}") from None
    finally:
        temp.unlink(missing_ok=True)


def _score_output_path(label: str, mode: str, turn: str, *, void: bool = False) -> Path:
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", label)
    turn_suffix = "" if turn == "graded" else f"-{turn}"
    void_suffix = ".VOID" if void else ""
    return OUT_DIR / f"score-{clean}-{mode}{turn_suffix}{void_suffix}.json"


def _resolve_out(a: argparse.Namespace, *, void: bool = False) -> Path:
    out = Path(a.out) if a.out else _score_output_path(a.label, a.mode, a.turn, void=void)
    return out if out.is_absolute() else REPO / out


def _validate_turn_rows(rows: list[dict], *, mode: str, turn: str) -> None:
    if mode != "hard" and turn != "graded":
        raise SystemExit("--turn turn1/pushback requires --mode hard")
    if turn != "graded":
        missing = [
            str(row.get("id") or "<unknown>")
            for row in rows
            if not str(row.get("answer") or "").strip()
        ]
        if missing:
            raise SystemExit(
                f"--turn {turn} has no captured answer for rows: "
                f"{', '.join(missing[:12])}"
            )


def build_rows(ckpt_rows: list[dict], gold: dict[str, dict]) -> list[dict]:
    out = []
    for r in ckpt_rows:
        g = gold.get(r["id"])
        if not g:
            continue
        out.append(
            {
                **r,
                "criteria_text": g["criteria"],
                "criteria": g["criteria"],  # judge_row replaces this with booleans
                "reference_answer": g["reference_answer"],
                "expected_refs": g.get("expected_refs") or [],
                "criteria_unstable": g.get("criteria_unstable", False),
                "_revised": g.get("_revised"),
            }
        )
    return out


_DEEPEN_FLAGS = (
    "REGENOLD_REF_GRAIN_DEEPEN", "REGENOLD_REF_GRAIN_DEPTH", "REGENOLD_GRAIN_QUESTION_SUPPORT",
    "REGENOLD_GRAIN_DISCRIMINATING_SUPPORT", "REGENOLD_GRAIN_SUBJECT_HEAD",
)


def _reference_pass_provenance(deepen: bool, redeepened: int) -> dict:
    """R452c — which deepener re-scored the recorded references, if any."""
    import subprocess  # noqa: PLC0415

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[2]), timeout=10,
        ).stdout.strip() or None
    except Exception:  # noqa: BLE001 — provenance must not fail a scoring run
        commit = None
    return {
        "redeepen": bool(deepen),
        "rows_changed": int(redeepened),
        "commit": commit,
        "flags": {f: os.environ.get(f) for f in _DEEPEN_FLAGS if os.environ.get(f) is not None},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--mode", choices=["easy", "hard"], required=True)
    # R393 — default 1, not 4. The judge transport is normally the LOCAL Claude
    # Max wrapper (one process, one CLI); workers x repeats x 2 judges saturates
    # it and every failed row is scored all-False in silence. Measured on one
    # checkpoint: workers=4 read Overall 60.2, workers=1 read 82.4. Raise it only
    # against a genuinely concurrent endpoint (Bedrock, OpenRouter).
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--deepen", action="store_true", default=True, help="Apply R388 grain deepening")
    ap.add_argument("--no-deepen", dest="deepen", action="store_false")
    ap.add_argument("--cache-file", default=None, help="Custom judge cache JSONL path")
    ap.add_argument("--out", type=Path, default=None, help="Custom score artifact path (must not exist)")
    ap.add_argument(
        "--turn",
        choices=("graded", "turn1", "pushback"),
        default="graded",
        help="Answer in the checkpoint to judge; turn1/pushback require per-turn provenance",
    )
    ap.add_argument("--rejudge", action="store_true", default=False, help="Bypass cache and re-judge all rows")
    ap.add_argument("--judge-only", action="store_true", default=False, help="Write judge-cache entries without publishing a score artifact")
    ap.add_argument(
        "--judge-provider",
        # R419 — ``openrouter`` is a first-class transport: the local wrapper's
        # Claude Code session can be down while ``/health`` still answers, and
        # the Bedrock bearer token can be rejected, at which point the third
        # route is the only one that can judge. Labelling it correctly keeps the
        # judge identity (and therefore the cache) from conflating transports.
        choices=("wrapper", "bedrock", "openrouter"),
        default=os.getenv("R388_JUDGE_PROVIDER", "wrapper") or "wrapper",
        help="LLM judge transport (explicitly recorded in cache/output provenance)",
    )
    ap.add_argument(
        "--judge-model",
        default=os.getenv("R388_JUDGE_MODEL", "claude-sonnet-5"),
        help="Exact judge model or Bedrock inference-profile alias",
    )
    ap.add_argument(
        "--judge-split",
        action="store_true",
        default=False,
        help="Legacy two judge calls per repetition (correctness, then tone). "
        "Grouped is the default; use this to re-score an arm against a cache "
        "written before R408.",
    )
    ap.add_argument(
        "--length-control",
        action="store_true",
        default=False,
        help="R460 - also re-judge every answer CUT to its reference answer's "
        "length, and report those answer axes next to the raw ones. Separates a "
        "real correctness edge from one that lives in extra sentences (the "
        "length-controlled-debiasing idea applied to a criteria rubric). Not "
        "cached: this pass re-judges on every run.",
    )
    a = ap.parse_args()

    official_judge.configure_judge(
        provider=a.judge_provider,
        model=a.judge_model,
        grouped=False if a.judge_split else None,
    )
    judge_id = official_judge.judge_identity().rsplit(":r=", 1)[0] + f":r={a.repeats}"
    print(f"judge identity: {judge_id}")

    cache_target = Path(a.cache_file) if a.cache_file else CACHE

    if not a.judge_only:
        # Fail before the judge runs, not after it: the artifact write refuses to
        # clobber, and finding that out once the live calls are spent wastes them.
        for existing in (_resolve_out(a), _resolve_out(a, void=True)):
            if existing.exists():
                raise SystemExit(
                    f"refusing to overwrite score artifact: {existing} "
                    "(use a new --label or pass --out)"
                )

    gold = load_gold()
    ckpt_rows = load_ckpt(Path(a.ckpt), turn=a.turn)
    _validate_turn_rows(ckpt_rows, mode=a.mode, turn=a.turn)
    rejected, unverified = _partition_stage2_rows(ckpt_rows, lenient=a.turn == "graded")
    if unverified:
        print(
            f"WARNING: {len(unverified)} row(s) carry no evidence of a healthy Stage-2 serve "
            "(older capture); their serve leg is UNVERIFIED and they are scored as recorded: "
            f"{', '.join(unverified[:12])}" + ("..." if len(unverified) > 12 else "")
        )
    if rejected:
        details = ", ".join(f"{row_id} ({reason})" for row_id, reason in rejected[:12])
        more = f"; and {len(rejected) - 12} more" if len(rejected) > 12 else ""
        if not a.judge_only:
            raise SystemExit(
                "refusing to grade rows without evidence of healthy primary polish or "
                "a recognized intentional Stage-2 skip: "
                f"{details}{more}. Re-serve degraded rows on a healthy leg before scoring."
            )
        print(
            "judge-only comparative mode: scoring artifacts are disabled; "
            "Stage-2 provenance remains attached to every answer. "
            f"Non-primary rows: {details}{more}"
        )
    rows = build_rows(ckpt_rows, gold)
    if a.limit:
        rows = rows[: a.limit]
    if not rows:
        raise SystemExit("no rows matched the reconstructed gold")

    # R452c — the re-deepen rewrites recorded references with THIS checkout's
    # deepener and flags, so its provenance goes into the payload. A production
    # board already carries the shipped pass; score it with --no-deepen.
    redeepened = 0
    if a.deepen:
        from app.routes.regenold import _deepen_ref_grain  # noqa: PLC0415
        for r in rows:
            before = list(r["references"])
            r["references"] = _deepen_ref_grain(before, r.get("question") or "", r.get("answer") or "")
            redeepened += r["references"] != before

    cache = {} if a.rejudge else load_cache(cache_target)
    todo, cached = [], []
    for r in rows:
        v = cache.get(_row_cache_key(r, judge_id))
        if v and _verdict_complete(v, a.repeats) and _criteria_match(v, r) and len(v.get("criteria") or []) == len(r["criteria_text"]):
            cached.append({**r, **v})
        else:
            todo.append(r)
    print(f"{len(rows)} rows: {len(cached)} cached, {len(todo)} to judge (cache: {cache_target.name})")

    cache_target.parent.mkdir(parents=True, exist_ok=True)
    import threading as _threading  # noqa: PLC0415
    _cache_lock = _threading.Lock()
    _done_count = 0

    def _on_row_done(j: dict) -> None:
        nonlocal _done_count
        if _verdict_complete(j, a.repeats):
            with _cache_lock:
                _done_count += 1
                with cache_target.open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "key": _row_cache_key(j, judge_id),
                                "answer_turn": j.get("answer_turn") or "graded",
                                "judge_identity": judge_id,
                                "provenance": j.get("provenance"),
                                "verdict": {
                                    **{
                                        k: j[k]
                                        for k in (
                                            "criteria",
                                            "criterion_remarks",
                                            "tone_ok",
                                            "tone_remark",
                                            "_judge_runs",
                                            "_criteria_rate_min",
                                            "_criteria_rate_max",
                                            "_judge_errors",
                                            "_corr_runs",
                                            "_tone_runs_raw",
                                        )
                                        if k in j
                                    },
                                    "_basis_sha": _judge_basis_sha(j),
                                },
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                passed = sum(1 for c in (j.get("criteria") or []) if c)
                total = len(j.get("criteria") or [])
                print(
                    f"  [{_done_count:3d}/{len(todo)}] checkpointed {j['id']} "
                    f"(criteria: {passed}/{total}, tone: {'PASS' if j.get('tone_ok') else 'FAIL'})",
                    flush=True,
                )

    judged = official_judge.judge_rows(todo, workers=a.workers, repeats=a.repeats, on_row=_on_row_done) if todo else []

    # R393 — LOUD failure on a saturated judge transport.
    #
    # MEASURED. ``judge_row`` returns all-False criteria and ``tone_ok=False``
    # when every repeat of a row fails, and nothing downstream distinguishes
    # that from a genuinely wrong answer. Against the LOCAL Claude Max wrapper
    # -- one process wrapping one CLI -- the default ``--workers 4`` times
    # ``repeats`` times two judges is up to 24 concurrent calls, and it
    # saturates. Same arm, same checkpoint, sonnet-5, only ``--workers``
    # differing:
    #
    #     workers=4   ans_loose 46.0   ans_strict 38.2   tone  47.3   Overall 60.2
    #     workers=1   ans_loose 90.2   ans_strict 83.3   tone 100.0   Overall 82.4
    #
    # A tone of 47.3 is not a scorecard, it is a broken instrument -- and it
    # silently read as a 22-point Overall regression. Never let that be quiet.
    if judged:
        dead = [j for j in judged if not j.get("_judge_runs", 0)]
        if dead:
            frac = len(dead) / len(judged)
            print(
                f"\n{'!' * 72}\n"
                f"JUDGE TRANSPORT DEGRADED: {len(dead)}/{len(judged)} rows "
                f"({frac:.0%}) returned NO live judge run and were scored "
                f"all-False.\nThe answer and tone axes below are NOT a "
                f"measurement. Re-run with --workers 1.\n"
                f"first offenders: {[j['id'] for j in dead[:8]]}\n"
                f"{'!' * 72}\n"
            )

    # R408 — grouped verdicts parse correctness and tone out of ONE reply, so a
    # judge that drifts off the output contract can drop the tone object on every
    # row while the criteria still parse. Tone would then read as a quiet
    # all-False: the R393 failure shape, one field over. Say so, and do not cache
    # those rows, so a re-run re-judges them.
    if judged:
        tone_dead = [j for j in judged if j.get("_judge_runs", 0) and not j.get("_tone_runs", 0)]
        if tone_dead:
            print(
                f"\n{'!' * 72}\n"
                f"TONE JUDGEMENT MISSING: {len(tone_dead)}/{len(judged)} rows "
                f"returned criteria but NO live tone run and were scored "
                f"tone=False.\nThe tone axis below is NOT a measurement, and "
                f"these rows were not cached.\n"
                f"first offenders: {[j['id'] for j in tone_dead[:8]]}\n"
                f"{'!' * 72}\n"
            )
        partial = [j["id"] for j in judged if j.get("_judge_runs", 0) and not _verdict_complete(j, a.repeats)]
        if partial:
            print(
                f"\nPARTIAL VERDICTS: {len(partial)}/{len(judged)} rows lost at least one "
                f"repetition; scored on the live runs and NOT cached: {partial[:8]}\n"
            )


    all_rows = cached + judged
    by_id = {r["id"]: r for r in all_rows}
    ordered = [by_id[r["id"]] for r in rows if r["id"] in by_id]

    # R460 - LENGTH CONTROL (opt-in, not cached). Re-judge the answers cut to
    # their reference length, so a correctness edge that exists only because the
    # answer is longer cannot be read as knowledge. Both sets of axes ship.
    length_controlled: dict | None = None
    lc_void = ""
    if a.length_control:
        capped = _length_controlled_rows(ordered)
        cut = sum(
            1 for r, c in zip(ordered, capped, strict=True) if r["answer"] != c["answer"]
        )
        raw_res = score_rows(ordered)
        print(
            f"\nlength control: re-judging {len(capped)} rows with {cut} answers cut "
            f"to their reference length (not cached -- this pass re-judges each run)"
        )
        lc_judged = official_judge.judge_rows(
            capped, workers=a.workers, repeats=a.repeats
        )
        lc_dead = [j for j in lc_judged if not j.get("_judge_runs", 0)]
        lc_tone_dead = [
            j for j in lc_judged if j.get("_judge_runs", 0) and not j.get("_tone_runs", 0)
        ]
        lc_partial = [
            j["id"] for j in lc_judged
            if j.get("_judge_runs", 0) and not _verdict_complete(j, a.repeats)
        ]
        # R414 applies to this pass too: a degraded second pass is withheld, not
        # printed as a measurement. The raw pass is independently valid.
        lc_void = judge_void_reason(lc_judged, a.repeats)
        if lc_dead:
            print(
                f"  {'!' * 68}\n  LENGTH-CONTROL PASS DEGRADED: "
                f"{len(lc_dead)}/{len(lc_judged)} rows returned NO live judge run and "
                f"were scored all-False.\n  The controlled axes below are NOT a "
                f"measurement; re-run with --workers 1.\n  {'!' * 68}"
            )
        if lc_partial:
            print(
                f"  LENGTH-CONTROL PARTIAL VERDICTS: {len(lc_partial)}/{len(lc_judged)} rows "
                f"lost at least one repetition and were scored on the live runs: "
                f"{lc_partial[:8]}"
            )
        by_lc = {r["id"]: r for r in capped}
        for j in lc_judged:
            if j.get("id") in by_lc:
                by_lc[j["id"]].update(j)
        lc_order = [by_lc[r["id"]] for r in ordered if r["id"] in by_lc]
        length_controlled = {
            "answers_cut": cut,
            "cached": False,
            "n": len(lc_judged),
            "dead_rows": len(lc_dead),
            "tone_dead_rows": len(lc_tone_dead),
            "partial_rows": len(lc_partial),
        }
        if lc_void:
            length_controlled["void"] = lc_void
            length_controlled["axes"] = None
            print(f"  length-controlled axes WITHHELD (exit 3): {lc_void}")
        else:
            lc_res = score_rows(lc_order)
            length_controlled["axes"] = {
                k: lc_res[k]
                for k in (
                    "ans_correctness_loose",
                    "ans_correctness_strict",
                    "ans_conciseness",
                    "regulatory_tone",
                )
            }
            print("  length-controlled (answer cut to the reference length):")
            for k, v in length_controlled["axes"].items():
                print(f"    {k:<26}{v:>8.2f}   (raw {raw_res[k]:.2f})")

    void_reason = judge_void_reason(judged, a.repeats)
    if a.judge_only:
        incomplete = [
            str(row.get("id") or "<unknown>")
            for row in judged
            if not _verdict_complete(row, a.repeats)
        ]
        if void_reason or incomplete:
            print(
                f"judge-only run incomplete/void: {void_reason or 'incomplete live repetitions'}; "
                f"rows={incomplete[:12]}"
            )
            return 3
        if todo and len(judged) != len(todo):
            raise SystemExit(f"judge-only run returned {len(judged)}/{len(todo)} live rows")
        print(f"judge-only complete: {len(rows)} rows, cache={cache_target}")
        return 0
    if void_reason:
        # R414 — REFUSE, do not warn. The reference axes are computed from the
        # reference LISTS and never touch the judge, so they remain valid and are
        # the only numbers this artifact may carry.
        res = score_rows(ordered)
        ref_only = {k: v for k, v in res.items() if k.startswith("ref_")}
        clean = re.sub(r"[^a-zA-Z0-9_-]", "_", a.label)
        out = _resolve_out(a, void=True)
        _atomic_write_new(
            out,
            {
                "label": clean,
                "mode": a.mode,
                "turn": a.turn,
                "ckpt": str(a.ckpt),
                "judge_identity": judge_id,
                "judge_valid": False,
                "judge_void_reason": void_reason,
                "reference_axes": ref_only,
                "n": res.get("n"),
            },
        )
        print("\n" + "!" * 88)
        print("VOID JUDGE RUN — THE JUDGED AXES ARE WITHHELD (exit 3).")
        print(f"  reason: {void_reason}")
        print(f"  reference axes (judge-free, still valid): {ref_only}")
        print(f"  artifact: {out.name}")
        print("!" * 88)
        return 3

    res = score_rows(ordered)
    ref = OFFICIAL[a.mode]

    print()
    print("=" * 88)
    print(f"R388 reconstructed official rubric  |  arm={a.label}  mode={a.mode}  turn={a.turn}  n={res['n']}")
    print("=" * 88)
    hdr = f"{'axis':<26}{'THIS ARM':>10}{'us(off)':>10}{'2026 frontier':>15}{'gap->frontier':>15}"
    print(hdr)
    print("-" * 88)
    for k in AXIS_ORDER:
        gap = res[k] - ref["frontier_2026"][k]
        mark = "  BEATS" if gap >= 0 else ""
        print(
            f"{k:<26}{res[k]:>10.1f}{ref['us'][k]:>10.1f}"
            f"{ref['frontier_2026'][k]:>15.1f}{gap:>+15.1f}{mark}"
        )
    print("-" * 88)
    gap_o = res["overall"] - ref["overall"]["frontier_2026"]
    print(
        f"{'OVERALL (geo mean)':<26}{res['overall']:>10.1f}"
        f"{ref['overall']['us']:>10.1f}{ref['overall']['frontier_2026']:>15.1f}{gap_o:>+15.1f}"
        + ("  BEATS" if gap_o >= 0 else "")
    )
    print()

    # Min-Max Uncertainty Bounds across repetitions (per official Table 1 & Table 2)
    has_runs = any("_corr_runs" in r for r in ordered)
    if has_runs:
        per_run_scores = []
        valid_repeats = [len(r["_corr_runs"]) for r in ordered if r.get("_corr_runs")]
        repeats_count = min(valid_repeats) if valid_repeats else 0
        if repeats_count > 1:
            for run_idx in range(repeats_count):
                run_rows = []
                for r in ordered:
                    r_copy = dict(r)
                    if r.get("_corr_runs") and len(r["_corr_runs"]) > run_idx and r["_corr_runs"][run_idx] is not None:
                        r_copy["criteria"] = r["_corr_runs"][run_idx]
                    if r.get("_tone_runs_raw") and len(r["_tone_runs_raw"]) > run_idx and r["_tone_runs_raw"][run_idx] is not None:
                        r_copy["tone_ok"] = r["_tone_runs_raw"][run_idx]
                    run_rows.append(r_copy)
                per_run_scores.append(score_rows(run_rows))

            if per_run_scores:
                print("-" * 88)
                print(f"Min–Max Uncertainty Bounds across {repeats_count} Repetitions (Temperature {os.getenv('R388_JUDGE_TEMPERATURE', '0.1')})")
                print("-" * 88)
                print(f"{'Metric':<26}{'Range':>20}{'Spread':>15}")
                for axis_name, axis_label in [
                    ("ans_correctness_loose", "Ans Cor L"),
                    ("ans_correctness_strict", "Ans Cor S"),
                    ("regulatory_tone", "Regulatory Tone"),
                    ("overall", "Overall (geo mean)"),
                ]:
                    vals = [s[axis_name] for s in per_run_scores]
                    min_v, max_v = min(vals), max(vals)
                    spread = max_v - min_v
                    print(f"{axis_label:<26}{f'{min_v:.1f}% – {max_v:.1f}%':>20}{f'{spread:+.1f} pp':>15}")
                print("-" * 88)
                print()

    print("diagnostics:")
    for k in (
        "_ans_loose_macro",
        "_mean_answer_chars",
        "_mean_reference_chars",
        "_mean_refs_per_row",
        "_mean_expected_per_row",
        "_mean_latency_s",
        "n_ref_scored",
    ):
        print(f"  {k:<26}{res[k]}")
    unstable = sum(1 for r in ordered if r.get("criteria_unstable"))
    print(f"  {'gold rows flagged unstable':<26}{unstable}")
    print()
    print("NOTE: criteria and reference answers are RECONSTRUCTED, not the evaluator's.")
    print("      Compare ARMS under this instrument; do not read a number as an official score.")

    clean_label = re.sub(r"[^a-zA-Z0-9_-]", "_", a.label)
    out = _resolve_out(a)
    payload = {
        "label": clean_label,
        "mode": a.mode,
        "turn": a.turn,
        "ckpt": str(a.ckpt),
        "stage2_unverified_rows": unverified,
        "judge_identity": judge_id,
        "reference_pass": _reference_pass_provenance(a.deepen, redeepened),
        "axes": res,
        "length_controlled": length_controlled,
        "official_reference": ref,
        "rows": [
            {
                "id": r["id"],
                "answer_turn": r.get("answer_turn") or "graded",
                "provenance": r.get("provenance"),
                "question": r.get("question") or "",
                "answer": r.get("answer") or "",
                "criteria_text": r["criteria_text"],
                "criteria": r.get("criteria"),
                "criterion_remarks": r.get("criterion_remarks") or [],
                "n_criteria_passed": sum(1 for c in (r.get("criteria") or []) if c),
                "tone_ok": r.get("tone_ok"),
                "tone_remark": r.get("tone_remark") or "",
                "answer_chars": len(r.get("answer") or ""),
                "reference_chars": len(r.get("reference_answer") or ""),
                "refs": _clean(r.get("references") or []),
                "expected_refs": r.get("expected_refs") or [],
                "latency_s": r.get("latency_s"),
            }
            for r in ordered
        ],
    }
    _atomic_write_new(out, payload)
    print(f"wrote {out}")
    if lc_void:
        # The raw axes above are valid and on disk; the controlled ones were asked
        # for and withheld, so the run must not read as a success to its caller.
        print(f"length-control pass VOID, controlled axes withheld: {lc_void}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

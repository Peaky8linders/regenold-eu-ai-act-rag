"""R460 Tier-0 fix 2 + 3, runner side.

* ``_provenance`` parses the engine's ``stage2_usage`` note into the row, so a
  board carries prompt/completion counters AND the payload shape per dispatch.
* ``assert_healthy`` asks one liveness question before it throws a whole sample
  away: a tripped primary is now confirmed with a tiny PRIMARY call. Slow is not
  down. Gated by ``REGENOLD_BATCH_PROBE_BEFORE_ABORT`` (default ON) so the old
  behaviour remains reachable.

Idempotent, asserted single matches.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "evals" / "regenold" / "run_official_batch.py"
src = RUNNER.read_text(encoding="utf-8")

# ── 1. provenance ────────────────────────────────────────────────────────────
PROV_OLD = """        model = ""
        served_by = ""
        for note in trace.get("notes") or []:
            if not isinstance(note, str):
                continue
            if not model and "stage2_model=" in note:
                model = note.split("stage2_model=", 1)[1].split()[0]
            # R418 — the route now names the leg it shipped. Prefer this over
            # inferring from the model prefix: ``primary`` / ``fallback`` /
            # ``deterministic`` is what the cacheability guard actually read.
            if not served_by and "stage2_served_by=" in note:
                served_by = note.split("stage2_served_by=", 1)[1].split()[0]
        return {
            "stage2_polish": trace.get("stage2_polish"),
            "retrieval_path": trace.get("retrieval_path"),
            "engine_confidence": trace.get("engine_confidence"),
            "stage2_model": model,            "stage2_served_by": served_by,
        }
"""
PROV_NEW = """        model = ""
        served_by = ""
        # R460 — usage + PAYLOAD SHAPE per dispatch, written by the engine on the
        # primary leg (`stage2_usage in=.. out=.. system_chars=.. user_chars=..
        # turns=..`). The wrapper's counter is a character heuristic over the
        # user message (round(len(user)/4.0)), and the system stack is either
        # not counted or delivered per model, so a row is only interpretable
        # when the sizes ride along with the counts.
        usage: dict[str, int] = {}
        for note in trace.get("notes") or []:
            if not isinstance(note, str):
                continue
            if not model and "stage2_model=" in note:
                model = note.split("stage2_model=", 1)[1].split()[0]
            # R418 — the route now names the leg it shipped. Prefer this over
            # inferring from the model prefix: ``primary`` / ``fallback`` /
            # ``deterministic`` is what the cacheability guard actually read.
            if not served_by and "stage2_served_by=" in note:
                served_by = note.split("stage2_served_by=", 1)[1].split()[0]
            if not usage and "stage2_usage " in note:
                for token in note.split("stage2_usage ", 1)[1].split():
                    key, _, value = token.partition("=")
                    if key not in ("in", "out", "system_chars", "user_chars", "turns"):
                        continue
                    try:
                        usage[key] = int(value)
                    except ValueError:
                        continue
        out: dict[str, Any] = {
            "stage2_polish": trace.get("stage2_polish"),
            "retrieval_path": trace.get("retrieval_path"),
            "engine_confidence": trace.get("engine_confidence"),
            "stage2_model": model,            "stage2_served_by": served_by,
        }
        if usage:
            out.update(
                {
                    "stage2_tokens_in": usage.get("in"),
                    "stage2_tokens_out": usage.get("out"),
                    "stage2_system_chars": usage.get("system_chars"),
                    "stage2_user_chars": usage.get("user_chars"),
                    "stage2_history_turns": usage.get("turns"),
                }
            )
        return out
"""

# ── 2. probe before abort ────────────────────────────────────────────────────
PROBE_ANCHOR = "    def assert_healthy(payload: object | None = None) -> None:"
PROBE_NEW = '''    def _primary_liveness_probe() -> bool:
        """One tiny PRIMARY call: True when the tunnel still answers (R460).

        Deliberately NOT the memoized ``preflight``: a cached verdict is the one
        thing that cannot answer "is the leg reachable right now". A 30 s
        budget keeps the check bounded; on a genuinely dead tunnel it fails fast
        and the abort path is unchanged.
        """
        if os.getenv("REGENOLD_BATCH_PROBE_BEFORE_ABORT", "1").strip().lower() in (
            "0",
            "false",
            "no",
            "off",
        ):
            return False
        try:
            try:
                from app.engines._graph_rag_impl import effective_stage2_model

                model = str(effective_stage2_model() or "").strip()
            except Exception:  # noqa: BLE001 — the probe must never break the run
                model = ""
            provider = _wp.get_openai_wrapper_provider()
            resp = provider.complete(
                _wp.OpenAIWrapperRequest(
                    user="Reply with the single word: alive",
                    max_tokens=16,
                    timeout_seconds=30.0,
                    **({"model": model} if model else {}),
                )
            )
            return bool(resp is not None and not getattr(resp, "error", None))
        except Exception:  # noqa: BLE001 — a failed probe is a failed probe
            return False

'''

ABORT_OLD = """        raise RuntimeError(
            f"Stage-2 PRIMARY transport is down: {tripped}. The fallback leg is not "
            "answering either, so the rest of the sample would be graded on "
            f"deterministic Stage-1 drafts. Aborting.{note}"
        )
"""
ABORT_NEW = """        # R460 — SLOW is not DOWN. Measured 2026-09-30: five consecutive Sonnet
        # generations crossed the provider's 60 s read deadline and this guard
        # aborted a 28/37 run, while the tunnel was answering ~7 s calls minutes
        # later. Before throwing the sample away, spend one tiny PRIMARY call on
        # the question this guard actually cares about: is a Stage-2 leg still
        # reachable? A probe that answers means the failure was latency, so
        # reset the counter and keep drawing — every degraded row still records
        # its own leg (R423.1/R431), so the draw stays separable.
        if _primary_liveness_probe():
            transport.record_ok()
            print(
                "\\n[transport] PRIMARY tripped the failure guard ("
                f"{tripped}) but a direct probe answered: treating it as SLOW, "
                "not DOWN, and continuing. Raise "
                "REGENOLD_STAGE2_WRAPPER_TIMEOUT_S if this repeats."
            )
            return
        raise RuntimeError(
            f"Stage-2 PRIMARY transport is down: {tripped}. The fallback leg is not "
            "answering either, so the rest of the sample would be graded on "
            f"deterministic Stage-1 drafts. Aborting.{note}"
        )
"""

edits: list[tuple[str, str, str]] = [
    ("provenance usage", PROV_OLD, PROV_NEW),
    ("probe helper", PROBE_ANCHOR, PROBE_NEW + PROBE_ANCHOR),
    ("abort guard", ABORT_OLD, ABORT_NEW),
]
changed = 0
for label, old, new in edits:
    if new in src:
        print(f"already: {label}")
        continue
    assert src.count(old) == 1, (label, src.count(old))
    src = src.replace(old, new)
    changed += 1
    print(f"patched: {label}")
if changed:
    RUNNER.write_text(src, encoding="utf-8")
print(f"done: {changed} edit(s)")

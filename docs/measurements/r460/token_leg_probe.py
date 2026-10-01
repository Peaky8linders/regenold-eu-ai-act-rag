"""R460 — the TOKEN leg of the Sonnet-vs-Opus gate.

The live board checkpoints record ``latency_ms`` but no token usage: the engine
has ``prompt_tokens`` / ``completion_tokens`` on every wrapper response, yet
nothing aggregates or persists them. Rather than re-run two 37-row live boards
just to add a counter, this probe replays the RECORDED Stage-2 payloads —
``stage2-payloads.jsonl`` from ``capture_payloads.py``, i.e. the exact
``system`` + ``user`` strings the wrapper receives — against both candidate
models with byte-identical input and reads ``usage`` off each response.

Two questions, both measured at the seam:

  * MODEL SWAP (leg M). On the same prompt, does ``claude-sonnet-5`` return
    fewer output tokens / lower latency than ``claude-opus-5-5``? Prompt tokens
    are payload-determined and must match exactly between the two models; a
    mismatch means something other than the model changed.
  * SYSTEM DELIVERY (leg D). The ``persona`` variant substitutes the 61-char
    multi-turn persona for the 60 643-char full stack, which is exactly what
    the R411/R412 gate does for ``history_turn_count >= 2``. If the wrapper
    forwards the system message, ``prompt_tokens`` must fall by roughly
    60 582 / 3.7 ~= 16.4 k tokens; if it drops the system message (the R282
    ``claude_cli`` finding), the counts stay put and the whole static stack is
    free. This settles the delivery question the census left open, per model.

Usage (from the worktree root)::

    ../../.venv/Scripts/python.exe docs/measurements/r460/token_leg_probe.py \\
        --draws 4 --max-tokens 2048

Writes ``token-leg-probe.jsonl`` (one row per call) and ``token-leg-probe.json``
(the summary). No route, no judge, no board: this is a microbenchmark, and its
latency numbers are single calls, not the official Resp. Speed axis.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
PAYLOADS = OUT / "stage2-payloads.jsonl"

PERSONA = "You are an expert EU AI Act regulatory compliance specialist."

# The system string the provider would send when the full stack is swapped for
# the persona, i.e. the R411/R412 multi-turn branch in
# ``_openai_wrapper_complete_for_graph_rag``.
FULL = "full"
PERSONA_VARIANT = "persona"


def _load_draws(limit: int) -> list[dict]:
    if not PAYLOADS.exists():
        raise SystemExit(f"missing {PAYLOADS}; run capture_payloads.py first")
    rows = []
    for line in PAYLOADS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("user"):
            rows.append(row)
    rows.sort(key=lambda r: len(r.get("user") or ""), reverse=True)
    # Deterministic, size-spread draw: widest, median-ish, narrowest, plus the
    # next widest — enough to see a per-draw signal without a 30-minute probe.
    picks: list[dict] = []
    idx = [0, len(rows) // 2, len(rows) - 1, 1 % len(rows)]
    for i in idx:
        if 0 <= i < len(rows) and rows[i] not in picks:
            picks.append(rows[i])
    return picks[:limit]


def _system_for(row: dict, variant: str) -> str:
    return PERSONA if variant == PERSONA_VARIANT else str(row.get("system") or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draws", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument(
        "--models",
        default="claude-opus-5-5,claude-sonnet-5",
        help="comma-separated wrapper model ids",
    )
    ap.add_argument(
        "--persona-draws",
        type=int,
        default=1,
        help="how many draws also get the persona variant (delivery leg)",
    )
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--out", default="token-leg-probe.jsonl")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — cp1252 consoles
        pass

    # Load .env at import (app.config::_load_dotenv_once). Without this the
    # provider has no CF Access service token and every call 401s.
    import app.config  # noqa: F401, PLC0415
    from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
        OpenAIWrapperRequest,
        get_openai_wrapper_provider,
        resolve_wrapper_model,
    )

    draws = _load_draws(args.draws)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    print(f"probe draws: {len(draws)}  models: {models}")
    for row in draws:
        print(
            f"  {row.get('id')}: system={len(row.get('system') or '')} "
            f"user={len(row.get('user') or '')}"
        )

    provider = get_openai_wrapper_provider()
    wire = {m: resolve_wrapper_model(m) for m in models}
    print(f"wire models: {wire}")

    out_path = OUT / args.out
    records: list[dict] = []
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for di, row in enumerate(draws):
            variants = [FULL]
            if di < args.persona_draws:
                variants.append(PERSONA_VARIANT)
            for variant in variants:
                system = _system_for(row, variant)
                # Alternate model order per draw so warm-up can't favour one
                # model on every call.
                order = models if di % 2 == 0 else list(reversed(models))
                for model in order:
                    t0 = time.monotonic()
                    error = ""
                    try:
                        resp = provider.complete(
                            OpenAIWrapperRequest(
                                system=system,
                                user=str(row["user"]),
                                model=model,
                                max_tokens=args.max_tokens,
                                temperature=0.0,
                                timeout_seconds=args.timeout,
                            )
                        )
                        rec = {
                            "id": row.get("id"),
                            "model": model,
                            "wire_model": wire.get(model, model),
                            "variant": variant,
                            "system_chars": len(system),
                            "user_chars": len(str(row["user"])),
                            "prompt_tokens": int(resp.prompt_tokens or 0),
                            "completion_tokens": int(resp.completion_tokens or 0),
                            "elapsed_ms": int(resp.elapsed_ms or 0),
                            "finish_reason": resp.finish_reason,
                            "text_chars": len(resp.text or ""),
                            "error": resp.error or "",
                            "wall_ms": int((time.monotonic() - t0) * 1000),
                        }
                    except Exception as exc:  # noqa: BLE001 — a probe never dies
                        error = f"{type(exc).__name__}: {exc}"
                        rec = {
                            "id": row.get("id"),
                            "model": model,
                            "wire_model": wire.get(model, model),
                            "variant": variant,
                            "system_chars": len(system),
                            "user_chars": len(str(row["user"])),
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "elapsed_ms": 0,
                            "finish_reason": None,
                            "text_chars": 0,
                            "error": error,
                            "wall_ms": int((time.monotonic() - t0) * 1000),
                        }
                    records.append(rec)
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(
                        f"  [{row.get('id')} {variant} {model}] "
                        f"in={rec['prompt_tokens']} out={rec['completion_tokens']} "
                        f"lat={rec['elapsed_ms']}ms chars={rec['text_chars']} "
                        f"finish={rec['finish_reason']}"
                        + (f" ERROR {rec['error']}" if rec["error"] else ""),
                        flush=True,
                    )

    summary: dict[str, object] = {
        "draws": [r.get("id") for r in draws],
        "models": models,
        "max_tokens": args.max_tokens,
        "calls": len(records),
        "errors": sum(1 for r in records if r["error"]),
        "usage_available": any(r["prompt_tokens"] for r in records),
        "per_model": {},
        "delivery": {},
    }
    for model in models:
        for variant in (FULL, PERSONA_VARIANT):
            cells = [
                r
                for r in records
                if r["model"] == model and r["variant"] == variant and not r["error"]
            ]
            if not cells:
                continue
            summary["per_model"].setdefault(model, {})[variant] = {
                "n": len(cells),
                "prompt_tokens_median": statistics.median(
                    r["prompt_tokens"] for r in cells
                ),
                "completion_tokens_median": statistics.median(
                    r["completion_tokens"] for r in cells
                ),
                "elapsed_ms_median": statistics.median(r["elapsed_ms"] for r in cells),
                "text_chars_median": statistics.median(r["text_chars"] for r in cells),
            }

    # Delivery leg: per model, the prompt-token delta full - persona on the
    # SAME draw. A positive delta means the static stack reached the model.
    for model in models:
        by_draw: dict[str, dict[str, int]] = {}
        for r in records:
            if r["model"] != model or r["error"]:
                continue
            by_draw.setdefault(str(r["id"]), {})[r["variant"]] = r["prompt_tokens"]
        for draw_id, cell in by_draw.items():
            if FULL in cell and PERSONA_VARIANT in cell:
                full_system_chars = next(
                    (
                        r["system_chars"]
                        for r in records
                        if r["model"] == model
                        and r["id"] == draw_id
                        and r["variant"] == FULL
                    ),
                    0,
                )
                summary["delivery"][f"{model}:{draw_id}"] = {
                    "system_chars": full_system_chars,
                    "prompt_tokens_full": cell[FULL],
                    "prompt_tokens_persona": cell[PERSONA_VARIANT],
                    "delta": cell[FULL] - cell[PERSONA_VARIANT],
                }

    (OUT / "token-leg-probe.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not summary["usage_available"]:
        print(
            "WARNING: every prompt_tokens came back 0 — the wrapper reports no "
            "usage on this transport; the token leg needs a different source."
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

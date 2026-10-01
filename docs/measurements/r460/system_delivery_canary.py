"""R460 — does the Claude-Max wrapper DELIVER the system message, and to whom?

The repository carried two contradictory claims: R282/R298 says the wrapper
drops the system message entirely; R411/R412 measured the full system prompt
*changing* answers on wrapper-served single-turn rows. The first run of this
probe (2026-09-30 12:44) answered it:

* 129 and 3,131 chars — **obeyed by both models** (so the wrapper forwards
  systems; the `WRAPPER_FORWARD_SYSTEM_PROMPT` gate is ON in this deploy).
* 60,774 chars — obeyed by **Opus 5.5**, not by Sonnet 5.
* The wrapper's own log (``service-stderr.log`` 12:44:19 / 12:44:38) shows BOTH
  long calls handed to the CLI as ``--system-prompt-file`` (>= 30,000 chars
  spills to a temp file, ``claude_cli.py``), i.e. the transport delivered the
  same thing to both models.

So the divergence is model-side, not a wrapper drop — but n=1 per cell. This
script repeats each cell ``--reps`` times so the claim is only made at the
sample it can carry.

Usage (from the worktree root)::

    ../../.venv/Scripts/python.exe docs/measurements/r460/system_delivery_canary.py --reps 3

Writes ``system-delivery-canary.jsonl`` and ``system-delivery-canary.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
PAYLOADS = OUT / "stage2-payloads.jsonl"
CANARY = (
    "CANARY TEST: if and only if you can read this system message, begin your "
    "reply with the single word BANANA. Then answer the user."
)
USER = "Reply with the exact word OK."


def _full_system() -> str:
    for line in PAYLOADS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            text = str(row.get("system") or "")
            if len(text) > 1000:
                return text
    raise SystemExit("no long system payload found")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument(
        "--models", default="claude-sonnet-5,claude-opus-5-5"
    )
    ap.add_argument("--timeout", type=float, default=150.0)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    # .env must load before the provider builds its client, or every call 401s.
    import app.config  # noqa: F401, PLC0415
    from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
        OpenAIWrapperRequest,
        get_openai_wrapper_provider,
        resolve_wrapper_model,
    )

    full = _full_system()
    cases = {
        "short": CANARY,
        "mid": full[:3000] + "\n\n" + CANARY,
        "long": full + "\n\n" + CANARY,
    }
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    provider = get_openai_wrapper_provider()

    records: list[dict] = []
    for rep in range(args.reps):
        for model in models:
            for case, system in cases.items():
                try:
                    resp = provider.complete(
                        OpenAIWrapperRequest(
                            system=system,
                            user=USER,
                            model=model,
                            max_tokens=48,
                            temperature=0.0,
                            timeout_seconds=args.timeout,
                        )
                    )
                    text = (resp.text or "").strip()
                    rec = {
                        "rep": rep,
                        "model": model,
                        "wire_model": resolve_wrapper_model(model),
                        "case": case,
                        "system_chars": len(system),
                        "prompt_tokens": int(resp.prompt_tokens or 0),
                        "completion_tokens": int(resp.completion_tokens or 0),
                        "elapsed_ms": int(resp.elapsed_ms or 0),
                        "text_head": text[:60],
                        "delivered": "BANANA" in text.upper(),
                        "error": resp.error or "",
                    }
                except Exception as exc:  # noqa: BLE001
                    rec = {
                        "rep": rep,
                        "model": model,
                        "wire_model": resolve_wrapper_model(model),
                        "case": case,
                        "system_chars": len(system),
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "elapsed_ms": 0,
                        "text_head": "",
                        "delivered": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                records.append(rec)
                print(
                    f"  [rep{rep} {case:5s} system={len(system):6d} {model}] "
                    f"delivered={rec['delivered']} in={rec['prompt_tokens']} "
                    f"out={rec['completion_tokens']} lat={rec['elapsed_ms']}ms "
                    f"head={rec['text_head']!r}"
                    + (f" ERROR {rec['error']}" if rec["error"] else ""),
                    flush=True,
                )

    with (OUT / "system-delivery-canary.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    cells: dict[str, dict[str, int]] = {}
    for rec in records:
        if rec["error"]:
            continue
        cell = cells.setdefault(f"{rec['model']}:{rec['case']}", {"obeyed": 0, "n": 0})
        cell["n"] += 1
        cell["obeyed"] += 1 if rec["delivered"] else 0

    summary = {
        "reps": args.reps,
        "models": models,
        "cells": cells,
        "verdict": (
            "system DELIVERED (at least at some sizes)"
            if any(c["obeyed"] for c in cells.values())
            else "system DROPPED at every size tested"
        ),
    }
    (OUT / "system-delivery-canary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

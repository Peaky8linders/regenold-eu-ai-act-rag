"""R460 Tier-0 fix 1: the primary Stage-2 call gets its own deadline, and every
successful dispatch records usage + payload shape for the row writer.

Three edits, all asserted single-match and idempotent:

* ``app/engines/_graph_rag_impl.py`` — resolve
  ``REGENOLD_STAGE2_WRAPPER_TIMEOUT_S`` (default 150 s) and pass it on both
  wrapper Stage-2 calls; record ``stage2_usage in/out/system_chars/user_chars/
  turns`` after a successful primary call.
* ``app/routes/regenold.py`` — register the new knob in ``_engine_cache_key``
  (R263.2/R288.1: any knob that can change whether a cached answer is the one
  the config would produce must be keyed).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "app" / "engines" / "_graph_rag_impl.py"
ROUTE = ROOT / "app" / "routes" / "regenold.py"

engine = ENGINE.read_text(encoding="utf-8")
route = ROUTE.read_text(encoding="utf-8")

TIMEOUT_BLOCK = """    _s2pol.record_attempt(_s2pol.STAGE2_PRIMARY)
    # R460 — the wrapper Stage-2 call had NO explicit timeout, so it inherited
    # the provider singleton's 60 s default. Measured 2026-09-30: Opus's p100
    # turn was already 46.2 s, and five consecutive Sonnet generations crossed
    # 60 s, which tripped the official harness's five-failure guard and aborted
    # a 28/37 run. The Bedrock leg has had its own knob since R139
    # (REGENOLD_BEDROCK_STAGE2_TIMEOUT_S, 180 s); the primary gets the same.
    try:
        _stage2_wrapper_timeout = float(
            os.getenv("REGENOLD_STAGE2_WRAPPER_TIMEOUT_S", "150")
        )
    except (TypeError, ValueError):
        _stage2_wrapper_timeout = 150.0
    try:
        response = _wrapper_provider.complete(
            OpenAIWrapperRequest(
                system=wrapper_system,
                user=user,
                model=model,
                max_tokens=safe_max_tokens,
                temperature=temperature,
                extra_headers=extra_headers,
                timeout_seconds=_stage2_wrapper_timeout,
            )
        )
"""
TIMEOUT_OLD = """    _s2pol.record_attempt(_s2pol.STAGE2_PRIMARY)
    try:
        response = _wrapper_provider.complete(
            OpenAIWrapperRequest(
                system=wrapper_system,
                user=user,
                model=model,
                max_tokens=safe_max_tokens,
                temperature=temperature,
                extra_headers=extra_headers,
            )
        )
"""

RETRY_OLD = """            response = _wrapper_provider.complete(
                OpenAIWrapperRequest(
                    system=wrapper_system,
                    user=user,
                    model=model,
                    max_tokens=safe_max_tokens,
                    temperature=temperature,
                    extra_headers=extra_headers,
                )
            )
"""
RETRY_NEW = RETRY_OLD.replace(
    "                    extra_headers=extra_headers,\n",
    "                    extra_headers=extra_headers,\n"
    "                    timeout_seconds=_stage2_wrapper_timeout,\n",
)

USAGE_OLD = """        if bedrock_answer is not None:
            return bedrock_answer
        raise
    # R417 — the wrapper INTERMITTENTLY relays an interim/empty Claude-CLI
"""
USAGE_NEW = """        if bedrock_answer is not None:
            return bedrock_answer
        raise
    # R460 — per-dispatch usage + SHAPE on the channel the row writer reads.
    # The wrapper's usage is a character heuristic over the user message
    # (round(len(user)/4.0) to the digit); recording it next to the payload
    # sizes is what lets a board say WHICH shape was sent and what the
    # transport counted it as. run_official_batch._provenance parses this into
    # the checkpoint row; the seam probe stays the controlled cross-check.
    if not getattr(response, "error", None):
        try:
            from app.integrations.regenold.reasoning_trace import record_note
            record_note(
                "stage2_usage in=%d out=%d system_chars=%d user_chars=%d turns=%s"
                % (
                    int(getattr(response, "prompt_tokens", 0) or 0),
                    int(getattr(response, "completion_tokens", 0) or 0),
                    len(wrapper_system or ""),
                    len(user or ""),
                    history_turn_count,
                )
            )
        except Exception:  # noqa: BLE001 — trace is best-effort telemetry
            pass
    # R417 — the wrapper INTERMITTENTLY relays an interim/empty Claude-CLI
"""

route_old = '            "REGENOLD_STAGE2_ALLOW_NON_OPUS",\n'
route_new = (
    '            "REGENOLD_STAGE2_ALLOW_NON_OPUS",\n'
    '            "REGENOLD_STAGE2_WRAPPER_TIMEOUT_S",\n'
)

edits: list[tuple[str, str, str, str]] = [
    ("engine", "timeout block", TIMEOUT_OLD, TIMEOUT_BLOCK),
    ("engine", "degenerate retry timeout", RETRY_OLD, RETRY_NEW),
    ("engine", "usage note", USAGE_OLD, USAGE_NEW),
]
changed = 0
for _, label, old, new in edits:
    if new in engine:
        print(f"engine already has: {label}")
        continue
    assert engine.count(old) == 1, (label, engine.count(old))
    engine = engine.replace(old, new)
    changed += 1
    print(f"engine patched: {label}")
if changed:
    ENGINE.write_text(engine, encoding="utf-8")

if route_new in route:
    print("route cache key already registered")
else:
    assert route.count(route_old) == 1, ("route", route.count(route_old))
    ROUTE.write_text(route.replace(route_old, route_new), encoding="utf-8")
    print("route patched: cache key")

print(f"done: {changed} engine edit(s)")

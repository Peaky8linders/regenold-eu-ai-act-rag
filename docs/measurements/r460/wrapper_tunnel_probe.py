"""R460 — one-call liveness probe for the Claude-Max wrapper tunnel.

The wrapper host sits behind Cloudflare Access, so a bare ``curl /health``
returns 401 and proves nothing about whether Opus 5.5 can actually answer.
This probe spends ONE Stage-2-sized call (max_tokens=16, the harness's own
"reply with the single word: alive" preflight shape) on the exact model the
official harness will send, and reports transport + model + latency + usage.

Usage (from the worktree root, main-checkout venv):

    ../../.venv/Scripts/python.exe docs/measurements/r460/wrapper_tunnel_probe.py

Exit codes: 0 = the tunnel answered; 2 = it did not (degraded/error/empty).
Never prints secrets — only host names, model ids and byte counts.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

try:  # Windows console is cp1252; dev logs carry non-ASCII.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def main() -> int:
    try:
        from dotenv import load_dotenv  # noqa: PLC0415

        load_dotenv(REPO / ".env", override=False)
    except Exception as exc:  # noqa: BLE001
        print(f"dotenv load failed ({exc}); continuing on the ambient env")

    from app.config import settings  # noqa: PLC0415
    from app.engines._graph_rag_impl import effective_stage2_model  # noqa: PLC0415
    from app.llm import openai_wrapper_provider as wp  # noqa: PLC0415

    model = str(effective_stage2_model() or "").strip()
    wire_model = wp.resolve_wrapper_model(model) if model else ""
    provider = wp.get_openai_wrapper_provider()
    base = str(getattr(provider, "_base_url", "") or getattr(provider, "base_url", "") or "")
    print(f"wrapper_enabled      {wp.is_openai_wrapper_enabled()}")
    print(f"base_host            {wp._host_of(base) or '-'}")
    print(f"cf_access_headers    {sorted(wp._resolve_cf_access_headers(base).keys())}")
    print(f"effective_model      {model or '-'} (wire: {wire_model or '-'})")
    print(f"stage2_timeout_env   {__import__('os').getenv('REGENOLD_STAGE2_WRAPPER_TIMEOUT_S', '150')}")

    started = time.perf_counter()
    try:
        resp = provider.complete(
            wp.OpenAIWrapperRequest(
                user="Reply with the single word: alive",
                max_tokens=16,
                model=model or "claude-opus-5-5",
                timeout_seconds=150.0,
            )
        )
    except Exception as exc:  # noqa: BLE001 — a raise is a failed probe
        print(f"PROBE RAISED         {type(exc).__name__}: {str(exc)[:300]}")
        print(f"elapsed              {time.perf_counter() - started:.1f}s")
        return 2

    print(f"text                 {resp.text!r} ({len(resp.text or '')} chars)")
    print(f"error                {resp.error!r}")
    print(f"served_model         {resp.model!r}")
    print(f"finish_reason        {resp.finish_reason!r}")
    print(f"tokens               in={resp.prompt_tokens} out={resp.completion_tokens}")
    print(f"elapsed              {(resp.elapsed_ms or 0) / 1000.0:.1f}s "
          f"(client {time.perf_counter() - started:.1f}s)")
    ok = bool((resp.text or "").strip()) and not resp.error
    print("PROBE OK" if ok else "PROBE DEGRADED (no usable text / error field set)")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

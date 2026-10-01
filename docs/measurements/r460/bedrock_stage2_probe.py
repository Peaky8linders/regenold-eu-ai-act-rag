"""R460 - which Stage-2 model does the Bedrock credential actually serve?

Operator instruction for this gate: run the live arm and the judge on Bedrock,
because the Claude Max tunnel is low on quota. Bedrock then serves Stage-2 as
leg 2, and ``stage2_policy.stage2_fallback_model()`` warns that the tier default
is a DIFFERENT family (Qwen 3 32B / 235B) and that the newer Claude pins can
return AccessDenied on the current key vintage. So probe before drawing:

    REGENOLD_STAGE2_BEDROCK_MODEL=<first model that answers>

Tiny calls only (16 max tokens each), and it never touches the tunnel.

    ../../.venv/Scripts/python.exe docs/measurements/r460/bedrock_stage2_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

CANDIDATES = (
    "eu.anthropic.claude-opus-5",
    "eu.anthropic.claude-opus-4-8",
    "eu.anthropic.claude-sonnet-5",
    "qwen.qwen3-235b-a22b-2507-v1:0",
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        print("python-dotenv missing; relying on the process env")

    from app.llm.bedrock_client import (
        BedrockRequest,
        complete_with_fallback,
        is_bedrock_provider_enabled,
        resolve_bedrock_model,
    )

    print(f"bedrock enabled: {is_bedrock_provider_enabled()}")
    if not is_bedrock_provider_enabled():
        print("no Bedrock credential in .env: fix that before drawing")
        return 1

    for model in CANDIDATES:
        try:
            resolved = resolve_bedrock_model(model)
        except Exception as exc:  # noqa: BLE001 - a bad alias is a datum
            print(f"  {model:<38} resolve failed: {type(exc).__name__}: {exc}")
            continue
        try:
            resp = complete_with_fallback(
                BedrockRequest(
                    system="You are a terse assistant.",
                    user="Reply with the single word: alive",
                    model=resolved,
                    max_tokens=16,
                    temperature=0.0,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - an error is the finding
            print(f"  {model:<38} raised: {type(exc).__name__}: {str(exc)[:110]}")
            continue
        text = getattr(resp, "text", None) or getattr(resp, "error", None)
        ok = bool(getattr(resp, "text", None))
        served = getattr(resp, "model", "") or resolved
        print(f"  {model:<38} {'OK  ' if ok else 'FAIL'} served={served} "
              f"{(str(text) or '').strip()[:60]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

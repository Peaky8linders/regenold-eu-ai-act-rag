"""CLI Testing & Validation Script for AWS Bedrock Client with Qwen 3 235B / 32B models."""
from __future__ import annotations

import argparse
import json
import sys
import time

from dotenv import load_dotenv

from app.llm.bedrock_client import (
    BedrockProvider,
    BedrockRequest,
    check_connectivity_and_permissions,
    is_bedrock_provider_enabled,
    list_foundation_models,
    resolve_bedrock_model,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="AWS Bedrock LLM Client Deep-Dive Tester")
    parser.add_argument("--probe", action="store_true", help="Run connectivity & permission probe")
    parser.add_argument("--list-models", action="store_true", help="List foundation models in Bedrock catalog")
    parser.add_argument("--provider", type=str, default=None, help="Filter list-models by provider")
    parser.add_argument("--model", type=str, default="qwen3-32b", help="Target model ID or inference profile")
    parser.add_argument("--prompt", type=str, default="Explain Article 50 transparency requirements under the EU AI Act in 2 concise sentences.", help="User prompt to send")
    parser.add_argument("--system", type=str, default="You are an expert EU AI Act regulatory counsel.", help="System prompt")
    parser.add_argument("--max-tokens", type=int, default=500, help="Max completion tokens")
    parser.add_argument("--temperature", type=float, default=0.0, help="Temperature")
    parser.add_argument("--stream", action="store_true", help="Stream response tokens")
    args = parser.parse_args()

    print("=" * 70)
    print(" AWS Bedrock Client Live Test Harness")
    print("=" * 70)
    print(f"Provider Enabled: {is_bedrock_provider_enabled()}")
    print("-" * 70)

    if args.probe:
        resolved = resolve_bedrock_model(args.model)
        print(f"\nRunning probe check for model: {args.model} -> {resolved}")
        res = check_connectivity_and_permissions(model_id=resolved)
        print(json.dumps(res, indent=2))
        return 0 if res.get("status") == "ok" else 1

    if args.list_models:
        print(f"\nListing Foundation Models (Provider filter: {args.provider or 'ALL'})...")
        try:
            models = list_foundation_models(provider=args.provider)
            print(f"Found {len(models)} model(s):\n")
            for m in models:
                provider_name = m.get("providerName", "Unknown")
                model_name = m.get("modelName", "Unknown")
                model_id = m.get("modelId", "")
                modalities = ",".join(m.get("outputModalities", []))
                print(f"  * [{provider_name}] {model_name}")
                print(f"    ID: {model_id} | Modalities: {modalities}")
            return 0
        except Exception as exc:
            print(f"ERROR listing models: {exc}")
            return 1

    # Completion mode
    resolved_model = resolve_bedrock_model(args.model)
    print(f"\nInvoking Bedrock completion on model: {args.model} -> {resolved_model}")
    print(f"System: {args.system!r}")
    print(f"Prompt: {args.prompt!r}")
    print("-" * 70)

    provider = BedrockProvider()
    req = BedrockRequest(
        user=args.prompt,
        system=args.system,
        model=resolved_model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    if args.stream:
        print("STREAM OUTPUT: ", end="", flush=True)
        t0 = time.monotonic()
        for event in provider.stream(req):
            if event.get("type") == "text":
                print(event["text"], end="", flush=True)
            elif event.get("type") == "error":
                print(f"\n[STREAM ERROR: {event['error']}]")
            elif event.get("type") == "metadata":
                print(f"\n[USAGE: in={event['inputTokens']}, out={event['outputTokens']}]")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        print(f"\nStream complete in {elapsed_ms} ms.")
        return 0

    t0 = time.monotonic()
    res = provider.complete(req)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if res.error:
        print(f"\n[ERROR] Bedrock call failed: {res.error}")
        print(f"Elapsed: {elapsed_ms} ms")
        return 1

    print("\n[SUCCESS] Response received:")
    print(res.text)
    print("\nMETRICS:")
    print(f"  Model Used:    {res.model}")
    print(f"  Input Tokens:  {res.input_tokens}")
    print(f"  Output Tokens: {res.output_tokens}")
    print(f"  Elapsed Time:  {res.elapsed_ms} ms")
    print(f"  Finish Reason: {res.finish_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

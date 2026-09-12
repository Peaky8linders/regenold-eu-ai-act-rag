"""Bedrock-backed OpenAI-spec stand-in for the Claude-Max wrapper.

WHY THIS EXISTS
---------------
The r411 gate (`REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`) rewrites the system slot
**only on the wrapper leg** of Stage-2 (`_openai_wrapper_complete_for_graph_rag`).
The real wrapper is a local Claude Code CLI front end, and the Max subscription
window was exhausted, so every request returns:

    HTTP 500 {"error":{"message":"No response from Claude Code"}}

With the wrapper down the engine falls back to Bedrock, which always receives the
full `system` — so both arms are byte-identical and the A/B can only measure
sampling noise. That voided the gate twice.

This stub keeps the **leg under test** alive: it speaks the same OpenAI
`/v1/chat/completions` contract the wrapper does, but serves it from the
pre-authorised Bedrock transport. The engine still runs its real wrapper code
path, so `wrapper_system` (persona vs full) is genuinely exercised.

WHAT IT IS NOT
--------------
It is NOT the Claude Code CLI. Latency characteristics differ from production's
primary transport. It measures the *mechanism* (system-prompt content -> answer
length -> emitted references) on the transport production actually falls back to,
which is why it is worth running, but a result from here is a stand-in result and
must be labelled as one.

The per-request JSONL log (`--log`) is the point: it records the length of the
`system` slot the engine actually sent, so "the arms differed" is a measurement
rather than an assumption.

    .venv/Scripts/python.exe docs/measurements/r411/wrapper_stub_bedrock.py \
        --port 8077 --log /tmp/r411-stub.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Model families the harness may ask for -> a Bedrock inference-profile id this
# account is entitled to. Verified reachable 2026-09-12; the alias-table
# fallback (`eu.anthropic.claude-opus-4-8`) is 403 on this account, so the
# mapping is explicit rather than delegated.
_MODEL_MAP: tuple[tuple[str, str], ...] = (
    ("opus", "eu.anthropic.claude-opus-4-6-v1"),
    ("sonnet", "eu.anthropic.claude-sonnet-4-6"),
    ("haiku", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
)
_DEFAULT_BEDROCK_MODEL = "eu.anthropic.claude-sonnet-4-6"

# Bedrock Converse finish reasons -> the OpenAI vocabulary the engine reads.
# `length` in particular is load-bearing: the engine's truncation guard treats it
# as a soft failure, so mapping it wrong would hide truncation.
_FINISH_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "content_filtered": "content_filter",
    "guardrail_intervened": "content_filter",
    "tool_use": "tool_calls",
}

_LOG_LOCK = threading.Lock()


def _bedrock_model(requested: str) -> str:
    low = (requested or "").lower()
    for needle, bedrock_id in _MODEL_MAP:
        if needle in low:
            return bedrock_id
    return _DEFAULT_BEDROCK_MODEL


def _load_dotenv() -> None:
    """Pull AWS credentials out of the repo `.env` (parity with the harness)."""
    env = Path(__file__).resolve().parents[3] / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


class _Handler(BaseHTTPRequestHandler):
    server_version = "claude-code-openai-wrapper-stub"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        """Silence the default stderr access log; `--log` carries the record."""

    # ── helpers ────────────────────────────────────────────────────────────
    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, rec: dict[str, Any]) -> None:
        log_path = self.server.log_path  # type: ignore[attr-defined]
        if not log_path:
            return
        with _LOG_LOCK:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")

    # ── routes ─────────────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/health", ""):
            self._send(
                200,
                {
                    "status": "healthy",
                    "service": "claude-code-openai-wrapper",
                    "stub": "bedrock",
                },
            )
            return
        if self.path.rstrip("/") == "/v1/models":
            self._send(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": mid, "object": "model", "owned_by": "bedrock"}
                        for _n, mid in _MODEL_MAP
                    ],
                },
            )
            return
        self._send(404, {"detail": "Not Found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send(404, {"detail": "Not Found"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception as exc:  # noqa: BLE001 — a malformed body is the caller's bug
            self._send(400, {"error": {"message": f"bad request body: {exc!r}"}})
            return

        requested = str(body.get("model") or "")
        messages = body.get("messages") or []
        system = ""
        user = ""
        for msg in messages:
            role = str((msg or {}).get("role") or "")
            content = str((msg or {}).get("content") or "")
            if role == "system" and not system:
                system = content
            elif role == "user":
                user = content

        thinking_header = self.headers.get("X-Claude-Max-Thinking-Tokens") or ""
        try:
            thinking_budget = int(thinking_header)
        except ValueError:
            thinking_budget = 0

        bedrock_model = _bedrock_model(requested)
        max_tokens = int(body.get("max_tokens") or 1024)

        from app.llm.bedrock_client import BedrockProvider, BedrockRequest  # noqa: PLC0415

        start = time.perf_counter()
        error: str | None = None
        text = ""
        finish = None
        prompt_tokens = 0
        completion_tokens = 0
        try:
            resp = BedrockProvider().complete(
                BedrockRequest(
                    user=user,
                    system=system,
                    model=bedrock_model,
                    max_tokens=max_tokens,
                    temperature=float(body.get("temperature") or 0.0),
                    thinking_budget=thinking_budget,
                )
            )
            error = getattr(resp, "error", None)
            text = getattr(resp, "text", "") or ""
            prompt_tokens = int(getattr(resp, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(resp, "completion_tokens", 0) or 0)
            finish = _FINISH_MAP.get(str(getattr(resp, "finish_reason", "") or ""), "stop")
        except Exception as exc:  # noqa: BLE001 — mirror the wrapper's 500 contract
            error = f"stub_exception: {exc!r}"[:300]

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        self._record(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "requested_model": requested,
                "bedrock_model": bedrock_model,
                "system_len": len(system),
                "system_head": system[:80],
                "user_len": len(user),
                "max_tokens": max_tokens,
                "thinking_budget": thinking_budget,
                "ok": error is None,
                "error": error,
                "elapsed_ms": elapsed_ms,
            }
        )

        if error:
            # Same 500 shape the real wrapper uses on a CLI failure, so the
            # engine's outage/fallback path is exercised identically.
            self._send(
                500,
                {"error": {"message": "No response from Claude Code (stub)", "type": "api_error", "code": "500"}},
            )
            return

        self._send(
            200,
            {
                "id": f"chatcmpl-stub-{int(time.time() * 1000)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": bedrock_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": finish,
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            },
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--log", default="")
    args = ap.parse_args()

    _load_dotenv()

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    server.log_path = args.log  # type: ignore[attr-defined]
    print(f"bedrock wrapper stub listening on http://{args.host}:{args.port}/v1", flush=True)
    if args.log:
        print(f"per-request log -> {args.log}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

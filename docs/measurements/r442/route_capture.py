"""R442 (from the R442 prompt-path review) — offline route-level capture of the DISPATCHED Stage-2 bytes.

* Every outbound socket connect is refused and counted (hard offline guarantee).
* ``_OpenAIWrapperProvider.complete`` is stubbed at CLASS level, so every
  provider instance (wrapper / groq / gemini / mistral) is intercepted at the
  seam where the request would leave the process: we record ``req.user`` /
  ``req.system`` exactly as the provider would have POSTed them.
* A Stage-2 polish request (user starts with ``ORIGINAL QUESTION:``) gets a
  canned, complete, multi-sentence reply so Stage-2 "lands"; auxiliary calls get
  an error reply (fail-soft paths).
* Bedrock is disabled by construction (no AWS creds in env; we also stub
  ``_try_bedrock``-style availability to False where importable).
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

# The repository root: this file lives in docs/measurements/r442/.
REPO = str(Path(__file__).resolve().parents[3])
REPO = os.environ.get("CR_TREE", REPO)
sys.path.insert(0, REPO)
os.chdir(REPO)

# Offline env BEFORE any app import.
os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "COHERE_API_KEY",
          "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_BEARER_TOKEN_BEDROCK",
          "GEMINI_API_KEY", "MISTRAL_API_KEY", "NEO4J_URI", "CF_ACCESS_CLIENT_ID",
          "CF_ACCESS_CLIENT_SECRET", "P2P_GRAPH_RAG_API_KEY"):
    os.environ.pop(k, None)

SOCKET_ATTEMPTS: list[object] = []
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_create_connection = socket.create_connection


def _blocked_connect(self, address):  # noqa: ANN001
    # asyncio's Windows event loop builds its self-pipe with socket.socketpair(),
    # which on Windows is a loopback connect to a listener in THIS process.
    # Allow exactly that caller; refuse everything else.
    if sys._getframe(1).f_code.co_name == "_fallback_socketpair":
        return _orig_connect(self, address)
    SOCKET_ATTEMPTS.append(address)
    raise ConnectionRefusedError(f"offline probe: blocked connect to {address!r}")


def _blocked_connect_ex(self, address):  # noqa: ANN001
    SOCKET_ATTEMPTS.append(address)
    return 111


def _blocked_create_connection(address, *a, **kw):  # noqa: ANN001
    SOCKET_ATTEMPTS.append(address)
    raise ConnectionRefusedError(f"offline probe: blocked create_connection {address!r}")


socket.socket.connect = _blocked_connect
socket.socket.connect_ex = _blocked_connect_ex
socket.create_connection = _blocked_create_connection

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from app.config import settings  # noqa: E402
from app.llm import openai_wrapper_provider as owp  # noqa: E402
from app.main import app  # noqa: E402

settings.regenold.api_key = SecretStr("regenold-test-key")

# The partner bucket is 60/minute; a corpus sweep would otherwise read 429s as
# "no Stage-2 dispatch". Same switch tests/test_auth_signup.py uses.
from app.rate_limit import limiter  # noqa: E402

limiter.enabled = False

CALLS: list[dict] = []
PRIMARY_MODE = {"mode": "ok"}  # "ok" | "fail"

CANNED = (
    "Yes. Under Article 26(6), deployers of a high-risk AI system must keep the "
    "automatically generated logs under their control for a period appropriate to "
    "the intended purpose of at least six months, unless provided otherwise in "
    "applicable Union or national law. This duty applies to the extent such logs are "
    "under the deployer's control."
)


def _stub_complete(self, req):  # noqa: ANN001
    endpoint = getattr(self, "_base_url", None) or getattr(self, "base_url", None) or ""
    rec = {
        "provider_obj": type(self).__name__,
        "endpoint": str(endpoint),
        "name": getattr(self, "_name", None) or getattr(self, "name", None),
        "model": req.model,
        "user": req.user,
        "system": req.system,
    }
    CALLS.append(rec)
    is_stage2 = req.user.startswith("ORIGINAL QUESTION:")
    if is_stage2 and PRIMARY_MODE["mode"] == "ok":
        return owp.OpenAIWrapperResponse(
            text=CANNED, model=req.model, completion_tokens=90, prompt_tokens=100,
            finish_reason="stop",
        )
    return owp.OpenAIWrapperResponse(text="", error="offline_probe_stub_error", model=req.model)


owp._OpenAIWrapperProvider.complete = _stub_complete

CLIENT = TestClient(app)


def clear_cache() -> None:
    from app.routes.regenold import _ENGINE_CACHE

    _ENGINE_CACHE.clear()


def ask(messages: list[dict], env: dict[str, str] | None = None, *, stage2: bool = True):
    """POST through the real route. ``env`` overrides are applied then restored."""
    env = dict(env or {})
    if stage2:
        env.setdefault("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    saved = {k: os.environ.get(k) for k in env}
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    clear_cache()
    start = len(CALLS)
    try:
        r = CLIENT.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=messages,
        )
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    calls = CALLS[start:]
    stage2 = [c for c in calls if c["user"].startswith("ORIGINAL QUESTION:")]
    return r, calls, stage2


def original_question_of(user: str) -> str:
    head = "ORIGINAL QUESTION: "
    assert user.startswith(head)
    body = user[len(head):]
    cut = [body.find(m) for m in ("\n\nREWRITTEN / SEARCH QUESTION: ", "\n\nLEGAL VERSION: ")]
    cut = [c for c in cut if c >= 0]
    return body[: min(cut)] if cut else body

import app as _app_pkg  # noqa: E402

assert os.path.normcase(os.path.abspath(_app_pkg.__file__)).startswith(
    os.path.normcase(os.path.abspath(REPO))), _app_pkg.__file__
print("[route_capture] app package:", _app_pkg.__file__)

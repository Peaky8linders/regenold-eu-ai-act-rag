# Sonnet 4.6 via claude-code-openai-wrapper

This bundle ships an `openai_wrapper` provider so you can route the Graph-RAG engine through any OpenAI-compatible Chat Completions endpoint — including the local **claude-code-openai-wrapper** that exposes a Claude Max subscription as an OpenAI-spec server.

## When to use which provider

| Provider | Cost model | Setup | When |
|----------|------------|-------|------|
| **`openai_wrapper`** (Sonnet via Claude Max) | Flat monthly Max fee | Local wrapper at `127.0.0.1:8000` + interactive `/login` on the bundled CLI | Recommended for eval rounds without burning per-token API budget. |
| **`anthropic`** | Pay-as-you-go API | `P2P_GRAPH_RAG_API_KEY=sk-ant-...` env var | Reproducible token-usage telemetry; production deploys (Railway) where Claude Max's OAuth flow can't run. |
| **`cli`** | Free (deterministic fallback only) | Nothing — engine handles every step with rule-based logic | CI runs, offline reproductions. The `evals/regenold/runner.py` default. |

## Provider override

```bash
# Default — falls back to anthropic when unset.
unset P2P_GRAPH_RAG_PROVIDER

# Explicit openai_wrapper (the Sonnet path)
export P2P_GRAPH_RAG_PROVIDER=openai_wrapper
export OPENAI_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=dummy   # any non-empty string — Max subscription doesn't enforce it

# Explicit anthropic (per-token billing)
export P2P_GRAPH_RAG_PROVIDER=anthropic
export P2P_GRAPH_RAG_API_KEY=sk-ant-...

# Force deterministic fallback (no LLM calls)
export P2P_GRAPH_RAG_PROVIDER=cli
```

## One-time wrapper setup

The wrapper itself is an independent project (`RichardAtCT/claude-code-openai-wrapper`, MIT). It does NOT live in this repo. To stand it up:

1. Clone it next to this bundle:
   ```bash
   cd "D:\Claude Projects"
   git clone https://github.com/RichardAtCT/claude-code-openai-wrapper
   cd claude-code-openai-wrapper
   ```

2. Install Python 3.12 deps inside a fresh venv:
   ```cmd
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" pydantic python-dotenv httpx sse-starlette python-multipart claude-agent-sdk slowapi
   ```

3. Apply the `load_dotenv(override=True)` patch — without it the wrapper silently keeps a stale parent-shell env var instead of reading `.env`. See the upstream-targeted patch in [`docs/operations/claude-code-openai-wrapper.md`](https://github.com/Peaky8linders/legit-ai/blob/main/docs/operations/claude-code-openai-wrapper.md) of the parent `legit-ai` repo (the canonical operator runbook).

4. Author the wrapper's `.env`. Leaving `ANTHROPIC_API_KEY` blank routes through Claude Max:
   ```dotenv
   # Empty = subscription mode via the bundled Claude Code CLI
   ANTHROPIC_API_KEY=
   ```

5. Run the interactive login ONCE per machine:
   ```cmd
   D:\Claude Projects\claude-code-openai-wrapper\login.bat
   ```
   This launches the bundled `claude.exe` with the `/login` flow and writes the OAuth credentials the wrapper subprocess reads on each call.

6. Start the server:
   ```cmd
   D:\Claude Projects\claude-code-openai-wrapper\start.bat
   ```
   Binds to `127.0.0.1:8000` by design. Verify auth:
   ```bash
   curl -s http://127.0.0.1:8000/v1/auth/status | python -m json.tool
   ```
   Expected: `"claude_code_auth": {..., "status": {"valid": true, "errors": []}}`.

## Failure modes

### "Not logged in · Please run /login"

The wrapper responded HTTP 200 with the sentinel `"Not logged in · Please run /login"` instead of real model output. The bundled CLI's OAuth token has expired or wasn't seeded.

**Fix**: re-run `login.bat` interactively, complete the browser flow, then retry.

**Symptom in this bundle**: `app/llm/openai_wrapper_provider.py` detects the sentinel and returns `error="wrapper_not_logged_in: ..."` so the engine falls back to deterministic rather than shipping the sentinel as the answer.

### `[WinError 267] The directory name is invalid`

The wrapper's logs show `Failed to start Claude Code: [WinError 267] The directory name is invalid` when spawning the bundled `claude.exe`. The wrapper subprocess inherited a CWD that no longer exists (e.g. a deleted worktree).

**Fix**: restart the wrapper from a CWD that exists. The wrapper's `start.bat` resolves the wrapper directory at launch and chdirs into it, so closing and reopening the terminal is usually sufficient.

### `ConnectionError: All connection attempts failed`

The wrapper isn't running. Start it with `start.bat`.

## Running the round-5 eval with Sonnet

```bash
cd "D:\Claude Projects\regenold-eu-ai-act-rag"

# Activate the wrapper provider
export OPENAI_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=dummy
export P2P_GRAPH_RAG_PROVIDER=openai_wrapper

# Run all 251 scenarios with Sonnet 4.6
.venv/Scripts/python.exe -m evals.regenold.runner \
  --json evals/regenold_results_round5_anthropic_wrapper.json \
  --label "round5-anthropic-wrapper-251"
```

Expected runtime: ~25 minutes for 251 scenarios at ~6s per Sonnet call. The `--quiet` flag suppresses the per-scenario log but keeps the JSON snapshot.

## What the `openai_wrapper` provider does NOT do

* It does **not** stream responses — `stream=false` is hardcoded since the engine consumes the full message at once anyway.
* It does **not** retry on 429 / 5xx — single shot. Re-run the eval to retry transient failures. The wrapper itself handles Max subscription rate-limiting internally.
* It does **not** preserve session_id across calls — each scenario is independent, the wrapper allocates a fresh session per request.

For production Regenold traffic on Railway, the bundle routes everything through the Anthropic SDK via `P2P_GRAPH_RAG_API_KEY`. The wrapper is a developer-side convenience for A/B comparisons against Claude Max and is never on the production hot path.

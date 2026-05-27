# Railway production deploy & redeploy

Production URL: `https://regenold-eu-ai-act-rag-production.up.railway.app`

## Always redeploy policy

After every push to **`main`** that should reach production, a redeploy must run. This repo enforces that with:

1. **GitHub Actions** — `.github/workflows/railway-redeploy.yml` runs on every `push` to `main` (and manual `workflow_dispatch`).
2. **Agents** — `.cursor/rules/railway-redeploy.mdc` (`alwaysApply: true`).
3. **Manual fallback** — `scripts/redeploy-railway.ps1`.

Railway may also auto-deploy from GitHub when the service is connected; the workflow is an explicit **second hook** so merges are never “forgotten” without a deploy attempt.

## One-time GitHub setup

1. Create a Railway account token: [railway.com/account/tokens](https://railway.com/account/tokens)
2. In GitHub: **Settings → Secrets and variables → Actions**, add:

| Secret | Required | Purpose |
|--------|----------|---------|
| `RAILWAY_TOKEN` | **Yes** | API token for `railway redeploy` in CI |
| `RAILWAY_SERVICE_ID` | Recommended | Target service (if not using linked default) |
| `RAILWAY_ENVIRONMENT` | Optional | e.g. `production` |
| `RAILWAY_PROJECT_ID` | Optional | Disambiguate multi-project tokens |

Find service/project IDs in the Railway dashboard URL or via `npx @railway/cli status` after `railway link`.

Until `RAILWAY_TOKEN` is set, the workflow **fails on purpose** on each `main` push — configure secrets before relying on CI.

## Local redeploy (Windows)

```powershell
cd "D:\Claude Projects\regenold-eu-ai-act-rag"
$env:RAILWAY_TOKEN = "your-token"
# optional:
# $env:RAILWAY_SERVICE_ID = "..."
.\scripts\redeploy-railway.ps1
```

Without `RAILWAY_TOKEN`, run `npx @railway/cli login` once, `railway link` in the project, then:

```powershell
npx @railway/cli redeploy --yes --from-source
```

## Verify

```powershell
curl https://regenold-eu-ai-act-rag-production.up.railway.app/healthz
curl https://regenold-eu-ai-act-rag-production.up.railway.app/healthz/llm
curl https://regenold-eu-ai-act-rag-production.up.railway.app/healthz/graph
```

Boot log (Railway): `regenold.startup provider=...` unless `REGENOLD_SKIP_STARTUP_LOG=1`.

## `railway.toml`

Root `railway.toml` sets start command, healthcheck path, and default `[deploy.envs]`. **Dashboard service variables override** `[deploy.envs]` — see R80.2 notes in `CLAUDE.md`.

## RushDB graph (Neo4j replacement)

Set **`RUSHDB_AUTH_TOKEN`** or **`RUSHDB_API_KEY`** on the Railway service
(optional **`RUSHDB_BASE_URL`**). After redeploy, `/healthz/graph` should
report `"detail": "ok (rushdb)"` when RushDB is primary.

Full cutover steps, hybrid retrieval flag, and Neo4j sunset checklist:
[`RUSHDB_RUNBOOK.md`](RUSHDB_RUNBOOK.md).

Until RushDB auth is set, production continues to use **Neo4j** when
`NEO4J_URI` is configured (current production state).

## Anthropic / wrapper paths

For LLM provider env (Anthropic SDK vs Claude Max wrapper), see **Production deploy on Railway** in `CLAUDE.md` — redeploy does not change that; it only rolls the latest commit.

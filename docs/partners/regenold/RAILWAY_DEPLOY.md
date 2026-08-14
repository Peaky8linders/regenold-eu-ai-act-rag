# Railway production deploy & redeploy

Production URL: `https://regenold-eu-ai-act-rag-production.up.railway.app`

> ⚠ **THIS REPO IS NOT `api.antifragile-ai.net`.** That host serves a DIFFERENT
> application — *"EU AI Act – Path to Production API"*, 456 routes — which happens to
> expose its own `/api/v1/regenold/eu-ai-act/ask`. This standalone service has a handful
> of routes and owns `/app` (the Lexy UI) and `/lexy_avatar.png`, which the other host
> does not have. R330 verified `/app` on `api.antifragile-ai.net` returns 404 and briefly
> misread that as the UI failing to register here; on the real host above it is 200. This
> is the "TWO app copies" gotcha — **always confirm the host before diagnosing prod.**

## Redeploy: it is automatic, on push to `main`

**Railway's GitHub integration auto-deploys this service on every push to `main`.** That is
the mechanism. Merging a PR to `main` IS the deploy — verified R330: the merge of #339 was
live on the production URL with no manual step.

⚠ **The GitHub Actions hook described here until R330 no longer exists.**
`.github/workflows/railway-redeploy.yml` was **deleted in `bc63f86`** (R127) after failing
on every `main` push for eight seconds apiece — `RAILWAY_TOKEN` was never added as a repo
secret, so the job exited 1 at its own guard. There is no `.github/workflows/` directory in
this repo at all. Do not go looking for a workflow run to confirm a deploy; check the
production URL instead (see **Verify** below).

`.cursor/rules/railway-redeploy.mdc` describes the same dead hook.

## Optional: restore the explicit CI hook

Only needed if you want a second, explicit deploy attempt rather than relying on Railway's
own integration. It requires re-creating the workflow file AND adding the secret:

1. Create a Railway account token: [railway.com/account/tokens](https://railway.com/account/tokens)
2. In GitHub: **Settings → Secrets and variables → Actions**, add:

| Secret | Required | Purpose |
|--------|----------|---------|
| `RAILWAY_TOKEN` | **Yes** | API token for `railway redeploy` in CI |
| `RAILWAY_SERVICE_ID` | Recommended | Target service (if not using linked default) |
| `RAILWAY_ENVIRONMENT` | Optional | e.g. `production` |
| `RAILWAY_PROJECT_ID` | Optional | Disambiguate multi-project tokens |

Find service/project IDs in the Railway dashboard URL or via `npx @railway/cli status` after `railway link`.

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
curl https://regenold-eu-ai-act-rag-production.up.railway.app/app   # 200 = this service
```

**To confirm a specific commit is live, use `/healthz/llm` — it returns the deployed
`commit` SHA and `deployment_id` directly:**

```jsonc
{"version":"1.2.3","commit":"4bb56847e210","deployment_id":"f810e6d0-…",
 "provider":"openai_wrapper","llm_ok":true,"cf_access":{"client_id_set":true,…}}
```

Match `commit` against `git rev-parse HEAD`. That is the canonical check — no guessing
from behaviour. `/healthz/graph` additionally returns `seed_version`, `kb_version` and
live node counts, and `cf_access` above tells you whether the Cloudflare Access service
token reached the service (without it, production serves ZERO Claude Max).

Boot log (Railway): `regenold.startup provider=...` unless `REGENOLD_SKIP_STARTUP_LOG=1`.

## `railway.toml`

Root `railway.toml` sets start command and healthcheck path.

⚠ **`[deploy.envs]` is INERT and always has been** — Railway's `[deploy]` schema has no
`envs` key, so the block was never read (it is not "overridden by the dashboard", which was
the R80.2 reading). All runtime defaults must be **code defaults** in Python. Set real
values on the Railway service. See the R306 note in `railway.toml` itself.

## Graph backend (R98: Neo4j Aura is default again)

The durable graph backend reverted from RushDB to **Neo4j Aura** in R98
(2026-05-30) — RushDB hit its free-trial limits. The selector is
**`REGENOLD_GRAPH_BACKEND`** (default `neo4j`, set in `railway.toml`):

* `neo4j` (default) — uses the Neo4j Aura instance. Set on the Railway
  service: **`NEO4J_URI`**, **`NEO4J_PASSWORD`**, and
  **`NEO4J_USERNAME`** *or* **`NEO4J_USER`** (the client reads either;
  Aura's default username is `neo4j`). Boot auto-seed + `/healthz/graph`
  use the Neo4j path. Every RushDB surface is **inert even if
  `RUSHDB_AUTH_TOKEN` is still set**.
* `rushdb` — re-enables the RushDB dual-path. Requires BOTH
  `REGENOLD_GRAPH_BACKEND=rushdb` AND `RUSHDB_AUTH_TOKEN` (or
  `RUSHDB_API_KEY`; optional `RUSHDB_BASE_URL`). Then `/healthz/graph`
  reports `"detail": "ok (rushdb)"`.

Legacy RushDB cutover steps + hybrid-retrieval flag:
[`RUSHDB_RUNBOOK.md`](RUSHDB_RUNBOOK.md).

## Anthropic / wrapper paths

For LLM provider env (Anthropic SDK vs Claude Max wrapper), see **Production deploy on Railway** in `CLAUDE.md` — redeploy does not change that; it only rolls the latest commit.

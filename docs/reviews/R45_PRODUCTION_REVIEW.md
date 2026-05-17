# R45 Production-Deploy + Observability Review

**Scope**: Railway deploy config, observability surface, env-var handling,
wire-contract hardening, boot-time gotchas. Companion review streams:
**B** (dead code + drift), **C** (test coverage + data-integrity), **D**
(performance + cold-start tails).

**Method**: read-only audit of `railway.toml`, `requirements.txt`, `Procfile`,
`app/main.py` (startup hooks + healthz handlers), `app/rate_limit.py`,
`app/config.py`, `app/integrations/regenold/{auth,models}.py`,
`app/evidence/store.py`, `app/graph/{client,config}.py`,
`app/routes/regenold.py` (route + cache key + audit write), the env-var
grep across the codebase, and the R43 security review for known gaps.

10 findings — 2 P0, 4 P1, 3 P2, 1 P3.

---

## A1 — Endpoint requires `P2P_REGENOLD_API_KEY`; docs / auth-module promise anonymous tier

**Severity**: P0
**Category**: wire-guard
**Files**:
- `app/routes/regenold.py:1232` (`api_key: str = Depends(require_regenold_api_key)`)
- `app/integrations/regenold/auth.py:27-63` (`require_regenold_api_key` = STRICT 503/401/403)
- `app/integrations/regenold/auth.py:66-107` (`optional_regenold_api_key` — UNUSED)
- `.env.example:1-4` (`P2P_REGENOLD_API_KEY=` "optional — anonymous tier works without one")
- `app/routes/regenold.py:14-16, 318-330` (docstring + rate-limit code paths still assume both tiers)

**Finding**: The actual wire is **fail-closed**: any deploy that doesn't
set `P2P_REGENOLD_API_KEY` returns HTTP 503
`regenold_not_configured` on every request, including `/api/v1/regenold/eu-ai-act/ask`.
A correctly-keyed caller works; an unkeyed Railway deploy is fully dead.
The auth module ships an `optional_regenold_api_key` dep, the rate-limit
infrastructure has working anonymous + privileged buckets
(`_RATE_KEY_PREFIX_ANON` / `_RATE_KEY_PREFIX_AUTHED`), and the audit chain
already distinguishes `tenant_id="partner:regenold"` from `"public:regenold-anon"`
— but the route wiring uses the strict dep. `.env.example` line 1 even
documents the key as **optional**, which is now false at the route layer.

This contradicts the "competition deliverable, route must be reachable
WITHOUT a partner key" comment in `auth.py:72-73`. A judge hitting the
Railway URL without a key gets a 503; an evaluator reading the README will
not know to request a key.

**Repro / evidence**:
```python
# auth.py line 27 (require_regenold_api_key)
if not _configured_key():
    raise HTTPException(status_code=503, detail={"code": "regenold_not_configured", ...})
if not api_key:
    raise HTTPException(status_code=401, ...)

# regenold.py line 1232 — route uses the STRICT dep
api_key: str = Depends(require_regenold_api_key),
```
On a Railway deploy with `P2P_REGENOLD_API_KEY` unset, every request to
`POST /api/v1/regenold/eu-ai-act/ask` returns 503. There is no test
fixture in this repo that exercises the route WITHOUT setting the env
var, so this regression would not be caught by CI.

**Suggested fix**: Decide and align. Either (a) swap the dep at
`regenold.py:1232` to `Depends(optional_regenold_api_key)` and adjust the
hardcoded `"tier": "partner"` audit-payload string to `"partner"` /
`"public"` based on the returned key (matching the rate-limit buckets that
already split the two tiers), OR (b) update `auth.py:72-73` docstring,
`.env.example:1-4`, the README, and the route docstring at lines 14-16 to
make "API key required" the explicit contract and add `P2P_REGENOLD_API_KEY`
to `railway.toml`'s `[deploy.envs]` so an unkeyed deploy fails loud at boot
rather than silently 503-ing every wire call. Recommended: (a), because the
benchmark / evaluator harness can't be retrofitted with a partner key.

---

## A2 — In-memory rate-limit storage doubles effective limit per worker

**Severity**: P0
**Category**: deploy-config
**Files**:
- `app/config.py:41` (`storage_uri: str = "memory://"`)
- `app/rate_limit.py:19-21` (limiter wired with `storage_uri`)
- `railway.toml:2` (`--workers 2`)
- `.env.example` (no `P2P_RATELIMIT_STORAGE_URI` documented)

**Finding**: slowapi's `memory://` backend keeps counters in-process. With
`--workers 2`, an attacker hitting the anonymous bucket bypasses half the
rate limit by virtue of round-robin worker selection. The documented
budget is 30/min anonymous + 60/min privileged; the effective ceiling is
~60/min anonymous + ~120/min privileged. Doubles cleanly to 4× on
`--workers 4`. The slowapi docs explicitly warn against `memory://` in
multi-worker deployments — counters do not synchronise across uvicorn
workers.

This is also a correctness issue for partner SLA: a partner key configured
for 60/min effectively gets 120/min, which the audit chain reports as
`tier=partner` rows with no rate-limit-bucket metadata. Forensic
reconstruction of "did the partner overflow their budget?" is broken.

**Repro / evidence**: Two workers + slowapi `memory://` is well-documented
elsewhere as a deployment foot-gun (see
https://slowapi.readthedocs.io/en/latest/#storage-backends). No mitigations
in this repo: no `P2P_RATELIMIT_STORAGE_URI` env var in `.env.example`,
`railway.toml`, or `README.md`.

**Suggested fix**: Add a Redis (or Memcached) storage backend before
production. Railway has a free Redis add-on; once provisioned, set
`P2P_RATELIMIT_STORAGE_URI=redis://default:<pw>@<host>:<port>` so all
workers share counters. Alternatively run a single worker
(`--workers 1` in `railway.toml` + `Procfile` + `railpack.json`) — but
that costs throughput. Add a startup-time WARNING when
`memory://` is the active backend AND workers > 1 (detectable via
`WEB_CONCURRENCY` env or process inspection); operators currently get no
signal.

---

## A3 — `_run_auto_seed_in_thread` swallows Postgres-down as "another worker is seeding"

**Severity**: P1
**Category**: boot-time
**Files**:
- `app/main.py:215-275` (`_acquire_postgres_advisory_lock`)
- `app/main.py:312-326` (callsite + the misleading skip path)

**Finding**: When `DATABASE_URL=postgres://...` is set but Postgres is
**unreachable** at boot (network partition, Postgres crash, Railway
service warming up), `_acquire_postgres_advisory_lock` returns `None`
because `psycopg.connect(...)` raised. The caller at line 318-326 then
checks `lock_handle is None AND DATABASE_URL startswith("postgres")` and
logs **`auto_seed_skipped reason=advisory_lock_held (another worker is
seeding)`** — an actively misleading message. No seed runs, Neo4j stays
empty, and operators chase the wrong root cause.

Same bug applies symmetrically when `psycopg` import fails (line 243-244):
caller can't tell "psycopg missing" from "Postgres unreachable" from
"another worker holds the lock".

The connect failure already logs at DEBUG (`logger.debug("auto-seed
advisory-lock connect failed: %s", exc)`) — invisible to operators on
LOG_LEVEL=INFO (the default per `.env.example:46`).

**Repro / evidence**: Synthesise by setting `DATABASE_URL=postgres://nonexistent:5432/x`
and `NEO4J_URI=bolt://localhost:7687` on a deploy. The boot log will read
`auto_seed_skipped reason=advisory_lock_held (another worker is seeding)`
even though no other worker exists. The seed never runs; `/healthz/graph`
reports `seed_version=""`.

**Suggested fix**: Distinguish the three failure modes in
`_acquire_postgres_advisory_lock`'s return. Promote the connect-failure
log from DEBUG to WARNING, and make the caller log a distinct reason for
each: `advisory_lock_held` (lock contended — the original meaning),
`advisory_lock_unavailable` (Postgres down — operator action needed),
`advisory_lock_driver_missing` (psycopg not installed). Without this, an
operator triaging "why is Neo4j empty on Railway?" reads "another worker
is seeding", waits ~30 minutes, then loops back confused.

---

## A4 — Neo4j auto-seed startup hook blocks uvicorn boot on slow Neo4j

**Severity**: P1
**Category**: boot-time
**Files**:
- `app/main.py:443-446` (synchronous `client.execute_read` in startup hook BEFORE thread spawn)
- `app/graph/config.py:37` (`connection_timeout: float = 5.0`)
- `app/graph/config.py:39-40` (`max_retries: int = 2`, `retry_backoff_seconds: float = 0.5`)
- `app/graph/client.py:148-167` (retry path)
- `railway.toml:4` (`healthcheckTimeout = 30`)

**Finding**: The boot path calls `client.execute_read(...)` synchronously
on the main thread BEFORE spawning the daemon seed thread, to read
`KBMetadata.seed_version` and decide whether to seed. This is the
"check, then conditionally seed" optimisation — but the check runs
inline. Neo4j Aura free-tier can take 2-3s for a cold-start session;
`ServiceUnavailable` retries linearly with `0.5s × (attempt+1)` backoff
for `max_retries=2`, so a fully-down Neo4j stalls boot for up to
`5s (connection_timeout) × 3 attempts + 0.5s + 1.0s + 1.5s = ~18s` before
falling through. On Railway's 30-second `healthcheckTimeout`, the first
`/healthz` probe lands during the stall and the deploy is marked
unhealthy if Neo4j is genuinely down at boot.

In addition, `_log_llm_provider_status` (line 122-175) ALSO probes Neo4j
synchronously via `_gc.health_check()` + `_gc.get_stats()` + `_resolve_gds_status`
during the boot LOG line. So the boot makes 3+ blocking Neo4j round-trips
before the FastAPI startup completes.

**Repro / evidence**: Synthesise `NEO4J_URI=bolt://10.255.255.1:7687`
(unroutable IP) on a boot. Uvicorn startup blocks for ~18s. With
`--workers 2` × 18s startup × 2 cold workers under a load-balancer, the
30s healthcheck flaps.

**Suggested fix**: Move the seed_version check + LLM-status Neo4j probes
into the daemon thread alongside the seed call itself. The boot path
should only log `auto_seed_check action=seed-started` (or skip), then
spawn the thread. The thread does the read + decide + seed sequence,
swallowing all timeouts on its own time. Bonus: the same daemon-thread
move fixes the symmetric problem in `_log_llm_provider_status` (every
Neo4j-bound boot log line is currently blocking).

---

## A5 — `NEO4J_URI` credentials leaked through driver-init and partial-seed exception logs

**Severity**: P1
**Category**: observability
**Files**:
- `app/graph/client.py:103` (`logger.info("Neo4j driver initialized: %s", settings.uri)`)
- `scripts/seed_neo4j_kb.py:776-783` (`logger.error("partial_seed_state ... error=%s", e)`)
- `app/graph/client.py:107` (`logger.warning("Neo4j connection failed: %s — graph features disabled", exc)`)

**Finding**: Open from R43 S3 — **still not fixed in current code**. The
Neo4j driver doesn't redact credentials from its exception messages, and
operators sometimes paste `NEO4J_URI=bolt+s://neo4j:password@host:7687`
(URI-embedded credentials) instead of the recommended split form. Any of
the three log calls above will print the password verbatim to the
Railway log stream:

- `client.py:103` always prints the full URI on every successful init.
- `client.py:107` prints `exc` which often quotes the URI.
- `seed_neo4j_kb.py:776` prints the seeder exception which is typically
  a `neo4j.exceptions.AuthenticationRateLimit` / `ServiceUnavailable`
  with the URI in the message.

The CLAUDE.md runbook prescribes the safe form, but the safe form is not
**enforced** anywhere — the deploy accepts the credential-embedded URI
silently.

**Repro / evidence**:
```python
from neo4j.exceptions import ServiceUnavailable
e = ServiceUnavailable('Failed to read from bolt://neo4j:secretpw@host:7687: connection refused')
str(e)
# → 'Failed to read from bolt://neo4j:secretpw@host:7687: connection refused'
```
With LOG_LEVEL=INFO (the deploy default), `logger.info("Neo4j driver
initialized: %s", "bolt+s://neo4j:secretpw@host:7687")` ships the password
to stdout, which Railway captures into its log stream and forwards to any
log aggregator (Datadog, Logtail, Better Stack).

**Suggested fix**: Centralise URI redaction in
`app/graph/client.py`. Add `def _redact_uri(uri: str) -> str` that strips
the `user:pass@` userinfo segment (`re.sub(r'://([^:/?#]+):([^@/?#]+)@', '://***:***@', uri)`),
and use it at every log site that touches `settings.uri` or a Neo4j
exception. Add a boot-time refusal in `_should_activate` when `NEO4J_URI`
contains `@` between scheme and host — fail-loud at boot is better than
silently logging credentials on every deploy. R43 S3 also recommended `error=%r`
+ truncation to 80 chars in `partial_seed_state`; combine both passes.

---

## A6 — Audit-chain failures silenced at DEBUG; operators can't see Postgres outage

**Severity**: P1
**Category**: observability
**Files**:
- `app/routes/regenold.py:1011-1012` (refusal-branch audit write — `logger.debug` on failure)
- `app/routes/regenold.py:2025-2026` (main-branch audit write — `logger.debug` on failure)

**Finding**: When `DATABASE_URL` is set and points at a Postgres that
becomes unavailable mid-request (network blip, max-connections exhaustion,
Postgres crash), every audit-chain write fails. The `try/except` correctly
prevents a 500 — the route continues to serve answers — but the failure
log is at DEBUG. With `LOG_LEVEL=INFO` (the deploy default in
`.env.example:46`), operators see **zero** signal that the durable audit
chain is broken. Audit compliance under EU AI Act Art. 12(1) requires
demonstrable persistence; silently losing every audit write to Postgres
while the route reports HTTP 200 is the worst-case operational failure
mode for a transparency bundle.

Note that this is also the wrong severity for an audit-system failure
in a regulatory-compliance product — the audit chain is the second
load-bearing surface after the wire contract.

**Repro / evidence**: Set `DATABASE_URL=postgresql://nobody:wrong@localhost:5432/missing`,
hit `/api/v1/regenold/eu-ai-act/ask`. The route returns 200. Inspect logs
at LOG_LEVEL=INFO: empty. Bump to DEBUG: a single
`regenold_question_evidence_failed` line per request. Verifying the chain
afterwards (`store.verify_chain()`) reports `is_valid=True total_entries=0`
because no writes ever landed — looks identical to "no traffic" from
outside.

**Suggested fix**: Promote the audit-failure log to WARNING (or ERROR if
EU AI Act Art. 12 compliance is the explicit contract). Add an
exception-type discriminator: cache one exception type per `error=%r` and
log only the first occurrence per minute to avoid log-flood under
sustained outage. Bonus: a /healthz/audit endpoint that reports
`store.count()` + `last_write_age_seconds` so uptime monitors can alert
on stalled chains independently of LLM / graph health. Today there's no
operational visibility into whether the audit chain is alive.

---

## A7 — Hardcoded `tier="partner"` in audit payload — anon traffic mis-tagged

**Severity**: P2
**Category**: observability
**Files**:
- `app/routes/regenold.py:2010` (main path: `"tier": "partner"`)
- `app/routes/regenold.py:991` (refusal path: `"tier": "partner"`)

**Finding**: The audit-chain payload hardcodes `"tier": "partner"` on
BOTH the main and refusal paths. This is correct IF the route enforces
required auth (A1) — every reachable caller is a partner. But the
auth.py + rate-limit code paths still describe a tier-split design
(`_RATE_KEY_PREFIX_ANON` + `_RATE_KEY_PREFIX_AUTHED` with distinct 30/60
limits and the docstring + audit comments at lines 1004-1009 explicitly
distinguish partner vs anonymous tenant IDs). If A1 is resolved by
swapping in `optional_regenold_api_key`, this hardcode silently mis-tags
every anonymous request as `partner`, breaking the audit-chain forensic
query "show me every public request".

Either way, the inconsistency between the rate-limit tier resolver
(`_regenold_dynamic_limit`) and the audit-tier string is a code-rot
flag — a future tier-split caller would need to remember to update both
sites independently.

**Repro / evidence**: `grep -n '"tier"' app/routes/regenold.py` →
both occurrences are the literal string `"partner"`. The route-level
`api_key: str = Depends(require_regenold_api_key)` will only ship a
typed string when auth landed, but the dep can't carry tier information
forward. The tenant_id string at 1009 / 2023 is also hardcoded
`"partner:regenold"` — same root cause.

**Suggested fix**: Derive `tier` from the request: if `api_key` is non-None
AND `validate_regenold_api_key(api_key)` → `"partner"`; otherwise
`"public"`. Pair with a dynamic tenant_id (`"partner:regenold"` vs
`"public:regenold-anon"`) so the audit forensic-query split actually
works. Same fix unblocks the partial migration to optional auth (A1).

---

## A8 — Structlog wired but never configured; logs are unstructured plaintext

**Severity**: P2
**Category**: observability
**Files**:
- `requirements.txt:10` (`structlog>=24.0.0` pinned)
- `app/routes/regenold.py:50, 106` (`import structlog; logger = structlog.get_logger(__name__)`)
- `app/main.py:22` (`logger = logging.getLogger(__name__)`)
- (no `structlog.configure` call anywhere — confirmed via grep across all of `app/`)
- (no `logging.basicConfig` call anywhere either)

**Finding**: The route imports `structlog` but no module ever calls
`structlog.configure(...)`. With no processors registered, structlog
falls back to its default `KeyValueRenderer` which emits unstructured
`key=value` lines. Meanwhile `app/main.py` and the rest of the codebase
use stdlib `logging`, which inherits uvicorn's default text formatter.
**Production log output is a mishmash of two formats** with no JSON
emission anywhere — log aggregators that expect JSON (Datadog,
Cloudwatch, Logtail in JSON-only mode) parse none of the lines as
structured events, breaking dashboards + alerting + queries.

Furthermore, even within structlog, no processors strip sensitive fields,
which means a future `logger.debug("evidence.record entry_type=%s payload=%s",
et, payload_copy)` would dump the full question + answer to logs.

**Repro / evidence**: `grep -rn "structlog.configure\|logging.basicConfig\|logging.config\.dictConfig" app/` returns zero matches.
Two log streams (`logging` and `structlog`) coexist with no shared
configuration; the JSON output Railway / Datadog expect is never emitted.

**Suggested fix**: Add an early `app/main.py` (or `app/__init__.py`) block
that configures structlog with shared processors:
```python
import structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
```
Gate behind an env flag (`REGENOLD_LOG_JSON=1`) so the dev path keeps the
pretty printer. Add a processor that redacts known secret-field keys
(`api_key`, `password`, `token`, `secret`, `dsn`) — defence-in-depth
against the A5 credential-leak surface.

---

## A9 — `REGENOLD_TRUST_PROXY` read at import time; can't flip without restart

**Severity**: P2
**Category**: config-env
**Files**:
- `app/routes/regenold.py:286-288` (`_TRUST_PROXY = os.getenv(...) ...` at module-load time)
- Same pattern: `_QA_TRIM_ENABLED` at 266, `_EXTRACT_EMBEDDINGS_ENABLED` at 272

**Finding**: `REGENOLD_TRUST_PROXY` is read once at module import. On
Railway, env-var changes via `railway variables --set ...` trigger a
redeploy, so this is fine in practice. **But**: if a deploy operator
needs to enable proxy-trust mid-incident (e.g. they just added a CDN in
front of an existing service and want to fix rate-limiting without
losing in-flight requests), they can't — the env-flip requires a full
redeploy. Same applies to `_QA_TRIM_ENABLED` and
`_EXTRACT_EMBEDDINGS_ENABLED`. The cache-key helper at line 197-213
deliberately reads the dense-rerank + citation-guard + PPR + PathRAG
flags lazily *because* runtime flips must invalidate cached results —
the same reasoning should apply to QA_TRIM and EXTRACT_EMBEDDINGS, which
change the answer text.

This contradicts the design note at lines 248-256: "their values are
fixed at process start". For `TRUST_PROXY` and `EXTRACT_EMBEDDINGS` this
is asserting a property that operators wouldn't expect.

**Repro / evidence**:
```python
# regenold.py:286
_TRUST_PROXY = os.getenv("REGENOLD_TRUST_PROXY", "").strip().lower() in {...}
```
A `railway variables --set REGENOLD_TRUST_PROXY=true` followed by a
mid-request env-read (e.g. operator runs a `python -c "import os; os.environ['REGENOLD_TRUST_PROXY']='true'"`)
has no effect until the next deploy. Documented as "fixed at process
start" in the design comment but the operator runbook
(`docs/partners/regenold/NEO4J_RUNBOOK.md`) doesn't surface this.

**Suggested fix**: Either (a) document the restart-required behaviour
explicitly in `.env.example` for `REGENOLD_TRUST_PROXY`,
`REGENOLD_QA_TRIM`, `REGENOLD_EXTRACT_EMBEDDINGS`, OR (b) move the read
to a small lazy helper (`_trust_proxy_enabled()`) keyed off env. Cost is
~50 ns per request which is well inside budget given the cache hit
rate. The cache-key precedent at line 197-213 already shows the pattern.

---

## A10 — `RegenoldChatMessage.role` validation produces no per-request size cap

**Severity**: P3
**Category**: wire-guard
**Files**:
- `app/integrations/regenold/models.py:34` (content max=4000)
- `app/integrations/regenold/models.py:46` (messages max_length=64)

**Finding**: The wire contract caps each message at 4 KB and the messages
array at 64 entries — total upper bound ~256 KB request body. This is
the documented design (`models.py:42-46`). However, FastAPI / Starlette's
default request body limit is unbounded — there's no `app.add_middleware(...)`
that rejects an oversized POST before pydantic parsing. A malicious
caller can send a 50 MB body; Starlette buffers the whole thing into
memory before pydantic gets a chance to reject the 64-element cap.
On the anonymous tier (if A1 is fixed), this is a memory-DOS vector
because the rate-limit budget is high enough that a small attacker can
sustain ~30 × 50 MB / min = 1.5 GB/min of buffered request bodies per
worker.

The current strict-auth posture (A1 unresolved) masks this — only authed
callers can trigger it, and they self-rate-limit. Promotion to optional
auth (recommended in A1) would expose the surface.

**Repro / evidence**: `curl -X POST -H "Content-Type: application/json"
--data @50MB_garbage.json https://<railway>/api/v1/regenold/eu-ai-act/ask`
will buffer the entire 50 MB into worker memory before pydantic raises
a `ValidationError`. No middleware-level guard exists.

**Suggested fix**: Add Starlette's `Content-Length` guard middleware
before mounting the API router. Reject any POST with declared body
length > 512 KB (2× the 256 KB theoretical max from `models.py`):
```python
@app.middleware("http")
async def _enforce_max_body_size(request: Request, call_next):
    content_length = int(request.headers.get("content-length", 0))
    if content_length > 512_000:
        return JSONResponse(
            status_code=413,
            content={"code": "payload_too_large", "max_bytes": 512_000},
        )
    return await call_next(request)
```
This is defence-in-depth — the pydantic cap still works as the
correctness gate; the middleware blocks the DOS amplifier before the
heap allocation.

---

# Severity rollup

| ID  | Severity | Category       | One-line |
| --- | -------- | -------------- | -------- |
| A1  | P0       | wire-guard     | Strict-auth dep wired; docs + audit infra all assume anonymous-friendly tier — every unkeyed deploy returns 503. |
| A2  | P0       | deploy-config  | slowapi `memory://` + `--workers 2` doubles effective rate-limit budget. |
| A3  | P1       | boot-time      | Auto-seed mis-reports Postgres-down as "another worker is seeding". |
| A4  | P1       | boot-time      | Synchronous Neo4j probe + seed-version read blocks uvicorn startup up to 18s. |
| A5  | P1       | observability  | `NEO4J_URI` credentials leak through driver-init + exception logs (R43 S3 still unfixed). |
| A6  | P1       | observability  | Audit-chain failures logged at DEBUG; operators have no signal that durable Postgres audit is broken. |
| A7  | P2       | observability  | `tier="partner"` hardcoded; anon traffic would mis-tag if A1 is resolved. |
| A8  | P2       | observability  | structlog imported but never `.configure()`'d; no JSON output anywhere. |
| A9  | P2       | config-env     | `REGENOLD_TRUST_PROXY` / `_QA_TRIM` / `_EXTRACT_EMBEDDINGS` read at import time. |
| A10 | P3       | wire-guard     | No middleware-level Content-Length guard; oversized POST buffers fully before pydantic rejects. |

# What I did NOT find (positive evidence, audit hygiene)

- `/healthz`, `/healthz/llm`, `/healthz/graph` correctly return HTTP 200
  on every degraded path per the documented contract — uptime monitors
  on the HTTP status code will not flap.
- The cache key (`_engine_cache_key`) correctly folds the 4 retrieval-
  affecting flags (TURBOQUANT_DENSE, CITATION_GUARD, GRAPH_PPR, PATH_RAG)
  + `KB_VERSION` + `question` + `system_context`. The post-cache flags
  (QA_TRIM / EXTRACT_EMBEDDINGS / REFBUDGET_PER_INTENT / CLARA_VERDICT /
  CROSS_ENCODER_RERANK) operate route-level after the cache lookup, so
  exclusion from the key is correct.
- `RegenoldChatMessage.content` max=4_000 + `messages` max_length=64
  combined give a clean 256 KB request body upper bound at the pydantic
  layer.
- The embedding assets (~1.8 MB in `app/engines/_assets/`) ARE committed
  to the repo (`.gitignore` doesn't exclude them) — no runtime download
  risk. The cross-encoder ONNX (`bge_reranker_base.onnx`) is NOT bundled,
  but the module is env-gated default OFF, so this is dormant code rather
  than image bloat or outage risk.
- The audit chain uses Postgres advisory locks correctly
  (`_AUDIT_CHAIN_LOCK_KEY` distinct from `_NEO4J_SEED_LOCK_KEY`) to fix
  the genesis-row fork race.
- `RegenoldAskRequest._last_user_message_must_be_non_empty` correctly
  rejects empty live-question requests with a 422.
- Multiple env-var failure modes (no `P2P_GRAPH_RAG_PROVIDER`, no
  `NEO4J_URI`, no `DATABASE_URL`) all degrade to a working deterministic
  baseline without crashing — graceful-degradation invariants hold.

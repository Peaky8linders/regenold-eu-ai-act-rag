# R462 — why the Cloudflare Access service token is refused (401), and what is restorable

Diagnosed **2026-10-08** against production `3cc2d5e135c1` and the operator's own
machine. Every claim below is a measured probe, not an inference from the code.

## 1. The symptom

`/healthz/llm` on production, both workers, every read:

```
llm_ok=false
provider="openai_wrapper (bedrock fallback FAILING)"
detail="primary offline (api_status_401: {\"message\":\"Unauthorized. You don't have
        permission to view this. Please contact you"
cf_access={client_id_set: true, client_secret_set: true, headers_attached: true}
stats: primary 0/4, fallback 0/4, refused_by_provider {groq: 4}
```

`headers_attached: true` means the provider **did** send a well-formed
`CF-Access-Client-Id` / `CF-Access-Client-Secret` pair for
`wrapper.antifragile-ai.net` (`_resolve_cf_access_headers` only returns headers
when both are set **and** the host is in `_cf_access_trusted_hosts()`).

## 2. Which edge refused it

Fetched the tunnel directly, three ways, with `follow_redirects=False`:

| request | status | body |
| :-- | :-- | :-- |
| no CF headers, `Accept: text/html` | 401 | Cloudflare Access block page (HTML) |
| **service token attached** | 401 | **byte-identical block page** |
| service token + bearer | 401 | byte-identical block page |

The block page names itself and the diagnostics:

```
Error – Cloudflare Access
Unauthorized. You don't have permission to view this. Please contact your system administrator.
Status code: 401
App AUD: 9bb8182c1d75191d35338987fc8e24db3191376290337de0b709e2cc496e4e9c
MTLS Status: NONE
```

Two facts settle it:

1. **Presenting the token changes nothing.** A garbage token (`id=x`, `secret=y`)
   returns the same response as ours. The edge is not honouring the credential.
2. **`server: cloudflare`, no `location` header.** An unauthenticated browser
   normally gets a **302** to `cloudflareaccess.com/cdn-cgi/access/login/...`.
   A **401 block page with no login redirect** is an Access application whose
   policy offers no interactive path — i.e. service-auth-only — so an
   unrecognised token falls straight to deny.

`app/main.py`'s own R277 comment describes this exact signature, written before
this incident: *"token set but rejected by policy -> headers_attached true,
llm_ok false"*. So the diagnosis is not novel; only the naming was missing (§5).

## 3. Why now — the timeline

| when | evidence | primary leg |
| :-- | :-- | :-- |
| 2026-10-02 15:49–15:56 | `CANARY-PRIMARY.md`, commit `7fbd46737548` | **serving**, `provider: openai_wrapper`, `detail: ok`, model `claude-opus-5-5` |
| 2026-10-07 **09:07** | `~/.claude/.credentials.json` mtime | Claude CLI re-authenticated |
| 2026-10-07 **09:11** | `C:\ProgramData\cloudflared\token` mtime; once-missing dir | **tunnel re-keyed** — service `Cloudflared` runs `tunnel run --token-file C:\ProgramData\cloudflared\token` |
| 2026-10-08 | this probe | 401, token refused |

A maintenance window on the morning of Oct 7 re-authenticated the CLI and
re-provisioned the tunnel four minutes later. Re-adding a public hostname in the
Zero Trust dashboard is the flow that creates/attaches an Access application, and
a service token that is not an `Include -> Service Auth` principal on the **new**
application is refused exactly as observed. The credentials themselves are
unchanged: **all ten `.env` files on this machine carry the identical token**
(sha256 prefixes `8f40386f9a26` / `f30ef1bbb10a`), including the ones that worked
in August and on Oct 2. There is no newer token on disk to adopt.

## 4. The second, independent blocker — and it is fixed

The tunnel terminates at a wrapper on **this machine** (`CANARY-PRIMARY.md`: the
tunnel points at `claude-code-openai-wrapper` on `127.0.0.1:8000`).

```
netstat -> nothing LISTENING on 127.0.0.1:8000
```

So even a valid token would have received a tunnel-side 502. Restarted via the
wrapper's own launcher:

```
uvicorn src.main:app --host 127.0.0.1 --port 8000
/v1/auth/status -> {"claude_code_auth":{"method":"claude_cli","status":{"valid":true,"errors":[]}}}
```

Verified through the repo's real provider path, `base_url=http://127.0.0.1:8000/v1`:

```
cf headers for local = {}          # no Zero Trust secret is sent to a local host
error   = None
model   = claude-sonnet-4-6
elapsed = 9713 ms
text    = 'I'm not sure what you mean by **"regenold-leg-probe"**...'
PRIMARY LEG (local): UP
```

**The primary leg is UP**, and it needs no Access token on this path: the leg is
reached over loopback, where `_resolve_cf_access_headers` correctly returns `{}`.

Re-probing the tunnel **with the origin now healthy** still returns the identical
Access 401 for token and no-token — proof the two failures are independent and
that §2 is not a side effect of the dead origin.

## 5. Shipped fix — R462, name the denial

`api_status_401` was a coin flip between two bugs needing opposite fixes, and the
message was truncated one character before it became legible. The provider now
appends a named, remedied suffix while leaving `api_status_<code>` first, so
`_graph_rag_impl`'s loud provider-outage branch (`"api_status_401" in _err_low`)
keeps matching:

```
api_status_401: {"message":"Unauthorized. You don't have permission to view this.
Please contact your system administrator.","status_code":401,"aud":"9bb8182c..."}
[cf_access_denied: the Cloudflare Access EDGE refused this request even though the
CF-Access-* service token WAS attached, so the token is not an Include -> Service
Auth principal on this Access application — it was rotated/revoked, or the
application was re-created. Issue a new service token and set CF_ACCESS_CLIENT_ID
+ CF_ACCESS_CLIENT_SECRET.]
```

Pinned by `tests/test_r462_cf_access_denial_named.py`, including the negative
controls: an ordinary wrapper 401/403/500, an empty body and a 200 all gain
**nothing**, and the secret never reaches the string.

### 5b. The first cut of this shipped a fix nobody could see

Measured on `07f8cc0` **minutes after the deploy landed**: the note was present
in the error string and **absent from `/healthz/llm`** — the one place an operator
looks. `_degraded_to_bedrock` summarises the provider error with
`detail[:100]` / `detail[:120]` / `detail[:150]`, and the note is appended after a
200-char body, so every slice landed mid-body:

```
primary offline (api_status_401: {"message":"Unauthorized. You don't have
permission to view this. Please contact your system administrat); bedrock
fallback active
```

Two fixes, both because the truncation told me something about the design:

1. `_degraded_to_bedrock` now lifts a bounded `[name: ...]` marker **outside**
the byte budget (`_named_error_marker`), so a named condition buys its own
characters and an unnamed one reads byte-identically to before.
2. The marker is **remedy-first**. Every consumer of this string slices it, so
an ordering that explains before it instructs loses the instruction — the first
cut's visible form ended at `...on this Access appli`, precisely one word short
of the action.

The lesson generalises: adding detail to an error is only a diagnosis if it
survives the narrowest slice that carries it to a human.

## 6. What is NOT restorable from here — the operator action

Production's primary leg stays down until a credential is re-issued in Cloudflare,
because the denial is an edge policy decision:

1. **Zero Trust → Access → Service Auth → Create Service Token**, then
2. add it to the `wrapper.antifragile-ai.net` application as
   `Include → Service Auth` (a token alone is not enough — it must be a policy
   principal), then
3. `railway variables --set CF_ACCESS_CLIENT_ID=<new id>` and
   `--set CF_ACCESS_CLIENT_SECRET=<new secret>`, mirror them into `.env`, and
   redeploy so the worker is recreated with the new env.

There is **no Cloudflare API token on this machine** (`CF_API_TOKEN` /
`CLOUDFLARE_API_TOKEN` / `CF_ACCOUNT_ID`: zero hits in `.env`) and no `railway`
CLI, so neither step 1–2 nor step 3 can be performed from here.

The Bedrock fallback leg is a separate credential outage — its local
`AWS_BEARER_TOKEN_BEDROCK` returns `api_key_invalid_403` — so the service is
currently answering Stage-2 deterministically. Fixing either leg restores
synthesis; fixing only the tunnel requires §4 to stay satisfied.

## 7. Resolution — measured 2026-10-09

The operator rotated the Access service token and minted a fresh Bedrock API
key, both set on the Railway service. Final state, measured against the live
deploy (`deployment_id cd847b7e-28b4-4389-91a2-508a67fa5c43`, `version 1.2.3`):

| probe | reading |
| :-- | :-- |
| `/healthz/llm`, **both** workers | `llm_ok: true`, `detail: "ok"` on pid 3 and pid 4; the anonymous probe fires a live wrapper completion (15.03 s / 12.37 s) |
| `/healthz/llm?probe_bedrock=1` | `status: "ok"`, `error: null`, `qwen.qwen3-235b-a22b-2507-v1:0`, **567 ms** — a real Converse call, not an auth rejection |
| transport contract | `strict: true`, `chain: ["openai_wrapper", "bedrock"]` |
| `POST /ask?include_telemetry=true` | **no `warning`** (the field is set only when Stage-2 failed), 27.35 s, `references: [Article 26.2, Article 27.1.e]` |
| serving-worker counters | `primary 1/1, fallback 0/0, refused 0` |

§1 is reversed and the chain is **2/2**: the tunnel carries Stage-2, and Bedrock
accepts the credential and returns a completion. Scope note on that second half —
at the time of this reading the probe called `check_connectivity_and_permissions()`
over the pinned `BEDROCK_FALLBACK_PROBE_MODELS`, not the fallback's own
`_bedrock_complete_for_graph_rag` path. With `REGENOLD_STAGE2_BEDROCK_MODEL`
unset both resolve to the same Qwen tier (`stage2_policy.stage2_fallback_model()`
returns `""` → Qwen 3 32B/235B), so the credential was cleared **on the model the
fallback actually serves**, and the completion path itself is pinned by
`tests/test_r431_fallback_leg_guard.py` rather than exercised live — forcing the
primary down for real would mean mutating the production env.

**R464 correction to that scope note.** The two sides are no longer compared by
hand: the probe resolves its walk through
`_graph_rag_impl.bedrock_fallback_model_chain()`, the same function
`_bedrock_complete_for_graph_rag` walks, and dials each candidate through
`complete_with_fallback(..., fallbacks=())` — the fallback's own transport. So
the "same tier by coincidence of defaults" argument above is superseded, not
merely still true: the walk follows every `REGENOLD_BEDROCK_*` override, and a
custom chain now moves the diagnostic with it. See
[../r464/PROBE-MODEL-FIDELITY.md](../r464/PROBE-MODEL-FIDELITY.md) §4 for the
live reading on the resolved walk (2026-10-21).

Two further reading notes, both measured:

* The health probe does **not** move the transport counters (pid 3 read `0/0`
  while `llm_ok: true`), so they are only evidence of real traffic — read them
  after an `/ask`, not after a probe. `--workers 2` makes them per-worker as
  well, so poll until the pid that served the request repeats.
* The new Bedrock key only took effect **after the process was recreated**: the
  `deployment_id` moved `0b58565b-…` → `cd847b7e-…` and every per-worker counter
  reset to `0/0` between two probes minutes apart, while the console already held
  the new value. That is the probe's own hint (`a new value … is NOT in
  os.environ until the process restarts`) observed rather than assumed — a
  Railway variable change that does not restart the worker reads `key_invalid`
  indefinitely.

### 7b. What the operator still owns

**`.env` on this machine still carries both revoked credentials** — the Access
pair unchanged from §3 (`8f40386f9a26` / `f30ef1bbb10a`) and the old Bedrock key
(`3b788124822d`), the file untouched since 2026-09-30. Production succeeds
because Railway holds the new values: a direct tunnel call from this box returns
the §2 block page, and a locally-run Bedrock call still gets
`api_key_invalid_403`. Paste both new values into `.env` before running anything
locally that dials a leg. The tunnel also terminates on this machine
(`127.0.0.1:8000`, §4), so production's primary leg depends on this box staying
up.

**Re-measured 2026-10-21 — half of that warning has expired.** A local
`/healthz/llm?probe_bedrock=1` returned `status: ok`,
`qwen.qwen3-32b-v1:0`, 1077 ms, `response_text: "OK."` with real token counts,
so the local `AWS_BEARER_TOKEN_BEDROCK` in `.env` is **live**, not the revoked
`3b788124822d`. The Access half still holds: the same process's base
`/healthz/llm` reported `api_status_401` with `cf_access_denied: … the token is
not a principal on the application`, so `CF_ACCESS_CLIENT_ID` /
`CF_ACCESS_CLIENT_SECRET` still need replacing. Only that pair is outstanding.

### 7c. Two traps found while re-testing

- **The hostname now carries a WAF UA rule.** A non-browser client gets
  `403 {"title":"Error 1010: Access denied"}` *before* Access is evaluated —
  with or without a valid service token. Production is unaffected (the provider
  pins a Chrome UA), but any `curl`/urllib retest must send one or it reports a
  failure that does not exist. §2's table only ever saw the 401 shape.
- **The legacy Groq hatch armed and was counted.** While the primary was down,
  the serving worker showed `refused_by_provider {groq: N}` — the engine tried to
  answer Stage-2 off-contract and the R360 guard blocked it. That is the policy
  working, not a new bug; with the tunnel restored the count is 0.

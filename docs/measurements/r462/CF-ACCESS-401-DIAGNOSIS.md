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

Pinned by `tests/test_r462_cf_access_denial_named.py` (14 tests), including the
negative controls: an ordinary wrapper 401/403/500, an empty body and a 200 all
gain **nothing**, and the secret never reaches the string.

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

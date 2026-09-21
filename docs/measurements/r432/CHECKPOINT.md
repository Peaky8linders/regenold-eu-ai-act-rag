# R432 — the outage remedy: use a working transport instead of grading Stage-1 drafts

**Context.** The R431 draw aborted on generation 3 because the Claude Max wrapper's
upstream returned `500 No response from Claude Code`, and the documented fallback
(Bedrock) was also down: the AWS long-term Bedrock API key had expired
(`api_key_invalid_403`, the engine's own diagnostic). Production was in the same state —
a live check on the deployed build showed every row served
`stage2_served_by=deterministic`, i.e. Stage-1 drafts, correctly marked
`cache_skip_degraded_serve`.

The ask was to use a fallback *directly* when the tunnel or its quota is down. Doing that
surfaced two real defects in the path that is supposed to make it possible.

## 1. The transport allowlist was doubling as the secret allowlist (security)

`_cf_access_trusted_hosts()` (R365) anchored the Cloudflare Access service-token scope on
`stage2_policy.allowed_primary_hosts()` — the list an operator edits via
`REGENOLD_STAGE2_PRIMARY_HOSTS` to point Stage-2 at a different transport. So **the one
knob an operator sets to recover from an outage also handed that host the Zero Trust
service-token SECRET.**

Measured on the R365 code:

```
CF_ACCESS_* set, REGENOLD_STAGE2_PRIMARY_HOSTS=openrouter.ai
_resolve_cf_access_headers("https://openrouter.ai/api/v1")
  -> {'CF-Access-Client-Id': 'ID', 'CF-Access-Client-Secret': 'SECRET'}
```

That is the same exfiltration R365 exists to prevent, reached through the documented
remedy. Two different questions were sharing an answer: *which hosts may Stage-2 dial*
(routing) and *which hosts may be handed a credential* (secret scope).

**Fix.** Secret scope is now `CF_ACCESS_HOSTNAME` (explicit operator pin) if set, else the
hardcoded default wrapper host. The transport allowlist no longer widens it. Renaming
one's own tunnel still works: pin it with `CF_ACCESS_HOSTNAME=<new host>`.

After the fix: `_resolve_cf_access_headers("https://openrouter.ai/api/v1") == {}` with
`REGENOLD_STAGE2_PRIMARY_HOSTS=openrouter.ai` set. Pinned by
`tests/test_r365_cf_access_host_pin.py::TestTransportAllowlistIsNotASecretAllowlist`
(inverted from a test that had encoded the leak).

## 2. The remedy could not actually deliver the same model (silent degradation)

Every model the app sends is a bare vendor name (`claude-opus-5`). A namespaced transport
requires `anthropic/claude-opus-5` and answers **HTTP 400** otherwise — and the failure
mode is silent: the engine falls through to a deterministic Stage-1 draft rather than
raising. Two fixes:

* **`REGENOLD_WRAPPER_MODEL_PREFIX`** (default `""` = today's behaviour). When set, it
  namespaces the `claude*` models at the single choke point
  (`resolve_wrapper_model`), so Stage-2, the denoiser, the intent classifier and the
  preflight all agree. Scoped to `claude*` deliberately: this provider class is reused for
  Groq / Gemini / Mistral, and a blanket prefix would rewrite their ids into nonsense.
  It also supersedes the alias table (which repairs a name *for the wrapper* — against a
  different namespace its targets are wrong).
* **The eval preflight now probes the configured Stage-2 model**, not the request
  default. It had been sending the literal `claude-opus-4-8` on the stated premise that
  the alias map would resolve it "to the same effective model the engine's Stage-2 calls
  land on" — true only while the alias table was ON, which it has not been since R308. The
  probe could therefore pass, or fail, on a model no row ever uses.

## 3. Evidence

| check | result |
| :-- | :-- |
| provider seam, alternate transport | `anthropic/claude-opus-5` → HTTP 200, text `OK`, 4.0 s |
| CF headers sent to the alternate transport | `{}` (was the service-token pair before this round) |
| models the app sends, availability | `anthropic/claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `claude-sonnet-4.6`, `claude-haiku-4.5` — all present |
| Bedrock leg (operator refreshed the key) | `check_connectivity_and_permissions() → status ok` |
| preflight, alternate transport | `Stage-2 transport preflight OK (model=anthropic/claude-opus-5)` |
| worktree | `Default` in `tests/test_r432_transport_remedy.py` + reworked R365 pin tests |

**Generator identity.** The alternate transport serves the *same* model ids — the board's
Stage-2 model `claude-opus-5` is available there as `anthropic/claude-opus-5`. What
changes is the serving route (Claude Max subscription vs OpenRouter), so answers stay
comparable on the model axis while **latency does not** (the alternate transport has no
Max-subscription fast path). Any speed axis on a draw taken this way must be read as a
transport figure, not a production figure.

## 4. What this restores

* Eval draws no longer die when the tunnel or its quota does: the leg-aware guard (R431)
  carries a run on a healthy fallback, and the alternate-transport contract carries it on
  the same model identity.
* Production has a documented remedy for the state it was in: `OPENAI_API_BASE` +
  `OPENAI_API_KEY` + `REGENOLD_STAGE2_PRIMARY_HOSTS` + `REGENOLD_WRAPPER_MODEL_PREFIX`,
  then redeploy. The refresher Bedrock key also restores the native fallback leg.

**Validation.** Focused transport/cache suite: **127 passed**. Full project suite:
**8,620 passed, 2 skipped**. Railway boot-healthcheck: **HTTP 200** under the repository's
actual `railway.toml` command. The completed R431 hard gate: **111/111 fresh draws**,
`SHIP`; the native Bedrock connectivity probe now returns `status=ok` with the refreshed
operator token.

**Honest scope.** Neither fix addresses the underlying outage; they make the recovery path
safe and faithful. Latency comparability is the one axis this round cannot preserve.

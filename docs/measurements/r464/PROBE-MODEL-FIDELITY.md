# R464 — the Bedrock health probe now dials the fallback's real path and model

`/healthz/llm?probe_bedrock=1` is the one instrument an operator reaches for when
Stage-2 leg 2 (Bedrock) is dark. It was answering a question adjacent to the one
being asked, in three separate ways. This note records the defect, the single
definition that removes it, and the two side effects that had to be suppressed
once the probe started borrowing the serving transport.

## 1. Three ways the reading could be about something else

**(a) It probed a mirrored list, not the resolved chain.** The walk was the
hand-typed constant `BEDROCK_FALLBACK_PROBE_MODELS` — Qwen 3 235B, then Qwen 3
32B. The fallback derives its list from `REGENOLD_BEDROCK_MODEL`,
`REGENOLD_BEDROCK_COMPLEX_MODEL`, `REGENOLD_BEDROCK_FALLBACK_CHAIN` and the
`REGENOLD_STAGE2_BEDROCK_MODEL` override that
`_try_bedrock_fallback` passes into `_bedrock_complete_for_graph_rag`. Pin all
four to one model and the fallback's ordered list becomes that model alone; the
probe kept clearing the credential on Qwen and reported `status: ok` for a leg
that could not answer a single Stage-2 call. R365 measured the same failure in
the other direction (`eu.anthropic.claude-opus-4-8` → `api_access_denied_403`
on an account whose Qwen tiers were fine).

**(b) It dialled a different transport.** `_bedrock_complete_for_graph_rag`
calls `complete_with_fallback(req, fallbacks=())` once per candidate; the probe
called `BedrockProvider.complete` directly, so alias resolution and the
process-global denied-model cache — the things that decide whether a call even
goes out — were outside the probe's view.

**(c) A wrapper-served call read as a healthy Bedrock call.** The wrapper hop
inside `complete_with_fallback` (`_try_wrapper_fallback`) is reached when every
Bedrock model refuses, and it returns a **successful** response tagged
`wrapper:<model>`. Reporting that as `ok` names a Bedrock model as the answering
model while a different provider served the completion — the mirror image of the
bug this round exists to fix, and a silent one: the deploy looks one-legged-safe
while the credential is dead.

## 2. The fix — one definition, two callers

`app/engines/_graph_rag_impl.py` now owns `bedrock_fallback_model_chain()`, the
single definition of the ordered list a completion would dial, and
`_bedrock_complete_for_graph_rag` walks it. `app/llm/bedrock_client.py` resolves
the probe's walk through that same function
(`_stage2_probe_models_and_source()`), over both question classes and with the
policy override applied, and echoes back:

* `resolved_models` — the list actually dialled, in order,
* `models_source` — `stage2_fallback` | `explicit` | `pinned_probe_list`.

`models=` lets a caller probe a chain it resolved itself (and lets tests drive
the walk without an engine); `None` still means "ask the engine". If the engine
cannot be imported the walk degrades to the old pinned literal **and says so**
in `models_source`, rather than reporting a credential problem from an empty
list.

The per-model dial now goes through `complete_with_fallback(..., fallbacks=())`
— the fallback's own transport, per candidate.

## 3. The two side effects borrowing that transport imports

Both are behaviours of the *transport*, invisible in a diff of the probe, so
each is pinned on an effect rather than on the call's shape.

**Counter bleed → `record_stage2=False`.** The wrapper hop counts itself as a
Stage-2 **primary** completion, and `easyhard_ab._transport_liveness` /
`gate_validity` read those process-global counters. A probe on a dead run could
therefore make the run read live — precisely the false-green R418 removed for
the Stage-0 de-noiser. The diagnostic is not Stage-2 traffic, so it records
none.

**The mask → `bedrock_exhausted_served_by_wrapper`.** A completion whose
`model` is tagged `wrapper:` is reported as an error naming the mask
(`served_by: wrapper:<model>`, plus a hint saying the reading is not evidence
about the credential), never as `ok`. `app/main.py::_probe_bedrock_leg`
forwards `served_by` alongside `resolved_models` so the operator sees who
actually answered.

## 4. Measured

Offline, after the last edit (whole-file, not filtered through the gate flag):

| suite | result |
|---|---|
| `tests/test_r464_bedrock_probe_model_fidelity.py` (+ R365 chain guards, R431 leg guard, R418 counter guard) | **88 passed**, exit 0 |
| `test_r361_instrument_fidelity`, `test_r321_review_fixes`, `test_r365_bearer_token_refresh`, `test_r370_probe_endpoint_auth`, `test_r394_2_tracked_module_imports`, `test_r355_cache_key_complete` | **97 passed**, exit 0 |
| `test_bedrock_client`, `test_bedrock_qwen_routing`, `test_r464_*` | **84 passed**, exit 0 |

The interface is tested through the route the operator uses, not just at the
client: `TestTheResolvedChainReachesTheOperator`
reaches `/healthz/llm?probe_bedrock=1`, where `_probe_bedrock_leg` forwards an
explicit key allow-list — a key the client reports and the route forgets is
indistinguishable from a clean answer with an odd error code. It pins that
`served_by` reaches the wire and that the masked verdict keeps the client's own
hint over the generic entitlement one.

The three R464 side-effect tests drive the **real** `complete_with_fallback`
with only its ends stubbed (Bedrock denies with the durable entitlement marker,
the wrapper hop accepts), so `record_stage2=False` and the mask guard are read
from `stage2_policy.transport_stats()` and the returned verdict, not from source
text. Two-sided: a Bedrock-served call still reports `ok`, names the model, and
leaves the counters at zero.

New pins: `tests/test_r464_bedrock_probe_model_fidelity.py`
(`TestTheWalkIsTheFallbacksChain`, `TestTheFalseHealthy`,
`TestTheProbeDialsTheFallbacksTransport`, `TestResolutionFailureStaysHonest`,
`TestTheResolvedChainReachesTheOperator`,
`TestTheProbesTransportSideEffects`); `tests/test_r365_probe_real_chain.py` and
`tests/test_r365_bedrock_diagnosability.py` updated to the resolved-chain
contract.

**Live reading on the previous cut** (deployment
`cd847b7e-28b4-4389-91a2-508a67fa5c43`, before this one): `?probe_bedrock=1` →
`status: ok`, `qwen.qwen3-235b-a22b-2507-v1:0`, 567 ms, no `warning`, Stage-2
landing on a real `/ask`. That reading was taken **through the old mirror**,
which is why the answering model is the 235B tier: the literal dialled 235B
first regardless of what the fallback would do.

### 4b. Live reading on THIS cut (2026-10-21)

Local `uvicorn app.main:app` on `127.0.0.1:8100`, real `.env` credentials, the
route the operator uses (not the client function):

| call | reading |
| :-- | :-- |
| `GET /healthz/llm` | `llm_ok: true`, `provider: "openai_wrapper (bedrock fallback)"`, `detail: "primary offline (api_status_401 … cf_access_denied …); bedrock fallback active"` — the local Access token is still the revoked one, so the primary leg is down on this box |
| `GET /healthz/llm?probe_bedrock=1` | `status: "ok"`, `model: "qwen.qwen3-32b-v1:0"`, **1077 ms**, `response_text: "OK."`, `input_tokens: 15`, `output_tokens: 3`, `models_source: "stage2_fallback"`, `chain` = one entry |

The `resolved_models` echo, which the old probe could not report at all:

```
["qwen.qwen3-32b-v1:0", "qwen.qwen3-235b-a22b-2507-v1:0",
 "eu.anthropic.claude-opus-4-6-v1", "nvidia.nemotron-super-3-120b",
 "mistral.devstral-2-123b"]
```

Two things are being measured there, not inferred. First, the walk is the
**fallback's** order, so a standard Stage-2 call dials the **32B** tier head and
that is the entry that answered — the old literal dialled 235B first and would
have reported 235B as "the model the fallback serves", which is the wrong tier.
Second, `models_source: stage2_fallback` says the list came from the engine, not
from the last-resort literal.

**The override now moves the diagnostic** — the defect class this round removes,
observed end to end. Restarting the same app with
`REGENOLD_BEDROCK_FALLBACK_CHAIN=qwen.qwen3-32b-v1:0` and
`REGENOLD_STAGE2_BEDROCK_MODEL=qwen.qwen3-32b-v1:0` collapsed the reading to
exactly

```
resolved_models: ["qwen.qwen3-32b-v1:0"]
status: "ok", 842 ms
```

i.e. pinning the chain to one model narrows the probe to one model. Before R464
that env pair changed nothing about the walk: the probe still dialled 235B then
32B and could clear the credential on a 235B entitlement the pinned fallback no
longer had.

Total spend: three billable Converse calls (`max_tokens=5`). The pre-cut reading
above is not comparable as a latency number — different day, different region
latency — only as an ordering number.

**Still offline-only:** the two side-effect branches (`record_stage2=False` and
the `wrapper:` mask) need a Bedrock chain that refuses. Forcing them live means
mutating the production credential, so they stay pinned by
`TestTheProbesTransportSideEffects`, which drives the real
`complete_with_fallback` with only its ends stubbed.

## 5. Cost, and one thing to know

`?probe_bedrock=1` stays opt-in and operator-only (R370). In the healthy case it
still short-circuits on the first answering model — one billable Converse call,
unchanged. In the outage it exists to detect it now also pays the wrapper hop,
which is the price of dialling the real path instead of a shortcut; the probe no
longer hides that hop, it reports it.

Still true and unrelated to this round: the walk skips nothing, so an
entitlement 403 the probe triggers is remembered in the process-global denied
cache for its TTL. That is the same caching real traffic does; the probe is not
poisoning a model it did not test.

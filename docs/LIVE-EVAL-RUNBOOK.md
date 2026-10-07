# Live eval runbook — scoring R360 over the cloudflared tunnel

**Why this file exists:** the R360 work was developed and validated in a Claude
Code remote container whose egress policy **denies** the tunnel. The live
pairwise A/B — the repo's stated merge gate — could not be run from there. Every
command below is ready to paste on the operator's machine, where the tunnel is
reachable.

## What was blocked, exactly

Measured from inside the container, `curl` through the session's agent proxy:

| host | result |
| :--- | :--- |
| `wrapper.antifragile-ai.net:443` | `connect_rejected` — 403 to CONNECT (egress policy) |
| `app.antifragile-ai.net:443`, `antifragile-ai.net:443` | `connect_rejected` |
| `regenold-eu-ai-act-rag-production.up.railway.app:443` | `connect_rejected` |
| `api.groq.com:443`, `openrouter.ai:443`, `api.cohere.com:443` | `connect_rejected` |
| `bedrock-runtime.eu-central-1.amazonaws.com` | **reachable**, but the container's `AWS_ACCESS_KEY_ID` is a proxy placeholder → `UnrecognizedClientException` |

So **no** live LLM transport was usable: not the tunnel, not Bedrock, not the
deployed endpoint. Nothing in this branch has a live judged score behind it.
What it does have is in `docs/reviews/r360-stage2-transport-contract-2026-08-22.md`.

## Prerequisites

```powershell
# The tunnel — Stage-2 primary. Without CF_ACCESS_* the Access edge answers an
# HTML login page + 401, which the harness now reports honestly instead of
# silently downgrading to the deterministic tier (R360.2).
$env:OPENAI_API_BASE       = "https://wrapper.antifragile-ai.net/v1"
$env:OPENAI_API_KEY        = "dummy"
$env:CF_ACCESS_CLIENT_ID   = "<service token id>"
$env:CF_ACCESS_CLIENT_SECRET = "<service token secret>"
$env:P2P_GRAPH_RAG_PROVIDER = "openai_wrapper"

# Bedrock — the fallback leg. Arm it, or the R360.1 fix has nothing to prove.
$env:AWS_BEARER_TOKEN_BEDROCK = "<token>"     # or AWS_ACCESS_KEY_ID + _SECRET
$env:BEDROCK_REGION           = "eu-central-1"
```

Confirm both legs before scoring anything:

```bash
curl -s https://wrapper.antifragile-ai.net/v1/auth/status \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET"

# Local app view of both legs at once — chain, strictness, and live counters.
curl -s http://127.0.0.1:8000/healthz/llm | jq .stage2_transport
```

## 0. Prove the contract fires before reading any number

This is the R329 rule the hard way: a routing lever that reads correctly and
makes zero calls is indistinguishable from one that works.

```bash
pytest tests/test_r360_stage2_transport_policy.py tests/test_r360_2_ab_judge_tunnel_probe.py -v
```

Then, after any live run, read the counters. `primary_ok` should carry the run;
`refused_by_provider` **must be empty**:

```bash
curl -s http://127.0.0.1:8000/healthz/llm | jq .stage2_transport.stats
```

## 1. The merge gate — live pairwise A/B

The instrument `CLAUDE.md` names as the only one that measures what the
competition measures. Probe set: **132 rows across 23 categories, 37 multi-turn**.

Judge on **Bedrock**, not the tunnel: judging over the tunnel competes with
Stage-2 for the single Claude Max wrapper, and `CLAUDE.md`'s own rule is
"No Parallel Wrapper Jobs". `--judge-provider bedrock` was unblocked in R360.2.

```bash
# Full set (132 rows x 2 arms x position-swapped judge). Start with --limit 12.
python -m evals.harness.ab_judge \
  --label r360-strict-transport \
  --baseline-env REGENOLD_STAGE2_STRICT_TRANSPORT=0 \
  --branch-env   REGENOLD_STAGE2_STRICT_TRANSPORT=1 \
  --judge-provider bedrock \
  --timeout 180
```

⚠ **Read this arm honestly.** With the tunnel healthy, both arms answer from the
tunnel and the A/B should read ~0 — that is the *expected* result and it is not
evidence of nothing, it is evidence that R360 does not disturb the happy path.
The change only bites when the tunnel fails. To measure *that*, force it:

```bash
# Tunnel unreachable in both arms; baseline may escape to Groq/Gemini, branch
# must fall to Bedrock. This is the arm where the contract is actually visible.
OPENAI_API_BASE=http://127.0.0.1:1/v1 python -m evals.harness.ab_judge \
  --label r360-tunnel-down \
  --baseline-env REGENOLD_STAGE2_STRICT_TRANSPORT=0 \
  --branch-env   REGENOLD_STAGE2_STRICT_TRANSPORT=1 \
  --judge-provider bedrock --timeout 180
```

## 2. Reference conciseness + strict recall

```bash
python -m evals.harness.easyhard_ab --local --label r360 --timeout 180
```

## 3. Golden datasets available

| dataset | path | rows | what it scores |
| :--- | :--- | ---: | :--- |
| A/B probe set (**merge gate**) | `evals/harness/probe_set.py` | **132** | pairwise win-rate per axis, sign-test p |
| davidath scenarios | `evals/bench/data/scenarios.json` | 339 | **RETIRED — not an instrument.** See below |
| davidath QA | `evals/bench/data/qa_pairs.json` | 137 | **RETIRED — not an instrument** |
| davidath total | — | **476** | **RETIRED — not an instrument** |
| regenold scenarios | `evals/regenold/scenarios.py` | **255** | legacy scenario suite |
| antifragile ground truth | `evals/regenold/antifragile_groundtruth.py` | 20 | multi-turn coherence |
| OOS / adversarial probes | `runner_v2 --probe-oos --oos-suite all` | 51 | scope gate |

> `CLAUDE.md` calls the regenold suite "the 276 scenarios". It is **255** today.
> Minor doc drift, recorded here rather than silently corrected.

⚠ **DAVIDATH IS RETIRED AS AN INSTRUMENT (operator directive, R461 close).**
`CLAUDE.md` § *The merge gate is ALWAYS the live pairwise A/B* already says
*"They are retired. The ONLY evaluation instrument is the live pairwise A/B
judge"* — this table was the last artefact still presenting the 476 rows as a
verification step, so it no longer does.

Why it cannot be one, kept here so the decision is not re-litigated:

* it runs `provider=cli`, so it cannot see Stage-2, synthesis or any live win —
  `evals/bench/runner.py` stamps its own sidecar `role: "regression_guard"` for
  exactly that reason;
* it is **BM25-saturated**, so it is structurally blind to a hop's cost: R110.1
  read a change "davidath byte-identical" and shipped it ON, and the same change
  was later found to cost 19 extra non-gold refs (R318);
* its token-overlap axes diverge from the live judge (R99.2).

**Measured, so the retirement is not an assumption.** At the R461 close the same
474 rows were replayed deterministically through `main` and through the branch
(`git archive` of each, `provider=cli`, Stage-2 pinned off): **every aggregate
axis is identical to four decimals** (`qa` RefL 0.8467 / RefS 0.5488, `scenarios`
RefC 0.4253, Ans Strict 0.3692), and the only per-row field that moved is
float-level noise in `scores`. The instrument is flat by construction, which is
precisely why it cannot price this class of change.

The dataset and its tests stay in the tree (the pin in
`tests/test_r394_2_tracked_module_imports.py`'s sibling checks and the
`dataset.ensure_dataset()` SHA pin are untouched), so nothing else churns and a
recorded draw can still be replayed. Running it is allowed; **quoting it as
evidence for or against a lever is not.**

## 4. Deterministic suites — retired as instruments

`CLAUDE.md` R330 turns these **off as gates**, and R461 retires them as
instruments outright (§3). Use one only to answer "did the deterministic wire
move at all?", never "is this lever a win". A flat reading is the expected
result and is **not** evidence the lever is inert.

```bash
# Only if a later change is EXPECTED to move deterministic retrieval.
REGENOLD_SKIP_DOTENV=1 python -m evals.bench.runner

# Scope gate — must set REGENOLD_SKIP_DOTENV=1, or the classifier makes live
# third-party calls and the "deterministic" probe stops being deterministic.
REGENOLD_SKIP_DOTENV=1 python -m evals.regenold.runner_v2 --local --probe-oos --oos-suite all
```

Judge the OOS run on the **adversarial** categories only (`injection`,
`injection_obf`, `scope_drift_mt`). `CLAUDE.md` records that the other
categories over-count: answering an off-topic pleasantry is allowed, and the
`adjacent_eu` "leaks" are legally correct answers.

## 5. Never run two wrapper-bound jobs at once

One local proxy instance, one job. `--judge-provider bedrock` exists precisely
so the judge does not become the second job.

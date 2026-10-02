"""R461.7 round close (docs only): canary PASS + the replicate closed without new draws.

Idempotent by marker. Backslash-free by construction (newlines are detected with
chr(13)/chr(10)) so the file survives any editor that doubles backslashes.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CR = chr(13)
LF = chr(10)


def read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def write(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def nl_of(t):
    return CR + LF if CR in t else LF


def block(seq, nl):
    return nl.join(seq) + nl


def patch_promotion():
    p = ROOT / "docs/measurements/r461/PROMOTION.md"
    t = read(p)
    if "## 6. Canary status (2026-10-02): RUN, PASS" in t:
        return "promotion: already applied"
    anchor = "## 6. Canary status (2026-10-02): BLOCKED on the shipped transport"
    if anchor not in t:
        raise SystemExit("promotion: anchor missing")
    head = t.split(anchor)[0]
    nl = nl_of(t)
    body = [
        "## 6. Canary status (2026-10-02): RUN, PASS",
        "",
        "The POST canary ran against the deployed merge `e1fba9733755` (deployment",
        "`5d8b7dcf-8e18-4d59-a947-7424ebb23fae`). All five gates PASS (`CANARY.md`,",
        "`canary-compare.json`, `canary-post.jsonl`):",
        "",
        "* `deploy` - the served commit is the expected `e1fba9733755` (PRE was",
        "  `ca71879d7059`);",
        "* `health` - `/healthz` 200, `/healthz/llm` `llm_ok`;",
        "* `transport` - 8/8 answered 200, non-empty, no refusal;",
        "* `budget` - mean refs 2.50 -> 1.875, in budget 6/8 -> 7/8;",
        "* `integrity` - mean chars 629.2 -> 667.8 (answers did not collapse).",
        "",
        "Transport caveat, recorded because it bounds the claim: BOTH health reads",
        "(PRE and POST) report `provider: openai_wrapper (bedrock fallback)` with",
        "`primary offline (api_status_500: 'No response from Claude Code'); bedrock",
        "fallback active`. The two phases therefore measured the promotion on the",
        "SAME served leg - the Bedrock fallback - so the pre/post delta is",
        "transport-consistent, but it is not yet a confirmation on the",
        "primary-wrapper leg the board gate measured. Re-check on the next deploy",
        "that serves the primary. (`stage2_transport.stats` read 0/0 on the sampled",
        "worker both times, pid 4; it is process-local and not evidence either way.)",
        "",
        "The replicate top-up was attempted twice and is CLOSED without new draws:",
        "",
        "* the wrapper top-up (`r461-countoff-s3`, samples 2-3) was stopped by",
        "  operator directive - wrapper quota burned - and its 31-row partial was",
        "  removed, not resumed into;",
        "* the Bedrock cross-transport replica drew arm A complete (2 draws,",
        "  rerank-ON) and aborted arm B twice at the Cohere trial RERANK monthly",
        "  cap: HTTP 429, 'You are using a Trial key, which is limited to 1000 API",
        "  calls / month', the same on all three keys found across the projects (the",
        "  embed endpoint still answers 200; the per-minute",
        "  `x-trial-endpoint-call-remaining` header is a red herring). Rerank",
        "  reorders the emitted reference list (`rerank_pool`) and the KG-context",
        "  block, so a rerank-OFF arm is a different retrieval condition, not the",
        "  gate's - the operator elected to skip rather than publish a caveated",
        "  read. Arm B partial (7 rows, rerank-ON) is retained for a resume under an",
        "  uncapped key.",
        "",
        "**The standing verdict is therefore the one-draw draw-stable read above**:",
        "rule #8 CLEAN, `ref_conciseness` +7.69 (CI [+1.41, +15.05]) against a floor",
        "of +1.81 - 4.2x the floor point estimate, but `ci_excludes_floor: false`,",
        "so the replicate-stable criterion is NOT met. `DRAW-STABLE-RULE8.md`",
        "SS5/SS8; `GATE-RUN-BEDROCK.log` (local; `*.log` is gitignored) carries the",
        "attempt-by-attempt record.",
        "",
    ]
    write(p, head + block(body, nl))
    return "promotion: patched"


def patch_checkpoint():
    p = ROOT / "docs/measurements/r460/CHECKPOINT.md"
    t = read(p)
    if "## 2026-10-02 (R461.7" in t:
        return "checkpoint: already applied"
    nl = nl_of(t)
    body = [
        "## 2026-10-02 (R461.7 -- round close: canary PASS on the fallback leg, replicate closed without new draws)",
        "",
        "Both R461.3 leftovers are closed.",
        "",
        "* POST canary RUN against the deployed merge `e1fba9733755`: all five gates",
        "  PASS - `deploy` (expected commit), `health`, `transport` (8/8, no",
        "  refusals), `budget` (mean refs 2.50 -> 1.875, in budget 6/8 -> 7/8),",
        "  `integrity` (mean chars 629.2 -> 667.8). `CANARY.md` /",
        "  `canary-compare.json` / `canary-post.jsonl`; PRE commit `ca71879d7059`.",
        "* Recorded caveat: both phases' `/healthz/llm` report `provider:",
        "  openai_wrapper (bedrock fallback)` + `primary offline ('No response from",
        "  Claude Code')`, so the canary measured the promotion on the fallback leg",
        "  in BOTH phases - transport-consistent, but not the primary-wrapper leg",
        "  the board gate measured. Production's primary is still down even though",
        "  the wrapper answers locally; re-run the POST read on the next",
        "  primary-serving deploy.",
        "* Replicate CLOSED without new draws. The wrapper top-up was stopped by",
        "  operator directive (quota) and its 31-row partial removed; the Bedrock",
        "  cross-transport attempt drew arm A complete (2 draws, rerank-ON) and",
        "  aborted arm B at the Cohere trial RERANK monthly cap (429 '1000 API",
        "  calls / month'; all three keys found in the projects capped; the embed",
        "  endpoint still answers 200). Rerank reorders the emitted reference list,",
        "  so rerank-OFF is a different retrieval condition, not the gate's; the",
        "  operator elected to skip the caveated read. Standing verdict = the",
        "  one-draw draw-stable read (rule #8 CLEAN; ref_conciseness +7.69 vs floor",
        "  +1.81, 4.2x, `ci_excludes_floor: false` -> replicate-stable criterion NOT",
        "  met). Arm-B partial (7 rows, rerank-ON) kept for a resume under an",
        "  uncapped key.",
        "* No harness or app code touched this round; docs and canary artifacts",
        "  only. `PROMOTION.md` SS6, `DRAW-STABLE-RULE8.md` SS8;",
        "  `GATE-RUN-BEDROCK.log` is local-only (`*.log` gitignored).",
        "",
    ]
    write(p, t.rstrip(CR + LF) + nl + nl + block(body, nl))
    return "checkpoint: appended"


def patch_drawstable():
    p = ROOT / "docs/measurements/r461/DRAW-STABLE-RULE8.md"
    t = read(p)
    if "## 8. Round close" in t:
        return "drawstable: already applied"
    nl = nl_of(t)
    body = [
        "## 8. Round close (R461.7): the replicate is closed without new draws",
        "",
        "SS5's block lifted (the wrapper token was alive, re-verified), but the",
        "replicate still never ran: the wrapper top-up was stopped by operator",
        "directive (quota) and the Bedrock cross-transport attempt hit the Cohere",
        "trial RERANK monthly cap (HTTP 429, '1000 API calls / month'; all three",
        "keys found in the projects are capped; the embed endpoint still answers",
        "200). Rerank reorders the emitted reference list, so a rerank-OFF arm is a",
        "different retrieval condition, not the gate's; the operator elected to",
        "skip the caveated read. The SS4 verdict stands as the R461 record: CLEAN",
        "draw-stable, `ref_conciseness` 4.2x the floor but `ci_excludes_floor:",
        "false`, i.e. the replicate-stable criterion is NOT met.",
        "",
        "The production canary then ran and PASSED on all five gates - on the",
        "Bedrock fallback leg in both phases, production's primary still being",
        "offline - see `PROMOTION.md` SS6 and `CANARY.md`.",
        "",
    ]
    write(p, t.rstrip(CR + LF) + nl + nl + block(body, nl))
    return "drawstable: appended"


def main():
    print(patch_promotion())
    print(patch_checkpoint())
    print(patch_drawstable())


if __name__ == "__main__":
    main()

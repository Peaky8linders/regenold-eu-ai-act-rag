"""Multi-agent deep code review dispatcher (implements ``CR-SKILL.md`` phases 2-3).

Dispatches specialist reviewer agents IN PARALLEL over a git range, each with a
single review lens, then prints the per-agent report paths so a verifier pass can
adjudicate. Each agent pulls its own diff and reads the code itself, so this
process holds no diff in memory and the agents are free to trace callers.

    .venv/Scripts/python.exe scripts/deep_code_review.py \
        --base f658a49 --head HEAD --out docs/reviews/cr-r416

Design notes
------------
* One process per (lens x partition). The specialist instruction set is the one
  ``CR-SKILL.md`` mandates, including the steering-file staleness caveat and the
  "bugs, not style" rule, so agents do not converge on nitpicks.
* Read-only: agents get ``Bash(git *) Read Grep Glob`` and are told NOT to fix
  anything. Findings are the deliverable; the caller decides what to apply.
* ``--model`` is per-partition so the highest-stakes code (production ``app/``)
  can run on a stronger model than the harness partition without paying for it
  everywhere.
"""

from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The five lenses ``CR-SKILL.md`` mandates, with the extra instructions that
#: skill attaches to two of them.
LENSES: dict[str, str] = {
    "logic": (
        "Wrong conditions, off-by-one errors, null/None paths, state transitions, "
        "algorithm errors, and — importantly — NEW code paths that skip processing, "
        "validation or cleanup that the sibling paths around them perform."
    ),
    "errors": (
        "Missing catches, swallowed exceptions, boundary validation and silent "
        "failures. ALSO: when code parses external output (API responses, LLM "
        "completions, user input) with exact string matching (equals, switch, "
        "regex), check whether realistic output variations — trailing punctuation, "
        "extra whitespace, mixed casing, surrounding formatting — would cause silent "
        "misclassification or a wrong default."
    ),
    "contract": (
        "Signature vs callers, type mismatches, broken API/data contracts, data shape "
        "drift, and logic duplication. ALSO: flag NEW code that reimplements logic "
        "already available in the codebase (check for existing utilities, helpers or "
        "services that do the same thing), and duplicated blocks within the diff that "
        "should be parameterised. Frame duplication as an integration issue — "
        "duplicated logic diverges over time and causes bugs."
    ),
    "concurrency": (
        "Races, shared mutable state, cache invalidation, and ordering assumptions. "
        "Include module-level singletons, ContextVars, in-process caches and their "
        "keys, and anything whose correctness depends on call order."
    ),
    "security": (
        "Injection, authentication/authorisation gaps, data exposure, secret handling, "
        "and OWASP top 10, at the changed input/output boundaries."
    ),
    "euaiac": (
        "EU AI ACT LEGAL CORRECTNESS. Ground every claim in the statute text this repo "
        "ships rather than in memory: `app/data/official_eu_ai_act.py` (the EUR-Lex text), "
        "`app/data/eu_ai_act_tree.py`, `app/data/article_requirements_full.py`, "
        "`app/data/article_existence.py`, `app/data/definitions.py`, "
        "`app/data/eu_ai_act_corpus.py`. Hunt: provision numbers that do not exist or are "
        "misnumbered; a duty attached to the WRONG ROLE (provider / deployer / importer / "
        "distributor / authorised representative / GPAI provider); prohibitions vs "
        "high-risk confusion; a rule that cites a parent article where the Act's operative "
        "limb is a specific subpoint (or vice versa); requirement→article mappings that "
        "contradict the Act (QMS→Art. 17, technical documentation→Art. 11, data "
        "governance→Art. 10, human oversight→Art. 14, FRIA→Art. 27, post-market "
        "monitoring→Art. 72, serious-incident reporting→Art. 73, registration→Art. 49, "
        "transparency→Art. 50, GPAI→Arts. 53-55); thresholds, dates, Annex III subpoint "
        "numbers and Annex I legislation that are wrong. Quote the exact provision that "
        "contradicts the code."
    ),
    "kg": (
        "KNOWLEDGE GRAPH INTEGRITY. The live store is Neo4j Aura; the code is "
        "`app/engines/kg_context.py`, the graph-expansion/fusion paths in "
        "`app/engines/_graph_rag_impl.py`, `app/engines/graph_semantic.py`, "
        "`scripts/seed_neo4j_kb.py`. Hunt: Cypher whose MATCH pattern cannot match the real "
        "schema (a required node or edge that does not exist for the common case, so the "
        "query returns 0 rows); label/property names that drifted from the seeder; "
        "ORDER/LIMIT that silently drops operative provisions; traversal that requires a "
        "SubPoint where the graph stores bare Points; the in-process mirror and the live "
        "query disagreeing in shape or budget; connection/timeout paths that swallow the "
        "error and return an EMPTY context, so retrieval silently produces nothing and the "
        "failure is indistinguishable from 'no provisions found'."
    ),
    "ontology": (
        "ONTOLOGY AND DATA-MODEL CONSISTENCY. `app/data/ontology.py`, "
        "`app/data/role_obligations.py`, `app/data/ids.py`, `app/data/eu_ai_act_tree.py`, "
        "`trustgraph-integration/knowledge/eu-ai-act-core.ttl` and its generator "
        "`scripts/build_trustgraph_core.py`. Hunt: role→article maps that list provisions "
        "imposing no duty on that role (or omit ones that do); requirement anchors that "
        "contradict the Act; identifier/canonicalisation drift — the same provision written "
        "two ways (`Art. 6` vs `Article 6`, `Annex III.1.a` vs `Annex III(1)(a)` vs "
        "`Annex III point 1(a)`) — that silently misses a join, a lookup or a de-duplication, "
        "or that lets one node be cited twice under two spellings; a generated artifact "
        "disagreeing with the Python it is generated from; alias/vocabulary tables mapping a "
        "concept to the wrong provision."
    ),
}

PROMPT = """You are a specialist code reviewer. Your ONLY lens is:

{lens}

Repository root: {repo}
Review range: `{base}..{head}` (this is the diff you are reviewing)

FILES IN YOUR SCOPE — review ONLY these; read them in full at HEAD:
{files}

METHOD (follow it; do not skip steps)
1. `git diff {base}..{head} -- <the files above>` to see exactly what changed.
2. Read each changed file at HEAD wherever the diff is not self-explanatory.
3. For EVERY changed function, grep the repo for its callers and callees and trace
   them ONE LEVEL DEEP. The most valuable bugs sit at integration boundaries.
4. Read the adjacent test files that cover the changed code. A test that passes
   accidentally (catch-all mock, wrong stub, assertion that cannot fail) is a real
   finding.

RULES
- Hunt BUGS, not style or quality nits. "Missing test" is at most a suggestion.
- Every finding MUST cite `path:line` and be verifiable by reading the code.
- Only report findings you are at least 60% confident about. Say why it matters.
- Do NOT fix anything and do NOT edit any file. The report is the deliverable.
- Steering files (CLAUDE.md, AGENTS.md) describe conventions but may be stale. If a
  steering file contradicts the actual code, report THAT as a finding.

OUTPUT — markdown only, no preamble, one section per finding:

## <one-line title>
- file: `path:line`
- bug: <what is wrong, concretely>
- impact: <what it breaks, and how you would notice>
- fix: <concrete suggested change>
- confidence: <60-100>

If you find nothing worth reporting, print exactly: NO FINDINGS
"""


def _run_agent(
    name: str, lens_key: str, files: list[str], *, base: str, head: str,
    model: str, out_dir: Path,
) -> tuple[str, int, Path]:
    dest = out_dir / f"{name}.md"
    prompt = PROMPT.format(
        lens=LENSES[lens_key],
        repo=REPO,
        base=base,
        head=head,
        files="\n".join(f"  {f}" for f in files),
    )
    with dest.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", model,
                "--allowedTools", "Bash(git *)", "Read", "Grep", "Glob",
                "--output-format", "text",
            ],
            cwd=str(REPO),
            stdin=subprocess.DEVNULL,
            stdout=fh,
            stderr=subprocess.PIPE,
            text=True,
        )
    return name, proc.returncode, dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--out", default="docs/reviews/cr-run")
    ap.add_argument("--app-model", default="opus")
    ap.add_argument("--harness-model", default="sonnet")
    ap.add_argument("--only", default="", help="comma-separated lens keys")
    # One claude CLI process per job, all at once by default. A saturated
    # wrapper answers nothing useful, so the cap is explicit and reported.
    ap.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="max concurrent agents (0 = all jobs at once)",
    )
    a = ap.parse_args()

    app_files = subprocess.run(
        ["git", "diff", "--name-only", f"{a.base}..{a.head}", "--", "app/"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    ).stdout.split()
    harness_files = subprocess.run(
        ["git", "diff", "--name-only", f"{a.base}..{a.head}", "--", "evals/", "tests/"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    ).stdout.split()
    if not app_files and not harness_files:
        print("empty diff — nothing to review")
        return 1

    out_dir = REPO / a.out
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = [k for k in LENSES if k in (a.only.split(",") if a.only else list(LENSES))]

    jobs = []
    for key in wanted:
        if app_files:
            jobs.append((f"{key}-app", key, app_files, a.app_model))
        if harness_files:
            jobs.append((f"{key}-harness", key, harness_files, a.harness_model))

    print(f"dispatching {len(jobs)} specialist agents in parallel -> {a.out}/", flush=True)
    for name, _key, files, model in jobs:
        print(f"  {name:<20} model={model:<8} files={len(files)}", flush=True)

    workers = len(jobs) if a.jobs <= 0 else min(a.jobs, len(jobs))
    print(f"concurrency: {workers} of {len(jobs)} jobs", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                _run_agent, name, key, files,
                base=a.base, head=a.head, model=model, out_dir=out_dir,
            )
            for name, key, files, model in jobs
        ]
        for fut in futures:
            name, rc, dest = fut.result()
            flag = "ok" if rc == 0 else f"rc={rc}"
            body = dest.read_text(encoding="utf-8", errors="replace")
            n = body.count("\n## ") + (1 if body.lstrip().startswith("## ") else 0)
            print(f"  {name:<20} {flag:<8} findings~{n}  {dest.relative_to(REPO)}", flush=True)

    print("\nNEXT: verify each finding against the code, drop the false positives, then fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Specialised code review over an HTTP transport (no local CLI needed).

``scripts/deep_code_review.py`` gives each reviewer git/read tools. When the
local ``claude`` CLI is rate-limited that path is unavailable, and this sibling
takes the opposite approach: it INLINES an evidence pack, so the agent needs no
tools at all. The packs are built from the repository's own sources, and the
rules require every legal finding to quote the provision it contradicts — an
agent that cannot cite the Act cannot report a legal bug.

    .venv/Scripts/python.exe scripts/deep_code_review_api.py \
        --base 04aa6c9 --head 4d36f3a --out docs/reviews/cr-r421-api

Lenses: ``euaiac`` (EU AI Act legal correctness), ``kg`` (Neo4j/KG integrity),
``ontology`` (ontology + data-model consistency). The three share one evidence
design: the production diff, plus the tables the code consults, plus the
verbatim text of every provision the diff names.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[1]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PACK_BUDGET = 180_000  # characters per agent, evidence + diff
PROVISION_BUDGET = 40_000  # characters of verbatim statute text
PROVISION_LIMIT = 24  # provisions inlined

LENSES: dict[str, str] = {
    "euaiac": (
        "EU AI ACT LEGAL CORRECTNESS. You are reviewing a retrieval-augmented system that "
        "answers EU AI Act questions. Judge the code's LEGAL CONTENT, not its style.\n"
        "Hunt: provision numbers that do not exist or are misnumbered; a duty attached to the "
        "WRONG ROLE (provider, deployer, importer, distributor, authorised representative, GPAI "
        "provider, notified body); prohibited-practice vs high-risk confusion; a rule that cites "
        "a parent article where the Act's operative limb is a specific subpoint, or the reverse; "
        "requirement-to-article mappings that contradict the Act (QMS -> Art. 17, technical "
        "documentation -> Art. 11, data governance -> Art. 10, human oversight -> Art. 14, FRIA "
        "-> Art. 27, post-market monitoring -> Art. 72, serious-incident reporting -> Art. 73, "
        "registration -> Art. 49, transparency -> Art. 50, GPAI -> Arts. 53-55); wrong Annex III "
        "subpoint numbers; wrong thresholds, dates, or Annex I legislation; obligations that "
        "live in a different Article than the code claims."
    ),
    "kg": (
        "KNOWLEDGE GRAPH INTEGRITY. The live store is Neo4j Aura and the code also keeps an "
        "in-process mirror. Judge the GRAPH ACCESS, not its style.\n"
        "Hunt: Cypher whose MATCH pattern cannot match the real schema (a required node label or "
        "relationship type that does not exist for the common case, so the query returns 0 "
        "rows); label/property names that drifted from the seeder; ORDER BY / LIMIT that silently "
        "drops operative provisions; traversal that requires a SubPoint where the graph stores "
        "bare Points; the mirror and the live query disagreeing in shape, grain or budget, so the "
        "same question retrieves different law online and offline; connection or timeout paths "
        "that swallow the error and return an EMPTY context, making 'the graph is down' "
        "indistinguishable from 'no provisions matched'."
    ),
    "ontology": (
        "ONTOLOGY AND DATA-MODEL CONSISTENCY. Judge the IDENTITY of the things this system "
        "reasons over, not its style.\n"
        "Hunt: role-to-article maps that list provisions imposing no duty on that role, or omit "
        "ones that do; requirement anchors that contradict the Act; identifier/canonicalisation "
        "drift — the same provision written two ways (`Art. 6` vs `Article 6`, `Annex III.1.a` "
        "vs `Annex III(1)(a)` vs `Annex III point 1(a)`, `Article 5(1)(f)` vs `Article 5.1.f`) — "
        "that silently misses a join, a lookup or a de-duplication, or lets one provision be "
        "counted twice under two spellings; a generated artifact disagreeing with the Python it "
        "is generated from; alias or vocabulary tables mapping a concept to the wrong provision; "
        "an enum whose membership disagrees with what the Act enumerates."
    ),
}

#: Evidence files per lens: ``(path, regex-or-None)``. ``None`` inlines the whole
#: file; a regex inlines windows around its matches (for files too large to
#: inline whole).
PACKS: dict[str, list[tuple[str, str | None]]] = {
    "euaiac": [
        ("app/data/article_existence.py", None),
        ("app/data/role_obligations.py", None),
        ("app/data/article_requirements_full.py", None),
        ("app/data/definitions.py", None),
    ],
    "kg": [
        ("app/engines/graph_rag/models.py", None),
        ("app/engines/graph_semantic.py", None),
        ("app/engines/kg_context.py", r"CYPHER|MATCH |_mirror|def |SUBPoint|Point|RELATED"),
        ("scripts/seed_neo4j_kb.py", r"MERGE|CREATE|LABEL|REL|:.*\)"),
    ],
    "ontology": [
        ("app/data/ids.py", None),
        ("app/data/eu_ai_act_tree.py", None),
        ("app/data/ontology.py", None),
        ("scripts/build_trustgraph_core.py", None),
        ("trustgraph-integration/knowledge/eu-ai-act-core.ttl", r"^@prefix|^euai:|^rdfs:"),
    ],
}

PROMPT = """You are a specialist reviewer of an EU AI Act question-answering system, working
under ONE lens:

{lens}

Repository: {repo}   Review range: `{base}..{head}`

You have NO file access: everything you may rely on is inlined below. Do not ask
for more files and do not speculate about code you cannot see.

METHOD
1. Read the DIFF first: it is the change under review.
2. Read the EVIDENCE PACK: the repository's own statute tables and the verbatim
   text of the provisions the diff names. These are the ground truth, NOT your
   memory of the Act.
3. For each suspected defect, check it against the EVIDENCE, then state it.

RULES — read these before you read the diff. The first one is the one that
separates a real finding from a fabricated one.

1. EVIDENCE IS THE STATUTE OR THE TABLE, NEVER A COMMENT. A comment, docstring,
   changelog, checkpoint or report inside this repository is NOT evidence: those
   describe what the code INTENDS or what was already fixed. You MUST NOT report
   a defect that a repository comment describes — in particular, never quote a
   comment such as "this used to do X, which was wrong" as proof that the code
   still does X. Before reporting anything, quote the CURRENT CODE LINE that
   exhibits the bug and show that the defect is live at {head}.
2. For a legal claim, also quote the provision text from the evidence pack that
   the code contradicts. A legal claim with no provision quote is not a finding.
3. Hunt BUGS with legal or behavioural consequences, not style or missing tests.
   A comment whose wording is merely loose is NOT a finding unless you can show a
   code path that behaves wrongly because of it.
4. Do not report anything you are less than 60% confident about.
5. If the evidence pack does not contain what you would need to check a claim,
   say so under a heading "NEEDS MORE EVIDENCE" instead of guessing.
6. Do NOT propose edits to files you have not seen.

OUTPUT — markdown only, no preamble. If you find nothing that survives the rules,
print exactly `NO FINDINGS`. Otherwise one section per finding:

## <one-line title>
- file: `path:line`
- current code: <quote the line(s) at {head} that exhibit the bug>
- bug: <what is wrong, concretely>
- evidence: <the verbatim provision or table row that contradicts it>
- impact: <what it breaks, and how you would notice>
- fix: <concrete suggested change>
- confidence: <60-100>

Then a final section "## NEEDS MORE EVIDENCE" (may be empty).

Finally, a section "## CHECKS PERFORMED": for each of the three most plausible
false alarms you considered and REJECTED, one line: the claim, and the code that
refuted it. This section is required even when you report no findings.

---
{evidence}
"""


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, check=True).stdout


def _windowed(text: str, pattern: str, radius: int = 6, limit: int = 400) -> str:
    """Windows of ``text`` around ``pattern`` matches, with line numbers."""
    lines = text.splitlines()
    rx = re.compile(pattern)
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if rx.search(line):
            keep.update(range(max(0, i - radius), min(len(lines), i + radius + 1)))
    out: list[str] = []
    prev = -2
    for i in sorted(keep):
        if i != prev + 1:
            out.append("    ...")
        out.append(f"{i + 1:>6}: {lines[i]}")
        prev = i
        if len(out) > limit:
            out.append("    ... (truncated)")
            break
    return "\n".join(out)


def _file_block(path: str, pattern: str | None, budget: int) -> str:
    p = REPO / path
    if not p.exists():
        return f"### {path}\n_(absent)_\n"
    text = p.read_text(encoding="utf-8", errors="replace")
    if pattern and len(text) > 40_000:
        body = _windowed(text, pattern)
    else:
        body = text
    if len(body) > budget:
        body = body[:budget] + "\n… (truncated)\n"
    return f"### {path}\n```\n{body}\n```\n"


def _provision_pack(diff: str) -> str:
    """Verbatim Act text for the provisions the diff names."""
    sys.path.insert(0, str(REPO))
    try:
        from app.data.official_eu_ai_act import OFFICIAL_ARTICLE_TEXT  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return f"_(statute text unavailable: {exc})_\n"
    wanted = sorted(
        {
            m
            for m in re.findall(
                r"\bArticle\s+\d{1,3}(?:\(\d+\)|\.\d+)*|\bAnnex\s+[IVX]+(?:\(\d+\)|\.\w+)*",
                diff,
            )
        }
    )
    refs: list[str] = []
    for w in wanted:
        head = re.sub(r"[\(.].*$", "", w).strip()
        if head and head not in refs:
            refs.append(head)
    out: list[str] = []
    used = 0
    for head in refs[:PROVISION_LIMIT]:
        text = OFFICIAL_ARTICLE_TEXT.get(head)
        if not text:
            continue
        if used + len(text) > PROVISION_BUDGET:
            break
        used += len(text)
        out.append(f"#### {head}\n{text}\n")
    return "\n".join(out) or "_(no provision text matched)_\n"


def _diff(base: str, head: str) -> str:
    return _run(["git", "diff", f"{base}..{head}", "--", "app/", "scripts/"])


def _build_evidence(lens_key: str, base: str, head: str) -> str:
    parts: list[str] = []
    parts.append("## DIFF under review\n```diff\n" + _diff(base, head) + "\n```\n")
    if lens_key == "euaiac":
        parts.append("## VERBATIM STATUTE TEXT (ground truth)\n" + _provision_pack(_diff(base, head)))
    parts.append("## EVIDENCE PACK (repository tables)\n")
    share = max(PACK_BUDGET // max(len(PACKS[lens_key]), 1), 20_000)
    for path, pattern in PACKS[lens_key]:
        parts.append(_file_block(path, pattern, share))
    return "\n".join(parts)


def _call(prompt: str, model: str, key: str, timeout: float = 900.0) -> tuple[str, dict]:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 8000,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = (data.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()
    return text, data.get("usage") or {}


def _run_lens(lens_key: str, args, key: str, out_dir: pathlib.Path) -> tuple[str, str, dict]:
    evidence = _build_evidence(lens_key, args.base, args.head)
    prompt = PROMPT.format(
        lens=LENSES[lens_key],
        repo=REPO,
        base=args.base,
        head=args.head,
        evidence=evidence,
    )
    (out_dir / f"{lens_key}.prompt.txt").write_text(prompt, encoding="utf-8")
    try:
        text, usage = _call(prompt, args.model, key)
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        text, usage = f"_(HTTP {exc.code}: {exc.read()[:400]!r})_", {}
    except Exception as exc:  # noqa: BLE001
        text, usage = f"_(call failed: {exc})_", {}
    (out_dir / f"{lens_key}.md").write_text(text + "\n", encoding="utf-8")
    return lens_key, text, usage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--out", default="docs/reviews/cr-api")
    ap.add_argument("--model", default="qwen/qwen3-235b-a22b-2507")
    ap.add_argument("--only", default="", help="comma-separated lens keys")
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("OPENROUTER_API_KEY is not set")
        return 2

    out_dir = REPO / a.out
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = [k for k in LENSES if k in (a.only.split(",") if a.only else list(LENSES))]
    print(f"dispatching {len(wanted)} specialist agents over {a.model} -> {a.out}/", flush=True)
    for k in wanted:
        ev = _build_evidence(k, a.base, a.head)
        print(f"  {k:<10} evidence {len(ev):,} chars", flush=True)

    with ThreadPoolExecutor(max_workers=min(a.jobs, len(wanted))) as pool:
        for lens_key, text, usage in pool.map(
            lambda k: _run_lens(k, a, key, out_dir), wanted
        ):
            n = text.count("\n## ") + (1 if text.lstrip().startswith("## ") else 0)
            print(
                f"  {lens_key:<10} findings~{n:<3} "
                f"tokens={(usage or {}).get('completion_tokens', '?')} "
                f"{out_dir.relative_to(REPO) / (lens_key + '.md')}",
                flush=True,
            )
    print("\nNEXT: verify each finding against the code, drop the false positives, then fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

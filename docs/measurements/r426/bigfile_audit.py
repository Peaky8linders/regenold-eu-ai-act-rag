"""R426 — a deterministic audit of the repo's largest Python modules.

WHY THIS EXISTS. "Simplify the big files" is not a plan. The two production
monsters are `app/engines/_graph_rag_impl.py` (~12.9 kLOC) and
`app/routes/regenold.py` (~12.8 kLOC), and the safe first tranche of any
simplification is the part that cannot change behaviour because nothing calls it:
unreferenced top-level definitions, and the same helper implemented twice. This
module measures both, from the AST, so the proposal is a list of names with
evidence rather than an opinion about style.

WHAT IT REPORTS

1. **Structure** — LOC, top-level def/class counts, and the largest functions, so
   "which file is big" becomes "which FUNCTIONS are big".
2. **Unreferenced top-level names** — defined in a target module and appearing in
   no other file's identifiers or text. Decorated callables are reported
   separately, because a FastAPI route, a `pytest.fixture`, or a registry entry
   reaches a function without ever naming it in a call.
3. **Cross-module duplicates** — the same top-level name defined in more than one
   module, with a body-similarity ratio, so "repeated code" is measured.

A name is only a DELETION CANDIDATE here, never a deletion: every candidate has to
be re-checked by hand against dynamic dispatch, entry points and docs before it is
removed. The audit prints the reference evidence it used.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r426.bigfile_audit
    .venv\\Scripts\\python.exe -m docs.measurements.r426.bigfile_audit --top 20 --json
"""
from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
SCAN_DIRS = ("app", "evals", "tests", "scripts")
TEXT_SUFFIXES = (".py", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ttl", ".cypher")
#: Decorators that mean "reached without being named".
DYNAMIC_DECORATORS = (
    "app.",
    "router.",
    "pytest.fixture",
    "fixture",
    "staticmethod",
    "classmethod",
    "property",
    "lru_cache",
    "contextmanager",
    "atexit",
)


def _files() -> list[Path]:
    out: list[Path] = []
    for d in SCAN_DIRS:
        out.extend(p for p in (REPO / d).rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(out)


def _candidate_files() -> list[Path]:
    """Files that could reference a name, WITHOUT walking .venv/.claude/docs.

    A whole-repo ``rglob`` is what made the first version time out: the virtualenv
    and the other threads' `.claude/worktrees` copies are inside the checkout, and
    `docs/measurements` holds tens of MB of JSONL evidence. Reference detection
    only needs the code, the tests, the scripts and the root-level docs/config.
    """
    roots: list[Path] = [REPO / d for d in SCAN_DIRS]
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if any(part in ("__pycache__", ".venv", "worktrees") for part in path.parts):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            out.append(path)
    out.extend(
        p
        for p in REPO.iterdir()
        if p.is_file() and p.suffix in (".md", ".toml", ".cfg", ".ini")
    )
    return sorted(set(out))


def _tokens_by_file() -> dict[Path, set[str]]:
    """Per-file identifier sets, so "referenced" can be asked per defining file.

    Counting GLOBALLY is not enough and excluding the target is worse: a helper
    used only inside its own module counts as referenced in that module, and a
    helper the ROUTE calls in the ENGINE counts as referenced from another file.
    So the corpus keeps both, and each candidate is asked two questions: is it
    used again in its own file, and is it used anywhere else.
    """
    out: dict[Path, set[str]] = {}
    for path in _candidate_files():
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        toks: set[str] = set()
        for tok in raw.replace("(", " ").replace(",", " ").replace("=", " ").split():
            toks.add(tok.strip("\"'`#:;[]{}"))
        if path.suffix == ".py":
            try:
                tree = ast.parse(raw)
            except SyntaxError:
                out[path] = toks
                continue
            toks.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
            toks.update(node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute))
            toks.update(
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            )
        out[path] = toks
    return out


def _top_level_defs(tree: ast.Module) -> list[tuple[str, int, int, bool]]:
    """``(name, start, end, is_dynamic)`` for every top-level definition."""
    out: list[tuple[str, int, int, bool]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            decs = [
                ast.unparse(d) if hasattr(ast, "unparse") else ""
                for d in getattr(node, "decorator_list", [])
            ]
            dynamic = any(any(key in d for key in DYNAMIC_DECORATORS) for d in decs)
            if isinstance(node, ast.ClassDef) and any(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name.startswith("test_")
                for n in node.body
            ):
                # pytest collects it by module scan; nothing ever names it.
                dynamic = True
            end = max(
                (getattr(n, "lineno", node.lineno) for n in ast.walk(node)), default=node.lineno
            )
            out.append((node.name, node.lineno, end, dynamic))
    return out


def _body_src(lines: list[str], node_start: int, node_end: int) -> str:
    return "\n".join(lines[node_start - 1 : node_end])


def audit(top: int) -> dict[str, Any]:
    files = _files()
    sizes = sorted(
        ((sum(1 for _ in p.open(encoding="utf-8", errors="replace")), p) for p in files),
        reverse=True,
    )
    targets = [p for _, p in sizes[:top]]
    per_file = _tokens_by_file()

    report: dict[str, Any] = {"files": [], "duplicates": [], "largest_functions": []}
    defs_by_name: dict[str, list[tuple[Path, int, int, str]]] = {}

    for path in targets:
        src = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            report["files"].append({"path": str(path.relative_to(REPO)), "error": str(exc)})
            continue
        loc = src.count("\n") + 1
        src_lines = src.splitlines()
        defs = _top_level_defs(tree)
        # References from every OTHER file (code, tests, scripts, root docs).
        elsewhere: set[str] = set()
        for other, toks in per_file.items():
            if other != path:
                elsewhere |= toks
        entry: dict[str, Any] = {
            "path": str(path.relative_to(REPO)),
            "loc": loc,
            "top_level_defs": len(defs),
            "top_level_classes": sum(
                1 for n in tree.body if isinstance(n, ast.ClassDef)
            ),
            "unreferenced": [],
            "unreferenced_decorated": [],
        }
        for name, start, end, dynamic in defs:
            defs_by_name.setdefault(name, []).append(
                (path, start, end, _body_src(src_lines, start, end))
            )
            size = end - start + 1
            report["largest_functions"].append(
                {"path": str(path.relative_to(REPO)), "name": name, "lines": size}
            )
            if name.startswith("__") or name in ("main", "cli"):
                continue
            if name in elsewhere:
                continue
            # Used again inside its own module? One occurrence is the `def` line.
            own_uses = len(re.findall(rf"\b{re.escape(name)}\b", src))
            if own_uses > 1:
                continue
            (entry["unreferenced_decorated"] if dynamic else entry["unreferenced"]).append(
                {"name": name, "line": start, "lines": size, "own_uses": own_uses}
            )
        report["files"].append(entry)

    for name, sites in sorted(defs_by_name.items()):
        if len(sites) < 2 or name.startswith("__"):
            continue
        best = 0.0
        for i in range(len(sites)):
            for j in range(i + 1, len(sites)):
                ratio = difflib.SequenceMatcher(
                    None, sites[i][3], sites[j][3]
                ).quick_ratio()
                best = max(best, ratio)
        report["duplicates"].append(
            {
                "name": name,
                "sites": [f"{p.relative_to(REPO)}:{s}" for p, s, _, _ in sites],
                "max_body_similarity": round(best, 3),
            }
        )
    report["largest_functions"] = sorted(
        report["largest_functions"], key=lambda r: r["lines"], reverse=True
    )[:25]
    # The structural prize: how much of each file sits in functions no human can
    # hold in their head. 150 lines is the threshold this repo's own review
    # culture already treats as "needs splitting".
    giant = [
        r for r in report["largest_functions"] if r["lines"] >= 150
    ]
    report["giant_functions"] = {
        "count": len(giant),
        "loc": sum(r["lines"] for r in giant),
        "top": giant[:12],
    }
    return report


def render(report: dict[str, Any]) -> None:
    print("=" * 92)
    print("R426 — largest-module audit (deterministic, AST-based)")
    print("=" * 92)
    print(
        f"{'module':<46}{'LOC':>8}{'defs':>7}{'classes':>9}"
        f"{'unref':>7}{'unref LOC':>11}{'unref@':>8}"
    )
    for f in report["files"]:
        if "error" in f:
            print(f"{f['path']:<46}  parse error: {f['error']}")
            continue
        dead_loc = sum(u["lines"] for u in f["unreferenced"])
        print(
            f"{f['path']:<46}{f['loc']:>8}{f['top_level_defs']:>7}"
            f"{f['top_level_classes']:>9}{len(f['unreferenced']):>7}"
            f"{dead_loc:>11}{len(f['unreferenced_decorated']):>8}"
        )
    print()
    print("-- largest functions in those modules " + "-" * 50)
    for r in report["largest_functions"]:
        print(f"  {r['lines']:>5}  {r['path']}:{r['name']}")
    print()
    print("-- unreferenced top-level names (deletion CANDIDATES, verify first) " + "-" * 12)
    for f in report["files"]:
        if f.get("unreferenced"):
            print(f"  {f['path']}")
            for u in sorted(f["unreferenced"], key=lambda u: -u["lines"]):
                print(f"      {u['lines']:>5} lines  {u['name']}  (line {u['line']})")
    print()
    print("-- unreferenced but DECORATED (never delete without checking the decorator) -")
    for f in report["files"]:
        if f.get("unreferenced_decorated"):
            print(f"  {f['path']}: {[u['name'] for u in f['unreferenced_decorated']]}")
    print()
    g = report["giant_functions"]
    print(
        f"-- functions >= 150 lines: {g['count']} holding {g['loc']} LOC "
        + "-" * 20
    )
    for r in g["top"]:
        print(f"  {r['lines']:>5}  {r['path']}:{r['name']}")
    print()
    print("-- same name defined in 2+ modules (repetition measure) " + "-" * 30)
    for d in sorted(report["duplicates"], key=lambda d: -d["max_body_similarity"]):
        print(f"  {d['max_body_similarity']:.2f}  {d['name']}")
        for s in d["sites"]:
            print(f"          {s}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12, help="how many of the largest files")
    ap.add_argument("--json", action="store_true", help="also write the JSON artifact")
    args = ap.parse_args()
    report = audit(args.top)
    render(report)
    if args.json:
        out = Path(__file__).resolve().parent / "bigfile_audit.json"
        out.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

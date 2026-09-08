"""R394.2 — every ``app.*`` module a COMMITTED file imports must itself be COMMITTED.

This test exists because of a production outage, not a hypothetical.

Commit ``303b81a`` (PR #389) extracted ``_shrink_user_for_groq`` out of
``app/engines/_graph_rag_impl.py`` into a new ``app/engines/prompt_budget.py``
and replaced the body with::

    from app.engines.prompt_budget import _shrink_user_for_groq

The new file was never ``git add``-ed. Nothing on the developer's box noticed:
the working tree HAD the file, so ``pytest tests/`` passed 7,525/7,525 and every
local import succeeded. But Railway deploys from a **git clone**, where the
module does not exist — so ``import app.main`` raised ``ModuleNotFoundError``,
``/healthz`` never bound, the healthcheck failed, and production stayed pinned
on the previous commit. Measured: 25 of 145 ``app`` modules failed to import in
a tracked-files-only checkout, all from that one line.

The failure is invisible to every other instrument in this repo *by
construction*: a test suite runs against the working tree, and the working tree
is exactly where the untracked file lives. The only view that can see it is
git's own object store.

So the gate reads git, not the filesystem. For every ``app/**/*.py`` **as
committed at HEAD** it parses the AST, collects each ``import app.x.y`` /
``from app.x.y import ...`` target (relative imports resolved against the file's
own package), and asserts the module part resolves to a path that exists at
HEAD. Two ``git`` calls and an AST walk — no imports are executed, no network.

Why HEAD and not the working tree: Railway deploys a *pushed commit*, so "the
committed tree is self-consistent" is the exact contract, and gating on it can
never be reddened by an unfinished local refactor. The working tree gets a
second, softer pass (:func:`test_working_tree_is_not_staging_the_same_defect`)
which warns rather than fails while a file is genuinely mid-edit — that pass is
what surfaced a *second* live instance of this same defect the day the gate was
written.

SCOPE, stated honestly: this catches an untracked *module*. It does not catch an
untracked *data file* opened at runtime, nor a third-party package missing from
``requirements.txt``. Those are different failure modes with different fixes.
"""

from __future__ import annotations

import ast
import subprocess
import warnings
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            check=True,
            timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"git unavailable or not a git checkout ({exc}) — nothing to compare against")


def _head_paths() -> frozenset[str]:
    """Every path in the HEAD commit, forward-slash and repo-relative."""
    out = _git("ls-tree", "-r", "--name-only", "-z", "HEAD")
    return frozenset(p.decode("utf-8") for p in out.split(b"\0") if p)


def _head_sources(paths: list[str]) -> dict[str, str]:
    """Read many blobs out of HEAD in ONE ``git cat-file --batch`` call.

    Per-file ``git show`` would be ~145 subprocesses; this is one.
    """
    if not paths:
        return {}
    stdin = "".join(f"HEAD:{p}\n" for p in paths).encode("utf-8")
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=_REPO_ROOT,
        input=stdin,
        capture_output=True,
        check=True,
        timeout=120,
    )
    buf, out, idx = proc.stdout, {}, 0
    for path in paths:
        nl = buf.index(b"\n", idx)
        header = buf[idx:nl].decode("utf-8")
        # "<sha> <type> <size>" for a hit; "<name> missing" otherwise.
        if header.endswith(" missing"):
            idx = nl + 1
            continue
        size = int(header.rsplit(" ", 1)[1])
        body = buf[nl + 1 : nl + 1 + size]
        out[path] = body.decode("utf-8", errors="replace")
        idx = nl + 1 + size + 1  # trailing newline after the blob
    return out


def _package_of(rel: str) -> str:
    """The dotted package a ``app/**/*.py`` file resolves ``.`` against.

    Python anchors a relative import on the importing file's *package*. For a
    plain module that is its containing directory; for a package ``__init__.py``
    it is the package itself — ``from . import config`` inside
    ``app/engines/graph_rag/__init__.py`` means ``app.engines.graph_rag.config``,
    not ``app.engines.config``. Collapsing those two cases yields wrong dotted
    names and therefore false violations, so they are kept distinct here.
    """
    parts = rel[:-3].split("/")  # drop ".py"
    return ".".join(parts[:-1])  # both cases drop the last component


def _module_targets(tree: ast.AST, package: str) -> list[tuple[str, int]]:
    """Return ``(dotted_module, lineno)`` for every ``app.*`` import target.

    ``package`` is the dotted package relative imports anchor on (see
    :func:`_package_of`).

    For ``from X import a, b`` only ``X`` is returned: ``a``/``b`` are usually
    symbols, not submodules, so requiring them to resolve as files would be a
    false positive. ``X`` is exactly the part that must exist as a module — and
    it is the part that was missing in the R394.1 outage.
    """
    pkg_parts = package.split(".") if package else []
    targets: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app" or alias.name.startswith("app."):
                    targets.append((alias.name, node.lineno))

        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level 1 == this package; each further dot strips one component.
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                if not base:
                    continue  # escapes the package root; not an app.* target
                dotted = ".".join(base + ([node.module] if node.module else []))
            else:
                dotted = node.module or ""
            if dotted == "app" or dotted.startswith("app."):
                targets.append((dotted, node.lineno))

    return targets


def _resolves(dotted: str, universe: frozenset[str]) -> bool:
    """True when ``dotted`` maps to a ``.py`` file or package init in ``universe``."""
    stem = dotted.replace(".", "/")
    return f"{stem}.py" in universe or f"{stem}/__init__.py" in universe


def _violations(sources: dict[str, str], universe: frozenset[str]) -> list[str]:
    out: list[str] = []
    for rel in sorted(sources):
        try:
            tree = ast.parse(sources[rel], filename=rel)
        except SyntaxError as exc:  # pragma: no cover - a syntax error fails elsewhere too
            out.append(f"{rel}:{exc.lineno}: does not parse: {exc.msg}")
            continue
        for dotted, lineno in _module_targets(tree, _package_of(rel)):
            if not _resolves(dotted, universe):
                on_disk = (_REPO_ROOT / (dotted.replace(".", "/") + ".py")).exists()
                why = (
                    "exists on disk but is NOT in git - run `git add` on it"
                    if on_disk
                    else "does not exist at all"
                )
                out.append(f"{rel}:{lineno}: imports `{dotted}`, which {why}")
    return out


def test_every_app_import_target_exists_in_the_committed_tree() -> None:
    """THE GATE. What git hands Railway must be importable."""
    head = _head_paths()
    app_modules = sorted(p for p in head if p.startswith("app/") and p.endswith(".py"))
    assert app_modules, "no app/*.py files at HEAD — the gate would pass vacuously"

    violations = _violations(_head_sources(app_modules), head)

    assert not violations, (
        "A committed module imports an app module that is not in the commit. A "
        "clone-based deploy (Railway) raises ModuleNotFoundError at import and the "
        "healthcheck never comes up, even though the full local suite passes "
        "because the working tree still has the file:\n  " + "\n  ".join(violations)
    )


def test_working_tree_is_not_staging_the_same_defect() -> None:
    """Early warning: the same check one step before the commit.

    A file that is mid-edit is allowed to be inconsistent — that is what an
    unfinished refactor looks like — so those only WARN. A violation in a file
    with no local modifications is a real committed defect and fails.
    """
    tracked = frozenset(
        p.decode("utf-8") for p in _git("ls-files", "-z").split(b"\0") if p
    )
    dirty = {
        line[3:].decode("utf-8").strip('"')
        for line in _git("status", "--porcelain").splitlines()
        if line[3:]
    }

    sources: dict[str, str] = {}
    for rel in sorted(p for p in tracked if p.startswith("app/") and p.endswith(".py")):
        path = _REPO_ROOT / rel
        if path.exists():  # tracked-but-deleted is a different defect
            sources[rel] = path.read_text(encoding="utf-8")

    violations = _violations(sources, tracked)
    wip = [v for v in violations if v.split(":", 1)[0] in dirty]
    committed = [v for v in violations if v.split(":", 1)[0] not in dirty]

    if wip:
        warnings.warn(
            "Uncommitted work imports an app module that is not in git. Commit it "
            "with `git add`, or this becomes the R394.1 Railway outage again:\n  "
            + "\n  ".join(wip),
            UserWarning,
            stacklevel=2,
        )

    assert not committed, (
        "An unmodified tracked file imports an untracked app module:\n  "
        + "\n  ".join(committed)
    )


def test_the_gate_actually_detects_an_untracked_import() -> None:
    """Two-sided: prove the gate FIRES, so a green run means something.

    A guard whose failing state is never exercised is the inert-feature trap
    this repo has paid for three times (R329's rerank placements, R330's
    semantic layer, R366's parent collapse). This reconstructs the exact
    R394.1 line against a universe that omits the module.
    """
    universe = frozenset({"app/engines/_graph_rag_impl.py"})
    src = "from app.engines.prompt_budget import _shrink_user_for_groq\n"

    targets = _module_targets(ast.parse(src), _package_of("app/engines/_graph_rag_impl.py"))
    assert targets == [("app.engines.prompt_budget", 1)]
    assert not _resolves("app.engines.prompt_budget", universe)

    found = _violations({"app/engines/_graph_rag_impl.py": src}, universe)
    # Assert the stable prefix only: the trailing hint distinguishes "untracked
    # but present on disk" from "absent entirely", which depends on whether the
    # WIP file happens to sit in this checkout — not on the gate's logic.
    assert len(found) == 1
    assert found[0].startswith(
        "app/engines/_graph_rag_impl.py:1: imports `app.engines.prompt_budget`, which "
    )

    # ...and that it goes quiet once the module is in the universe.
    with_module = universe | {"app/engines/prompt_budget.py"}
    assert _resolves("app.engines.prompt_budget", with_module)
    assert _violations({"app/engines/_graph_rag_impl.py": src}, with_module) == []


def test_relative_imports_resolve_against_their_package() -> None:
    """Pin the module-vs-package anchoring rule that a naive version gets wrong."""
    mod = _package_of("app/engines/graph_rag/pipeline.py")
    assert mod == "app.engines.graph_rag"
    assert _module_targets(ast.parse("from . import models\n"), mod) == [
        ("app.engines.graph_rag", 1)
    ]
    assert _module_targets(ast.parse("from ..kb import x\n"), mod) == [("app.engines.kb", 1)]
    assert _module_targets(ast.parse("from .risk_engine import y\n"), mod) == [
        ("app.engines.graph_rag.risk_engine", 1)
    ]

    # A package __init__ anchors on ITSELF, not on its parent: `.` inside
    # app/engines/graph_rag/__init__.py is app.engines.graph_rag. Resolving it
    # to app.engines would invent false violations for every relative import in
    # every package init in the tree.
    pkg = _package_of("app/engines/graph_rag/__init__.py")
    assert pkg == "app.engines.graph_rag"
    assert _module_targets(ast.parse("from . import config\n"), pkg) == [
        ("app.engines.graph_rag", 1)
    ]

    # A relative import that escapes the root is skipped rather than mis-resolved.
    assert _module_targets(ast.parse("from ..... import z\n"), "app.engines") == []


def test_absolute_and_symbol_imports_are_classified_correctly() -> None:
    """`from X import symbol` must check X, not X.symbol; non-app imports ignored."""
    pkg = _package_of("app/routes/regenold.py")

    # Only the module part is required to resolve.
    assert _module_targets(ast.parse("from app.data.kb import ARTICLES, ANNEXES\n"), pkg) == [
        ("app.data.kb", 1)
    ]
    # Plain `import app.x.y` requires the whole dotted path.
    assert _module_targets(ast.parse("import app.engines.graph_rag\n"), pkg) == [
        ("app.engines.graph_rag", 1)
    ]
    # Third-party and stdlib are out of scope — requirements.txt covers those.
    assert _module_targets(ast.parse("import os\nfrom fastapi import APIRouter\n"), pkg) == []
    # A module merely NAMED like the package must not be picked up.
    assert _module_targets(ast.parse("import application\nfrom apps import x\n"), pkg) == []

"""R355 — cache-key completeness: every engine-read env flag must be accounted
for in ``_engine_cache_key``.

The engine caches ``GraphRAGResponse`` (route ``_ENGINE_CACHE`` keyed by
``_engine_cache_key``). Any ``REGENOLD_*`` / ``P2P_*`` flag read by the engine
that flips that response MUST be folded into the key, or an in-process
two-arm A/B (``easyhard_ab`` / ``ab_judge`` mutate ``os.environ`` between
arms) serves arm A's cached response to arm B — the R263.2 cross-arm
contamination, which looks exactly like a flat "+0.0000, no effect" (R329 /
R331 doctrine).

This test statically scans the engine for env reads and asserts each one is
either:

  1. keyed literally in the ``engine_flags`` tuple of ``_engine_cache_key``,
  2. covered via a helper function that ``_engine_cache_key`` calls (e.g.
     ``is_adaptive_router_enabled()``), or
  3. listed in ``_JUSTIFIED_EXCLUSIONS`` with an explicit reason (route-side
     post-processing that re-runs on cache hit, credentials, dead flags).

Comment/docstring mentions are ignored (AST-based, so only real reads count).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_KEY_FILE = _REPO_ROOT / "app" / "routes" / "regenold.py"
_ENGINE_DIRS = (_REPO_ROOT / "app" / "engines", _REPO_ROOT / "app" / "integrations" / "regenold",
    _REPO_ROOT / "app" / "data",  # R379 — prompt flags
    _REPO_ROOT / "app" / "llm",  # Stage-0 and Stage-2 flags also change answers
)
_FLAG_RE = re.compile(r"^(?:REGENOLD|P2P)_[A-Z0-9_]+$")
_KEY_TUPLE_LINE_RE = re.compile(r'^[ \t]*"((?:REGENOLD|P2P)_[A-Z0-9_]+)",[ \t]*$', re.M)

# Env-name module constants (e.g. ``_ENV_MODEL = "REGENOLD_COHERE_RERANK_MODEL"``).
_ENV_CONST_RE = re.compile(r"^_?[A-Z][A-Z0-9_]*ENV[A-Z0-9_]*$|^_OPT_IN_ENV$|^_ENV_FLAG$|^_ENV_GATE$|^_ENV_MODEL$")


def _is_flag(s: str) -> bool:
    return bool(_FLAG_RE.match(s))


def _flag_from_call(node: ast.Call, consts: dict[str, str]) -> str | None:
    """Flag read by this Call if it is an env read (os.getenv / os.environ.get /
    helpers). The name may be a literal or a module-level constant passed BY NAME
    (``os.getenv(EVIDENCE_BUNDLE_ENV, "0")``), resolved through ``consts``.

    The callee is matched on its full dotted text, so ``os.environ.get`` counts
    (its last attribute alone, ``get``, does not look like an env read).
    """
    lowered = ast.unparse(node.func).lower()
    if "getenv" not in lowered and "environ" not in lowered and "env_" not in lowered and "_env" not in lowered:
        return None
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str) and _is_flag(first.value):
        return first.value
    if isinstance(first, ast.Name):
        return consts.get(first.id)
    return None


def _flag_from_subscript(node: ast.Subscript) -> str | None:
    if (
        isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
        and _is_flag(node.slice.value)
    ):
        return node.slice.value
    return None


def _assigned_flag(node: ast.Assign | ast.AnnAssign) -> tuple[str, str] | None:
    """``(name, flag)`` for ``NAME = "REGENOLD_X"`` and the annotated form
    ``NAME: Final = "REGENOLD_X"`` (an ``ast.AnnAssign``, not an ``ast.Assign``)."""
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1:
            return None
        target = node.targets[0]
    else:
        target = node.target
    value = node.value
    if (
        isinstance(target, ast.Name)
        and isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and _is_flag(value.value)
    ):
        return target.id, value.value
    return None


def _flag_from_assign(node: ast.Assign | ast.AnnAssign) -> str | None:
    """Module-level env-name constant assignment, plain or annotated."""
    named = _assigned_flag(node)
    if named and _ENV_CONST_RE.match(named[0]):
        return named[1]
    return None


class _EnvReadCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self._stack: list[str] = []
        self._consts: dict[str, str] = {}
        self.reads: dict[str, list[tuple[Path, int, str | None]]] = {}

    def visit_Module(self, node: ast.Module) -> None:  # noqa: N802
        # Module-level flag constants first, so a read that passes one by name
        # resolves wherever it sits in the file.
        for stmt in node.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                named = _assigned_flag(stmt)
                if named:
                    self._consts[named[0]] = named[1]
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def _record(self, flag: str | None, node: ast.AST) -> None:
        if flag:
            fn = self._stack[-1] if self._stack else None
            self.reads.setdefault(flag, []).append((node.lineno, fn))

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self._record(_flag_from_call(node, self._consts), node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        self._record(_flag_from_subscript(node), node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        self._record(_flag_from_assign(node), node)
        self.generic_visit(node)

    visit_AnnAssign = visit_Assign  # noqa: N815


def _collect_engine_reads() -> dict[str, list[tuple[str, int, str | None]]]:
    """{flag: [(file, line, enclosing_function_or_None)]} across the engine."""
    out: dict[str, list[tuple[str, int, str | None]]] = {}
    for d in _ENGINE_DIRS:
        for path in sorted(d.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            collector = _EnvReadCollector()
            collector.visit(tree)
            for flag, sites in collector.reads.items():
                out.setdefault(flag, []).extend(
                    (str(path.relative_to(_REPO_ROOT)), line, fn) for line, fn in sites
                )
    return out


def _key_function_source() -> str:
    src = _KEY_FILE.read_text(encoding="utf-8")
    m = re.search(r"def _engine_cache_key\(.*?(?=\ndef |\n@|$)", src, re.S)
    assert m, "_engine_cache_key not found in regenold.py"
    return m.group(0)


def _keyed_literals(key_src: str) -> set[str]:
    """Flag literals in the engine_flags tuple of the key, plus any flag read
    directly via an env call in the key body (e.g. ``P2P_GRAPH_RAG_PROVIDER``
    folded into ``provider_bit``)."""
    tuple_flags = {m.group(1) for m in _KEY_TUPLE_LINE_RE.finditer(key_src)}
    direct = set(
        re.findall(
            r'(?:os\.getenv|os\.environ\.get|env_enabled|_env_on|_int_env)\(\s*"((?:REGENOLD|P2P)_[A-Z0-9_]+)"',
            key_src,
        )
    )
    return tuple_flags | direct


def _helper_covered(key_src: str) -> set[tuple[str, str]]:
    """``(module, function)`` of each reader helper that _engine_cache_key calls.

    Resolves the key's lazy imports with ``ast``, so the parenthesised
    multi-name form (``from m import (\\n a,\\n b as c,\\n)``) yields every name,
    not just the first, then keeps the imported names actually called in the key
    body. Coverage is per MODULE: a flag read in ``cite_describe_guard.is_enabled``
    is not covered by the key calling ``citation_guard.is_enabled``.
    """
    imports: dict[str, tuple[str, str]] = {}  # local-name -> (module, real-name)
    for node in ast.walk(ast.parse(key_src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    called = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", key_src))
    return {pair for local, pair in imports.items() if local in called}


def _module_of(path: str) -> str:
    """``app\\engines\\x.py`` (as recorded by the collector) -> ``app.engines.x``."""
    return path.replace("\\", "/").removesuffix(".py").replace("/", ".")


# Flags that are correctly NOT keyed. Every entry must name a flag that IS
# read by the engine (stale entries fail CI) and give the reason it cannot
# serve a stale cached response.
_JUSTIFIED_EXCLUSIONS: dict[str, str] = {
    # CLARA runs route-side (after the engine cache) and re-runs on every
    # cache hit, so flipping any of these cannot serve a stale answer —
    # the same doctrine as REGENOLD_CLARA_VERDICT, documented in the key.
    "REGENOLD_CLARA_FAILURE_THRESHOLD": "route-side (CLARA verdict re-runs on cache hit)",
    "REGENOLD_CLARA_FAILURE_WINDOW": "route-side (CLARA verdict re-runs on cache hit)",
    "REGENOLD_CLARA_LLM": "route-side (CLARA verdict re-runs on cache hit)",
    "REGENOLD_CLARA_MODEL": "route-side (CLARA verdict re-runs on cache hit)",
    "REGENOLD_CLARA_TIMEOUT": "route-side (CLARA verdict re-runs on cache hit)",
    # Keyed through the flag_bits helpers the key calls (module-scope env
    # constants, so the literal is not in the engine_flags tuple).
    "REGENOLD_TURBOQUANT_DENSE": "keyed via turboquant_index.is_enabled() in flag_bits (_dense_enabled)",
    "REGENOLD_CITATION_GUARD": "keyed via citation_guard.is_enabled() in flag_bits (_guard_enabled)",
    "REGENOLD_COHERE_RERANK": "keyed via cohere_rerank.rerank_enabled()",
    # Route post-processing — re-runs on every cache hit, so a flip cannot
    # serve a stale answer. The _engine_cache_key docstring names this family
    # (REGENOLD_HARD_CHAR_CAP, REGENOLD_REF_DESCRIBE_AUG, REGENOLD_TONE_GUARD,
    # REGENOLD_QA_TRIM) as deliberately unkeyed.
    "REGENOLD_HARD_CHAR_CAP": "route post-processing (documented unkeyed in the key docstring)",
    "REGENOLD_MAX_ANSWER_SENTENCES": "route post-processing (normalise_answer_for_regenold)",
    "REGENOLD_QA_LENGTH_CAP": "route post-processing (normalise_answer_for_regenold)",
    "REGENOLD_LIVE_SENTENCE_CAP": "route post-processing (normalise_answer_for_regenold)",
    "REGENOLD_CITATION_FORM": "route post-processing (normalise_answer_for_regenold)",
    "REGENOLD_STRIP_PREAMBLE": "route post-processing (answer normaliser family)",
    "REGENOLD_STRIP_DASHES": "route post-processing (answer normaliser family)",
    "REGENOLD_STRIP_HEDGE": "route post-processing (answer normaliser family)",
    "REGENOLD_STRIP_META": "route post-processing (answer normaliser family)",
    "REGENOLD_STRIP_RETRIEVAL_META": "route post-processing (answer normaliser family)",
    "REGENOLD_STRIP_SECTION_HEADERS": "route post-processing (answer normaliser family)",
    "REGENOLD_REPAIR_ELISION": "route post-processing (answer normaliser family)",
    "REGENOLD_ENUM_GUARD": "route post-processing (answer normaliser family)",
    "REGENOLD_REF_DESCRIBE_REPLACE": "route post-processing (ref-describe family, like REGENOLD_REF_DESCRIBE_AUG)",
    "REGENOLD_R89A_FORCE_APPEND": "route post-processing (ref-describe family, like REGENOLD_REF_DESCRIBE_AUG)",
    # Route-side gates / configuration that decide refusal or app behaviour
    # after the cache, never the cached engine response.
    "REGENOLD_AI_USECASE_RESCUE": "route-side jailbreak-refusal rescue gate",
    "REGENOLD_SAFETY_GATE": "route-side safety gate",
    "REGENOLD_LEXY_LLM_GATE": "route-side safety gate (lexy)",
    # Read through a module constant (os.getenv(_ENV_TIMEOUT)); the lexy gate
    # decides refusal before the engine cache key is even computed.
    "REGENOLD_LEXY_GATE_TIMEOUT": "route-side safety gate timeout (lexy, pre-cache)",
    # Read through an annotated constant (_ENV_FLAG: str = ...). The R66-B guard
    # prunes the wire refs after the engine result, on every request.
    "REGENOLD_CITE_DESCRIBE_GUARD": "route post-processing; re-runs on every cache hit",
    "REGENOLD_SCOPE_STICKINESS": "route-side conversation-scope classification (in/out-of-scope refusal)",
    "REGENOLD_APP_URL": "route-side app configuration (email links)",
    "REGENOLD_USER_DB_URL": "infrastructure configuration (user-store backend selection)",
    # External configuration, not an engine-behaviour lever.
    "REGENOLD_NLI_API": "external endpoint URL; its gate (REGENOLD_NLI_VERIFY) is route-side",
    # Consumed only by the dead app/engines/graph_rag/ sub-package — zero
    # request-path callers (R290 verified with sys.settrace). No runtime effect.
    "REGENOLD_GRAPH_RAG_V2": "dead flag — only read by the dead graph_rag split package (R290)",
    # Pure concurrency admission cap (threading.BoundedSemaphore); changes
    # parallelism, never engine output.
    "REGENOLD_KG_MAX_INFLIGHT": "concurrency cap only — does not flip engine output",
    "REGENOLD_INTENT_CACHE_MAX": "LRU capacity only; intent cache entries are configuration-scoped",
}


def test_every_engine_env_flag_is_accounted_for() -> None:
    reads = _collect_engine_reads()
    key_src = _key_function_source()
    keyed = _keyed_literals(key_src)
    helper_covered = _helper_covered(key_src)

    unaccounted: list[str] = []
    for flag in sorted(reads):
        if flag in keyed or flag in _JUSTIFIED_EXCLUSIONS:
            continue
        if any((_module_of(file), fn) in helper_covered for file, _, fn in reads[flag]):
            continue
        sites = ", ".join(f"{file}:{line} ({fn or '<module>'})" for file, line, fn in reads[flag])
        unaccounted.append(f"  {flag} — read at {sites}")

    assert not unaccounted, (
        "Engine env flags missing from _engine_cache_key (R30/R56/R79/R263.2 doctrine — "
        "an unkeyed flip serves stale cached answers and makes same-process A/Bs "
        "unfalsifiable). Add each to the engine_flags tuple in _engine_cache_key, or "
        "justify it in _JUSTIFIED_EXCLUSIONS:\n" + "\n".join(unaccounted)
    )


def test_collector_sees_annotated_and_name_argument_env_reads() -> None:
    """R461 — the gate was blind to the idioms ``evidence_bundle`` uses, so its two
    unkeyed flags passed CI: an annotated constant (``X: Final = "REGENOLD_..."``
    is an ``ast.AnnAssign``) read by NAME (``os.getenv(X)``). ``os.environ.get``
    was invisible too, because only the callee's last attribute (``get``) was
    inspected."""
    src = "\n".join(
        [
            "import os",
            "from typing import Final",
            'A_ENV: Final = "REGENOLD_S_ANNOTATED"',
            '_ENV_FLAG: str = "REGENOLD_S_ANNOTATED_STR"',
            'FLAGNAME = "REGENOLD_S_BY_NAME"',
            "def by_name():",
            '    return os.getenv(FLAGNAME, "0")',
            "def environ_get():",
            '    return os.environ.get("REGENOLD_S_ENVIRON_GET", "")',
            "def read_before_declared():",
            "    return os.getenv(LATE_FLAG)",
            'LATE_FLAG = "REGENOLD_S_LATE"',
        ]
    )
    collector = _EnvReadCollector()
    collector.visit(ast.parse(src))
    for flag in (
        "REGENOLD_S_ANNOTATED",
        "REGENOLD_S_ANNOTATED_STR",
        "REGENOLD_S_BY_NAME",
        "REGENOLD_S_ENVIRON_GET",
        "REGENOLD_S_LATE",
    ):
        assert flag in collector.reads, f"collector cannot see {flag}"
    # A by-name read is attributed to the function that performs it, which is
    # what helper coverage keys on.
    assert [fn for _, fn in collector.reads["REGENOLD_S_BY_NAME"]] == ["by_name"]


def test_helper_covered_reads_parenthesised_imports_per_module() -> None:
    """R461 — the import regex captured only the first name of ``from m import (a, b)``,
    and coverage matched a bare function NAME, so ``cite_describe_guard.is_enabled``
    counted as keyed because the key calls ``citation_guard.is_enabled``."""
    key_src = "\n".join(
        [
            "def _engine_cache_key(q, ctx):",
            "    from app.engines.alpha import (",
            "        reader_a,",
            "        reader_b as _rb,",
            "    )",
            "    from app.engines.beta import is_enabled",
            '    return f"{reader_a()}:{_rb()}"',
        ]
    )
    assert _helper_covered(key_src) == {
        ("app.engines.alpha", "reader_a"),
        ("app.engines.alpha", "reader_b"),
    }
    assert _module_of("app\\engines\\alpha.py") == "app.engines.alpha"


def test_justified_exclusions_are_still_real_engine_reads() -> None:
    reads = _collect_engine_reads()
    for flag in _JUSTIFIED_EXCLUSIONS:
        assert flag in reads, (
            f"{flag} is in _JUSTIFIED_EXCLUSIONS but is no longer read anywhere in the "
            "engine — remove the stale allowlist entry (or restore the read)."
        )

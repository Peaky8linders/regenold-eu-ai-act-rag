"""R296 — regression pins for three LIVE-path defects found auditing R294/R295.

All three were already deployed to production (R294 #306 / R295 #308 merged to
``origin/main``, which auto-deploys), so these are production bug fixes, not
pre-merge review findings.

1. ``default_groq_model`` was imported INSIDE ``_general_llm_candidates`` but
   called inside ``_rewrite_multiturn_query`` — a genuine ``NameError``,
   swallowed by ``except Exception: logger.debug(...)``, silently dropping Groq
   from the multi-turn query de-noiser on EVERY multi-turn request. Same class
   as the R295 ``logger``-with-no-``logging``-import fix, still live.
2. The Annex-III Article 6(3) graph lookup was the one live consumer with NO
   wall-clock budget and NO circuit breaker (R294 bounded the others).
3. ``REGENOLD_CAP_EXPANSION`` — the fourth knob of the 2-hop family — was
   missing from ``_engine_cache_key`` (R295 keyed the other three).
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest


def _module_level_names(tree: ast.Module) -> set[str]:
    """Names bound at MODULE scope only (not inside any function body)."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Try):
            # try/except ImportError blocks at module scope still bind names.
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for alias in sub.names:
                        names.add(alias.asname or alias.name.split(".")[0])
    return names


def _unresolved_names(func: ast.FunctionDef | ast.AsyncFunctionDef,
                      module_names: set[str]) -> list[str]:
    """Names LOADed in ``func`` that resolve neither locally nor at module scope."""
    local: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                local.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
        elif isinstance(node, ast.arg):
            local.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node is not func:
                local.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            local.add(node.name)
    used = {
        n.id for n in ast.walk(func)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    return sorted(used - local - module_names - set(dir(builtins)))


ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "routes" / "regenold.py"


class TestR296NoUndefinedNames:
    """Fix 1 + the guard that stops this whole class of bug recurring."""

    def test_denoiser_resolves_default_groq_model(self) -> None:
        """The exact live NameError: called at :5092, imported only at :4464."""
        tree = ast.parse(ROUTE_PATH.read_text(encoding="utf-8"))
        module_names = _module_level_names(tree)
        target = next(
            fn for fn in tree.body
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            and fn.name == "_rewrite_multiturn_query"
        )
        assert _unresolved_names(target, module_names) == []

    def test_no_module_level_function_has_an_unresolved_name(self) -> None:
        """Whole-file sweep — the R295 logger bug and this one are one class."""
        tree = ast.parse(ROUTE_PATH.read_text(encoding="utf-8"))
        module_names = _module_level_names(tree)
        offenders = {
            fn.name: missing
            for fn in tree.body
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            if (missing := _unresolved_names(fn, module_names))
        }
        assert offenders == {}, f"unresolved names: {offenders}"

    def test_denoiser_groq_branch_actually_reaches_the_model_call(self) -> None:
        """Guard the swallow: the NameError hid behind ``except Exception``."""
        from app.llm.openai_wrapper_provider import default_groq_model

        assert isinstance(default_groq_model(), str)
        assert default_groq_model().strip()


class TestR296BoundedAnnexIIIGraphRead:
    """Fix 2 — the last unbounded live graph consumer."""

    def test_returns_empty_when_breaker_open(self, monkeypatch) -> None:
        from app.engines import _graph_rag_impl as impl

        monkeypatch.setattr("app.graph.timeouts.graph_circuit_open", lambda: True)

        class _Boom:
            def execute_read(self, *a, **k):  # pragma: no cover - must not run
                raise AssertionError("breaker open: must not query")

        assert impl._bounded_graph_read(_Boom(), "MATCH (n) RETURN n") == []

    def test_slow_query_is_bounded_and_fails_soft(self, monkeypatch) -> None:
        import time

        from app.engines import _graph_rag_impl as impl

        monkeypatch.setattr("app.graph.timeouts.graph_circuit_open", lambda: False)
        monkeypatch.setattr("app.graph.timeouts.resolve_graph_timeout_ms", lambda *a, **k: 50)

        class _Slow:
            def execute_read(self, *a, **k):
                time.sleep(2.0)
                return [{"letter": "a"}]

        started = time.perf_counter()
        rows = impl._bounded_graph_read(_Slow(), "MATCH (n) RETURN n")
        elapsed = time.perf_counter() - started

        assert rows == []
        assert elapsed < 1.0, f"unbounded: took {elapsed:.2f}s against a 50ms budget"

    def test_raising_client_fails_soft(self, monkeypatch) -> None:
        from app.engines import _graph_rag_impl as impl

        monkeypatch.setattr("app.graph.timeouts.graph_circuit_open", lambda: False)

        class _Raises:
            def execute_read(self, *a, **k):
                raise RuntimeError("connection refused")

        assert impl._bounded_graph_read(_Raises(), "MATCH (n) RETURN n") == []

    def test_healthy_query_passes_rows_through(self, monkeypatch) -> None:
        from app.engines import _graph_rag_impl as impl

        monkeypatch.setattr("app.graph.timeouts.graph_circuit_open", lambda: False)
        rows = [{"point_id": "article_6_3_a", "letter": "a", "text": "narrow task"}]

        class _Ok:
            def execute_read(self, *a, **k):
                return rows

        assert impl._bounded_graph_read(_Ok(), "MATCH (n) RETURN n") == rows


class TestR296CapExpansionInCacheKey:
    """Fix 3 — the fourth 2-hop knob; R295 keyed the other three."""

    @pytest.mark.parametrize(
        "var",
        [
            "REGENOLD_CAP_EXPANSION",
            # R295's three, pinned so a refactor can't silently drop them.
            "REGENOLD_GRAPH_TIMEOUT_MS",
            "REGENOLD_GRAPH_BREAKER",
            "REGENOLD_GRAPH_FUSE_SLACK",
        ],
    )
    def test_knob_changes_the_engine_cache_key(self, monkeypatch, var: str) -> None:
        from app.routes.regenold import _engine_cache_key

        question = "What are the obligations of deployers of high-risk AI systems?"

        monkeypatch.setenv(var, "0")
        key_off = _engine_cache_key(question, "")
        monkeypatch.setenv(var, "1")
        key_on = _engine_cache_key(question, "")

        assert key_off != key_on, f"{var} missing from _engine_cache_key"

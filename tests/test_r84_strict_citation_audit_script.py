"""R84-C — :mod:`scripts.audit_neo4j_strict_citation` behavioural tests.

Covers the three branches an operator hits in CI / pre-deploy:

* No ``NEO4J_URI`` env var → ``SKIPPED`` + exit 0.
* GraphClient returns empty result set → ``OK`` + exit 0.
* GraphClient returns at least one malformed row → ``FAIL`` + exit 1.

The driver is never spun up; we monkeypatch the lazily-imported
``get_graph_client`` so the test stays offline.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from scripts import audit_neo4j_strict_citation


# ─── Fixtures ────────────────────────────────────────────────────────────


class _FakeGraphClient:
    """In-memory stand-in for :class:`app.graph.client.GraphClient`.

    Records the query that ``execute_read`` was called with so tests can
    assert the audit Cypher actually reaches the driver layer.
    """

    def __init__(self, *, enabled: bool = True, rows: list[dict[str, Any]] | None = None) -> None:
        self.enabled = enabled
        self._rows = list(rows or [])
        self.queries: list[str] = []

    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.queries.append(query)
        return list(self._rows)


@pytest.fixture
def _unset_neo4j_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEO4J_URI", raising=False)


@pytest.fixture
def _set_neo4j_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")


# ─── Branch 1 — missing NEO4J_URI ────────────────────────────────────────


class TestR84AuditScriptMissingURI:
    def test_skipped_message_printed(
        self,
        _unset_neo4j_uri: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = audit_neo4j_strict_citation.run_audit()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "SKIPPED" in captured.out
        assert "NEO4J_URI" in captured.out

    def test_main_returns_zero_without_uri(
        self,
        _unset_neo4j_uri: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = audit_neo4j_strict_citation.main([])
        assert exit_code == 0


# ─── Branch 2 — empty result → OK ────────────────────────────────────────


class TestR84AuditScriptEmptyResult:
    def test_ok_message_printed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _set_neo4j_uri: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        client = _FakeGraphClient(enabled=True, rows=[])
        # The audit script imports get_graph_client lazily inside
        # run_audit. We patch the underlying module to ensure the lazy
        # import yields our fake client regardless of installation state.
        import app.graph.client as graph_client_module

        monkeypatch.setattr(graph_client_module, "get_graph_client", lambda: client)

        exit_code = audit_neo4j_strict_citation.run_audit()
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "OK" in captured.out
        assert "126" in captured.out  # 113 Articles + 13 Annexes
        # Sanity — the audit Cypher actually executed.
        assert len(client.queries) == 1
        assert "Article" in client.queries[0]
        assert "Annex" in client.queries[0]
        assert "strict_citation" in client.queries[0]


# ─── Branch 3 — non-empty result → FAIL ──────────────────────────────────


class TestR84AuditScriptNonEmptyResult:
    def test_fail_message_printed_with_row(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _set_neo4j_uri: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bad_rows = [
            {
                "label": "Article",
                "id": "article_42",
                "number": "42x",  # malformed — would fail =~ '\d+'
                "strict_citation": "Art. 42",  # malformed — internal form
            },
            {
                "label": "Annex",
                "id": "annex_3",
                "number": "3",  # malformed — Arabic
                "strict_citation": "Annex 3",  # malformed
            },
        ]
        client = _FakeGraphClient(enabled=True, rows=bad_rows)
        import app.graph.client as graph_client_module

        monkeypatch.setattr(graph_client_module, "get_graph_client", lambda: client)

        exit_code = audit_neo4j_strict_citation.run_audit()
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "2" in captured.out  # row count summary
        # Each bad row was printed (id appears in output).
        assert "article_42" in captured.out
        assert "annex_3" in captured.out
        # Operator runbook pointer.
        assert "seed_neo4j_kb" in captured.out


# ─── Branch 4 — driver init / query failure → SKIPPED ────────────────────


class TestR84AuditScriptDriverFailure:
    def test_disabled_client_skips(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _set_neo4j_uri: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        client = _FakeGraphClient(enabled=False)
        import app.graph.client as graph_client_module

        monkeypatch.setattr(graph_client_module, "get_graph_client", lambda: client)

        exit_code = audit_neo4j_strict_citation.run_audit()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "SKIPPED" in captured.out

    def test_query_exception_skips(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _set_neo4j_uri: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        class _BrokenClient:
            enabled = True

            def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
                raise RuntimeError("simulated driver error")

        import app.graph.client as graph_client_module

        monkeypatch.setattr(graph_client_module, "get_graph_client", lambda: _BrokenClient())

        exit_code = audit_neo4j_strict_citation.run_audit()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "SKIPPED" in captured.out
        assert "driver error" in captured.out


# ─── CLI flag wiring ─────────────────────────────────────────────────────


class TestR84AuditScriptCLI:
    def test_cli_uri_override_sets_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--neo4j-uri populates NEO4J_URI before run_audit dispatches."""
        # Start with no URI set.
        monkeypatch.delenv("NEO4J_URI", raising=False)

        # Patch get_graph_client so the audit returns OK on the override.
        client = _FakeGraphClient(enabled=True, rows=[])
        import app.graph.client as graph_client_module

        monkeypatch.setattr(graph_client_module, "get_graph_client", lambda: client)

        exit_code = audit_neo4j_strict_citation.main(
            ["--neo4j-uri", "bolt://override:7687"]
        )
        assert exit_code == 0
        # The env var should have been populated by _apply_env_overrides.
        import os as _os

        assert _os.environ.get("NEO4J_URI") == "bolt://override:7687"

    def test_help_flag_exits_zero(self) -> None:
        """``--help`` must not crash even if the driver isn't installed."""
        with pytest.raises(SystemExit) as exc_info:
            audit_neo4j_strict_citation.main(["--help"])
        # argparse exits 0 on --help.
        assert exc_info.value.code == 0

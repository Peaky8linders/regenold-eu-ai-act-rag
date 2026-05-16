"""Tests for ``app.engines.graph_aware_retrieval``.

Covers the three new graph-traversal helpers (definition lookup,
recital grounding, role × risk obligation enumeration), each across:

* env-gate off (sub-µs passthrough)
* client disabled
* successful Cypher returns
* zero-match Cypher returns
* malformed Cypher rows
* timeout (Cypher exceeds budget → empty / None)
* exception swallowing
* existence-gate validation against ``ARTICLE_EXISTENCE``

The real Neo4j driver is never invoked — every test patches
``app.graph.client.get_graph_client`` with the same ``_FakeClient``
shape used by ``test_graph_expand_2hop``.
"""
from __future__ import annotations

import time
from typing import Any

import pytest

from app.engines import graph_aware_retrieval as gar
from app.engines.graph_aware_retrieval import (
    RecitalGrounding,
    RoleObligation,
    is_enabled,
    lookup_definition_by_term,
    obligations_for_role,
    recitals_for_article,
)


# ─── Fake client ──────────────────────────────────────────────────────────


class _FakeClient:
    """Stand-in for ``GraphClient``. Records every ``execute_read`` call."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        return_value: list[dict] | None = None,
        raise_exc: BaseException | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.enabled = enabled
        self._return_value = return_value or []
        self._raise_exc = raise_exc
        self._delay_seconds = delay_seconds
        self.calls: list[tuple[str, dict]] = []

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
        self.calls.append((query, dict(parameters or {})))
        if self._delay_seconds:
            time.sleep(self._delay_seconds)
        if self._raise_exc is not None:
            raise self._raise_exc
        return list(self._return_value)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Default to env-var unset for every test (explicit set inside).

    Also resets the module's shared ``ThreadPoolExecutor`` so a timeout
    test in one case can't tie up worker slots for the next. Without
    this, a 200ms-delay fake from one timeout test keeps a worker busy
    after pytest moves on, and the next test's ``future.result`` can
    fire its own timeout before the queued task even starts running.
    """
    monkeypatch.delenv("REGENOLD_GRAPH_AWARE", raising=False)
    # Force a fresh executor for each test — the module re-creates it on
    # next access via the lazy ``_get_executor`` path.
    gar._EXECUTOR = None
    yield
    gar._EXECUTOR = None


def _install_fake(monkeypatch, client: _FakeClient) -> None:
    """Patch ``get_graph_client`` at the import site used by the module.

    The module does a *deferred* import inside ``_resolve_client``, so
    we patch the source module rather than the module-level binding
    (which doesn't exist in our namespace).
    """
    import app.graph.client as gc

    monkeypatch.setattr(gc, "get_graph_client", lambda: client)


# ─── is_enabled() ─────────────────────────────────────────────────────────


def test_is_enabled_false_when_env_unset(monkeypatch):
    """No env-var → disabled even with a healthy client."""
    _install_fake(monkeypatch, _FakeClient(enabled=True))
    assert is_enabled() is False


def test_is_enabled_false_when_env_zero(monkeypatch):
    """Env-var ``"0"`` → disabled (strict ``"1"`` match)."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "0")
    _install_fake(monkeypatch, _FakeClient(enabled=True))
    assert is_enabled() is False


def test_is_enabled_false_when_env_arbitrary_string(monkeypatch):
    """Env-var ``"true"`` → disabled (only ``"1"`` flips on)."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "true")
    _install_fake(monkeypatch, _FakeClient(enabled=True))
    assert is_enabled() is False


def test_is_enabled_false_when_client_disabled(monkeypatch):
    """Env on but client.enabled=False → disabled."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    _install_fake(monkeypatch, _FakeClient(enabled=False))
    assert is_enabled() is False


def test_is_enabled_true_when_both_conditions_met(monkeypatch):
    """Env-var ``"1"`` AND ``client.enabled=True`` → enabled."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    _install_fake(monkeypatch, _FakeClient(enabled=True))
    assert is_enabled() is True


def test_is_enabled_false_when_client_factory_raises(monkeypatch):
    """``get_graph_client`` raises → treated as disabled."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    import app.graph.client as gc

    def _boom():
        raise RuntimeError("driver init failed")

    monkeypatch.setattr(gc, "get_graph_client", _boom)
    assert is_enabled() is False


# ─── lookup_definition_by_term() — passthrough cases ──────────────────────


def test_lookup_definition_disabled_returns_none_fast(monkeypatch):
    """Env-gate off → ``None``, no Cypher call."""
    client = _FakeClient(
        enabled=True,
        return_value=[{"id": "def_ai_system", "text": "definition prose"}],
    )
    _install_fake(monkeypatch, client)
    assert lookup_definition_by_term("AI system") is None
    assert client.calls == []


def test_lookup_definition_empty_term_returns_none(monkeypatch):
    """Empty / whitespace-only term → ``None``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True)
    _install_fake(monkeypatch, client)
    assert lookup_definition_by_term("") is None
    assert lookup_definition_by_term("   ") is None
    assert client.calls == []


def test_lookup_definition_client_disabled_returns_none(monkeypatch):
    """Env on, client.enabled=False → ``None``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=False, return_value=[{"id": "x"}])
    _install_fake(monkeypatch, client)
    assert lookup_definition_by_term("AI system") is None
    assert client.calls == []


# ─── lookup_definition_by_term() — happy path ─────────────────────────────


def test_lookup_definition_returns_text_on_match(monkeypatch):
    """Cypher returns a row → text is surfaced."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {
                "id": "def_ai_system",
                "term": "AI system",
                "text": "An AI system means a machine-based system…",
                "rank": 0,
                "id_len": 13,
            }
        ],
    )
    _install_fake(monkeypatch, client)
    result = lookup_definition_by_term("AI system")
    assert result == "An AI system means a machine-based system…"
    # The parameter is slugified.
    assert len(client.calls) == 1
    _, params = client.calls[0]
    assert params["term_slug"] == "ai_system"


def test_lookup_definition_slug_handles_punctuation(monkeypatch):
    """``"AI system"`` / ``"AI-system"`` / ``"AI  system!"`` all → ``"ai_system"``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    for raw in ("AI system", "AI-system", "AI  system!", "AI_System"):
        client.calls.clear()
        lookup_definition_by_term(raw)
        _, params = client.calls[0]
        assert params["term_slug"] == "ai_system", f"failed on input {raw!r}"


def test_lookup_definition_returns_none_when_no_match(monkeypatch):
    """Cypher returns ``[]`` → ``None``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    assert lookup_definition_by_term("nonsense term") is None


def test_lookup_definition_returns_none_when_row_lacks_text(monkeypatch):
    """Malformed row missing ``text`` → ``None``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[{"id": "def_ai_system"}],  # no text key
    )
    _install_fake(monkeypatch, client)
    assert lookup_definition_by_term("AI system") is None


def test_lookup_definition_returns_none_when_text_empty(monkeypatch):
    """``text=""`` → ``None`` (defensive)."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[{"id": "def_x", "text": "   "}],
    )
    _install_fake(monkeypatch, client)
    assert lookup_definition_by_term("x") is None


def test_lookup_definition_swallows_exception(monkeypatch):
    """Cypher raises → ``None``, no propagation."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        raise_exc=RuntimeError("Neo4j unreachable"),
    )
    _install_fake(monkeypatch, client)
    # Must not raise.
    assert lookup_definition_by_term("provider") is None


def test_lookup_definition_timeout_returns_none(monkeypatch):
    """Slow Cypher (>budget) → ``None``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[{"id": "def_x", "text": "won't make it"}],
        delay_seconds=0.2,
    )
    _install_fake(monkeypatch, client)
    assert lookup_definition_by_term("provider", timeout_ms=10) is None


# ─── recitals_for_article() — passthrough cases ───────────────────────────


def test_recitals_disabled_returns_empty_fast(monkeypatch):
    """Env-gate off → ``[]``, no Cypher call."""
    client = _FakeClient(
        enabled=True,
        return_value=[{"num": "47", "text": "Recital 47 prose"}],
    )
    _install_fake(monkeypatch, client)
    assert recitals_for_article("Article 6") == []
    assert client.calls == []


def test_recitals_empty_article_returns_empty(monkeypatch):
    """Empty article ref → ``[]``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True)
    _install_fake(monkeypatch, client)
    assert recitals_for_article("") == []
    assert client.calls == []


def test_recitals_zero_max_returns_empty(monkeypatch):
    """``max_recitals=0`` → ``[]``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True)
    _install_fake(monkeypatch, client)
    assert recitals_for_article("Article 6", max_recitals=0) == []
    assert client.calls == []


def test_recitals_bogus_article_returns_empty(monkeypatch):
    """Article ref outside ``ARTICLE_EXISTENCE`` → ``[]``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True)
    _install_fake(monkeypatch, client)
    # 200 isn't in the 113-article catalog.
    assert recitals_for_article("Article 200") == []
    assert client.calls == []


def test_recitals_unparseable_ref_returns_empty(monkeypatch):
    """Garbage ref → ``[]``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True)
    _install_fake(monkeypatch, client)
    assert recitals_for_article("not-an-article") == []
    assert client.calls == []


# ─── recitals_for_article() — happy path ──────────────────────────────────


def test_recitals_returns_zero_when_cypher_empty(monkeypatch):
    """Article exists but has no anchored recitals → ``[]``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    assert recitals_for_article("Article 6") == []


def test_recitals_returns_one(monkeypatch):
    """Single recital row → list of length 1, fully populated."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[{"num": "47", "text": "Recital 47 prose."}],
    )
    _install_fake(monkeypatch, client)
    result = recitals_for_article("Article 6")
    assert len(result) == 1
    rg = result[0]
    assert isinstance(rg, RecitalGrounding)
    assert rg.article_ref == "Article 6"
    assert rg.recital_number == 47
    assert rg.recital_text == "Recital 47 prose."


def test_recitals_returns_three(monkeypatch):
    """Three recital rows → list of length 3 in input order."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"num": "47", "text": "r47"},
            {"num": "50", "text": "r50"},
            {"num": "85", "text": "r85"},
        ],
    )
    _install_fake(monkeypatch, client)
    result = recitals_for_article("Article 6", max_recitals=3)
    assert [r.recital_number for r in result] == [47, 50, 85]


def test_recitals_caps_at_max_recitals(monkeypatch):
    """10 recital rows but ``max_recitals=3`` → list of length 3."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    rows = [{"num": str(n), "text": f"r{n}"} for n in range(10, 20)]
    client = _FakeClient(enabled=True, return_value=rows)
    _install_fake(monkeypatch, client)
    result = recitals_for_article("Article 6", max_recitals=3)
    assert len(result) == 3
    # Cap parameter passed through to Cypher.
    _, params = client.calls[0]
    assert params["cap"] == 3


def test_recitals_handles_user_facing_and_internal_form(monkeypatch):
    """``"Article 6"`` and ``"Art. 6"`` both Cypher with ``num="6"``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    for raw in ("Article 6", "Art. 6"):
        client.calls.clear()
        recitals_for_article(raw)
        _, params = client.calls[0]
        assert params["num"] == "6"


def test_recitals_drops_malformed_rows(monkeypatch):
    """Rows missing ``num`` / ``text`` are dropped silently."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"text": "no num"},                    # missing num
            {"num": "12"},                         # missing text
            {"num": "not-a-number", "text": "x"},  # malformed num
            {"num": "47", "text": "good"},         # well-formed
            "not-a-dict",
        ],
    )
    _install_fake(monkeypatch, client)
    result = recitals_for_article("Article 6", max_recitals=5)
    assert len(result) == 1
    assert result[0].recital_number == 47


def test_recitals_swallows_exception(monkeypatch):
    """Cypher raises → ``[]``, no propagation."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, raise_exc=RuntimeError("oh no"))
    _install_fake(monkeypatch, client)
    assert recitals_for_article("Article 6") == []


def test_recitals_timeout_returns_empty(monkeypatch):
    """Slow Cypher → ``[]``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[{"num": "47", "text": "wont land"}],
        delay_seconds=0.2,
    )
    _install_fake(monkeypatch, client)
    assert recitals_for_article("Article 6", timeout_ms=10) == []


# ─── obligations_for_role() — passthrough cases ───────────────────────────


def test_obligations_disabled_returns_empty_fast(monkeypatch):
    """Env-gate off → ``[]``, no Cypher call."""
    client = _FakeClient(
        enabled=True,
        return_value=[{"id": "obl_9", "art": "9", "text": "duty"}],
    )
    _install_fake(monkeypatch, client)
    assert obligations_for_role("provider", "high-risk") == []
    assert client.calls == []


def test_obligations_unknown_role_returns_empty(monkeypatch):
    """Role outside the canonical set → ``[]``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    assert obligations_for_role("auditor", "high-risk") == []
    assert client.calls == []


def test_obligations_unknown_risk_level_returns_empty(monkeypatch):
    """Risk level outside the alias table → ``[]``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    assert obligations_for_role("provider", "unknown-tier") == []
    assert client.calls == []


def test_obligations_zero_cap_returns_empty(monkeypatch):
    """``max_obligations=0`` → ``[]``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    assert obligations_for_role("provider", "high-risk", max_obligations=0) == []
    assert client.calls == []


def test_obligations_client_disabled_returns_empty(monkeypatch):
    """Env on, client.enabled=False → ``[]``, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=False, return_value=[{"id": "x"}])
    _install_fake(monkeypatch, client)
    assert obligations_for_role("provider", "high-risk") == []
    assert client.calls == []


# ─── obligations_for_role() — happy path ──────────────────────────────────


def test_obligations_returns_one(monkeypatch):
    """Single obligation row → one fully-populated RoleObligation."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {
                "id": "obl_9",
                "art": "9",
                "para": "",
                "text": "Establish a risk-management system…",
                "mandatory": True,
            }
        ],
    )
    _install_fake(monkeypatch, client)
    result = obligations_for_role("provider", "high-risk")
    assert len(result) == 1
    obl = result[0]
    assert isinstance(obl, RoleObligation)
    assert obl.obligation_id == "obl_9"
    assert obl.article_ref == "Article 9"
    assert "risk-management" in obl.text
    assert obl.mandatory is True


def test_obligations_returns_multiple_with_paragraph_refs(monkeypatch):
    """Paragraph refs are appended to article refs."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {
                "id": "obl_9_2",
                "art": "9",
                "para": "2",
                "text": "...",
                "mandatory": True,
            },
            {
                "id": "obl_10",
                "art": "10",
                "para": "",
                "text": "Data governance...",
                "mandatory": True,
            },
        ],
    )
    _install_fake(monkeypatch, client)
    result = obligations_for_role("provider", "high-risk", max_obligations=5)
    assert len(result) == 2
    assert result[0].article_ref == "Article 9.2"
    assert result[1].article_ref == "Article 10"


def test_obligations_normalises_risk_level_aliases(monkeypatch):
    """``"high_risk"`` / ``"High"`` / ``"high-risk"`` all map to ``risk_high``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    for raw in ("high-risk", "high_risk", "High-Risk", "HIGH"):
        client.calls.clear()
        obligations_for_role("provider", raw)
        _, params = client.calls[0]
        assert params["risk_id"] == "risk_high", f"failed on input {raw!r}"


def test_obligations_normalises_role_aliases(monkeypatch):
    """``"Provider"`` / ``"provider"`` / ``"authorised_representative"`` accepted."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    for raw in ("provider", "Provider", "PROVIDER"):
        client.calls.clear()
        out = obligations_for_role(raw, "high-risk")
        assert out == []
        assert len(client.calls) == 1  # Cypher fired
    # British spelling collapses to American.
    client.calls.clear()
    out = obligations_for_role("authorised_representative", "high-risk")
    assert len(client.calls) == 1


def test_obligations_caps_at_max(monkeypatch):
    """20 returned rows but ``max_obligations=3`` → list of length 3."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    rows = [
        {
            "id": f"obl_{n}",
            "art": str(n),
            "para": "",
            "text": f"obligation {n}",
            "mandatory": True,
        }
        for n in range(6, 26)  # Art. 6..25, all valid
    ]
    client = _FakeClient(enabled=True, return_value=rows)
    _install_fake(monkeypatch, client)
    result = obligations_for_role("provider", "high-risk", max_obligations=3)
    assert len(result) == 3


def test_obligations_dedupes_by_id(monkeypatch):
    """Duplicate obligation IDs surface once."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"id": "obl_9", "art": "9", "para": "", "text": "x", "mandatory": True},
            {"id": "obl_9", "art": "9", "para": "", "text": "x", "mandatory": True},
        ],
    )
    _install_fake(monkeypatch, client)
    result = obligations_for_role("provider", "high-risk")
    assert len(result) == 1


def test_obligations_drops_invalid_article_refs(monkeypatch):
    """Article refs outside ``ARTICLE_EXISTENCE`` are dropped."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"id": "obl_200", "art": "200", "para": "", "text": "fake", "mandatory": True},
            {"id": "obl_9", "art": "9", "para": "", "text": "real", "mandatory": True},
        ],
    )
    _install_fake(monkeypatch, client)
    result = obligations_for_role("provider", "high-risk")
    assert len(result) == 1
    assert result[0].obligation_id == "obl_9"


def test_obligations_drops_malformed_rows(monkeypatch):
    """Rows missing required fields are dropped silently."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"art": "9", "text": "no id"},
            {"id": "obl_9", "art": "9"},                  # missing text
            {"id": "obl_x", "art": "9", "text": ""},      # empty text
            {"id": "obl_real", "art": "9", "text": "ok", "mandatory": True},
            "not-a-dict",
        ],
    )
    _install_fake(monkeypatch, client)
    result = obligations_for_role("provider", "high-risk")
    assert len(result) == 1
    assert result[0].obligation_id == "obl_real"


def test_obligations_swallows_exception(monkeypatch):
    """Cypher raises → ``[]``, no propagation."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        raise_exc=RuntimeError("driver crashed"),
    )
    _install_fake(monkeypatch, client)
    assert obligations_for_role("provider", "high-risk") == []


def test_obligations_timeout_returns_empty(monkeypatch):
    """Slow Cypher → ``[]``."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"id": "obl_9", "art": "9", "para": "", "text": "wont land", "mandatory": True}
        ],
        delay_seconds=0.2,
    )
    _install_fake(monkeypatch, client)
    assert obligations_for_role("provider", "high-risk", timeout_ms=10) == []


def test_obligations_mandatory_defaults_true(monkeypatch):
    """Missing ``mandatory`` key → defaults to True."""
    monkeypatch.setenv("REGENOLD_GRAPH_AWARE", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"id": "obl_9", "art": "9", "para": "", "text": "ok"}  # no mandatory key
        ],
    )
    _install_fake(monkeypatch, client)
    result = obligations_for_role("provider", "high-risk")
    assert len(result) == 1
    assert result[0].mandatory is True


# ─── Module-level guarantees ──────────────────────────────────────────────


def test_module_import_is_lightweight(monkeypatch):
    """Reimporting the module shouldn't trigger Neo4j or driver load."""
    import importlib

    import app.graph.client as gc

    sentinel = {"called": False}

    def _trap():
        sentinel["called"] = True
        raise AssertionError("get_graph_client called during module import")

    original = gc.get_graph_client
    gc.get_graph_client = _trap  # type: ignore[assignment]
    try:
        importlib.reload(gar)
    finally:
        gc.get_graph_client = original  # type: ignore[assignment]
    assert sentinel["called"] is False


def test_recital_grounding_is_frozen():
    """The dataclass is frozen — assignment should raise."""
    rg = RecitalGrounding(
        article_ref="Article 6", recital_number=47, recital_text="..."
    )
    with pytest.raises(Exception):
        rg.article_ref = "Article 9"  # type: ignore[misc]


def test_role_obligation_is_frozen():
    """The dataclass is frozen — assignment should raise."""
    obl = RoleObligation(
        obligation_id="obl_9", article_ref="Article 9", text="...", mandatory=True
    )
    with pytest.raises(Exception):
        obl.obligation_id = "obl_10"  # type: ignore[misc]


def test_public_api_surface():
    """``__all__`` exports the documented symbols."""
    assert set(gar.__all__) == {
        "RecitalGrounding",
        "RoleObligation",
        "is_enabled",
        "lookup_definition_by_term",
        "recitals_for_article",
        "obligations_for_role",
    }


def test_disabled_path_is_fast():
    """All three helpers return in well under 10 ms when env-gate is off.

    The doc promises "~1µs" — we test for a generous ceiling so the CI
    is robust across slow hosts but still catches a regression (e.g.
    accidentally firing a Cypher / loading the client at module import).
    """
    # NOTE: no env-var set (autouse fixture deletes it). Helpers should
    # short-circuit BEFORE touching the client.
    started = time.perf_counter()
    for _ in range(1000):
        assert lookup_definition_by_term("provider") is None
        assert recitals_for_article("Article 6") == []
        assert obligations_for_role("provider", "high-risk") == []
    elapsed_ms = (time.perf_counter() - started) * 1000
    # 3000 calls, expected ~µs each → comfortably under 100 ms.
    assert elapsed_ms < 500, f"disabled path too slow: {elapsed_ms:.1f}ms / 3000 calls"

"""R330 Z2 + Z3 — kg_context coordinate rendering and the dead deontic query.

Z2: ``render_kg_context`` printed the literal ``point (None)`` whenever a
SubPoint had no parent Point letter — 39 occurrences across 7 of the 15
captured failing Stage-2 prompts, including july7-221's
``Article 5, paragraph 1, point (None), subpoint (ii)``.

Z3: ``_DEONTIC_CYPHER`` ends ``LIMIT $limit`` but the caller bound only
``{"ids": ids}``, so live Aura answered ``ParameterMissing``, the error was
recorded as a graph *success*, and the block never rendered — at a measured
cost of 130-158 ms of Aura round-trip per request.
"""

import os
import re

os.environ["NEO4J_AUTO_SEED"] = "0"

from app.engines import kg_context as kg
from app.engines.kg_context import render_kg_context, reset_kg_context_memo


def setup_function():
    reset_kg_context_memo()


def _silence_other_layers(monkeypatch):
    monkeypatch.setattr(kg, "fetch_provision_hierarchy", lambda _refs: [])
    monkeypatch.setattr(kg, "fetch_recital_anchors", lambda _refs: [])
    monkeypatch.setattr(kg, "_render_semantic_layers", lambda _q, _refs: [])


# ── Z2 — coordinate rendering ────────────────────────────────────────────────


def test_subpoint_without_point_letter_never_renders_none(monkeypatch):
    """july7-221's exact shape: Art. 5(1) sub-point (ii) with no parent letter."""
    _silence_other_layers(monkeypatch)
    monkeypatch.setattr(
        kg,
        "fetch_subpoint_detail",
        lambda _refs: [{
            "cite": "Article 5",
            "para": "1",
            "letter": None,
            "roman": "ii",
            "sid": "article_5_1_ii",
            "text": "A nested enumerated element with no parent point letter.",
        }],
    )

    rendered = "\n".join(render_kg_context(["Art. 5"]))

    assert "KNOWLEDGE-GRAPH SUB-POINT DETAIL" in rendered
    assert "Article 5, paragraph 1, subpoint (ii)" in rendered
    assert "(None)" not in rendered
    assert ", point (" not in rendered  # the segment is omitted, not blanked


def test_blank_and_whitespace_letters_are_also_dropped(monkeypatch):
    _silence_other_layers(monkeypatch)
    monkeypatch.setattr(
        kg,
        "fetch_subpoint_detail",
        lambda _refs: [
            {"cite": "Article 5", "para": "1", "letter": "", "roman": "i",
             "text": "empty-string letter"},
            {"cite": "Article 5", "para": "2", "letter": "   ", "roman": "ii",
             "text": "whitespace-only letter"},
        ],
    )

    rendered = "\n".join(render_kg_context(["Art. 5"]))

    assert "Article 5, paragraph 1, subpoint (i)" in rendered
    assert "Article 5, paragraph 2, subpoint (ii)" in rendered
    assert "(None)" not in rendered
    assert ", point (" not in rendered  # the segment is omitted, not blanked


def test_real_point_letter_still_renders_the_full_coordinate(monkeypatch):
    """The R326 contract is unchanged when the graph does supply a letter."""
    _silence_other_layers(monkeypatch)
    monkeypatch.setattr(
        kg,
        "fetch_subpoint_detail",
        lambda _refs: [{
            "cite": "Article 5",
            "para": "1",
            "letter": "h",
            "roman": "iii",
            "sid": "article_5_1_h_iii",
            "text": "A nested enumerated element.",
        }],
    )

    rendered = "\n".join(render_kg_context(["Art. 5"]))

    assert "Article 5, paragraph 1, point (h), subpoint (iii)" in rendered


# ── Z3 — the deontic gate and its missing Cypher parameter ───────────────────


def test_deontic_gate_defaults_off_and_parses_fail_closed(monkeypatch):
    monkeypatch.delenv("REGENOLD_KG_DEONTIC", raising=False)
    assert kg._kg_deontic_enabled() is False
    for value in ("0", "off", "", "  ", "maybe", "2", "TRUE-ish"):
        monkeypatch.setenv("REGENOLD_KG_DEONTIC", value)
        assert kg._kg_deontic_enabled() is False, value
    for value in ("1", "true", "YES", " on "):
        monkeypatch.setenv("REGENOLD_KG_DEONTIC", value)
        assert kg._kg_deontic_enabled() is True, value


def test_deontic_path_is_not_called_with_the_gate_off(monkeypatch):
    """The 130-158 ms Aura round-trip must be gone, and output unchanged."""
    monkeypatch.delenv("REGENOLD_KG_DEONTIC", raising=False)
    _silence_other_layers(monkeypatch)
    monkeypatch.setattr(kg, "fetch_subpoint_detail", lambda _refs: [])

    calls: list[list[str]] = []

    def _boom(refs):
        calls.append(refs)
        raise AssertionError("fetch_deontic_context must not be called when OFF")

    monkeypatch.setattr(kg, "fetch_deontic_context", _boom)

    rendered = "\n".join(render_kg_context(["Annex III"]))

    assert calls == []
    assert "KNOWLEDGE-GRAPH REGULATORY CLASSIFICATION" not in rendered


def test_deontic_cypher_params_include_limit_when_the_gate_is_on(monkeypatch):
    monkeypatch.setenv("REGENOLD_KG_DEONTIC", "1")
    _silence_other_layers(monkeypatch)
    monkeypatch.setattr(kg, "fetch_subpoint_detail", lambda _refs: [])

    seen: list[tuple[str, dict]] = []

    def _read(cypher, params):
        seen.append((cypher, params))
        if cypher == kg._DEONTIC_CYPHER:
            return [{
                "cite": "Annex III",
                "practices": [],
                "annex_iii": ["Employment, workers management and access to self-employment"],
                "roles": [],
                "phases": [],
            }]
        return []

    monkeypatch.setattr(kg, "_bounded_execute_read", _read)
    reset_kg_context_memo()

    rendered = "\n".join(render_kg_context(["Annex III"]))

    deontic_calls = [(c, p) for c, p in seen if c == kg._DEONTIC_CYPHER]
    assert deontic_calls, "the deontic query must run when the gate is on"
    _cypher, params = deontic_calls[0]
    assert params["ids"] == ["annex_III"]
    assert "limit" in params, (
        "LIMIT $limit was unbound — live Aura answers ParameterMissing"
    )
    assert isinstance(params["limit"], int) and params["limit"] >= 1
    assert "KNOWLEDGE-GRAPH REGULATORY CLASSIFICATION" in rendered
    assert "Employment, workers management" in rendered


def test_every_deontic_cypher_placeholder_is_bound(monkeypatch):
    """The class of bug: a Cypher constant drifted from its single call site."""
    monkeypatch.setenv("REGENOLD_KG_DEONTIC", "1")

    captured: dict[str, dict] = {}

    def _read(cypher, params):
        if cypher == kg._DEONTIC_CYPHER:
            captured["params"] = dict(params)
        return []

    monkeypatch.setattr(kg, "_bounded_execute_read", _read)
    reset_kg_context_memo()

    kg.fetch_deontic_context(["Art. 5"])

    placeholders = set(re.findall(r"\$(\w+)", kg._DEONTIC_CYPHER))
    assert placeholders <= set(captured.get("params", {})), (
        f"unbound Cypher placeholders: {placeholders - set(captured.get('params', {}))}"
    )


def test_limit_is_folded_into_the_deontic_cache_key(monkeypatch):
    """A changed ref budget must not be served from a memo taken under the old one."""
    monkeypatch.setenv("REGENOLD_KG_DEONTIC", "1")

    keys: list[str] = []
    real_memoized = kg._memoized_read

    def _spy(cache_key, cypher, params):
        keys.append(cache_key)
        return real_memoized(cache_key, cypher, params)

    monkeypatch.setattr(kg, "_memoized_read", _spy)
    monkeypatch.setattr(kg, "_bounded_execute_read", lambda _c, _p: [])
    reset_kg_context_memo()

    monkeypatch.setenv("REGENOLD_KG_MAX_REFS", "8")
    kg.fetch_deontic_context(["Art. 5"])
    monkeypatch.setenv("REGENOLD_KG_MAX_REFS", "3")
    kg.fetch_deontic_context(["Art. 5"])

    assert keys == ["de:article_5:l8", "de:article_5:l3"]

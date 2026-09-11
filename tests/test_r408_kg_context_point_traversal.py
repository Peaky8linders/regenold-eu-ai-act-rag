"""R408/R409 — point text reaches Stage-2, and no cited provision is starved.

The first R408 test patched ``fetch_subpoint_detail`` itself, so it exercised
only the renderer: with the pre-R408 ``kg_context.py`` swapped back in it still
PASSED. These tests drive ``fetch_subpoint_detail`` through ``_memoized_read``
with the row shape the live query returns, and pin the R409 budget defect
two-sided: R408 sorted every row by ``cite`` under one ``LIMIT 24``, and
``"Annex" < "Article"``, so Annex III (24 point rows on live Aura) evicted every
Article's point text. The live-graph measurement (conftest blanks ``NEO4J_*``)
is ``docs/measurements/r409/kg_subpoint_allocation_probe.py``.
"""
from app.engines import kg_context as kg


def _points(ref_index, cite, n):
    return [
        {
            "ref_index": ref_index,
            "cite": cite,
            "para": "1",
            "letter": chr(97 + k),
            "sid": None,
            "roman": None,
            "text": f"{cite} point {chr(97 + k)} text",
        }
        for k in range(n)
    ]


# Live row counts on Aura (R409): Article 5 has 13 point rows, Annex III 24.
_ART5 = _points(0, "Article 5", 13)
_ANNEX3 = _points(1, "Annex III", 24)


def _serve(monkeypatch, rows):
    calls = []
    monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")

    def fake(cache_key, cypher, params):
        if cypher is not kg._SUBPOINT_CYPHER:
            return kg._ReadRows()
        calls.append(params)
        return kg._ReadRows(rows)

    monkeypatch.setattr(kg, "_memoized_read", fake)
    return calls


def test_legacy_global_limit_evicted_the_article():
    """Tripwire: the fixture reproduces the measured R408 eviction."""
    legacy = sorted(_ART5 + _ANNEX3, key=lambda r: r["cite"])[:24]
    assert {r["cite"] for r in legacy} == {"Annex III"}


def test_allocator_shares_the_budget_round_robin_in_ref_order():
    kept = kg._allocate_units(_ART5 + _ANNEX3, 24)
    assert [r["cite"] for r in kept] == ["Article 5"] * 12 + ["Annex III"] * 12

    # A short provision's unused share flows to the long one.
    kept = kg._allocate_units(_points(0, "Article 25", 5) + _ANNEX3, 24)
    assert [r["cite"] for r in kept].count("Article 25") == 5
    assert len(kept) == 24

    # Rows without ``ref_index`` degrade to a plain prefix; a zero budget is empty.
    bare = [{k: v for k, v in r.items() if k != "ref_index"} for r in _ANNEX3]
    assert kg._allocate_units(bare, 5) == bare[:5]
    assert kg._allocate_units(_ART5, 0) == []


def test_fetch_keeps_every_cited_provision(monkeypatch):
    calls = _serve(monkeypatch, _ART5 + _ANNEX3)
    rows = kg.fetch_subpoint_detail(["Article 5", "Annex III"])

    assert len(calls) == 1
    assert calls[0]["ids"] == ["article_5", "annex_III"]
    # The query must not cut a later provision before the budget is shared.
    assert calls[0]["max_rows"] >= 24 * len(calls[0]["ids"])
    cites = [r["cite"] for r in rows]
    assert {"Article 5", "Annex III"} <= set(cites)
    assert cites.index("Annex III") > max(i for i, c in enumerate(cites) if c == "Article 5")


def test_bare_point_renders_its_own_text(monkeypatch):
    _serve(monkeypatch, _points(0, "Article 25", 3))
    monkeypatch.setattr(kg, "fetch_provision_hierarchy", lambda _refs: [])
    text = "\n".join(kg.render_kg_context(["Article 25"]))

    assert "- Article 25, paragraph 1, point (a): Article 25 point a text" in text
    assert "subpoint (" not in text

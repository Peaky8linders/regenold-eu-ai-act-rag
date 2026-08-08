"""R324 — regression tests for the R323 deep-review findings.

Every test here is written against a case that was MEASURED failing on
``8cd05a8`` (the R323 HEAD), not against the shape of the fix. Where a test
could pass for the wrong reason, it asserts the negative control too.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import app.engines.kg_context as kg
from app.data.provision_hierarchy import build_hierarchy_payload
from app.engines.kg_context import _UNIT_HARD_CEILING, _flat
from app.routes.regenold import (
    _add_prose_named_refs,
    _prose_mention_is_real_citation,
)


# ── C1: the foreign-citation guard ───────────────────────────────────────────
#
# All five LEAK cases below shipped a fabricated AI Act article on R323 HEAD.
# The KEEP cases are the controls: a guard that suppresses these is worse than
# the leak, because dropping a real citation is the R142.1 failure mode.

LEAKS = [
    # (prose, the AI Act article it fabricated pre-R324)
    ("Article 10, second subparagraph, point (b), of Regulation (EU) No 1025/2012 applies.", "Article 10"),
    ("Article 6(1), point (a), second subparagraph, of Regulation (EU) 2016/679 applies.", "Article 6"),
    ("Regulation (EU) No 1025/2012, Article 10 requires standards.", "Article 10"),
    ("Under Regulation (EU) 2016/679, Article 35 requires a DPIA.", "Article 35"),
    ("Article 5 of Regulation 2016/679 sets the principles.", "Article 5"),
    ("Under Regulation (EC) No 765/2008 Article 30 applies.", "Article 30"),
]

KEEPS = [
    ("Article 13 requires transparency for high-risk systems.", "Article 13"),
    # The decisive control: a foreign instrument in the NEXT sentence must not
    # suppress this one. A naive window widening fails exactly here.
    (
        "Article 13 requires transparency for high-risk systems. "
        "Article 35 of Regulation (EU) 2016/679 requires a DPIA.",
        "Article 13",
    ),
    ("Article 6 of Regulation (EU) 2024/1689 sets classification.", "Article 6"),
    ("Article 11 requires technical documentation, and Annex IV lists its contents.", "Annex IV"),
]


@pytest.mark.parametrize("prose,fabricated", LEAKS)
def test_foreign_citation_is_not_promoted(prose: str, fabricated: str) -> None:
    assert fabricated not in _add_prose_named_refs([], prose)


@pytest.mark.parametrize("prose,genuine", KEEPS)
def test_genuine_ai_act_citation_survives(prose: str, genuine: str) -> None:
    assert genuine in _add_prose_named_refs([], prose)


def test_ahead_window_is_bounded_by_the_clause():
    """The window must not reach into the next sentence.

    Pins the mechanism, not just the outcome: if a future round widens the
    window without bounding it, this fails while the outcome test above might
    still pass by luck of char counts.
    """
    prose = (
        "Article 13 requires transparency. "
        "Article 35 of Regulation (EU) 2016/679 requires a DPIA."
    )
    start = prose.index("Article 13")
    end = start + len("Article 13")
    assert "Regulation" not in kg_ahead(prose, end)


def kg_ahead(prose: str, end: int) -> str:
    from app.routes.regenold import _ahead_window

    return _ahead_window(prose, end)


def test_component_d_applies_the_foreign_instrument_guard():
    """Component D was a SECOND, unguarded prose-to-citation path.

    R323's regex widening measured byte-identical on the wire because this
    path re-added whatever the guard dropped. Asserted at the guard level so
    the test does not need a live Stage-2.
    """
    prose = "Article 30 of Regulation (EC) No 765/2008 applies."
    m_start = prose.index("Article 30")
    m_end = m_start + len("Article 30")
    assert not _prose_mention_is_real_citation(prose, m_start, m_end)

    import inspect

    from app.routes import regenold

    src = inspect.getsource(regenold)
    marker = "prose_citations = set()"
    idx = src.index(marker)
    window = src[idx : idx + 700]
    assert "_prose_mention_is_real_citation" in window, (
        "Component D must route its prose extraction through the "
        "foreign-instrument guard, or C1's fix is undone on the wire."
    )


# ── C2: the _flat enumeration ceiling ────────────────────────────────────────


def test_unit_hard_ceiling_is_a_ceiling_not_a_switch():
    """Past the ceiling, R323 fell back to ``limit`` instead of cutting AT it.

    Measured on HEAD: Article 5(1) (4701 chars) delivered at 905 — 19% — so
    prohibitions (c) through (h) never reached the model.
    """
    body = {n["id"]: n.get("text", "") for n in build_hierarchy_payload().paragraph_nodes}
    art_5_1 = body["article_5_1"]
    assert len(art_5_1) > _UNIT_HARD_CEILING, "fixture assumption: 5(1) is oversized"

    out = _flat(art_5_1, 900)
    assert len(out) > 2000, f"regressed to the R323 cliff: {len(out)} chars"
    assert len(out) <= _UNIT_HARD_CEILING + 8, "ceiling must still bound the worst case"
    assert out.endswith("[...]"), "a truncated unit must say so"
    # The concrete legal consequence: more of the prohibition list arrives.
    assert "(c)" in out and "(d)" in out


def test_short_enumeration_still_delivered_whole():
    """The R323 win must survive the R324 fix — Art 27(1) is under the ceiling."""
    body = {n["id"]: n.get("text", "") for n in build_hierarchy_payload().paragraph_nodes}
    art_27_1 = body["article_27_1"]
    out = _flat(art_27_1, 900)
    assert out == " ".join(art_27_1.split())
    assert not out.endswith("[...]")


def test_hierarchy_cypher_orders_numerically():
    """``number`` is a STRING property, so a bare ORDER BY sorted 1,10..19,2.

    Measured: Article 3 kept 1, 10-19, 2, 20-29, 3, 30 and dropped 44 of 68
    definitions — including 3(4) deployer and 3(6) importer.
    """
    assert "toIntegerOrNull(u.number)" in kg._HIERARCHY_CYPHER
    assert "toIntegerOrNull(r.number)" in kg._RECITAL_CYPHER
    assert "toIntegerOrNull(p.number)" in kg._SUBPOINT_CYPHER


def test_article_3_numeric_order_keeps_the_role_definitions():
    """The consequence of the sort, asserted on real data rather than the SQL."""
    nums = [
        n["number"]
        for n in build_hierarchy_payload().paragraph_nodes
        if n["id"].startswith("article_3_")
    ]
    lexicographic = sorted(nums)[:24]
    numeric = sorted(nums, key=int)[:24]
    # deployer / authorised rep / importer / distributor
    for role_def in ("4", "5", "6", "7"):
        assert role_def not in lexicographic, "fixture assumption: the bug existed"
        assert role_def in numeric


# ── C3: the char budget must not delete the blocks R323 added ────────────────


def _fake_rows(refs):
    paras: dict[str, list[dict]] = {}
    for n in build_hierarchy_payload().paragraph_nodes:
        paras.setdefault(n["id"].rsplit("_", 1)[0], []).append(
            {"num": n.get("number"), "text": n.get("text")}
        )
    out = []
    for r in refs:
        aid = "article_" + r.split()[1] if r.startswith("Article") else "annex_" + r.split()[1]
        if aid in paras:
            out.append({"id": aid, "cite": r, "title": "", "units": paras[aid]})
    return out


@pytest.mark.parametrize(
    "refs",
    [
        [f"Article {n}" for n in range(9, 16)],  # the HRAIS chain
        ["Article 5", "Article 6", "Article 9", "Article 10",
         "Article 11", "Article 13", "Article 26", "Article 50"],  # _DEFAULT_MAX_REFS
    ],
)
def test_new_layers_survive_a_heavy_provision_block(refs):
    """Both collapsed to a single block on R323 HEAD.

    The dropped block is the one whose own heading says "a prohibition stated
    without its exception is WRONG", so losing it under budget pressure is the
    failure it was added to prevent.
    """
    sub = [{"cite": "Article 5", "para": "1", "letter": "h",
            "sid": "article_5_1_h_i", "text": "X" * 400}]
    deo = [{"cite": "Article 5", "practices": ["social scoring"],
            "annex_iii": [], "roles": [], "phases": []}]
    with patch.object(kg, "kg_context_enabled", return_value=True), \
         patch.object(kg, "fetch_provision_hierarchy", return_value=_fake_rows(refs)), \
         patch.object(kg, "fetch_subpoint_detail", return_value=sub), \
         patch.object(kg, "fetch_deontic_context", return_value=deo), \
         patch.object(kg, "fetch_recital_anchors", return_value=[]), \
         patch.object(kg, "fetch_cross_regulatory_context", return_value=[]):
        kg.reset_render_memo()
        parts = kg.render_kg_context(refs)

    assert any("SUB-POINT DETAIL" in p for p in parts)
    assert any("REGULATORY CLASSIFICATION" in p for p in parts)
    assert sum(len(p) for p in parts) <= 16000


# ── Important: cache key + memo reset ────────────────────────────────────────


def test_kg_max_chars_is_in_the_engine_cache_key():
    """Unkeyed, an in-process two-arm A/B of this ceiling measures nothing.

    Its five R315 siblings were keyed; R323 added this one and did not.
    """
    import inspect

    from app.routes import regenold

    src = inspect.getsource(regenold._engine_cache_key)
    for knob in (
        "REGENOLD_KG_MAX_CHARS",
        "REGENOLD_KG_UNIT_CHARS",
        "REGENOLD_KG_MAX_REFS",
    ):
        assert knob in src, f"{knob} flips the engine output and must be keyed"


def test_render_memo_reset_exists_and_clears():
    """R323's docstring claimed a per-request reset that did not exist."""
    kg._RENDER_MEMO.set((("Article 5",), ["stale"]))
    kg.reset_render_memo()
    assert kg._RENDER_MEMO.get() is None


def test_route_resets_the_render_memo():
    import inspect

    from app.routes import regenold

    src = inspect.getsource(regenold)
    assert "reset_render_memo()" in src, (
        "the route must reset the memo per request, beside _request_intent_cache"
    )

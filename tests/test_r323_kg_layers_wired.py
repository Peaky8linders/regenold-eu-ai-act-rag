"""R323 — the seeded graph layers nothing was reading are now on the answer path.

MEASURED BEFORE: the graph holds 18 node labels and 16 relationship types, but
a live request issued only FOUR distinct Cypher shapes and touched Article /
Annex / Paragraph / Point / Recital plus three edge types. The entire deontic
layer — the one that answers "is this prohibited?", "what must a deployer do?",
"is this Annex III?" — was seeded and never read:

    SubPoint 37          HAS_SUBPOINT 37            <- Article 5(1)(h)(i)-(iii)
    Practice 8           PROHIBITED_UNDER 8
    AnnexIIICategory 8   TRIGGERS_HIGH_RISK_UNDER 8
    OperatorRole 5       HAS_OBLIGATION_ARTICLE 36  <- carries a tier property
    LifecyclePhase 4     APPLIES_TO 20

MEASURED AFTER: 7 distinct shapes, and the edge set gains HAS_SUBPOINT,
PROHIBITED_UNDER, TRIGGERS_HIGH_RISK_UNDER and APPLIES_TO. Query volume held at
the pre-wiring level (23 per 3 requests) because the request-scoped memo removed
the 3x duplicate render that used to pay for every round-trip three times.

Everything is rendered as NON-CITABLE context, exactly like the existing
hierarchy block — additive, never a ranker, never a wire citation. That is the
R252 line and these tests pin it.

``tests/conftest.py`` deliberately deletes ``NEO4J_URI`` so unit tests never
depend on a network service. A ``skipif(no live graph)`` marker would therefore
ALWAYS skip here, and a test that cannot fail pins nothing — so the rendering
contract is exercised against a FAKE client returning rows copied verbatim from
the live instance.
"""

from __future__ import annotations

import pytest

import app.engines.kg_context as K


class _FakeClient:
    """Returns canned rows keyed on which Cypher shape is being run."""

    enabled = True

    def __init__(self, *, subpoints=None, deontic=None) -> None:
        self._subpoints = subpoints or []
        self._deontic = deontic or []

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
        if "HAS_SUBPOINT" in query:
            return list(self._subpoints)
        if "PROHIBITED_UNDER" in query:
            return list(self._deontic)
        return []


# Rows copied from the live Aura instance (article_5_1_h_i/ii/iii, 164/192/545 chars).
_LIVE_SUBPOINT_ROWS = [
    {
        "cite": "Article 5",
        "para": "1",
        "letter": "h",
        "sid": "article_5_1_h_i",
        "text": (
            "the targeted search for specific victims of abduction, trafficking "
            "in human beings or sexual exploitation, as well as the search for "
            "missing persons"
        ),
    },
    {
        "cite": "Article 5",
        "para": "1",
        "letter": "h",
        "sid": "article_5_1_h_ii",
        "text": (
            "the prevention of a specific, substantial and imminent threat to the "
            "life or physical safety of natural persons"
        ),
    },
    {
        "cite": "Article 5",
        "para": "1",
        "letter": "h",
        "sid": "article_5_1_h_iii",
        "text": (
            "the localisation or identification of a person suspected of having "
            "committed a criminal offence, for the purpose of conducting a "
            "criminal investigation"
        ),
    },
]

_LIVE_DEONTIC_ROWS = [
    {
        "cite": "Article 26",
        "practices": [],
        "annex_iii": [],
        "roles": ["Deployer (primary)"],
        "phases": ["High-risk AI obligations from 2026-08-02"],
    }
]


@pytest.fixture()
def fake_graph(monkeypatch: pytest.MonkeyPatch):
    """Install a fake graph client and clear the request-scoped memo."""

    def _install(**kwargs):
        import app.graph.client as GC

        client = _FakeClient(**kwargs)
        monkeypatch.setattr(GC, "get_graph_client", lambda: client)
        monkeypatch.setattr(K, "kg_context_enabled", lambda: True)
        K._RENDER_MEMO.set(None)
        return client

    yield _install
    K._RENDER_MEMO.set(None)


def _render(refs: list[str]) -> str:
    return "\n".join(K.render_kg_context(refs) or [])


# ── the fetchers exist and are fail-soft ────────────────────────────────────


@pytest.mark.parametrize("fn", [K.fetch_subpoint_detail, K.fetch_deontic_context])
def test_fetchers_return_a_list_and_never_raise(fn) -> None:
    for refs in ([], ["not a citation"], ["Article 5"], None):
        assert isinstance(fn(refs), list)


def test_fetchers_are_empty_without_resolvable_refs() -> None:
    assert K.fetch_subpoint_detail(["nonsense"]) == []
    assert K.fetch_deontic_context(["nonsense"]) == []


def test_graph_rows_swallows_a_broken_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """A graph failure must degrade to no context, never break the answer."""
    import app.graph.client as GC

    def boom():
        raise RuntimeError("instance gone")

    monkeypatch.setattr(GC, "get_graph_client", boom)
    assert K._graph_rows("MATCH (n) RETURN n", {}) == []


# ── the layers actually reach the rendered context ──────────────────────────


def test_article_5_rbi_carve_outs_reach_the_context(fake_graph) -> None:
    """Article 5(1)(h)(i)-(iii) are the real-time RBI EXCEPTIONS.

    Surfacing the prohibition without them states the law backwards. They sat
    in the graph unread before R323.
    """
    fake_graph(subpoints=_LIVE_SUBPOINT_ROWS)
    rendered = _render(["Article 5"])
    assert "SUB-POINT DETAIL" in rendered
    for roman in ("(i)", "(ii)", "(iii)"):
        assert f"Article 5(1)(h){roman}" in rendered, f"missing carve-out {roman}"
    assert "targeted search" in rendered


def test_operator_duty_and_tier_reach_the_context(fake_graph) -> None:
    """Article 26 is the deployer's article; the tier marks a primary duty."""
    fake_graph(deontic=_LIVE_DEONTIC_ROWS)
    rendered = _render(["Article 26"])
    assert "REGULATORY CLASSIFICATION" in rendered
    assert "operator duties" in rendered
    assert "Deployer" in rendered
    assert "primary" in rendered
    assert "2026-08-02" in rendered


def test_context_is_labelled_non_citable(fake_graph) -> None:
    """The R252 line: graph output is context, never licence to cite more."""
    fake_graph(subpoints=_LIVE_SUBPOINT_ROWS, deontic=_LIVE_DEONTIC_ROWS)
    assert "do NOT cite" in _render(["Article 5"])


def test_empty_graph_renders_no_new_sections(fake_graph) -> None:
    """No rows must mean no heading — never an empty labelled block."""
    fake_graph()
    rendered = _render(["Article 5"])
    assert "SUB-POINT DETAIL" not in rendered
    assert "REGULATORY CLASSIFICATION" not in rendered


# ── the request-scoped memo ─────────────────────────────────────────────────


def test_repeat_render_issues_no_further_graph_queries(fake_graph) -> None:
    """render_kg_context ran 3x per request with identical refs before R323."""
    client = fake_graph(subpoints=_LIVE_SUBPOINT_ROWS, deontic=_LIVE_DEONTIC_ROWS)
    seen: list[str] = []
    inner = client.execute_read

    def spy(query, parameters=None):
        seen.append(query)
        return inner(query, parameters)

    client.execute_read = spy  # type: ignore[method-assign]

    first = K.render_kg_context(["Article 5"])
    after_first = len(seen)
    second = K.render_kg_context(["Article 5"])

    assert after_first > 0, "the first render should query the graph"
    assert len(seen) == after_first, "the repeat render must be a memo hit"
    assert first == second


def test_memo_is_keyed_on_the_exact_refs() -> None:
    """A different question must never read another question's entry."""
    K._RENDER_MEMO.set((("Article 5",), ["CACHED-BLOCK"]))
    try:
        assert K.render_kg_context(["Article 5"]) == ["CACHED-BLOCK"]
        assert K.render_kg_context(["Article 26"]) != ["CACHED-BLOCK"]
    finally:
        K._RENDER_MEMO.set(None)


def test_memo_is_bypassed_when_the_gate_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(K, "kg_context_enabled", lambda: False)
    K._RENDER_MEMO.set((("Article 5",), ["CACHED-BLOCK"]))
    try:
        assert K.render_kg_context(["Article 5"]) == []
    finally:
        K._RENDER_MEMO.set(None)

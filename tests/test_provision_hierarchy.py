"""Tests for the nesting-aware provision hierarchy parser.

The graph seed needs a FAITHFUL sub-point tree: paragraphs → lettered points
(a)(b)(c)… → nested roman sub-points (i)(ii)(iii). The shared wire parser
``provision_text._subpoints`` FLATTENS the tree into a single dict keyed by
letter, which (a) mislabels the roman carve-outs as top-level "letters" and
(b) COLLIDES the romans of two different letters (Art 5(1)(c)(i) and
Art 5(1)(h)(i) both become the single key ``"i"``, last-write-wins) — data
loss + a scrambled structure verified live (``article_5_1`` points were
``[a,b,c,i,ii,d,e,f,g,h,iii]``).

``provision_text.subpoints_nested`` is the new, additive, nesting-aware parser
used ONLY by the graph ingest (the wire parser is untouched → davidath
byte-identical). Disambiguation rule (verified against the corpus): a
roman-valued marker introduced by ``:`` opens a nested list under the current
letter; a marker that continues the top-level ``a→b→c…`` letter sequence is a
letter (so Article 16's real letter ``(i)`` stays a letter, while Article
5(1)(h)'s roman ``(i)`` nests).
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from app.data.provision_text import article_body, _paragraphs, subpoints_nested


def _para(article: str, n: int | None = None) -> str:
    body = article_body(article) or ""
    if n is None:
        return body
    return _paragraphs(body).get(n, body)


# ── Article 5(1): the canonical nesting case ────────────────────────────────
# Letters (a)-(h); (c) carries nested romans (i)(ii); (h) carries (i)(ii)(iii).


def test_article_5_1_top_level_letters_are_a_to_h() -> None:
    tree = subpoints_nested(_para("Article 5", 1))
    assert list(tree.keys()) == ["a", "b", "c", "d", "e", "f", "g", "h"], (
        f"top-level points must be the 8 letters a-h in order; got {list(tree.keys())}"
    )


def test_article_5_1_c_has_two_nested_romans() -> None:
    tree = subpoints_nested(_para("Article 5", 1))
    assert list(tree["c"]["subs"].keys()) == ["i", "ii"], (
        f"(c) social-scoring carries nested (i)(ii); got {list(tree['c']['subs'].keys())}"
    )


def test_article_5_1_h_has_three_nested_romans() -> None:
    tree = subpoints_nested(_para("Article 5", 1))
    assert list(tree["h"]["subs"].keys()) == ["i", "ii", "iii"], (
        f"(h) real-time RBI carries nested (i)(ii)(iii); got {list(tree['h']['subs'].keys())}"
    )


def test_article_5_1_c_and_h_romans_do_not_collide() -> None:
    """The exact data-loss bug: (c)(i) and (h)(i) must be DISTINCT text."""
    tree = subpoints_nested(_para("Article 5", 1))
    c_i = tree["c"]["subs"]["i"]
    h_i = tree["h"]["subs"]["i"]
    assert c_i and h_i and c_i != h_i, (
        "Article 5(1)(c)(i) and 5(1)(h)(i) collided into the same text (flatten bug)"
    )


def test_article_5_1_non_nested_letters_have_empty_subs() -> None:
    tree = subpoints_nested(_para("Article 5", 1))
    for letter in ("a", "b", "d", "e", "f", "g"):
        assert tree[letter]["subs"] == {}, f"letter ({letter}) should carry no nested romans"


def test_article_5_1_text_is_verbatim() -> None:
    tree = subpoints_nested(_para("Article 5", 1))
    # (a) is the subliminal-techniques prohibition
    assert "subliminal" in tree["a"]["text"].lower()
    # (h)(iii) is the criminal-offence carve-out (Annex II threshold)
    assert tree["h"]["subs"]["iii"], "(h)(iii) text must be present verbatim"


# ── Article 13(3): romans nest under (b) ────────────────────────────────────


def test_article_13_3_romans_nest_under_b() -> None:
    tree = subpoints_nested(_para("Article 13", 3))
    assert list(tree.keys()) == ["a", "b", "c", "d", "e", "f"], (
        f"Art 13(3) top-level letters a-f; got {list(tree.keys())}"
    )
    assert list(tree["b"]["subs"].keys()) == ["i", "ii", "iii", "iv", "v", "vi", "vii"], (
        f"Art 13(3)(b) carries nested (i)-(vii); got {list(tree['b']['subs'].keys())}"
    )


# ── Article 16: real letter (i) must NOT be treated as a roman ──────────────


def test_article_16_letter_i_is_a_top_level_letter_not_a_roman() -> None:
    tree = subpoints_nested(_para("Article 16"))
    keys = list(tree.keys())
    assert "i" in keys and "j" in keys and "k" in keys and "l" in keys, (
        f"Art 16 has real letter points (i)(j)(k)(l); got {keys}"
    )
    # None of them should carry nested romans (they are flat obligations).
    assert tree["i"]["subs"] == {}, "Art 16 (i) is a letter, not a nesting parent"


# ── Article 6(3): the hardcoded live consumer needs flat (a)(b)(c) Points ───


def test_article_6_3_points_are_flat_a_b_c_d() -> None:
    tree = subpoints_nested(_para("Article 6", 3))
    assert list(tree.keys()) == ["a", "b", "c", "d"], (
        f"Art 6(3) must expose flat (a)(b)(c)(d) for the live Cypher; got {list(tree.keys())}"
    )
    for letter in ("a", "b", "c", "d"):
        assert tree[letter]["subs"] == {}, f"Art 6(3)({letter}) carries no nested romans"


# ── Paragraph-less / marker-less bodies degrade gracefully ──────────────────


def test_no_subpoints_returns_empty() -> None:
    assert subpoints_nested("A flat paragraph with no lettered list items.") == {}


def test_empty_text_returns_empty() -> None:
    assert subpoints_nested("") == {}
    assert subpoints_nested("   ") == {}


# ── Verbatim fidelity: nested text carries no marker artefacts ──────────────


def test_nested_text_does_not_include_child_markers() -> None:
    """A letter's own ``text`` must stop where its first nested roman begins."""
    tree = subpoints_nested(_para("Article 5", 1))
    # (h)'s own text is the RBI chapeau; the (i)/(ii)/(iii) objectives live in subs.
    h_text = tree["h"]["text"]
    assert "(ii)" not in h_text and "(iii)" not in h_text, (
        "letter text leaked a child roman marker — the split boundary is wrong"
    )


# ── The full hierarchy payload (Article/Annex → Paragraph → Point → SubPoint) ─

from app.data.provision_hierarchy import build_hierarchy_payload


def test_hierarchy_payload_has_no_id_collisions() -> None:
    p = build_hierarchy_payload()
    ids = (
        [n["id"] for n in p.paragraph_nodes]
        + [n["id"] for n in p.point_nodes]
        + [n["id"] for n in p.subpoint_nodes]
    )
    assert len(ids) == len(set(ids)), "hierarchy node ids collide"


def test_hierarchy_preserves_flat_art_6_3_points() -> None:
    """The live Art 6(3) Cypher needs flat (a)(b)(c)(d) Points under article_6_3."""
    p = build_hierarchy_payload()
    letters = sorted(
        n["letter"] for n in p.point_nodes if n["id"].startswith("article_6_3_")
    )
    assert letters == ["a", "b", "c", "d"]


def test_hierarchy_nests_art_5_1_romans_without_collision() -> None:
    p = build_hierarchy_payload()
    sub_ids = {n["id"] for n in p.subpoint_nodes if n["id"].startswith("article_5_1_")}
    # (c) and (h) each carry their own scoped romans — no flat collision.
    assert "article_5_1_c_i" in sub_ids
    assert "article_5_1_h_i" in sub_ids
    assert "article_5_1_h_iii" in sub_ids
    # And the parent Points are clean letters, not scrambled with romans.
    p51_letters = sorted(
        n["letter"]
        for n in p.point_nodes
        if n["id"].startswith("article_5_1_") and n["id"].count("_") == 3
    )
    assert p51_letters == ["a", "b", "c", "d", "e", "f", "g", "h"]


def test_hierarchy_every_edge_endpoint_resolves() -> None:
    """No dangling HAS_PARAGRAPH / HAS_POINT / HAS_SUBPOINT edges within the tree."""
    p = build_hierarchy_payload()
    para_ids = {n["id"] for n in p.paragraph_nodes}
    point_ids = {n["id"] for n in p.point_nodes}
    sub_ids = {n["id"] for n in p.subpoint_nodes}
    for e in p.has_point_edges:
        assert e["source_id"] in para_ids
        assert e["target_id"] in point_ids
    for e in p.has_subpoint_edges:
        assert e["source_id"] in point_ids
        assert e["target_id"] in sub_ids
    # HAS_PARAGRAPH targets are Paragraphs; sources are Article/Annex roots.
    for e in p.has_paragraph_edges:
        assert e["target_id"] in para_ids
        assert e["source_id"].startswith(("article_", "annex_"))

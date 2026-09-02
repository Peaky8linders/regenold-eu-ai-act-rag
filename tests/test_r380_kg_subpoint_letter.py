"""R380 — ``_SUBPOINT_CYPHER`` selects a property Point nodes never carry.

Measured live against the Aura graph: ``Point`` nodes have ``.letter`` on
421/421 and ``.number`` on 0/421 (confirmed against the seeder,
``app/data/provision_hierarchy.py``'s ``_MERGE_POINT`` sets only
``pt.letter``, never ``pt.number``; ``scripts/seed_neo4j_kb.py`` mirrors it).
Yet ``_SUBPOINT_CYPHER`` selected ``pt.number AS letter`` — always null — so
every sub-point coordinate rendered into the Stage-2 "SUB-POINT DETAIL" block
silently lost its point letter. The R330 "Z2" patch
(``tests/test_r330_kg_context_fixes.py``) only suppressed the literal
``point (None)`` symptom; it did not restore the letter.

``SubPoint`` nodes carry ``.roman`` (``_MERGE_SUBPOINT`` sets ``sp.roman``,
never ``sp.number``), and ``_SUBPOINT_CYPHER`` already selected
``sp.roman AS roman`` correctly — only the Point-side selection was wrong.

The sibling query ``_FOCUS_COORD_CYPHER`` (``app/engines/graph_semantic.py``)
already gets this right: ``head([n IN chain WHERE n:Point | n.letter])``.
"""

import os

os.environ["NEO4J_AUTO_SEED"] = "0"

from app.engines import kg_context as kg
from app.engines.kg_context import render_kg_context, reset_kg_context_memo


def setup_function():
    reset_kg_context_memo()


def _silence_other_layers(monkeypatch):
    monkeypatch.setattr(kg, "fetch_provision_hierarchy", lambda _refs: [])
    monkeypatch.setattr(kg, "fetch_recital_anchors", lambda _refs: [])
    monkeypatch.setattr(kg, "_render_semantic_layers", lambda _q, _refs: [])


# ── the Cypher must actually read the property Point nodes carry ───────────


def test_subpoint_cypher_selects_point_letter_not_point_number():
    """``Point`` nodes carry ``.letter`` (421/421); ``.number`` is 0/421."""
    assert "coalesce(pt.letter, pt.number) AS letter" in kg._SUBPOINT_CYPHER, (
        "the Point-side selection must prefer pt.letter — the property the "
        "seeder (app/data/provision_hierarchy.py::_MERGE_POINT) actually sets"
    )
    assert "pt.number AS letter" not in kg._SUBPOINT_CYPHER, (
        "a bare pt.number selection is always null on the live graph"
    )


def test_subpoint_cypher_still_selects_subpoint_roman():
    """``SubPoint`` nodes carry ``.roman`` — this side was already correct."""
    assert "sp.roman AS roman" in kg._SUBPOINT_CYPHER


# ── end-to-end: a fetch shaped like the FIXED live query renders the letter ─


def test_fixed_cypher_row_shape_renders_the_point_letter(monkeypatch):
    """Once the Cypher reads ``pt.letter``, a real Point letter reaches the
    renderer through the ``letter`` alias exactly like the pre-existing R330
    contract test (``test_real_point_letter_still_renders_the_full_coordinate``)
    — pinned again here under the R380 name so this file is self-contained.
    """
    _silence_other_layers(monkeypatch)
    monkeypatch.setattr(
        kg,
        "fetch_subpoint_detail",
        lambda _refs: [{
            "cite": "Article 5",
            "para": "1",
            "letter": "b",
            "roman": "i",
            "sid": "article_5_1_b_i",
            "text": "A nested enumerated element under point (b).",
        }],
    )

    rendered = "\n".join(render_kg_context(["Art. 5"]))

    assert "Article 5, paragraph 1, point (b), subpoint (i)" in rendered
    assert "(None)" not in rendered

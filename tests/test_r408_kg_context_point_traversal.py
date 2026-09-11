"""Test 2-hop Point traversal for points without subpoints."""
from unittest.mock import patch
from app.engines import kg_context


def test_subpoint_cypher_includes_points_without_subpoints():
    mock_rows = [
        {
            "cite": "Article 13",
            "para": "3",
            "letter": "a",
            "sid": None,
            "roman": None,
            "text": "the identity and the contact details of the provider",
        },
        {
            "cite": "Article 13",
            "para": "3",
            "letter": "b",
            "sid": "art13_3_b_i",
            "roman": "i",
            "text": "its intended purpose",
        },
    ]

    with patch.object(kg_context, "kg_context_enabled", return_value=True), \
         patch.object(kg_context, "fetch_provision_hierarchy", return_value=[]), \
         patch.object(kg_context, "fetch_subpoint_detail", return_value=mock_rows):

        parts = kg_context.render_kg_context(["Article 13"])
        full_text = "\n".join(parts)

        assert "point (a): the identity and the contact details" in full_text
        assert "subpoint (i): its intended purpose" in full_text

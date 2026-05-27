"""Unit test to verify that the Article 9 summary in the KB contains the verbatim procedural steps.

Asserts that key tokens (identify, analyse, estimate, evaluate, misuse, mitigation) are present.
"""

from __future__ import annotations

from app.data.kb import EC_CHECKER_OBLIGATION_MAP


def test_article_9_summary_has_procedural_steps() -> None:
    """Art. 9 stub must surface the specific procedural verbs: identify, analyse, estimate, evaluate."""
    assert "Art. 9" in EC_CHECKER_OBLIGATION_MAP, "Art. 9 missing from EC_CHECKER_OBLIGATION_MAP"
    summary = EC_CHECKER_OBLIGATION_MAP["Art. 9"]["summary"]
    summary_lower = summary.lower()

    # Verbatim procedural steps checklist
    assert "identify" in summary_lower, "Art. 9 stub missing 'identify'"
    assert "analyse" in summary_lower, "Art. 9 stub missing 'analyse'"
    assert "estimate" in summary_lower, "Art. 9 stub missing 'estimate'"
    assert "evaluate" in summary_lower, "Art. 9 stub missing 'evaluate'"

    # Misuse and mitigation context
    assert "misuse" in summary_lower, "Art. 9 stub missing 'misuse'"
    assert "mitigation" in summary_lower, "Art. 9 stub missing 'mitigation'"
    assert "post-market" in summary_lower, "Art. 9 stub missing 'post-market'"

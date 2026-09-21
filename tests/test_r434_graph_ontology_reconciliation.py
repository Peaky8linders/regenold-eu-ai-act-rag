"""R434 focused regressions for ontology and graph reconciliation audits."""
from pathlib import Path

from app.data.role_obligations import applies_to_role, articles_for_role

REPO = Path(__file__).resolve().parents[1]


def test_role_article_queries_normalize_authorised_spelling() -> None:
    assert articles_for_role("authorised_rep", include_secondary=False)
    assert applies_to_role("Art. 22(2)", "authorised_rep")
    assert applies_to_role("Art. 22(2)", "authorized_representative")


def test_seed_reconciles_shadow_article_properties_and_edge_direction() -> None:
    source = (REPO / "scripts/seed_neo4j_kb.py").read_text(encoding="utf-8")
    assert "shadow.strict_citation = 'Article ' + substring(shadow.id, 3)" in source
    assert "MERGE (canonical)-[:APPLIES_TO_ROLE]->(role)" in source
    assert "MERGE (canonical)-[:REQUIRES]" not in source


def test_tail_gate_diagnoses_cut_final_sentence_not_whole_answer() -> None:
    source = (REPO / "docs/measurements/r413/tail_repair_gate.py").read_text(
        encoding="utf-8"
    )
    assert 'cut_fragment = _sentence_suffix(case["truncated"])' in source
    assert 'diag = _diagnose(shipped, cut_fragment)' in source

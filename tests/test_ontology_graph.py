from unittest.mock import MagicMock, patch
from app.graph.ontology_ingest import ingest_ontology, _provision_root


@patch("app.graph.ontology_ingest.get_graph_client")
def test_ingest_ontology(mock_get_client):
    mock_client = MagicMock()
    mock_client.enabled = True
    mock_get_client.return_value = mock_client

    ingest_ontology()

    # ingest_ontology writes the ontology batch (roles/practices/AnnexIII/
    # phases) and THEN drives ingest_legal_ast(client) on the SAME client to
    # build the Article/Annex -> Paragraph -> Point hierarchy — so the mock is
    # called at least twice (one ontology batch + >= 1 legal-AST batch).
    assert mock_client.execute_write_batch.call_count >= 2

    # The first batch is the ontology one — verify shape + significant length.
    first_batch = mock_client.execute_write_batch.call_args_list[0][0][0]
    assert isinstance(first_batch, list)
    assert len(first_batch) > 10

    # Combine every batch and confirm the Legal-AST hierarchy was ingested
    # through the same client (Paragraph nodes present, Annexes labelled
    # :Annex with the seeder-matching UPPERCASE id — never duplicate :Article).
    q_texts, q_params = [], []
    for call in mock_client.execute_write_batch.call_args_list:
        for q in call[0][0]:
            q_texts.append(q[0])
            q_params.append(q[1])
    assert any("MERGE (p:Paragraph {id: $id})" in qt for qt in q_texts)
    assert any("MERGE (a:Annex {id: $id})" in qt for qt in q_texts)
    assert any(str(qp.get("id", "")) == "annex_III" for qp in q_params)
    # No annex root mislabeled as :Article (the pre-fix bug).
    assert not any(
        "MERGE (a:Article {id: $id})" in qt
        and str(qp.get("id", "")).startswith("annex_")
        for qt, qp in zip(q_texts, q_params)
    )


def test_provision_root_labels_match_seeder():
    """Annex refs -> :Annex with UPPERCASE id; articles -> :Article."""
    assert _provision_root("Annex III") == ("Annex", "annex_III")
    assert _provision_root("Annex I") == ("Annex", "annex_I")
    assert _provision_root("Art. 6") == ("Article", "article_6")
    assert _provision_root("Art. 113") == ("Article", "article_113")

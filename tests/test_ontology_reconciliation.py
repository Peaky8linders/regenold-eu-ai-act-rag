from app.data.ontology_reconciliation import build_reconciliation_report


def test_current_legal_ontology_reconciles_cleanly() -> None:
    report = build_reconciliation_report()
    assert report.ok, report.as_dict()
    assert report.ontology_unknown_refs == ()
    assert report.role_unknown_refs == ()
    assert report.xref_unknown_endpoints == ()
    assert report.xref_self_edges == ()
    assert report.schema_edges_without_endpoints == ()


def test_report_is_json_shaped_for_ci_and_evolution_ledger() -> None:
    report = build_reconciliation_report().as_dict()
    assert report["ok"] is True
    assert report["checks"]["article_catalog_nonempty"] is True
    assert isinstance(report["ontology_unknown_refs"], tuple)

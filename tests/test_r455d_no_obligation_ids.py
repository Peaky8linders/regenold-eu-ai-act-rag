"""R455d — internal evidence / obligation identifiers never reach the answer.

System-prompt rule 3 told the model to "include the obligation ID for traceability"; on production
the rg_046 answer shipped "(obligation role-obligation-provider-high_risk_annex_iii-Art." mid-sentence.
"""
from __future__ import annotations

import pytest

from app.data.graph_rag_prompts import resolve_answer_system
from app.integrations.regenold.models import _strip_evidence_labels, normalise_answer_for_regenold


@pytest.mark.parametrize("raw,clean", [
    ("Article 13(3) requires six categories of information (obligation role-obligation-provider-high_risk_annex_iii-Art. "
     "The six categories follow.", "Article 13(3) requires six categories of information. The six categories follow."),
    ("Marking falls on the provider (obligation kb-transparency-Article 50.2), not the deployer.",
     "Marking falls on the provider, not the deployer."),
    ("See [kb-risk_mgmt-Art. 5] Art. 5 for the bans.", "See Art. 5 for the bans."),
])
def test_leaked_ids_are_removed(raw, clean):
    assert _strip_evidence_labels(raw) == clean


@pytest.mark.parametrize("text", [
    "The deployer has an obligation (obligation to inform workers) under Article 26(7).",
    "No labels here, Article 5(1)(f) applies.",
])
def test_ordinary_prose_is_untouched(text):
    assert _strip_evidence_labels(text) == text


def test_the_normaliser_strips_them_on_every_path():
    out = normalise_answer_for_regenold(
        "Marking falls on the provider (obligation kb-transparency-Article 50.2), not the deployer.", max_sentences=4)
    assert "kb-" not in out and "obligation kb" not in out


def test_rule_3_no_longer_asks_for_ids(monkeypatch):
    for k in ("REGENOLD_MINIMAL_COMPOSER", "REGENOLD_REF_MINIMALITY"):
        monkeypatch.delenv(k, raising=False)
    system = resolve_answer_system()
    assert "include the obligation ID for traceability" not in system
    assert "Never write internal obligation or evidence identifiers" in system

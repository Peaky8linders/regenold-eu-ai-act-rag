"""R455d follow-up: an evidence id is stripped by its grammar, so none reaches the answer.

``_strip_evidence_labels`` (R455d) deletes the internal ids the Stage-2 dossier
carries. Its bracket patterns stopped at the pid's own parentheses and could not see
an id listed after a citation, so recorded answers under docs/measurements shipped
"...must do 26-26(5))." and "(Article 14.1, kb-art-Article 14-14(1))". Every
non-control case below is one of those recorded shapes. Deletion stays the rule
(pinned in tests/test_r455d_no_obligation_ids.py); no id is rewritten into a citation.
"""

from __future__ import annotations

import re
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.integrations.regenold.models import (
    _strip_evidence_labels,
    normalise_answer_for_regenold,
)

_ID_OR_PID = re.compile(r"(?i)(?<![\w-])(?:kb|role-obligation)-|\b\d+-\d+\(\d+\)")

_RECORDED = [
    # the pid carries its own parentheses
    (
        "Article 26.5 sets out what the deployer must do (obligation kb-art-Article 26-26(5)). "
        "The trigger is a risk.",
        "Article 26.5 sets out what the deployer must do. The trigger is a risk.",
    ),
    (
        "Under Article 26.5 (obligation kb-art-Article 26-26(5)), a deployer must suspend use.",
        "Under Article 26.5, a deployer must suspend use.",
    ),
    (
        "Persons oversee them while in use (kb-art-Article 14-14(1)). The aim is prevention.",
        "Persons oversee them while in use. The aim is prevention.",
    ),
    # an id listed after a citation in the same bracket
    (
        "Oversight applies while in use (Article 14.1, kb-art-Article 14-14(1)). "
        "Under Article 14.4, staff must understand the system.",
        "Oversight applies while in use (Article 14.1). "
        "Under Article 14.4, staff must understand the system.",
    ),
    # two ids, the second cut mid-entity, then a new sentence
    (
        "Codes cover governance mechanisms (obligation kb-art-Article 95-95(1), "
        "kb-governance-Art. The aim is voluntary application.",
        "Codes cover governance mechanisms. The aim is voluntary application.",
    ),
    # a cut id after a citation: the citation stays and its bracket is closed
    (
        "The reclassification procedure (Article 80, kb-risk_mgmt-Art. Evaluation: Under "
        "Article 80.1, the authority evaluates it.",
        "The reclassification procedure (Article 80). Evaluation: Under Article 80.1, the "
        "authority evaluates it.",
    ),
    (
        "The provider's own duty (Article 20, kb-post_market-Art. Once aware, the provider must act.",
        "The provider's own duty (Article 20). Once aware, the provider must act.",
    ),
    # an Annex id, and a cut role id before a new sentence
    (
        "Annex VIII Section A sets out thirteen items (kb-governance-Annex VIII). "
        "The name of the provider comes first.",
        "Annex VIII Section A sets out thirteen items. The name of the provider comes first.",
    ),
    (
        "Instructions must be comprehensible to deployers (obligation role-obligation-provider-"
        "high_risk_annex_iii-Art. Article 13.3 lists the required contents.",
        "Instructions must be comprehensible to deployers. Article 13.3 lists the required contents.",
    ),
    # a bracketed id inside a bracket leaves no empty bracket behind
    (
        "The references ([kb-transparency-Article 50.2]) support this rule.",
        "The references support this rule.",
    ),
    ("The text ([kb-art-Article 14-14(1)]) covers oversight.", "The text covers oversight."),
]


@pytest.mark.parametrize("raw, clean", _RECORDED)
def test_recorded_shapes_leave_no_id_and_no_residue(raw, clean):
    assert _strip_evidence_labels(raw) == clean
    assert not _ID_OR_PID.search(clean)


@pytest.mark.parametrize("raw, clean", _RECORDED)
def test_strip_is_idempotent(raw, clean):
    assert _strip_evidence_labels(clean) == clean


@pytest.mark.parametrize(
    "text",
    [
        "Article 50.2 requires marking. Annex III point 1(a) identifies the relevant use "
        "case, and high-risk systems remain subject to Article 6.",
        # passes the early "kb-" gate but is not an id
        "The kb-style index (Article 10) governs data, and the role-obligation-mapping "
        "table is internal.",
    ],
)
def test_plain_citations_and_unrelated_text_are_unchanged(text):
    assert _strip_evidence_labels(text) == text


def test_normaliser_removes_the_id_and_keeps_the_legal_prose():
    raw = (
        "Under Article 26.5 (obligation kb-art-Article 26-26(5)), a deployer must suspend "
        "use of the system and inform the provider without undue delay."
    )
    assert normalise_answer_for_regenold(
        raw, question="What must a deployer do under Article 26(5)?"
    ) == (
        "Under Article 26.5, a deployer must suspend use of the system and inform the "
        "provider without undue delay."
    )


def test_a_landed_stage2_answer_ships_no_id_on_the_wire(monkeypatch):
    """The real route with a scripted LANDED Stage-2 answer carrying recorded shapes."""
    from app.config import settings
    from app.main import app
    from app.rate_limit import limiter
    from app.routes import regenold as R

    key = "r452-evidence-label-key"
    scripted = (
        "Under Article 26.5 (obligation kb-art-Article 26-26(5)), a deployer must suspend use "
        "of the system and inform the provider without undue delay (Article 26.5, "
        "kb-art-Article 26-26(5)). Instructions must be comprehensible to deployers "
        "(obligation role-obligation-provider-high_risk_annex_iii-Art. Article 13.3 lists "
        "the required contents."
    )
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
    monkeypatch.setattr(settings.regenold, "api_key", SecretStr(key))
    limiter.reset()
    R._ENGINE_CACHE.clear()
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True)
        )
        completion = stack.enter_context(
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                side_effect=lambda *a, **kw: scripted,
            )
        )
        with TestClient(app, headers={"X-Regenold-Api-Key": key}) as client:
            response = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json=[{
                    "role": "user",
                    "content": "What must a deployer of a high-risk AI system do if it "
                    "identifies a risk under Article 79(1)?",
                }],
            )
    assert response.status_code == 200, response.text
    answer = str(response.json().get("answer") or "")
    assert completion.call_count >= 1
    assert "must suspend use of the system" in answer, answer  # the scripted text shipped
    assert not _ID_OR_PID.search(answer), answer

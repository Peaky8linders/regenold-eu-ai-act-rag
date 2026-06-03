"""R105 — post-cap reference reconciliation (refs-faithfulness).

The R104.2 conciseness cap (#178) truncates the Stage-2-polished prose
*after* the R72 reconcile (and the Component D grounding guard) already
finalised the wire ``references`` against the UN-truncated prose. A
reference whose describing sentence the cap truncated away is then
"cited but never described" in the FINAL shipped answer — the
LLM-as-judge's refs-faithfulness penalty (r1042-conc-live: refs
0.53 → 0.37 after #178 added the cap).

R105 re-runs ``_reconcile_references_to_prose`` against the FINAL
``answer_text`` so every shipped reference is named in the answer
actually returned. These tests pin:

* the composed mechanism (cap-then-reconcile) on the real helpers, and
* the route-level ordering invariant end-to-end (the actual regression
  guard — it FAILS on the pre-R105 route).

The whole tail is ``stage2_landed``-gated, so the wrapper-less davidath
bench is byte-identical by construction.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.integrations.regenold.models import (
    _cap_readable_units,
    _hard_truncate_at_clause,
    normalise_answer_for_regenold,
)
from app.main import app
from app.routes.regenold import (
    _reconcile_references_to_prose,
    _reference_described_in_prose,
)


# ── Mechanism (deterministic, real helpers) ──────────────────────────────


def test_truncation_then_reconcile_drops_unnamed_ref() -> None:
    """The R105 mechanism: a ref described only in the truncated tail is
    kept by the pre-cap reconcile but dropped by the post-cap reconcile."""
    full = (
        "Providers must establish a risk management system under Article 9. "
        "Data governance duties arise under Article 10. "
        "Technical documentation is required under Article 11. "
        "Penalties for non-compliance are set out in Article 99."
    )
    refs = ["Article 9", "Article 10", "Article 11", "Article 99"]

    # Pre-cap (R72): every ref is named in the FULL prose → all kept.
    assert _reconcile_references_to_prose(refs, full) == refs

    # The conciseness cap truncates the trailing Article 99 (+11) sentences.
    capped = _cap_readable_units(_hard_truncate_at_clause(full, 150), max_units=4)
    capped = normalise_answer_for_regenold(capped, question="")
    assert "Article 99" not in capped

    # Post-cap (R105): the now-unnamed refs are dropped; floor keeps recall.
    out = _reconcile_references_to_prose(refs, capped, floor=2)
    assert "Article 9" in out
    assert "Article 99" not in out
    assert all(_reference_described_in_prose(r, capped) for r in out) or len(out) <= 2


# ── Route ordering invariant (the regression guard) ──────────────────────

_WALL = (
    "Providers of high-risk AI systems must establish a risk management "
    "system under Article 9. They must apply data governance practices under "
    "Article 10. Technical documentation must be drawn up under Article 11. "
    "Records must be kept under Article 12. Transparency information must be "
    "provided to deployers under Article 13. Human oversight must be ensured "
    "under Article 14. Accuracy and robustness must be maintained under "
    "Article 15. A quality management system is required under Article 16."
)
_Q = (
    "What are the obligations of providers of high-risk AI systems under "
    "Articles 9, 10, 11, 12, 13, 14, 15 and 16?"
)


def _stage2_env(monkeypatch) -> None:
    """Force a Stage-2-landed, hard-truncated answer through the route."""
    settings.regenold.api_key = SecretStr("regenold-test-key")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
    monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_DYNAMIC_GROUNDING", "1")  # drift-tolerant + floor=1
    monkeypatch.setenv("REGENOLD_QA_REF_BUDGET", "0")      # budget 5 (multi-ref)
    monkeypatch.setenv("REGENOLD_MAX_ANSWER_SENTENCES", "6")
    monkeypatch.setenv("REGENOLD_QA_LENGTH_CAP", "2000")
    monkeypatch.setenv("REGENOLD_STAGE2_CHAR_CAP", "160")  # force hard truncation
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")


def _post(question: str):
    with (
        patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=True,
        ),
        patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            return_value=_WALL,
        ),
    ):
        client = TestClient(app)
        return client.post(
            "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": question}],
        )


def test_post_cap_reconcile_keeps_every_ref_described(monkeypatch) -> None:
    """End-to-end: after the cap truncates the Stage-2 prose, no shipped
    reference is left cited-but-undescribed (beyond the recall floor).

    FAILS on the pre-R105 route, where the truncated-away Articles 11-14
    stay in the wire references."""
    monkeypatch.setenv("REGENOLD_REFS_RECONCILE", "1")
    _stage2_env(monkeypatch)
    body = _post(_Q).json()

    answer = body["answer"]
    refs = body["references"]

    # Confirm we exercised the gated path: Stage-2 landed (the synthesised
    # wall shipped, truncated), not a verbatim quote or deterministic prose.
    assert body.get("retrieval_path") not in {"verbatim_exact_text", "no_match"}
    assert "Article 9" in answer          # synthesised prose shipped
    assert "Article 13" not in answer     # ... and the cap truncated the tail
    assert refs                            # never emptied

    undescribed = [r for r in refs if not _reference_described_in_prose(r, answer)]
    # reconcile_floor == 1 under REGENOLD_DYNAMIC_GROUNDING=1 (recall insurance).
    assert len(undescribed) <= 1, (refs, answer, undescribed)


def test_off_switch_preserves_undescribed_refs(monkeypatch) -> None:
    """REGENOLD_REFS_RECONCILE=0 disables both reconcile passes — the
    pre-R105 behaviour, proving the gate is real (the cap leaves cited-but-
    undescribed refs on the wire)."""
    monkeypatch.setenv("REGENOLD_REFS_RECONCILE", "0")
    _stage2_env(monkeypatch)
    body = _post(_Q + " (off-switch variant)").json()

    answer = body["answer"]
    refs = body["references"]
    assert "Article 13" not in answer  # cap still truncates
    undescribed = [r for r in refs if not _reference_described_in_prose(r, answer)]
    assert len(undescribed) >= 2, (refs, answer, undescribed)

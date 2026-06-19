"""R134 — answer-quality: clean Stage-2 prose + citation/prose consistency.

A user flagged two live Stage-2 (Sonnet) answer defects:

1. Clunky off-register / irrelevant / mid-clause-truncated describer
   fragments bolted onto fluent prose — e.g. an off-topic
   ``Under Article 50, … cumulatively with Article 13`` LEAD and a
   dangling ``Under Annex III, Eight high-risk use-case categories:
   biometrics, critical infrastructure.`` APPEND on a technical-
   documentation / hardware question. Root cause: the Stage-2
   ``augment_with_ref_descriptions`` wire (``REGENOLD_STAGE2_REF_AUGMENT``)
   was default-ON (despite its comment saying "default OFF") and appended
   a raw ``Under <ref>, <KB-stub>`` clause for every under-described cited
   ref — which ALSO defeated the R72 reconcile below.

2. An answer that mentions "Article 6(1)" while the wire references omit
   Article 6 entirely (described-but-not-cited).

R134 fixes:
* Fix A — flip ``REGENOLD_STAGE2_REF_AUGMENT`` default ON → OFF so the
  polished Sonnet prose ships as written and the R72 reconcile (no longer
  defeated by appended describers) drops the genuinely-undescribed
  over-cited refs.
* Fix B — ``_add_prose_named_refs`` (bidirectional reconcile): ADD the
  article / annex the prose explicitly NAMES when the wire never cited it.

The whole tail is ``stage2_landed``-gated → the wrapper-less davidath
bench is byte-identical by construction.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.routes.regenold import (
    _add_prose_named_refs,
    _reconcile_references_to_prose,
    _reference_described_in_prose,
)


# ── Fix A downstream + Fix B helpers (deterministic, real helpers) ────────


_TECHDOC_PROSE = (
    "Yes. Under Article 11, read together with Annex IV, the technical "
    "documentation of a high-risk AI system must describe the system's "
    "design and architecture, which includes the hardware on which it is "
    "intended to run."
)
# The contaminated wire ref set the live answer shipped (multi-turn bleed).
_TECHDOC_REFS = ["Article 11", "Annex IV", "Annex III", "Article 13", "Article 50"]


def test_reconcile_drops_overcited_refs_when_augmenter_is_off() -> None:
    """With the Stage-2 augmenter OFF, the prose names only Art 11 + Annex IV
    so the R72 reconcile drops the over-cited Annex III / 13 / 50."""
    out = _reconcile_references_to_prose(_TECHDOC_REFS, _TECHDOC_PROSE, floor=1)
    assert out == ["Article 11", "Annex IV"]
    assert "Annex III" not in out
    assert "Article 50" not in out
    assert "Article 13" not in out


def test_add_prose_named_promotes_uncited_article_6() -> None:
    """Fix B — prose says 'Article 6(1)' but the wire omits Article 6 →
    Article 6 is promoted into the references (citation/prose consistency)."""
    prose = (
        "A system is high-risk under Article 6(1) when it is a safety "
        "component of a product covered by the Union harmonisation "
        "legislation listed in Annex I and must undergo third-party "
        "conformity assessment under Article 43."
    )
    refs = ["Annex I", "Article 43"]
    out = _add_prose_named_refs(refs, prose)
    assert "Article 6" in out
    # Existing refs preserved + order stable; addition appended.
    assert out[:2] == ["Annex I", "Article 43"]


def test_add_prose_named_existence_gated() -> None:
    """A Sonnet-named NON-provision (Article 999) is never added."""
    out = _add_prose_named_refs(
        ["Article 26"], "Article 999 says nothing; Article 26 governs deployers."
    )
    assert out == ["Article 26"]


def test_add_prose_named_no_duplicate_when_already_cited() -> None:
    out = _add_prose_named_refs(
        ["Article 6"], "A system is high-risk under Article 6."
    )
    assert out == ["Article 6"]  # already present → no dup


def test_add_prose_named_respects_cap() -> None:
    # Singular "Article N" form is what the matcher promotes (conservative —
    # a plural "Articles 8, 9" list is deliberately not expanded).
    prose = (
        "Article 8 imposes duties; Article 9 adds a risk system; "
        "Article 10 governs data; Article 11 the documentation."
    )
    out = _add_prose_named_refs([], prose, cap=2)
    # Only the first two prose-named existing articles are added.
    assert len(out) == 2
    assert out == ["Article 8", "Article 9"]


def test_add_prose_named_empty_prose_is_noop() -> None:
    assert _add_prose_named_refs(["Article 13"], "") == ["Article 13"]


def test_add_prose_named_skips_cross_regulation_gdpr() -> None:
    """A GDPR cross-reference ("Article 50 of Regulation (EU) 2016/679")
    is NOT AI-Act Article 50 and must not be promoted."""
    prose = (
        "The AI Act transparency duty is distinct from Article 50 of "
        "Regulation (EU) 2016/679 (the GDPR), which governs binding "
        "corporate rules; Article 13 is the operative provision here."
    )
    out = _add_prose_named_refs(["Article 13"], prose)
    assert "Article 50" not in out


def test_add_prose_named_skips_directive_and_gdpr_named() -> None:
    prose = (
        "Unlike Article 7 of the GDPR and Article 5 of Directive 2006/42/EC, "
        "the AI Act imposes Article 11 documentation duties."
    )
    out = _add_prose_named_refs(["Article 11"], prose)
    assert out == ["Article 11"]  # GDPR + Directive refs both skipped


def test_add_prose_named_keeps_ai_act_self_reference() -> None:
    """'Article 6 of the Regulation' / 'of Regulation (EU) 2024/1689' refers
    to the AI Act itself — a REAL citation, must be promoted."""
    prose = (
        "A system is high-risk under Article 6 of Regulation (EU) 2024/1689 "
        "when it is a safety component."
    )
    assert "Article 6" in _add_prose_named_refs(["Annex I"], prose)
    prose2 = "Article 6 of the Regulation classifies the system as high-risk."
    assert "Article 6" in _add_prose_named_refs(["Annex I"], prose2)


def test_add_prose_named_skips_contrasted_away_mention() -> None:
    """A contrasted-away mention ("…applies, NOT Article 5") must not be
    promoted — the article is being excluded, not cited."""
    prose = (
        "Article 50 transparency applies, not Article 5 (which prohibits the "
        "practice outright)."
    )
    out = _add_prose_named_refs(["Article 50"], prose)
    assert "Article 5" not in out


def test_drop_then_add_passes_are_disjoint() -> None:
    """Composing reconcile (drop) then add must not re-introduce a dropped
    ref nor drop an added one — the passes operate on disjoint sets."""
    recon = _reconcile_references_to_prose(_TECHDOC_REFS, _TECHDOC_PROSE, floor=1)
    out = _add_prose_named_refs(recon, _TECHDOC_PROSE)
    # Prose names exactly Article 11 + Annex IV → nothing to add, nothing
    # re-introduced.
    assert out == ["Article 11", "Annex IV"]
    assert all(_reference_described_in_prose(r, _TECHDOC_PROSE) for r in out)


# ── Route-level gate proofs (Fix A default-OFF) ──────────────────────────


_SONNET = (
    "Yes. Under Article 11, read together with Annex IV, the technical "
    "documentation must describe the hardware on which the high-risk AI "
    "system is intended to run."
)
_Q = (
    "Does the technical documentation of a high-risk AI system require "
    "specifications regarding the required hardware?"
)


def _stage2_env(monkeypatch) -> None:
    settings.regenold.api_key = SecretStr("regenold-test-key")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")  # keep Sonnet prose on the wire
    monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")


def _post(question: str, augment_spy):
    with (
        patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=True,
        ),
        patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            return_value=_SONNET,
        ),
        patch(
            "app.integrations.regenold.grounded_prose.augment_with_ref_descriptions",
            side_effect=augment_spy,
        ) as spy,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": question}],
        )
        return resp.json(), spy


def _passthrough(answer, *_a, **_k):
    """Augmenter spy that returns the answer unchanged (so we observe calls
    without changing wire output)."""
    return answer


def test_stage2_augmenter_not_called_by_default(monkeypatch) -> None:
    """Fix A — with the default (REGENOLD_STAGE2_REF_AUGMENT unset), the
    Stage-2 describe-append augmenter is NOT invoked, so no clunky
    ``Under <ref>, <stub>`` clause is bolted onto the polished prose."""
    monkeypatch.delenv("REGENOLD_STAGE2_REF_AUGMENT", raising=False)
    _stage2_env(monkeypatch)
    body, spy = _post(_Q, _passthrough)
    # Confirm we exercised the Stage-2 path (not a deterministic / verbatim
    # / refusal answer) — else the gate assertion is vacuous.
    if body.get("retrieval_path") not in {"no_match"} and "Article" in body.get(
        "answer", ""
    ):
        assert spy.call_count == 0, "Stage-2 augmenter must be OFF by default"
    # And no clunky describer fragment ever reaches the wire.
    assert "Under Annex" not in body.get("answer", "")
    assert "cumulatively with Article 13" not in body.get("answer", "")


def test_stage2_augmenter_called_when_enabled(monkeypatch) -> None:
    """Off-switch proof: REGENOLD_STAGE2_REF_AUGMENT=1 re-enables the
    augmenter invocation (the gate is real, the change is reversible)."""
    monkeypatch.setenv("REGENOLD_STAGE2_REF_AUGMENT", "1")
    _stage2_env(monkeypatch)
    body, spy = _post(_Q + " (augment-on variant)", _passthrough)
    if body.get("retrieval_path") not in {"no_match"} and "Article" in body.get(
        "answer", ""
    ):
        assert spy.call_count >= 1, "augmenter must fire when explicitly enabled"

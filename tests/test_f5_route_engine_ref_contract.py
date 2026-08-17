"""R363 / F5 — cross-side reference contract: route wire refs stay within the
engine's grounding universe.

The route re-implements a large reference pipeline on top of the engine's
output (validate -> rank -> collapse -> cap -> recover). Its documented
reference sources are:

  1. the engine's citations (``rag_res.citations[].article_ref`` — the seed),
  2. the engine's answer prose / the live question (prose-named refs, the
     recovery passes),
  3. the ontology 1-hop expansion of the engine's candidates (R104
     ``_apply_ontology_hops`` — structural targets like Section-2
     requirements), and
  4. curated intercepts (hand-picked authoritative ref sets).

The contract pinned here: every wire reference's HEAD (base provision, e.g.
"Article 13" for "Article 13.2.a") must be present in the union of those
sources for the same question — the engine citation heads, the heads named in
the engine's answer prose / the question (tolerance-aware via the route's own
``_reference_described_in_prose``), or the ontology 1-hop closure of the
engine heads. A route change that starts emitting a provision grounded in none
of those sources fails here.

Note: the prose source is the ENGINE's answer, not the route's final wire
answer — the route's own normalization legitimately trims article mentions
from the final prose after the prose-named refs were added (measured: the
Article 16 obligations answer names "Arts. 11 and 18" in engine prose while
the wire answer drops the mention).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app


def _client() -> TestClient:
    return TestClient(app)


def _messages(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


# Wire-form refs are "Article 13.2.a" / "Article 13" / "Annex IV.2". The head
# is the base provision: article number (context-guarded so "Article 13" does
# not match "Article 130") or the Annex roman numeral.
_HEAD_RE = re.compile(r"^(?:Article|Art\.?)\s+(\d+)\b", re.IGNORECASE)
_ANNEX_HEAD_RE = re.compile(r"^Annex\s+([IVXLCDM]+)\b", re.IGNORECASE)


def _head(ref: str) -> str:
    m = _HEAD_RE.match(ref.strip())
    if m:
        return f"Article {m.group(1)}"
    m = _ANNEX_HEAD_RE.match(ref.strip())
    if m:
        return f"Annex {m.group(1)}"
    return ref.strip()


def _engine_grounding(question: str) -> tuple[set[str], str]:
    """(citation heads, raw answer prose) from a direct engine call."""
    from app.engines._graph_rag_impl import ask_compliance_question
    from app.models import GraphRAGRequest

    eng = ask_compliance_question(GraphRAGRequest(question=question))
    heads = {
        _head(c.article_ref or "")
        for c in (eng.citations or [])
        if (c.article_ref or "").strip()
    }
    return heads, eng.answer or ""


def _ontology_closure(heads: set[str], question: str) -> set[str]:
    """The R104 ontology 1-hop closure of the engine heads, computed with the
    same inputs the route uses (same cached intent label, same question)."""
    from app.routes.regenold import _apply_ontology_hops

    out: set[str] = set()
    try:
        from app.routes.regenold import _classify_intent_cached

        _intent_res = _classify_intent_cached(question)
        _label = _intent_res.intent if _intent_res else None
    except Exception:  # noqa: BLE001 — degrade to no label; the hop gate is
        # additive either way and the engine heads still anchor the contract.
        _label = None
    try:
        hops = _apply_ontology_hops(sorted(heads), _label, question)
        out = {_head(h) for h in hops}
    except Exception:  # noqa: BLE001 — a hop failure must not break the test
        out = set()
    return out


GROUNDED_QUESTIONS = [
    "What does Article 13 require for transparency?",
    "What obligations does a provider of a high-risk AI system have under "
    "Article 16?",
    "For how long must providers retain automatically generated logs?",
]


@pytest.mark.parametrize("question", GROUNDED_QUESTIONS)
def test_route_wire_refs_stay_within_engine_universe_or_prose(question: str) -> None:
    from app.integrations.regenold.models import reference_from_article_ref
    from app.routes.regenold import _reference_described_in_prose

    settings.regenold.api_key = SecretStr("regenold-test-key")
    r = _client().post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(question),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    wire = data.get("references") or []
    assert wire, (question, data)  # must be a grounded question

    engine_heads, engine_answer = _engine_grounding(question)
    assert engine_heads, question  # the engine itself must ground the question
    allowed_heads = engine_heads | _ontology_closure(engine_heads, question)
    prose_source = f"{question} {engine_answer}"

    for ref in wire:
        # Format + corpus existence (the P0 validator).
        assert reference_from_article_ref(ref) is not None, (question, ref)
        # The F5 cross-side contract: never invented — the engine surfaced
        # the head, its ontology closure added it, or the engine's own
        # answer prose / the question names it (the additive passes'
        # documented sources).
        assert (
            _head(ref) in allowed_heads
            or _reference_described_in_prose(ref, prose_source)
        ), (question, ref, sorted(allowed_heads), engine_answer[:400])


def test_route_wire_refs_never_contain_fabricated_provisions() -> None:
    """The grounding allowance must be tight: a ref whose head is in none of
    the engine sources is a fabrication and must never appear on the wire."""
    from app.routes.regenold import _reference_described_in_prose

    settings.regenold.api_key = SecretStr("regenold-test-key")
    question = GROUNDED_QUESTIONS[0]
    r = _client().post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(question),
    )
    assert r.status_code == 200
    data = r.json()
    wire = data.get("references") or []
    engine_heads, engine_answer = _engine_grounding(question)
    allowed_heads = engine_heads | _ontology_closure(engine_heads, question)

    # Nonexistent provisions must not even pass the format validator, and a
    # hypothetical head in none of the engine sources must not be emitted.
    assert "Article 999" not in wire
    assert "Article 999.1" not in wire
    for ref in wire:
        if _head(ref) in allowed_heads:
            continue
        assert _reference_described_in_prose(
            ref, f"{question} {engine_answer}"
        ), (ref, engine_answer[:400])


def test_prose_matcher_accepts_plural_arts() -> None:
    """R363 — the plural fix: the engine's answer template emits \"Arts. 11
    and 18\"; the route's matcher must recognise it as describing Article 11
    (the old regex only matched \"Article N\" / \"Art. N\")."""
    from app.routes.regenold import _reference_described_in_prose

    prose = "keep the technical documentation (Arts. 11 and 18)"
    assert _reference_described_in_prose("Article 11", prose) is True
    assert _reference_described_in_prose("Article 18", prose) is True
    assert _reference_described_in_prose("Article 12", prose) is False
    # Singular forms still work, and the number-boundary guard holds.
    assert _reference_described_in_prose("Article 11", "Art. 11 applies") is True
    assert _reference_described_in_prose("Article 11", "Article 110 does not") is False

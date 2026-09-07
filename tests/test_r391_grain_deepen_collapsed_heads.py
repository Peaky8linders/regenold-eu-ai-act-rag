"""R391 — the D1 granularity pass and the grain deepener were fighting.

``_apply_ref_granularity`` (auto) collapses a head's leaves onto the head and
records the head in ``_collapsed_to_heads``; ``_deepen_ref_grain`` was then told
to SKIP exactly those heads. One pass discarded the sub-point coordinate and the
other was forbidden from restoring it — on the axis (Ref. Correctness Strict)
where we sit furthest behind the frontier baseline.

Every assertion here is on the WIRE or on a measured invariant, never on the
shape of the code (the R360 rule: three R329 rerank placements all read
correctly in the diff and all made zero calls).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.routes import regenold as R

_CAPTURE = (
    Path(__file__).resolve().parents[1]
    / "evals" / "bench" / "results" / "official-r391-ab-A-easy.ckpt.jsonl"
)
_INSTRUCTIONS_FOR_USE = (
    "Under the EU AI Act, what must a provider of a high-risk AI system supply "
    "to the deployer in the instructions for use? List the required categories "
    "of information."
)


def _head(ref: str) -> str:
    return str(ref).split(".")[0].strip()


# -- the flag ----------------------------------------------------------------


def test_default_is_on(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS", raising=False)
    assert R._deepen_collapsed_heads_enabled()


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF"])
def test_the_off_switch_works(monkeypatch, value):
    monkeypatch.setenv("REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS", value)
    assert not R._deepen_collapsed_heads_enabled()


def test_flag_changes_cache_identity(monkeypatch):
    """R263.2 — otherwise a same-process A/B serves arm A's cache to arm B."""
    monkeypatch.setenv("REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS", "0")
    off = R._engine_cache_key(_INSTRUCTIONS_FOR_USE, None)
    monkeypatch.setenv("REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS", "1")
    assert R._engine_cache_key(_INSTRUCTIONS_FOR_USE, None) != off


# -- the wire, two-sided -----------------------------------------------------


def _ask(client, question: str) -> list[str]:
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
        json={"messages": [{"role": "user", "content": question}]},
        headers={"User-Agent": "pytest"},
    )
    assert resp.status_code == 200, resp.status_code
    return list(resp.json().get("references") or [])


@pytest.fixture()
def _offline(monkeypatch):
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")


def test_the_collapsed_head_reaches_the_wire_deepened(_offline, monkeypatch):
    """Two-sided: the exemption really does suppress the deepener when OFF.

    A guard whose OFF state behaves like its ON state is the inert-feature trap
    (R360). ``Article 13`` is the head the granularity pass collapses to on this
    question, and ``Article 13.3`` is the official answer key.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS", "0")
    kept = _ask(TestClient(app), _INSTRUCTIONS_FOR_USE)
    monkeypatch.setenv("REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS", "1")
    lifted = _ask(TestClient(app), _INSTRUCTIONS_FOR_USE)

    assert "Article 13" in kept, kept
    assert "Article 13" not in lifted, lifted
    assert "Article 13.3" in lifted, lifted
    # the non-exempt heads were already being deepened in BOTH arms, so the
    # only difference must be the collapsed head
    assert [r for r in kept if _head(r) != "Article 13"] == [
        r for r in lifted if _head(r) != "Article 13"
    ]


# -- the invariant that makes hard rule #8 structural ------------------------


def test_deepening_never_changes_the_head_set():
    """``gold_dropped_head`` folds both sides onto heads, and deepening maps a
    head to its OWN leaf — so the gate delta is ``+0`` BY CONSTRUCTION.

    Pinned over a real live capture rather than a synthetic list, because that
    is the input distribution the claim is about.
    """
    if not _CAPTURE.exists():
        pytest.skip("live capture not present in this checkout")
    rows = [json.loads(x) for x in _CAPTURE.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert rows, "capture is empty"
    os.environ.pop("REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS", None)
    for row in rows:
        before = [str(x) for x in (row.get("pred_refs") or [])]
        after = R._deepen_ref_grain(before, row["question"], row["pred_answer"])
        assert {_head(r) for r in before} == {_head(r) for r in after}, row["id"]
        assert len(after) == len(before), row["id"]


def test_deepening_is_one_reference_for_one_reference():
    """Ref. Conciseness is a pure COUNT ratio, so a length-preserving transform
    cannot move it. This is why lifting the exemption is free on that axis.
    """
    refs = ["Article 13", "Article 26"]
    out = R._deepen_ref_grain(refs, _INSTRUCTIONS_FOR_USE, "The provider shall supply them.")
    assert len(out) == len(refs)


def test_a_head_whose_own_leaf_is_present_is_still_left_alone():
    """Guard G1 is unaffected: that cluster belongs to parent collapse (R381),
    which removes the redundant head for free.
    """
    refs = ["Article 13", "Article 13.3"]
    out = R._deepen_ref_grain(refs, _INSTRUCTIONS_FOR_USE, "The provider shall supply them.")
    assert "Article 13.3" in out
    assert len(out) == 2

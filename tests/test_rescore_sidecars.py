# tests/test_rescore_sidecars.py
"""R82-A — rescore historical sidecars in place (write siblings)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.rescore_sidecars import (
    iter_sidecars,
    rescore_row,
    rescore_sidecar,
)


@pytest.fixture
def fake_sidecar(tmp_path: Path) -> Path:
    """A minimal sidecar with one QA row and one rep-100-style row."""
    p = tmp_path / "results" / "fake.json"
    p.parent.mkdir(parents=True)
    payload = {
        "label": "fake",
        "rows": [
            {
                "id": "fake_qa_1",
                "kind": "qa",
                "gold_answer": "high‑risk providers must document",
                "gold_articles": [9],
                "predicted_answer": "high-risk providers must document",
                "pred_refs": ["Article 9"],
                "latency_ms": 100.0,
                # No expected_keywords field — davidath-style row.
            },
            {
                "id": "fake_rep_1",
                "kind": "multiturn",
                "gold_answer": "providers must conduct risk assessment",
                "gold_articles": [9, 27],
                "predicted_answer": "the provider must perform a risk assessment",
                "pred_refs": ["Article 9", "Article 27"],
                "expected_keywords": ["risk", "assessment"],
                "latency_ms": 200.0,
            },
        ],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_iter_sidecars_finds_label_rows(fake_sidecar: Path) -> None:
    found = list(iter_sidecars(fake_sidecar.parent))
    assert len(found) == 1
    assert found[0].name == "fake.json"


def test_rescore_row_qa_row_emits_legacy_and_corrected(fake_sidecar: Path) -> None:
    payload = json.loads(fake_sidecar.read_text(encoding="utf-8"))
    row = payload["rows"][0]
    out = rescore_row(row)
    # New axes
    assert "ans_correctness_loose" in out
    assert "ans_correctness_strict" in out
    # Legacy axes
    assert "ans_correctness_loose_legacy" in out
    assert "ans_correctness_strict_legacy" in out
    # NBH-vs-ASCII pair: corrected Loose strictly higher than legacy
    assert out["ans_correctness_loose"] > out["ans_correctness_loose_legacy"]
    # No keyword recall for davidath-style row
    assert out["ans_keyword_recall"] is None


def test_rescore_row_rep100_emits_keyword_recall(fake_sidecar: Path) -> None:
    payload = json.loads(fake_sidecar.read_text(encoding="utf-8"))
    row = payload["rows"][1]
    out = rescore_row(row)
    # Curated keyword list present → recall computed
    assert isinstance(out["ans_keyword_recall"], float)
    assert out["ans_keyword_recall"] > 0


def test_rescore_sidecar_writes_sibling_file(fake_sidecar: Path) -> None:
    sibling = rescore_sidecar(fake_sidecar)
    assert sibling.name == "fake.rescored.json"
    assert sibling.exists()
    # Original untouched
    payload = json.loads(fake_sidecar.read_text(encoding="utf-8"))
    assert "rescored_aggregate" not in payload


def test_rescore_sidecar_aggregate_present(fake_sidecar: Path) -> None:
    sibling = rescore_sidecar(fake_sidecar)
    rescored = json.loads(sibling.read_text(encoding="utf-8"))
    assert "rescored_aggregate" in rescored
    assert "ans_correctness_loose" in rescored["rescored_aggregate"]
    assert "ans_correctness_loose_legacy" in rescored["rescored_aggregate"]

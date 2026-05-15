"""SHA-pinned loader for the davidath/ai-act-evaluation-benchmark dataset.

Source: https://github.com/davidath/ai-act-evaluation-benchmark
Paper:  arXiv:2603.09435 (Davvetas et al., 2026)
Licence: CC-BY-4.0 (data) / Apache 2.0 (code)

We cache the dataset under ``evals/bench/data/`` and pin the SHA-256 of
both JSON files so a re-fetch can verify byte-identity. If the file is
missing OR the cached SHA mismatches, we re-download from the upstream
``main`` branch.

Schema (post-load):
    QA: list[dict] of {question, answer, relevant_article}
    Scenario: list[dict] of {role, intended_use, system_type, input_data,
                             domain, related_articles, obligations, risk_level}
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"
QA_PATH = DATA_DIR / "qa_pairs.json"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"

# Pinned upstream SHAs — verified after first fetch on 2026-05-15.
# A mismatch on subsequent runs means upstream changed; re-pin
# deliberately rather than silently absorbing edits.
QA_SHA256 = "a2fffe370fff9fba05e85b46d05473b707e30f055aa45b9d2c26c80488aed8b9"
SCENARIOS_SHA256 = (
    "0fc1c7491372cf0aa787b4b650f77245ec775f8bff0c4c84f253435c7dcb1b25"
)

_RAW_BASE = (
    "https://raw.githubusercontent.com/davidath/ai-act-evaluation-benchmark/main"
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": "regenold-eu-ai-act-rag/bench"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())


def ensure_dataset(*, verify: bool = True) -> None:
    """Download the benchmark JSON files if missing or SHA-mismatched.

    Idempotent — a clean checkout calls this once before running, a
    cached checkout returns immediately.
    """
    targets = [
        (QA_PATH, f"{_RAW_BASE}/qa_pairs.json", QA_SHA256),
        (SCENARIOS_PATH, f"{_RAW_BASE}/scenarios.json", SCENARIOS_SHA256),
    ]
    for path, url, expected_sha in targets:
        needs_fetch = not path.exists() or (
            verify and _sha256_file(path) != expected_sha
        )
        if needs_fetch:
            _fetch(url, path)
        if verify:
            actual = _sha256_file(path)
            if actual != expected_sha:
                raise RuntimeError(
                    f"SHA mismatch for {path.name}: expected {expected_sha}, "
                    f"got {actual}. Upstream changed — re-pin deliberately."
                )


def load_qa_pairs() -> list[dict[str, Any]]:
    """Return the 137 QA pairs from qa_pairs.json.

    Schema: ``{question: str, answer: str, relevant_article: int}``.
    """
    ensure_dataset()
    payload = json.loads(QA_PATH.read_text(encoding="utf-8"))
    return list(payload.get("data") or [])


def load_scenarios() -> list[dict[str, Any]]:
    """Return the 339 scenarios from scenarios.json.

    Schema: ``{role, intended_use, system_type, input_data, domain,
               related_articles: list[int], obligations: list[str],
               risk_level: "prohibited"|"high-risk"|"limited"|"minimal"}``.
    """
    ensure_dataset()
    payload = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    return list(payload.get("data") or [])


def dataset_fingerprint() -> dict[str, str]:
    """Return the cached SHAs — included in result rows for provenance."""
    return {
        "qa_pairs_sha256": _sha256_file(QA_PATH) if QA_PATH.exists() else "",
        "scenarios_sha256": (
            _sha256_file(SCENARIOS_PATH) if SCENARIOS_PATH.exists() else ""
        ),
        "qa_pairs_expected": QA_SHA256,
        "scenarios_expected": SCENARIOS_SHA256,
    }

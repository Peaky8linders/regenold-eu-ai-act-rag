"""Deterministic hold-out split of the davidath benchmark.

The Round-23..R37 tuning runs against ``evals.bench.runner`` which uses
EVERY QA pair and scenario from the pinned davidath dataset. After 14
rounds of feedback those scores are IN-SAMPLE — each new optimisation
can be tuned against the bench it's measured by, so the score over-
states real-world generalisation.

This module carves a held-out 20% slice out of the same pinned dataset
so we can measure generalisation against a slice the optimisation
loop has never seen. The split is:

    * Hash-bucketed by ``SHA-256(projection_text) mod 5``
    * Bucket 0 (~20%) → held-out
    * Buckets 1-4 (~80%) → train (the slice the bench tunes against)
    * Deterministic — no randomness, no seed knob, no time component
    * Source-independent — QA splits independently from scenarios
    * Re-derivable from the JSON sidecars alone

The projection text for the hash bucket is:
    * QA pair → ``question``
    * Scenario → role + intended_use + system_type + domain joined with ``|``

Both are the canonical fingerprints of an item — they don't change with
re-ordering of the JSON file and they uniquely identify each row.

Public API:
    * ``load_holdout_qa()``    → list[dict]  (~20% of qa_pairs.json)
    * ``load_train_qa()``      → list[dict]  (~80%)
    * ``load_holdout_scenarios()`` → list[dict] (~20% of scenarios.json)
    * ``load_train_scenarios()``   → list[dict] (~80%)
    * ``summary()``                → dict — counts of each split
"""
from __future__ import annotations

import hashlib
from typing import Any

from evals.bench import dataset as bench_dataset


HOLDOUT_BUCKET = 0
NUM_BUCKETS = 5


def _hash_bucket(text: str) -> int:
    """Return ``int(sha256(text).hexdigest(), 16) % NUM_BUCKETS``.

    Deterministic on the input ``text``. No salting — we *want* the
    bucket assignment to be reproducible from the JSON sidecar alone
    so any future re-run of the harness lands on the same slice.
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest, 16) % NUM_BUCKETS


def _scenario_question_text(item: dict[str, Any]) -> str:
    """Canonical fingerprint for a scenario row.

    We don't use the SYNTHESISED question from ``runner._scenario_to_question``
    because that string concatenation could shift over time. The four
    structured fields (role, intended_use, system_type, domain) uniquely
    identify each scenario in the pinned dataset.
    """
    parts = [
        (item.get("role") or "").strip().lower(),
        (item.get("intended_use") or "").strip().lower(),
        (item.get("system_type") or "").strip().lower(),
        (item.get("domain") or "").strip().lower(),
    ]
    return "|".join(parts)


def _qa_key(item: dict[str, Any]) -> str:
    return (item.get("question") or "").strip()


def load_holdout_qa() -> list[dict[str, Any]]:
    """Return the ~20% hold-out slice of qa_pairs.json."""
    return [
        item
        for item in bench_dataset.load_qa_pairs()
        if _hash_bucket(_qa_key(item)) == HOLDOUT_BUCKET
    ]


def load_train_qa() -> list[dict[str, Any]]:
    """Return the ~80% train slice — the rest of qa_pairs.json."""
    return [
        item
        for item in bench_dataset.load_qa_pairs()
        if _hash_bucket(_qa_key(item)) != HOLDOUT_BUCKET
    ]


def load_holdout_scenarios() -> list[dict[str, Any]]:
    """Return the ~20% hold-out slice of scenarios.json."""
    return [
        item
        for item in bench_dataset.load_scenarios()
        if _hash_bucket(_scenario_question_text(item)) == HOLDOUT_BUCKET
    ]


def load_train_scenarios() -> list[dict[str, Any]]:
    """Return the ~80% train slice — the rest of scenarios.json."""
    return [
        item
        for item in bench_dataset.load_scenarios()
        if _hash_bucket(_scenario_question_text(item)) != HOLDOUT_BUCKET
    ]


def summary() -> dict[str, dict[str, int]]:
    """Return per-source split counts for diagnostics + provenance.

    Shape::
        {
          "qa":        {"total": N, "holdout": k, "train": N-k},
          "scenarios": {"total": M, "holdout": j, "train": M-j},
        }
    """
    all_qa = bench_dataset.load_qa_pairs()
    all_sc = bench_dataset.load_scenarios()
    hold_qa = sum(1 for q in all_qa if _hash_bucket(_qa_key(q)) == HOLDOUT_BUCKET)
    hold_sc = sum(
        1
        for s in all_sc
        if _hash_bucket(_scenario_question_text(s)) == HOLDOUT_BUCKET
    )
    return {
        "qa": {
            "total": len(all_qa),
            "holdout": hold_qa,
            "train": len(all_qa) - hold_qa,
        },
        "scenarios": {
            "total": len(all_sc),
            "holdout": hold_sc,
            "train": len(all_sc) - hold_sc,
        },
    }

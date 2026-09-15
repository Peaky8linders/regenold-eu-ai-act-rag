"""R418 — the serving leg must be readable from the WIRE, not only from graph_stats.

R417 recorded ``stage2_served_by`` in ``graph_stats`` and made the route refuse to
cache a degraded serve. Both are correct, and neither was *observable* on a
deployed run: the response body carries only ``answer`` / ``references`` /
``reasoning``, so ``graph_stats`` never reaches an eval. A live audit could only
infer the leg from the ``stage2_model=`` prefix — and that inference is what
turned one Bedrock fallback on rg_010 into what looked like three independent
observations of a wrapper-served answer.

These tests pin the two halves of the fix: the route names the leg in the trace,
and the harness reads it.
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.regenold.run_official_batch import _provenance

REPO = Path(__file__).resolve().parents[1]


def _body(notes: list[str], **extra) -> dict:
    return {"reasoning": json.dumps({"notes": notes, **extra})}


def test_provenance_reads_the_named_leg() -> None:
    prov = _provenance(_body(["stage2_model=claude-opus-5", "stage2_served_by=primary"]))
    assert prov["stage2_served_by"] == "primary"
    assert prov["stage2_model"] == "claude-opus-5"


def test_provenance_names_a_fallback_even_though_the_model_is_also_recorded() -> None:
    """The leg is the route's own answer; the model is not a substitute for it."""
    prov = _provenance(_body(["stage2_model=qwen.qwen3-32b-v1:0", "stage2_served_by=fallback"]))
    assert prov["stage2_served_by"] == "fallback"


def test_provenance_reads_the_leg_when_the_note_precedes_the_model_note() -> None:
    """Note order must not decide whether the leg is found."""
    prov = _provenance(_body(["stage2_served_by=deterministic", "stage2_model=claude-opus-5"]))
    assert prov["stage2_served_by"] == "deterministic"
    assert prov["stage2_model"] == "claude-opus-5"


def test_provenance_defaults_the_leg_to_empty_and_stays_fail_soft() -> None:
    """An older trace (no leg note) must not invent one, and a bad body must not raise."""
    assert _provenance(_body(["stage2_model=claude-opus-5"]))["stage2_served_by"] == ""
    assert _provenance({"reasoning": "not json"}) == {}
    assert _provenance(None) == {}
    assert _provenance(_body([None, 7, "stage2_served_by=primary"]))["stage2_served_by"] == "primary"


def test_route_records_the_leg_for_both_cache_paths() -> None:
    """Wired-in check: the note is emitted once, from the resolved response.

    Placed after the cache lookup, so a cache HIT names the leg of the answer it
    replays rather than going silent — the exact blindness the R417 cache-skip
    note was added to cure.
    """
    src = (REPO / "app/routes/regenold.py").read_text(encoding="utf-8")
    assert 'f"stage2_served_by={_served_leg}"' in src
    emit = src.index('f"stage2_served_by={_served_leg}"')
    lookup = src.index("rag_res = _ENGINE_CACHE.get(cache_key)")
    assert lookup < emit, "the leg note must read the RESOLVED response, not the pre-lookup one"

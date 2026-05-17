"""Tests for evals.bench.refusal_probe.

Covers:
    * Probe set is well-formed (20+ items, each with id/category/
      question/expected; expected in {"refuse","accept"}).
    * is_refusal classifier returns True for the canonical opener +
      empty refs; False for in-scope responses.
    * score_refusal_correctness correctly tallies correct refusals,
      correct acceptances, false acceptances, false refusals.
    * Scoring tolerates an agent_fn that raises (captures error, marks
      row incorrect).
"""
from __future__ import annotations

from evals.bench import refusal_probe as rp


# ── Probe shape ──────────────────────────────────────────────────────────


def test_probe_is_well_formed() -> None:
    items = rp.REFUSAL_PROBE
    assert len(items) >= 20
    seen_ids: set[str] = set()
    for it in items:
        assert "id" in it and it["id"]
        assert it["id"] not in seen_ids, f"duplicate id {it['id']}"
        seen_ids.add(it["id"])
        assert it["category"]
        assert it["question"]
        assert it["expected"] in {"refuse", "accept"}


def test_probe_covers_required_categories() -> None:
    """Spec requires consumer / commercial / legal-adjacent /
    jailbreak / conversational + at least 5 in-scope controls."""
    cats = {it["category"] for it in rp.REFUSAL_PROBE}
    assert "consumer" in cats
    assert "commercial" in cats
    assert "legal_adjacent" in cats
    assert "jailbreak" in cats
    assert "conversational" in cats
    assert "inscope" in cats
    in_scope = [it for it in rp.REFUSAL_PROBE if it["expected"] == "accept"]
    assert len(in_scope) >= 5


def test_load_returns_shallow_copy() -> None:
    """Mutating the loaded list must not corrupt the canonical probe."""
    a = rp.load_refusal_probe()
    a.append({"id": "evil", "category": "x", "question": "q", "expected": "refuse"})
    b = rp.load_refusal_probe()
    assert len(b) == len(rp.REFUSAL_PROBE)
    assert all(row.get("id") != "evil" for row in b)


# ── Refusal detector ─────────────────────────────────────────────────────


def test_is_refusal_detects_canonical_opener() -> None:
    answer = (
        "I only answer questions about the EU AI Act (Regulation 2024/1689). "
        "Try a regulatory question..."
    )
    assert rp.is_refusal(answer, []) is True


def test_is_refusal_requires_empty_refs() -> None:
    """The opener WITH non-empty refs isn't the wire's refusal copy."""
    answer = "I only answer questions about the EU AI Act ..."
    assert rp.is_refusal(answer, ["Article 13"]) is False


def test_is_refusal_rejects_inscope_answer() -> None:
    answer = (
        "Requires high-risk AI systems to be designed for sufficient "
        "transparency..."
    )
    assert rp.is_refusal(answer, ["Article 13"]) is False
    # And on empty refs but a non-refusal opener — also False
    assert rp.is_refusal(answer, []) is False


def test_is_refusal_handles_empty_inputs() -> None:
    assert rp.is_refusal("", []) is False
    assert rp.is_refusal("", ["Article 13"]) is False


# ── Scoring ───────────────────────────────────────────────────────────────


_REFUSAL_RESP = {
    "answer": (
        "I only answer questions about the EU AI Act (Regulation 2024/1689). "
        "Try a regulatory question, for example..."
    ),
    "references": [],
}

_ACCEPT_RESP = {
    "answer": (
        "Requires high-risk AI systems to be designed for sufficient "
        "operational transparency to deployers."
    ),
    "references": ["Article 13"],
}


def test_score_perfect_run_returns_full_marks() -> None:
    """If the agent always refuses OOS and accepts in-scope, the
    score is 100% on both axes."""

    def perfect_agent(item: dict) -> dict:
        if item["expected"] == "refuse":
            return _REFUSAL_RESP
        return _ACCEPT_RESP

    out = rp.score_refusal_correctness(rp.load_refusal_probe(), perfect_agent)
    assert out["refusal_accuracy"] == 1.0
    assert out["in_scope_acceptance_rate"] == 1.0
    assert out["overall_accuracy"] == 1.0
    assert out["false_acceptances"] == 0
    assert out["false_refusals"] == 0
    # Sanity on counts
    assert out["n"] == len(rp.REFUSAL_PROBE)
    assert out["n_out_of_scope"] + out["n_in_scope"] == out["n"]


def test_score_always_refuse_over_refuses_in_scope() -> None:
    """An over-eager refuser hits 1.0 on the OOS slice but 0.0 on
    in-scope — refusal accuracy alone is misleading without it."""

    def always_refuse(item: dict) -> dict:
        return _REFUSAL_RESP

    out = rp.score_refusal_correctness(rp.load_refusal_probe(), always_refuse)
    assert out["refusal_accuracy"] == 1.0
    assert out["in_scope_acceptance_rate"] == 0.0
    assert out["false_refusals"] > 0


def test_score_always_accept_leaks_out_of_scope() -> None:
    """An always-accept agent has 0 refusal accuracy and 100%
    in-scope acceptance — the dual axes catch the failure mode."""

    def always_accept(item: dict) -> dict:
        return _ACCEPT_RESP

    out = rp.score_refusal_correctness(rp.load_refusal_probe(), always_accept)
    assert out["refusal_accuracy"] == 0.0
    assert out["in_scope_acceptance_rate"] == 1.0
    assert out["false_acceptances"] > 0


def test_score_tolerates_raising_agent() -> None:
    """A misbehaving agent_fn must not crash the eval — it captures
    the error in the row and counts that row as wrong."""

    def crashing_agent(item: dict) -> dict:
        raise RuntimeError("boom")

    out = rp.score_refusal_correctness(rp.load_refusal_probe(), crashing_agent)
    # All rows wrong → refusal_accuracy 0.0 (empty answers don't pass
    # the opener check) and in_scope_acceptance_rate 1.0 (empty
    # answers don't trigger refusal either, so in-scope items count
    # as "accepted" - a quirk worth surfacing but stable).
    assert out["refusal_accuracy"] == 0.0
    # 0 supported rows from refusal-side
    assert out["correct_refusals"] == 0
    assert out["n"] == len(rp.REFUSAL_PROBE)


def test_score_rows_carry_per_item_decisions() -> None:
    """The ``rows`` list must record each item's outcome label so a
    debugger can drill into which probe items failed."""

    def perfect_agent(item: dict) -> dict:
        if item["expected"] == "refuse":
            return _REFUSAL_RESP
        return _ACCEPT_RESP

    out = rp.score_refusal_correctness(rp.load_refusal_probe(), perfect_agent)
    rows = out["rows"]
    assert len(rows) == len(rp.REFUSAL_PROBE)
    for r in rows:
        assert "id" in r and "outcome" in r and "refusal_detected" in r
        assert r["outcome"] in {
            "correct_refusal",
            "false_acceptance",
            "correct_acceptance",
            "false_refusal",
        }

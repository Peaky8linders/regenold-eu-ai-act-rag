"""R360 — HyPA-RAG reference-free axes: answer_faithfulness + answer_relevancy.

HyPA-RAG (Kalra et al.) evaluation metrics #1 (Faithfulness) and #2
(Answer Relevancy), ported from Ragas. Both are reference-free — they
score from the retrieved context / the question alone, never the gold
answer — which is precisely what makes the no-gold half of a benchmark
scorable. These tests pin the post-processing contract (verdict
derivation, threshold, unscorable-vs-pass semantics).
"""
from __future__ import annotations

import pytest

from evals.judge import legal_v2 as L


# ── _AXIS_KEYS / unanswered semantics ────────────────────────────────────


def test_faithfulness_keys_require_structured_carrier():
    """A reply carrying only free text has not answered the axis.

    R350 doctrine: ABSENT IS NOT EMPTY. ``{"failure_mode": "..."}`` must be
    unscorable — never a silent 1.0 pass. Only an explicit ``claims`` array
    (including ``[]``) answers the axis.
    """
    assert L._AXIS_KEYS["answer_faithfulness"] == ("claims",)
    r = L._postprocess("answer_faithfulness", {"failure_mode": "none"}, {}, {})
    assert r.get("judge_error") == "axis_unanswered_answer_faithfulness"


def test_relevancy_keys_require_structured_carrier():
    assert L._AXIS_KEYS["answer_relevancy"] == ("relevancy",)
    r = L._postprocess("answer_relevancy", {"rationale": "only prose"}, {}, {})
    assert r.get("judge_error") == "axis_unanswered_answer_relevancy"


# ── answer_faithfulness post-processing ──────────────────────────────────


def test_faithfulness_all_supported_passes():
    raw = {"claims": [{"text": "A", "status": "SUPPORTED"},
                      {"text": "B", "status": "SUPPORTED"}]}
    r = L._postprocess_answer_faithfulness(raw)
    assert r["verdict"] == "pass"
    assert r["faithfulness"] == 1.0
    assert r["supported"] == 2 and r["unsupported"] == 0


def test_faithfulness_one_unsupported_fails_at_ragas_threshold():
    """Ragas default threshold is 1.0 — a single unsupported claim fails."""
    raw = {"claims": [{"text": "A", "status": "SUPPORTED"},
                      {"text": "B", "status": "UNSUPPORTED", "why": "not in text"}]}
    r = L._postprocess_answer_faithfulness(raw)
    assert r["verdict"] == "fail"
    assert r["faithfulness"] == 0.5
    assert r["unsupported_claims"] == ["B"]


def test_faithfulness_empty_claims_is_pass():
    """[] is a legitimate finding (nothing decomposed -> nothing to be
    unfaithful to) — Ragas semantics, and the file's R350 doctrine that
    an explicitly-empty structured array is the pass case."""
    r = L._postprocess_answer_faithfulness({"claims": []})
    assert r["verdict"] == "pass"
    assert r["faithfulness"] == 1.0


def test_faithfulness_unclassified_claim_counts_supported():
    """A malformed claim entry is never evidence of a hallucination."""
    raw = {"claims": [{"text": "A", "status": "SUPPORTED"},
                      {"text": "B"}]}
    r = L._postprocess_answer_faithfulness(raw)
    assert r["verdict"] == "pass"
    assert r["faithfulness"] == 1.0


def test_faithfulness_judge_error_passthrough():
    raw = {"judge_error": "call_failed", "_raw": {}}
    assert L._postprocess_answer_faithfulness(raw) == raw


# ── answer_relevancy post-processing ─────────────────────────────────────


def test_relevancy_high_passes():
    r = L._postprocess_answer_relevancy({"relevancy": 0.9, "rationale": "directly answers"})
    assert r["verdict"] == "pass"
    assert r["relevancy"] == 0.9


def test_relevancy_evasion_fails():
    r = L._postprocess_answer_relevancy({"relevancy": 0.2, "rationale": "answers a different question"})
    assert r["verdict"] == "fail"


def test_relevancy_half_misses_core_subquestion_still_passes():
    """0.5 = 'addresses a substantial part but misses a core sub-question'.
    Relevancy is about addressing the question, not completeness — that is
    graded elsewhere. Ragas default threshold = 0.5."""
    r = L._postprocess_answer_relevancy({"relevancy": 0.5})
    assert r["verdict"] == "pass"


def test_relevancy_non_numeric_unscorable():
    r = L._postprocess_answer_relevancy({"relevancy": "abc"})
    assert r.get("judge_error") == "relevancy_not_numeric"


def test_relevancy_out_of_range_unscorable():
    r = L._postprocess_answer_relevancy({"relevancy": 1.7})
    assert r.get("judge_error") == "relevancy_out_of_range: 1.7"
    r2 = L._postprocess_answer_relevancy({"relevancy": -0.1})
    assert r2.get("judge_error")


def test_relevancy_judge_error_passthrough():
    raw = {"judge_error": "call_failed", "_raw": {}}
    assert L._postprocess_answer_relevancy(raw) == raw


# ── _postprocess dispatch ────────────────────────────────────────────────


@pytest.mark.parametrize("axis,raw", [
    ("answer_faithfulness", {"claims": [{"text": "A", "status": "SUPPORTED"}]}),
    ("answer_relevancy", {"relevancy": 0.8}),
])
def test_dispatch_routes_new_axes(axis, raw):
    r = L._postprocess(axis, raw, {}, {})
    assert r["verdict"] == "pass"


# ── aggregate ────────────────────────────────────────────────────────────


def test_aggregate_surfaces_reference_free_stats():
    rows = [
        {"id": "r1", "category": "c", "verdicts": {
            "answer_faithfulness": {"verdict": "pass", "faithfulness": 1.0,
                                    "supported": 2, "unsupported": 0},
            "answer_relevancy": {"verdict": "pass", "relevancy": 0.9},
        }},
        {"id": "r2", "category": "c", "verdicts": {
            "answer_faithfulness": {"verdict": "fail", "faithfulness": 0.5,
                                    "supported": 1, "unsupported": 1},
            "answer_relevancy": {"verdict": "fail", "relevancy": 0.2},
        }},
    ]
    agg = L._aggregate(rows)
    f, rel = agg["answer_faithfulness"], agg["answer_relevancy"]
    assert f["mean_faithfulness"] == 0.75
    assert f["unsupported_rows"] == 1
    assert rel["mean_relevancy"] == 0.55


def test_aggregate_default_axes_unaffected():
    """Standard 4-axis runs carry no reference-free keys -> no entries."""
    rows = [{"id": "r1", "category": "c", "verdicts": {
        "answer_correctness": {"verdict": "pass"},
        "reference_correctness": {"verdict": "pass"},
        "citation_faithfulness": {"verdict": "pass"},
        "answer_conciseness": {"verdict": "pass"},
    }}]
    agg = L._aggregate(rows)
    assert "answer_faithfulness" not in agg
    assert "answer_relevancy" not in agg


# ── prepare (grounding contract) ────────────────────────────────────────


def test_prepare_faithfulness_uses_pred_refs_only():
    """The faithfulness axis must ground ONLY on the predicted refs —
    never gold refs/answers — or it stops being reference-free and can no
    longer score the no-gold half of a benchmark."""
    r = {"id": "x", "category": "c", "question": "Q", "answer": "A",
         "pred_refs": ["Article 5"], "gold_refs": ["Article 99"],
         "gold_answer": "secret gold that must not leak"}
    prompt, ctx = L._prepare("answer_faithfulness", r)
    assert "secret gold" not in prompt
    assert "Article 99" not in prompt
    assert list(ctx["pred_map"].keys()) == ["Article 5"]


def test_prepare_relevancy_question_answer_only():
    r = {"id": "x", "category": "c", "question": "Q", "answer": "A",
         "pred_refs": ["Article 5"], "gold_refs": ["Article 99"],
         "gold_answer": "secret gold"}
    prompt, ctx = L._prepare("answer_relevancy", r)
    assert "secret gold" not in prompt
    assert "Article 99" not in prompt
    assert ctx == {}

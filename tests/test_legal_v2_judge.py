"""R305 — offline unit tests for ``evals.judge.legal_v2`` (no LLM calls).

Locks in:
* Bias-control allowlist — a forbidden key (``arm`` / ``label`` /
  ``july07_answer`` / ``system`` / prior ``score``) on the input row never
  leaks into any of the 4 rendered prompts.
* Quote-substantiation forcing function (``_quote_substantiated``).
* The three-way reference-correctness rule: SUPPORTING never fails the
  axis; an unsubstantiated WRONG/MISSING claim is downgraded/dropped; a
  substantiated one survives.
* CoVe answer-correctness: an unsubstantiated CONTRADICTED proposition is
  downgraded to NOT-ADDRESSED; omission alone still fails the axis.
* Citation-faithfulness quote-or-retract downgrade.
* Answer-conciseness never rewards omission and drops hallucinated
  "redundant sentence" claims that aren't real substrings of the answer.
* Self-consistency aggregation — majority verdict (2-way ties -> fail),
  median numeric fields, per-row agreement.

``get_provision_text`` is a pure local data lookup (no network), so these
tests exercise the real render/prepare path against real EU AI Act text.
"""
from __future__ import annotations

import pytest

from evals.judge.legal_v2 import (
    AXES,
    _aggregate_samples,
    _postprocess_answer_conciseness,
    _postprocess_answer_correctness,
    _postprocess_citation_faithfulness,
    _postprocess_reference_correctness,
    _prepare,
    _quote_substantiated,
)
from evals.judge.grounded import _norm


# ── fixtures ──────────────────────────────────────────────────────────────

_REAL_ART9_TEXT = (
    "A risk management system shall be established, implemented, "
    "documented and maintained in relation to high-risk AI systems."
)


def _row(**overrides):
    base = {
        "id": "t1",
        "category": "test",
        "question": "What must a provider establish to manage risk?",
        "pred_answer": "Providers must establish a risk management system per Article 9.",
        "pred_refs": ["Article 9"],
        "gold_refs": ["Article 9"],
    }
    base.update(overrides)
    return base


# ── bias-control allowlist ────────────────────────────────────────────────


class TestBiasAllowlist:
    def test_forbidden_keys_never_reach_the_normalised_row(self) -> None:
        raw = _row(
            arm="branch",
            label="r298-secret-label",
            july07_answer="ZZZ_FORBIDDEN_JULY7_BASELINE_ZZZ",
            system="production-v3",
            score=0.42,
        )
        r = _norm(raw)
        assert "arm" not in r
        assert "label" not in r
        assert "july07_answer" not in r
        assert "system" not in r
        assert "score" not in r

    def test_forbidden_values_never_leak_into_any_rendered_prompt(self) -> None:
        marker_arm = "MARKER_ARM_XYZQ"
        marker_label = "MARKER_LABEL_XYZQ"
        marker_july7 = "MARKER_JULY7_BASELINE_XYZQ"
        raw = _row(
            arm=marker_arm,
            label=marker_label,
            july07_answer=marker_july7,
            system="MARKER_SYSTEM_XYZQ",
        )
        r = _norm(raw)
        for axis in AXES:
            prompt, _ctx = _prepare(axis, r)
            assert marker_arm not in prompt
            assert marker_label not in prompt
            assert marker_july7 not in prompt
            assert "MARKER_SYSTEM_XYZQ" not in prompt

    def test_norm_allowlist_includes_only_independent_grounding_inputs(self) -> None:
        r = _norm(_row())
        assert set(r.keys()) == {
            "id", "category", "question", "answer", "pred_refs", "gold_refs",
            "gold_answer", "independent_gold_context",
        }


# ── quote substantiation ──────────────────────────────────────────────────


class TestQuoteSubstantiation:
    def test_empty_quote_fails(self) -> None:
        assert _quote_substantiated("", "some long block of text here") is False

    def test_short_quote_below_min_words_fails(self) -> None:
        assert _quote_substantiated("short quote", "short quote of text appears here too") is False

    def test_quote_not_present_anywhere_fails(self) -> None:
        assert _quote_substantiated(
            "this exact phrase does not exist in the source text at all",
            "a completely different block of source material entirely",
        ) is False

    def test_literal_substring_with_whitespace_and_case_noise_passes(self) -> None:
        block = "A Risk Management   System shall be established, implemented, documented and maintained."
        quote = "a risk management system shall be established implemented documented and maintained"
        # Normalisation strips whitespace-run differences; punctuation is
        # NOT stripped, so drop the trailing period from the quote — the
        # comma inside is preserved verbatim from the block.
        quote = "a risk management system shall be established, implemented, documented and maintained"
        assert _quote_substantiated(quote, block) is True

    def test_checks_multiple_blocks(self) -> None:
        assert _quote_substantiated(
            "a risk management system shall be established, implemented",
            "irrelevant block one that does not contain it",
            _REAL_ART9_TEXT,
        ) is True


# ── reference correctness: three-way classification ───────────────────────


class TestReferenceCorrectnessThreeWay:
    def test_unsubstantiated_wrong_is_downgraded_to_supporting(self) -> None:
        raw = {
            "classifications": [
                {"ref": "Article 9", "class": "WRONG", "quote": "a made up quote that is not in the text"},
            ],
            "missing_governing": [],
        }
        pred_map = {"Article 9": _REAL_ART9_TEXT}
        out = _postprocess_reference_correctness(raw, pred_map, {}, ["Article 9"])
        assert out["wrong_refs"] == []
        assert out["supporting_refs"] == ["Article 9"]
        assert out["verdict"] == "pass"
        assert len(out["unsubstantiated_verdicts"]) == 1
        assert out["unsubstantiated_verdicts"][0]["claimed"] == "WRONG"

    def test_substantiated_wrong_survives_and_fails(self) -> None:
        raw = {
            "classifications": [
                {
                    "ref": "Article 99",
                    "class": "WRONG",
                    "quote": "administrative fines of up to eur 35 000 000",
                },
            ],
            "missing_governing": [],
        }
        pred_map = {
            "Article 99": (
                "Non-compliance with the prohibition of the AI practices referred to "
                "in Article 5 shall be subject to administrative fines of up to EUR "
                "35 000 000 or, if the offender is an undertaking, up to 7 % of its "
                "total worldwide annual turnover."
            ),
        }
        out = _postprocess_reference_correctness(raw, pred_map, {}, ["Article 99"])
        assert out["wrong_refs"] == ["Article 99"]
        assert out["verdict"] == "fail"
        assert out["unsubstantiated_verdicts"] == []

    def test_supporting_refs_never_fail_the_axis_even_with_many(self) -> None:
        raw = {
            "classifications": [
                {"ref": "Article 9", "class": "GOVERNING"},
                {"ref": "Article 10", "class": "SUPPORTING"},
                {"ref": "Article 11", "class": "SUPPORTING"},
                {"ref": "Article 12", "class": "SUPPORTING"},
                {"ref": "Article 13", "class": "SUPPORTING"},
            ],
            "missing_governing": [],
        }
        pred_refs = ["Article 9", "Article 10", "Article 11", "Article 12", "Article 13"]
        out = _postprocess_reference_correctness(raw, {}, {}, pred_refs)
        assert out["verdict"] == "pass"
        assert len(out["supporting_refs"]) == 4
        assert out["governing_refs"] == ["Article 9"]
        assert out["wrong_refs"] == []

    def test_unsubstantiated_missing_is_dropped(self) -> None:
        raw = {
            "classifications": [{"ref": "Article 9", "class": "GOVERNING"}],
            "missing_governing": [{"ref": "Article 27", "quote": "an invented quote not in gold text"}],
        }
        out = _postprocess_reference_correctness(raw, {}, {}, ["Article 9"])
        assert out["missing_governing_refs"] == []
        assert out["verdict"] == "pass"
        assert any(u["claimed"] == "MISSING" for u in out["unsubstantiated_verdicts"])

    def test_substantiated_missing_survives_and_fails(self) -> None:
        gold_map = {"Article 27": "Deployers shall carry out a fundamental rights impact assessment."}
        raw = {
            "classifications": [{"ref": "Article 9", "class": "GOVERNING"}],
            "missing_governing": [
                {"ref": "Article 27", "quote": "deployers shall carry out a fundamental rights impact assessment"},
            ],
        }
        out = _postprocess_reference_correctness(raw, {}, gold_map, ["Article 9"])
        assert out["missing_governing_refs"] == ["Article 27"]
        assert out["verdict"] == "fail"

    def test_focus_vs_legal_soundness_precision_and_recall_formulas(self) -> None:
        raw = {
            "classifications": [
                {"ref": "Article 9", "class": "GOVERNING"},
                {"ref": "Article 10", "class": "SUPPORTING"},
            ],
            "missing_governing": [],
        }
        out = _postprocess_reference_correctness(raw, {}, {}, ["Article 9", "Article 10"])
        assert out["focus_precision"] == 0.5  # GOVERNING / total
        assert out["legal_soundness_precision"] == 1.0  # (GOVERNING+SUPPORTING) / total
        assert out["recall"] == 1.0  # no missing


# ── answer correctness: chain-of-verification ──────────────────────────────


class TestAnswerCorrectnessCoVe:
    def test_unsubstantiated_contradiction_downgrades_to_not_addressed(self) -> None:
        raw = {
            "propositions": [
                {"text": "emotion recognition is fully permitted everywhere", "status": "CONTRADICTED", "quote": "made up quote"},
            ],
            "omission_present": False,
        }
        out = _postprocess_answer_correctness(raw, {"Article 5.1.f": "irrelevant unrelated block of text here"})
        assert out["contradicted"] == 0
        assert out["not_addressed"] == 1
        assert out["fabrication_present"] is False
        # Unsupported propositions now count against correctness.
        assert out["verdict"] == "fail"
        assert out["unsupported_present"] is True
        assert len(out["unsubstantiated_verdicts"]) == 1

    def test_substantiated_contradiction_fails_as_fabrication(self) -> None:
        text = "the placing on the market of AI systems to infer emotions in the workplace is prohibited"
        raw = {
            "propositions": [
                {"text": "emotion recognition is fully permitted in the workplace", "status": "CONTRADICTED", "quote": text},
            ],
            "omission_present": False,
        }
        out = _postprocess_answer_correctness(raw, {"Article 5.1.f": text})
        assert out["contradicted"] == 1
        assert out["fabrication_present"] is True
        assert out["verdict"] == "fail"

    def test_omission_alone_fails_even_with_zero_contradictions(self) -> None:
        raw = {
            "propositions": [{"text": "x is true", "status": "SUPPORTED"}],
            "omission_present": True,
            "omission_detail": "never states whether the system is high-risk",
        }
        out = _postprocess_answer_correctness(raw, {})
        assert out["contradicted"] == 0
        assert out["fabrication_present"] is False
        assert out["omission_present"] is True
        assert out["verdict"] == "fail"

    def test_all_supported_no_omission_passes(self) -> None:
        raw = {
            "propositions": [
                {"text": "a", "status": "SUPPORTED"},
                {"text": "b", "status": "SUPPORTED"},
            ],
            "omission_present": False,
        }
        out = _postprocess_answer_correctness(raw, {})
        assert out["verdict"] == "pass"
        assert out["factual_score"] == 1.0


# ── citation faithfulness ────────────────────────────────────────────────


class TestCitationFaithfulness:
    def test_unsubstantiated_mismatch_downgrades_to_faithful(self) -> None:
        raw = {"citations": [{"ref": "Article 9", "status": "MISMATCHED", "quote": "invented text"}]}
        out = _postprocess_citation_faithfulness(raw, {"Article 9": _REAL_ART9_TEXT}, ["Article 9"])
        assert out["mismatched_refs"] == []
        assert out["verdict"] == "pass"
        assert len(out["unsubstantiated_verdicts"]) == 1

    def test_substantiated_mismatch_fails(self) -> None:
        ce_text = "the CE marking shall be subject to the general principles set out in Article 30"
        raw = {"citations": [{"ref": "Article 9", "status": "MISMATCHED", "quote": ce_text}]}
        out = _postprocess_citation_faithfulness(raw, {"Article 9": ce_text}, ["Article 9"])
        assert out["mismatched_refs"] == ["Article 9"]
        assert out["verdict"] == "fail"


# ── answer conciseness ───────────────────────────────────────────────────


class TestAnswerConciseness:
    def test_hallucinated_redundant_sentence_is_dropped(self) -> None:
        answer = "Providers must establish a risk management system per Article 9."
        raw = {"redundant_sentences": ["this sentence never appeared anywhere in the answer text"], "unrequested_topics": []}
        out = _postprocess_answer_conciseness(raw, answer)
        assert out["redundant_sentence_count"] == 0
        assert out["verdict"] == "pass"
        assert len(out["unsubstantiated_verdicts"]) == 1

    def test_real_substring_redundant_sentence_survives_and_fails(self) -> None:
        answer = "Providers must establish a risk management system. As noted, providers must establish a risk management system."
        raw = {"redundant_sentences": ["providers must establish a risk management system"], "unrequested_topics": []}
        out = _postprocess_answer_conciseness(raw, answer)
        assert out["redundant_sentence_count"] == 1
        assert out["verdict"] == "fail"

    def test_prompt_explicitly_forbids_penalising_omission(self) -> None:
        from evals.judge.legal_v2 import render_answer_conciseness
        p = render_answer_conciseness({"question": "q", "answer": "a"})
        assert "do not judge completeness" in p.lower()


# ── self-consistency aggregation ─────────────────────────────────────────


class TestSelfConsistencyAggregation:
    def test_majority_verdict_and_median_numeric_field(self) -> None:
        samples = [
            {"verdict": "pass", "focus_precision": 0.5},
            {"verdict": "pass", "focus_precision": 0.9},
            {"verdict": "fail", "focus_precision": 0.6},
        ]
        merged = _aggregate_samples(samples, "reference_correctness")
        assert merged["verdict"] == "pass"
        assert merged["_agreement"] == round(2 / 3, 4)
        assert merged["focus_precision"] == 0.6  # median of [0.5, 0.6, 0.9]
        assert merged["_samples_n"] == 3

    def test_two_way_tie_resolves_to_fail(self) -> None:
        samples = [{"verdict": "pass"}, {"verdict": "fail"}]
        merged = _aggregate_samples(samples, "citation_faithfulness")
        assert merged["verdict"] == "fail"
        assert merged["_agreement"] == 0.5

    def test_all_samples_errored_reports_judge_error(self) -> None:
        samples = [{"judge_error": "timeout"}, {"judge_error": "timeout"}]
        merged = _aggregate_samples(samples, "answer_correctness")
        assert merged.get("judge_error")

    def test_single_sample_passthrough(self) -> None:
        samples = [{"verdict": "pass", "focus_precision": 0.8}]
        merged = _aggregate_samples(samples, "reference_correctness")
        assert merged["verdict"] == "pass"
        assert merged["_agreement"] == 1.0
        assert merged["focus_precision"] == 0.8


# ── axes shape ────────────────────────────────────────────────────────────


class TestAxes:
    def test_exactly_four_axes(self) -> None:
        assert len(AXES) == 4
        assert set(AXES) == {
            "answer_correctness", "reference_correctness",
            "citation_faithfulness", "answer_conciseness",
        }

    def test_unknown_axis_raises(self) -> None:
        with pytest.raises(ValueError):
            _prepare("nonexistent_axis", _norm(_row()))

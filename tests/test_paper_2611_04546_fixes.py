"""Verification suite for the arXiv:2611.04546 benchmark & pipeline improvements.

Covers:
1. Versioned benchmark profile (``published_2026`` vs ``r391_report``) in
   ``evals/official/rubric.py`` and ``evals/regenold/hard_preamble.py``.
2. Decision machinery, pooled micro-correctness in ``evals/official/paired_ab.py``,
   strict winner & criterion validation in ``evals/harness/ab_judge.py`` and
   ``evals/official/judge.py``, and complete cache identity in
   ``evals/official/score_arm.py``.
3. Runtime conversation anchor boundary matching, ``EvidenceBundle``
   claim-to-provision linking, and curated sentence/reference preservation
   across single- and multi-sentence hospital deployer phrasings.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.engines.evidence_bundle import (
    ClaimProvisionLink,
    parse_evidence_block,
    required_claim_provisions,
)
from app.routes import regenold as route_mod
from evals.harness import ab_judge
from evals.official import judge as official_judge
from evals.official import paired_ab, rubric
from evals.official import score_arm as sa
from evals.regenold import hard_preamble as hp

# ── 1. Versioned Benchmark Profile & Released Scorer Adapter ───────────────


def test_published_ref_scoring_matches_first_sublevel_and_parent_exemption() -> None:
    # Deep subpoints collapse to first sublevel (Article 13.3) in published_2026.
    assert (
        rubric.reference_correctness_strict_published(
            ["Article 13.3.b"], ["Article 13.3.a"]
        )
        == 1.0
    )
    assert (
        rubric.reference_correctness_strict(["Article 13.3.b"], ["Article 13.3.a"])
        == 0.0
    )

    # Top-level parent alongside expected subpoint is exempt from excess penalty
    # in published_2026 (1 / (1 + 0) = 1.0), vs count ratio 1/2 = 0.5 in r391_report.
    assert (
        rubric.reference_conciseness_published(
            ["Article 6", "Article 6.1"], ["Article 6.1"]
        )
        == 1.0
    )
    assert (
        rubric.reference_conciseness(["Article 6", "Article 6.1"], ["Article 6.1"])
        == 0.5
    )

    # Specific paragraph satisfies expected top-level Article, but second sibling
    # paragraph remains an extra (strict_extra_pct = 1.0 -> conciseness = 0.5).
    scores = rubric.compute_published_ref_scores(
        ["Article 6.1", "Article 6.2"], ["Article 6"]
    )
    assert scores["strict_found_pct"] == 1.0
    assert scores["strict_extra_pct"] == 1.0
    assert (
        rubric.reference_conciseness_published(
            ["Article 6.1", "Article 6.2"], ["Article 6"]
        )
        == 0.5
    )

    # Empty expected references return None across all three reference metrics.
    assert rubric.reference_correctness_loose_published(["Article 6"], []) is None
    assert rubric.reference_correctness_strict_published(["Article 6"], []) is None
    assert rubric.reference_conciseness_published(["Article 6"], []) is None


def test_published_answer_conciseness_uses_word_counts() -> None:
    ref = "alpha beta gamma delta"  # 4 words, 22 chars
    cand = "a b c d e f g h"  # 8 words, 15 chars
    # Word-based: 4 / 8 = 0.5. Character-based: min(1.0, 22 / 15) = 1.0.
    assert rubric.answer_conciseness_published(cand, ref) == 0.5
    assert rubric.answer_conciseness(cand, ref) == 1.0


def test_score_rows_supports_both_profiles_and_rejects_unknown() -> None:
    rows = [
        {
            "criteria": [True, False],
            "answer": "a b c d e f g h",
            "reference_answer": "alpha beta gamma delta",
            "references": ["Article 6", "Article 6.1"],
            "expected_refs": ["Article 6.1"],
            "tone_ok": True,
            "latency_s": 10.0,
        }
    ]
    r391 = rubric.score_rows(rows)
    pub = rubric.score_rows(rows, profile=rubric.PROFILE_PUBLISHED_2026)
    # R474: the result dict is written verbatim as ``axes`` and read as numbers by every
    # consumer, so it must hold NO string (R473 added ``"profile"`` and broke one).
    for res in (r391, pub):
        assert all(isinstance(v, int | float) for v in res.values()), res
    assert r391["ans_conciseness"] == 100.0
    assert pub["ans_conciseness"] == 50.0
    assert r391["ref_conciseness"] == 50.0
    assert pub["ref_conciseness"] == 100.0

    with pytest.raises(ValueError, match="Unknown rubric profile"):
        rubric.score_rows(rows, profile="unknown_profile")


def test_summarize_published_runs_computes_per_run_metrics_and_validates_coverage() -> None:
    # Single question with 2 criteria across 3 judge repeats:
    # Run 0: [T, F] -> loose 50, strict 0
    # Run 1: [T, T] -> loose 100, strict 100
    # Run 2: [F, T] -> loose 50, strict 0
    # Published per-run mean: loose = 66.67, strict = 33.33 (vs 100.0 under majority vote).
    entries = [
        {
            "judgements_correctness": [
                {"criteria": [{"passed": True}, {"passed": False}]},
                {"criteria": [{"passed": True}, {"passed": True}]},
                {"criteria": [{"passed": False}, {"passed": True}]},
            ],
            "judgements_tone": [
                {"appropriateness_passed": True, "clarity_passed": True},
                {"appropriateness_passed": True, "clarity_passed": False},
                {"appropriateness_passed": True, "clarity_passed": True},
            ],
            "answer_conciseness_score": 1.0,
            "loose_found_pct": 1.0,
            "strict_found_pct": 1.0,
            "strict_extra_pct": 0.0,
            "latency_seconds": 10.0,
        }
    ]
    report = rubric.summarize_published_runs(entries)
    assert report["rows"] == 1
    assert report["judge_runs"] == 3
    assert report["by_axis"]["ans_correctness_loose"]["mean"] == pytest.approx(
        200.0 / 3.0
    )
    assert report["by_axis"]["ans_correctness_strict"]["mean"] == pytest.approx(
        100.0 / 3.0
    )
    assert report["by_axis"]["ans_correctness_strict"]["min"] == 0.0
    assert report["by_axis"]["ans_correctness_strict"]["max"] == 100.0
    assert report["by_axis"]["regulatory_tone"]["mean"] == pytest.approx(200.0 / 3.0)

    # Uneven repeat coverage must raise ValueError when strict_coverage=True.
    bad_entries = [
        {
            **entries[0],
            "judgements_tone": [
                {"appropriateness_passed": True, "clarity_passed": True}
            ],
        }
    ]
    with pytest.raises(ValueError, match="uneven repeat coverage"):
        rubric.summarize_published_runs(bad_entries, strict_coverage=True)


def test_published_2026_hard_preamble_and_pushback_template() -> None:
    pub_msgs = hp.preamble_messages(profile=hp.MODE_PUBLISHED)
    fixed_msgs = hp.preamble_messages(profile=hp.MODE_FIXED)
    assert len(pub_msgs) == 18
    assert sum(len(m["content"].split()) for m in pub_msgs) == 501
    assert hp.preamble_digest(profile=hp.MODE_PUBLISHED) != hp.preamble_digest(
        profile=hp.MODE_FIXED
    )
    assert hp.preamble_messages() == fixed_msgs
    assert (
        hp.hard_preamble_mode({hp.HARD_PREAMBLE_ENV: "published"})
        == hp.MODE_PUBLISHED
    )

    pb = hp.build_prefixed_pushback_messages(
        "What is Article 6?", "It governs high-risk classification.", profile="published"
    )
    assert len(pb) == 21
    assert pb[-1]["content"].startswith(
        "I don't think this is correct. Perhaps your answer contains hallucinations."
    )
    assert pb[-1]["content"].endswith("Let's try again:\nWhat is Article 6?")


# ── 2. Decision Machinery, Paired Micro-Correctness, Judge & Cache ─────────


def test_paired_ab_compare_uses_pooled_micro_correctness_and_retains_macro(
    tmp_path: Path,
) -> None:
    a_file = tmp_path / "score-a.json"
    b_file = tmp_path / "score-b.json"
    rows_a = [
        {
            "id": "q_short",
            "criteria": [False],
            "tone_ok": True,
            "latency_s": 5.0,
            "answer_chars": 100,
            "reference_chars": 100,
            "refs": ["Article 6"],
            "expected_refs": ["Article 6"],
        },
        {
            "id": "q_long",
            "criteria": [True, True, True, True, True],
            "tone_ok": True,
            "latency_s": 5.0,
            "answer_chars": 100,
            "reference_chars": 100,
            "refs": ["Article 6"],
            "expected_refs": ["Article 6"],
        },
    ]
    rows_b = [
        {
            "id": "q_short",
            "criteria": [True],
            "tone_ok": True,
            "latency_s": 5.0,
            "answer_chars": 100,
            "reference_chars": 100,
            "refs": ["Article 6"],
            "expected_refs": ["Article 6"],
        },
        {
            "id": "q_long",
            "criteria": [False, False, True, True, True],
            "tone_ok": True,
            "latency_s": 5.0,
            "answer_chars": 100,
            "reference_chars": 100,
            "refs": ["Article 6"],
            "expected_refs": ["Article 6"],
        },
    ]
    a_file.write_text(json.dumps({"rows": rows_a}), encoding="utf-8")
    b_file.write_text(json.dumps({"rows": rows_b}), encoding="utf-8")

    cmp_res = paired_ab.compare(a_file, b_file)
    loose = cmp_res["axes"]["ans_correctness_loose"]
    # Pooled micro correctness: A satisfies 5/6 (83.33%), B satisfies 4/6 (66.67%) -> delta = -16.67 pp.
    assert loose["mean_a"] == pytest.approx(500.0 / 6.0)
    assert loose["mean_b"] == pytest.approx(400.0 / 6.0)
    assert loose["delta"] == pytest.approx(-100.0 / 6.0)
    # Macro diagnostic is preserved explicitly.
    assert loose["macro_mean_a"] == pytest.approx(50.0)
    assert loose["macro_mean_b"] == pytest.approx(80.0)
    assert loose["macro_delta"] == pytest.approx(30.0)


def test_ab_judge_rejects_malformed_winner_and_separates_invalids_from_ties() -> None:
    a = ab_judge.ArmAnswer("Candidate A.", [], 0.0, 200)
    b = ab_judge.ArmAnswer("Candidate B.", [], 0.0, 200)

    def banana_caller(_prompt):
        return {"winner": "banana"}

    assert ab_judge._judge_one_ok(banana_caller, "p") == ("tie", False)
    v, agreed, outcome = ab_judge._pairwise_verdict_outcome(
        {"question": "Q?"}, "correctness", a, b, banana_caller, {}
    )
    assert (v, agreed, outcome) == ("tie", False, "invalid")

    def tie_caller(_prompt):
        return {"winner": "tie"}

    assert ab_judge._judge_one_ok(tie_caller, "p") == ("tie", True)
    v_tie, agreed_tie, outcome_tie = ab_judge._pairwise_verdict_outcome(
        {"question": "Q?"}, "correctness", a, b, tie_caller, {}
    )
    assert (v_tie, agreed_tie, outcome_tie) == ("tie", True, "tie")

    # Position disagreement: always picks first slot "A" in both orderings.
    def pos_biased_caller(_prompt):
        return {"winner": "A"}

    v_flip, agreed_flip, outcome_flip = ab_judge._pairwise_verdict_outcome(
        {"question": "Q?"}, "correctness", a, b, pos_biased_caller, {}
    )
    assert (v_flip, agreed_flip, outcome_flip) == (
        "tie",
        False,
        "position_disagreement",
    )


def test_gate_exit_code_distinguishes_pass_fail_and_indeterminate() -> None:
    assert ab_judge.gate_exit_code({"tier": "deterministic", "n_rows": 30}) == 2
    assert (
        ab_judge.gate_exit_code(
            {
                "tier": "live-pairwise",
                "n_rows": 10,
                "axes": {
                    "correctness": {"verdict": "even", "invalids": 5},
                },
            }
        )
        == 2
    )
    assert (
        ab_judge.gate_exit_code(
            {
                "tier": "live-pairwise",
                "n_rows": 10,
                "axes": {
                    "correctness": {"verdict": "BASELINE wins (sig)", "invalids": 0},
                    "overall": {"verdict": "even", "invalids": 0},
                },
            }
        )
        == 1
    )
    # R474 - a PASS needs evidence the test could have failed on. This case used
    # n_rows=10 and no decisive-pair counts and expected PASS: the very false green
    # R398 removed from easyhard_ab (n floor 30; a sign test needs >= 6 decisive pairs).
    assert (
        ab_judge.gate_exit_code(
            {
                "tier": "live-pairwise",
                "n_rows": 60,
                "axes": {
                    "correctness": {
                        "verdict": "BRANCH wins (sig)",
                        "invalids": 0,
                        "wins_branch": 12,
                        "wins_baseline": 1,
                    },
                    "overall": {"verdict": "branch leans (ns)", "invalids": 0},
                },
            }
        )
        == 0
    )


def test_official_judge_verdicts_from_enforces_strict_one_to_one_coverage() -> None:
    # Valid 1-based
    assert official_judge._verdicts_from(
        [
            {"n": 1, "satisfied": True, "why": "ok"},
            {"n": 2, "satisfied": False, "why": "no"},
        ],
        2,
    ) == ([True, False], ["ok", "no"])
    # Valid 0-based
    assert official_judge._verdicts_from(
        [
            {"n": 0, "satisfied": False, "why": "no"},
            {"n": 1, "satisfied": True, "why": "ok"},
        ],
        2,
    ) == ([False, True], ["no", "ok"])
    # Out-of-range criterion index n=99 must be rejected, not defaulted to False.
    assert official_judge._verdicts_from(
        [
            {"n": 1, "satisfied": True, "why": "ok"},
            {"n": 99, "satisfied": True, "why": "bad"},
        ],
        2,
    ) == (None, [])
    # Duplicate criterion index must be rejected.
    assert official_judge._verdicts_from(
        [
            {"n": 1, "satisfied": True, "why": "ok"},
            {"n": 1, "satisfied": False, "why": "dup"},
        ],
        2,
    ) == (None, [])
    # Length mismatch must be rejected.
    assert official_judge._verdicts_from(
        [{"n": 1, "satisfied": True, "why": "ok"}], 2
    ) == (None, [])


def test_judge_basis_sha_changes_when_question_or_criteria_or_refs_change() -> None:
    base = {
        "question": "Original question?",
        "criteria_text": ["Criterion 1"],
        "expected_refs": ["Article 6.2"],
    }
    sha_base = sa._judge_basis_sha(base)
    assert sha_base != sa._judge_basis_sha({**base, "question": "Changed question?"})
    assert sha_base != sa._judge_basis_sha({**base, "criteria_text": ["Criterion 2"]})
    assert sha_base != sa._judge_basis_sha({**base, "expected_refs": ["Article 13.1"]})


# ── 3. Runtime Pipeline Fixes: Anchors, Evidence Links & Finalization ──────


def test_extract_conversation_anchors_word_boundaries_and_plurals() -> None:
    turns = [
        SimpleNamespace(
            role="user",
            content="Are providers of Annex III AI systems automatically high-risk?",
        )
    ]
    anchors = route_mod._extract_conversation_anchors(turns)
    assert "Annex III" in anchors
    assert "provider" in anchors
    assert "annex iii" in anchors
    assert "high-risk" in anchors
    # Must NOT match "annex i" inside "Annex III".
    assert "annex i," not in anchors and not anchors.endswith("annex i]")


def test_evidence_bundle_claim_provision_links_on_hospital_answer() -> None:
    evidence_text = (
        "APPLICABLE OBLIGATIONS:\n"
        "- [kb-deployer-Art. 26] Article 26 deployer obligations\n"
        "- [kb-fria-Art. 27] Article 27 fundamental rights impact assessment\n"
        "- [kb-expl-Art. 86] Article 86 right to explanation\n"
        "- [kb-role-Art. 25] Article 25 value chain provider obligations\n"
        "- [kb-trans-Art. 13] Article 13 instructions for use\n"
    )
    bundle = parse_evidence_block(evidence_text)
    bundle.verify()
    assert bundle.render() == evidence_text

    hospital_answer = (
        "As deployer, the hospital must use the system in accordance with the "
        "provider's instructions for use, which Article 13 requires the provider "
        "to supply (Article 26(1)). "
        "The hospital must assign human oversight to natural persons with the "
        "necessary competence, training and authority (Article 26(2)), monitor "
        "the system's operation on the basis of those instructions and inform "
        "the provider of serious incidents (Article 26(5)), and retain the logs "
        "the system automatically generates (Article 26(6)). "
        "Where the hospital is a body governed by public law, a private entity "
        "providing public services, or a deployer of an Annex III point 5(b) or "
        "5(c) system, it must perform a fundamental rights impact assessment "
        "before first use (Article 27). "
        "A person subject to a deployer decision based on the system's output "
        "that produces legal effects or similarly significantly affects health, "
        "safety or fundamental rights has a right to an explanation (Article 86). "
        "These are deployer duties only: the hospital does not bear the "
        "provider's design and conformity duties unless it becomes a provider "
        "under Article 25 by putting its name or trademark on the system, making "
        "a substantial modification, or changing the intended purpose."
    )
    links = bundle.claim_links(hospital_answer)
    assert len(links) == 5
    assert all(isinstance(link, ClaimProvisionLink) and link.required for link in links)
    req_provs = required_claim_provisions(hospital_answer, bundle=bundle)
    for expected in (
        "Article 13",
        "Article 26.1",
        "Article 26.2",
        "Article 26.5",
        "Article 26.6",
        "Article 27",
        "Article 86",
        "Article 25",
    ):
        assert expected in req_provs


@pytest.mark.parametrize(
    "question",
    [
        "What obligations must a hospital meet when it deploys a high-risk AI system?",
        "A hospital deploys a high-risk AI system. What are the hospital's obligations?",
    ],
)
def test_hospital_deployer_paraphrases_preserve_all_five_sentences_and_citations(
    question: str,
) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json={"messages": [{"role": "user", "content": question}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    answer = body["answer"]
    refs = body["references"]

    for phrase in (
        "Article 13",
        "Article 26(1)",
        "Article 26(2)",
        "Article 26(5)",
        "Article 26(6)",
        "Article 27",
        "Article 86",
        "Article 25",
    ):
        assert phrase in answer

    ref_heads = {r.split(".", 1)[0] for r in refs}
    assert ref_heads == {
        "Article 26",
        "Article 27",
        "Article 86",
        "Article 25",
        "Article 13",
    }
    assert "Article 26" in refs

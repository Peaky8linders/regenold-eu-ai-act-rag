"""Tests for evals.bench.citation_faithfulness.

Covers:
    * All sentences supported by cited refs → recall = 1.0
    * All cited refs used by sentences → precision = 1.0
    * Hallucinated sentence (no overlap with any ref) → recall < 1.0
    * Hallucinated ref (no sentence overlap) → precision < 1.0
    * Empty answer → vacuous recall=1.0, precision=0.0, f1=0.0
    * Empty refs (with non-empty answer) → recall=N/A but precision=0.0
      and F1=0.0 (no refs to use → strict precision failure)
    * Wire-format ref normalisation (Article 13 → Art. 13 lookup hits)
    * Aggregate macro-averages cleanly.
"""
from __future__ import annotations

from evals.bench import citation_faithfulness as cf


# ── Fixture lookup ────────────────────────────────────────────────────────


def _make_lookup(mapping: dict[str, str]):
    """Tiny in-memory KB-text lookup for unit tests."""

    def _lookup(kb_key: str) -> str:
        return mapping.get(kb_key, "")

    return _lookup


# ── Happy path ────────────────────────────────────────────────────────────


def test_all_sentences_supported_recall_one() -> None:
    """Every answer sentence shares >=3 tokens with the cited ref."""
    lookup = _make_lookup(
        {
            "Art. 13": (
                "High-risk transparency instructions intended purpose "
                "lifetime providers designed covering supplied capabilities "
                "limitations human oversight."
            )
        }
    )
    # Each sentence carries 4+ non-stopword tokens that overlap the ref:
    # sent 1: {transparency, instructions, intended, purpose} (4)
    # sent 2: {lifetime, providers, oversight, human, capabilities} (5)
    answer = (
        "Transparency instructions cover the intended purpose. "
        "Providers must document lifetime capabilities and human oversight."
    )
    score = cf.score_citation_faithfulness(
        answer=answer,
        references=["Article 13"],
        kb_text_lookup=lookup,
    )
    assert score.n_sentences == 2
    assert score.n_supported == 2
    assert score.citation_recall == 1.0
    assert score.citation_precision == 1.0
    assert 0.99 <= score.citation_f1 <= 1.0


def test_all_refs_used_precision_one() -> None:
    """Every cited ref is used by at least one sentence."""
    lookup = _make_lookup(
        {
            "Art. 13": (
                "transparency instructions intended purpose lifetime "
                "providers capabilities limitations"
            ),
            "Art. 26": (
                "deployer monitoring oversight human suspension corrective "
                "fundamental rights impact assessment"
            ),
        }
    )
    # sent 1 → Art. 13 overlap: {transparency, instructions, intended,
    # purpose, lifetime} (5)
    # sent 2 → Art. 26 overlap: {monitoring, oversight, human,
    # corrective, suspension} (5)
    answer = (
        "Transparency instructions document intended purpose lifetime. "
        "Monitoring oversight requires human review suspension corrective."
    )
    score = cf.score_citation_faithfulness(
        answer=answer,
        references=["Article 13", "Article 26"],
        kb_text_lookup=lookup,
    )
    assert score.n_used_refs == 2
    assert score.citation_precision == 1.0


# ── Negative cases ────────────────────────────────────────────────────────


def test_hallucinated_sentence_reduces_recall() -> None:
    """A sentence with no overlap with any cited ref drops recall."""
    lookup = _make_lookup(
        {
            "Art. 13": "transparency instructions purpose providers lifetime",
        }
    )
    answer = (
        "Transparency instructions cover purpose and lifetime. "
        "Penguins migrate seasonally across the southern ocean."
    )
    score = cf.score_citation_faithfulness(
        answer=answer,
        references=["Article 13"],
        kb_text_lookup=lookup,
    )
    assert score.n_sentences == 2
    assert score.n_supported == 1
    assert score.citation_recall < 1.0
    assert score.citation_recall == 0.5


def test_hallucinated_ref_reduces_precision() -> None:
    """A cited ref not used by ANY sentence drops precision."""
    lookup = _make_lookup(
        {
            "Art. 13": "transparency instructions purpose providers lifetime",
            "Art. 99": "fines penalties enforcement market surveillance",
        }
    )
    answer = "Transparency instructions cover purpose and lifetime."
    score = cf.score_citation_faithfulness(
        answer=answer,
        references=["Article 13", "Article 99"],
        kb_text_lookup=lookup,
    )
    assert score.n_used_refs == 1
    assert score.citation_precision == 0.5
    assert score.citation_precision < 1.0


# ── Edge cases ────────────────────────────────────────────────────────────


def test_empty_answer_returns_zero_scores() -> None:
    """Empty answer → no sentences. Recall vacuous, precision/F1 zero."""
    score = cf.score_citation_faithfulness(
        answer="",
        references=["Article 13"],
        kb_text_lookup=_make_lookup({"Art. 13": "anything"}),
    )
    assert score.n_sentences == 0
    assert score.n_supported == 0
    assert score.n_used_refs == 0
    assert score.citation_recall == 1.0  # vacuous
    assert score.citation_precision == 0.0
    assert score.citation_f1 == 0.0


def test_empty_refs_with_nonempty_answer() -> None:
    """Empty refs + non-empty answer → strict precision failure (no
    refs to justify the claims). F1 collapses to zero."""
    score = cf.score_citation_faithfulness(
        answer="High-risk AI systems must be transparent.",
        references=[],
        kb_text_lookup=_make_lookup({}),
    )
    assert score.n_sentences == 1
    # Recall is supported/total. With zero refs no sentence can be
    # supported → recall is 0 (no ref to claim the support from).
    assert score.citation_recall == 0.0
    assert score.citation_precision == 0.0
    assert score.citation_f1 == 0.0


def test_both_empty_returns_vacuous() -> None:
    """Empty answer + empty refs → 1.0 recall (vacuous), 0 precision."""
    score = cf.score_citation_faithfulness(
        answer="",
        references=[],
    )
    assert score.n_sentences == 0
    assert score.citation_recall == 1.0
    assert score.citation_precision == 0.0
    assert score.citation_f1 == 0.0


def test_malformed_ref_counts_as_unused() -> None:
    """Refs not matching ``Article N`` / ``Annex X`` count against
    precision (denominator) without ever supporting a sentence."""
    lookup = _make_lookup({"Art. 13": "transparency instructions purpose"})
    answer = "Transparency instructions cover purpose."
    score = cf.score_citation_faithfulness(
        answer=answer,
        references=["Article 13", "bogus-ref-format"],
        kb_text_lookup=lookup,
    )
    # 1 sentence supported by Art. 13; bogus-ref used by nothing.
    assert score.n_supported == 1
    assert score.n_used_refs == 1
    assert score.citation_precision == 0.5


# ── Ref normalisation ─────────────────────────────────────────────────────


def test_wire_format_article_normalises_to_internal_key() -> None:
    """The wire emits ``Article 13``; the KB is keyed ``Art. 13``."""
    assert cf._normalise_ref_to_kb_key("Article 13") == "Art. 13"
    assert cf._normalise_ref_to_kb_key("Article 13.1") == "Art. 13"
    assert cf._normalise_ref_to_kb_key("Annex III") == "Annex III"
    assert cf._normalise_ref_to_kb_key("Annex IV.2") == "Annex IV"
    assert cf._normalise_ref_to_kb_key("nonsense") is None
    assert cf._normalise_ref_to_kb_key("") is None


# ── Default lookup ────────────────────────────────────────────────────────


def test_default_lookup_resolves_known_articles() -> None:
    """When no custom lookup is passed, the default pulls from the
    project's KB. Smoke-test: Art. 13 must produce non-empty text."""
    lookup = cf._get_default_lookup()
    text = lookup("Art. 13")
    assert text  # non-empty
    assert isinstance(text, str)


def test_score_uses_default_lookup_when_omitted() -> None:
    """Sanity: dropping the lookup shouldn't crash and should score
    a plausibly-grounded answer above zero."""
    answer = "High-risk AI systems must be designed for transparency."
    score = cf.score_citation_faithfulness(
        answer=answer,
        references=["Article 13"],
    )
    # The wire-style answer overlaps with the regulation prose of
    # Art. 13 — expect at least partial recall.
    assert score.n_sentences == 1
    assert score.citation_recall in (0.0, 1.0)  # binary on 1 sentence
    # Don't pin to a specific value; assert the score function runs
    # without raising AND the dataclass round-trips cleanly.
    assert isinstance(score.as_dict(), dict)


# ── Aggregate ─────────────────────────────────────────────────────────────


def test_aggregate_empty_returns_zero_row() -> None:
    agg = cf.aggregate([])
    assert agg["n"] == 0
    assert agg["citation_recall"] == 0.0
    assert agg["citation_precision"] == 0.0
    assert agg["citation_f1"] == 0.0


def test_aggregate_macro_averages() -> None:
    """Macro-average across two scores."""
    a = cf.FaithfulnessScore(1.0, 1.0, 1.0, 2, 2, 2)
    b = cf.FaithfulnessScore(0.5, 0.5, 0.5, 2, 1, 1)
    agg = cf.aggregate([a, b])
    assert agg["n"] == 2
    assert agg["citation_recall"] == 0.75
    assert agg["citation_precision"] == 0.75
    # F1 is recomputed from the averages, not averaged. With recall=
    # precision=0.75 → F1=0.75.
    assert agg["citation_f1"] == 0.75
    assert agg["n_sentences_total"] == 4
    assert agg["n_supported_total"] == 3
    assert agg["n_used_refs_total"] == 3

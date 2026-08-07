"""R319 — regression guards for two measurement-integrity defects.

1. THE JUDGE COULD NOT SEE THE ANSWER IT WAS JUDGING.
   Both judges rendered `r['answer'][:1400]` (and [:1200] on the citation
   axis). Measured on the july7-r309 judged corpus: mean answer length 1413.3
   chars, 50% (36/72) of rows over 1400, 58% over 1200. The judge was shown a
   mid-sentence fragment and truthfully reported that fragment looked
   incomplete -- producing FALSE "omission" verdicts on 3 of the 4 axes.
   Verified false failures: july7-327 was failed for omitting the
   profiling-always-high-risk rule, which is present verbatim at char 2007.

   These tests pin the ANSWER TAIL being visible to the judge, not the constant
   itself -- so raising the constant is fine and re-introducing any truncation
   below a realistic answer length fails loudly.

2. `_article_key` WAS NOT IDEMPOTENT FOR ANNEXES.
   The engine double-normalises (`_covered_article_keys` -> `assess_sufficiency`),
   so every Annex in the covered set silently became "" and the high-precision
   `uncovered_explicit_refs` path fired on refs that were already covered.
"""
from __future__ import annotations

import pytest

from app.engines.sufficient_context import _article_key


# ── 1. judge answer-window ───────────────────────────────────────────────

# Longer than the old 1400 cap and than the observed corpus max (4361), with a
# sentinel in the tail that only a non-truncating renderer can reach.
_TAIL = "ZZZ_TAIL_SENTINEL_ZZZ"
_LONG_ANSWER = ("Article 6(2) classifies the system as high-risk. " * 100) + _TAIL


def _row() -> dict:
    return {
        "id": "r319-probe",
        "question": "Is this system high-risk under the EU AI Act?",
        "answer": _LONG_ANSWER,
        "pred_refs": ["Article 6"],
        "gold_refs": ["Article 6"],
        "expected_keywords": ["high-risk"],
    }


def test_long_answer_is_long_enough_to_have_tripped_the_old_cap():
    """Guard the guard: the fixture must exceed the old 1400/1200 caps."""
    assert len(_LONG_ANSWER) > 4361, "fixture must exceed the observed corpus max"


@pytest.mark.parametrize("axis", ["answer_correctness", "citation_faithfulness"])
def test_grounded_judge_sees_the_answer_tail(axis):
    from evals.judge import grounded

    r = _row()
    prompt = getattr(grounded, f"render_{axis}")(r)
    assert _TAIL in prompt, (
        f"grounded.render_{axis} truncated the answer before its tail -- the "
        f"judge cannot see what it is scoring (R319)"
    )


def test_legal_v2_answer_correctness_sees_the_answer_tail():
    from evals.judge import legal_v2

    prompt = legal_v2.render_answer_correctness(_row(), {})
    assert _TAIL in prompt


def test_legal_v2_citation_faithfulness_sees_the_answer_tail():
    from evals.judge import legal_v2

    prompt = legal_v2.render_citation_faithfulness(_row(), {})
    assert _TAIL in prompt


def test_legal_v2_answer_conciseness_sees_the_answer_tail():
    from evals.judge import legal_v2

    prompt = legal_v2.render_answer_conciseness(_row())
    assert _TAIL in prompt


def test_answer_cap_clears_the_observed_corpus_max():
    from evals.judge.grounded import _ANSWER_TEXT_CAP

    # Longest answer in the july7-r309 judged corpus was 4361 chars.
    assert _ANSWER_TEXT_CAP >= 4361


# ── 2. _article_key idempotency ──────────────────────────────────────────


@pytest.mark.parametrize(
    "ref",
    ["Annex IV", "Annex I", "Annex III", "Annex 4", "Article 6", "Art. 13", "Art 113"],
)
def test_article_key_is_idempotent(ref):
    once = _article_key(ref)
    assert once, f"{ref!r} should normalise to a non-empty key"
    assert _article_key(once) == once, (
        f"_article_key is not idempotent for {ref!r}: {once!r} -> "
        f"{_article_key(once)!r}. The engine double-normalises, so a "
        f"non-idempotent key silently drops coverage (R319)."
    )


def test_annex_key_round_trip_specifically():
    """The exact regression: annexes lost their key on a second pass."""
    assert _article_key(_article_key("Annex IV")) == "annexiv"
    assert _article_key(_article_key("Annex I")) == "annexi"


@pytest.mark.parametrize(
    "junk", ["", "obligation-1234", "the provider must", "annexes generally", "annex"]
)
def test_non_reference_still_yields_empty_key(junk):
    """The conservative fix must not make free text look like a reference."""
    assert _article_key(junk) == ""

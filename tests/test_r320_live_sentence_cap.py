"""R320 — live Stage-2 sentence cap (opt-in) + Stage-2 prompt de-duplication.

Context
-------
The July-7 graded batch scored Answer-Conciseness 96.0 (easy) / 93.4 (hard) —
the ONLY official axis this system leads, i.e. the one with pure downside
risk. R308 (2026-08-03, twenty-seven days AFTER that batch) flipped
``REGENOLD_ANSWER_NO_CAP`` default ON, removing BOTH the sentence slice and
the soft char-cap loop on the live Stage-2 path. Measured on the recorded
72-row ``july7-r309-ALL`` arm, live answers are now **1.130x** the length of
the arm whose official conciseness we know.

What R320 adds is an OPT-IN third mode: apply the SENTENCE cap, skip the CHAR
cap. Measured offline at zero generation variance
(``.evalout/r320/cap_sweep2.py`` — the caps are pure route post-processing):

    uncapped (R308, today)   1.130x the July-7 graded answer length
    sentence cap 4           1.089x, 0 enumerations cut, 0 leads dropped
    + char cap (any value)   16 verdict-first LEAD sentences DROPPED

The char cap drops "the longest NON-CITE-ANCHORED sentence" first, and a
crisp verdict-first opener ("No such list exists.") is exactly that shape —
so it silently deletes the direct answer. july7-287 is the worked example.

It ships **DEFAULT OFF**: the paired judge A/B on the 21 rows the cap
actually changes returned answer_conciseness +0.095 / citation_faithfulness
+0.095 but answer_correctness **-0.143**, none significant at n=21. That is a
trade, not a win, so it is an operator opt-in pending a powered A/B.
"""

from __future__ import annotations

import pytest

from app.integrations.regenold import models as M
from app.integrations.regenold.models import (
    MAX_ANSWER_SENTENCES,
    normalise_answer_for_regenold,
)

# The cap ships DEFAULT OFF. Tests that exercise it opt in explicitly, exactly
# as an operator would.
CAP_ON = "4"


def _norm(text: str, *, live: bool, question: str = "") -> str:
    tok = M._ANSWER_NO_CAP.set(live)
    try:
        return normalise_answer_for_regenold(text, question=question)
    finally:
        M._ANSWER_NO_CAP.reset(tok)


# A 6-sentence answer whose LEAD is short and carries no citation anchor —
# precisely the shape the char-cap loop preferentially deletes.
_LEAD = "No such list exists."
_LONG_BODY = " ".join(
    f"Under Article {10 + i}, the provider shall maintain documentation "
    f"covering the relevant technical characteristics of the system in "
    f"sufficient detail for assessment number {i}."
    for i in range(1, 6)
)
_ANSWER = f"{_LEAD} {_LONG_BODY}"


class TestDefaultIsOff:
    """R320 ships opt-in: the live path must behave exactly as R308 did."""

    def test_live_path_uncapped_by_default(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.delenv("REGENOLD_LIVE_SENTENCE_CAP", raising=False)
        out = _norm(_ANSWER, live=True)
        assert len(M._split_sentences(out)) > 4, "default must remain R308-uncapped"

    def test_default_does_not_apply_char_cap(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.delenv("REGENOLD_LIVE_SENTENCE_CAP", raising=False)
        monkeypatch.setenv("REGENOLD_QA_LENGTH_CAP", "120")
        out = _norm(_ANSWER, live=True)
        assert len(out) > 120


class TestBenchPathUnchanged:
    """The deterministic bench never sets the ContextVar -> must not move.

    Verified empirically too: davidath 476/476 rows byte-identical on
    pred_answer, pred_refs and every score axis vs the r319 baseline.
    """

    def test_bench_default_is_module_constant(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.delenv("REGENOLD_LIVE_SENTENCE_CAP", raising=False)
        out = _norm(_ANSWER, live=False)
        assert len(M._split_sentences(out)) <= max(MAX_ANSWER_SENTENCES, 1)

    def test_bench_still_applies_char_cap(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_QA_LENGTH_CAP", "200")
        out = _norm(_ANSWER, live=False)
        assert len(out) < len(_ANSWER)


class TestOptInSentenceCapOnly:
    def test_opt_in_applies_sentence_cap(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", CAP_ON)
        out = _norm(_ANSWER, live=True)
        assert len(M._split_sentences(out)) <= 4

    def test_opt_in_does_not_apply_char_cap(self, monkeypatch):
        """The regression that matters: with the char cap active the loop
        deletes the verdict-first lead."""
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", CAP_ON)
        monkeypatch.setenv("REGENOLD_QA_LENGTH_CAP", "120")
        out = _norm(_ANSWER, live=True)
        assert len(out) > 120, "char cap must not run on the live Stage-2 path"

    def test_opt_in_preserves_verdict_first_lead(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", CAP_ON)
        monkeypatch.setenv("REGENOLD_QA_LENGTH_CAP", "120")
        out = _norm(_ANSWER, live=True)
        assert out.strip().lower().startswith("no such list exists")


class TestReversibility:
    def test_explicit_env_still_wins(self, monkeypatch):
        """An operator pin must override BOTH the ContextVar and the live cap."""
        monkeypatch.setenv("REGENOLD_MAX_ANSWER_SENTENCES", "2")
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", CAP_ON)
        out = _norm(_ANSWER, live=True)
        assert len(M._split_sentences(out)) <= 2

    @pytest.mark.parametrize(
        "bad", ["abc", "   x", "", "   ", "false", "no", "disabled", "4.0", "-2", "-3", "0"]
    )
    def test_unparseable_or_non_positive_cap_fails_CLOSED(self, monkeypatch, bad):
        """R321 — anything we cannot read as a positive integer means OFF.

        As shipped this failed OPEN: "" was absent from the disable-set,
        ``int("")`` raised, and the handler ENABLED the cap. Measured: ''/'  '/
        'false'/'no'/'disabled'/'four' all capped at 4, and '-2' clamped via
        ``max(1, min(12, -2))`` to a ONE-sentence wire answer. So clearing the
        Railway variable, or writing "false", silently switched on a mode whose
        own A/B measured answer_correctness -0.143 (1 up / 4 DOWN).
        """
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", bad)
        out = _norm(_ANSWER, live=True)
        uncapped = _norm(_ANSWER, live=True)  # same config; establishes the shape
        assert len(M._split_sentences(out)) == len(M._split_sentences(uncapped))
        assert len(M._split_sentences(out)) > 4, (
            f"REGENOLD_LIVE_SENTENCE_CAP={bad!r} must NOT enable the cap"
        )

    @pytest.mark.parametrize("good,expect", [("4", 4), ("2", 2), ("1", 1)])
    def test_explicit_positive_integer_still_enables_the_cap(self, monkeypatch, good, expect):
        """The opt-in must still work — the fix must not make the flag inert."""
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", good)
        out = _norm(_ANSWER, live=True)
        assert len(M._split_sentences(out)) <= expect


class TestEnumerationStillProtected:
    def test_enumerated_run_survives_the_opt_in_cap(self, monkeypatch):
        """R306 — never truncate a list the answer started.

        The shape escalation (_is_enum / _is_multi) must still run on the
        live path; a hard cap that skipped it truncated 3 inline
        enumerations on the recorded arm.
        """
        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", CAP_ON)
        q = "What practices are prohibited under Article 5?"
        enumerated = (
            "Article 5 prohibits eight practices. "
            "(a) subliminal techniques. (b) exploitation of vulnerabilities. "
            "(c) social scoring. (d) risk assessment for criminal offences. "
            "(e) untargeted scraping of facial images. "
            "(f) emotion inference in the workplace. "
            "(g) biometric categorisation. "
            "(h) real-time remote biometric identification."
        )
        out = _norm(enumerated, live=True, question=q)
        for marker in ("(a)", "(h)"):
            assert marker in out, f"enumeration truncated: {marker} missing"


class TestCoverageClauseNotDuplicated:
    def test_coverage_clause_appended_exactly_once(self):
        """R320 — a copy-paste duplication appended the 1955-char coverage
        clause TWICE (~3910 chars of the delivered budget), doubling the
        completeness pressure that drives padding on the one axis we lead.
        This one IS shipped: it is a bug, not a trade."""
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "app/engines/_graph_rag_impl.py"
        text = src.read_text(encoding="utf-8")
        # R377 — the clause is now delivered via a selector function, not a
        # constant, but the duplication guard still applies.
        assert text.count("user_message += user_answer_coverage_clause()") == 1


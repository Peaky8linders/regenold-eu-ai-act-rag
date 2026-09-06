"""R385 — the question-relevance reference prune. Built, gated, REJECTED.

WHAT IT IS
----------
The sonnet-5 judge scored the live round at answer correctness 0.870, reference
correctness 0.480 and citation faithfulness **0.960**. Those three together locate
the defect exactly: the wrong references genuinely DO support sentences in our
answer, so they are not wrong relative to the ANSWER — they are wrong relative to
the QUESTION. The answer drifts into adjacent law and the citations follow it
faithfully.

So this filter scores each emitted reference against the QUESTION, reusing the
repo's own dense index as a PRECISION filter rather than the recall filter it was
built as, and fuses that with where the answer first names the provision.

Measured separation on the 110-row live round, against the judge's labels:

    signal                            wrong refs     right refs
    rank in the question's ranking    median 17.0    median  4.0
    share in the question's top-5          17.6 %         52.8 %
    first named in the answer at      median 0.552   median 0.137

Against those labels it works: held-out reference pass 0.480 -> 0.560, in-sample
0.610 at precision 0.760, removing 30 wrong references for 6 right ones.

WHY IT DOES NOT SHIP
--------------------
It fails hard rule #8 at every threshold. Zero-variance replay over the 129
gold-bearing live probe rows:

    setting              gold_dropped_head    recall    RefConc
    OFF (baseline)                      37      82.2       54.7
    rank<8  pos<=0.50                  +19      73.1       66.7
    rank<15 pos<=0.60                   +9      77.9       62.6
    rank<30 pos<=0.80                   +3      80.8       58.1
    rank<40 pos<=0.85                   +1      81.7       56.6
    rank<80 pos<=0.95                   +1      81.7       55.2

The curve is monotone: every point of Ref Conciseness costs gold, and the
most conservative setting that still gains anything measurable already drops a
gold head. There is no operating point.

THE FINDING THAT OUTLIVES THE LEVER
-----------------------------------
The two instruments disagree about what a correct citation set IS. The official
judge calls these references over-citation; our probe gold calls the same
references required. CLAUDE.md already records why — "gold_dropped_head is
computed against our own hand-built probe gold, which is NOT minimal, so the
internal gate actively fights the official RefConc axis" — and this is the first
lever to measure the size of that conflict: 19 gold heads at the setting the
judge likes best.

**Until the gate's gold is minimal, or the evaluator's real expected sets exist,
every reference-precision lever will fail this gate by construction.** That is a
statement about the instrument, not about the lever, and it should be fixed at
the instrument.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

Q = "What are the transparency obligations for a chatbot under the EU AI Act?"
A = (
    "Article 50(1) requires providers to ensure that an AI system intended to "
    "interact directly with natural persons discloses that fact. Article 99 sets "
    "the penalties for infringement."
)
REFS = ["Article 50", "Article 99", "Annex XI"]


class TestDefaultOff:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_QREL_PRUNE", raising=False)
        from app.routes.regenold import _qrel_prune_enabled

        assert _qrel_prune_enabled() is False

    def test_is_a_strict_no_op_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_QREL_PRUNE", raising=False)
        from app.routes.regenold import _qrel_prune_references

        assert _qrel_prune_references(list(REFS), Q, A) == REFS

    @pytest.mark.parametrize("v", ["1", "true", "yes", "on"])
    def test_opt_in_values(self, monkeypatch: pytest.MonkeyPatch, v: str) -> None:
        monkeypatch.setenv("REGENOLD_QREL_PRUNE", v)
        from app.routes.regenold import _qrel_prune_enabled

        assert _qrel_prune_enabled() is True


class TestSafetyInvariants:
    """Whatever the thresholds, these must hold — they are what keep the filter
    out of the R142.1 family."""

    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REGENOLD_QREL_PRUNE", "1")
        monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
        monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")

    def test_never_returns_an_empty_list(self) -> None:
        from app.routes.regenold import _qrel_prune_references

        out = _qrel_prune_references(list(REFS), "totally unrelated question about cheese", "")
        assert out, "a precision filter must never strip the citation list to nothing"

    def test_never_adds_or_reorders(self) -> None:
        from app.routes.regenold import _qrel_prune_references

        out = _qrel_prune_references(list(REFS), Q, A)
        assert set(out) <= set(REFS), "the filter must only remove"
        assert out == [r for r in REFS if r in out], "relative order must be preserved"

    def test_a_question_named_provision_is_never_dropped(self) -> None:
        """The anchor rule. A provision the user asked about outright survives
        regardless of what either signal says."""
        from app.routes.regenold import _qrel_prune_references

        q = "What does Article 99 say about penalties?"
        out = _qrel_prune_references(["Article 99", "Annex XI"], q, "Some answer text.")
        assert "Article 99" in out

    def test_single_reference_lists_are_untouched(self) -> None:
        from app.routes.regenold import _qrel_prune_references

        assert _qrel_prune_references(["Article 6"], Q, A) == ["Article 6"]

    def test_fails_soft_when_the_index_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A precision filter must never 500 the route or silently empty a list."""
        import app.engines.turboquant_index as tq
        from app.routes.regenold import _qrel_prune_references

        def boom(*a, **k):
            raise RuntimeError("index unavailable")

        monkeypatch.setattr(tq, "dense_top_k", boom)
        assert _qrel_prune_references(list(REFS), Q, A) == REFS


class TestRegisteredAndWired:
    def test_flag_is_in_the_engine_cache_key(self) -> None:
        import inspect

        from app.routes import regenold as R

        assert "REGENOLD_QREL_PRUNE" in inspect.getsource(R._engine_cache_key)

    def test_the_pass_is_actually_called(self) -> None:
        """R329/R330/R366/R382/R383 were all levers that read correctly in the
        diff and made zero calls. Grep the call site, not the definition."""
        import inspect

        from app.routes import regenold as R

        assert inspect.getsource(R).count("_qrel_prune_references(") >= 2

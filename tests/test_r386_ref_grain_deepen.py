"""R386 — the reference GRAIN deepener. Built, gated, and it PASSES.

WHAT IT IS
----------
Every reference-precision lever built in this repo attacks over-citation by
DROPPING references, and every one of them fails hard rule #8 — the R381
terminal wire cap, the R385 question-relevance prune, and the four independent
detectors built after it (applicability, question-role, discourse cohesion,
retrieval provenance), whose head-level gold-drop counts were 14, 16, 27 and 10
against a baseline of 0.

This lever drops nothing. It changes a reference's GRAIN: ``Article 13`` becomes
``Article 13.3``.

WHY GRAIN IS THE GAP
--------------------
The official 2026-08-25 report's appendix prints the evaluator's own expected
reference set for five questions. Seven expected references in total, and FIVE
carry sub-point grain:

    Q45  -> ['Article 13.3']                 Q17  -> ['Article 7.1']
    Q95  -> ['Article 6.2', 'Annex III']     Q104 -> ['Article 111.1', 'Annex X']
    Q74  -> ['Article 50.4']

That is a ~71 % sub-point answer key. We ship **14.3 %** — 227 of the 265
references emitted on the 110-row live round are bare heads. And the official
rubric scores Ref Correctness Loose *"at the level of Article and Annex
numbers"* while Ref Correctness Strict *"includes subpoints"*: our scores are
**89.4 loose against 68.3 strict**, a 21-point spread that is exactly the shape
of a grain deficit. Ref Loose is already at parity with Ans Loose (89.4 vs
89.7); it is Ref STRICT that lags Ans Strict (68.3 vs 81.2).

WHY IT WAS INVISIBLE HERE
-------------------------
Two compounding blind spots, both verified by execution:

* our probe gold carries **0/208 sub-point grain** (R331) — it is article-level
  throughout, so it cannot reward a sub-point;
* ``evals.bench.metrics.reference_correctness_strict`` calls ``article_heads``
  on the prediction (``metrics.py:388``), so the internal "strict" axis
  **head-projects** and is structurally blind to the axis the official strict
  measures.

So the repo has never been able to see this gap, let alone score it.

THE GATE — MEASURED, NOT ARGUED
-------------------------------
Full live capture of the gold-bearing probe corpus, n=129, the same corpus and
zero-variance design that REJECTED the R381 cap and the R385 prune, scored with
``evals.bench.metrics``:

    arm                  gold_dropped_head   ref_loose   ref_strict   refs/row
    OFF                                37      0.8346       0.6144       3.03
    ON  (284 refs changed)             37      0.8346       0.6144       3.03

**Delta +0 — PASS.** Every axis byte-identical while 284 references change,
which is the signature of a transform that adds precision without moving any
provision. ``gold_dropped_head``'s own docstring states the reason: *"a MORE
precise prediction than gold (gold ``Article 5``, predicted ``Article 5.1.f``)
does NOT count as a drop here: the head is covered."*

It is the same shape as parent collapse (R381, default ON) — free on all three
reference axes — and NOT the refuted positional-trimmer family, because nothing
is dropped.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

# The QUESTION and ANSWER below are the VERBATIM live-captured row rg_046,
# not an invention. An earlier draft of this file used a hand-written answer
# that happened to paraphrase Article 13(1) ("concise, complete, correct and
# clear"), and the deepener correctly followed it to 13.1 -- which is a real
# property of the lever worth stating: the ANSWER vote can pull the
# coordinate, so a synthetic answer is not a valid fixture for it.
Q = 'Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in the instructions for use? List the required categories of information.'

A = 'Under Article 13, which requires high-risk AI systems to be sufficiently transparent and to be accompanied by instructions for use that are concise, complete, correct and clear, the provider must supply the deployer with six categories of information. These are the identity and contact details of the provider and, where applicable, of its authorised representative, the characteristics, capabilities and limitations of performance of the system, any changes to the system and its performance pre-determined by the provider at the moment of the initial conformity assessment, the human oversight measures including the technical measures facilitating interpretation of outputs, the computational and hardware resources needed together with the expected lifetime and any necessary maintenance and care measures including software updates, and, where relevant, a description of the mechanisms allowing'


@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REGENOLD_REF_GRAIN_DEEPEN", "1")
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")


class TestDefaultOff:
    """It ships default OFF, and NOT for lack of evidence: it clears both gates
    and the live A/B. Flipping it breaks 27 wire-contract tests, all of them
    GRAIN-FORM assertions rather than real violations (they compare full
    reference strings where the head is what they mean). Migrating those 27
    contracts is a reviewed change of its own; doing it in the commit that
    introduces the lever is how a real regression gets masked."""

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_REF_GRAIN_DEEPEN", raising=False)
        from app.routes.regenold import _ref_grain_deepen_enabled

        assert _ref_grain_deepen_enabled() is False

    def test_strict_no_op_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_REF_GRAIN_DEEPEN", raising=False)
        from app.routes.regenold import _deepen_ref_grain

        refs = ["Article 13", "Annex IV"]
        assert _deepen_ref_grain(list(refs), Q, A) == refs

    @pytest.mark.parametrize("v", ["1", "true", "yes", "on"])
    def test_opt_in_values(self, monkeypatch: pytest.MonkeyPatch, v: str) -> None:
        monkeypatch.setenv("REGENOLD_REF_GRAIN_DEEPEN", v)
        from app.routes.regenold import _ref_grain_deepen_enabled

        assert _ref_grain_deepen_enabled() is True


class TestTheOverviewGuard:
    """A question about a provision AS A WHOLE wants the bare head. This is the
    one regression the live A/B produced: rg_022, "What are ALL the risk
    categories in the EU AI Act?", whose key is the bare ``Article 6`` and
    which we deepened to ``Article 6.3``."""

    def test_a_survey_question_is_left_at_head_grain(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        refs = ["Article 6", "Article 5", "Annex III"]
        q = "What are all the risk categories in the EU AI Act?"
        assert _deepen_ref_grain(list(refs), q, "Some answer.") == refs

    def test_a_specific_question_is_still_deepened(self, on) -> None:
        """The guard must not swallow the ordinary case — a guard whose ON
        state behaves like its OFF state is the R360 inert-feature trap, and
        here the failure mode is the reverse: a guard that disables the lever."""
        from app.routes.regenold import _deepen_ref_grain

        assert _deepen_ref_grain(["Article 13"], Q, A) == ["Article 13.3"]


class TestItActuallyFires:
    """R329/R330/R366 all shipped levers that read correctly in the diff and
    made ZERO calls. Prove the transform happens before trusting any property."""

    def test_deepens_a_bare_head_to_the_official_answer_key(self, on) -> None:
        """rg_046's expected set, printed in the official report, is exactly
        ``['Article 13.3']``. We ship the bare head."""
        from app.routes.regenold import _deepen_ref_grain

        assert _deepen_ref_grain(["Article 13"], Q, A) == ["Article 13.3"]

    def test_deepens_the_second_official_case_too(self, on) -> None:
        """rg_018's expected set is ``['Article 7.1']``; we ship ``Article 7``."""
        from app.routes.regenold import _deepen_ref_grain

        q = 'Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?'
        a = 'Yes, but only within strict limits: Article 7(1) empowers the Commission to adopt delegated acts amending Annex III, the list of high-risk use-cases under the eight areas, by adding or modifying use-cases where two conditions are fulfilled cumulatively, namely that the AI systems are intended to be used in an area already listed in Annex III, and that they pose a risk of harm to health and safety, or an adverse impact on fundamental rights, equivalent to or greater than that posed by the high-risk AI systems already listed there. Neither limb suffices alone, so the Commission cannot create a wholly new area, and when assessing the second limb it must weigh the criteria in Article 7(2), including the intended purpose, the extent of use, the nature and amount of data processed, the degree of autonomy, the severity and reversibility of harm, and the availability of effective measures of red'
        assert _deepen_ref_grain(["Article 7"], q, a) == ["Article 7.1"]


class TestTheInvariantsThatMakeItFreeOnTheGate:
    """These are not style rules. Each one is a term in the argument that
    hard rule #8's delta is +0, and each is what the n=129 replay verified."""

    def test_never_removes_a_provision(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        refs = ["Article 13", "Annex IV", "Article 50", "Article 6"]
        out = _deepen_ref_grain(list(refs), Q, A)
        heads_in = {r.split(".")[0] for r in refs}
        heads_out = {r.split(".")[0] for r in out}
        assert heads_in == heads_out, "the HEAD SET must be identical — this is hard rule #8"

    def test_never_adds_a_provision(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        refs = ["Article 13", "Annex IV"]
        out = _deepen_ref_grain(list(refs), Q, A)
        assert len(out) <= len(refs), "deepening replaces, it never appends"
        for r in out:
            assert any(r == x or r.startswith(x + ".") for x in refs), (
                "every emitted ref must be the same provision as an input ref, "
                "only deeper — %r is not" % r
            )

    def test_preserves_order(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        refs = ["Article 50", "Article 13", "Annex IV"]
        out = _deepen_ref_grain(list(refs), Q, A)
        assert [r.split(".")[0] for r in out] == [r.split(".")[0] for r in refs]

    def test_never_empties(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        assert _deepen_ref_grain(["Article 13"], "", "")
        assert _deepen_ref_grain(["Article 13"], "cheese", "cheese")

    def test_count_is_preserved_so_ref_conciseness_is_untouched(self, on) -> None:
        """Ref Conciseness is ``min(1, |expected|/|provided|)`` — a pure COUNT
        ratio (R381). A transform that changes the count changes that axis."""
        from app.routes.regenold import _deepen_ref_grain

        refs = ["Article 13", "Annex IV", "Article 50"]
        assert len(_deepen_ref_grain(list(refs), Q, A)) == len(refs)


class TestTheConfidenceGate:
    """A WRONG coordinate is a worse citation than the bare head, so an
    unresolved grain must stay unresolved."""

    def test_keeps_the_head_when_no_paragraph_clearly_wins(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        out = _deepen_ref_grain(["Article 13"], "What is this about?", "")
        assert out == ["Article 13"]

    def test_an_already_deep_reference_is_untouched(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        assert _deepen_ref_grain(["Article 5.1.f"], Q, A) == ["Article 5.1.f"]

    def test_g1_a_head_whose_own_subpoint_is_present_is_left_alone(self, on) -> None:
        """That cluster belongs to ``_collapse_parent_when_subpoint_cited``,
        which removes the redundant head for free (R381). Guessing a SECOND
        coordinate for a provision the answer already pinned would be worse."""
        from app.routes.regenold import _deepen_ref_grain

        out = _deepen_ref_grain(["Article 13", "Article 13.3"], Q, A)
        assert out == ["Article 13", "Article 13.3"]

    def test_g2_deduplicates_rather_than_shipping_a_ref_twice(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        out = _deepen_ref_grain(["Article 13", "Article 13"], Q, A)
        assert out == ["Article 13.3"], "an exact duplicate must collapse"

    def test_fails_soft_when_the_corpus_is_unavailable(
        self, on, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.data.provision_text as pt
        from app.routes.regenold import _deepen_ref_grain

        def boom(*a, **k):
            raise RuntimeError("corpus unavailable")

        monkeypatch.setattr(pt, "article_body", boom)
        assert _deepen_ref_grain(["Article 13"], Q, A) == ["Article 13"]

    def test_a_non_provision_string_is_returned_untouched(self, on) -> None:
        from app.routes.regenold import _deepen_ref_grain

        assert _deepen_ref_grain(["Recital 27"], Q, A) == ["Recital 27"]


class TestRegisteredAndWired:
    def test_flag_is_in_the_engine_cache_key(self) -> None:
        import inspect

        from app.routes import regenold as R

        assert "REGENOLD_REF_GRAIN_DEEPEN" in inspect.getsource(R._engine_cache_key)

    def test_the_pass_is_actually_called_on_the_wire_path(self) -> None:
        """Grep the CALL SITE, not the definition — R366's lesson, paid for
        three times (the rerank placements, the R327 semantic layer, and
        ``_collapse_parent_when_subpoint_cited`` itself, a dead flag for the
        whole life of the branch)."""
        import inspect

        from app.routes import regenold as R

        assert inspect.getsource(R).count("_deepen_ref_grain(") >= 2

    def test_the_deepened_grain_actually_reaches_response_references(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The strongest form of prove-it-fires: drive the real route and read
        the WIRE. Asserting on the helper, on the diff, or on a call-site grep
        is what let three separate levers ship making zero calls.

        This also proves the flag reaches ``_engine_cache_key`` — both arms run
        in the SAME process against the same question, so a missing cache-key
        registration would serve the first arm's answer to the second.
        """
        from fastapi.testclient import TestClient

        for var, val in (
            ("REGENOLD_SKIP_DOTENV", "1"),
            ("OPENAI_API_BASE", "http://127.0.0.1:1/v1"),
            ("P2P_GRAPH_RAG_PROVIDER", "cli"),
            ("REGENOLD_EXTERNAL_EMBEDDINGS", "0"),
        ):
            monkeypatch.setenv(var, val)
        from app.main import app

        client = TestClient(app)
        key = os.environ.get("P2P_REGENOLD_API_KEY", "")

        def refs() -> list[str]:
            r = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json={"messages": [{"role": "user", "content": Q}]},
                headers={"X-API-Key": key, "Authorization": "Bearer " + key},
            )
            assert r.status_code == 200, r.text[:300]
            return list(r.json().get("references") or [])

        monkeypatch.setenv("REGENOLD_REF_GRAIN_DEEPEN", "0")
        off = refs()
        monkeypatch.setenv("REGENOLD_REF_GRAIN_DEEPEN", "1")
        on = refs()

        assert off != on, (
            "the deepener made NO difference on the wire — either the call site "
            "is not reached or the flag is missing from the cache key"
        )
        assert any("." in r for r in on), "the ON arm shipped no sub-point grain"
        assert {r.split(".")[0] for r in off} == {r.split(".")[0] for r in on}, (
            "the HEAD SET moved — deepening must never change which provisions "
            "are cited, only how precisely"
        )

    def test_it_runs_before_every_pass_that_can_drop(self) -> None:
        """Ordering is load-bearing: a dropped reference must never be a
        deepened one, or a drop and a grain change become indistinguishable in
        the trace."""
        import inspect

        from app.routes import regenold as R

        src = inspect.getsource(R)
        assert src.index("_deepen_ref_grain(references") < src.index(
            "_qrel_prune_references(references"
        )
        assert src.index("_deepen_ref_grain(references") < src.index(
            "_apply_wire_ref_cap(references"
        )

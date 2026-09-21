"""R429 — the wire coordinate must be COMPLETED to the grain the prose names.

THE DEFICIT. Of the 207 gold sub-point expectations the engine misses on the
recorded hard board, 63 have their parent on the wire but only at a shallower
grain: ``Annex IV.1`` shipped where the gold key is ``Annex IV.1.e``. R425
deliberately abstained on that shape and said why — *"a prefix means depth, not
substitution ... rewriting it would replace a graded coordinate with a deeper one
the evaluator may not key on."*

THAT PREMISE IS FALSE, and the rubric says so in its own source:

    def _is_descendant(pred: str, expected: str) -> bool:
        return pred == expected or pred.startswith(expected + ".")

A prediction STRICTLY MORE PRECISE than the key satisfies the key. So completing
a wire coordinate to a deeper coordinate of the SAME limb is MONOTONE on all
three reference axes — Ref. Strict can only gain a satisfied expectation, Ref.
Loose is scored through ``ref_head`` and the parent never changes, and Ref.
Conciseness is a pure COUNT ratio over a 1:1 in-place rewrite. ``NotSwapped``
below pins that a completion never becomes a substitution.

Measured on 477 recorded hard draws with gold refs and a landed Stage-2
(``docs/measurements/r429/wire_depth_probe.py``, real ``evals.official.rubric``):
Ref. Strict 65.55 -> 72.68 (**+7.13 pp**), Ref. Loose and Ref. Conciseness
byte-identical, count and folded-head-set violations 0, and 0 rows where any
expectation went met -> unmet. That is why the default is ON.
"""

from __future__ import annotations

import inspect
import os
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from app.config import settings  # noqa: E402
from app.data.provision_coordinates import coordinate_exists  # noqa: E402
from app.main import app  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.routes import regenold as R  # noqa: E402
from app.routes.regenold import (  # noqa: E402
    _grain_complete,
    _grain_relation,
    _ground_wire_depth_enabled,
    _ground_wire_subpoints,
)
from evals.official.rubric import (  # noqa: E402
    ref_head,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

FLAG = "REGENOLD_GROUND_WIRE_DEPTH"
_KEY = "regenold-r429-eval-key"


# -- the gate ------------------------------------------------------------------


def test_the_gate_is_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FLAG, raising=False)
    assert _ground_wire_depth_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF"])
def test_an_explicit_falsy_value_turns_it_off(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(FLAG, value)
    assert _ground_wire_depth_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "", "garbage"])
def test_a_blank_or_unexpected_value_keeps_the_on_behaviour(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Deny-list semantics for a default-ON gate — the R379 P2-7 defect."""
    monkeypatch.setenv(FLAG, value)
    assert _ground_wire_depth_enabled() is True


def test_the_flag_is_in_the_engine_cache_key() -> None:
    """It rewrites the emitted references, so it must not share a cache entry."""
    assert FLAG in inspect.getsource(R._engine_cache_key)


def test_the_question_is_an_optional_parameter() -> None:
    """Existing 2-arg callers (probes, tests) must keep working unchanged."""
    params = inspect.signature(_ground_wire_subpoints).parameters
    assert params["question"].default == ""


# -- the relation --------------------------------------------------------------


def test_the_four_readings_of_a_wire_coordinate() -> None:
    assert _grain_relation(("1", "h"), ("1", "h")) == "same"
    # The wire is the SAME limb at a coarser grain: the R429 population.
    assert _grain_relation(("3",), ("3", "b")) == "coarser"
    assert _grain_relation(("3",), ("3", "b", "i")) == "coarser"
    # The wire is already the finer of the two: nothing to complete.
    assert _grain_relation(("3", "b"), ("3",)) == "finer"
    # Different limbs: the R425 substitution population.
    assert _grain_relation(("2",), ("3",)) == "sibling"
    assert _grain_relation(("1",), ("10",)) == "sibling"


# -- the completion ------------------------------------------------------------


def test_a_shallower_wire_coordinate_is_completed_to_the_prose_grain() -> None:
    """The Annex IV.1 / Annex IV.1.e shape, on the real coordinate registry."""
    assert coordinate_exists("Annex IV.1.e"), "fixture assumption broke"
    assert _ground_wire_subpoints(
        "Annex IV.1.e sets out the hardware specifications.", ["Annex IV.1"]
    ) == ["Annex IV.1.e"]


def test_the_completion_reaches_the_full_depth_the_prose_names() -> None:
    """Not one step: the deepest coordinate the prose actually uses."""
    assert _ground_wire_subpoints(
        "Article 13(3)(b)(i) requires the instructions to state the characteristics.",
        ["Article 13.3"],
    ) == ["Article 13.3.b.i"]


def test_the_dotted_and_parenthesised_prose_forms_both_complete() -> None:
    paren = _ground_wire_subpoints("Article 13(3)(b) applies.", ["Article 13.3"])
    dotted = _ground_wire_subpoints("Article 13.3.b applies.", ["Article 13.3"])
    assert paren == dotted == ["Article 13.3.b"]


def test_a_wire_coordinate_already_finer_than_the_prose_is_kept() -> None:
    """Completing downward is the whole job; there is nothing to complete to."""
    refs = ["Article 13.3.b"]
    assert _ground_wire_subpoints("Article 13(3) covers instructions.", refs) == refs


def test_a_bare_head_is_left_to_the_deepener() -> None:
    """Turning a head into a leaf is R386/R133's remit, not this pass's."""
    refs = ["Article 13"]
    assert _ground_wire_subpoints("Article 13.3.b requires instructions.", refs) == refs


def test_a_coordinate_the_regulation_lacks_is_never_minted() -> None:
    assert not coordinate_exists("Article 6.9.z"), "fixture assumption broke"
    refs = ["Article 6.9"]
    assert _ground_wire_subpoints(
        "Article 6(9)(z) would be the clause.", refs
    ) == refs


class TestCompletionIsNeverASwap:
    """R425's contract, kept: a deeper coordinate of the SAME limb is not a swap.

    The prose here names BOTH a sibling limb and a deeper coordinate of the wire's
    own limb. The sibling is a substitution the pass must not make, and the
    completion it must make is the one on its own limb.
    """

    def test_a_named_sibling_does_not_win_over_the_same_limb(self) -> None:
        answer = (
            "Article 6.3 provides a derogation, while Article 6.1.b sets out "
            "the product route."
        )
        assert _ground_wire_subpoints(answer, ["Article 6.1"]) == ["Article 6.1.b"]

    def test_the_r425_substitution_still_fires_when_the_limb_is_unnamed(self) -> None:
        out = _ground_wire_subpoints(
            "Article 6(3) sets out the derogation.", ["Article 6.2", "Annex I"]
        )
        assert out == ["Article 6.3", "Annex I"]


class TestTheTieBreak:
    """Several prose-named descendants compete: the ANSWER decides.

    Free either way on the graded axes — every rival is a descendant of the
    coordinate it replaces — so this chooses the RIVAL most likely to be the one
    the gold keys on, by the R425 doctrine (the wire follows the answer's prose).
    On the board's 18 deciding cases: answer overlap 18/18, question overlap
    13/18, prose order 13/18, lexicographic-first 3/18.
    """

    _ANSWER = (
        "A GPAI provider's duties under Article 53(1) include both limbs: "
        "Article 53.1.a covers the technical documentation of the model, while "
        "Article 53.1.b requires it to draw up, keep up to date and make "
        "available information and documentation to providers of AI systems who "
        "intend to integrate the model."
    )

    def test_the_rival_the_answer_discusses_wins(self) -> None:
        """The answer quotes 53.1(b)'s substance, so 53.1(b) is the completion."""
        assert _ground_wire_subpoints(self._ANSWER, ["Article 53.1"]) == ["Article 53.1.b"]

    def test_the_choice_is_total_and_deterministic(self) -> None:
        picks = {
            tuple(_ground_wire_subpoints(self._ANSWER, ["Article 53.1"]))
            for _ in range(5)
        }
        assert len(picks) == 1, f"a tie-break must be stable, got {picks}"

    def test_a_single_candidate_needs_no_judgement(self) -> None:
        got = _grain_complete(
            [((("1", "b")), "Article 6.1.b")], "", ""
        )
        assert got[1] == "Article 6.1.b"

    def test_the_deeper_rival_wins_because_depth_dominates(self) -> None:
        """A deeper prediction satisfies its ancestors too (rubric._is_descendant)."""
        got = _grain_complete(
            [((("1", "b")), "Article 6.1.b"), ((("1", "b", "i")), "Article 6.1.b.i")],
            "",
            "",
        )
        assert got[1] == "Article 6.1.b.i"


# -- the safety property, against the real rubric -------------------------------


#: (answer, wire, gold expected refs). Realistic shapes from the recorded board.
_MONOTONE_CASES: list[tuple[str, list[str], list[str]]] = [
    # the plain depth completion
    (
        "Annex IV.1.e sets out the hardware specifications.",
        ["Annex IV.1", "Article 11"],
        ["Annex IV.1.e"],
    ),
    # a completion whose gold keys on the SHALLOWER coordinate: must not regress
    (
        "Article 13(3)(b) requires instructions for use.",
        ["Article 13.3"],
        ["Article 13.3"],
    ),
    # a competing sibling the prose also names
    (
        "Article 6.3 is the derogation while Article 6.1.b is the product route.",
        ["Article 6.1"],
        ["Article 6.1.b", "Article 6.3"],
    ),
    # two rivals, gold on one
    (
        "Article 53.1.a covers documentation; Article 53.1.b requires information "
        "to be made available to providers of AI systems who intend to integrate "
        "the model.",
        ["Article 53.1", "Annex XII.1"],
        ["Article 53.1.b"],
    ),
    # a head and an unrelated ref are not the pass's business
    (
        "Article 1.1 sets the objective.",
        ["Article 1", "Article 99"],
        ["Article 1.1"],
    ),
]


@pytest.mark.parametrize(("answer", "refs", "gold"), _MONOTONE_CASES)
def test_the_rewrite_is_monotone_and_free_on_the_real_rubric(
    monkeypatch: pytest.MonkeyPatch, answer: str, refs: list[str], gold: list[str]
) -> None:
    """The whole safety argument, asserted rather than claimed (Hard Rule #8)."""
    monkeypatch.setenv(FLAG, "0")
    off = _ground_wire_subpoints(answer, list(refs))
    monkeypatch.delenv(FLAG, raising=False)
    on = _ground_wire_subpoints(answer, list(refs))

    s_off = reference_correctness_strict(off, gold)
    s_on = reference_correctness_strict(on, gold)
    assert s_on >= s_off, f"Ref. Strict regressed: {s_off} -> {s_on} ({off} -> {on})"
    assert reference_correctness_loose(on, gold) == reference_correctness_loose(off, gold)
    assert reference_conciseness(on, gold) == reference_conciseness(off, gold)
    assert len(on) == len(off), "the reference count must be invariant"
    assert [ref_head(r) for r in on] == [ref_head(r) for r in off], (
        "the folded head set must be bit-identical"
    )
    assert len(set(on)) == len(on), f"a duplicate reference reached the wire: {on}"


def test_the_lever_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """``=0`` restores the R425 abstention — the arm the gate measures against."""
    monkeypatch.setenv(FLAG, "0")
    refs = ["Article 13.3"]
    assert (
        _ground_wire_subpoints("Article 13(3)(b) requires instructions.", refs) == refs
    )


# -- fail-soft -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "refs"),
    [
        ("", ["Article 13.3"]),
        ("Article 13.3.b applies.", []),
        ("No provisions named here.", ["Article 13.3"]),
    ],
)
def test_a_missing_input_is_a_strict_no_op(answer: str, refs: list[str]) -> None:
    assert _ground_wire_subpoints(answer, refs) == refs


def test_garbage_input_never_raises() -> None:
    assert _ground_wire_subpoints(None, ["Article 13.3"]) == ["Article 13.3"]  # type: ignore[arg-type]
    assert _ground_wire_subpoints("Article 13(3)(b) applies.", ["!!", "Article 13"]) == [
        "!!",
        "Article 13",
    ]


def test_an_unusable_tie_break_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A raising text lookup must fall back, not propagate into the route."""
    import app.data.provision_text as pt

    monkeypatch.setattr(pt, "get_provision_text", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    got = _ground_wire_subpoints(
        "Article 53.1.a covers documentation; Article 53.1.b requires information.",
        ["Article 53.1"],
    )
    assert got in (["Article 53.1.a"], ["Article 53.1.b"]), got


# -- the live route ------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001 — never block a test on cleanup
        pass


@pytest.fixture
def _client():
    prev = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_KEY)
    try:
        with TestClient(app, headers={"X-Regenold-Api-Key": _KEY}) as c:
            yield c
    finally:
        settings.regenold.api_key = prev


def _ask(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    answer: str,
    question: str,
) -> dict[str, Any]:
    """One real route request with a scripted LANDED Stage-2 (the R425 pattern)."""
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            )
        )
        stack.enter_context(
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                side_effect=lambda *a, **kw: answer,
            )
        )
        r = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": question}],
        )
    assert r.status_code == 200, r.text
    return r.json()


class TestTheRouteWiresTheQuestionThrough:
    def test_the_pass_receives_the_asked_question(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The third argument is the live question — the tie-break reads it."""
        seen: list[str] = []

        def spy(_answer: str, refs: list[str], question: str = "") -> list[str]:
            seen.append(question)
            return list(refs)

        monkeypatch.setattr("app.routes.regenold._ground_wire_subpoints", spy)
        q = "What documentation must a provider of a high-risk AI system draw up?"
        _ask(_client, monkeypatch, answer="Article 11 requires Annex IV documentation.", question=q)
        assert seen, (
            "the call site was never reached with a landed Stage-2 answer — the R329 "
            "zero-calls failure"
        )
        assert any(s.strip() == q for s in seen), (
            f"the pass must see the live question, got {seen!r}"
        )

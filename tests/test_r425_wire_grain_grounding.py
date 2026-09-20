"""R425 — the wire grain must be grounded in the answer's OWN prose.

THE DEFECT. The official evaluator grades Ref. Correctness (Strict) off the
``references`` field we ship, and the route's contract is that the wire is
recomputed from the final Stage-2 prose. But R133's
``_surface_prose_subpoints`` only ADDS a prose-named leaf when the **bare parent**
is on the list, so a list that already carries a SIBLING limb never receives the
grounded one and the ungrounded limb ships:

    rg_100  answer says "Article 6(3)"  ·  wire recorded "Article 6.2"
    rg_067  answer says "Article 3(64)" ·  wire recorded "Article 3.65"
    rg_103  answer says "Article 3(60)" ·  wire recorded "Article 3.46"

``_ground_wire_subpoints`` rewrites the wire limb in place onto the limb the prose
names. The direction is measured, not preferred: over the R424 gate's six
checkpoints (``docs/measurements/r425``) the wire limb is the gold one in **0** of
106 substitutions and the prose-named limb is gold in **15**, which moves the exact
Ref. Strict mean +0.62 pp with Ref. Loose and Ref. Conciseness unmoved.

WHY IT CANNOT TRIP HARD RULE #8. The rewrite stays inside the SAME parent, so the
folded head set is bit-identical before and after, and it is 1:1 in place, so the
reference COUNT is invariant — asserted both ways below rather than argued.

The route-level cases drive the REAL route with a scripted Stage-2 answer, so
``_stage2_landed`` is true and the pass sees the prose the model actually
produced. They assert behaviour at the wire, because R329/R330/R366/R397 all
shipped levers that read correctly in the diff and made zero calls.
"""

from __future__ import annotations

import inspect
import json
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
    _grain_compatible,
    _ground_wire_subpoints,
    _ground_wire_subpoints_enabled,
    _leaf_coordinate,
    _prose_named_subpoints,
)

_KEY = "regenold-r425-eval-key"
FLAG = "REGENOLD_GROUND_WIRE_SUBPOINTS"

#: A deployer question whose offline wire carries ``Article 6.2`` — i.e. the
#: exact shape of the defect, on a fixture that stays in-repo.
_Q = "What must a deployer of a high-risk recruitment AI system do?"
#: The scripted Stage-2 prose names ``Article 6(3)``: a DIFFERENT limb of the same
#: parent the wire carries. This is the `rg_100` shape, reproduced deterministically.
_ANSWER = (
    "A deployer of a high-risk recruitment AI system must comply with Article 26 "
    "duties, and where it considers a system high-risk under Article 6(3) it must "
    "document that assessment. Serious incidents are reported under Article 73."
)


# -- the gate -----------------------------------------------------------------


def test_the_gate_is_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FLAG, raising=False)
    assert _ground_wire_subpoints_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF"])
def test_an_explicit_falsy_value_turns_it_off(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(FLAG, value)
    assert _ground_wire_subpoints_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "", "garbage"])
def test_a_blank_or_unexpected_value_keeps_the_on_behaviour(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Deny-list semantics for a default-ON gate — the R379 P2-7 defect."""
    monkeypatch.setenv(FLAG, value)
    assert _ground_wire_subpoints_enabled() is True


def test_the_flag_is_in_the_engine_cache_key() -> None:
    """It rewrites the emitted references, so it must not share a cache entry."""
    assert FLAG in inspect.getsource(R._engine_cache_key)


# -- coordinates --------------------------------------------------------------


def test_a_leaf_coordinate_is_parent_keyed_and_alnum_split() -> None:
    assert _leaf_coordinate("Article 5.1.h") == ("article 5", ("1", "h"))
    assert _leaf_coordinate("Article 5.1h") == ("article 5", ("1", "h"))
    assert _leaf_coordinate("Annex III.7.b") == ("annex iii", ("7", "b"))
    # A bare head has no coordinate: it is the ADD case, which belongs to R133.
    assert _leaf_coordinate("Article 6") is None
    assert _leaf_coordinate("not a reference") is None


def test_a_prefix_is_a_grain_difference_and_not_a_substitution() -> None:
    assert _grain_compatible(("3",), ("3", "b"))
    assert _grain_compatible(("3", "b"), ("3",))
    assert _grain_compatible(("1", "h"), ("1", "h"))
    # Different limbs are NOT compatible, and `6.1` is not a prefix of `6.10`.
    assert not _grain_compatible(("2",), ("3",))
    assert not _grain_compatible(("1",), ("10",))


def test_the_prose_miner_reads_both_citation_forms() -> None:
    paren = _prose_named_subpoints("Article 6(3) applies to the case.")
    assert paren == {"article 6": ["Article 6.3"]}
    dotted = _prose_named_subpoints("See Article 6.3 for the derogation.")
    assert dotted == {"article 6": ["Article 6.3"]}
    annex = _prose_named_subpoints("Annex III point 7(c) lists it.")
    assert annex == {"annex iii": ["Annex III.7.c"]}
    assert _prose_named_subpoints("No provisions named here.") == {}


# -- the rewrite --------------------------------------------------------------


def test_a_substituted_limb_is_rewritten_to_the_prose_named_one() -> None:
    """The `rg_100` shape: the answer names 6(3), the wire carried 6.2."""
    out = _ground_wire_subpoints(
        "Article 6(3) sets out the derogation.", ["Article 6.2", "Annex I"]
    )
    assert out == ["Article 6.3", "Annex I"]


def test_the_dotted_prose_form_grounds_the_wire_the_same_way() -> None:
    out = _ground_wire_subpoints("Under Article 3.64 a provider is defined.", ["Article 3.65"])
    assert out == ["Article 3.64"]


def test_an_annex_limb_is_grounded() -> None:
    out = _ground_wire_subpoints("Annex III point 7(c) lists the use case.", ["Annex III.7.b"])
    assert out == ["Annex III.7.c"]


def test_a_grain_depth_difference_is_left_alone() -> None:
    """Prose names the SAME limb at a deeper grain: that is depth, not a swap."""
    refs = ["Article 13.3"]
    assert _ground_wire_subpoints("Article 13(3)(b) requires instructions.", refs) == refs


def test_the_two_spellings_of_a_sub_letter_are_one_coordinate() -> None:
    """The wire dots the sub-letter; the prose parenthesises it."""
    refs = ["Article 5.1.h"]
    assert _ground_wire_subpoints("Article 5(1)(h) is prohibited.", refs) == refs


def test_a_parent_the_prose_does_not_sub_point_is_left_alone() -> None:
    """An ordinary additional citation is not the defect and is not touched."""
    refs = ["Article 6.2", "Article 99"]
    assert _ground_wire_subpoints("Article 6 applies to the system.", refs) == refs


def test_a_grounded_limb_already_on_the_wire_is_never_dropped() -> None:
    """Replacing would duplicate and dropping would change the count: leave it.

    This is deliberately NOT in scope. Removing an ungrounded sibling that sits
    beside a grounded one moves Ref. Conciseness, which needs its own gate.
    """
    refs = ["Article 6.1", "Article 6.2"]
    assert _ground_wire_subpoints("Article 6(1) classifies it as high-risk.", refs) == refs


def test_a_non_existent_coordinate_is_never_minted() -> None:
    """The pass must not trade a real coordinate for one the Regulation lacks."""
    assert not coordinate_exists("Article 6.9"), "fixture assumption broke"
    refs = ["Article 6.2"]
    assert _ground_wire_subpoints("Article 6(9) would be the clause.", refs) == refs


def test_a_bare_head_is_not_rewritten() -> None:
    """Turning a head into a leaf is R133's job, not this pass's."""
    refs = ["Article 6"]
    assert _ground_wire_subpoints("Article 6(3) sets out the derogation.", refs) == refs


def test_the_rewrite_is_in_place_count_neutral_and_head_preserving() -> None:
    """The whole safety argument, asserted rather than claimed (Hard Rule #8)."""
    refs = ["Annex I", "Article 6.2", "Article 50.4", "Article 12"]
    out = _ground_wire_subpoints("Article 6(3) and Article 50(1) apply.", refs)
    assert len(out) == len(refs), "the reference count must be invariant"
    assert [r.split(".")[0] for r in out] == [r.split(".")[0] for r in refs], (
        "the folded head set must be bit-identical"
    )
    assert out[0] == "Annex I" and out[3] == "Article 12", "order must be preserved"


def test_two_refs_of_the_same_parent_cannot_land_on_one_limb() -> None:
    """A rewrite must never duplicate: the second holder of a parent is skipped."""
    refs = ["Article 6.2", "Article 6.1"]
    out = _ground_wire_subpoints("Article 6(3) sets out the derogation.", refs)
    assert len(set(out)) == len(out), f"duplicate reference on the wire: {out}"


@pytest.mark.parametrize(
    ("answer", "refs"),
    [
        ("", ["Article 6.2"]),
        ("Article 6(3) applies.", []),
        ("No provisions named here.", ["Article 6.2"]),
    ],
)
def test_a_missing_input_is_a_strict_no_op(answer: str, refs: list[str]) -> None:
    assert _ground_wire_subpoints(answer, refs) == refs


def test_garbage_input_never_raises() -> None:
    """Fail-soft: the pass is a route post-processing step, never a 500."""
    assert _ground_wire_subpoints(None, ["Article 6.2"]) == ["Article 6.2"]  # type: ignore[arg-type]
    assert _ground_wire_subpoints("Article 6(3) applies.", ["!!", "Article 6"]) == [
        "!!",
        "Article 6",
    ]


# -- the live route -----------------------------------------------------------


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


def _stage2_env(monkeypatch: pytest.MonkeyPatch, *, flag: str) -> None:
    """Force a LANDED Stage-2 so the pass sees real model prose.

    Offline the wrapper is unreachable, ``_stage2_landed`` is false and the pass is
    correctly skipped (pinned separately below), so a wiring assertion needs a
    scripted completion — the pattern ``tests/test_r138_bluf_verdict_citations.py``
    established.
    """
    monkeypatch.setenv(FLAG, flag)
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)


def _ask(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    flag: str,
    answer: str = _ANSWER,
    question: str = _Q,
    reasoning: bool = False,
    landed: bool = True,
) -> dict[str, Any]:
    """One real route request, optionally with a scripted LANDED Stage-2."""
    _stage2_env(monkeypatch, flag=flag)
    url = "/api/v1/regenold/eu-ai-act/ask"
    if reasoning:
        url += "?include_reasoning=true"
    with ExitStack() as stack:
        if landed:
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
        r = client.post(url, json=[{"role": "user", "content": question}])
    assert r.status_code == 200, r.text
    return r.json()


def _heads(refs: list[str]) -> list[str]:
    return [str(r).split(".")[0].strip() for r in refs]


class TestTheShapeOfTheDefectIsFixedOnTheLiveRoute:
    """Not a stub: the real route, the real passes, a scripted landed answer."""

    def test_the_wire_ships_the_limb_the_prose_names(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        off = _ask(_client, monkeypatch, flag="0")
        on = _ask(_client, monkeypatch, flag="1")
        off_refs = [str(x) for x in off.get("references") or []]
        on_refs = [str(x) for x in on.get("references") or []]
        assert "Article 6.2" in off_refs, (
            f"fixture assumption broke — the pre-R425 wire no longer carries the "
            f"ungrounded sibling: {off_refs}"
        )
        assert "Article 6.3" in on_refs, f"the prose-named limb is missing: {on_refs}"
        assert "Article 6.2" not in on_refs, f"the ungrounded sibling survived: {on_refs}"

    def test_the_answer_set_count_and_heads_are_all_untouched(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        off = _ask(_client, monkeypatch, flag="0")
        on = _ask(_client, monkeypatch, flag="1")
        assert off.get("answer") == on.get("answer"), (
            "the pass edits the reference list only — the answer must be byte-identical"
        )
        off_refs = [str(x) for x in off.get("references") or []]
        on_refs = [str(x) for x in on.get("references") or []]
        assert len(off_refs) == len(on_refs), "the reference count must be invariant"
        assert _heads(off_refs) == _heads(on_refs), "the folded head set must be invariant"


class TestTheCallSiteIsReached:
    def test_flag_on_invokes_the_helper(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []

        def spy(_answer: str, refs: list[str]) -> list[str]:
            seen.append(list(refs))
            return list(refs)

        monkeypatch.setattr("app.routes.regenold._ground_wire_subpoints", spy)
        _ask(_client, monkeypatch, flag="1")
        assert seen, (
            f"{FLAG}=1 on a landed Stage-2 but _ground_wire_subpoints was never "
            "called — the route call site is missing or unreachable (the R329 "
            "zero-calls failure)"
        )

    def test_flag_off_never_invokes_the_helper(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []

        def spy(_answer: str, refs: list[str]) -> list[str]:
            seen.append(list(refs))
            return list(refs)

        monkeypatch.setattr("app.routes.regenold._ground_wire_subpoints", spy)
        _ask(_client, monkeypatch, flag="0")
        assert not seen, (
            "the pass ran with the flag OFF — a guard whose OFF state behaves like "
            "its ON state is the R360 inert-feature trap"
        )

    def test_a_deterministic_answer_is_not_touched_at_all(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ``_stage2_landed`` gate, and why it is the right place for it.

        The deterministic / curated-interception path has no Stage-2 prose and its
        reference set is hand-validated (the R274 doctrine), so a prose-derived
        rewrite must not reach it. That is also what keeps every offline
        instrument neutral. Asserted on the wire: with Stage-2 NOT landing the two
        arms are byte-identical.
        """
        seen: list[list[str]] = []

        def spy(_answer: str, refs: list[str]) -> list[str]:
            seen.append(list(refs))
            return list(refs)

        monkeypatch.setattr("app.routes.regenold._ground_wire_subpoints", spy)
        off = _ask(_client, monkeypatch, flag="0", landed=False)
        on = _ask(_client, monkeypatch, flag="1", landed=False)
        assert not seen, "the pass ran on a deterministic answer"
        assert (off.get("references") or []) == (on.get("references") or [])

    def test_the_helper_receives_the_final_reference_list(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It must see the refs the route is about to ship, not an early draft."""
        seen: list[list[str]] = []

        def spy(_answer: str, refs: list[str]) -> list[str]:
            seen.append(list(refs))
            return list(refs)

        monkeypatch.setattr("app.routes.regenold._ground_wire_subpoints", spy)
        body = _ask(_client, monkeypatch, flag="1")
        assert seen
        assert seen[-1] == (body.get("references") or [])


class TestTheResultReachesTheWire:
    def test_a_stub_change_shows_up_on_the_wire(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.routes.regenold._ground_wire_subpoints",
            lambda _answer, refs: list(refs) + ["Annex IX"],
        )
        after = _ask(_client, monkeypatch, flag="1")
        refs = [str(x) for x in after.get("references") or []]
        assert refs[-1] == "Annex IX", (
            "the pass's result did not reach the wire — nothing may re-add or "
            f"overwrite refs after the call site. got {refs}"
        )

    def test_flag_off_ignores_the_same_stub(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.routes.regenold._ground_wire_subpoints",
            lambda _answer, refs: list(refs) + ["Annex IX"],
        )
        after = _ask(_client, monkeypatch, flag="0")
        refs = [str(x) for x in after.get("references") or []]
        assert "Annex IX" not in refs, "the OFF state must be byte-identical"

    def test_the_rewrite_is_recorded_in_the_reasoning_trace(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An operator-visible signal, per the R360 'prove it fires' rule."""
        body = _ask(_client, monkeypatch, flag="1", reasoning=True)
        notes = json.loads(body.get("reasoning") or "{}").get("notes") or []
        assert any(str(n).startswith("wire_grain_grounded ") for n in notes), notes

    def test_the_trace_still_equals_the_wire(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The call site must sit BEFORE the trace finalisation."""
        body = _ask(_client, monkeypatch, flag="1", reasoning=True)
        traced = json.loads(body.get("reasoning") or "{}").get("references")
        assert traced == (body.get("references") or [])


class TestTheAddTwinSeesTheDottedForm:
    """R133's ADD path must read the same prose forms the rewrite reads.

    The rewrite is the mirror of the ADD pass, so they have to agree about what
    the prose NAMES. R133 reads the parenthesised and ``point``/``paragraph``
    forms; this pins that it now also reads the user-facing dotted form, which is
    the form the rewrite path handles and the form answers actually use.
    """

    def test_the_dotted_form_adds_the_leaf_the_parenthesised_form_adds(self) -> None:
        paren = R._surface_prose_subpoints("see Article 6(3) for this", ["Article 6"])
        dotted = R._surface_prose_subpoints("see Article 6.3 for this", ["Article 6"])
        assert "Article 6.3" in paren, paren
        assert dotted == paren, f"dotted={dotted} paren={paren}"

    def test_it_still_only_fires_on_the_bare_parent(self) -> None:
        """The R133 contract is unchanged: no bare parent on the wire, no ADD."""
        out = R._surface_prose_subpoints("see Article 6.3", ["Article 9"])
        assert out == ["Article 9"], out
        head = R._surface_prose_subpoints("see Article 6 for this", ["Article 6"])
        assert head == ["Article 6"], head


class TestFailSoft:
    def test_a_raising_helper_never_500s_the_route(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = [str(x) for x in (_ask(_client, monkeypatch, flag="0").get("references") or [])]

        def _boom(_answer: str, refs: list[str]) -> list[str]:
            raise RuntimeError("guard blew up")

        monkeypatch.setattr("app.routes.regenold._ground_wire_subpoints", _boom)
        after = _ask(_client, monkeypatch, flag="1")
        assert [str(x) for x in (after.get("references") or [])] == baseline

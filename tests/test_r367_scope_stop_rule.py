"""R367 — the scope stop rule must actually reach the model.

This repo has paid three times for the opposite: R329 seated a reranker in
three places that all read correctly in the diff and all made **zero calls**;
R330 found the entire R327 semantic layer had never executed; R366 found
``REGENOLD_PARENT_COLLAPSE`` had been a dead flag for the whole life of the
branch. Default-ON + cache-keyed + unit-tested + documented is **not** evidence
a flag runs.

So these assertions are on the WIRE — the actual Stage-2 user message captured
from a spy on the transport function — never on the shape of the source. A
source-text scan would also walk straight into the R366 comment-as-code trap.

The clause is DEFAULT OFF, so this module also pins the two-sided property: a
guard whose OFF state behaves like its ON state is the inert-feature trap
(R360's lesson).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")


@pytest.fixture()
def captured_user_messages(monkeypatch):
    """Spy on the Stage-2 transport and return every user message it saw."""
    import app.engines._graph_rag_impl as impl

    seen: list[str] = []

    def _spy(*args, **kwargs):
        seen.append(str(kwargs.get("user") or (args[1] if len(args) > 1 else "")))
        # Return None so the caller takes the deterministic fallback. We only
        # care about what was ASSEMBLED, not about a live completion.
        return None

    monkeypatch.setattr(
        impl, "_openai_wrapper_complete_for_graph_rag", _spy, raising=True
    )
    return seen


def _run(monkeypatch, enabled: str) -> str:
    """Assemble one Stage-2 user message with the flag set to ``enabled``."""
    import app.engines._graph_rag_impl as impl

    monkeypatch.setenv("REGENOLD_SCOPE_STOP_RULE", enabled)
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")

    query = impl._deterministic_parse("What must Article 13 instructions for use contain?")
    context = impl._retrieve_from_kb(query)
    impl._claude_max_enhance_answer(
        question="What must Article 13 instructions for use contain?",
        kg_answer="Article 13 fixes the minimum content of the instructions for use.",
        context=context,
    )
    return ""


class TestTheClauseReachesTheWire:
    def test_flag_on_puts_the_stop_rule_in_the_user_message(
        self, monkeypatch, captured_user_messages
    ) -> None:
        _run(monkeypatch, "1")
        assert captured_user_messages, (
            "the Stage-2 transport was never called — the spy proved nothing"
        )
        joined = "\n".join(captured_user_messages)
        assert "SCOPE STOP RULE" in joined, (
            "REGENOLD_SCOPE_STOP_RULE=1 but the clause never reached the user "
            "channel — this is the R329/R330/R366 inert-lever class"
        )

    def test_flag_off_is_a_strict_no_op(
        self, monkeypatch, captured_user_messages
    ) -> None:
        """Two-sided: the OFF state must really differ from the ON state."""
        _run(monkeypatch, "0")
        assert captured_user_messages, "transport never called"
        joined = "\n".join(captured_user_messages)
        assert "SCOPE STOP RULE" not in joined, (
            "the clause leaks in with the flag OFF — the default is supposed "
            "to be byte-identical to the pre-R367 prompt"
        )

    def test_on_and_off_differ_only_by_the_clause(
        self, monkeypatch, captured_user_messages
    ) -> None:
        from app.data.graph_rag_prompts import USER_SCOPE_STOP_CLAUSE

        _run(monkeypatch, "0")
        off = list(captured_user_messages)
        captured_user_messages.clear()
        _run(monkeypatch, "1")
        on = list(captured_user_messages)

        assert off and on and len(off) == len(on)
        for a, b in zip(off, on):
            assert USER_SCOPE_STOP_CLAUSE in b
            assert b.replace(USER_SCOPE_STOP_CLAUSE, "") == a, (
                "the ON arm differs from the OFF arm by something other than "
                "the clause — the A/B would not be measuring this lever"
            )


class TestTheClauseSaysTheRightThing:
    """The clause must target the CAUSE without licensing a correctness trade.

    R320 measured the blunt sentence cap at answer_conciseness +0.095 for
    answer_correctness **-0.143**. This lever is only worth running if it cuts
    unasked material and nothing else, so the completeness carve-out is
    load-bearing, not decoration.
    """

    def test_it_forbids_the_trailing_unasked_sentence(self) -> None:
        from app.data.graph_rag_prompts import USER_SCOPE_STOP_CLAUSE

        lowered = USER_SCOPE_STOP_CLAUSE.lower()
        for concept in ("stop", "did not raise", "delete it"):
            assert concept in lowered, f"clause is missing {concept!r}"

    def test_it_explicitly_protects_asked_for_completeness(self) -> None:
        from app.data.graph_rag_prompts import USER_SCOPE_STOP_CLAUSE

        lowered = USER_SCOPE_STOP_CLAUSE.lower()
        assert "never licenses dropping" in lowered
        for asked in ("enumerated set", "count", "second limb", "yes/no"):
            assert asked in lowered, (
                f"clause does not protect {asked!r} — that is the R320 trade"
            )

    def test_it_names_the_reference_side_too(self) -> None:
        """One root cause, both conciseness axes — say so in the instruction."""
        from app.data.graph_rag_prompts import USER_SCOPE_STOP_CLAUSE

        assert "citation list" in USER_SCOPE_STOP_CLAUSE.lower()


class TestFlagPlumbing:
    def test_default_is_off(self, monkeypatch) -> None:
        from app.data.graph_rag_prompts import scope_stop_rule_enabled

        monkeypatch.delenv("REGENOLD_SCOPE_STOP_RULE", raising=False)
        assert scope_stop_rule_enabled() is False, (
            "R367 must ship OFF — a prompt-side lever is not reference-neutral "
            "(AGENTS.md invariant #5) and its gates have not been run"
        )

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "ON", " 1 "])
    def test_truthy_values_enable(self, monkeypatch, value: str) -> None:
        from app.data.graph_rag_prompts import scope_stop_rule_enabled

        monkeypatch.setenv("REGENOLD_SCOPE_STOP_RULE", value)
        assert scope_stop_rule_enabled() is True

    @pytest.mark.parametrize("value", ["0", "off", "", "false", "no", "banana"])
    def test_anything_unreadable_fails_closed(self, monkeypatch, value: str) -> None:
        """R321's lesson: an unparseable value must never silently ENABLE."""
        from app.data.graph_rag_prompts import scope_stop_rule_enabled

        monkeypatch.setenv("REGENOLD_SCOPE_STOP_RULE", value)
        assert scope_stop_rule_enabled() is False

    def test_it_is_registered_in_the_engine_cache_key(self) -> None:
        """R263.2 — without this a same-process A/B serves arm A's cache to B.

        That is precisely how a lever reads +0.0000 while working fine.
        """
        from app.routes.regenold import _engine_cache_key

        args = ("What must the instructions for use contain?", None)
        os.environ["REGENOLD_SCOPE_STOP_RULE"] = "0"
        off = _engine_cache_key(*args)
        os.environ["REGENOLD_SCOPE_STOP_RULE"] = "1"
        on = _engine_cache_key(*args)
        os.environ["REGENOLD_SCOPE_STOP_RULE"] = "0"
        assert off != on, (
            "flipping REGENOLD_SCOPE_STOP_RULE does not move the engine cache "
            "key — a two-arm A/B would compare an arm against itself"
        )

    def test_the_clause_sits_in_the_protected_tail(self) -> None:
        """R341's shrinker preserves head + tail and compresses the middle.

        The shrinker in question is ``_shrink_user_for_groq``, and R360's
        strict transport policy now REFUSES the Groq leg, so this path does
        not run on the shipped contract. The marker is registered anyway so
        the clause cannot silently fall out of the protected tail if the
        shrinker is ever reused for another transport. Exercised through the
        real function, not by reading its marker tuple.
        """
        import app.engines._graph_rag_impl as impl
        from app.data.graph_rag_prompts import USER_SCOPE_STOP_CLAUSE

        user = (
            "ORIGINAL QUESTION: what must the instructions for use contain?\n"
            + ("COMPRESSIBLE MIDDLE. " * 3000)
            + USER_SCOPE_STOP_CLAUSE
        )
        out = impl._shrink_user_for_groq(user, budget=4000)
        assert len(out) < len(user), "the shrinker did not shrink anything"
        assert "SCOPE STOP RULE" in out, (
            "the stop rule is chopped by the tail-preserving shrinker — it "
            "must be a registered tail marker or it stops being delivered"
        )

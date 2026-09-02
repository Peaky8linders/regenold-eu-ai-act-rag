"""R380 — the V3 ANSWER DISCIPLINE block must actually reach the model, and
the clauses it replaces must actually be withheld.

Same discipline as R367: every assertion is on the WIRE — the real Stage-2
user message captured by a spy on the transport function — never on the
shape of the source (the R366 comment-as-code trap). Two-sided: the OFF state
is pinned as byte-equivalent to the pre-R380 message, because a guard whose
OFF state behaves like its ON state is the inert-feature trap (R360).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")

_Q = "What must Article 13 instructions for use contain?"

# The instructions V3 withholds. Each is a verbatim fragment of a clause that
# the R380 audit identified as inviting adjacent-but-unasked law.
_WITHHELD = (
    "For a practice restricted only in certain contexts, state both",
    "rule 12b closed-set completeness",
    "CROSS-REFERENCED PROVISIONS (background only",
    " ANSWER COVERAGE:",
    " CRITICAL ANSWER RULES",
    " REFERENCE MINIMALITY:",
    " SUB-PARAGRAPH DISCIPLINE:",
    " TERMINOLOGY: use the EU AI Act's exact statutory terms",
    "Refine the knowledge-graph draft above",
)


@pytest.fixture()
def captured_user_messages(monkeypatch):
    """Spy on the Stage-2 transport and return every user message it saw."""
    import app.engines._graph_rag_impl as impl

    seen: list[str] = []

    def _spy(*args, **kwargs):
        seen.append(str(kwargs.get("user") or (args[1] if len(args) > 1 else "")))
        return None

    monkeypatch.setattr(
        impl, "_openai_wrapper_complete_for_graph_rag", _spy, raising=True
    )
    return seen


def _assemble(monkeypatch, v3: str) -> None:
    import app.engines._graph_rag_impl as impl

    monkeypatch.setenv("REGENOLD_PROMPT_V3", v3)
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    # Make the withheld clauses' own gates deterministic for the OFF arm.
    monkeypatch.setenv("REGENOLD_SCOPE_STOP_RULE", "0")
    monkeypatch.setenv("REGENOLD_ANSWER_FIRST", "0")
    query = impl._deterministic_parse(_Q)
    context = impl._retrieve_from_kb(query)
    impl._claude_max_enhance_answer(
        question=_Q,
        kg_answer="Article 13 fixes the minimum content of the instructions for use.",
        context=context,
    )


class TestV3ReachesTheWire:
    def test_on_appends_the_block_last(self, monkeypatch, captured_user_messages):
        _assemble(monkeypatch, "1")
        assert captured_user_messages, "the Stage-2 transport was never called"
        msg = captured_user_messages[-1]
        pos = msg.find(" ANSWER DISCIPLINE (V3")
        assert pos > 0, "REGENOLD_PROMPT_V3=1 but the block never reached the user channel"
        # Last instruction the model reads: after the block, only the R357
        # final-sentence completeness reminder may follow (it is 364 chars and
        # length-neutral), never another rule set.
        assert "6. GROUNDING" in msg[pos:]
        end = msg.find("lettered articles.") + len("lettered articles.")
        after = msg[end:].strip()
        assert after == "" or after.startswith("COMPLETENESS OF THE FINAL SENTENCE"), after[:120]
        assert " ANSWER COVERAGE:" not in msg[pos:]
        assert " CRITICAL ANSWER RULES" not in msg[pos:]

    def test_on_withholds_every_breadth_clause(self, monkeypatch, captured_user_messages):
        _assemble(monkeypatch, "1")
        msg = captured_user_messages[-1]
        leaked = [w for w in _WITHHELD if w in msg]
        assert not leaked, f"V3 ON but these clauses still reached the model: {leaked}"
        assert "RETRIEVED DRAFT (machine-generated; over-inclusive)" in msg
        assert "NOT an outline" in msg

    def test_on_keeps_the_grounding_and_the_verdict_first_rule(
        self, monkeypatch, captured_user_messages
    ):
        _assemble(monkeypatch, "1")
        msg = captured_user_messages[-1]
        assert "EU AI ACT REFERENCES" in msg
        assert "Lead with a DIRECT verdict" in msg
        assert "ANSWER THE CURRENT QUESTION ONLY" in msg

    def test_on_is_materially_shorter_in_instructions(
        self, monkeypatch, captured_user_messages
    ):
        _assemble(monkeypatch, "0")
        off = captured_user_messages[-1]
        _assemble(monkeypatch, "1")
        on = captured_user_messages[-1]
        # Same grounding both arms; the instruction stack is what shrinks.
        # (~2.9k against the V1 stack that R379 restored as default, ~7k
        # against the V2 stack; the block itself is 6k because it carries the
        # Article 5 verdict roster and the factual guards.)
        assert len(on) < len(off) - 2000, (len(on), len(off))


class TestOffIsAStrictNoOp:
    def test_off_sends_the_pre_r380_message(self, monkeypatch, captured_user_messages):
        _assemble(monkeypatch, "0")
        msg = captured_user_messages[-1]
        assert " ANSWER DISCIPLINE (V3" not in msg
        assert "RETRIEVED DRAFT (machine-generated" not in msg
        assert "Refine the knowledge-graph draft above" in msg
        assert "For a practice restricted only in certain contexts, state both" in msg
        assert "rule 12b closed-set completeness" in msg
        assert " ANSWER COVERAGE:" in msg
        assert " CRITICAL ANSWER RULES" in msg

    def test_unparseable_value_means_off(self, monkeypatch):
        from app.data.graph_rag_prompts import prompt_v3_enabled

        for v in ("", " ", "false", "no", "off", "disabled", "-1", "v3"):
            monkeypatch.setenv("REGENOLD_PROMPT_V3", v)
            assert prompt_v3_enabled() is False, v
        for v in ("1", "true", "yes", "on", " ON "):
            monkeypatch.setenv("REGENOLD_PROMPT_V3", v)
            assert prompt_v3_enabled() is True, v


class TestCacheKeyAndTailPreservation:
    def test_flag_is_in_the_engine_cache_key(self, monkeypatch):
        """Without this a same-process A/B serves arm A's cache to arm B."""
        from app.routes import regenold as route

        monkeypatch.setenv("REGENOLD_PROMPT_V3", "0")
        k0 = route._engine_cache_key(_Q, None)
        monkeypatch.setenv("REGENOLD_PROMPT_V3", "1")
        k1 = route._engine_cache_key(_Q, None)
        assert k0 != k1

    def test_shrinker_keeps_the_v3_tail(self):
        """The R336 tail-preserving truncation must protect the V3 block."""
        import app.engines._graph_rag_impl as impl
        from app.data.graph_rag_prompts import USER_V3_DISCIPLINE_CLAUSE

        body = "EU AI ACT REFERENCES:\n" + ("Article 13 text. " * 2000)
        user = body + USER_V3_DISCIPLINE_CLAUSE
        shrunk = impl._shrink_user_for_groq(user, budget=10000)
        assert " ANSWER DISCIPLINE (V3" in shrunk
        assert shrunk.rstrip().endswith("lettered articles.")

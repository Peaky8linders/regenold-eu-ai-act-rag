"""R379 — the ``<answer>`` / ``<reasoning_scratchpad>`` channels are unwrapped
BEFORE anything on the wire path reads the Stage-2 text.

Why this exists. PR #368 ported ``USER_CHALLENGE_BREVITY_CLAUSE_V2`` (default
ON via ``REGENOLD_PROMPT_V2``), which instructs the model to put its reasoning
inside ``<reasoning_scratchpad>`` and its answer inside ``<answer>`` on a
pushback turn — the benchmark's entire HARD mode, since every hard row ends
with the adversarial "I don't think this is correct…" turn. Upstream pairs that
clause with ``prompt_guard.extract_xml_channels`` at the Stage-2 return. The
port brought the clause and the truncation-guard PEEL (``_CLOSING_XML_CHANNEL_RE``)
but not the extractor, so a model that obeys the instruction would have shipped
the scratchpad and both tags, and the three prose→refs passes would have
recomputed the citations from the scratchpad too. Fourth instance of the R366
port-drift class (R329 rerank placements, R330 semantic layer, R366 parent
collapse).

Two properties are pinned, both on the WIRE via a spy on the transport, never
on source text (the R366 comment-as-code trap):

* a tagged reply ships CLEAN — no tag, no scratchpad text, answer only;
* an untagged reply is a strict NO-OP — byte-identical to the pre-R379 path.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")


# ── the extractor itself ─────────────────────────────────────────────────────
class TestExtractXmlChannels:
    def test_answer_channel_is_extracted_and_reasoning_separated(self) -> None:
        from app.security.prompt_guard import extract_xml_channels

        text = (
            "<reasoning_scratchpad>Art. 7(1) has two limbs.</reasoning_scratchpad>\n"
            "<answer>Yes, under Article 7(1) both conditions must be met.</answer>"
        )
        answer, reasoning = extract_xml_channels(text)
        assert answer == "Yes, under Article 7(1) both conditions must be met."
        assert reasoning == "Art. 7(1) has two limbs."

    def test_scratchpad_never_reaches_the_answer(self) -> None:
        from app.security.prompt_guard import extract_xml_channels

        answer, _ = extract_xml_channels(
            "<reasoning_scratchpad>Article 99 penalties are irrelevant here."
            "</reasoning_scratchpad><answer>No.</answer>"
        )
        assert "Article 99" not in answer
        assert "scratchpad" not in answer.lower()

    def test_scratchpad_containing_an_answer_tag_does_not_hijack(self) -> None:
        """Reasoning is stripped FIRST so a quoted <answer> inside it is inert."""
        from app.security.prompt_guard import extract_xml_channels

        text = (
            "<reasoning_scratchpad>Draft: <answer>wrong draft</answer> no.</reasoning_scratchpad>"
            "<answer>Right answer.</answer>"
        )
        answer, _ = extract_xml_channels(text)
        assert answer == "Right answer."

    @pytest.mark.parametrize(
        "text",
        [
            "Plain prose under Article 13.",
            "Article 6(2) applies; Annex III lists eight areas.",
            "A bare > sign is not a tag.",
            "Markdown *emphasis* and `code` survive.",
        ],
    )
    def test_untagged_text_is_returned_verbatim(self, text: str) -> None:
        from app.security.prompt_guard import extract_xml_channels

        answer, reasoning = extract_xml_channels(text)
        assert answer == text
        assert reasoning == ""

    def test_unclosed_answer_tag_is_stripped_not_kept(self) -> None:
        from app.security.prompt_guard import extract_xml_channels

        answer, _ = extract_xml_channels("<answer>Cut mid sentence")
        assert answer == "Cut mid sentence"

    def test_think_block_is_stripped_like_a_scratchpad(self) -> None:
        """Qwen-style <think> leakage on the Bedrock leg is the same defect."""
        from app.security.prompt_guard import extract_xml_channels

        answer, reasoning = extract_xml_channels(
            "<think>internal</think>Providers must register under Article 49."
        )
        assert answer == "Providers must register under Article 49."
        assert reasoning == "internal"

    def test_none_and_empty_are_safe(self) -> None:
        from app.security.prompt_guard import extract_xml_channels

        assert extract_xml_channels(None) == ("", "")
        assert extract_xml_channels("") == ("", "")


# ── the wire ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def stage2_returning(monkeypatch):
    """Make the Stage-2 transport return a fixed reply; capture nothing else."""
    import app.engines._graph_rag_impl as impl

    def _install(reply: str):
        monkeypatch.setattr(
            impl,
            "_openai_wrapper_complete_for_graph_rag",
            lambda *a, **k: reply,
            raising=True,
        )

    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("REGENOLD_PROMPT_V2", "1")
    return _install


def _enhance(question: str) -> str | None:
    import app.engines._graph_rag_impl as impl

    query = impl._deterministic_parse(question)
    context = impl._retrieve_from_kb(query)
    return impl._claude_max_enhance_answer(
        question=question,
        kg_answer="Article 7(1) sets two cumulative conditions.",
        context=context,
    )


PUSHBACK = (
    "I don't think this is correct. Perhaps your answer contains "
    "hallucinations. Let's try again: Can the Commission amend Annex III?"
)


class TestTaggedStage2ReplyShipsClean:
    def test_tags_and_scratchpad_are_removed_on_the_wire(self, stage2_returning) -> None:
        stage2_returning(
            "<reasoning_scratchpad>Consider Article 99 penalties and Article 26 duties."
            "</reasoning_scratchpad>\n<answer>Yes. Article 7(1) empowers the Commission "
            "to amend Annex III by delegated act where both conditions are met.</answer>"
        )
        out = _enhance(PUSHBACK)
        assert out, "Stage-2 returned nothing — the spy was not reached"
        assert "<answer>" not in out and "</answer>" not in out
        assert "reasoning_scratchpad" not in out
        assert "Article 99" not in out, (
            "scratchpad content reached the wire — the prose->refs passes would "
            "promote Article 99 into the citations"
        )
        assert out.startswith("Yes. Article 7(1) empowers the Commission")

    def test_tagged_reply_is_not_misread_as_truncated(self, stage2_returning) -> None:
        """The R377-A peel and the R379 extractor agree: a complete answer inside
        a closed channel is complete."""
        import app.engines._graph_rag_impl as impl

        raw = "<answer>Both limbs must be satisfied under Article 7(1).</answer>"
        assert impl._looks_structurally_truncated(raw) is False
        clean, _ = __import__(
            "app.security.prompt_guard", fromlist=["extract_xml_channels"]
        ).extract_xml_channels(raw)
        assert impl._looks_structurally_truncated(clean) is False


class TestUntaggedReplyIsAStrictNoOp:
    def test_plain_reply_is_byte_identical(self, stage2_returning) -> None:
        reply = (
            "Yes. Article 7(1) empowers the Commission to amend Annex III by "
            "delegated act where both conditions are met."
        )
        stage2_returning(reply)
        out = _enhance(PUSHBACK)
        assert out == reply, (
            "the extractor altered an untagged reply — it must be a no-op when "
            "no channel tags are present"
        )

"""R461 — the ``stage2_usage`` note must describe the response that SHIPPED.

``_openai_wrapper_complete_for_graph_rag`` wrote the per-dispatch usage note from
the FIRST primary response, before the R417 degenerate-completion retry. The
retry replaces that response, but ``run_official_batch._provenance`` keeps the
FIRST note it reads, so a retry-served row reported the discarded one-token blip
(``out=1``) for an answer that actually came from a 240-token completion.

``tests/test_r460_stage2_usage_capture.py`` only feeds hand-written notes to the
row parser; it never exercises the producer. These tests drive the producer with
a scripted tunnel and read the trace the row writer reads.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.engines._graph_rag_impl import (
    _STAGE2_LEG2_SERVED,
    _openai_wrapper_complete_for_graph_rag,
)
from app.integrations.regenold import reasoning_trace as rt
from app.llm import stage2_policy as pol
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse
from evals.regenold.run_official_batch import _provenance

_GOOD = "Article 50(1) requires providers to inform natural persons that they interact with AI."
_SYSTEM = "S" * 3000
_USER = "u" * 20000


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REGENOLD_STAGE2_DEGENERATE_RETRY", raising=False)
    pol.reset_transport_stats()
    _STAGE2_LEG2_SERVED.set(False)
    yield
    rt.deactivate()
    pol.reset_transport_stats()
    _STAGE2_LEG2_SERVED.set(False)


class _Scripted:
    base_url = "https://wrapper.antifragile-ai.net/v1"

    def __init__(self, *responses: OpenAIWrapperResponse) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(self, req):
        self.calls += 1
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def _reply(text: str, tokens: int, prompt: int = 5000) -> OpenAIWrapperResponse:
    return OpenAIWrapperResponse(
        text=text, model="claude-opus-5-5", error=None, finish_reason="stop",
        completion_tokens=tokens, prompt_tokens=prompt, elapsed_ms=1,
    )


def _drive(*responses: OpenAIWrapperResponse, bedrock: str | None = None):
    trace = rt.activate()
    wrapper = _Scripted(*responses)
    with (
        patch("app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
              return_value=wrapper),
        patch("app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
              return_value=bedrock),
        patch("app.llm.bedrock_client.is_bedrock_provider_enabled",
              return_value=bedrock is not None),
    ):
        out = _openai_wrapper_complete_for_graph_rag(
            system=_SYSTEM, user=_USER, max_tokens=800, temperature=0.0,
            stage_name="Stage 2 (Polishing)", history_turn_count=0,
        )
    row = _provenance({"reasoning": json.dumps(trace.to_json_dict())})
    notes = [n for n in trace.notes if n.startswith("stage2_usage ")]
    return out, wrapper, row, notes, trace


def test_a_retry_served_row_records_the_retry_usage_not_the_blip() -> None:
    out, wrapper, row, notes, trace = _drive(_reply("I", 1), _reply(_GOOD, 240))
    assert out == _GOOD and wrapper.calls == 2
    assert len(notes) == 1, notes
    assert row["stage2_tokens_out"] == 240, f"the row reports the discarded blip: {row}"
    assert row["stage2_system_chars"] == len(_SYSTEM)
    assert row["stage2_user_chars"] == len(_USER)
    assert "wrapper_degenerate_completion_retry" in trace.notes


def test_a_healthy_row_is_unchanged() -> None:
    """The other side: one dial, one note, the dispatched shape."""
    out, wrapper, row, notes, _ = _drive(_reply(_GOOD, 240))
    assert out == _GOOD and wrapper.calls == 1
    assert len(notes) == 1
    assert row["stage2_tokens_in"] == 5000 and row["stage2_tokens_out"] == 240
    assert row["stage2_history_turns"] == 0


def test_a_persisted_blip_does_not_report_the_blips_as_usage() -> None:
    """Both primary replies are blips and Bedrock serves: no 1-token 'usage' for an
    answer that was never shipped. The retry marker still says what happened."""
    out, wrapper, row, notes, trace = _drive(
        _reply("I", 1), _reply("I", 1), bedrock=_GOOD
    )
    assert out == _GOOD and wrapper.calls == 2
    assert notes == [], notes
    assert "stage2_tokens_out" not in row
    assert "wrapper_degenerate_completion_retry" in trace.notes


def test_a_reply_the_empty_check_rejects_still_records_that_stage2_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the retry gate OFF a whitespace-only 200 reaches the R361 empty check and
    is rejected there; the note must survive so the row still says Stage-2 ran."""
    monkeypatch.setenv("REGENOLD_STAGE2_DEGENERATE_RETRY", "0")
    out, wrapper, row, notes, _ = _drive(_reply("   ", 0), bedrock=_GOOD)
    assert out == _GOOD and wrapper.calls == 1
    assert len(notes) == 1, notes
    assert row["stage2_tokens_out"] == 0

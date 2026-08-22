"""R360.12/.13 — two verified defects found by adversarial review, not by tests.

Both share a shape: a failure that looked like data. One turned a telemetry
field into a Stage-2 outage; the other turned a failed graph query into an
empty result.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


class TestNullTokenCountsDoNotKillStage2:
    """R360.12 — ``.get(k, 0)`` covers a MISSING key, not a null VALUE.

    Several OpenAI-compatible facades send ``"prompt_tokens": null`` on a cache
    hit. ``int(None)`` raises TypeError, and the line sits outside the guarding
    try — so the whole Stage-2 call died over a number nothing downstream reads.
    """

    @pytest.mark.parametrize(
        "usage",
        [
            {"prompt_tokens": None, "completion_tokens": None},
            {"prompt_tokens": None, "completion_tokens": 12},
            {},  # the missing-key case that already worked — pin it
        ],
    )
    def test_response_parses_with_null_or_absent_usage(self, usage: dict) -> None:
        import httpx

        from app.llm import openai_wrapper_provider as owp

        payload = {
            "model": "claude-opus-4-8",
            "choices": [
                {
                    "message": {"content": "Article 50 applies."},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        prov = owp._OpenAIWrapperProvider(
            base_url="http://127.0.0.1:8000/v1", api_key="k", timeout=5.0
        )
        prov._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="http://127.0.0.1:8000/v1",
        )
        try:
            resp = prov.complete(
                owp.OpenAIWrapperRequest(
                    system="s", user="u", model="claude-opus-4-8",
                    max_tokens=64, temperature=0.0,
                )
            )
        finally:
            prov._client.close()

        assert resp.error is None, resp.error
        assert resp.text == "Article 50 applies."
        assert resp.prompt_tokens == 0 or isinstance(resp.prompt_tokens, int)


class TestStrictGraphReadExists:
    """R360.13 — ``kg_context`` probed for a method the client never had.

    ``getattr(client, "execute_read_strict", None)`` has been in kg_context
    since R326; the only implementations were test doubles. So the tests
    exercised a raising branch production never took, and every real graph
    read collapsed failure into ``[]`` — a failed query and a genuinely empty
    result reported as the same fact.
    """

    def test_the_production_client_implements_it(self) -> None:
        from app.graph.client import GraphClient

        assert callable(getattr(GraphClient, "execute_read_strict", None)), (
            "kg_context probes for execute_read_strict; the real client must have it"
        )

    def test_it_raises_where_execute_read_would_swallow(self) -> None:
        from app.graph.client import GraphClient
        from app.graph.config import GraphSettings

        client = GraphClient.__new__(GraphClient)
        client._driver = object()
        client._settings = GraphSettings()

        with patch.object(
            GraphClient, "_run_read", side_effect=RuntimeError("cypher exploded")
        ):
            # The lenient sibling hides it...
            assert client.execute_read("MATCH (n) RETURN n") == []
            # ...the strict one does not.
            with pytest.raises(RuntimeError, match="cypher exploded"):
                client.execute_read_strict("MATCH (n) RETURN n")

    def test_a_healthy_read_still_returns_rows(self) -> None:
        from app.graph.client import GraphClient
        from app.graph.config import GraphSettings

        client = GraphClient.__new__(GraphClient)
        client._driver = object()
        client._settings = GraphSettings()

        with patch.object(GraphClient, "_run_read", return_value=[{"n": 1}]):
            assert client.execute_read_strict("MATCH (n) RETURN n") == [{"n": 1}]

    def test_no_driver_raises_rather_than_reporting_empty(self) -> None:
        from app.graph.client import GraphClient
        from app.graph.config import GraphSettings

        client = GraphClient.__new__(GraphClient)
        client._driver = None
        client._settings = GraphSettings()

        with pytest.raises(RuntimeError, match="no driver"):
            client.execute_read_strict("MATCH (n) RETURN n")

"""R131 — final wire references (with sub-points) surfaced in the reasoning trace.

The R130 sub-point fix made the API ``references`` carry ``Article 3.1`` /
``Annex IV.2`` style sub-points, but the ``?include_reasoning=true`` trace
recorded only ``anchors_used`` (keyword-derived, internal ``Art. N`` form, no
sub-points, and absent on the definitional path). So the UI reasoning panel
never showed the citations actually returned.

R131 records the FINAL wire ``references`` into the trace, serialised AFTER
every reference pass (R72 reconcile, conciseness cap, R105, R130
``Article 3.N`` upgrade) so the reasoning logs match the API response exactly.

Locks in:
* ``ReasoningTrace.references`` recorder + ``to_json_dict`` emission contract.
* Route integration: ``reasoning.references`` == wire ``references`` (with
  sub-points) for definitional / sub-point / multi-article questions.
* Default-off path unchanged (no ``references`` leak when reasoning is off).
* Refusal path: empty references → the key is dropped (not an empty list).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.integrations.regenold import reasoning_trace as rt
from app.main import app
from app.rate_limit import limiter

_EVAL_KEY = "regenold-r131-eval-key"


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def _client():
    prev = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_EVAL_KEY)
    try:
        with TestClient(app, headers={"X-Regenold-Api-Key": _EVAL_KEY}) as c:
            yield c
    finally:
        settings.regenold.api_key = prev


# ── Unit — recorder + serialisation contract ────────────────────────────


class TestRecorderContract:
    def test_record_populates_active_trace(self) -> None:
        trace = rt.activate()
        try:
            rt.record_references(["Article 3.1", "Annex IV.2"])
            assert trace.references == ["Article 3.1", "Annex IV.2"]
            assert trace.to_json_dict()["references"] == [
                "Article 3.1",
                "Annex IV.2",
            ]
        finally:
            rt.deactivate()

    def test_empty_references_dropped_from_payload(self) -> None:
        trace = rt.activate()
        try:
            rt.record_references([])
            assert "references" not in trace.to_json_dict()
        finally:
            rt.deactivate()

    def test_no_active_trace_is_noop(self) -> None:
        rt.deactivate()  # ensure no active trace
        # Must not raise when reasoning is off (the default path).
        rt.record_references(["Article 13"])
        assert rt.current() is None

    def test_recorder_copies_not_aliases(self) -> None:
        trace = rt.activate()
        try:
            src = ["Article 6"]
            rt.record_references(src)
            src.append("Article 99")  # mutate the source after recording
            assert trace.references == ["Article 6"]
        finally:
            rt.deactivate()


# ── Route integration — trace references == wire references ──────────────


class TestRouteReferencesMatchWire:
    @pytest.mark.parametrize(
        "question",
        [
            "What is an AI system?",                       # definitional → Article 3.1
            "Who is a deployer?",                          # Article 3.4
            "What information must the technical documentation contain?",  # Annex IV.2
            "What are the obligations of deployers of high-risk AI systems?",
            "What does Article 13 require?",
        ],
    )
    def test_reasoning_references_equal_wire_references(
        self, _client: TestClient, question: str
    ) -> None:
        body = _client.post(
            "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
            json=[{"role": "user", "content": question}],
        ).json()
        wire_refs = body.get("references") or []
        assert wire_refs, f"expected non-empty wire refs for: {question!r}"
        parsed = json.loads(body.get("reasoning") or "{}")
        assert parsed.get("references") == wire_refs, (
            "reasoning trace references must mirror the wire references "
            f"(with sub-points) for: {question!r}"
        )

    def test_subpoint_surfaces_in_reasoning(self, _client: TestClient) -> None:
        """The R130 ``Article 3.N`` sub-point must appear in BOTH the wire
        and the reasoning trace."""
        body = _client.post(
            "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
            json=[{"role": "user", "content": "What is an AI system?"}],
        ).json()
        assert "Article 3.1" in (body.get("references") or [])
        parsed = json.loads(body.get("reasoning") or "{}")
        assert "Article 3.1" in (parsed.get("references") or [])


class TestRefusalAndDefault:
    def test_refusal_has_no_references_key(self, _client: TestClient) -> None:
        """OOS refusal ships empty references → the trace drops the key
        (not an empty list)."""
        body = _client.post(
            "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
            json=[{"role": "user", "content": "Tell me a joke about cats."}],
        ).json()
        assert (body.get("references") or []) == []
        parsed = json.loads(body.get("reasoning") or "{}")
        assert "references" not in parsed

    def test_default_off_reasoning_carries_no_references(
        self, _client: TestClient
    ) -> None:
        """Without ?include_reasoning=true the reasoning field stays the
        spec-default empty string — the references recorder is a no-op."""
        body = _client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": "What does Article 13 require?"}],
        ).json()
        assert body.get("reasoning") == ""
        # The wire references are still produced (the response field).
        assert body.get("references")

    def test_param_does_not_change_answer_or_references(
        self, _client: TestClient
    ) -> None:
        """R131 is purely additive to the reasoning field — answer +
        wire references are byte-identical with/without the param."""
        q = "What are the obligations of deployers of high-risk AI systems?"
        without = _client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": q}],
        ).json()
        with_ = _client.post(
            "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
            json=[{"role": "user", "content": q}],
        ).json()
        assert without.get("answer") == with_.get("answer")
        assert without.get("references") == with_.get("references")

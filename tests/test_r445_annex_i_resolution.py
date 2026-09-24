"""R445 — Annex I point coordinates must agree with the adopted sectioned list.

The Act numbers Annex I continuously across its headings: MDR is point 11 in
Section A; Regulation (EU) 2019/2144 is point 19 in Section B. A model's prose
count must not override that list, and an ambiguous mention must not produce a
leaf citation.
"""
from __future__ import annotations

import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.data.provision_coordinates import coordinate_exists
from app.main import app
from app.rate_limit import limiter
from app.routes import regenold as R
from evals.official.rubric import reference_correctness_strict

_MEDICAL_Q = (
    "Are AI safety components within medical devices of MDR class IIa, IIb, "
    "or III high-risk under the EU AI Act?"
)
_VEHICLE_Q = (
    "Are AI safety components in motor vehicles covered by Regulation (EU) "
    "2019/2144 high-risk under the EU AI Act?"
)
_KEY = "r445-annex-i-test-key"


@pytest.fixture(autouse=True)
def _resolver_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """R446b — the resolver ships default OFF; this module pins how it behaves ON."""
    monkeypatch.setenv("REGENOLD_ANNEX_I_RESOLUTION", "1")


def test_adopted_list_index_preserves_section_and_printed_numbering() -> None:
    index = R._annex_i_listed_instruments()
    assert index[("regulation", "2017/745")] == (("A", 11),)
    assert index[("regulation", "2019/2144")] == (("B", 19),)
    assert index[("regulation", "2008/300")] == (("B", 13),)
    assert coordinate_exists("Annex I.11")
    assert coordinate_exists("Annex I.19")


@pytest.mark.parametrize(
    "question,answer,expected",
    [
        (
            _MEDICAL_Q,
            "Annex I includes Regulation (EU) 2017/745 (MDR) at point 11 for medical devices.",
            "Annex I.11",
        ),
        (
            _MEDICAL_Q,
            "Annex I includes Regulation (EU) 2017/745 (MDR) at point 19 for medical devices.",
            "Annex I.11",
        ),
        (
            _VEHICLE_Q,
            "Annex I includes Regulation (EU) 2019/2144 at point 11 for motor vehicles.",
            "Annex I.19",
        ),
    ],
)
def test_deepener_resolves_act_against_adopted_annex_list(question, answer, expected):
    assert R._deepen_one_ref("Annex I", question, answer) == expected


def test_already_emitted_leaf_is_repaired_from_mdr_identity() -> None:
    answer = "Annex I lists Regulation (EU) 2017/745 (MDR) at point 19 for medical devices."
    assert R._repair_annex_i_wire_points(["Annex I.19"], _MEDICAL_Q, answer) == [
        "Annex I.11"
    ]


def test_already_emitted_leaf_keeps_continuous_section_b_number() -> None:
    answer = "Annex I lists Regulation (EU) 2019/2144 at point 11 for motor vehicles."
    assert R._repair_annex_i_wire_points(["Annex I.11"], _VEHICLE_Q, answer) == [
        "Annex I.19"
    ]


def test_ambiguous_or_unlisted_act_abstains_to_head() -> None:
    ambiguous = (
        "Annex I includes Regulation (EU) 2017/745 and Regulation (EU) "
        "2019/2144 at point 19 for this product."
    )
    assert R._deepen_one_ref("Annex I", _MEDICAL_Q, ambiguous) == "Annex I"
    assert R._repair_annex_i_wire_points(["Annex I.19"], _MEDICAL_Q, ambiguous) == [
        "Annex I"
    ]

    unknown = "Annex I includes Regulation (EU) 2099/1234 at point 19 for devices."
    assert R._deepen_one_ref("Annex I", _MEDICAL_Q, unknown) == "Annex I"


def test_ambiguous_enumeration_is_not_rewritten() -> None:
    answer = "Annex I points 11 and 19 cover the MDR and vehicle legislation."
    assert R._repair_annex_i_prose_points(answer, _MEDICAL_Q) == answer
    assert R._deepen_one_ref("Annex I", _MEDICAL_Q, answer) == "Annex I"


def test_scorer_distinguishes_flat_wrong_point_and_normalizes_valid_legacy_form() -> None:
    key = ["Article 6.1", "Annex I.a.11"]
    assert reference_correctness_strict(["Article 6.1", "Annex I.11"], key) == 1.0
    assert reference_correctness_strict(["Article 6.1", "Annex I.a.11"], key) == 1.0
    assert reference_correctness_strict(["Article 6.1", "Annex I.19"], key) == 0.5


def _stage2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
    monkeypatch.setattr(settings.regenold, "api_key", SecretStr(_KEY))
    limiter.reset()


def _live_ask(
    monkeypatch: pytest.MonkeyPatch,
    *,
    question: str,
    answer: str,
    initial_refs: list[str],
    reasoning: bool = False,
) -> dict:
    _stage2_env(monkeypatch)
    original_deepen = R._deepen_ref_grain

    def seed_leaf(refs, q, prose, exempt_heads=None):
        deepened = original_deepen(refs, q, prose, exempt_heads=exempt_heads)
        return [r for r in deepened if not str(r).lower().startswith("annex i.")] + initial_refs

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True)
        )
        stack.enter_context(
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                side_effect=lambda *args, **kwargs: answer,
            )
        )
        stack.enter_context(patch.object(R, "_deepen_ref_grain", side_effect=seed_leaf))
        with TestClient(app, headers={"X-Regenold-Api-Key": _KEY}) as client:
            suffix = "?include_reasoning=true" if reasoning else ""
            response = client.post(
                f"/api/v1/regenold/eu-ai-act/ask{suffix}",
                json=[{"role": "user", "content": question}],
            )
    assert response.status_code == 200, response.text
    return response.json()


def test_route_wire_repairs_mdr_miscount_in_answer_refs_and_reasoning(monkeypatch) -> None:
    # R446 — the prose half of this test needs the regime it was written for:
    # the answer-text rewrite is now behind a default-OFF flag (review finding
    # F1; the default-OFF arm is pinned in tests/test_r446_annex_i_review_fixes.py).
    monkeypatch.setenv("REGENOLD_ANNEX_I_PROSE_REPAIR", "1")
    answer = (
        "Under Article 6(1), an AI safety component in a medical device is high-risk "
        "when third-party conformity assessment is required. Annex I lists "
        "Regulation (EU) 2017/745 (MDR) at point 19."
    )
    body = _live_ask(
        monkeypatch,
        question=_MEDICAL_Q,
        answer=answer,
        initial_refs=["Annex I.19"],
        reasoning=True,
    )
    refs = [str(ref) for ref in body.get("references") or []]
    output = str(body.get("answer") or "")
    assert "Annex I.11" in refs, refs
    assert "Annex I.19" not in refs, refs
    assert "at point 11" in output, output
    assert "at point 19" not in output, output
    traced = json.loads(body.get("reasoning") or "{}").get("references")
    assert traced == refs


def test_resolver_failure_coarsens_leaf_and_does_not_break_route(monkeypatch) -> None:
    def fail_index():
        raise RuntimeError("adopted corpus index unavailable")

    monkeypatch.setattr(R, "_annex_i_listed_instruments", fail_index)
    answer = "Annex I lists Regulation (EU) 2017/745 (MDR) at point 19."
    assert R._repair_annex_i_wire_points(["Annex I.19"], _MEDICAL_Q, answer) == [
        "Annex I"
    ]


def test_question_side_act_identifier_repairs_leaf_when_answer_only_has_point() -> None:
    answer = "Annex I point 19 applies to motor vehicles."
    assert R._repair_annex_i_wire_points(
        ["Annex I.11"], _VEHICLE_Q, answer
    ) == ["Annex I.19"]


def test_plain_sectioned_alias_does_not_rewrite_other_annexes() -> None:
    answer = "Annex IV point 2 covers hardware descriptions."
    assert R._deepen_one_ref("Annex IV", "What does Annex IV point 2 say?", answer) == "Annex IV.2"

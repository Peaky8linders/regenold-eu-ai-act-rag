"""R418 — the serving leg must be readable from the WIRE, not only from graph_stats.

R417 recorded ``stage2_served_by`` in ``graph_stats`` and made the route refuse to
cache a degraded serve. Both are correct, and neither was *observable* on a
deployed run: the response body carries only ``answer`` / ``references`` /
``reasoning``, so ``graph_stats`` never reaches an eval. A live audit could only
infer the leg from the ``stage2_model=`` prefix — and that inference is what
turned one Bedrock fallback on rg_010 into what looked like three independent
observations of a wrapper-served answer.

These tests pin the two halves of the fix: the route names the leg in the trace,
and the harness reads it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.regenold.run_official_batch import _provenance

REPO = Path(__file__).resolve().parents[1]


def _body(notes: list[str], **extra) -> dict:
    return {"reasoning": json.dumps({"notes": notes, **extra})}


def test_provenance_reads_the_named_leg() -> None:
    prov = _provenance(_body(["stage2_model=claude-opus-5", "stage2_served_by=primary"]))
    assert prov["stage2_served_by"] == "primary"
    assert prov["stage2_model"] == "claude-opus-5"


def test_provenance_names_a_fallback_even_though_the_model_is_also_recorded() -> None:
    """The leg is the route's own answer; the model is not a substitute for it."""
    prov = _provenance(_body(["stage2_model=qwen.qwen3-32b-v1:0", "stage2_served_by=fallback"]))
    assert prov["stage2_served_by"] == "fallback"


def test_provenance_reads_the_leg_when_the_note_precedes_the_model_note() -> None:
    """Note order must not decide whether the leg is found."""
    prov = _provenance(_body(["stage2_served_by=deterministic", "stage2_model=claude-opus-5"]))
    assert prov["stage2_served_by"] == "deterministic"
    assert prov["stage2_model"] == "claude-opus-5"


def test_provenance_defaults_the_leg_to_empty_and_stays_fail_soft() -> None:
    """An older trace (no leg note) must not invent one, and a bad body must not raise."""
    assert _provenance(_body(["stage2_model=claude-opus-5"]))["stage2_served_by"] == ""
    assert _provenance({"reasoning": "not json"}) == {}
    assert _provenance(None) == {}
    assert _provenance(_body([None, 7, "stage2_served_by=primary"]))["stage2_served_by"] == "primary"


def test_provenance_preserves_only_known_intentional_skip_reasons() -> None:
    known = _provenance(_body(["stage2_skipped_curated_authoritative"]))
    unknown = _provenance(_body(["stage2_skipped_some_new_reason"]))
    assert known["stage2_skip_reason"] == "stage2_skipped_curated_authoritative"
    assert unknown["stage2_skip_reason"] == ""


def test_provenance_carries_polish_state_for_fail_closed_scoring() -> None:
    assert _provenance(_body(["stage2_served_by=primary"], stage2_polish=True))["stage2_polish"] is True
    assert _provenance(_body(["stage2_skipped_pure_definitional"], stage2_polish=False))["stage2_skip_reason"] == "stage2_skipped_pure_definitional"


def test_hard_capture_keeps_each_turns_provenance() -> None:
    import io

    from evals.regenold.official_batch import OfficialRow
    from evals.regenold.run_official_batch import _run_hard

    # A synthetic row: the real batch is gitignored competition data, so a test
    # that loaded it could not run on a clean clone.
    row = OfficialRow(
        id="rg_synth",
        question="Which provision governs the registration of a high-risk system?",
        question_hash="synthetic",
        jul07_answer="",
        jul07_refs=(),
        jul07_confidence=None,
        jul07_retrieval_path="",
        jul07_scope_reason="",
    )
    calls = iter(
        [
            {
                **_body(["stage2_served_by=primary"], stage2_polish=True),
                "answer": "A complete first answer.",
                "references": ["Article 49.1"],
            },
            {
                **_body(["stage2_served_by=deterministic"], stage2_polish=False),
                "answer": "A complete pushback answer.",
                "references": ["Article 49.1"],
            },
        ]
    )

    def poster(*_args, **_kwargs):
        return next(calls), 5.0, 200, None, 1, None

    captured = _run_hard([row], poster, "local", "key", 30, io.StringIO())[0]
    assert captured["turn1_provenance"]["stage2_served_by"] == "primary"
    assert captured["pushback_provenance"]["stage2_served_by"] == "deterministic"
    assert captured["graded_turn"] == "pushback"
    assert captured["provenance"] == captured["pushback_provenance"]


def test_skip_reason_vocabularies_agree() -> None:
    from evals.official.score_arm import _INTENTIONAL_STAGE2_SKIPS
    from evals.regenold.run_official_batch import _STAGE2_SKIP_REASONS

    assert _STAGE2_SKIP_REASONS == _INTENTIONAL_STAGE2_SKIPS


@pytest.mark.parametrize(
    ("question", "skip_reason", "served_by", "polish", "dispatches"),
    [
        (
            "What are the guiding principles established by the AI Act?",
            "stage2_skipped_curated_authoritative",
            "",
            False,
            0,
        ),
        (
            "What is a deployer under the EU AI Act?",
            "stage2_skipped_pure_definitional",
            "",
            False,
            0,
        ),
        (
            "What does Article 4 of the EU AI Act require regarding AI literacy?",
            "",
            "primary",
            True,
            1,
        ),
    ],
)
def test_the_real_route_emits_the_skip_reasons_the_scorer_accepts(
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    skip_reason: str,
    served_by: str,
    polish: bool,
    dispatches: int,
) -> None:
    """Every skip reason the scorer accepts is one the engine really writes.

    Driven through the real route with Stage-2 live and its transport faked, so
    the notes are the engine's own. A skip reason that no emitter produces would
    leave every curated or definitional row refused by the scorer.
    """
    from app.config import settings
    from app.engines import _graph_rag_impl as impl
    from app.routes.regenold import _ENGINE_CACHE
    from evals.official.score_arm import _stage2_row_rejection_reason
    from evals.regenold.runner_v2 import _post_local

    monkeypatch.setattr(settings.regenold, "api_key", settings.regenold.api_key)
    for name, value in (
        ("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper"),
        ("OPENAI_API_BASE", "http://127.0.0.1:1/v1"),
        ("OPENAI_API_KEY", "dummy"),
        ("REGENOLD_EXTERNAL_EMBEDDINGS", "0"),
        ("REGENOLD_COHERE_RERANK", "0"),
        ("REGENOLD_FUSION_STAGE2", "0"),
    ):
        monkeypatch.setenv(name, value)
    sent: list[dict] = []

    def fake_transport(**kwargs):
        sent.append(kwargs)
        return "Article 4 requires providers and deployers to ensure AI literacy."

    monkeypatch.setattr(impl, "_openai_wrapper_complete_for_graph_rag", fake_transport)
    _ENGINE_CACHE.clear()
    try:
        body, _ms, status, _err, _att, _ = _post_local(
            "local", None, [{"role": "user", "content": question}], 120
        )
    finally:
        _ENGINE_CACHE.clear()

    assert status == 200
    provenance = _provenance(body)
    assert len(sent) == dispatches
    assert provenance["stage2_skip_reason"] == skip_reason
    assert provenance["stage2_served_by"] == served_by
    assert provenance["stage2_polish"] is polish
    assert _stage2_row_rejection_reason({"provenance": provenance}) is None


def test_score_cache_key_separates_answer_turn_even_for_identical_text() -> None:
    from evals.official import score_arm

    first = {"id": "rg_037", "answer": "same", "answer_turn": "turn1"}
    second = {"id": "rg_037", "answer": "same", "answer_turn": "pushback"}
    assert score_arm._row_cache_key(first, "judge") != score_arm._row_cache_key(second, "judge")


def test_route_records_the_leg_for_both_cache_paths() -> None:
    """Wired-in check: the note is emitted once, from the resolved response.

    Placed after the cache lookup, so a cache HIT names the leg of the answer it
    replays rather than going silent — the exact blindness the R417 cache-skip
    note was added to cure.
    """
    src = (REPO / "app/routes/regenold.py").read_text(encoding="utf-8")
    assert 'f"stage2_served_by={_served_leg}"' in src
    emit = src.index('f"stage2_served_by={_served_leg}"')
    lookup = src.index("rag_res = _ENGINE_CACHE.get(cache_key)")
    assert lookup < emit, "the leg note must read the RESOLVED response, not the pre-lookup one"

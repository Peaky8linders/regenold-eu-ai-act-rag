"""R415 — the single-turn full-system lever's SCOPE, measured at the provider seam.

``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`` is default ON (R412). Its claim is
that it cannot change a multi-turn request, and the scope it relies on is
``history_turn_count <= 1`` — but ``history_turn_count`` is not one value per
modality. The ROUTE derives it as ``max(0, user+assistant messages - 1)``, so:

* a first ask (1 message) reads **0**,
* a two-message request reads **1**,
* a normal follow-up (user / assistant / user) reads **2**,
* a direct engine caller that omits the field gets ``GraphRAGRequest``'s default
  **1**,
* the official hard final (10 messages) reads **9**, and the pushback 9 or 10.

``None`` means "modality unknown" and is never single-turn — that is what keeps
the Stage-1 parser and the auxiliary passes out of the lever.

These tests read the REAL substitution, at the seam that carries the truth
(``OpenAIWrapperRequest.system``). Patching ``_openai_wrapper_complete_for_graph_rag``
instead would record the PRE-substitution text and report the two arms as
identical — the trap ``evals.harness.gate_validity`` documents and the first cut
of the R415 probe walked into.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.engines import _graph_rag_impl as impl

FLAG = "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN"
#: Longer than the 1000-char threshold that decides persona vs full system.
LONG_SYSTEM = "S" * 5000
PERSONA_LEN = 61
FULL_LEN = 5000


class _Provider:
    """Records what the model would actually receive."""

    def __init__(self) -> None:
        self.systems: list[str] = []

    def complete(self, request, *a: Any, **k: Any):  # noqa: ANN002, ANN003
        self.systems.append(str(getattr(request, "system", "") or ""))
        return SimpleNamespace(
            error=None,
            text="Under Article 11 the provider must draw up technical documentation.",
            thinking="",
            finish_reason="stop",
            model="test",
            usage=None,
            latency_ms=1,
            headers=None,
        )


@pytest.fixture()
def provider(monkeypatch: pytest.MonkeyPatch) -> _Provider:
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider

    rec = _Provider()
    singleton = get_openai_wrapper_provider()
    monkeypatch.setattr(singleton, "complete", rec.complete)
    return rec


def _system_for(
    provider: _Provider, turns: int | None, *, on: bool
) -> str:
    import os

    os.environ[FLAG] = "1" if on else "0"
    before = len(provider.systems)
    impl._openai_wrapper_complete_for_graph_rag(
        system=LONG_SYSTEM,
        user="ANSWER CONTRACT",
        max_tokens=16,
        temperature=0.0,
        stage_name="Stage 2 (Polishing)",
        history_turn_count=turns,
    )
    assert len(provider.systems) == before + 1
    return provider.systems[-1]


class TestLeverScope:
    @pytest.mark.parametrize("turns", [0, 1])
    def test_single_turn_shaped_asks_get_the_full_system(
        self, provider: _Provider, monkeypatch: pytest.MonkeyPatch, turns: int
    ) -> None:
        monkeypatch.setenv(FLAG, "1")
        assert len(_system_for(provider, turns, on=True)) == FULL_LEN

    @pytest.mark.parametrize("turns", [2, 9])
    def test_multi_turn_asks_are_untouched_by_the_lever(
        self, provider: _Provider, monkeypatch: pytest.MonkeyPatch, turns: int
    ) -> None:
        # The whole point: the flag's two arms dispatch the SAME bytes here.
        monkeypatch.setenv(FLAG, "1")
        on = _system_for(provider, turns, on=True)
        monkeypatch.setenv(FLAG, "0")
        off = _system_for(provider, turns, on=False)
        assert on == off
        assert len(on) == PERSONA_LEN

    def test_unknown_modality_is_never_single_turn(
        self, provider: _Provider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``None`` is what the Stage-1 parser and every auxiliary pass leave, so
        # the lever can never reach them.
        monkeypatch.setenv(FLAG, "1")
        assert len(_system_for(provider, None, on=True)) == PERSONA_LEN

    def test_scope_is_the_documented_threshold_not_a_guess(
        self, provider: _Provider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        differ = []
        for turns in (None, 0, 1, 2, 9):
            monkeypatch.setenv(FLAG, "1")
            on = _system_for(provider, turns, on=True)
            monkeypatch.setenv(FLAG, "0")
            off = _system_for(provider, turns, on=False)
            if on != off:
                differ.append(turns)
        # The differ-set: first ask (0) and two-message request (1), not the
        # ordinary three-message follow-up after a completed prior exchange (2).
        assert differ == [0, 1]

    def test_flag_off_reproduces_the_persona_everywhere(
        self, provider: _Provider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(FLAG, "0")
        for turns in (None, 0, 1, 2, 9):
            assert len(_system_for(provider, turns, on=False)) == PERSONA_LEN

    def test_a_short_system_is_passed_through_either_way(
        self, provider: _Provider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The persona substitution only applies above the 1000-char threshold.
        monkeypatch.setenv(FLAG, "0")
        impl._openai_wrapper_complete_for_graph_rag(
            system="short system",
            user="ANSWER CONTRACT",
            max_tokens=16,
            temperature=0.0,
            stage_name="Stage 1 (Scope & Extraction)",
            history_turn_count=None,
        )
        assert provider.systems[-1] == "short system"

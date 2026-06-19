"""R131 — deterministic de-noiser salvage for a self-contained final turn.

Root cause (production "Intent & Query denoiser skipped (provider_error)"):
a multi-turn conversation whose final, self-contained question ("Does the
technical documentation of a high-risk AI system require to provide
specifications regarding the required hardware?") followed prior turns that
discussed Article 86 / Article 27. The LLM query de-noiser — which rewrites
the follow-up into a standalone query, stripping that prior-turn
contamination — failed (Groq TPD cap / tunnel timeout) with NO fallback, so
the flattened history bled Article 86 / 27 into retrieval, scope anchors, and
the per-reference description pass, and the answer led with those tangential
provisions instead of Article 11 + Annex IV.

R131 salvages the common case deterministically: on LLM-de-noiser FAILURE, if
the final user turn is self-contained, process it as a single-turn question
(clean engine query + scope on the live turn alone + no assistant-anchor
inheritance). Gated so that ``cli`` / no-provider (the davidath bench) and
coreferent follow-ups are byte-identical to the prior behaviour.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.routes import regenold as r


# ── _live_turn_is_self_contained ─────────────────────────────────────────


def test_self_contained_true_for_techdoc_question() -> None:
    q = (
        "Does the technical documentation of a high-risk AI system require to "
        "provide specifications regarding the required hardware?"
    )
    assert r._live_turn_is_self_contained(q) is True


@pytest.mark.parametrize(
    "q",
    [
        "Are these checks continuous?",            # leading coreference
        "What about deployers?",                   # short coreferent
        "And if it is high-risk?",                 # leading 'and if'
        "Does it still apply to that system?",     # mid coref markers
        "Yes please.",                              # too short
        "Tell me more.",                            # too short, no anchor
    ],
)
def test_self_contained_false_for_coreferent_or_short(q: str) -> None:
    assert r._live_turn_is_self_contained(q) is False


def test_self_contained_false_without_ai_act_anchor() -> None:
    # Long enough + non-coreferent, but carries no AI-Act subject of its own.
    assert (
        r._live_turn_is_self_contained(
            "Please summarise the weather forecast for tomorrow afternoon."
        )
        is False
    )


# ── env gate ─────────────────────────────────────────────────────────────


def test_salvage_enabled_default_on(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_DENOISE_SALVAGE", raising=False)
    assert r._is_denoise_salvage_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF"])
def test_salvage_disabled_by_env(monkeypatch, val: str) -> None:
    monkeypatch.setenv("REGENOLD_DENOISE_SALVAGE", val)
    assert r._is_denoise_salvage_enabled() is False


# ── _rewrite_multiturn_query salvage on provider failure ─────────────────


def _mk_msg(role: str, content: str):
    m = MagicMock()
    m.role = role
    m.content = content
    return m


_SELF_CONTAINED = (
    "Does the technical documentation of a high-risk AI system require to "
    "provide specifications regarding the required hardware?"
)


def _failing_wrapper():
    resp = MagicMock()
    resp.error = "network_error: timed out"
    resp.text = ""
    prov = MagicMock()
    prov.complete.return_value = resp
    return prov


@pytest.fixture
def force_failing_wrapper(monkeypatch):
    """Pin the de-noiser to a WIRED-but-FAILING wrapper provider, order-robust.

    The conftest pins ``REGENOLD_QUERY_DENOISER=0`` + a dead OPENAI_API_BASE,
    and pytest-randomly can leave ``GROQ_API_KEY`` / ``REGENOLD_INTENT_PROVIDER``
    set from a neighbouring test — which would steer the de-noiser onto Groq
    instead of the patched wrapper. Pin every selector so the provider-failure
    path is deterministic regardless of test order.
    """
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    import app.llm.openai_wrapper_provider as wp

    monkeypatch.setattr(wp, "is_groq_intent_provider_enabled", lambda: False)
    monkeypatch.setattr(wp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(
        wp, "get_openai_wrapper_provider", lambda: _failing_wrapper()
    )


def test_provider_failure_self_contained_salvages(
    monkeypatch, force_failing_wrapper
) -> None:
    monkeypatch.delenv("REGENOLD_DENOISE_SALVAGE", raising=False)
    out = r._rewrite_multiturn_query(
        _SELF_CONTAINED, [_mk_msg("user", "We deploy a high-risk AI system.")]
    )
    # The salvage returns the verbatim live turn.
    assert out == _SELF_CONTAINED


def test_provider_failure_coreferent_does_not_salvage(
    monkeypatch, force_failing_wrapper
) -> None:
    monkeypatch.delenv("REGENOLD_DENOISE_SALVAGE", raising=False)
    out = r._rewrite_multiturn_query(
        "Are these checks continuous?",
        [_mk_msg("user", "We deploy a high-risk AI system.")],
    )
    assert out is None


def test_provider_failure_salvage_disabled_returns_none(
    monkeypatch, force_failing_wrapper
) -> None:
    monkeypatch.setenv("REGENOLD_DENOISE_SALVAGE", "0")
    out = r._rewrite_multiturn_query(
        _SELF_CONTAINED, [_mk_msg("user", "We deploy a high-risk AI system.")]
    )
    assert out is None


def test_no_provider_does_not_salvage(monkeypatch) -> None:
    # cli / no-provider (the davidath bench): the salvage must NOT fire so the
    # multi-turn flatten stays byte-identical.
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import app.llm.openai_wrapper_provider as wp

    monkeypatch.setattr(wp, "is_openai_wrapper_enabled", lambda: False)
    out = r._rewrite_multiturn_query(
        _SELF_CONTAINED, [_mk_msg("user", "We deploy a high-risk AI system.")]
    )
    assert out is None


# ── _build_question_from_history salvaged flag ───────────────────────────


def test_flatten_salvaged_flag_on_provider_failure(
    monkeypatch, force_failing_wrapper
) -> None:
    msgs = [
        _mk_msg("user", "We deploy a high-risk AI system affecting individuals."),
        _mk_msg("assistant", "Under Article 86 ... Under Article 27, deployers ..."),
        _mk_msg("user", _SELF_CONTAINED),
    ]
    res = r._build_question_from_history(msgs)
    assert res.salvaged is True
    # The engine question is the clean live turn — no Article 86/27, no
    # "Conversation so far" history block.
    assert res[0] == _SELF_CONTAINED
    assert "Article 86" not in res[0]
    assert "Conversation so far" not in res[0]


def test_flatten_not_salvaged_for_coreferent(
    monkeypatch, force_failing_wrapper
) -> None:
    msgs = [
        _mk_msg("user", "We deploy a high-risk AI system affecting individuals."),
        _mk_msg("assistant", "Under Article 86 ... Under Article 27, deployers ..."),
        _mk_msg("user", "Are these checks continuous?"),
    ]
    res = r._build_question_from_history(msgs)
    assert res.salvaged is False
    # Coreferent follow-up keeps the concatenation path (history preserved).
    assert "Conversation so far" in res[0]


def test_flatten_not_salvaged_in_cli_mode(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import app.llm.openai_wrapper_provider as wp

    monkeypatch.setattr(wp, "is_openai_wrapper_enabled", lambda: False)
    msgs = [
        _mk_msg("user", "We deploy a high-risk AI system affecting individuals."),
        _mk_msg("assistant", "Under Article 86 ... Under Article 27, deployers ..."),
        _mk_msg("user", _SELF_CONTAINED),
    ]
    res = r._build_question_from_history(msgs)
    assert res.salvaged is False


def test_questionhistoryresult_salvaged_default_false() -> None:
    res = r.QuestionHistoryResult("q", None, "q")
    assert res.salvaged is False
    res2 = r.QuestionHistoryResult("q", None, "q", True)
    assert res2.salvaged is True

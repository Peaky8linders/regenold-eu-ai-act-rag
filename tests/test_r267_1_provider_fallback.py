"""R267.1 — provider fallback chain for the general assistant and the
multi-turn de-noiser.

Root cause fixed: Groq ``qwen/qwen3.6-27b`` has a daily tokens-per-day cap
(``api_status_429``, ``Limit 200000``). When it is exhausted the Groq-only
general assistant returned ``None`` (branded decline for every benign
off-topic question) and the de-noiser's Groq->wrapper chain fell to the
~10 s Claude Max wrapper, which the fail-fast timeout always tripped into a
``provider_error``. Both now fall through to Gemini flash / Mistral large.

These tests mock the providers so they run in the no-API-key test env.
"""
from __future__ import annotations

import pytest

import app.llm.openai_wrapper_provider as owp
import app.routes.regenold as route


class _Resp:
    def __init__(self, text: str = "", error: str | None = None,
                 finish_reason: str | None = "stop") -> None:
        self.text = text
        self.error = error
        self.finish_reason = finish_reason
        self.model = "fake"
        self.elapsed_ms = 5
        self.thinking = None


class _Prov:
    """Records every request it receives and returns a canned response."""

    def __init__(self, text: str = "", error: str | None = None,
                 finish_reason: str | None = "stop") -> None:
        self._resp = _Resp(text, error, finish_reason)
        self.calls: list = []

    def complete(self, req):  # noqa: ANN001
        self.calls.append(req)
        return self._resp


def _wire(monkeypatch, *, groq=None, gemini=None, mistral=None) -> None:
    """Enable/disable each general-assistant provider on the owp module."""
    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: groq is not None)
    if groq is not None:
        monkeypatch.setattr(owp, "get_groq_provider", lambda: groq)
    monkeypatch.setattr(owp, "is_gemini_provider_enabled", lambda: gemini is not None)
    if gemini is not None:
        monkeypatch.setattr(owp, "get_gemini_provider", lambda: gemini)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: mistral is not None)
    if mistral is not None:
        monkeypatch.setattr(owp, "get_mistral_provider", lambda: mistral)


# ── general assistant ────────────────────────────────────────────────────────

def test_groq_tpd_429_falls_through_to_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = _Prov(error="api_status_429: tokens per day (TPD): Limit 200000")
    gemini = _Prov(text="Try Da Enzo al 29 in Trastevere for classic Roman food.")
    _wire(monkeypatch, groq=groq, gemini=gemini)
    out = route._general_assistant_answer("recommend a restaurant in Rome")
    assert out is not None and "Trastevere" in out
    assert len(groq.calls) == 1  # Groq tried first
    assert len(gemini.calls) == 1  # then fell through to Gemini


def test_groq_and_gemini_fail_falls_through_to_mistral(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = _Prov(error="api_status_429")
    gemini = _Prov(error="api_status_500")
    mistral = _Prov(text="The capital of France is Paris.")
    _wire(monkeypatch, groq=groq, gemini=gemini, mistral=mistral)
    out = route._general_assistant_answer("what is the capital of France?")
    assert out is not None and "Paris" in out
    assert len(groq.calls) == len(gemini.calls) == len(mistral.calls) == 1


def test_first_success_short_circuits_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = _Prov(text="Paris.")
    gemini = _Prov(text="SHOULD NOT BE CALLED")
    _wire(monkeypatch, groq=groq, gemini=gemini)
    out = route._general_assistant_answer("capital of France?")
    assert out is not None and "Paris" in out
    assert len(groq.calls) == 1
    assert gemini.calls == []  # Groq succeeded → Gemini never reached


def test_all_providers_fail_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = _Prov(error="api_status_429")
    gemini = _Prov(error="api_status_500")
    mistral = _Prov(error="timeout")
    _wire(monkeypatch, groq=groq, gemini=gemini, mistral=mistral)
    assert route._general_assistant_answer("recommend a restaurant in Rome") is None


def test_no_provider_wired_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch)  # nothing enabled
    assert route._general_assistant_answer("hello there general") is None


def test_candidate_order_is_groq_then_gemini_then_mistral(monkeypatch: pytest.MonkeyPatch) -> None:
    """R289 re-pin — the Groq slot reads ``default_groq_model()``, not a literal.

    This assertion used to hard-code ``"qwen/qwen3.6-27b"``. R289
    (``029dcb0``, PR #301, "one Groq knob instead of nine") replaced the nine
    copies of the Groq model id with a single source of truth,
    ``openai_wrapper_provider.default_groq_model()``, whose comment records the
    deliberate change and why: *"This value has now been changed twice by
    editing NINE separate literals, and the first of those swaps took
    production down … openai/gpt-oss-120b is the value verified live on
    production at 5869eec."* R381 independently re-confirmed that the old
    ``qwen``-era ids are not resolvable on this Groq account.

    The re-pin is strictly stronger than the literal it replaces: it pins the
    provider ORDER as well as the model ids (the old assertion could not tell
    Groq-first from Gemini-first), and it pins the R289 contract itself by
    moving ``default_groq_model()`` and asserting the Groq slot follows — a
    re-introduced hard-coded literal in ``_general_llm_candidates`` now fails
    here, which the old string comparison could never detect.
    """
    from app.llm.openai_wrapper_provider import default_groq_model

    g, ge, mi = _Prov(), _Prov(), _Prov()
    _wire(monkeypatch, groq=g, gemini=ge, mistral=mi)
    monkeypatch.delenv("REGENOLD_GENERAL_MODEL_GROQ", raising=False)
    monkeypatch.delenv("REGENOLD_GROQ_DEFAULT_MODEL", raising=False)

    cands = route._general_llm_candidates()
    assert [p for p, _ in cands] == [g, ge, mi]  # Groq -> Gemini -> Mistral
    models = [m for _, m in cands]
    assert models == [default_groq_model(), "gemini-2.5-flash", "mistral-large-latest"]
    assert models[0] == "openai/gpt-oss-120b"  # the live-validated default

    # R289: the Groq slot must TRACK the single source of truth, not copy it.
    monkeypatch.setenv("REGENOLD_GROQ_DEFAULT_MODEL", "groq/sentinel-model")
    assert [m for _, m in route._general_llm_candidates()][0] == "groq/sentinel-model"


def test_think_block_stripped_then_still_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    # Qwen leaks a <think> block; validate_llm_output strips it, real answer stays.
    groq = _Prov(text="<think>let me reason</think>The capital of France is Paris.")
    _wire(monkeypatch, groq=groq)
    out = route._general_assistant_answer("capital of France?")
    assert out is not None and "Paris" in out and "<think>" not in out


# ── multi-turn de-noiser ─────────────────────────────────────────────────────

class _Msg:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


def _wire_denoiser(monkeypatch, *, groq=None, gemini=None, mistral=None,
                   wrapper=None) -> None:
    monkeypatch.setattr(owp, "is_groq_intent_provider_enabled", lambda: groq is not None)
    if groq is not None:
        monkeypatch.setattr(owp, "get_groq_intent_provider", lambda: groq)
    monkeypatch.setattr(owp, "is_gemini_provider_enabled", lambda: gemini is not None)
    if gemini is not None:
        monkeypatch.setattr(owp, "get_gemini_provider", lambda: gemini)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: mistral is not None)
    if mistral is not None:
        monkeypatch.setattr(owp, "get_mistral_provider", lambda: mistral)
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: wrapper is not None)
    if wrapper is not None:
        monkeypatch.setattr(owp, "get_openai_wrapper_provider", lambda: wrapper)


def test_denoiser_groq_429_falls_through_to_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    groq = _Prov(error="api_status_429: tokens per day (TPD)")
    gemini = _Prov(text="What are the transparency obligations for high-risk AI deployers?")
    wrapper = _Prov(text="SHOULD NOT BE REACHED")
    _wire_denoiser(monkeypatch, groq=groq, gemini=gemini, wrapper=wrapper)
    history = [
        _Msg("user", "Tell me about high-risk AI transparency."),
        _Msg("assistant", "Article 13 governs transparency for high-risk AI systems."),
    ]
    out = route._rewrite_multiturn_query("And what about the deployers of those?", history)
    assert out is not None and "deployers" in out.lower()
    assert len(groq.calls) == 1  # Groq tried first (429)
    assert len(gemini.calls) == 1  # Gemini rewrote it
    assert wrapper.calls == []  # the slow wrapper was never reached


def test_denoiser_gemini_and_mistral_are_in_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    groq = _Prov(error="api_status_429")
    gemini = _Prov(error="api_status_500")
    mistral = _Prov(text="What incident-reporting duties apply to high-risk AI providers?")
    _wire_denoiser(monkeypatch, groq=groq, gemini=gemini, mistral=mistral)
    history = [
        _Msg("user", "What are the post-market monitoring duties?"),
        _Msg("assistant", "Article 72 sets out post-market monitoring for providers."),
    ]
    out = route._rewrite_multiturn_query("And the reporting duties for those providers?", history)
    assert out is not None
    assert len(groq.calls) == len(gemini.calls) == len(mistral.calls) == 1  # full chain walked

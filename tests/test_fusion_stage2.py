"""Tests for the Mixture-of-Agents fusion Stage-2 (app/engines/fusion.py).

Hermetic — every test monkeypatches the provider getters so no network /
wrapper / Groq / Mistral call is made. Covers the env gating, the Mistral
provider wiring, panel resolution (incl. the Opus-on-complex addition), the
SELECT-not-MERGE judge prompt, and the fail-soft contract of
``fusion_complete`` (>= min drafts -> judge selects; below -> None; judge
error / empty / truncated -> None; never raises).

The judge is **Sonnet 4.6** (``claude-sonnet-4-6``) — the same model id the
``sonnet`` panel member uses — so the fake wrapper distinguishes the judge call
from the panel-draft call by the ``"FUSION JUDGE"`` marker the
``_build_judge_user`` instruction injects.
"""
from __future__ import annotations

import pytest

from app.engines import fusion
from app.llm import openai_wrapper_provider as owp
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


@pytest.fixture(autouse=True)
def _fusion_gate_all(monkeypatch):
    """R124 — the default ``REGENOLD_FUSION_GATE`` is ``complex`` (fuse only
    complex questions). The panel-mechanics tests below call
    ``fusion_complete`` WITHOUT ``complex_question=True`` and expect the panel
    to fire, so open the gate for the module by default. The dedicated gate
    tests override this with their own ``setenv`` (the test body's monkeypatch
    runs after this fixture, so it wins).

    R127 — also pin ``REGENOLD_FUSION_JUDGE=llm`` so the historical
    ``fusion_complete`` tests (which mock the wrapper judge call) keep
    exercising the Sonnet SELECT-and-polish judge. The new R127 deterministic
    DEFAULT is covered by ``TestDeterministicJudge``, whose tests override this
    with their own ``setenv`` / ``delenv``."""
    monkeypatch.setenv("REGENOLD_FUSION_GATE", "all")
    monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "llm")


# ── env gating ────────────────────────────────────────────────────────────────

def test_fusion_disabled_default_off(monkeypatch):
    # 2026-06-30 Sonnet-5-routing directive — the MoA panel is OFF by default so
    # complex questions route to a single Opus 4.8 call (not a Groq/Mistral
    # panel). Pin the new default loudly so a future revert is not silent.
    monkeypatch.delenv("REGENOLD_FUSION_STAGE2", raising=False)
    assert fusion.fusion_stage2_enabled() is False


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "FALSE", ""])
def test_fusion_disabled_by_env(monkeypatch, val):
    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", val)
    assert fusion.fusion_stage2_enabled() is False


def test_fusion_enabled_explicit_on(monkeypatch):
    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "1")
    assert fusion.fusion_stage2_enabled() is True


# ── judge model ─────────────────────────────────────────────────────────────────

def test_default_judge_is_sonnet(monkeypatch):
    monkeypatch.delenv("REGENOLD_FUSION_JUDGE_MODEL", raising=False)
    assert fusion._judge_model() == "claude-sonnet-4-6"


def test_judge_model_env_override(monkeypatch):
    monkeypatch.setenv("REGENOLD_FUSION_JUDGE_MODEL", "claude-opus-4-8")
    assert fusion._judge_model() == "claude-opus-4-8"


# ── Mistral provider wiring ─────────────────────────────────────────────────────

def test_mistral_provider_gate(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    assert owp.is_mistral_provider_enabled() is False
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-mistral-test")
    assert owp.is_mistral_provider_enabled() is True


def test_mistral_provider_singleton_base_url(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-mistral-test")
    monkeypatch.delenv("MISTRAL_API_BASE", raising=False)
    owp._reset_mistral_singleton_for_tests()
    try:
        prov = owp.get_mistral_provider()
        assert prov is owp.get_mistral_provider()  # pooled singleton
        assert prov._base_url == "https://api.mistral.ai/v1"  # noqa: SLF001
    finally:
        owp._reset_mistral_singleton_for_tests()


# ── panel resolution ─────────────────────────────────────────────────────────

def test_enabled_panel_filters_unavailable(monkeypatch):
    monkeypatch.delenv("REGENOLD_FUSION_PANEL", raising=False)
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: False)
    panel = fusion._enabled_panel()
    labels = [p[0] for p in panel]
    assert "sonnet" in labels and "groq" in labels
    assert "mistral" not in labels  # transport unavailable -> filtered


def test_enabled_panel_custom_env(monkeypatch):
    monkeypatch.setenv("REGENOLD_FUSION_PANEL", "groq, mistral")
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: True)
    panel = fusion._enabled_panel()
    labels = [p[0] for p in panel]
    assert labels == ["groq", "mistral"]  # sonnet not requested; non-complex


def test_enabled_panel_swaps_sonnet_for_opus_on_complex(monkeypatch):
    """R124 — the wrapper member is SWAPPED Sonnet→Opus 4.8 on complex (one
    wrapper-bound member, not two). Groq + Mistral stay on their own
    endpoints."""
    monkeypatch.delenv("REGENOLD_FUSION_PANEL", raising=False)
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)  # opus + sonnet
    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: True)

    simple = [p[0] for p in fusion._enabled_panel(complex_question=False)]
    assert simple == ["sonnet", "groq", "mistral"]  # Sonnet wrapper member on simple

    complex_ = [p[0] for p in fusion._enabled_panel(complex_question=True)]
    assert complex_ == ["opus", "groq", "mistral"]  # SWAP — Sonnet→Opus
    assert "sonnet" not in complex_  # swapped out, NOT added alongside (R124)
    assert ("opus", "claude-opus-4-8", "wrapper") in fusion._enabled_panel(
        complex_question=True
    )
    # Exactly ONE wrapper-bound member on complex (no Sonnet+Opus double tunnel).
    wrapper_members = [
        p for p in fusion._enabled_panel(complex_question=True) if p[2] == "wrapper"
    ]
    assert len(wrapper_members) == 1


def test_enabled_panel_swaps_only_when_sonnet_present(monkeypatch):
    """A custom panel with no sonnet still gets a frontier candidate (opus
    appended) on complex — never left without one."""
    monkeypatch.setenv("REGENOLD_FUSION_PANEL", "groq, mistral")
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: True)
    labels = [p[0] for p in fusion._enabled_panel(complex_question=True)]
    assert labels == ["groq", "mistral", "opus"]  # opus appended (nothing to swap)


def test_enabled_panel_no_double_opus_when_configured(monkeypatch):
    """Operator-listed opus is not duplicated on complex."""
    monkeypatch.setenv("REGENOLD_FUSION_PANEL", "sonnet, opus")
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
    labels = [p[0] for p in fusion._enabled_panel(complex_question=True)]
    assert labels == ["sonnet", "opus"]  # opus present once, not appended again


# ── judge prompt is SELECT, not MERGE ───────────────────────────────────────────

def test_judge_user_is_select_not_merge():
    drafts = [("sonnet", "draft A"), ("groq", "draft B"), ("mistral", "draft C")]
    judge_user = fusion._build_judge_user("QUESTION: x", drafts)
    # Select-and-tighten contract.
    assert "CHOOSE THE SINGLE BEST DRAFT" in judge_user
    assert "Do NOT blend" in judge_user
    assert "do NOT make the chosen draft longer" in judge_user
    # Conciseness is an explicit ranked criterion (the bug this round fixes).
    assert "CONCISENESS" in judge_user
    assert "prefer the SHORTEST" in judge_user
    # The drafts are present + generically labelled.
    assert "DRAFT 1:" in judge_user and "DRAFT 3:" in judge_user
    assert "draft A" in judge_user and "draft C" in judge_user
    # The old merge instruction must be gone.
    assert "include any correct point one draft raised" not in judge_user
    # Carries the JUDGE marker the fake wrapper keys on.
    assert "FUSION JUDGE" in judge_user


# ── fusion_complete fail-soft contract ──────────────────────────────────────────

class _FakeProvider:
    """A pooled-provider stand-in. ``script`` maps model id -> response fn."""

    def __init__(self, script):
        self._script = script

    def complete(self, req):
        fn = self._script.get(req.model)
        if fn is None:
            return OpenAIWrapperResponse(error="no_script", model=req.model)
        return fn(req)


def _sonnet_script(*, panel_text: str, judge_resp: OpenAIWrapperResponse):
    """Sonnet (``claude-sonnet-4-6``) serves BOTH the panel draft AND the judge.

    The judge call carries the ``"FUSION JUDGE"`` marker in its user message;
    the panel-draft call does not.
    """
    def _fn(req):
        if "FUSION JUDGE" in (req.user or ""):
            return judge_resp
        return OpenAIWrapperResponse(text=panel_text)

    return _fn


def _wire_three_transports(monkeypatch, *, wrapper, groq, mistral):
    """Make sonnet/groq/mistral the live panel + route the judge."""
    monkeypatch.delenv("REGENOLD_FUSION_PANEL", raising=False)
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "get_openai_wrapper_provider", lambda: wrapper)
    monkeypatch.setattr(owp, "get_groq_provider", lambda: groq)
    monkeypatch.setattr(owp, "get_mistral_provider", lambda: mistral)
    # Avoid the heavy graph_rag import in the truncation check.
    monkeypatch.setattr(fusion, "_looks_truncated", lambda _t: False)


def test_fusion_complete_happy_path(monkeypatch):
    # Sonnet (wrapper) is BOTH a panel member AND the judge — keyed on the
    # FUSION JUDGE marker so the judge's SELECTED final answer reaches the wire.
    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _sonnet_script(
            panel_text="Article 50 requires the deployer to inform exposed persons.",
            judge_resp=OpenAIWrapperResponse(
                text="Article 50 requires the deployer to inform exposed persons "
                     "that they are interacting with an AI system."
            ),
        ),
    })
    groq = _FakeProvider({
        "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(
            text="Deployers must inform people under Article 50."
        )
    })
    mistral = _FakeProvider({
        "mistral-large-latest": lambda r: OpenAIWrapperResponse(
            text="Article 50 transparency applies to the deployer."
        )
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=groq, mistral=mistral)

    out = fusion.fusion_complete(
        system="SYS", user="QUESTION: x\n\nEU AI ACT REFERENCES:\n- Article 50",
        max_tokens=512,
    )
    assert out is not None
    # The judge's selected final answer (NOT a raw merge of the three drafts).
    assert "Article 50" in out
    assert out.startswith("Article 50 requires the deployer")


def test_fusion_complete_insufficient_live_panel_returns_none(monkeypatch):
    # Only the wrapper transport is live -> 1 panel member < min 2 -> None.
    monkeypatch.delenv("REGENOLD_FUSION_PANEL", raising=False)
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_groq_provider_enabled", lambda: False)
    monkeypatch.setattr(owp, "is_mistral_provider_enabled", lambda: False)
    out = fusion.fusion_complete(system="SYS", user="QUESTION: x", max_tokens=512)
    assert out is None


def test_fusion_complete_too_few_drafts_returns_none(monkeypatch):
    # Panel is live but every member errors -> 0 drafts < min -> None.
    err = _FakeProvider({})  # every model -> "no_script" error
    _wire_three_transports(monkeypatch, wrapper=err, groq=err, mistral=err)
    out = fusion.fusion_complete(system="SYS", user="QUESTION: x", max_tokens=512)
    assert out is None


def test_fusion_complete_judge_error_returns_none(monkeypatch):
    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _sonnet_script(
            panel_text="draft A",
            judge_resp=OpenAIWrapperResponse(error="api_status_500"),
        ),
    })
    ok = _FakeProvider({
        "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(text="draft B"),
        "mistral-large-latest": lambda r: OpenAIWrapperResponse(text="draft C"),
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=ok, mistral=ok)
    out = fusion.fusion_complete(system="SYS", user="QUESTION: x", max_tokens=512)
    assert out is None  # judge failed -> fall through to single-provider path


def test_fusion_complete_judge_empty_returns_none(monkeypatch):
    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _sonnet_script(
            panel_text="draft A",
            judge_resp=OpenAIWrapperResponse(text="   "),
        ),
    })
    ok = _FakeProvider({
        "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(text="draft B"),
        "mistral-large-latest": lambda r: OpenAIWrapperResponse(text="draft C"),
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=ok, mistral=ok)
    assert fusion.fusion_complete(system="SYS", user="Q", max_tokens=512) is None


def test_fusion_complete_judge_truncated_returns_none(monkeypatch):
    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _sonnet_script(
            panel_text="draft A",
            judge_resp=OpenAIWrapperResponse(
                text="Article 50 requires", finish_reason="length"
            ),
        ),
    })
    ok = _FakeProvider({
        "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(text="draft B"),
        "mistral-large-latest": lambda r: OpenAIWrapperResponse(text="draft C"),
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=ok, mistral=ok)
    assert fusion.fusion_complete(system="SYS", user="Q", max_tokens=512) is None


def test_fusion_complete_never_raises(monkeypatch):
    class _Boom:
        def complete(self, req):
            raise RuntimeError("transport blew up")

    boom = _Boom()
    _wire_three_transports(monkeypatch, wrapper=boom, groq=boom, mistral=boom)
    # Panel members raise -> caught per-member -> 0 drafts -> None, no exception.
    assert fusion.fusion_complete(system="SYS", user="Q", max_tokens=512) is None


def test_fusion_complete_complex_adds_opus_panel_member(monkeypatch):
    """On a complex question, Opus 4.8 is a panel candidate the judge can pick."""
    seen_models: list[str] = []

    def _track(req):
        seen_models.append(req.model)
        if "FUSION JUDGE" in (req.user or ""):
            return OpenAIWrapperResponse(text="Article 6 classifies the system as high-risk.")
        return OpenAIWrapperResponse(text=f"draft from {req.model}")

    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _track,
        "claude-opus-4-8": _track,
    })
    groq = _FakeProvider({
        "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(text="draft groq"),
    })
    mistral = _FakeProvider({
        "mistral-large-latest": lambda r: OpenAIWrapperResponse(text="draft mistral"),
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=groq, mistral=mistral)

    out = fusion.fusion_complete(
        system="SYS", user="QUESTION: x", max_tokens=512, complex_question=True
    )
    assert out is not None
    assert "claude-opus-4-8" in seen_models  # opus answered as a panel member
    assert "claude-sonnet-4-6" in seen_models  # sonnet judged (FUSION JUDGE call)


# ── cache-key invalidation ──────────────────────────────────────────────────────

def test_engine_cache_key_includes_fusion_flag(monkeypatch):
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "1")
    k_on = _engine_cache_key("q", None)
    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
    k_off = _engine_cache_key("q", None)
    assert k_on != k_off  # flipping fusion invalidates the cache identity


def test_engine_cache_key_includes_judge_model(monkeypatch):
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv("REGENOLD_FUSION_JUDGE_MODEL", "claude-opus-4-8")
    k_a = _engine_cache_key("q", None)
    monkeypatch.setenv("REGENOLD_FUSION_JUDGE_MODEL", "claude-sonnet-4-6")
    k_b = _engine_cache_key("q", None)
    assert k_a != k_b


def test_engine_cache_key_includes_fusion_gate(monkeypatch):
    """R124 — flipping the fusion gate flips the cached answer (panel+judge vs
    single-Sonnet polish), so it must invalidate the cache identity."""
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv("REGENOLD_FUSION_GATE", "complex")
    k_complex = _engine_cache_key("q", None)
    monkeypatch.setenv("REGENOLD_FUSION_GATE", "all")
    k_all = _engine_cache_key("q", None)
    assert k_complex != k_all


# ── R124 — fusion gate (when the panel fires) ───────────────────────────────────

def test_fusion_gate_default_is_complex(monkeypatch):
    monkeypatch.delenv("REGENOLD_FUSION_GATE", raising=False)
    assert fusion.fusion_gate() == "complex"


@pytest.mark.parametrize(
    "val,expected",
    [
        ("complex", "complex"), ("all", "all"), ("off", "off"),
        ("ALL", "all"), (" off ", "off"),
        ("bogus", "complex"), ("", "complex"),  # unknown / empty → complex
    ],
)
def test_fusion_gate_values(monkeypatch, val, expected):
    monkeypatch.setenv("REGENOLD_FUSION_GATE", val)
    assert fusion.fusion_gate() == expected


def test_fusion_complete_gate_complex_skips_simple(monkeypatch):
    """Default gate=complex: a SIMPLE question returns None (caller runs the
    cheaper single-Sonnet polish) — the panel + judge never fire."""
    monkeypatch.setenv("REGENOLD_FUSION_GATE", "complex")
    called = {"complete": 0}

    class _Track:
        def complete(self, req):
            called["complete"] += 1
            return OpenAIWrapperResponse(text="should not be called")

    _wire_three_transports(monkeypatch, wrapper=_Track(), groq=_Track(), mistral=_Track())
    out = fusion.fusion_complete(
        system="SYS", user="QUESTION: x", max_tokens=512, complex_question=False
    )
    assert out is None
    assert called["complete"] == 0  # no panel / judge wrapper calls at all


def test_fusion_complete_gate_complex_fires_complex(monkeypatch):
    """Default gate=complex: a COMPLEX question DOES fuse."""
    monkeypatch.setenv("REGENOLD_FUSION_GATE", "complex")
    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _sonnet_script(
            panel_text="draft", judge_resp=OpenAIWrapperResponse(text="Final selected answer."),
        ),
        "claude-opus-4-8": lambda r: OpenAIWrapperResponse(text="opus draft"),
    })
    ok = _FakeProvider({
        "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(text="groq draft"),
        "mistral-large-latest": lambda r: OpenAIWrapperResponse(text="mistral draft"),
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=ok, mistral=ok)
    out = fusion.fusion_complete(
        system="SYS", user="QUESTION: x", max_tokens=512, complex_question=True
    )
    assert out == "Final selected answer."


def test_fusion_complete_gate_all_fires_on_simple(monkeypatch):
    """gate=all (R123): fuse even a simple question."""
    monkeypatch.setenv("REGENOLD_FUSION_GATE", "all")
    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _sonnet_script(
            panel_text="draft", judge_resp=OpenAIWrapperResponse(text="Selected."),
        ),
    })
    ok = _FakeProvider({
        "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(text="b"),
        "mistral-large-latest": lambda r: OpenAIWrapperResponse(text="c"),
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=ok, mistral=ok)
    out = fusion.fusion_complete(
        system="SYS", user="QUESTION: x", max_tokens=512, complex_question=False
    )
    assert out == "Selected."


def test_fusion_complete_gate_off_never_fires(monkeypatch):
    """gate=off: never fuse, even on a complex question."""
    monkeypatch.setenv("REGENOLD_FUSION_GATE", "off")
    boom = _FakeProvider({})
    _wire_three_transports(monkeypatch, wrapper=boom, groq=boom, mistral=boom)
    out = fusion.fusion_complete(
        system="SYS", user="Q", max_tokens=512, complex_question=True
    )
    assert out is None


# ── R124 — per-transport fast timeout ───────────────────────────────────────────

def test_fast_timeout_default(monkeypatch):
    monkeypatch.delenv("REGENOLD_FUSION_FAST_TIMEOUT", raising=False)
    assert fusion._fast_timeout_seconds() == 25.0


def test_fast_timeout_env_override(monkeypatch):
    monkeypatch.setenv("REGENOLD_FUSION_FAST_TIMEOUT", "12.5")
    assert fusion._fast_timeout_seconds() == 12.5


def test_fast_timeout_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("REGENOLD_FUSION_FAST_TIMEOUT", "not-a-number")
    assert fusion._fast_timeout_seconds() == 25.0


def test_panel_members_get_per_transport_timeout(monkeypatch):
    """The non-wrapper members (groq/mistral) get the fast timeout; the
    wrapper member gets the full wrapper timeout."""
    monkeypatch.setenv("REGENOLD_FUSION_GATE", "all")
    monkeypatch.setenv("REGENOLD_FUSION_TIMEOUT", "60")
    monkeypatch.setenv("REGENOLD_FUSION_FAST_TIMEOUT", "20")
    seen: dict[str, float] = {}

    def _capture(label, model, transport, *, system, user, max_tokens,
                 temperature, timeout, thinking_budget=0):
        seen[transport] = timeout
        return label, f"draft from {label}", ""

    monkeypatch.setattr(fusion, "_one_candidate", _capture)
    wrapper = _FakeProvider({
        "claude-sonnet-4-6": _sonnet_script(
            panel_text="x", judge_resp=OpenAIWrapperResponse(text="final"),
        ),
    })
    _wire_three_transports(monkeypatch, wrapper=wrapper, groq=wrapper, mistral=wrapper)
    fusion.fusion_complete(system="SYS", user="Q", max_tokens=512, complex_question=False)
    assert seen.get("wrapper") == 60.0
    assert seen.get("groq") == 20.0
    assert seen.get("mistral") == 20.0


# ── R127 — deterministic SELECT judge (default; $0, no extra tunnel call) ─────

class TestDeterministicJudge:
    def test_default_judge_mode_is_deterministic(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_FUSION_JUDGE", raising=False)
        assert fusion.fusion_judge_mode() == "deterministic"

    def test_judge_mode_llm_override(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "llm")
        assert fusion.fusion_judge_mode() == "llm"

    def test_judge_mode_unknown_falls_back_deterministic(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "banana")
        assert fusion.fusion_judge_mode() == "deterministic"

    def test_prefers_wrapper_draft_on_tie(self):
        # Same grounding (all cite Article 50) → the wrapper (Claude) draft
        # wins the tie-break, keeping the wire prose on the Max subscription.
        user = "QUESTION: x\n\nEU AI ACT REFERENCES:\n- Article 50"
        drafts = [
            ("groq", "Article 50 transparency applies to the deployer here."),
            ("sonnet", "Article 50 requires the deployer to inform exposed persons."),
            ("mistral", "Article 50 obliges deployers to disclose AI use clearly."),
        ]
        assert fusion._deterministic_judge(user, drafts) == (
            "Article 50 requires the deployer to inform exposed persons."
        )

    def test_penalises_hallucinated_ref_over_wrapper_bonus(self):
        # The wrapper draft cites a NON-retrieved Article 99 (-3.0) which beats
        # its +1.5 wrapper bonus, so the clean Groq draft wins.
        user = "QUESTION: x\n\nEU AI ACT REFERENCES:\n- Article 50"
        drafts = [
            ("sonnet", "Article 99 sets the penalties and Article 50 transparency applies here."),
            ("groq", "Article 50 requires the deployer to inform exposed persons of AI use."),
        ]
        assert fusion._deterministic_judge(user, drafts).startswith(
            "Article 50 requires"
        )

    def test_drops_truncated_drafts(self, monkeypatch):
        monkeypatch.setattr(
            fusion, "_looks_truncated", lambda t: t.startswith("Article 50 requires the")
        )
        user = "QUESTION: x\n\nEU AI ACT REFERENCES:\n- Article 50"
        drafts = [
            ("sonnet", "Article 50 requires the"),  # truncated → skipped
            ("groq", "Article 50 obliges deployers to inform exposed persons of AI use."),
        ]
        assert fusion._deterministic_judge(user, drafts).startswith("Article 50 obliges")

    def test_all_unusable_returns_none(self, monkeypatch):
        monkeypatch.setattr(fusion, "_looks_truncated", lambda _t: True)
        assert fusion._deterministic_judge("u", [("sonnet", "x"), ("groq", "y")]) is None

    def test_fusion_complete_deterministic_makes_no_judge_call(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "deterministic")

        def _sonnet_panel_only(req):
            # A judge call would carry the FUSION JUDGE marker — must NOT happen.
            assert "FUSION JUDGE" not in (req.user or ""), "deterministic mode must not call the LLM judge"
            return OpenAIWrapperResponse(
                text="Article 50 requires the deployer to inform exposed persons."
            )

        wrapper = _FakeProvider({"claude-sonnet-4-6": _sonnet_panel_only})
        ok = _FakeProvider({
            "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(
                text="Groq draft about Article 50 transparency here."
            ),
            "mistral-large-latest": lambda r: OpenAIWrapperResponse(
                text="Mistral draft about Article 50 transparency here."
            ),
        })
        _wire_three_transports(monkeypatch, wrapper=wrapper, groq=ok, mistral=ok)
        out = fusion.fusion_complete(
            system="SYS",
            user="QUESTION: x\n\nEU AI ACT REFERENCES:\n- Article 50",
            max_tokens=512,
        )
        # Wrapper (sonnet) panel draft is preferred (tie-break) + returned verbatim.
        assert out == "Article 50 requires the deployer to inform exposed persons."

    def test_engine_cache_key_includes_judge_mode(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "deterministic")
        k_det = _engine_cache_key("q", None)
        monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "llm")
        k_llm = _engine_cache_key("q", None)
        assert k_det != k_llm


# ── R131.3 — real Opus extended-thinking surfaced on the fusion path ─────────


class TestR131_3FusionThinking:
    """The wrapper-bound (Opus) panel member requests extended thinking on a
    complex question and its real chain-of-thought is recorded into the
    reasoning trace so ?include_reasoning=true + the UI 🧠 panel show genuine
    model reasoning (previously EMPTY on the fusion/deterministic-judge path)."""

    def test_opus_thinking_recorded_into_trace(self, monkeypatch):
        from app.config import settings
        from app.integrations.regenold import reasoning_trace as rt

        # Production default judge (R127): deterministic SELECT, no wrapper
        # judge round-trip — the opus-only fake serves the panel draft cleanly,
        # and the thinking-record fires before the judge branch regardless.
        monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "deterministic")
        orig = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_thinking_tokens = 1024
        seen_headers: dict[str, str] = {}

        def _opus_panel(req):
            seen_headers.update(req.extra_headers or {})
            return OpenAIWrapperResponse(
                text="Article 51 classifies a GPAI model as systemic risk at "
                     "10^25 FLOPs.",
                thinking="Reasoning: the question asks about GPAI systemic risk; "
                         "Article 51 sets the 10^25 FLOPs threshold and the "
                         "Commission designation route.",
                model="claude-opus-4-8",
            )

        wrapper = _FakeProvider({"claude-opus-4-8": _opus_panel})
        groq = _FakeProvider({
            "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(
                text="GPAI is systemic under Article 51."
            )
        })
        mistral = _FakeProvider({
            "mistral-large-latest": lambda r: OpenAIWrapperResponse(
                text="Article 51 governs systemic GPAI."
            )
        })
        _wire_three_transports(monkeypatch, wrapper=wrapper, groq=groq, mistral=mistral)

        trace = rt.activate()
        try:
            out = fusion.fusion_complete(
                system="SYS",
                user="Q: GPAI systemic?\n\nEU AI ACT REFERENCES:\n- Article 51",
                max_tokens=512,
                complex_question=True,
            )
            thinking_blob = dict(trace.llm_thinking)
        finally:
            rt.deactivate()
            settings.graph_rag.complex_thinking_tokens = orig

        assert out is not None
        # The wrapper (Opus) member was asked for extended thinking.
        assert seen_headers.get("X-Claude-Max-Thinking-Tokens") == "1024"
        # The REAL Opus chain-of-thought is recorded under a Fusion-panel stage.
        assert any("Fusion panel" in stage for stage in thinking_blob), thinking_blob
        assert any("Reasoning:" in txt for txt in thinking_blob.values()), thinking_blob

    def test_no_thinking_header_when_budget_zero(self, monkeypatch):
        """Budget 0 → no header on the wrapper member; trace thinking stays empty."""
        from app.config import settings
        from app.integrations.regenold import reasoning_trace as rt

        monkeypatch.setenv("REGENOLD_FUSION_JUDGE", "deterministic")
        orig = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_thinking_tokens = 0
        seen_headers: dict[str, str] = {}

        def _opus_panel(req):
            seen_headers.update(req.extra_headers or {})
            return OpenAIWrapperResponse(text="Art 51 systemic GPAI.", model="claude-opus-4-8")

        wrapper = _FakeProvider({"claude-opus-4-8": _opus_panel})
        groq = _FakeProvider({
            "llama-3.3-70b-versatile": lambda r: OpenAIWrapperResponse(text="Art 51.")
        })
        mistral = _FakeProvider({
            "mistral-large-latest": lambda r: OpenAIWrapperResponse(text="Art 51.")
        })
        _wire_three_transports(monkeypatch, wrapper=wrapper, groq=groq, mistral=mistral)

        trace = rt.activate()
        try:
            out = fusion.fusion_complete(
                system="SYS", user="Q\n\nEU AI ACT REFERENCES:\n- Article 51",
                max_tokens=512, complex_question=True,
            )
            thinking_blob = dict(trace.llm_thinking)
        finally:
            rt.deactivate()
            settings.graph_rag.complex_thinking_tokens = orig

        assert out is not None
        assert "X-Claude-Max-Thinking-Tokens" not in seen_headers
        assert thinking_blob == {}

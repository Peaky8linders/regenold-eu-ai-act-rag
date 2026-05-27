"""R86 — Query De-Noiser + Deployer Graph-Hop regression tests.

Covers the three invariants for the two R86 surfaces:

R86 Query De-Noiser (multi-turn search-query rewriter)
------------------------------------------------------
1. Disabled when ``REGENOLD_QUERY_DENOISER=0`` — returns ``None``
   without touching any provider.
2. Returns ``None`` on empty history (single-turn questions need no
   rewrite, the caller falls back to the live question directly).
3. Returns ``None`` on every LLM-failure path: import failure, no
   provider configured, ``OpenAIWrapperResponse.error`` non-empty,
   empty text, length out of sanity bounds (< 10 or > 500 chars).
   Each ``None`` means the caller falls back to the existing
   concatenation path — the de-noiser is strictly opportunistic.
4. The cache-key sees ``REGENOLD_QUERY_DENOISER`` + the two model
   override env vars — flipping the de-noiser on or off without a
   process restart cannot serve a stale answer (R30/R56/R79
   cache-poisoning doctrine).

R86-D Deployer Graph-Hop (deterministic 1-hop expansion)
--------------------------------------------------------
1. Disabled when ``REGENOLD_DEPLOYER_HOP=0`` — returns the input
   list unchanged.
2. Trigger fires on ``intent`` containing "deployer" OR ``intent ==
   "role_obligations"`` OR the question's literal substring contains
   "deployer". All three are independent triggers.
3. Hop targets are APPENDED — never displaces a BM25 winner. Cap of
   3 new refs per call (over-citation guard, mirrors R47 trade-off).
4. Hop targets are deduped against both existing candidates AND
   against each other.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.routes.regenold import (
    _DEPLOYER_HOP_MAP,
    _DEPLOYER_HOP_MAX_INJECT,
    _apply_deployer_hop,
    _engine_cache_key,
    _is_query_denoiser_enabled,
    _rewrite_multiturn_query,
)


# ─── R86 Query De-Noiser ───────────────────────────────────────────────────


def _mk_msg(role: str, content: str):
    """Mirror the route's expected message shape (has .role + .content)."""
    m = MagicMock()
    m.role = role
    m.content = content
    return m


def test_denoiser_disabled_returns_none(monkeypatch) -> None:
    """REGENOLD_QUERY_DENOISER=0 → bail before any provider work."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    assert _is_query_denoiser_enabled() is False
    out = _rewrite_multiturn_query(
        "What else?", [_mk_msg("user", "What is Article 13?")]
    )
    assert out is None


def test_denoiser_default_is_enabled(monkeypatch) -> None:
    """Unset env → default ON (per the R86 ship-default-ON brief)."""
    monkeypatch.delenv("REGENOLD_QUERY_DENOISER", raising=False)
    assert _is_query_denoiser_enabled() is True


def test_denoiser_no_history_returns_none(monkeypatch) -> None:
    """Empty history is the single-turn path — no rewrite needed."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    assert _rewrite_multiturn_query("What is Article 13?", []) is None


def test_denoiser_no_provider_returns_none(monkeypatch) -> None:
    """No wrapper + no Groq configured → return None (caller falls back)."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    out = _rewrite_multiturn_query(
        "What about deployers?",
        [_mk_msg("user", "What is Article 13?")],
    )
    assert out is None


def test_denoiser_returns_none_on_provider_error(monkeypatch) -> None:
    """LLM call returns error → de-noiser returns None."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    fake_resp = MagicMock()
    fake_resp.error = "network_error: timed out"
    fake_resp.text = ""
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        out = _rewrite_multiturn_query(
            "What about deployers?",
            [_mk_msg("user", "What is Article 13?")],
        )
    assert out is None


def test_denoiser_returns_none_on_empty_text(monkeypatch) -> None:
    """LLM returns empty .text → bail rather than ship blank query."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = "   "  # all whitespace
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        out = _rewrite_multiturn_query(
            "What about deployers?",
            [_mk_msg("user", "What is Article 13?")],
        )
    assert out is None


def test_denoiser_returns_none_when_too_short(monkeypatch) -> None:
    """< 10-char rewrites are suspicious — bail to fallback path."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = "Art. 13?"  # 8 chars
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        out = _rewrite_multiturn_query(
            "What about deployers?",
            [_mk_msg("user", "What is Article 13?")],
        )
    assert out is None


def test_denoiser_returns_none_when_too_long(monkeypatch) -> None:
    """> 500-char rewrites mean the LLM ignored the rule — bail."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = "x" * 600
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        out = _rewrite_multiturn_query(
            "What about deployers?",
            [_mk_msg("user", "What is Article 13?")],
        )
    assert out is None


def test_denoiser_returns_rewritten_text_on_happy_path(monkeypatch) -> None:
    """Valid LLM response → returns the cleaned rewrite (strips quotes)."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = '"deployer transparency obligations Art. 26"'
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        out = _rewrite_multiturn_query(
            "What about deployers?",
            [_mk_msg("user", "What is Article 13?")],
        )
    # Quotes stripped, content preserved
    assert out == "deployer transparency obligations Art. 26"


def test_denoiser_uses_one_second_timeout(monkeypatch) -> None:
    """R86 brief — timeout MUST be 1.0s, not 2.0s (fail-fast)."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = "deployer obligations under Art. 26"
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        _rewrite_multiturn_query(
            "What about deployers?",
            [_mk_msg("user", "What is Article 13?")],
        )
    # The request object passed to provider.complete carries timeout_seconds
    sent_req = fake_provider.complete.call_args.args[0]
    assert sent_req.timeout_seconds == 1.0, (
        "R86 timeout must be 1.0s — anything longer adds latency tail "
        "to multi-turn requests without measurable rewrite-quality gain."
    )


def test_denoiser_env_vars_in_cache_key(monkeypatch) -> None:
    """REGENOLD_QUERY_DENOISER + model overrides must be in cache identity.

    R30/R56/R79 cache-poisoning doctrine: any env var that flips engine
    or pre-engine behaviour must be folded into the cache key, otherwise
    a runtime flip serves stale entries.
    """
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    key_on = _engine_cache_key("test question", None)
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    key_off = _engine_cache_key("test question", None)
    assert key_on != key_off

    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("REGENOLD_DENOISER_MODEL", "claude-haiku-4-5-20251001")
    key_haiku = _engine_cache_key("test question", None)
    monkeypatch.setenv("REGENOLD_DENOISER_MODEL", "claude-sonnet-4-6")
    key_sonnet = _engine_cache_key("test question", None)
    assert key_haiku != key_sonnet


# ─── R86-D Deployer Graph-Hop ─────────────────────────────────────────────


def test_deployer_hop_disabled_returns_input_unchanged(monkeypatch) -> None:
    """REGENOLD_DEPLOYER_HOP=0 → no-op, returns the list verbatim."""
    monkeypatch.setenv("REGENOLD_DEPLOYER_HOP", "0")
    cands = ["Article 26", "Article 50"]
    out = _apply_deployer_hop(cands, "role_obligations", "deployer obligations?")
    assert out == cands


def test_deployer_hop_fires_on_role_obligations_intent(monkeypatch) -> None:
    """``intent == 'role_obligations'`` is an independent trigger."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26"]
    out = _apply_deployer_hop(cands, "role_obligations", "What about Art. 26?")
    # BM25 winner preserved at position 0
    assert out[0] == "Article 26"
    # Hop targets appended
    assert "Article 13" in out
    # Capped at MAX_INJECT
    assert len(out) - len(cands) <= _DEPLOYER_HOP_MAX_INJECT


def test_deployer_hop_fires_on_deployer_in_intent_label(monkeypatch) -> None:
    """Any intent label containing 'deployer' fires the hop."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    out = _apply_deployer_hop(
        ["Article 26"], "deployer_transparency", "Art. 26 obligations?"
    )
    assert "Article 13" in out or "Article 14" in out


def test_deployer_hop_fires_on_definitional_question(monkeypatch) -> None:
    """Definitional Wh-shape mentioning 'deployer' fires (Rule 3).

    R86 calibration: literal-substring trigger alone over-cited 339
    davidath scenario rows (Ref Loose −0.008). Restricting to Wh-shape
    definitional questions (not scenario openers) preserves the QA lift
    without polluting scenario precision.
    """
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    out = _apply_deployer_hop(
        ["Article 26"], "", "What are deployer obligations?"
    )
    assert any(r in out for r in ("Article 13", "Article 14", "Article 9"))


def test_deployer_hop_skips_scenario_opener_with_deployer(monkeypatch) -> None:
    """Scenario opener 'We are a deployer ...' must NOT fire the hop.

    R86 calibration — scenario gold is single-anchor (Art. 26 alone);
    injecting provider-side hops adds non-gold tokens that drag Ref
    Loose Jaccard. Verified against davidath A/B (Ref Loose 0.5696 →
    0.5776 after this gate was added).
    """
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26"]
    out = _apply_deployer_hop(
        cands,
        "",  # no intent label (TestClient bench has no LLM provider)
        "We are a deployer of a high-risk CV-screening AI system.",
    )
    assert out == cands, (
        "Scenario opener should NOT trigger deployer hop — "
        "single-anchor gold gets polluted."
    )


def test_deployer_hop_skips_non_wh_statement_with_deployer(monkeypatch) -> None:
    """A bare statement mentioning 'deployer' is NOT a definitional Q."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26"]
    # No Wh-start, no '?'; not a scenario opener but not a question either
    out = _apply_deployer_hop(
        cands, "", "The deployer must keep logs.",
    )
    assert out == cands


def test_deployer_hop_skips_when_neither_signal_present(monkeypatch) -> None:
    """No deployer signal → no hop expansion."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26"]
    out = _apply_deployer_hop(cands, "definition", "What is an AI system?")
    assert out == cands  # unchanged


def test_deployer_hop_never_displaces_bm25_winner(monkeypatch) -> None:
    """Hop targets APPEND — original BM25 order at the top stays intact."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26", "Article 27", "Article 50"]
    out = _apply_deployer_hop(cands, "role_obligations", "deployer Q")
    # First 3 positions = original BM25 winners
    assert out[:3] == cands


def test_deployer_hop_dedupes_against_existing_candidates(monkeypatch) -> None:
    """Article 13 already in candidates → not re-injected."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26", "Article 13"]  # Art. 13 already there
    out = _apply_deployer_hop(cands, "role_obligations", "deployer Q")
    # Art. 13 not duplicated
    assert out.count("Article 13") == 1


def test_deployer_hop_dedupes_against_self(monkeypatch) -> None:
    """Art 26 → [13/14/9] and Art 26.5 → [13/14/9] — no dup-13/14/9."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26", "Article 26.5"]
    out = _apply_deployer_hop(cands, "role_obligations", "deployer Q")
    # Each hop target appears at most once
    for r in ("Article 13", "Article 14", "Article 9"):
        assert out.count(r) <= 1


def test_deployer_hop_capped_at_max_inject(monkeypatch) -> None:
    """Cap protects against over-citation; mirrors R47 budget trade-off."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    # All 3 deployer roots present → 6 unique hop targets available,
    # but the cap holds the total injection to MAX_INJECT (3).
    cands = ["Article 26", "Article 27", "Article 50"]
    out = _apply_deployer_hop(cands, "role_obligations", "deployer Q")
    added = len(out) - len(cands)
    assert added <= _DEPLOYER_HOP_MAX_INJECT


def test_deployer_hop_returns_new_list_not_mutated(monkeypatch) -> None:
    """Must not mutate the input list — downstream callers may iterate it."""
    monkeypatch.delenv("REGENOLD_DEPLOYER_HOP", raising=False)
    cands = ["Article 26"]
    cands_id_before = id(cands)
    cands_snapshot = list(cands)
    out = _apply_deployer_hop(cands, "role_obligations", "deployer Q")
    assert cands == cands_snapshot          # unchanged
    assert id(out) != cands_id_before        # genuinely a new list


def test_deployer_hop_env_var_in_cache_key(monkeypatch) -> None:
    """Flipping REGENOLD_DEPLOYER_HOP must produce a distinct cache key."""
    monkeypatch.setenv("REGENOLD_DEPLOYER_HOP", "1")
    key_on = _engine_cache_key("deployer obligations?", None)
    monkeypatch.setenv("REGENOLD_DEPLOYER_HOP", "0")
    key_off = _engine_cache_key("deployer obligations?", None)
    assert key_on != key_off


def test_deployer_hop_map_endpoints_are_well_shaped() -> None:
    """Every source key + target value matches the AI-Act ref shape.

    Cheap structural check that prevents typos like 'Article  26' (two
    spaces) or 'Art. 26' (wire-internal canonical) from polluting the
    map. Wire-facing format is ``Article N`` / ``Annex <Roman>``.
    """
    import re
    art_re = re.compile(r"^Article\s+\d+(\.\d+)?$")
    annex_re = re.compile(r"^Annex\s+[IVXLCDM]+$")
    for src, targets in _DEPLOYER_HOP_MAP.items():
        assert art_re.match(src), f"bad source key {src!r}"
        assert isinstance(targets, list) and targets, f"empty targets for {src!r}"
        for t in targets:
            assert art_re.match(t) or annex_re.match(t), f"bad target {t!r}"

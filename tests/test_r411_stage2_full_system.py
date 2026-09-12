"""R411 — pin ``REGENOLD_STAGE2_FULL_SYSTEM``'s wiring and semantics.

The flag decides whether the Stage-2 **primary** transport (the cloudflared
Claude-Max tunnel) receives the real ``ANSWER_GENERATE_SYSTEM`` prompt or the
R342 62-character persona that replaced it.

Why this is worth a test rather than a comment: R342 added the cap on a premise
("the bundled CLI 500s on a 53 kB system prompt") that R383 later **falsified**
over the same tunnel — 0 errors in 6/6 calls at 53,601 chars of system plus
18-21 kB of user. R383 then measured the cap itself: the full system produced
**0.199x** the answer length and ran **2.38x faster**, because the persona path
leaves the model with no system-channel rules at all. R411 re-measured it paired
across the full probe corpus (mean latency 27.97 s -> 14.94 s, 11 of 12 rows
faster, ``gold_dropped_head`` +0) and gated it.

Two properties must hold and neither is visible in a diff:

1. The flag is registered in ``_engine_cache_key``. It rewrites the answer, and
   the wire references are recomputed FROM that answer, so a same-process A/B
   differing only here must not be served a shared cache entry
   (``AGENTS.md`` invariant #4).
2. Default OFF, and the gate is an **allow-list** (``in {"1","true","yes","on"}``).
   A blank value keeps the persona. This is deliberate: the R342 -> R383 history
   is a chain of changes whose author assumed the safer branch was taken.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import app.llm.openai_wrapper_provider as wp
from app.engines import _graph_rag_impl as G

PERSONA = "You are an expert EU AI Act regulatory compliance specialist."
REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTES = REPO_ROOT / "app" / "routes" / "regenold.py"

# Comfortably over the 1000-char threshold, and long enough that a regression
# which silently truncates instead of substituting would also be caught.
LONG_SYSTEM = (
    "You are an expert EU AI Act regulatory compliance specialist.\n"
    + "\n".join(f"{i}. Rule number {i} for grounded citation of the Regulation." for i in range(1, 40))
)
assert len(LONG_SYSTEM) > 1000


class _CapturingProvider:
    """Stands in for the pooled wrapper provider; records the request."""

    base_url = wp._DEFAULT_WRAPPER_BASE

    def __init__(self) -> None:
        self.calls: list[wp.OpenAIWrapperRequest] = []

    def complete(self, req: wp.OpenAIWrapperRequest) -> wp.OpenAIWrapperResponse:
        self.calls.append(req)
        return wp.OpenAIWrapperResponse(
            text="Article 6 sets out the classification rules for high-risk AI systems.",
            model="claude-opus-5",
        )


@pytest.fixture()
def provider(monkeypatch: pytest.MonkeyPatch) -> _CapturingProvider:
    doub = _CapturingProvider()
    # _graph_rag_impl imports this name at CALL time, so patching the source
    # module's attribute is what the engine actually resolves.
    monkeypatch.setattr(wp, "get_openai_wrapper_provider", lambda: doub)
    return doub


def _call(provider: _CapturingProvider, system: str) -> str | None:
    return G._openai_wrapper_complete_for_graph_rag(
        system=system,
        user="ORIGINAL QUESTION: What does Article 6 say?",
        max_tokens=1024,
        temperature=0.0,
        complex_question=False,
        stage_name="Stage 2 (Polishing)",
    )


def test_flag_is_registered_in_engine_cache_key() -> None:
    """Invariant #4 — an answer-flipping flag needs its own cache-key slot."""
    from app.routes import regenold as route_mod

    src = Path(route_mod.__file__).read_text(encoding="utf-8")
    fn = src[src.index("def _engine_cache_key") :]
    # Stop at the next top-level def so the scan cannot borrow a later entry.
    nxt = re.search(r"\ndef [a-zA-Z_]", fn[1:])
    if nxt:
        fn = fn[: nxt.start() + 1]
    assert "REGENOLD_STAGE2_FULL_SYSTEM" in fn, (
        "REGENOLD_STAGE2_FULL_SYSTEM rewrites the answer and therefore the wire "
        "references derived from it, but is not in _engine_cache_key(): an "
        "in-process A/B would be served arm A's cached output."
    )


def test_default_keeps_the_persona_on_the_primary_transport(
    provider: _CapturingProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R411 — default OFF, and it must STAY off: the lever is modality-split.

    Delivering the full system measured +13 pp Speed with gold_drop_hd +0 on the
    easy split (n=12) and a -10.8 pp ref_loose / +6 gold-drop LOSS on the hard
    (pushback) split (n=37). This test exists so nobody flips the default on the
    easy-mode number alone — it is invisible at the request level (the answer
    just quietly gets shorter and the request faster).
    """
    monkeypatch.delenv("REGENOLD_STAGE2_FULL_SYSTEM", raising=False)
    _call(provider, LONG_SYSTEM)
    assert provider.calls, "the primary transport was never dialled"
    assert provider.calls[0].system == PERSONA


def test_blank_value_keeps_the_persona(
    provider: _CapturingProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Allow-list gate: a blank value must NOT enable the full system."""
    monkeypatch.setenv("REGENOLD_STAGE2_FULL_SYSTEM", "")
    _call(provider, LONG_SYSTEM)
    assert provider.calls[0].system == PERSONA


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "ON", " 1 "])
def test_enable_values_deliver_the_full_system(
    provider: _CapturingProvider, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Every documented ON spelling must deliver the real prompt verbatim."""
    monkeypatch.setenv("REGENOLD_STAGE2_FULL_SYSTEM", value)
    _call(provider, LONG_SYSTEM)
    assert provider.calls[0].system == LONG_SYSTEM


def test_short_system_is_never_substituted(
    provider: _CapturingProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A system prompt under the cap is passed through on both flag values."""
    short = "You are a concise EU AI Act assistant."
    for value in ("0", "1"):
        monkeypatch.setenv("REGENOLD_STAGE2_FULL_SYSTEM", value)
        provider.calls.clear()
        _call(provider, short)
        assert provider.calls[0].system == short


def test_answer_generate_system_is_far_over_the_cap() -> None:
    """Documents the size that makes this lever load-bearing, not cosmetic."""
    from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM

    assert len(ANSWER_GENERATE_SYSTEM) > 10_000

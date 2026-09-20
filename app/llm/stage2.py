"""Stage-2 **leg-2 dispatch** — one function, one outcome type (R427 / R426 T1).

WHY THIS MODULE EXISTS
----------------------
Stage-2 runs on exactly two transports (``app/llm/stage2_policy``): the
cloudflared tunnel in front of the Claude Max wrapper (**leg 1**), and AWS
Bedrock (**leg 2**). Two different functions dial leg 2:

* ``_openai_wrapper_complete_for_graph_rag`` — the transport, whose nested
  ``_try_bedrock_fallback`` fires on an off-contract base URL, a transport error,
  ``finish_reason="length"`` and structural truncation;
* ``_claude_max_enhance_answer`` — the answer path, with its own inline fallback
  block.

Each carried **its own** copy of the leg-2 verdict, and the copies drifted:

1. **The counter was recorded at different times.** R361 established that the
   verdict must be deferred until the text has survived the rejection rules — a
   discarded answer must not count as ``fallback_ok``, because that counter is
   what an operator reads on ``/healthz/llm`` to decide whether the tunnel is
   healthy. The transport copy defers; the answer-path copy recorded
   ``ok=bool(text)`` the moment Bedrock replied.
2. **The emptiness rule differed.** The transport copy treats a *falsy* answer as
   empty (``not text``); the answer-path copy treats a *whitespace-only* answer
   as empty (``bool(text.strip())``).
3. **``_looks_structurally_truncated`` was applied on one path only.** A truncated
   Bedrock answer is no better than a truncated tunnel answer: shipping it sets
   ``stage2_landed=True`` and lets the R72 reconcile pass prune citations the cut
   prose never described.

This module makes all three **visible in one place** and is the only place the
leg-2 verdict is decided or recorded, so ``attempts == ok + failed`` holds on
both paths by construction.

T1 IS A PURE MOVE — the two presets ARE the two pre-T1 behaviours
----------------------------------------------------------------
The move that shipped here is behaviour-preserving, which is why it is gated by
a differential replay (``docs/measurements/r427``) rather than a new scoreboard:
OLD and NEW are driven over the same corpus and must agree byte-for-byte on the
shipped text, the counter deltas and the branch taken. The two presets name the
pre-existing behaviours — they do **not** equalise them:

``PRESET_TRANSPORT``
    what ``_openai_wrapper_complete_for_graph_rag`` has always done — falsy is
    empty, structural truncation rejects.
``PRESET_ANSWER``
    what ``_claude_max_enhance_answer`` has always done — stripped-empty is
    empty, structural truncation is NOT applied, and the text is passed through
    untouched.

Equalising the two — i.e. applying the truncation rule on the answer path too —
is a **behaviour change**, not a move: it changes which text ships. It is
therefore recorded as the next, separately-gated step (T1b in
``docs/measurements/r427/CHECKPOINT.md``) rather than smuggled into this one.

PURITY
------
Nothing here imports the engine (which would be a cycle). The caller injects its
own structural-truncation predicate, so the decisions are unit-testable without
a transport, and ``text`` is always carried **verbatim** — the dispatch never
rewrites an answer.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

__all__ = [
    "LEG_FALLBACK",
    "PRESET_ANSWER",
    "PRESET_TRANSPORT",
    "REJECT_EMPTY",
    "REJECT_TRUNCATED",
    "Stage2Outcome",
    "classify_leg2",
    "dispatch_leg2",
    "leg2_presets",
]

#: The serving leg, for the R417 ``stage2_served_by`` bookkeeping.
LEG_FALLBACK = "fallback"

#: ``Stage2Outcome.rejected`` values. Stable strings: counters, logs and tests
#: all compare against these rather than against prose.
REJECT_EMPTY = "empty"
REJECT_TRUNCATED = "truncated"

#: The two pre-T1 dispositions. See the module docstring — a preset names a
#: behaviour that already shipped; it is not a tuning knob.
PRESET_TRANSPORT = "transport"
PRESET_ANSWER = "answer"

_PRESETS = (PRESET_TRANSPORT, PRESET_ANSWER)


@dataclass(frozen=True)
class Stage2Outcome:
    """What one leg-2 dial produced, and what the caller may do with it.

    ``text`` is the leg-2 response **verbatim** (``None`` only when there was no
    text at all), so a caller strips it exactly where it always did. ``ok`` is
    the recorded verdict: a caller that sees ``rejected`` must fall through,
    never ship.
    """

    text: str | None
    leg: str = LEG_FALLBACK
    rejected: str = ""
    ok: bool = True

    @property
    def usable(self) -> bool:
        """May the caller ship ``text``? The same value that was recorded."""
        return self.ok and not self.rejected


def leg2_presets() -> tuple[str, ...]:
    """The disposition names :func:`classify_leg2` accepts (for tests and docs)."""
    return _PRESETS


def classify_leg2(
    text: str | None,
    *,
    preset: str,
    structurally_truncated: Callable[[str], bool],
) -> Stage2Outcome:
    """Verdict on a leg-2 response, under one named pre-T1 disposition.

    ``structurally_truncated`` is the engine's own predicate (R102/R377): the
    wrapper reports ``finish_reason="stop"`` even on a stream cut mid-word, so
    the finish-reason guard cannot see a cut answer.
    """
    if preset == PRESET_TRANSPORT:
        # Falsy is empty; a whitespace-only answer is NOT empty here, and the
        # structural predicate returns False for it, so it used to ship. Kept
        # exactly (see the module docstring, divergence 2).
        if not text:
            return Stage2Outcome(text=None, rejected=REJECT_EMPTY, ok=False)
        if structurally_truncated(text):
            return Stage2Outcome(text=text, rejected=REJECT_TRUNCATED, ok=False)
        return Stage2Outcome(text=text)
    if preset == PRESET_ANSWER:
        # Stripped-empty is empty, and the text passes through untouched.
        ok = bool((text or "").strip())
        return Stage2Outcome(text=text, rejected="" if ok else REJECT_EMPTY, ok=ok)
    raise ValueError(f"unknown leg-2 preset {preset!r}; expected one of {_PRESETS}")


def dispatch_leg2(
    text: str | None,
    *,
    preset: str,
    structurally_truncated: Callable[[str], bool],
) -> Stage2Outcome:
    """:func:`classify_leg2` plus **the one** ``record_result`` for leg 2.

    The recording lives here and nowhere else, on the deferred outcome, so a
    discarded answer can never be counted as ``fallback_ok`` (R361) and
    ``fallback_attempts == fallback_ok + fallback_failed`` holds no matter which
    call site dialled. Fail-soft by design: a counter must never break Stage-2.
    """
    from app.llm import stage2_policy as _policy

    outcome = classify_leg2(
        text, preset=preset, structurally_truncated=structurally_truncated
    )
    try:
        _policy.record_result(_policy.STAGE2_FALLBACK, ok=outcome.usable)
    except Exception:  # noqa: BLE001 — accounting is best-effort
        pass
    return outcome

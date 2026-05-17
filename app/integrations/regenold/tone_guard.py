"""Tone enforcement guard (R38 / Issue A4).

The Regenold competition rubric scores 'professional tone' against
gold examples. Strip LLM hedge prefixes ("I think", "It seems") and
self-references ("As an AI") that don't appear in regulator voice.
Preserve sentences that already lead with a citation anchor or an
imperative.

Designed to be fail-soft: on any exception, return the original input.
"""
from __future__ import annotations

import re

# Hedge patterns, ordered longest-first so compound hedges peel cleanly.
# Each pattern matches from start of string, case-insensitive, including
# a trailing punctuation + space.
_HEDGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*as\s+an\s+ai(?:\s+(?:language\s+)?model)?[,\.\s]+(?:i\s+(?:can(?:not)?|am)\s+\S+\s+\S+[,\.\s]+)?", re.I),
    re.compile(r"^\s*based\s+on\s+(?:my\s+(?:understanding|reading|interpretation|knowledge)|the\s+(?:provided\s+)?information)[,\.\s]+", re.I),
    re.compile(r"^\s*please\s+note(?:\s+that)?[,\.\s]+", re.I),
    re.compile(r"^\s*it\s+(?:seems|appears|is\s+(?:likely|possible))\s+(?:that[,\.\s]+)?", re.I),
    re.compile(r"^\s*i\s+(?:think|believe|would\s+argue|understand)(?:\s+that)?[,\.\s]+", re.I),
    re.compile(r"^\s*in\s+my\s+(?:opinion|view|understanding)[,\.\s]+", re.I),
    re.compile(r"^\s*to\s+(?:the\s+best\s+of\s+my|my)\s+(?:knowledge|understanding)[,\.\s]+", re.I),
    re.compile(r"^\s*from\s+what\s+i\s+(?:can\s+tell|understand|see)[,\.\s]+", re.I),
)


def _capitalise_first_letter(s: str) -> str:
    if not s:
        return s
    if s[0].islower():
        return s[0].upper() + s[1:]
    return s


def enforce_tone(answer: str | None) -> str:
    """Strip hedge prefixes; preserve cite-anchored or imperative starts.

    Iterates patterns until no more strip; capitalises the resulting
    first letter. Returns "" on None input. Returns input verbatim on
    any internal exception (fail-soft per spec).
    """
    if not answer:
        return ""
    try:
        out = answer
        # Peel hedges iteratively — compound hedges (#9 test) need
        # multiple passes.
        for _ in range(4):  # bounded to avoid runaway loop
            before = out
            for pattern in _HEDGE_PATTERNS:
                out = pattern.sub("", out, count=1)
            if out == before:
                break
        out = out.strip()
        out = _capitalise_first_letter(out)
        return out
    except Exception:  # noqa: BLE001 — fail-soft
        return answer

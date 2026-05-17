"""R41 Phase C.1 — scope.py governance anchor expansion regression tests.

Verifies that the new multi-word governance anchors from the AI Guide
(chapters 2/4/8) and the Digital Omnibus changes spec route their
respective questions in-scope WITHOUT regressing the R34 P0 false-
positive corpus (bare-verb anchors causing off-topic confidently-wrong
answers — "Birth certificate processing time", "Suspend my Netflix
subscription", "When did the queen withdraw from public life",
"Who is your favourite musician").

Each test pair below covers one of the new governance phrases:

* A FALSE-POSITIVE probe — must stay OUT of scope.
* An IN-SCOPE probe — must flip in-scope on the new anchor.
"""
from __future__ import annotations

import pytest

from app.integrations.regenold.scope import classify_scope


# ── R34 P0 false-positive corpus — these MUST remain out-of-scope ─────────


FALSE_POSITIVE_QUERIES: tuple[str, ...] = (
    "Birth certificate processing time in France?",
    "I want to suspend my Netflix subscription",
    "When did the queen withdraw from public life?",
    "Who is your favourite musician?",
)


class TestFalsePositivesRemainOutOfScope:
    """The four R34 P0 probes must NEVER be matched by any new anchor."""

    @pytest.mark.parametrize("query", FALSE_POSITIVE_QUERIES)
    def test_fp_query_stays_out_of_scope(self, query: str) -> None:
        verdict = classify_scope(query)
        assert not verdict.in_scope, (
            f"FALSE POSITIVE — R41 anchors leak in: {query!r} → {verdict}"
        )


# ── New in-scope governance probes ───────────────────────────────────────


# Each pair = (phrase, probe question containing the phrase). The probe
# is shaped like a real user question — "What does X cover?" / "Tell me
# about Y" — so the anchor is forced to do the in-scope flip.
NEW_INSCOPE_PROBES: tuple[tuple[str, str], ...] = (
    ("product manufacturer", "What does product manufacturer mean here?"),
    (
        "making available on the market",
        "When is making available on the market considered to have occurred?",
    ),
    ("household exemption", "Tell me about the household exemption."),
    (
        "new legislative framework",
        "What is the new legislative framework approach to AI?",
    ),
    (
        "single point of contact",
        "Is there a single point of contact requirement?",
    ),
    (
        "fulfil a safety function",
        "When does a system fulfil a safety function?",
    ),
    (
        "third-party conformity assessment",
        "When is third-party conformity assessment required?",
    ),
    ("affected person", "Who counts as an affected person?"),
    ("product presenting a risk", "What is a product presenting a risk?"),
    (
        "AI Office investigation",
        "What does the AI Office investigation power cover?",
    ),
    ("periodic penalty payment", "What is a periodic penalty payment?"),
    ("negotiated disclosure", "Where does negotiated disclosure apply?"),
    (
        "small mid-cap enterprise",
        "When can a small mid-cap enterprise use sandbox privileges?",
    ),
    (
        "real-world testing framework",
        "What is the real-world testing framework?",
    ),
    (
        "single application unified assessment",
        "What is the single application unified assessment?",
    ),
    ("intended purpose", "What is the intended purpose used for?"),
    (
        "post-market monitoring system",
        "How does the post-market monitoring system work?",
    ),
    (
        "competent national authority",
        "Who is the competent national authority?",
    ),
    (
        "output is intended to be used",
        "What does output is intended to be used cover?",
    ),
    ("scientific panel", "Who sits on the scientific panel?"),
    ("advisory forum", "What is the advisory forum?"),
)


class TestNewAnchorsRouteInScope:
    """Each new governance phrase must flip its probe question in-scope."""

    @pytest.mark.parametrize("phrase,probe", NEW_INSCOPE_PROBES)
    def test_inscope_probe(self, phrase: str, probe: str) -> None:
        verdict = classify_scope(probe)
        assert verdict.in_scope, (
            f"IN-SCOPE FAIL — anchor {phrase!r} probe: {probe!r} → {verdict}"
        )

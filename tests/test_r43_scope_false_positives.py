"""R43 Fix A.2 — consumer-context false-positive regression guard.

The R41 + R42 anchor expansions added several phrases that double as
common English in non-regulatory contexts:

* ``intended purpose`` — also appears in travel ("intended purpose of
  my visit"), retail ("intended purpose paint"), food ("intended
  purpose meal kits") framings.
* ``affected person`` — generic legal term (tort law, civil law,
  insurance claims).
* ``household exemption`` — common tax / accounting phrase.
* ``credit scoring`` — generic finance term (consumer credit reports,
  FICO score explanations).
* ``predictive policing`` — common in fiction / film analysis.
* ``fraud detection`` — every consumer streaming / banking / email
  service markets a "fraud detection" feature.

Pre-R43 these phrases substring-matched into ``_AI_ACT_ANCHORS`` /
``KEYWORD_TO_ARTICLE`` and flipped the question in-scope, producing a
confident regulatory answer to a tax / movie / consumer-product
question. R43 introduces co-occurrence disqualifiers
(:data:`_ANCHOR_DISQUALIFIERS`) that suppress these anchors when a
non-AI-Act domain phrase appears in the same question — without
breaking legitimate AI Act probes that reuse those same anchor
keywords (covered by ``tests/test_r41_scope_anchors.py``).

The corpus below is the AUTHORITATIVE FP set — every R43+ change to
the disqualifier list must keep these out of scope while keeping the
R41 21 in-scope probes flipping in.
"""
from __future__ import annotations

import pytest

from app.integrations.regenold.scope import classify_scope


# ── Consumer-context FP corpus (required by the R43 Fix A.2 brief + extras) ──


CONSUMER_FALSE_POSITIVES: tuple[str, ...] = (
    # R43 brief — direct probes.
    "Can you check my credit scoring report?",
    "Please ensure my fraud detection on Netflix.",
    "Tell me about predictive policing in movies",
    "What is the intended purpose of my visit?",
    "I bought intended purpose paint for my walls.",
    "Affected person rights in tort law?",
    "Can I claim the household exemption on my tax return?",
    # ── R43 extras — additional consumer-context shapes ────────────────────
    # Travel / retail context for ``intended purpose``
    "What is the intended purpose of my trip to Paris?",
    "The intended purpose of this paint is to cover walls.",
    # Tort-law context for ``affected person``
    "Affected person compensation in car accident claims?",
    # Tax / accounting context for ``household exemption``
    "IRS household exemption rules for income tax",
    "Council tax household exemption application",
    # Consumer credit-report context for ``credit scoring``
    "my personal credit scoring report at Experian",
    "FICO credit scoring report explanation",
    # Fiction / film context for ``predictive policing``
    "Predictive policing in Minority Report the movie",
    "How does predictive policing appear in TV shows?",
    # Consumer service anti-fraud context for ``fraud detection``
    "Fraud detection on PayPal",
    "fraud detection on my bank app saved me",
)


class TestR43ConsumerFalsePositives:
    """Each consumer-context probe must route OUT-of-scope post-R43.

    These probes carry NO genuine AI Act signal — the only "anchor"
    is a substring of a common English phrase. A confident regulatory
    answer to one of these would be a sycophancy / hallucination on a
    non-regulatory query, which Regenold's rubric penalises.
    """

    @pytest.mark.parametrize("query", CONSUMER_FALSE_POSITIVES)
    def test_consumer_queries_are_out_of_scope(self, query: str) -> None:
        verdict = classify_scope(query)
        assert not verdict.in_scope, (
            f"R43 FP leak — anchor substring routed {query!r} as in-scope "
            f"({verdict.reason.value!r}: {verdict.evidence!r})"
        )


# ── Companion in-scope corpus — must STILL pass after R43 disqualifiers ──


LEGITIMATE_AI_ACT_PROBES: tuple[str, ...] = (
    # The disqualifiers are co-occurrence-only — a genuine AI Act
    # question that re-uses the same anchor keywords MUST still flip
    # in-scope. Each probe pairs a suspect anchor with an explicit AI
    # Act / regulatory signal (article ref / "AI Act" / "Annex III" /
    # "high-risk").
    "Are AI systems for credit scoring high-risk under Annex III?",
    "Is predictive policing prohibited under the AI Act?",
    "Does the AI Act apply to fraud detection AI in banking?",
    "What does intended purpose mean under the EU AI Act?",
    "Who is an affected person under Article 86 of the AI Act?",
    "Is the household exemption in Art. 2 a personal-use carve-out?",
)


class TestR43DisqualifiersAreCoOccurrenceOnly:
    """Re-using a disqualifier anchor inside a real AI Act question
    must NOT suppress the in-scope verdict — the disqualifier fires
    only when the consumer-domain pattern co-occurs.

    Without this regression guard, an over-broad disqualifier could
    silently refuse legitimate AI Act questions that happen to mention
    credit-scoring / predictive-policing / etc.
    """

    @pytest.mark.parametrize("query", LEGITIMATE_AI_ACT_PROBES)
    def test_ai_act_context_probe_stays_in_scope(self, query: str) -> None:
        verdict = classify_scope(query)
        assert verdict.in_scope, (
            f"R43 over-pruning — legitimate AI Act probe {query!r} routed "
            f"as out-of-scope ({verdict.reason.value!r}: "
            f"{verdict.evidence!r})"
        )


# ── R41 anchor compatibility — explicit cross-check ──────────────────────


# Pin the 3 single-anchor R41 probes whose ONLY in-scope signal is the
# disqualifier-suspect anchor itself. The R43 disqualifier must not
# strip these — they have no consumer-domain co-occurrence, so the
# anchor stays valid. tests/test_r41_scope_anchors.py covers the full
# 21-probe corpus; this is a redundancy check focused on the suspects.
SUSPECT_ANCHOR_R41_PROBES: tuple[tuple[str, str], ...] = (
    ("household exemption", "Tell me about the household exemption."),
    ("affected person", "Who counts as an affected person?"),
    ("intended purpose", "What is the intended purpose used for?"),
)


class TestR43LeavesR41BareAnchorsAlone:
    """The R41 bare-anchor in-scope probes must continue to flip
    in-scope after R43. These probes have no other anchor and no
    consumer-domain phrase — the disqualifier shouldn't fire.
    """

    @pytest.mark.parametrize("phrase,probe", SUSPECT_ANCHOR_R41_PROBES)
    def test_r41_bare_anchor_still_in_scope(
        self, phrase: str, probe: str
    ) -> None:
        verdict = classify_scope(probe)
        assert verdict.in_scope, (
            f"R43 regression — R41 bare anchor {phrase!r} probe "
            f"{probe!r} routed out-of-scope: {verdict}"
        )


# ── R41 letter-suffix article wire compatibility — sanity check ─────────


# The R41 KB additions include letter-suffix articles (Art. 4a, 60a,
# 75a-75e) and Annex XIV. Fix A.1 updated the wire-output regex to
# accept ``Article 75e`` / ``Article 4a.2`` shapes. This pins a few
# of the letter-suffix shapes through ``classify_scope`` to confirm
# the letter-suffix path doesn't accidentally tangle with the
# disqualifier work.
LETTER_SUFFIX_PROBES: tuple[str, ...] = (
    "What does Article 75e cover?",
    "Tell me about Art. 4a bias-data legal basis",
    "What are the procedural safeguards in Art. 75d?",
    "Compare Art. 75a and Art. 75b investigation powers",
    "Article 60a Section B real-world testing framework",
)


class TestR43LetterSuffixArticlesRouteInScope:
    """Letter-suffix article references (Art. 4a / 60a / 75a-e) must
    flip in-scope through ``classify_scope`` — Fix A.1's regex update
    is the precondition for this; Fix A.2's disqualifier additions
    must not interfere.
    """

    @pytest.mark.parametrize("query", LETTER_SUFFIX_PROBES)
    def test_letter_suffix_article_query_in_scope(self, query: str) -> None:
        verdict = classify_scope(query)
        assert verdict.in_scope, (
            f"Letter-suffix article ref didn't flip in-scope: {query!r} "
            f"-> {verdict}"
        )

"""R146 — Stage-2 fidelity guard: the intelligent Stage-1 / Stage-2 combine.

The two-stage pipeline builds every answer in two passes:

* **Stage 1 (deterministic)** — fast, citation-exact, identical every run.
  It is the CONTENT source of truth: a curated classification verdict carries
  every risk tier the question implicates and every tier's anchor article.
* **Stage 2 (Opus 4.8 polish)** — natural, concise, regulator-toned prose, but
  non-deterministic and prone to DROP content when it rewrites. The motivating
  failure (the "emotion bug"): a deterministic cross-tier verdict
  (prohibited / high-risk / transparency) was rewritten by Opus into a
  prohibition-only answer, and the downstream R72 reconcile then deleted the
  dropped tiers' citations too — net an incomplete answer.

R144's fix for the curated set was a binary SKIP (don't let Stage-2 run). This
module is the *intelligent* combine: keep Stage-2's polish, but GUARD it against
dropping a load-bearing tier. After the polish, it verifies that every risk
TIER the deterministic Stage-1 draft asserted still survives in the polished
prose. If a tier was dropped it REPAIRS (re-injects the deterministic clause for
that tier, keeping the rest of the polish) or, when repair cannot recover, FALLS
BACK to the deterministic draft. Best of both: Opus polish when faithful, the
deterministic content guarantee otherwise — generalising the R144 emotion fix to
EVERY cross-tier classification (transcription, recruitment, biometric, …), not
just the six curated intercepts.

Scope (deliberately narrow, to avoid the R142.1 over-citation trap): the guard
acts ONLY when BOTH

* the QUESTION explicitly asks for a cross-tier classification — enumerated tier
  options ("prohibited, high-risk, or limited?"), "what risk tier / category /
  level", "always / ever prohibited", etc. — so completeness IS the answer; AND
* the deterministic draft names ≥ 2 distinct risk tiers.

This is the crucial gate the first cut lacked: for a FOCUSED yes/no question
("is X high-risk?") Opus correctly NARROWS the verbose deterministic verdict to
the relevant tier, and re-inflating the omitted tiers would regress conciseness
(R142.1 in a new form). The question gate keeps the guard off those rows. The
contract is a subset of the deterministic draft's own tier anchors, so the guard
can never introduce a citation the deterministic verdict did not already
establish.

Default mode is ``fallback`` — when Opus drops a tier on a cross-tier-
classification ask, ship the COMPLETE deterministic verdict (R144 proved this is
correct + complete + faster for the emotion cross-tier case; no splice/seam or
conciseness-inflation risk). ``repair`` (env-opt-in) keeps the polish and grafts
the dropped tier's deterministic clause back in.

Pure-stdlib, fail-soft: any exception leaves the polished answer untouched.
Env-gated ``REGENOLD_STAGE2_FIDELITY`` (mode via ``REGENOLD_STAGE2_FIDELITY_MODE``
= ``fallback`` (default) | ``repair``).
"""

from __future__ import annotations

import os
import re

__all__ = [
    "fidelity_guard_enabled",
    "fidelity_mode",
    "extract_tier_set",
    "is_cross_tier_classification_ask",
    "guard_cross_tier_polish",
]


# ── Risk-tier anchor map ─────────────────────────────────────────────────────
#
# Each risk tier is identified by the anchor provision(s) the EU AI Act gives
# it. A tier is "present" in a piece of prose when AT LEAST ONE of its anchors
# is named — so narrowing within a tier (e.g. citing Article 6 but not Annex
# III) keeps the tier, and only a WHOLE missing tier registers as a drop.
_TIER_ANCHORS: dict[str, tuple[str, ...]] = {
    # Unacceptable-risk / prohibited practices.
    "prohibited": ("Article 5",),
    # High-risk classification (Annex III use-case route + Annex I product
    # route, both governed by Article 6).
    "high_risk": ("Article 6", "Annex III"),
    # Limited-risk transparency.
    "limited": ("Article 50",),
    # General-purpose AI model regime.
    "gpai": (
        "Article 51",
        "Article 52",
        "Article 53",
        "Article 54",
        "Article 55",
    ),
}


def _anchor_pattern(anchor: str) -> re.Pattern[str]:
    """Word-boundary regex that matches ``anchor`` in prose without prefix bleak.

    ``Article 5`` must NOT match inside ``Article 50`` (the trailing ``\b``
    fails because ``5`` is followed by the word-char ``0``); ``Annex I`` must
    NOT match inside ``Annex III`` (same reason). Accepts the ``Art.`` short
    form too (Stage-2 prose is normalised to ``Article N`` on the wire, but the
    guard runs pre-normalise so the short form can still appear).
    """
    if anchor.startswith("Article"):
        num = anchor.split()[1]
        return re.compile(rf"\b(?:Article|Art\.?)\s+{num}\b", re.IGNORECASE)
    if anchor.startswith("Annex"):
        roman = anchor.split()[1]
        return re.compile(rf"\bAnnex\s+{roman}\b", re.IGNORECASE)
    return re.compile(re.escape(anchor), re.IGNORECASE)


# Precompile per-tier anchor patterns.
_TIER_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    tier: tuple(_anchor_pattern(a) for a in anchors)
    for tier, anchors in _TIER_ANCHORS.items()
}


# Sentence splitter — light, abbreviation-aware enough for re-injection. The
# deterministic draft uses ``Article N`` / ``Annex N`` (no bare ``Art.`` mid
# sentence in the verdict prose), so a terminal-punctuation split is sufficient;
# a mis-split can never fabricate a tier match (the anchor token has to be
# present), so the result is robust.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Conservative verdict-polarity probes. A deterministic cross-tier verdict
# almost always LEADS with a negation ("not prohibited" / "neither prohibited")
# when the practice is permitted in some context; if the polish instead asserts
# a flat prohibition verdict, that is a legal-classification FLIP and must fall
# back rather than ship a wrong verdict.
_DET_NOT_PROHIBITED = re.compile(
    r"\b(?:not\s+(?:categorically\s+|always\s+)?prohibited|"
    r"neither\s+prohibited|not\s+(?:among|one\s+of)\s+the\s+prohibited)",
    re.IGNORECASE,
)
_POLISH_IS_PROHIBITED = re.compile(
    r"\b(?:is\s+prohibited|are\s+prohibited|categorically\s+(?:banned|prohibited)|"
    r"falls\s+(?:under|within)\s+the\s+prohibited)",
    re.IGNORECASE,
)
_NEGATION_NEAR_PROHIBITED = re.compile(
    r"\b(?:not|never|neither|nor|unless|only\s+(?:where|when|in))\b",
    re.IGNORECASE,
)


def fidelity_guard_enabled() -> bool:
    """Env gate. Default ON; ``REGENOLD_STAGE2_FIDELITY=0`` disables."""
    return os.getenv("REGENOLD_STAGE2_FIDELITY", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def fidelity_mode() -> str:
    """``fallback`` (default — ship the complete deterministic verdict on a tier
    drop) or ``repair`` (keep the polish, re-inject the dropped tier's clause)."""
    mode = os.getenv("REGENOLD_STAGE2_FIDELITY_MODE", "fallback").strip().lower()
    return mode if mode in ("repair", "fallback") else "fallback"


def extract_tier_set(text: str) -> set[str]:
    """Return the set of risk-tier names whose anchor is named in ``text``."""
    if not text:
        return set()
    present: set[str] = set()
    for tier, patterns in _TIER_PATTERNS.items():
        if any(p.search(text) for p in patterns):
            present.add(tier)
    return present


# Question shapes where a cross-tier classification IS the answer — completeness
# is correctness, so Opus dropping a tier is a defect (not a conciseness win).
_CLASSIFICATION_ASK_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Enumerated tier options: "prohibited, high-risk, or limited[-risk]?",
    # "prohibited or high-risk", "high-risk or limited" — two tier words joined
    # by "or" within a short span.
    re.compile(
        r"\b(?:prohibited|high[\s-]?risk|limited[\s-]?risk|limited|minimal)\b"
        r"[^.?!]{0,40}?\bor\b[^.?!]{0,40}?"
        r"\b(?:prohibited|high[\s-]?risk|limited[\s-]?risk|limited|minimal|"
        r"unacceptable|gpai)\b",
        re.IGNORECASE,
    ),
    # Explicit "what / which risk tier|category|level|classification".
    re.compile(
        r"\b(?:what|which)\b[^.?!]{0,30}?\brisk\s+(?:tier|categor|level|class)",
        re.IGNORECASE,
    ),
    # "always / ever prohibited" (the emotion-style boundary ask).
    re.compile(r"\b(?:always|ever)\s+prohibit", re.IGNORECASE),
)


def is_cross_tier_classification_ask(question: str) -> bool:
    """True iff the question explicitly asks to classify across risk tiers.

    Scans the whole (possibly flattened multi-turn) string — the enumerated-tier
    phrase / "what risk tier" lives in the live turn; a prior turn almost never
    carries it. Conservative: a bare "is X high-risk?" yes/no question or "how is
    X classified?" does NOT fire (Opus narrowing the deterministic verdict to the
    relevant tier is correct there)."""
    if not question:
        return False
    return any(p.search(question) for p in _CLASSIFICATION_ASK_PATTERNS)


def _verdict_flip(deterministic: str, polished: str) -> bool:
    """True iff the polish flips a permitted-context verdict into a flat ban.

    Conservative: requires the deterministic draft to assert a "not prohibited"
    verdict AND the polish to assert a prohibition verdict WITHOUT a nearby
    negation/conditional. The cross-tier completeness check catches most drops;
    this guards the rarer, more dangerous legal-classification inversion.
    """
    if not _DET_NOT_PROHIBITED.search(deterministic):
        return False
    m = _POLISH_IS_PROHIBITED.search(polished)
    if not m:
        return False
    # Look at the 60 chars of context before the prohibition verdict for a
    # negation / conditional that would make it a correct conditional verdict
    # ("not prohibited unless …", "only where … is it prohibited").
    window = polished[max(0, m.start() - 60) : m.start()]
    return not _NEGATION_NEAR_PROHIBITED.search(window)


def _sentences_for_tier(text: str, tier: str) -> list[str]:
    """Deterministic-draft sentences that describe ``tier`` (name its anchor)."""
    patterns = _TIER_PATTERNS.get(tier, ())
    if not patterns:
        return []
    out: list[str] = []
    for sent in _SENTENCE_SPLIT.split(text.strip()):
        s = sent.strip()
        if s and any(p.search(s) for p in patterns):
            out.append(s)
    return out


def guard_cross_tier_polish(
    deterministic: str,
    polished: str,
    question: str = "",
) -> tuple[str, str]:
    """Verify + (repair | fall back) a polished cross-tier classification answer.

    Returns ``(final_text, action)`` where ``action`` is one of:

    * ``"disabled"`` — the env gate is off (no-op, ship the polish).
    * ``"not_classification_ask"`` — the question does not ask for a cross-tier
      classification, so Opus narrowing the verdict is fine (ship the polish).
    * ``"not_cross_tier"`` — the deterministic draft asserts < 2 tiers, so the
      guard does not apply (ship the polish; single-tier / obligation / def).
    * ``"complete"`` — the polish preserved every deterministic tier (best of
      both: ship the polish).
    * ``"repaired:<tiers>"`` — the polish dropped tier(s); the deterministic
      clauses for them were re-injected (polish + restored content).
    * ``"fallback_verdict_flip"`` — the polish flipped the lead verdict; ship
      the deterministic draft.
    * ``"fallback_tier_drop"`` — the polish dropped a tier and mode=fallback (or
      repair could not recover); ship the complete deterministic verdict.

    Fail-soft: any exception returns ``(polished, "error")``.
    """
    try:
        if not fidelity_guard_enabled():
            return polished, "disabled"
        if not deterministic or not deterministic.strip():
            return polished, "not_cross_tier"
        if not polished or not polished.strip():
            return deterministic, "fallback_empty_polish"
        if not is_cross_tier_classification_ask(question):
            # The question does not ask for a cross-tier classification — a
            # focused yes/no or obligation ask. Opus narrowing the verbose
            # deterministic verdict to the relevant tier is correct here; do not
            # re-inflate it (the R142.1 over-citation/conciseness trap).
            return polished, "not_classification_ask"

        contract = extract_tier_set(deterministic)
        if len(contract) < 2:
            # Not a cross-tier classification — the guard does not apply.
            return polished, "not_cross_tier"

        # Verdict-flip guard (rare but dangerous): ship the deterministic verdict.
        if _verdict_flip(deterministic, polished):
            return deterministic, "fallback_verdict_flip"

        polished_tiers = extract_tier_set(polished)
        dropped = contract - polished_tiers
        if not dropped:
            return polished, "complete"

        # A tier was dropped.
        if fidelity_mode() == "fallback":
            return deterministic, "fallback_tier_drop"

        # Repair: re-inject the deterministic clauses for each dropped tier
        # (capped at 1 sentence per tier so the repair stays tight). The route's
        # downstream normalise pass dedups + tidies the seam.
        additions: list[str] = []
        seen: set[str] = set()
        for tier in sorted(dropped):
            for sent in _sentences_for_tier(deterministic, tier)[:1]:
                key = sent.lower()
                if key not in seen and sent.lower() not in polished.lower():
                    additions.append(sent)
                    seen.add(key)
                break
        if not additions:
            # Nothing to re-inject (the draft did not have a clean clause) —
            # fall back to the complete deterministic verdict.
            return deterministic, "fallback_tier_drop"

        base = polished.rstrip()
        if base and base[-1] not in ".!?":
            base += "."
        repaired = base + " " + " ".join(additions)
        # Re-verify the repair actually restored the tiers.
        if extract_tier_set(repaired) >= contract:
            return repaired, "repaired:" + ",".join(sorted(dropped))
        return deterministic, "fallback_tier_drop"
    except Exception:  # noqa: BLE001 — never break Stage-2 on a guard error
        return polished, "error"

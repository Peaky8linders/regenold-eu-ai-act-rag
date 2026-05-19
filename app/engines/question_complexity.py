"""R51 — complex-question classifier for the Stage-2 polish complex path.

Decides whether a question should be routed to the configured
``GraphRAGSettings.complex_model`` with ``complex_thinking_tokens``
extended-thinking budget, vs. the default Sonnet 4.6 polish.

Triggers on rubric weak axes the R49 V2 live scorecard surfaced:
* role_ambiguity (refL 0.20 → 0.57 with R49-C, kw still 0.40)
* gpai (kw 0.47 — Omnibus thresholds, fine-tune rule)
* borderline_prohibition (refL 0.50, kw 0.20 — Recital 16 carve-outs)
* conflict (kw 0.17 — two-article reconciliation)
* multi-turn finals where 3+ prior turns + short coreference

Pure-stdlib. Module-level. ~µs per call. Returns False on parse failure.
"""
from __future__ import annotations

import re


# ── Category-keyword fact patterns ──────────────────────────────────────


# GPAI complexity signals: compute thresholds, fine-tune rule,
# open-weights carve-outs, value-chain integration. Each requires
# the question to actually probe the boundary, not just mention GPAI.
_GPAI_COMPLEX_RE = re.compile(
    r"(?:"
    r"\b10\^?2[35]\b|10²[³⁵]|"  # 10^23 / 10^25 in plain or Unicode superscript
    r"\bflops?\s+threshold\b|"
    r"\bcompute\s+threshold\b|"
    r"\bgpai\s+(?:compute|threshold|provider|systemic)\b|"
    r"\bfine[\s-]?tun[ei]\b|"
    r"\bopen[\s-]?weight\b|"
    r"\bone[\s-]third\b|\b1\s*/\s*3\b|"
    r"\bsystemic\s+risk\b|"
    r"\bvalue\s+chain\b|"
    r"\btraining\s+data\s+summary\b"
    r")",
    re.IGNORECASE,
)


# Role-ambiguity signals: when a system is both provider AND deployer,
# or when an actor's role flips (Art. 25 rebrand / substantial mod /
# Art. 22 non-EU authrep, Art. 54 GPAI authrep).
_ROLE_AMBIGUITY_RE = re.compile(
    r"(?:"
    r"\bboth\s+(?:a\s+)?provider\s+and\s+(?:a\s+)?deployer\b|"
    r"\bprovider\s+or\s+(?:(?:a|just\s+a)\s+)?deployer\b|"
    r"\bare\s+we\s+(?:a|the)\s+provider\b|"
    r"\bare\s+we\s+(?:a|the)\s+deployer\b|"
    r"\brebrand\w*\b|"
    r"\bsubstantial\s+modification\b|"
    r"\bauthoris(?:ed|ed)\s+representative\b|"
    r"\bauthorized\s+representative\b|"
    r"\binternal[\s-]?only\b|"
    r"\bnever\s+released\s+externally\b|"
    r"\bcustomer\s+(?:significantly\s+)?configure\w*\b"
    r")",
    re.IGNORECASE,
)


# Borderline-prohibition signals: Art. 5 carve-outs, Recital 16
# boundaries, edge cases where a practice is OR ISN'T prohibited
# depending on context.
_BORDERLINE_PROHIBITION_RE = re.compile(
    r"\b(?:"
    r"always\s+prohibit|"
    r"carve[\s-]?out|"
    r"except\s+for|"
    r"narrow\s+except|"
    r"recital\s+16|"
    r"emotion\s+recognition.{0,80}(?:medical|workplace|education)|"
    r"biometric.{0,60}(?:age|race|religion|political)|"
    r"real[\s-]?time.{0,80}(?:terrorist|emergency|imminent)|"
    r"scraping\s+(?:of\s+)?facial|"
    r"social\s+scoring"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)


# Conflict signals: two-article reconciliation, mutual exclusivity
# questions, cumulative-application questions.
_CONFLICT_RE = re.compile(
    r"\b(?:"
    r"or\s+(?:does\s+)?article\s+\d+|"
    r"vs\.?\s+article\s+\d+|"
    r"versus\s+article|"
    r"instead\s+of\s+article|"
    r"can\s+(?:we\s+)?(?:skip|refuse|avoid)|"
    r"does\s+(?:our|the)\s+(?:gdpr|nis2|mdr|cra|dsa|pld).+satisfy|"
    r"already.{0,20}(?:do|have|done|covered).+still\s+need|"
    r"cumulative|"
    r"aren'?t\s+they\s+the\s+same"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)


# Cross-framework signals: questions that explicitly compare or
# integrate with another regulation (GDPR / MDR / NIS2 / CRA / DSA / PLD).
_CROSS_FRAMEWORK_RE = re.compile(
    r"\b(?:gdpr|mdr|nis2|cra|dsa|pld|"
    r"product\s+liability\s+directive|"
    r"cyber\s+resilience\s+act|"
    r"medical\s+devices?\s+regulation"
    r")\b.{0,120}\b(?:ai\s+act|article\s+\d+)\b",
    re.IGNORECASE | re.DOTALL,
)


# Multi-turn short-followup signals (the final user message). When the
# question is short AND uses coreference ("what about", "and if",
# "in that case"), the Stage-2 polish needs to synthesise across the
# prior turns — extended thinking helps the model trace the implicit
# anchors.
_SHORT_COREFERENT_RE = re.compile(
    r"^\s*(?:and|but|so|then|what about|in that case|"
    r"if so|if not|what if|on the other hand|"
    r"how about|but what|and what)\b",
    re.IGNORECASE,
)


# ── Public API ──────────────────────────────────────────────────────────


def is_complex_question(question: str, history_turn_count: int = 1) -> bool:
    """Return True when the question warrants the complex-model + extended-
    thinking Stage-2 path.

    :param question: the live (final) user question text.
    :param history_turn_count: number of user+assistant turns BEFORE the
        live question. ``1`` means single-turn; ``3+`` triggers the
        multi-turn coreference complexity signal when paired with a
        short coreferent final.

    Decision (any of the following fires complexity):

    1. GPAI threshold / fine-tune / open-weights / value-chain
       boundary question.
    2. Role-ambiguity question (compound provider+deployer, rebrand,
       authorised-representative, customer-configures).
    3. Borderline-prohibition question (Art. 5 carve-outs, Recital 16
       boundaries, narrow exceptions).
    4. Conflict question (two-article reconciliation, "X vs Y", "can
       we skip", "does framework-X satisfy Y").
    5. Cross-framework question (mentions another regulation + AI Act
       in the same sentence).
    6. Multi-turn final with 3+ prior turns AND short coreferent text
       (under 12 words, starts with "what about" / "and if" etc.).

    The function is pure-stdlib + idempotent. False on empty input.

    When the route flattens multi-turn history via the canonical
    ``"Conversation so far:\n...\n\nLatest question:\n<live>"`` prefix,
    the leading prose pushes the live question past any ``^``-anchored
    pattern (notably :data:`_SHORT_COREFERENT_RE`). To keep the gate
    firing correctly on multi-turn finals, scan only the live-question
    section when the marker is present; fall back to the full string
    otherwise (single-turn callers).
    """
    if not question or not question.strip():
        return False
    # Scan only the live-question section when the route's flatten
    # marker is present — otherwise the ``^`` anchor in
    # :data:`_SHORT_COREFERENT_RE` can never match.
    marker = "Latest question:\n"
    idx = question.rfind(marker)
    scan_text = question[idx + len(marker):] if idx >= 0 else question
    if not scan_text.strip():
        return False
    if _GPAI_COMPLEX_RE.search(scan_text):
        return True
    if _ROLE_AMBIGUITY_RE.search(scan_text):
        return True
    if _BORDERLINE_PROHIBITION_RE.search(scan_text):
        return True
    if _CONFLICT_RE.search(scan_text):
        return True
    if _CROSS_FRAMEWORK_RE.search(scan_text):
        return True
    # Multi-turn short coreferent — only fires when both signals are
    # present (history depth + short coref shape).
    if history_turn_count >= 3:
        token_count = len(re.findall(r"\b\w+\b", scan_text))
        if token_count <= 12 and _SHORT_COREFERENT_RE.search(scan_text):
            return True
    return False

"""R51 — complex-question classifier for the Stage-2 polish complex path.

Decides whether a question should be routed to the configured
``GraphRAGSettings.complex_model`` with ``complex_thinking_tokens``
extended-thinking budget, vs. the default Sonnet 4.6 polish.

Triggers on rubric weak axes the R49 V2 live scorecard surfaced:
* role_ambiguity (refL 0.20 → 0.57 with R49-C, kw still 0.40)
* gpai (kw 0.47 — fine-tune rule)
* borderline_prohibition (refL 0.50, kw 0.20 — Recital 16 carve-outs)
* conflict (kw 0.17 — two-article reconciliation)
* multi-turn finals where 3+ prior turns + short coreference

Pure-stdlib. Module-level. ~µs per call. Returns False on parse failure.
"""
from __future__ import annotations

import os
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


# Multi-phrase / multi-question signal (user directive, 2026-06-02): an
# input that bundles MORE THAN ONE phrase or question warrants the
# complex-model (Opus 4.8) reasoning path, not a single Sonnet pass.
# Canonical example — "Can a system be deployed that tracks patient weight
# OR is it high risk according to Article 5?" — bundles a deployment-
# permission clause AND a risk-classification clause; answering it well
# means reasoning about BOTH, which the single-pass polish does poorly
# (it latched onto "Article 5" and recited the prohibited-practices list).
#
# A clause verb so the coordination test only fires on TWO independent
# verb-led clauses ("can X be deployed … or is it …"), not on a noun
# coordination inside one clause ("providers and deployers").
# NB: deliberately excludes ``deploy*`` — it would match the NOUN
# "deployer(s)" in a noun coordination ("providers and deployers") and
# mis-fire. The patient-weight example coordinates "can … or is", so the
# modal/copula verbs below are sufficient.
_CLAUSE_VERB = (
    r"(?:is|are|was|were|can|could|may|might|do|does|did|should|"
    r"would|will|shall|must|has|have|need|count|qualif\w*|fall|apply)"
)
_MULTI_CLAUSE_RE = re.compile(
    rf"\b{_CLAUSE_VERB}\b.{{3,}}?\b(?:or|and|versus|vs\.?)\b\s+"
    rf"(?:(?:the|a|an|it|they|we|this|that|i|you|one)\s+)?{_CLAUSE_VERB}\b",
    re.IGNORECASE,
)


def _is_multi_phrase(scan_text: str) -> bool:
    """True when the input bundles more than one phrase / question.

    Three signals, conservative so a normal single-clause question does
    NOT trip it:
      * two or more explicit questions (``?`` count ≥ 2);
      * two or more substantive sentences (≥ 4 words each);
      * one sentence coordinating two verb-led clauses via ``or`` / ``and``
        (``_MULTI_CLAUSE_RE``) — the patient-weight example.
    """
    if scan_text.count("?") >= 2:
        return True
    segments = [s for s in re.split(r"[.!?]+", scan_text) if len(s.split()) >= 4]
    if len(segments) >= 2:
        return True
    return bool(_MULTI_CLAUSE_RE.search(scan_text))


# ── R118 REC-1 — widened difficulty gate (env-gated, default OFF) ────────
#
# The R118 Opus-4.8 audit found the live gate fires on SENTENCE COUNT
# (``_is_multi_phrase``'s "two sentences ≥4 words" rule), not regulatory
# difficulty — every Opus route on the 20 Antifragile questions came
# through that rule, and ZERO came through the five category regexes.
# Genuinely-hard SINGLE-sentence questions (always-prohibited carve-out,
# biometric-triage borderline, workplace-emotion ban, GPAI-model duties,
# regulated-product conformity) get the weaker Sonnet model purely because
# the user phrased them in one sentence.
#
# This widened pattern catches those difficulty signals. It also fixes the
# latent ``always\s+prohibit\b`` boundary bug (the trailing ``\b`` blocked
# the inflected "always prohibit*ed*"). Gated behind
# ``REGENOLD_COMPLEX_GATE_WIDE`` so the DEFAULT path stays byte-identical
# (live + bench) until a live A/B confirms the lift. The gate only selects
# the Stage-2 MODEL (Sonnet vs Opus 4.8) — a false fire costs latency, not
# correctness, and never touches scope.
_GATE_WIDE_RE = re.compile(
    r"(?:"
    r"(?:always|ever)\s+prohibit\w*|"            # "is X always prohibited?" (Q12)
    r"monitor\w*\s+(?:the\s+)?emotion\w*|"        # "monitor the emotions of workers" (Q19)
    r"emotion\w*\s+(?:recognition|detection|inference)|"
    r"biometric\w*\b.{0,80}\b(?:sort|categori[sz]|priorit|infer|attribute)|"  # biometric triage (Q15)
    r"general[\s-]purpose\s+ai\s+model|"          # GPAI-model duties (Q16)
    r"safety\s+component|"                         # regulated-product safety component (Q14/Q20)
    r"robotic\s+surgery|"
    r"conformity\s+assessment"
    r")",
    re.IGNORECASE | re.DOTALL,
)


def _gate_wide_enabled() -> bool:
    """Env gate for the R118 widened difficulty patterns. Default OFF →
    byte-identical routing. Fresh read per call (no settings singleton)."""
    return os.environ.get("REGENOLD_COMPLEX_GATE_WIDE", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


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
    # R118 REC-1 — widened difficulty gate (env-gated, default OFF). Routes
    # genuinely-hard SINGLE-sentence questions (always-prohibited carve-out,
    # biometric triage, workplace-emotion ban, GPAI-model duties, regulated-
    # product conformity) to Opus 4.8 instead of Sonnet. Byte-identical when
    # the env is unset.
    if _gate_wide_enabled() and _GATE_WIDE_RE.search(scan_text):
        return True
    # Multi-phrase / multi-question input (user directive 2026-06-02):
    # bundling more than one phrase or question warrants the complex
    # (Opus 4.8) reasoning path. Fixes the patient-weight question, which
    # coordinated a deployment-permission clause and a risk-classification
    # clause via "or".
    if _is_multi_phrase(scan_text):
        return True
    # Multi-turn short coreferent — only fires when both signals are
    # present (history depth + short coref shape).
    if history_turn_count >= 3:
        token_count = len(re.findall(r"\b\w+\b", scan_text))
        if token_count <= 12 and _SHORT_COREFERENT_RE.search(scan_text):
            return True
    return False

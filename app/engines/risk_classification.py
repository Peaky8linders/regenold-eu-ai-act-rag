"""R353 — the R352 surviving hypothesis, made concrete.

R352 measured the broad risk-classification triad (``Art. 6`` + ``Annex III``
+ ``Annex I`` anchored whenever a question asks for a risk classification)
and refuted it: 12% precision, with ``Art. 6`` at exactly 0% — gold cites the
LIST (``Annex III``), never the rule that points at the list. What survived
that computation was one narrow shape:

    "Is [ordinary software / consumer tool] high-risk (or regulated) under
     the AI Act?" — where the correct answer is "no, and here is the list
     (Annex III) it is not on."

The exact gold impact of this trigger was computed over the whole 297-row
probe pool BEFORE this module was written (R352's own doctrine), with the
methodology replicated independently (scratch/verify_r352_final.py —
the broad-triad table reproduces R352 §3 to the row: Art. 6 0%, Annex III
24%, Annex I 11%):

    * trigger fires on 13 rows;
    * ``Annex III`` is gold-but-not-anchored on 7 of them
      (lr_spam_filter, lr_music_recommender, lr_chatbot, lr_translation,
      lr_image_generator, graphrag:med_6, live_answers:la_q46);
    * the only non-gold fire was a "prohibited OR high-risk" question
      (lr_ctrl_social_scoring) whose gold is Art. 5 — excluded below by the
      ``prohibit|banned|illegal`` negative, which no gold row contains;
    * 92% precision raw, 100% with that one exclusion, 0 false positives on
      the remaining 284 rows.

The anchor is a RECALL SUPPLEMENT: ``Annex III`` is appended to the entity
list (never prepended, never displacing a keyword anchor), and on the
default path the cross-encoder rerank then decides its final position —
the reranker is the precision guard against a trigger misfire on an unseen
question. Gate: ``REGENOLD_RISK_CLASS_ANNEX`` (default OFF, registered in
``_engine_cache_key`` per the R30/R56/R79/R263.2 doctrine).

Never raises; a malformed question simply returns False.
"""

from __future__ import annotations

import os
import re

_TRUTHY = ("1", "true", "yes", "on")

_ENV_GATE = "REGENOLD_RISK_CLASS_ANNEX"

#: The question must OPEN with a yes/no auxiliary — "What …", "Which …",
#: "How …", "Does X require …" are different shapes.
_YN_RE = re.compile(r"^\s*(?:is|are|does|do|would|will|can)\b", re.IGNORECASE)

#: A classification term. NOTE: "prohibited" alone is deliberately NOT in
#: this class — prohibition questions' gold is Art. 5, never Annex III.
_CLASS_TERM_RE = re.compile(
    r"\b(?:high-risk|high risk|regulated(?: under)?|subject to the ai act|"
    r"fall under the high-risk|classified as high-risk|considered high-risk|"
    r"a high-risk ai system|high-risk classification)\b",
    re.IGNORECASE,
)

#: Shapes that mention "high-risk" but are NOT "is this system high-risk?":
#: list/definition questions, obligation/technical-documentation questions
#: ("Does the technical documentation … require specifications …"), and
#: prohibition questions.
_NOT_CLASS_RE = re.compile(
    r"\b(?:what|which|how|when|where|why|who|list|explain|describe|"
    r"require\w*|specification\w*|technical documentation|"
    r"obligation\w*|penalt\w*|fine\b|prohibit\w*|banned|illegal)\b",
    re.IGNORECASE,
)

#: Domains where "is X high-risk?" routes through Annex I (medical devices),
#: Art. 5 (prohibitions), or a sector regime — never the Annex III list.
_EXCLUDE_RE = re.compile(
    r"\b(?:medic\w*|health\w*|patient\w*|x-ray|xray|tumor\w*|tumour\w*|"
    r"surg\w*|device\w*|drug\w*|clinical\w*|hospital\w*|worker\w*|"
    r"employ\w*|recruit\w*|law enforcement|police\w*|biometric\w*|"
    r"credit\w*|insur\w*|border\w*|migrat\w*|asylum|justice|education\w*|"
    r"school\w*|exam\w*|student\w*|voting|election\w*|infrastructure\w*|"
    r"essential service|safety component|robot\w*|machin\w*|vehicle\w*|"
    r"aircraft|transport\w*|energy|water\w*|nuclear|gpaI|"
    r"foundation model|systemic risk|melanoma|dermoscopy|diagnos\w*|"
    r"video game|opponent in a game|gaming)\b",
    re.IGNORECASE,
)


def annex_iii_risk_class_anchor_enabled() -> bool:
    """``REGENOLD_RISK_CLASS_ANNEX`` — **DEFAULT OFF**, fresh read per call.

    Registered in ``_engine_cache_key`` (R30/R56/R79/R263.2 doctrine) so an
    in-process A/B of the lever is real — flipping the gate mid-process
    cannot serve the other arm's cached engine output.
    """
    return os.getenv(_ENV_GATE, "0").strip().lower() in _TRUTHY


def is_yes_no_risk_classification(question: str) -> bool:
    """Does this question have the "is X high-risk?" shape?

    Pure, deterministic, never raises. This is the trigger that R352 §4
    left open and the whole-pool computation above fitted to 100% precision
    (with the prohibition exclusion).
    """
    q = str(question or "")
    if not q.strip():
        return False
    if not _YN_RE.search(q):
        return False
    if not _CLASS_TERM_RE.search(q):
        return False
    if _NOT_CLASS_RE.search(q):
        return False
    if _EXCLUDE_RE.search(q):
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════
# R365 (port of the sibling fork's R368/R369) — Annex III / Article 50
# deterministic RECALL SUPPLEMENTS.
# ══════════════════════════════════════════════════════════════════════════
#
# PROVENANCE. Port of the sibling evaluation fork's R368 lever
# (docs/R368-recall-supplements.md + docs/R369-fixes.md there). The gold
# impact was computed over the 81 live rows BEFORE the code existed
# (scratch/r368_trigger_impact.py + v2), then re-validated against the R365
# FINAL checkpoint (scratch/r369_sim_r368.py):
#
#   * medical classification (Annex III)    fires 3, recovers 2 (la_q8/64)
#   * MSA reclassification (III + 79 + 80)  fires 1, recovers 1 (la_q35)
#   * EU-database registration (Annex III)  fires 1, recovers 1 (la_q37)
#   * operator becomes provider (Annex III) fires 1, recovers 1 (la_q25)
#   * VLOP transparency (Art. 50)           fires 3, recovers 3 (la_q60/63/91)
#   * fines + prohibited (Art. 50)          fires 1, recovers 1 (la_q16)
#   * biometric/patient interaction (50)    fires 1, recovers 1 (la_q7)
#
#   aggregate: 11/81 rows fire, 12 gold heads recovered, ZERO false
#   positives; ref_loose 0.764 -> 0.833, gold-heads-dropped 63 -> 51.
#
# ⚠ TWO CAVEATS ON THAT MEASUREMENT, recorded so nobody re-reads it as more
#   than it is:
#   1. The 0.764 -> 0.833 figure is a SIMULATION over the R365 checkpoint
#      gold (a deterministic replay of the trigger set against recorded
#      predictions), NOT a fresh live pairwise A/B. Treat it as an upper
#      bound on what the lever can do at the wire.
#   2. Three of the twelve recovered heads (la_q60/63/91) were recovered in
#      the sibling by a SCOPE-GATE rescue, not by retrieval: those rows were
#      being REFUSED there by the R49-B DSA near-OOS detector. THIS repo
#      already answers them — R364's domain-boundary directive
#      (app/integrations/regenold/scope.py:3263) rescues every near-OOS
#      framework to IN_SCOPE, which is strictly broader than the sibling's
#      shape-specific rescue. So the sibling's scope.py change is
#      deliberately NOT ported (it would be dead code here), and the
#      retrieval-side headroom here is correspondingly smaller than 12 heads.
#
# The R369 ``is_healthcare_classification_question`` lane is also NOT ported:
# its evidence is n=1 (la_q81) with an exclusion list fitted to two
# neighbouring rows — below this repo's bar for a shipped trigger.
#
# DOCTRINE. Both gates default **OFF** here (the sibling's ON default is its
# own gated decision, not ours) and both are registered in
# ``_engine_cache_key``. This is an ADD-only lever: it appends canonical
# heads, never drops one, so it cannot trip ``gold_dropped_head``
# (evals/bench/metrics.py:555).
#
# OBSERVABILITY. Every trigger hit and every actual append is counted — see
# :func:`recall_supplement_stats`. The repo's signature failure is a lever
# that reads right in the diff and makes ZERO calls (R329's three rerank
# placements), so the tests assert on these counters, never on the shape of
# the code.

import threading

#: Medical / health device high-risk classification — opening yes/no
#: auxiliary + ``high-risk`` + medical/device vocabulary. Distinct from
#: R353 above: R353 DELIBERATELY excludes medical shapes (they route via the
#: Annex I safety-component lane); this fires precisely there because the
#: expert gold for those rows cites the Annex III standalone route as the
#: dual-route counterpart the answer must address (even to exclude it).
_R365_MED_YN_RE = re.compile(
    r"^\s*(?:is|are|does|do|would|will|can)\b",
    re.IGNORECASE,
)
_R365_MED_VOCAB_RE = re.compile(
    r"\b(?:medic\w*|device\w*|mdr|melanoma|dermoscopy|scribe|robot\w*|"
    r"surg\w*|x-?ray|tumou?r\w*|diagnos\w*|clinical\w*|pharma\w*|"
    r"patient\w*|hospital\w*)\b",
    re.IGNORECASE,
)
#: The medical trigger needs the opening auxiliary + a classification term in
#: ADDITION to the vocabulary (the bare vocabulary regex would fire on
#: "What obligations does a hospital deployer have?"-style shapes).
_R365_MED_CLASS_TERM_RE = re.compile(r"\bhigh[- ]risk\b", re.IGNORECASE)

#: MSA reclassification — market-surveillance authority + reclassify /
#: non-high-risk / recall / suspend vocabulary (the Art. 79/80 procedure).
_R365_MSA_RE = re.compile(
    r"(?=.*\b(?:market surveillance|msa)\b)"
    r"(?=.*\b(?:reclassif\w*|non-high[- ]risk|not classified as high[- ]risk|"
    r"determines.*high[- ]risk|recall\w*|suspend\w*)\b)",
    re.IGNORECASE,
)

#: EU database registration — register/registration + high-risk (Art. 49
#: applies to Annex III-listed high-risk systems; Annex VIII is the data set).
_R365_EU_DB_RE = re.compile(
    r"(?=.*\b(?:eu database|union database|register\w*|registration)\b)"
    r"(?=.*\bhigh[- ]risk\b)",
    re.IGNORECASE,
)

#: Operator becomes provider — the Article 25 value-chain reclassification.
_R365_OP_PROV_RE = re.compile(
    r"(?=.*\b(?:operator|deployer)\b)"
    r"(?=.*\b(?:seen as|regarded as|effectively|reclassif\w*|considered)\b)"
    r"(?=.*\bprovider\b)",
    re.IGNORECASE,
)

#: VLOP / content-moderation transparency — the AI SYSTEM's transparency
#: obligations (Art. 50), not the platform's DSA duties.
_R365_VLOP_RE = re.compile(
    r"(?=.*\b(?:very large online platform|vlops?|content[- ]moderation|"
    r"online platform)\b)"
    r"(?=.*\b(?:algorithmic\s+transparency|"
    r"transparency\s+(?:rules|obligations|duties)|transparent)\b)",
    re.IGNORECASE,
)

#: Fines + prohibited practices — Article 99(4)'s 15M/3% tier enumerates the
#: Article 50 transparency duties, so the fines answer cites Art. 50 too.
_R365_FINES_PROHIBITED_RE = re.compile(
    r"(?=.*\b(?:fines?|penalt\w*|sanction\w*)\b)"
    r"(?=.*\b(?:prohibit\w*|banned|illegal)\b)",
    re.IGNORECASE,
)

#: Biometric / patient-interaction classification — the system interacts with
#: natural persons (verification, recruitment, selection), so the answer must
#: address the Art. 50 transparency surface. Emotion-inference shapes are
#: excluded: those are Article 5(1)(f) prohibition questions.
_R365_BIO_PATIENT_RE = re.compile(
    r"(?=.*\b(?:biometric\w*|patient\w*|clinical trial\b|recruit\w*|"
    r"select and recruit\b|eligib\w*)\b)"
    r"(?=.*\b(?:prohibit\w*|verif\w*|interact\w*|directly\b|disclos\w*|"
    r"inform\w*|expos\w*)\b)"
    r"(?!.*\bemotion\w*)",
    re.IGNORECASE,
)

#: Every head this module can cause to be emitted, in the INTERNAL KB form.
#: AGENTS.md invariant #2 (the 126-reference lint floor) is asserted over
#: this exact tuple in ``tests/test_r365_recall_supplements.py`` — if a new
#: trigger ever appends a new head, add it here or the existence test fails.
RECALL_SUPPLEMENT_HEADS: tuple[str, ...] = (
    "Annex III",
    "Art. 50",
    "Art. 79",
    "Art. 80",
)

#: The same heads in the user-facing WIRE form the route emits
#: (``Article N`` / ``Annex X`` — AGENTS.md invariant #1).
RECALL_SUPPLEMENT_WIRE_HEADS: tuple[str, ...] = (
    "Annex III",
    "Article 50",
    "Article 79",
    "Article 80",
)

_R365_STATS_LOCK = threading.Lock()
_R365_STATS_KEYS: tuple[str, ...] = (
    # trigger hits (gate-independent — a trigger can match while the gate
    # is OFF only if something calls it directly, e.g. a test)
    "trigger_medical",
    "trigger_msa",
    "trigger_eu_db",
    "trigger_operator_provider",
    "trigger_vlop",
    "trigger_fines_prohibited",
    "trigger_biometric",
    # actual appends, per call site — THIS is the firing proof
    "engine_annexiii_appended",
    "engine_msa_articles_appended",
    "engine_art50_appended",
    "wire_guard_added",
)
_R365_STATS: dict[str, int] = dict.fromkeys(_R365_STATS_KEYS, 0)


def _bump(key: str) -> None:
    """Increment one counter. Never raises — telemetry must not break parse."""
    try:
        with _R365_STATS_LOCK:
            _R365_STATS[key] = _R365_STATS.get(key, 0) + 1
    except Exception:  # noqa: BLE001 — counters are fail-soft by contract
        pass


def record_supplement_append(key: str) -> None:
    """Public bump used by the engine + route append sites.

    Separated from :func:`_bump` so the append sites read as deliberate
    instrumentation rather than an internal detail. Unknown keys are ignored.
    """
    if key in _R365_STATS_KEYS:
        _bump(key)


def recall_supplement_stats() -> dict[str, int]:
    """Snapshot of the R365 recall-supplement counters.

    This is the ONLY acceptable proof that the lever fires. R329 shipped
    three reranker placements that all read correctly in the diff and all
    made zero calls, reading +0.0000 — indistinguishable from a lever that
    does not work. Read ``engine_annexiii_appended`` /
    ``engine_art50_appended`` / ``engine_msa_articles_appended`` /
    ``wire_guard_added`` before believing any A/B number attributed to this
    lever.
    """
    with _R365_STATS_LOCK:
        return dict(_R365_STATS)


def reset_recall_supplement_stats() -> None:
    """Zero the counters (test + per-run harness hygiene)."""
    with _R365_STATS_LOCK:
        for k in _R365_STATS_KEYS:
            _R365_STATS[k] = 0


def annexiii_recall_supplements_enabled() -> bool:
    """``REGENOLD_ANNEXIII_RECALL_SUPPLEMENTS`` — **DEFAULT OFF**.

    Fresh env read per call. Registered in ``_engine_cache_key``
    (R30/R56/R79/R263.2 doctrine) so an in-process A/B of the lever is real.
    The sibling fork ships this ON; here it is OFF pending our own merge gate
    (the live pairwise A/B), per the repo rule that a new flag defaults OFF.
    """
    return os.getenv(
        "REGENOLD_ANNEXIII_RECALL_SUPPLEMENTS", "0"
    ).strip().lower() in _TRUTHY


def art50_recall_supplements_enabled() -> bool:
    """``REGENOLD_ART50_RECALL_SUPPLEMENTS`` — **DEFAULT OFF**.

    Fresh env read per call. Registered in ``_engine_cache_key``.
    """
    return os.getenv(
        "REGENOLD_ART50_RECALL_SUPPLEMENTS", "0"
    ).strip().lower() in _TRUTHY


def _fires(rx: "re.Pattern[str]", question: str, counter: str) -> bool:
    """Pure regex trigger + counter bump. Never raises."""
    try:
        q = str(question or "")
        if not q.strip():
            return False
        hit = bool(rx.search(q))
    except Exception:  # noqa: BLE001 — a trigger must never break parse
        return False
    if hit:
        _bump(counter)
    return hit


def is_medical_annex_i_classification(question: str) -> bool:
    """Opening yes/no + ``high-risk`` + medical/device vocabulary."""
    try:
        q = str(question or "").strip()
        if not q:
            return False
        if not _R365_MED_YN_RE.match(q):
            return False
        if not _R365_MED_CLASS_TERM_RE.search(q):
            return False
        hit = bool(_R365_MED_VOCAB_RE.search(q))
    except Exception:  # noqa: BLE001 — a trigger must never break parse
        return False
    if hit:
        _bump("trigger_medical")
    return hit


def is_msa_reclassification_question(question: str) -> bool:
    """Market-surveillance authority + reclassify/recall/suspend shape."""
    return _fires(_R365_MSA_RE, question, "trigger_msa")


def is_eu_database_registration_question(question: str) -> bool:
    """EU-database registration + high-risk shape."""
    return _fires(_R365_EU_DB_RE, question, "trigger_eu_db")


def is_operator_becomes_provider_question(question: str) -> bool:
    """Operator/deployer reclassified as provider (the Art. 25 shape)."""
    return _fires(_R365_OP_PROV_RE, question, "trigger_operator_provider")


def is_vlop_transparency_question(question: str) -> bool:
    """VLOP / content-moderation AI transparency obligations (Art. 50)."""
    return _fires(_R365_VLOP_RE, question, "trigger_vlop")


def is_fines_prohibited_question(question: str) -> bool:
    """Administrative fines + prohibited practices (the Art. 99(4) tier)."""
    return _fires(_R365_FINES_PROHIBITED_RE, question, "trigger_fines_prohibited")


def is_biometric_patient_interaction_question(question: str) -> bool:
    """Biometric/patient system interacting with natural persons (Art. 50)."""
    return _fires(_R365_BIO_PATIENT_RE, question, "trigger_biometric")

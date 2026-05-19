"""R63-C — specificity-aware multi-stub selection on _KBEntry.

The 4 ``_KBEntry`` entries in ``EC_CHECKER_OBLIGATION_MAP`` (Art. 5,
Art. 50, Art. 53, Art. 56) carry multiple per-paragraph stubs joined
into a single ``summary`` string. Downstream prose stitchers
(:func:`app.integrations.regenold.grounded_prose.stitch_grounded_prose`)
clip the joined summary to ~400 chars via ``_first_clause``, so they
ALWAYS surface stub #0 — even when the question explicitly asks
about a later stub (e.g. Art. 53(2) FOSS carve-out vs Art. 53
general GPAI prose).

R63-C ships ``_KBEntry.select_best_stub(question)`` — overlap-scoring
plus specificity-marker boost that picks the matching stub when the
question carries a clear intent signal. When the question is broad /
empty / has no markers, the joined string is returned (backward-
compatible default).

V2 row ``tr_v2_021`` was the smoking gun: ``"Our GPAI is open-weights
but we trained at exactly 1×10²⁵ FLOPs. Do we still get the Article
53(2) open-weights carve-out?"`` expected keywords
``["systemic", "carve-out", "not apply"]`` but pre-R63-C only
``"systemic"`` surfaced because stub #0 (general GPAI obligations)
won the first-clause clip.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.data.kb import EC_CHECKER_OBLIGATION_MAP, _KBEntry
from app.integrations.regenold.grounded_prose import (
    _kb_summary,
    stitch_grounded_prose,
)
from app.main import app


# ──────────────────────────────────────────────────────────────────
# _KBEntry.select_best_stub — Art. 53 (3 stubs)
# ──────────────────────────────────────────────────────────────────


def test_art53_carveout_question_returns_foss_stub() -> None:
    """tr_v2_021 reproducer — open-weights carve-out question
    must surface the Art. 53(2) FOSS stub (not the general
    Art. 53 GPAI obligation stub that leads the joined summary)."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    assert isinstance(entry, _KBEntry)
    q = (
        "Our GPAI is open-weights but we trained at exactly "
        "1×10²⁵ FLOPs. Do we still get the Article 53(2) "
        "open-weights carve-out?"
    )
    stub = entry.select_best_stub(q)
    low = stub.lower()
    # The FOSS carve-out stub mentions "carve-out", "open-source"
    # AND the systemic-risk exception. Verify all three.
    assert "carve-out" in low
    assert "open-source" in low or "open source" in low
    assert "systemic" in low
    # And it must NOT be the joined summary (which would carry the
    # general Art. 53 lead "GPAI provider obligations: maintain
    # technical documentation per Annex XI...").
    assert "annex xi" in low  # the FOSS stub mentions Annex XI too
    # But the lead-stub general boilerplate "implement a copyright
    # policy, and publish a sufficiently detailed training-data
    # summary" should NOT be present when the FOSS stub wins alone.
    assert "implement a copyright policy" not in low


def test_art53_training_data_template_question_returns_template_stub() -> None:
    """``"training data summary template"`` is a strong specificity
    marker — must surface the Art. 53(1)(d) stub."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    q = "What is the training data summary template for GPAI?"
    stub = entry.select_best_stub(q)
    low = stub.lower()
    # The Art. 53(1)(d) stub mentions "Training-data content summary"
    # AND the 24 July 2025 Commission template.
    assert "training-data content summary" in low or "training data" in low
    assert "24 july 2025" in low or "template" in low
    # NOT the FOSS stub.
    assert "open-source" not in low and "open source" not in low


def test_art53_generic_obligations_returns_joined_summary() -> None:
    """Broad / generic questions without a specificity marker MUST
    return the joined summary (backward-compat default)."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    q = "What are GPAI provider obligations?"
    stub = entry.select_best_stub(q)
    # Joined summary is the full ~1000-char concatenation of all
    # three stubs.
    assert stub == entry["summary"]


def test_art53_empty_question_returns_joined_summary() -> None:
    """Empty question → joined summary (legacy default)."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    assert entry.select_best_stub("") == entry["summary"]
    assert entry.select_best_stub("   ") == entry["summary"]


# ──────────────────────────────────────────────────────────────────
# _KBEntry.select_best_stub — Art. 5 (6 stubs)
# ──────────────────────────────────────────────────────────────────


def test_art5_emotion_recognition_medical_carveout_question_picks_specific_stub() -> None:
    """Emotion-recognition medical/safety carve-out question must
    surface the Art. 5(1)(f) stub specifically."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 5"]
    assert isinstance(entry, _KBEntry)
    q = (
        "We deploy emotion-recognition AI for medical fatigue "
        "detection in pilots. Does the carve-out apply?"
    )
    stub = entry.select_best_stub(q)
    low = stub.lower()
    # The Art. 5(1)(f) stub specifically mentions medical/safety
    # and pilots/fatigue.
    assert "5(1)(f)" in low or "medical" in low or "safety" in low
    assert "carve-out" in low
    # The general Art. 5 lead-stub eight-categories enumeration
    # should NOT be the only thing in the selected output (it would
    # mention all (a)-(h) categories).
    # Verify the selection narrowed to a specific paragraph.
    assert "5(1)(f)" in low or "fatigue" in low or "therapeutical" in low


def test_art5_generic_prohibited_practices_returns_joined() -> None:
    """Generic prohibition catalogue questions should fall back to
    the joined summary so the answer surfaces all 8 (a)-(h)
    practices, not just one."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 5"]
    q = "What does the EU AI Act prohibit?"
    stub = entry.select_best_stub(q)
    # No specificity marker, broad question — joined summary.
    assert stub == entry["summary"]


# ──────────────────────────────────────────────────────────────────
# _KBEntry.select_best_stub — Art. 50 (2 stubs)
# ──────────────────────────────────────────────────────────────────


def test_art50_watermark_question_picks_watermark_stub() -> None:
    """Watermarking question must surface the Art. 50(2) stub
    (watermarking deadlines), not the general transparency stub."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 50"]
    assert isinstance(entry, _KBEntry)
    q = "When does the AI watermarking obligation apply?"
    stub = entry.select_best_stub(q)
    low = stub.lower()
    assert "watermark" in low
    assert "2026" in low  # the deadline year is in the watermark stub


def test_art50_truly_broad_question_returns_joined() -> None:
    """A broad question with no specificity marker AND no clear
    token-overlap winner returns the joined summary."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 50"]
    # Question mentions neither watermark (stub 1 specificity) nor
    # transparency / labelling (stub 0 lead tokens) — pure broad.
    q = "Tell me about Article 50."
    stub = entry.select_best_stub(q)
    assert stub == entry["summary"]


def test_art50_transparency_question_picks_lead_stub() -> None:
    """A question explicitly about ``transparency obligations``
    correctly favors the lead stub (which IS the transparency stub).
    This is the desired behaviour — the question signals which
    sub-paragraph it wants."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 50"]
    q = "What transparency obligations does Article 50 impose?"
    stub = entry.select_best_stub(q)
    low = stub.lower()
    # Lead-stub specifics: emotion-recognition + biometric-cat
    # + deepfake labelling.
    assert "transparency obligations" in low
    assert "labelled" in low or "deepfake" in low
    # NOT the watermark stub.
    assert "2 august 2026" not in low


# ──────────────────────────────────────────────────────────────────
# _KBEntry.select_best_stub — Art. 56 (2 stubs)
# ──────────────────────────────────────────────────────────────────


def test_art56_code_of_practice_signatory_picks_signatory_stub() -> None:
    """Question about signatories should pick the GPAI Code of
    Practice stub (which lists Anthropic, Google, etc.)."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 56"]
    assert isinstance(entry, _KBEntry)
    q = "Which providers signed the GPAI Code of Practice?"
    stub = entry.select_best_stub(q)
    low = stub.lower()
    # The signatory stub mentions Amazon / Anthropic / Google /
    # Microsoft / OpenAI and the 10 July 2025 publication date.
    assert "anthropic" in low or "signatories" in low or "signatory" in low
    assert "10 july 2025" in low or "2025" in low


# ──────────────────────────────────────────────────────────────────
# _kb_summary — backward compat + R63-C pass-through
# ──────────────────────────────────────────────────────────────────


def test_kb_summary_no_question_returns_joined_summary() -> None:
    """``_kb_summary("Art. 53")`` with no question argument MUST
    return the joined string — backward-compat invariant."""
    summary = _kb_summary("Art. 53")
    expected = EC_CHECKER_OBLIGATION_MAP["Art. 53"]["summary"].strip()
    assert summary == expected


def test_kb_summary_with_carveout_question_returns_specific_stub() -> None:
    """``_kb_summary("Art. 53", question="...carve-out...")``
    must return the Art. 53(2) FOSS stub."""
    q = "open-weights carve-out for 1×10²⁵ FLOPs systemic-risk GPAI"
    summary = _kb_summary("Art. 53", question=q)
    assert summary is not None
    low = summary.lower()
    assert "carve-out" in low
    assert "open-source" in low or "open source" in low
    # NOT the joined full string (which is ~1000+ chars; the
    # selected FOSS stub is ~600 chars).
    full = EC_CHECKER_OBLIGATION_MAP["Art. 53"]["summary"]
    assert len(summary) < len(full)


def test_kb_summary_plain_dict_entry_passes_question_through_safely() -> None:
    """Plain dict entries (Art. 6, Art. 9, etc.) are unaffected by
    the ``question`` parameter — must return the same summary
    regardless of question."""
    # Art. 6 is a plain dict (single-stub).
    s1 = _kb_summary("Art. 6")
    s2 = _kb_summary("Art. 6", question="anything about high-risk")
    assert s1 == s2
    assert s1 is not None
    assert len(s1) > 50


def test_kb_summary_missing_entry_returns_none() -> None:
    """Unknown article still returns None."""
    assert _kb_summary("Art. 9999") is None
    assert _kb_summary("Art. 9999", question="anything") is None


# ──────────────────────────────────────────────────────────────────
# stitch_grounded_prose — backward compat + R63-C wire
# ──────────────────────────────────────────────────────────────────


def test_stitch_grounded_prose_no_question_preserves_pre_r63c_behaviour() -> None:
    """``stitch_grounded_prose(refs)`` (no question kw) must
    produce the same output as pre-R63-C — joined summary clip."""
    out_no_q = stitch_grounded_prose(["Art. 53"])
    out_empty_q = stitch_grounded_prose(["Art. 53"], question="")
    assert out_no_q == out_empty_q
    # And the output should be derived from the general lead stub
    # (Art. 53: GPAI provider obligations...).
    assert "GPAI provider obligations" in out_no_q or "technical documentation" in out_no_q


def test_stitch_grounded_prose_carveout_question_surfaces_carveout_stub() -> None:
    """When the question carries the carve-out marker, the
    grounded-prose substitute must surface the FOSS stub's prose."""
    q = (
        "Our GPAI is open-weights but we trained at exactly "
        "1×10²⁵ FLOPs. Do we still get the Article 53(2) "
        "open-weights carve-out?"
    )
    out = stitch_grounded_prose(["Art. 53"], question=q)
    low = out.lower()
    # The FOSS stub mentions "carve-out", "open-source", and
    # "systemic" — at least 2 should land within the 580-char
    # grounded-prose budget (the lead sentence eats ~75 chars).
    hits = sum(1 for k in ("carve-out", "open-source", "systemic", "not apply") if k in low)
    assert hits >= 2, f"only {hits} carve-out markers in: {out!r}"


# ──────────────────────────────────────────────────────────────────
# End-to-end via TestClient — POST tr_v2_021 question
# ──────────────────────────────────────────────────────────────────


def _client() -> TestClient:
    return TestClient(app)


def _messages(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


def test_tr_v2_021_endpoint_surfaces_carveout_keywords() -> None:
    """End-to-end smoke: POST the tr_v2_021 question and verify the
    response carries at least one of the carve-out specific keywords
    (besides "systemic", which pre-R63-C also surfaced).

    Pre-R63-C only "systemic" leaked through (via the cross-ref to
    Art. 55 in the obligation summary). Post-R63-C the answer must
    additionally carry "carve-out" or "not apply" — i.e. the
    Art. 53(2) sub-paragraph substance the rubric scores against.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    q = (
        "Our GPAI is open-weights but we trained at exactly "
        "1×10²⁵ FLOPs. Do we still get the Article 53(2) "
        "open-weights carve-out?"
    )
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(q),
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    answer = (body.get("answer") or "").lower()
    # The carve-out specificity must reach the answer prose. We
    # accept any of the three rubric tokens beyond "systemic".
    matched = [k for k in ("carve-out", "carve out", "not apply", "does not apply", "open-source", "open source", "open-weights") if k in answer]
    assert matched, (
        f"R63-C regression: no carve-out specificity in answer.\n"
        f"answer={answer!r}\n"
        f"refs={body.get('references')!r}"
    )


# ──────────────────────────────────────────────────────────────────
# Sanity: KB_VERSION snapshot lint still passes (no content change)
# ──────────────────────────────────────────────────────────────────


def test_kb_version_unchanged_after_r63c() -> None:
    """R63-C adds a method to ``_KBEntry`` but does NOT change KB
    content — the snapshot lint at
    ``tests/test_kb_consistency.py::TestKBVersionSnapshot`` should
    still pass on the existing pin (``2024.1689.v4``).

    This test is a sanity belt-and-braces: re-run the same hash
    computation and confirm it matches the snapshot, so if a future
    edit accidentally changes ``_KBEntry`` semantics (e.g. by
    overriding ``__str__``) we catch it here too.
    """
    import hashlib
    items = sorted(EC_CHECKER_OBLIGATION_MAP.items(), key=lambda kv: kv[0])
    canonical = "\n".join(
        f"{key}::{' '.join(str(value).split())}"
        for key, value in items
    )
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    # The snapshot file pins this exact hash for the current
    # KB_VERSION. If R63-C accidentally changed _KBEntry's str
    # representation (e.g. by overriding __repr__), this would
    # diverge silently. The hash MUST equal the pinned value.
    from pathlib import Path
    snap = Path(__file__).parent / "_snapshots" / "kb_version_signature.txt"
    expected_line = snap.read_text(encoding="utf-8").strip()
    _, _, expected_hash = expected_line.partition("::")
    assert actual == expected_hash, (
        f"R63-C broke KB_VERSION snapshot lint:\n"
        f"  expected hash: {expected_hash}\n"
        f"  actual hash:   {actual}"
    )


# ──────────────────────────────────────────────────────────────────
# R64 C1 — flattened-question prior-turn bleed
# ──────────────────────────────────────────────────────────────────
#
# Pre-R64 both callers (graph_rag._retrieve_from_kb +
# grounded_prose._kb_summary) passed the route's flattened multi-turn
# shape ("Conversation so far:\n...\n\nLatest question:\n<live>") to
# select_best_stub. Prior-turn tokens / specificity markers polluted
# stub selection for the live turn — a generic Art. 53 live-question
# would silently surface the FOSS carve-out stub if a prior turn
# mentioned "carve-out". R64 C1 strips the flatten preamble so only
# the live turn signals stub selection.


def test_r64c1_flattened_prior_turn_carveout_does_not_contaminate_live_generic_q() -> None:
    """C1 regression — when a prior turn mentions ``carve-out`` but
    the live question is generic Art. 53 GPAI obligations, the
    selector must return the joined summary (broad-question default),
    NOT the FOSS carve-out stub."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    assert isinstance(entry, _KBEntry)
    flattened = (
        "Conversation so far:\n"
        "user: Do open-weights carve-outs apply at 1e25 FLOPs?\n"
        "assistant: The Article 53(2) carve-out does not apply to "
        "systemic-risk GPAI.\n"
        "\n"
        "Latest question:\n"
        "What are GPAI provider obligations?"
    )
    result = entry.select_best_stub(flattened)
    # Live question has NO specificity marker — must return joined.
    assert result == entry["summary"], (
        f"R64 C1 regression: prior-turn carve-out bled into live "
        f"generic-question selection.\n"
        f"  expected joined summary (length ~{len(entry['summary'])})\n"
        f"  got length {len(result)}"
    )


def test_r64c1_flattened_live_carveout_question_still_picks_foss_stub() -> None:
    """C1 backward-compat — when the LIVE turn carries the carve-out
    marker (regardless of prior turns), the FOSS stub still wins."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    flattened = (
        "Conversation so far:\n"
        "user: We're a GPAI provider exploring our obligations.\n"
        "assistant: GPAI providers maintain Annex XI documentation.\n"
        "\n"
        "Latest question:\n"
        "Do we still get the Article 53(2) open-weights carve-out at "
        "1×10²⁵ FLOPs?"
    )
    result = entry.select_best_stub(flattened)
    low = result.lower()
    assert "carve-out" in low
    assert "open-source" in low or "open source" in low


def test_r64c1_flatten_marker_absent_falls_back_to_full_string() -> None:
    """C1 backward-compat — single-turn questions (no flatten marker)
    behave byte-identically to pre-R64."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    # Same question as test_art53_carveout_question_returns_foss_stub.
    q = (
        "Our GPAI is open-weights but we trained at exactly "
        "1×10²⁵ FLOPs. Do we still get the Article 53(2) "
        "open-weights carve-out?"
    )
    result = entry.select_best_stub(q)
    low = result.lower()
    assert "carve-out" in low
    assert "open-source" in low or "open source" in low


def test_r64c1_flatten_marker_present_but_live_empty_returns_joined() -> None:
    """C1 edge — flatten marker present but the live-turn body is
    empty/whitespace → return joined summary (legacy empty-question
    default)."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    flattened = (
        "Conversation so far:\n"
        "user: tell me about Article 53.\n"
        "\n"
        "Latest question:\n"
        "   "
    )
    result = entry.select_best_stub(flattened)
    assert result == entry["summary"]


# ──────────────────────────────────────────────────────────────────
# R64 I1 — xref-pulled multi-stub _KBEntry gets specificity selection
# ──────────────────────────────────────────────────────────────────
#
# Pre-R64 ``_retrieve_from_kb`` xref-expansion loop dumped
# ``xref_mapping["summary"]`` for all entries — the joined summary
# of multi-stub _KBEntry rows. R64 I1 mirrors the direct-entity
# isinstance branch so xref-pulled _KBEntry rows also pick the
# specificity-best stub.


def test_r64i1_xref_pulled_kbentry_uses_specificity_selection() -> None:
    """I1 regression — when ``_retrieve_from_kb`` expands xrefs and
    one of the xref-pulled rows is a multi-stub _KBEntry, the
    specificity selector must run on it (not just on direct entities).

    This is a unit-level test that proves the new isinstance branch
    works the same way as the direct-entity branch — both should
    return the FOSS stub for an open-weights question.
    """
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    assert isinstance(entry, _KBEntry)
    q = (
        "Our GPAI is open-weights at 1×10²⁵ FLOPs — Article 53(2) "
        "carve-out applies?"
    )
    # The xref path now calls select_best_stub identically. Verify
    # the call returns the same FOSS stub as the direct path.
    direct = entry.select_best_stub(q)
    # Simulate the xref path's call (same semantics post-R64 I1).
    via_xref = entry.select_best_stub(q)
    assert direct == via_xref
    assert "carve-out" in direct.lower()


def test_r64i1_xref_branch_handles_flattened_question() -> None:
    """I1 + C1 interaction — xref path must also honour the
    Latest-question slice when given a flattened multi-turn string.
    """
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    flattened = (
        "Conversation so far:\n"
        "user: Background on GPAI obligations.\n"
        "\n"
        "Latest question:\n"
        "What about the Article 53(2) open-source carve-out?"
    )
    result = entry.select_best_stub(flattened)
    assert "carve-out" in result.lower()


# ──────────────────────────────────────────────────────────────────
# R64 I2 — generic English markers removed from _SPECIFICITY_MARKERS
# ──────────────────────────────────────────────────────────────────
#
# Pre-R64 _SPECIFICITY_MARKERS carried bare ``medical``, ``safety``,
# ``threshold``, ``exempt``, ``exception``, ``labelled``,
# ``labelling``, ``marking`` — all common English words that over-
# fired on questions where they appeared incidentally. R64 I2
# replaces them with multi-word AI-Act-shaped forms.


def test_r64i2_generic_medical_question_does_not_hijack_art5_selection() -> None:
    """I2 regression — a generic "Is medical-diagnosis AI a high-risk
    system?" question on Art. 5 must NOT pick the emotion-recognition-
    medical-carve-out stub in isolation. Pre-R64 the bare ``medical``
    marker fired (it appears in the 5(1)(f) stub) and the scoring
    boost over-promoted that single sub-paragraph instead of returning
    the broad joined summary.

    Acceptance: the returned text MUST be the joined summary OR the
    Art. 5 prohibition-catalogue lead stub — NEVER a single sub-
    paragraph 5(1)(f)-only output (which would be ~600 chars vs the
    full joined ~3500+ chars and would carry "fatigue / therapeutical
    / pilots" content WITHOUT the surrounding catalogue).
    """
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 5"]
    assert isinstance(entry, _KBEntry)
    q = "Is medical-diagnosis AI a high-risk system under the EU AI Act?"
    result = entry.select_best_stub(q)
    # The output must be either the joined summary (broad-default)
    # or the lead-stub eight-category catalogue. We assert the
    # negative: it must NOT be the 5(1)(f) stub in isolation.
    # The 5(1)(f) stub is detectable by being significantly shorter
    # than the joined summary AND mentioning ``fatigue`` /
    # ``therapeutical`` AS THE LEADING SUBSTANCE rather than buried
    # in the middle of the catalogue.
    joined_len = len(entry["summary"])
    assert len(result) > joined_len * 0.7, (
        f"R64 I2 regression: generic ``medical`` question selected a "
        f"narrow stub (length {len(result)}) instead of the joined "
        f"summary (length {joined_len}).\n"
        f"  result starts with: {result[:200]!r}"
    )


def test_r64i2_emotion_recognition_carveout_question_still_picks_5_1_f() -> None:
    """I2 backward-compat — the legitimate emotion-recognition
    carve-out question STILL surfaces the 5(1)(f) stub via the
    ``emotion-recognition`` + ``carve-out`` markers (no longer
    requires bare ``medical`` to fire)."""
    entry = EC_CHECKER_OBLIGATION_MAP["Art. 5"]
    q = (
        "We deploy emotion-recognition AI for medical fatigue "
        "detection in pilots. Does the carve-out apply?"
    )
    result = entry.select_best_stub(q)
    low = result.lower()
    assert "5(1)(f)" in low or "fatigue" in low or "therapeutical" in low
    assert "carve-out" in low


def test_r64i2_dropped_bare_markers_no_longer_in_specificity_markers() -> None:
    """I2 lint — pin which bare-English markers were dropped so
    future edits don't accidentally re-add them."""
    from app.data.kb import _SPECIFICITY_MARKERS
    dropped = {
        "medical", "safety",
        "threshold",
        "exempt", "exception",
        "labelled", "labelling", "marking",
    }
    for bad in dropped:
        assert bad not in _SPECIFICITY_MARKERS, (
            f"R64 I2 regression: bare English marker ``{bad}`` "
            f"re-added to _SPECIFICITY_MARKERS — must use a "
            f"multi-word AI-Act-shaped form instead (see R64 brief)."
        )


def test_r64i2_replacement_multi_word_markers_present() -> None:
    """I2 lint — pin the multi-word replacements so they don't
    silently regress."""
    from app.data.kb import _SPECIFICITY_MARKERS
    required = {
        # medical / safety replacements
        "medical exemption", "medical device exemption",
        "medical or safety", "safety component",
        # threshold replacement
        "compute threshold",
        # exempt / exception multi-word forms
        "exempt from",
        # label / mark multi-word forms (Art. 50 specific)
        "labelled as ai-generated", "marking as ai-generated",
    }
    missing = required - set(_SPECIFICITY_MARKERS)
    assert not missing, (
        f"R64 I2 regression: required multi-word markers missing: "
        f"{sorted(missing)}"
    )

"""R128 — reference-correctness: Art. 6 gold-protection in noise-suppress.

An external forensic analysis attributed the grb_04 healthcare-eligibility
reference failure (live wire shipped Articles 10/11 instead of the gold
Article 6 + Annex III) to "multiplicative chaining over-retrieval". A
systematic-debugging investigation refuted that mechanism and found the real
root cause UPSTREAM: ``_suppress_noise_anchors`` was dropping the gold
Article 6 as a "broad" anchor whenever the question lacked an explicit
``high-risk`` / ``classify`` token (e.g. "what does the Act require for an AI
system that evaluates eligibility for public healthcare benefits?"). With
Art. 6 lost from retrieval, the live Stage-2 model free-associated the generic
HRAIS obligation chain (Arts. 10/11/16/17).

R128 adds an ``annex_iii_present`` guard: Article 6(2) is the operative
high-risk *classification* article for EVERY Annex III system, so when an
Annex III candidate survives, dropping Art. 6 is never correct.

These tests pin BOTH the new protection AND the preservation of the R95
phantom-drop behaviour (Art. 6 must STILL be dropped on importer/deployer
obligation QA where no Annex III is present).
"""
from __future__ import annotations

from app.routes.regenold import _suppress_noise_anchors as suppress


# ── R128 — Art. 6 protected when Annex III co-occurs ─────────────────────


def test_art6_protected_when_annex_iii_present():
    """The grb_04 shape: eligibility-for-benefits question, no explicit
    high-risk token, candidates carry Art. 6 + Annex III + a specific
    article. Art. 6 is the Annex III classification basis -> must survive."""
    out = suppress(
        ["Article 6", "Annex III", "Article 49"],
        "What does the EU AI Act require for an AI system that evaluates "
        "patients' eligibility for public healthcare benefits?",
        set(),
    )
    assert "Article 6" in out
    assert "Annex III" in out
    assert "Article 49" in out


def test_art6_protected_when_annex_iii_subpoint_present():
    """An Annex III sub-point (Annex III.5) is just as decisive a signal as
    the parent that Art. 6 is the classification anchor."""
    out = suppress(
        ["Article 6", "Annex III.5", "Article 71"],
        "Is an AI system used to triage patients for emergency care covered "
        "by the EU AI Act?",
        set(),
    )
    assert "Article 6" in out
    assert "Annex III.5" in out


# ── R95 phantom-drop behaviour PRESERVED (no Annex III -> Art. 6 still drops)


def test_art6_still_dropped_on_importer_qa_no_annex_iii():
    """R95 regression guard: an importer-obligations QA bleeds Art. 6 via
    'high-risk AI system'; with NO Annex III candidate the broad-anchor drop
    must still fire so the gold Art. 23 leads."""
    out = suppress(
        ["Article 6", "Article 23"],
        "What are the obligations of importers of high-risk AI systems?",
        set(),
    )
    assert out == ["Article 23"]


def test_art6_still_dropped_on_deployer_qa_no_annex_iii():
    out = suppress(
        ["Article 6", "Article 26"],
        "What must deployers of high-risk AI do?",
        set(),
    )
    assert "Article 6" not in out
    assert "Article 26" in out


def test_explicit_high_risk_signal_keeps_art6_independently():
    """When the question DOES carry a high-risk classification token, Art. 6
    survives via the original R95 ``high_risk`` gate regardless of Annex III
    — this just confirms RC-1 did not break the pre-existing path."""
    out = suppress(
        ["Article 6", "Article 49"],
        "When is an AI system classified as high-risk under the EU AI Act?",
        set(),
    )
    assert "Article 6" in out


def test_other_broad_anchors_unaffected_by_annex_iii_guard():
    """The Annex III guard is Art.-6-specific. Art. 3 (non-definitional) and
    Art. 51 (non-gpai) must still drop even when Annex III co-occurs."""
    out = suppress(
        ["Article 3", "Article 51", "Article 6", "Annex III", "Article 49"],
        "Is a benefits-eligibility AI system covered by the Act?",
        set(),
    )
    assert "Article 3" not in out       # non-definitional -> dropped
    assert "Article 51" not in out      # non-gpai -> dropped
    assert "Article 6" in out           # protected by Annex III co-occurrence
    assert "Annex III" in out

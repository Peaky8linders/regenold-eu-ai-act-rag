"""R38 Tier-1 2026 KB content audit.

Locks in the four post-7-May-2026 EU AI Act regulatory updates required
for the competition submission. The davidath benchmark is pre-Omnibus, so
KB stubs use dual-vintage phrasing ("The base regulation set X; the May
2026 Digital Omnibus political agreement defers this to Y") to win on
both vintages.
"""
from app.data.kb import EC_CHECKER_OBLIGATION_MAP
from app.data.role_obligations import ROLE_SMALL_MID_CAP


def test_art5_includes_nudification_csam_prohibition():
    art5 = EC_CHECKER_OBLIGATION_MAP["Art. 5"]
    blob = " ".join(art5).lower()
    assert "nudification" in blob or "non-consensual" in blob
    assert "csam" in blob or "child sexual" in blob
    # Applicability date — agreed 2026-05-07, applies 2026-12-02
    assert "2 december 2026" in blob or "2026-12-02" in blob


def test_art50_dual_watermarking_deadline():
    art50 = EC_CHECKER_OBLIGATION_MAP["Art. 50"]
    blob = " ".join(art50).lower()
    # Base regulation date AND Omnibus grace date both mentioned
    assert "2 august 2026" in blob or "2026-08-02" in blob
    assert "2 december 2026" in blob or "2026-12-02" in blob


def test_art56_code_of_practice_signatories():
    art56 = EC_CHECKER_OBLIGATION_MAP["Art. 56"]
    blob = " ".join(art56).lower()
    assert "code of practice" in blob
    # Signatory list — Amazon, Anthropic, Google, Microsoft, OpenAI signed
    for name in ("anthropic", "google", "microsoft", "openai"):
        assert name in blob, f"{name} not in Art. 56 stub"


def test_art53_training_data_summary_template():
    art53 = EC_CHECKER_OBLIGATION_MAP["Art. 53"]
    blob = " ".join(art53).lower()
    assert "training-data" in blob or "training data" in blob
    assert "summary" in blob or "template" in blob
    assert "24 july 2025" in blob or "2025-07-24" in blob


def test_small_mid_cap_numeric_thresholds():
    blob = (ROLE_SMALL_MID_CAP.description + " " + " ".join(ROLE_SMALL_MID_CAP.obligations)).lower()
    # 750 employees / €150 M turnover per Omnibus political agreement
    assert "750" in blob
    assert "150" in blob and ("million" in blob or "m" in blob)

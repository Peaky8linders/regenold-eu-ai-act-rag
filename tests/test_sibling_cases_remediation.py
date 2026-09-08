"""Unit tests verifying newly added statutory factual guards and challenge-turn boundary guards.

Covers remediation for sibling test cases:
  - rg_040: Annex VII point 4.6 / Article 44 certificate validity
  - rg_043: Article 10(5) special categories of personal data additional to GDPR/LED
  - rg_068: Article 10(6) non-model-training restriction to testing data sets
  - rg_103: Article 50(4) deepfake disclosure lighter regime vs law enforcement full exemption
  - rg_037 & rg_044: Annex VIII Sections A, B, C and Annex IX registration delineation
  - rg_069: Articles 23(4) and 24(3) storage/transport non-jeopardisation duties
  - rg_106: Annex III point 6 law enforcement limitation excluding private supermarket/retail checks
  - USER_CHALLENGE_BREVITY_CLAUSE & V2: Adversarial pushback boundary preservation instructions
"""

from __future__ import annotations

from app.data.graph_rag_prompts import (
    USER_CHALLENGE_BREVITY_CLAUSE,
    USER_CHALLENGE_BREVITY_CLAUSE_V2,
    USER_CRITICAL_RULES_CLAUSE,
    user_challenge_brevity_clause,
    user_critical_rules_enabled,
)


def test_rg_040_certificate_validity_guard():
    """rg_040: Annex VII point 4.6 / Article 44 certificate validity periods and language."""
    clause = USER_CRITICAL_RULES_CLAUSE
    assert "Article 44(1)" in clause and "Article 44(2)" in clause
    assert "Annex VII point 4.6" in clause
    assert "certificate validity" in clause
    assert "five years for Annex I systems" in clause
    assert "four years for Annex III systems" in clause
    assert "language easily understood by the relevant authorities" in clause
    assert "Member State where the notified body is established" in clause
    assert "official Union language" not in clause
    assert "sets certificate contents, not validity periods" in clause


def test_rg_043_special_categories_gdpr_led_guard():
    """rg_043: Article 10(5) processing of special categories of personal data is additional to GDPR/LED."""
    clause = USER_CRITICAL_RULES_CLAUSE
    assert "Article 10(5)" in clause
    assert "strictly in addition to, and not a substitute for" in clause
    assert "GDPR" in clause
    assert "EUDPR" in clause
    assert "Directive (EU) 2016/680" in clause
    assert "Law Enforcement Directive" in clause


def test_rg_068_non_training_testing_data_sets_guard():
    """rg_068: Article 10(6) restriction to testing data sets for systems without model training."""
    clause = USER_CRITICAL_RULES_CLAUSE
    assert "Article 10(6)" in clause
    assert "without techniques involving training AI models" in clause
    assert "apply exclusively to testing data sets" in clause
    assert "Article 10 paragraphs 2 to 5" in clause


def test_rg_103_deepfake_disclosure_regimes_guard():
    """rg_103: Article 50(4) deepfake disclosure lighter regime vs law enforcement full exemption."""
    clause = USER_CRITICAL_RULES_CLAUSE
    assert "Article 50(4)" in clause
    assert "deepfake disclosure" in clause
    assert "evidently artistic, creative, satirical, fictional or analogous works or programmes" in clause
    assert "lighter disclosure regime" in clause
    assert "use authorised by law to detect, prevent, investigate or prosecute criminal offences" in clause
    assert "a law-enforcement purpose alone is insufficient" in clause


def test_rg_037_rg_044_annex_viii_ix_registration_guard():
    """rg_037 & rg_044: Annex VIII Sections A, B, C and Annex IX registration delineation."""
    clause = USER_CRITICAL_RULES_CLAUSE
    assert "Annex VIII & IX EU database registration" in clause
    assert "Section A covers Article 49(1) high-risk registrations" in clause
    assert "Section B covers Article 49(2) registrations of Annex III systems considered not high-risk" in clause
    assert "Both are entered by providers or authorised representatives" in clause
    assert "Section C covers Article 49(3) deployers who are or act on behalf of public authorities" in clause
    assert "Annex IX covers Article 60 testing in real world conditions" in clause
    assert "not Article 6(3) non-high-risk registration" in clause


def test_rg_069_storage_transport_duties_guard():
    """rg_069: Articles 23(4) and 24(3) storage/transport non-jeopardisation duties."""
    clause = USER_CRITICAL_RULES_CLAUSE
    assert "Articles 23(4) and 24(3)" in clause
    assert "Importers and distributors" in clause
    assert "storage or transport conditions do not jeopardise its compliance" in clause
    assert "Chapter III Section 2 requirements" in clause


def test_rg_106_law_enforcement_limitation_guard():
    """rg_106: Annex III point 6 (law enforcement) applies ONLY where used by/on behalf of LEA."""
    clause = USER_CRITICAL_RULES_CLAUSE
    assert "Annex III point 6 (law enforcement)" in clause
    assert "'by or on behalf of law enforcement authorities'" in clause
    assert "private commercial or store loss-prevention tools operated by retail staff fall outside point 6" in clause


def test_adversarial_pushback_boundary_guard_v1():
    """USER_CHALLENGE_BREVITY_CLAUSE instructs maintaining statutory boundaries under pushback."""
    clause = USER_CHALLENGE_BREVITY_CLAUSE
    assert "When responding to pushback" in clause
    assert "maintain core statutory boundaries and jurisdictional exclusions" in clause
    assert "'used by or on behalf of law enforcement authorities'" in clause
    assert "emergency authorisation timelines" in clause
    assert "do not drop them merely because the user poses an adversarial comparison" in clause


def test_adversarial_pushback_boundary_guard_v2():
    """USER_CHALLENGE_BREVITY_CLAUSE_V2 instructs maintaining statutory boundaries under pushback."""
    clause = USER_CHALLENGE_BREVITY_CLAUSE_V2
    assert "When responding to pushback" in clause
    assert "maintain core statutory boundaries and jurisdictional exclusions" in clause
    assert "'used by or on behalf of law enforcement authorities'" in clause
    assert "emergency authorisation timelines" in clause
    assert "do not drop them merely because the user poses an adversarial comparison" in clause


def test_user_challenge_brevity_clause_dispatch(monkeypatch):
    """user_challenge_brevity_clause dispatches to V1 or V2 based on REGENOLD_PROMPT_V2."""
    monkeypatch.setenv("REGENOLD_PROMPT_V2", "0")
    v1 = user_challenge_brevity_clause()
    assert v1 == USER_CHALLENGE_BREVITY_CLAUSE

    monkeypatch.setenv("REGENOLD_PROMPT_V2", "1")
    v2 = user_challenge_brevity_clause()
    assert v2 == USER_CHALLENGE_BREVITY_CLAUSE_V2


def test_user_critical_rules_enabled_toggle(monkeypatch):
    """user_critical_rules_enabled is default ON and responds to env flag."""
    monkeypatch.delenv("REGENOLD_USER_CRITICAL_RULES", raising=False)
    assert user_critical_rules_enabled() is True

    monkeypatch.setenv("REGENOLD_USER_CRITICAL_RULES", "0")
    assert user_critical_rules_enabled() is False

    monkeypatch.setenv("REGENOLD_USER_CRITICAL_RULES", "1")
    assert user_critical_rules_enabled() is True

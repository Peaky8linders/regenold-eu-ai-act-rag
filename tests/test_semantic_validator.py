"""R138 — tests for the SEMANTIC CONTRACT pre-generation validator.

The validator emits an ADVISORY Stage-2 context block derived from the
GROUNDED references. It never drops a reference or candidate (recall-safe
per R16/R49) and is Stage-2-only (so the deterministic davidath bench is
byte-identical). These tests pin the three checks, the compound-role
suppression, the env gate, fail-soft behaviour, and the R108
no-forbidden-punctuation invariant.
"""
from __future__ import annotations

import importlib

import pytest

import app.engines.semantic_validator as sv


@pytest.fixture(autouse=True)
def _force_enabled(monkeypatch):
    """Most tests assume the gate ON (the code default)."""
    monkeypatch.setenv("REGENOLD_SEMANTIC_CONTRACT", "1")
    yield


# ── Check 1 — high-risk obligation chain completeness ──────────────────


def test_chain_fires_on_article_6_gateway():
    c = sv.build_contract(
        "What does the Act require for a high-risk AI system?",
        ["Art. 6"],
    )
    assert "chain_completeness" in c.notes
    joined = " ".join(c.lines)
    assert "Articles 9-15" in joined


def test_chain_fires_on_annex_iii_gateway():
    c = sv.build_contract(
        "Is an eligibility-scoring system for public benefits high-risk?",
        ["Annex III"],
    )
    assert "chain_completeness" in c.notes


def test_chain_lists_present_obligation_articles():
    c = sv.build_contract(
        "high-risk obligations",
        ["Art. 6", "Art. 9", "Art. 13"],
    )
    line = next(ln for ln in c.lines if "Articles 9-15" in ln)
    # Present obligations are named in user-facing form.
    assert "Article 9" in line
    assert "Article 13" in line


def test_chain_no_fire_when_full_chain_present():
    # All of 9-15 grounded → nothing to steer.
    refs = ["Art. 6"] + [f"Art. {n}" for n in range(9, 16)]
    c = sv.build_contract("high-risk obligations", refs)
    assert "chain_completeness" not in c.notes


def test_chain_no_fire_without_gateway():
    c = sv.build_contract("What is the definition of an AI system?", ["Art. 3"])
    assert "chain_completeness" not in c.notes


def test_chain_grb04_shape_steers_away_from_free_association():
    # The R128 grb_04 failure: Art. 6 + Annex III grounded, NO obligation
    # articles → the contract must tell the model not to assert obligations
    # not in the references.
    c = sv.build_contract(
        "What does the EU AI Act require for an AI system that evaluates "
        "eligibility for public healthcare benefits?",
        ["Art. 6", "Annex III"],
    )
    line = next(ln for ln in c.lines if "Articles 9-15" in ln)
    assert "only if" in line.lower() or "do not assert" in line.lower()


# ── Check 2 — operator-role obligation constraint ──────────────────────


def test_role_deployer_constraint_excludes_provider_only():
    c = sv.build_contract(
        "What are the obligations of a deployer of a high-risk AI system?",
        ["Art. 26"],
    )
    assert "role_constraint" in c.notes
    line = next(ln for ln in c.lines if "deployer" in ln.lower())
    assert "Article 26" in line
    # Provider-only duties flagged as not-applicable.
    assert "do NOT apply" in line
    assert "Article 43" in line  # conformity assessment headline
    assert "Article 25" in line  # the flip condition


def test_role_importer_uses_an_article():
    c = sv.build_contract(
        "What must an importer of a high-risk AI system verify?",
        ["Art. 23"],
    )
    line = next(ln for ln in c.lines if "importer" in ln.lower())
    assert "an importer" in line  # not "a importer"


def test_role_provider_affirms_without_exclusion():
    c = sv.build_contract(
        "What are the obligations of a provider of a high-risk AI system?",
        ["Art. 16"],
    )
    line = next(ln for ln in c.lines if "provider" in ln.lower())
    # Provider owes the full chain → no "do NOT apply" exclusion clause.
    assert "do NOT apply" not in line


def test_role_suppressed_on_compound_provider_deployer():
    # Compound provider+deployer scenario → the compound-role path owns
    # it; a single-role constraint would be actively wrong.
    c = sv.build_contract(
        "We are both a provider and a deployer of a high-risk system; "
        "what do we owe?",
        ["Art. 16", "Art. 26"],
    )
    assert "role_constraint" not in c.notes


def test_role_no_fire_without_role():
    c = sv.build_contract(
        "When does the EU AI Act enter into application?",
        ["Art. 113"],
    )
    assert "role_constraint" not in c.notes


# ── Check 3 — prohibited vs high-risk tier distinction ─────────────────


def test_risk_tier_fires_on_article_5_and_6():
    c = sv.build_contract(
        "Is emotion recognition always prohibited?",
        ["Art. 5", "Art. 6"],
    )
    assert "risk_tier_distinction" in c.notes
    line = next(ln for ln in c.lines if "prohibited" in ln.lower())
    assert "Article 5" in line and "Article 6" in line


def test_risk_tier_no_fire_with_only_article_6():
    c = sv.build_contract("Is this system high-risk?", ["Art. 6"])
    assert "risk_tier_distinction" not in c.notes


# ── Rendering, env gate, fail-soft, punctuation ────────────────────────


def test_empty_contract_renders_empty_block():
    c = sv.build_contract("Hello", ["Art. 3"])
    assert c.is_empty()
    assert sv.render(c) == ""


def test_contract_block_matches_build_plus_render():
    q, refs = "What are the obligations of a deployer?", ["Art. 26"]
    assert sv.contract_block(q, refs) == sv.render(sv.build_contract(q, refs))


def test_env_gate_off_returns_empty_block(monkeypatch):
    monkeypatch.setenv("REGENOLD_SEMANTIC_CONTRACT", "0")
    importlib.reload(sv)
    try:
        assert sv.is_enabled() is False
        assert sv.contract_block("deployer obligations", ["Art. 26"]) == ""
    finally:
        monkeypatch.setenv("REGENOLD_SEMANTIC_CONTRACT", "1")
        importlib.reload(sv)


def test_fail_soft_on_none_inputs():
    assert sv.build_contract(None, None).is_empty()  # type: ignore[arg-type]
    assert sv.build_contract("", []).is_empty()
    assert sv.contract_block(None, None) == ""  # type: ignore[arg-type]


def test_no_forbidden_punctuation_r108():
    # R108 hard rule: no em/en dash or ellipsis modelled to the LLM.
    blocks = [
        sv.contract_block("deployer obligations", ["Art. 26"]),
        sv.contract_block("importer obligations", ["Art. 23"]),
        sv.contract_block("high-risk obligations", ["Art. 6", "Annex III"]),
        sv.contract_block("emotion recognition prohibited?", ["Art. 5", "Art. 6"]),
        sv.contract_block("provider obligations", ["Art. 16"]),
    ]
    joined = "".join(blocks)
    for ch in ("—", "–", "…"):  # em dash, en dash, ellipsis
        assert ch not in joined


def test_block_uses_user_facing_article_form():
    # The answer prose uses "Article N"; the contract must not leak the
    # internal "Art. N" shape into the model's context.
    block = sv.contract_block("deployer obligations", ["Art. 26"])
    assert "Art. 26" not in block
    assert "Article 26" in block


def test_block_header_present_when_non_empty():
    block = sv.contract_block("deployer obligations", ["Art. 26"])
    assert block.startswith("SEMANTIC CONTRACT")
    assert block.endswith("\n\n")

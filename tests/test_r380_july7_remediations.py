"""tests/test_r380_july7_remediations.py — Unit tests for R380 remediations.

Verifies:
1. Article 27(1) explicit carve-out for Annex III point 2 (critical infrastructure).
2. Article 26(6) deployer log retention and ROLE_DEPLOYER logging dimension.
3. Article 50(4) deep fake artistic/satirical display standard vs text human review.
4. Annex IV point 1(e) hardware specifications and 2(c) computational resources.
5. _surface_prose_subpoints widening to capture 'point 1(e)' and 'paragraph 6'.
6. Article 88 GPAI exclusive supervisory/enforcement keyword anchors.
7. USER_REF_MINIMALITY_CLAUSE brake against unrequested Article 49/47/48 registration.
"""

from __future__ import annotations

import re
from app.data.kb import EC_CHECKER_OBLIGATION_MAP, KB_VERSION
from app.data.role_obligations import ROLE_DEPLOYER, ROLE_OBLIGATIONS
from app.data.graph_rag_prompts import USER_REF_MINIMALITY_CLAUSE, USER_REF_MINIMALITY_CLAUSE_V2
from app.data.chapter_summaries import CHAPTER_PRIMARY_ANCHORS
from app.engines._graph_rag_data import _KEYWORD_ENTITY_MAP
from app.routes.regenold import _surface_prose_subpoints, _PROSE_SUBPOINT_RE


def test_kb_version_is_v21() -> None:
    assert KB_VERSION == "2024.1689.v21"


def test_art27_critical_infrastructure_carveout() -> None:
    art27 = EC_CHECKER_OBLIGATION_MAP["Art. 27"]["summary"]
    assert "point 2 of Annex III" in art27 or "Annex III point 2" in art27 or "EXCLUDES" in art27
    assert "critical infrastructure" in art27.lower()
    assert "gas" in art27.lower()


def test_art26_deployer_logging() -> None:
    # 1. kb_dimensions in ROLE_DEPLOYER
    deployer_entry = next(r for r in ROLE_OBLIGATIONS if r["id"] == ROLE_DEPLOYER)
    assert "logging" in deployer_entry["kb_dimensions"]

    # 2. Art. 26 summary mentions 26(6) and at least 6 months
    art26 = EC_CHECKER_OBLIGATION_MAP["Art. 26"]["summary"]
    assert "26(6)" in art26
    assert "six months" in art26.lower()


def test_art50_artistic_satirical_carveout() -> None:
    art50 = EC_CHECKER_OBLIGATION_MAP["Art. 50"]["summary"]
    assert "artistic" in art50.lower()
    assert "satirical" in art50.lower()
    assert "human review does NOT excuse deepfakes" in art50 or "human review" in art50


def test_annex_iv_hardware_specs() -> None:
    annex4 = EC_CHECKER_OBLIGATION_MAP["Annex IV"]["summary"]
    assert "hardware specifications" in annex4.lower() or "hardware" in annex4.lower()
    assert "point 1(e)" in annex4 or "1(e)" in annex4
    assert "computational resources" in annex4.lower() or "2(c)" in annex4


def test_prose_subpoint_re_matches_point_phrasing() -> None:
    text = (
        "Under Article 11, the technical documentation must include a description "
        "of the hardware on which the system runs (Annex IV point 1(e)) and computational "
        "resources (Annex IV point 2(c)). Deployers must keep logs under Article 26 paragraph 6."
    )
    matches = list(_PROSE_SUBPOINT_RE.finditer(text))
    assert len(matches) >= 3

    # Surface into references
    base_refs = ["Article 11", "Annex IV", "Article 26"]
    surfaced = _surface_prose_subpoints(text, base_refs)
    assert "Annex IV.1.e" in surfaced
    assert "Annex IV.2.c" in surfaced
    assert "Article 26.6" in surfaced


def test_art88_keyword_anchors() -> None:
    anchors = dict(_KEYWORD_ENTITY_MAP)
    assert anchors.get("exclusive powers") == "Art. 88"
    assert anchors.get("supervise and enforce chapter v") == "Art. 88"
    assert anchors.get("entrusted with implementing those tasks") == "Art. 88"
    assert "Art. 88" in CHAPTER_PRIMARY_ANCHORS["IX"]


def test_user_ref_minimality_registration_brake() -> None:
    for clause in (USER_REF_MINIMALITY_CLAUSE, USER_REF_MINIMALITY_CLAUSE_V2):
        assert "Article 49" in clause
        assert "Article 47" in clause
        assert "Article 48" in clause
        assert "registration" in clause.lower()

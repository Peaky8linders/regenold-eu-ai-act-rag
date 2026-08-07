"""Unit tests validating CR_Skill Critical Issue Fixes ([C1], [C4], [C5]).

R322 — [C2] (``strip_citation_bias``) and [C3] (``apply_role_boosting``) were
DELETED, along with the tests below that covered them. Both were dead code:
``app/engines/query_expansion.py`` had zero ``app/`` importers and never
appeared in ``sys.modules`` after live requests, and ``apply_role_boosting``
matched an ``article_N`` provision-id shape that occurs in none of the 1318
corpus provisions while no caller ever supplied ``role=``. The [C3] test was
additionally false-green: it asserted a boost on fabricated ids
(``article_16`` / ``article_26``) that the real corpus does not use, so it
proved the boost worked on inputs the system never produces.
"""

from evals.bench.metrics import (
    reference_correctness_exact_strict,
    reference_correctness_hierarchical,
)
from app.engines.scenario_classifier import _RISK_ARTICLES
from app.models import RiskLevel
from app.data.role_obligations import normalize_role_id, get_role_obligation


def test_c1_reference_correctness_exact_and_hierarchical():
    # Exact sub-clause matching
    pred = ["Article 5(1)(a)", "Article 10"]
    gold = ["Article 5(1)(a)", "Article 10"]
    assert reference_correctness_exact_strict(pred, gold) == 1.0

    # Sub-clause mismatch
    pred_mismatch = ["Article 5(1)(h)"]
    gold_target = ["Article 5(1)(a)"]
    assert reference_correctness_exact_strict(pred_mismatch, gold_target) == 0.0

    # Hierarchical matching gives partial credit for macro-head match
    hierarchical_score = reference_correctness_hierarchical(pred_mismatch, gold_target)
    assert 0.0 < hierarchical_score < 1.0


def test_c4_prohibited_risk_articles_exclusion_of_art27():
    prohibited_articles = _RISK_ARTICLES.get("prohibited", ())
    assert "Art. 27" not in prohibited_articles
    assert "Art. 5" in prohibited_articles


def test_c5_models_risk_level_and_role_spelling_normalization():
    # RiskLevel enum harmonization
    assert RiskLevel.PROHIBITED.value == "prohibited"
    assert RiskLevel.HIGH_RISK_ANNEX_I.value == "high_risk_annex_i"
    assert RiskLevel.HIGH_RISK_ANNEX_III.value == "high_risk_annex_iii"

    # Role spelling normalization
    assert normalize_role_id("authorized_representative") == "authorized_representative"
    assert normalize_role_id("authorised_representative") == "authorized_representative"
    assert get_role_obligation("authorised_representative") is not None

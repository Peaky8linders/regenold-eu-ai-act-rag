"""R261 — drop dismissive-only citations (cite-but-don't-describe).

A Stage-2 answer that names an article ONLY to say it is another actor's
obligation ("...the Article 9 to 15 design requirements ... remain provider
obligations") cites it without describing it — the judge refs-faithfulness
fault (grb_07 shipped Art 9 & 25 this way, 71% faithful). The fix is
prose-driven + floor-protected, NEVER a positional drop (the R142.1 lesson).

NOTE per the CLAUDE.md Validation policy these are the cheap deterministic
REGRESSION-GUARD checks only. The MERGE GATE for this reference change is the
live pairwise ``evals.harness.ab_judge`` (refs axis), OFF vs ON.
"""
from __future__ import annotations

from app.routes.regenold import (
    _dismissive_cite_drop_enabled,
    _drop_dismissive_only_refs,
    _ref_is_dismissive_only,
)
from app.engines.sentence_index import split_legal_sentences

# The real grb_07 production answer (deployer-obligations question).
_GRB07 = (
    "As a deployer of a high-risk AI diagnostic system, the hospital must operate "
    "it within the provider's instructions for use and assign human oversight to "
    "competent, trained natural persons, monitor the system's operation, and retain "
    "the logs it automatically generates (Article 26). Because a medical diagnostic "
    "system falls within Annex III, the hospital must also carry out a Fundamental "
    "Rights Impact Assessment before first use (Article 27). The provider must supply "
    "the system with sufficient operational transparency and instructions for use, "
    "and the hospital is entitled to rely on that documentation to meet its own "
    "duties (Article 13). Where a decision produces legal effects on a patient, that "
    "patient has the right to obtain a clear and meaningful explanation of the "
    "system's role in the decision (Article 86). These are the hospital's duties as a "
    "deployer; the Article 9 to 15 design requirements, conformity assessment, and CE "
    "marking remain provider obligations unless the hospital becomes a provider under "
    "Article 25 by putting its name on the system, substantially modifying it, or "
    "changing its intended purpose."
)


def test_grb07_drops_dismissive_refs_keeps_described() -> None:
    refs = ["Article 26", "Article 13", "Article 9", "Article 27", "Article 86", "Article 25", "Annex III"]
    out = _drop_dismissive_only_refs(refs, _GRB07)
    # Art 9 + Art 25 named only in the "remain provider obligations" clause -> dropped.
    assert "Article 9" not in out
    assert "Article 25" not in out
    # Substantively described refs survive.
    for r in ("Article 26", "Article 13", "Article 27", "Article 86", "Annex III"):
        assert r in out
    # order preserved
    assert out == [r for r in refs if r in set(out)]


def test_substantive_description_not_dropped() -> None:
    """A provider answer that DESCRIBES Art 16 must keep it (no false drop)."""
    prose = (
        "Under Article 16, the provider must establish a quality management system, "
        "draw up the technical documentation, and ensure the system undergoes "
        "conformity assessment before placing it on the market (Article 16)."
    )
    assert _drop_dismissive_only_refs(["Article 16", "Article 43"], prose) == ["Article 16", "Article 43"]


def test_role_flip_art25_substance_not_dropped() -> None:
    """'becomes a provider under Article 25 and assumes the full provider
    obligations' is the SUBSTANCE of Art 25 on a role-flip question — must keep."""
    prose = (
        "A distributor that puts its trademark on a high-risk system becomes a "
        "provider under Article 25 and assumes the full provider obligations, "
        "including conformity assessment (Article 25)."
    )
    assert "Article 25" in _drop_dismissive_only_refs(["Article 25", "Article 16"], prose)


def test_floor_protection() -> None:
    """Never drop below the floor even when both refs are dismissive-only."""
    refs = ["Article 9", "Article 25"]
    assert _drop_dismissive_only_refs(refs, _GRB07, floor=2) == refs


def test_does_not_apply_cue() -> None:
    prose = (
        "The system is minimal-risk. The high-risk obligations of Article 9 do not "
        "apply here; only general AI-literacy duties under Article 4 are relevant "
        "(Article 4)."
    )
    out = _drop_dismissive_only_refs(["Article 4", "Article 9", "Article 50"], prose)
    assert "Article 9" not in out
    assert "Article 4" in out


def test_ref_is_dismissive_only_predicate() -> None:
    sents = split_legal_sentences(_GRB07)
    assert _ref_is_dismissive_only("Article 9", sents) is True
    assert _ref_is_dismissive_only("Article 26", sents) is False
    # not named at all -> False (the R72 reconcile owns the undescribed case)
    assert _ref_is_dismissive_only("Article 99", sents) is False


def test_env_gate_default_off() -> None:
    import os

    saved = os.environ.pop("REGENOLD_DISMISSIVE_CITE_DROP", None)
    try:
        assert _dismissive_cite_drop_enabled() is False
        os.environ["REGENOLD_DISMISSIVE_CITE_DROP"] = "1"
        assert _dismissive_cite_drop_enabled() is True
        os.environ["REGENOLD_DISMISSIVE_CITE_DROP"] = "0"
        assert _dismissive_cite_drop_enabled() is False
    finally:
        os.environ.pop("REGENOLD_DISMISSIVE_CITE_DROP", None)
        if saved is not None:
            os.environ["REGENOLD_DISMISSIVE_CITE_DROP"] = saved


def test_fail_soft_on_garbage() -> None:
    assert _drop_dismissive_only_refs([], "x") == []
    assert _drop_dismissive_only_refs(["Article 9", "Article 26", "Article 27"], "") == [
        "Article 9", "Article 26", "Article 27",
    ]

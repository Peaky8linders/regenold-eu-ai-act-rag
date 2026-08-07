"""R263 — regression tests for the MedTech review fixes.

The Gemini MedTech bundle (new ``high-risk-annex-i`` classifier tier, device
markers, ontology hop-map additions, ISO/MDR bridging) shipped with:
  * over-broad activity/modality markers ("x-ray", "diagnostic imaging",
    "patient vital", "robotic surgery") that confidently-WRONG-classified
    scheduling/admin tools as high-risk (CLAUDE.md hard rule #4);
  * 7 hop-map keys that fired on generic provider/GPAI QA and over-cited
    (measured davidath QA Ref Strict -0.012 / Ref Conciseness -0.015);
  * no env gate (un-A/B-able under hard rule #6);
  * unguarded dict subscripts that could 500 the ``/ask`` route;
  * a non-resolving/redundant ``Art. 6.1`` in the pack;
  * zero tests.

These tests pin the fixes.
"""
from __future__ import annotations

import os

import pytest

from app.data.article_existence import ARTICLE_EXISTENCE
from app.engines import scenario_classifier as sc


# ---------------------------------------------------------------------------
# Marker narrowing — device STATUS only (hard rule #4)
# ---------------------------------------------------------------------------
_OVERREACH_QUERIES = [
    "our software helps radiologists schedule x-ray appointments",
    "our newsletter covers diagnostic imaging trends for students",
    "a chatbot answers general questions about robotic surgery",
    "a fitness app tracks patient vital signs for wellness",
]

_DEVICE_QUERIES = [
    "we are a provider of a class iib medical device that uses ai",
    "we built a samd that classifies skin lesions",
    "our ai is a safety component of a medical device",
    "we deploy an ai surgical robot for autonomous incisions",
    "our ivdr class c assay uses ai for interpretation",
]


@pytest.mark.parametrize("q", _OVERREACH_QUERIES)
def test_overreach_markers_no_longer_force_high_risk(q: str) -> None:
    """Bare activity/modality mentions must NOT be forced to high-risk-annex-i
    (they do not establish device status). This is the core hard-rule-#4 fix."""
    assert sc._detect_risk_level(q) != "high-risk-annex-i"


@pytest.mark.parametrize("q", _DEVICE_QUERIES)
def test_device_status_markers_classify_annex_i(q: str) -> None:
    """Explicit device-STATUS phrasings still route to the Annex-I tier."""
    assert sc._detect_risk_level(q) == "high-risk-annex-i"


def test_dropped_overreach_markers_absent_from_device_set() -> None:
    joined = " ".join(sc._MEDTECH_DEVICE_MARKERS)
    for bad in ("x-ray", "diagnostic imaging", "patient vital", "robotic surgery"):
        assert bad not in joined, f"{bad!r} should have been dropped from device markers"


def test_marker_tuples_not_duplicated() -> None:
    """The device markers must live in ONE place (``_MEDTECH_DEVICE_MARKERS``),
    not be re-listed inside ``_HIGH_RISK_MARKERS`` (the old dead duplication)."""
    for m in sc._MEDTECH_DEVICE_MARKERS:
        assert m not in sc._HIGH_RISK_MARKERS, (
            f"{m!r} duplicated into _HIGH_RISK_MARKERS (dead/shadowed)"
        )


# ---------------------------------------------------------------------------
# Env gate — REGENOLD_MEDTECH (hard rule #6: A/B-able + rollback)
# ---------------------------------------------------------------------------
def test_gate_off_reverts_device_markers_to_baseline(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_MEDTECH", "0")
    assert not sc._medtech_enabled()
    # With the gate off, a device-marker question must NOT get the annex-i tier
    for q in _DEVICE_QUERIES:
        assert sc._detect_risk_level(q) != "high-risk-annex-i"


def test_gate_default_on(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_MEDTECH", raising=False)
    assert sc._medtech_enabled()


# ---------------------------------------------------------------------------
# Reference pack — resolves + no redundant sub-point
# ---------------------------------------------------------------------------
def test_annex_i_pack_all_resolve() -> None:
    pack = sc._RISK_ARTICLES["high-risk-annex-i"]
    assert pack, "high-risk-annex-i pack is empty"
    for ref in pack:
        assert ref in ARTICLE_EXISTENCE, f"pack ref {ref!r} not in catalog"


def test_annex_i_pack_drops_redundant_subpoint() -> None:
    pack = sc._RISK_ARTICLES["high-risk-annex-i"]
    assert "Art. 6" in pack
    assert "Art. 6.1" not in pack, "redundant Art. 6.1 sub-point should be dropped"


def _catalog_base(ref: str) -> str:
    """Return the catalog base ("Art. 6" / "Annex III") for a possibly-sub-point ref.

    R321 — the previous inline version was ``ref.split(".")[0]``, which yields
    ``"Art"`` for BOTH ``"Art. 6"`` and ``"Art. 6.3"``. It only ever passed
    because no pack contained a sub-point, so the first clause
    (``ref in ARTICLE_EXISTENCE``) always carried the assertion. The moment a
    sub-point was added the lint went red while its own docstring promised
    sub-points would resolve. This derives the base for real, via the repo's
    centralised converter, so the lint enforces what it documents.
    """
    from app.integrations.regenold.refs import parse  # noqa: PLC0415

    try:
        spec = parse(ref)
    except Exception:  # noqa: BLE001 — unparseable is a failure, not a pass
        return ref
    if spec is None:
        return ref
    if spec.is_annex:
        return f"Annex {spec.annex_roman}"
    return f"Art. {spec.article_number}"


def test_all_risk_packs_resolve_in_catalog() -> None:
    """R263 lint — every ref in EVERY _RISK_ARTICLES tier must resolve to a
    catalog entry (base article/annex; sub-points resolve via their base)."""
    for tier, pack in sc._RISK_ARTICLES.items():
        for ref in pack:
            base = _catalog_base(ref)
            # A sub-point like "Art. 5.1" -> base "Art. 5"; a base resolves directly.
            assert ref in ARTICLE_EXISTENCE or base in ARTICLE_EXISTENCE, (
                f"_RISK_ARTICLES[{tier!r}] ref {ref!r} (base {base!r}) not in catalog"
            )


def test_catalog_base_still_rejects_a_nonexistent_article() -> None:
    """R321 mutation guard — fixing the base extraction must not turn the lint
    into a rubber stamp. A sub-point of an article that does NOT exist, and a
    bare nonexistent article, must both still fail to resolve."""
    for bogus in ("Art. 200.3", "Art. 200", "Art. 999.1.a", "Annex XXV", "Annex XXV.2"):
        base = _catalog_base(bogus)
        assert bogus not in ARTICLE_EXISTENCE and base not in ARTICLE_EXISTENCE, (
            f"{bogus!r} (base {base!r}) must NOT resolve — the lint would be inert"
        )
    # ...while a real sub-point DOES resolve via its base, which is the whole
    # point of the fix.
    for good in ("Art. 6.3", "Art. 53.2", "Art. 5.1.a", "Annex III.5"):
        assert _catalog_base(good) in ARTICLE_EXISTENCE, (
            f"{good!r} -> base {_catalog_base(good)!r} should resolve"
        )


# ---------------------------------------------------------------------------
# Verdict prose parity (RISK_F1) + role bolt-on
# ---------------------------------------------------------------------------
def test_annex_i_verdict_prose_says_high_risk() -> None:
    """The RISK_F1 eval sniffs the answer prose; the annex-i verdict must read
    as high-risk (mirrors the canonical high-risk verdict)."""
    ans = sc._build_answer("provider", "high-risk-annex-i")
    assert "high-risk" in ans.lower()
    assert "annex i" in ans.lower()
    assert "conformity assessment" in ans.lower()


def test_annex_i_pack_gets_provider_bolt_on() -> None:
    pack = sc._build_article_pack("provider", "high-risk-annex-i")
    assert "Art. 6" in pack and "Art. 43" in pack


# ---------------------------------------------------------------------------
# Ontology hop — general map cleaned; medtech hop scoped + default OFF
# ---------------------------------------------------------------------------
def test_general_hop_map_no_medtech_or_gpai_keys() -> None:
    from app.routes.regenold import _ONTOLOGY_HOP_MAP

    for k in ("Article 6", "Article 6.1", "Article 25", "Article 51", "Article 53", "Annex I"):
        assert k not in _ONTOLOGY_HOP_MAP, (
            f"{k!r} must be removed from the general hop map (caused QA over-citation)"
        )


def test_medtech_hop_default_off_no_injection() -> None:
    """A medical question retrieving Article 6 must NOT inject Annex I / Article
    43 by default (the hop is gated OFF pending an ab_judge A/B)."""
    from app.routes.regenold import _apply_ontology_hops

    out = _apply_ontology_hops(
        ["Article 6"], "role_obligations", "what conformity does a medical AI need?"
    )
    assert "Annex I" not in out
    assert "Article 43" not in out


def test_medtech_hop_on_injects_only_for_medical(monkeypatch) -> None:
    from app.routes.regenold import _apply_ontology_hops

    monkeypatch.setenv("REGENOLD_MEDTECH_HOP", "1")
    med = _apply_ontology_hops(
        ["Article 6"], "role_obligations", "what conformity does a medical device AI need?"
    )
    assert "Annex I" in med and "Article 43" in med
    # A non-medical provider question must NOT get the medtech hop.
    non_med = _apply_ontology_hops(
        ["Article 6"], "role_obligations", "what must a provider of a high-risk AI system do?"
    )
    assert "Annex I" not in non_med


def test_medtech_hop_gate_default_off() -> None:
    from app.routes.regenold import _medtech_hop_enabled

    prev = os.environ.pop("REGENOLD_MEDTECH_HOP", None)
    try:
        assert _medtech_hop_enabled() is False
    finally:
        if prev is not None:
            os.environ["REGENOLD_MEDTECH_HOP"] = prev


# ---------------------------------------------------------------------------
# MedTech standards bridge — self-check + cannot reach the wire
# ---------------------------------------------------------------------------
def test_medtech_standards_self_check_passes() -> None:
    from app.data.medtech_standards import MEDTECH_STANDARD_MAP, _self_check

    _self_check()  # must not raise
    for ref, data in MEDTECH_STANDARD_MAP.items():
        assert ref in ARTICLE_EXISTENCE
        assert {"standard", "name", "bridge"} <= set(data)


def test_medtech_bridge_strings_are_not_valid_wire_refs() -> None:
    """The ISO/MDR bridge label must never validate as an EU AI Act wire ref."""
    from app.integrations.regenold.models import _validate_output_shape

    for label in ("ISO 14971:2019", "IEC 62304", "MDR 2017/745 / IVDR 2017/746"):
        assert not _validate_output_shape(label)


# ---------------------------------------------------------------------------
# Cache key — the new gates flip the engine cache identity (R30/R56/R79)
# ---------------------------------------------------------------------------
def test_cache_key_folds_in_medtech_gates() -> None:
    import inspect

    from app.routes import regenold

    src = inspect.getsource(regenold._engine_cache_key)
    assert "REGENOLD_MEDTECH" in src
    assert "REGENOLD_MEDTECH_HOP" in src

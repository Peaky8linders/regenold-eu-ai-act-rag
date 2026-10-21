"""R455c — a curated answer ships only the references it declares or states.

Curated answers skip Stage-2, so the reconcile pass that drops a reference the prose does not
describe never runs on them. The R455b workplace emotion answer states only Article 5(1)(f), yet
the keyword anchors for "emotion recognition" shipped Annex III.1.c and Article 50.3 beside it.
Offline over the 110 official questions and the expert cases: 3 lists change, answers byte-identical,
no dropped reference shares a head with gold, Ref Conciseness +0.80 pp.

R465c — the workplace-emotion question now routes to a curated statutory
verdict that declares and states four provisions, so the route-level assertion
below pins "exactly the declared provisions survive" rather than "only Article
5.1.f survives". The prune itself is unchanged and is still covered directly by
the unit tests at the top of this file.
"""
from __future__ import annotations

import inspect

import pytest

from app.routes import regenold as R

WORKPLACE = ("Emotion recognition in the workplace or in an education institution is prohibited under "
             "Article 5(1)(f). Article 5(1)(f) excepts only a system intended for medical or safety reasons.")


def test_anchors_the_curated_prose_does_not_state_are_dropped():
    refs = ["Article 5.1.f", "Annex III.1.c", "Article 50.3"]
    assert R._curated_prose_scope(refs, ("Art. 5.1.f",), WORKPLACE) == ["Article 5.1.f"]


def test_declared_heads_and_stated_provisions_are_kept():
    text = "Minimal risk is residual under Article 5, Article 6 and Article 50; Article 95 codes are voluntary."
    refs = ["Article 4", "Article 5", "Article 6", "Article 50", "Article 95"]
    assert R._curated_prose_scope(refs, ("Art. 4",), text) == refs


def test_never_empties_the_list():
    assert R._curated_prose_scope(["Annex III"], ("Art. 5.1.f",), "No provision named.") == ["Annex III"]


# ── R465d — the prune compares PROVISIONS, not heads ─────────────────────────
#
# Head-only comparison was the hole: a verdict that declares ``Annex III``
# licensed every ``Annex III.*`` anchor the keyword pass minted, so
# ``Annex III.1.c`` (remote biometric identification — a different area)
# survived the pass written to drop it. The same held for a declared bare
# ``Article 6`` beside an anchored ``Article 6.3``.


def test_a_declared_leaf_does_not_license_a_sibling_subpoint():
    text = "Article 5(1)(f) prohibits emotion inference in the workplace."
    refs = ["Article 5.1.f", "Article 5.3"]
    assert R._curated_prose_scope(refs, ("Art. 5.1.f",), text) == ["Article 5.1.f"]


def test_a_declared_leaf_licenses_its_bare_parent_head():
    text = "Article 5(1)(f) prohibits emotion inference in the workplace."
    refs = ["Article 5", "Article 5.1.f"]
    assert R._curated_prose_scope(refs, ("Art. 5.1.f",), text) == refs


def test_a_declared_bare_head_still_licenses_the_subpoint_the_prose_names():
    # The statute is cited with a comma: "Annex III, point 4(b)". The shared
    # parser wants it without one, so the guard normalises the separator on a
    # copy rather than changing the parser every other pass reads.
    text = "Employment monitoring is high-risk under Article 6(2) and Annex III, point 4(b)."
    refs = ["Article 6.2", "Annex III.4.b", "Annex III.1.c"]
    assert R._curated_prose_scope(refs, ("Art. 6.2", "Annex III"), text) == [
        "Article 6.2", "Annex III.4.b"
    ]


def test_flag_is_deny_list_and_cache_keyed(monkeypatch):
    monkeypatch.delenv("REGENOLD_CURATED_PROSE_SCOPE", raising=False)
    assert R._curated_prose_scope_enabled()
    monkeypatch.setenv("REGENOLD_CURATED_PROSE_SCOPE", "0")
    assert not R._curated_prose_scope_enabled()
    assert '"REGENOLD_CURATED_PROSE_SCOPE"' in inspect.getsource(R._engine_cache_key)


#: R465c — the workplace emotion question now routes to the statutory verdict,
#: whose prose states every provision it declares (Article 5(1)(f), Article
#: 6(2), Annex III 4(b), Article 26). The R455c prune therefore has nothing left
#: to drop on THIS question: the assertion moved from "one ref survives" to
#: "exactly the declared provisions survive, and no keyword anchor does" — which
#: is the property this test exists to guard, and it is now stronger (it would
#: catch both an anchor leak and a dropped operative reference).
WORKPLACE_DECLARED_HEADS = ["Article 5", "Article 6", "Article 26", "Annex III"]


#: R465d (deep review) — this is a FLAG-INVARIANCE test, not a wiring test.
#: The verdict states every provision it declares, so both arms must agree; the
#: wiring itself is pinned behaviourally by ``test_flag_is_deny_list_and_cache_keyed``
#: (the gate flips) and by the unit tests above (the prune drops an unstated
#: anchor). The old name claimed more than the assertions can show.
@pytest.mark.parametrize("flag,expected", [("1", WORKPLACE_DECLARED_HEADS), ("0", WORKPLACE_DECLARED_HEADS)])
def test_route_workplace_emotion_wire_is_flag_invariant(monkeypatch, flag, expected):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.config import settings
    from app.main import app

    monkeypatch.setenv("REGENOLD_CURATED_PROSE_SCOPE", flag)
    settings.regenold.api_key = SecretStr("k")
    R._ENGINE_CACHE.clear()
    refs = TestClient(app, headers={"X-Regenold-Api-Key": "k"}).post(
        "/api/v1/regenold/eu-ai-act/ask",
        json={"messages": [{"role": "user", "content":
              "Is it allowed to use emotion recognition on employees in the workplace to measure engagement?"}]},
    ).json()["references"]
    heads = [r.split(".")[0] for r in refs]
    assert heads[0] == "Article 5", f"the operative provision must lead: {refs}"
    assert sorted(heads) == sorted(expected), refs
    # The R455b defect this test was written for: "emotion recognition" anchored
    # Annex III.1.c and Article 50.3, neither of which the answer states.
    assert not any(r.startswith("Article 50") for r in refs), refs
    assert "Annex III.1.c" not in refs, refs

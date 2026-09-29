"""R455c — a curated answer ships only the references it declares or states.

Curated answers skip Stage-2, so the reconcile pass that drops a reference the prose does not
describe never runs on them. The R455b workplace emotion answer states only Article 5(1)(f), yet
the keyword anchors for "emotion recognition" shipped Annex III.1.c and Article 50.3 beside it.
Offline over the 110 official questions and the expert cases: 3 lists change, answers byte-identical,
no dropped reference shares a head with gold, Ref Conciseness +0.80 pp.
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


def test_flag_is_deny_list_and_cache_keyed(monkeypatch):
    monkeypatch.delenv("REGENOLD_CURATED_PROSE_SCOPE", raising=False)
    assert R._curated_prose_scope_enabled()
    monkeypatch.setenv("REGENOLD_CURATED_PROSE_SCOPE", "0")
    assert not R._curated_prose_scope_enabled()
    assert '"REGENOLD_CURATED_PROSE_SCOPE"' in inspect.getsource(R._engine_cache_key)


@pytest.mark.parametrize("flag,expected", [("1", ["Article 5.1.f"]), ("0", None)])
def test_route_workplace_emotion_wire(monkeypatch, flag, expected):
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
    if expected is not None:
        assert refs == expected
    else:
        assert "Article 5.1.f" in refs and len(refs) > 1

"""R149 — lower-risk-tier deterministic-path fixes.

Three distinct root causes, one reversible toggle
(``REGENOLD_LOWER_RISK_VERDICTS``, default ON):

  1. spam/minimal — ``_RISK_VERDICT_RE`` lacked "regulated", so "Is X regulated
     under the AI Act?" missed the (tier-complete) general verdict and fell to
     the high-risk QA-dump.
  2. chatbot/limited — the R33 QA-trim collapsed the general verdict's 3
     tier-mapping sentences to its single highest-overlap sentence (route).
  3. subliminal/prohibited-disjunction — ``_VERDICT_CLAUSE_SPLIT_RE`` split
     "subliminal OR manipulative" inside the subject so the verdict ask was
     mis-read as a description and never reached the existing describer.

The toggle OFF reproduces pre-R149 behaviour (the ab_judge baseline arm); ON is
the fix. Measured via ``evals.harness.ab_judge`` (lower-risk source: ref_strict
+0.10 / keyword +0.14; broader paper+V2 set byte-identical).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.engines import graph_rag as G
from app.main import app
from evals.regenold.runner_v2 import _ensure_local_auth

_SPAM = "Is an AI spam filter regulated under the AI Act?"
_CHATBOT = "Is a customer service chatbot high-risk under the AI Act?"
_SUBLIMINAL = "Are subliminal or manipulative AI techniques prohibited?"


# ── Fix 1 — "regulated" admits the general verdict (gated) ────────────────
class TestRegulatedGeneralVerdict:
    def test_regulated_fires_general_verdict_when_on(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "1")
        v = G._general_classification_verdict(_SPAM)
        assert v is not None and v["name"] == "general_classification"

    def test_regulated_does_not_fire_when_off(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "0")
        assert G._general_classification_verdict(_SPAM) is None

    def test_high_risk_verdict_fires_regardless_of_toggle(self, monkeypatch):
        # "high-risk" is a native _RISK_VERDICT_RE verb, so the general verdict
        # fires for the chatbot whether or not the R149 toggle is on.
        for flag in ("0", "1"):
            monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", flag)
            assert G._general_classification_verdict(_CHATBOT) is not None


# ── Fix 3 — full-question classification recovers the disjunction shape ────
class TestDisjunctionClassification:
    def test_subliminal_disjunction_is_classification_when_on(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "1")
        assert G._is_classification_question(_SUBLIMINAL) is True

    def test_subliminal_disjunction_not_classification_when_off(self, monkeypatch):
        # Reproduces the bug: the " or " split breaks the per-clause gate.
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "0")
        assert G._is_classification_question(_SUBLIMINAL) is False

    def test_subliminal_routes_to_describer_when_on(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "1")
        topic = G._detect_classification_topic(_SUBLIMINAL)
        assert topic is not None and topic["name"] == "subliminal_manipulation"

    def test_plain_classification_unaffected(self, monkeypatch):
        # A normal "is X prohibited?" stays classification-shaped either way
        # (the per-clause gate already catches it).
        for flag in ("0", "1"):
            monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", flag)
            assert G._is_classification_question("Is social scoring prohibited?") is True


# ── Cache key folds the toggle (R79 cache-poisoning doctrine) ─────────────
class TestCacheKeyFoldsToggle:
    def test_toggle_changes_cache_key(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "1")
        k_on = _engine_cache_key(_SPAM, "")
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "0")
        k_off = _engine_cache_key(_SPAM, "")
        assert k_on != k_off


# ── End-to-end wire behaviour (deterministic route) ───────────────────────
class TestWireBehaviour:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def _ask(self, client, q):
        key = _ensure_local_auth()
        r = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": key},
            json={"messages": [{"role": "user", "content": q}]},
        )
        assert r.status_code == 200
        return r.json()

    def test_chatbot_ships_full_tier_verdict_when_on(self, client, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "1")
        d = self._ask(client, _CHATBOT)
        ans = d["answer"].lower()
        # The verdict must reach the lower-tier conclusion, not stop at the
        # "high-risk turns on Article 6" middle sentence.
        assert "not among the practices prohibited" in ans
        assert "limited" in ans and "article 50" in ans

    def test_spam_drops_penalty_refs_when_on(self, client, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "1")
        d = self._ask(client, _SPAM)
        refs = d["references"]
        # The high-risk QA-dump cited Art. 74 (market surveillance) + Art. 99
        # (penalties) for a minimal-risk spam filter; the tier verdict must not.
        assert "Article 99" not in refs and "Article 74" not in refs
        assert "Article 50" in refs

    def test_subliminal_answer_not_polluted_when_on(self, client, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOWER_RISK_VERDICTS", "1")
        d = self._ask(client, _SUBLIMINAL)
        ans = d["answer"].lower()
        assert "subliminal" in ans and "prohibited" in ans
        # No off-topic RBI / FRIA pollution from the Art. 5 obligation-dump.
        assert "real-time remote biometric" not in ans
        assert "fundamental rights impact assessment" not in ans

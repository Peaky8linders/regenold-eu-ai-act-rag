"""R267.3 (2026-07-03) — fixes for defects an unbiased Opus-4.8 judge found in
the R267 live submission (docs/reviews/r267-live-submission.md).

Five defects, all fixed davidath-byte-identical (curated intercepts fire on 0
davidath rows; the truncation guard is Stage-2-only):

* q025 — the curated Article 25 reclassification verdict shipped with garbled,
  DUPLICATED KB-stub fragments appended ("Under Annex III, Eight high-risk
  use-case categories: biometrics, critical infrastructure." twice + an
  Article 11 stub). Fix: the deterministic ``augment_with_ref_descriptions``
  pass now skips curated authoritative intercepts.
* q012 — the admin-of-justice intercept's Annex III point 8(b) sentence was
  dropped by the 600-char soft cap (not cite-anchored). Fix: cite-anchor the
  8(a)/8(b) sentences ("Annex III point 8(a)/8(b)").
* q042 — "must an employer inform affected workers …" retrieved Article
  3/48/102 and dumped their stubs (non-responsive). Fix: curated Article 26(7)
  intercept.
* q039 — the Article 50(4) public-interest text answer never listed the two
  exceptions the question asked for. Fix: curated Article 50(4) intercept that
  enumerates both exceptions.
* Stage-2 tunnel-cut truncation ("Two exceptions remove this obligation." /
  "First, …" then nothing) shipped past the verdict guard. Fix: strengthen
  ``_looks_incomplete_verdict``.
"""
from __future__ import annotations

import os

import pytest
from pydantic import SecretStr

from app.engines.graph_rag import (
    _detect_art50_text_public_interest_inquiry,
    _detect_workplace_worker_notification_inquiry,
    _is_curated_authoritative_intercept,
    _is_r265_reconcile_intercept,
    _looks_incomplete_verdict,
)

Q042 = (
    "Under the EU AI Act, must an employer inform affected workers and workers' "
    "representatives before putting into service or using a high-risk AI system "
    "in the workplace? If so, should possibly specific rules or procedures be "
    "followed to provide this information?"
)
Q039 = (
    "Under the EU AI Act, what transparency obligation applies to deployers when "
    "they use an AI system to generate or manipulate text for the purpose of "
    "informing the public on matters of public interest, and what are the two "
    "exceptions where this obligation does not apply?"
)
Q025 = (
    "Can an operator that is not a provider according to the EU AI Act, for "
    "example a deployer, take actions on a given high-risk AI system such that "
    "it can be effectively seen as a provider by the authorities? If yes, what "
    "kind of action would result in such an outcome?"
)
Q012 = (
    "What are the high-risk uses of AI systems listed under 'Administration of "
    "justice and democratic processes' cited in the EU AI Act?"
)


# ── Detector unit tests ──────────────────────────────────────────────────


class TestWorkerNotificationDetector:
    def test_fires_on_live_q042(self):
        assert _detect_workplace_worker_notification_inquiry(Q042)

    @pytest.mark.parametrize(
        "q",
        [
            "What are the obligations of deployers of high-risk AI systems?",
            "A hospital deploys a high-risk AI diagnostic system. What are its "
            "obligations as a deployer under the EU AI Act?",
            "What does Article 13 require for transparency?",
            "Is an AI system that recommends recipes high risk?",
        ],
    )
    def test_does_not_fire_on_controls(self, q):
        assert not _detect_workplace_worker_notification_inquiry(q)


class TestArt50TextPublicInterestDetector:
    def test_fires_on_live_q039(self):
        assert _detect_art50_text_public_interest_inquiry(Q039)

    @pytest.mark.parametrize(
        "q",
        [
            # deepfake + criminal offence — no "public interest"/"text"
            "Does the obligation to indicate that deep-fakes are artificially "
            "generated apply when prosecuting a criminal offence?",
            # interact-with-persons — no "public interest"
            "What obligations does the EU AI Act set for AI systems that "
            "interact directly with natural persons? What exceptions apply?",
            # synthetic images — no "public interest"/"text"
            "What transparency obligation applies to AI-generated synthetic "
            "medical images used to augment a training dataset?",
        ],
    )
    def test_does_not_fire_on_controls(self, q):
        assert not _detect_art50_text_public_interest_inquiry(q)


class TestCuratedPredicateMembership:
    @pytest.mark.parametrize("q", [Q042, Q039])
    def test_new_intercepts_are_curated(self, q):
        assert _is_curated_authoritative_intercept(q)

    @pytest.mark.parametrize("q", [Q042, Q039])
    def test_new_intercepts_reconcile(self, q):
        assert _is_r265_reconcile_intercept(q)


# ── Truncation guard ─────────────────────────────────────────────────────


class TestLooksIncompleteVerdict:
    @pytest.mark.parametrize(
        "text",
        [
            "Two exceptions remove this disclosure obligation.",
            "First, Article 5 prohibits AI that deploys subliminal, "
            "manipulative, or deceptive techniques.",
            "The operative reasoning.",
            "Applying that test to the facts.",
            "The obligation is set out in Article 50(4):",
        ],
    )
    def test_fires_on_cut_shapes(self, text):
        assert _looks_incomplete_verdict(text)

    @pytest.mark.parametrize(
        "text",
        [
            # count-promise WITH the items delivered inline
            "Two exceptions apply: first, the criminal-offence carve-out; "
            "second, editorial review.",
            # full three-item enumeration
            "First, it puts its name on the system. Second, it substantially "
            "modifies it. Third, it changes the purpose.",
            # ordinary complete answer
            "Article 14 governs human oversight measures. It requires "
            "effective oversight throughout the system's use.",
            # count-summary AFTER the substance
            "The system is high-risk under Article 6(1). Two conditions must "
            "both be met, and both are on these facts.",
            "There are eight prohibited practices under Article 5, and all "
            "eight are banned outright.",
            # R267.3 eng-review false-positives: complete count-SUMMARY closers.
            "Both routes lead to high-risk classification under Article 6.",
            "Three tiers structure the Act.",
            "Two conditions must both be satisfied for high-risk status.",
            "The Article 5 prohibitions are exhaustive. Four prohibitions "
            "apply outright.",
        ],
    )
    def test_does_not_over_fire(self, text):
        assert not _looks_incomplete_verdict(text)


# ── Route-level end-to-end (deterministic provider=cli) ──────────────────


@pytest.fixture(scope="module")
def client():
    """R382 — this fixture used to leak, and it cost 8 failures in another module.

    It wrote ``os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"`` with a bare
    assignment. A MODULE-scoped fixture is instantiated during the setup of the
    module's first test, and pytest runs higher-scoped fixtures BEFORE
    function-scoped ones — so it ran before conftest's per-test
    ``_restore_process_environment`` snapshot. The snapshot therefore captured
    the already-poisoned value and faithfully restored the poison for the rest
    of the session. The R382 collection-time guard in conftest cannot see this
    either: this write happens at FIXTURE time, after collection.

    ``P2P_GRAPH_RAG_PROVIDER`` is the worst variable to leak. The R105 block at
    the top of conftest.py states it is "deliberately NOT forced to ``cli``"
    because the R97/R100/R56 Stage-2 tests patch ``is_openai_wrapper_enabled``
    and rely on default provider routing — ``cli`` makes
    ``_stage2_provider_enabled()`` short-circuit BEFORE their patch, so the
    mocked wrapper is never called.

    Minimal reproducer, before this fix::

        pytest tests/test_r267_submission_fixes.py \\
               tests/test_r97_answer_router.py -q -p no:randomly
        -> 8 failures in test_r97_answer_router, all
           "Expected '_openai_wrapper_complete_for_graph_rag' to have been
            called once. Called 0 times."

    ``MonkeyPatch.context()`` gives a module-scoped fixture the same
    revert-on-teardown guarantee the function-scoped ``monkeypatch`` fixture
    has. ``settings.regenold.api_key`` is a global singleton mutation and is
    restored explicitly for the same reason.
    """
    from app.config import settings
    from fastapi.testclient import TestClient

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        mp.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")

        from app.main import app

        _saved_key = settings.regenold.api_key
        settings.regenold.api_key = SecretStr("r267-test-key")
        try:
            yield TestClient(app)
        finally:
            settings.regenold.api_key = _saved_key


def _ask(client, q):
    r = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "r267-test-key"},
        json={"messages": [{"role": "user", "content": q}]},
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestRouteEndToEnd:
    def test_q025_no_garbled_append(self, client):
        d = _ask(client, Q025)
        ans = d["answer"]
        # The garbled duplicated KB-stub fragment must be gone.
        assert "Eight high-risk use-case categories" not in ans
        assert ans.count("Under Annex III") == 0
        # The clean Article 25 verdict survives.
        assert "Article 25(1)" in ans
        # Tangential refs (Annex III / Article 11) are reconciled away.
        assert "Annex III" not in " ".join(d["references"])
        assert "Article 11" not in d["references"]

    def test_q042_workplace_worker_notification(self, client):
        d = _ask(client, Q042)
        ans = d["answer"]
        assert "Article 26(7)" in ans
        assert "workers' representatives" in ans or "workers’ representatives" in ans
        # NOT the old Art 3/48/102 stub dump.
        assert "civil aviation" not in ans.lower()
        assert "Article 26.7" in d["references"]

    def test_q012_includes_8a_and_8b(self, client):
        d = _ask(client, Q012)
        ans = d["answer"]
        assert "8(a)" in ans
        assert "8(b)" in ans  # was dropped by the soft cap pre-fix
        assert "election" in ans.lower()

    def test_q039_lists_both_exceptions(self, client):
        d = _ask(client, Q039)
        ans = d["answer"].lower()
        assert "article 50(4)" in ans
        # exception 1: criminal-offence carve-out
        assert "criminal offence" in ans
        # exception 2: human review / editorial responsibility
        assert "editorial" in ans

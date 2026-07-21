"""Regression tests for the GENERAL classification-verdict fallback.

Motivating live bug (Marco, 2026-06-02): the question

    "Can a system be deployed that tracks patient weight or is it high
     risk according to Article 5 of the AI Act"

returned the full Article 5 prohibited-practices catalogue (RBI + social
scoring carve-outs) and shipped ``references=["Article 5"]`` — completely
ignoring the actual question (is a patient-weight tracker high-risk?).

Root cause: the engine recognised the question as a verdict ask
(``_is_classification_question == True``) but matched NO curated
``_CLASSIFICATION_TOPICS`` entry, no scenario shape and no role × risk
matrix, so it fell through to the QA-dump path and recited whichever
article the user named ("Article 5"). There was no GENERAL
classification-verdict path.

CLAUDE.md hard rule #3 forbids adding a topic-specific overfit entry, so
the fix is a *domain-general* verdict gated narrowly on a genuine
risk-tier intent (``_RISK_VERDICT_RE``) — excluding pure
scope/applicability asks ("does the Act apply to military use?") for which
the verdict would be wrong. Measured to fire on 0/137 davidath QA + 0/339
scenarios, so the bench stays byte-identical; the win lands on real-world
out-of-catalogue classification questions.

A second manifestation of the same symptom: the R19 explicit-anchor
pruner collapsed the verdict's authoritative refs down to the user's named
"Article 5". The fix protects the general-verdict refs from that pruner
(``general_classification_verdict_refs``).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines.graph_rag import (
    _RISK_VERDICT_RE,
    _detect_classification_topic,
    _general_classification_verdict,
    _is_classification_question,
    ask_compliance_question,
    general_classification_verdict_refs,
)
from app.main import app
from app.models import GraphRAGRequest
from app.rate_limit import limiter

PATIENT_WEIGHT_Q = (
    "Can a system be deployed that tracks patient weight or is it high "
    "risk according to Article 5 of the AI Act"
)
# A pure scope/applicability question — the lone davidath QA row that
# reaches the fall-through gate. The verdict must NOT fire here (gold is
# the Article 2 scope carve-out, not a risk-tier verdict).
MILITARY_SCOPE_Q = (
    "Does the AI Regulation apply to AI systems used for military or "
    "national security purposes?"
)


# ── Detector / gate unit tests (wrapper-independent) ────────────────────


class TestGeneralVerdictDetection:
    def test_patient_weight_is_classification_question(self) -> None:
        assert _is_classification_question(PATIENT_WEIGHT_Q) is True

    def test_patient_weight_matches_no_curated_topic(self) -> None:
        assert _detect_classification_topic(PATIENT_WEIGHT_Q) is None

    def test_general_verdict_fires_on_patient_weight(self) -> None:
        verdict = _general_classification_verdict(PATIENT_WEIGHT_Q)
        assert verdict is not None
        assert verdict["name"] == "general_classification"
        assert "Art. 6" in verdict["refs"]
        assert "Annex III" in verdict["refs"]

    def test_general_verdict_excludes_scope_question(self) -> None:
        # The narrow risk-verdict gate must NOT match a pure
        # scope/applicability ask — else the davidath military-scope row
        # would flip from its Article 2 answer to the wrong verdict.
        assert _general_classification_verdict(MILITARY_SCOPE_Q) is None

    def test_risk_verdict_re_distinguishes_tier_from_scope(self) -> None:
        assert _RISK_VERDICT_RE.search(PATIENT_WEIGHT_Q) is not None
        assert _RISK_VERDICT_RE.search(MILITARY_SCOPE_Q) is None


# ── Engine end-to-end (deterministic, wrapper-independent) ──────────────


class TestEngineAnswer:
    """Engine answer path with Stage-2 polish OFF.

    The fix targets the DETERMINISTIC verdict (the production floor — the
    live bug was served with ``stage2_polish: false``). Forcing Stage-2 off
    keeps the assertions stable whether or not a Claude Max wrapper is
    reachable in the test env (CI has none; a dev box may, and would
    otherwise reword the verdict prose).
    """

    @pytest.fixture(autouse=True)
    def _no_stage2(self, monkeypatch):
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")

    def test_patient_weight_answer_is_verdict_not_art5_dump(self) -> None:
        res = ask_compliance_question(GraphRAGRequest(question=PATIENT_WEIGHT_Q))
        answer = res.answer
        low = answer.lower()
        # The verdict must address the actual high-risk question via Art. 6.
        assert "not among the practices prohibited under article 5" in low
        assert "article 6" in low
        # Pre-fix smoking gun: the engine dumped the Art. 5 catalogue.
        assert not answer.startswith("Prohibits eight categories"), (
            "Regression — pre-fix Article 5 prohibited-practices dump fired"
        )

    def test_off_switch_reverts_to_prior_behaviour(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_GENERAL_VERDICT", "0")
        res = ask_compliance_question(GraphRAGRequest(question=PATIENT_WEIGHT_Q))
        # With the fallback disabled the engine reverts to the article dump.
        assert res.answer.startswith("Prohibits eight categories")


# ── Shared full-gate predicate (engine ⇄ route parity) ──────────────────


class TestVerdictRefsPredicate:
    def test_predicate_returns_refs_on_patient_weight(self) -> None:
        refs = general_classification_verdict_refs(PATIENT_WEIGHT_Q)
        assert "Art. 6" in refs
        assert "Annex III" in refs

    def test_predicate_empty_on_scope_question(self) -> None:
        assert general_classification_verdict_refs(MILITARY_SCOPE_Q) == ()

    def test_predicate_empty_on_curated_topic(self) -> None:
        # A curated topic fires in the engine first, so the predicate must
        # return () (no protection — the curated topic owns its refs).
        assert general_classification_verdict_refs(
            "Is emotion recognition in the workplace prohibited?"
        ) == ()

    def test_predicate_empty_when_disabled(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_GENERAL_VERDICT", "0")
        assert general_classification_verdict_refs(PATIENT_WEIGHT_Q) == ()


# ── Route end-to-end (force deterministic so CI ⇄ local agree) ──────────


@pytest.fixture
def det_client(monkeypatch):
    """TestClient with the partner key seeded and Stage-2 polish OFF.

    Forcing the deterministic path keeps the assertions stable whether or
    not a Claude Max wrapper happens to be reachable in the test env (CI
    has none; a dev box may). The deterministic verdict is the production
    floor anyway (the live bug was served with ``stage2_polish: false``).
    """
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")
    prev = settings.regenold.api_key
    settings.regenold.api_key = SecretStr("test")
    try:
        limiter.reset()
    except Exception:
        pass
    with TestClient(app, headers={"X-Regenold-Api-Key": "test"}) as c:
        yield c
    settings.regenold.api_key = prev


class TestRouteEndToEnd:
    def test_wire_answer_and_refs(self, det_client: TestClient) -> None:
        r = det_client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": PATIENT_WEIGHT_Q}],
        )
        assert r.status_code == 200
        body = r.json()
        answer = body.get("answer", "")
        refs = body.get("references", [])
        # Answer addresses the high-risk question, not an Art. 5 dump.
        assert "Article 6" in answer
        assert not answer.startswith("Prohibits eight categories")
        # The user named "Article 5"; the R19 pruner must NOT collapse the
        # verdict's high-risk-classification refs to just Article 5.
        assert "Article 5" in refs
        assert "Article 6" in refs
        assert "Annex III" in refs

    def test_scope_question_not_swept_into_verdict(
        self, det_client: TestClient
    ) -> None:
        r = det_client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": MILITARY_SCOPE_Q}],
        )
        assert r.status_code == 200
        answer = r.json().get("answer", "").lower()
        # Must answer the scope carve-out, not emit the risk-tier verdict.
        assert "not among the practices prohibited under article 5" not in answer


# ── The verdict is curated, complete prose — never augment it ───────────


class TestVerdictShipsCleanNotAugmented:
    """The general verdict must ship verbatim, never inline-rewritten.

    Live bug (2026-06-03): ``augment_with_ref_descriptions`` (the deterministic
    ref-describer, default ON) ran on the general verdict because the route's
    augment-gate only skips *curated* ``_CLASSIFICATION_TOPICS``
    (``not _is_classification_topic``) — the general verdict is the fallthrough
    floor, so it was unprotected. In ``replace_mode`` the augmenter rewrote the
    bare "Article 5"/"Article 6" tokens (grammatically EMBEDDED in the verdict's
    own prose, e.g. "prohibited under Article 5 (...)") into truncated KB-stub
    clips, producing run-on fusion + a mid-enumeration ``(a)``-only truncation +
    a ``.:`` artifact:

        "...prohibited under Article 5 prohibits eight categories of AI
         practice: (a) subliminal / manipulative / deceptive. ... turns on
         Article 6 classifies an AI system as high-risk when ...: it is
         high-risk only if ..."

    The verdict already describes every ref in its own words, so augmenting it
    is pure harm. These assertions pin the fusion/truncation signatures out.
    """

    @pytest.fixture(autouse=True)
    def _no_stage2(self, monkeypatch):
        # The augmenter only runs on the deterministic (non-Stage-2) path,
        # which is also the production floor — force it so the test is stable
        # whether or not a Claude Max wrapper is reachable.
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")

    def test_verdict_not_inline_fused(self, det_client: TestClient) -> None:
        r = det_client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": PATIENT_WEIGHT_Q}],
        )
        assert r.status_code == 200
        answer = r.json().get("answer", "")
        low = answer.lower()
        # Fusion signatures — the augmenter splicing a KB-stub clip onto the
        # grammatically-embedded "Article 5"/"Article 6" tokens.
        assert "prohibits eight categories" not in low, (
            f"Art. 5 KB-stub fused into the verdict prose: {answer!r}"
        )
        assert "classifies an ai system as high-risk when" not in low, (
            f"Art. 6 KB-stub fused into the verdict prose: {answer!r}"
        )
        # Truncation signature — the 8-category list clipped after "(a)".
        assert "(a) subliminal" not in low, (
            f"Article 5 enumeration truncated into the verdict: {answer!r}"
        )
        # Concatenation artifact left when a clip ending in "." meets the
        # template's ":".
        assert ".:" not in answer, f"'.:' artifact in verdict: {answer!r}"
        # The clean verdict prose must survive intact.
        assert "social scoring, untargeted facial-image scraping" in answer
        assert "limited- or minimal-risk" in answer


# ── R285 — the softened draft is an A/B ARM, never the silent default ──────


class TestR285GeneralVerdictV2Arm:
    """``REGENOLD_GENERAL_VERDICT_V2`` gates the R284-checkpoint-section-6
    "general-fallback softening".

    A prior commit shipped a softening with no A/B AND in a form that stopped
    being an answer — it opened "Evaluate the described system against ...",
    a second-person instruction telling the reader to do the classification
    they had just asked for. These tests pin (a) the default is the
    R284-validated text, (b) the arm is opt-in, and (c) the arm's text is
    still a declarative, tier-naming, cite-anchored ANSWER.
    """

    def test_default_arm_is_the_validated_legacy_text(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_GENERAL_VERDICT_V2", raising=False)
        from app.engines import graph_rag as g

        assert g._general_verdict_v2_enabled() is False
        assert (
            g._general_classification_verdict_text()
            == g._GENERAL_CLASSIFICATION_VERDICT_LEGACY
        )

    def test_arm_selects_the_softened_text(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_GENERAL_VERDICT_V2", "1")
        from app.engines import graph_rag as g

        assert (
            g._general_classification_verdict_text()
            == g._GENERAL_CLASSIFICATION_VERDICT_V2
        )

    def test_softened_text_is_still_an_answer_not_an_instruction(self) -> None:
        from app.engines import graph_rag as g

        text = g._GENERAL_CLASSIFICATION_VERDICT_V2
        low = text.lower()
        # Declarative, not an imperative aimed at the reader.
        assert not low.startswith("evaluate "), text
        assert not low.startswith("consider "), text
        assert not low.startswith("assess "), text
        # Still names the operative test AND the residual tier.
        assert "article 6" in low
        assert "annex i" in low and "annex iii" in low
        assert "limited- or minimal-risk" in low, (
            "the residual tier must be named — dropping it was one of the "
            "regressions in the reverted commit"
        )
        # Article 50 stays CONDITIONAL on direct interaction with people; it
        # does not apply to every non-high-risk system.
        assert "where it interacts directly with people" in low
        # Third-person regulator voice: never addresses the reader.
        assert " you " not in f" {low} " and "your " not in low

    def test_softened_text_drops_the_confident_not_prohibited_assertion(self) -> None:
        """The whole point of the softening: a described-not-named prohibited
        practice must not have a confident-wrong draft for Stage-2 to polish."""
        from app.engines import graph_rag as g

        assert (
            "not among the practices prohibited"
            in g._GENERAL_CLASSIFICATION_VERDICT_LEGACY.lower()
        )
        assert (
            "not among the practices prohibited"
            not in g._GENERAL_CLASSIFICATION_VERDICT_V2.lower()
        )

    def test_every_sentence_of_both_arms_is_cite_anchored(self) -> None:
        """Un-anchored sentences are dropped by the soft-cap pass."""
        import re

        from app.engines import graph_rag as g

        for text in (
            g._GENERAL_CLASSIFICATION_VERDICT_LEGACY,
            g._GENERAL_CLASSIFICATION_VERDICT_V2,
        ):
            for sentence in [s for s in re.split(r"(?<=\.)\s+", text) if s.strip()]:
                assert re.search(r"Article \d+|Annex [IVX]+", sentence), (
                    f"sentence without a cite anchor: {sentence!r}"
                )

    def test_neither_arm_uses_dash_separators_or_ellipses(self) -> None:
        from app.engines import graph_rag as g

        for text in (
            g._GENERAL_CLASSIFICATION_VERDICT_LEGACY,
            g._GENERAL_CLASSIFICATION_VERDICT_V2,
        ):
            assert "—" not in text and "–" not in text and "..." not in text

    def test_arm_flag_is_in_the_engine_cache_key(self) -> None:
        """R263.2 doctrine: a flag that changes the CACHED engine answer must be
        in the cache identity, or a same-process A/B serves the baseline arm's
        response to the branch arm and the measurement is silently void."""
        import inspect

        from app.routes import regenold

        src = inspect.getsource(regenold._engine_cache_key)
        assert "REGENOLD_GENERAL_VERDICT_V2" in src

    def test_arms_produce_distinct_engine_answers(self, monkeypatch) -> None:
        from app.engines.graph_rag import _general_classification_verdict

        q = "We built an AI tool that tracks patient weight in a ward. Is it high-risk?"
        monkeypatch.setenv("REGENOLD_GENERAL_VERDICT_V2", "0")
        a = _general_classification_verdict(q)
        monkeypatch.setenv("REGENOLD_GENERAL_VERDICT_V2", "1")
        b = _general_classification_verdict(q)
        assert a is not None and b is not None
        assert a["answer"] != b["answer"]
        assert a["refs"] == b["refs"], "the arm changes prose only, never refs"

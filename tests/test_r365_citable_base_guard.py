"""R365 — the retrieval-grounding guard on the prose-promotion passes.

``_add_prose_named_refs`` has always taken a ``citable_bases`` keyword and
NEITHER call site ever passed it, so the parameter was dead code: the fallback
``allowed_source`` is ``references | prose bases``, which contains every
prose-named base by construction, so the "allowed" test was vacuously true.
``REGENOLD_CITABLE_BASE_GUARD`` (default OFF) supplies the route's real
retrieval-derived citation universe instead, so a provision the Stage-2 polish
merely NAMES cannot become a wire citation unless retrieval actually surfaced
it.

WHY THESE TESTS ASSERT ON COUNTERS AND ON THE WIRE, NEVER ON CODE SHAPE
----------------------------------------------------------------------
This repo's signature failure is a lever that reads correctly in the diff and
makes zero calls (R329: three Cohere-rerank placements, all +0.0000). R365 hit
a sharper version of it. Wiring the guard at both ``_add_prose_named_refs``
call sites and nowhere else MEASURED, through the real route:

    counters   attempts=2  blocked=1        <- the lever fired
    wire refs  ['Article 27','Article 14','Article 111']  BOTH arms
               "Component D Grounding Guard: Prose cited Article 111 ...
                Dynamically augmenting references list."

i.e. the guard blocked the promotion and the Component-D post-polish pass
(the THIRD prose-to-citation site, which sits BETWEEN the two call sites) put
it straight back — the same defect R324 recorded for the foreign-instrument
guard. Firing counters alone would have certified an inert feature, so
``TestRouteWireEffect`` pins the WIRE, two-sided.

THE PRE-R365 BASELINE IS MEASURED, NOT ASSUMED
----------------------------------------------
``_PRE_R365_REFS`` below was produced by running this exact request against
the unmodified HEAD module (``app/routes/regenold.py`` with no R365 code in
it at all, ``has guard: False``) on 2026-08-24. The default/OFF arm must
reproduce it byte-for-byte.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.routes.regenold import (
    _CITE_CONSISTENCY_CAP,
    _add_prose_named_refs,
    _citable_base_guard_enabled,
    _engine_cache_key,
    citable_base_guard_stats,
    reset_citable_base_guard_stats,
)

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_CITABLE_BASE_GUARD", raising=False)
    reset_citable_base_guard_stats()


# ── The gate ─────────────────────────────────────────────────────────────


class TestGateDefaultOff:
    def test_disabled_by_default(self) -> None:
        # New levers ship OFF. The sibling evaluation fork ships this same
        # predicate default ON; that default is deliberately NOT ported —
        # flipping it is a separate, easyhard_ab-gated decision.
        assert _citable_base_guard_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " on "])
    def test_truthy_values_enable(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", val)
        assert _citable_base_guard_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_falsy_values_disable(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", val)
        assert _citable_base_guard_enabled() is False

    def test_env_is_read_fresh_per_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # R263.2 — easyhard_ab / ab_judge mutate os.environ BETWEEN arms in
        # the SAME process. A value snapshot at import time makes both arms
        # read the baseline and the A/B measures nothing.
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "1")
        assert _citable_base_guard_enabled() is True
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "0")
        assert _citable_base_guard_enabled() is False


# ── The predicate itself ─────────────────────────────────────────────────

#: A realistic deployer-duties shape: retrieval surfaced 26/14/27, the polish
#: also names Article 111 (transitional provisions for large-scale IT
#: systems) — real, catalog-resolving, and legally inapposite here. This is
#: the failure class CLAUDE.md describes: "semantically plausible and legally
#: inapposite".
_REFS = ["Article 26", "Article 14", "Article 27"]
_PROSE = (
    "Deployers of a high-risk recruitment system must use it in accordance "
    "with the instructions for use under Article 26, assign competent human "
    "oversight under Article 14, and complete a fundamental-rights impact "
    "assessment under Article 27. Article 111 also applies to the system."
)
#: What retrieval actually produced — Article 111 is NOT in it.
_UNIVERSE = frozenset(_REFS)


class TestUnguardedIsUnchanged:
    """The OFF state, at the function's own seam."""

    def test_no_citable_bases_promotes_the_ungrounded_base(self) -> None:
        # This is the pre-R365 behaviour and it must be preserved exactly:
        # every prose-named, catalog-resolving base is promoted regardless of
        # whether retrieval ever saw it.
        out = _add_prose_named_refs(
            list(_REFS), _PROSE, cap=_CITE_CONSISTENCY_CAP
        )
        assert out == [*_REFS, "Article 111"]

    def test_unguarded_call_bumps_no_counters(self) -> None:
        _add_prose_named_refs(list(_REFS), _PROSE, cap=_CITE_CONSISTENCY_CAP)
        assert citable_base_guard_stats() == {
            "attempts": 0,
            "blocked": 0,
            "noop": 0,
            "component_d_attempts": 0,
            "component_d_blocked": 0,
        }

    def test_existing_guards_still_hold_unguarded(self) -> None:
        # A negated mention and a foreign-instrument mention are still
        # rejected with no citable_bases supplied (R311 / R321 / R325).
        prose = (
            "The classification does not depend on Annex III. Article 35 of "
            "the GDPR governs the separate DPIA duty."
        )
        assert _add_prose_named_refs(["Article 6"], prose) == ["Article 6"]


class TestGuardBlocksUngrounded:
    """The ON state: an ungrounded promotion is refused AND counted."""

    def test_ungrounded_base_is_not_promoted(self) -> None:
        out = _add_prose_named_refs(
            list(_REFS),
            _PROSE,
            citable_bases=_UNIVERSE,
            cap=_CITE_CONSISTENCY_CAP,
        )
        assert out == _REFS
        assert "Article 111" not in out

    def test_counter_increments(self) -> None:
        _add_prose_named_refs(
            list(_REFS),
            _PROSE,
            citable_bases=_UNIVERSE,
            cap=_CITE_CONSISTENCY_CAP,
        )
        stats = citable_base_guard_stats()
        assert stats["attempts"] == 1
        assert stats["blocked"] == 1
        assert stats["noop"] == 0

    def test_guard_never_invents_a_reference(self) -> None:
        # The universe may name provisions the prose never mentions; those
        # must NOT be added. The pass only ever promotes prose-named bases.
        out = _add_prose_named_refs(
            list(_REFS),
            _PROSE,
            citable_bases=frozenset({*_REFS, "Article 99", "Annex IV"}),
            cap=_CITE_CONSISTENCY_CAP,
        )
        assert out == _REFS
        assert "Article 99" not in out and "Annex IV" not in out


class TestGuardDoesNotOverBlock:
    """The ON state must still promote a base retrieval DID surface."""

    def test_grounded_prose_base_is_still_promoted(self) -> None:
        # Article 27 is in the retrieval universe but NOT yet on the wire —
        # exactly the R134/R138 defect the pass exists to fix. The guard must
        # not touch it.
        refs = ["Article 26", "Article 14"]
        out = _add_prose_named_refs(
            list(refs),
            _PROSE,
            citable_bases=frozenset({*refs, "Article 27"}),
            cap=_CITE_CONSISTENCY_CAP,
        )
        assert out == [*refs, "Article 27"]

    def test_noop_counted_when_nothing_is_blocked(self) -> None:
        refs = ["Article 26", "Article 14"]
        _add_prose_named_refs(
            list(refs),
            "Deployers must comply with Article 26 and Article 14.",
            citable_bases=frozenset(refs),
            cap=_CITE_CONSISTENCY_CAP,
        )
        stats = citable_base_guard_stats()
        assert stats["attempts"] == 1
        assert stats["blocked"] == 0
        assert stats["noop"] == 1

    def test_annex_grain_is_promoted_when_grounded(self) -> None:
        prose = "Annex III point 4 lists employment use cases; see Annex III."
        out = _add_prose_named_refs(
            ["Article 6"], prose, citable_bases=frozenset({"Article 6", "Annex III"})
        )
        assert out == ["Article 6", "Annex III"]


# ── The wire: does the lever actually change the emitted references? ──────

_Q = "What must a deployer of a high-risk recruitment AI system do?"
_STAGE2_ANSWER = (
    "Deployers of a high-risk recruitment system must use it in accordance "
    "with the instructions for use, assign competent human oversight under "
    "Article 14, and complete a fundamental-rights impact assessment under "
    "Article 27. Article 111 also applies to the system."
)
#: MEASURED 2026-08-24 against the unmodified HEAD module (no R365 code
#: present). The default / OFF arm must reproduce this byte-for-byte.
_PRE_R365_REFS = ["Article 27", "Article 14", "Article 111"]


def _stage2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # setattr, not a bare assignment — monkeypatch restores it, so this file
    # cannot leave a test key on the shared ``settings`` singleton for the
    # rest of the session.
    monkeypatch.setattr(settings.regenold, "api_key", SecretStr("regenold-test-key"))
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")  # keep the polish on the wire
    monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.setenv("REGENOLD_CITE_CONSISTENCY", "1")
    # The dev .env may pin provider=cli, which skips Stage-2 entirely and
    # would make every assertion below vacuous.
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)


def _post() -> dict:
    """One route call with Stage-2 stubbed — no network, no LLM."""
    with (
        patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=True,
        ),
        patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            side_effect=lambda *a, **kw: _STAGE2_ANSWER,
        ),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": _Q}],
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestRouteWireEffect:
    def test_default_wire_is_byte_identical_to_pre_r365(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stage2_env(monkeypatch)  # flag left unset by the autouse fixture
        body = _post()
        assert "Article 14" in (body.get("answer") or ""), (
            "Stage-2 did not land — the arm is vacuous"
        )
        assert body["references"] == _PRE_R365_REFS
        # And the guard was never consulted, so it cannot have had an effect.
        assert citable_base_guard_stats()["attempts"] == 0
        assert citable_base_guard_stats()["component_d_attempts"] == 0

    def test_off_explicitly_is_byte_identical_to_pre_r365(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stage2_env(monkeypatch)
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "0")
        assert _post()["references"] == _PRE_R365_REFS

    def test_on_removes_the_ungrounded_reference_from_the_wire(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stage2_env(monkeypatch)
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "1")
        body = _post()
        refs = body["references"]
        assert "Article 14" in (body.get("answer") or ""), (
            "Stage-2 did not land — the arm is vacuous"
        )
        # THE WIRE MOVED. This is the assertion the counters alone could not
        # make: with only the two _add_prose_named_refs sites guarded, the
        # counters read blocked=1 and this list was unchanged.
        assert refs != _PRE_R365_REFS
        assert "Article 111" not in refs
        # ... and the grounded references survive (no over-blocking).
        assert refs == ["Article 27", "Article 14"]

    def test_on_fires_the_counters_at_both_layers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stage2_env(monkeypatch)
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "1")
        _post()
        stats = citable_base_guard_stats()
        # attempts == 0 would mean the lever never ran; any downstream A/B
        # number off this path would then be UNMEASURED, not "no effect".
        assert stats["attempts"] > 0, stats
        assert stats["blocked"] > 0, stats
        assert stats["component_d_attempts"] > 0, stats
        assert stats["component_d_blocked"] > 0, stats

    def test_answer_prose_is_retained_not_discarded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The remedy is scoped to the REFERENCE. It must never route into the
        # Component-D hallucination branch, which throws away the entire
        # polished answer and falls back to the deterministic stub.
        _stage2_env(monkeypatch)
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "1")
        answer = _post().get("answer") or ""
        assert "fundamental-rights impact assessment" in answer


# ── Cache-key identity (AGENTS.md invariant #4) ───────────────────────────


class TestCacheKey:
    def test_flag_reaches_engine_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "0")
        off = _engine_cache_key(_Q, None)
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "1")
        on = _engine_cache_key(_Q, None)
        assert off != on, (
            "REGENOLD_CITABLE_BASE_GUARD is not in the engine cache key — an "
            "in-process two-arm A/B would serve arm A's cached response to "
            "arm B (R263.2) and read +0.0000 on every axis."
        )

    def test_key_is_stable_for_a_fixed_flag_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_CITABLE_BASE_GUARD", "1")
        assert _engine_cache_key(_Q, None) == _engine_cache_key(_Q, None)


# ── Counter plumbing ──────────────────────────────────────────────────────


def test_reset_zeroes_every_field() -> None:
    _add_prose_named_refs(list(_REFS), _PROSE, citable_bases=_UNIVERSE)
    assert any(v for v in citable_base_guard_stats().values())
    reset_citable_base_guard_stats()
    assert set(citable_base_guard_stats().values()) == {0}


def test_stats_snapshot_is_a_copy() -> None:
    snap = citable_base_guard_stats()
    snap["attempts"] = 999
    assert citable_base_guard_stats()["attempts"] == 0


def test_guard_is_fail_soft() -> None:
    # A malformed universe must never break the route; the pass returns its
    # input unchanged rather than raising.
    assert _add_prose_named_refs(list(_REFS), _PROSE, citable_bases=object()) == _REFS  # type: ignore[arg-type]

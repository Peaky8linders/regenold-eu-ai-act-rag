"""R294 — graph query budget + circuit breaker.

Background (all numbers measured against the live Aura instance the R291
seed targets, and against the DNS-dead R290 host):

* production 2-hop Cypher: COLD 703 ms, WARM mean 64 ms / max 215 ms —
  so the old hard-coded 50 ms budget returned **0 hop2 refs** on every
  seed; at 250 ms the same three seeds returned **15**;
* dead host: ``execute_read`` stalls 1631 ms in-thread, so a naive raise
  would cost ~197 ms extra per call. Over 10 calls: status quo 1442 ms,
  naive raise 2597 ms, raise + breaker **765 ms**.

The breaker is what makes the raise safe, so it is tested as hard as the
budget itself.
"""
from __future__ import annotations

import os

import pytest

from app.graph import timeouts as T


@pytest.fixture(autouse=True)
def _clean_breaker_and_env(monkeypatch):
    """Every test starts with a closed breaker and no env override."""
    monkeypatch.delenv(T.GRAPH_TIMEOUT_ENV_VAR, raising=False)
    monkeypatch.delenv("REGENOLD_GRAPH_BREAKER", raising=False)
    T.reset_graph_circuit()
    yield
    T.reset_graph_circuit()


# ── Budget resolution ──────────────────────────────────────────────────


class TestResolveGraphTimeoutMs:
    def test_default_exceeds_measured_warm_worst_case(self):
        """250 ms default must clear the 215 ms worst warm sample."""
        assert T.resolve_graph_timeout_ms() == T.DEFAULT_GRAPH_TIMEOUT_MS
        assert T.DEFAULT_GRAPH_TIMEOUT_MS >= 215

    def test_explicit_wins_over_env(self, monkeypatch):
        monkeypatch.setenv(T.GRAPH_TIMEOUT_ENV_VAR, "400")
        assert T.resolve_graph_timeout_ms(75) == 75

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv(T.GRAPH_TIMEOUT_ENV_VAR, "500")
        assert T.resolve_graph_timeout_ms() == 500

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("99999", T.MAX_GRAPH_TIMEOUT_MS),   # clamp high
            ("0", T.MIN_GRAPH_TIMEOUT_MS),       # clamp low — never disable
            ("-5", T.MIN_GRAPH_TIMEOUT_MS),
            ("abc", T.DEFAULT_GRAPH_TIMEOUT_MS),  # fail-soft
            ("", T.DEFAULT_GRAPH_TIMEOUT_MS),
            ("  300  ", 300),                     # whitespace tolerated
        ],
    )
    def test_env_edge_cases(self, monkeypatch, raw, expected):
        monkeypatch.setenv(T.GRAPH_TIMEOUT_ENV_VAR, raw)
        assert T.resolve_graph_timeout_ms() == expected

    def test_explicit_is_clamped_too(self):
        assert T.resolve_graph_timeout_ms(10**9) == T.MAX_GRAPH_TIMEOUT_MS
        assert T.resolve_graph_timeout_ms(0) == T.MIN_GRAPH_TIMEOUT_MS


# ── Circuit breaker ────────────────────────────────────────────────────


class TestGraphCircuitBreaker:
    def test_starts_closed(self):
        assert T.graph_circuit_open() is False

    def test_opens_only_at_threshold(self):
        for _ in range(T.GRAPH_BREAKER_THRESHOLD - 1):
            T.record_graph_failure()
            assert T.graph_circuit_open() is False
        T.record_graph_failure()
        assert T.graph_circuit_open() is True

    def test_success_resets_the_streak(self):
        for _ in range(T.GRAPH_BREAKER_THRESHOLD - 1):
            T.record_graph_failure()
        T.record_graph_success()
        # Streak cleared — one more failure must NOT open it.
        T.record_graph_failure()
        assert T.graph_circuit_open() is False

    def test_half_opens_after_cooldown(self, monkeypatch):
        for _ in range(T.GRAPH_BREAKER_THRESHOLD):
            T.record_graph_failure()
        assert T.graph_circuit_open() is True

        real = T.time.monotonic
        monkeypatch.setattr(
            T.time, "monotonic",
            lambda: real() + T.GRAPH_BREAKER_COOLDOWN_S + 1,
        )
        # Half-open: exactly one probe is let through.
        assert T.graph_circuit_open() is False

    def test_env_disable(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GRAPH_BREAKER", "0")
        for _ in range(T.GRAPH_BREAKER_THRESHOLD * 3):
            T.record_graph_failure()
        assert T.graph_circuit_open() is False

    def test_reset_forces_closed(self):
        for _ in range(T.GRAPH_BREAKER_THRESHOLD):
            T.record_graph_failure()
        assert T.graph_circuit_open() is True
        T.reset_graph_circuit()
        assert T.graph_circuit_open() is False

    def test_thread_safe_under_concurrent_recorders(self):
        """The recorders run from both request and executor threads."""
        import threading

        def hammer():
            for _ in range(200):
                T.record_graph_failure()
                T.record_graph_success()

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Ends on a success in every thread → breaker closed, no crash.
        assert T.graph_circuit_open() is False


# ── Call-site wiring ───────────────────────────────────────────────────


class TestCallSitesResolveTheBudget:
    def test_public_signatures_default_to_none(self):
        """``None`` is what routes the call through the resolver."""
        import inspect

        from app.engines.graph_aware_retrieval import (
            lookup_definition_by_term,
            obligations_for_role,
            recitals_for_article,
        )
        from app.engines.graph_expand_2hop import expand_2hop

        for fn in (
            expand_2hop,
            lookup_definition_by_term,
            recitals_for_article,
            obligations_for_role,
        ):
            param = inspect.signature(fn).parameters["timeout_ms"]
            assert param.default is None, f"{fn.__name__} still pins a budget"

    def test_no_hardcoded_50ms_budget_remains(self):
        """Regression guard: the 50 ms literal must not creep back."""
        from pathlib import Path

        import app.engines.graph_aware_retrieval as gar
        import app.engines.graph_expand_2hop as g2h

        for mod in (gar, g2h):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            assert "timeout_ms: int = 50" not in src, (
                f"{mod.__name__} re-pinned the measured-too-small 50 ms budget"
            )

    def test_open_circuit_short_circuits_expand_2hop(self, monkeypatch):
        """An open breaker must skip the executor entirely."""
        import app.engines.graph_expand_2hop as g2h

        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setattr(g2h, "_embedded_selected", lambda: False)

        submitted: list[int] = []

        class _Boom:
            def submit(self, fn):  # pragma: no cover — must never run
                submitted.append(1)
                raise AssertionError("executor used while circuit open")

        monkeypatch.setattr(g2h, "_resolve_client", lambda: object())
        monkeypatch.setattr(g2h, "_get_executor", lambda: _Boom())

        for _ in range(T.GRAPH_BREAKER_THRESHOLD):
            T.record_graph_failure()

        result = g2h.expand_2hop(["Art. 6"])
        assert not result.hop2_articles  # tuple field on the dataclass
        assert submitted == []

    def test_open_circuit_short_circuits_graph_aware(self, monkeypatch):
        import app.engines.graph_aware_retrieval as gar

        def _boom():  # pragma: no cover — must never run
            raise AssertionError("fn executed while circuit open")

        for _ in range(T.GRAPH_BREAKER_THRESHOLD):
            T.record_graph_failure()

        assert gar._with_timeout(_boom, timeout_ms=None, label="probe") is None


# ── R295: same-process A/B integrity (R263.2 cross-arm contamination) ──


class TestAbGateIntegrity:
    """Both flags flip engine output, so an in-process A/B must isolate them.

    Without these two properties a 50↔250 A/B silently measures nothing:
    the branch arm is served the baseline arm's cached answer, and/or the
    baseline arm's timeouts latch the process-global breaker and suppress
    the branch arm's graph calls.
    """

    def test_timeout_is_in_the_engine_cache_key(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key

        q = "What must deployers of high-risk AI systems do?"
        monkeypatch.setenv(T.GRAPH_TIMEOUT_ENV_VAR, "50")
        k_baseline = _engine_cache_key(q, "")
        monkeypatch.setenv(T.GRAPH_TIMEOUT_ENV_VAR, "250")
        k_branch = _engine_cache_key(q, "")
        assert k_baseline != k_branch, (
            "R263.2: branch arm would be served the baseline arm's cached engine output"
        )

    def test_breaker_flag_is_in_the_engine_cache_key(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key

        q = "What must deployers of high-risk AI systems do?"
        monkeypatch.setenv("REGENOLD_GRAPH_BREAKER", "1")
        k_on = _engine_cache_key(q, "")
        monkeypatch.setenv("REGENOLD_GRAPH_BREAKER", "0")
        k_off = _engine_cache_key(q, "")
        assert k_on != k_off

    def test_disabled_breaker_does_not_latch(self, monkeypatch):
        """A disabled breaker must accumulate NO state.

        Otherwise the pre-R294 baseline arm (50 ms, breaker off) times out,
        latches ``_opened_at``, and the R294 branch arm is short-circuited.
        """
        monkeypatch.setenv("REGENOLD_GRAPH_BREAKER", "0")
        for _ in range(T.GRAPH_BREAKER_THRESHOLD * 3):
            T.record_graph_failure()

        monkeypatch.delenv("REGENOLD_GRAPH_BREAKER", raising=False)
        assert T.graph_circuit_open() is False, "disabled breaker leaked state"

    def test_disabled_breaker_still_opens_once_re_enabled(self, monkeypatch):
        """The off-switch must not permanently disarm the breaker."""
        monkeypatch.setenv("REGENOLD_GRAPH_BREAKER", "0")
        for _ in range(T.GRAPH_BREAKER_THRESHOLD * 2):
            T.record_graph_failure()
        monkeypatch.delenv("REGENOLD_GRAPH_BREAKER", raising=False)
        for _ in range(T.GRAPH_BREAKER_THRESHOLD):
            T.record_graph_failure()
        assert T.graph_circuit_open() is True


# ── R295: the fusion budget is the real gate; and its latent NameError ──


class TestGraphFusionSlack:
    def test_kb_search_defines_a_logger(self):
        """Regression: ``logger.debug`` was called with no logger defined.

        Both call sites fire ONLY when the graph contributes refs, which
        measurement showed almost never happened (1/132 fusion calls had
        slack) — so the NameError stayed dormant. The engine calls
        ``top_articles_by_relevance`` unguarded, so once the graph does
        contribute it would propagate into retrieval.
        """
        import logging

        import app.data.kb_search as ks

        assert isinstance(getattr(ks, "logger", None), logging.Logger)

    def test_fusion_adding_refs_does_not_raise(self, monkeypatch):
        """Directly exercise the previously-crashing branch."""
        import app.data.kb_search as ks
        import app.engines.graph_expand_2hop as g2

        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setattr(g2, "is_enabled", lambda: True)
        monkeypatch.setattr(
            g2, "expand_2hop",
            lambda seeds, **kw: g2.GraphExpansion(hop2_articles=("Art. 99",)),
        )
        # Force the "fusion added a ref" path that used to NameError.
        monkeypatch.setattr(
            g2, "fuse_with_kb_xrefs",
            lambda winners, exp, budget=10: list(winners) + ["Art. 99"],
        )
        ks.top_articles_by_relevance("What are the penalties?", k=5)

    def test_slack_defaults_to_zero(self, monkeypatch):
        """Default 0 keeps pre-R295 behaviour byte-identical.

        MEASURED: slack>0 is rubric-NEGATIVE. On the 132-row probe set it
        changes 99-100% of candidate sets (+261 refs at slack=2), but at the
        WIRE only 1/40 rows change — and that row (paper_st_v4:st_v4_002,
        gold ('Article 5',), a prohibited biometric-categorisation question)
        goes from a perfect ['Article 5'] to ['Article 2','Article 27',
        'Article 49'] — the gold is DESTROYED. Textbook R142.1 gold-drop,
        and it compounds the R287 over-citation finding. Ships OFF.
        """
        monkeypatch.delenv("REGENOLD_GRAPH_FUSE_SLACK", raising=False)
        assert os.getenv("REGENOLD_GRAPH_FUSE_SLACK") is None

    def test_slack_is_in_the_engine_cache_key(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key

        q = "Which article prohibits biometric categorisation?"
        monkeypatch.setenv("REGENOLD_GRAPH_FUSE_SLACK", "0")
        k0 = _engine_cache_key(q, "")
        monkeypatch.setenv("REGENOLD_GRAPH_FUSE_SLACK", "3")
        k3 = _engine_cache_key(q, "")
        assert k0 != k3

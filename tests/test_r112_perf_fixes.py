"""R112 performance-fix regression tests (findings #11, #12, #33, #49).

* Finding #11 (HIGH) — ``app/engines/external_embeddings.py``: skip the
  embeddings probe when ``OPENAI_API_BASE`` targets the Claude-Max CHAT
  wrapper (no ``/embeddings`` endpoint there), cache the negative probe,
  use a pooled client with a short split timeout.
* Finding #12 (HIGH) — ``app/main.py``: startup index warm-up hook
  (daemon thread, never blocks boot, env-gated ``REGENOLD_INDEX_WARMUP``
  default ON, honours ``REGENOLD_SKIP_STARTUP_LOG=1``).
* Finding #33 (MEDIUM) — ``app/llm/openai_wrapper_provider.py``: the
  pooled client's bare-float 60 s timeout meant connect=60 s; now the
  connect class is capped at 5 s while read/write/pool keep the caller's
  budget, and the per-request override contract is preserved.
* Finding #49 (LOW) — ``app/data/kb_search.py``: the entity-extraction
  regex sweep ran TWICE per ``top_articles_by_relevance`` call
  (``boosted_articles`` internally + ``extract_entities`` again); now it
  runs once, with byte-identical ranking output (pinned below against
  values captured from the PRE-refactor code).
"""
from __future__ import annotations

import threading

import httpx
import pytest

import app.engines.external_embeddings as ee


# ─────────────────────────────────────────────────────────────────────────
# Finding #11 — external_embeddings chat-wrapper skip + negative cache
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    """Isolate the negative-probe cache per test (and from the suite)."""
    ee._reset_probe_cache_for_tests()
    yield
    ee._reset_probe_cache_for_tests()


class TestChatWrapperDetection:
    @pytest.mark.parametrize(
        "base",
        [
            "http://127.0.0.1:8000/v1",       # local wrapper default
            "http://127.0.0.1:1/v1",           # conftest dead-port guard
            "http://localhost:8000/v1",
            "https://wrapper.antifragile-ai.net/v1",  # Cloudflare tunnel
            "127.0.0.1:8000/v1",               # scheme-less loopback
        ],
    )
    def test_wrapper_bases_detected(self, base: str) -> None:
        assert ee._targets_chat_wrapper(base) is True

    @pytest.mark.parametrize(
        "base",
        [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/embeddings",
            "https://my-embeddings-proxy.example.com/v1",
            "",
        ],
    )
    def test_real_bases_not_detected(self, base: str) -> None:
        assert ee._targets_chat_wrapper(base) is False

    def test_unavailable_when_base_is_wrapper(self, monkeypatch) -> None:
        """The production misfire: chat-wrapper OPENAI_* vars must NOT
        activate the embeddings path."""
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("REGENOLD_EXTERNAL_EMBEDDINGS", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        assert ee.is_available() is False
        assert ee._get_provider() is None

    def test_get_embedding_no_http_call_on_wrapper_base(self, monkeypatch) -> None:
        """No doomed POST through the tunnel — get_embedding returns None
        without touching HTTP when the base is the chat wrapper."""
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("REGENOLD_EXTERNAL_EMBEDDINGS", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")
        monkeypatch.setenv(
            "OPENAI_API_BASE", "https://wrapper.antifragile-ai.net/v1"
        )

        def _boom(*args, **kwargs):  # pragma: no cover — must not run
            raise AssertionError("HTTP POST fired against the chat wrapper")

        monkeypatch.setattr("httpx.Client.post", _boom)
        assert ee.get_embedding("biometric systems") is None

    def test_explicit_opt_in_overrides_wrapper_detection(self, monkeypatch) -> None:
        """An operator with a REAL local embeddings server opts in."""
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
        assert ee._get_provider() == "openai"
        assert ee.is_available() is True

    def test_explicit_opt_out_disables_everything(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
        monkeypatch.setenv("COHERE_API_KEY", "co-key")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-key")
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        assert ee._get_provider() is None
        assert ee.is_available() is False

    def test_real_openai_config_still_available(self, monkeypatch) -> None:
        """Key set, base unset → canonical api.openai.com → available
        (pre-R112 behaviour preserved for genuine OpenAI configs)."""
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
        assert ee._get_provider() == "openai"
        assert ee.is_available() is True


class TestNegativeProbeCache:
    def test_openai_failure_cached_no_second_post(self, monkeypatch) -> None:
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        calls = {"n": 0}

        def _failing_post(self, url, **kwargs):
            calls["n"] += 1
            raise httpx.ConnectError("refused")

        monkeypatch.setattr("httpx.Client.post", _failing_post)

        assert ee.get_embedding("clinical notes") is None
        assert calls["n"] == 1
        # Second call must short-circuit on the negative cache.
        assert ee.get_embedding("clinical notes") is None
        assert calls["n"] == 1
        # is_available reflects the cached negative → turboquant's build
        # gate skips the probe entirely.
        assert ee.is_available() is False
        # Reset hook restores availability.
        ee._reset_probe_cache_for_tests()
        assert ee.is_available() is True

    def test_cohere_failure_not_cached(self, monkeypatch) -> None:
        """Cohere is a dedicated embeddings API — failures are treated as
        transient, never cached (keeps the turboquant cohere tests and a
        flaky-network deploy functional)."""
        monkeypatch.setenv("COHERE_API_KEY", "co-test")
        monkeypatch.delenv("REGENOLD_EXTERNAL_EMBEDDINGS", raising=False)

        calls = {"n": 0}

        def _failing_post(self, url, **kwargs):
            calls["n"] += 1
            raise RuntimeError("transient")

        monkeypatch.setattr("httpx.Client.post", _failing_post)

        assert ee.get_embedding("x") is None
        assert ee.get_embedding("x") is None
        assert calls["n"] == 2  # retried — not negative-cached
        assert ee.is_available() is True


class TestPooledEmbeddingsClient:
    def test_client_is_pooled_singleton(self) -> None:
        c1 = ee._get_client()
        c2 = ee._get_client()
        assert c1 is c2

    def test_client_timeout_split_and_short(self) -> None:
        t = ee._get_client().timeout
        assert t.connect == 3.0
        assert t.read == 10.0  # was a blanket 30 s fresh client per call


# ─────────────────────────────────────────────────────────────────────────
# Finding #12 — startup index warm-up hook
# ─────────────────────────────────────────────────────────────────────────


class TestIndexWarmupHook:
    @pytest.fixture(autouse=True)
    def _reset_started_flag(self):
        import app.main as m

        m._INDEX_WARMUP_STARTED = False
        yield
        m._INDEX_WARMUP_STARTED = False

    @staticmethod
    def _fake_thread(monkeypatch):
        import app.main as m

        spawned: list[dict] = []

        class _FakeThread:
            def __init__(self, *, target=None, name=None, daemon=None, args=()):
                spawned.append(
                    {"target": target, "name": name, "daemon": daemon}
                )

            def start(self) -> None:
                pass

        monkeypatch.setattr(m._threading, "Thread", _FakeThread)
        return spawned

    def test_env_gate_default_on(self, monkeypatch) -> None:
        import app.main as m

        monkeypatch.delenv("REGENOLD_INDEX_WARMUP", raising=False)
        assert m._index_warmup_disabled_by_env() is False
        # Empty string is NOT a disable signal (auto-seed semantics).
        monkeypatch.setenv("REGENOLD_INDEX_WARMUP", "")
        assert m._index_warmup_disabled_by_env() is False
        for off in ("0", "false", "No", "OFF"):
            monkeypatch.setenv("REGENOLD_INDEX_WARMUP", off)
            assert m._index_warmup_disabled_by_env() is True
        monkeypatch.setenv("REGENOLD_INDEX_WARMUP", "1")
        assert m._index_warmup_disabled_by_env() is False

    def test_hook_spawns_daemon_thread(self, monkeypatch) -> None:
        import app.main as m

        monkeypatch.delenv("REGENOLD_SKIP_STARTUP_LOG", raising=False)
        monkeypatch.delenv("REGENOLD_INDEX_WARMUP", raising=False)
        spawned = self._fake_thread(monkeypatch)
        m._maybe_warm_indexes()
        assert len(spawned) == 1
        assert spawned[0]["daemon"] is True
        assert spawned[0]["name"] == "regenold-index-warmup"
        assert spawned[0]["target"] is m._run_index_warmup_in_thread
        # Second invocation (dev-reload double hook) must not respawn.
        m._maybe_warm_indexes()
        assert len(spawned) == 1

    def test_hook_skips_under_test_harness_env(self, monkeypatch) -> None:
        import app.main as m

        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        spawned = self._fake_thread(monkeypatch)
        m._maybe_warm_indexes()
        assert spawned == []

    def test_hook_skips_when_disabled_by_env(self, monkeypatch) -> None:
        import app.main as m

        monkeypatch.delenv("REGENOLD_SKIP_STARTUP_LOG", raising=False)
        monkeypatch.setenv("REGENOLD_INDEX_WARMUP", "0")
        spawned = self._fake_thread(monkeypatch)
        m._maybe_warm_indexes()
        assert spawned == []

    def test_warmup_body_swallows_step_failures(self, monkeypatch) -> None:
        """One failing builder must not abort the remaining steps."""
        import app.main as m
        from app.data import kb_search

        # Keep the run fast in-test: skip the dense build.
        monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")

        import app.engines.embeddings_index as emb

        def _boom() -> None:
            raise RuntimeError("asset missing")

        monkeypatch.setattr(emb, "warm_up", _boom)

        # Must not raise despite the failing step.
        m._run_index_warmup_in_thread()

        # Later/earlier steps still populated the lazy caches.
        assert kb_search._build_index.cache_info().currsize == 1
        from app.engines.sentence_index import _all_sentence_indexes

        assert _all_sentence_indexes.cache_info().currsize == 1


# ─────────────────────────────────────────────────────────────────────────
# Finding #33 — wrapper provider connect-timeout split
# ─────────────────────────────────────────────────────────────────────────


class TestWrapperConnectTimeoutSplit:
    def test_pooled_client_connect_capped(self, monkeypatch) -> None:
        monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        provider = _OpenAIWrapperProvider()
        try:
            t = provider._client.timeout
            assert t.connect == 5.0
            assert t.read == 60.0
            assert t.write == 60.0
            assert t.pool == 60.0
            assert provider._timeout == 60.0  # budget default unchanged
        finally:
            provider._close()

    def test_per_request_timeout_split_on_wire(self) -> None:
        """The actual timeout dict httpx sends per request carries the
        capped connect class on the default path and the caller's short
        budget (un-loosened) on overrides."""
        from app.llm.openai_wrapper_provider import (
            OpenAIWrapperRequest,
            _OpenAIWrapperProvider,
        )

        seen: list[dict] = []

        def _handler(req: httpx.Request) -> httpx.Response:
            seen.append(dict(req.extensions["timeout"]))
            return httpx.Response(
                200,
                json={"model": "x", "choices": [{"message": {"content": "ok"}}]},
            )

        provider = _OpenAIWrapperProvider()
        provider._timeout = 60.0
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.test.invalid",
        )

        provider.complete(OpenAIWrapperRequest(user="ping"))
        assert seen[-1]["connect"] == 5.0
        assert seen[-1]["read"] == 60.0

        provider.complete(OpenAIWrapperRequest(user="quick", timeout_seconds=2.5))
        assert seen[-1]["connect"] == 2.5  # min(5, budget) — never loosened
        assert seen[-1]["read"] == 2.5

        provider.complete(OpenAIWrapperRequest(user="long", timeout_seconds=30))
        assert seen[-1]["connect"] == 5.0
        assert seen[-1]["read"] == 30.0

    def test_budget_timeout_float_equality_contract(self) -> None:
        """The pre-R112 ``post(timeout=<float budget>)`` contract (pinned
        by tests/test_llm_providers.py) survives the split."""
        from app.llm.openai_wrapper_provider import _split_connect_timeout

        t = _split_connect_timeout(60.0)
        assert t == 60.0
        assert not (t == 59.0)
        assert t.connect == 5.0
        t2 = _split_connect_timeout(2.5)
        assert t2 == 2.5
        assert t2.connect == 2.5
        # httpx normalises the subclass into a plain Timeout cleanly.
        norm = httpx.Timeout(t)
        assert norm.connect == 5.0 and norm.read == 60.0


# ─────────────────────────────────────────────────────────────────────────
# Finding #49 — single entity-extraction sweep, identical ranking output
# ─────────────────────────────────────────────────────────────────────────

# Captured from the PRE-refactor code (boosted_articles + second
# extract_entities) under the pytest env (conftest neutralisation), with
# the dense paths disabled — see the R112 work log. The refactored code
# must reproduce these byte-for-byte. The importer row was re-captured
# AFTER the R112 entity-extractor fix (finding 9) landed in the same
# round: Art. 99 is no longer drift-promoted onto non-penalty
# operator-obligation questions, so it dropped out of the top-5. The
# refactor-equivalence itself stays pinned by
# test_boost_helper_matches_boosted_articles (semantic drift guard).
_EXPECTED_BM25_ONLY: dict[str, list[str]] = {
    "What are the obligations of importers of high-risk AI systems?": [
        "Art. 23", "Art. 20", "Art. 6", "Art. 95", "Art. 13",
    ],
    "What technical documentation must providers maintain?": [
        "Art. 16", "Art. 11", "Art. 53", "Annex VII", "Art. 18",
    ],
    "We are a provider of an AI chatbot for customer service.": [
        "Art. 16", "Art. 49", "Annex X", "Art. 3", "Art. 1",
    ],
    # R263 Fix 3 lengthened the bare ``Art. 50`` KB stub's summary (new
    # public-interest text-generation duty + exceptions sentence). BM25's
    # length-normalisation slightly dilutes a longer doc's score, so the
    # already-existing tighter ``Art. 50.3`` sub-entry (whose summary is
    # topically tight to "emotion-recognition" / "biometric-categorisation")
    # now narrowly outranks the bare ``Art. 50`` doc, which also drops out
    # of the top-5 in favour of the ``Art. 3`` definitional virtual doc.
    # Re-captured after the KB_VERSION v17 -> v18 content bump; this is the
    # documented refactor-equivalence pin reacting to a deliberate content
    # edit, not a regression in the entity-extraction refactor it guards.
    "Are emotion recognition systems prohibited in the workplace?": [
        "Annex III", "Art. 5", "Art. 50.3", "Art. 13", "Art. 3",
    ],
    "Who must register the system in the EU database?": [
        "Art. 49", "Art. 16", "Art. 22", "Art. 71", "Art. 83",
    ],
    "What records must deployers retain and for how long?": [
        "Art. 26", "Art. 61", "Annex IX", "Annex X", "Art. 10",
    ],
    # R263 Fix 3 — see the matching comment above; the lengthened bare
    # ``Art. 50`` doc's diluted BM25 score now drops it out of this row's
    # top-5, replaced by ``Art. 96`` (Right to lodge a complaint).
    "transparency obligations for limited-risk systems": [
        "Art. 13", "Art. 6", "Art. 1", "Art. 2", "Art. 96",
    ],
    "What is the definition of a general-purpose AI model?": [
        "Art. 53", "Art. 3", "Art. 51", "Art. 90", "Art. 92",
    ],
}

# Same capture under the DEFAULT env (turboquant dense + embeddings index
# ON, repo assets present) — exercises the full fused path.
_EXPECTED_DEFAULT_ENV: dict[str, list[str]] = {
    "What are the obligations of importers of high-risk AI systems?": [
        "Art. 23", "Art. 20", "Art. 6", "Art. 95", "Art. 13",
    ],
    # R263 Fix 3 — see the matching comment in ``_EXPECTED_BM25_ONLY``
    # above; same re-rank, different tail slot (the dense paths fill the
    # 5th slot with ``Art. 50`` here instead of BM25's ``Art. 3``).
    "Are emotion recognition systems prohibited in the workplace?": [
        "Annex III", "Art. 5", "Art. 50.3", "Art. 13", "Art. 50",
    ],
    "What records must deployers retain and for how long?": [
        "Art. 26", "Art. 61", "Annex IX", "Annex X", "Art. 10",
    ],
}


class TestEntityExtractionDedupe:
    @pytest.fixture(autouse=True)
    def _default_entity_env(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ENTITY_BOOST", raising=False)
        monkeypatch.delenv("REGENOLD_ENTITY_BOOST_FACTOR_ROLE", raising=False)
        monkeypatch.delenv("REGENOLD_ENTITY_BOOST_FACTOR_CONCEPT", raising=False)
        yield

    def test_ranking_identical_bm25_only(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
        monkeypatch.setenv("REGENOLD_EMBEDDINGS_INDEX", "0")
        from app.data.kb_search import top_articles_by_relevance

        for q, expected in _EXPECTED_BM25_ONLY.items():
            assert top_articles_by_relevance(q, k=5) == expected, q

    def test_ranking_identical_default_env(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_TURBOQUANT_DENSE", raising=False)
        monkeypatch.delenv("REGENOLD_EMBEDDINGS_INDEX", raising=False)
        from app.data.kb_search import top_articles_by_relevance

        for q, expected in _EXPECTED_DEFAULT_ENV.items():
            assert top_articles_by_relevance(q, k=5) == expected, q

    def test_extract_entities_runs_exactly_once(self, monkeypatch) -> None:
        """The R112 point: ONE regex sweep per ranking call (was two —
        one inside boosted_articles, one for the injection step)."""
        import app.engines.entity_extractor as ex
        from app.data.kb_search import top_articles_by_relevance

        monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
        monkeypatch.setenv("REGENOLD_EMBEDDINGS_INDEX", "0")

        calls = {"n": 0}
        real = ex.extract_entities

        def _counting(question):
            calls["n"] += 1
            return real(question)

        monkeypatch.setattr(ex, "extract_entities", _counting)

        out = top_articles_by_relevance(
            "What are the obligations of importers of high-risk AI systems?",
            k=5,
        )
        assert calls["n"] == 1
        assert out == _EXPECTED_BM25_ONLY[
            "What are the obligations of importers of high-risk AI systems?"
        ]

    def test_boost_helper_matches_boosted_articles(self) -> None:
        """Drift guard: the kb_search-local boost derivation must stay
        byte-identical to entity_extractor.boosted_articles."""
        from app.data.kb_search import _entity_boosts_from_entities
        from app.engines.entity_extractor import (
            boosted_articles,
            extract_entities,
        )

        questions = list(_EXPECTED_BM25_ONLY) + [
            "",  # no entities
            "banana bread recipe",  # OOS — no entities
            "Must the importer and the distributor verify CE marking "
            "and keep technical documentation?",  # multi role+concept
            "Does the authorised representative handle conformity "
            "assessment and post-market monitoring?",
        ]
        for q in questions:
            assert (
                _entity_boosts_from_entities(extract_entities(q))
                == boosted_articles(q)
            ), q

    def test_disabled_gate_yields_no_boosts(self, monkeypatch) -> None:
        """REGENOLD_ENTITY_BOOST=0 path unchanged: no extraction needed,
        ranking falls back to pure BM25 semantics."""
        monkeypatch.setenv("REGENOLD_ENTITY_BOOST", "0")
        monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
        monkeypatch.setenv("REGENOLD_EMBEDDINGS_INDEX", "0")
        import app.engines.entity_extractor as ex
        from app.data.kb_search import top_articles_by_relevance

        calls = {"n": 0}
        real = ex.extract_entities

        def _counting(question):
            calls["n"] += 1
            return real(question)

        monkeypatch.setattr(ex, "extract_entities", _counting)
        out = top_articles_by_relevance(
            "What are the obligations of importers of high-risk AI systems?",
            k=5,
        )
        assert calls["n"] == 0
        assert isinstance(out, list) and out

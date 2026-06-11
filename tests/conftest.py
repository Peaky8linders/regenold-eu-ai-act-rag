"""Project-wide pytest fixtures.

R63-E (2026-05-19) — autouse fixture that resets the EvidenceStore
singleton before each test. Fixes test-order pollution where
test_consistency_guard.py + other audit-writing tests leak state into
test_regenold_integration.py::test_authenticated_request_writes_partner_tenant_chain_entry
(captures ``before = len(...)`` then asserts ``after > before`` — a
dirty singleton inflates ``before`` and breaks the strict-monotonic
assertion).

The reset is cheap: it just drops a module-level singleton ref. The
next call to ``get_evidence_store()`` rebuilds from env (DATABASE_URL
etc.), which in the standard pytest run is unset → in-memory backend.

Tests that own their own DSNs (e.g. ``test_sqlite_audit_store.py``)
compose cleanly because they call ``reset_evidence_store_for_tests()``
explicitly inside the test body — the autouse fixture runs first, the
test's own reset runs second (idempotent).

R64 (2026-05-19) — distinguish import failures from runtime failures:

* **Import failure** (``reset_evidence_store_for_tests`` is renamed,
  moved, or removed) → raise ``pytest.UsageError`` at collection time.
  Without this helper, the R63-E autouse fixture can't isolate test
  state and the flake silently returns; loud-fail surfaces the
  regression immediately in CI.
* **Runtime failure** (helper raises) → log a WARNING once per session
  and continue. We never want a transient cleanup failure to mask the
  real test outcome, but silently swallowing every call hides
  systematic degradation.
"""
from __future__ import annotations

import logging
import os

# ── R105 — deterministic offline test environment ────────────────────────
#
# pydantic ``Settings`` loads the repo ``.env`` (via ``env_file``), which on a
# developer / CI machine carries the PRODUCTION integration credentials
# (``NEO4J_URI`` → live Aura, ``GROQ_API_KEY`` / ``OPENAI_API_BASE`` → the
# Claude-Max wrapper). Combined with ``is_openai_wrapper_enabled()`` being
# hard-coded ``True`` and the wrapper base URL falling back to the live
# ``wrapper.antifragile-ai.net`` tunnel (60 s timeout), an unguarded
# ``pytest -q`` fires REAL Stage-2 polish + Neo4j hops + de-noiser calls on
# hundreds of route tests. Symptoms: a 74-minute, non-deterministic suite
# whose mock-based de-noiser / wrapper tests FAIL because a real provider
# answers instead of the mock, and whose live-Aura latency makes route tests
# flaky.
#
# Every round's contract ("davidath byte-identical because TestClient skips
# Stage-2") assumes NONE of these services are reachable from the test
# process. This block restores that invariant by neutralising the
# integration-activating env vars in ``os.environ`` BEFORE the first ``app``
# import below — ``os.environ`` takes precedence over the ``.env`` file in
# pydantic, and the per-call ``os.getenv`` gates (Stage-2 master flag,
# de-noiser) read the same values. Tests that need a live-shaped surface opt
# back in per-test via ``monkeypatch.setenv`` / ``monkeypatch.delenv`` (which
# override this base and auto-revert).
#
# NOTE: ``P2P_GRAPH_RAG_PROVIDER`` is deliberately NOT forced to ``cli`` — the
# R97/R100/R56 Stage-2 tests patch ``is_openai_wrapper_enabled`` + set
# ``P2P_GRAPH_RAG_ENABLE_STAGE2=1`` and rely on the default provider routing;
# forcing ``cli`` would make ``_stage2_provider_enabled()`` short-circuit
# before their patch. The Stage-2 master gate below is the safe lever — it
# short-circuits ``_two_stage_generate`` ahead of the provider check, and the
# Stage-2-exercising tests set it back to ``1`` themselves.
#
# Escape hatch: ``REGENOLD_TEST_ALLOW_LIVE=1`` skips the neutralisation
# entirely (e.g. an intentional live-integration smoke run from pytest).
if os.getenv("REGENOLD_TEST_ALLOW_LIVE", "").strip().lower() not in (
    "1",
    "true",
    "yes",
    "on",
):
    # Empty string overrides the ``.env`` value and reads as "disabled" by
    # every presence / truthy gate (graph client, Groq key, RushDB token, …).
    # NOTE: ``OPENAI_API_KEY`` is deliberately NOT cleared — some unit tests
    # (e.g. ``test_external_embeddings``) build a mocked OpenAI client that
    # still needs a non-empty key; and the Stage-2 master gate is left at its
    # code default (ON) so the drift / cap / consistency tests that exercise
    # ``_two_stage_generate`` keep working — they patch the wrapper provider,
    # so they never touch the network.
    for _var in (
        "NEO4J_URI",
        "NEO4J_PASSWORD",
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "DATABASE_URL",
        "GROQ_API_KEY",
        "COHERE_API_KEY",
        "RUSHDB_AUTH_TOKEN",
        "REGENOLD_INTENT_PROVIDER",
        "P2P_GRAPH_RAG_API_KEY",
    ):
        os.environ[_var] = ""
    # Point the Claude-Max wrapper at an UNREACHABLE local port. Route tests
    # that don't patch the provider then fail-fast (connection refused, ~1 ms)
    # → deterministic fallback, instead of a 10-60 s live call to the
    # production ``wrapper.antifragile-ai.net`` tunnel (the wrapper is
    # hard-coded "enabled" + falls back to that tunnel when the base is empty).
    # Unit tests that patch ``_openai_wrapper_complete_for_graph_rag`` /
    # ``get_openai_wrapper_provider`` bypass the HTTP layer entirely, so this
    # is invisible to them.
    os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
    # Multi-turn query de-noiser network OFF (unit tests opt back in per-test).
    os.environ["REGENOLD_QUERY_DENOISER"] = "0"

import pytest

logger = logging.getLogger(__name__)

# R64 — module-level import. If this fails, every test loses isolation
# and the R63-E flake returns invisibly; raise loudly at collection time
# so the regression is caught immediately in CI. AttributeError is NOT
# caught here — a test env that intentionally stubs out the helper can
# still rebind the symbol on this module after import.
try:
    from app.evidence.store import reset_evidence_store_for_tests
except ImportError as _import_exc:  # pragma: no cover — collection-time guard
    raise pytest.UsageError(
        "tests/conftest.py — required import failed: "
        f"app.evidence.store.reset_evidence_store_for_tests ({_import_exc}). "
        "Without this helper, the R63-E autouse fixture cannot isolate "
        "test state and the R63-E flake "
        "(test_authenticated_request_writes_partner_tenant_chain_entry "
        "↔ test_consistency_guard.py) will silently return. Update the "
        "import path or the helper name and re-run."
    ) from _import_exc

# One-shot flag so a systematic runtime failure (e.g. broken DSN parsing
# during ``reset_evidence_store_for_tests``) logs once per session rather
# than once per test.
_RESET_FAILURE_LOGGED: bool = False


def _safe_reset_audit_store() -> None:
    """Call ``reset_evidence_store_for_tests`` with one-shot WARNING on failure.

    R64 — extracted from the autouse fixture body so the regression test
    can exercise the one-shot WARNING semantics directly (pytest forbids
    calling fixtures directly).
    """
    global _RESET_FAILURE_LOGGED
    try:
        reset_evidence_store_for_tests()
    except Exception as exc:  # noqa: BLE001 — never block a test on cleanup
        if not _RESET_FAILURE_LOGGED:
            logger.warning(
                "tests/conftest.py: reset_evidence_store_for_tests() raised "
                "%s; subsequent failures will be silent. R63-E test isolation "
                "may be degraded.",
                exc,
            )
            _RESET_FAILURE_LOGGED = True


@pytest.fixture(autouse=True)
def _reset_audit_store():
    """Drop the EvidenceStore singleton between tests.

    R64 — runtime failures here are wrapped in a one-shot WARNING so a
    transient cleanup error never blocks a test's real outcome, but a
    systematic degradation is still visible in the pytest log stream.
    Import failures are handled at module level above (loud-fail).
    """
    _safe_reset_audit_store()
    yield
    # No post-test reset needed; the next test's pre-yield reset
    # handles cleanup. Keeping this one-sided also means a failing
    # test's audit-chain state is still inspectable in a post-mortem
    # pytest --pdb session.


# R84 (2026-05-24) — `app.routes.regenold._classify_intent_cached` memoises
# `classify_intent(question)` per request via a `ContextVar[dict | None]`.
# Inside the route the ContextVar is `.set({})` at the top of the handler
# (per-request scope). Tests that exercise `_classify_intent_cached` /
# `_intent_anchor_set` directly skip that reset, so the lazy-init dict
# from one test persists into the next and serves cached results across
# distinct `patch("classify_intent", ...)` setups. Symptom: two tests
# patching the SAME question key to different mocked IntentResult values
# see the FIRST test's value in BOTH (e.g.
# `test_unknown_article_anchor_is_dropped` caches an empty result for
# `"What's the max fine?"` and the subsequent `test_known_article_anchor_is_kept`
# reads the empty cache hit instead of the patched `Art. 99` result).
# Mirrors the R63-E EvidenceStore isolation pattern above.
try:
    from app.routes import regenold as _regenold_module
except ImportError:  # pragma: no cover — tested env always has this
    _regenold_module = None


# R100 (2026-05-31) — reset the slowapi route rate-limiter between tests.
# The route enforces a per-API-key budget (default 60/min). The full suite
# shares one key (``regenold-test-key``) across hundreds of route POSTs
# that all complete inside one ~50s window, so the per-key counter
# accumulates and tips late-running route tests over the limit → HTTP 429
# (e.g. test_regenold_integration's compound-role budget assertions read a
# 429 body and fail on ``len(references)``). Several modules already reset
# the limiter per-module (test_consistency_guard, test_retrieval_upgrades,
# test_route_include_reasoning, …); this autouse fixture lifts that to the
# whole suite so adding route tests in any round can't re-trip the ceiling.
# Mirrors the R63-E / R84 reset-shared-state pattern above. No test asserts
# a route 429, so a global reset is safe.
try:
    from app.rate_limit import limiter as _route_limiter
except ImportError:  # pragma: no cover — tested env always has this
    _route_limiter = None


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the slowapi route limiter before each test (R100)."""
    if _route_limiter is not None:
        try:
            _route_limiter.reset()
        except Exception:  # noqa: BLE001 — never block a test on cleanup
            pass
    yield


@pytest.fixture(autouse=True)
def _reset_request_intent_cache():
    """Clear the per-request intent cache ContextVar between tests.

    R84 isolation — see comment above. Setting the ContextVar to ``None``
    re-arms the lazy-init path so each test starts with no in-flight
    cache state.
    """
    if _regenold_module is not None:
        try:
            _regenold_module._request_intent_cache.set(None)
        except Exception:  # noqa: BLE001 — never block a test on cleanup
            pass
    yield


# R105 — reset the pooled LLM provider singletons + the lazy Anthropic
# client cache between tests. The provider module memoises FOUR
# process-wide objects that bind to env at FIRST construction and never
# rebuild:
#
#   * ``openai_wrapper_provider._SINGLETON``  — bound to ``OPENAI_API_BASE``
#   * ``openai_wrapper_provider._GROQ_SINGLETON``   — bound to ``GROQ_API_KEY``
#   * ``openai_wrapper_provider._GEMINI_SINGLETON``  — bound to ``GEMINI_API_KEY``
#   * ``graph_rag._get_anthropic_client`` — ``lru_cache(maxsize=1)`` keyed
#     on NO args, holding a client built from ``settings.graph_rag.api_key``.
#
# A Stage-2-exercising test (e.g. ``test_anthropic_provider.py``,
# ``test_r97_answer_router.py``) constructs one of these under its own
# ``monkeypatch.setenv`` / ``monkeypatch.setattr`` setup; the value is
# cached. When that test's monkeypatch reverts, the SINGLETON does NOT —
# it stays bound to the now-reverted env, and a later test reading the
# same accessor gets the stale object. Concrete observed failures (pass
# in isolation, fail in-suite):
#   * ``test_r91_llm_truncation::test_anthropic_end_turn_returns_text`` —
#     monkeypatches ``anthropic.Anthropic`` to a fake, but the cached
#     ``_get_anthropic_client`` returns the prior test's client (built
#     before the patch) → the fake ``create()`` never runs → result is
#     ``None`` instead of the mocked text.
#   * the ``test_graph_rag_bugfixes`` drift-guard tests, similarly, see a
#     cached wrapper / anthropic client from a Stage-2 polluter.
# This mirrors the c4a7505 anthropic-client-cache fix (which only cleared
# the cache inside ``test_anthropic_provider``'s own fixture) and the
# R63-E / R84 / R100 reset-shared-state pattern — lifted to the whole
# suite so any test order is isolated. Fail-soft: a reset error never
# blocks a test.
try:
    from app.llm import openai_wrapper_provider as _llm_provider
except ImportError:  # pragma: no cover — tested env always has this
    _llm_provider = None

try:
    from app.engines.graph_rag import _get_anthropic_client as _anthropic_client_cache
except ImportError:  # pragma: no cover — tested env always has this
    _anthropic_client_cache = None


@pytest.fixture(autouse=True)
def _reset_llm_provider_singletons():
    """Drop the pooled LLM provider singletons + Anthropic client cache (R105)."""
    if _llm_provider is not None:
        # Groq + Gemini have dedicated reset helpers (close the pooled
        # httpx.Client + null the module global).
        for _helper in ("_reset_groq_singleton_for_tests", "_reset_gemini_singleton_for_tests"):
            fn = getattr(_llm_provider, _helper, None)
            if fn is not None:
                try:
                    fn()
                except Exception:  # noqa: BLE001 — never block a test on cleanup
                    pass
        # The main wrapper singleton has no helper — reset its module
        # global directly, closing the pooled client first.
        try:
            existing = getattr(_llm_provider, "_SINGLETON", None)
            if existing is not None:
                try:
                    existing._close()  # noqa: SLF001 — test hook
                except Exception:  # noqa: BLE001
                    pass
            _llm_provider._SINGLETON = None
        except Exception:  # noqa: BLE001
            pass
    if _anthropic_client_cache is not None:
        try:
            _anthropic_client_cache.cache_clear()
        except Exception:  # noqa: BLE001
            pass
    yield


# R89-A code-review fix (E&EC-F4) — clear REGENOLD_R89A_FORCE_APPEND
# before every test so a developer running the full suite with the
# production env var set (matches railway.toml) sees CI / local parity.
# Tests that want to exercise the force-append path explicitly opt in
# via ``monkeypatch.setenv("REGENOLD_R89A_FORCE_APPEND", "1")``. Mirrors
# the per-test env-clearing pattern documented in the R84 fixture above.
@pytest.fixture(autouse=True)
def _reset_r89a_force_append_env(monkeypatch):
    """Default the R89-A force-append env to OFF for every test.

    Without this, a developer who runs the full suite with the
    production env (``REGENOLD_R89A_FORCE_APPEND=1`` from railway.toml)
    in their shell would see different augmenter behavior than CI —
    the legacy R79 / R80 / R81-N appender-path guards would fail in a
    way that's hard to debug. Forcing OFF here keeps every test
    deterministic regardless of the developer's shell state.
    """
    monkeypatch.delenv("REGENOLD_R89A_FORCE_APPEND", raising=False)
    yield


# R105 — default the per-call answer-shaping env knobs OFF for every test.
#
# Three env vars flip CALL-TIME behaviour of code the deterministic
# regression tests assert against. They are NOT in the import-time
# neutralisation block at the top of this file (that block runs ONCE,
# before the first import, and only covers integration credentials). A
# test that sets one without ``monkeypatch`` — or any future leak into
# the process environment — persists into later tests and silently flips
# behaviour, producing in-suite-ONLY failures (the tests pass in
# isolation because the developer ``.env`` does NOT auto-load into
# ``os.environ``). Defaulting them OFF per test makes the affected guards
# deterministic regardless of run order. Tests that need the ON path opt
# back in via ``monkeypatch.setenv`` (which overrides this ``delenv`` for
# that one test and auto-reverts). Mirrors the ``_reset_r89a_force_append_env``
# pattern above.
#
# * ``REGENOLD_DYNAMIC_GROUNDING`` — R101 historically gated the
#   parametric-memory tolerance in the Stage-2 drift guard. R113
#   (2026-06-11) baked that tolerance into the CODE default
#   (``graph_rag._polished_prose_has_unknown_citations`` only flags
#   fabricated provisions now), so the flag's remaining effect is the
#   R72 reconcile floor in ``routes/regenold.py``. Still defaulted OFF
#   per test for determinism; ``test_r105_post_cap_reconcile.py`` opts
#   it ON via its own setenv.
# * ``REGENOLD_MAX_ANSWER_SENTENCES`` — ``normalise_answer_for_regenold``
#   reads it at call time; an unset value falls back to the code constant
#   ``MAX_ANSWER_SENTENCES`` (3). A leaked higher value (e.g. 6 from
#   ``test_r105``'s ``_stage2_env``) breaks
#   ``test_citation_minimisation_and_caps::test_sentence_cap_enforced_when_input_exceeds``.
# * ``REGENOLD_HARD_CHAR_CAP`` — the R78 hard-truncate backstop, default
#   OFF in code; a leaked ``1`` makes
#   ``test_citation_minimisation_and_caps::test_soft_cap_keeps_at_least_one_sentence_even_if_all_cite``
#   truncate a load-bearing cite sentence it asserts is preserved. The
#   ``TestR78HardCharCap`` cases opt it ON via their own setenv.
@pytest.fixture(autouse=True)
def _reset_answer_shaping_env(monkeypatch):
    """Default the per-call answer-shaping env knobs OFF for every test (R105)."""
    for _var in (
        "REGENOLD_DYNAMIC_GROUNDING",
        "REGENOLD_MAX_ANSWER_SENTENCES",
        "REGENOLD_HARD_CHAR_CAP",
    ):
        monkeypatch.delenv(_var, raising=False)
    yield


# R94 (2026-05-29) — verbatim exact-text answers ship as the route DEFAULT
# (``REGENOLD_VERBATIM_ANSWER`` on): when a request resolves to references,
# the wire ``answer`` is replaced with the VERBATIM EUR-Lex text of the
# cited provisions (sub-point-resolved), per the user's "exact text, no
# reformulations, drop caps" directive. The modules below predate R94 and
# pin the underlying answer-ASSEMBLY contract — classification verdicts,
# the 3-sentence / 600-char cap conformance gates, role-obligation prose,
# the refusal/short-circuit gates — which still runs BENEATH the verbatim
# presentation layer. The verbatim default itself is validated end-to-end
# in ``tests/test_r94_verbatim.py``. Disable verbatim for these modules so
# their assertions exercise the layer they were written for.
_R94_VERBATIM_OFF_MODULES = (
    "test_classification_verdicts",
    "test_regenold_integration",
    "test_regenold_scope",
    "test_retrieval_upgrades",
    "test_route_round_36_fixes",
)


@pytest.fixture(autouse=True)
def _r94_pin_verbatim_off(request, monkeypatch):
    """Pin verbatim mode OFF for the legacy answer-assembly test modules."""
    mod = getattr(request, "module", None)
    name = getattr(mod, "__name__", "") if mod is not None else ""
    if any(name.endswith(m) for m in _R94_VERBATIM_OFF_MODULES):
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
    yield


# R98 (2026-05-30) — RushDB is now OPT-IN. The 2026-05-25 RushDB migration
# hit RushDB's free-trial limits, so Neo4j Aura is the default graph
# backend again and every RushDB surface is gated behind
# ``REGENOLD_GRAPH_BACKEND=rushdb`` (see
# app/graph/rushdb_config.py::rushdb_backend_selected). The RushDB-specific
# suites still exercise the dormant RushDB code paths, so they opt in here;
# every other test runs under the default neo4j backend (RushDB inert),
# which is exactly what production now does.
_RUSHDB_OPT_IN_MODULES = frozenset(
    {
        "test_rushdb_client",
        "test_rushdb_auto_seed",
        "test_rushdb_hybrid_retrieval",
        "test_seed_rushdb_kb",
    }
)


@pytest.fixture(autouse=True)
def _rushdb_backend_opt_in(request, monkeypatch):
    """Select the RushDB backend for the RushDB-specific suites only.

    ``test_healthz_graph`` is intentionally excluded: it monkeypatches
    ``rushdb_client.is_enabled`` directly (replacing the function), so it
    bypasses the backend gate and doesn't need the opt-in.
    """
    mod = getattr(request, "module", None)
    name = getattr(mod, "__name__", "") if mod is not None else ""
    stem = name.rsplit(".", 1)[-1]
    if stem in _RUSHDB_OPT_IN_MODULES:
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "rushdb")
    yield

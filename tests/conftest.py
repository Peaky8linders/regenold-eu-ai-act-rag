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

import errno as _errno
import ipaddress as _ipaddress
import logging
import os
import socket as _socket

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
    # every presence / truthy gate (graph client, Groq key, …).
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
    # R127 — the PRODUCTION graph-backend default is now ``embedded`` (the
    # in-process SQLite property graph; Aura retired as the default). The
    # historical Neo4j-path tests (``test_graph_expand_2hop`` mocks the
    # client + asserts Cypher-shaped hop1/hop2 rows; the client-activation
    # tests) were written against the old neo4j default, so pin neo4j as the
    # test-suite base. Embedded-path tests opt in via
    # ``monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")``; the
    # default-resolution test deletes the var to assert the embedded code
    # default. NEO4J_URI stays empty above, so the Neo4j *client* is still
    # disabled in tests — only the backend *selector* reads neo4j here.
    os.environ["REGENOLD_GRAPH_BACKEND"] = "neo4j"

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


# ══════════════════════════════════════════════════════════════════════════
# R361 — global process-state isolation.
#
# MEASURED 2026-08-23: the full suite reported 95 failures while the same
# files passed in isolation — e.g. tests/test_two_stage_pipeline.py fails 8
# in-suite and passes 40/40 alone; tests/test_topic_filter.py fails 3
# in-suite and passes 23/23 alone, both with a dead wrapper and a live one.
# That is not a hermeticity problem and not a real defect: it is ORDER
# DEPENDENCE. Whatever ran earlier left process-global state behind.
#
# The source: 48 raw ``os.environ[...] = ...`` writes across tests/ that never
# restore, plus module-level caches that outlive the test that filled them.
# The fixtures above reset seven specific singletons; nothing resets the
# ENVIRONMENT, which is the widest channel of all — this repo's own CLAUDE.md
# records that `REGENOLD_*` flags are behavioural, so a leaked one silently
# reconfigures every later test.
#
# Fixing 37 files individually would be churn with a long tail. One snapshot
# /restore closes the whole class, and keeps working for tests added later.
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def _restore_process_environment():
    """Snapshot ``os.environ`` before each test; restore it exactly after.

    ``monkeypatch.setenv`` already unwinds itself. This catches the raw
    ``os.environ[...] =`` writes that do not, so one test can no longer
    reconfigure the ones that follow it.

    Restores by MUTATING the existing mapping rather than rebinding it —
    ``os.environ`` is a live object other modules may hold a reference to.
    """
    import os as _os

    snapshot = dict(_os.environ)
    try:
        yield
    finally:
        current = dict(_os.environ)
        for key in current:
            if key not in snapshot:
                _os.environ.pop(key, None)
        for key, value in snapshot.items():
            if current.get(key) != value:
                _os.environ[key] = value


@pytest.fixture(autouse=True)
def _reset_engine_and_transport_state():
    """Clear the route engine cache and the Stage-2 transport counters.

    The engine LRU stores FINAL polished prose keyed by an env fingerprint, so
    a cached blob from an earlier test can be replayed into a later one whose
    env differs only in a dimension the key does not cover — the same class of
    bug AGENTS.md invariant #4 exists to prevent, arriving via the test suite.

    The transport counters are process-global by design (R360), so without a
    reset a test asserting ``primary_ok == 1`` passes or fails depending on how
    many Stage-2 calls happened to run before it.
    """
    try:
        from app.routes.regenold import _ENGINE_CACHE
        clear = getattr(_ENGINE_CACHE, "clear", None)
        if callable(clear):
            clear()
    except Exception:  # noqa: BLE001 — cleanup must never block a test
        pass
    try:
        from app.llm import stage2_policy as _s2pol
        _s2pol.reset_transport_stats()
    except Exception:  # noqa: BLE001
        pass
    yield


# ══════════════════════════════════════════════════════════════════════════
# R365 — the suite is OFFLINE BY DEFAULT, and fast about it.
#
# TWO measured defects, both fixed here at the socket layer.
#
# (1) EGRESS. The import-time block at the top of this file points
#     ``OPENAI_API_BASE`` at a dead loopback port, which covers MOST of the
#     suite. It does not cover the 14 sites that ``monkeypatch.delenv`` that
#     very variable: with the var gone, ``OpenAIWrapperProvider.__init__``
#     (app/llm/openai_wrapper_provider.py:403-406) falls back to a hard-coded
#     PRODUCTION host. MEASURED 2026-08-24 — 5 tests in 3 files issued 8 real
#     HTTPS POSTs to the production wrapper on every ``pytest`` run:
#       test_clara_logic::test_extract_tags_llm_returns_none_when_wrapper_disabled  1
#       test_r86_query_denoiser_and_deployer_hop::test_denoiser_no_provider_returns_none  1
#       test_r100_synthesis_default::TestRouteSynthesisDefault (3 tests)            2 each
#     They "pass" because Cloudflare Access answers 401 and every caller has a
#     deterministic fallback — i.e. the round-trip buys nothing but latency,
#     non-determinism and quota. An env var is the wrong lever (a ``delenv``
#     defeats it); the socket is the right one.
#
# (2) LATENCY. The R105 block above claims a dead-base connect "fail[s]-fast
#     (connection refused, ~1 ms)". MEASURED on this Windows box: a TCP
#     connect to ANY closed loopback port costs **2.03 s** before
#     WSAECONNREFUSED (127.0.0.1:1 → 2.0351 s, :9 → 2.0457 s, :47111 →
#     2.0346 s). Not ~1 ms — ~2000 ms, paid per LLM call.
#     ``tests/test_topic_filter.py`` spent ~16 s of its 19.6 s in 8 such
#     connects.
#
# MECHANISM — one patch over ``socket.socket.connect`` / ``connect_ex``:
#
#   * NON-LOOPBACK destination → refused before the syscall, naming the test
#     and the destination. Nothing leaves the box.
#   * LOOPBACK destination → still attempted for real, but under a 0.25 s
#     ceiling, and a ``(host, port)`` that refuses once is remembered so later
#     connects short-circuit with no syscall at all. MEASURED: a live loopback
#     listener accepts in **0.00037 s**, so 0.25 s is a ~680× margin — this
#     cannot turn a working local server into a failure. ``bind()`` drops the
#     matching entry, so a test that starts a server on a port an earlier test
#     found closed still connects.
#   * ``@pytest.mark.allow_network`` disables the guard for one test.
#
# WHY ``ConnectionRefusedError`` AND NOT A HARD FAIL BY DEFAULT: a refusal is
# exactly what the caller sees with the network truly unplugged, so the
# offline path under test is the REAL offline path and the five tests above
# keep asserting the fallback they were written to assert. Loudness is not
# sacrificed — every blocked attempt is logged, an end-of-session report names
# each offender, and ``REGENOLD_TEST_EGRESS_STRICT=1`` escalates any blocked
# egress to a test failure.
#
# NOT PATCHED: ``socket.getaddrinfo``. ``tests/test_r136_dns_retry.py``
# installs its own TTL cache there and asserts the identity of the installed
# function; patching it would break a currently-passing test.
# ══════════════════════════════════════════════════════════════════════════
#: Marker that opts a single test out of the guard entirely.
ALLOW_NETWORK_MARKER = "allow_network"

#: Ceiling on a LOOPBACK connect attempt. A live local listener accepts in
#: ~0.4 ms (measured); a closed port would otherwise burn 2.03 s.
LOOPBACK_CONNECT_BUDGET_SECONDS = 0.25

_LOOPBACK_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", ""})

# Session state. Single-element lists so the patched functions can mutate them
# without ``global``.
_egress_current_test: list[str] = ["<session>"]
_egress_allowed: list[bool] = [False]
#: ``(nodeid, "host:port")`` for every connect the guard refused.
BLOCKED_EGRESS: list[tuple[str, str]] = []
#: ``(host, port)`` pairs on loopback that have already refused once.
_DEAD_LOOPBACK: set[tuple[str, int]] = set()

# Stashed on the ``socket`` MODULE, not just here, so that a second import of
# this conftest under a different module name cannot capture an already-guarded
# function as the "original" and wrap the guard in itself.
_real_socket_connect = getattr(_socket, "_r365_real_connect", None) or _socket.socket.connect
_real_socket_connect_ex = (
    getattr(_socket, "_r365_real_connect_ex", None) or _socket.socket.connect_ex
)
_real_socket_bind = getattr(_socket, "_r365_real_bind", None) or _socket.socket.bind
_socket._r365_real_connect = _real_socket_connect
_socket._r365_real_connect_ex = _real_socket_connect_ex
_socket._r365_real_bind = _real_socket_bind


class NetworkEgressBlocked(ConnectionRefusedError):
    """A test tried to open a TCP connection to a non-loopback address.

    Subclasses ``ConnectionRefusedError`` on purpose — see the R365 note
    above. The connection is never attempted, so no request is sent and no
    provider quota is consumed.
    """


def _egress_inet_target(address) -> tuple[str, int] | None:
    """``(host, port)`` for an AF_INET/AF_INET6 target, else ``None``.

    ``None`` means "not an IP socket" (an AF_UNIX path, bytes, an odd tuple);
    those pass through untouched.
    """
    if not isinstance(address, tuple) or len(address) < 2:
        return None
    host, port = address[0], address[1]
    if not isinstance(host, str) or not isinstance(port, int):
        return None
    return host, port


def _egress_is_loopback(host: str) -> bool:
    """True when a connect to ``host`` cannot leave the machine."""
    candidate = host.strip().lower()
    if candidate in _LOOPBACK_HOSTNAMES:
        return True
    if candidate in ("0.0.0.0", "::"):  # wildcard → resolves local
        return True
    try:
        parsed = _ipaddress.ip_address(candidate.split("%", 1)[0])
    except ValueError:
        # Not a literal IP and not a known local alias. DNS has not resolved
        # it here, so treat it as remote — the safe side.
        return False
    if parsed.is_loopback or parsed.is_unspecified:
        return True
    if isinstance(parsed, _ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        return parsed.ipv4_mapped.is_loopback
    return False


def _egress_dead_keys(host: str, port: int) -> tuple[tuple[str, int], ...]:
    """Negative-cache keys for one endpoint, folding the loopback aliases.

    ``localhost`` / ``127.0.0.1`` / ``::1`` are the same listener as far as a
    test is concerned, so one refusal should silence all three spellings.
    """
    canonical = host.strip().lower()
    if _egress_is_loopback(canonical):
        return tuple(
            (alias, port) for alias in ("localhost", "127.0.0.1", "::1", canonical)
        )
    return ((canonical, port),)


def _egress_refuse_remote(host: str, port: int) -> NetworkEgressBlocked:
    """Record the violation and build the error that names it."""
    destination = f"{host}:{port}"
    nodeid = _egress_current_test[0]
    BLOCKED_EGRESS.append((nodeid, destination))
    logger.warning(
        "R365 socket guard BLOCKED network egress: test=%s destination=%s",
        nodeid,
        destination,
    )
    return NetworkEgressBlocked(
        _errno.ECONNREFUSED,
        (
            f"R365 offline test suite: {nodeid} attempted a TCP connect to "
            f"{destination}, which is not loopback. The connection was refused "
            f"before any bytes were sent — no request reached that host and no "
            f"provider quota was spent. "
            f"If this is accidental (the usual cause is a monkeypatch.delenv of "
            f"OPENAI_API_BASE, which lets OpenAIWrapperProvider fall back to "
            f"the hard-coded production host at "
            f"app/llm/openai_wrapper_provider.py:405), point the provider at a "
            f"stub or patch the transport. If this test genuinely needs the "
            f"network, mark it @pytest.mark.{ALLOW_NETWORK_MARKER}."
        ),
    )


def _egress_connect_budget(sock, address, real_call):
    """Run ``real_call`` against a loopback endpoint under a time ceiling.

    Raises ``TimeoutError`` when the ceiling is hit; the caller turns that
    into a refusal and remembers the endpoint.
    """
    original_timeout = sock.gettimeout()
    # A non-blocking socket (0) or one already on a tighter budget needs no
    # help, and overriding it would CHANGE that socket's semantics.
    if (
        original_timeout is not None
        and original_timeout <= LOOPBACK_CONNECT_BUDGET_SECONDS
    ):
        return real_call(sock, address)
    try:
        sock.settimeout(LOOPBACK_CONNECT_BUDGET_SECONDS)
    except OSError:  # pragma: no cover — closed / exotic socket
        return real_call(sock, address)
    try:
        return real_call(sock, address)
    finally:
        try:
            sock.settimeout(original_timeout)
        except OSError:  # pragma: no cover
            pass


def _egress_guarded_connect(self, address):
    """``socket.socket.connect`` under the R365 guard."""
    if _egress_allowed[0]:
        return _real_socket_connect(self, address)
    target = _egress_inet_target(address)
    if target is None:
        return _real_socket_connect(self, address)
    host, port = target
    if not _egress_is_loopback(host):
        raise _egress_refuse_remote(host, port)
    keys = _egress_dead_keys(host, port)
    if any(key in _DEAD_LOOPBACK for key in keys):
        # Already proven closed this session — skip the syscall entirely.
        raise ConnectionRefusedError(
            _errno.ECONNREFUSED,
            f"R365: {host}:{port} refused earlier in this session (cached)",
        )
    try:
        return _egress_connect_budget(self, address, _real_socket_connect)
    except (TimeoutError, ConnectionRefusedError):
        _DEAD_LOOPBACK.update(keys)
        raise


def _egress_guarded_connect_ex(self, address):
    """``socket.socket.connect_ex`` under the R365 guard.

    A remote destination RAISES rather than returning an errno: a silent
    errno is precisely the failure mode this guard exists to end.
    """
    if _egress_allowed[0]:
        return _real_socket_connect_ex(self, address)
    target = _egress_inet_target(address)
    if target is None:
        return _real_socket_connect_ex(self, address)
    host, port = target
    if not _egress_is_loopback(host):
        raise _egress_refuse_remote(host, port)
    keys = _egress_dead_keys(host, port)
    if any(key in _DEAD_LOOPBACK for key in keys):
        return _errno.ECONNREFUSED
    try:
        result = _egress_connect_budget(self, address, _real_socket_connect_ex)
    except (TimeoutError, ConnectionRefusedError):
        _DEAD_LOOPBACK.update(keys)
        return _errno.ECONNREFUSED
    # ``connect_ex`` reports the budget expiry as a return code, not a raise.
    # 10035 WSAEWOULDBLOCK / 10060 WSAETIMEDOUT / 10061 WSAECONNREFUSED.
    if result in (_errno.ECONNREFUSED, _errno.ETIMEDOUT, 10035, 10060, 10061):
        _DEAD_LOOPBACK.update(keys)
        if result in (10035, 10060):
            return _errno.ECONNREFUSED
    return result


def _egress_guarded_bind(self, address):
    """``socket.socket.bind`` — un-blacklists the port about to be served.

    Without this, a test that starts a local server on a port some earlier
    test found closed would be refused straight out of the negative cache.
    """
    result = _real_socket_bind(self, address)
    try:
        target = _egress_inet_target(address)
        port = target[1] if target is not None else None
        if not port:  # bind(('127.0.0.1', 0)) — the OS chose the port
            port = self.getsockname()[1]
        for alias in ("localhost", "127.0.0.1", "::1"):
            _DEAD_LOOPBACK.discard((alias, port))
    except Exception:  # noqa: BLE001 — bookkeeping must never break a bind
        pass
    return result


def _egress_install() -> None:
    _socket.socket.connect = _egress_guarded_connect
    _socket.socket.connect_ex = _egress_guarded_connect_ex
    _socket.socket.bind = _egress_guarded_bind


def _egress_uninstall() -> None:
    _socket.socket.connect = _real_socket_connect
    _socket.socket.connect_ex = _real_socket_connect_ex
    _socket.socket.bind = _real_socket_bind


# Installed at conftest IMPORT time, not inside the session fixture: test
# modules are imported during collection, before any fixture runs, so a module
# that dials out at import would otherwise slip past.
_egress_install()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{ALLOW_NETWORK_MARKER}: R365 — allow this test real network egress "
        "(the suite is offline by default).",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Arm the guard for this test before its fixtures run."""
    _egress_current_test[0] = item.nodeid
    _egress_allowed[0] = item.get_closest_marker(ALLOW_NETWORK_MARKER) is not None


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    _egress_allowed[0] = False


def _egress_strict_enabled() -> bool:
    return os.getenv("REGENOLD_TEST_EGRESS_STRICT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@pytest.fixture(autouse=True)
def _fail_on_blocked_egress(request):
    """Under ``REGENOLD_TEST_EGRESS_STRICT=1``, blocked egress fails the test.

    Default OFF: refusing the connect already delivers the safety property
    (nothing is sent), and the five tests that currently trip the guard are
    asserting their offline fallback — which is exactly what a refusal
    produces. Strict mode exists so CI can demand a suite that does not even
    ATTEMPT to dial out.
    """
    before = len(BLOCKED_EGRESS)
    yield
    if not _egress_strict_enabled():
        return
    new = BLOCKED_EGRESS[before:]
    if new:
        destinations = sorted({dest for _nodeid, dest in new})
        pytest.fail(
            "R365 strict mode: this test attempted network egress to "
            f"{', '.join(destinations)}. Mark it "
            f"@pytest.mark.{ALLOW_NETWORK_MARKER} or stop it dialling out.",
            pytrace=False,
        )


@pytest.fixture(scope="session", autouse=True)
def _r365_socket_guard():
    """Session-scoped owner of the guard: verify, then report, then restore."""
    assert _socket.socket.connect is _egress_guarded_connect, (
        "R365 socket guard is not installed — the suite would be free to dial "
        "the production wrapper."
    )
    try:
        yield
    finally:
        _egress_uninstall()
        if BLOCKED_EGRESS:
            offenders: dict[str, set[str]] = {}
            for nodeid, dest in BLOCKED_EGRESS:
                offenders.setdefault(nodeid, set()).add(dest)
            print(
                "\n"
                + "=" * 74
                + f"\nR365 socket guard: BLOCKED {len(BLOCKED_EGRESS)} network "
                f"connect(s) from {len(offenders)} test(s).\n"
                "Nothing was sent. Each of these would have dialled out on a "
                "developer machine:\n"
            )
            for nodeid in sorted(offenders):
                print(f"  {nodeid}\n      -> {', '.join(sorted(offenders[nodeid]))}")
            print(
                "Set REGENOLD_TEST_EGRESS_STRICT=1 to turn these into test "
                "failures.\n" + "=" * 74
            )

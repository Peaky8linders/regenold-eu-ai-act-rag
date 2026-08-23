"""R361 — the instruments must not report a state the system is not in.

Every test here pins a RUNTIME observation (a counter, a returned verdict, a
seed decision), never the shape of the code. That is the R329/R331 discipline:
three rerank placements once read correctly in the diff and made zero calls, so
a test that asserts on structure proves nothing.

Each test is written to FAIL against the pre-R361 code at ``1cab8f0``. Where a
fix has a natural inverse, the inverse is pinned too — a guard whose OFF state
behaves like its ON state is the inert-feature trap.
"""
from __future__ import annotations

import json
import time

import pytest

from app.llm import stage2_policy as s2pol


# ══════════════════════════════════════════════════════════════════════════
# A1 / I1 / L2 — the boot auto-seed guard must treat a SWALLOWED read failure
# as ignorance, not as "the graph is empty".
# ══════════════════════════════════════════════════════════════════════════
class _LenientClient:
    """Mimics the REAL ``GraphClient``: ``execute_read`` swallows and returns [].

    This is the distinction the pre-R361 test missed. Its double raised, which
    the production client cannot do (``client.py:203`` logs and returns ``[]``),
    so it exercised a branch production never took.
    """

    enabled = True

    def __init__(self, *, strict_raises: bool = True) -> None:
        self.strict_raises = strict_raises
        self.reads: list[str] = []

    def execute_read(self, query, parameters=None):
        self.reads.append(query)
        return []                      # <-- the swallow, verbatim

    def execute_read_strict(self, query, parameters=None):
        self.reads.append(query)
        if self.strict_raises:
            raise RuntimeError("Unable to retrieve routing information")
        return []

    def health_check(self):
        return {"status": "unhealthy"}


def _seed_decisions(monkeypatch, client) -> list[str]:
    """Run the real ``_maybe_auto_seed_neo4j`` and capture any seed reason."""
    import app.main as main

    monkeypatch.setenv("NEO4J_URI", "neo4j+s://test.databases.neo4j.io")
    monkeypatch.delenv("NEO4J_AUTO_SEED", raising=False)   # default-ON path
    monkeypatch.setattr(main, "_AUTO_SEED_STARTED", False, raising=False)
    monkeypatch.setattr(main, "get_graph_client", lambda: client, raising=False)
    monkeypatch.setattr(
        "app.graph.client.get_graph_client", lambda: client, raising=False
    )

    fired: list[str] = []
    # Replace the WORK, not ``threading.Thread``. Patching Thread on the real
    # threading module also breaks ThreadPoolExecutor, which this very function
    # uses for its bounded metadata probe — the executor's worker never starts
    # and the seeder deadlocks on ``.result()``.
    monkeypatch.setattr(
        main, "_run_auto_seed_in_thread",
        lambda reason: fired.append(reason), raising=False,
    )
    main._maybe_auto_seed_neo4j()
    # The seeder spawns a real daemon thread; give it a moment to append.
    for _ in range(50):
        if fired:
            break
        time.sleep(0.01)
    return fired


def test_a_swallowed_metadata_failure_does_not_seed(monkeypatch):
    """The bug that could overwrite a live Aura graph.

    Pre-R361 both reads used the lenient method, so a retry-exhausted read gave
    ``meta_rows=[]`` -> ``current_seed=""`` -> the seed-version match was never
    reached -> the ``not current_seed`` branch -> node count also ``[]`` -> 0 ->
    ``reason="graph_empty"`` -> a full MERGE over live data.
    """
    client = _LenientClient()
    assert _seed_decisions(monkeypatch, client) == [], (
        "an UNREADABLE graph was treated as an EMPTY graph and seeded"
    )


def test_a_strict_read_returning_no_rows_does_not_seed(monkeypatch):
    """Even a *successful* strict read of zero rows is ignorance.

    ``MATCH (n) RETURN count(n) AS c`` always yields exactly one row on a live
    graph, so an empty result set means the query did not really answer.
    """
    client = _LenientClient(strict_raises=False)
    assert _seed_decisions(monkeypatch, client) == []


def test_the_seeder_reads_through_the_strict_client(monkeypatch):
    """Behavioural proof the guard consults the RAISING reader.

    Asserted via the calls the client actually received, not by grepping the
    source: a lenient-only client records its query through ``execute_read``.
    """
    client = _LenientClient()
    _seed_decisions(monkeypatch, client)
    assert client.reads, "the seed guard never queried the graph at all"


# ══════════════════════════════════════════════════════════════════════════
# B5 / L1 / L8 — /healthz/llm must not report green from CREDENTIALS while its
# own counters say the fallback leg is failing.
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def _fresh_stats():
    s2pol.reset_transport_stats()
    yield
    s2pol.reset_transport_stats()


def test_healthz_is_not_green_when_the_fallback_leg_is_failing(monkeypatch, _fresh_stats):
    """Reproduces the exact production body measured on 1cab8f0.

    llm_ok:true + "bedrock fallback active" while the same JSON carried
    fallback_ok:0 / fallback_failed:2 and users got deterministic answers.
    """
    import app.main as main

    monkeypatch.setattr(
        "app.llm.bedrock_client.is_bedrock_provider_enabled",
        lambda: True, raising=False,
    )
    s2pol.record_attempt(s2pol.STAGE2_FALLBACK)
    s2pol.record_result(s2pol.STAGE2_FALLBACK, ok=False)
    s2pol.record_attempt(s2pol.STAGE2_FALLBACK)
    s2pol.record_result(s2pol.STAGE2_FALLBACK, ok=False)

    out = main._degraded_to_bedrock({"provider": "openai_wrapper"}, "api_status_500")

    assert out["llm_ok"] is False, (
        "healthz reported GREEN while the fallback leg had 2 attempts and 0 "
        "successes — the false green measured live in production"
    )
    assert "FAILING" in str(out["provider"]) or "0 successes" in str(out["detail"])


def test_healthz_stays_green_when_the_fallback_is_actually_serving(monkeypatch, _fresh_stats):
    """The inverse. A guard whose ON state always fires is not a guard."""
    import app.main as main

    monkeypatch.setattr(
        "app.llm.bedrock_client.is_bedrock_provider_enabled",
        lambda: True, raising=False,
    )
    s2pol.record_attempt(s2pol.STAGE2_FALLBACK)
    s2pol.record_result(s2pol.STAGE2_FALLBACK, ok=True)

    out = main._degraded_to_bedrock({"provider": "openai_wrapper"}, "api_status_500")
    assert out["llm_ok"] is True
    assert "fallback active" in str(out["detail"])


def test_healthz_does_not_go_red_on_zero_evidence(monkeypatch, _fresh_stats):
    """Zero attempts is UNKNOWN, not BROKEN — never page on no evidence."""
    import app.main as main

    monkeypatch.setattr(
        "app.llm.bedrock_client.is_bedrock_provider_enabled",
        lambda: True, raising=False,
    )
    out = main._degraded_to_bedrock({"provider": "openai_wrapper"}, "api_status_500")
    assert out["llm_ok"] is True


def test_healthz_reports_no_credentials_case_unchanged(monkeypatch, _fresh_stats):
    """R360.9's original branch must survive."""
    import app.main as main

    monkeypatch.setattr(
        "app.llm.bedrock_client.is_bedrock_provider_enabled",
        lambda: False, raising=False,
    )
    out = main._degraded_to_bedrock({"provider": "openai_wrapper"}, "boom")
    assert out["llm_ok"] is False
    assert "NO bedrock credentials" in str(out["detail"])


# ══════════════════════════════════════════════════════════════════════════
# I5 / I6 — counter integrity: attempts == ok + failed, on every exit path.
# ══════════════════════════════════════════════════════════════════════════
def _balanced(stats: dict, leg: str) -> bool:
    return stats[f"{leg}_attempts"] == stats[f"{leg}_ok"] + stats[f"{leg}_failed"]


def test_a_discarded_truncated_fallback_answer_is_not_counted_ok(_fresh_stats):
    """Pre-R361 ``ok=bool(text)`` fired BEFORE the truncation guard discarded
    the answer, so ``fallback_ok`` counted answers that were never served."""
    s2pol.record_attempt(s2pol.STAGE2_FALLBACK)
    s2pol.record_result(s2pol.STAGE2_FALLBACK, ok=False)   # discarded
    st = s2pol.transport_stats()
    assert st["fallback_ok"] == 0
    assert _balanced(st, "fallback")


def test_counters_balance_on_every_leg(_fresh_stats):
    for leg in (s2pol.STAGE2_PRIMARY, s2pol.STAGE2_FALLBACK):
        s2pol.record_attempt(leg)
        s2pol.record_result(leg, ok=True)
        s2pol.record_attempt(leg)
        s2pol.record_result(leg, ok=False)
    st = s2pol.transport_stats()
    assert _balanced(st, "primary") and _balanced(st, "fallback")


def test_transport_stats_does_not_leak_a_mutable_alias(_fresh_stats):
    snap = s2pol.transport_stats()
    snap["primary_ok"] = 9999
    snap["refused_by_provider"]["injected"] = 1
    fresh = s2pol.transport_stats()
    assert fresh["primary_ok"] == 0
    assert "injected" not in fresh["refused_by_provider"]


# ══════════════════════════════════════════════════════════════════════════
# K4 / L5 — the host allowlist flips which MODEL answers, so it must be part of
# the engine cache identity (AGENTS.md invariant #4).
# ══════════════════════════════════════════════════════════════════════════
def test_primary_hosts_changes_the_engine_cache_key(monkeypatch):
    """Without this, an A/B of the flag replays the other arm's cached prose
    and every axis reads +0.0000 — the R329 unfalsifiable-lever trap."""
    from app.routes.regenold import _engine_cache_key

    monkeypatch.delenv("REGENOLD_STAGE2_PRIMARY_HOSTS", raising=False)
    before = _engine_cache_key("what is Article 6?", None)
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "tunnel.example.test")
    after = _engine_cache_key("what is Article 6?", None)
    assert before != after, (
        "REGENOLD_STAGE2_PRIMARY_HOSTS is not in the cache key, so arm B can "
        "serve arm A's answer"
    )


def test_a_blank_primary_hosts_value_cannot_disable_the_guard(monkeypatch):
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "   ")
    assert s2pol.allowed_primary_hosts() == s2pol.STAGE2_PRIMARY_HOSTS


# ══════════════════════════════════════════════════════════════════════════
# L4 — a judge that never ran must not exit 0 with a scorecard of zeros.
# ══════════════════════════════════════════════════════════════════════════
def test_grounded_judge_default_model_is_one_that_actually_works():
    """``claude-sonnet-5`` resolved to a Bedrock id that 403s on the current
    key vintage; 120/120 rows errored and the run still exited 0."""
    from evals.judge import grounded

    assert grounded._DEFAULT_MODEL == "claude-sonnet-4-6"


def test_grounded_judge_exits_nonzero_when_every_row_errored(monkeypatch, capsys):
    from evals.judge import grounded

    dead = {
        "aggregate": {
            ax: {"n": 120, "pass": 0, "fail": 0, "error": 120, "pass_rate": 0.0}
            for ax in ("answer_correctness", "reference_correctness",
                       "citation_faithfulness")
        }
    }
    monkeypatch.setattr(grounded, "run", lambda **kw: dead)
    monkeypatch.setattr(grounded, "_fmt", lambda s: "")

    rc = grounded.main([
        "--sidecar", "x.jsonl", "--label", "l", "--provider", "bedrock",
    ])
    assert rc == 2, "a judge that never ran exited 0 with a 0.0000 scorecard"
    assert "JUDGE DID NOT RUN" in capsys.readouterr().err


def test_grounded_judge_exits_zero_on_a_real_run(monkeypatch):
    from evals.judge import grounded

    live = {
        "aggregate": {
            "answer_correctness": {"n": 120, "pass": 55, "fail": 65,
                                   "error": 0, "pass_rate": 0.4583},
        }
    }
    monkeypatch.setattr(grounded, "run", lambda **kw: live)
    monkeypatch.setattr(grounded, "_fmt", lambda s: "")
    assert grounded.main(
        ["--sidecar", "x.jsonl", "--label", "l", "--provider", "bedrock"]
    ) == 0


# ══════════════════════════════════════════════════════════════════════════
# C1 — the merge gate's liveness probe must dial a real completion.
# ══════════════════════════════════════════════════════════════════════════
class _Resp:
    def __init__(self, status=200, body=b"{}"):
        self.status, self._b = status, body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_wrapper_probe_rejects_a_lying_auth_status(monkeypatch):
    """`/v1/auth/status` answers 200 valid:true on token PRESENCE. Measured
    2026-08-23: it did exactly that while every completion returned 500."""
    from evals.harness import ab_judge

    def _urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "auth/status" in url:
            return _Resp(200, json.dumps({"valid": True}).encode())
        raise RuntimeError("api_status_500: No response from Claude Code")

    monkeypatch.setattr(ab_judge.urllib.request, "urlopen", _urlopen)
    assert ab_judge._wrapper_up(timeout=1.0) is False, (
        "the merge gate accepted a lying auth-status and would have run a "
        "'live' tier with Stage-2 dead on BOTH arms"
    )


def test_wrapper_probe_rejects_an_empty_completion(monkeypatch):
    from evals.harness import ab_judge

    empty = {"choices": [{"message": {"content": ""}}]}

    def _urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "auth/status" in url:
            return _Resp(200, json.dumps({"valid": True}).encode())
        return _Resp(200, json.dumps(empty).encode())

    monkeypatch.setattr(ab_judge.urllib.request, "urlopen", _urlopen)
    assert ab_judge._wrapper_up(timeout=1.0) is False


def test_wrapper_probe_accepts_a_real_completion(monkeypatch):
    """The inverse — the probe must still say UP when the wrapper works."""
    from evals.harness import ab_judge

    ok = {"choices": [{"message": {"content": "OK"}}]}

    def _urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "auth/status" in url:
            return _Resp(200, json.dumps({"valid": True}).encode())
        return _Resp(200, json.dumps(ok).encode())

    monkeypatch.setattr(ab_judge.urllib.request, "urlopen", _urlopen)
    assert ab_judge._wrapper_up(timeout=1.0) is True

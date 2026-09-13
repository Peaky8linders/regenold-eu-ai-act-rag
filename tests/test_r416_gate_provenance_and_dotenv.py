"""R416 — two defects in the paired-gate instrument, both found on the hard split.

DEFECT 1 — ``ArmProbe`` stripped the Cloudflare Access service token.

``_OpenAIWrapperProvider`` resolves its CF Access service-token headers ONCE, at
construction, and caches them for the life of the process. ``app.config`` is what
puts ``.env`` into ``os.environ``, and it does so lazily on first import.
``gate_validity._PayloadRecorder.install()`` imported the provider modules FIRST,
so the singleton was constructed against an environment with no
``CF_ACCESS_CLIENT_ID``/``SECRET`` and no ``OPENAI_API_BASE`` — and every
subsequent primary call was refused by Cloudflare Access with an HTTP 401.

MEASURED (hard split, 37 rows x 2 arms): 74/74 Stage-2 calls fell back, with
``primary_attempts=37, primary_ok=0, fallback_ok=37`` on BOTH arms and no
``cloudflare_access_service_token_active`` line anywhere in the gate's log, while
a direct call in the same environment minutes apart was served 10/10 by the
primary. That is the R412 near-miss class — a VOID run that reads as a plausible
null — self-inflicted by the module that exists to detect it.

DEFECT 2 — the arm checkpoint recorded no per-row transport provenance.

The only provenance was an arm-level total, so a single fallback row voided the
whole run and there was no way to show WHICH rows the other transport carried.
The R415 lesson one layer down: a gate that cannot say which rows were served by
the other leg can only void, never repair.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# ── DEFECT 1 ────────────────────────────────────────────────────────────────


def test_armprobe_loads_app_config_before_constructing_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Providers must be constructed AFTER ``.env`` has been loaded.

    R416: constructing them first permanently strips the CF Access service-token
    headers for the whole process, and the entire paired run is then served by
    the fallback leg while still printing a clean delta table.
    """
    import app.llm.openai_wrapper_provider as owp
    from evals.harness import gate_validity

    monkeypatch.setattr(owp, "_SINGLETON", None, raising=False)
    constructed_after_config: list[bool] = []
    real_init = owp._OpenAIWrapperProvider.__init__

    def spy(self: Any, *args: Any, **kwargs: Any) -> None:
        constructed_after_config.append("app.config" in sys.modules)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(owp._OpenAIWrapperProvider, "__init__", spy)
    # Start from a state where app.config has NOT been imported in this process
    # slice, so this asserts ORDERING and not the suite's import history.
    monkeypatch.delitem(sys.modules, "app.config", raising=False)

    with gate_validity.ArmProbe("baseline"):
        pass

    assert constructed_after_config, "no provider was constructed — the probe observes nothing"
    assert all(constructed_after_config), (
        "a provider was constructed BEFORE app.config loaded .env; its Cloudflare "
        "Access service-token headers resolve once at construction, so every "
        "primary call 401s and the whole arm is served by the fallback (R416)"
    )


def test_armprobe_provider_carries_the_service_token_when_env_sets_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh singleton built under a CF-token environment must carry the headers."""
    import app.llm.openai_wrapper_provider as owp
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider
    from evals.harness import gate_validity

    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    monkeypatch.setenv("OPENAI_API_BASE", owp._DEFAULT_WRAPPER_BASE)
    monkeypatch.setattr(owp, "_SINGLETON", None, raising=False)

    with gate_validity.ArmProbe("baseline"):
        pass

    headers = get_openai_wrapper_provider()._cf_access_headers
    assert headers.get("CF-Access-Client-Id") == "cf-id"
    assert headers.get("CF-Access-Client-Secret") == "cf-secret"


# ── DEFECT 2 ────────────────────────────────────────────────────────────────


def test_row_transport_derives_per_row_fallback_provenance() -> None:
    from evals.harness.easyhard_ab import _row_transport

    before = {"primary_attempts": 4, "primary_ok": 3, "fallback_attempts": 1, "fallback_ok": 1}
    after = {"primary_attempts": 5, "primary_ok": 3, "fallback_attempts": 2, "fallback_ok": 2}
    rec = _row_transport(before, after)
    assert rec["stage2_primary_attempts"] == 1
    assert rec["stage2_primary_ok"] == 0
    assert rec["stage2_fallback_attempts"] == 1
    assert rec["stage2_fallback_ok"] == 1
    assert rec["stage2_used"] is True
    assert rec["stage2_fell_back"] is True

    clean = _row_transport(
        {"primary_attempts": 0, "primary_ok": 0, "fallback_attempts": 0, "fallback_ok": 0},
        {"primary_attempts": 1, "primary_ok": 1, "fallback_attempts": 0, "fallback_ok": 0},
    )
    assert clean["stage2_used"] is True
    assert clean["stage2_fell_back"] is False


def test_row_transport_omits_provenance_when_counters_are_unobservable() -> None:
    """R418 — an unobservable transport must report NO provenance, not zeroes.

    This test previously asserted the opposite (``stage2_used is False``,
    ``stage2_fell_back is False``), which is the defect the review found: those
    zeroes are arithmetic on no evidence, and because the KEYS were present,
    ``_fallback_served``'s missing-key conservatism could not fire — so a row
    whose transport was never observed was recorded as tunnel-served. A false
    green on the one guard whose whole job is to prevent false greens.

    The corrected contract is stricter, never looser: no observation ⇒ no
    provenance ⇒ the row counts as possibly-fallback and is dropped from the
    paired comparison.
    """
    from evals.harness.easyhard_ab import _fallback_served, _row_transport

    rec = _row_transport({}, {})
    assert rec == {}, "no observation must not be reported as zero deltas"
    assert _fallback_served({"id": "r1", **rec}) is True, (
        "a row with no provenance must not be counted as tunnel-served"
    )
    # A half-observable pair is unobservable too: a missing 'before' snapshot
    # would otherwise turn the arm switch itself into a positive delta.
    assert _row_transport({}, {"primary_ok": 2}) == {}
    # A non-int stat (``refused_by_provider`` is a map) must not raise.
    assert _row_transport({"primary_ok": "x"}, {"primary_ok": 2})["stage2_primary_ok"] == 0


def test_exclude_fallback_rows_drops_the_same_ids_from_both_arms() -> None:
    """Symmetry is the point: one arm's mean must not keep a row the other lost."""
    from evals.harness.easyhard_ab import _exclude_fallback_rows

    a = [
        {"id": "r1", "stage2_fell_back": False},
        {"id": "r2", "stage2_fell_back": True},   # arm A fell back
        {"id": "r3", "stage2_fell_back": False},
    ]
    b = [
        {"id": "r1", "stage2_fell_back": False},
        {"id": "r2", "stage2_fell_back": False},
        {"id": "r3", "stage2_fell_back": True},  # arm B fell back
    ]
    a2, b2, dropped = _exclude_fallback_rows(a, b)
    assert dropped == ["r2", "r3"]
    assert [r["id"] for r in a2] == ["r1"]
    assert [r["id"] for r in b2] == ["r1"]


def test_missing_provenance_counts_as_fallback_served() -> None:
    """A row that cannot be SHOWN to be tunnel-served must not be counted as one."""
    from evals.harness.easyhard_ab import _fallback_served

    assert _fallback_served({"id": "old-ckpt-row"}) is True
    assert _fallback_served({"id": "x", "stage2_fell_back": False}) is False


def test_assess_suppresses_the_fallback_reason_only_on_request() -> None:
    """``ignore_fallback_leg`` is the caller's contract, not a default."""
    from evals.harness import gate_validity

    def prov(label: str) -> gate_validity.ArmProvenance:
        return gate_validity.ArmProvenance(
            label=label,
            rows=37,
            stats={"primary_attempts": 37, "primary_ok": 36, "fallback_ok": 1},
        )

    strict = gate_validity.assess(base=prov("baseline"), branch=prov("branch"), lever=False)
    assert not strict.valid
    assert any("FALLBACK transport" in r for r in strict.reasons)

    rescued = gate_validity.assess(
        base=prov("baseline"), branch=prov("branch"), lever=False, ignore_fallback_leg=True
    )
    assert rescued.valid
    assert not any("FALLBACK transport" in r for r in rescued.reasons)


def test_run_arm_writes_transport_provenance_into_every_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every arm row carries which leg served it — the thing that was missing."""
    from app.llm import stage2_policy
    from evals.harness import easyhard_ab as m
    from evals.harness.probe_set import load_probe_set
    from evals.regenold import runner_v2

    rows = load_probe_set(multiturn=True)[:1]
    assert rows, "the hard split must not be empty"

    def fake_post_local(url: str, api_key: Any, history: Any, timeout: float) -> tuple:
        return (
            {"answer": "Article 6 applies. References: Article 6.", "references": ["Article 6"]},
            1200.0,
            200,
            None,
            1,
            [],
        )

    monkeypatch.setattr(runner_v2, "_post_local", fake_post_local)

    # The first snapshot is the pre-row baseline; the second shows the row's
    # primary dial and the third the fallback dial that followed it.
    snapshots = iter(
        [
            {"primary_attempts": 0, "primary_ok": 0, "fallback_attempts": 0, "fallback_ok": 0},
            {"primary_attempts": 1, "primary_ok": 0, "fallback_attempts": 1, "fallback_ok": 1},
            {"primary_attempts": 1, "primary_ok": 0, "fallback_attempts": 1, "fallback_ok": 1},
        ]
    )
    monkeypatch.setattr(stage2_policy, "transport_stats", lambda: next(snapshots))

    out = m._run_arm(
        rows,
        endpoint=None,
        api_key=None,
        local=True,
        timeout=180.0,
        arm_env={"REGENOLD_KG_POINT_TEXT": "0"},
        ckpt_path=tmp_path / "arm.jsonl",
    )

    assert len(out) == 1
    rec = out[0]
    assert rec["stage2_primary_attempts"] == 1
    assert rec["stage2_fallback_ok"] == 1
    assert rec["stage2_used"] is True
    assert rec["stage2_fell_back"] is True

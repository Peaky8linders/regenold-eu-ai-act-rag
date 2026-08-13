"""R329 — the HyPA adaptive parameters must reach real consumers.

When the router landed, four of its five parameters (``query_rewrites``,
``kg_max_keywords``, ``kg_depth``, ``kg_max_units``) had zero production
consumers — only ``top_k_dense`` was read — so the paper's distinguishing claim
(arXiv:2409.09046v2 §7: the classifier tunes knowledge-graph and rewriter
parameters, not just top-k) was decorative.

These tests pin the three properties that make the wiring correct:

1. router OFF is byte-identical to the historical static defaults;
2. router ON actually moves each knob, monotonically with complexity;
3. an explicit env override still beats adaptation — required by
   ``evals/harness/ab_judge.py``, which flips env between arms in the SAME
   process and would otherwise silently measure the adaptive value.
"""
from __future__ import annotations

import pytest

from app.engines import graph_semantic as GS
from app.engines import kg_context as K
from app.engines import query_complexity_router as R
from app.engines.sufficient_context import max_sub_queries

_TUNED_ENV = (
    "REGENOLD_KG_MAX_UNITS",
    "REGENOLD_KG_MAX_REFS",
    "REGENOLD_SEMANTIC_ANN_FANOUT",
    "REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in _TUNED_ENV:
        monkeypatch.delenv(name, raising=False)
    token = R.set_active_parameters(None)
    yield monkeypatch
    R.reset_active_parameters(token)


def _knobs() -> tuple[int, int, int, int]:
    return (
        K._adaptive_int("kg_max_units", "REGENOLD_KG_MAX_UNITS", 24, 1, 100),
        K._adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", 8, 1, 20),
        GS._adaptive_fanout(),
        max_sub_queries(),
    )


def test_router_off_preserves_static_defaults(clean_env):
    """The default path must not move — this is what arm A/C parity rests on."""
    clean_env.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "0")
    R.set_active_parameters(R.CLASS_2_PARAMS)  # even with params bound
    assert _knobs() == (24, 8, 60, 3)


def test_router_on_moves_every_knob(clean_env):
    clean_env.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "1")

    R.set_active_parameters(R.CLASS_0_PARAMS)
    simple = _knobs()
    R.set_active_parameters(R.CLASS_1_PARAMS)
    standard = _knobs()
    R.set_active_parameters(R.CLASS_2_PARAMS)
    complex_ = _knobs()

    assert simple == (12, 3, 30, 2)
    # Class 1 pins fanout and hops to the production defaults, so standard-tier
    # traffic is unchanged by the wiring existing at all.
    assert standard == (18, 4, 60, 3)
    assert complex_ == (24, 5, 90, 5)

    # Monotonic in complexity on every axis — no knob may invert.
    for a, b, c in zip(simple, standard, complex_):
        assert a <= b <= c, (a, b, c)


def test_explicit_env_beats_adaptation(clean_env):
    """ab_judge flips env between arms in-process; env must win or arms alias."""
    clean_env.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "1")
    R.set_active_parameters(R.CLASS_2_PARAMS)  # would give 24 / 5 / 90 / 5

    clean_env.setenv("REGENOLD_KG_MAX_UNITS", "5")
    clean_env.setenv("REGENOLD_KG_MAX_REFS", "2")
    clean_env.setenv("REGENOLD_SEMANTIC_ANN_FANOUT", "17")
    clean_env.setenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", "1")

    assert _knobs() == (5, 2, 17, 1)


def test_no_binding_falls_back_to_defaults(clean_env):
    """A request whose classification failed must not inherit a stale class."""
    clean_env.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "1")
    R.set_active_parameters(None)
    assert _knobs() == (24, 8, 60, 3)


def test_adaptive_int_clamps_and_survives_garbage_env(clean_env):
    clean_env.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "1")
    R.set_active_parameters(R.CLASS_2_PARAMS)
    clean_env.setenv("REGENOLD_KG_MAX_UNITS", "not-a-number")
    assert K._adaptive_int("kg_max_units", "REGENOLD_KG_MAX_UNITS", 24, 1, 100) == 24
    # adaptive value is clamped into the caller's range
    assert R.adaptive_int("kg_max_units", "__unset__", 24, 1, 10) == 10

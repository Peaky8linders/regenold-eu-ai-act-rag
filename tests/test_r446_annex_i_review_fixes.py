"""R446 — fixes for the review of PRs #461/#462 (Annex I resolver, run lock).

Every property is pinned on the thing that ships — the route's answer and
references, a call count at the call site, or a measured timing — never on the
shape of the code. Findings:

* F1 — the R445 prose rewrite turned correct answer text into wrong law. It is
  now behind ``REGENOLD_ANNEX_I_PROSE_REPAIR`` (default OFF, allow-list).
* F2 — an Act the ANSWER names beside the point proves the point; the
  question-overlap ``best >= 2`` rule coarsened ``rg_072``'s ``Annex I.2``.
* F3 — the wire pass shipped duplicates (``Annex I`` x3).
* F4 — the wire pass ran on the deterministic path too (11 of the official 110
  changed offline). Now ``_stage2_landed``-gated plus
  ``REGENOLD_ANNEX_I_RESOLUTION`` (default ON, deny-list).
* F6 — cubic backtracking: "Annex I" + 2000 spaces took 115 s per pass.
* F7 — the strict axis double-counted a key after canonicalising.
* F10 / F11 — the run lock and the preflight memo (eval harness).
"""
from __future__ import annotations

import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.rate_limit import limiter
from app.routes import regenold as R
from evals.official.rubric import reference_correctness_strict

_KEY = "r446-annex-i-test-key"
_MDR_Q = (
    "Are AI safety components within medical devices of MDR class IIa, IIb, "
    "or III considered to be high-risk according to the EU AI Act? Why?"
)  # rg_008
_TOY_Q = (
    "Under the EU AI Act, can an AI system intended to be used as a toy qualify "
    "as a high-risk AI system, and if so under what conditions?"
)  # rg_072
_LIFT_Q = (
    "Under the EU AI Act, can an AI system intended to be used as a safety "
    "component in a lift qualify as a high-risk AI system, and under what "
    "conditions?"
)  # rg_073
_VEHICLE_Q = (
    "Are AI safety components in motor vehicles covered by Regulation (EU) "
    "2019/2144 high-risk under the EU AI Act?"
)
_OFFLINE_Q = (
    "We developed a product listed in Annex I where an AI system is a safety "
    "component. We had the option to opt out of the third-party conformity "
    "assessment base case by using harmonized standards. Thus no third-party "
    "conformity assessment happened. This means we can skip the requirements of "
    "Chapter 3 Section 2 of the AI Act, right?"
)  # rg_109 — offline, the pre-R446 route coarsened its `Annex I.20`

#: The five F1 reproductions: (question, the sentence the rewrite corrupted).
_F1_CASES = [
    (_MDR_Q, "Motor vehicles are listed at Annex I point 19, whereas the MDR is point 11."),
    (
        _MDR_Q,
        "Devices under the MDR are listed in Annex I; a safety component is "
        "defined in point (14) of Article 3.",
    ),
    (_MDR_Q, "Regulation (EU) 2017/745 is listed in Annex I, item 19 of which is a different Act."),
    (_MDR_Q, "Devices under the MDR are listed in Annex I. 12 notified bodies assess them."),
    (_VEHICLE_Q, "Motor vehicles fall under Annex I, Section B, point 7."),
]
_LEAD = (
    "Yes, under Article 6(1) such a safety component is high-risk where the "
    "device needs third-party conformity assessment. "
)


def _route_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
    monkeypatch.delenv("REGENOLD_ANNEX_I_PROSE_REPAIR", raising=False)
    monkeypatch.delenv("REGENOLD_ANNEX_I_RESOLUTION", raising=False)
    monkeypatch.setattr(settings.regenold, "api_key", SecretStr(_KEY))
    limiter.reset()


def _ask(
    monkeypatch: pytest.MonkeyPatch,
    *,
    question: str,
    answer: str | None,
    seed: list[str] | None = None,
) -> tuple[dict, dict[str, int]]:
    """POST through the real route and count the two Annex I passes.

    ``answer=None`` leaves the engine offline (no Stage-2 lands); otherwise the
    Stage-2 transport returns ``answer`` verbatim, as tests/test_r445 does.
    ``seed`` replaces any ``Annex I.N`` leaf the deepener minted, so the wire
    pass has a leaf to act on.
    """
    R._ENGINE_CACHE.clear()
    calls = {"prose": 0, "wire": 0}
    real_prose, real_wire = R._repair_annex_i_prose_points, R._repair_annex_i_wire_points
    original_deepen = R._deepen_ref_grain

    def prose_spy(*args, **kwargs):
        calls["prose"] += 1
        return real_prose(*args, **kwargs)

    def wire_spy(*args, **kwargs):
        calls["wire"] += 1
        return real_wire(*args, **kwargs)

    def seed_leaf(refs, q, prose, exempt_heads=None):
        deepened = original_deepen(refs, q, prose, exempt_heads=exempt_heads)
        if seed is None:
            return deepened
        return [r for r in deepened if not str(r).lower().startswith("annex i.")] + seed

    with ExitStack() as stack:
        if answer is not None:
            stack.enter_context(
                patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True)
            )
            stack.enter_context(
                patch(
                    "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                    side_effect=lambda *args, **kwargs: answer,
                )
            )
        stack.enter_context(patch.object(R, "_repair_annex_i_prose_points", side_effect=prose_spy))
        stack.enter_context(patch.object(R, "_repair_annex_i_wire_points", side_effect=wire_spy))
        stack.enter_context(patch.object(R, "_deepen_ref_grain", side_effect=seed_leaf))
        with TestClient(app, headers={"X-Regenold-Api-Key": _KEY}) as client:
            response = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json=[{"role": "user", "content": question}],
            )
    assert response.status_code == 200, response.text
    return response.json(), calls


# -- F1: the prose rewrite is OFF by default ----------------------------------


@pytest.mark.parametrize(
    ("value", "enabled"),
    [(None, False), ("0", False), ("", False), ("enabled", False), ("1", True), ("true", True), ("on", True)],
)
def test_prose_repair_flag_is_default_off_allow_list(monkeypatch, value, enabled) -> None:
    if value is None:
        monkeypatch.delenv("REGENOLD_ANNEX_I_PROSE_REPAIR", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_ANNEX_I_PROSE_REPAIR", value)
    assert R._annex_i_prose_repair_enabled() is enabled


@pytest.mark.parametrize(("question", "sentence"), _F1_CASES)
def test_default_off_ships_the_answer_text_byte_identical(monkeypatch, question, sentence) -> None:
    """Each sentence below was rewritten into wrong law by the R445 route."""
    _route_env(monkeypatch)
    body, calls = _ask(monkeypatch, question=question, answer=_LEAD + sentence, seed=["Annex I.11"])
    assert sentence in str(body.get("answer") or ""), body.get("answer")
    assert calls["prose"] == 0
    assert calls["wire"] >= 1  # non-vacuous: Stage-2 landed and the wire pass ran


def test_prose_repair_runs_only_when_switched_on(monkeypatch) -> None:
    """Two-sided: the flag is what keeps the rewrite off the answer."""
    _route_env(monkeypatch)
    monkeypatch.setenv("REGENOLD_ANNEX_I_PROSE_REPAIR", "1")
    _body, calls = _ask(
        monkeypatch, question=_MDR_Q, answer=_LEAD + _F1_CASES[0][1], seed=["Annex I.11"]
    )
    assert calls["prose"] == 1


def test_a_period_after_the_annex_is_not_a_point_marker() -> None:
    answer = "Devices under the MDR are listed in Annex I. 12 notified bodies assess them."
    assert R._repair_annex_i_prose_points(answer, _MDR_Q) == answer


# -- F2: an Act the answer names proves its single point ----------------------


def test_answer_named_act_keeps_its_single_point_rg_072() -> None:
    """R419 hard board, rg_072: gold `Annex I.a.2`; the pass cut the leaf."""
    answer = (
        "Yes. Under Article 6(1), an AI system intended to be used as a toy can be a "
        "high-risk AI system. This is the Annex I product route, because Directive "
        "2009/48/EC on the safety of toys is listed in Annex I, point 2."
    )
    wire = R._repair_annex_i_wire_points(["Article 6.1", "Annex I.2"], _TOY_Q, answer)
    assert wire == ["Article 6.1", "Annex I.2"]
    assert reference_correctness_strict(wire, ["Article 6.1", "Annex I.a.2"]) == 1.0
    assert R._deepen_one_ref("Annex I", _TOY_Q, answer) == "Annex I.2"
    # The same Act named in an Annex I sentence with no point still keeps it.
    no_point = "Toys are covered by Directive 2009/48/EC, which is listed in Annex I."
    assert R._repair_annex_i_wire_points(["Annex I.2"], _TOY_Q, no_point) == ["Annex I.2"]


@pytest.mark.parametrize(
    ("question", "answer", "wire"),
    [
        # two Acts beside the point
        (
            _MDR_Q,
            "Annex I includes Regulation (EU) 2017/745 and Regulation (EU) 2019/2144 at point 19.",
            ["Annex I.19"],
        ),
        # no Act, and nothing in the question singles a point out
        (
            "Is an AI triage module inside a class IIb device high-risk under the AI Act?",
            "Such devices are covered by Annex I point 11.",
            ["Annex I.11"],
        ),
        # an Act that is not on the adopted list
        (_MDR_Q, "Annex I includes Regulation (EU) 2099/1234 at point 19.", ["Annex I.19"]),
        # an Act named only in CONTRAST: must not move a lift question to point 11
        (_LIFT_Q, "Lifts are in Annex I point 4, not under the MDR.", ["Annex I.4"]),
    ],
)
def test_ambiguous_evidence_still_abstains_to_the_head(question, answer, wire) -> None:
    assert R._repair_annex_i_wire_points(list(wire), question, answer) == ["Annex I"]


# -- F3: no duplicates on the wire ----------------------------------------------


@pytest.mark.parametrize(
    ("question", "answer", "wire"),
    [
        (
            _MDR_Q,
            "Motor vehicles are listed at Annex I point 19, whereas the MDR is point 11.",
            ["Article 6.1", "Annex I.11", "Annex I.19"],
        ),
        (
            _MDR_Q,
            "The MDR (Annex I point 11) and the IVDR (Annex I point 12) are both listed.",
            ["Article 6.1", "Annex I", "Annex I.11", "Annex I.12"],
        ),
    ],
)
def test_wire_pass_never_emits_a_duplicate(question, answer, wire) -> None:
    out = R._repair_annex_i_wire_points(list(wire), question, answer)
    assert len(out) == len(set(out)), out
    assert out[0] == "Article 6.1"


def test_route_ships_no_duplicate_annex_i_reference(monkeypatch) -> None:
    """The p10 reproduction: `['Article 6.1', 'Annex I', 'Annex I', 'Annex I']`."""
    _route_env(monkeypatch)
    answer = _LEAD + "The MDR (Annex I point 11) and the IVDR (Annex I point 12) are both listed."
    body, calls = _ask(monkeypatch, question=_MDR_Q, answer=answer, seed=["Annex I.11", "Annex I.12"])
    refs = [str(r) for r in body.get("references") or []]
    assert calls["wire"] >= 1
    assert len(refs) == len(set(refs)), refs


# -- F4: gated on Stage-2 landing, plus a deny-list flag -------------------------


@pytest.mark.parametrize(
    ("value", "enabled"),
    [(None, True), ("1", True), ("", True), ("garbage", True), ("0", False), ("off", False), ("false", False)],
)
def test_resolution_flag_is_default_on_deny_list(monkeypatch, value, enabled) -> None:
    if value is None:
        monkeypatch.delenv("REGENOLD_ANNEX_I_RESOLUTION", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_ANNEX_I_RESOLUTION", value)
    assert R._annex_i_resolution_enabled() is enabled


def test_offline_path_never_calls_the_annex_i_passes(monkeypatch) -> None:
    """No Stage-2 landed: the deterministic wire is the pre-R445 wire."""
    _route_env(monkeypatch)
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    body, calls = _ask(monkeypatch, question=_OFFLINE_Q, answer=None, seed=["Annex I.20"])
    assert body.get("answer") and body.get("references")  # non-vacuous
    assert calls == {"prose": 0, "wire": 0}
    assert "Annex I.20" in [str(r) for r in body["references"]]


def test_resolution_flag_off_ships_the_leaf_unchanged(monkeypatch) -> None:
    _route_env(monkeypatch)
    answer = _LEAD + "Annex I lists Regulation (EU) 2017/745 (MDR) at point 19."
    on, on_calls = _ask(monkeypatch, question=_MDR_Q, answer=answer, seed=["Annex I.19"])
    monkeypatch.setenv("REGENOLD_ANNEX_I_RESOLUTION", "0")
    off, off_calls = _ask(monkeypatch, question=_MDR_Q, answer=answer, seed=["Annex I.19"])
    assert on_calls["wire"] == 1 and off_calls["wire"] == 0
    assert "Annex I.11" in on["references"] and "Annex I.19" not in on["references"]
    assert "Annex I.19" in off["references"]


@pytest.mark.parametrize("flag", ["REGENOLD_ANNEX_I_RESOLUTION", "REGENOLD_ANNEX_I_PROSE_REPAIR"])
def test_both_flags_are_in_the_cache_key(monkeypatch, flag) -> None:
    monkeypatch.setenv(flag, "0")
    off = R._engine_cache_key("q", None)
    monkeypatch.setenv(flag, "1")
    assert R._engine_cache_key("q", None) != off


# -- F6: bounded runs, no catastrophic backtracking -----------------------------


def test_long_whitespace_runs_stay_linear() -> None:
    """MEASURED before: "Annex I" + 1000 spaces 14.3 s, + 2000 spaces 115 s."""
    spaces = " " * 5000
    t0 = time.perf_counter()
    for answer in ("Annex I" + spaces + "x", "Annex I point 11," + spaces + "x"):
        R._repair_annex_i_prose_points(answer, _MDR_Q)
        R._repair_annex_i_wire_points(["Annex I.11"], _MDR_Q, answer)
        R._deepen_one_ref("Annex I", _MDR_Q, answer)
    R._prose_named_annex_point("III", "Annex III" + spaces + "x", {n: "" for n in range(1, 9)})
    R._question_names_annex_i_point("Annex I point" + spaces + "x", 11)
    assert time.perf_counter() - t0 < 0.5


def test_bounded_template_still_reads_the_live_shapes() -> None:
    units = {n: "" for n in range(1, 21)}
    assert R._prose_named_annex_point("IV", "see Annex IV point 1(e) for hardware", units) == 1
    assert R._prose_named_annex_point("III", "listed in Annex III (point 5) here", units) == 5
    assert R._prose_named_annex_point("III", "Annex III points 1, 6 and 7 apply", units) is None


# -- F7: the strict axis counts each canonical key once ------------------------


def test_strict_axis_dedupes_after_canonicalising() -> None:
    key = ["Annex I.a.11", "Annex I.11", "Article 6.1"]
    assert reference_correctness_strict(["Article 6.1"], key) == 0.5
    assert reference_correctness_strict(["Article 6.1", "Annex I.11"], key) == 1.0


# -- F10: run lock ------------------------------------------------------------------


@pytest.fixture
def run_lock_module():
    from evals.regenold import run_lock

    run_lock.release()
    yield run_lock
    run_lock.release()


def test_an_unopenable_lock_file_is_a_runtime_error(run_lock_module, tmp_path, monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(run_lock_module.os, "open", refuse)
    with pytest.raises(RuntimeError, match="cannot open the run lock"):
        run_lock_module.acquire(tmp_path, "ro")


def test_every_held_label_is_released(run_lock_module, tmp_path) -> None:
    x = run_lock_module.acquire(tmp_path, "x")
    y = run_lock_module.acquire(tmp_path, "y")
    run_lock_module.release(y)  # one label
    assert run_lock_module.acquire(tmp_path, "y") == y
    with pytest.raises(RuntimeError, match="already owned"):
        run_lock_module.acquire(tmp_path, "x")  # still held by this process
    run_lock_module.release()  # all labels
    assert run_lock_module.acquire(tmp_path, "x") == x
    assert run_lock_module.acquire(tmp_path, "y") == y


def test_owner_note_is_written_in_binary_mode(run_lock_module, tmp_path) -> None:
    lock = run_lock_module.acquire(tmp_path, "note")
    run_lock_module.release()
    raw = Path(lock).read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\r\n"), raw


# -- F11: preflight memo keyed on the wire id and the endpoint ------------------


@pytest.fixture
def preflight_guard(monkeypatch):
    from app.llm import openai_wrapper_provider as _wp
    from evals.regenold import run_official_batch as rob

    probes: list[tuple[str, str]] = []
    provider = MagicMock()

    def _complete(req):
        probes.append((_wp.resolve_wrapper_model(req.model), provider._base_url))
        return _wp.OpenAIWrapperResponse(text="alive", model=req.model)

    provider.complete = MagicMock(side_effect=_complete)
    provider._base_url = "http://127.0.0.1:9/v1"
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(
        _wp._OpenAIWrapperProvider, "complete", _wp._OpenAIWrapperProvider.complete
    )
    monkeypatch.setattr(_wp, "get_openai_wrapper_provider", lambda: provider)
    monkeypatch.setattr(_wp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "0")
    monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
    monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "claude-opus-5-5")
    preflight, _ = rob._install_stage2_transport_guard()
    return preflight, probes, provider


def test_an_arm_that_changes_only_the_wire_prefix_is_probed(preflight_guard, monkeypatch) -> None:
    preflight, probes, _provider = preflight_guard
    preflight()
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_PREFIX", "anthropic/")
    preflight()
    preflight()  # same wire id and endpoint: memo hit
    assert [wire for wire, _ in probes] == ["claude-opus-5-5", "anthropic/claude-opus-5-5"]


def test_an_arm_on_another_endpoint_is_probed(preflight_guard) -> None:
    preflight, probes, provider = preflight_guard
    preflight()
    provider._base_url = "http://127.0.0.1:10/v1"
    preflight()
    assert [url for _, url in probes] == ["http://127.0.0.1:9/v1", "http://127.0.0.1:10/v1"]

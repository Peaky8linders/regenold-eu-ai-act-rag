"""R424 — is every hard row asked inside the SAME conversation, and is it deep?

The claim under test is about WHAT GETS DISPATCHED, so it is measured at the
provider seam over the REAL request path (row -> request builder -> route ->
history flattening -> engine -> provider), not read off a flag. Per dispatch it
records the ``history_turn_count`` the route derives from the request
(``max(0, user+assistant messages - 1)``) and the system-prompt size the engine
actually chose — the OBSERVABLE consequence, because ``_graph_rag_impl``
substitutes the full ~59.6 kB system prompt when ``history_turn_count <= 1`` and
the 61-char persona otherwise.

The decisive pair varies **only a row's position**: the same row asked as the
first row of a run, then asked behind another. Measured live, in ``rolling`` mode:

    rg_004 first   -> history_turn_count  0 -> system 59 644 chars (FULL)
    rg_004 second  -> history_turn_count  2 -> system     61 chars (persona)

That is the leak: the SAME question is put to a different system prompt depending
on where it sits in the run, and the leading rows of every arm are the ones that
took the full prompt. In ``fixed`` mode both must read 18 (turn 1) and 20 (the
pushback) and the persona, wherever the row sits.

WHAT THE FIXTURE DOES AND DOES NOT DO — measured, not assumed
-------------------------------------------------------------
Recorded per dispatch is whether the fixture's text appears in the payload. In
this architecture it does NOT: the route flattens prior turns into a
``"Conversation so far: … Latest question: …"`` preamble and the engine STRIPS it
for the model-facing prompts (``_graph_rag_impl`` searches for the
``Latest question:`` marker to work on the live turn), using it instead for
classification, scope, anchors and the deterministic retrieval input. So the
official 9-turn dialogue changes what the ENGINE sees — a constant, deep
multi-turn request instead of a cold single-turn one — not what the model reads.
That is the honest scope of this lever and the reason the gate reports every axis
rather than a single headline.

Default runs OFFLINE with a stubbed provider (the dispatch shape is decided
BEFORE the provider is reached, so the stub is faithful for what is measured and
the check costs no quota). ``--live`` uses the real transport.

Run::

    .venv/Scripts/python.exe -m docs.measurements.r424.hard_preamble_probe
    .venv/Scripts/python.exe -m docs.measurements.r424.hard_preamble_probe --live
"""
from __future__ import annotations

import argparse
import json
import os

# The shipped defaults under test; assert them rather than a local override.
for _flag in (
    "REGENOLD_STAGE2_FULL_SYSTEM",
    "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN",
    "REGENOLD_HARD_PREAMBLE",
):
    os.environ.pop(_flag, None)

#: ``history_turn_count <= 1`` is the engine's single-turn predicate, and the full
#: system prompt is what crosses the wire differently because of it.
FULL_MIN_CHARS = 10_000
#: A phrase only the fixture's first user turn carries.
_FIXTURE_MARK = "compliance workstream"
#: Stage-2 answer markers — the same filter ``gate_validity`` uses to identify the
#: GRADED call among the route's several provider dispatches.
_STAGE2_MARKERS = ("EU AI ACT REFERENCES:", "ANSWER CONTRACT")
#: What the Stage-1 parser sends. Anything else is an auxiliary pass.
_PARSE_MARKERS = ("Question:", "JSON")

CALLS: list[dict[str, object]] = []
STATE: dict[str, object] = {"run": "?", "row": "?", "turn": "?", "msgs": 0}

from app.llm import openai_wrapper_provider as _OWP  # noqa: E402

_ORIG = _OWP._OpenAIWrapperProvider.complete

_PARSED_JSON = json.dumps(
    {
        "intent": "general_compliance",
        "entities": ["provider", "high-risk AI system"],
        "risk_context": "high_risk",
        "dimension_hint": "obligations",
        "keywords": ["technical documentation", "Annex IV"],
        "reasoning": "stub parse for the R424 shape probe",
    }
)
_ANSWER = (
    "Under Article 6 the system is high-risk. References: Article 6, Article 16."
)


def _spy(self, req):  # noqa: ANN001, ANN201 - transport seam
    user = str(getattr(req, "user", "") or "")
    is_stage2 = any(m in user for m in _STAGE2_MARKERS)
    CALLS.append(
        {
            "run": STATE["run"],
            "row": STATE["row"],
            "turn": STATE["turn"],
            "msgs": int(STATE["msgs"]),
            "system_chars": len(getattr(req, "system", "") or ""),
            "stage2": is_stage2,
            "parse": (not is_stage2) and any(m in user for m in _PARSE_MARKERS),
            "fixture": _FIXTURE_MARK in user,
            "conversation": "Conversation so far" in user,
            "anchors": "[Context anchors" in user,
        }
    )
    if _STUBBED[0] and not _LIVE_ORIG[0]:
        text = _ANSWER if is_stage2 else _PARSED_JSON
        return _OWP.OpenAIWrapperResponse(text=text, model="stub")
    return _ORIG(self, req)


_OWP._OpenAIWrapperProvider.complete = _spy
#: Flipped by ``main`` before any dispatch.
_STUBBED = [True]
_LIVE_ORIG = [False]

import evals.regenold.run_official_batch as _R  # noqa: E402
from evals.regenold.hard_preamble import MODE_FIXED, MODE_ROLLING  # noqa: E402
from evals.regenold.official_batch import load_official_batch  # noqa: E402
from evals.regenold.run_official_batch import (  # noqa: E402
    _clear_engine_cache,
    _run_hard,
    select_rows,
)
from evals.regenold.runner_v2 import _post_local  # noqa: E402


class _DevNull:
    def write(self, _s: str) -> None:  # pragma: no cover - sink
        pass

    def flush(self) -> None:  # pragma: no cover - sink
        pass


def _patch_builders(question_to_id: dict[str, str]) -> None:
    """Record, per row and turn, how many messages this request carries.

    The FIXED builders take the question (the dialogue is the prefix, not an
    argument), so the row id is recovered by lookup; the ROLLING builders take the
    row directly. Both are wrapped rather than replaced.
    """
    orig = {
        "pref1": _R.build_prefixed_messages,
        "pref2": _R.build_prefixed_pushback_messages,
        "roll1": _R.build_hard_messages,
        "roll2": _R.build_pushback_messages,
    }

    def _note(row_id: str, turn: str, n: int) -> None:
        STATE["row"], STATE["turn"], STATE["msgs"] = row_id, turn, n

    def pref1(question):  # noqa: ANN001, ANN202
        msgs = orig["pref1"](question)
        _note(question_to_id[question], "t1", len(msgs))
        return msgs

    def pref2(question, first, pushback):  # noqa: ANN001, ANN202
        msgs = orig["pref2"](question, first, pushback)
        _note(question_to_id[question], "pb", len(msgs))
        return msgs

    def roll1(row, history):  # noqa: ANN001, ANN202
        msgs = orig["roll1"](row, history)
        _note(row.id, "t1", len(msgs))
        return msgs

    def roll2(row, history, first):  # noqa: ANN001, ANN202
        msgs = orig["roll2"](row, history, first)
        _note(row.id, "pb", len(msgs))
        return msgs

    _R.build_prefixed_messages = pref1
    _R.build_prefixed_pushback_messages = pref2
    _R.build_hard_messages = roll1
    _R.build_pushback_messages = roll2


def _drive(run: str, ids: str, mode: str, rows_all) -> None:
    """Ask every selected row in ONE call, so the rolling history really rolls."""
    rows = select_rows(list(rows_all), ids=ids)
    STATE["run"] = run
    # A cold route cache per sub-run: two sub-runs that post byte-identical
    # requests WOULD otherwise be served from the response cache (which is itself
    # evidence that the fixed request is position-invariant), but the point here is
    # to see the dispatch, so the cache is cleared before each one.
    cleared, err = _clear_engine_cache()
    print(
        f"\n########## {run}  mode={mode}  ids={ids}  rows={[r.id for r in rows]}"
        f"  cache_cleared={cleared}{' ERR ' + str(err) if err else ''}",
        flush=True,
    )
    _run_hard(
        rows, _post_local, "local", "unused", 300, _DevNull(), sample=0, preamble=mode
    )


def _kind(call: dict[str, object]) -> str:
    if call["stage2"]:
        return "stage2"
    if call["parse"]:
        return "parse"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="use the real transport")
    args = ap.parse_args()
    _STUBBED[0] = not args.live
    _LIVE_ORIG[0] = args.live
    print(f"transport: {'LIVE' if args.live else 'stubbed'}", flush=True)

    rows_all = list(load_official_batch())
    _patch_builders({r.question: r.id for r in rows_all})

    #: The paired row must reach Stage-2 (``rg_001`` is a curated deterministic
    #: intercept and dispatches nothing at all — kept in the run precisely so that
    #: is visible rather than assumed).
    pair_row = "rg_004"
    runs = [
        (f"{MODE_ROLLING}:alone", pair_row, MODE_ROLLING),
        (f"{MODE_ROLLING}:behind", f"rg_001,{pair_row}", MODE_ROLLING),
        (f"{MODE_FIXED}:alone", pair_row, MODE_FIXED),
        (f"{MODE_FIXED}:behind", f"rg_001,{pair_row}", MODE_FIXED),
    ]
    for run, ids, mode in runs:
        _drive(run, ids, mode, rows_all)

    print("\n=== every provider dispatch ===", flush=True)
    print(
        f"  {'run':22}{'row':8}{'turn':4}{'kind':8}{'req_msgs':>9}{'hist':>6}"
        f"{'system_ch':>10}  {'fixture':8}{'conv':6}{'anchors':8}prompt"
    )
    for call in CALLS:
        kind = _kind(call)
        if kind == "other":
            continue
        system_chars = int(call["system_chars"])
        tag = (
            "FULL"
            if system_chars >= FULL_MIN_CHARS
            else ("persona" if system_chars < 200 else f"OTHER({system_chars})")
        )
        print(
            f"  {str(call['run']):22}{str(call['row']):8}{str(call['turn']):4}{kind:8}"
            f"{int(call['msgs']):>9}{max(0, int(call['msgs']) - 1):>6}"
            f"{system_chars:>10}  {'yes' if call['fixture'] else 'no':8}"
            f"{'yes' if call['conversation'] else 'no':6}"
            f"{'yes' if call['anchors'] else 'no':8}{tag}"
        )

    print("\n=== the decisive pair: same row, only its POSITION differs ===", flush=True)
    print(
        f"  {'mode':9}{'row':8}{'turn':4}{'alone (hist, system)':>26}"
        f"{'behind (hist, system)':>26}   verdict"
    )
    failures: list[str] = []

    def _pick(run: str, row_id: str, turn: str, kind: str = "stage2"):
        return next(
            (
                c for c in CALLS
                if c["run"] == run and c["row"] == row_id and c["turn"] == turn
                and _kind(c) == kind
            ),
            None,
        )

    for mode in (MODE_ROLLING, MODE_FIXED):
        alone_run, behind_run = f"{mode}:alone", f"{mode}:behind"
        for turn in ("t1", "pb"):
            alone = _pick(alone_run, pair_row, turn)
            behind = _pick(behind_run, pair_row, turn)

            def _f(c):  # noqa: ANN001, ANN202
                if c is None:
                    return "-"
                return f"({max(0, int(c['msgs']) - 1)}, {c['system_chars']})"

            differs = (
                alone is not None
                and behind is not None
                and (max(0, int(alone["msgs"]) - 1), alone["system_chars"])
                != (max(0, int(behind["msgs"]) - 1), behind["system_chars"])
            )
            if mode == MODE_FIXED and differs:
                failures.append(f"fixed/{pair_row}/{turn} changed with position")
            if mode == MODE_ROLLING and not differs:
                failures.append(
                    f"rolling/{pair_row}/{turn} did NOT change with position: the "
                    "leak this probe exists to show was not reproduced"
                )
            print(
                f"  {mode:9}{pair_row:8}{turn:4}{_f(alone):>26}{_f(behind):>26}"
                f"   {'CHANGED with position' if differs else 'invariant'}"
            )

    #: The full-prompt dispatches are the leak's footprint: which rows took the
    #: 59.6 kB system prompt because of where they sat in the run.
    full = sorted({str(c["row"]) for c in CALLS if int(c["system_chars"]) >= FULL_MIN_CHARS})
    print(f"\n  rows dispatched the FULL system prompt: {full or 'none'}")

    print()
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print(
        "PASS: in rolling mode the same row changes modality with its position "
        "(the leak); in fixed mode every row reads the same depth and the same "
        "system prompt wherever it sits in the run."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""R415 — is the multi-turn pushback path TOUCHED by the single-turn lever?

``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`` is default ON (R412). The claim under
test is that it cannot change a hard-mode request, because its predicate is
``history_turn_count <= 1`` and every hard-mode ask reads >= 2 (the 9-turn final
and the adversarial pushback). That is a claim about WHAT GETS DISPATCHED, so it
is measured at the seam that carries the truth — ``OpenAIWrapperRequest.system``,
the text the model actually receives — over the REAL request path
(route -> history flattening -> engine -> provider).

WHY THE PROVIDER SEAM AND NOT THE ENGINE FUNCTION. The system substitution
happens INSIDE ``_openai_wrapper_complete_for_graph_rag``. Replacing that whole
function (the first cut of this probe) records the PRE-substitution text and
reports two different arms as IDENTICAL — the trap ``evals.harness.gate_validity``
documents, walked into again here. So the function is wrapped as a PASS-THROUGH
that records the kwargs the route threaded and then delegates to the real body,
while the payload is recorded one layer down at the provider.

WHAT IT PROVES, and the control that keeps it honest:

* PREDICATE SCOPE — the same long system and one Stage-2 answer call at
  ``history_turn_count`` in (None, 0, 1, 2, 9), flag 0 vs 1. The arms may differ
  ONLY at <= 1.
* END-TO-END — hard probe rows must have identical signatures across arms, and
  EASY rows must DIFFER with the same instrument in the same run. That non-vacuity
  control is load-bearing: a probe showing "no change" everywhere is
  indistinguishable from a probe whose seam never fired.

No live model calls: the provider is patched to return a stage-appropriate canned
response (JSON for the parse, prose for the graded answer).

Usage::

    set -a; . ./.env; set +a
    .venv\\Scripts\\python.exe docs/measurements/r415/pushback_invariance_probe.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r415"
FLAG = "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN"

#: Stage-2 answer markers — the same filter ``gate_validity`` uses.
_STAGE2_MARKERS = ("EU AI ACT REFERENCES:", "ANSWER CONTRACT")

_PARSED = json.dumps(
    {
        "intent": "general_compliance",
        "entities": ["provider", "high-risk AI system"],
        "risk_context": "high_risk",
        "dimension_hint": "obligations",
        "keywords": ["technical documentation", "Annex IV"],
        "reasoning": "stub parse for the invariance probe",
    }
)

_ANSWER = (
    "Under Article 11 read with Annex IV, the provider of a high-risk AI system "
    "must draw up and keep up to date the technical documentation set out in "
    "Annex IV. Article 16 makes that duty an obligation of the provider, and "
    "Article 18 requires the documentation to be kept for the lifetime of the "
    "system. References: Article 11, Annex IV, Article 16, Article 18."
)


class ProviderRecorder:
    """The truth: what each dispatched request's system payload actually was."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def complete(self, request, *args: Any, **kwargs: Any):  # noqa: ANN002, ANN003
        system = str(getattr(request, "system", "") or "")
        user = str(getattr(request, "user", "") or "")
        stage2 = any(m in user for m in _STAGE2_MARKERS)
        self.payloads.append(
            {
                "stage2_answer_call": stage2,
                "system_len": len(system),
                "system_sha": hashlib.sha256(system.encode("utf-8")).hexdigest()[:16],
            }
        )
        return SimpleNamespace(
            error=None,
            text=_ANSWER if stage2 else _PARSED,
            thinking="",
            finish_reason="stop",
            model="probe-stub",
            usage=None,
            latency_ms=1,
            headers=None,
        )


class KwargsPassThrough:
    """Records what the route THREADED, then runs the real body."""

    def __init__(self, real) -> None:  # noqa: ANN001
        self.real = real
        self.kwargs: list[dict] = []

    def __call__(self, *, system: str, user: str, **kw: Any) -> Any:
        self.kwargs.append(
            {
                "stage_name": kw.get("stage_name"),
                "history_turn_count": kw.get("history_turn_count"),
                "system_len_in": len(system),
            }
        )
        return self.real(system=system, user=user, **kw)


def _installed():
    """Return (impl, original, provider, original_provider) with both patches on."""
    from app.engines import _graph_rag_impl as impl
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider

    provider = get_openai_wrapper_provider()
    original_provider = provider.complete
    recorder = ProviderRecorder()
    provider.complete = recorder.complete  # type: ignore[method-assign]
    original = impl._openai_wrapper_complete_for_graph_rag
    passthrough = KwargsPassThrough(original)
    impl._openai_wrapper_complete_for_graph_rag = passthrough  # type: ignore[assignment]
    return {
        "impl": impl,
        "original": original,
        "provider": provider,
        "original_provider": original_provider,
        "recorder": recorder,
        "passthrough": passthrough,
    }


def _restore(h: dict) -> None:
    h["provider"].complete = h["original_provider"]  # type: ignore[method-assign]
    h["impl"]._openai_wrapper_complete_for_graph_rag = h["original"]  # type: ignore[assignment]


def _signature(h: dict) -> dict:
    payloads = [
        (p["stage2_answer_call"], p["system_len"], p["system_sha"])
        for p in h["recorder"].payloads
    ]
    graded = [g for g in payloads if g[0]]
    return {
        "threaded": [
            (k["stage_name"], k["history_turn_count"]) for k in h["passthrough"].kwargs
        ],
        "payloads": payloads,
        #: The call the benchmark GRADES. Its payload is the one the lever edits.
        "graded": graded[-1][1:] if graded else None,
        "graded_is_full_system": bool(graded and graded[-1][1] > 1000),
    }


def _predicate_scope() -> list[dict]:
    """The scope of the predicate, measured through the real substitution."""
    from app.engines import _graph_rag_impl as impl

    long_system = "S" * 5000
    rows: list[dict] = []
    for turns in (None, 0, 1, 2, 9):
        lens: dict[str, int] = {}
        for flag_on in (False, True):
            os.environ[FLAG] = "1" if flag_on else "0"
            h = _installed()
            try:
                impl._openai_wrapper_complete_for_graph_rag(
                    system=long_system,
                    user="ANSWER CONTRACT",
                    max_tokens=16,
                    temperature=0.0,
                    stage_name="Stage 2 (Answer)",
                    history_turn_count=turns,
                )
            finally:
                _restore(h)
            lens["on" if flag_on else "off"] = h["recorder"].payloads[0]["system_len"]
        rows.append(
            {
                "history_turn_count": turns,
                "flag_off_system_len": lens["off"],
                "flag_on_system_len": lens["on"],
                "identical": lens["off"] == lens["on"],
            }
        )
    return rows


def _run_row(history: list[dict], *, flag_on: bool) -> tuple[dict, str, list[str]]:
    from evals.regenold.runner_v2 import _post_local

    os.environ[FLAG] = "1" if flag_on else "0"
    h = _installed()
    try:
        body, _latency, _status, _err, _attempts, _retried = _post_local(
            "local://app.main:app/api/v1/regenold/eu-ai-act/ask",
            None,
            history,
            180.0,
        )
    finally:
        _restore(h)
    answer = str((body or {}).get("answer") or "")
    refs = [str(r) for r in ((body or {}).get("references") or [])]
    return _signature(h), answer, refs


def main() -> int:
    provider = os.getenv("P2P_GRAPH_RAG_PROVIDER", "")
    if provider != "openai_wrapper":
        print(
            f"!! P2P_GRAPH_RAG_PROVIDER={provider!r}: the single-turn lever edits the\n"
            "   WRAPPER leg's system slot, so with any other provider this probe\n"
            "   cannot see it and a 'no change' reading is vacuous. Source the\n"
            "   deploy's .env (set -a; . ./.env; set +a) before running."
        )
        return 2

    from evals.harness.probe_set import load_probe_set

    print("=" * 96)
    print("PREDICATE SCOPE — the real substitution, long system, one Stage-2 answer call")
    print(f"  {'history_turn_count':>18}  {'flag=0 len':>10}  {'flag=1 len':>10}  identical")
    scope = _predicate_scope()
    for r in scope:
        print(
            f"  {str(r['history_turn_count']):>18}  {r['flag_off_system_len']:>10}"
            f"  {r['flag_on_system_len']:>10}  {r['identical']}"
        )
    differ_at = [r["history_turn_count"] for r in scope if not r["identical"]]
    print(f"  arms differ ONLY at history_turn_count in {differ_at} (expected [0, 1])")
    # The predicate is ``history_turn_count <= 1``, and the ROUTE's arithmetic is
    # ``max(0, user+assistant messages - 1)`` — so the FIRST ask reads **0**, a
    # ask with one prior exchange reads **1**, the official hard final (10
    # messages) reads 9, and the pushback reads 9 or 10. Both 0 and 1 are
    # single-turn-shaped, which is why the measured differ-set is {0, 1} and not
    # {1}: the code comment in ``_graph_rag_impl`` says "a single-turn ask reads
    # 1", which is true for a DIRECT engine caller (``GraphRAGRequest`` defaults
    # to 1) but not for the route.
    scope_ok = differ_at == [0, 1]

    report: dict[str, Any] = {"predicate_scope": scope, "hard": [], "easy": []}
    hard = load_probe_set(multiturn=True, limit=4)
    easy = load_probe_set(multiturn=False, limit=4)
    if not hard or not easy:
        print("!! probe set missing a split; cannot establish the control")
        return 2

    for label, rows in (("hard", hard), ("easy", easy)):
        print("=" * 96)
        print(f"{label.upper()} rows: {len(rows)}")
        for row in rows:
            history = [dict(m) for m in row.messages]
            sig_on, ans_on, refs_on = _run_row(history, flag_on=True)
            sig_off, ans_off, refs_off = _run_row(history, flag_on=False)
            same = sig_on == sig_off
            graded_same = sig_on["graded"] == sig_off["graded"]
            rec = {
                "id": row.id,
                "is_multiturn": bool(row.is_multiturn),
                "signature_identical": same,
                "threaded_on": sig_on["threaded"],
                "threaded_off": sig_off["threaded"],
                "payloads_on": sig_on["payloads"],
                "payloads_off": sig_off["payloads"],
                "graded_on": sig_on["graded"],
                "graded_off": sig_off["graded"],
                "graded_identical": graded_same,
                "graded_full_on": sig_on["graded_is_full_system"],
                "graded_full_off": sig_off["graded_is_full_system"],
                "answer_identical": (ans_on == ans_off) and (refs_on == refs_off),
            }
            report[label].append(rec)
            print(
                f"  {row.id:<26} threaded {sig_on['threaded'][:1]} vs "
                f"{sig_off['threaded'][:1]}"
            )
            print(
                f"  {'':<26} GRADED payload {sig_on['graded']} vs {sig_off['graded']}"
                f"  (full-system {sig_on['graded_is_full_system']} vs "
                f"{sig_off['graded_is_full_system']})  "
                f"{'IDENTICAL' if graded_same else 'DIFFER'}"
            )
            if not same and graded_same:
                print(
                    f"  {'':<26} note: call COUNT differs "
                    f"({len(sig_on['payloads'])} vs {len(sig_off['payloads'])}) with an "
                    "identical graded payload — pipeline retry noise (Groq TPD 429 / "
                    "Neo4j), not the lever."
                )

    # The lever edits the GRADED call's system slot. The modality claim is about
    # that payload and about what the route threaded; a differing CALL COUNT is an
    # external-retry artefact (measured: the same row's count moved when Groq
    # answered 429 on tokens-per-day), so it is reported but not counted as a hit.
    hard_untouched = all(r["graded_identical"] for r in report["hard"])
    hard_threaded_same = all(
        r["threaded_on"] == r["threaded_off"] for r in report["hard"]
    )
    easy_visible = any(not r["graded_identical"] for r in report["easy"])
    seam_fired = all(r["graded_on"] and r["graded_off"] for r in report["hard"])
    report["hard_threaded_same"] = hard_threaded_same
    report["call_count_variance_rows"] = [
        r["id"] for r in report["hard"] if not r["signature_identical"]
    ]

    print("=" * 96)
    print("VERDICT")
    print(f"  predicate differs only at <= 1 turn                             : {scope_ok}")
    print(f"  hard rows: GRADED payload identical across arms                  : {hard_untouched}")
    print(f"  hard rows: route threaded the same modality                      : {hard_threaded_same}")
    print(f"  the payload seam fired on every hard row (else vacuous)          : {seam_fired}")
    print(f"  NON-VACUITY control — easy rows' GRADED payload DIFFERS           : {easy_visible}")
    if report["call_count_variance_rows"]:
        print(
            "  note: call count varied on "
            f"{report['call_count_variance_rows']} (external retries, not the lever)"
        )
    report["conclusive"] = bool(
        scope_ok and hard_untouched and hard_threaded_same and seam_fired and easy_visible
    )
    report["predicate_scope_ok"] = scope_ok
    report["hard_untouched"] = hard_untouched
    report["seam_fired"] = seam_fired
    report["non_vacuity_control_passed"] = easy_visible
    print(f"  CONCLUSIVE: {report['conclusive']}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pushback-invariance.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"wrote {OUT / 'pushback-invariance.json'}")
    return 0 if report["conclusive"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

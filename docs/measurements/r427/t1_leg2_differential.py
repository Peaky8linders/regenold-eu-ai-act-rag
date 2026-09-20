"""R427 / R426 T1 — differential replay of the leg-2 dispatch: OLD vs NEW.

T1 collapses the two Stage-2 leg-2 (Bedrock) paths into one dispatch with one
outcome type (``app/llm/stage2.py``). The tranche is declared a **pure move**, so
the gate is the repo's byte-identical replay: drive the SAME inputs through the
pre-T1 code and the post-T1 code and require identical observable output.

What is replayed, and why it can be exact
-----------------------------------------
A recorded-draw replay at the *row* level is not available for this move: the
transport decision happens UPSTREAM of generation, no board checkpoint stores the
raw leg-2 text, and re-calling the models is not byte-reproducible. What the
decision is a pure function of is the leg-2 response TEXT plus which call site
dialled it — so the replay drives both real implementations over a corpus of
text and diffs the observable consequences:

1. **the text the caller receives** (byte-for-byte),
2. **the ``stage2_policy`` counter delta** (attempts dropped into the counter at
   every step, so a drifted ``record_result`` shows up as a delta),
3. **the leg-2 serve marker** (R417 ``stage2_served_by`` bookkeeping),
4. **every warning the branch emitted** (the discard is usually only visible as a
   log line).

The corpus is anchored in the recorded draws and then closed over classes
-----------------------------------------------------------------------
* **recorded**: every ``pred_answer`` / ``turn1_answer`` / ``pushback_answer`` on
  the recorded hard-split boards — the only production-shaped Stage-2 text on
  disk — reduced to a stable, deduplicated sample;
* **classes**: the shapes the branches actually key on. The pre-T1 code has two
  emptiness notions (``not text`` on the transport, ``bool(text.strip())`` on the
  answer path) and a structural-truncation rule applied on one path only, so the
  boundary set is the whole point: ``None``, ``""``, whitespace-only, a
  mid-clause cut, a complete sentence, an ``<answer>``-wrapped complete answer, a
  markdown table row, an ellipsis ending.

Honest scope
------------
* No recorded row on any recent board was served by leg 2
  (``provenance.stage2_served_by`` never equals ``fallback``), so the row-level
  replay is ``+0`` by construction and this differential is the operative
  equivalence proof — it is run over the real code on both sides, not a
  transcription of it.
* The answer-path preset is deliberately NOT consumed (see T1b in
  ``CHECKPOINT.md``): equalising it changes which text ships, which is a
  behaviour change and must not ride along inside a move. This harness therefore
  asserts equality with the answer-path preset still in its pre-T1 shape.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r427.t1_leg2_differential
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

IMPL_REL = "app/engines/_graph_rag_impl.py"
BOARDS = ("official-r424-preamble", "official-r423-need4", "official-r423-need")
RESULTS = REPO / "evals" / "bench" / "results"
#: jsonl, one drive per line, following the checkpoints' own convention.
OUT_JSON = REPO / "docs" / "measurements" / "r427" / "t1_differential.jsonl"

#: The branches key on these shapes, so the corpus must contain all of them.
CLASS_CASES: tuple[tuple[str, str | None], ...] = (
    ("none", None),
    ("empty", ""),
    ("whitespace", "   \n  "),
    ("mid_clause_cut", "A provider of a high-risk AI system must establish a quality "
                       "management system and the provider mus"),
    ("complete_sentence", "Yes. Article 11 requires technical documentation."),
    ("xml_channels", "<reasoning_scratchpad>considering Article 11</reasoning_scratchpad>"
                     "<answer>Yes. Article 11 requires technical documentation.</answer>"),
    ("table_row", "| Provider | Art. 11 |\n| Deployer | Art. 13 |"),
    ("ellipsis_cut", "The obligations are set out in Article 13, namely…"),
)

#: The two call sites this tranche moved, plus a third drive that reaches the
#: answer path's inline block (see ``_drive``).
SITES = ("transport", "answer", "answer_block")


def load_old_impl() -> Any:
    """Import ``_graph_rag_impl`` **as committed at HEAD**, side by side with NEW."""
    src = subprocess.run(
        ["git", "show", f"HEAD:{IMPL_REL}"],
        cwd=REPO, capture_output=True, check=True,
    ).stdout
    tmp = Path(tempfile.mkdtemp(prefix="r427_old_"))
    target = tmp / "r427_old_impl.py"
    target.write_bytes(src)
    spec = importlib.util.spec_from_file_location("r427_old_impl", target)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["r427_old_impl"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Capture(logging.Handler):
    """Collect WARNING+ records so a branch that only logs is still comparable."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        # Message only: the logger NAME differs by construction (OLD is loaded
        # from a temp file under a different module name), so comparing it would
        # report a mismatch for every case that logs anything.
        self.records.append(record.getMessage())


def _snapshot() -> dict[str, Any]:
    from app.llm import stage2_policy as pol

    raw = pol.transport_stats()
    return {
        k: (dict(sorted(v.items())) if isinstance(v, dict) else v)
        for k, v in raw.items()
    }


def _drive(mod: Any, site: str, text: str | None) -> dict[str, Any]:
    """One real drive of one call site, returning the observable output."""
    from unittest.mock import patch

    from app.engines.graph_rag import GraphContext
    from app.llm import stage2_policy as pol
    from app.llm.openai_wrapper_provider import OpenAIWrapperResponse

    class _DeadWrapper:
        """Leg 1 fails, so leg 2 is the only leg that can answer.

        The two sites need DIFFERENT leg-1 failures, and that is a fact about
        the pipeline rather than a convenience:

        * the transport site takes a plain transport error (its
          ``response.error`` branch reaches ``_try_bedrock_fallback``);
        * the answer site dials the wrapper transport as its OWN leg 1, and a
          leg 1 that *raises* is caught by the enclosing ``except`` — which
          returns ``None`` and never reaches the inline fallback block this
          tranche moved. So it gets ``finish_reason="length"``, whose own leg-2
          attempt the stub below starves, leaving leg 1 returning ``None``.
        """

        def complete(self, request: Any) -> Any:
            if site == "transport":
                return OpenAIWrapperResponse(
                    text="", model="dead", error="api_status_500",
                    finish_reason=None, completion_tokens=0, elapsed_ms=1,
                )
            return OpenAIWrapperResponse(
                text="partial", model="dead", error="",
                finish_reason="length", completion_tokens=900, elapsed_ms=1,
            )

    calls = {"n": 0}

    def _bedrock(**kwargs: Any) -> str | None:
        """Leg 2 as the corpus wants it dialled.

        Transport: the only dial is the one under test, so it always serves the
        corpus text. Answer: the FIRST dial is leg 1's own attempt and must fail
        (that is what makes leg 1 return ``None`` instead of raising); the corpus
        text is served on the dial that lands in the inline fallback block.
        """
        calls["n"] += 1
        if site == "answer" and calls["n"] == 1:
            return None
        return text

    os.environ["AWS_ACCESS_KEY_ID"] = "fake"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "fake"
    os.environ["REGENOLD_FUSION_STAGE2"] = "0"
    os.environ.pop("P2P_GRAPH_RAG_PROVIDER", None)

    served_before = mod._STAGE2_LEG2_SERVED.get()
    pol.reset_transport_stats()
    capture = _Capture()
    logging.getLogger().addHandler(capture)
    raised = ""
    out: str | None = None
    try:
        patchers: list[Any] = [
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=_DeadWrapper(),
            ),
            patch(
                "app.llm.bedrock_client.is_bedrock_provider_enabled", return_value=True,
            ),
            patch.object(mod, "_bedrock_complete_for_graph_rag", side_effect=_bedrock),
        ]
        if site == "answer_block":
            # Seam, stated plainly. The answer path's inline leg-2 block is only
            # entered when the wrapper TRANSPORT returns ``None``, and no shipped
            # branch does that: every leg-1 failure either returns leg 2's answer
            # or raises (measured — see CHECKPOINT section 6). So the block is
            # unreachable today, which is exactly why it is worth replaying: it
            # is shipped code that would run the moment any branch changes, and
            # it carried a second, drifted copy of the leg-2 policy. Leg 1 is
            # stubbed to its documented "no answer" return, and the drive asserts
            # that ONE leg-2 dial then happens — from the block itself.
            patchers.append(
                patch.object(
                    mod, "_openai_wrapper_complete_for_graph_rag", return_value=None,
                )
            )
        with ExitStack() as stack:
            for _patcher in patchers:
                stack.enter_context(_patcher)
            if site == "transport":
                out = mod._openai_wrapper_complete_for_graph_rag(
                    system="SYSTEM", user="USER", max_tokens=512, temperature=0.0,
                )
            else:
                out = mod._claude_max_enhance_answer(
                    question="What does Article 11 require?",
                    kg_answer="Article 11 requires technical documentation.",
                    context=GraphContext(),
                )
    except Exception as exc:  # noqa: BLE001 — the raise IS an observable outcome
        raised = f"{type(exc).__name__}: {exc}"
    finally:
        logging.getLogger().removeHandler(capture)
    counters = _snapshot()
    pol.reset_transport_stats()
    return {
        "returned": out,
        "raised": raised,
        "bedrock_calls": calls["n"],
        "counters": counters,
        "leg2_served": mod._STAGE2_LEG2_SERVED.get(),
        "warnings": sorted(capture.records),
        "served_before": served_before,
    }


#: The counter order used in the artifact, so a row stays readable at a glance.
COUNTER_ORDER = (
    "primary_attempts", "primary_ok", "primary_failed",
    "fallback_attempts", "fallback_ok", "fallback_failed", "refused",
)


def _sha(text: str | None) -> str:
    return "" if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _compact(side: dict[str, Any], *, keep_text: bool) -> dict[str, Any]:
    """The artifact's per-side record.

    The claim under test is BYTE identity, so a digest is the evidence; the full
    text is kept only for a side that disagreed, where it is needed to debug.
    Storing both sides in full on every drive produced a 2.5 MB artifact for a
    result that is 774 identical rows.
    """
    out: dict[str, Any] = {
        "returned_len": None if side["returned"] is None else len(side["returned"]),
        "returned_sha": _sha(side["returned"]),
        "raised": side["raised"],
        "bedrock_calls": side["bedrock_calls"],
        "counters": [side["counters"][k] for k in COUNTER_ORDER],
        "refused_by_provider": side["counters"]["refused_by_provider"],
        "leg2_served": side["leg2_served"],
        "warnings_count": len(side["warnings"]),
        "warnings_sha": _sha("\n".join(side["warnings"])),
    }
    if keep_text:
        out["returned"] = side["returned"]
        out["warnings"] = side["warnings"]
    return out


def _recorded_corpus(limit: int) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for stem in BOARDS:
        for path in sorted(RESULTS.glob(f"{stem}-*.ckpt.jsonl")):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for field in ("pred_answer", "turn1_answer", "pushback_answer"):
                    value = row.get(field)
                    if isinstance(value, str) and value.strip() and value not in seen:
                        seen.add(value)
                        texts.append(value)
                        if len(texts) >= limit:
                            return texts
    return texts


def main() -> int:
    try:  # the corpus is legal prose: em dashes and ellipses on a cp1252 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recorded", type=int, default=250,
                        help="how many recorded answers to include (default 250; "
                             "the whole replay costs seconds because no model is called)")
    parser.add_argument("--json", action="store_true", help="write the artifact JSON")
    args = parser.parse_args()

    old = load_old_impl()
    import app.engines._graph_rag_impl as new

    corpus: list[tuple[str, str | None]] = list(CLASS_CASES)
    corpus += [(f"recorded[{i}]", t) for i, t in enumerate(_recorded_corpus(args.recorded))]

    rows: list[dict[str, Any]] = []
    mismatches = 0
    for site in SITES:
        for label, text in corpus:
            a = _drive(old, site, text)
            b = _drive(new, site, text)
            same = a == b
            mismatches += 0 if same else 1
            rows.append({
                "site": site, "case": label, "identical": same,
                "chars": None if text is None else len(text),
                "old": a, "new": b,
            })
            flag = "OK " if same else "DIFF"
            print(f"  [{flag}] {site:9s} {label:22s} chars={str(None if text is None else len(text)):>5s}")

    identical = sum(1 for r in rows if r["identical"])
    print(
        f"\n{identical}/{len(rows)} drives byte-identical "
        f"({len(corpus)} inputs x {len(SITES)} call sites)"
    )

    # Vacuity guard, in the R422/R425 tradition: an equivalence result is worth
    # nothing if the second call site was never reached. The answer path has to
    # dial leg 2 twice (leg 1's own attempt, then the inline fallback block); a
    # drive with a single dial measured leg 1 and called itself a pass.
    expected = {"transport": (1, 1), "answer": (1, 1), "answer_block": (0, 1)}
    void_sites: list[str] = []
    for name, (want_primary, want_fallback) in expected.items():
        seen = sorted({(r["new"]["counters"]["primary_attempts"],
                        r["new"]["counters"]["fallback_attempts"])
                       for r in rows if r["site"] == name})
        ok = seen == [(want_primary, want_fallback)]
        print(f"  {name:13s} (primary, fallback) dials per drive: {seen} "
              f"{'REACHED' if ok else 'VOID'}")
        if not ok:
            void_sites.append(name)
    if void_sites:
        print(f"VOID — the moved code was not exercised at: {', '.join(void_sites)}")
        mismatches += 1
    if mismatches:
        print("\nMISMATCHES")
        for r in rows:
            if not r["identical"]:
                print(f"  {r['site']}/{r['case']}")
                for key in ("returned", "raised", "counters", "leg2_served", "warnings"):
                    if r["old"][key] != r["new"][key]:
                        print(f"    {key}: OLD={str(r['old'][key])[:240]}")
                        print(f"    {key}: NEW={str(r['new'][key])[:240]}")
    if args.json:
        header = {
            "kind": "header",
            "site_count": len(SITES),
            "inputs": len(corpus),
            "recorded_inputs": sum(1 for c, _ in corpus if c.startswith("recorded")),
            "class_inputs": sum(1 for c, _ in corpus if not c.startswith("recorded")),
            "corpus_sha": _sha("\u0000".join((c or "") + "\u0001" + (t or "")
                                             for c, t in corpus)),
            "head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=REPO,
                capture_output=True, text=True,
            ).stdout.strip(),
            "counter_order": list(COUNTER_ORDER),
            "identical": identical, "mismatches": mismatches,
        }
        lines = [json.dumps(header, separators=(",", ":"))]
        lines += [
            json.dumps({
                "site": r["site"], "case": r["case"],
                "identical": r["identical"], "chars": r["chars"],
                "old": _compact(r["old"], keep_text=not r["identical"]),
                "new": _compact(r["new"], keep_text=not r["identical"]),
            }, separators=(",", ":"))
            for r in rows
        ]
        OUT_JSON.write_text("\n".join(lines) + "\n", encoding="utf-8")
        size_kb = OUT_JSON.stat().st_size / 1024
        print(f"wrote {OUT_JSON.relative_to(REPO)} ({size_kb:.0f} KB)")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())

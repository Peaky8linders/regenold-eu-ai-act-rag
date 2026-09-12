"""R413 — live probe of the terminate rung on the R411 production weld.

The R411 live verification produced this shipped text (hospital-chatbot ask):

    "... the only EU AI Act transparency duties it triggers are those in
     answering general patient queries on a hospital website is neither
     emergency triage nor ..."

The cut sentence was ALREADY grammatical; the model tail started a NEW clause
after it. This probe drives the real guard over that exact text through the
wired Stage-2 provider and reports which rung answered, so the fix is verified
on the live transport and not only in unit tests.

Also probes a genuinely incomplete cut (the rg_034 shape the n=40 gate
measured) to confirm the reconstruction names the operative provision instead
of hedging.

Usage::

    .venv/Scripts/python.exe docs/measurements/r413/hospital_case_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.engines import graph_rag as gr  # noqa: E402
from app.engines.graph_rag.models import GraphContext  # noqa: E402
from app.llm.stage2_policy import reset_transport_stats, transport_stats  # noqa: E402

#: The R411 production text, cut exactly where the token cap landed.
HOSPITAL = (
    "For a patient-facing chatbot deployed by a hospital, the only EU AI Act "
    "transparency duties it triggers are those in answering general patient "
    "queries on a hospital website"
)

#: The rg_034 shape: the cut lands where the sentence was about to name the
#: governing provision (Article 100(5)), which the R413 gate showed the first
#: reconstruction prompt hedged away.
COURT = (
    "Article 99 outlines the administrative penalty regime and fine ceilings "
    "for general-purpose AI model providers, but it does not address judicial "
    "review. Consequently, the specific legal authority and remedial actions "
    "available to the Court"
)


def main() -> int:
    import os

    os.environ["REGENOLD_STAGE2_TAIL_REPAIR_MODE"] = "sentence"
    rc = 0
    for name, text in (("hospital", HOSPITAL), ("court", COURT)):
        reset_transport_stats()
        out, used = gr._guard_stage2_truncation(
            "What transparency duties apply to a hospital's patient chatbot?",
            text,
            "DETERMINISTIC_STAGE1_ANSWER",
            GraphContext(question="q"),
        )
        stats = transport_stats()
        print(f"\n=== {name} ===")
        print(f"  stage2_used={used}  primary_ok={stats.get('primary_ok')}  "
              f"fallback_ok={stats.get('fallback_ok')}  refused={stats.get('refused')}")
        print(f"  cut      : ...{text[-110:]}")
        print(f"  shipped  : ...{out[-180:]}")
        print(f"  complete : {not gr._looks_incomplete_final_sentence(out)}")
        if name == "hospital":
            term = out.rstrip().endswith(text.rstrip() + ".")
            print(f"  lossless termination (verbatim + full stop): {term}")
            rc |= 0 if term else 1
        else:
            names = "Article 100(5)" in out
            print(f"  reconstruction names the operative provision: {names}")
            rc |= 0 if names else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

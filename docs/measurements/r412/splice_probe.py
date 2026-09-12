"""R412 — reproduce and diagnose the live Stage-2 sentence-splicing residual.

The R411 deploy verification recorded two production answers whose prose welds
two clauses into an ungrammatical sentence, e.g.

    "... the only EU AI Act transparency duties it triggers are those in
     answering general patient queries on a hospital website is neither
     emergency triage nor ..."

The deterministic path is clean, so the artefact is produced between the
retrieved evidence and the wire. Two candidate producers are known to JOIN text:

* ``_attempt_stage2_tail_repair`` — splices a model-generated "missing tail"
  onto the truncated polish (``enhanced.rstrip() + tail``).
* ``_salvage_truncated_polish`` — cuts the polish at its last complete sentence.

This probe asks the exact question shape that produced the artefact and dumps
the FULL answer plus every trace note, so the diagnosis is read off the wire
rather than inferred from a fragment.

    .venv/Scripts/python.exe docs/measurements/r412/splice_probe.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
URL = f"{BASE}/api/v1/regenold/eu-ai-act/ask"

# The provider-chatbot-on-a-hospital-website question reproduces the observed
# weld: a PROVIDER asking about its own transparency duties where a hospital is
# named only as the VENUE (this is also the shape R411 fix #2 un-captured).
HOSPITAL_Q = (
    "We provide a patient-facing chatbot that a hospital deploys on its website "
    "to answer general patient queries. What EU AI Act transparency duties apply "
    "to us as provider, and is the system emergency triage or otherwise high-risk?"
)


def ask(question: str) -> dict:
    body = json.dumps([{"role": "user", "content": question}]).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    payload = ask(HOSPITAL_Q)
    print("=== top-level keys ===")
    print(sorted(payload.keys()))
    answer = payload.get("answer") or payload.get("response") or ""
    print(f"\n=== answer ({len(answer)} chars) ===")
    print(answer)
    print("\n=== references ===")
    print(json.dumps(payload.get("references"), ensure_ascii=False))
    for key in ("notes", "trace", "reasoning_trace", "debug", "metadata"):
        value = payload.get(key)
        if value:
            print(f"\n=== {key} ===")
            print(json.dumps(value, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

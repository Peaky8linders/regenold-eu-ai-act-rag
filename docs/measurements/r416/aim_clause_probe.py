"""R416 — where does rg_010's Article 14 *aim* clause actually come from?

THE DISCREPANCY
---------------
* R416 easy gate (in-process TestClient, shipped config, KG=1): ``rg_010`` answered
  in ~1,350 chars WITH the aim clause ("prevent or minimise risks to health,
  safety or fundamental rights"), against ~1,125 chars and NO aim clause on the
  KG=0 arm. The gate credited the clause to the point-text lever.
* Post-deploy live probe (production, the SAME question text byte-for-byte):
  ~470 chars, no aim clause.

Same question, same single-turn modality. This probe isolates the variable. It
records, for each local run, the LENGTH OF THE ``system`` PAYLOAD ACTUALLY
DISPATCHED to the provider (via ``gate_validity.ArmProbe`` at the real transport
seam) — the two candidate levers differ by exactly that, and the answer length
alone cannot tell them apart:

* ``REGENOLD_KG_POINT_TEXT`` changes the **user** payload (the KG block);
* ``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`` (R412, default ON) swaps the
  **system** payload between a 61-char persona and the ~59.6 kB full prompt.

It then runs the same question under both settings of the second flag so the
observable (answer length + aim clause) can be attributed.

    .venv/Scripts/python.exe docs/measurements/r416/aim_clause_probe.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

QUESTION = "Which article of the EU AI Act governs human oversight measures?"
PROD = "https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask"
URL_LOCAL = "local://app.main:app/api/v1/regenold/eu-ai-act/ask?include_reasoning=true"


def _aim(answer: str) -> bool:
    low = answer.lower()
    return "aim" in low or ("health" in low and ("safety" in low or "fundamental rights" in low))


def ask_local(label: str, env: dict[str, str]) -> tuple[str, list[str], float]:
    for k, v in env.items():
        os.environ[k] = v
    from evals.regenold.runner_v2 import _post_local

    t0 = time.perf_counter()
    body, _lat, status, err, _att, _ret = _post_local(URL_LOCAL, None, [{"role": "user", "content": QUESTION}], 600.0)
    dt = time.perf_counter() - t0
    answer = str((body or {}).get("answer") or "")
    refs = list((body or {}).get("references") or [])
    print("=" * 100)
    print(f"[{label}] env={env} chars={len(answer)} aim={_aim(answer)} refs={refs} "
          f"elapsed={dt:.1f}s status={status} err={err}")
    print(f"  {answer!r}")
    return answer, refs, dt


def ask_prod(call: int) -> tuple[str, list[str], float]:
    req = urllib.request.Request(
        PROD,
        data=json.dumps([{"role": "user", "content": QUESTION}]).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
        d = json.loads(resp.read().decode())
    dt = time.perf_counter() - t0
    answer = str(d.get("answer") or "")
    refs = list(d.get("references") or [])
    print("=" * 100)
    print(f"[production #{call}] chars={len(answer)} aim={_aim(answer)} refs={refs} elapsed={dt:.1f}s")
    print(f"  {answer!r}")
    return answer, refs, dt


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    try:
        from app import config  # noqa: F401, PLC0415

        print("app.config loaded (the gate's ordering)")
    except Exception as exc:  # noqa: BLE001
        print(f"app.config import failed: {exc}")

    ask_local("local, KG=1 (gate arm B), shipped defaults", {"REGENOLD_KG_POINT_TEXT": "1"})
    ask_local(
        "local, KG=1 but FULL_SYSTEM_SINGLE_TURN=0",
        {"REGENOLD_KG_POINT_TEXT": "1", "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN": "0"},
    )
    for i in (1, 2):
        ask_prod(i)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

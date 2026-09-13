"""R415 — post-deploy live check, aimed at the two rows the lever costs.

The official-corpus gate (`official_lever_gate.py`) found that this round's
lever costs exactly **two criteria on two rows** out of 90, and both losses are
content omissions in the 41 % shorter answer rather than judge variance:

* ``rg_010`` — "Which article of the EU AI Act governs human oversight
  measures?" — the answer names Article 14 and all five overseer capabilities but
  never states the **aim** (prevent/minimise risks to health, safety, fundamental
  rights).
* ``rg_045`` — the deployer who has reason to believe a high-risk system presents
  a risk — the answer states all three duties but attaches *"without undue
  delay"* to the informing actions only, leaving the **suspension unqualified**.

Those readings come from the offline/reconstructed corpus. This script re-asks
both against the LIVE deployed endpoint so the residual is confirmed on the real
transport (production Stage-2) rather than only in the gate.

WHAT IS ASSERTED vs REPORTED
----------------------------
Asserted: the deploy is healthy, both asks return a non-empty answer with wire
references, and the answer names the operative article. These are properties the
deploy must have.

REPORTED, not asserted: whether the two lost clauses survive. The lever was
shipped ON by measurement (OVERALL +6.1 pp) with this cost accepted and recorded,
so a missing clause here is not a test failure — it is the residual being
re-verified on production, and printing it is the point. Turning it into a red
assert would make the script lie about what the round decided.

    .venv/Scripts/python.exe docs/measurements/r415/live_prod_check.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
URL = f"{BASE}/api/v1/regenold/eu-ai-act/ask"
HEALTHZ = f"{BASE}/healthz"

OVERSIGHT_Q = "Which article of the EU AI Act governs human oversight measures?"
DEPLOYER_RISK_Q = (
    "Under the EU AI Act, if a deployer has reason to believe that the use of a "
    "high-risk AI system may present a risk, what must the deployer do, and whom "
    "must the deployer inform?"
)

CASES = [("rg_010-oversight", OVERSIGHT_Q), ("rg_045-deployer-risk", DEPLOYER_RISK_Q)]


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
    except Exception:  # noqa: BLE001 — odd/older stdouts
        pass

    with urllib.request.urlopen(HEALTHZ, timeout=30) as resp:
        health = json.loads(resp.read().decode("utf-8"))
    print(f"deployed commit: {health.get('commit')}  status={health.get('status')}")

    failures: list[str] = []
    for label, question in CASES:
        try:
            data = ask(question)
        except Exception as exc:  # noqa: BLE001
            print(f"[{label}] request failed: {exc}")
            failures.append(f"{label}: request failed")
            continue
        answer = (data.get("answer") or "").strip()
        refs = data.get("references") or []
        low = answer.lower()
        print("=" * 94)
        print(f"[{label}] chars={len(answer)} refs={refs}")
        print(f"  lead: {answer[:260]!r}")

        if not answer:
            failures.append(f"{label}: empty answer")
        if not refs:
            failures.append(f"{label}: no wire references")

        if label == "rg_010-oversight":
            if "article 14" not in low:
                failures.append(f"{label}: answer does not name Article 14 (got {refs})")
            # The reported residual: Art. 14's AIM clause.
            aim = ("health" in low and ("safety" in low or "fundamental rights" in low))
            print(f"  [reported] Art. 14 aim clause present: {aim}")
        else:
            if not any(r.startswith(("Article 3", "Article 26", "Article 79")) for r in refs):
                print(f"  [note] refs do not obviously match the Art. 26 deployer duty: {refs}")
            # The reported residual: does 'without undue delay' cover the suspension?
            susp = low.find("suspend")
            delay = low.find("undue delay")
            window = ""
            if susp != -1 and delay != -1:
                window = low[min(susp, delay) : max(susp, delay) + 40]
            attached = bool(window) and abs(susp - delay) < 400
            print(
                f"  [reported] 'undue delay' near the suspension: {attached} "
                f"(suspend@{susp}, delay@{delay})"
            )

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("LIVE CHECKS PASSED (the two clause residuals above are reported, not asserted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

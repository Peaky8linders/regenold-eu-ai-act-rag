"""R410 — post-deploy production check on the Antifragile Part II items.

Read-only POSTs to the live deployed endpoint (production Stage-2 is Opus, so
these are polished answers, not the deterministic ones the offline probe pins).
Only the DIRECTLY VERIFIABLE invariants are asserted: the guiding-principles
answer must open with the denial, and the clinical-trial questions must not
assert emergency dispatch.

    .venv/Scripts/python.exe docs/measurements/r409/r410_live_prod_check.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

URL = (
    "https://regenold-eu-ai-act-rag-production.up.railway.app"
    "/api/v1/regenold/eu-ai-act/ask"
)
HEALTHZ = (
    "https://regenold-eu-ai-act-rag-production.up.railway.app/healthz"
)

_CT = (
    "Under the EU AI Act, can a hospital use an AI system to sort patients based "
    "on their biometric data to determine priority for an experimental clinical "
    "trial"
)
CASES = [
    ("q06-guiding-principles", "Does the EU AI Act establish guiding principles for AI?"),
    ("q08-conditional", _CT + "?"),
    ("q09-race", _CT + ", where the system infers each patient's race from that data?"),
    ("q10-sex", _CT + ", where the system infers each patient's sex from that data?"),
    ("q11-physiological", _CT + ", where the system sorts on clinically relevant "
                              "physiological parameters and infers no sensitive or "
                              "protected attribute?"),
]


def ask(question: str) -> dict:
    body = json.dumps([{"role": "user", "content": question}]).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    # The wire carries typographic characters (U+2011 etc.); the default Windows
    # console codec is cp1252 and would raise on print.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — older/odd stdouts
        pass

    with urllib.request.urlopen(HEALTHZ, timeout=30) as resp:
        health = json.loads(resp.read().decode("utf-8"))
    print(f"deployed commit: {health.get('commit')}  status={health.get('status')}")

    wanted = sys.argv[1:]
    cases = [c for c in CASES if not wanted or any(c[0].startswith(w) for w in wanted)]

    failures: list[str] = []
    answers: dict[str, str] = {}
    for label, question in cases:
        try:
            data = ask(question)
        except Exception as exc:  # noqa: BLE001
            print(f"[{label}] request failed: {exc}")
            failures.append(f"{label}: request failed")
            continue
        answer = (data.get("answer") or "").strip()
        answers[label] = answer
        print("=" * 94)
        print(f"[{label}] chars={len(answer)} refs={data.get('references')}")
        print(f"  lead: {answer[:260]!r}")

    q6 = answers.get("q06-guiding-principles", "").lower()
    if q6 and "does not" not in q6:
        failures.append("q06: answer does not carry the denial")
    if q6 and "guiding principles" not in q6:
        failures.append("q06: answer lost the subject")

    for label in ("q08-conditional", "q09-race", "q10-sex", "q11-physiological"):
        low = answers.get(label, "").lower()
        if not low:
            continue
        # The DEFECT was that the VERDICT was emergency dispatch — the
        # Annex III(5)(d) answer for four different facts. A correct, fuller
        # answer may legitimately list emergency triage as one of the eight
        # Annex III areas, so only the LEAD (the verdict sentence) is asserted.
        if "emergency" in low[:400]:
            failures.append(f"{label}: verdict lead asserts emergency dispatch")

    print("\n" + "=" * 94)
    if failures:
        print(f"LIVE PROD CHECK: {len(failures)} unmet:")
        for f in failures:
            print("  -", f)
    else:
        print("LIVE PROD CHECK: all asserted invariants hold.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""R410 — end-to-end wire probe over the Antifragile Part II questions.

Deterministic offline (no Stage-2 provider): exercises the route + engine
intercepts the four R410 fixes touch. Run:

    REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe docs/measurements/r409/r410_wire_probe.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

CLIENT = TestClient(app)


def ask(question: str) -> dict:
    resp = CLIENT.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=[{"role": "user", "content": question}],
    )
    if resp.status_code != 200:
        return {"answer": "", "references": [], "status": resp.status_code}
    return resp.json()


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# The REAL Antifragile Part II items (corrected_question), copy-pasted from
# ``run_antifragile_frontier_judge.py``. Q8-Q11 are the biometric clinical-trial
# triage variants that must resolve to three DIFFERENT statutory branches.
_CT = (
    "Under the EU AI Act, can a hospital use an AI system to sort patients based on "
    "their biometric data to determine priority for an experimental clinical trial"
)

CASES = [
    ("q01-risk-categories", "What risk categories, if any, does the EU AI Act provide for AI systems?"),
    ("q05-minimal-risk", "Does the EU AI Act provide for a category of minimal risk AI systems?"),
    ("q06-guiding-principles", "Does the EU AI Act establish guiding principles for AI?"),
    ("q08-conditional", _CT + "?"),
    ("q09-race-PROHIBITED", _CT + ", where the system infers each patient's race from that data?"),
    ("q10-sex-HIGH-RISK", _CT + ", where the system infers each patient's sex from that data?"),
    ("q11-physiological-FALLBACK", _CT + ", where the system sorts on clinically relevant physiological parameters and infers no sensitive or protected attribute?"),
]

#: Substrings each answer MUST / MUST NOT state, grounded in the gold refs and
#: the Article 5(1)(g) closed list (race|political|trade-union|religious|
#: philosophical|sex life|sexual orientation — `sex` is deliberately absent).
EXPECT = {
    "q01-risk-categories": {"must": ["condition"], "must_not": []},
    "q05-minimal-risk": {
        "must": ["does not"],
        "must_not": [],
    },
    "q06-guiding-principles": {"must": ["does not"], "must_not": []},
    "q08-conditional": {"must": [], "must_not": ["emergency"]},
    "q09-race-PROHIBITED": {"must": ["Article 5"], "must_not": ["emergency"]},
    "q10-sex-HIGH-RISK": {"must": ["high-risk"], "must_not": ["emergency", "5(1)(g)", "5.1.g"]},
    "q11-physiological-FALLBACK": {"must": ["Article 6"], "must_not": ["emergency", "5.1.g"]},
}

if __name__ == "__main__":
    out: dict[str, dict] = {}
    for label, q in CASES:
        data = ask(q)
        answer = strip_tags(data.get("answer", ""))
        refs = data.get("references") or []
        out[label] = {
            "question": q,
            "answer": answer,
            "answer_chars": len(answer),
            "references": refs,
            "lead": answer[:110],
        }
        print("=" * 90)
        print(f"[{label}] {q}")
        print(f"  chars={len(answer)} refs={refs}")
        print(f"  lead: {answer[:170]!r}")

    dest = REPO / "docs" / "measurements" / "r409" / "r410_wire_probe.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {dest}")

    failures: list[str] = []
    for label, exp in EXPECT.items():
        a = out[label]["answer"].lower()
        for token in exp["must"]:
            if token.lower() not in a:
                failures.append(f"{label}: missing required {token!r}")
        for token in exp["must_not"]:
            if token.lower() in a:
                failures.append(f"{label}: contains forbidden {token!r}")

    print("\n" + "=" * 90)
    if failures:
        print(f"WIRE PROBE: {len(failures)} expectation(s) unmet:")
        for f in failures:
            print("  -", f)
    else:
        print("WIRE PROBE: all Part II expectations met.")
    sys.exit(1 if failures else 0)

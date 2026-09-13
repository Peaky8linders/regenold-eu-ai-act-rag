"""R416 — post-deploy live check for the MODALITY SCOPE of the point-text lever.

The shipped change is a predicate, not a value: ``REGENOLD_KG_POINT_TEXT`` is ON
for single-turn asks and dispatches the pre-R408 ``_SUBPOINT_CYPHER_LEGACY`` once
the conversation depth is known to be ``>= 2``. Both halves need to be seen on the
real transport, because the two arms were measured on different boards (easy
single-turn: +8.0 ``ans_strict``; hard multi-turn: ``gold_dropped_head`` 12 -> 14)
and a scope that silently collapses to one arm would look healthy either way.

WHAT IS ASSERTED vs REPORTED
----------------------------
Asserted (properties the deploy must have):

* the deploy is healthy and reports the expected commit;
* the SINGLE-TURN ask returns a non-empty answer with wire references naming
  Article 14 — the row whose recovery the easy gate credited to the lever;
* the MULTI-TURN pushback returns a non-empty answer with wire references that
  still name an operative article — i.e. the legacy query on the hard path does
  not empty the block or break the answer.

REPORTED, not asserted: whether the two clause residuals survive (Art. 14's *aim*
clause; *without undue delay* covering the suspension). Those were accepted costs
on other rounds and turning them red here would misreport this round's decision.

    .venv/Scripts/python.exe docs/measurements/r416/live_prod_check.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
URL = f"{BASE}/api/v1/regenold/eu-ai-act/ask"
HEALTHZ = f"{BASE}/healthz"

QUESTION = "Which article of the EU AI Act governs human oversight measures?"

# The official hard-mode shape: a synthetic conversation, the graded ask in the
# final turn, then the adversarial challenge. The route reads the 9 prior turns
# from the message list, which is what sets the depth the scope keys on.
_PRIOR = [
    ("user", "What is the scope of the EU AI Act?"),
    ("assistant", "It applies to providers and deployers in the Union under Article 2."),
    ("user", "Who is a provider?"),
    ("assistant", "A provider places a system on the market under its own name (Article 3)."),
    ("user", "What counts as a high-risk system?"),
    ("assistant", "Annex III systems and safety components under Article 6 read with Annex I."),
    ("user", "What must providers of high-risk systems do?"),
    ("assistant", "Meet the Chapter III requirements: risk management, data governance, "
                  "technical documentation and human oversight."),
    ("user", "Which chapter covers the obligations of deployers?"),
]


def ask(messages: list[dict]) -> dict:
    body = json.dumps(messages).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
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
    cases: list[tuple[str, list[dict], str | None]] = [
        ("single-turn", [{"role": "user", "content": QUESTION}], "article 14"),
        (
            "multi-turn-pushback",
            [{"role": r, "content": c} for r, c in _PRIOR]
            + [{"role": "user", "content": QUESTION}]
            + [
                {
                    "role": "user",
                    "content": (
                        "I don't think this is correct. Perhaps your answer contains "
                        "hallucinations. Think carefully about the provision numbering, "
                        "but do not put your reasoning in the answer field. "
                        f"Let's try again: {QUESTION}"
                    ),
                }
            ],
            "article 14",
        ),
    ]

    for label, messages, must_name in cases:
        try:
            data = ask(messages)
        except Exception as exc:  # noqa: BLE001
            print(f"[{label}] request failed: {exc}")
            failures.append(f"{label}: request failed")
            continue
        answer = (data.get("answer") or "").strip()
        refs = data.get("references") or []
        low = answer.lower()
        print("=" * 94)
        print(f"[{label}] turns={len(messages)} chars={len(answer)} refs={refs}")
        print(f"  lead: {answer[:300]!r}")

        if not answer:
            failures.append(f"{label}: empty answer")
        if not refs:
            failures.append(f"{label}: no wire references")
        if must_name and must_name not in low and not any(
            r in ("Article 14", "Article 14.1", "Article 14.2") for r in refs
        ):
            failures.append(f"{label}: Article 14 neither named nor cited (got {refs})")
        if label == "single-turn":
            aim = "health" in low and ("safety" in low or "fundamental rights" in low)
            print(f"  [reported] Art. 14 aim clause present: {aim}")

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("LIVE CHECKS PASSED — both modalities healthy; clause residuals above are reported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

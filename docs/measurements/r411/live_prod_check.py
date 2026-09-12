"""R411 — post-deploy production check for the mention-vs-ask and Art. 113 fixes.

Read-only POSTs to the live deployed endpoint. Production Stage-2 is Opus, so
these are polished answers, not the deterministic drafts the offline probes pin.

The two live defects this verifies were both observed on the PREVIOUS deploy:

1. *"If a provider relies on the Article 6(3) derogation for an Annex III system,
   what documentation and registration duties apply?"* was answered with the
   ``rg_031`` classification verdict ("No. Structuring or deduplicating
   information is a narrow procedural task ...") — a fluent answer to a question
   nobody asked, because ``_detect_article_6_3_inquiry`` fired on the bare
   MENTION of "Article 6(3)" and short-circuited Stage-2.
2. The same request shipped wire refs ``['Article 49.2', 'Article 6.3',
   'Article 113.3']`` — the ``Article 113.3`` came from ``_APPLICABILITY_CUE_RE``
   matching the bare word "apply" in "what documentation and registration duties
   apply?".

Assertions are kept to what is directly verifiable from the response.

    .venv/Scripts/python.exe docs/measurements/r411/live_prod_check.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

URL = (
    "https://regenold-eu-ai-act-rag-production.up.railway.app"
    "/api/v1/regenold/eu-ai-act/ask"
)
HEALTHZ = "https://regenold-eu-ai-act-rag-production.up.railway.app/healthz"

# The defect question. It MENTIONS Article 6(3) but ASKS about the Article 6(4)
# documentation duty and the Article 49(2) registration duty.
DUTIES_Q = (
    "If a provider relies on the Article 6(3) derogation for an Annex III system, "
    "what documentation and registration duties apply?"
)

# The R356 task shape the intercept EXISTS for. It must still get the verdict.
CLASSIFICATION_Q = (
    "Is an AI system used to structure or deduplicate information for a use case "
    "listed in Annex III considered high-risk?"
)

CASES = [
    ("duties-after-6-3-mention", DUTIES_Q),
    ("classification-task-shape", CLASSIFICATION_Q),
]

# The stock curated Article 6(3) verdict's DISTINCTIVE phrase, verified live:
#   "No. Structuring or deduplicating information is a narrow procedural task, so
#    the system falls under the Article 6(3) first subparagraph point (a)
#    derogation and is not high-risk ..."
# NOTE: matched on "narrow procedural task", not on "not considered high-risk".
# The live wording is "is not high-risk"; an earlier cut of this probe asserted
# the "considered" spelling and reported a false FAILURE of the intercept's own
# recall. Assert the phrase the verdict actually uses.
VERDICT_PHRASE = "narrow procedural task"


def ask(question: str) -> dict:
    body = json.dumps([{"role": "user", "content": question}]).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    # The wire carries typographic characters; the default Windows console codec
    # is cp1252 and would raise on print.
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
    for label, question in cases:
        try:
            data = ask(question)
        except Exception as exc:  # noqa: BLE001
            print(f"[{label}] request failed: {exc}")
            failures.append(f"{label}: request failed")
            continue
        answer = (data.get("answer") or "").strip()
        refs = data.get("references") or []
        print("=" * 94)
        print(f"[{label}] chars={len(answer)} refs={refs}")
        print(f"  lead: {answer[:300]!r}")

        low = answer.lower()
        if label == "duties-after-6-3-mention":
            # 1. it must NOT be the stock classification verdict.
            if VERDICT_PHRASE in low:
                failures.append(
                    "duties-after-6-3-mention: still answered with the stock "
                    "Article 6(3) classification verdict"
                )
            # 2. the Art. 113 date seed must not fire on a bare "apply".
            if any(r.startswith("Article 113") for r in refs):
                failures.append(
                    f"duties-after-6-3-mention: applicability seed still fired "
                    f"(refs={refs})"
                )
            # 3. REPORTED, NOT ASSERTED — the residual the fix does NOT cover.
            # The guarantee here is narrow: the intercept no longer hijacks a
            # mention. What the fallback path then answers is a separate,
            # retrieval/relevance question (measured live: the answer explains
            # the Article 6(1)/6(2) classification routes and names neither
            # Article 6(4) nor Article 49(2), so it is still off the ask).
            if "6(4)" not in answer and "49(2)" not in answer:
                print(
                    "  [note] residual: the fallback answer names neither "
                    "Article 6(4) nor Article 49(2) — the duties actually asked "
                    "about. Out of scope for the mention gate."
                )
        if label == "classification-task-shape":
            if VERDICT_PHRASE not in low:
                failures.append(
                    "classification-task-shape: the intercept no longer fires on "
                    "the R356 task shape it exists for"
                )
            if not any(r.startswith("Article 6.3") for r in refs):
                failures.append(
                    f"classification-task-shape: expected an Article 6.3.x wire "
                    f"ref, got {refs}"
                )

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

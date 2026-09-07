"""R388 - calibrate the reconstructed judge against the evaluator's OWN verdicts.

The 2026-08-25 report's appendix prints six questions in full: the question,
the candidate answer we shipped, the evaluator's correctness criteria, and its
PASS/FAIL verdict on every one of them, with reasoning.  That is seventeen
criterion-level judgements of known ground truth -- the only direct evidence
anywhere of how the official judge actually behaves.

This module replays them.

Two-sided by construction
-------------------------
The appendix is an "examples of INCORRECT answers" section, so sixteen of the
seventeen printed verdicts are FAIL.  A judge that returned FAIL unconditionally
would score 16/17 on that set, which makes the negative direction almost
worthless on its own.  So the harness runs a second arm: the SAME criteria
judged against a known-good answer (the reconstructed reference answer for that
question), where the expected verdict is PASS on essentially everything.  A
judge only calibrates if it clears BOTH.

    .venv/Scripts/python.exe -m evals.official.calibration
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
sys.path.insert(0, str(REPO))

from evals.official.judge import judge_row  # noqa: E402

# --- the appendix, transcribed verbatim from report_antifragile_ai.pdf -------
# Question numbers are the evaluator's own 1-110 index, which does NOT map onto
# our rg_NNN ids; the question text is what identifies the row.

APPENDIX: list[dict] = [
    {
        "qid": "Q45",
        "mode": "easy",
        "question": (
            "Under the EU AI Act, what must a provider of a high-risk AI system supply to the "
            "deployer in the instructions for use? List the required categories of information."
        ),
        "expected_refs": ["Article 13.3"],
        "criteria": [
            "Provider and if applicable authorised representative contact details",
            "Intended purpose and risks",
            "Human oversight measures",
            "Required computational resources/hardware, expected lifetime, maintaince measures",
            "Info about logging mechanisms",
        ],
        "printed_verdicts": [False, False, False, False, False],
        "answer": (
            "The question asks what a provider of a high-risk AI system must include in the "
            "instructions for use. The Act does specify those categories in Article 13, but the "
            "materials available here do not permit a citation-supported enumeration of them. A "
            "complete answer to this question turns on Article 13 and, for the detailed content "
            "list, on the requirements it sets out for transparency and provision of information "
            "to deployers."
        ),
    },
    {
        "qid": "Q96",
        "mode": "easy",
        "question": "Name the areas of high-risk use cases. Is healthcare decision making one of them?",
        "expected_refs": ["Annex III"],
        "criteria": [
            "Biometrics; Critical infrastructure; Education; Employment; Access/enjoyment "
            "essential services; Law enforcement; Migration/asylum/border control; "
            "Justice/democracy administration",
            "No",
        ],
        "printed_verdicts": [False, False],
        "answer": (
            "I cannot answer your question from my Knowledge Graph, which address only obligations "
            "under Regulation (EU) 2024/1689 (the AI Act), such as AI literacy duties for providers "
            "and deployers (Article 4), coordination of notified bodies (Article 38), and access to "
            "the Scientific Panel's expert pool (Article 69). If you have a question about AI Act "
            "compliance, I am glad to help."
        ),
    },
    {
        "qid": "Q17",
        "mode": "easy",
        "question": (
            "Can the European Commission amend Annex III of the EU AI Act to add or modify "
            "use-cases classified as high-risk AI systems? Under what conditions?"
        ),
        "expected_refs": ["Article 7.1"],
        "criteria": [
            "Yes",
            "Condition: AI intended to be used in any of the areas listed in Annex III",
            "Condition: posed risk is equal or greater than those already referred to in Annex III",
            'Both condition must apply ("and" clause)',
        ],
        "printed_verdicts": [True, False, False, False],
        "answer": (
            "The Commission is empowered to amend Annex III by adding new use cases or modifying "
            "existing ones through delegated acts adopted in accordance with Article 97, subject to "
            "the conditions set out in Article 7(1). Article 6(2) makes the Annex III use cases "
            "high-risk, and Article 6(6) empowers the Commission to adopt delegated acts to amend "
            "the derogation conditions in Article 6(3), but the power to amend the list of use cases "
            "in Annex III itself is conferred by a separate provision (Article 7) that the Act does "
            "not settle within the text supplied here. The Act does not specify the full conditions "
            "for amending Annex III within the provisions of Article 6 or Annex III alone."
        ),
    },
    {
        "qid": "Q74",
        "mode": "hard",
        "question": (
            "I generated audio with AI for my artistic work (sole purpose). Do I need to provide "
            "some marking of its artificial nature? I feel that would compromise the enjoyment of "
            "the work."
        ),
        "expected_refs": ["Article 50.4"],
        "criteria": [
            "No need of marking that would compromise enjoyment",
            "Still required: other form of disclosure that such content exist (must be unambiguous "
            "in the answer)",
        ],
        "printed_verdicts": [False, False],
        "answer": (
            "Yes. The provider of an AI system generating synthetic audio must ensure the outputs "
            "are marked in a machine-readable format and detectable as artificially generated or "
            "manipulated, with technical solutions that are effective, interoperable, robust and "
            "reliable, under Article 50(2). Artistic purpose is not a carve-out from that marking "
            "duty, which is displaced only to the extent the system performs an assistive function "
            "for standard editing or does not substantially alter the input data or its semantics, "
            "or where authorised by law to detect, prevent, investigate or prosecute criminal "
            "offences. The artistic, creative, satirical or fictional limitation applies to the "
            "separate deployer duty to disclose deep fake content under Article 50(4), where "
            "disclosure is limited to an appropriate manner that does not hamper the display or "
            "enjoyment of the work."
        ),
    },
    {
        "qid": "Q95",
        "mode": "hard",
        "question": (
            'What is an "area" and what is a "use case" for high-risk as per Article 6(2)? '
            "How many areas exist?"
        ),
        "expected_refs": ["Article 6.2", "Annex III"],
        "criteria": ["Area contain use cases", "8 areas exist"],
        "printed_verdicts": [False, False],
        "answer": (
            "Classifies an AI system as high-risk on two routes. Annex I route (Article 6(1)): the "
            "system is a safety component of, or is itself, a product covered by the Union "
            "harmonisation legislation listed in Annex I AND that product must undergo a "
            "third-party conformity assessment under that sectoral legislation. Annex III route "
            "(Article 6(2)): the system falls within one of the eight Annex III use cases. Article "
            "6(3) derogation: an Annex III system is NOT high-risk where it poses no significant "
            "risk of harm and meets one of four conditions (a narrow procedural task; improving the "
            "result of a previously completed human activity; detecting decision-making patterns or "
            "deviations without replacing or influencing the human assessment; or a preparatory "
            "task), unless it profiles natural persons, in which case it is always high-risk; the "
            "provider must document this self-assessment before placing the system on the market "
            "and still register it under Article 49(2). Carve-out: an Annex-III system is NOT "
            "high-risk if it doesn't pose a significant risk of harm AND one of four conditions is "
            "met, (a) performs a narrow procedural task; (b) improves the result of a previously "
            "completed human activity; (c) detects decision-making patterns or deviations without "
            "replacing the human assessment; (d) performs a preparatory task to an Annex-III use "
            "case. Provider must document the assessment before placing on market and still "
            "register the system per Article 49(2)."
        ),
    },
    {
        "qid": "Q104",
        "mode": "hard",
        "question": "What is Annex X about? What is it used for?",
        "expected_refs": ["Article 111.1", "Annex X"],
        "criteria": [
            "Annex X lists Union legal acts for large-scale IT systems",
            "Used to define systems with specific transition and compliance timelines",
        ],
        "printed_verdicts": [False, False],
        "answer": (
            "Annex X sets the information that providers (and, where applicable, authorised "
            "representatives) and public-authority deployers must enter in the EU database when "
            "registering high-risk AI systems referred to in Article 49: provider / "
            "authorised-representative / deployer identity + contact details, system name + trade "
            "name + additional unambiguous reference, intended purpose, status of the system (on "
            "the market / in service / no longer placed on the market / recalled), type + number of "
            "the conformity-assessment certificate + identity of the issuing notified body where "
            "applicable, Member States in which the system is placed on the market or put into "
            "service, and a copy of the EU declaration of conformity (Article 47) + the "
            "instructions for use. Public-access carve-outs in Annex X apply to law-enforcement, "
            "migration, asylum, and border-control systems. GPAI provider obligations: maintain "
            "technical documentation per Annex XI, supply downstream-provider information per Annex "
            "XII, implement a copyright policy, and publish a sufficiently detailed training-data "
            "summary. Where the model meets the Article 51 systemic-risk threshold (10^25 FLOPs "
            "cumulative training compute), the additional Article 55 obligations apply on top."
        ),
    },
]


def run(positive_answers: dict[str, str] | None = None) -> dict:
    """Replay the appendix. ``positive_answers`` maps qid -> a known-good answer."""
    neg_rows, pos_rows = [], []
    for case in APPENDIX:
        neg_rows.append(dict(case))
        good = (positive_answers or {}).get(case["qid"])
        if good:
            pos = dict(case)
            pos["answer"] = good
            pos_rows.append(pos)

    def _score(rows, label):
        agree = total = 0
        detail = []
        for r in rows:
            got = judge_row(r)["criteria"]
            exp = r["printed_verdicts"] if label == "negative" else [True] * len(r["criteria"])
            for i, (g, e) in enumerate(zip(got, exp), 1):
                total += 1
                agree += int(bool(g) == bool(e))
                if bool(g) != bool(e):
                    detail.append(
                        f"{r['qid']} criterion {i}: judge={'PASS' if g else 'FAIL'} "
                        f"expected={'PASS' if e else 'FAIL'} :: {r['criteria'][i-1][:70]}"
                    )
        return {"agree": agree, "total": total, "rate": round(agree / total, 4) if total else 0.0,
                "disagreements": detail}

    out = {"negative": _score(neg_rows, "negative")}
    if pos_rows:
        out["positive"] = _score(pos_rows, "positive")
    return out


def main() -> int:
    pos_path = REPO / "docs" / "measurements" / "r388" / "calibration_positive_answers.json"
    positive = json.loads(pos_path.read_text(encoding="utf-8")) if pos_path.exists() else None
    res = run(positive)

    print("=" * 72)
    print("R388 judge calibration against the report's printed appendix verdicts")
    print("=" * 72)
    neg = res["negative"]
    print(f"\nNEGATIVE arm (the shipped answers the evaluator judged):")
    print(f"  agreement {neg['agree']}/{neg['total']} = {neg['rate']*100:.1f}%")
    for d in neg["disagreements"]:
        print(f"    ! {d}")
    if "positive" in res:
        pos = res["positive"]
        print(f"\nPOSITIVE arm (a known-good answer, same criteria):")
        print(f"  agreement {pos['agree']}/{pos['total']} = {pos['rate']*100:.1f}%")
        for d in pos["disagreements"]:
            print(f"    ! {d}")
    else:
        print("\nPOSITIVE arm: SKIPPED - no calibration_positive_answers.json.")
        print("  A negative-only calibration is WEAK: 16 of the 17 printed verdicts are FAIL,")
        print("  so an always-FAIL judge scores 94% on it. Generate the positive arm before")
        print("  quoting this number as evidence the judge is calibrated.")

    out_path = REPO / "docs" / "measurements" / "r388" / "calibration.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

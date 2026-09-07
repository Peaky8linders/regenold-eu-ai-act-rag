"""R388 - generate the POSITIVE arm of the judge calibration.

The report's appendix is an "incorrect answers" section: 16 of its 17 printed
verdicts are FAIL, so a judge that always says FAIL scores 94% against it.  The
negative arm alone therefore cannot distinguish a calibrated judge from a
broken one.

This writes the other half: for each appendix question, an answer that DOES
state every fact the evaluator's own criteria demand, grounded on the verbatim
provisions.  The judge should return PASS on essentially all of them.  A judge
that fails these is over-strict; one that passes the negative arm's answers is
over-lenient.  Only clearing both is calibration.

    .venv/Scripts/python.exe -m evals.official._make_positive_arm
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
sys.path.insert(0, str(REPO))

from evals.official.build_gold import call  # noqa: E402
from evals.official.calibration import APPENDIX  # noqa: E402
from evals.official.judge import _provisions_for  # noqa: E402

PROMPT = """You are a regulatory lawyer answering a question on the EU AI Act (Regulation (EU) 2024/1689).

Write an answer that is CORRECT and that unambiguously states each of the required facts listed below. State the substance of each fact in your own prose - do not merely cite the provision that contains it, and do not list the facts as bullet points.

Keep it to 3-5 sentences of plain professional regulatory prose. Answer only what was asked.

VERBATIM STATUTORY TEXT:
{provisions}

QUESTION:
{question}

REQUIRED FACTS (each must be unambiguously stated in your answer):
{criteria}

Return ONLY the answer prose. No preamble, no JSON, no markdown."""


def main() -> int:
    out: dict[str, str] = {}
    for case in APPENDIX:
        prompt = PROMPT.format(
            provisions=_provisions_for(case["expected_refs"]),
            question=case["question"],
            criteria="\n".join(f"- {c}" for c in case["criteria"]),
        )
        text = call(prompt, max_tokens=900).strip()
        out[case["qid"]] = text
        print(f"{case['qid']}: {len(text)} chars")
        print(f"   {text[:200]}...")
    path = REPO / "docs" / "measurements" / "r388" / "calibration_positive_answers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

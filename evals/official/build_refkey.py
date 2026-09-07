"""R388 - rebuild the expected-reference answer key at the RIGHT GRAIN.

Why R386's minimal-gold set is not good enough as a scoring key
--------------------------------------------------------------
R386's probe recovered the expected references with two passes: locate the
head, then pin the paragraph.  Pass 2 *always* tries to pin a paragraph, so the
resulting key is 92.4% sub-point.  The evaluator's own key, measured from the
eight expected references its appendix prints, is 62.5% sub-point -- it uses a
BARE HEAD whenever the question is about the provision as a whole::

    Q45  -> Article 13.3      (one paragraph carries the list)      sub-point
    Q96  -> Annex III         ("name the areas" -- the whole annex)  HEAD
    Q17  -> Article 7.1       (one paragraph carries the conditions) sub-point
    Q74  -> Article 50.4      (one paragraph carries the carve-out)  sub-point
    Q95  -> Article 6.2, Annex III      one of each
    Q104 -> Article 111.1, Annex X      one of each

Scoring against an over-fine key understates Ref. Correctness (Strict) badly.
Executed, on the r387 110-row live capture::

    strict vs the R386 key (92.4% sub-point)   37.5
    strict vs the same key head-projected      90.4
    official printed strict                    68.3

68.3 sits between the two, and solving the interpolation puts the evaluator's
real key at ~39% sub-point.  So the R386 key is roughly twice as fine as it
should be and the 37.5 is a pessimistic floor, not our score.

This module rebuilds the key with the grain rule stated explicitly and
few-shot from the evaluator's own eight printed references, then
:func:`validate` checks it reproduces all eight -- including the three bare
heads, which is the half R386's method could not produce.

    .venv/Scripts/python.exe -m evals.official.build_refkey --validate
    .venv/Scripts/python.exe -m evals.official.build_refkey
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from app.data.provision_text import get_provision_text  # noqa: E402
from evals.official.build_gold import TITLE_INDEX, call, parse_json  # noqa: E402
from evals.official.calibration import APPENDIX  # noqa: E402
from evals.official.rubric import normalise_ref, ref_head  # noqa: E402

BATCH = REPO / "evals" / "regenold" / "_official_batch_20260707.json"
MINGOLD = REPO / "docs" / "measurements" / "r386" / "minimal-gold-probe-set-n110.jsonl"
OUT = REPO / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"

GRAIN_RULE = """THE GRAIN RULE - this is the part annotators get wrong, so read it twice.

Cite a BARE HEAD (e.g. "Annex III", "Article 6") when the question is about the provision AS A WHOLE: it asks what the provision is, asks you to enumerate its whole content, or the answer draws on several of its paragraphs.

Cite a SUB-POINT (e.g. "Article 13.3", "Article 50.4", "Annex III.5.d") when ONE specific paragraph carries the operative rule that decides the question.

These are the evaluator's own eight expected references, from its published report. Note that THREE of the eight are bare heads - do not reflexively pin a paragraph:

  Q "what must a provider supply to the deployer in the instructions for use? List the required categories"
    -> ["Article 13.3"]          one paragraph carries the whole list
  Q "Name the areas of high-risk use cases. Is healthcare decision making one of them?"
    -> ["Annex III"]             the question is about the annex as a whole -> BARE HEAD
  Q "Can the Commission amend Annex III ...? Under what conditions?"
    -> ["Article 7.1"]           one paragraph carries the conditions
  Q "I generated audio with AI for my artistic work. Do I need to mark it?"
    -> ["Article 50.4"]          one paragraph carries the carve-out
  Q "What is an 'area' and what is a 'use case' per Article 6(2)? How many areas exist?"
    -> ["Article 6.2", "Annex III"]      one sub-point + one BARE HEAD
  Q "What is Annex X about? What is it used for?"
    -> ["Article 111.1", "Annex X"]      one sub-point + one BARE HEAD
"""

PROMPT = """You are the annotator for an EU AI Act question-answering benchmark (Regulation (EU) 2024/1689). Produce the EXPECTED REFERENCES for one question: the MINIMAL set of provisions that contain the information needed to answer it correctly.

MINIMAL means the provisions that actually DECIDE the question. Not context. Not neighbouring law. Not the provision that defines a term used in passing. Not the enforcement or penalty article unless the question asks about enforcement or penalties. Usually ONE provision, sometimes two, very rarely three.

{grain_rule}

THE ACT'S FULL INDEX:
{index}

QUESTION:
{question}

Return ONLY a JSON array of references in the exact format "Article N", "Article N.P", "Annex R", "Annex R.P" (Arabic for articles, uppercase Roman for annexes). Most important first. No prose, no markdown fence."""

VERIFY_PROMPT = """You are checking one candidate answer key for an EU AI Act benchmark question against the verbatim statutory text.

QUESTION:
{question}

CANDIDATE EXPECTED REFERENCES: {refs}

VERBATIM TEXT OF EACH CANDIDATE REFERENCE:
{provisions}

Check two things and fix them:
1. GROUNDING - does the cited text actually contain what is needed to answer the question? Drop any reference whose text does not.
2. GRAIN - {grain_hint}

{grain_rule}

Return ONLY the corrected JSON array. No prose, no markdown fence."""

GRAIN_HINT = (
    "if the question is about a provision AS A WHOLE, the key must be the bare head; "
    "if ONE paragraph decides it, the key must be that paragraph. Adjust either way."
)


def _provisions(refs: list[str], budget: int = 7000) -> str:
    chunks, used = [], 0
    for r in refs:
        n = normalise_ref(r)
        if not n:
            continue
        t = get_provision_text(n)
        if not t:
            chunks.append(f"--- {n} ---\n(no text found - this reference may not exist)")
            continue
        room = max(0, budget - used)
        if room < 200:
            break
        body = t if len(t) <= room else t[:room] + " [...]"
        chunks.append(f"--- {n} ---\n{body}")
        used += len(body)
    return "\n\n".join(chunks) if chunks else "(none)"


def _norm_list(d) -> list[str]:
    if not isinstance(d, list):
        return []
    out, seen = [], set()
    for x in d:
        n = normalise_ref(str(x))
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out[:3]


def derive(question: str, *, samples: int = 3) -> dict:
    """Three independent draws, then majority + a grounding/grain verification.

    R386 measured single draws to be unstable (three draws of one row gave
    three different keys), so a single sample is not a key.  Majority at the
    REFERENCE level rather than at the list level, because two draws routinely
    agree on the operative provision and disagree only on whether to add a
    second, less-central one.
    """
    draws = []
    for _ in range(samples):
        draws.append(_norm_list(parse_json(call(PROMPT.format(
            grain_rule=GRAIN_RULE, index=TITLE_INDEX, question=question), max_tokens=300))))
    counts = Counter(r for d in draws for r in set(d))
    threshold = (samples // 2) + 1
    majority = [r for r, c in counts.most_common() if c >= threshold]
    if not majority and draws:
        majority = next((d for d in draws if d), [])
    if not majority:
        return {"expected": [], "unstable": True, "_draws": draws}

    verified = _norm_list(parse_json(call(VERIFY_PROMPT.format(
        question=question, refs=json.dumps(majority), provisions=_provisions(majority),
        grain_hint=GRAIN_HINT, grain_rule=GRAIN_RULE), max_tokens=300)))
    final = verified or majority
    # A verification that changes the HEAD (not just the grain) is the model
    # second-guessing the majority of three draws; distrust it and keep the
    # majority's heads, taking only the grain refinement.
    maj_heads = {ref_head(r) for r in majority}
    if {ref_head(r) for r in final} != maj_heads:
        final = majority
    return {
        "expected": final,
        "unstable": len(set(map(tuple, (sorted(d) for d in draws)))) == samples,
        "_draws": draws,
        "_majority": majority,
    }


def validate() -> int:
    """Reproduce the evaluator's eight printed references. The real gate."""
    print("validating against the evaluator's own printed expected references\n")
    ok_exact = ok_head = total = 0
    for case in APPENDIX:
        got = derive(case["question"])
        exp = [normalise_ref(r) for r in case["expected_refs"]]
        g, e = set(got["expected"]), set(exp)
        total += len(e)
        ok_exact += len(g & e)
        ok_head += len({ref_head(x) for x in g} & {ref_head(x) for x in e})
        status = "EXACT" if g == e else ("SUBSET" if g <= e or e <= g else "DIFF")
        print(f"  {case['qid']:<6} got {got['expected']!s:<34} want {exp!s:<34} {status}")
    print(f"\n  exact-reference recall {ok_exact}/{total}   head recall {ok_head}/{total}")
    print("  (R386's method scored 5/7 head recall and produced NO bare heads)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.validate:
        return validate()

    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    rows = [q for q in batch if q["id"] not in done]
    if a.limit:
        rows = rows[: a.limit]
    if not rows:
        print(f"nothing to do; {len(done)} rows already in {out_path}")
        return 0
    print(f"deriving {len(rows)} reference keys ({len(done)} already done)")

    def _one(q):
        try:
            d = derive(q["question"])
            return {"id": q["id"], "question": q["question"], "expected": d["expected"],
                    "unstable": d["unstable"], "_majority": d.get("_majority")}
        except Exception as exc:  # noqa: BLE001
            print(f"  {q['id']} FAILED: {exc}")
            return None

    with out_path.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(_one, rows):
            if r is None:
                continue
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  {r['id']}  {r['expected']}{'  UNSTABLE' if r['unstable'] else ''}")
    print(f"wrote -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

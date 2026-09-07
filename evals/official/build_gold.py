"""R388 - reconstruct the two gold inputs the evaluator never published.

The official rubric needs three per-question inputs.  One of them survives:

* ``expected references`` -- recovered by R386's minimal-gold probe
  (``docs/measurements/r386/minimal-gold-probe-set-n110.jsonl``), validated
  against the five keys the report prints: 3 EXACT, 2 a subset; precision 7/7,
  grain 5/5, recall 5/7.

The other two do not, and are rebuilt here:

* ``correctness criteria`` -- the atomic facts a correct answer must contain.
  The report grades Ans. Correctness against these, NOT against a reference
  answer.
* ``reference answer``     -- an exemplary correct answer, used only to
  estimate whether the candidate is more verbose than necessary.

Method, and why it is shaped this way
-------------------------------------
1. **Question-only.**  The generator never sees our answer, our references,
   the July-7 answers, or any judge output.  If it did, the criteria would be
   shaped by what we happen to say and the instrument would grade us against
   ourselves -- the exact defect R381 found in the July-7 judge, where a
   one-char key mismatch made it score us against our own references on 24/24
   rows.
2. **Few-shot on the report's own worked examples.**  The appendix prints six
   questions with their real criteria.  Their style is highly specific: terse,
   atomic, one substantive fact each, and a bare ``Yes``/``No`` criterion when
   the question asks for a verdict.  Those six are quoted verbatim as the
   style contract.
3. **Double-sampled and reconciled.**  R386 measured single draws to be
   unstable (three draws of one row gave three different keys).  Two
   independent samples are generated and a third call reconciles them; a row
   whose two samples disagree on the COUNT of criteria by more than one is
   flagged ``unstable`` and reported separately rather than silently trusted.
4. **Grounded on verbatim text.**  Every criterion must be supported by the
   verbatim provisions of the expected references, which are supplied in full.

Calibration
-----------
The implied mean reference-answer length is ~640 characters (see
:func:`evals.official.rubric.answer_conciseness` for the derivation).  This
module targets that band explicitly and :mod:`evals.official.calibration`
checks the realised mean, because an instrument whose references are longer
than the evaluator's would flatter us on Ans. Conciseness.

Usage
-----
    .venv/Scripts/python.exe -m evals.official.build_gold --limit 5
    .venv/Scripts/python.exe -m evals.official.build_gold           # all 110
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, str(REPO))

from app.data.official_eu_ai_act import (  # noqa: E402
    OFFICIAL_ANNEX_TITLES,
    OFFICIAL_ARTICLE_TITLES,
)
from app.data.provision_text import get_provision_text  # noqa: E402
from evals.official.rubric import normalise_ref, ref_head  # noqa: E402

BATCH = REPO / "evals" / "regenold" / "_official_batch_20260707.json"
MINGOLD = REPO / "docs" / "measurements" / "r386" / "minimal-gold-probe-set-n110.jsonl"
OUT_DIR = REPO / "docs" / "measurements" / "r388"
OUT = OUT_DIR / "official_gold_n110.jsonl"

URL = os.getenv("R388_WRAPPER_URL", "http://127.0.0.1:8000/v1/chat/completions")
MODEL = os.getenv("R388_GOLD_MODEL", "claude-sonnet-5")

_HDRS = {
    # A bare urllib UA trips Cloudflare error 1010 on the tunnel (a 403 that
    # looks exactly like an auth failure).  Always send a browser UA.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Authorization": "Bearer dummy",
}
if os.getenv("CF_ACCESS_CLIENT_ID"):
    _HDRS["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
    _HDRS["CF-Access-Client-Secret"] = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")


def call(prompt: str, *, max_tokens: int = 1600, timeout: float = 300.0, retries: int = 3) -> str:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
    ).encode()
    last: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers=_HDRS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            return d["choices"][0]["message"]["content"] or ""
        except Exception as exc:  # noqa: BLE001 - network, retried
            last = exc
    raise RuntimeError(f"wrapper call failed after {retries} attempts: {last}")


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def parse_json(text: str) -> dict | list | None:
    t = _FENCE.sub("", text or "").strip()
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = t.find(opener), t.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(t[i : j + 1])
            except Exception:  # noqa: BLE001
                continue
    return None


def _sort_key(k: str):
    if k.startswith("Article "):
        return (0, int(k.split()[1]))
    romans = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
    r = k.split()[1]
    return (1, romans.index(r) if r in romans else 99)


TITLE_INDEX = "\n".join(
    f"{k} - {v}"
    for k, v in sorted(
        {**OFFICIAL_ARTICLE_TITLES, **OFFICIAL_ANNEX_TITLES}.items(), key=lambda kv: _sort_key(kv[0])
    )
)

# The six worked examples the 2026-08-25 report prints verbatim in its
# appendix.  These are the evaluator's OWN criteria, so they are the style
# contract -- note the terseness, the atomicity, the bare-verdict criterion,
# and the human typo in Q45 #4 (reproduced as printed).
FEWSHOT = """Here are SIX real annotated examples from this exact benchmark, printed verbatim in the evaluator's own report. Match this style precisely.

Q: "Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in the instructions for use? List the required categories of information."
criteria:
  1. Provider and if applicable authorised representative contact details
  2. Intended purpose and risks
  3. Human oversight measures
  4. Required computational resources/hardware, expected lifetime, maintaince measures
  5. Info about logging mechanisms

Q: "Name the areas of high-risk use cases. Is healthcare decision making one of them?"
criteria:
  1. Biometrics; Critical infrastructure; Education; Employment; Access/enjoyment essential services; Law enforcement; Migration/asylum/border control; Justice/democracy administration
  2. No

Q: "Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?"
criteria:
  1. Yes
  2. Condition: AI intended to be used in any of the areas listed in Annex III
  3. Condition: posed risk is equal or greater than those already referred to in Annex III
  4. Both condition must apply ("and" clause)

Q: "I generated audio with AI for my artistic work (sole purpose). Do I need to provide some marking of its artificial nature? I feel that would compromise the enjoyment of the work."
criteria:
  1. No need of marking that would compromise enjoyment
  2. Still required: other form of disclosure that such content exist (must be unambiguous in the answer)

Q: "What is an \\"area\\" and what is a \\"use case\\" for high-risk as per Article 6(2)? How many areas exist?"
criteria:
  1. Area contain use cases
  2. 8 areas exist

Q: "What is Annex X about? What is it used for?"
criteria:
  1. Annex X lists Union legal acts for large-scale IT systems
  2. Used to define systems with specific transition and compliance timelines
"""

GEN_PROMPT = """You are the annotator for an EU AI Act question-answering benchmark (Regulation (EU) 2024/1689, state of affairs as at 1 May 2026).

Your job for ONE question: write (a) the CORRECTNESS CRITERIA an answer must satisfy, and (b) a REFERENCE ANSWER.

{fewshot}

RULES FOR THE CRITERIA
- Each criterion is ONE atomic substantive fact that a correct answer must contain. Terse. A label, not a sentence.
- If the question asks for a verdict, the FIRST criterion is the bare verdict word ("Yes" / "No").
- Typically 2 or 3 criteria. Use 4-5 only when the question explicitly asks to enumerate several things. NEVER more than 6.
- Criteria must be things the QUESTION ACTUALLY ASKS FOR. Do not add a criterion for adjacent law the question did not raise, for a definition used only in passing, or for enforcement/penalties unless the question is about enforcement or penalties. An answer that covers everything you list and nothing else should be a complete answer to exactly this question.
- Every criterion must be supported by the verbatim statutory text supplied below. Do not invent a requirement the text does not carry.

RULES FOR THE REFERENCE ANSWER
- An EXEMPLARY answer: correct, complete with respect to your criteria, and as short as it can be while still being complete.
- Target 3 to 5 sentences, roughly 550-750 characters. This is a hard style constraint - the benchmark uses this answer only to judge whether a candidate is MORE VERBOSE THAN NECESSARY, so it must itself be maximally lean.
- Plain professional regulatory prose. No headings, no bullet lists, no markdown.
- Cite provisions inline in the form "Article 13(3)" / "Annex III" as a lawyer would.
- Answer ONLY what was asked. Do not append neighbouring provisions, derogations, cross-references, or "note also that ..." material.

THE ACT'S FULL INDEX (for orientation only):
{index}

VERBATIM TEXT OF THE PROVISIONS THAT DECIDE THIS QUESTION:
{provisions}

QUESTION:
{question}

Return ONLY this JSON object, no markdown fence, no prose:
{{"criteria": ["...", "..."], "reference_answer": "..."}}"""

RECONCILE_PROMPT = """You are the lead annotator for an EU AI Act benchmark, reconciling two independent annotations of the SAME question into the final answer key.

QUESTION:
{question}

VERBATIM TEXT OF THE DECIDING PROVISIONS:
{provisions}

ANNOTATION A:
{a}

ANNOTATION B:
{b}

Produce the FINAL key:
- Keep a criterion only if it is genuinely required to answer THIS question and is supported by the verbatim text above. When the two annotators agree on a fact, keep it. When only one raised it, keep it ONLY if the question plainly demands it.
- Prefer FEWER, more atomic criteria. Typically 2-3; never more than 6. Merge near-duplicates.
- Each criterion stays a terse label, not a sentence. A verdict question keeps a bare "Yes"/"No" as its first criterion.
- For the reference answer, take the better of the two or write a better one. It must be correct, cover every final criterion, and be as SHORT as possible while complete: 3-5 sentences, roughly 550-750 characters, plain prose, no lists, answering only what was asked.

Return ONLY this JSON object, no markdown fence, no prose:
{{"criteria": ["...", "..."], "reference_answer": "..."}}"""


def provisions_block(refs: list[str], budget: int = 9000) -> str:
    """Verbatim text for the expected refs, plus each one's parent head.

    The head is included because a sub-point key like ``Article 13.3`` is
    routinely unintelligible without the paragraph that introduces it.
    """
    wanted: list[str] = []
    for r in refs:
        n = normalise_ref(r)
        if not n:
            continue
        if n not in wanted:
            wanted.append(n)
        h = ref_head(n)
        if h and h != n and h not in wanted:
            wanted.append(h)
    chunks: list[str] = []
    used = 0
    for w in wanted:
        t = get_provision_text(w)
        if not t:
            continue
        room = max(0, budget - used)
        if room < 200:
            break
        body = t if len(t) <= room else t[:room] + " [...]"
        chunks.append(f"--- {w} ---\n{body}")
        used += len(body)
    return "\n\n".join(chunks) if chunks else "(no verbatim text available)"


def load_inputs() -> list[dict]:
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    mg: dict[str, dict] = {}
    for line in MINGOLD.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            row = json.loads(line)
            mg[row["id"]] = row
    out = []
    for q in batch:
        g = mg.get(q["id"], {})
        expected = [] if g.get("unstable") else list(g.get("expected") or [])
        out.append(
            {
                "id": q["id"],
                "question": q["question"],
                "expected_refs": expected,
                # kept only so the provisions block has something to ground on
                # when the minimal-gold row was unstable
                "_fallback_refs": list(g.get("pass1_heads") or []),
            }
        )
    return out


def build_one(row: dict) -> dict:
    refs = row["expected_refs"] or row["_fallback_refs"]
    prov = provisions_block(refs)
    gen = GEN_PROMPT.format(
        fewshot=FEWSHOT, index=TITLE_INDEX, provisions=prov, question=row["question"]
    )
    a_raw = call(gen)
    b_raw = call(gen)
    a, b = parse_json(a_raw), parse_json(b_raw)

    def _norm(d) -> dict:
        if not isinstance(d, dict):
            return {"criteria": [], "reference_answer": ""}
        crit = [str(c).strip() for c in (d.get("criteria") or []) if str(c).strip()]
        return {"criteria": crit[:6], "reference_answer": str(d.get("reference_answer") or "").strip()}

    a, b = _norm(a), _norm(b)
    final_raw = call(
        RECONCILE_PROMPT.format(
            question=row["question"],
            provisions=prov,
            a=json.dumps(a, ensure_ascii=False, indent=1),
            b=json.dumps(b, ensure_ascii=False, indent=1),
        )
    )
    final = _norm(parse_json(final_raw))
    if not final["criteria"]:
        final = a if a["criteria"] else b
    unstable = abs(len(a["criteria"]) - len(b["criteria"])) > 1 or not final["criteria"]
    return {
        "id": row["id"],
        "question": row["question"],
        "expected_refs": row["expected_refs"],
        "criteria": final["criteria"],
        "reference_answer": final["reference_answer"],
        "criteria_unstable": bool(unstable),
        "_sample_a_n": len(a["criteria"]),
        "_sample_b_n": len(b["criteria"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default=None, help="comma-separated ids")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:  # noqa: BLE001
                    pass

    rows = load_inputs()
    if a.only:
        keep = {s.strip() for s in a.only.split(",")}
        rows = [r for r in rows if r["id"] in keep]
    rows = [r for r in rows if r["id"] not in done]
    if a.limit:
        rows = rows[: a.limit]
    if not rows:
        print(f"nothing to do; {len(done)} rows already in {out_path}")
        return 0

    print(f"building {len(rows)} rows via {MODEL} at {URL} ({len(done)} already done)")
    n_ok = 0
    with out_path.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(_safe_build, rows):
            if res is None:
                continue
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
            n_ok += 1
            flag = " UNSTABLE" if res.get("criteria_unstable") else ""
            print(
                f"  {res['id']}  {len(res['criteria'])} criteria  "
                f"{len(res['reference_answer'])} chars{flag}"
            )
    print(f"wrote {n_ok} rows -> {out_path}")
    return 0


def _safe_build(row: dict) -> dict | None:
    try:
        return build_one(row)
    except Exception as exc:  # noqa: BLE001
        print(f"  {row['id']} FAILED: {exc}")
        return None


if __name__ == "__main__":
    raise SystemExit(main())

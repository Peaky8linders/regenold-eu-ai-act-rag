"""R386 - build a MINIMAL-GOLD probe set: the expected reference set as the
EVALUATOR defines it, at the grain the operative rule actually sits at.

WHY THIS EXISTS
---------------
Every reference-precision lever built in this repo fails hard rule #8, and R385
established why: `gold_dropped_head` is scored against our own hand-built probe
gold, which is NOT minimal. The official judge calls the same references
over-citation that our gate calls required. Four independent detectors
(applicability, question-role, discourse, retrieval-provenance) all hit the same
wall. The blocker is the INSTRUMENT, not the lever.

So: build the instrument. Per question, ask sonnet-5 -- grounded on verbatim Act
text -- for the MINIMAL set of provisions a correct answer must cite, at the
grain the operative rule sits at.

CONTAMINATION CONTROL
---------------------
The probe sees the QUESTION ONLY. It never sees our answer, our references, the
July-7 references, or any judge output. It cannot rediscover our own citations.

VALIDATION -- and this is the part that makes it an instrument rather than
another opinion. The official report's appendix prints the evaluator's OWN
expected sets for five questions. Those five map into this batch:

    rg_046 -> ['Article 13.3']                  rg_018 -> ['Article 7.1']
    rg_024 -> ['Article 6.2', 'Annex III']      rg_105 -> ['Article 111.1', 'Annex X']
    rg_075 -> ['Article 50.4']

If the probe reproduces those, it is measuring what the evaluator measures.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\Claude Projects\regenold-eu-ai-act-rag"
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
sys.path.insert(0, REPO)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(REPO, ".env"))

from app.data.official_eu_ai_act import (  # noqa: E402
    OFFICIAL_ANNEX_TITLES,
    OFFICIAL_ARTICLE_TITLES,
)
from app.data.provision_text import get_provision_text  # noqa: E402

URL = "https://wrapper.antifragile-ai.net/v1/chat/completions"
MODEL = "claude-sonnet-5"
SEP = chr(10) * 2
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mingold_rows.jsonl")

_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Authorization": "Bearer dummy",
}
if os.getenv("CF_ACCESS_CLIENT_ID"):
    _HDRS["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
    _HDRS["CF-Access-Client-Secret"] = os.environ["CF_ACCESS_CLIENT_SECRET"]


def call(prompt: str, max_tokens: int = 900, timeout: float = 180.0) -> str:
    body = json.dumps(
        {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
         "max_tokens": max_tokens}
    ).encode()
    req = urllib.request.Request(URL, data=body, headers=_HDRS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]


def _sort_key(k: str):
    if k.startswith("Article "):
        return (0, int(k.split()[1]))
    romans = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
    r = k.split()[1]
    return (1, romans.index(r) if r in romans else 99)


TITLE_INDEX = "\n".join(
    f"{k} - {v}" for k, v in sorted(
        {**OFFICIAL_ARTICLE_TITLES, **OFFICIAL_ANNEX_TITLES}.items(), key=lambda kv: _sort_key(kv[0])
    )
)

P1 = """You are annotating an EU AI Act benchmark. For the question below, name the MINIMAL set of provisions that a correct answer MUST cite.

MINIMAL means: the provisions that actually decide the question. Not context, not neighbouring law, not the provision that defines a term used in passing, not the enforcement or penalty article unless the question asks about enforcement or penalties. A benchmark annotator writing an answer key -- typically ONE provision, sometimes two, rarely three.

Here is the complete index of the Act's articles and annexes:

{index}

QUESTION:
{question}

Return ONLY a JSON array of head-level provision names, most important first, e.g. ["Article 50"] or ["Article 6", "Annex III"]. No prose, no markdown fence."""

P2 = """You are annotating an EU AI Act benchmark answer key. A previous step decided that this question is decided by the provision(s) below. Your job is to pin the EXACT GRAIN: the specific paragraph or sub-point that carries the operative rule.

QUESTION:
{question}

VERBATIM TEXT OF THE CANDIDATE PROVISION(S):
{texts}

Rules for the grain:
- If ONE numbered paragraph decides the question, cite that paragraph: "Article 50.4".
- If one lettered sub-point within a paragraph decides it, cite that: "Article 5.1.f".
- If the question is about the provision AS A WHOLE (its subject matter, its scope, "what is X about"), cite the bare head: "Annex III".
- Do NOT cite a paragraph and its own parent as two separate entries. Pick one.
- Drop any candidate provision that does not in fact decide the question.

Return ONLY a JSON array of the final minimal expected references, e.g. ["Article 13.3"]. No prose, no markdown fence."""


def parse_arr(s: str) -> list[str]:
    s = s.strip()
    m = re.search(r"\[.*?\]", s, re.S)
    if not m:
        return []
    try:
        v = json.loads(m.group(0))
    except Exception:
        return []
    return [str(x).strip() for x in v if isinstance(x, (str,))][:5]


_HEAD_RE = re.compile(r"^(Article\s+\d{1,3}|Annex\s+[IVXL]+)", re.I)


def head_of(ref: str) -> str | None:
    m = _HEAD_RE.match(ref.strip())
    if not m:
        return None
    h = m.group(1)
    return "Article " + h.split()[1] if h.lower().startswith("article") else "Annex " + h.split()[1].upper()


LOCK = threading.Lock()
DONE: set[str] = set()
if os.path.exists(OUT):
    for line in open(OUT, encoding="utf-8"):
        try:
            DONE.add(json.loads(line)["id"])
        except Exception:
            pass


def work(row: dict) -> None:
    if row["id"] in DONE:
        return
    q = row["question"]
    rec: dict = {"id": row["id"], "question": q}
    try:
        heads = [h for h in (head_of(x) for x in parse_arr(call(P1.format(index=TITLE_INDEX, question=q), 300))) if h]
        heads = list(dict.fromkeys(heads))[:3]
        rec["pass1_heads"] = heads
        if not heads:
            rec["expected"] = []
        else:
            blocks = []
            for h in heads:
                t = get_provision_text(h) or ""
                blocks.append("### " + h + chr(10) + t[:6000])
            # Pass 2 is sampled TWICE and INTERSECTED. Measured on the five
            # validation rows: the head and its primary coordinate are stable
            # across draws, but a SECOND entry is noise, and on rg_075 even the
            # coordinate drifted (50.4 -> 50.2). Three draws of rg_018 gave
            # ['Article 7.1'], ['Article 7.1','Annex III'] and
            # ['Article 7.1','Article 7.2'] against an official key of
            # ['Article 7.1']. Intersecting two draws keeps what both agree on,
            # which is exactly the right bias for a MINIMAL gold set.
            prompt2 = P2.format(question=q, texts=SEP.join(blocks))
            s_a = parse_arr(call(prompt2, 300))
            s_b = parse_arr(call(prompt2, 300))
            rec["sample_a"], rec["sample_b"] = s_a, s_b
            both = [r for r in s_a if r in set(s_b)]
            # Two draws sharing nothing means the grain is genuinely unsettled;
            # record it rather than inventing a key.
            rec["expected"] = both
            rec["unstable"] = not both
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    with LOCK:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("%-8s %-28s %s" % (rec["id"], str(rec.get("pass1_heads")), rec.get("expected", rec.get("error"))), flush=True)


if __name__ == "__main__":
    rows = json.load(open(os.path.join(REPO, "evals/regenold/_official_batch_20260707.json"), encoding="utf-8"))
    only = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "all" else None
    if only:
        rows = [r for r in rows if r["id"] in only]
    todo = [r for r in rows if r["id"] not in DONE]
    print("to do: %d rows (%d already captured)" % (len(todo), len(DONE)), flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(work, todo))
    print("DONE")

"""R386 - score every reference lever against the MINIMAL-GOLD probe set.

This is the measurement the whole line of work has been blocked on. R385
established that our probe gold is not minimal, so `gold_dropped_head` fights
the official Ref Conciseness axis and every precision lever fails it BY
CONSTRUCTION. Four independent detectors then hit the same wall. The fix was
never another detector; it was to build gold the evaluator would recognise.

Three axes, scored the way the OFFICIAL rubric describes them rather than the
way this repo's internal metrics do:

  Ref Loose   F1 at Article/Annex HEAD level        ("at the level of Article
                                                     and Annex numbers")
  Ref Strict  F1 at FULL grain, sub-points included ("includes subpoints")
              -- note this does NOT head-project, unlike
              evals.bench.metrics.reference_correctness_strict, which calls
              article_heads on the prediction and is therefore blind to grain.
  Ref Conc    min(1, |expected| / |provided|)       -- a pure COUNT ratio (R381)

and the hard-rule-#8 instrument, gold_dropped_head, recomputed against MINIMAL
gold instead of our non-minimal probe gold.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys

from pathlib import Path
DIR = Path(__file__).resolve().parent
REPO = str(DIR.parents[2])
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
sys.path.insert(0, REPO)
sys.path.insert(0, str(DIR))

from deepen_probe import deepen_list  # noqa: E402

HEAD = re.compile(r"^(Article\s+\d{1,3}|Annex\s+[IVXL]+)")


def norm(r: str) -> str:
    """'Article 26(6)' / 'Article 3.19 (definition of ...)' -> 'Article 26.6'."""
    r = (r or "").strip()
    r = re.sub(r"\s*\(([0-9]+)\)", r".\1", r)
    r = re.sub(r"\s*\(([a-z])\)", r".\1", r)
    r = re.sub(r"\s*\(.*?\)\s*$", "", r).strip()
    return re.sub(r"\s+", " ", r)


def head(r: str) -> str:
    m = HEAD.match(norm(r))
    return m.group(1) if m else norm(r)


def f1(pred: set, gold: set) -> float:
    if not gold and not pred:
        return 1.0
    if not gold or not pred:
        return 0.0
    tp = len(pred & gold)
    if not tp:
        return 0.0
    p, rc = tp / len(pred), tp / len(gold)
    return 2 * p * rc / (p + rc)


gold_rows = {}
for line in open(DIR / "minimal-gold-probe-set-n110.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r.get("expected"):
        gold_rows[r["id"]] = [norm(x) for x in r["expected"]]

live = {r["id"]: r for r in json.load(
    open(os.path.join(REPO, "docs/measurements/r384/r384-reeval-round-2026-07-2324-live.json"), encoding="utf-8"))}

ROWS = [(rid, live[rid]["question"], live[rid]["now"]["ans"],
         [norm(x) for x in live[rid]["now"]["refs"]], g)
        for rid, g in gold_rows.items() if rid in live]


def arm(fn, label):
    L, S, C, drop = [], [], [], 0
    counts, changed = [], 0
    for _rid, q, a, refs, gold in ROWS:
        out = fn(list(refs), q, a)
        changed += sum(1 for x in out if x not in refs)
        counts.append(len(out))
        gset, pset = set(gold), set(out)
        gh, ph = {head(x) for x in gold}, {head(x) for x in out}
        L.append(f1(ph, gh))
        S.append(f1(pset, gset))
        C.append(min(1.0, len(gold) / max(1, len(out))))
        drop += len(gh - ph)
    print("%-30s  RefLoose %5.1f   RefStrict %5.1f   RefConc %5.1f   refs/row %4.2f   gold_dropped_head %3d   changed %3d"
          % (label, 100 * statistics.mean(L), 100 * statistics.mean(S),
             100 * statistics.mean(C), statistics.mean(counts), drop, changed))
    return 100 * statistics.mean(S), drop


print("MINIMAL-GOLD probe set: %d rows with a stable key (of %d built)"
      % (len(ROWS), len(gold_rows)))
print("gold refs/row %.2f   sub-point grain %.0f%%"
      % (statistics.mean([len(g) for _, _, _, _, g in ROWS]),
         100 * sum(1 for _, _, _, _, g in ROWS for x in g if "." in x)
         / sum(len(g) for _, _, _, _, g in ROWS)))
print("our shipped refs/row %.2f   sub-point grain %.0f%%"
      % (statistics.mean([len(r) for _, _, _, r, _ in ROWS]),
         100 * sum(1 for _, _, _, r, _ in ROWS for x in r if "." in x)
         / sum(len(r) for _, _, _, r, _ in ROWS)))
print("=" * 150)
base_s, base_d = arm(lambda r, q, a: r, "OFF (as shipped live)")
new_s, new_d = arm(lambda r, q, a: deepen_list(r, q, a), "R386 grain deepener")
print("=" * 150)
print("Ref Strict %+.1f pp   |   hard rule #8 delta %+d gold heads -> %s"
      % (new_s - base_s, new_d - base_d, "PASS" if new_d <= base_d else "FAIL"))

# --- THE RE-TEST THAT THE INSTRUMENT FIX EXISTS FOR ------------------------
# R385's question-relevance prune was REJECTED because it dropped 19 gold heads
# at its best threshold -- against our own NON-MINIMAL probe gold. If that gold
# was the problem rather than the lever, the same prune scored against a minimal
# key should look completely different. This is the decisive re-test.
os.environ["REGENOLD_QREL_PRUNE"] = "1"
from app.routes.regenold import _qrel_prune_references  # noqa: E402

print()
print("RE-TEST: the levers this repo REJECTED, now scored against MINIMAL gold")
print("-" * 150)
arm(lambda r, q, a: _qrel_prune_references(list(r), q, a), "R385 qrel prune (rejected)")
arm(lambda r, q, a: _qrel_prune_references(deepen_list(r, q, a), q, a),
    "R386 deepen + R385 prune")


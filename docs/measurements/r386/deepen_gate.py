"""R386 - the grain deepener against HARD RULE #8, scored with the REAL metric.

R385's lesson: do not argue a gate, run it. This replays the deepener over the
full live capture of the gold-bearing probe corpus (n=129, the same corpus and
the same zero-variance design that REJECTED the R381 wire cap and the R385
question-relevance prune) and scores it with `evals.bench.metrics`, not with a
hand-rolled head count.
"""
from __future__ import annotations

import ast
import json
import os
import statistics
import sys

REPO = r"D:\Claude Projects\regenold-eu-ai-act-rag"
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deepen_probe import deepen_list  # noqa: E402
from evals.bench.metrics import (  # noqa: E402
    gold_dropped_head,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

rows = json.load(open("probe_live_capture.json", encoding="utf-8"))


def lit(v):
    return ast.literal_eval(v) if isinstance(v, str) else v


def arm(fn, label):
    drop = 0
    loose, strict, conc = [], [], []
    n_deep = 0
    counts = []
    for r in rows:
        refs, gold = lit(r["refs"]), lit(r["gold"])
        out = fn(refs, r["question"], r["answer"])
        n_deep += sum(1 for x in out if x not in refs)
        counts.append(len(out))
        drop += gold_dropped_head(out, gold)["dropped_count"]
        loose.append(reference_correctness_loose(out, gold))
        strict.append(reference_correctness_strict(out, gold))
        conc.append(reference_conciseness(out, gold))
    print("%-34s gold_dropped_head %3d   ref_loose %.4f   ref_strict %.4f   ref_conc %.4f   refs/row %.2f   changed %d"
          % (label, drop, statistics.mean(loose), statistics.mean(strict),
             statistics.mean(conc), statistics.mean(counts), n_deep))
    return drop


print("live capture of the gold-bearing probe corpus, n=%d rows" % len(rows))
print("=" * 132)
base = arm(lambda refs, q, a: list(refs), "OFF (baseline)")
new = arm(lambda refs, q, a: deepen_list(refs, q, a), "ON  (grain deepener)")
print("=" * 132)
d = new - base
print("HARD RULE #8 delta: %+d gold heads  ->  %s" % (d, "PASS" if d <= 0 else "FAIL"))

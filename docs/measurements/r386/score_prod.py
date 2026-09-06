"""R386 - score the PRODUCTION functions, not a scratchpad copy of them.

An earlier version of this measurement mirrored the route's logic into the
probe file and a heredoc silently ate the `\\b` word boundaries out of the
overview regex, so the two diverged. This imports what actually ships.

Both gates, both instruments, one script:
  GATE 1  our own gold-bearing probe corpus, n=129, scored with
          evals.bench.metrics -- the instrument that REJECTED the R381 wire cap
          and the R385 prune.
  GATE 2  the R386 minimal-gold probe set, n=99 stable keys, scored the way the
          OFFICIAL rubric describes the axes (strict at FULL grain, no
          head-projection).
"""
from __future__ import annotations

import ast
import json
import os
import re
import statistics
import sys

REPO = r"D:\Claude Projects\regenold-eu-ai-act-rag"
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
sys.path.insert(0, REPO)

from app.routes.regenold import _deepen_ref_grain  # noqa: E402
from evals.bench.metrics import (  # noqa: E402
    gold_dropped_head,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

HEAD = re.compile(r"^(Article\s+\d{1,3}|Annex\s+[IVXL]+)")


def norm(r: str) -> str:
    r = re.sub(r"\s*\(([0-9]+)\)", r".\1", (r or "").strip())
    r = re.sub(r"\s*\(([a-z])\)", r".\1", r)
    return re.sub(r"\s*\(.*?\)\s*$", "", r).strip()


def head(r: str) -> str:
    m = HEAD.match(norm(r))
    return m.group(1) if m else norm(r)


def f1(p: set, g: set) -> float:
    if not g and not p:
        return 1.0
    if not g or not p:
        return 0.0
    tp = len(p & g)
    if not tp:
        return 0.0
    pr, rc = tp / len(p), tp / len(g)
    return 2 * pr * rc / (pr + rc)


def on(v: str) -> None:
    os.environ["REGENOLD_REF_GRAIN_DEEPEN"] = v


# ---- GATE 1 -----------------------------------------------------------------
rows = json.load(open(os.path.join(REPO, "docs/measurements/r386/gold-bearing-probe-live-capture-n129.json"), encoding="utf-8"))
print("GATE 1 - our own gold-bearing probe corpus, n=%d, scored with evals.bench.metrics" % len(rows))
print("-" * 140)
res1 = {}
for label, val in (("OFF", "0"), ("ON  (default)", "1")):
    on(val)
    drop, L, S, C, cnt, ch = 0, [], [], [], [], 0
    for r in rows:
        refs = ast.literal_eval(r["refs"]) if isinstance(r["refs"], str) else r["refs"]
        gold = ast.literal_eval(r["gold"]) if isinstance(r["gold"], str) else r["gold"]
        out = _deepen_ref_grain(list(refs), r["question"], r["answer"])
        ch += sum(1 for x in out if x not in refs)
        cnt.append(len(out))
        drop += gold_dropped_head(out, gold)["dropped_count"]
        L.append(reference_correctness_loose(out, gold))
        S.append(reference_correctness_strict(out, gold))
        C.append(reference_conciseness(out, gold))
    res1[label] = drop
    print("%-16s gold_dropped_head %3d   ref_loose %.4f   ref_strict %.4f   ref_conc %.4f   refs/row %.2f   changed %3d"
          % (label, drop, statistics.mean(L), statistics.mean(S), statistics.mean(C), statistics.mean(cnt), ch))
d1 = res1["ON  (default)"] - res1["OFF"]
print("HARD RULE #8 delta: %+d  ->  %s" % (d1, "PASS" if d1 <= 0 else "FAIL"))

# ---- GATE 2 -----------------------------------------------------------------
gold = {}
for line in open(os.path.join(REPO, "docs/measurements/r386/minimal-gold-probe-set-n110.jsonl"), encoding="utf-8"):
    r = json.loads(line)
    if r.get("expected"):
        gold[r["id"]] = [norm(x) for x in r["expected"]]
live = {r["id"]: r for r in json.load(open(os.path.join(REPO, "docs/measurements/r384/r384-reeval-round-2026-07-2324-live.json"), encoding="utf-8"))}
ROWS = [(live[k]["question"], live[k]["now"]["ans"], [norm(x) for x in live[k]["now"]["refs"]], g)
        for k, g in gold.items() if k in live]

print()
print("GATE 2 - the R386 minimal-gold probe set, n=%d, scored as the OFFICIAL rubric describes the axes" % len(ROWS))
print("-" * 140)
res2 = {}
for label, val in (("OFF", "0"), ("ON  (default)", "1")):
    on(val)
    L, S, C, drop, cnt, ch = [], [], [], 0, [], 0
    for q, a, refs, g in ROWS:
        out = _deepen_ref_grain(list(refs), q, a)
        ch += sum(1 for x in out if x not in refs)
        cnt.append(len(out))
        L.append(f1({head(x) for x in out}, {head(x) for x in g}))
        S.append(f1({norm(x) for x in out}, set(g)))
        C.append(min(1.0, len(g) / max(1, len(out))))
        drop += len({head(x) for x in g} - {head(x) for x in out})
    res2[label] = (100 * statistics.mean(S), drop)
    print("%-16s RefLoose %5.1f   RefStrict %5.1f   RefConc %5.1f   refs/row %.2f   gold_dropped_head %2d   changed %3d"
          % (label, 100 * statistics.mean(L), 100 * statistics.mean(S), 100 * statistics.mean(C),
             statistics.mean(cnt), drop, ch))
ds = res2["ON  (default)"][0] - res2["OFF"][0]
d2 = res2["ON  (default)"][1] - res2["OFF"][1]
print("Ref Strict %+.1f pp   |   HARD RULE #8 delta: %+d  ->  %s" % (ds, d2, "PASS" if d2 <= 0 else "FAIL"))
on("1")

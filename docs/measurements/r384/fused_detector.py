"""Fused reference-precision detector, scored held-out on the live round.

SIGNALS (all computable at emission time, none reads the judge's labels):
  Q-REL   the reference's rank in the QUESTION's own dense ranking. This is the
          repo's existing retrieval index reused as a PRECISION filter instead of
          a recall one. Measured separation: wrong refs median rank 17, right
          refs median rank 4.
  PROSE   where the final answer FIRST names the provision, as a fraction through
          the answer. Right refs median 0.137, wrong refs 0.552 — the R367
          "answer, then append adjacent-but-unasked law" shape.
  ANCHOR  the question names the provision outright. Never dropped.

Fusion rather than either alone, because the two signals fail on different rows:
Q-REL misses a provision the question implies without matching its vocabulary,
PROSE misses one the model states up front and wrongly.

SCORING is the conservative rule from refprec_sim: a row passes only when it
keeps no WRONG ref, has no originally-missing ref, AND drops no RIGHT ref.

HELD-OUT by construction: thresholds are fitted on one half of the rows and
scored on the other, both directions, and the reported number is the mean of the
two out-of-fold scores.
"""
import json
import os
import re
import statistics
import sys

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
sys.path.insert(0, r"D:\Claude Projects\regenold-eu-ai-act-rag")

from app.engines import turboquant_index as T  # noqa: E402

REPO = r"D:\Claude Projects\regenold-eu-ai-act-rag"
j = json.load(open(os.path.join(REPO, "docs/measurements/r384/grounded-r384-now-sonnet5.json"), encoding="utf-8"))
live = {r["id"]: r for r in json.load(
    open(os.path.join(REPO, "docs/measurements/r384/r384-reeval-round-2026-07-2324-live.json"), encoding="utf-8"))}

COORD = re.compile(r"(?:Article|Art\.?)\s*(\d+)|Annex\s+([IVXLC]+)", re.I)


def head_internal(ref: str) -> str:
    ref = ref.strip()
    if ref.startswith("Article "):
        return "Art. " + ref[len("Article "):].split(".")[0]
    if ref.startswith("Annex "):
        return "Annex " + ref[len("Annex "):].split(".")[0]
    return ref


def first_mention(ans: str, ref: str):
    m = re.match(r"(Article|Annex)\s+([\w.]+)", ref)
    if not m:
        return None
    kind, num = m.group(1), m.group(2).split(".")[0]
    pat = (r"Article\s+0*%s\b" % re.escape(num)) if kind == "Article" else (r"Annex\s+%s\b" % re.escape(num))
    s = re.search(pat, ans)
    return (s.start() / max(1, len(ans))) if s else None


QC: dict[str, dict] = {}


def qrank(question: str) -> dict[str, int]:
    if question not in QC:
        try:
            ranked = sorted(T.dense_top_k(question, k=300), key=lambda kv: -kv[1])
        except Exception:
            ranked = []
        QC[question] = {k: i for i, (k, _) in enumerate(ranked)}
    return QC[question]


ROWS = []
for r in j["rows"]:
    v = (r.get("verdicts") or {}).get("reference_correctness") or {}
    if v.get("judge_error"):
        continue
    src = live.get(r["id"])
    if not src:
        continue
    q, ans = src["question"], src["now"]["ans"]
    rk = qrank(q)
    nums = {m.group(1) for m in COORD.finditer(q) if m.group(1)}
    anx = {(m.group(2) or "").upper() for m in COORD.finditer(q) if m.group(2)}
    feats = {}
    for ref in src["now"]["refs"]:
        m = re.match(r"(Article|Annex)\s+([\w.]+)", ref)
        head = m.group(2).split(".")[0] if m else ""
        anchor = bool(m) and ((m.group(1) == "Article" and head in nums)
                              or (m.group(1) == "Annex" and head.upper() in anx))
        feats[ref] = {
            "rank": rk.get(head_internal(ref), 999),
            "pos": first_mention(ans, ref),
            "anchor": anchor,
        }
    ROWS.append({"id": r["id"], "refs": list(src["now"]["refs"]),
                 "wrong": set(v.get("wrong_refs") or []),
                 "missing": list(v.get("missing_refs") or []), "f": feats})


def keep_fn(row, ref, max_rank, max_pos, floor):
    f = row["f"][ref]
    if f["anchor"]:
        return True
    good_rank = f["rank"] < max_rank
    p = f["pos"]
    good_pos = (p is not None and p <= max_pos)
    if good_rank and good_pos:
        return True
    if not good_rank and not good_pos:
        # both signals say drop — unless we would fall under the floor
        kept_strong = sum(
            1 for x in row["refs"]
            if row["f"][x]["anchor"]
            or (row["f"][x]["rank"] < max_rank and row["f"][x]["pos"] is not None
                and row["f"][x]["pos"] <= max_pos))
        return kept_strong < floor
    # exactly one signal fires: keep it (fusion is deliberately lenient here)
    return True


def score(rows, max_rank, max_pos, floor, label=None):
    tot = wrongkept = 0
    passes = 0
    wd = rd = 0
    counts = []
    for row in rows:
        kept = [r for r in row["refs"] if keep_fn(row, r, max_rank, max_pos, floor)]
        if not kept:
            kept = row["refs"][:1]
        dropped = [r for r in row["refs"] if r not in kept]
        wd += sum(1 for r in dropped if r in row["wrong"])
        rdrop = sum(1 for r in dropped if r not in row["wrong"])
        rd += rdrop
        wk = sum(1 for r in kept if r in row["wrong"])
        tot += len(kept)
        wrongkept += wk
        counts.append(len(kept))
        if wk == 0 and not row["missing"] and rdrop == 0:
            passes += 1
    prec = 1 - wrongkept / max(1, tot)
    rc = 100 * statistics.mean([min(1.0, 1.4 / max(1, c)) for c in counts])
    if label:
        print("%-40s pass %5.3f  prec %5.3f  refs/row %4.2f  RefConc %4.1f  dropped %2dW/%2dR"
              % (label, passes / len(rows), prec, statistics.mean(counts), rc, wd, rd))
    return passes / len(rows)


GRID = [(mr, mp, fl) for mr in (5, 8, 10, 12, 15, 20)
        for mp in (0.40, 0.50, 0.60, 0.70, 0.80)
        for fl in (1, 2)]

print("live round, n=%d judged rows" % len(ROWS))
print("=" * 96)
score(ROWS, 999, 1.01, 1, "BASELINE (ship everything)")
print()

# --- held-out: fit on fold A, score fold B, and vice versa ---
A = [r for i, r in enumerate(ROWS) if i % 2 == 0]
B = [r for i, r in enumerate(ROWS) if i % 2 == 1]
outs = []
for fit, test, name in ((A, B, "fit A -> score B"), (B, A, "fit B -> score A")):
    best = max(GRID, key=lambda g: score(fit, *g))
    s = score(test, *best)
    outs.append(s)
    print("%-18s best params rank<%-3d pos<=%.2f floor=%d   OUT-OF-FOLD pass %.3f"
          % (name, best[0], best[1], best[2], s))
print()
print("HELD-OUT MEAN: %.3f" % statistics.mean(outs))
print()

# --- in-sample best, reported as such, for the shipping threshold ---
best_all = max(GRID, key=lambda g: score(ROWS, *g))
print("in-sample best params: rank<%d pos<=%.2f floor=%d" % best_all)
score(ROWS, *best_all, label="FUSED (in-sample best)")
print()
print("for reference:")
score(ROWS, 999, 0.50, 2, "  prose-only (previous best)")
score(ROWS, 10, 1.01, 2, "  q-relevance-only rank<10")

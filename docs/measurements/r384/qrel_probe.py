"""Is a shipped reference's relevance TO THE QUESTION a precision signal?

The insight this tests: citation faithfulness is 0.96, i.e. the wrong references
DO support sentences in our answer. So they are not wrong relative to the answer
— they are wrong relative to the QUESTION. The answer drifted, and the citations
followed it faithfully.

If that is right, then scoring each emitted reference against the QUESTION (not
the answer, not the retrieved set) should separate judged-wrong from judged-right.
Uses the repo's own dense index — the same retrieval machinery, reused as a
precision filter rather than a recall one.
"""
import json
import os
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


def wire_to_internal(ref: str) -> str:
    """'Article 13.3' -> 'Art. 13';  'Annex IV.2' -> 'Annex IV'  (index is head-level)."""
    ref = ref.strip()
    if ref.startswith("Article "):
        return "Art. " + ref[len("Article "):].split(".")[0]
    if ref.startswith("Annex "):
        return "Annex " + ref[len("Annex "):].split(".")[0]
    return ref


CACHE: dict[str, dict[str, float]] = {}


def q_scores(question: str) -> dict[str, float]:
    if question not in CACHE:
        try:
            CACHE[question] = {k: v for k, v in T.dense_top_k(question, k=300)}
        except Exception:
            CACHE[question] = {}
    return CACHE[question]


wrong_s, right_s = [], []
wrong_r, right_r = [], []
rows = 0
for r in j["rows"]:
    v = (r.get("verdicts") or {}).get("reference_correctness") or {}
    if v.get("judge_error"):
        continue
    src = live.get(r["id"])
    if not src:
        continue
    rows += 1
    sc = q_scores(src["question"])
    ranked = sorted(sc.items(), key=lambda kv: -kv[1])
    rank = {k: i for i, (k, _) in enumerate(ranked)}
    wrong = set(v.get("wrong_refs") or [])
    for ref in src["now"]["refs"]:
        key = wire_to_internal(ref)
        s = sc.get(key)
        rk = rank.get(key)
        if s is None:
            s, rk = 0.0, 999
        (wrong_s if ref in wrong else right_s).append(s)
        (wrong_r if ref in wrong else right_r).append(rk)

print("rows scored: %d" % rows)
print()
print("DENSE SIMILARITY OF THE SHIPPED REFERENCE TO THE QUESTION")
print("  WRONG refs  n=%3d   mean %.4f   median %.4f" % (len(wrong_s), statistics.mean(wrong_s), statistics.median(wrong_s)))
print("  RIGHT refs  n=%3d   mean %.4f   median %.4f" % (len(right_s), statistics.mean(right_s), statistics.median(right_s)))
print()
print("RANK OF THE REFERENCE IN THE QUESTION'S OWN DENSE RANKING (0 = best)")
print("  WRONG refs  median rank %5.1f   share in top-5: %4.1f%%   share unranked: %4.1f%%"
      % (statistics.median(wrong_r), 100 * sum(1 for x in wrong_r if x < 5) / len(wrong_r),
         100 * sum(1 for x in wrong_r if x == 999) / len(wrong_r)))
print("  RIGHT refs  median rank %5.1f   share in top-5: %4.1f%%   share unranked: %4.1f%%"
      % (statistics.median(right_r), 100 * sum(1 for x in right_r if x < 5) / len(right_r),
         100 * sum(1 for x in right_r if x == 999) / len(right_r)))
print()
for t in (5, 8, 10, 15, 20, 30):
    w = 100 * sum(1 for x in wrong_r if x < t) / len(wrong_r)
    rr = 100 * sum(1 for x in right_r if x < t) / len(right_r)
    print("  keep rank < %-3d  ->  keeps %5.1f%% of RIGHT,  %5.1f%% of WRONG   (separation %+.1f)"
          % (t, rr, w, rr - w))

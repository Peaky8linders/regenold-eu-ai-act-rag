"""R386 - can we DEEPEN a bare head reference to its operative sub-point?

WHY THIS IS THE RIGHT LEVER
---------------------------
The official report's appendix prints the evaluator's expected sets for five
questions. Seven expected references in total: FIVE of them carry sub-point
grain (Article 13.3, Article 7.1, Article 6.2, Article 111.1, Article 50.4),
two are bare heads (Annex III, Annex X). So the answer key is ~71% sub-point.

On the live round we ship 14.3% sub-point grain: 227 of 265 emitted references
are bare heads. The official rubric scores Ref Correctness Loose "at the level
of Article and Annex numbers" and Ref Correctness Strict "includes subpoints" --
and our two scores are 89.4 LOOSE against 68.3 STRICT. That 21-point spread is
the grain gap, and it is measured from the evaluator's own printed data.

WHY IT IS FREE ON THE GATE
--------------------------
Deepening REPLACES a head with its own sub-point. It never removes a provision.
  * gold_dropped_head folds both sides onto heads (metrics.py:572-574), so the
    head set is unchanged -> hard rule #8 delta is +0 BY CONSTRUCTION. (Verified
    by execution below, not argued -- R385's lesson.)
  * Ref Conciseness is min(1, |expected|/|provided|), a pure COUNT ratio, and
    the count is unchanged -> neutral.
  * Ref Loose is scored at head level and the head survives inside the leaf ->
    unchanged.
  * Ref Strict includes sub-points -> this is the axis that can only gain.
This is the same shape as parent collapse (R381, shipped default ON), not the
refuted positional-trimmer family: nothing is dropped.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

REPO = r"D:\Claude Projects\regenold-eu-ai-act-rag"
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
os.environ.setdefault("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
sys.path.insert(0, REPO)

from app.data import provision_text as PT  # noqa: E402

MIN_TOP = 3      # winning paragraph must carry at least this much overlap
MIN_MARGIN = 2   # and must beat the runner-up by at least this much

_HEAD_RE = re.compile(r"^(Article\s+(\d{1,3})|Annex\s+([IVXL]+))$")


def deepen_list(refs: list[str], question: str, answer: str) -> list[str]:
    """Apply ``deepen`` across a reference list, with the two list-level guards.

    G1 -- a head whose OWN sub-point is already on the list is left alone.
    Deepening it would guess a second coordinate for a provision the answer has
    already pinned; that cluster belongs to ``_collapse_parent_when_subpoint_cited``
    (R325/R381), which removes the redundant head for free.

    G2 -- deduplicate. Deepening can map a head onto a leaf the list already
    carries; emitting it twice would be a wire defect. Dedup only ever removes
    an EXACT duplicate, so no provision leaves the citation set.
    """
    heads_with_leaf = set()
    for r in refs:
        m = re.match(r"(Article\s+\d{1,3}|Annex\s+[IVXL]+)\.", r.strip())
        if m:
            heads_with_leaf.add(m.group(1))
    out: list[str] = []
    for r in refs:
        d = r if r.strip() in heads_with_leaf else deepen(r, question, answer)
        if d not in out:
            out.append(d)
    return out or list(refs)


def deepen(ref: str, question: str, answer: str) -> str:
    """Head -> its question-and-answer-relevant numbered paragraph.

    Pure, fail-soft, returns ``ref`` unchanged whenever the evidence is not
    clear. Never returns a different provision, only a deeper coordinate of
    the same one.
    """
    m = _HEAD_RE.match(ref.strip())
    if not m:
        return ref                       # already a sub-point, or unparseable
    try:
        body = PT.article_body(ref.strip())
        if not body:
            return ref
        units = PT._paragraphs(body) if m.group(2) else PT._annex_items(body)
        if len(units) < 2:
            return ref                   # nothing to choose between
        q_tok = PT._tokens(question)
        a_tok = PT._tokens(answer)
        if not q_tok:
            return ref
        # The QUESTION decides which rule is operative; the ANSWER is a weaker
        # corroborating vote, because the answer is what drifted in the first
        # place (citation faithfulness 0.960 with reference correctness 0.480).
        scored = sorted(
            ((n, 2 * len(q_tok & PT._tokens(t)) + len(a_tok & PT._tokens(t)))
             for n, t in units.items()),
            key=lambda x: (-x[1], x[0]),
        )
        top, second = scored[0], (scored[1] if len(scored) > 1 else (0, 0))
        if top[1] < MIN_TOP or top[1] - second[1] < MIN_MARGIN:
            return ref                   # no clear winner -- keep the head
        return "%s.%d" % (ref.strip(), top[0])
    except Exception:                    # noqa: BLE001 -- never break the route
        return ref


if __name__ == "__main__":
    j = json.load(open(os.path.join(REPO, "docs/measurements/r384/grounded-r384-now-sonnet5.json"), encoding="utf-8"))
    live = {r["id"]: r for r in json.load(
        open(os.path.join(REPO, "docs/measurements/r384/r384-reeval-round-2026-07-2324-live.json"), encoding="utf-8"))}

    OFFICIAL = {  # the evaluator's OWN printed answer keys
        "rg_046": ["Article 13.3"], "rg_018": ["Article 7.1"],
        "rg_024": ["Article 6.2", "Annex III"],
        "rg_105": ["Article 111.1", "Annex X"], "rg_075": ["Article 50.4"],
    }

    n_head = n_deep = 0
    heads_before = heads_after = 0
    right_deep = wrong_deep = 0
    per_row = {}
    for r in j["rows"]:
        v = (r.get("verdicts") or {}).get("reference_correctness") or {}
        if v.get("judge_error"):
            continue
        src = live.get(r["id"])
        if not src:
            continue
        q, ans = src["question"], src["now"]["ans"]
        wrong = set(v.get("wrong_refs") or [])
        out = []
        for ref in src["now"]["refs"]:
            d = deepen(ref, q, ans)
            out.append(d)
            if _HEAD_RE.match(ref.strip()):
                n_head += 1
                if d != ref:
                    n_deep += 1
                    (wrong_deep if ref in wrong else right_deep).__int__()
                    if ref in wrong:
                        wrong_deep += 1
                    else:
                        right_deep += 1
        per_row[r["id"]] = (list(src["now"]["refs"]), out)

        def hd(x):
            mm = re.match(r"(Article\s+\d{1,3}|Annex\s+[IVXL]+)", x.strip())
            return mm.group(1) if mm else x
        heads_before += len({hd(x) for x in src["now"]["refs"]})
        heads_after += len({hd(x) for x in out})

    print("live round, %d judged rows" % len(per_row))
    print("bare-head references: %d   deepened: %d (%.1f%%)" % (n_head, n_deep, 100 * n_deep / max(1, n_head)))
    print("  of the deepened:  %d judged-RIGHT, %d judged-WRONG" % (right_deep, wrong_deep))
    tot = sum(len(v[0]) for v in per_row.values())
    leaf_b = sum(1 for v in per_row.values() for x in v[0] if "." in x)
    leaf_a = sum(1 for v in per_row.values() for x in v[1] if "." in x)
    print("SUB-POINT COVERAGE: %.1f%% -> %.1f%%  (%d -> %d of %d refs)"
          % (100 * leaf_b / tot, 100 * leaf_a / tot, leaf_b, leaf_a, tot))
    print("HEAD SET distinct heads: %d -> %d   (hard rule #8 needs these EQUAL)" % (heads_before, heads_after))
    print("REF COUNT: %d -> %d   (Ref Conciseness needs these EQUAL)"
          % (tot, sum(len(v[1]) for v in per_row.values())))
    print()
    print("AGAINST THE EVALUATOR'S OWN FIVE PRINTED ANSWER KEYS")
    for rid, gold in OFFICIAL.items():
        if rid not in per_row:
            print("  %-8s (not in judged set)" % rid)
            continue
        before, after = per_row[rid]
        hit_b = sum(1 for g in gold if g in before)
        hit_a = sum(1 for g in gold if g in after)
        mark = "GAIN" if hit_a > hit_b else ("loss" if hit_a < hit_b else "  = ")
        print("  %-8s %s  strict-exact hits %d -> %d   gold=%s" % (rid, mark, hit_b, hit_a, gold))
        print("           before: %s" % before)
        print("           after : %s" % after)
